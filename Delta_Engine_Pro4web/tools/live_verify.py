"""aggTrade + depth ライブ検証スクリプト（課題 #2）。

Usage:
    python -m tools.live_verify --duration 60

ネットワーク接続が必要。pytest には含めない。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Ensure project root is on path when run as python -m tools.live_verify
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import logging

from src.config import load_config
from src.pipeline import LivePipeline, load_profile


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    # Suppress noisy libraries.
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


async def _run(duration: int) -> None:
    config = load_config(PROJECT_ROOT / "config" / "config.yaml")
    profile = load_profile(PROJECT_ROOT / "config" / "profiles" / "binance.yaml")

    pipeline = LivePipeline.from_config(config, profile)

    print(f"[live_verify] Starting — symbol={config.market.symbol} "
          f"duration={duration}s", flush=True)

    stats = await pipeline.run_async(duration_sec=float(duration))

    print("\n=== LiveStats ===")
    print(f"  raw_out                          : {stats.raw_out}")
    print(f"  forwarded                        : {stats.forwarded}")
    print(f"  filtered                         : {stats.filtered}")
    print(f"  normalized                       : {stats.normalized}")
    print(f"  duplicates                       : {stats.duplicates}")
    print(f"  reordered                        : {stats.reordered}")
    print(f"  normalizer_rejected              : {stats.normalizer_rejected}")
    print(f"  trades_stored                    : {stats.trades_stored}")
    print(f"  candles_stored                   : {stats.candles_stored}")
    print(f"  signals_stored                   : {stats.signals_stored}")
    print(f"  final_cvd                        : {stats.final_cvd}")
    print(f"  reconnects                       : {stats.reconnects}")
    print(f"  recorded                         : {stats.recorded}")

    print("\n=== OrderBook Stats ===")
    print(f"  book_snapshots_applied           : {stats.book_snapshots_applied}")
    print(f"  book_diffs_applied               : {stats.book_diffs_applied}")
    print(f"  book_diffs_rejected_before_snap  : {stats.book_diffs_rejected_before_snapshot}")
    print(f"  book_gaps_detected               : {stats.book_gaps_detected}")
    print(f"  book_diffs_stale                 : {stats.book_diffs_stale}")
    print(f"  depth_processed                  : {stats.depth_processed}")
    print(f"  depth_rejected                   : {stats.depth_rejected}")

    print("\n=== Absorption Stats ===")
    print(f"  absorption_events_detected       : {stats.absorption_events_detected}")

    print("\n=== Liquidation Stats ===")
    print(f"  liquidations_received            : {stats.liquidations_received}")

    print("\n=== Storage Paths ===")
    parquet_path = Path(config.database.parquet_path)
    duckdb_path = Path(config.database.duckdb_path)
    for label, p in [("Parquet dir", parquet_path), ("DuckDB file", duckdb_path)]:
        if p.exists():
            size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.is_dir() else p.stat().st_size
            print(f"  {label}: {p} ({size / 1024:.1f} KB)")
        else:
            print(f"  {label}: {p} (not found)")


def main() -> None:
    parser = argparse.ArgumentParser(description="aggTrade + depth ライブ検証")
    parser.add_argument(
        "--duration", type=int, default=60,
        help="capture duration in seconds (default: 60)",
    )
    parser.add_argument("--debug", action="store_true", help="enable DEBUG logging")
    args = parser.parse_args()
    if args.debug:
        _setup_logging()
    asyncio.run(_run(args.duration))


if __name__ == "__main__":
    main()
