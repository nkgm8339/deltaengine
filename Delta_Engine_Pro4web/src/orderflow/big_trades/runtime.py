"""Live/Replay-common Big Trades V2 orchestration.

All decisions use authoritative source time.  Storage completion is delivered
through a thread-safe acknowledgement queue, and no browser-facing record is
published before its DuckDB transaction has committed.
"""

from __future__ import annotations

import logging
import heapq
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from queue import Empty, Queue
from typing import Any, Callable, Iterable, Mapping, Optional, Protocol

from src.database.big_trades_schema import (
    BigTradeOriginStorageBatch,
    candle_observation_to_row,
    checkpoint_from_row,
    checkpoint_to_row,
    event_from_row,
    interaction_from_row,
    interaction_to_row,
    link_from_row,
    link_to_row,
    snapshot_from_row,
    snapshot_to_row,
    zone_from_row,
)
from src.database.big_trades_storage import (
    BigTradesBackgroundStorageWriter,
    CommitAck,
    CommitFuture,
)

from .activation import (
    ActivationArtifact,
    ActivationHistoryError,
    SourceConfirmedSessionTracker,
    select_historical_activation,
)
from .aggregation import ExecutionClusterAggregator, create_big_trade_event
from .artifacts import BigTradesArtifactRepository, CalibrationArtifact, SessionStatsBuilder
from .candle_observer import CandleBoundaryMismatch, ZoneCandleObserver
from .constants import (
    DEFAULT_HORIZONS_SECONDS,
    ClusterCloseReason,
    FilterMode,
    InteractionType,
    PriceRelation,
    SnapshotValidity,
    ZoneLifecycle,
)
from .filtering import AutomaticSizeFilter, decide_cluster
from .ids import canonical_json, checkpoint_id, content_hash
from .models import (
    BigTradeEvent,
    BigTradeFill,
    BigTradesSettingsSnapshot,
    ClosedCandle,
    ExecutionCluster,
    ReactionZone,
    ResultSnapshot,
    SourceGap,
    ZoneCandleObservation,
    ZoneEventLink,
    ZoneInteraction,
    ZoneStateCheckpoint,
)
from .ordering import SameMillisecondTradeOrderBuffer
from .price_path import SourcePricePathIndex
from .reaction_zones import (
    ReactionZoneObserver,
    create_reaction_zone,
    create_zone_state_checkpoint,
    link_event_to_zone,
)
from .settings import SettingsVersion
from .time_buckets import epoch_microseconds, require_aware_utc
from .zone_index import ReactionZoneBoundaryIndex
from .horizons import ResultHorizonTracker


logger = logging.getLogger("orderflow.big_trades")


class RuntimeMode(str, Enum):
    LIVE = "LIVE"
    REPLAY = "REPLAY"


class BigTradesRuntimeStatus(str, Enum):
    DISABLED = "DISABLED"
    STARTING = "STARTING"
    MANUAL_READY = "MANUAL_READY"
    AUTOMATIC_READY = "AUTOMATIC_READY"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    CALIBRATION_UNAVAILABLE = "CALIBRATION_UNAVAILABLE"
    CALIBRATION_ACTIVATION_FAILED = "CALIBRATION_ACTIVATION_FAILED"
    DEGRADED_STORAGE = "DEGRADED_STORAGE"
    DEGRADED_POINTER_CACHE = "DEGRADED_POINTER_CACHE"
    DEGRADED_SOURCE_GAP = "DEGRADED_SOURCE_GAP"
    ERROR = "ERROR"


@dataclass(frozen=True)
class ResolvedRuntimeSettings:
    snapshot: BigTradesSettingsSnapshot
    automatic_filter: Optional[AutomaticSizeFilter]


class RuntimeSettingsResolver(Protocol):
    def resolve(self, trade: BigTradeFill) -> ResolvedRuntimeSettings: ...

    def automatic_filter_for(
        self, snapshot: BigTradesSettingsSnapshot
    ) -> Optional[AutomaticSizeFilter]: ...


class FixedActivationSettingsResolver:
    """Validated fixed snapshot used by Live and fixed-fixture tests."""

    def __init__(
        self,
        settings: SettingsVersion,
        activation: ActivationArtifact,
        calibration: Optional[CalibrationArtifact] = None,
    ) -> None:
        if activation.settings_id != settings.settings_id:
            raise ValueError("activation/settings mismatch")
        if activation.calibration_id != settings.calibration_id:
            raise ValueError("activation/settings calibration mismatch")
        if settings.filter_mode is FilterMode.AUTOMATIC:
            if calibration is None or calibration.calibration_id != settings.calibration_id:
                raise ValueError("Automatic settings require their calibration")
        elif calibration is not None:
            raise ValueError("Manual settings cannot attach a calibration")
        self.settings = settings
        self.activation = activation
        self.calibration = calibration
        self._effective_key = activation.effective_key
        self._snapshot = settings.to_runtime_snapshot(activation_id=activation.activation_id)
        self._automatic = (
            AutomaticSizeFilter(calibration.calibration_id, calibration.thresholds)
            if calibration is not None
            else None
        )

    def resolve(self, trade: BigTradeFill) -> ResolvedRuntimeSettings:
        if trade.symbol != self.settings.symbol or trade.venue != self.settings.venue:
            raise ValueError("trade identity does not match fixed activation")
        if trade.source_key < self._effective_key:
            raise ActivationHistoryError("activation is not effective for source trade")
        return ResolvedRuntimeSettings(self._snapshot, self._automatic)

    def automatic_filter_for(
        self, snapshot: BigTradesSettingsSnapshot
    ) -> Optional[AutomaticSizeFilter]:
        if snapshot.settings_id != self._snapshot.settings_id:
            return None
        return self._automatic


class RecordedActivationSettingsResolver:
    """Replay resolver: selection is solely by committed effective source key."""

    def __init__(
        self,
        *,
        activations: Iterable[ActivationArtifact],
        settings: Mapping[str, SettingsVersion],
        calibrations: Mapping[str, CalibrationArtifact],
    ) -> None:
        self.activations = tuple(activations)
        self.settings = dict(settings)
        self.calibrations = dict(calibrations)
        self._automatic: dict[str, AutomaticSizeFilter] = {
            identifier: AutomaticSizeFilter(identifier, item.thresholds)
            for identifier, item in self.calibrations.items()
        }

    def resolve(self, trade: BigTradeFill) -> ResolvedRuntimeSettings:
        activation = select_historical_activation(
            self.activations,
            symbol=trade.symbol,
            venue=trade.venue,
            cluster_first_time=trade.event_time,
            cluster_first_trade_id=trade.trade_id,
        )
        settings = self.settings.get(activation.settings_id)
        if settings is None:
            raise ActivationHistoryError("REPLAY_SETTINGS_HISTORY_MISSING")
        if settings.calibration_id != activation.calibration_id:
            raise ActivationHistoryError("REPLAY_ACTIVATION_SETTINGS_MISMATCH")
        automatic = self.automatic_filter_for(
            settings.to_runtime_snapshot(activation_id=activation.activation_id)
        )
        if settings.filter_mode is FilterMode.AUTOMATIC and automatic is None:
            raise ActivationHistoryError("REPLAY_CALIBRATION_HISTORY_MISSING")
        return ResolvedRuntimeSettings(
            settings.to_runtime_snapshot(activation_id=activation.activation_id), automatic
        )

    def automatic_filter_for(
        self, snapshot: BigTradesSettingsSnapshot
    ) -> Optional[AutomaticSizeFilter]:
        if snapshot.calibration_id is None:
            return None
        return self._automatic.get(snapshot.calibration_id)


_RECORD_PRECEDENCE = {
    "EVENT_CREATED": 0,
    "ZONE_CREATED": 1,
    "ZONE_INTERACTION": 2,
    "ZONE_EVENT_LINK": 3,
    "RESULT_SNAPSHOT": 4,
    "CANDLE_OBSERVATION": 5,
    "USER_ASSESSMENT": 6,
}


@dataclass(frozen=True)
class RuntimeRecord:
    kind: str
    source_event_time: datetime
    source_trade_id: Optional[int]
    record_id: str
    content_hash: str
    payload: Mapping[str, Any]

    @property
    def sort_key(self) -> tuple[int, int, int, str]:
        return (
            epoch_microseconds(self.source_event_time),
            self.source_trade_id if self.source_trade_id is not None else 2**63 - 1,
            _RECORD_PRECEDENCE[self.kind],
            self.record_id,
        )


@dataclass
class _PendingOrigin:
    token: int
    batch: BigTradeOriginStorageBatch
    event: BigTradeEvent
    zone: ReactionZone
    records: tuple[RuntimeRecord, ...]
    dependent: dict[str, list[Any]] = field(default_factory=lambda: defaultdict(list))


@dataclass
class _PendingUpdate:
    token: int
    kind: str
    records: tuple[RuntimeRecord, ...]
    zone_ids: frozenset[str] = frozenset()
    on_success: Optional[Callable[[], None]] = None


class BigTradesRuntimeV2:
    """Deterministic runtime shared by Live and Replay adapters."""

    def __init__(
        self,
        *,
        enabled: bool,
        mode: RuntimeMode | str,
        symbol: str,
        venue: str,
        tick_size: Decimal,
        settings_resolver: Optional[RuntimeSettingsResolver] = None,
        storage_writer: Optional[BigTradesBackgroundStorageWriter] = None,
        artifact_repository: Optional[BigTradesArtifactRepository] = None,
        horizons_seconds: tuple[int, ...] = DEFAULT_HORIZONS_SECONDS,
        max_staleness_ms: int = 1_000,
        zone_capacity: int = 5_000,
        link_tolerance_ticks: int = 1,
        recent_capacity: int = 20_000,
        publication_callback: Optional[Callable[[tuple[RuntimeRecord, ...]], None]] = None,
    ) -> None:
        self.enabled = bool(enabled)
        self.mode = RuntimeMode(mode)
        if not symbol or not venue:
            raise ValueError("symbol and venue must be non-empty")
        self.symbol = symbol
        self.venue = venue
        self.tick_size = Decimal(str(tick_size))
        if not self.tick_size.is_finite() or self.tick_size <= 0:
            raise ValueError("tick_size must be finite and positive")
        if zone_capacity < 1 or recent_capacity < 1 or link_tolerance_ticks < 0:
            raise ValueError("runtime capacities/tolerance are invalid")
        if self.enabled and (settings_resolver is None or storage_writer is None):
            raise ValueError("enabled Big Trades runtime requires settings and storage")
        self.settings_resolver = settings_resolver
        self.storage_writer = storage_writer
        self.artifact_repository = artifact_repository
        self.horizons_seconds = tuple(horizons_seconds)
        self.max_staleness_ms = max_staleness_ms
        self.zone_capacity = zone_capacity
        self.link_tolerance_ticks = link_tolerance_ticks
        self.recent_capacity = recent_capacity
        self.publication_callback = publication_callback

        self.status = (
            BigTradesRuntimeStatus.STARTING if self.enabled else BigTradesRuntimeStatus.DISABLED
        )
        self.last_error: Optional[str] = None
        self.ordering = SameMillisecondTradeOrderBuffer()
        self.aggregator = ExecutionClusterAggregator()
        self.session_tracker = SourceConfirmedSessionTracker()
        self.price_path = SourcePricePathIndex(symbol=symbol, venue=venue)
        self.zone_index = ReactionZoneBoundaryIndex()
        self.candle_observer = ZoneCandleObserver(tick_size=self.tick_size)
        self.observers: dict[str, ReactionZoneObserver] = {}
        self.events_by_zone: dict[str, BigTradeEvent] = {}
        self.horizon_trackers: dict[str, ResultHorizonTracker] = {}
        self._horizon_due_heap: list[tuple[int, str]] = []
        self._committed_zones: set[str] = set()
        self._pending_origin_by_token: dict[int, _PendingOrigin] = {}
        self._pending_origin_token_by_zone: dict[str, int] = {}
        self._pending_updates: dict[int, _PendingUpdate] = {}
        self._ack_queue: Queue[tuple[int, CommitAck]] = Queue()
        self._next_token = 1
        self._dirty_checkpoints: dict[tuple[str, datetime], ZoneStateCheckpoint] = {}
        self._closed_zone_cleanup_pending: set[str] = set()
        self._recent_records: list[RuntimeRecord] = []
        self._new_publications: list[RuntimeRecord] = []
        self._stats_builder: Optional[SessionStatsBuilder] = None
        self._current_session_id: Optional[str] = None
        self._open_gap: Optional[SourceGap] = None
        self._last_processed_trade: Optional[BigTradeFill] = None
        self._previous_candle_close: Optional[Decimal] = None
        self._halted = False
        self.counters: dict[str, int] = defaultdict(
            int,
            {
                "trades_observed": 0,
                "invalid_trades": 0,
                "clusters_finalized": 0,
                "clusters_accepted": 0,
                "clusters_rejected": 0,
                "origin_batches_submitted": 0,
                "origin_batches_committed": 0,
                "origin_batches_failed": 0,
                "storage_updates_failed": 0,
                "source_gap_epochs": 0,
                "sessions_source_confirmed": 0,
                "errors": 0,
            },
        )

    def process(self, trade: BigTradeFill | Any) -> tuple[RuntimeRecord, ...]:
        if not self.enabled or self._halted:
            return ()
        if self._pending_origin_by_token or self._pending_updates:
            self.drain_commit_acks()
        try:
            normalized = (
                trade
                if isinstance(trade, BigTradeFill)
                else BigTradeFill.from_normalized(trade, venue=self.venue)
            )
            if normalized.symbol != self.symbol or normalized.venue != self.venue:
                raise ValueError("trade identity does not match runtime")
        except (TypeError, ValueError) as exc:
            self.counters["invalid_trades"] += 1
            if self._stats_builder is not None:
                self._stats_builder.record_invalid_trade()
            logger.warning("Big Trades rejected invalid input: %s", exc)
            return self.take_publications()
        try:
            for ordered in self.ordering.push(normalized):
                self._process_ordered(ordered)
        except Exception as exc:  # noqa: BLE001 - isolate Big Trades from existing pipeline
            self._set_error(exc)
        return self.take_publications()

    def flush(
        self,
        reason: ClusterCloseReason = ClusterCloseReason.STREAM_ENDED,
    ) -> tuple[RuntimeRecord, ...]:
        if not self.enabled or self._halted:
            return ()
        try:
            for ordered in self.ordering.flush():
                self._process_ordered(ordered)
            for cluster in self.aggregator.flush(reason):
                self._handle_finalized_cluster(cluster, post_trade=None)
            # STREAM_ENDED/DISCONNECTED do not source-confirm the current
            # one-second bucket.  Its final state is reconstructed from
            # immutable interactions after restart instead of committing a
            # provisional checkpoint that could later collide.
        except Exception as exc:  # noqa: BLE001
            self._set_error(exc)
        self.drain_commit_acks()
        return self.take_publications()

    def _process_ordered(self, trade: BigTradeFill) -> None:
        transition = self.session_tracker.observe(trade)
        if transition is not None:
            self._complete_source_confirmed_session(transition)
        if self._stats_builder is None:
            self._start_session(trade)
        if self._open_gap is not None:
            self._end_source_gap(trade.event_time)
        self._flush_checkpoint_buckets_before(trade.event_time)

        self._finalize_due_horizons(trade)

        previous_observation = self.price_path.last_observation
        previous_price = previous_observation.price if previous_observation is not None else None
        self.price_path.append(trade)
        self._stats_builder.observe_trade(trade)
        self.counters["trades_observed"] += 1
        if previous_price is None:
            candidate_ids = self.zone_index.containing(trade.price)
        else:
            candidate_ids = self.zone_index.candidates(previous_price, trade.price)
        for zone_id in candidate_ids:
            self._observe_zone_trade(zone_id, trade)

        assert self.settings_resolver is not None
        resolved = self.settings_resolver.resolve(trade)
        self._set_ready_status(resolved)
        for cluster in self.aggregator.process(trade, resolved.snapshot):
            self._handle_finalized_cluster(cluster, post_trade=trade)
        self._last_processed_trade = trade

    def _start_session(self, trade: BigTradeFill) -> None:
        self._current_session_id = trade.session_id
        self._stats_builder = SessionStatsBuilder(
            session_id=trade.session_id,
            symbol=self.symbol,
            venue=self.venue,
        )

    def _set_ready_status(self, resolved: ResolvedRuntimeSettings) -> None:
        if self.status in {
            BigTradesRuntimeStatus.DEGRADED_SOURCE_GAP,
            BigTradesRuntimeStatus.DEGRADED_STORAGE,
            BigTradesRuntimeStatus.ERROR,
        }:
            return
        if resolved.snapshot.filter_mode is FilterMode.MANUAL:
            self.status = BigTradesRuntimeStatus.MANUAL_READY
        elif resolved.automatic_filter is None:
            self.status = BigTradesRuntimeStatus.CALIBRATION_UNAVAILABLE
        else:
            self.status = BigTradesRuntimeStatus.AUTOMATIC_READY

    def _handle_finalized_cluster(
        self,
        cluster: ExecutionCluster,
        *,
        post_trade: Optional[BigTradeFill],
    ) -> None:
        self.counters["clusters_finalized"] += 1
        if self._stats_builder is None or self._stats_builder.session_id != cluster.session_id:
            raise RuntimeError("cluster/session stats ownership mismatch")
        self._stats_builder.observe_cluster(cluster)
        if cluster.close_reason is ClusterCloseReason.MAX_FILLS_EXCEEDED:
            self.counters["clusters_rejected"] += 1
            return
        assert self.settings_resolver is not None
        decision = decide_cluster(
            cluster, self.settings_resolver.automatic_filter_for(cluster.settings)
        )
        if not decision.accepted:
            self.counters["clusters_rejected"] += 1
            if decision.reason.value == "AUTOMATIC_UNAVAILABLE":
                self.status = BigTradesRuntimeStatus.CALIBRATION_UNAVAILABLE
            return
        if len(self.zone_index) >= self.zone_capacity:
            raise RuntimeError("BIG_TRADES_ZONE_CAPACITY_EXCEEDED")

        event = create_big_trade_event(cluster, decision)
        zone = create_reaction_zone(event)
        observer = ReactionZoneObserver(zone, tick_size=self.tick_size)
        links: list[ZoneEventLink] = []
        link_candidate_ids = self.zone_index.overlapping_or_adjacent(
            event.low_price,
            event.high_price,
            self.tick_size * self.link_tolerance_ticks,
        )
        for prior_zone_id in link_candidate_ids:
            prior = self.observers[prior_zone_id]
            if prior.lifecycle is ZoneLifecycle.SESSION_CLOSED:
                continue
            link = link_event_to_zone(
                prior.zone,
                event,
                tick_size=self.tick_size,
                tolerance_ticks=self.link_tolerance_ticks,
                ordinal_for_zone=prior.linked_big_trade_count + 1,
            )
            if link is not None:
                observed_time = post_trade.event_time if post_trade is not None else event.last_time
                observed_trade_id = (
                    post_trade.trade_id if post_trade is not None else event.last_trade_id
                )
                prior.register_link(
                    link,
                    linked_trade_id=event.last_trade_id,
                    observed_time=observed_time,
                    observed_trade_id=observed_trade_id,
                )
                self._mark_checkpoint(prior, observed_time)
                links.append(link)

        self.zone_index.add(zone)
        self.observers[zone.zone_id] = observer
        self.events_by_zone[zone.zone_id] = event
        self.horizon_trackers[zone.zone_id] = ResultHorizonTracker(
            event,
            zone,
            observer,
            self.price_path,
            horizons_seconds=self.horizons_seconds,
            max_staleness_ms=self.max_staleness_ms,
        )
        self._schedule_horizon_tracker(zone.zone_id)
        batch = BigTradeOriginStorageBatch.create(
            event, cluster.fills, zone, observer.interactions[0], links
        )
        records = tuple(
            sorted(
                (
                    self._event_record(event, batch.event),
                    self._zone_record(zone, batch.zone),
                    *(self._link_record(link) for link in links),
                ),
                key=lambda item: item.sort_key,
            )
        )
        assert self.storage_writer is not None
        future = self.storage_writer.submit_origin_batch(batch)
        token = self._register_ack(future)
        pending = _PendingOrigin(token, batch, event, zone, records)
        self._pending_origin_by_token[token] = pending
        self._pending_origin_token_by_zone[zone.zone_id] = token
        if post_trade is not None:
            self._observe_zone_trade(zone.zone_id, post_trade)
        self.counters["clusters_accepted"] += 1
        self.counters["origin_batches_submitted"] += 1

    def _observe_zone_trade(self, zone_id: str, trade: BigTradeFill) -> None:
        observer = self.observers[zone_id]
        before = self._observer_state(observer)
        interactions = observer.observe_trade(trade)
        if interactions:
            self._submit_interactions(interactions)
        if self._observer_state(observer) != before:
            self._mark_checkpoint(observer, trade.event_time)

    @staticmethod
    def _observer_state(observer: ReactionZoneObserver) -> tuple[Any, ...]:
        return (
            observer.current_relation,
            observer.first_exit_direction,
            observer.touch_count,
            observer.cross_count,
            observer.inside_buy_quantity,
            observer.inside_sell_quantity,
            observer.linked_big_trade_count,
            observer.lifecycle,
        )

    def _mark_checkpoint(
        self, observer: ReactionZoneObserver, source_time: datetime
    ) -> None:
        checkpoint = create_zone_state_checkpoint(observer, source_time)
        self._dirty_checkpoints[(checkpoint.zone_id, checkpoint.source_bucket_time)] = checkpoint

    def _flush_checkpoint_buckets_before(self, source_time: datetime) -> None:
        if not self._dirty_checkpoints:
            return
        boundary = require_aware_utc(source_time).replace(microsecond=0)
        due_keys = [key for key in self._dirty_checkpoints if key[1] < boundary]
        self._flush_checkpoint_keys(due_keys)

    def _flush_all_checkpoints(self) -> None:
        self._flush_checkpoint_keys(list(self._dirty_checkpoints))

    def _flush_checkpoint_keys(self, keys: Iterable[tuple[str, datetime]]) -> None:
        grouped: dict[Optional[int], list[ZoneStateCheckpoint]] = defaultdict(list)
        for key in sorted(keys, key=lambda item: (item[1], item[0])):
            checkpoint = self._dirty_checkpoints.pop(key, None)
            if checkpoint is None:
                continue
            grouped[self._pending_origin_token_by_zone.get(checkpoint.zone_id)].append(checkpoint)
        for origin_token, checkpoints in grouped.items():
            if origin_token is None:
                self._submit_checkpoints(tuple(checkpoints))
            else:
                self._pending_origin_by_token[origin_token].dependent[
                    "big_trade_zone_checkpoints"
                ].extend(checkpoints)

    def observe_closed_candle(
        self,
        candle: ClosedCandle,
        *,
        normalized_true_range: Optional[Decimal] = None,
    ) -> tuple[RuntimeRecord, ...]:
        if not self.enabled or self._halted:
            return ()
        self.drain_commit_acks()
        try:
            observations: list[ZoneCandleObservation] = []
            for observer in tuple(self.observers.values()):
                if observer.lifecycle is ZoneLifecycle.SESSION_CLOSED:
                    continue
                if candle.open_time.date().isoformat() != observer.zone.session_id:
                    continue
                observations.append(self.candle_observer.observe(observer.zone, candle))
            if observations:
                self._submit_candles(tuple(observations))
            if (
                self._stats_builder is not None
                and candle.open_time.date().isoformat() == self._stats_builder.session_id
            ):
                ntr = normalized_true_range
                if ntr is None and self._previous_candle_close is not None:
                    true_range = max(
                        candle.high - candle.low,
                        abs(candle.high - self._previous_candle_close),
                        abs(candle.low - self._previous_candle_close),
                    )
                    ntr = true_range / candle.close
                self._stats_builder.observe_candle_ntr(ntr)
                self._previous_candle_close = candle.close
        except CandleBoundaryMismatch as exc:
            self._set_error(exc)
        except Exception as exc:  # noqa: BLE001
            self._set_error(exc)
        self.drain_commit_acks()
        return self.take_publications()

    def recover_current_session(
        self,
        *,
        session_id: str,
        source_trades: Iterable[BigTradeFill],
    ) -> None:
        """Recover committed active zones and open a visible restart gap.

        ``source_trades`` is the existing authoritative normalized-trade
        history for the current UTC session.  Big Trades does not invent or
        interpolate absent prices.
        """

        if not self.enabled or self._halted:
            return
        if self.observers or len(self.price_path) or self.ordering.pending_count:
            raise RuntimeError("Big Trades recovery requires an empty runtime")
        assert self.storage_writer is not None
        trades = tuple(sorted(source_trades, key=lambda item: item.source_key))
        if any(
            trade.symbol != self.symbol
            or trade.venue != self.venue
            or trade.session_id != session_id
            for trade in trades
        ):
            raise ValueError("recovery source trade identity/session mismatch")
        if any(left.source_key >= right.source_key for left, right in zip(trades, trades[1:])):
            raise ValueError("recovery source trades must be strictly ordered")

        store = self.storage_writer.store
        event_rows = tuple(
            row
            for row in store.fetch_rows("big_trade_events")
            if row["symbol"] == self.symbol
            and row["venue"] == self.venue
            and row["session_id"] == session_id
        )
        fill_rows_by_event: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        event_ids = {row["event_id"] for row in event_rows}
        for row in store.fetch_rows("big_trade_event_fills"):
            if row["event_id"] in event_ids:
                fill_rows_by_event[row["event_id"]].append(row)
        zone_rows = tuple(
            row
            for row in store.fetch_rows("big_trade_reaction_zones")
            if row["symbol"] == self.symbol
            and row["venue"] == self.venue
            and row["session_id"] == session_id
        )
        event_by_id = {
            row["event_id"]: event_from_row(row, fill_rows_by_event[row["event_id"]])
            for row in event_rows
        }
        zones = tuple(
            zone_from_row(row, event_by_id[row["origin_event_id"]]) for row in zone_rows
        )
        zone_ids = {zone.zone_id for zone in zones}
        interactions_by_zone: dict[str, list[ZoneInteraction]] = defaultdict(list)
        for row in store.fetch_rows("big_trade_zone_interactions"):
            if row["zone_id"] in zone_ids:
                interactions_by_zone[row["zone_id"]].append(interaction_from_row(row))
        links_by_zone: dict[str, list[ZoneEventLink]] = defaultdict(list)
        for row in store.fetch_rows("big_trade_zone_event_links"):
            if row["zone_id"] in zone_ids:
                links_by_zone[row["zone_id"]].append(link_from_row(row))
        checkpoints_by_zone: dict[str, list[ZoneStateCheckpoint]] = defaultdict(list)
        for row in store.fetch_rows("big_trade_zone_state_checkpoints"):
            if row["zone_id"] in zone_ids:
                checkpoints_by_zone[row["zone_id"]].append(checkpoint_from_row(row))
        snapshots_by_zone: dict[str, list[ResultSnapshot]] = defaultdict(list)
        for row in store.fetch_rows("big_trade_result_snapshots"):
            if row["zone_id"] in zone_ids:
                snapshots_by_zone[row["zone_id"]].append(snapshot_from_row(row))

        self.price_path = SourcePricePathIndex(symbol=self.symbol, venue=self.venue)
        self._stats_builder = SessionStatsBuilder(
            session_id=session_id, symbol=self.symbol, venue=self.venue
        )
        for trade in trades:
            self.price_path.append(trade)
            self._stats_builder.observe_trade(trade)
        self._stats_builder.mark_restart_truncated()
        self._current_session_id = session_id
        self.session_tracker.restore_current_session(session_id)
        self._last_processed_trade = trades[-1] if trades else None

        incomplete = False
        for zone in sorted(zones, key=lambda item: (item.zone_source_start, item.zone_id)):
            persisted_interactions = tuple(
                sorted(interactions_by_zone[zone.zone_id], key=lambda item: item.ordinal)
            )
            if any(
                item.interaction_type is InteractionType.ZONE_SESSION_CLOSED
                for item in persisted_interactions
            ):
                continue
            links = tuple(
                sorted(
                    links_by_zone[zone.zone_id],
                    key=lambda item: (item.linked_time, item.ordinal_for_zone),
                )
            )
            observer = self._replay_recovery_zone(
                zone, persisted_interactions, links, event_by_id, trades
            )
            if observer is None:
                checkpoints = sorted(
                    checkpoints_by_zone[zone.zone_id],
                    key=lambda item: item.source_bucket_time,
                )
                checkpoint = checkpoints[-1] if checkpoints else self._infer_checkpoint(
                    zone, persisted_interactions, links
                )
                observer = ReactionZoneObserver.restore(
                    zone,
                    tick_size=self.tick_size,
                    checkpoint=checkpoint,
                    interactions=persisted_interactions,
                    links=links,
                )
                incomplete = True
            self.zone_index.add(zone)
            self.observers[zone.zone_id] = observer
            self.events_by_zone[zone.zone_id] = event_by_id[zone.origin_event_id]
            tracker = ResultHorizonTracker(
                event_by_id[zone.origin_event_id],
                zone,
                observer,
                self.price_path,
                horizons_seconds=self.horizons_seconds,
                max_staleness_ms=self.max_staleness_ms,
            )
            tracker.restore_completed(tuple(snapshots_by_zone[zone.zone_id]))
            self.horizon_trackers[zone.zone_id] = tracker
            self._schedule_horizon_tracker(zone.zone_id)
            self._committed_zones.add(zone.zone_id)

        if zones and not trades:
            raise RuntimeError("active zone recovery requires authoritative source trades")
        if trades:
            open_gap_ids = {
                observer._open_gap_id
                for observer in self.observers.values()
                if observer._open_gap_id is not None
            }
            if len(open_gap_ids) > 1:
                raise RuntimeError("recovered zones disagree on the open gap epoch")
            restart_interactions = []
            if open_gap_ids:
                existing_gap_id = next(iter(open_gap_ids))
                starts = [
                    item.source_event_time
                    for items in interactions_by_zone.values()
                    for item in items
                    if item.interaction_type is InteractionType.SOURCE_GAP_STARTED
                    and item.gap_epoch_id == existing_gap_id
                ]
                if not starts:
                    raise RuntimeError("recovered open gap has no start interaction")
                gap = self.price_path.restore_open_gap(existing_gap_id, min(starts))
                if any(
                    observer._open_gap_id != existing_gap_id
                    for observer in self.observers.values()
                ):
                    raise RuntimeError("active zone is missing the recovered open gap")
            else:
                gap = self.price_path.start_gap(trades[-1].event_time)
                for observer in self.observers.values():
                    restart_interactions.append(
                        observer.start_gap(gap.gap_epoch_id, gap.start_time)
                    )
                    self._mark_checkpoint(observer, gap.start_time)
            self._open_gap = gap
            if restart_interactions:
                self._submit_interactions(tuple(restart_interactions))
            self._stats_builder.mark_source_gap()
            self.counters["source_gap_epochs"] += 1
            self.status = BigTradesRuntimeStatus.DEGRADED_SOURCE_GAP
        if incomplete:
            self.counters["restart_incomplete_recoveries"] += 1
        self.counters["restart_recoveries"] += 1

    def _replay_recovery_zone(
        self,
        zone: ReactionZone,
        persisted: tuple[ZoneInteraction, ...],
        links: tuple[ZoneEventLink, ...],
        event_by_id: Mapping[str, BigTradeEvent],
        trades: tuple[BigTradeFill, ...],
    ) -> Optional[ReactionZoneObserver]:
        if not persisted:
            return None
        observer = ReactionZoneObserver(zone, tick_size=self.tick_size)
        gap_actions = [
            item
            for item in persisted
            if item.interaction_type
            in {InteractionType.SOURCE_GAP_STARTED, InteractionType.SOURCE_GAP_ENDED}
        ]
        timeline: list[tuple[tuple[int, int, int, str], str, Any]] = []
        for trade in trades:
            if trade.source_key > (
                epoch_microseconds(zone.zone_source_start),
                zone.origin_last_trade_id,
            ):
                timeline.append(
                    (
                        (
                            epoch_microseconds(trade.event_time),
                            1,
                            trade.trade_id,
                            str(trade.trade_id),
                        ),
                        "trade",
                        trade,
                    )
                )
        for item in gap_actions:
            precedence = (
                0 if item.interaction_type is InteractionType.SOURCE_GAP_ENDED else 2
            )
            timeline.append(
                (
                    (
                        epoch_microseconds(item.source_event_time),
                        precedence,
                        item.source_trade_id if item.source_trade_id is not None else 2**63 - 1,
                        item.interaction_id,
                    ),
                    "gap",
                    item,
                )
            )
        for link in links:
            linked_event = event_by_id.get(link.linked_event_id)
            if linked_event is None:
                return None
            timeline.append(
                (
                    (
                        epoch_microseconds(link.linked_time),
                        3,
                        linked_event.last_trade_id,
                        link.link_id,
                    ),
                    "link",
                    (link, linked_event.last_trade_id),
                )
            )
        try:
            for _, kind, value in sorted(timeline, key=lambda item: item[0]):
                if kind == "trade":
                    observer.observe_trade(value)
                elif kind == "link":
                    link, trade_id = value
                    observer.register_link(link, linked_trade_id=trade_id)
                elif value.interaction_type is InteractionType.SOURCE_GAP_STARTED:
                    observer.start_gap(value.gap_epoch_id, value.source_event_time)
                else:
                    observer.end_gap(value.gap_epoch_id, value.source_event_time)
        except ValueError:
            return None
        generated = {(item.interaction_id, item.content_hash) for item in observer.interactions}
        authoritative = {(item.interaction_id, item.content_hash) for item in persisted}
        return observer if generated == authoritative else None

    @staticmethod
    def _infer_checkpoint(
        zone: ReactionZone,
        interactions: tuple[ZoneInteraction, ...],
        links: tuple[ZoneEventLink, ...],
    ) -> ZoneStateCheckpoint:
        ordered = tuple(sorted(interactions, key=lambda item: item.ordinal))
        if not ordered:
            raise RuntimeError("cannot infer checkpoint without interactions")
        current_relation = next(
            (
                item.current_relation
                for item in reversed(ordered)
                if item.current_relation is not None
            ),
            PriceRelation.INSIDE,
        )
        first_exit = next(
            (
                item
                for item in ordered
                if item.interaction_type
                in {InteractionType.FIRST_EXIT_UP, InteractionType.FIRST_EXIT_DOWN}
            ),
            None,
        )
        open_gap_id: Optional[str] = None
        for item in ordered:
            if item.interaction_type is InteractionType.SOURCE_GAP_STARTED:
                open_gap_id = item.gap_epoch_id
            elif item.interaction_type is InteractionType.SOURCE_GAP_ENDED:
                open_gap_id = None
        bucket = ordered[-1].source_event_time.replace(microsecond=0)
        payload = {
            "checkpoint_id": checkpoint_id(zone.zone_id, bucket),
            "zone_id": zone.zone_id,
            "source_bucket_time": bucket,
            "current_relation": current_relation,
            "first_exit_direction": first_exit.direction if first_exit else None,
            "first_exit_time": first_exit.source_event_time if first_exit else None,
            "touch_count": sum(
                item.interaction_type
                in {InteractionType.TOUCH_FROM_ABOVE, InteractionType.TOUCH_FROM_BELOW}
                for item in ordered
            ),
            "cross_count": sum(
                item.interaction_type in {InteractionType.CROSS_UP, InteractionType.CROSS_DOWN}
                for item in ordered
            ),
            "inside_buy_quantity": Decimal("0"),
            "inside_sell_quantity": Decimal("0"),
            "linked_event_count": len(links),
            "gap_epoch_id": open_gap_id,
        }
        return ZoneStateCheckpoint(content_hash=content_hash(payload), **payload)

    def start_source_gap(self, source_time: Optional[datetime] = None) -> None:
        if not self.enabled or self._halted or self._open_gap is not None:
            return
        # The disconnect interaction can occur in the same source-time second
        # as the last trade.  Defer checkpoint emission until the gap mutation
        # has replaced that second's provisional checkpoint.
        try:
            for ordered in self.ordering.flush():
                self._process_ordered(ordered)
            for cluster in self.aggregator.flush(ClusterCloseReason.STREAM_DISCONNECTED):
                self._handle_finalized_cluster(cluster, post_trade=None)
        except Exception as exc:  # noqa: BLE001
            self._set_error(exc)
            return
        when = source_time or (
            self._last_processed_trade.event_time if self._last_processed_trade is not None else None
        )
        if when is None:
            return
        gap = self.price_path.start_gap(when)
        self._open_gap = gap
        interactions = []
        for observer in self.observers.values():
            interactions.append(observer.start_gap(gap.gap_epoch_id, gap.start_time))
            self._mark_checkpoint(observer, gap.start_time)
        if interactions:
            self._submit_interactions(tuple(interactions))
        if self._stats_builder is not None:
            self._stats_builder.mark_source_gap()
        self.counters["source_gap_epochs"] += 1
        self.status = BigTradesRuntimeStatus.DEGRADED_SOURCE_GAP

    def _end_source_gap(self, source_time: datetime) -> None:
        assert self._open_gap is not None
        gap = self.price_path.end_gap(source_time)
        interactions = []
        for observer in self.observers.values():
            interactions.append(observer.end_gap(gap.gap_epoch_id, source_time))
            self._mark_checkpoint(observer, source_time)
        if interactions:
            self._submit_interactions(tuple(interactions))
        self._open_gap = None

    def _complete_source_confirmed_session(self, transition: Any) -> None:
        for cluster in self.aggregator.flush(ClusterCloseReason.SESSION_CHANGED):
            self._handle_finalized_cluster(cluster, post_trade=None)
        snapshots: list[ResultSnapshot] = []
        for tracker in self.horizon_trackers.values():
            snapshots.extend(tracker.finalize_session())
        if snapshots:
            self._submit_snapshots(tuple(snapshots))
        interactions = []
        for zone_id, observer in self.observers.items():
            interactions.append(observer.close_session())
            self._closed_zone_cleanup_pending.add(zone_id)
            self._mark_checkpoint(observer, transition.confirmed_by_event_time)
        if interactions:
            self._submit_interactions(tuple(interactions))
        self._flush_all_checkpoints()

        if self._stats_builder is None:
            raise RuntimeError("source-confirmed transition has no session stats")
        stats = self._stats_builder.finalize(
            confirmed_by_session_id=transition.next_session_id,
            confirmed_by_event_time=transition.confirmed_by_event_time,
            confirmed_by_trade_id=transition.confirmed_by_trade_id,
        )
        if self.artifact_repository is not None:
            self.artifact_repository.write_session_stats(stats)
        assert self.storage_writer is not None
        future = self.storage_writer.submit_session_stats((stats,))
        self._register_update(future, "big_trade_session_stats", ())
        self.counters["sessions_source_confirmed"] += 1

        for zone_id in tuple(self.observers):
            self.zone_index.remove(zone_id)
        self.horizon_trackers.clear()
        self._horizon_due_heap.clear()
        self.price_path = SourcePricePathIndex(symbol=self.symbol, venue=self.venue)
        self._stats_builder = None
        self._current_session_id = None
        self._open_gap = None
        self._previous_candle_close = None

    def _schedule_horizon_tracker(self, zone_id: str) -> None:
        tracker = self.horizon_trackers.get(zone_id)
        if tracker is None:
            return
        target = tracker.next_target_time
        if target is not None:
            heapq.heappush(
                self._horizon_due_heap,
                (epoch_microseconds(target), zone_id),
            )

    def _finalize_due_horizons(self, trade: BigTradeFill) -> None:
        current_us = epoch_microseconds(trade.event_time)
        while self._horizon_due_heap and self._horizon_due_heap[0][0] < current_us:
            target_us, zone_id = heapq.heappop(self._horizon_due_heap)
            tracker = self.horizon_trackers.get(zone_id)
            if tracker is None:
                continue
            target = tracker.next_target_time
            if target is None or epoch_microseconds(target) != target_us:
                continue
            snapshots = tracker.on_trade(trade)
            if snapshots:
                self._submit_snapshots(snapshots)
            self._schedule_horizon_tracker(zone_id)

    def _submit_interactions(self, items: tuple[ZoneInteraction, ...]) -> None:
        self._submit_zone_dependent(
            "big_trade_zone_interactions", items, lambda values: self.storage_writer.submit_zone_interactions(values),
        )

    def _submit_snapshots(self, items: tuple[ResultSnapshot, ...]) -> None:
        self._submit_zone_dependent(
            "big_trade_result_snapshots", items, lambda values: self.storage_writer.submit_result_snapshots(values),
        )

    def _submit_candles(self, items: tuple[ZoneCandleObservation, ...]) -> None:
        self._submit_zone_dependent(
            "big_trade_zone_candles", items, lambda values: self.storage_writer.submit_zone_candles(values),
        )

    def _submit_checkpoints(self, items: tuple[ZoneStateCheckpoint, ...]) -> None:
        self._submit_zone_dependent(
            "big_trade_zone_checkpoints", items, lambda values: self.storage_writer.submit_zone_checkpoints(values),
        )

    def _submit_zone_dependent(
        self,
        kind: str,
        items: tuple[Any, ...],
        submit: Callable[[tuple[Any, ...]], CommitFuture],
    ) -> None:
        if not items:
            return
        assert self.storage_writer is not None
        ready: list[Any] = []
        for item in items:
            origin_token = self._pending_origin_token_by_zone.get(item.zone_id)
            if origin_token is None:
                if item.zone_id not in self._committed_zones:
                    raise RuntimeError(f"dependent update has no committed origin: {item.zone_id}")
                ready.append(item)
            else:
                self._pending_origin_by_token[origin_token].dependent[kind].append(item)
        if ready:
            values = tuple(ready)
            future = submit(values)
            records = self._records_for_update(kind, values)
            self._register_update(
                future,
                kind,
                records,
                zone_ids=frozenset(item.zone_id for item in values),
            )

    def _submit_buffered_origin_dependents(self, pending: _PendingOrigin) -> None:
        dispatch = {
            "big_trade_zone_interactions": self._submit_interactions,
            "big_trade_result_snapshots": self._submit_snapshots,
            "big_trade_zone_candles": self._submit_candles,
            "big_trade_zone_checkpoints": self._submit_checkpoints,
        }
        for kind, items in pending.dependent.items():
            dispatch[kind](tuple(items))

    def _records_for_update(self, kind: str, items: tuple[Any, ...]) -> tuple[RuntimeRecord, ...]:
        if kind == "big_trade_zone_interactions":
            return tuple(self._interaction_record(item) for item in items)
        if kind == "big_trade_result_snapshots":
            return tuple(self._snapshot_record(item) for item in items)
        if kind == "big_trade_zone_candles":
            return tuple(self._candle_record(item) for item in items)
        if kind == "big_trade_zone_checkpoints":
            return ()
        raise RuntimeError(f"unknown dependent record kind {kind}")

    def _register_ack(self, future: CommitFuture) -> int:
        token = self._next_token
        self._next_token += 1
        future.add_done_callback(lambda ack, token=token: self._ack_queue.put((token, ack)))
        return token

    def _register_update(
        self,
        future: CommitFuture,
        kind: str,
        records: tuple[RuntimeRecord, ...],
        zone_ids: frozenset[str] = frozenset(),
        on_success: Optional[Callable[[], None]] = None,
    ) -> int:
        token = self._register_ack(future)
        self._pending_updates[token] = _PendingUpdate(
            token, kind, records, zone_ids, on_success
        )
        return token

    def drain_commit_acks(self) -> tuple[RuntimeRecord, ...]:
        if self._ack_queue.empty():
            return tuple(self._new_publications)
        while True:
            try:
                token, ack = self._ack_queue.get_nowait()
            except Empty:
                break
            origin = self._pending_origin_by_token.pop(token, None)
            if origin is not None:
                self._pending_origin_token_by_zone.pop(origin.zone.zone_id, None)
                if ack.success:
                    self._committed_zones.add(origin.zone.zone_id)
                    self.counters["origin_batches_committed"] += 1
                    self._publish(origin.records)
                    self._submit_buffered_origin_dependents(origin)
                else:
                    self.counters["origin_batches_failed"] += 1
                    self._discard_failed_origin(origin, ack)
                continue
            update = self._pending_updates.pop(token, None)
            if update is None:
                self._set_error(RuntimeError(f"unknown storage acknowledgement token {token}"))
                continue
            if ack.success:
                self._publish(update.records)
                if update.on_success is not None:
                    update.on_success()
            else:
                self.counters["storage_updates_failed"] += 1
                if ack.error_code == "CONTENT_COLLISION":
                    self._set_error(RuntimeError(ack.error or ack.error_code))
                else:
                    self.status = BigTradesRuntimeStatus.DEGRADED_STORAGE
                    self.last_error = ack.error or ack.error_code
                    for zone_id in update.zone_ids:
                        observer = self.observers.get(zone_id)
                        if observer is not None:
                            observer.lifecycle = ZoneLifecycle.ERROR
                            self.zone_index.remove(zone_id)
        self._cleanup_closed_zones()
        return tuple(self._new_publications)

    def _discard_failed_origin(self, pending: _PendingOrigin, ack: CommitAck) -> None:
        zone_id = pending.zone.zone_id
        self.zone_index.remove(zone_id)
        self.observers.pop(zone_id, None)
        self.events_by_zone.pop(zone_id, None)
        self.horizon_trackers.pop(zone_id, None)
        self._closed_zone_cleanup_pending.discard(zone_id)
        for key in [key for key in self._dirty_checkpoints if key[0] == zone_id]:
            self._dirty_checkpoints.pop(key, None)
        self.status = BigTradesRuntimeStatus.DEGRADED_STORAGE
        self.last_error = ack.error or ack.error_code
        self._halted = True

    def _cleanup_closed_zones(self) -> None:
        if not self._closed_zone_cleanup_pending:
            return
        pending_zone_ids = set(self._pending_origin_token_by_zone)
        for update in self._pending_updates.values():
            pending_zone_ids.update(update.zone_ids)
        pending_zone_ids.update(zone_id for zone_id, _ in self._dirty_checkpoints)
        for zone_id in tuple(self._closed_zone_cleanup_pending):
            if zone_id in pending_zone_ids:
                continue
            self.observers.pop(zone_id, None)
            self.events_by_zone.pop(zone_id, None)
            self.horizon_trackers.pop(zone_id, None)
            self._committed_zones.discard(zone_id)
            self._closed_zone_cleanup_pending.discard(zone_id)

    def _publish(self, records: Iterable[RuntimeRecord]) -> None:
        ordered = tuple(sorted(records, key=lambda item: item.sort_key))
        if not ordered:
            return
        self._recent_records.extend(ordered)
        by_identity: dict[tuple[str, str], RuntimeRecord] = {}
        for record in self._recent_records:
            key = record.kind, record.record_id
            existing = by_identity.get(key)
            if existing is not None and existing.content_hash != record.content_hash:
                self._set_error(RuntimeError("runtime publication content collision"))
                return
            by_identity[key] = record
        self._recent_records = sorted(by_identity.values(), key=lambda item: item.sort_key)[
            -self.recent_capacity :
        ]
        self._new_publications.extend(ordered)
        if self.publication_callback is not None:
            self.publication_callback(ordered)

    def take_publications(self) -> tuple[RuntimeRecord, ...]:
        if not self._new_publications:
            return ()
        published = tuple(sorted(self._new_publications, key=lambda item: item.sort_key))
        self._new_publications.clear()
        return published

    @property
    def recent_records(self) -> tuple[RuntimeRecord, ...]:
        return tuple(self._recent_records)

    def _event_record(
        self, event: BigTradeEvent, row: Mapping[str, Any]
    ) -> RuntimeRecord:
        return RuntimeRecord(
            "EVENT_CREATED", event.last_time, event.last_trade_id, event.event_id, event.content_hash, row
        )

    def _zone_record(
        self, zone: ReactionZone, row: Mapping[str, Any]
    ) -> RuntimeRecord:
        return RuntimeRecord(
            "ZONE_CREATED",
            zone.zone_source_start,
            zone.origin_last_trade_id,
            zone.zone_id,
            zone.content_hash,
            row,
        )

    def _interaction_record(self, item: ZoneInteraction) -> RuntimeRecord:
        return RuntimeRecord(
            "ZONE_INTERACTION",
            item.source_event_time,
            item.source_trade_id,
            item.interaction_id,
            item.content_hash,
            interaction_to_row(item),
        )

    def _link_record(self, item: ZoneEventLink) -> RuntimeRecord:
        return RuntimeRecord(
            "ZONE_EVENT_LINK",
            item.linked_time,
            None,
            item.link_id,
            item.content_hash,
            link_to_row(item),
        )

    def _snapshot_record(self, item: ResultSnapshot) -> RuntimeRecord:
        return RuntimeRecord(
            "RESULT_SNAPSHOT",
            item.target_time,
            item.snapshot_trade_id,
            item.snapshot_id,
            item.content_hash,
            snapshot_to_row(item),
        )

    def _candle_record(self, item: ZoneCandleObservation) -> RuntimeRecord:
        row = candle_observation_to_row(item)
        return RuntimeRecord(
            "CANDLE_OBSERVATION",
            row["candle_id"],
            None,
            item.candle_observation_id,
            item.content_hash,
            row,
        )

    def statistics(self) -> dict[str, Any]:
        storage = self.storage_writer.statistics() if self.storage_writer is not None else {}
        return {
            "status": self.status.value,
            "mode": self.mode.value,
            "active_zone_count": len(self.zone_index),
            "boundary_index_size": len(self.zone_index),
            "price_path_index_size": len(self.price_path),
            "pending_origins": len(self._pending_origin_by_token),
            "pending_updates": len(self._pending_updates),
            "recent_records": len(self._recent_records),
            "last_error": self.last_error,
            **dict(self.counters),
            "storage": storage,
        }

    def _set_error(self, exc: BaseException) -> None:
        self.status = BigTradesRuntimeStatus.ERROR
        self.last_error = f"{type(exc).__name__}: {exc}"
        self._halted = True
        self.counters["errors"] += 1
        logger.exception("Big Trades runtime isolated failure", exc_info=exc)


def runtime_records_canonical(records: Iterable[RuntimeRecord]) -> str:
    """Stable comparison helper for Live/Replay fixture parity tests."""

    return canonical_json(
        [
            {
                "kind": item.kind,
                "source_event_time": item.source_event_time,
                "source_trade_id": item.source_trade_id,
                "record_id": item.record_id,
                "content_hash": item.content_hash,
                "payload": item.payload,
            }
            for item in sorted(records, key=lambda value: value.sort_key)
        ]
    )
