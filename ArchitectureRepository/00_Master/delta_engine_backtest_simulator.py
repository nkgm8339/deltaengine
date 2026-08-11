# -*- coding: utf-8 -*-
"""Real-event replay validation for Directional Pressure Detection concept v4.

This is a validation-only program.  It reads the persisted DeltaEngine capture
and research Parquet stores, creates causal pressure episodes, and prints a
report.  It does not generate market events, mutate the production database,
change configuration, place orders, or modify the completed Flow Price
Response / three-tier chart implementation.

Concept mapping
---------------
* T_start   : first same-direction trade in the rolling cluster that triggers.
* T_trigger : source time of the trade where the frozen condition first holds.
* T_detect  : Receiver/journal received_time of that trigger trade.  This is an
              earliest in-engine availability proxy, not socket-arrival time.
* T_end     : inactivity timeout or opposite trigger, whichever closes first.
* Detection : trigger-window raw trade features only.
* Response  : raw 100/250/500/1000 ms mid-price responses after T_trigger.
* Outcome   : 1/3/5 minute return, MFE, MAE and time-to-extreme.

The concept intentionally leaves several parameters undecided.  This harness
does not present research assumptions as approved specification.  Operational
parameters are read from the existing repository YAML.  Distribution-outlier
thresholds are fitted on the chronological training block only and frozen
before the embargoed evaluation block.
"""

from __future__ import annotations

import argparse
import bisect
import heapq
import hashlib
import json
import lzma
import math
import statistics
import sys
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

try:
    import pyarrow.parquet as parquet
except ImportError as exc:  # pragma: no cover - environment failure path
    raise SystemExit("pyarrow is required to read the real OI Parquet store") from exc

try:
    import yaml
except ImportError as exc:  # pragma: no cover - environment failure path
    raise SystemExit("PyYAML is required to read the actual DeltaEngine config") from exc


SCRIPT_PATH = Path(__file__).resolve()
REPOSITORY_ROOT = SCRIPT_PATH.parents[2]
APP_ROOT = REPOSITORY_ROOT / "Delta_Engine_Pro4web"
CAPTURE_ROOT = APP_ROOT / "data_05M" / "hook_observer" / "campaigns"
OI_ROOT = APP_ROOT / "data_05M" / "parquet" / "open_interest_samples"
RUNTIME_CONFIG = APP_ROOT / "config" / "config.yaml"
VALIDATION_CONFIG = APP_ROOT / "config" / "flow_strategy_evaluation.yaml"
CONCEPT_PATH = (
    REPOSITORY_ROOT
    / "ArchitectureRepository"
    / "00_Master"
    / "DIRECTIONAL_PRESSURE_DETECTION_CONCEPT_V4_20260809.md"
)

SUPPORTED_TRADE_EVENTS = {"trade", "aggTrade"}
OUTCOME_HORIZONS_SEC = (60, 180, 300)
RESPONSE_HORIZONS_MS = (100, 250, 500, 1000)


class ValidationError(RuntimeError):
    """The real persisted inputs cannot support the requested validation."""


@dataclass(frozen=True, slots=True)
class Parameters:
    cluster_window_ms: int
    inactivity_timeout_ms: int
    minimum_price_levels: int
    pressure_ratio_threshold: float
    book_stale_after_ms: int
    book_depth_levels: int
    oi_poll_interval_sec: int
    train_fraction: float
    split_embargo_sec: int
    minimum_interim_episodes: int
    minimum_deployment_episodes: int
    outlier_quantile: float
    sample_step_ms: int


@dataclass(frozen=True, slots=True)
class Trade:
    source_ms: int
    received_ms: int
    price: float
    quantity: float
    direction: int
    trade_id: int
    session_index: int


@dataclass(frozen=True, slots=True)
class Quote:
    source_ms: int
    received_ms: int
    bid: float
    ask: float
    bid_top_quantity: float
    ask_top_quantity: float

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread_bps(self) -> float:
        return (self.ask - self.bid) / self.mid * 10_000.0


@dataclass(frozen=True, slots=True)
class Liquidation:
    source_ms: int
    received_ms: int
    direction: int
    quantity: float


@dataclass(frozen=True, slots=True)
class OISample:
    source_ms: int
    received_ms: int
    value: float


@dataclass(slots=True)
class SessionData:
    index: int
    session_id: str
    path: Path
    files: tuple[Path, ...]
    summary: dict[str, Any]
    meta: dict[str, Any]
    trades: list[Trade] = field(default_factory=list)
    quotes: list[Quote] = field(default_factory=list)
    quote_source_times: list[int] = field(default_factory=list)
    liquidations: list[Liquidation] = field(default_factory=list)
    counts: dict[str, Any] = field(default_factory=dict)

    @property
    def source_start_ms(self) -> int:
        return self.trades[0].source_ms

    @property
    def source_end_ms(self) -> int:
        return self.trades[-1].source_ms


@dataclass(frozen=True, slots=True)
class TriggerCandidate:
    session_index: int
    trigger_kind: str
    direction: int
    t_start_ms: int
    t_trigger_ms: int
    t_detect_ms: int
    last_trade_ms: int
    trade_volume: float
    trade_notional: float
    trade_count: int
    trades_per_second: float
    buy_volume: float
    sell_volume: float
    directional_volume: float
    delta: float
    delta_ratio: float
    price_level_count: int
    price_band_low: float
    price_band_high: float
    interval_cv: float | None
    volume_percentile: float
    notional_percentile: float
    delta_percentile: float
    robust_volume_z: float | None


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValidationError(f"expected JSON object: {path}")
    return value


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise ValidationError(f"expected YAML mapping: {path}")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iso_to_ms(value: str) -> int:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(round(parsed.timestamp() * 1000.0))


def _ms_to_iso(value: int | None) -> str | None:
    if value is None:
        return None
    return (
        datetime.fromtimestamp(value / 1000.0, tz=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _finite_positive(value: Any) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0.0:
        raise ValueError("value must be finite and positive")
    return parsed


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise ValidationError("cannot calculate a quantile from no real observations")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _percentile_rank(ordered: Sequence[float], value: float) -> float:
    if not ordered:
        return 0.0
    return bisect.bisect_right(ordered, value) / len(ordered) * 100.0


def _round(value: float | None, digits: int = 6) -> float | None:
    return None if value is None else round(value, digits)


def _load_parameters(outlier_quantile: float, sample_step_ms: int) -> Parameters:
    runtime = _read_yaml(RUNTIME_CONFIG)
    validation = _read_yaml(VALIDATION_CONFIG)
    flow_detector = runtime["flow_detector"]
    flow_response = runtime["flow_response"]
    webapp = runtime["webapp"]
    rules = validation["validation"]
    return Parameters(
        cluster_window_ms=int(flow_detector["sweep_window_ms"]),
        inactivity_timeout_ms=int(flow_detector["tape_pause_threshold_ms"]),
        minimum_price_levels=int(flow_detector["sweep_min_levels"]),
        pressure_ratio_threshold=float(flow_response["pressure_threshold"]),
        book_stale_after_ms=int(webapp["book_stale_after_ms"]),
        book_depth_levels=int(webapp["depth_levels"]),
        oi_poll_interval_sec=int(webapp["oi_poll_interval_sec"]),
        train_fraction=float(validation["train_fraction"]),
        split_embargo_sec=int(validation["split_embargo_sec"]),
        minimum_interim_episodes=int(rules["minimum_interim_test_trades"]),
        minimum_deployment_episodes=int(rules["minimum_deployment_trades"]),
        outlier_quantile=outlier_quantile,
        sample_step_ms=sample_step_ms,
    )


def _discover_valid_sessions(explicit: Sequence[str]) -> tuple[list[Path], list[str]]:
    excluded: list[str] = []
    if explicit:
        paths = [Path(value).expanduser().resolve() for value in explicit]
    else:
        paths = sorted(
            path.parent
            for path in CAPTURE_ROOT.glob("*/full/session-*/session_summary.json")
        )
    selected: list[tuple[str, Path]] = []
    for path in paths:
        summary_path = path / "session_summary.json"
        meta_path = path / "session_meta.json"
        files = tuple(sorted(path.glob("raw-*.jsonl.xz")))
        if not summary_path.is_file() or not meta_path.is_file() or not files:
            excluded.append(f"{path}: missing summary/meta/XZ")
            continue
        try:
            summary = _read_json(summary_path)
            meta = _read_json(meta_path)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            excluded.append(f"{path}: {exc}")
            continue
        if summary.get("valid") is not True or summary.get("mode") != "full":
            excluded.append(f"{path}: session_summary.valid is not true full-mode")
            continue
        selected.append((str(meta.get("started_at", "")), path.resolve()))
    result = [path for _, path in sorted(selected)]
    if not result:
        raise ValidationError("no valid full-mode real XZ capture sessions were found")
    return result, excluded


class _BookReplay:
    """Validation copy of the existing OrderBookStateManager sequence semantics."""

    def __init__(self, depth_levels: int) -> None:
        self.depth_levels = depth_levels
        self.bids: dict[float, float] = {}
        self.asks: dict[float, float] = {}
        self.bid_heap: list[float] = []
        self.ask_heap: list[float] = []
        self.top_refresh_ms = 500
        self.last_top_refresh_ms: int | None = None
        self.cached_bid_top_quantity = 0.0
        self.cached_ask_top_quantity = 0.0
        self.last_update_id: int | None = None
        self.initialized = False
        self.sync_pending = False
        self.snapshots = 0
        self.applied_diffs = 0
        self.before_snapshot = 0
        self.stale_diffs = 0
        self.gaps = 0
        self.crossed_quotes = 0

    @staticmethod
    def _replace_side(
        side: dict[float, float],
        heap: list[float],
        updates: Iterable[Sequence[Any]],
        *,
        bid_side: bool,
    ) -> None:
        for raw_price, raw_quantity, *_ in updates:
            price = float(raw_price)
            quantity = float(raw_quantity)
            if not math.isfinite(price) or price <= 0.0 or not math.isfinite(quantity):
                continue
            exists = price in side
            if quantity <= 0.0:
                if exists:
                    side.pop(price, None)
            else:
                side[price] = quantity
                if not exists:
                    heapq.heappush(heap, -price if bid_side else price)

    def snapshot(self, payload: dict[str, Any]) -> None:
        bid_rows = payload.get("b", payload.get("bids", ()))
        ask_rows = payload.get("a", payload.get("asks", ()))
        update_id = payload.get("u", payload.get("lastUpdateId"))
        if update_id is None:
            return
        self.bids.clear()
        self.asks.clear()
        self.bid_heap.clear()
        self.ask_heap.clear()
        self._replace_side(self.bids, self.bid_heap, bid_rows, bid_side=True)
        self._replace_side(self.asks, self.ask_heap, ask_rows, bid_side=False)
        self.last_top_refresh_ms = None
        self.last_update_id = int(update_id)
        self.initialized = True
        self.sync_pending = True
        self.snapshots += 1

    def diff(self, payload: dict[str, Any]) -> bool:
        if not self.initialized or self.last_update_id is None:
            self.before_snapshot += 1
            return False
        final_id = int(payload["u"])
        if final_id <= self.last_update_id:
            self.stale_diffs += 1
            return False
        if self.sync_pending:
            self.sync_pending = False
        else:
            previous = payload.get("pu")
            first = payload.get("U")
            gap = (
                int(previous) != self.last_update_id
                if previous is not None
                else first is not None and int(first) != self.last_update_id + 1
            )
            if gap:
                self.bids.clear()
                self.asks.clear()
                self.bid_heap.clear()
                self.ask_heap.clear()
                self.last_update_id = None
                self.initialized = False
                self.sync_pending = False
                self.gaps += 1
                return False
        self._replace_side(
            self.bids, self.bid_heap, payload.get("b", ()), bid_side=True
        )
        self._replace_side(
            self.asks, self.ask_heap, payload.get("a", ()), bid_side=False
        )
        self.last_update_id = final_id
        self.applied_diffs += 1
        return True

    def quote(self, source_ms: int, received_ms: int) -> Quote | None:
        while self.bid_heap and -self.bid_heap[0] not in self.bids:
            heapq.heappop(self.bid_heap)
        while self.ask_heap and self.ask_heap[0] not in self.asks:
            heapq.heappop(self.ask_heap)
        if self.sync_pending or not self.bid_heap or not self.ask_heap:
            return None
        bid = -self.bid_heap[0]
        ask = self.ask_heap[0]
        if bid >= ask:
            self.crossed_quotes += 1
            return None
        if (
            self.last_top_refresh_ms is None
            or source_ms - self.last_top_refresh_ms >= self.top_refresh_ms
        ):
            top_bids = heapq.nlargest(self.depth_levels, self.bids)
            top_asks = heapq.nsmallest(self.depth_levels, self.asks)
            self.cached_bid_top_quantity = sum(self.bids[value] for value in top_bids)
            self.cached_ask_top_quantity = sum(self.asks[value] for value in top_asks)
            self.last_top_refresh_ms = source_ms
        return Quote(
            source_ms=source_ms,
            received_ms=received_ms,
            bid=bid,
            ask=ask,
            bid_top_quantity=self.cached_bid_top_quantity,
            ask_top_quantity=self.cached_ask_top_quantity,
        )


def _trade_source_time(payload: dict[str, Any]) -> int:
    return int(payload["T"])


def _depth_source_time(payload: dict[str, Any]) -> int:
    value = payload.get("T", payload.get("E"))
    if value is None:
        raise ValueError("depth event has no source time")
    return int(value)


def _load_session(
    index: int, path: Path, parameters: Parameters, *, replay_depth: bool
) -> SessionData:
    summary = _read_json(path / "session_summary.json")
    meta = _read_json(path / "session_meta.json")
    files = tuple(sorted(path.glob("raw-*.jsonl.xz")))
    session = SessionData(
        index=index,
        session_id=str(summary.get("session_id", path.name)),
        path=path,
        files=files,
        summary=summary,
        meta=meta,
    )
    book = _BookReplay(parameters.book_depth_levels)
    event_counts: Counter[str] = Counter()
    invalid_trade_reasons: Counter[str] = Counter()
    seen_trade_ids: set[int] = set()
    record_count = 0
    json_errors = 0
    sequence_gaps = 0
    sequence_reversals = 0
    last_sequence: int | None = None
    last_trade_source: int | None = None
    trade_source_reversals = 0
    latency_values: list[float] = []
    file_manifest: list[dict[str, Any]] = []

    for file_path in files:
        file_manifest.append(
            {
                "path": str(file_path.resolve()),
                "compressed_bytes": file_path.stat().st_size,
                "sha256": _sha256_file(file_path),
            }
        )
        try:
            with lzma.open(file_path, "rt", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    record_count += 1
                    try:
                        envelope = json.loads(line)
                    except json.JSONDecodeError:
                        json_errors += 1
                        continue
                    if not isinstance(envelope, dict):
                        json_errors += 1
                        continue
                    sequence = envelope.get("sequence")
                    if isinstance(sequence, int):
                        if last_sequence is not None:
                            if sequence > last_sequence + 1:
                                sequence_gaps += sequence - last_sequence - 1
                            elif sequence <= last_sequence:
                                sequence_reversals += 1
                        last_sequence = sequence
                    payload = envelope.get("payload")
                    if not isinstance(payload, dict):
                        event_counts["MISSING_PAYLOAD"] += 1
                        continue
                    event_type = str(payload.get("e", "UNKNOWN"))
                    event_counts[event_type] += 1
                    try:
                        received_ms = _iso_to_ms(str(envelope["received_time"]))
                    except (KeyError, ValueError, OverflowError):
                        event_counts["INVALID_RECEIVED_TIME"] += 1
                        continue

                    if event_type in SUPPORTED_TRADE_EVENTS:
                        if str(payload.get("s", "")).upper() != "BTCUSDT":
                            event_counts["OTHER_SYMBOL_TRADE"] += 1
                            continue
                        try:
                            source_ms = _trade_source_time(payload)
                            price = _finite_positive(payload["p"])
                            quantity = _finite_positive(payload["q"])
                            maker = payload["m"]
                            if not isinstance(maker, bool):
                                raise ValueError("maker flag is not boolean")
                            id_field = "t" if event_type == "trade" else "a"
                            trade_id = int(payload[id_field])
                        except (KeyError, TypeError, ValueError, OverflowError):
                            invalid_trade_reasons["MALFORMED_OR_NONPOSITIVE"] += 1
                            continue
                        if trade_id in seen_trade_ids:
                            invalid_trade_reasons["DUPLICATE_ID"] += 1
                            continue
                        seen_trade_ids.add(trade_id)
                        if last_trade_source is not None and source_ms < last_trade_source:
                            trade_source_reversals += 1
                        last_trade_source = source_ms
                        direction = -1 if maker else 1
                        session.trades.append(
                            Trade(
                                source_ms=source_ms,
                                received_ms=received_ms,
                                price=price,
                                quantity=quantity,
                                direction=direction,
                                trade_id=trade_id,
                                session_index=index,
                            )
                        )
                        latency_values.append(float(received_ms - source_ms))
                        continue

                    if event_type == "depthSnapshot":
                        if not replay_depth:
                            continue
                        try:
                            source_ms = _depth_source_time(payload)
                            book.snapshot(payload)
                        except (KeyError, TypeError, ValueError, OverflowError):
                            event_counts["INVALID_DEPTH_SNAPSHOT"] += 1
                        continue

                    if event_type == "depthUpdate":
                        if not replay_depth:
                            continue
                        try:
                            source_ms = _depth_source_time(payload)
                            applied = book.diff(payload)
                            if applied:
                                quote = book.quote(source_ms, received_ms)
                                if quote is not None:
                                    session.quotes.append(quote)
                        except (KeyError, TypeError, ValueError, OverflowError):
                            event_counts["INVALID_DEPTH_UPDATE"] += 1
                        continue

                    if event_type == "forceOrder":
                        try:
                            order = payload["o"]
                            side = str(order["S"]).upper()
                            direction = 1 if side == "BUY" else -1 if side == "SELL" else 0
                            if direction == 0:
                                raise ValueError("unknown liquidation side")
                            source_ms = int(order.get("T", payload["E"]))
                            quantity = _finite_positive(order.get("q", order.get("z")))
                            session.liquidations.append(
                                Liquidation(source_ms, received_ms, direction, quantity)
                            )
                        except (KeyError, TypeError, ValueError, OverflowError):
                            event_counts["INVALID_LIQUIDATION"] += 1

        except (OSError, EOFError, lzma.LZMAError) as exc:
            raise ValidationError(f"cannot read real capture {file_path}: {exc}") from exc

    if not session.trades:
        raise ValidationError(f"session has no valid BTCUSDT trades: {path}")
    session.trades.sort(key=lambda value: (value.source_ms, value.trade_id))
    session.quotes.sort(key=lambda value: (value.source_ms, value.received_ms))
    session.quote_source_times = [value.source_ms for value in session.quotes]
    session.liquidations.sort(key=lambda value: value.source_ms)
    expected = summary.get("accepted")
    summary_consistent = bool(
        isinstance(expected, int)
        and expected == record_count
        and summary.get("persisted") == expected
        and summary.get("durably_committed", expected) == expected
        and summary.get("dropped_queue_full") == 0
        and summary.get("rejected_deadline") == 0
        and summary.get("rejected_disk_low") == 0
        and summary.get("writer_error") is None
    )
    latency_summary: dict[str, Any]
    if latency_values:
        latency_summary = {
            "count": len(latency_values),
            "p50_ms": _round(_quantile(latency_values, 0.50), 3),
            "p95_ms": _round(_quantile(latency_values, 0.95), 3),
            "p99_ms": _round(_quantile(latency_values, 0.99), 3),
            "max_ms": _round(max(latency_values), 3),
            "negative_count": sum(value < 0.0 for value in latency_values),
        }
    else:
        latency_summary = {"count": 0}
    session.counts = {
        "records": record_count,
        "summary_consistent": summary_consistent,
        "json_errors": json_errors,
        "sequence_gaps": sequence_gaps,
        "sequence_reversals": sequence_reversals,
        "event_counts": dict(sorted(event_counts.items())),
        "valid_trades": len(session.trades),
        "invalid_trade_reasons": dict(sorted(invalid_trade_reasons.items())),
        "trade_source_reversals": trade_source_reversals,
        "quotes": len(session.quotes),
        "depth_replayed_for_evaluation": replay_depth,
        "liquidations": len(session.liquidations),
        "book": {
            "snapshots": book.snapshots,
            "applied_diffs": book.applied_diffs,
            "before_snapshot": book.before_snapshot,
            "stale_diffs": book.stale_diffs,
            "gaps": book.gaps,
            "crossed_quotes": book.crossed_quotes,
        },
        "trade_source_to_receiver_latency": latency_summary,
        "files": file_manifest,
    }
    return session


def _approximate_split_session_index(
    session_paths: Sequence[Path], train_fraction: float
) -> int:
    """Locate the split session from metadata only, solely to skip training books.

    The exact source-time split is still calculated later from parsed trades.  The
    approximate split session itself is always depth-replayed, so metadata drift
    cannot remove a quote needed by evaluation.
    """
    spans: list[int] = []
    for path in session_paths:
        meta = _read_json(path / "session_meta.json")
        summary = _read_json(path / "session_summary.json")
        spans.append(
            max(0, _iso_to_ms(str(summary["closed_at"])) - _iso_to_ms(str(meta["started_at"])))
        )
    target = sum(spans) * train_fraction
    consumed = 0.0
    for index, span in enumerate(spans):
        if consumed + span >= target:
            return index
        consumed += span
    return len(session_paths) - 1


def _load_oi_samples(
    sessions: Sequence[SessionData],
) -> tuple[list[OISample], list[dict[str, Any]]]:
    days: set[tuple[int, int, int]] = set()
    for session in sessions:
        start = datetime.fromtimestamp(session.source_start_ms / 1000.0, tz=timezone.utc)
        end = datetime.fromtimestamp(session.source_end_ms / 1000.0, tz=timezone.utc)
        cursor = start.date()
        while cursor <= end.date():
            days.add((cursor.year, cursor.month, cursor.day))
            cursor += timedelta(days=1)
    files: list[Path] = []
    for year, month, day in sorted(days):
        directory = (
            OI_ROOT
            / "symbol=BTCUSDT"
            / f"year={year:04d}"
            / f"month={month:02d}"
            / f"day={day:02d}"
        )
        files.extend(sorted(directory.glob("*.parquet")))
    samples: list[OISample] = []
    used_files: list[dict[str, Any]] = []
    for path in files:
        table = parquet.ParquetFile(path).read(
            columns=["source_time", "received_time", "symbol", "open_interest"]
        )
        used_files.append(
            {
                "path": str(path.resolve()),
                "bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
        for row in table.to_pylist():
            if str(row["symbol"]).upper() != "BTCUSDT":
                continue
            source = row["source_time"]
            received = row["received_time"]
            if source.tzinfo is None:
                source = source.replace(tzinfo=timezone.utc)
            if received.tzinfo is None:
                received = received.replace(tzinfo=timezone.utc)
            value = float(row["open_interest"])
            in_capture_range = any(
                session.source_start_ms - 30_000
                <= int(round(source.timestamp() * 1000.0))
                <= session.source_end_ms + 30_000
                for session in sessions
            )
            if in_capture_range and math.isfinite(value) and value > 0.0:
                samples.append(
                    OISample(
                        source_ms=int(round(source.timestamp() * 1000.0)),
                        received_ms=int(round(received.timestamp() * 1000.0)),
                        value=value,
                    )
                )
    samples.sort(key=lambda value: value.source_ms)
    unique: list[OISample] = []
    for sample in samples:
        if unique and sample.source_ms == unique[-1].source_ms:
            if sample.received_ms < unique[-1].received_ms:
                unique[-1] = sample
            continue
        unique.append(sample)
    return unique, used_files


def _active_time_split(
    sessions: Sequence[SessionData], train_fraction: float
) -> tuple[int, int, float]:
    durations = [max(0, value.source_end_ms - value.source_start_ms) for value in sessions]
    total = sum(durations)
    if total <= 0:
        raise ValidationError("captured sessions have no active source-time duration")
    target = total * train_fraction
    consumed = 0.0
    for session, duration in zip(sessions, durations):
        if consumed + duration >= target:
            split = session.source_start_ms + int(target - consumed)
            return split, session.index, total / 1000.0
        consumed += duration
    return sessions[-1].source_end_ms, sessions[-1].index, total / 1000.0


def _training_feature_distributions(
    sessions: Sequence[SessionData],
    split_ms: int,
    parameters: Parameters,
) -> dict[str, list[float]]:
    result = {
        "volume": [],
        "same_side_volume": [],
        "abs_delta": [],
        "notional": [],
    }
    window_ms = parameters.cluster_window_ms
    step_ms = parameters.sample_step_ms
    for session in sessions:
        if session.source_start_ms >= split_ms:
            continue
        trades = session.trades
        start = ((trades[0].source_ms + step_ms - 1) // step_ms) * step_ms
        end = min(trades[-1].source_ms, split_ms - 1)
        left = 0
        right = 0
        buy = sell = notional = 0.0
        for boundary in range(start, end + 1, step_ms):
            while right < len(trades) and trades[right].source_ms <= boundary:
                trade = trades[right]
                if trade.direction > 0:
                    buy += trade.quantity
                else:
                    sell += trade.quantity
                notional += trade.price * trade.quantity
                right += 1
            cutoff = boundary - window_ms
            while left < right and trades[left].source_ms < cutoff:
                trade = trades[left]
                if trade.direction > 0:
                    buy -= trade.quantity
                else:
                    sell -= trade.quantity
                notional -= trade.price * trade.quantity
                left += 1
            volume = max(0.0, buy + sell)
            if volume <= 0.0:
                continue
            result["volume"].append(volume)
            result["same_side_volume"].append(max(buy, sell))
            result["abs_delta"].append(abs(buy - sell))
            result["notional"].append(max(0.0, notional))
    if min(len(values) for values in result.values()) < 100:
        raise ValidationError("training block has too few fixed-grid real observations")
    for values in result.values():
        values.sort()
    return result


def _coefficient_of_variation(times: Sequence[int]) -> float | None:
    if len(times) < 3:
        return None
    intervals = [float(right - left) for left, right in zip(times, times[1:])]
    mean = statistics.fmean(intervals)
    if mean <= 0.0:
        return None
    return statistics.pstdev(intervals) / mean


def _candidate(
    session_index: int,
    kind: str,
    buffer: Sequence[Trade],
    trigger_trade: Trade,
    buy_volume: float,
    sell_volume: float,
    notional: float,
    distributions: dict[str, list[float]],
    median_volume: float,
    mad_volume: float,
    window_ms: int,
) -> TriggerCandidate:
    delta = buy_volume - sell_volume
    direction = 1 if delta > 0.0 else -1
    same_side = [trade for trade in buffer if trade.direction == direction]
    same_times = [trade.source_ms for trade in same_side]
    same_prices = [trade.price for trade in same_side]
    volume = buy_volume + sell_volume
    robust_z = (
        (volume - median_volume) / (1.4826 * mad_volume)
        if mad_volume > 0.0
        else None
    )
    return TriggerCandidate(
        session_index=session_index,
        trigger_kind=kind,
        direction=direction,
        t_start_ms=same_side[0].source_ms,
        t_trigger_ms=trigger_trade.source_ms,
        t_detect_ms=trigger_trade.received_ms,
        last_trade_ms=same_side[-1].source_ms,
        trade_volume=volume,
        trade_notional=notional,
        trade_count=len(buffer),
        trades_per_second=len(buffer) / (window_ms / 1000.0),
        buy_volume=buy_volume,
        sell_volume=sell_volume,
        directional_volume=sum(trade.quantity for trade in same_side),
        delta=delta,
        delta_ratio=delta / volume,
        price_level_count=len(set(same_prices)),
        price_band_low=min(same_prices),
        price_band_high=max(same_prices),
        interval_cv=_coefficient_of_variation(same_times),
        volume_percentile=_percentile_rank(distributions["volume"], volume),
        notional_percentile=_percentile_rank(distributions["notional"], notional),
        delta_percentile=_percentile_rank(distributions["abs_delta"], abs(delta)),
        robust_volume_z=robust_z,
    )


def _detect_candidates(
    session: SessionData,
    thresholds: dict[str, float],
    distributions: dict[str, list[float]],
    parameters: Parameters,
) -> tuple[list[TriggerCandidate], list[TriggerCandidate]]:
    buffer: deque[Trade] = deque()
    buy = sell = notional = 0.0
    delta_candidates: list[TriggerCandidate] = []
    cluster_candidates: list[TriggerCandidate] = []
    previous_delta_pass = False
    previous_delta_direction = 0
    previous_cluster_pass = False
    previous_cluster_direction = 0
    median_volume = statistics.median(distributions["volume"])
    deviations = sorted(abs(value - median_volume) for value in distributions["volume"])
    mad_volume = statistics.median(deviations)

    for trade in session.trades:
        buffer.append(trade)
        if trade.direction > 0:
            buy += trade.quantity
        else:
            sell += trade.quantity
        notional += trade.price * trade.quantity
        cutoff = trade.source_ms - parameters.cluster_window_ms
        while buffer and buffer[0].source_ms < cutoff:
            old = buffer.popleft()
            if old.direction > 0:
                buy -= old.quantity
            else:
                sell -= old.quantity
            notional -= old.price * old.quantity

        volume = buy + sell
        delta = buy - sell
        if volume <= 0.0 or delta == 0.0:
            previous_delta_pass = False
            previous_cluster_pass = False
            continue
        direction = 1 if delta > 0.0 else -1
        same_side_volume = buy if direction > 0 else sell
        same_prices = {value.price for value in buffer if value.direction == direction}
        delta_pass = abs(delta) >= thresholds["abs_delta"]
        cluster_pass = bool(
            delta_pass
            and volume >= thresholds["volume"]
            and same_side_volume >= thresholds["same_side_volume"]
            and abs(delta / volume) > parameters.pressure_ratio_threshold
            and len(same_prices) >= parameters.minimum_price_levels
        )
        if delta_pass and (
            not previous_delta_pass or direction != previous_delta_direction
        ):
            delta_candidates.append(
                _candidate(
                    session.index,
                    "DELTA_ONLY_TRIGGER",
                    tuple(buffer),
                    trade,
                    buy,
                    sell,
                    notional,
                    distributions,
                    median_volume,
                    mad_volume,
                    parameters.cluster_window_ms,
                )
            )
        if cluster_pass and (
            not previous_cluster_pass or direction != previous_cluster_direction
        ):
            cluster_candidates.append(
                _candidate(
                    session.index,
                    "TRADE_CLUSTER_TRIGGER",
                    tuple(buffer),
                    trade,
                    buy,
                    sell,
                    notional,
                    distributions,
                    median_volume,
                    mad_volume,
                    parameters.cluster_window_ms,
                )
            )
        previous_delta_pass = delta_pass
        previous_delta_direction = direction if delta_pass else 0
        previous_cluster_pass = cluster_pass
        previous_cluster_direction = direction if cluster_pass else 0
    return delta_candidates, cluster_candidates


def _candidate_raw(candidate: TriggerCandidate) -> dict[str, Any]:
    return {
        "trigger_kind": candidate.trigger_kind,
        "direction": "BUY" if candidate.direction > 0 else "SELL",
        "T_start": _ms_to_iso(candidate.t_start_ms),
        "T_trigger": _ms_to_iso(candidate.t_trigger_ms),
        "T_detect": _ms_to_iso(candidate.t_detect_ms),
        "signal_age_ms": candidate.t_detect_ms - candidate.t_trigger_ms,
        "trade_volume": _round(candidate.trade_volume),
        "trade_notional": _round(candidate.trade_notional, 2),
        "trade_count": candidate.trade_count,
        "trades_per_second": _round(candidate.trades_per_second),
        "buy_volume": _round(candidate.buy_volume),
        "sell_volume": _round(candidate.sell_volume),
        "directional_volume": _round(candidate.directional_volume),
        "delta": _round(candidate.delta),
        "delta_ratio": _round(candidate.delta_ratio),
        "price_level_count": candidate.price_level_count,
        "price_band_low": _round(candidate.price_band_low, 2),
        "price_band_high": _round(candidate.price_band_high, 2),
        "interval_cv": _round(candidate.interval_cv),
        "volume_percentile": _round(candidate.volume_percentile, 3),
        "notional_percentile": _round(candidate.notional_percentile, 3),
        "delta_percentile": _round(candidate.delta_percentile, 3),
        "robust_volume_z": _round(candidate.robust_volume_z),
    }


def _build_episodes(
    candidates: Sequence[TriggerCandidate],
    session: SessionData,
    inactivity_timeout_ms: int,
) -> list[dict[str, Any]]:
    if not candidates:
        return []
    episodes: list[dict[str, Any]] = []
    active: dict[str, Any] | None = None

    def close(end_ms: int, reason: str) -> None:
        nonlocal active
        assert active is not None
        active["t_end_ms"] = min(end_ms, session.source_end_ms)
        active["end_reason"] = reason
        episodes.append(active)
        active = None

    for sequence, candidate in enumerate(candidates, start=1):
        if active is not None:
            gap = candidate.t_trigger_ms - active["last_trigger_ms"]
            if gap > inactivity_timeout_ms:
                close(active["last_trigger_ms"] + inactivity_timeout_ms, "INACTIVITY_TIMEOUT")
            elif candidate.direction != active["direction"]:
                close(candidate.t_trigger_ms, "NEW_OPPOSITE_TRIGGER")
        if active is None:
            active = {
                "episode_id": (
                    f"{session.session_id}:{candidate.trigger_kind}:{sequence}:"
                    f"{candidate.t_trigger_ms}"
                ),
                "session_index": session.index,
                "trigger_kind": candidate.trigger_kind,
                "direction": candidate.direction,
                "t_start_ms": candidate.t_start_ms,
                "t_trigger_ms": candidate.t_trigger_ms,
                "t_detect_trade_ms": candidate.t_detect_ms,
                "last_trigger_ms": candidate.t_trigger_ms,
                "trigger_count": 1,
                "trigger_raw": _candidate_raw(candidate),
            }
        else:
            active["last_trigger_ms"] = candidate.t_trigger_ms
            active["trigger_count"] += 1
    if active is not None:
        end = active["last_trigger_ms"] + inactivity_timeout_ms
        reason = "INACTIVITY_TIMEOUT" if end <= session.source_end_ms else "SESSION_END"
        close(end, reason)
    return episodes


def _quote_before(
    quotes: Sequence[Quote], source_times: Sequence[int], target_ms: int, stale_ms: int
) -> Quote | None:
    index = bisect.bisect_right(source_times, target_ms) - 1
    if index < 0:
        return None
    quote = quotes[index]
    return quote if target_ms - quote.source_ms <= stale_ms else None


def _quote_after(
    quotes: Sequence[Quote], source_times: Sequence[int], target_ms: int, lag_ms: int
) -> tuple[int, Quote] | None:
    index = bisect.bisect_left(source_times, target_ms)
    if index >= len(quotes):
        return None
    quote = quotes[index]
    if quote.source_ms - target_ms > lag_ms:
        return None
    return index, quote


def _measure_outcome(
    session: SessionData,
    start_ms: int,
    direction: int,
    horizons_sec: Sequence[int],
    stale_ms: int,
) -> dict[str, Any] | None:
    quotes = session.quotes
    if not quotes:
        return None
    times = session.quote_source_times
    base = _quote_before(quotes, times, start_ms, stale_ms)
    if base is None:
        return None
    base_index = bisect.bisect_right(times, start_ms) - 1
    result: dict[str, Any] = {
        "base_time": _ms_to_iso(start_ms),
        "base_quote_source_time": _ms_to_iso(base.source_ms),
        "base_mid": _round(base.mid, 4),
        "horizons": {},
    }
    for horizon in horizons_sec:
        target_ms = start_ms + horizon * 1000
        located = _quote_after(quotes, times, target_ms, stale_ms)
        if located is None:
            return None
        target_index, target = located
        path = quotes[base_index : target_index + 1]
        signed = [
            ((quote.mid - base.mid) * direction / base.mid) * 10_000.0
            for quote in path
        ]
        if not signed:
            return None
        maximum = max(signed)
        minimum = min(signed)
        index_mfe = signed.index(maximum)
        index_mae = signed.index(minimum)
        mfe = max(0.0, maximum)
        mae = max(0.0, -minimum)
        result["horizons"][str(horizon)] = {
            "outcome_quote_source_time": _ms_to_iso(target.source_ms),
            "signed_return_bps": _round(signed[-1]),
            "mfe_bps": _round(mfe),
            "mae_bps": _round(mae),
            "mfe_mae_ratio": _round(mfe / mae if mae > 0.0 else None),
            "time_to_mfe_ms": path[index_mfe].source_ms - start_ms,
            "time_to_mae_ms": path[index_mae].source_ms - start_ms,
        }
    return result


def _measure_responses(
    session: SessionData,
    trigger_ms: int,
    direction: int,
    stale_ms: int,
) -> dict[str, Any]:
    quotes = session.quotes
    times = session.quote_source_times
    base = _quote_before(quotes, times, trigger_ms, stale_ms)
    result: dict[str, Any] = {}
    if base is None:
        return {str(value): None for value in RESPONSE_HORIZONS_MS}
    for horizon_ms in RESPONSE_HORIZONS_MS:
        located = _quote_after(quotes, times, trigger_ms + horizon_ms, stale_ms)
        if located is None:
            result[str(horizon_ms)] = None
            continue
        _, quote = located
        result[str(horizon_ms)] = _round(
            ((quote.mid - base.mid) * direction / base.mid) * 10_000.0
        )
    return result


def _book_evidence(
    session: SessionData,
    episode: dict[str, Any],
    parameters: Parameters,
) -> dict[str, Any]:
    quotes = session.quotes
    times = session.quote_source_times
    start = _quote_before(quotes, times, episode["t_start_ms"], parameters.book_stale_after_ms)
    trigger = _quote_before(
        quotes, times, episode["t_trigger_ms"], parameters.book_stale_after_ms
    )
    if start is None or trigger is None:
        return {
            "data_quality": "MISSING_OR_STALE",
            "missing_reason": "no synchronized source-time quote within stale guard",
            "aggressor_side": "BOOK_DATA_INVALID",
            "support_side": "BOOK_DATA_INVALID",
            "supported": False,
            "detect_ms": None,
        }
    if episode["direction"] > 0:
        aggressor_start = start.ask_top_quantity
        aggressor_end = trigger.ask_top_quantity
        support_start = start.bid_top_quantity
        support_end = trigger.bid_top_quantity
    else:
        aggressor_start = start.bid_top_quantity
        aggressor_end = trigger.bid_top_quantity
        support_start = start.ask_top_quantity
        support_end = trigger.ask_top_quantity
    aggressor_change = aggressor_end - aggressor_start
    support_change = support_end - support_start
    if aggressor_change < 0.0:
        aggressor_label = "BOOK_REDUCED_UNCLASSIFIED"
    elif aggressor_change > 0.0:
        aggressor_label = "AGGRESSOR_SIDE_REPLENISHED"
    else:
        aggressor_label = "AGGRESSOR_SIDE_UNCHANGED"
    if support_change > 0.0:
        support_label = "SUPPORT_SIDE_ADDED"
    elif support_change < 0.0:
        support_label = "SUPPORT_SIDE_CANCELLED"
    else:
        support_label = "SUPPORT_SIDE_UNCHANGED"
    return {
        "data_quality": "PARTIAL_TOP_N_PROXY",
        "observed_depth_levels": parameters.book_depth_levels,
        "constraint": "top-N quantity proxy; cluster-price-band reconciliation not implemented",
        "top_n_quantity_refresh_ms": 500,
        "start_quote_source_time": _ms_to_iso(start.source_ms),
        "trigger_quote_source_time": _ms_to_iso(trigger.source_ms),
        "start_quote_received_time": _ms_to_iso(start.received_ms),
        "trigger_quote_received_time": _ms_to_iso(trigger.received_ms),
        "aggressor_start_quantity": _round(aggressor_start),
        "aggressor_end_quantity": _round(aggressor_end),
        "aggressor_change": _round(aggressor_change),
        "support_start_quantity": _round(support_start),
        "support_end_quantity": _round(support_end),
        "support_change": _round(support_change),
        "aggressor_side": aggressor_label,
        "support_side": support_label,
        "supported": aggressor_label == "BOOK_REDUCED_UNCLASSIFIED",
        "detect_ms": max(episode["t_detect_trade_ms"], trigger.received_ms),
    }


def _oi_evidence(
    episode: dict[str, Any],
    oi_samples: Sequence[OISample],
    oi_times: Sequence[int],
    episode_trigger_times: Sequence[int],
    parameters: Parameters,
) -> dict[str, Any]:
    trigger = episode["t_trigger_ms"]
    previous_index = bisect.bisect_right(oi_times, trigger) - 1
    next_index = bisect.bisect_right(oi_times, trigger)
    maximum_gap_ms = parameters.oi_poll_interval_sec * 3 * 1000
    if previous_index < 0 or next_index >= len(oi_samples):
        return {"state": "OI_UNKNOWN", "attributable": False, "detect_ms": None}
    previous = oi_samples[previous_index]
    following = oi_samples[next_index]
    if trigger - previous.source_ms > maximum_gap_ms or following.source_ms - trigger > maximum_gap_ms:
        return {
            "state": "OI_UNKNOWN",
            "attributable": False,
            "missing_reason": "poll samples outside 3x configured interval",
            "detect_ms": None,
        }
    first_trigger = bisect.bisect_right(episode_trigger_times, previous.source_ms)
    last_trigger = bisect.bisect_right(episode_trigger_times, following.source_ms)
    attributable = last_trigger - first_trigger == 1
    change = following.value - previous.value
    state = "OI_UP" if change > 0.0 else "OI_DOWN" if change < 0.0 else "OI_FLAT"
    if not attributable:
        state = "OI_UNATTRIBUTABLE"
    return {
        "state": state,
        "attributable": attributable,
        "previous_source_time": _ms_to_iso(previous.source_ms),
        "next_source_time": _ms_to_iso(following.source_ms),
        "previous_received_time": _ms_to_iso(previous.received_ms),
        "next_received_time": _ms_to_iso(following.received_ms),
        "previous_open_interest": _round(previous.value, 3),
        "next_open_interest": _round(following.value, 3),
        "change": _round(change, 3),
        "poll_interval_ms": following.source_ms - previous.source_ms,
        "episode_count_in_poll_window": last_trigger - first_trigger,
        "directional": False,
        "detect_ms": following.received_ms if attributable else None,
    }


def _liquidation_evidence(
    session: SessionData, episode: dict[str, Any]
) -> dict[str, Any]:
    start = episode["t_start_ms"]
    end = episode["t_trigger_ms"] + 1000
    events = [value for value in session.liquidations if start <= value.source_ms <= end]
    if not events:
        return {
            "state": "LIQUIDATION_UNOBSERVED",
            "independent": False,
            "event_count": 0,
            "detect_ms": None,
        }
    aligned = sum(value.direction == episode["direction"] for value in events)
    opposite = len(events) - aligned
    state = (
        "LIQUIDATION_ALIGNED"
        if aligned > opposite
        else "LIQUIDATION_OPPOSITE"
        if opposite > aligned
        else "LIQUIDATION_PRESENT"
    )
    return {
        "state": state,
        "independent": False,
        "event_count": len(events),
        "aligned_count": aligned,
        "opposite_count": opposite,
        "reported_quantity": _round(sum(value.quantity for value in events)),
        "quantity_trusted": False,
        "detect_ms": max(value.received_ms for value in events),
    }


def _attach_evidence_and_outcomes(
    episodes: list[dict[str, Any]],
    sessions: Sequence[SessionData],
    oi_samples: Sequence[OISample],
    parameters: Parameters,
) -> None:
    oi_times = [value.source_ms for value in oi_samples]
    trigger_times = sorted(value["t_trigger_ms"] for value in episodes)
    for episode in episodes:
        session = sessions[episode["session_index"]]
        episode["T_start"] = _ms_to_iso(episode["t_start_ms"])
        episode["T_trigger"] = _ms_to_iso(episode["t_trigger_ms"])
        episode["T_detect_trade"] = _ms_to_iso(episode["t_detect_trade_ms"])
        episode["T_end"] = _ms_to_iso(episode["t_end_ms"])
        episode["signal_age_trade_ms"] = (
            episode["t_detect_trade_ms"] - episode["t_trigger_ms"]
        )
        episode["trade_clock_order_valid"] = (
            episode["t_detect_trade_ms"] >= episode["t_trigger_ms"]
        )
        episode["price_response_bps"] = _measure_responses(
            session,
            episode["t_trigger_ms"],
            episode["direction"],
            parameters.book_stale_after_ms,
        )
        book = _book_evidence(session, episode, parameters)
        oi = _oi_evidence(episode, oi_samples, oi_times, trigger_times, parameters)
        liquidation = _liquidation_evidence(session, episode)
        episode["book"] = book
        episode["open_interest"] = oi
        episode["liquidation"] = liquidation
        episode["outcome_theoretical"] = _measure_outcome(
            session,
            episode["t_trigger_ms"],
            episode["direction"],
            OUTCOME_HORIZONS_SEC,
            parameters.book_stale_after_ms,
        )
        episode["outcome_real_trade"] = (
            _measure_outcome(
                session,
                episode["t_detect_trade_ms"],
                episode["direction"],
                OUTCOME_HORIZONS_SEC,
                parameters.book_stale_after_ms,
            )
            if episode["trade_clock_order_valid"]
            else None
        )
        book_detect = book.get("detect_ms")
        episode["outcome_real_book"] = (
            _measure_outcome(
                session,
                int(book_detect),
                episode["direction"],
                OUTCOME_HORIZONS_SEC,
                parameters.book_stale_after_ms,
            )
            if isinstance(book_detect, int) and book_detect >= episode["t_trigger_ms"]
            else None
        )
        oi_detect = oi.get("detect_ms")
        episode["outcome_real_oi"] = (
            _measure_outcome(
                session,
                max(episode["t_detect_trade_ms"], int(oi_detect)),
                episode["direction"],
                OUTCOME_HORIZONS_SEC,
                parameters.book_stale_after_ms,
            )
            if isinstance(oi_detect, int) and oi_detect >= episode["t_trigger_ms"]
            else None
        )


def _mark_overlap(episodes: Sequence[dict[str, Any]], horizon_sec: int) -> None:
    last_end_by_session: dict[int, int] = {}
    for episode in sorted(episodes, key=lambda value: (value["session_index"], value["t_trigger_ms"])):
        previous_end = last_end_by_session.get(episode["session_index"], -1)
        overlap = episode["t_trigger_ms"] < previous_end
        episode["evaluation_overlap"] = overlap
        if not overlap:
            last_end_by_session[episode["session_index"]] = (
                episode["t_trigger_ms"] + horizon_sec * 1000
            )


def _wilson(successes: int, sample_count: int) -> list[float] | None:
    if sample_count <= 0:
        return None
    z = 1.959963984540054
    p = successes / sample_count
    denominator = 1.0 + z * z / sample_count
    center = (p + z * z / (2.0 * sample_count)) / denominator
    margin = (
        z
        * math.sqrt(p * (1.0 - p) / sample_count + z * z / (4.0 * sample_count**2))
        / denominator
    )
    return [_round(max(0.0, center - margin)), _round(min(1.0, center + margin))]  # type: ignore[list-item]


def _summarize_outcomes(
    episodes: Sequence[dict[str, Any]], outcome_key: str
) -> dict[str, Any]:
    complete = [
        value
        for value in episodes
        if not value.get("evaluation_overlap") and value.get(outcome_key) is not None
    ]
    result: dict[str, Any] = {
        "candidate_episodes": len(episodes),
        "overlap_excluded": sum(bool(value.get("evaluation_overlap")) for value in episodes),
        "complete_independent_episodes": len(complete),
        "missing_outcome": sum(
            not value.get("evaluation_overlap") and value.get(outcome_key) is None
            for value in episodes
        ),
        "horizons": {},
    }
    for horizon in OUTCOME_HORIZONS_SEC:
        key = str(horizon)
        rows = [value[outcome_key]["horizons"][key] for value in complete]
        returns = [float(value["signed_return_bps"]) for value in rows]
        mfe = [float(value["mfe_bps"]) for value in rows]
        mae = [float(value["mae_bps"]) for value in rows]
        time_mfe = [int(value["time_to_mfe_ms"]) for value in rows]
        time_mae = [int(value["time_to_mae_ms"]) for value in rows]
        ratios = [float(value["mfe_mae_ratio"]) for value in rows if value["mfe_mae_ratio"] is not None]
        hits = sum(value > 0.0 for value in returns)
        result["horizons"][key] = {
            "n": len(rows),
            "hit_rate": _round(hits / len(rows) if rows else None),
            "hit_rate_wilson95": _wilson(hits, len(rows)),
            "mean_signed_return_bps": _round(statistics.fmean(returns) if returns else None),
            "median_signed_return_bps": _round(statistics.median(returns) if returns else None),
            "median_mfe_bps": _round(statistics.median(mfe) if mfe else None),
            "median_mae_bps": _round(statistics.median(mae) if mae else None),
            "median_mfe_mae_ratio": _round(statistics.median(ratios) if ratios else None),
            "median_time_to_mfe_ms": _round(statistics.median(time_mfe) if time_mfe else None, 1),
            "median_time_to_mae_ms": _round(statistics.median(time_mae) if time_mae else None, 1),
        }
    return result


def _market_context(
    session: SessionData, target_ms: int, stale_ms: int
) -> tuple[float, float, float] | None:
    quotes = session.quotes
    times = session.quote_source_times
    current = _quote_before(quotes, times, target_ms, stale_ms)
    if current is None:
        return None
    start_index = bisect.bisect_left(times, target_ms - 30_000)
    end_index = bisect.bisect_right(times, target_ms)
    path = quotes[start_index:end_index]
    if len(path) < 2:
        return None
    mids = [value.mid for value in path]
    range_bps = (max(mids) - min(mids)) / current.mid * 10_000.0
    liquidity = current.bid_top_quantity + current.ask_top_quantity
    return range_bps, current.spread_bps, liquidity


def _baseline_episode(
    episode_id: str,
    session: SessionData,
    target_ms: int,
    direction: int,
    parameters: Parameters,
    kind: str,
) -> dict[str, Any] | None:
    outcome = _measure_outcome(
        session,
        target_ms,
        direction,
        OUTCOME_HORIZONS_SEC,
        parameters.book_stale_after_ms,
    )
    if outcome is None:
        return None
    return {
        "episode_id": f"{kind}:{episode_id}",
        "session_index": session.index,
        "direction": direction,
        "t_trigger_ms": target_ms,
        "evaluation_overlap": False,
        "outcome_theoretical": outcome,
    }


def _build_real_baselines(
    reference: Sequence[dict[str, Any]],
    sessions: Sequence[SessionData],
    parameters: Parameters,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    independent = [
        value
        for value in reference
        if not value.get("evaluation_overlap") and value.get("outcome_theoretical") is not None
    ]
    unconditional: list[dict[str, Any]] = []
    matched: list[dict[str, Any]] = []
    candidate_cache: dict[int, list[tuple[int, tuple[float, float, float]]]] = {}
    used_matched: dict[int, set[int]] = {}
    all_pressure_by_session: dict[int, list[tuple[int, int]]] = {}
    for value in reference:
        all_pressure_by_session.setdefault(value["session_index"], []).append(
            (value["t_start_ms"], value["t_end_ms"])
        )

    for episode in independent:
        session = sessions[episode["session_index"]]
        lower = session.source_start_ms + 30_000
        upper = session.source_end_ms - max(OUTCOME_HORIZONS_SEC) * 1000 - 2_000
        if upper <= lower:
            continue
        for attempt in range(32):
            digest = hashlib.sha256(
                f"{episode['episode_id']}:unconditional:{attempt}".encode("utf-8")
            ).digest()
            fraction = int.from_bytes(digest[:8], "big") / float(2**64 - 1)
            target = lower + int((upper - lower) * fraction)
            baseline = _baseline_episode(
                episode["episode_id"],
                session,
                target,
                episode["direction"],
                parameters,
                "UNCONDITIONAL_REAL_TIME",
            )
            if baseline is not None:
                unconditional.append(baseline)
                break

        if session.index not in candidate_cache:
            candidates: list[tuple[int, tuple[float, float, float]]] = []
            pressure_intervals = sorted(all_pressure_by_session.get(session.index, ()))
            for target in range(lower, upper + 1, 30_000):
                contaminated = any(
                    start - parameters.cluster_window_ms
                    <= target
                    <= end + parameters.cluster_window_ms
                    for start, end in pressure_intervals
                )
                if contaminated:
                    continue
                context = _market_context(session, target, parameters.book_stale_after_ms)
                if context is not None:
                    candidates.append((target, context))
            candidate_cache[session.index] = candidates
            used_matched[session.index] = set()

        reference_context = _market_context(
            session, episode["t_trigger_ms"], parameters.book_stale_after_ms
        )
        if reference_context is None:
            continue
        best: tuple[float, int] | None = None
        for target, context in candidate_cache[session.index]:
            if target in used_matched[session.index]:
                continue
            distance = sum(
                abs(math.log((candidate_value + 1e-9) / (reference_value + 1e-9)))
                for candidate_value, reference_value in zip(context, reference_context)
            )
            if best is None or distance < best[0]:
                best = (distance, target)
        if best is not None:
            baseline = _baseline_episode(
                episode["episode_id"],
                session,
                best[1],
                episode["direction"],
                parameters,
                "MATCHED_REAL_TIME",
            )
            if baseline is not None:
                baseline["match_distance"] = _round(best[0])
                used_matched[session.index].add(best[1])
                matched.append(baseline)

    return unconditional, matched, {
        "unconditional_sampling": (
            "deterministic SHA-256 selection of real source times in the same session; "
            "reference episode direction is retained"
        ),
        "matched_sampling": (
            "one-to-one real 30-second anchors in the same session, excluding active "
            "pressure-episode intervals, matched on trailing 30s range, spread, and "
            "top-N liquidity"
        ),
        "synthetic_prices_or_events": False,
    }


def _comparison(
    left: dict[str, Any], right: dict[str, Any]
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for horizon in OUTCOME_HORIZONS_SEC:
        key = str(horizon)
        a = left["horizons"][key]
        b = right["horizons"][key]
        result[key] = {
            "left_n": a["n"],
            "right_n": b["n"],
            "hit_rate_difference_points": (
                _round((a["hit_rate"] - b["hit_rate"]) * 100.0, 3)
                if a["hit_rate"] is not None and b["hit_rate"] is not None
                else None
            ),
            "median_return_difference_bps": (
                _round(a["median_signed_return_bps"] - b["median_signed_return_bps"])
                if a["median_signed_return_bps"] is not None
                and b["median_signed_return_bps"] is not None
                else None
            ),
        }
    return result


def _clean_episode_for_json(episode: dict[str, Any]) -> dict[str, Any]:
    hidden = {
        "t_start_ms",
        "t_trigger_ms",
        "t_detect_trade_ms",
        "last_trigger_ms",
        "t_end_ms",
        "direction",
    }
    result = {key: value for key, value in episode.items() if key not in hidden}
    result["direction"] = "BUY" if episode["direction"] > 0 else "SELL"
    return result


def _run_validation(
    session_paths: Sequence[Path], excluded_sessions: Sequence[str], parameters: Parameters
) -> dict[str, Any]:
    approximate_split_index = _approximate_split_session_index(
        session_paths, parameters.train_fraction
    )
    sessions = [
        _load_session(
            index,
            path,
            parameters,
            replay_depth=index >= approximate_split_index,
        )
        for index, path in enumerate(session_paths)
    ]
    split_ms, split_session_index, active_seconds = _active_time_split(
        sessions, parameters.train_fraction
    )
    evaluation_start_ms = split_ms + parameters.split_embargo_sec * 1000
    distributions = _training_feature_distributions(sessions, split_ms, parameters)
    thresholds = {
        name: _quantile(values, parameters.outlier_quantile)
        for name, values in distributions.items()
    }

    all_delta_episodes: list[dict[str, Any]] = []
    all_cluster_episodes: list[dict[str, Any]] = []
    candidate_counts: list[dict[str, Any]] = []
    for session in sessions:
        delta_candidates, cluster_candidates = _detect_candidates(
            session, thresholds, distributions, parameters
        )
        delta_episodes = _build_episodes(
            delta_candidates, session, parameters.inactivity_timeout_ms
        )
        cluster_episodes = _build_episodes(
            cluster_candidates, session, parameters.inactivity_timeout_ms
        )
        all_delta_episodes.extend(delta_episodes)
        all_cluster_episodes.extend(cluster_episodes)
        candidate_counts.append(
            {
                "session_id": session.session_id,
                "delta_trigger_candidates": len(delta_candidates),
                "delta_episodes": len(delta_episodes),
                "trade_cluster_candidates": len(cluster_candidates),
                "trade_cluster_episodes": len(cluster_episodes),
            }
        )

    test_delta = [
        value for value in all_delta_episodes if value["t_trigger_ms"] >= evaluation_start_ms
    ]
    test_cluster = [
        value for value in all_cluster_episodes if value["t_trigger_ms"] >= evaluation_start_ms
    ]
    oi_samples, oi_files = _load_oi_samples(sessions)
    # Training episodes exist only to establish the frozen feature distribution.
    # Never spend outcome work on them, and never let their outcomes enter the
    # evaluation object.
    _attach_evidence_and_outcomes(test_delta, sessions, oi_samples, parameters)
    _attach_evidence_and_outcomes(test_cluster, sessions, oi_samples, parameters)
    _mark_overlap(test_delta, max(OUTCOME_HORIZONS_SEC))
    _mark_overlap(test_cluster, max(OUTCOME_HORIZONS_SEC))

    book_reduced = [
        value for value in test_cluster if value["book"].get("supported") is True
    ]
    oi_up = [
        value
        for value in book_reduced
        if value["open_interest"].get("state") == "OI_UP"
    ]
    oi_down = [
        value
        for value in book_reduced
        if value["open_interest"].get("state") == "OI_DOWN"
    ]
    liquidation_observed = [
        value
        for value in test_cluster
        if value["liquidation"].get("state") != "LIQUIDATION_UNOBSERVED"
    ]
    clock_inversions = sum(
        value["t_detect_trade_ms"] < value["t_trigger_ms"] for value in test_cluster
    )
    valid_signal_ages = sorted(
        value["t_detect_trade_ms"] - value["t_trigger_ms"]
        for value in test_cluster
        if value["t_detect_trade_ms"] >= value["t_trigger_ms"]
    )

    unconditional, matched, baseline_protocol = _build_real_baselines(
        test_cluster, sessions, parameters
    )
    tiers = {
        "UNCONDITIONAL_REAL_BASELINE": _summarize_outcomes(
            unconditional, "outcome_theoretical"
        ),
        "MATCHED_REAL_BASELINE": _summarize_outcomes(matched, "outcome_theoretical"),
        "DELTA_ONLY_BASELINE_THEORETICAL": _summarize_outcomes(
            test_delta, "outcome_theoretical"
        ),
        "TRADE_CLUSTER_THEORETICAL": _summarize_outcomes(
            test_cluster, "outcome_theoretical"
        ),
        "TRADE_CLUSTER_REAL_TDETECT": _summarize_outcomes(
            test_cluster, "outcome_real_trade"
        ),
        "TRADE_PLUS_BOOK_REDUCED_THEORETICAL": _summarize_outcomes(
            book_reduced, "outcome_theoretical"
        ),
        "TRADE_PLUS_BOOK_REDUCED_REAL_TDETECT": _summarize_outcomes(
            book_reduced, "outcome_real_book"
        ),
        "TRADE_BOOK_OI_UP_REAL_CONFIRMATION": _summarize_outcomes(
            oi_up, "outcome_real_oi"
        ),
        "TRADE_BOOK_OI_DOWN_REAL_CONFIRMATION": _summarize_outcomes(
            oi_down, "outcome_real_oi"
        ),
    }

    concept_hash = _sha256_file(CONCEPT_PATH)
    file_hashes = [
        item["sha256"]
        for session in sessions
        for item in session.counts["files"]
    ] + [item["sha256"] for item in oi_files]
    dataset_hash = hashlib.sha256("\n".join(file_hashes).encode("ascii")).hexdigest()
    integrity_ok = all(
        session.counts["summary_consistent"]
        and session.counts["json_errors"] == 0
        and session.counts["sequence_gaps"] == 0
        and session.counts["sequence_reversals"] == 0
        and session.counts["trade_source_reversals"] == 0
        for session in sessions
    )
    trade_n = tiers["TRADE_CLUSTER_THEORETICAL"]["complete_independent_episodes"]
    book_n = tiers["TRADE_PLUS_BOOK_REDUCED_THEORETICAL"][
        "complete_independent_episodes"
    ]
    reasons: list[str] = []
    if not integrity_ok:
        reasons.append("one or more selected capture sessions failed integrity checks")
    if trade_n < parameters.minimum_interim_episodes:
        reasons.append(
            f"trade-cluster independent test episodes below interim minimum "
            f"({trade_n} < {parameters.minimum_interim_episodes})"
        )
    if trade_n < parameters.minimum_deployment_episodes:
        reasons.append(
            f"trade-cluster independent test episodes below deployment minimum "
            f"({trade_n} < {parameters.minimum_deployment_episodes})"
        )
    if book_n < parameters.minimum_interim_episodes:
        reasons.append(
            f"book-confirmed independent episodes below interim minimum "
            f"({book_n} < {parameters.minimum_interim_episodes})"
        )
    if not liquidation_observed:
        reasons.append("no forceOrder event overlaps an evaluation pressure episode")
    if clock_inversions:
        reasons.append(
            f"source/received clock inversion makes T_detect unusable for "
            f"{clock_inversions} evaluation episodes"
        )
    reasons.append(
        "book evidence is PARTIAL_TOP_N_PROXY; cluster-price-band trade/depth "
        "reconciliation remains unimplemented"
    )
    reasons.append(
        "the concept leaves the incremental-significance method undecided; this "
        "harness therefore reports differences but does not declare significance"
    )

    report: dict[str, Any] = {
        "purpose": "DIRECTIONAL_PRESSURE_V4_REAL_EVENT_VALIDATION_ONLY",
        "concept": {
            "path": str(CONCEPT_PATH.resolve()),
            "sha256": concept_hash,
            "implementation_scope": (
                "validation harness only; no production detector, signal, order, "
                "Flow Price Response, or chart mutation"
            ),
        },
        "data_policy": {
            "synthetic_market_data": False,
            "generated_prices": False,
            "generated_events": False,
            "production_writes": False,
            "runtime_changes": False,
            "baseline_timestamps": "real captured source times only",
        },
        "dataset": {
            "sha256": dataset_hash,
            "selected_session_count": len(sessions),
            "excluded_sessions": list(excluded_sessions),
            "active_source_seconds": _round(active_seconds, 3),
            "source_start": _ms_to_iso(min(value.source_start_ms for value in sessions)),
            "source_end": _ms_to_iso(max(value.source_end_ms for value in sessions)),
            "records": sum(value.counts["records"] for value in sessions),
            "valid_trades": sum(value.counts["valid_trades"] for value in sessions),
            "quotes": sum(value.counts["quotes"] for value in sessions),
            "quote_scope": (
                "synchronized books replayed from the approximate split session onward; "
                "training-only books intentionally skipped"
            ),
            "liquidations": sum(value.counts["liquidations"] for value in sessions),
            "oi_samples": len(oi_samples),
            "oi_files": oi_files,
            "integrity_ok": integrity_ok,
            "sessions": [
                {
                    "session_id": value.session_id,
                    "path": str(value.path.resolve()),
                    "source_start": _ms_to_iso(value.source_start_ms),
                    "source_end": _ms_to_iso(value.source_end_ms),
                    "counts": value.counts,
                }
                for value in sessions
            ],
        },
        "protocol": {
            "parameter_sources": {
                "runtime": {
                    "path": str(RUNTIME_CONFIG.resolve()),
                    "sha256": _sha256_file(RUNTIME_CONFIG),
                },
                "validation": {
                    "path": str(VALIDATION_CONFIG.resolve()),
                    "sha256": _sha256_file(VALIDATION_CONFIG),
                },
                "distribution_outlier": (
                    "research assumption fitted on chronological train block only; "
                    "not an approved concept parameter"
                ),
            },
            "actual_input_stream": "btcusdt@trade (individual trades), not aggTrade",
            "trade_adapter": (
                "individual public trades are clustered directly; no synthetic "
                "aggregation or participant identity claim"
            ),
            "cluster_window_ms": parameters.cluster_window_ms,
            "fixed_grid_training_sample_ms": parameters.sample_step_ms,
            "outlier_quantile": parameters.outlier_quantile,
            "inactivity_timeout_ms": parameters.inactivity_timeout_ms,
            "minimum_price_levels": parameters.minimum_price_levels,
            "pressure_ratio_threshold": parameters.pressure_ratio_threshold,
            "book_stale_after_ms": parameters.book_stale_after_ms,
            "book_depth_levels": parameters.book_depth_levels,
            "train_fraction": parameters.train_fraction,
            "split_source_time": _ms_to_iso(split_ms),
            "split_session_index": split_session_index,
            "depth_replay_start_session_index": approximate_split_index,
            "embargo_sec": parameters.split_embargo_sec,
            "evaluation_start": _ms_to_iso(evaluation_start_ms),
            "outcome_horizons_sec": list(OUTCOME_HORIZONS_SEC),
            "response_horizons_ms": list(RESPONSE_HORIZONS_MS),
            "thresholds_frozen_from_train": {
                key: _round(value) for key, value in thresholds.items()
            },
            "future_outcomes_used_in_thresholds": False,
            "T_detect_definition": (
                "raw journal received_time stamped in DataReceiver callback before "
                "the normalization destination queue"
            ),
            "overlap_policy": (
                "episodes are lifecycle-merged; later episodes whose 5m evaluation "
                "overlaps a retained episode are flagged and excluded from independent stats"
            ),
            "baseline_protocol": baseline_protocol,
        },
        "episode_counts_by_session": candidate_counts,
        "evaluation": {
            "tiers": tiers,
            "incremental_differences_not_significance_claims": {
                "trade_cluster_minus_delta_only": _comparison(
                    tiers["TRADE_CLUSTER_THEORETICAL"],
                    tiers["DELTA_ONLY_BASELINE_THEORETICAL"],
                ),
                "book_reduced_minus_trade_cluster": _comparison(
                    tiers["TRADE_PLUS_BOOK_REDUCED_THEORETICAL"],
                    tiers["TRADE_CLUSTER_THEORETICAL"],
                ),
                "trade_cluster_minus_matched_real": _comparison(
                    tiers["TRADE_CLUSTER_THEORETICAL"],
                    tiers["MATCHED_REAL_BASELINE"],
                ),
            },
            "oi_directionless_strata": {
                "OI_UP_book_reduced_episodes": len(oi_up),
                "OI_DOWN_book_reduced_episodes": len(oi_down),
                "interpretation": (
                    "OI never supplies BUY/SELL direction and is not counted as an "
                    "independent directional trace"
                ),
            },
            "liquidation_overlap_episodes": len(liquidation_observed),
            "T_detect_trade_quality": {
                "evaluation_episodes": len(test_cluster),
                "source_received_clock_inversions": clock_inversions,
                "valid_signal_age_count": len(valid_signal_ages),
                "valid_signal_age_p50_ms": _round(
                    _quantile(valid_signal_ages, 0.50) if valid_signal_ages else None, 3
                ),
                "valid_signal_age_p95_ms": _round(
                    _quantile(valid_signal_ages, 0.95) if valid_signal_ages else None, 3
                ),
                "clock_inversions_excluded_from_real_Tdetect_metrics": True,
            },
        },
        "verdict": {
            "status": "INCOMPLETE_EVIDENCE_NO_FULL_V4_JUSTIFICATION",
            "delta_only_increment_significant": None,
            "full_five_trace_justified": False,
            "reasons": reasons,
            "decision_rule": (
                "No deployment or five-trace justification is allowed unless frozen "
                "out-of-sample evidence reaches repository minimums and an approved "
                "incremental-significance method confirms value over delta-only."
            ),
        },
        "episodes": {
            "delta_only_evaluation": [_clean_episode_for_json(value) for value in test_delta],
            "trade_cluster_evaluation": [
                _clean_episode_for_json(value) for value in test_cluster
            ],
        },
    }
    canonical = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    report["deterministic_result_sha256"] = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()
    return report


def _percent(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100.0:.1f}%"


def _number(value: float | None, suffix: str = "") -> str:
    return "N/A" if value is None else f"{value:.3f}{suffix}"


def _render_report(report: dict[str, Any]) -> str:
    dataset = report["dataset"]
    protocol = report["protocol"]
    tiers = report["evaluation"]["tiers"]
    detect_quality = report["evaluation"]["T_detect_trade_quality"]
    lines = [
        "=" * 88,
        "DIRECTIONAL PRESSURE v4 - REAL EVENT EPISODE VALIDATION (READ ONLY)",
        "=" * 88,
        f"Concept SHA-256: {report['concept']['sha256']}",
        f"Dataset SHA-256: {dataset['sha256']}",
        (
            f"Sessions={dataset['selected_session_count']} | records={dataset['records']:,} | "
            f"trades={dataset['valid_trades']:,} | synchronized quotes={dataset['quotes']:,} | "
            f"OI={dataset['oi_samples']:,} | forceOrder={dataset['liquidations']:,}"
        ),
        f"Integrity: {dataset['integrity_ok']} | source {dataset['source_start']} -> {dataset['source_end']}",
        "-" * 88,
        "FROZEN CAUSAL PROTOCOL",
        (
            f"Actual stream={protocol['actual_input_stream']} | cluster={protocol['cluster_window_ms']}ms | "
            f"inactivity={protocol['inactivity_timeout_ms']}ms"
        ),
        (
            f"Train split={protocol['split_source_time']} | embargo={protocol['embargo_sec']}s | "
            f"evaluation={protocol['evaluation_start']}"
        ),
        (
            f"Train-only q={protocol['outlier_quantile']}: "
            f"volume={protocol['thresholds_frozen_from_train']['volume']:.6f} BTC, "
            f"same-side={protocol['thresholds_frozen_from_train']['same_side_volume']:.6f} BTC, "
            f"|delta|={protocol['thresholds_frozen_from_train']['abs_delta']:.6f} BTC"
        ),
        "T_start/T_trigger/T_detect/T_end are stored per episode; response and outcome are separated.",
        (
            f"T_detect quality: clock_inversions="
            f"{detect_quality['source_received_clock_inversions']}, "
            f"valid_age_p50={_number(detect_quality['valid_signal_age_p50_ms'], ' ms')}, "
            f"valid_age_p95={_number(detect_quality['valid_signal_age_p95_ms'], ' ms')}"
        ),
        "-" * 88,
        "INDEPENDENT OUT-OF-SAMPLE RESULTS (5m-overlap excluded)",
    ]
    display = (
        "UNCONDITIONAL_REAL_BASELINE",
        "MATCHED_REAL_BASELINE",
        "DELTA_ONLY_BASELINE_THEORETICAL",
        "TRADE_CLUSTER_THEORETICAL",
        "TRADE_CLUSTER_REAL_TDETECT",
        "TRADE_PLUS_BOOK_REDUCED_THEORETICAL",
        "TRADE_PLUS_BOOK_REDUCED_REAL_TDETECT",
        "TRADE_BOOK_OI_UP_REAL_CONFIRMATION",
        "TRADE_BOOK_OI_DOWN_REAL_CONFIRMATION",
    )
    for name in display:
        value = tiers[name]
        lines.append(
            f"{name}: candidates={value['candidate_episodes']}, "
            f"independent_complete={value['complete_independent_episodes']}, "
            f"overlap_excluded={value['overlap_excluded']}, missing={value['missing_outcome']}"
        )
        for horizon in OUTCOME_HORIZONS_SEC:
            stats = value["horizons"][str(horizon)]
            interval = stats["hit_rate_wilson95"]
            ci = (
                "N/A"
                if interval is None
                else f"{interval[0] * 100.0:.1f}-{interval[1] * 100.0:.1f}%"
            )
            lines.append(
                f"  {horizon // 60}m n={stats['n']}: hit={_percent(stats['hit_rate'])} "
                f"(Wilson95 {ci}), median={_number(stats['median_signed_return_bps'], ' bps')}, "
                f"MFE={_number(stats['median_mfe_bps'], ' bps')}, "
                f"MAE={_number(stats['median_mae_bps'], ' bps')}"
            )
    lines.extend(
        [
            "-" * 88,
            "INCREMENTAL DIFFERENCES (descriptive only; not a significance claim)",
        ]
    )
    comparisons = report["evaluation"]["incremental_differences_not_significance_claims"]
    for name, values in comparisons.items():
        lines.append(name)
        for horizon, value in values.items():
            lines.append(
                f"  {int(horizon) // 60}m: hit diff="
                f"{_number(value['hit_rate_difference_points'], ' points')}, "
                f"median diff={_number(value['median_return_difference_bps'], ' bps')} "
                f"(n={value['left_n']} vs {value['right_n']})"
            )
    lines.extend(
        [
            "-" * 88,
            f"VERDICT: {report['verdict']['status']}",
        ]
    )
    for reason in report["verdict"]["reasons"]:
        lines.append(f"  - {reason}")
    lines.extend(
        [
            report["verdict"]["decision_rule"],
            f"Deterministic result SHA-256: {report['deterministic_result_sha256']}",
            "No synthetic market data or production write was used.",
            "=" * 88,
        ]
    )
    return "\n".join(lines)


def _probability(value: str) -> float:
    parsed = float(value)
    if not 0.5 < parsed < 1.0:
        raise argparse.ArgumentTypeError("outlier quantile must be between 0.5 and 1")
    return parsed


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Replay real DeltaEngine journal sessions as causal directional-pressure "
            "episodes. This program is validation-only and read-only."
        )
    )
    parser.add_argument(
        "--session",
        action="append",
        default=[],
        help="explicit valid full capture session; repeatable (default: all valid full sessions)",
    )
    parser.add_argument(
        "--outlier-quantile",
        type=_probability,
        default=0.99,
        help="train-only research assumption for distribution outliers (default: 0.99)",
    )
    parser.add_argument(
        "--sample-step-ms",
        type=_positive_int,
        default=100,
        help="fixed-grid interval for the train distribution (default: 100)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit full deterministic JSON including raw episode evidence vectors",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        parameters = _load_parameters(args.outlier_quantile, args.sample_step_ms)
        session_paths, excluded = _discover_valid_sessions(args.session)
        report = _run_validation(session_paths, excluded, parameters)
    except (ValidationError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"VALIDATION ERROR: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print(_render_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
