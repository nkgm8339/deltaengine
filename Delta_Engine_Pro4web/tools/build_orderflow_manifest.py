"""Build a read-only manifest for order-flow research inputs."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

import pyarrow.parquet as pq


@dataclass(frozen=True)
class TradePoint:
    event_time: datetime
    trade_id: str
    price: float
    quantity: float
    side: str


def _files(folder: Path) -> list[Path]:
    return sorted(path for path in folder.rglob("*.parquet") if path.is_file())


def _trade_rows(folder: Path) -> Iterable[dict[str, Any]]:
    for path in _files(folder):
        try:
            table = pq.ParquetFile(path).read(
                columns=["event_time", "trade_id", "price", "quantity", "side"]
            )
        except (OSError, ValueError, KeyError):
            continue
        for row in table.to_pylist():
            if row.get("trade_id") is not None:
                yield row


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    raise ValueError("event_time must be a datetime")


def inspect_trades(folder: Path) -> dict[str, Any]:
    count = 0
    unique_ids: set[str] = set()
    duplicate_ids = 0
    invalid_nonpositive = 0
    invalid_side = 0
    minutes: set[datetime] = set()
    first: datetime | None = None
    last: datetime | None = None
    for row in _trade_rows(folder):
        count += 1
        trade_id = str(row["trade_id"])
        if trade_id in unique_ids:
            duplicate_ids += 1
        unique_ids.add(trade_id)
        price = float(row["price"])
        quantity = float(row["quantity"])
        if price <= 0 or quantity <= 0:
            invalid_nonpositive += 1
        if row.get("side") not in ("BUY", "SELL"):
            invalid_side += 1
        event_time = _as_datetime(row["event_time"])
        minute = event_time.replace(second=0, microsecond=0)
        minutes.add(minute)
        first = event_time if first is None else min(first, event_time)
        last = event_time if last is None else max(last, event_time)
    ordered = sorted(minutes)
    gaps = [
        int((right - left).total_seconds())
        for left, right in zip(ordered, ordered[1:])
        if right - left > timedelta(minutes=1)
    ]
    return {
        "files": len(_files(folder)),
        "trade_rows": count,
        "unique_trade_ids": len(unique_ids),
        "duplicate_trade_ids": duplicate_ids,
        "invalid_nonpositive": invalid_nonpositive,
        "invalid_side": invalid_side,
        "first_event_time": first.isoformat() if first is not None else None,
        "last_event_time": last.isoformat() if last is not None else None,
        "minutes_with_trades": len(ordered),
        "gap_count_over_1m": len(gaps),
        "gap_count_over_10m": sum(gap > 600 for gap in gaps),
        "max_gap_seconds": max(gaps, default=0),
        "gaps_seconds": gaps,
    }


def build_manifest(project: Path) -> dict[str, Any]:
    parquet = project / "data_05M" / "parquet"
    raw_folder = parquet / "symbol=BTCUSDT" / "year=2026"
    return {
        "schema_version": 1,
        "generated_at": datetime.now().astimezone().isoformat(),
        "read_only": True,
        "project": str(project),
        "inputs": {
            "raw_trade_root": str(raw_folder),
            "flow_response_events": str(parquet / "flow_response_events"),
            "flow_response_outcomes": str(parquet / "flow_response_outcomes"),
            "native_flow_events": str(parquet / "native_flow_events"),
            "native_flow_outcomes": str(parquet / "native_flow_outcomes"),
            "hfm_context_outcomes": str(parquet / "hfm_context_outcomes"),
        },
        "raw_trades": inspect_trades(raw_folder),
        "research_constraints": {
            "episode_must_not_cross_data_gap": True,
            "missing_values_are_not_interpolated": True,
            "existing_1m_logic_is_unchanged": True,
            "orders_sent": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = build_manifest(args.project.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
