"""Dry-run distribution collection for Stage 2C-2 Hook candidates.

This tool replays committed records from Hook Observer ``full`` sessions on the
host.  It never writes threshold/config/capture files.  Candidate values are
spooled to a temporary DuckDB database so the 72-hour input can be processed
session by session without retaining all values in memory.

The default target set is A01-A24, C03-C08, D06-D08, F01-F05 and G01-G11.
E01-E06 and C09 are intentionally excluded because they require liquidation
records.  F01-F05 remain in the result with count=0 when, as in Stage 2C-2,
the full journal contains no open-interest samples.

Usage:
    python tools/calibrate_hooks.py
    python tools/calibrate_hooks.py --output-json C:/tmp/hook_distribution.json
    python tools/calibrate_hooks.py --max-sessions 1 --max-records-per-session 50000
"""

from __future__ import annotations

import argparse
import bisect
import concurrent.futures
import hashlib
import json
import logging
import sys
import tempfile
import time
from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

# Make the project root importable when run as a script.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import duckdb  # noqa: E402
import yaml  # noqa: E402

from src.config import load_config  # noqa: E402
from src.normalization.normalizer import (  # noqa: E402
    DataNormalizer,
    ExchangeProfile,
    NormalizationError,
    normalize_raw,
)
from src.observation.hook_replay import JournalReplay  # noqa: E402
from src.orderflow.absorption import AbsorptionResult  # noqa: E402
from src.orderflow.cvd import CvdCalculator  # noqa: E402
from src.orderflow.flow_price_response import (  # noqa: E402
    FlowPriceResponseDetector,
    FlowResponseSnapshot,
)
from src.orderflow.footprint import FootprintCalculator  # noqa: E402
from src.orderflow.hooks.dom_features import DomFeatureCache  # noqa: E402
from src.orderflow.hooks.dom_iceberg import DomIcebergDetector  # noqa: E402
from src.orderflow.hooks.dom_liquidity import DomLiquidityDetector  # noqa: E402
from src.orderflow.hooks.dom_quote_motion import DomQuoteMotionDetector  # noqa: E402
from src.orderflow.hooks.dom_wall import DomWallDetector  # noqa: E402
from src.orderflow.hooks.flow_transition import FlowTransitionDetector  # noqa: E402
from src.orderflow.hooks.interaction import InteractionDetector  # noqa: E402
from src.orderflow.hooks.models import (  # noqa: E402
    HookCandidate,
    HookQualityStatus,
    HookSide,
)
from src.orderflow.hooks.price_structure import PriceStructureDetector  # noqa: E402
from src.orderflow.orderbook import (  # noqa: E402
    OrderBookSnapshot,
    OrderBookStateManager,
)
from src.orderflow.volume_ref import VolumeRefTracker  # noqa: E402


DEFAULT_CAMPAIGN_ROOT = (
    PROJECT_ROOT
    / "data_05M"
    / "hook_observer"
    / "campaigns"
    / "stage2a_20260726_xz"
    / "full"
)
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "config.yaml"
DEFAULT_PROFILE = PROJECT_ROOT / "config" / "profiles" / "binance.yaml"

A_HOOKS = tuple(f"A{index:02d}" for index in range(1, 25))
C_HOOKS = tuple(f"C{index:02d}" for index in range(3, 9))
D_HOOKS = ("D06", "D07", "D08")
F_HOOKS = tuple(f"F{index:02d}" for index in range(1, 6))
G_HOOKS = tuple(f"G{index:02d}" for index in range(1, 12))
TARGET_HOOKS = A_HOOKS + C_HOOKS + D_HOOKS + F_HOOKS + G_HOOKS
TARGET_HOOK_SET = frozenset(TARGET_HOOKS)
QUANTILES = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99)


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _decimal_text(value: Any) -> str:
    parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    if not parsed.is_finite():
        raise ValueError(f"candidate value is not finite: {value!r}")
    return format(parsed, "f")


def _display_number(value: Any) -> str:
    if value is None:
        return "—"
    parsed = Decimal(str(value))
    if parsed == 0:
        return "0"
    absolute = abs(parsed)
    if absolute >= Decimal("1000000000") or absolute < Decimal("0.000001"):
        return f"{parsed:.8E}"
    text = f"{parsed:.10f}".rstrip("0").rstrip(".")
    return text or "0"


def _json_number(value: Any) -> str | None:
    return None if value is None else _display_number(value)


def _campaign_manifest_hash(session_dirs: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for session_dir in session_dirs:
        digest.update(session_dir.name.encode("utf-8"))
        digest.update(b"\0")
        path = session_dir / "manifest_events.jsonl"
        if not path.is_file():
            digest.update(b"MISSING")
            continue
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


class CandidateStore:
    """Transactional, disk-backed candidate spool with exact input decimals."""

    def __init__(self, database_path: Path, *, batch_size: int = 50_000) -> None:
        self.database_path = database_path
        self.batch_size = batch_size
        self.connection = duckdb.connect(str(database_path))
        self.connection.execute("SET threads = 1")
        self.connection.execute(
            "CREATE TABLE samples (hook_id VARCHAR NOT NULL, value DECIMAL(38,18) NOT NULL)"
        )
        self._hook_ids: list[str] = []
        self._values: list[str] = []
        self._in_transaction = False
        self.total_rows = 0

    def begin_session(self) -> None:
        if self._in_transaction:
            raise RuntimeError("candidate transaction already active")
        self.connection.execute("BEGIN TRANSACTION")
        self._in_transaction = True

    def add(self, candidates: Iterable[HookCandidate]) -> int:
        added = 0
        for candidate in candidates:
            if candidate.hook_id not in TARGET_HOOK_SET:
                continue
            self._hook_ids.append(candidate.hook_id)
            self._values.append(_decimal_text(candidate.metric_value))
            added += 1
        if len(self._hook_ids) >= self.batch_size:
            self._flush()
        return added

    def _flush(self) -> None:
        if not self._hook_ids:
            return
        self.connection.execute(
            """
            INSERT INTO samples
            SELECT
                unnest(?::VARCHAR[]),
                CAST(unnest(?::VARCHAR[]) AS DECIMAL(38,18))
            """,
            [self._hook_ids, self._values],
        )
        self.total_rows += len(self._hook_ids)
        self._hook_ids = []
        self._values = []

    def commit_session(self) -> None:
        if not self._in_transaction:
            raise RuntimeError("no candidate transaction active")
        self._flush()
        self.connection.execute("COMMIT")
        self._in_transaction = False

    def rollback_session(self) -> None:
        self._hook_ids = []
        self._values = []
        if self._in_transaction:
            self.connection.execute("ROLLBACK")
            self._in_transaction = False
        self.total_rows = int(
            self.connection.execute("SELECT count(*) FROM samples").fetchone()[0]
        )

    def statistics(self) -> list[dict[str, Any]]:
        return _statistics_from_source(
            self.connection,
            "SELECT hook_id, value FROM samples",
        )

    def close(self) -> None:
        if self._in_transaction:
            self.rollback_session()
        self.connection.close()


def _statistics_from_source(
    connection: Any,
    source_sql: str,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        f"""
            SELECT
                hook_id,
                count(*) AS sample_count,
                min(value) AS minimum,
                max(value) AS maximum,
                avg(value) AS mean,
                median(value) AS median,
                quantile_cont(value, [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99])
                    AS quantiles,
                stddev_pop(value) AS standard_deviation
            FROM ({source_sql}) AS candidate_source
            GROUP BY hook_id
            ORDER BY hook_id
        """
    ).fetchall()
    found: dict[str, dict[str, Any]] = {}
    for row in rows:
        quantiles = row[6]
        found[str(row[0])] = {
            "hook_id": str(row[0]),
            "count": int(row[1]),
            "min": _json_number(row[2]),
            "max": _json_number(row[3]),
            "mean": _json_number(row[4]),
            "p50": _json_number(row[5]),
            "p5": _json_number(quantiles[0]),
            "p10": _json_number(quantiles[1]),
            "p25": _json_number(quantiles[2]),
            "p75": _json_number(quantiles[4]),
            "p90": _json_number(quantiles[5]),
            "p95": _json_number(quantiles[6]),
            "p99": _json_number(quantiles[7]),
            "stddev": _json_number(row[7]),
        }
    empty = {
        "count": 0,
        "min": None,
        "max": None,
        "mean": None,
        "p50": None,
        "p5": None,
        "p10": None,
        "p25": None,
        "p75": None,
        "p90": None,
        "p95": None,
        "p99": None,
        "stddev": None,
    }
    return [
        found.get(hook_id, {"hook_id": hook_id, **empty})
        for hook_id in TARGET_HOOKS
    ]


@dataclass
class SessionResult:
    session: str
    status: str
    records_seen: int
    candidates: int
    elapsed_sec: float
    record_types: dict[str, int] = field(default_factory=dict)
    uncommitted_tail_bytes: int = 0
    normalizer_processed: int = 0
    normalizer_duplicates: int = 0
    normalizer_reordered: int = 0
    normalizer_rejected: int = 0
    dom_valid_diffs: int = 0
    dom_rejected_diffs: int = 0
    dom_gaps: int = 0
    error: str | None = None
    limited: bool = False


@dataclass
class ActiveAbsorption:
    result: AbsorptionResult

    @property
    def anchor(self) -> Decimal:
        return (self.result.price_low + self.result.price_high) / Decimal(2)


class BookSnapshotProxy:
    """Expose the already-built depth snapshot without copying the full book."""

    def __init__(self) -> None:
        self.latest: Any | None = None

    def snapshot(self) -> Any | None:
        return self.latest


class ReplayAbsorptionDetector:
    """Semantics-equivalent incremental form of legacy AbsorptionDetector.

    The production implementation scans every trade in the 10-second window on
    every tick.  That is appropriate for a live bounded rate but dominates a
    72-hour replay.  This form maintains the same sums and distinct-price set
    incrementally while preserving window-start snapshot behavior and the
    original decision order.
    """

    def __init__(
        self,
        *,
        window_sec: int,
        price_stall_ticks: int,
        volume_multiplier: Decimal,
        volume_ref: VolumeRefTracker,
        book_state: BookSnapshotProxy,
    ) -> None:
        self.window_sec = int(window_sec)
        self.price_stall_ticks = int(price_stall_ticks)
        self.volume_multiplier = Decimal(str(volume_multiplier))
        self.volume_ref = volume_ref
        self.book_state = book_state
        self.window: deque[Any] = deque()
        self.buy_quantity = Decimal(0)
        self.sell_quantity = Decimal(0)
        self.price_counts: Counter[Decimal] = Counter()
        self.window_start_snapshot: Any | None = None
        self.last_result: AbsorptionResult | None = None
        self.events_detected = 0
        self.aggression_condition_fails = 0
        self.stall_condition_fails = 0
        self.replenish_condition_fails = 0
        self.double_direction_events = 0

    def _add(self, trade: Any) -> None:
        quantity = Decimal(str(trade.quantity))
        price = Decimal(str(trade.price))
        if trade.side == "BUY":
            self.buy_quantity += quantity
        else:
            self.sell_quantity += quantity
        self.price_counts[price] += 1

    def _remove(self, trade: Any) -> None:
        quantity = Decimal(str(trade.quantity))
        price = Decimal(str(trade.price))
        if trade.side == "BUY":
            self.buy_quantity -= quantity
        else:
            self.sell_quantity -= quantity
        self.price_counts[price] -= 1
        if self.price_counts[price] <= 0:
            del self.price_counts[price]

    def observe_trade(self, trade: Any) -> None:
        cutoff = trade.event_time - timedelta(seconds=self.window_sec)
        was_empty = not self.window
        old_head = self.window[0].event_time if self.window else None
        while self.window and self.window[0].event_time <= cutoff:
            self._remove(self.window.popleft())
        new_head = self.window[0].event_time if self.window else None
        if was_empty or old_head != new_head:
            snapshot = self.book_state.snapshot()
            if snapshot is not None:
                self.window_start_snapshot = snapshot
        self.window.append(trade)
        self._add(trade)
        current = self.book_state.snapshot()
        if current is None or self.window_start_snapshot is None:
            self.last_result = None
            return
        self.last_result = self._evaluate(current)

    def current(self) -> AbsorptionResult | None:
        return self.last_result

    def _evaluate(self, current: Any) -> AbsorptionResult | None:
        if len(self.price_counts) > self.price_stall_ticks:
            self.stall_condition_fails += 1
            return None
        volume_ref = self.volume_ref.current()
        if volume_ref is None:
            return None
        threshold = volume_ref * self.volume_multiplier
        buy_candidate = self.sell_quantity >= threshold
        sell_candidate = self.buy_quantity >= threshold
        if not buy_candidate and not sell_candidate:
            self.aggression_condition_fails += 1
            return None
        prices = tuple(self.price_counts)
        start = self.window_start_snapshot
        buy_replenished = buy_candidate and all(
            current.bid_quantity_at(price) >= start.bid_quantity_at(price)
            for price in prices
        )
        sell_replenished = sell_candidate and all(
            current.ask_quantity_at(price) >= start.ask_quantity_at(price)
            for price in prices
        )
        if not buy_replenished and not sell_replenished:
            self.replenish_condition_fails += 1
            return None
        if buy_replenished and sell_replenished:
            self.double_direction_events += 1
            sell_replenished = False
        low, high = min(prices), max(prices)
        if buy_replenished:
            strength = min(self.sell_quantity / threshold, Decimal(1))
            classification = "BUY_ABSORPTION"
        else:
            strength = min(self.buy_quantity / threshold, Decimal(1))
            classification = "SELL_ABSORPTION"
        self.events_detected += 1
        return AbsorptionResult(
            classification=classification,
            strength=strength,
            price_low=low,
            price_high=high,
        )


@dataclass(frozen=True)
class ReplayDomQualitySnapshot:
    status: HookQualityStatus
    reason: str | None


class ReplayDomQualityGate:
    """Mirror OrderBookStateManager's production initial-sync semantics."""

    def __init__(self) -> None:
        self.is_valid = False
        self.reason: str | None = "NO_SNAPSHOT"
        self.valid_diffs = 0
        self.rejected_diffs = 0
        self.gaps = 0

    def observe(self, update: Any, apply_result: Any) -> ReplayDomQualitySnapshot:
        if apply_result.gap_detected:
            self.is_valid = False
            self.reason = "SEQUENCE_GAP"
            self.gaps += 1
        elif update.update_type == "SNAPSHOT" and apply_result.applied:
            self.is_valid = False
            self.reason = "WAITING_FIRST_DIFF"
        elif update.update_type == "DIFF" and apply_result.applied:
            # OrderBookStateManager deliberately accepts the first non-stale
            # diff after a REST snapshot, then enforces pu/U continuity.
            self.is_valid = True
            self.reason = None
            self.valid_diffs += 1
        elif update.update_type == "DIFF":
            self.rejected_diffs += 1
        return ReplayDomQualitySnapshot(
            status=(
                HookQualityStatus.VALID
                if self.is_valid
                else HookQualityStatus.INVALID
            ),
            reason=self.reason,
        )


class ReplayFlowPriceResponseDetector(FlowPriceResponseDetector):
    """Existing trade/state logic with a prefix-summed replay snapshot."""

    def _snapshot(self, event_time: datetime) -> tuple[FlowResponseSnapshot, ...]:
        end_second = int(event_time.timestamp())
        if self._last_emitted_second == end_second:
            return ()
        self._last_emitted_second = end_second
        self._prune(end_second)
        buckets = list(self._buckets)
        if not buckets:
            return ()

        seconds = [bucket.second for bucket in buckets]
        buy_prefix = [Decimal(0)]
        sell_prefix = [Decimal(0)]
        trade_prefix = [0]
        positive_prefix = [0]
        negative_prefix = [0]
        for bucket in buckets:
            buy_prefix.append(buy_prefix[-1] + bucket.buy_volume)
            sell_prefix.append(sell_prefix[-1] + bucket.sell_volume)
            trade_prefix.append(trade_prefix[-1] + bucket.trade_count)
            positive_prefix.append(
                positive_prefix[-1] + (1 if bucket.delta > 0 else 0)
            )
            negative_prefix.append(
                negative_prefix[-1] + (1 if bucket.delta < 0 else 0)
            )

        baseline_cutoff = end_second - self.baseline_window_sec + 1
        baseline_start = bisect.bisect_left(seconds, baseline_cutoff)
        baseline_ready = (
            baseline_start < len(buckets)
            and end_second - buckets[baseline_start].second + 1
            >= self.baseline_window_sec
        )
        baseline_total = (
            buy_prefix[-1]
            - buy_prefix[baseline_start]
            + sell_prefix[-1]
            - sell_prefix[baseline_start]
        )
        baseline_rate = (
            baseline_total / Decimal(self.baseline_window_sec)
            if baseline_ready and baseline_total > 0
            else None
        )

        snapshots: list[FlowResponseSnapshot] = []
        for window_sec in self.windows_sec:
            cutoff = end_second - window_sec + 1
            start = bisect.bisect_left(seconds, cutoff)
            if (
                start >= len(buckets)
                or end_second - buckets[start].second + 1 < window_sec
            ):
                continue
            buy_volume = buy_prefix[-1] - buy_prefix[start]
            sell_volume = sell_prefix[-1] - sell_prefix[start]
            total_volume = buy_volume + sell_volume
            delta = buy_volume - sell_volume
            pressure_ratio = (
                delta / total_volume if total_volume > 0 else Decimal(0)
            )
            pressure_side = (
                "BUY" if delta > 0
                else "SELL" if delta < 0
                else "NEUTRAL"
            )
            positive = positive_prefix[-1] - positive_prefix[start]
            negative = negative_prefix[-1] - negative_prefix[start]
            directional = positive + negative
            if not directional or pressure_side == "NEUTRAL":
                persistence = Decimal(0)
            elif pressure_side == "BUY":
                persistence = Decimal(positive) / Decimal(directional)
            else:
                persistence = Decimal(negative) / Decimal(directional)

            selected = buckets[start:]
            first_price = selected[0].open
            last_price = selected[-1].close
            high_price = max(bucket.high for bucket in selected)
            low_price = min(bucket.low for bucket in selected)
            price_change = last_price - first_price
            price_change_bps = (
                price_change / first_price * Decimal(10_000)
                if first_price != 0
                else Decimal(0)
            )
            trade_count = trade_prefix[-1] - trade_prefix[start]
            current_rate = total_volume / Decimal(window_sec)
            relative_volume = (
                current_rate / baseline_rate
                if baseline_rate is not None
                else None
            )
            state = self._classify(
                pressure_side=pressure_side,
                pressure_ratio=pressure_ratio,
                persistence=persistence,
                price_change_bps=price_change_bps,
                trade_count=trade_count,
            )
            snapshots.append(FlowResponseSnapshot(
                event_time=event_time,
                symbol=self._symbol or "",
                window_sec=window_sec,
                state=state,
                pressure_side=pressure_side,
                buy_volume=buy_volume,
                sell_volume=sell_volume,
                total_volume=total_volume,
                delta=delta,
                pressure_ratio=pressure_ratio,
                persistence=persistence,
                first_price=first_price,
                last_price=last_price,
                high_price=high_price,
                low_price=low_price,
                price_change=price_change,
                price_change_bps=price_change_bps,
                relative_volume=relative_volume,
                trade_count=trade_count,
                observed_span_sec=window_sec,
            ))
        return tuple(snapshots)


class BoundedBookIndex:
    """Sorted price index over OrderBookStateManager's authoritative maps."""

    def __init__(self, depth_levels: int) -> None:
        self.depth_levels = depth_levels
        self.bid_prices: list[Decimal] = []
        self.ask_prices: list[Decimal] = []
        self.bid_set: set[Decimal] = set()
        self.ask_set: set[Decimal] = set()

    def reset(self) -> None:
        self.bid_prices = []
        self.ask_prices = []
        self.bid_set.clear()
        self.ask_set.clear()

    @staticmethod
    def _update_side(
        prices: list[Decimal],
        present: set[Decimal],
        levels: Iterable[Any],
        current: dict[Decimal, Decimal],
    ) -> None:
        for level in levels:
            price = level.price
            exists = price in current
            indexed = price in present
            if exists and not indexed:
                bisect.insort(prices, price)
                present.add(price)
            elif not exists and indexed:
                index = bisect.bisect_left(prices, price)
                if index < len(prices) and prices[index] == price:
                    prices.pop(index)
                present.discard(price)

    def observe(
        self,
        update: Any,
        apply_result: Any,
        book: OrderBookStateManager,
    ) -> None:
        if apply_result.gap_detected:
            self.reset()
            return
        if not apply_result.applied:
            return
        if update.update_type == "SNAPSHOT":
            self.bid_prices = sorted(book._bids)  # noqa: SLF001
            self.ask_prices = sorted(book._asks)  # noqa: SLF001
            self.bid_set = set(self.bid_prices)
            self.ask_set = set(self.ask_prices)
            return
        self._update_side(
            self.bid_prices,
            self.bid_set,
            update.bids,
            book._bids,  # noqa: SLF001
        )
        self._update_side(
            self.ask_prices,
            self.ask_set,
            update.asks,
            book._asks,  # noqa: SLF001
        )

    def snapshot(self, book: OrderBookStateManager, symbol: str) -> OrderBookSnapshot | None:
        if not book.is_initialized:
            return None
        bid_keys = self.bid_prices[-self.depth_levels :]
        ask_keys = self.ask_prices[: self.depth_levels]
        bids = {
            price: book._bids[price]  # noqa: SLF001
            for price in bid_keys
        }
        asks = {
            price: book._asks[price]  # noqa: SLF001
            for price in ask_keys
        }
        return OrderBookSnapshot(
            symbol=symbol,
            last_update_id=int(book._last_update_id),  # noqa: SLF001
            bids=bids,
            asks=asks,
            event_time=book.last_event_time,
        )


class SessionCalibration:
    """One-session replay graph. State never leaks across failed/session gaps."""

    def __init__(
        self,
        *,
        config: Any,
        profile: ExchangeProfile,
        store: CandidateStore,
        max_records: int | None,
        progress_every: int,
        session_name: str,
    ) -> None:
        self.config = config
        self.profile = profile
        self.store = store
        self.max_records = max_records
        self.progress_every = progress_every
        self.session_name = session_name
        self.symbol = str(config.market.symbol).upper()
        self.timeframe = str(config.market.bar_timeframe)

        self.normalizer = DataNormalizer(profile)
        self.book = OrderBookStateManager(self.symbol)
        self.book_index = BoundedBookIndex(depth_levels=50)
        self.quality = ReplayDomQualityGate()
        self.dom_cache = DomFeatureCache(depth_levels=50)
        self.dom_wall = DomWallDetector()
        self.dom_liquidity = DomLiquidityDetector()
        self.dom_quote = DomQuoteMotionDetector()
        self.dom_iceberg = DomIcebergDetector(episode_window_ms=5_000)
        self.interaction = InteractionDetector()
        self.flow = ReplayFlowPriceResponseDetector(
            windows_sec=config.flow_response.windows_sec,
            baseline_window_sec=int(config.flow_response.baseline_window_sec),
            pressure_threshold=Decimal(str(config.flow_response.pressure_threshold)),
            persistence_threshold=Decimal(
                str(config.flow_response.persistence_threshold)
            ),
            stall_bps=Decimal(str(config.flow_response.stall_bps)),
            effective_bps=Decimal(str(config.flow_response.effective_bps)),
            opposite_bps=Decimal(str(config.flow_response.opposite_bps)),
            min_trades=int(config.flow_response.min_trades),
        )
        self.flow_transition = FlowTransitionDetector(min_aligned_windows=2)
        self.cvd = CvdCalculator(self.symbol, self.timeframe)
        self.price_structure = PriceStructureDetector(
            lookback_bars=10,
            timeframe_sec=60,
            round_increment=Decimal("50"),
            volume_node_bin_size=Decimal("1"),
        )
        self.footprint = FootprintCalculator(self.symbol, self.timeframe)
        self.volume_ref = VolumeRefTracker(
            bars=int(config.absorption.volume_ref_bars)
        )
        self.absorption_book = BookSnapshotProxy()
        self.absorption = ReplayAbsorptionDetector(
            window_sec=int(config.absorption.window_sec),
            price_stall_ticks=int(config.absorption.price_stall_ticks),
            volume_multiplier=Decimal(str(config.absorption.volume_multiplier)),
            volume_ref=self.volume_ref,
            book_state=self.absorption_book,
        )

        # DOM execution attribution uses raw arrival order plus source times.
        # The production trade normalizer deliberately buffers for 500 ms, so
        # its release order would associate trades with a later DOM interval.
        self.pending_dom_trades: list[Any] = []
        self.active_absorption: ActiveAbsorption | None = None
        self.records_seen = 0
        self.candidates = 0
        self.record_types: Counter[str] = Counter()

    def _collect(self, candidates: Iterable[HookCandidate]) -> None:
        self.candidates += self.store.add(candidates)

    def _absorption_broken(self, trade: Any) -> bool:
        active = self.active_absorption
        if active is None:
            return False
        result = active.result
        if result.classification == "BUY_ABSORPTION":
            return trade.price < result.price_low
        if result.classification == "SELL_ABSORPTION":
            return trade.price > result.price_high
        return False

    def _emit_absorption(
        self,
        result: AbsorptionResult,
        trade: Any,
        *,
        broken: bool,
    ) -> None:
        anchor = (result.price_low + result.price_high) / Decimal(2)
        snapshot = self.absorption_book.snapshot()
        bid = max(snapshot.bids) if snapshot is not None and snapshot.bids else None
        ask = min(snapshot.asks) if snapshot is not None and snapshot.asks else None
        self._collect(self.interaction.observe_absorption(
            classification=result.classification,
            symbol=self.symbol,
            anchor_price=anchor,
            strength=result.strength,
            event_time=trade.event_time,
            received_time=trade.event_time,
            broken=broken,
            bid=bid,
            ask=ask,
        ))

    def _process_trade(self, trade: Any) -> None:
        if self.quality.is_valid and self._absorption_broken(trade):
            assert self.active_absorption is not None
            self._emit_absorption(
                self.active_absorption.result,
                trade,
                broken=True,
            )
            self.active_absorption = None

        closed_footprint = self.footprint.process_trade(trade)
        if closed_footprint is not None:
            self.volume_ref.observe_bar(
                level.buy_volume + level.sell_volume
                for level in closed_footprint.levels
            )

        if self.quality.is_valid:
            self.absorption.observe_trade(trade)
            current = self.absorption.current()
            if current is not None:
                current_key = (
                    current.classification,
                    current.price_low,
                    current.price_high,
                )
                previous_key = None
                if self.active_absorption is not None:
                    previous = self.active_absorption.result
                    previous_key = (
                        previous.classification,
                        previous.price_low,
                        previous.price_high,
                    )
                if current_key != previous_key:
                    self._emit_absorption(current, trade, broken=False)
                self.active_absorption = ActiveAbsorption(current)
            else:
                self.active_absorption = None
        else:
            self.active_absorption = None

        snapshots = self.flow.process(trade)
        if snapshots:
            self._collect(self.flow_transition.process(
                snapshots,
                received_time=trade.event_time,
            ))

        cvd_result = self.cvd.process(trade)
        if cvd_result.closed_candle is not None:
            candle = cvd_result.closed_candle
            self._collect(self.price_structure.process(
                candle,
                received_time=trade.event_time,
            ))

    def _clear_dom_interval(self) -> None:
        self.pending_dom_trades = []

    def _observe_raw_trade_for_dom(self, payload: dict[str, Any]) -> None:
        try:
            trade = normalize_raw(payload, self.profile)
        except NormalizationError:
            return
        if trade.symbol.upper() == self.symbol:
            self.pending_dom_trades.append(trade)

    def _top_depth_snapshot(self) -> OrderBookSnapshot | None:
        """Copy only the 50 levels consumed by DomFeatureCache.

        ``OrderBookStateManager.snapshot`` intentionally copies the entire
        REST book.  Repeating that for every 100 ms diff dominates a 72-hour
        calibration even though Stage 2B reads only 50 levels per side.  The
        manager remains authoritative for update/gap semantics; this bounded
        immutable view only narrows its already-applied state for detectors.
        """
        if not self.book.is_initialized:
            return None
        # Access is deliberately isolated here.  There is no public bounded
        # snapshot API on OrderBookStateManager.
        return self.book_index.snapshot(self.book, self.symbol)

    def _process_depth(self, payload: dict[str, Any], received_time: datetime) -> None:
        update = self.normalizer.process_depth(payload)
        if update is None or update.symbol.upper() != self.symbol:
            return
        apply_result = self.book.apply(update)
        self.book_index.observe(update, apply_result, self.book)
        quality = self.quality.observe(update, apply_result)
        if update.update_type == "SNAPSHOT" and apply_result.applied:
            self.book.apply_initial_sync(update.final_update_id)
        if apply_result.gap_detected:
            self.dom_cache.reset()
            self.absorption_book.latest = None
            self._clear_dom_interval()
            self.active_absorption = None
            return
        if not apply_result.applied:
            return
        snapshot = self._top_depth_snapshot()
        if snapshot is None:
            return
        self.absorption_book.latest = snapshot
        flags = (quality.reason,) if quality.reason else ()
        delta = self.dom_cache.process(
            snapshot,
            source_time=update.event_time,
            # REST snapshot assembly can stamp E a few milliseconds after the
            # journal accepted the wrapper.  Availability must never precede
            # source time at the Hook contract boundary.
            received_time=max(received_time, update.event_time),
            quality_status=quality.status,
            quality_flags=flags,
        )
        if delta is None:
            self._clear_dom_interval()
            return

        previous = delta.previous
        current = delta.current
        interval_trades: list[Any] = []
        future_trades: list[Any] = []
        for trade in self.pending_dom_trades:
            if trade.event_time > current.source_time:
                future_trades.append(trade)
            elif previous is not None and trade.event_time > previous.source_time:
                interval_trades.append(trade)
        self.pending_dom_trades = future_trades
        executed_bid: dict[Decimal, Decimal] = defaultdict(Decimal)
        executed_ask: dict[Decimal, Decimal] = defaultdict(Decimal)
        for trade in interval_trades:
            executed = executed_ask if trade.side == "BUY" else executed_bid
            executed[trade.price] += trade.quantity

        self._collect(self.dom_wall.process(
            delta,
            executed_bid=executed_bid,
            executed_ask=executed_ask,
        ))
        self._collect(self.dom_liquidity.process(delta))
        self._collect(self.dom_quote.process(delta))

        if previous is not None:
            wall_inputs = (
                (
                    HookSide.BID,
                    previous.bid_wall_price,
                    previous.bid_quantity(previous.bid_wall_price),
                    current.bid_quantity(previous.bid_wall_price),
                    executed_bid.get(previous.bid_wall_price, Decimal(0)),
                ),
                (
                    HookSide.ASK,
                    previous.ask_wall_price,
                    previous.ask_quantity(previous.ask_wall_price),
                    current.ask_quantity(previous.ask_wall_price),
                    executed_ask.get(previous.ask_wall_price, Decimal(0)),
                ),
            )
            for side, price, before, after, aggressive in wall_inputs:
                self._collect(self.interaction.observe_wall_trade(
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
                ))
            for trade in interval_trades:
                self._collect(self.dom_iceberg.process_trade(
                    trade,
                    before=previous,
                    after=current,
                    received_time=trade.event_time,
                ))

    def _finalize(self) -> None:
        for trade in self.normalizer.flush():
            self._process_trade(trade)
        snapshots = self.flow.finalize()
        if snapshots:
            self._collect(self.flow_transition.process(
                snapshots,
                received_time=max(snapshot.event_time for snapshot in snapshots),
            ))
        candle = self.cvd.finalize()
        if candle is not None:
            bar_time = candle.bar_time
            if bar_time.tzinfo is None:
                bar_time = bar_time.replace(tzinfo=timezone.utc)
            close_time = bar_time + timedelta(seconds=60)
            self._collect(self.price_structure.process(
                candle,
                received_time=close_time,
            ))

    def run(self, replay: JournalReplay) -> bool:
        limited = False
        for record in replay.records():
            if self.max_records is not None and self.records_seen >= self.max_records:
                limited = True
                break
            self.records_seen += 1
            self.record_types[record.record_type] += 1
            payload = record.payload
            received_time = _parse_time(record.received_time)
            kind = self.normalizer.classify_raw(payload)
            if kind == "depth":
                self._process_depth(payload, received_time)
            elif kind == "trade":
                self._observe_raw_trade_for_dom(payload)
                for trade in self.normalizer.process(payload):
                    self._process_trade(trade)
            # liquidation is intentionally excluded from this calibration.
            if (
                self.progress_every
                and self.records_seen % self.progress_every == 0
            ):
                print(
                    f"[{self.session_name}] records={self.records_seen:,} "
                    f"candidates={self.candidates:,}",
                    file=sys.stderr,
                    flush=True,
                )
        self._finalize()
        return limited


def _load_profile(path: Path) -> ExchangeProfile:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return ExchangeProfile.from_dict(raw)


def _run_session(
    session_dir: Path,
    *,
    config: Any,
    profile: ExchangeProfile,
    store: CandidateStore,
    max_records: int | None,
    progress_every: int,
) -> SessionResult:
    started = time.perf_counter()
    calibration: SessionCalibration | None = None
    replay: JournalReplay | None = None
    store.begin_session()
    try:
        replay = JournalReplay(
            session_dir,
            allow_active=True,
            allow_invalid=True,
        )
        calibration = SessionCalibration(
            config=config,
            profile=profile,
            store=store,
            max_records=max_records,
            progress_every=progress_every,
            session_name=session_dir.name,
        )
        limited = calibration.run(replay)
        store.commit_session()
        return SessionResult(
            session=session_dir.name,
            status="OK_LIMITED" if limited else "OK",
            records_seen=calibration.records_seen,
            candidates=calibration.candidates,
            elapsed_sec=round(time.perf_counter() - started, 3),
            record_types=dict(sorted(calibration.record_types.items())),
            uncommitted_tail_bytes=replay.uncommitted_tail_bytes,
            normalizer_processed=calibration.normalizer.processed,
            normalizer_duplicates=calibration.normalizer.duplicates,
            normalizer_reordered=calibration.normalizer.reordered,
            normalizer_rejected=calibration.normalizer.rejected,
            dom_valid_diffs=calibration.quality.valid_diffs,
            dom_rejected_diffs=calibration.quality.rejected_diffs,
            dom_gaps=calibration.quality.gaps,
            limited=limited,
        )
    except Exception as exc:
        store.rollback_session()
        return SessionResult(
            session=session_dir.name,
            status="ERROR",
            records_seen=calibration.records_seen if calibration else 0,
            candidates=0,
            elapsed_sec=round(time.perf_counter() - started, 3),
            record_types=(
                dict(sorted(calibration.record_types.items()))
                if calibration
                else {}
            ),
            uncommitted_tail_bytes=(
                replay.uncommitted_tail_bytes if replay is not None else 0
            ),
            error=f"{type(exc).__name__}: {exc}",
        )


def _partition_sessions(
    session_dirs: list[Path],
    jobs: int,
) -> list[list[Path]]:
    """Greedy balance by compressed bytes while preserving session isolation."""
    partitions: list[list[Path]] = [[] for _ in range(jobs)]
    sizes = [0 for _ in range(jobs)]
    weighted = []
    for session_dir in session_dirs:
        size = sum(
            path.stat().st_size
            for path in session_dir.glob("raw-*.jsonl.*")
            if path.is_file()
        )
        weighted.append((size, session_dir))
    for size, session_dir in sorted(weighted, key=lambda row: row[0], reverse=True):
        target = min(range(jobs), key=lambda index: sizes[index])
        partitions[target].append(session_dir)
        sizes[target] += size
    for partition in partitions:
        partition.sort()
    return [partition for partition in partitions if partition]


def _run_partition(
    worker_index: int,
    session_paths: list[str],
    *,
    config_path: str,
    profile_path: str,
    database_path: str,
    max_records: int | None,
    progress_every: int,
) -> dict[str, Any]:
    logging.basicConfig(level=logging.ERROR)
    config = load_config(config_path)
    profile = _load_profile(Path(profile_path))
    store = CandidateStore(Path(database_path))
    results: list[SessionResult] = []
    try:
        for index, raw_path in enumerate(session_paths, 1):
            session_dir = Path(raw_path)
            print(
                f"worker {worker_index} session {index}/{len(session_paths)}: "
                f"{session_dir.name}",
                file=sys.stderr,
                flush=True,
            )
            result = _run_session(
                session_dir,
                config=config,
                profile=profile,
                store=store,
                max_records=max_records,
                progress_every=progress_every,
            )
            results.append(result)
            print(
                f"  worker {worker_index} {result.status}: "
                f"records={result.records_seen:,} "
                f"candidates={result.candidates:,} "
                f"elapsed={result.elapsed_sec:.3f}s"
                + (f" error={result.error}" if result.error else ""),
                file=sys.stderr,
                flush=True,
            )
        return {
            "worker_index": worker_index,
            "database_path": database_path,
            "candidate_rows": store.total_rows,
            "sessions": [asdict(item) for item in results],
        }
    finally:
        store.close()


def _render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "## Hook candidate distribution",
        "",
        (
            f"sessions: {result['sessions_succeeded']}/"
            f"{result['sessions_discovered']} succeeded; "
            f"records: {result['records_succeeded']:,}; "
            f"candidate values: {result['candidate_rows']:,}"
        ),
        "",
        "| Hook ID | count | min | max | mean | p50 | p5 | p10 | p25 | p75 | p90 | p95 | p99 | stddev |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in result["statistics"]:
        lines.append(
            "| {hook_id} | {count} | {min} | {max} | {mean} | {p50} | "
            "{p5} | {p10} | {p25} | {p75} | {p90} | {p95} | {p99} | "
            "{stddev} |".format(
                **{
                    key: ("—" if value is None else value)
                    for key, value in row.items()
                }
            )
        )
    lines.extend((
        "",
        "### Samples below 100",
        "",
        ", ".join(result["insufficient_hooks"])
        if result["insufficient_hooks"]
        else "None",
    ))
    return "\n".join(lines)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay Hook full journals and report candidate distributions (dry-run only)."
    )
    parser.add_argument(
        "--campaign-root",
        type=Path,
        default=DEFAULT_CAMPAIGN_ROOT,
        help="full-stream session directory",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="read-only production config used for detector parameters",
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=DEFAULT_PROFILE,
        help="read-only exchange profile",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="optional new JSON output path (must not already exist)",
    )
    parser.add_argument(
        "--max-sessions",
        type=int,
        default=None,
        help="diagnostic limit; default replays every session",
    )
    parser.add_argument(
        "--max-records-per-session",
        type=int,
        default=None,
        help="diagnostic limit; default replays every committed record",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=250_000,
        help="stderr progress interval in records; 0 disables",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="independent session workers (default 1)",
    )
    args = parser.parse_args(argv)
    for name in ("max_sessions", "max_records_per_session"):
        value = getattr(args, name)
        if value is not None and value < 1:
            parser.error(f"--{name.replace('_', '-')} must be >= 1")
    if args.progress_every < 0:
        parser.error("--progress-every must be >= 0")
    if args.jobs < 1:
        parser.error("--jobs must be >= 1")
    return args


def main(argv: list[str] | None = None) -> int:
    # Windows PowerShell commonly exposes cp932 even when report content uses
    # Markdown Unicode.  Keep redirected/stdout output deterministic.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    args = _parse_args(argv or sys.argv[1:])
    logging.basicConfig(level=logging.ERROR)
    campaign_root = args.campaign_root.resolve()
    if not campaign_root.is_dir():
        print(f"campaign root is not a directory: {campaign_root}", file=sys.stderr)
        return 2
    if not args.config.is_file() or not args.profile.is_file():
        print("config/profile file is missing", file=sys.stderr)
        return 2
    if args.output_json is not None and args.output_json.exists():
        print(
            f"refusing to overwrite existing output: {args.output_json}",
            file=sys.stderr,
        )
        return 2

    session_dirs = sorted(path for path in campaign_root.iterdir() if path.is_dir())
    discovered = len(session_dirs)
    if args.max_sessions is not None:
        session_dirs = session_dirs[: args.max_sessions]
    started = time.perf_counter()

    with tempfile.TemporaryDirectory(prefix="calibrate_hooks_") as temp_dir:
        session_results: list[SessionResult] = []
        database_paths: list[Path] = []
        candidate_rows = 0
        jobs = min(args.jobs, max(1, len(session_dirs)))
        if jobs == 1:
            config = load_config(str(args.config))
            profile = _load_profile(args.profile)
            database_path = Path(temp_dir) / "candidate_values.duckdb"
            database_paths.append(database_path)
            store = CandidateStore(database_path)
            try:
                for index, session_dir in enumerate(session_dirs, 1):
                    print(
                        f"session {index}/{len(session_dirs)}: {session_dir.name}",
                        file=sys.stderr,
                        flush=True,
                    )
                    session_result = _run_session(
                        session_dir,
                        config=config,
                        profile=profile,
                        store=store,
                        max_records=args.max_records_per_session,
                        progress_every=args.progress_every,
                    )
                    session_results.append(session_result)
                    print(
                        f"  {session_result.status}: "
                        f"records={session_result.records_seen:,} "
                        f"candidates={session_result.candidates:,} "
                        f"elapsed={session_result.elapsed_sec:.3f}s"
                        + (
                            f" error={session_result.error}"
                            if session_result.error
                            else ""
                        ),
                        file=sys.stderr,
                        flush=True,
                    )
                statistics = store.statistics()
                candidate_rows = store.total_rows
            finally:
                store.close()
        else:
            partitions = _partition_sessions(session_dirs, jobs)
            future_rows: list[
                tuple[
                    concurrent.futures.Future[dict[str, Any]],
                    list[Path],
                    Path,
                ]
            ] = []
            with concurrent.futures.ProcessPoolExecutor(
                max_workers=len(partitions)
            ) as executor:
                for worker_index, partition in enumerate(partitions, 1):
                    database_path = (
                        Path(temp_dir) / f"candidate_values_{worker_index}.duckdb"
                    )
                    future = executor.submit(
                        _run_partition,
                        worker_index,
                        [str(path) for path in partition],
                        config_path=str(args.config.resolve()),
                        profile_path=str(args.profile.resolve()),
                        database_path=str(database_path),
                        max_records=args.max_records_per_session,
                        progress_every=args.progress_every,
                    )
                    future_rows.append((future, partition, database_path))

                for future, partition, database_path in future_rows:
                    try:
                        worker_result = future.result()
                    except Exception as exc:
                        error = f"{type(exc).__name__}: {exc}"
                        session_results.extend(
                            SessionResult(
                                session=session_dir.name,
                                status="ERROR",
                                records_seen=0,
                                candidates=0,
                                elapsed_sec=0,
                                error=f"worker failure: {error}",
                            )
                            for session_dir in partition
                        )
                        continue
                    database_paths.append(database_path)
                    candidate_rows += int(worker_result["candidate_rows"])
                    session_results.extend(
                        SessionResult(**row)
                        for row in worker_result["sessions"]
                    )

            aggregate = duckdb.connect(":memory:")
            try:
                sources = []
                for index, database_path in enumerate(database_paths, 1):
                    escaped = str(database_path).replace("'", "''")
                    alias = f"worker_{index}"
                    aggregate.execute(
                        f"ATTACH '{escaped}' AS {alias} (READ_ONLY)"
                    )
                    sources.append(
                        f"SELECT hook_id, value FROM {alias}.samples"
                    )
                statistics = (
                    _statistics_from_source(
                        aggregate,
                        " UNION ALL ".join(sources),
                    )
                    if sources
                    else [
                        {
                            "hook_id": hook_id,
                            "count": 0,
                            "min": None,
                            "max": None,
                            "mean": None,
                            "p50": None,
                            "p5": None,
                            "p10": None,
                            "p25": None,
                            "p75": None,
                            "p90": None,
                            "p95": None,
                            "p99": None,
                            "stddev": None,
                        }
                        for hook_id in TARGET_HOOKS
                    ]
                )
            finally:
                aggregate.close()

        order = {path.name: index for index, path in enumerate(session_dirs)}
        session_results.sort(key=lambda item: order.get(item.session, len(order)))
        successful = [
            item for item in session_results
            if item.status in {"OK", "OK_LIMITED"}
        ]
        failed = [item for item in session_results if item.status == "ERROR"]
        limited = any(item.limited for item in session_results)
        result = {
            "schema_version": 1,
            "dry_run": True,
            "generated_at_utc": _utc_now_text(),
            "campaign_root": str(campaign_root),
            "input_manifest_sha256": _campaign_manifest_hash(session_dirs),
            "target_hooks": list(TARGET_HOOKS),
            "excluded_hooks": [
                "C09",
                "E01",
                "E02",
                "E03",
                "E04",
                "E05",
                "E06",
            ],
            "unavailable_input_hooks": {
                hook_id: "OPEN_INTEREST records are absent from the full journal"
                for hook_id in F_HOOKS
            },
            "parameters": {
                "dom_depth_levels": 50,
                "iceberg_episode_window_ms": 5000,
                "flow_transition_min_aligned_windows": 2,
                "price_structure_lookback_bars": 10,
                "price_structure_timeframe_sec": 60,
                "price_structure_round_increment": "50",
                "price_structure_volume_node_bin_size": "1",
                "quantile_method": "DuckDB quantile_cont (linear interpolation)",
                "standard_deviation": "population",
                "session_state_policy": "reset all detector state at each session boundary",
                "failed_session_policy": "transactional rollback; no partial candidates retained",
                "jobs": jobs,
            },
            "sessions_discovered": discovered,
            "sessions_selected": len(session_dirs),
            "sessions_succeeded": len(successful),
            "sessions_failed": len(failed),
            "limited_run": limited,
            "records_succeeded": sum(item.records_seen for item in successful),
            "candidate_rows": candidate_rows,
            "record_types_succeeded": dict(sorted(sum(
                (Counter(item.record_types) for item in successful),
                Counter(),
            ).items())),
            "elapsed_sec": round(time.perf_counter() - started, 3),
            "statistics": statistics,
            "insufficient_hooks": [
                row["hook_id"] for row in statistics if row["count"] < 100
            ],
            "sessions": [asdict(item) for item in session_results],
        }
        rendered = _render_markdown(result)
        print(rendered)
        if args.output_json is not None:
            args.output_json.parent.mkdir(parents=True, exist_ok=True)
            with args.output_json.open("x", encoding="utf-8", newline="\n") as handle:
                json.dump(result, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            print(f"wrote {args.output_json}", file=sys.stderr)
        return 0 if successful else 1


if __name__ == "__main__":
    raise SystemExit(main())
