"""Phase6 live capture CLI — run the CVD path against a real Binance WebSocket.

Loads the validated configuration and the active exchange profile, connects to
the live Binance Futures aggTrade stream, and runs the same CVD path used by
ReplayPipeline (M6): normalize -> CVD -> Parquet/DuckDB. Optionally records the
forwarded market stream as JSON Lines so the session can be replayed
deterministically (M6 replay source). Recorded sessions also include REST
depth snapshots, which are required to reconstruct exact best bid/ask from
incremental depth updates.

Usage (from the project root):
    python -m tools.live_capture --duration 30 --record data/recordings/btcusdt.jsonl
    python -m tools.live_capture --max-trades 500

Stops on --duration seconds, --max-trades events, or Ctrl-C; on stop it flushes
all buffered events and the final open bar, then prints a LiveStats summary.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from src.config import load_config
from src.pipeline import LivePipeline, load_profile


def _profile_path(config, config_dir: Path) -> Path:
    return config_dir / "profiles" / f"{config.normalizer.exchange_profile}.yaml"


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase6 Binance live CVD capture")
    parser.add_argument("--config", default="config/config.yaml", help="config YAML path")
    parser.add_argument("--duration", type=float, default=None, help="stop after N seconds")
    parser.add_argument("--max-trades", type=int, default=None, help="stop after N aggTrade events")
    parser.add_argument(
        "--record",
        default=None,
        help="JSON Lines path for trades, depth updates, and REST depth snapshots",
    )
    args = parser.parse_args()

    if args.duration is None and args.max_trades is None:
        parser.error("specify at least one stop condition: --duration and/or --max-trades")

    config_path = Path(args.config)
    config = load_config(config_path)
    logging.basicConfig(
        level=getattr(logging, config.system.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    profile = load_profile(_profile_path(config, config_path.parent))
    pipeline = LivePipeline.from_config(config, profile)

    print(
        f"[live] connecting {pipeline.ws_url} streams={pipeline.subscribe_streams} "
        f"symbol={pipeline.symbol} timeframe={pipeline.timeframe}"
    )
    stats = pipeline.run(
        duration_sec=args.duration,
        max_trades=args.max_trades,
        record_path=args.record,
    )

    print("[live] session complete:")
    print(f"  raw messages off socket : {stats.raw_out}")
    print(f"  aggTrade forwarded       : {stats.forwarded}")
    print(f"  non-trade frames filtered: {stats.filtered}")
    print(f"  normalized               : {stats.normalized}")
    print(f"  duplicates / reordered   : {stats.duplicates} / {stats.reordered}")
    print(f"  normalizer rejected      : {stats.normalizer_rejected}")
    print(f"  trades stored            : {stats.trades_stored}")
    print(f"  candles stored           : {stats.candles_stored}")
    print(f"  final CVD                : {stats.final_cvd}")
    print(f"  reconnects               : {stats.reconnects}")
    if args.record:
        print(f"  recorded ({stats.recorded} events) -> {args.record}")


if __name__ == "__main__":
    main()
