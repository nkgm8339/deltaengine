"""Fixed source-time result horizon finalization."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from .constants import DEFAULT_HORIZONS_SECONDS, SnapshotValidity
from .ids import flat_content_hash, snapshot_id
from .models import BigTradeEvent, BigTradeFill, ReactionZone, ResultSnapshot, ZERO
from .price_path import SourcePricePathIndex
from .reaction_zones import BPS, ReactionZoneObserver, relation_for_price
from .time_buckets import epoch_microseconds, milliseconds_between, session_id, source_key


class ResultHorizonTracker:
    def __init__(
        self,
        event: BigTradeEvent,
        zone: ReactionZone,
        observer: ReactionZoneObserver,
        price_path: SourcePricePathIndex,
        *,
        horizons_seconds: tuple[int, ...] = DEFAULT_HORIZONS_SECONDS,
        max_staleness_ms: int = 1_000,
    ) -> None:
        horizons = tuple(horizons_seconds)
        if (
            not horizons
            or tuple(sorted(set(horizons))) != horizons
            or any(not isinstance(value, int) or isinstance(value, bool) or value < 1 for value in horizons)
        ):
            raise ValueError("horizons_seconds must be unique ascending positive integers")
        if max_staleness_ms < 0:
            raise ValueError("max_staleness_ms must be non-negative")
        if event.event_id != zone.origin_event_id or observer.zone.zone_id != zone.zone_id:
            raise ValueError("event, zone, and observer identity mismatch")
        if price_path.symbol != event.symbol or price_path.venue != event.venue:
            raise ValueError("price path identity mismatch")
        self.event = event
        self.zone = zone
        self.observer = observer
        self.price_path = price_path
        self.horizons_seconds = horizons
        self.max_staleness_ms = max_staleness_ms
        self._completed: dict[int, ResultSnapshot] = {}

    def on_trade(self, current_trade: BigTradeFill) -> tuple[ResultSnapshot, ...]:
        if current_trade.symbol != self.event.symbol or current_trade.venue != self.event.venue:
            return ()
        completed: list[ResultSnapshot] = []
        for horizon in self.horizons_seconds:
            if horizon in self._completed:
                continue
            target = self.event.last_time + timedelta(seconds=horizon)
            if current_trade.event_time <= target:
                continue
            snapshot = self._build(horizon, target)
            self._completed[horizon] = snapshot
            completed.append(snapshot)
        return tuple(completed)

    def finalize_session(self) -> tuple[ResultSnapshot, ...]:
        completed: list[ResultSnapshot] = []
        for horizon in self.horizons_seconds:
            if horizon in self._completed:
                continue
            target = self.event.last_time + timedelta(seconds=horizon)
            snapshot = self._build(horizon, target, force_session=True)
            self._completed[horizon] = snapshot
            completed.append(snapshot)
        return tuple(completed)

    def restore_completed(self, snapshots: tuple[ResultSnapshot, ...]) -> None:
        """Restore already committed horizons without recomputing or publishing them."""

        for snapshot in snapshots:
            if snapshot.zone_id != self.zone.zone_id:
                raise ValueError("snapshot belongs to a different zone")
            if snapshot.horizon_seconds not in self.horizons_seconds:
                raise ValueError("snapshot horizon is not configured")
            existing = self._completed.get(snapshot.horizon_seconds)
            if existing is not None and existing.content_hash != snapshot.content_hash:
                raise ValueError("snapshot content collision during recovery")
            self._completed[snapshot.horizon_seconds] = snapshot

    def _build(
        self,
        horizon: int,
        target: datetime,
        *,
        force_session: bool = False,
    ) -> ResultSnapshot:
        price_observation = self.price_path.last_at_or_before(target)
        metrics = self.observer.metrics_at_or_before(target)
        validity = SnapshotValidity.VALID
        if session_id(target) != self.event.session_id:
            validity = SnapshotValidity.MISSING_SESSION
        elif self.price_path.gap_intersects(self.event.last_time, target):
            validity = SnapshotValidity.MISSING_SOURCE_GAP
        elif price_observation is None:
            validity = SnapshotValidity.MISSING_NO_TRADE
        else:
            source_age = milliseconds_between(price_observation.event_time, target)
            if source_age > self.max_staleness_ms:
                validity = SnapshotValidity.MISSING_STALE
        if force_session and session_id(target) != self.event.session_id:
            validity = SnapshotValidity.MISSING_SESSION

        valid = validity is SnapshotValidity.VALID and price_observation is not None
        snapshot_price = price_observation.price if valid else None
        relation = relation_for_price(self.zone, snapshot_price) if snapshot_price is not None else None
        source_age_ms = (
            milliseconds_between(price_observation.event_time, target)
            if valid and price_observation is not None
            else None
        )
        return_last = (
            (snapshot_price / self.event.last_price - 1) * BPS
            if snapshot_price is not None
            else None
        )
        return_vwap = (
            (snapshot_price / self.event.vwap - 1) * BPS
            if snapshot_price is not None
            else None
        )
        signed = (
            return_vwap * (Decimal("1") if self.event.side == "BUY" else Decimal("-1"))
            if return_vwap is not None
            else None
        )
        extrema = self.price_path.range_min_max_by_source_key(
            source_key(self.event.last_time, self.event.last_trade_id),
            (epoch_microseconds(target), 2**63 - 1),
        )
        range_min = extrema[0] if extrema is not None else self.event.last_price
        range_max = extrema[1] if extrema is not None else self.event.last_price
        payload = {
            "snapshot_id": snapshot_id(self.zone.zone_id, horizon),
            "zone_id": self.zone.zone_id,
            "horizon_seconds": horizon,
            "target_time": target,
            "snapshot_trade_id": price_observation.trade_id if valid and price_observation else None,
            "snapshot_trade_time": price_observation.event_time if valid and price_observation else None,
            "snapshot_source_age_ms": source_age_ms,
            "snapshot_price": snapshot_price,
            "relation": relation,
            "return_from_last_price_bps": return_last,
            "return_from_vwap_bps": return_vwap,
            "origin_side_signed_return_bps": signed,
            "max_above_ticks_to_horizon": max(
                ZERO, (range_max - self.zone.zone_high) / self.observer.tick_size
            ),
            "max_below_ticks_to_horizon": max(
                ZERO, (self.zone.zone_low - range_min) / self.observer.tick_size
            ),
            "touch_count_to_horizon": metrics.touch_count if metrics else 0,
            "cross_count_to_horizon": metrics.cross_count if metrics else 0,
            "linked_big_trade_count_to_horizon": metrics.linked_big_trade_count if metrics else 0,
            "inside_buy_quantity_to_horizon": metrics.inside_buy_quantity if metrics else ZERO,
            "inside_sell_quantity_to_horizon": metrics.inside_sell_quantity if metrics else ZERO,
            "validity": validity,
        }
        return ResultSnapshot(content_hash=flat_content_hash(payload), **payload)

    @property
    def completed(self) -> tuple[ResultSnapshot, ...]:
        return tuple(self._completed[horizon] for horizon in sorted(self._completed))

    @property
    def next_target_time(self) -> datetime | None:
        """Return the next incomplete source-time horizon, if any."""

        for horizon in self.horizons_seconds:
            if horizon not in self._completed:
                return self.event.last_time + timedelta(seconds=horizon)
        return None
