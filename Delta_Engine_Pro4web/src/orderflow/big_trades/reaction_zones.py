"""Reaction Zone creation, sequential observation, and event linking."""

from __future__ import annotations

from bisect import bisect_right
from datetime import datetime
from decimal import Decimal
from typing import Optional

from .constants import InteractionType, PriceRelation, ZoneLifecycle
from .ids import checkpoint_id, content_hash, interaction_id, link_id, zone_id_for_event
from .models import (
    BigTradeEvent,
    BigTradeFill,
    ReactionZone,
    ZoneEventLink,
    ZoneInteraction,
    ZoneMetricsSnapshot,
    ZoneStateCheckpoint,
    ZERO,
)
from .time_buckets import (
    epoch_microseconds,
    milliseconds_between,
    require_aware_utc,
    session_end,
    source_key,
)


BPS = Decimal("10000")


def relation_for_price(zone: ReactionZone, price: Decimal) -> PriceRelation:
    parsed = Decimal(str(price))
    if parsed < zone.zone_low:
        return PriceRelation.BELOW
    if parsed > zone.zone_high:
        return PriceRelation.ABOVE
    return PriceRelation.INSIDE


def create_reaction_zone(event: BigTradeEvent) -> ReactionZone:
    zone_id = zone_id_for_event(event.logic_version, event.event_id)
    payload = {
        "zone_id": zone_id,
        "zone_schema_version": 1,
        "origin_event_id": event.event_id,
        "zone_low": event.low_price,
        "zone_high": event.high_price,
        "zone_anchor": event.vwap,
        "zone_visual_start": event.first_time,
        "zone_source_start": event.last_time,
        "origin_last_trade_id": event.last_trade_id,
        "origin_last_price": event.last_price,
        "origin_side": event.side,
        "symbol": event.symbol,
        "venue": event.venue,
        "session_id": event.session_id,
        "logic_version": event.logic_version,
        "settings_id": event.settings_id,
        "calibration_id": event.calibration_id,
        "activation_id": event.activation_id,
        "lifecycle": ZoneLifecycle.ACTIVE,
    }
    return ReactionZone(content_hash=content_hash(payload), **payload)


class ReactionZoneObserver:
    def __init__(self, zone: ReactionZone, *, tick_size: Decimal) -> None:
        parsed_tick = Decimal(str(tick_size))
        if not parsed_tick.is_finite() or parsed_tick <= ZERO:
            raise ValueError("tick_size must be finite and positive")
        self.zone = zone
        self.tick_size = parsed_tick
        self.lifecycle = ZoneLifecycle.ACTIVE
        self.current_relation = PriceRelation.INSIDE
        self.first_exit_direction: Optional[str] = None
        self.max_price_seen = zone.origin_last_price
        self.min_price_seen = zone.origin_last_price
        self.touch_count = 0
        self.reentry_count = 0
        self.cross_count = 0
        self.linked_big_trade_count = 0
        self.linked_buy_quantity = ZERO
        self.linked_sell_quantity = ZERO
        self.inside_buy_quantity = ZERO
        self.inside_sell_quantity = ZERO
        self.inside_buy_trade_count = 0
        self.inside_sell_trade_count = 0
        self._ordinal = 0
        self._interactions: list[ZoneInteraction] = []
        self._metric_keys: list[tuple[int, int]] = []
        self._metrics: list[ZoneMetricsSnapshot] = []
        self._open_gap_id: Optional[str] = None
        self._append_interaction(
            InteractionType.ZONE_CREATED,
            zone.zone_source_start,
            zone.origin_last_trade_id,
            zone.origin_last_price,
            None,
            PriceRelation.INSIDE,
        )
        self._record_metrics(
            zone.zone_source_start,
            zone.origin_last_trade_id,
            PriceRelation.INSIDE,
        )

    @classmethod
    def restore(
        cls,
        zone: ReactionZone,
        *,
        tick_size: Decimal,
        checkpoint: ZoneStateCheckpoint,
        interactions: tuple[ZoneInteraction, ...],
        links: tuple[ZoneEventLink, ...] = (),
    ) -> "ReactionZoneObserver":
        """Restore derived runtime state without rewriting authoritative facts."""

        if checkpoint.zone_id != zone.zone_id:
            raise ValueError("checkpoint belongs to a different zone")
        if not interactions or interactions[0].interaction_type is not InteractionType.ZONE_CREATED:
            raise ValueError("recovery requires the authoritative ZONE_CREATED interaction")
        ordered = tuple(sorted(interactions, key=lambda item: item.ordinal))
        if tuple(item.ordinal for item in ordered) != tuple(range(1, len(ordered) + 1)):
            raise ValueError("zone interaction ordinals are not contiguous")
        if any(item.zone_id != zone.zone_id for item in ordered):
            raise ValueError("interaction belongs to a different zone")
        if any(item.zone_id != zone.zone_id for item in links):
            raise ValueError("link belongs to a different zone")
        if checkpoint.linked_event_count != len(links):
            raise ValueError("checkpoint linked-event count mismatch")

        restored = cls(zone, tick_size=tick_size)
        restored._interactions = list(ordered)
        restored._ordinal = ordered[-1].ordinal
        restored.current_relation = checkpoint.current_relation
        restored.first_exit_direction = checkpoint.first_exit_direction
        restored.touch_count = checkpoint.touch_count
        restored.reentry_count = sum(
            item.interaction_type
            in {InteractionType.REENTER_FROM_ABOVE, InteractionType.REENTER_FROM_BELOW}
            for item in ordered
        )
        restored.cross_count = checkpoint.cross_count
        restored.linked_big_trade_count = checkpoint.linked_event_count
        restored.linked_buy_quantity = sum(
            (item.linked_quantity for item in links if item.linked_side == "BUY"), ZERO
        )
        restored.linked_sell_quantity = sum(
            (item.linked_quantity for item in links if item.linked_side == "SELL"), ZERO
        )
        restored.inside_buy_quantity = checkpoint.inside_buy_quantity
        restored.inside_sell_quantity = checkpoint.inside_sell_quantity
        restored.inside_buy_trade_count = 0
        restored.inside_sell_trade_count = 0
        restored._open_gap_id = checkpoint.gap_epoch_id
        if any(
            item.interaction_type is InteractionType.ZONE_SESSION_CLOSED for item in ordered
        ):
            restored.lifecycle = ZoneLifecycle.SESSION_CLOSED
        elif checkpoint.gap_epoch_id is not None or any(
            item.interaction_type is InteractionType.SOURCE_GAP_STARTED for item in ordered
        ):
            restored.lifecycle = ZoneLifecycle.ACTIVE_WITH_GAP
        else:
            restored.lifecycle = ZoneLifecycle.ACTIVE
        restored._metric_keys = []
        restored._metrics = []
        latest_trade_interaction = next(
            (item for item in reversed(ordered) if item.source_trade_id is not None),
            None,
        )
        metric_time = max(
            checkpoint.source_bucket_time,
            latest_trade_interaction.source_event_time
            if latest_trade_interaction is not None
            else zone.zone_source_start,
        )
        metric_trade_id = (
            latest_trade_interaction.source_trade_id
            if latest_trade_interaction is not None
            else zone.origin_last_trade_id
        )
        assert metric_trade_id is not None
        restored._record_metrics(metric_time, metric_trade_id, checkpoint.current_relation)
        return restored

    def observe_trade(self, trade: BigTradeFill) -> tuple[ZoneInteraction, ...]:
        if trade.symbol != self.zone.symbol or trade.venue != self.zone.venue:
            return ()
        if trade.session_id != self.zone.session_id:
            return ()
        if trade.source_key <= source_key(self.zone.zone_source_start, self.zone.origin_last_trade_id):
            return ()
        if self.lifecycle is ZoneLifecycle.SESSION_CLOSED:
            return ()
        previous = self.current_relation
        current = relation_for_price(self.zone, trade.price)
        self.max_price_seen = max(self.max_price_seen, trade.price)
        self.min_price_seen = min(self.min_price_seen, trade.price)
        if current is PriceRelation.INSIDE:
            if trade.side == "BUY":
                self.inside_buy_quantity += trade.quantity
                self.inside_buy_trade_count += 1
            else:
                self.inside_sell_quantity += trade.quantity
                self.inside_sell_trade_count += 1

        before = len(self._interactions)
        if self.first_exit_direction is None and current is not PriceRelation.INSIDE:
            direction = "UP" if current is PriceRelation.ABOVE else "DOWN"
            self.first_exit_direction = direction
            distance = (
                (trade.price - self.zone.zone_high) / self.tick_size
                if direction == "UP"
                else (self.zone.zone_low - trade.price) / self.tick_size
            )
            self._append_interaction(
                InteractionType.FIRST_EXIT_UP if direction == "UP" else InteractionType.FIRST_EXIT_DOWN,
                trade.event_time,
                trade.trade_id,
                trade.price,
                previous,
                current,
                direction=direction,
                time_to_exit_ms=milliseconds_between(self.zone.zone_source_start, trade.event_time),
                distance_from_nearest_boundary_ticks=distance,
            )

        if previous is PriceRelation.ABOVE and current is PriceRelation.INSIDE:
            self.touch_count += 1
            self.reentry_count += 1
            self._append_interaction(
                InteractionType.TOUCH_FROM_ABOVE,
                trade.event_time,
                trade.trade_id,
                trade.price,
                previous,
                current,
            )
            self._append_interaction(
                InteractionType.REENTER_FROM_ABOVE,
                trade.event_time,
                trade.trade_id,
                trade.price,
                previous,
                current,
            )
        elif previous is PriceRelation.BELOW and current is PriceRelation.INSIDE:
            self.touch_count += 1
            self.reentry_count += 1
            self._append_interaction(
                InteractionType.TOUCH_FROM_BELOW,
                trade.event_time,
                trade.trade_id,
                trade.price,
                previous,
                current,
            )
            self._append_interaction(
                InteractionType.REENTER_FROM_BELOW,
                trade.event_time,
                trade.trade_id,
                trade.price,
                previous,
                current,
            )
        elif previous is PriceRelation.BELOW and current is PriceRelation.ABOVE:
            self.cross_count += 1
            self._append_interaction(
                InteractionType.CROSS_UP,
                trade.event_time,
                trade.trade_id,
                trade.price,
                previous,
                current,
                direction="UP",
            )
        elif previous is PriceRelation.ABOVE and current is PriceRelation.BELOW:
            self.cross_count += 1
            self._append_interaction(
                InteractionType.CROSS_DOWN,
                trade.event_time,
                trade.trade_id,
                trade.price,
                previous,
                current,
                direction="DOWN",
            )

        if current is not previous:
            relation_type = {
                PriceRelation.ABOVE: InteractionType.RELATION_ABOVE,
                PriceRelation.INSIDE: InteractionType.RELATION_INSIDE,
                PriceRelation.BELOW: InteractionType.RELATION_BELOW,
            }[current]
            self._append_interaction(
                relation_type,
                trade.event_time,
                trade.trade_id,
                trade.price,
                previous,
                current,
            )
        self.current_relation = current
        self._record_metrics(trade.event_time, trade.trade_id, current)
        return tuple(self._interactions[before:])

    def register_link(self, link: ZoneEventLink, *, linked_trade_id: int) -> None:
        if link.zone_id != self.zone.zone_id:
            raise ValueError("link belongs to a different zone")
        self.linked_big_trade_count += 1
        if link.linked_side == "BUY":
            self.linked_buy_quantity += link.linked_quantity
        else:
            self.linked_sell_quantity += link.linked_quantity
        self._record_metrics(link.linked_time, linked_trade_id, self.current_relation)

    def start_gap(self, gap_epoch_id: str, source_time: datetime) -> ZoneInteraction:
        if self._open_gap_id is not None:
            raise ValueError("zone already has an open source gap")
        self._open_gap_id = gap_epoch_id
        self.lifecycle = ZoneLifecycle.ACTIVE_WITH_GAP
        return self._append_interaction(
            InteractionType.SOURCE_GAP_STARTED,
            source_time,
            None,
            None,
            self.current_relation,
            self.current_relation,
            gap_epoch_id=gap_epoch_id,
        )

    def end_gap(self, gap_epoch_id: str, source_time: datetime) -> ZoneInteraction:
        if self._open_gap_id != gap_epoch_id:
            raise ValueError("gap epoch does not match the open zone gap")
        self._open_gap_id = None
        return self._append_interaction(
            InteractionType.SOURCE_GAP_ENDED,
            source_time,
            None,
            None,
            self.current_relation,
            self.current_relation,
            gap_epoch_id=gap_epoch_id,
        )

    def close_session(self) -> ZoneInteraction:
        if self.lifecycle is ZoneLifecycle.SESSION_CLOSED:
            raise ValueError("zone session is already closed")
        self.lifecycle = ZoneLifecycle.SESSION_CLOSED
        return self._append_interaction(
            InteractionType.ZONE_SESSION_CLOSED,
            session_end(self.zone.session_id),
            None,
            None,
            self.current_relation,
            self.current_relation,
        )

    def metrics_at_or_before(self, target_time: datetime) -> Optional[ZoneMetricsSnapshot]:
        position = bisect_right(
            self._metric_keys,
            (epoch_microseconds(target_time), 2**63 - 1),
        ) - 1
        return self._metrics[position] if position >= 0 else None

    def _append_interaction(
        self,
        interaction_type: InteractionType,
        source_event_time: datetime,
        source_trade_id: Optional[int],
        price: Optional[Decimal],
        previous_relation: Optional[PriceRelation],
        current_relation: Optional[PriceRelation],
        *,
        direction: Optional[str] = None,
        gap_epoch_id: Optional[str] = None,
        time_to_exit_ms: Optional[int] = None,
        distance_from_nearest_boundary_ticks: Optional[Decimal] = None,
    ) -> ZoneInteraction:
        self._ordinal += 1
        identity = source_trade_id if source_trade_id is not None else gap_epoch_id
        identifier = interaction_id(
            self.zone.zone_id,
            interaction_type.value,
            source_event_time,
            identity,
            self._ordinal,
        )
        payload = {
            "interaction_id": identifier,
            "zone_id": self.zone.zone_id,
            "interaction_type": interaction_type,
            "source_event_time": source_event_time,
            "source_trade_id": source_trade_id,
            "source_candle_id": None,
            "price": price,
            "previous_relation": previous_relation,
            "current_relation": current_relation,
            "direction": direction,
            "ordinal": self._ordinal,
            "gap_epoch_id": gap_epoch_id,
            "time_to_exit_ms": time_to_exit_ms,
            "distance_from_nearest_boundary_ticks": distance_from_nearest_boundary_ticks,
        }
        interaction = ZoneInteraction(content_hash=content_hash(payload), **payload)
        self._interactions.append(interaction)
        return interaction

    def _record_metrics(
        self,
        source_event_time: datetime,
        source_trade_id: int,
        relation: PriceRelation,
    ) -> None:
        key = source_key(source_event_time, source_trade_id)
        metrics = ZoneMetricsSnapshot(
            source_event_time=source_event_time,
            source_trade_id=source_trade_id,
            relation=relation,
            max_price_seen=self.max_price_seen,
            min_price_seen=self.min_price_seen,
            max_above_ticks=max(ZERO, (self.max_price_seen - self.zone.zone_high) / self.tick_size),
            max_below_ticks=max(ZERO, (self.zone.zone_low - self.min_price_seen) / self.tick_size),
            max_above_bps=max(ZERO, (self.max_price_seen / self.zone.zone_anchor - 1) * BPS),
            max_below_bps=max(ZERO, (1 - self.min_price_seen / self.zone.zone_anchor) * BPS),
            touch_count=self.touch_count,
            reentry_count=self.reentry_count,
            cross_count=self.cross_count,
            linked_big_trade_count=self.linked_big_trade_count,
            linked_buy_quantity=self.linked_buy_quantity,
            linked_sell_quantity=self.linked_sell_quantity,
            inside_buy_quantity=self.inside_buy_quantity,
            inside_sell_quantity=self.inside_sell_quantity,
            inside_buy_trade_count=self.inside_buy_trade_count,
            inside_sell_trade_count=self.inside_sell_trade_count,
        )
        if self._metric_keys and key < self._metric_keys[-1]:
            raise ValueError("zone metrics must be source ordered")
        if self._metric_keys and key == self._metric_keys[-1]:
            self._metrics[-1] = metrics
        else:
            self._metric_keys.append(key)
            self._metrics.append(metrics)

    @property
    def interactions(self) -> tuple[ZoneInteraction, ...]:
        return tuple(self._interactions)

    @property
    def metrics(self) -> tuple[ZoneMetricsSnapshot, ...]:
        return tuple(self._metrics)

    @property
    def first_exit_time(self) -> Optional[datetime]:
        first = next(
            (
                item
                for item in self._interactions
                if item.interaction_type
                in {InteractionType.FIRST_EXIT_UP, InteractionType.FIRST_EXIT_DOWN}
            ),
            None,
        )
        return first.source_event_time if first is not None else None


def create_zone_state_checkpoint(
    observer: ReactionZoneObserver,
    source_time: datetime,
) -> ZoneStateCheckpoint:
    normalized = require_aware_utc(source_time)
    bucket = normalized.replace(microsecond=0)
    payload = {
        "checkpoint_id": checkpoint_id(observer.zone.zone_id, bucket),
        "zone_id": observer.zone.zone_id,
        "source_bucket_time": bucket,
        "current_relation": observer.current_relation,
        "first_exit_direction": observer.first_exit_direction,
        "first_exit_time": observer.first_exit_time,
        "touch_count": observer.touch_count,
        "cross_count": observer.cross_count,
        "inside_buy_quantity": observer.inside_buy_quantity,
        "inside_sell_quantity": observer.inside_sell_quantity,
        "linked_event_count": observer.linked_big_trade_count,
        "gap_epoch_id": observer._open_gap_id,
    }
    return ZoneStateCheckpoint(content_hash=content_hash(payload), **payload)


def interval_gap(zone: ReactionZone, event: BigTradeEvent) -> Decimal:
    return max(
        ZERO,
        max(zone.zone_low, event.low_price) - min(zone.zone_high, event.high_price),
    )


def link_event_to_zone(
    zone: ReactionZone,
    event: BigTradeEvent,
    *,
    tick_size: Decimal,
    tolerance_ticks: int,
    ordinal_for_zone: int,
) -> Optional[ZoneEventLink]:
    parsed_tick = Decimal(str(tick_size))
    if parsed_tick <= ZERO or not parsed_tick.is_finite():
        raise ValueError("tick_size must be finite and positive")
    if tolerance_ticks < 0:
        raise ValueError("tolerance_ticks must be non-negative")
    if ordinal_for_zone < 1:
        raise ValueError("ordinal_for_zone must be >= 1")
    if event.event_id == zone.origin_event_id:
        return None
    if event.symbol != zone.symbol or event.venue != zone.venue or event.session_id != zone.session_id:
        return None
    if source_key(event.last_time, event.last_trade_id) <= source_key(
        zone.zone_source_start, zone.origin_last_trade_id
    ):
        return None
    gap = interval_gap(zone, event)
    if gap > parsed_tick * tolerance_ticks:
        return None
    identifier = link_id(zone.zone_id, event.event_id)
    payload = {
        "link_id": identifier,
        "zone_id": zone.zone_id,
        "origin_event_id": zone.origin_event_id,
        "linked_event_id": event.event_id,
        "linked_side": event.side,
        "linked_quantity": event.aggregate_quantity,
        "linked_low": event.low_price,
        "linked_high": event.high_price,
        "linked_time": event.last_time,
        "interval_gap_ticks": gap / parsed_tick,
        "same_as_origin_side": event.side == zone.origin_side,
        "ordinal_for_zone": ordinal_for_zone,
    }
    return ZoneEventLink(content_hash=content_hash(payload), **payload)
