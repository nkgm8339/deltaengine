"""CVD slope reference calibration (Task-B).

Computes the 80th percentile of |Candle.delta| over the most recent N days of
confirmed candles and reports it as the CVD slope reference used by
``score_cvd`` (SignalEngine). With ``--write`` the value is persisted to
``signal.cvd_slope_ref`` in the config file so the CVD module leaves the
"UNREF" state.

Decimal-only: all volume/delta arithmetic uses Decimal (no float), matching the
storage schema DECIMAL(20,8) and the project's no-float rule. The percentile is
the nearest-rank value (an actual observed |delta|), so no interpolation — and
thus no float — is required.

Source: DuckDB candles table (the canonical analytical mirror). The recency
window is anchored on the latest bar_time present in the data (not wall-clock),
so calibration is deterministic against a fixed snapshot.

Usage:
    python tools/calibrate_cvd.py                 # report only, 7-day window
    python tools/calibrate_cvd.py --days 3        # report only, 3-day window
    python tools/calibrate_cvd.py --write         # persist to config.yaml
"""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

# Make the project root importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import duckdb  # noqa: E402

from src.config import load_config  # noqa: E402

PERCENTILE = Decimal("80")           # 80th percentile (Task-B spec)
_DEFAULT_CONFIG = "config/config.yaml"


def _nearest_rank_percentile(values: list[Decimal], percentile: Decimal) -> Decimal:
    """Nearest-rank percentile of a non-empty list (Decimal-only, no interpolation)."""
    ordered = sorted(values)
    n = len(ordered)
    rank = (percentile / Decimal(100) * Decimal(n)).to_integral_value(rounding=ROUND_CEILING)
    idx = max(1, min(int(rank), n))
    return ordered[idx - 1]


def compute_slope_ref(
    db_path: str, symbol: str, timeframe: str, days: int
) -> tuple[Decimal | None, int, str | None]:
    """Return (slope_ref, sample_count, window_start_iso).

    slope_ref is None when there are no candles in the window.
    """
    con = duckdb.connect(db_path, read_only=True)
    try:
        latest = con.execute(
            "SELECT max(bar_time) FROM candles WHERE symbol = ? AND timeframe = ?",
            [symbol, timeframe],
        ).fetchone()[0]
        if latest is None:
            return None, 0, None
        window_start = latest - timedelta(days=days)
        rows = con.execute(
            "SELECT delta FROM candles "
            "WHERE symbol = ? AND timeframe = ? AND bar_time >= ? AND delta IS NOT NULL",
            [symbol, timeframe, window_start],
        ).fetchall()
    finally:
        con.close()

    # duckdb returns DECIMAL columns as Python Decimal — keep them Decimal.
    abs_deltas = [abs(Decimal(str(r[0]))) for r in rows]
    if not abs_deltas:
        return None, 0, window_start.isoformat()
    return _nearest_rank_percentile(abs_deltas, PERCENTILE), len(abs_deltas), window_start.isoformat()


def _write_signal_cvd_slope_ref(config_path: Path, value: Decimal) -> None:
    """Replace signal.cvd_slope_ref in the YAML file, section-aware, comments preserved.

    Only the cvd_slope_ref key inside the top-level ``signal:`` block is touched;
    the identically-named key under ``calibration:`` is left untouched.
    """
    lines = config_path.read_text(encoding="utf-8").splitlines(keepends=True)
    in_signal = False
    replaced = False
    literal = format(value.normalize(), "f")  # plain decimal string, no exponent
    for i, line in enumerate(lines):
        stripped = line.rstrip("\n")
        # A non-indented, non-blank, non-comment line starts a new top-level section.
        if stripped and not stripped[0].isspace() and not stripped.lstrip().startswith("#"):
            in_signal = stripped.split(":", 1)[0] == "signal"
            continue
        if in_signal and line.lstrip().startswith("cvd_slope_ref:"):
            indent = line[: len(line) - len(line.lstrip())]
            lines[i] = f"{indent}cvd_slope_ref: {literal}\n"
            replaced = True
            break
    if not replaced:
        raise RuntimeError("signal.cvd_slope_ref key not found in config")
    config_path.write_text("".join(lines), encoding="utf-8")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Calibrate CVD slope reference.")
    parser.add_argument("--days", type=int, default=7, help="recency window in days (default 7)")
    parser.add_argument("--config", default=_DEFAULT_CONFIG, help="config file path")
    parser.add_argument("--db", default=None, help="override DuckDB path (default: config)")
    parser.add_argument("--write", action="store_true", help="persist to signal.cvd_slope_ref")
    args = parser.parse_args(argv[1:])

    if args.days < 1:
        print("--days must be >= 1", file=sys.stderr)
        return 2

    config = load_config(args.config)
    db_path = args.db or config.database.duckdb_path
    symbol = config.market.symbol
    timeframe = config.market.bar_timeframe

    slope_ref, count, window_start = compute_slope_ref(db_path, symbol, timeframe, args.days)
    if slope_ref is None:
        print(
            f"No candles for {symbol}/{timeframe} in the last {args.days} day(s) "
            f"(db={db_path}); nothing to calibrate.",
            file=sys.stderr,
        )
        return 1

    print(
        f"CVD slope ref (P{int(PERCENTILE)} of |delta|): {format(slope_ref.normalize(), 'f')}\n"
        f"  symbol={symbol} timeframe={timeframe} samples={count} "
        f"window_start={window_start} days={args.days}"
    )

    if args.write:
        _write_signal_cvd_slope_ref(Path(args.config), slope_ref)
        print(f"Wrote signal.cvd_slope_ref = {format(slope_ref.normalize(), 'f')} to {args.config}")
    else:
        print("(dry run — re-run with --write to persist)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
