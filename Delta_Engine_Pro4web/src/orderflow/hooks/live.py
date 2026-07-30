"""Observe-only live orchestration for calibrated Stage 2C Hook detectors.

This module has no Strategy Engine or execution dependency.  It converts the
same A/C/D/G measurements used by the Stage 2C calibration replay into
``HookEvent`` objects through ``ThresholdBook`` and persists only events that
pass a CALIBRATED threshold.
"""

from __future__ import annotations

import logging
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

import yaml

from src.normalization.normalizer import (
    ExchangeProfile,
    NormalizationError,
    normalize_raw,
)

from .config import ThresholdBook
from .dom_features import DomFeatureCache
from .dom_iceberg import DomIcebergDetector
from .dom_liquidity import DomLiquidityDetector
from .dom_quote_motion import DomQuoteMotionDetector
from .dom_wall import DomWallDetector
from .flow_transition import FlowTransitionDetector
from .interaction import InteractionDetector
from .models import HookCandidate, HookEvent, HookSide, as_utc
from .price_structure import PriceStructureDetector
from .quality import DomDataQualityGate
from .runtime import HookEventSink, HookRuntime


logger = logging.getLogger("orderflow.hooks.live")

_ZERO = Decimal(0)
STAGE2C4_CALIBRATED_HOOK_IDS = frozenset(
    [
        *(f"A{index:02d}" for index in range(1, 25)),
        "C06",
        "D07",
        "D08",
        *(f"G{index:02d}" for index in range(1, 12)),
    ]
)


@dataclass(frozen=True)
class LiveHookConfig:
    """Independent fail-closed control plane for live HookEvent observation."""

    event_firing_enabled: bool
    mode: str
    execution_enabled: bool
    calibrated_hook_ids: frozenset[str]


def load_live_hook_config(path: str | Path) -> LiveHookConfig:
    """Load live firing controls without changing capture campaign identity."""
    config_path = Path(path)
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("live Hook config root must be a mapping")
    allowed = {
        "schema_version",
        "event_firing_enabled",
        "mode",
        "execution_enabled",
        "calibrated_hook_ids",
    }
    unknown = set(raw) - allowed
    missing = allowed - set(raw)
    if unknown or missing:
        raise ValueError(
            f"live Hook config keys invalid: missing={sorted(missing)} "
            f"unknown={sorted(unknown)}"
        )
    if raw["schema_version"] != 1:
        raise ValueError("live Hook config schema_version must be 1")
    if not isinstance(raw["event_firing_enabled"], bool):
        raise ValueError("event_firing_enabled must be boolean")
    if raw["mode"] != "OBSERVE":
        raise ValueError("live Hook config mode must be OBSERVE")
    if raw["execution_enabled"] is not False:
        raise ValueError("live Hook config execution_enabled must be false")
    hook_ids = raw["calibrated_hook_ids"]
    if (
        not isinstance(hook_ids, list)
        or not hook_ids
        or any(not isinstance(item, str) or not item for item in hook_ids)
    ):
        raise ValueError("calibrated_hook_ids must be a non-empty string list")
    if len(hook_ids) != len(set(hook_ids)):
        raise ValueError("calibrated_hook_ids must not contain duplicates")
    return LiveHookConfig(
        event_firing_enabled=raw["event_firing_enabled"],
        mode=raw["mode"],
        execution_enabled=raw["execution_enabled"],
        calibrated_hook_ids=frozenset(hook_ids),
    )


class LiveHookObserver:
    """Feed live pipeline observations into calibration-gated Hook detectors."""

    def __init__(
        self,
        *,
        symbol: str,
        profile: ExchangeProfile,
        thresholds: ThresholdBook,
        sink: HookEventSink,
        timeframe_sec: int = 60,
        detector_version: str = "stage2c4-live-v1",
    ) -> None:
        if timeframe_sec < 1:
            raise ValueError("timeframe_sec must be positive")
        self.symbol = symbol.upper()
        self.profile = profile
        self.sink = sink
        self.runtime = HookRuntime(
            thresholds,
            detector_version=detector_version,
            sink=sink,
        )
        self.detector_version = detector_version
        self.quality = DomDataQualityGate()
        self.dom_cache = DomFeatureCache(depth_levels=50)
        self.dom_wall = DomWallDetector()
        self.dom_liquidity = DomLiquidityDetector()
        self.dom_quote = DomQuoteMotionDetector()
        self.dom_iceberg = DomIcebergDetector(episode_window_ms=5_000)
        self.interaction = InteractionDetector()
        self.flow_transition = FlowTransitionDetector(min_aligned_windows=2)
        self.price_structure = PriceStructureDetector(
            lookback_bars=10,
            timeframe_sec=timeframe_sec,
            round_increment=Decimal("50"),
            volume_node_bin_size=Decimal("1"),
        )
        self._timeframe_sec = int(timeframe_sec)
        self._pending_dom_trades: list[tuple[Any, datetime]] = []
        self.candidates_by_hook: Counter[str] = Counter()
        self.events_by_hook: Counter[str] = Counter()
        self.observer_errors = 0
        self.last_error: str | None = None
        self._last_summary_log = 0.0
        self._closed = False

    @staticmethod
    def _received_at(
        received_time: datetime | None,
        source_time: datetime,
    ) -> datetime:
        received = as_utc(
            received_time or datetime.now(timezone.utc),
            "received_time",
        )
        return max(received, as_utc(source_time, "source_time"))

    def _record_error(self, operation: str, exc: Exception) -> None:
        self.observer_errors += 1
        self.last_error = f"{operation}: {type(exc).__name__}: {exc}"
        logger.exception("live Hook observer %s failed; market pipeline continues", operation)

    def _submit(
        self,
        candidates: Iterable[HookCandidate],
    ) -> tuple[HookEvent, ...]:
        batch = tuple(candidates)
        self.candidates_by_hook.update(candidate.hook_id for candidate in batch)
        events = self.runtime.submit(batch)
        self.events_by_hook.update(event.hook_id for event in events)
        now = time.monotonic()
        if events and now - self._last_summary_log >= 10:
            self._last_summary_log = now
            logger.info(
                "HookEvent observe summary total=%d by_hook=%s",
                self.runtime.events_emitted,
                dict(sorted(self.events_by_hook.items())),
            )
        return events

    def observe_raw_trade(
        self,
        payload: dict[str, Any],
        *,
        received_time: datetime | None = None,
    ) -> None:
        """Retain raw-arrival trade attribution for the next DOM interval."""
        try:
            trade = normalize_raw(payload, self.profile)
            if trade.symbol.upper() != self.symbol:
                return
            received = self._received_at(received_time, trade.event_time)
            self._pending_dom_trades.append((trade, received))
        except NormalizationError:
            return
        except Exception as exc:
            self._record_error("observe_raw_trade", exc)

    def _clear_dom_interval(self) -> None:
        self._pending_dom_trades = []

    def observe_depth(
        self,
        update: Any,
        apply_result: Any,
        snapshot: Any | None,
        *,
        received_time: datetime | None = None,
    ) -> tuple[HookEvent, ...]:
        """Process one already-applied authoritative live book update."""
        try:
            quality = self.quality.observe(update, apply_result)
            if getattr(apply_result, "gap_detected", False):
                self.dom_cache.reset()
                self._clear_dom_interval()
                return ()
            if not getattr(apply_result, "applied", False) or snapshot is None:
                return ()
            if not self.quality.is_valid:
                self.dom_cache.reset()
                self._clear_dom_interval()
                return ()

            received = self._received_at(received_time, update.event_time)
            flags = (quality.reason,) if quality.reason else ()
            delta = self.dom_cache.process(
                snapshot,
                source_time=update.event_time,
                received_time=received,
                quality_status=quality.status,
                quality_flags=flags,
            )
            if delta is None:
                self._clear_dom_interval()
                return ()

            previous = delta.previous
            current = delta.current
            interval_trades: list[tuple[Any, datetime]] = []
            future_trades: list[tuple[Any, datetime]] = []
            for trade, trade_received in self._pending_dom_trades:
                if trade.event_time > current.source_time:
                    future_trades.append((trade, trade_received))
                elif previous is not None and trade.event_time > previous.source_time:
                    interval_trades.append((trade, trade_received))
            self._pending_dom_trades = future_trades

            executed_bid: dict[Decimal, Decimal] = defaultdict(Decimal)
            executed_ask: dict[Decimal, Decimal] = defaultdict(Decimal)
            for trade, _trade_received in interval_trades:
                executed = executed_ask if trade.side == "BUY" else executed_bid
                executed[trade.price] += trade.quantity

            emitted: list[HookEvent] = []
            emitted.extend(self._submit(self.dom_wall.process(
                delta,
                executed_bid=executed_bid,
                executed_ask=executed_ask,
            )))
            emitted.extend(self._submit(self.dom_liquidity.process(delta)))
            emitted.extend(self._submit(self.dom_quote.process(delta)))

            if previous is not None:
                wall_inputs = (
                    (
                        HookSide.BID,
                        previous.bid_wall_price,
                        previous.bid_quantity(previous.bid_wall_price),
                        current.bid_quantity(previous.bid_wall_price),
                        executed_bid.get(previous.bid_wall_price, _ZERO),
                    ),
                    (
                        HookSide.ASK,
                        previous.ask_wall_price,
                        previous.ask_quantity(previous.ask_wall_price),
                        current.ask_quantity(previous.ask_wall_price),
                        executed_ask.get(previous.ask_wall_price, _ZERO),
                    ),
                )
                for side, price, before, after, aggressive in wall_inputs:
                    emitted.extend(self._submit(
                        self.interaction.observe_wall_trade(
                            symbol=self.symbol,
                            wall_side=side,
                            price=price,
                            before_quantity=before,
                            after_quantity=after,
                            aggressive_quantity=aggressive,
                            event_time=current.source_time,
                            received_time=current.received_time,
                            source_sequence=str(current.sequence),
                            bid=current.best_bid,
                            ask=current.best_ask,
                        )
                    ))
                for trade, trade_received in interval_trades:
                    emitted.extend(self._submit(
                        self.dom_iceberg.process_trade(
                            trade,
                            before=previous,
                            after=current,
                            received_time=trade_received,
                        )
                    ))
            return tuple(emitted)
        except Exception as exc:
            self._record_error("observe_depth", exc)
            return ()

    def observe_flow_response(
        self,
        snapshots: Iterable[Any],
        *,
        received_time: datetime | None = None,
    ) -> tuple[HookEvent, ...]:
        try:
            batch = tuple(snapshots)
            if not batch:
                return ()
            latest_source = max(as_utc(row.event_time) for row in batch)
            received = self._received_at(received_time, latest_source)
            return self._submit(
                self.flow_transition.process(batch, received_time=received)
            )
        except Exception as exc:
            self._record_error("observe_flow_response", exc)
            return ()

    def observe_candle(
        self,
        candle: Any,
        *,
        received_time: datetime | None = None,
    ) -> tuple[HookEvent, ...]:
        try:
            bar_time = as_utc(candle.bar_time, "candle.bar_time")
            close_time = bar_time + timedelta(seconds=self._timeframe_sec)
            received = self._received_at(received_time, close_time)
            return self._submit(
                self.price_structure.process(candle, received_time=received)
            )
        except Exception as exc:
            self._record_error("observe_candle", exc)
            return ()

    def stats(self) -> dict[str, Any]:
        threshold_book = self.runtime.thresholds
        storage_stats = (
            self.sink.stats()
            if callable(getattr(self.sink, "stats", None))
            else {}
        )
        return {
            "status": "ACTIVE" if not self._closed else "CLOSED",
            "detector_version": self.detector_version,
            "calibrated_hook_ids": list(threshold_book.calibrated_hook_ids()),
            "candidates_seen": self.runtime.candidates_seen,
            "candidates_by_hook": dict(sorted(self.candidates_by_hook.items())),
            "events_emitted": self.runtime.events_emitted,
            "events_by_hook": dict(sorted(self.events_by_hook.items())),
            "duplicates_suppressed": self.runtime.duplicates_suppressed,
            "sink_rejected": self.runtime.sink_rejected,
            "suppressed_uncalibrated": threshold_book.suppressed_uncalibrated,
            "suppressed_metric_mismatch": threshold_book.suppressed_metric_mismatch,
            "suppressed_threshold": threshold_book.suppressed_threshold,
            "suppressed_quality": threshold_book.suppressed_quality,
            "suppressed_manifest_mismatch": (
                threshold_book.suppressed_manifest_mismatch
            ),
            "observer_errors": self.observer_errors,
            "last_error": self.last_error,
            "storage": storage_stats,
        }

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        close = getattr(self.sink, "close", None)
        if callable(close):
            close()
        logger.info("HookEvent observe final summary: %s", self.stats())
