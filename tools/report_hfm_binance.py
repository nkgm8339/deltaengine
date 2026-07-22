"""Create a JSON and console report from a Binance/HFM observation CSV."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.latency_observer import build_report, load_quotes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, nargs="?", default=Path("data/latency/quotes.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/latency/report.json"))
    parser.add_argument("--move-bps", type=float, default=1.0)
    parser.add_argument("--match-window-ms", type=int, default=5_000)
    parser.add_argument("--max-staleness-ms", type=int, default=1_000)
    parser.add_argument(
        "--entry-delay-ms",
        type=int,
        default=1_000,
        help="Delay from a Binance move event to the hypothetical HFM entry",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        load_quotes(args.input),
        move_threshold_bps=args.move_bps,
        match_window_ms=args.match_window_ms,
        max_staleness_ms=args.max_staleness_ms,
        entry_delay_ms=args.entry_delay_ms,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Saved: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
