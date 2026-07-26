"""Reproducible synthetic hot-path benchmark for Stage 2B DOM detectors."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.orderflow.hooks.dom_features import DomFeatureCache
from src.orderflow.hooks.dom_liquidity import DomLiquidityDetector
from src.orderflow.hooks.dom_quote_motion import DomQuoteMotionDetector
from src.orderflow.hooks.dom_wall import DomWallDetector
from src.orderflow.orderbook import OrderBookSnapshot


def _snapshot(index: int, levels: int) -> OrderBookSnapshot:
    mid = Decimal("100000") + Decimal(index % 17) / Decimal(10)
    bids = {
        mid - Decimal(level + 1) / Decimal(10):
        Decimal((level % 7) + 1) + Decimal(index % 5) / Decimal(10)
        for level in range(levels)
    }
    asks = {
        mid + Decimal(level + 1) / Decimal(10):
        Decimal(((level + 3) % 7) + 1) + Decimal(index % 3) / Decimal(10)
        for level in range(levels)
    }
    return OrderBookSnapshot(
        symbol="BTCUSDT",
        last_update_id=index + 1,
        bids=bids,
        asks=asks,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", type=int, default=10_000)
    parser.add_argument("--levels", type=int, default=50)
    args = parser.parse_args()
    if args.frames < 100 or args.levels < 2:
        parser.error("frames must be >= 100 and levels must be >= 2")

    snapshots = [_snapshot(index, args.levels) for index in range(args.frames)]
    cache = DomFeatureCache(depth_levels=args.levels)
    detectors = (
        DomWallDetector(),
        DomLiquidityDetector(),
        DomQuoteMotionDetector(),
    )
    base = datetime(2026, 7, 26, tzinfo=timezone.utc)
    elapsed_ns: list[int] = []
    candidates = 0
    for index, snapshot in enumerate(snapshots):
        when = base + timedelta(milliseconds=index * 100)
        started = time.perf_counter_ns()
        delta = cache.process(
            snapshot,
            source_time=when,
            received_time=when,
        )
        if delta is not None:
            for detector in detectors:
                candidates += len(detector.process(delta))
        elapsed_ns.append(time.perf_counter_ns() - started)

    ordered = sorted(value / 1_000_000 for value in elapsed_ns)
    p99_index = min(len(ordered) - 1, int(len(ordered) * 0.99))
    report = {
        "schema_version": 1,
        "frames": args.frames,
        "levels_per_side": args.levels,
        "candidates": candidates,
        "mean_ms": sum(ordered) / len(ordered),
        "p99_ms": ordered[p99_index],
        "max_ms": ordered[-1],
        "gate": {"p99_lt_ms": 10, "max_lt_ms": 25},
        "passed": ordered[p99_index] < 10 and ordered[-1] < 25,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
