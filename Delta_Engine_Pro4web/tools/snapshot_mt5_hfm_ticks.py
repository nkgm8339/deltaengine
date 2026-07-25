"""Snapshot real HFM MT5 ticks with an audited server-clock normalization.

The command is read-only with respect to MT5. It never imports an order helper
or calls an order function. Output is a reproducible Parquet research snapshot
containing Bid, Ask, zero-spread mid, raw server time, and normalized UTC time.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq


UTC = timezone.utc


@dataclass(frozen=True)
class ClockCalibration:
    offset_sec: int
    anchor_count: int
    anchor_matching_count: int
    anchor_residual_ms_min: float
    anchor_residual_ms_median: float
    anchor_residual_ms_max: float
    live_sample_count: int
    live_residual_ms_min: float
    live_residual_ms_median: float
    live_residual_ms_max: float

    def to_row(self) -> dict[str, object]:
        return dict(self.__dict__)


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return parsed.astimezone(UTC)


def calibrate_clock(
    anchor_offset_sec: Iterable[float],
    live_offset_ms: Iterable[float],
    *,
    minimum_anchor_count: int = 20,
    maximum_residual_ms: float = 5_000.0,
) -> ClockCalibration:
    """Require historical local/source pairs and live measurement to agree."""

    anchors = list(anchor_offset_sec)
    live = list(live_offset_ms)
    if len(anchors) < minimum_anchor_count:
        raise ValueError("not enough local/source anchor pairs")
    if not live:
        raise ValueError("live MT5 clock samples are required")
    rounded_anchor = [int(round(value / 3_600.0) * 3_600) for value in anchors]
    offset_sec, matching_count = Counter(rounded_anchor).most_common(1)[0]
    if matching_count != len(anchors):
        raise ValueError("historical HFM clock offset is not stable")
    anchor_residual_ms = [(value - offset_sec) * 1_000.0 for value in anchors]

    rounded_live = [int(round(value / 3_600_000.0) * 3_600) for value in live]
    if any(value != offset_sec for value in rounded_live):
        raise ValueError("live HFM clock offset disagrees with historical anchors")
    live_residual_ms = [value - offset_sec * 1_000.0 for value in live]
    if max(abs(value) for value in (*anchor_residual_ms, *live_residual_ms)) > maximum_residual_ms:
        raise ValueError("HFM clock residual exceeds the safety limit")
    return ClockCalibration(
        offset_sec=offset_sec,
        anchor_count=len(anchors),
        anchor_matching_count=matching_count,
        anchor_residual_ms_min=min(anchor_residual_ms),
        anchor_residual_ms_median=statistics.median(anchor_residual_ms),
        anchor_residual_ms_max=max(anchor_residual_ms),
        live_sample_count=len(live),
        live_residual_ms_min=min(live_residual_ms),
        live_residual_ms_median=statistics.median(live_residual_ms),
        live_residual_ms_max=max(live_residual_ms),
    )


def load_anchor_offsets(context_root: Path) -> list[float]:
    dataset = ds.dataset(context_root, format="parquet", partitioning="hive")
    table = dataset.to_table(
        columns=[
            "hfm_entry_status",
            "hfm_entry_time",
            "hfm_entry_source_time",
        ]
    )
    result: list[float] = []
    for row in table.to_pylist():
        local_time = row["hfm_entry_time"]
        source_time = row["hfm_entry_source_time"]
        if (
            row["hfm_entry_status"] == "LIVE"
            and local_time is not None
            and source_time is not None
        ):
            result.append((source_time - local_time).total_seconds())
    return result


def sample_live_offsets(
    mt5: object,
    symbol: str,
    *,
    sample_count: int = 20,
    sample_interval_sec: float = 0.05,
) -> list[float]:
    result: list[float] = []
    for _ in range(sample_count):
        tick = mt5.symbol_info_tick(symbol)
        received_ms = time.time_ns() / 1_000_000.0
        if tick is not None and int(tick.time_msc) > 0:
            result.append(float(tick.time_msc) - received_ms)
        time.sleep(sample_interval_sec)
    return result


def _fetch_ticks(
    mt5: object,
    symbol: str,
    *,
    local_start: datetime,
    local_end: datetime,
    offset_sec: int,
    chunk_hours: int,
) -> tuple[list[dict[str, object]], dict[str, int]]:
    seen: set[tuple[int, float, float]] = set()
    rows: list[dict[str, object]] = []
    audit = {
        "chunks": 0,
        "ticks_returned": 0,
        "duplicates_excluded": 0,
        "invalid_quotes_excluded": 0,
        "outside_range_excluded": 0,
    }
    cursor = local_start
    while cursor < local_end:
        chunk_end = min(local_end, cursor + timedelta(hours=chunk_hours))
        source_start = cursor + timedelta(seconds=offset_sec)
        source_end = chunk_end + timedelta(seconds=offset_sec)
        ticks = mt5.copy_ticks_range(
            symbol,
            source_start,
            source_end,
            mt5.COPY_TICKS_ALL,
        )
        audit["chunks"] += 1
        if ticks is None:
            raise RuntimeError(f"MT5 copy_ticks_range failed: {mt5.last_error()}")
        audit["ticks_returned"] += len(ticks)
        for tick in ticks:
            time_msc = int(tick["time_msc"])
            bid = float(tick["bid"])
            ask = float(tick["ask"])
            if not (
                math.isfinite(bid)
                and math.isfinite(ask)
                and bid > 0
                and ask >= bid
            ):
                audit["invalid_quotes_excluded"] += 1
                continue
            event_time = datetime.fromtimestamp(
                time_msc / 1_000.0 - offset_sec,
                tz=UTC,
            )
            if not (local_start <= event_time <= local_end):
                audit["outside_range_excluded"] += 1
                continue
            key = (time_msc, bid, ask)
            if key in seen:
                audit["duplicates_excluded"] += 1
                continue
            seen.add(key)
            rows.append(
                {
                    "event_time": event_time,
                    "source_time": datetime.fromtimestamp(time_msc / 1_000.0, tz=UTC),
                    "source_time_msc": time_msc,
                    "symbol": symbol,
                    "bid": bid,
                    "ask": ask,
                    "mid": (bid + ask) / 2.0,
                    "spread": ask - bid,
                    "flags": int(tick["flags"]),
                    "volume_real": float(tick["volume_real"]),
                }
            )
        cursor = chunk_end
    rows.sort(key=lambda row: (row["event_time"], row["source_time_msc"]))
    audit["rows_included"] = len(rows)
    return rows, audit


def _table(rows: list[dict[str, object]]) -> pa.Table:
    schema = pa.schema(
        [
            ("event_time", pa.timestamp("us", tz="UTC")),
            ("source_time", pa.timestamp("us", tz="UTC")),
            ("source_time_msc", pa.int64()),
            ("symbol", pa.string()),
            ("bid", pa.float64()),
            ("ask", pa.float64()),
            ("mid", pa.float64()),
            ("spread", pa.float64()),
            ("flags", pa.int64()),
            ("volume_real", pa.float64()),
        ]
    )
    return pa.Table.from_pylist(rows, schema=schema)


def _args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, help="normalized UTC start")
    parser.add_argument("--end", required=True, help="normalized UTC end")
    parser.add_argument("--symbol", default="#BTCUSDr")
    parser.add_argument(
        "--terminal-path",
        type=Path,
        default=Path(r"C:\Program Files\HFM Metatrader 5\terminal64.exe"),
    )
    parser.add_argument(
        "--context-root",
        type=Path,
        default=Path("data_05M/parquet/combined_context_events"),
    )
    parser.add_argument("--chunk-hours", type=int, default=3)
    parser.add_argument("--live-samples", type=int, default=20)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data_05M/research/hfm_mt5_ticks_20260725.parquet"),
    )
    parser.add_argument(
        "--metadata-output",
        type=Path,
        default=Path("data_05M/research/hfm_mt5_ticks_20260725.metadata.json"),
    )
    args = parser.parse_args(argv)
    if args.chunk_hours < 1 or args.live_samples < 1:
        parser.error("chunk-hours and live-samples must be positive")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    local_start = parse_utc(args.start)
    local_end = parse_utc(args.end)
    if local_end <= local_start:
        raise ValueError("end must be after start")

    import MetaTrader5 as mt5

    if not mt5.initialize(path=str(args.terminal_path)):
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
    try:
        terminal = mt5.terminal_info()
        account = mt5.account_info()
        if terminal is None or not terminal.connected:
            raise RuntimeError("MT5 terminal is not connected")
        anchor_offsets = load_anchor_offsets(args.context_root)
        live_offsets = sample_live_offsets(
            mt5,
            args.symbol,
            sample_count=args.live_samples,
        )
        calibration = calibrate_clock(anchor_offsets, live_offsets)
        rows, audit = _fetch_ticks(
            mt5,
            args.symbol,
            local_start=local_start,
            local_end=local_end,
            offset_sec=calibration.offset_sec,
            chunk_hours=args.chunk_hours,
        )
        if not rows:
            raise RuntimeError("MT5 returned no valid HFM ticks")
        metadata = {
            "generated_at": datetime.now(UTC).isoformat(),
            "observation_only": True,
            "orders_sent": False,
            "terminal_connected": True,
            "account_server": account.server if account is not None else None,
            "symbol": args.symbol,
            "normalized_start": local_start.isoformat(),
            "normalized_end": local_end.isoformat(),
            "clock_basis": "PAIRED_LOCAL_SOURCE_ANCHORS_AND_LIVE_MEASUREMENT",
            "calibration": calibration.to_row(),
            "audit": audit,
            "first_event_time": rows[0]["event_time"].isoformat(),
            "last_event_time": rows[-1]["event_time"].isoformat(),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.metadata_output.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(_table(rows), args.output, compression="zstd")
        args.metadata_output.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "ticks": len(rows),
                    "offset_sec": calibration.offset_sec,
                    "output": str(args.output),
                    "metadata": str(args.metadata_output),
                    "orders_sent": False,
                },
                ensure_ascii=False,
            )
        )
        return 0
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())

