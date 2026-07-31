"""Replay + live pipelines — end-to-end CVD + Signal wiring (M6/M11/B-2).

Replay (M6, YAMLReference_v3.1 §5): recorded raw events (JSON Lines) replace the
live WebSocket; all downstream processing is identical to live mode:

    ReplaySource -> classify_raw -> trade path: DataNormalizer -> CVD + Footprint
                                               + Imbalance + Absorption -> SignalEngine -> Storage
                                -> depth path: OrderBookStateManager

Live (Phase6/M11/B-2): the same pipeline sourced from a real Binance Futures WebSocket:

    ExchangeConnector(binance_connect) -> BoundedEventQueue
        -> DataReceiver(validate=is_agg_trade_or_depth, record JSONL) -> BoundedEventQueue
        -> classify_raw -> trade/depth routing -> CVD + Footprint + Imbalance
        + Absorption -> SignalEngine -> Storage

On each confirmed bar:
  - volume_ref.observe_bar() is called with the bar's per-level volumes.
  - absorption.current() is passed to SignalEngine (replaces the former None).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

import yaml

import logging

from .acquisition.binance_rest import fetch_depth_snapshot, rest_to_depth_event
from .acquisition.binance_ws import is_agg_trade, is_agg_trade_or_depth, make_binance_connect
from .acquisition.depth_sync import (
    DepthSyncAction,
    DepthSyncCoordinator,
    DepthSyncState,
    SnapshotRequest,
)
from .ai.analysis import AnalysisEngine, AnalysisInput
from .mt5.adapter import MT5Server, analysis_to_mt5_message
from .acquisition.connector import ExchangeConnector
from .acquisition.event_queue import BoundedEventQueue
from .acquisition.receiver import STOP, DataReceiver, JsonlRecorder, default_validate
from .acquisition.replay import ReplaySource
from .database.schema import (
    candle_to_row,
    flow_response_event_to_row,
    flow_response_outcome_to_row,
    signal_to_row,
    trade_to_row,
)
from .database.flow_response_warm_start import load_recent_flow_response_trades
from .database.session_vwap_warm_start import load_latest_session_vwap_seed
from .database.storage import BackgroundStorageWriter, StorageWriter
from .normalization.normalizer import (
    DataNormalizer,
    ExchangeProfile,
    LiquidationEvent,
    NormalizationError,
    normalize_raw_liquidation,
)
from .orderflow.absorption import AbsorptionDetector
from .orderflow.cvd import CvdCalculator
from .orderflow.multi_timeframe import MultiTimeframeCandleAggregator
from .orderflow.native_execution_pipeline import NativeExecutionCoordinator
from .orderflow.divergence import CvdDivergenceDetector
from .orderflow.flow_detector import (
    ExhaustionDetector,
    FlowEvent,
    LargeTradeDetector,
    SweepDetector,
    TapeAnalyzer,
    UnfinishedAuctionDetector,
)
from .orderflow.footprint import FootprintCalculator
from .orderflow.flow_price_response import (
    FlowPriceResponseDetector,
    FlowResponseOutcomeTracker,
)
from .orderflow.imbalance import ImbalanceDetector, ImbalanceResult
from .orderflow.orderbook import OrderBookStateManager
from .orderflow.signal import SignalEngine, SignalResult
from .orderflow.volume_ref import VolumeRefTracker
from .strategy_engine.ingestion.snapshot_producer import SnapshotProducer

logger = logging.getLogger("pipeline")

# Error code (ErrorCodes: E3xxx = orderflow) for an unconfigured imbalance floor.
ERROR_IMBALANCE_MIN_VOLUME_DEFAULTED = "E3002"
_IMBALANCE_MIN_VOLUME_DEFAULT = Decimal("0.5")

# Task-A: same-direction webapp IMBALANCE flow-event cooldown, in confirmed bars.
_IMBALANCE_COOLDOWN_BARS = 3
_DEC_ZERO = Decimal("0")


class _RecorderFanout:
    """Preserve the legacy recorder while isolating an optional observation tap."""

    def __init__(self, legacy: Any | None, observation: Any | None) -> None:
        self._legacy = legacy
        self._observation = observation

    @property
    def written(self) -> int:
        return int(getattr(self._legacy, "written", 0))

    def write(self, obj: dict[str, Any]) -> None:
        if self._legacy is not None:
            self._legacy.write(obj)
        if self._observation is not None:
            try:
                self._observation.write(obj)
            except Exception:
                logger.exception(
                    "independent Hook observation tap failed; market pipeline continues"
                )

    def write_snapshot(self, obj: dict[str, Any], *, reason: str) -> None:
        """Keep legacy bytes stable while adding acquisition reason to research raw."""
        if self._legacy is not None:
            self._legacy.write(obj)
        if self._observation is not None:
            observation_row = dict(obj)
            observation_row["_capture_reason"] = reason
            try:
                self._observation.write(observation_row)
            except Exception:
                logger.exception(
                    "independent Hook snapshot tap failed; market pipeline continues"
                )

    def record_sync_action(self, action: DepthSyncAction) -> None:
        """Forward terminal depth sync metadata to the observation recorder only."""
        if self._observation is None:
            return
        callback = getattr(self._observation, "record_sync_action", None)
        if callback is None:
            return
        try:
            callback(action)
        except Exception:
            logger.exception(
                "independent Hook sync metadata tap failed; market pipeline continues"
            )

    def close(self) -> None:
        if self._legacy is not None:
            self._legacy.close()
        if self._observation is not None:
            try:
                self._observation.close()
            except Exception:
                logger.exception("independent Hook observation tap close failed")


def _resolve_imbalance_min_volume(raw_min_volume: Any) -> Decimal:
    """Resolve imbalance.min_volume from config into a Decimal floor (Task-A).

    A null (None) config value no longer silently becomes Decimal("0") — which
    disabled the volume filter entirely. Instead it is logged (E3002) and falls
    back to a conservative default floor, so a mis-configured deployment still
    filters thin one-sided levels rather than saturating.
    """
    if raw_min_volume is None:
        logger.warning(
            "%s imbalance.min_volume is null; defaulting to %s",
            ERROR_IMBALANCE_MIN_VOLUME_DEFAULTED, _IMBALANCE_MIN_VOLUME_DEFAULT,
        )
        return _IMBALANCE_MIN_VOLUME_DEFAULT
    return Decimal(str(raw_min_volume))


def _imbalance_should_fire(
    net: Decimal,
    bars_since_last: Optional[int],
    last_net: Decimal,
    cooldown_bars: int = _IMBALANCE_COOLDOWN_BARS,
) -> bool:
    """Pure decision: should a stacked-imbalance webapp flow event fire this bar?

    Fires when the cooldown has elapsed (never fired → bars_since_last is None,
    or bars_since_last >= cooldown_bars), or when the stacked net strictly
    exceeds the net at the previous fire (an escalating stack). Otherwise the
    event is suppressed to stop every-bar spam. State is held by the caller
    (Pipeline side); this function is side-effect free.
    """
    if bars_since_last is None or bars_since_last >= cooldown_bars:
        return True
    return net > last_net
# --- Strict Order Book snapshot fetch worker (ADR-003/ADR-010/ADR-011) --------

_BOOK_RESYNC_BACKOFF_SEC: tuple[int, ...] = (5, 10, 30)
_DEPTH_SYNC_MAX_BUFFERED_DIFFS: int = 100000
_DEPTH_SYNC_MAX_ATTEMPTS: int = 3


@dataclass
class BookResyncCounters:
    """Mutable counters owned by the live pipeline's single asyncio loop."""
    resyncs: int = 0
    fetch_failures: int = 0


@dataclass(frozen=True)
class _DepthSnapshotFetchResult:
    request: SnapshotRequest
    snapshot: Optional[dict[str, Any]] = None
    error: Optional[str] = None


async def _book_resync_supervisor(
    *,
    symbol: str,
    fetch_snapshot: Callable,
    requests: asyncio.Queue[SnapshotRequest],
    results: asyncio.Queue[_DepthSnapshotFetchResult],
    counters: BookResyncCounters,
    recorder: Optional[Any] = None,
    sleep: Callable[[int], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Fetch requested candidates only; never mutate or validate the order book."""
    while True:
        request = await requests.get()
        try:
            raw_snap = await fetch_snapshot(symbol)
            depth_evt = rest_to_depth_event(raw_snap, symbol)
            if recorder is not None:
                if hasattr(recorder, "write_snapshot"):
                    recorder.write_snapshot(depth_evt, reason=request.reason)
                else:
                    recorder.write(depth_evt)
            await results.put(
                _DepthSnapshotFetchResult(request=request, snapshot=depth_evt)
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            counters.fetch_failures += 1
            delay = _BOOK_RESYNC_BACKOFF_SEC[
                min(request.attempt - 1, len(_BOOK_RESYNC_BACKOFF_SEC) - 1)
            ]
            logger.warning(
                "depth snapshot fetch failed "
                "(epoch=%s attempt=%s retry_in=%ss): %s",
                request.epoch,
                request.attempt,
                delay,
                exc,
            )
            await sleep(delay)
            await results.put(
                _DepthSnapshotFetchResult(request=request, error=str(exc))
            )
        finally:
            requests.task_done()

@dataclass(frozen=True)
class PushFlowEvent:
    """FlowEvent for webapp broadcast (IMBALANCE/ABSORPTION only, v1)."""
    event_time: Any
    symbol: str
    category: str
    side: str
    strength: Decimal
    detector: str
    detail: str


def load_profile(path: str | Path) -> ExchangeProfile:
    """Load an exchange profile YAML (YAMLReference §4) into an ExchangeProfile."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return ExchangeProfile.from_dict(data)


@dataclass(frozen=True)
class ReplayStats:
    raw_events: int
    invalid: int
    normalized: int
    duplicates: int
    reordered: int
    normalizer_rejected: int
    trades_stored: int
    candles_stored: int
    signals_stored: int
    final_cvd: Decimal
    analysis_count: int
    native_candles_stored: int = 0
    native_flow_events_stored: int = 0
    native_flow_outcomes_stored: int = 0
    footprint_bars_stored: int = 0
    footprint_levels_stored: int = 0


class ReplayPipeline:
    """Wires the CVD path for deterministic replay from a JSON Lines file."""

    def __init__(
        self,
        symbol: str,
        timeframe: str,
        profile: ExchangeProfile,
        parquet_path: str | Path,
        duckdb_path: str | Path,
        *,
        dedup_window: int = 10000,
        reorder_tolerance_ms: int = 500,
        batch_size: int = 1000,
        flush_interval_sec: int = 5,
        tick_size: Decimal = Decimal("0.1"),
    ) -> None:
        self.symbol = symbol
        self.timeframe = timeframe
        self.profile = profile
        self.parquet_path = parquet_path
        self.duckdb_path = duckdb_path
        self.dedup_window = dedup_window
        self.reorder_tolerance_ms = reorder_tolerance_ms
        self.batch_size = batch_size
        self.flush_interval_sec = flush_interval_sec
        self.tick_size = tick_size

    def __init__(
        self,
        symbol: str,
        timeframe: str,
        profile: ExchangeProfile,
        parquet_path: str | Path,
        duckdb_path: str | Path,
        *,
        dedup_window: int = 10000,
        reorder_tolerance_ms: int = 500,
        batch_size: int = 1000,
        flush_interval_sec: int = 5,
        tick_size: Decimal = Decimal("0.1"),
        replay_speed: float = 0.0,
        replay_monotonic: Callable[[], float] = time.monotonic,
        replay_sleep: Callable[[float], None] = time.sleep,
        cvd_slope_ref: Optional[Decimal] = None,
        imbalance_ratio_threshold: Decimal = Decimal("3.0"),
        imbalance_min_volume: Decimal = Decimal("50"),
        imbalance_ratio_cap: Decimal = Decimal("10.0"),
        imbalance_stack_count: int = 3,
        signal_w_cvd: Decimal = Decimal("1.0"),
        signal_w_fp: Decimal = Decimal("1.0"),
        signal_w_imb: Decimal = Decimal("1.0"),
        signal_confidence_threshold: Decimal = Decimal("0.6"),
        signal_absorption_veto_threshold: Decimal = Decimal("0.5"),
        signal_stack_ref: int = 3,
        absorption_window_sec: int = 10,
        absorption_price_stall_ticks: int = 1,
        absorption_volume_multiplier: Decimal = Decimal("2.0"),
        absorption_volume_ref_bars: int = 20,
        divergence_equal_pivot_policy: str = "first",
        divergence_min_price_move: Decimal = Decimal("0"),
        divergence_min_bar_distance: int = 0,
        flow_response_enabled: bool = True,
        flow_response_windows_sec: tuple[int, ...] = (30, 60, 180, 300, 900, 1800),
        flow_response_baseline_window_sec: int = 1800,
        flow_response_pressure_threshold: Decimal = Decimal("0.20"),
        flow_response_persistence_threshold: Decimal = Decimal("0.60"),
        flow_response_stall_bps: Decimal = Decimal("1.0"),
        flow_response_effective_bps: Decimal = Decimal("2.0"),
        flow_response_opposite_bps: Decimal = Decimal("1.0"),
        flow_response_min_trades: int = 20,
        flow_response_outcome_horizons_sec: tuple[int, ...] = (60, 180, 300, 600),
    ) -> None:
        self.symbol = symbol
        self.timeframe = timeframe
        self.profile = profile
        self.parquet_path = parquet_path
        self.duckdb_path = duckdb_path
        self.dedup_window = dedup_window
        self.reorder_tolerance_ms = reorder_tolerance_ms
        self.batch_size = batch_size
        self.flush_interval_sec = flush_interval_sec
        self.tick_size = tick_size
        if replay_speed < 0:
            raise ValueError("replay_speed must be >= 0")
        self.replay_speed = float(replay_speed)
        self._replay_monotonic = replay_monotonic
        self._replay_sleep = replay_sleep
        self.cvd_slope_ref = cvd_slope_ref
        self.imbalance_ratio_threshold = imbalance_ratio_threshold
        self.imbalance_min_volume = imbalance_min_volume
        self.imbalance_ratio_cap = imbalance_ratio_cap
        self.imbalance_stack_count = imbalance_stack_count
        self.signal_w_cvd = signal_w_cvd
        self.signal_w_fp = signal_w_fp
        self.signal_w_imb = signal_w_imb
        self.signal_confidence_threshold = signal_confidence_threshold
        self.signal_absorption_veto_threshold = signal_absorption_veto_threshold
        self.signal_stack_ref = signal_stack_ref
        self.absorption_window_sec = absorption_window_sec
        self.absorption_price_stall_ticks = absorption_price_stall_ticks
        self.absorption_volume_multiplier = absorption_volume_multiplier
        self.absorption_volume_ref_bars = absorption_volume_ref_bars
        self.divergence_equal_pivot_policy = divergence_equal_pivot_policy
        self.divergence_min_price_move = divergence_min_price_move
        self.divergence_min_bar_distance = divergence_min_bar_distance
        self.flow_response_enabled = flow_response_enabled
        self.flow_response_windows_sec = tuple(flow_response_windows_sec)
        self.flow_response_baseline_window_sec = flow_response_baseline_window_sec
        self.flow_response_pressure_threshold = flow_response_pressure_threshold
        self.flow_response_persistence_threshold = flow_response_persistence_threshold
        self.flow_response_stall_bps = flow_response_stall_bps
        self.flow_response_effective_bps = flow_response_effective_bps
        self.flow_response_opposite_bps = flow_response_opposite_bps
        self.flow_response_min_trades = flow_response_min_trades
        self.flow_response_outcome_horizons_sec = tuple(flow_response_outcome_horizons_sec)
        # Latest closed 5m/15m candles; used by the trend filter in the next phase.
        self.higher_timeframe_candles: dict = {}
        self.trend_state = None
        self.divergence = None
        self.on_accepted_trade: Optional[Callable] = None
        self.on_trade: Optional[Callable] = None
        self.on_candle: Optional[Callable] = None
        self.on_analysis: Optional[Callable] = None
        self.on_absorption_state: Optional[Callable] = None
        self.on_flow_response: Optional[Callable] = None
        self._last_bar_close = None
        self._last_fp_bar = None
        self._last_event_time = None

    @classmethod
    def from_config(
        cls,
        config: Any,
        profile: ExchangeProfile,
        parquet_path: str | Path,
        duckdb_path: str | Path,
    ) -> "ReplayPipeline":
        sig = config.signal
        imb = config.imbalance
        abs_ = config.absorption
        div = config.divergence
        fr = config.flow_response
        replay = getattr(config, "replay", None)
        cvd_ref = sig.cvd_slope_ref  # decision 11: use signal.cvd_slope_ref
        return cls(
            symbol=config.market.symbol,
            timeframe=config.market.bar_timeframe,
            profile=profile,
            parquet_path=parquet_path,
            duckdb_path=duckdb_path,
            dedup_window=config.normalizer.dedup_window,
            reorder_tolerance_ms=config.normalizer.reorder_tolerance_ms,
            batch_size=config.database.batch_size,
            flush_interval_sec=config.database.flush_interval_sec,
            tick_size=Decimal(str(config.market.tick_size)),
            replay_speed=(
                float(getattr(replay, "speed", 0.0))
                if bool(getattr(replay, "enabled", False))
                else 0.0
            ),
            cvd_slope_ref=Decimal(str(cvd_ref)) if cvd_ref is not None else None,
            imbalance_ratio_threshold=Decimal(str(imb.ratio_threshold)),
            imbalance_min_volume=_resolve_imbalance_min_volume(imb.min_volume),
            imbalance_ratio_cap=Decimal(str(imb.ratio_cap)),
            imbalance_stack_count=imb.stack_count,
            signal_w_cvd=Decimal(str(sig.weight["cvd"])),
            signal_w_fp=Decimal(str(sig.weight["footprint"])),
            signal_w_imb=Decimal(str(sig.weight["imbalance"])),
            signal_confidence_threshold=Decimal(str(sig.confidence_threshold)),
            signal_absorption_veto_threshold=Decimal(str(sig.absorption_veto_threshold)),
            signal_stack_ref=sig.stack_ref,
            absorption_window_sec=abs_.window_sec,
            absorption_price_stall_ticks=abs_.price_stall_ticks,
            absorption_volume_multiplier=Decimal(str(abs_.volume_multiplier)),
            absorption_volume_ref_bars=abs_.volume_ref_bars,
            divergence_equal_pivot_policy=div.equal_pivot_policy,
            divergence_min_price_move=Decimal(div.min_price_move),
            divergence_min_bar_distance=div.min_bar_distance,
            flow_response_enabled=fr.enabled,
            flow_response_windows_sec=tuple(fr.windows_sec),
            flow_response_baseline_window_sec=fr.baseline_window_sec,
            flow_response_pressure_threshold=Decimal(fr.pressure_threshold),
            flow_response_persistence_threshold=Decimal(fr.persistence_threshold),
            flow_response_stall_bps=Decimal(fr.stall_bps),
            flow_response_effective_bps=Decimal(fr.effective_bps),
            flow_response_opposite_bps=Decimal(fr.opposite_bps),
            flow_response_min_trades=fr.min_trades,
            flow_response_outcome_horizons_sec=tuple(fr.outcome_horizons_sec),
        )

    def run(self, data_path: str | Path) -> ReplayStats:
        raws = ReplaySource(data_path).read_all()
        normalizer = DataNormalizer(self.profile, self.dedup_window, self.reorder_tolerance_ms)
        cvd = CvdCalculator(self.symbol, self.timeframe)
        higher_timeframes = MultiTimeframeCandleAggregator(self.symbol)
        native_coordinator = NativeExecutionCoordinator(self.symbol)
        divergence_detector = CvdDivergenceDetector(
            equal_pivot_policy=self.divergence_equal_pivot_policy,
            min_price_move=self.divergence_min_price_move,
            min_bar_distance=self.divergence_min_bar_distance,
        )
        flow_response_detector = None
        flow_response_tracker = None
        if self.flow_response_enabled:
            flow_response_detector = FlowPriceResponseDetector(
                windows_sec=self.flow_response_windows_sec,
                baseline_window_sec=self.flow_response_baseline_window_sec,
                pressure_threshold=self.flow_response_pressure_threshold,
                persistence_threshold=self.flow_response_persistence_threshold,
                stall_bps=self.flow_response_stall_bps,
                effective_bps=self.flow_response_effective_bps,
                opposite_bps=self.flow_response_opposite_bps,
                min_trades=self.flow_response_min_trades,
            )
            flow_response_tracker = FlowResponseOutcomeTracker(
                self.flow_response_outcome_horizons_sec
            )
        self.flow_response = ()
        self.flow_response_events = deque(maxlen=5000)
        self.flow_response_outcomes = deque(maxlen=5000)
        producer = SnapshotProducer(self.symbol)
        replay_origin_source_ns: int | None = None
        replay_last_source_ns: int | None = None
        self._last_market_state = None
        footprint = FootprintCalculator(self.symbol, self.timeframe)
        book_state = OrderBookStateManager(symbol=self.symbol)
        volume_ref = VolumeRefTracker(bars=self.absorption_volume_ref_bars)
        absorption = AbsorptionDetector(
            window_sec=self.absorption_window_sec,
            price_stall_ticks=self.absorption_price_stall_ticks,
            volume_multiplier=self.absorption_volume_multiplier,
            volume_ref=volume_ref,
            book_state=book_state,
        )
        imbalance_detector = ImbalanceDetector(
            ratio_threshold=self.imbalance_ratio_threshold,
            min_volume=self.imbalance_min_volume,
            ratio_cap=self.imbalance_ratio_cap,
            stack_count=self.imbalance_stack_count,
            volume_ref=volume_ref,
        )
        signal_engine = SignalEngine(
            w_cvd=self.signal_w_cvd,
            w_fp=self.signal_w_fp,
            w_imb=self.signal_w_imb,
            confidence_threshold=self.signal_confidence_threshold,
            absorption_veto_threshold=self.signal_absorption_veto_threshold,
        )
        storage = StorageWriter(
            self.parquet_path,
            self.duckdb_path,
            batch_size=self.batch_size,
            flush_interval_sec=self.flush_interval_sec,
        )

        invalid = 0
        analysis_count = 0
        analysis_engine = AnalysisEngine()
        pacing_origin_source_ns: int | None = None
        pacing_origin_monotonic: float | None = None
        self._last_bar_close = None
        self._last_fp_bar = None
        self._last_event_time = None

        def pace(event_time: datetime) -> None:
            """Map replay source time to wall time; speed=0 remains deterministic fast."""
            nonlocal pacing_origin_source_ns, pacing_origin_monotonic
            if self.replay_speed == 0:
                return
            source_ns = _to_source_ns(event_time)
            if pacing_origin_source_ns is None:
                pacing_origin_source_ns = source_ns
                pacing_origin_monotonic = self._replay_monotonic()
                return
            assert pacing_origin_monotonic is not None
            source_elapsed = max(0.0, (source_ns - pacing_origin_source_ns) / 1e9)
            target_elapsed = source_elapsed / self.replay_speed
            wall_elapsed = self._replay_monotonic() - pacing_origin_monotonic
            delay = target_elapsed - wall_elapsed
            if delay > 0:
                self._replay_sleep(delay)

        def handle(normalized) -> None:
            nonlocal analysis_count, replay_origin_source_ns, replay_last_source_ns
            pace(normalized.event_time)
            event_source_ns = _to_source_ns(normalized.event_time)
            if replay_origin_source_ns is None:
                replay_origin_source_ns = event_source_ns
            replay_last_source_ns = event_source_ns
            self._last_event_time = normalized.event_time
            if self.on_accepted_trade is not None:
                try:
                    self.on_accepted_trade(normalized)
                except Exception:
                    logger.exception(
                        "accepted-trade observer failed; replay analysis continues"
                    )
            producer.observe_trade(normalized)
            storage.add_trade(trade_to_row(normalized))
            native_coordinator.process(normalized, storage)
            if flow_response_detector is not None and flow_response_tracker is not None:
                snapshots = flow_response_detector.process(normalized)
                if snapshots:
                    self.flow_response = snapshots
                    for _snap in snapshots:
                        producer.observe_flow_response(_snap)
                    events = flow_response_tracker.register(snapshots)
                    self.flow_response_events.extend(events)
                    for event in events:
                        storage.add_flow_response_event(flow_response_event_to_row(event))
                    if self.on_flow_response is not None:
                        self.on_flow_response(snapshots)
                outcomes = flow_response_tracker.observe_trade(normalized)
                self.flow_response_outcomes.extend(outcomes)
                for outcome in outcomes:
                    storage.add_flow_response_outcome(flow_response_outcome_to_row(outcome))
            if self.on_trade is not None:
                self.on_trade(normalized)
            cvd_result = cvd.process(normalized)
            if cvd_result.update is not None:
                producer.observe_cvd(cvd_result.update)
            if cvd_result.accepted:
                closed_higher = higher_timeframes.process(normalized)
                self.higher_timeframe_candles.update(closed_higher)
            fp_closed = footprint.process_trade(normalized)
            _observe_absorption_state(
                absorption,
                normalized,
                self.on_absorption_state,
            )
            if cvd_result.closed_candle is not None:
                detected_divergence = divergence_detector.update(cvd_result.closed_candle)
                # Spec §3.2: event indicators are silent on non-fire bars.
                # Assign every bar (None when nothing fired) — fixes stale-persist bug.
                self.divergence = detected_divergence
                storage.add_candle(candle_to_row(cvd_result.closed_candle))
                if fp_closed is None:
                    logger.warning(
                        "E9001 footprint bar did not close with candle bar_time=%s",
                        cvd_result.closed_candle.bar_time,
                    )
                    self._last_fp_bar = None
                    if self.on_candle is not None:
                        self.on_candle(cvd_result.closed_candle)
                else:
                    # Persist only bars closed by a real timeframe rollover.  The
                    # final/forming bar emitted by ``finalize`` remains transient.
                    storage.add_footprint_bar(fp_closed)
                    _bar_result = _evaluate_and_store(
                        cvd_result.closed_candle, fp_closed,
                        imbalance_detector, signal_engine, storage,
                        self.cvd_slope_ref, self.signal_stack_ref,
                        volume_ref, absorption, analysis_engine, trend_state=self.trend_state,
                    )
                    producer.observe_absorption(_bar_result.absorption_result)
                    producer.observe_imbalance(_bar_result.imbalance_result)
                    self._last_market_state = producer.build_market_state(
                        engine_time_ns=event_source_ns - replay_origin_source_ns,
                        source_time_ns=event_source_ns,
                        tick_size=self.tick_size,
                    )
                    self._last_bar_close = _bar_result
                    self._last_fp_bar = fp_closed
                    if self.on_candle is not None:
                        self.on_candle(cvd_result.closed_candle)
                    if (
                        _bar_result.analysis_result is not None
                        and self.on_analysis is not None
                    ):
                        self.on_analysis(_bar_result.analysis_result)
                    analysis_count += 1

        for raw in raws:
            if not default_validate(raw):
                invalid += 1
                continue
            kind = normalizer.classify_raw(raw)
            if kind == "depth":
                update = normalizer.process_depth(raw)
                if update is not None:
                    apply_result = book_state.apply(update)
                    book_snapshot = book_state.snapshot()
                    producer.observe_book_update(
                        update,
                        apply_result,
                        book_snapshot,
                        approved_tick_size=self.tick_size,
                    )
            else:
                for normalized in normalizer.process(raw):
                    handle(normalized)
        for normalized in normalizer.flush():
            handle(normalized)

        if flow_response_detector is not None and flow_response_tracker is not None:
            snapshots = flow_response_detector.finalize()
            if snapshots:
                self.flow_response = snapshots
                for _snap in snapshots:
                    producer.observe_flow_response(_snap)
                events = flow_response_tracker.register(snapshots)
                self.flow_response_events.extend(events)
                for event in events:
                    storage.add_flow_response_event(flow_response_event_to_row(event))
                if self.on_flow_response is not None:
                    self.on_flow_response(snapshots)

        native_coordinator.finalize(storage)
        final_candle = cvd.finalize()
        final_fp = footprint.finalize()
        if final_candle is not None:
            storage.add_candle(candle_to_row(final_candle))
            if final_fp is None:
                logger.warning("E9001 footprint final bar missing for bar_time=%s", final_candle.bar_time)
            else:
                _bar_result = _evaluate_and_store(
                    final_candle, final_fp,
                    imbalance_detector, signal_engine, storage,
                    self.cvd_slope_ref, self.signal_stack_ref,
                    volume_ref, absorption, analysis_engine, trend_state=self.trend_state,
                )
                producer.observe_absorption(_bar_result.absorption_result)
                producer.observe_imbalance(_bar_result.imbalance_result)
                final_source_ns = (
                    replay_last_source_ns
                    if replay_last_source_ns is not None
                    else _to_source_ns(final_candle.bar_time)
                )
                self._last_market_state = producer.build_market_state(
                    engine_time_ns=(
                        final_source_ns - replay_origin_source_ns
                        if replay_origin_source_ns is not None
                        else 0
                    ),
                    source_time_ns=final_source_ns,
                    tick_size=self.tick_size,
                )
                self._last_bar_close = _bar_result
                self._last_fp_bar = final_fp
                if self.on_candle is not None:
                    self.on_candle(final_candle)
                if (
                    _bar_result.analysis_result is not None
                    and self.on_analysis is not None
                ):
                    self.on_analysis(_bar_result.analysis_result)
                analysis_count += 1
        storage.close()

        return ReplayStats(
            raw_events=len(raws),
            invalid=invalid,
            normalized=normalizer.processed,
            duplicates=normalizer.duplicates,
            reordered=normalizer.reordered,
            normalizer_rejected=normalizer.rejected,
            trades_stored=storage.trades_written,
            candles_stored=storage.candles_written - native_coordinator.candles_written,
            signals_stored=storage.signals_written,
            final_cvd=cvd.cvd,
            analysis_count=analysis_count,
            native_candles_stored=native_coordinator.candles_written,
            native_flow_events_stored=len(native_coordinator.events),
            native_flow_outcomes_stored=len(native_coordinator.outcomes),
            footprint_bars_stored=storage.footprint_bars_written,
            footprint_levels_stored=storage.footprint_levels_written,
        )


def _to_source_ns(dt: datetime) -> int:
    """Convert a source datetime to UTC epoch nanoseconds."""

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    td = dt - epoch
    return (td.days * 86400 + td.seconds) * 1_000_000_000 + td.microseconds * 1000

def _to_engine_ns(dt: datetime, origin_source_ns: int | None) -> int:
    if origin_source_ns is None:
        return 0
    return _to_source_ns(dt) - origin_source_ns


def _observe_absorption_state(
    absorption: AbsorptionDetector,
    trade: Any,
    on_state: Optional[Callable],
) -> tuple[int, Optional[Any]]:
    """Update the tick-driven detector and publish only meaningful UI state changes."""

    previous = absorption.current()
    previous_events = absorption.events_detected
    absorption.observe_trade(trade)
    current = absorption.current()
    detected = absorption.events_detected > previous_events
    if on_state is not None and (detected or current != previous):
        on_state(trade.event_time, current)
    return previous_events, current



@dataclass(frozen=True)
class _BarCloseResult:
    """All outputs from a single bar-close evaluation."""
    analysis_result: Optional[Any]
    imbalance_result: ImbalanceResult
    signal_result: SignalResult
    absorption_result: Optional[Any]
    module_scores: dict  # {"cvd": Decimal|None, "footprint": Decimal|None, "imbalance": Decimal|None}
    imbalance_detector: Any = None  # exposed for webapp wall payload (Imbalance独立化)
    flow_events: Optional[list] = None  # exposed for ANALYSIS payload (Flow独立化)


def _evaluate_and_store(
    candle: Any,
    fp_bar: Any,
    imbalance_detector: ImbalanceDetector,
    signal_engine: SignalEngine,
    storage: StorageWriter,
    cvd_slope_ref: Optional[Decimal],
    stack_ref: int,
    volume_ref: VolumeRefTracker,
    absorption: AbsorptionDetector,
    analysis_engine: AnalysisEngine,
    flow_events: Optional[list] = None,
    on_webapp_flow_event: Optional[Callable] = None,
    imbalance_fire_state: Optional[dict] = None,
    trend_state: Any = None,
) -> _BarCloseResult:
    """Shared bar-close: volume_ref update -> Imbalance -> Signal -> Analysis -> storage.

    ``imbalance_fire_state`` (Pipeline-owned, mutable) holds per-direction cooldown
    state ({direction: {"bars_since": int, "last_net": Decimal}}) for webapp
    IMBALANCE flow events; the fire/suppress decision itself lives in the pure
    ``_imbalance_should_fire``.
    """
    imbalance_result = imbalance_detector.detect(fp_bar)

    buy_total = sum((lv.buy_volume for lv in fp_bar.levels), Decimal(0))
    sell_total = sum((lv.sell_volume for lv in fp_bar.levels), Decimal(0))
    if buy_total + sell_total == Decimal(0):
        logger.warning("E9001 zero footprint volume at bar_time=%s, fp score=0", candle.bar_time)

    per_level_volumes = [lv.buy_volume + lv.sell_volume for lv in fp_bar.levels]
    volume_ref.observe_bar(per_level_volumes)

    # CVD is now an independent native indicator (spec §9 step1); pull it out of
    # composite by passing None; CVD is rendered through its independent payload.
    s_cvd = None
    # Footprint is now an independent native indicator (spec §9 step2, same
    # treatment as CVD): pull it out of composite by passing None. Its native
    # reading (POC / Value Area) is computed webapp-side and rendered in the
    # footprint panel with a gear-adjustable VA%.
    s_fp = None
    # Imbalance is now an independent native indicator (spec §9 step2-3, same
    # treatment as CVD/Footprint): pull it out of composite by passing None. Its
    # native reading (stacked walls) is sent structured in the ANALYSIS payload
    # and rendered as the independent wall payload.
    s_imb = None
    absorption_result = absorption.current()
    signal_result = signal_engine.evaluate(
        s_cvd, s_fp, s_imb,
        absorption_result=absorption_result,
        flow_events=None,
    )
    storage.add_signal(signal_to_row(candle.bar_time, candle.symbol, signal_result))

    analysis_input = AnalysisInput(
        analysis_time=candle.bar_time,
        symbol=candle.symbol,
        signal_result=signal_result,
        cvd_delta=candle.delta,
        fp_buy_total=buy_total,
        fp_sell_total=sell_total,
        imbalance_result=imbalance_result,
        absorption_result=absorption_result,
    )
    return _BarCloseResult(
        analysis_result=analysis_engine.evaluate(analysis_input),
        imbalance_result=imbalance_result,
        signal_result=signal_result,
        absorption_result=absorption_result,
        module_scores={"cvd": s_cvd, "footprint": s_fp, "imbalance": s_imb},
        imbalance_detector=imbalance_detector,
        flow_events=flow_events,
    )


# ConnectFn: connect(url, streams) -> AsyncIterator[dict] (see ExchangeConnector).
ConnectFn = Callable[[str, list[str]], Awaitable[Any]]


@dataclass(frozen=True)
class LiveStats:
    """Outcome of a live capture session."""

    raw_out: int              # messages the connector pulled off the socket
    forwarded: int            # events forwarded past the receiver filter
    filtered: int             # frames dropped by the receiver (counted)
    normalized: int
    duplicates: int
    reordered: int
    normalizer_rejected: int
    trades_stored: int
    candles_stored: int
    signals_stored: int
    final_cvd: Decimal
    reconnects: int
    recorded: int             # events written to the JSON Lines replay recording
    # order-book stats (LiveVerification)
    book_snapshots_applied: int
    book_diffs_applied: int
    book_diffs_rejected_before_snapshot: int
    book_gaps_detected: int
    book_diffs_stale: int
    book_resyncs: int
    book_snapshot_fetch_failures: int
    absorption_events_detected: int
    # depth normalizer diagnostics
    depth_processed: int
    depth_rejected: int
    # liquidation stream (@forceOrder)
    liquidations_received: int
    # flow detector events
    flow_events_emitted: int
    native_candles_stored: int = 0
    native_flow_events_stored: int = 0
    native_flow_outcomes_stored: int = 0
    footprint_bars_stored: int = 0
    footprint_levels_stored: int = 0


class LivePipeline:
    """Live CVD path sourced from a real Binance Futures WebSocket (Phase6/B-2).

    Reuses the exact M4/M5/M6 components; only the data source differs from
    ReplayPipeline. Runs on a single asyncio event loop (ADR-003): a connector
    task and a receiver task feed a consumer that normalizes, computes CVD, and
    persists. Terminates on ``duration_sec``, ``max_trades``, a clean connector
    stop (finite/injected sources), or cancellation — always flushing buffered
    events and the final open bar (no silent loss).
    """

    def __init__(
        self,
        symbol: str,
        timeframe: str,
        profile: ExchangeProfile,
        ws_url: str,
        subscribe_streams: list[str],
        parquet_path: str | Path,
        duckdb_path: str | Path,
        *,
        dedup_window: int = 10000,
        reorder_tolerance_ms: int = 500,
        batch_size: int = 1000,
        flush_interval_sec: int = 5,
        tick_size: Decimal = Decimal("0.1"),
        queue_depth: int = 10000,
        overflow_policy: str = "drop_oldest_log",
        depth_sync_max_buffered_diffs: int = _DEPTH_SYNC_MAX_BUFFERED_DIFFS,
        depth_sync_max_attempts: int = _DEPTH_SYNC_MAX_ATTEMPTS,
        reconnect: bool = True,
        reconnect_delay_sec: int = 5,
        reconnect_max_retries: int = 0,
        connect_timeout_sec: int = 10,
        heartbeat_sec: int = 30,
        cvd_slope_ref: Optional[Decimal] = None,
        imbalance_ratio_threshold: Decimal = Decimal("3.0"),
        imbalance_min_volume: Decimal = Decimal("50"),
        imbalance_ratio_cap: Decimal = Decimal("10.0"),
        imbalance_stack_count: int = 3,
        signal_w_cvd: Decimal = Decimal("1.0"),
        signal_w_fp: Decimal = Decimal("1.0"),
        signal_w_imb: Decimal = Decimal("1.0"),
        signal_w_flow: Decimal = Decimal("1.0"),
        signal_confidence_threshold: Decimal = Decimal("0.6"),
        signal_absorption_veto_threshold: Decimal = Decimal("0.5"),
        signal_stack_ref: int = 3,
        absorption_window_sec: int = 10,
        absorption_price_stall_ticks: int = 1,
        absorption_volume_multiplier: Decimal = Decimal("2.0"),
        absorption_volume_ref_bars: int = 20,
        divergence_equal_pivot_policy: str = "first",
        divergence_min_price_move: Decimal = Decimal("0"),
        divergence_min_bar_distance: int = 0,
        mt5_enabled: bool = False,
        mt5_bind_address: str = "127.0.0.1",
        mt5_port: int = 5555,
        mt5_max_clients: int = 3,
        mt5_heartbeat_interval: float = 5.0,
        mt5_max_buffer_messages: int = 1000,
        on_trade: Optional[Callable] = None,
        on_accepted_trade: Optional[Callable] = None,
        on_candle: Optional[Callable] = None,
        on_analysis: Optional[Callable] = None,
        on_absorption_state: Optional[Callable] = None,
        on_liquidation: Optional[Callable] = None,
        on_flow_event: Optional[Callable] = None,
        on_webapp_flow_event: Optional[Callable] = None,
        on_flow_response: Optional[Callable] = None,
        on_native_candle: Optional[Callable] = None,
        flow_large_trade_min_qty: Decimal = Decimal("5.0"),
        flow_sweep_window_ms: int = 500,
        flow_sweep_min_qty: Decimal = Decimal("8.0"),
        flow_sweep_min_levels: int = 3,
        flow_sweep_cooldown_ms: int = 2000,
        flow_exhaustion_ratio: Decimal = Decimal("0.25"),
        flow_ua_min_vol: Decimal = Decimal("2.0"),
        flow_tape_window_ms: int = 5000,
        flow_tape_emit_interval_ms: int = 1000,
        flow_tape_pause_threshold_ms: int = 3000,
        flow_response_enabled: bool = True,
        flow_response_windows_sec: tuple[int, ...] = (30, 60, 180, 300, 900, 1800),
        flow_response_baseline_window_sec: int = 1800,
        flow_response_pressure_threshold: Decimal = Decimal("0.20"),
        flow_response_persistence_threshold: Decimal = Decimal("0.60"),
        flow_response_stall_bps: Decimal = Decimal("1.0"),
        flow_response_effective_bps: Decimal = Decimal("2.0"),
        flow_response_opposite_bps: Decimal = Decimal("1.0"),
        flow_response_min_trades: int = 20,
        flow_response_outcome_horizons_sec: tuple[int, ...] = (60, 180, 300, 600),
    ) -> None:
        self.symbol = symbol
        self.timeframe = timeframe
        self.profile = profile
        self.ws_url = ws_url
        self.subscribe_streams = list(subscribe_streams)
        self.parquet_path = parquet_path
        self.duckdb_path = duckdb_path
        self.dedup_window = dedup_window
        self.reorder_tolerance_ms = reorder_tolerance_ms
        self.batch_size = batch_size
        self.flush_interval_sec = flush_interval_sec
        self.tick_size = tick_size
        self.queue_depth = queue_depth
        self.overflow_policy = overflow_policy
        self.depth_sync_max_buffered_diffs = depth_sync_max_buffered_diffs
        self.depth_sync_max_attempts = depth_sync_max_attempts
        self.reconnect = reconnect
        self.reconnect_delay_sec = reconnect_delay_sec
        self.reconnect_max_retries = reconnect_max_retries
        self.connect_timeout_sec = connect_timeout_sec
        self.heartbeat_sec = heartbeat_sec
        self.cvd_slope_ref = cvd_slope_ref
        self.imbalance_ratio_threshold = imbalance_ratio_threshold
        self.imbalance_min_volume = imbalance_min_volume
        self.imbalance_ratio_cap = imbalance_ratio_cap
        self.imbalance_stack_count = imbalance_stack_count
        self.signal_w_cvd = signal_w_cvd
        self.signal_w_fp = signal_w_fp
        self.signal_w_imb = signal_w_imb
        self.signal_w_flow = signal_w_flow
        self.signal_confidence_threshold = signal_confidence_threshold
        self.signal_absorption_veto_threshold = signal_absorption_veto_threshold
        self.signal_stack_ref = signal_stack_ref
        self.absorption_window_sec = absorption_window_sec
        self.absorption_price_stall_ticks = absorption_price_stall_ticks
        self.absorption_volume_multiplier = absorption_volume_multiplier
        self.absorption_volume_ref_bars = absorption_volume_ref_bars
        self.divergence_equal_pivot_policy = divergence_equal_pivot_policy
        self.divergence_min_price_move = divergence_min_price_move
        self.divergence_min_bar_distance = divergence_min_bar_distance
        # Latest closed 5m/15m candles; used by the trend filter in the next phase.
        self.higher_timeframe_candles: dict = {}
        self.trend_state = None
        self.divergence = None
        self.mt5_enabled = mt5_enabled
        self.mt5_bind_address = mt5_bind_address
        self.mt5_port = mt5_port
        self.mt5_max_clients = mt5_max_clients
        self.mt5_heartbeat_interval = mt5_heartbeat_interval
        self.mt5_max_buffer_messages = mt5_max_buffer_messages
        self.on_trade = on_trade
        self.on_accepted_trade = on_accepted_trade
        self.on_candle = on_candle
        self.on_analysis = on_analysis
        self.on_absorption_state = on_absorption_state
        self.on_liquidation = on_liquidation
        self.on_flow_event = on_flow_event
        self.on_webapp_flow_event = on_webapp_flow_event
        self.on_flow_response = on_flow_response
        self.on_native_candle = on_native_candle
        self.flow_large_trade_min_qty = flow_large_trade_min_qty
        self.flow_sweep_window_ms = flow_sweep_window_ms
        self.flow_sweep_min_qty = flow_sweep_min_qty
        self.flow_sweep_min_levels = flow_sweep_min_levels
        self.flow_sweep_cooldown_ms = flow_sweep_cooldown_ms
        self.flow_exhaustion_ratio = flow_exhaustion_ratio
        self.flow_ua_min_vol = flow_ua_min_vol
        self.flow_tape_window_ms = flow_tape_window_ms
        self.flow_tape_emit_interval_ms = flow_tape_emit_interval_ms
        self.flow_tape_pause_threshold_ms = flow_tape_pause_threshold_ms
        self.flow_response_enabled = flow_response_enabled
        self.flow_response_windows_sec = tuple(flow_response_windows_sec)
        self.flow_response_baseline_window_sec = flow_response_baseline_window_sec
        self.flow_response_pressure_threshold = flow_response_pressure_threshold
        self.flow_response_persistence_threshold = flow_response_persistence_threshold
        self.flow_response_stall_bps = flow_response_stall_bps
        self.flow_response_effective_bps = flow_response_effective_bps
        self.flow_response_opposite_bps = flow_response_opposite_bps
        self.flow_response_min_trades = flow_response_min_trades
        self.flow_response_outcome_horizons_sec = tuple(flow_response_outcome_horizons_sec)

    @classmethod
    def from_config(
        cls,
        config: Any,
        profile: ExchangeProfile,
        *,
        parquet_path: str | Path | None = None,
        duckdb_path: str | Path | None = None,
    ) -> "LivePipeline":
        ws = config.websocket
        sig = config.signal
        imb = config.imbalance
        abs_ = config.absorption
        div = config.divergence
        fr = config.flow_response
        cvd_ref = sig.cvd_slope_ref
        return cls(
            symbol=config.market.symbol,
            timeframe=config.market.bar_timeframe,
            profile=profile,
            ws_url=ws.url,
            subscribe_streams=list(ws.subscribe_streams),
            parquet_path=parquet_path or config.database.parquet_path,
            duckdb_path=duckdb_path or config.database.duckdb_path,
            dedup_window=config.normalizer.dedup_window,
            reorder_tolerance_ms=config.normalizer.live_reorder_tolerance_ms,
            batch_size=config.database.batch_size,
            flush_interval_sec=config.database.flush_interval_sec,
            tick_size=Decimal(str(config.market.tick_size)),
            queue_depth=config.queue.default_depth,
            overflow_policy=config.queue.overflow_policy,
            reconnect=ws.reconnect,
            reconnect_delay_sec=ws.reconnect_delay_sec,
            reconnect_max_retries=ws.reconnect_max_retries,
            connect_timeout_sec=ws.connect_timeout_sec,
            heartbeat_sec=ws.heartbeat_sec,
            cvd_slope_ref=Decimal(str(cvd_ref)) if cvd_ref is not None else None,
            imbalance_ratio_threshold=Decimal(str(imb.ratio_threshold)),
            imbalance_min_volume=_resolve_imbalance_min_volume(imb.min_volume),
            imbalance_ratio_cap=Decimal(str(imb.ratio_cap)),
            imbalance_stack_count=imb.stack_count,
            signal_w_cvd=Decimal(str(sig.weight["cvd"])),
            signal_w_fp=Decimal(str(sig.weight["footprint"])),
            signal_w_imb=Decimal(str(sig.weight["imbalance"])),
            signal_w_flow=Decimal(str(sig.weight.get("flow", 1.0))),
            signal_confidence_threshold=Decimal(str(sig.confidence_threshold)),
            signal_absorption_veto_threshold=Decimal(str(sig.absorption_veto_threshold)),
            signal_stack_ref=sig.stack_ref,
            absorption_window_sec=abs_.window_sec,
            absorption_price_stall_ticks=abs_.price_stall_ticks,
            absorption_volume_multiplier=Decimal(str(abs_.volume_multiplier)),
            absorption_volume_ref_bars=abs_.volume_ref_bars,
            divergence_equal_pivot_policy=div.equal_pivot_policy,
            divergence_min_price_move=Decimal(div.min_price_move),
            divergence_min_bar_distance=div.min_bar_distance,
            mt5_enabled=config.mt5.enabled,
            mt5_bind_address=config.mt5.bind_address,
            mt5_port=config.mt5.port,
            mt5_max_clients=config.mt5.max_clients,
            mt5_heartbeat_interval=float(config.mt5.heartbeat_interval_sec),
            mt5_max_buffer_messages=config.mt5.max_buffer_messages,
            flow_large_trade_min_qty=Decimal(config.flow_detector.large_trade_min_qty),
            flow_sweep_window_ms=config.flow_detector.sweep_window_ms,
            flow_sweep_min_qty=Decimal(config.flow_detector.sweep_min_qty),
            flow_sweep_min_levels=config.flow_detector.sweep_min_levels,
            flow_sweep_cooldown_ms=config.flow_detector.sweep_cooldown_ms,
            flow_exhaustion_ratio=Decimal(config.flow_detector.exhaustion_ratio),
            flow_ua_min_vol=Decimal(config.flow_detector.ua_min_vol),
            flow_tape_window_ms=config.flow_detector.tape_window_ms,
            flow_tape_emit_interval_ms=config.flow_detector.tape_emit_interval_ms,
            flow_tape_pause_threshold_ms=config.flow_detector.tape_pause_threshold_ms,
            flow_response_enabled=fr.enabled,
            flow_response_windows_sec=tuple(fr.windows_sec),
            flow_response_baseline_window_sec=fr.baseline_window_sec,
            flow_response_pressure_threshold=Decimal(fr.pressure_threshold),
            flow_response_persistence_threshold=Decimal(fr.persistence_threshold),
            flow_response_stall_bps=Decimal(fr.stall_bps),
            flow_response_effective_bps=Decimal(fr.effective_bps),
            flow_response_opposite_bps=Decimal(fr.opposite_bps),
            flow_response_min_trades=fr.min_trades,
            flow_response_outcome_horizons_sec=tuple(fr.outcome_horizons_sec),
        )

    async def run_async(
        self,
        *,
        duration_sec: Optional[float] = None,
        max_trades: Optional[int] = None,
        record_path: str | Path | None = None,
        raw_recorder: Any | None = None,
        connect: Optional[ConnectFn] = None,
        event_filter: Callable[[Any], bool] = is_agg_trade_or_depth,
        treat_stream_end_as_disconnect: bool = True,
        poll_interval: float = 0.5,
        fetch_snapshot: Optional[Callable] = fetch_depth_snapshot,
        hook_observer: Any | None = None,
    ) -> LiveStats:
        """Run the live CVD+Absorption path until a stop condition; return a LiveStats.

        ``connect`` defaults to the real Binance transport; inject a fake
        ConnectFn (e.g. over ListTransport) for tests. ``record_path`` captures
        the forwarded stream and every applied REST depth snapshot as JSON
        Lines, so recorded depth diffs can be reconstructed exactly.
        ``raw_recorder`` is an independent optional append-only observation tap;
        when omitted, the pre-Stage-2A path is unchanged.
        """
        connect = connect or make_binance_connect(ping_interval=self.heartbeat_sec)

        owned_hook_observer = False
        hook_event_storage = None
        self.hook_observer_error = None
        self.hook_observer_failures = 0
        if hook_observer is None:
            hook_config_path = os.environ.get("HOOK_OBSERVER_CONFIG", "").strip()
            if hook_config_path:
                try:
                    from .observation.hook_storage import HookEventStorage
                    from .orderflow.hooks.config import (
                        ThresholdBook,
                        load_hook_observer_config,
                        validate_observe_only_playbooks,
                    )
                    from .orderflow.hooks.live import (
                        STAGE2C4_CALIBRATED_HOOK_IDS,
                        LiveHookObserver,
                        load_live_hook_config,
                    )

                    hook_config = load_hook_observer_config(hook_config_path)
                    live_config_path = os.environ.get(
                        "HOOK_LIVE_CONFIG",
                        str(
                            Path(hook_config_path).with_name(
                                "hook_live_observer.yaml"
                            )
                        ),
                    ).strip()
                    live_config = load_live_hook_config(live_config_path)
                    if hook_config.enabled and live_config.event_firing_enabled:
                        if not hook_config.storage.enabled:
                            raise RuntimeError(
                                "HookEvent firing requires storage.enabled=true"
                            )
                        if (
                            live_config.mode != "OBSERVE"
                            or live_config.execution_enabled
                        ):
                            raise RuntimeError(
                                "HookEvent firing must remain observe-only"
                            )
                        validate_observe_only_playbooks(hook_config.playbooks_path)
                        threshold_book = ThresholdBook.load(
                            hook_config.thresholds_path
                        )
                        calibrated = frozenset(
                            threshold_book.calibrated_hook_ids()
                        )
                        if calibrated != STAGE2C4_CALIBRATED_HOOK_IDS:
                            raise RuntimeError(
                                "Stage 2C-4 calibrated Hook set mismatch: "
                                f"expected={sorted(STAGE2C4_CALIBRATED_HOOK_IDS)} "
                                f"actual={sorted(calibrated)}"
                            )
                        if (
                            live_config.calibrated_hook_ids
                            != STAGE2C4_CALIBRATED_HOOK_IDS
                        ):
                            raise RuntimeError(
                                "Stage 2C-4 live allowlist mismatch: "
                                f"expected={sorted(STAGE2C4_CALIBRATED_HOOK_IDS)} "
                                f"actual={sorted(live_config.calibrated_hook_ids)}"
                            )
                        timeframe_seconds = {
                            "1s": 1,
                            "1m": 60,
                            "5m": 300,
                            "15m": 900,
                            "1h": 3600,
                            "4h": 14400,
                            "1d": 86400,
                        }.get(self.timeframe)
                        if timeframe_seconds is None:
                            raise RuntimeError(
                                "unsupported Hook price-structure timeframe: "
                                f"{self.timeframe}"
                            )
                        hook_event_storage = HookEventStorage(
                            hook_config.storage.root,
                            queue_depth=hook_config.storage.queue_depth,
                            batch_size=hook_config.storage.batch_size,
                            flush_interval_sec=(
                                hook_config.storage.flush_interval_sec
                            ),
                        )
                        hook_observer = LiveHookObserver(
                            symbol=self.symbol,
                            profile=self.profile,
                            thresholds=threshold_book,
                            sink=hook_event_storage,
                            timeframe_sec=timeframe_seconds,
                        )
                        owned_hook_observer = True
                        logger.info(
                            "Stage 2C-4 HookEvent observe firing enabled for %d "
                            "CALIBRATED Hooks; execution remains disconnected",
                            len(calibrated),
                        )
                except Exception as exc:
                    if hook_event_storage is not None:
                        with contextlib.suppress(Exception):
                            hook_event_storage.close()
                    hook_observer = None
                    self.hook_observer_error = f"{type(exc).__name__}: {exc}"
                    logger.exception(
                        "Stage 2C-4 HookEvent observe runtime did not start; "
                        "market pipeline continues"
                    )
        self.hook_observer = hook_observer

        def notify_hook(method: str, *args: Any, **kwargs: Any) -> Any:
            if hook_observer is None:
                return None
            try:
                callback = getattr(hook_observer, method)
                return callback(*args, **kwargs)
            except Exception as exc:
                self.hook_observer_failures += 1
                self.hook_observer_error = (
                    f"{method}: {type(exc).__name__}: {exc}"
                )
                logger.exception(
                    "Hook observer callback %s failed; market pipeline continues",
                    method,
                )
                return None

        out_q = BoundedEventQueue(self.queue_depth, self.overflow_policy, name="ws_out")
        norm_q = BoundedEventQueue(self.queue_depth, self.overflow_policy, name="receiver_out")

        connector = ExchangeConnector(
            url=self.ws_url,
            subscribe_streams=self.subscribe_streams,
            out_queue=out_q,
            connect=connect,
            reconnect=self.reconnect,
            reconnect_delay_sec=self.reconnect_delay_sec,
            reconnect_max_retries=self.reconnect_max_retries,
            connect_timeout_sec=self.connect_timeout_sec,
            heartbeat_sec=self.heartbeat_sec,
            treat_stream_end_as_disconnect=treat_stream_end_as_disconnect,
        )
        legacy_recorder = JsonlRecorder(record_path) if record_path else None
        recorder = (
            _RecorderFanout(legacy_recorder, raw_recorder)
            if legacy_recorder is not None or raw_recorder is not None
            else None
        )
        depth_sync: Optional[DepthSyncCoordinator] = None
        snapshot_requests: asyncio.Queue[SnapshotRequest] = asyncio.Queue()
        snapshot_results: asyncio.Queue[_DepthSnapshotFetchResult] = asyncio.Queue()
        depth_sync_actions: asyncio.Queue[DepthSyncAction] = asyncio.Queue()
        prebuffered_depth_events: dict[int, dict[str, Any]] = {}
        if fetch_snapshot is not None:
            depth_sync = DepthSyncCoordinator(
                max_buffered_diffs=self.depth_sync_max_buffered_diffs,
                max_attempts=self.depth_sync_max_attempts,
            )

        def notify_depth_sync(message: dict[str, Any]) -> None:
            """Buffer valid pre-sync depth after raw recording and before forward."""
            if (
                depth_sync is None
                or not depth_sync.is_valid_depth_update(message)
                or depth_sync.state
                in {DepthSyncState.SYNCED, DepthSyncState.SYNC_FAILED}
            ):
                return
            action = depth_sync.observe_depth(message)
            prebuffered_depth_events[id(message)] = message
            if (
                action.request is not None
                or action.is_verified
                or action.state is DepthSyncState.SYNC_FAILED
            ):
                depth_sync_actions.put_nowait(action)

        receiver = DataReceiver(
            out_q,
            norm_q,
            recorder=recorder,
            validate=lambda m: default_validate(m) and event_filter(m),
            on_valid_message=notify_depth_sync,
        )
        normalizer = DataNormalizer(self.profile, self.dedup_window, self.reorder_tolerance_ms)
        cvd = CvdCalculator(self.symbol, self.timeframe)
        higher_timeframes = MultiTimeframeCandleAggregator(self.symbol)
        native_coordinator = NativeExecutionCoordinator(
            self.symbol,
            on_candle=self.on_native_candle,
        )
        self.native_coordinator = native_coordinator
        divergence_detector = CvdDivergenceDetector(
            equal_pivot_policy=self.divergence_equal_pivot_policy,
            min_price_move=self.divergence_min_price_move,
            min_bar_distance=self.divergence_min_bar_distance,
        )
        flow_response_detector = None
        flow_response_tracker = None
        self.flow_response_warm_start_trades = 0
        self.flow_response_warm_start_error = None
        session_vwap_seed = None
        self.session_vwap_warm_start_trades = 0
        self.session_vwap_warm_start_complete = False
        self.session_vwap_warm_start_error = None
        try:
            session_vwap_seed = load_latest_session_vwap_seed(
                self.duckdb_path, self.symbol
            )
        except Exception as exc:  # fail closed; live accumulation remains available
            self.session_vwap_warm_start_error = str(exc)
            logger.warning("session VWAP warm-start skipped: %s", exc)
        if self.flow_response_enabled:
            flow_response_detector = FlowPriceResponseDetector(
                windows_sec=self.flow_response_windows_sec,
                baseline_window_sec=self.flow_response_baseline_window_sec,
                pressure_threshold=self.flow_response_pressure_threshold,
                persistence_threshold=self.flow_response_persistence_threshold,
                stall_bps=self.flow_response_stall_bps,
                effective_bps=self.flow_response_effective_bps,
                opposite_bps=self.flow_response_opposite_bps,
                min_trades=self.flow_response_min_trades,
            )
            flow_response_tracker = FlowResponseOutcomeTracker(
                self.flow_response_outcome_horizons_sec
            )
            try:
                seed_trades = load_recent_flow_response_trades(
                    self.duckdb_path,
                    self.symbol,
                    self.flow_response_baseline_window_sec,
                )
                self.flow_response_warm_start_trades = flow_response_detector.warm_start(
                    seed_trades
                )
                if self.flow_response_warm_start_trades:
                    logger.info(
                        "flow response warm-start loaded %d persisted trades",
                        self.flow_response_warm_start_trades,
                    )
            except Exception as exc:  # warm start is recoverable; live accumulation continues
                self.flow_response_warm_start_error = str(exc)
                logger.warning("flow response warm-start skipped: %s", exc)
        footprint = FootprintCalculator(self.symbol, self.timeframe)
        book_state = OrderBookStateManager(symbol=self.symbol)
        volume_ref = VolumeRefTracker(bars=self.absorption_volume_ref_bars)
        absorption = AbsorptionDetector(
            window_sec=self.absorption_window_sec,
            price_stall_ticks=self.absorption_price_stall_ticks,
            volume_multiplier=self.absorption_volume_multiplier,
            volume_ref=volume_ref,
            book_state=book_state,
        )
        imbalance_detector = ImbalanceDetector(
            ratio_threshold=self.imbalance_ratio_threshold,
            min_volume=self.imbalance_min_volume,
            ratio_cap=self.imbalance_ratio_cap,
            stack_count=self.imbalance_stack_count,
            volume_ref=volume_ref,
        )
        signal_engine = SignalEngine(
            w_cvd=self.signal_w_cvd,
            w_fp=self.signal_w_fp,
            w_imb=self.signal_w_imb,
            w_flow=self.signal_w_flow,
            confidence_threshold=self.signal_confidence_threshold,
            absorption_veto_threshold=self.signal_absorption_veto_threshold,
        )
        storage = BackgroundStorageWriter(
            self.parquet_path,
            self.duckdb_path,
            batch_size=self.batch_size,
            flush_interval_sec=self.flush_interval_sec,
            queue_depth=self.queue_depth,
        )
        # OI polling appends through the same ordered background writer. All
        # Parquet/DuckDB I/O stays off the latency-critical market-data loop.
        self.storage_writer = storage

        analysis_engine = AnalysisEngine()

        # Flow detectors (Phase A)
        _large_trade_det = LargeTradeDetector(self.flow_large_trade_min_qty)
        _sweep_det = SweepDetector(
            window_ms=self.flow_sweep_window_ms,
            min_qty=self.flow_sweep_min_qty,
            min_levels=self.flow_sweep_min_levels,
            tick_size=Decimal("1"),
            cooldown_ms=self.flow_sweep_cooldown_ms,
        )
        _exhaustion_det = ExhaustionDetector(self.flow_exhaustion_ratio)
        _ua_det = UnfinishedAuctionDetector(self.flow_ua_min_vol)
        _tape_analyzer = TapeAnalyzer(
            window_ms=self.flow_tape_window_ms,
            emit_interval_ms=self.flow_tape_emit_interval_ms,
            pause_threshold_ms=self.flow_tape_pause_threshold_ms,
        )
        flow_event_buffer: deque = deque(maxlen=500)
        flow_events_emitted = 0

        def _emit_flow(evt: FlowEvent) -> None:
            nonlocal flow_events_emitted
            flow_event_buffer.append(evt)
            flow_events_emitted += 1
            if self.on_flow_event is not None:
                self.on_flow_event(evt)

        # Expose key objects for webapp callbacks.
        self.book_manager = book_state
        self.volume_ref_tracker = volume_ref
        self.cvd_calculator = cvd
        self.absorption_detector = absorption
        # SelfMonitor v1 / BAR_UPDATE: read-only exposure for the webapp layer.
        self._connector = connector
        self._footprint_calculator = footprint
        self._last_event_time = None
        self._last_bar_close: Optional[_BarCloseResult] = None
        self._last_fp_bar: Optional[Any] = None
        self.flow_event_buffer = flow_event_buffer
        self.flow_response = ()
        self.flow_response_events = deque(maxlen=5000)
        self.flow_response_outcomes = deque(maxlen=5000)
        producer = SnapshotProducer(self.symbol)
        if session_vwap_seed is not None:
            try:
                self.session_vwap_warm_start_trades = producer.seed_session_vwap(
                    session_vwap_seed
                )
                self.session_vwap_warm_start_complete = (
                    session_vwap_seed.session_complete
                )
                logger.info(
                    "session VWAP warm-start loaded %d persisted trades; complete=%s",
                    self.session_vwap_warm_start_trades,
                    self.session_vwap_warm_start_complete,
                )
            except Exception as exc:  # fail closed; do not stop the market pipeline
                self.session_vwap_warm_start_error = str(exc)
                logger.warning("session VWAP seed rejected: %s", exc)
        self._last_market_state = None
        self._snapshot_producer = producer
        # Per-direction cooldown state for webapp IMBALANCE flow events (Task-A).
        self._imbalance_fire_state: dict = {}

        # Liquidation tracking (in-memory, not persisted — design decision #1).
        liquidation_buffer: deque = deque(maxlen=200)
        long_liq_notional = Decimal(0)
        short_liq_notional = Decimal(0)
        liquidations_received = 0

        # Start MT5 server if enabled.
        mt5_server: Optional[MT5Server] = None
        if self.mt5_enabled:
            mt5_server = MT5Server(
                bind_address=self.mt5_bind_address,
                port=self.mt5_port,
                max_clients=self.mt5_max_clients,
                heartbeat_interval=self.mt5_heartbeat_interval,
                max_buffer_messages=self.mt5_max_buffer_messages,
            )
            await mt5_server.start()

        def handle(normalized) -> None:
            if self.on_accepted_trade is not None:
                try:
                    self.on_accepted_trade(normalized)
                except Exception:
                    logger.exception(
                        "accepted-trade observer failed; live analysis continues"
                    )
            storage.add_trade(trade_to_row(normalized))
            native_coordinator.process(normalized, storage)
            self._last_event_time = normalized.event_time
            producer.observe_trade(normalized)
            if flow_response_detector is not None and flow_response_tracker is not None:
                snapshots = flow_response_detector.process(normalized)
                if snapshots:
                    self.flow_response = snapshots
                    for _snap in snapshots:
                        producer.observe_flow_response(_snap)
                    notify_hook(
                        "observe_flow_response",
                        snapshots,
                        received_time=datetime.now(timezone.utc),
                    )
                    events = flow_response_tracker.register(snapshots)
                    self.flow_response_events.extend(events)
                    for event in events:
                        storage.add_flow_response_event(flow_response_event_to_row(event))
                    if self.on_flow_response is not None:
                        self.on_flow_response(snapshots)
                outcomes = flow_response_tracker.observe_trade(normalized)
                self.flow_response_outcomes.extend(outcomes)
                for outcome in outcomes:
                    storage.add_flow_response_outcome(flow_response_outcome_to_row(outcome))
            if self.on_trade is not None:
                self.on_trade(normalized)
            cvd_result = cvd.process(normalized)
            if cvd_result.update is not None:
                producer.observe_cvd(cvd_result.update)
            if cvd_result.accepted:
                closed_higher = higher_timeframes.process(normalized)
                self.higher_timeframe_candles.update(closed_higher)
            fp_closed = footprint.process_trade(normalized)
            prev_abs, ar = _observe_absorption_state(
                absorption,
                normalized,
                self.on_absorption_state,
            )
            if self.on_webapp_flow_event is not None and absorption.events_detected > prev_abs:
                if ar is not None:
                    side = "BUY" if ar.classification == "BUY_ABSORPTION" else "SELL"
                    self.on_webapp_flow_event(PushFlowEvent(
                        event_time=normalized.event_time,
                        symbol=self.symbol,
                        category="ABSORPTION",
                        side=side,
                        strength=ar.strength,
                        detector="AbsorptionDetector",
                        detail=f"window_sec={self.absorption_window_sec}",
                    ))
            # flow detectors: trade path
            _lt = _large_trade_det.process(normalized)
            if _lt is not None:
                _emit_flow(_lt)
            _sw = _sweep_det.process(normalized)
            if _sw is not None:
                _emit_flow(_sw)
            _ta = _tape_analyzer.process(normalized)
            if _ta is not None:
                _emit_flow(_ta)
            if cvd_result.closed_candle is not None:
                notify_hook(
                    "observe_candle",
                    cvd_result.closed_candle,
                    received_time=normalized.event_time,
                )
                detected_divergence = divergence_detector.update(cvd_result.closed_candle)
                # Spec §3.2: event indicators are silent on non-fire bars.
                # Assign every bar (None when nothing fired) — fixes stale-persist bug.
                self.divergence = detected_divergence
                storage.add_candle(candle_to_row(cvd_result.closed_candle))
                if fp_closed is None:
                    logger.warning(
                        "E9001 footprint bar did not close with candle bar_time=%s",
                        cvd_result.closed_candle.bar_time,
                    )
                    if self.on_candle is not None:
                        self.on_candle(cvd_result.closed_candle)
                else:
                    # History contains closed bars only; do not persist the
                    # forming bar returned by ``finalize`` during shutdown.
                    storage.add_footprint_bar(fp_closed)
                    # flow detectors: bar-close path (before signal so they're included)
                    _ex = _exhaustion_det.process(fp_closed)
                    if _ex is not None:
                        _emit_flow(_ex)
                    _ua = _ua_det.process(fp_closed)
                    if _ua is not None:
                        _emit_flow(_ua)
                    bar_close = _evaluate_and_store(
                        cvd_result.closed_candle, fp_closed,
                        imbalance_detector, signal_engine, storage,
                        self.cvd_slope_ref, self.signal_stack_ref,
                        volume_ref, absorption, analysis_engine, trend_state=self.trend_state,
                        flow_events=list(flow_event_buffer),
                        on_webapp_flow_event=self.on_webapp_flow_event,
                        imbalance_fire_state=self._imbalance_fire_state,
                    )
                    producer.observe_absorption(bar_close.absorption_result)
                    producer.observe_imbalance(bar_close.imbalance_result)
                    self._last_market_state = producer.build_market_state(
                        engine_time_ns=time.monotonic_ns(),
                        source_time_ns=_to_source_ns(normalized.event_time),
                        tick_size=self.tick_size,
                    )
                    self._last_bar_close = bar_close
                    self._last_fp_bar = fp_closed
                    if self.on_candle is not None:
                        self.on_candle(cvd_result.closed_candle)
                    if bar_close.analysis_result is not None and self.on_analysis is not None:
                        self.on_analysis(bar_close.analysis_result)
                    if mt5_server is not None and bar_close.analysis_result is not None:
                        asyncio.ensure_future(
                            mt5_server.broadcast(analysis_to_mt5_message(bar_close.analysis_result))
                        )

        self.book_resync_counters = BookResyncCounters()

        def apply_verified_depth_sync(action: DepthSyncAction) -> None:
            """Apply a strictly verified batch from this sole book-owning coroutine."""
            if not action.is_verified or action.snapshot is None:
                raise RuntimeError("depth sync action is not strictly verified")

            snapshot_update = normalizer.process_depth(action.snapshot)
            diff_updates = [
                normalizer.process_depth(raw_diff) for raw_diff in action.diffs
            ]
            if snapshot_update is None or any(
                update is None for update in diff_updates
            ):
                raise RuntimeError("verified depth batch failed normalization")

            snapshot_result = book_state.apply(snapshot_update)
            if not snapshot_result.applied:
                raise RuntimeError("verified depth snapshot was not applied")
            book_state.apply_initial_sync(snapshot_update.final_update_id)
            notify_hook(
                "observe_depth",
                snapshot_update,
                snapshot_result,
                book_state.snapshot(),
                received_time=datetime.now(timezone.utc),
            )

            for raw_diff, update in zip(action.diffs, diff_updates):
                if update is None:  # narrowed above; retained for runtime clarity
                    raise RuntimeError("verified depth diff normalized to None")
                apply_result = book_state.apply(update)
                if not apply_result.applied or apply_result.gap_detected:
                    raise RuntimeError(
                        "coordinator-verified depth diff was rejected "
                        f"(U={raw_diff.get('U')}, u={raw_diff.get('u')}, "
                        f"pu={raw_diff.get('pu')})"
                    )
                book_snapshot = book_state.snapshot()
                producer.observe_book_update(
                    update,
                    apply_result,
                    book_snapshot,
                    approved_tick_size=self.tick_size,
                )
                notify_hook(
                    "observe_depth",
                    update,
                    apply_result,
                    book_snapshot,
                    received_time=datetime.now(timezone.utc),
                )

            if action.epoch > 1:
                self.book_resync_counters.resyncs += 1
                logger.info(
                    "order book strict resync verified: epoch=%s attempt=%s "
                    "snap_id=%s bridge_U=%s bridge_u=%s resyncs=%s",
                    action.epoch,
                    action.attempt,
                    action.snapshot["u"],
                    action.diffs[0]["U"],
                    action.diffs[0]["u"],
                    self.book_resync_counters.resyncs,
                )
            else:
                logger.info(
                    "initial order book strict sync verified: attempt=%s "
                    "snap_id=%s bridge_U=%s bridge_u=%s",
                    action.attempt,
                    action.snapshot["u"],
                    action.diffs[0]["U"],
                    action.diffs[0]["u"],
                )

        def handle_depth_sync_action(action: DepthSyncAction) -> None:
            if action.request is not None:
                snapshot_requests.put_nowait(action.request)
            if action.state is DepthSyncState.SYNC_FAILED:
                if recorder is not None:
                    recorder.record_sync_action(action)
                logger.error(
                    "depth synchronization failed closed: %s",
                    action.failure_reason,
                )
                return
            if action.is_verified:
                try:
                    apply_verified_depth_sync(action)
                    if recorder is not None:
                        recorder.record_sync_action(action)
                except Exception as exc:
                    if depth_sync is not None:
                        failed = depth_sync.fail(
                            f"verified depth batch apply failed: {exc}"
                        )
                        if recorder is not None:
                            recorder.record_sync_action(failed)
                        logger.exception(
                            "depth synchronization failed closed: %s",
                            failed.failure_reason,
                        )

        def drain_depth_sync_actions() -> None:
            while True:
                try:
                    action = depth_sync_actions.get_nowait()
                except asyncio.QueueEmpty:
                    break
                try:
                    handle_depth_sync_action(action)
                finally:
                    depth_sync_actions.task_done()

        def drain_snapshot_results() -> None:
            if depth_sync is None:
                return
            while True:
                try:
                    result = snapshot_results.get_nowait()
                except asyncio.QueueEmpty:
                    break
                try:
                    if result.error is not None:
                        action = depth_sync.observe_fetch_failure(
                            result.request, result.error
                        )
                    elif result.snapshot is not None:
                        action = depth_sync.observe_snapshot(
                            result.request, result.snapshot
                        )
                    else:
                        action = depth_sync.fail(
                            "snapshot worker returned neither candidate nor error"
                        )
                    handle_depth_sync_action(action)
                except Exception as exc:
                    failed = depth_sync.fail(
                        f"snapshot candidate processing failed: {exc}"
                    )
                    handle_depth_sync_action(failed)
                    logger.exception("snapshot candidate processing failed")
                finally:
                    snapshot_results.task_done()

        def process_live_depth(raw_depth: dict[str, Any]) -> None:
            """Route one depth event; only this main consumer mutates book_state."""
            if depth_sync is None:
                update = normalizer.process_depth(raw_depth)
                if update is not None:
                    apply_result = book_state.apply(update)
                    book_snapshot = book_state.snapshot()
                    producer.observe_book_update(
                        update,
                        apply_result,
                        book_snapshot,
                        approved_tick_size=self.tick_size,
                    )
                    notify_hook(
                        "observe_depth",
                        update,
                        apply_result,
                        book_snapshot,
                        received_time=datetime.now(timezone.utc),
                    )
                return

            buffered_raw = prebuffered_depth_events.get(id(raw_depth))
            if buffered_raw is raw_depth:
                del prebuffered_depth_events[id(raw_depth)]
                return
            if (
                prebuffered_depth_events
                and depth_sync.state
                in {DepthSyncState.SYNCED, DepthSyncState.SYNC_FAILED}
            ):
                # This unmarked depth arrived after synchronization. Any older
                # pre-sync events not seen by the main queue were explicitly
                # dropped by that queue, but remain covered by the coordinator's
                # verified raw batch. Release their identity guards now.
                prebuffered_depth_events.clear()

            if not depth_sync.is_valid_depth_update(raw_depth):
                # Invalid depth cannot open or participate in a strict bridge.
                normalizer.process_depth(raw_depth)
                logger.warning(
                    "depth update excluded from strict synchronization: "
                    "integer U/u/pu contract not satisfied"
                )
                return

            if depth_sync.state is DepthSyncState.SYNCED:
                update = normalizer.process_depth(raw_depth)
                if update is None:
                    return
                apply_result = book_state.apply(update)
                book_snapshot = book_state.snapshot()
                producer.observe_book_update(
                    update,
                    apply_result,
                    book_snapshot,
                    approved_tick_size=self.tick_size,
                )
                notify_hook(
                    "observe_depth",
                    update,
                    apply_result,
                    book_snapshot,
                    received_time=datetime.now(timezone.utc),
                )
                if apply_result.gap_detected:
                    handle_depth_sync_action(depth_sync.start_resync(raw_depth))
                return

            handle_depth_sync_action(depth_sync.observe_depth(raw_depth))

        loop = asyncio.get_event_loop()
        connector_task = asyncio.create_task(connector.run())
        receiver_task = asyncio.create_task(receiver.run())

        # The worker starts idle. The receiver tap enqueues the first request
        # only after recording the first valid depthUpdate. It fetches and records
        # candidates but never touches the mutable order book (ADR-003).
        book_supervisor_task: Optional[asyncio.Task] = None
        if fetch_snapshot is not None:
            book_supervisor_task = asyncio.create_task(_book_resync_supervisor(
                symbol=self.symbol,
                fetch_snapshot=fetch_snapshot,
                requests=snapshot_requests,
                results=snapshot_results,
                counters=self.book_resync_counters,
                recorder=recorder,
            ))
        deadline = (loop.time() + duration_sec) if duration_sec is not None else None
        trades_in = 0

        try:
            while True:
                drain_depth_sync_actions()
                drain_snapshot_results()
                now = loop.time()
                if deadline is not None and now >= deadline:
                    break
                # Natural end: the connector stopped (finite/injected source) and
                # everything it produced has been drained.
                source_drained = (
                    connector_task.done()
                    and out_q.empty()
                    and norm_q.empty()
                    and receiver.forwarded + receiver.invalid
                    >= connector.messages_out
                )
                if source_drained:
                    if depth_sync is None or depth_sync.state in {
                        DepthSyncState.WAITING_FOR_FIRST_DEPTH,
                        DepthSyncState.SYNCED,
                        DepthSyncState.SYNC_FAILED,
                    }:
                        break
                    if depth_sync.state in {
                        DepthSyncState.VERIFYING_INITIAL_BRIDGE,
                        DepthSyncState.VERIFYING_RESYNC_BRIDGE,
                    }:
                        handle_depth_sync_action(
                            depth_sync.fail(
                                "depth stream ended before a strict snapshot bridge "
                                "could be verified"
                            )
                        )
                        break
                timeout = poll_interval
                if deadline is not None:
                    timeout = min(poll_interval, max(0.0, deadline - now))
                try:
                    raw = await asyncio.wait_for(norm_q.get(), timeout=timeout)
                except asyncio.TimeoutError:
                    drain_depth_sync_actions()
                    drain_snapshot_results()
                    storage.tick()  # time-based flush while idle
                    continue
                if raw is STOP:
                    break
                drain_depth_sync_actions()
                drain_snapshot_results()
                kind = normalizer.classify_raw(raw)
                if kind == "liquidation":
                    try:
                        liq_evt = normalize_raw_liquidation(raw, self.profile)
                        liquidation_buffer.append(liq_evt)
                        if liq_evt.side == "SELL":
                            long_liq_notional += liq_evt.price * liq_evt.quantity
                        else:
                            short_liq_notional += liq_evt.price * liq_evt.quantity
                        liquidations_received += 1
                        if self.on_liquidation is not None:
                            self.on_liquidation(liq_evt)
                    except NormalizationError as exc:
                        logger.warning("liquidation normalization failed: %s", exc)
                elif kind == "depth":
                    process_live_depth(raw)
                else:
                    notify_hook(
                        "observe_raw_trade",
                        raw,
                        received_time=datetime.now(timezone.utc),
                    )
                    for normalized in normalizer.process(raw):
                        handle(normalized)
                    trades_in += 1
                storage.tick()
                if max_trades is not None and trades_in >= max_trades:
                    break
        finally:
            connector.stop()
            if book_supervisor_task is not None:
                book_supervisor_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await book_supervisor_task
            # Unblock the receiver and let it forward anything still queued.
            await out_q.put(STOP)
            with contextlib.suppress(Exception):
                await asyncio.wait_for(receiver_task, timeout=5)
            drain_depth_sync_actions()
            drain_snapshot_results()
            # Drain any events the receiver forwarded after the consumer stopped.
            while not norm_q.empty():
                pending = norm_q.get_nowait()
                if pending is STOP:
                    continue
                kind = normalizer.classify_raw(pending)
                if kind == "liquidation":
                    try:
                        liq_evt = normalize_raw_liquidation(pending, self.profile)
                        liquidation_buffer.append(liq_evt)
                        if liq_evt.side == "SELL":
                            long_liq_notional += liq_evt.price * liq_evt.quantity
                        else:
                            short_liq_notional += liq_evt.price * liq_evt.quantity
                        liquidations_received += 1
                        if self.on_liquidation is not None:
                            self.on_liquidation(liq_evt)
                    except NormalizationError as exc:
                        logger.warning("liquidation normalization failed: %s", exc)
                elif kind == "depth":
                    process_live_depth(pending)
                else:
                    notify_hook(
                        "observe_raw_trade",
                        pending,
                        received_time=datetime.now(timezone.utc),
                    )
                    for normalized in normalizer.process(pending):
                        handle(normalized)
            drain_depth_sync_actions()
            drain_snapshot_results()
            for normalized in normalizer.flush():
                handle(normalized)
            if flow_response_detector is not None and flow_response_tracker is not None:
                snapshots = flow_response_detector.finalize()
                if snapshots:
                    self.flow_response = snapshots
                    for _snap in snapshots:
                        producer.observe_flow_response(_snap)
                    events = flow_response_tracker.register(snapshots)
                    self.flow_response_events.extend(events)
                    for event in events:
                        storage.add_flow_response_event(flow_response_event_to_row(event))
                    if self.on_flow_response is not None:
                        self.on_flow_response(snapshots)
            final_candle = cvd.finalize()
            final_fp = footprint.finalize()
            if final_candle is not None:
                storage.add_candle(candle_to_row(final_candle))
                if final_fp is None:
                    logger.warning("E9001 footprint final bar missing for bar_time=%s", final_candle.bar_time)
                else:
                    _ex = _exhaustion_det.process(final_fp)
                    if _ex is not None:
                        _emit_flow(_ex)
                    _ua = _ua_det.process(final_fp)
                    if _ua is not None:
                        _emit_flow(_ua)
                    bar_close = _evaluate_and_store(
                        final_candle, final_fp,
                        imbalance_detector, signal_engine, storage,
                        self.cvd_slope_ref, self.signal_stack_ref,
                        volume_ref, absorption, analysis_engine, trend_state=self.trend_state,
                        flow_events=list(flow_event_buffer),
                        on_webapp_flow_event=self.on_webapp_flow_event,
                        imbalance_fire_state=self._imbalance_fire_state,
                    )
                    producer.observe_absorption(bar_close.absorption_result)
                    producer.observe_imbalance(bar_close.imbalance_result)
                    self._last_market_state = producer.build_market_state(
                        engine_time_ns=time.monotonic_ns(),
                        source_time_ns=_to_source_ns(
                            self._last_event_time
                            if self._last_event_time is not None
                            else final_candle.bar_time
                        ),
                        tick_size=self.tick_size,
                    )
                    if mt5_server is not None and bar_close.analysis_result is not None:
                        await mt5_server.broadcast(
                            analysis_to_mt5_message(bar_close.analysis_result)
                        )
            native_coordinator.finalize(storage)
            storage.close()
            if mt5_server is not None:
                await mt5_server.stop()
            if owned_hook_observer and hook_observer is not None:
                with contextlib.suppress(Exception):
                    hook_observer.close()
            if recorder is not None:
                recorder.close()
            if not connector_task.done():
                connector_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await connector_task

        return LiveStats(
            raw_out=connector.messages_out,
            forwarded=receiver.forwarded,
            filtered=receiver.invalid,
            normalized=normalizer.processed,
            duplicates=normalizer.duplicates,
            reordered=normalizer.reordered,
            normalizer_rejected=normalizer.rejected,
            trades_stored=storage.trades_written,
            candles_stored=storage.candles_written - native_coordinator.candles_written,
            signals_stored=storage.signals_written,
            final_cvd=cvd.cvd,
            reconnects=connector.reconnect_count,
            recorded=(recorder.written if recorder is not None else 0),
            book_snapshots_applied=book_state.snapshots_applied,
            book_diffs_applied=book_state.diffs_applied,
            book_diffs_rejected_before_snapshot=book_state.diffs_rejected_before_snapshot,
            book_gaps_detected=book_state.gaps_detected,
            book_diffs_stale=book_state.diffs_stale,
            book_resyncs=self.book_resync_counters.resyncs,
            book_snapshot_fetch_failures=self.book_resync_counters.fetch_failures,
            absorption_events_detected=absorption.events_detected,
            depth_processed=normalizer.depth_processed,
            depth_rejected=normalizer.depth_rejected,
            liquidations_received=liquidations_received,
            flow_events_emitted=flow_events_emitted,
            native_candles_stored=native_coordinator.candles_written,
            native_flow_events_stored=len(native_coordinator.events),
            native_flow_outcomes_stored=len(native_coordinator.outcomes),
            footprint_bars_stored=storage.footprint_bars_written,
            footprint_levels_stored=storage.footprint_levels_written,
        )

    def run(self, **kwargs: Any) -> LiveStats:
        """Synchronous entry point (wraps run_async in asyncio.run)."""
        return asyncio.run(self.run_async(**kwargs))



