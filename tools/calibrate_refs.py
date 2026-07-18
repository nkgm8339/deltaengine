"""stack_ref / imbalance.min_volume 較正 (優先度3).

DuckDB の trades テーブルから確定バーの Footprint を決定的に再構成し、

  1. imbalance.min_volume — レベル総出来高 (buy+sell) 分布の P25 (nearest-rank)。
     「薄い片側レベル」を弾く床値。分布の下位 1/4 を薄いとみなす。
  2. signal.stack_ref    — 実運用と同一の ImbalanceDetector (対角比較・
     stack_count=2) で検出した stacked run 長の P80 (nearest-rank)。
     score_imb = clamp(net / stack_ref, ...) の基準値。

を推奨する。calibrate_cvd.py と同じ規律:
  - Decimal 専用 (float 不使用)。percentile は nearest-rank (補間なし)。
  - 窓は最新 bar_time 起点 (壁時計に依存しない → 固定スナップショットで決定的)。
  - 既定はドライラン。--write で config.yaml に書き込む (コメント保持・節単位置換)。

順序に注意: min_volume を先に確定し、その値で stack_ref を測る
(min_volume が変わると qualify するレベルが変わるため)。本ツールは
1 回の実行で「推奨 min_volume を使って stack_ref を測る」一貫計算を行う。

Usage:
    python tools/calibrate_refs.py                # report only, 7-day window
    python tools/calibrate_refs.py --days 3
    python tools/calibrate_refs.py --write        # persist both to config.yaml
"""
from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import duckdb  # noqa: E402

from src.config import load_config  # noqa: E402
from src.orderflow.footprint import FootprintBar, PriceLevel  # noqa: E402
from src.orderflow.imbalance import ImbalanceDetector  # noqa: E402

MIN_VOLUME_PERCENTILE = Decimal("25")   # 分布下位 1/4 を薄いレベルとみなす床
STACK_REF_PERCENTILE = Decimal("80")    # calibrate_cvd (P80) と同一の分位
_DEFAULT_CONFIG = "config/config.yaml"


def _nearest_rank_percentile(values: list, percentile: Decimal):
    ordered = sorted(values)
    n = len(ordered)
    rank = (percentile / Decimal(100) * Decimal(n)).to_integral_value(rounding=ROUND_CEILING)
    idx = max(1, min(int(rank), n))
    return ordered[idx - 1]


def load_bars(
    db_path: str, symbol: str, timeframe_sec: int, days: int, timeframe: str = "1m"
) -> tuple[list[FootprintBar], str | None]:
    """trades テーブルからバーごとの価格レベル集計 (昇順) を再構成する。

    SQL は epoch 秒の整数除算でバー境界を決める (UTC clock 整列 — CVD と同一規則)。
    """
    con = duckdb.connect(db_path, read_only=True)
    try:
        latest = con.execute(
            "SELECT max(event_time) FROM trades WHERE symbol = ?", [symbol]
        ).fetchone()[0]
        if latest is None:
            return [], None
        window_start = latest - timedelta(days=days)
        rows = con.execute(
            """
            SELECT
              (epoch(event_time)::BIGINT // ?) * ? AS bar_epoch,
              price,
              sum(CASE WHEN side = 'BUY'  THEN quantity ELSE 0 END) AS buy_volume,
              sum(CASE WHEN side = 'SELL' THEN quantity ELSE 0 END) AS sell_volume
            FROM trades
            WHERE symbol = ? AND event_time >= ?
            GROUP BY 1, 2
            ORDER BY 1, 2
            """,
            [timeframe_sec, timeframe_sec, symbol, window_start],
        ).fetchall()
    finally:
        con.close()

    from datetime import datetime, timezone

    bars: list[FootprintBar] = []
    current_time = None
    levels: list[PriceLevel] = []
    for bar_epoch, price, buy_v, sell_v in rows:
        bar_time = datetime.fromtimestamp(int(bar_epoch), tz=timezone.utc)
        if bar_time != current_time:
            if levels:
                bars.append(FootprintBar(bar_time=current_time, symbol=symbol,
                                         timeframe=timeframe, levels=tuple(levels)))
            current_time = bar_time
            levels = []
        levels.append(
            PriceLevel(
                price=Decimal(str(price)),
                buy_volume=Decimal(str(buy_v)),
                sell_volume=Decimal(str(sell_v)),
            )
        )
    if levels:
        bars.append(FootprintBar(bar_time=current_time, symbol=symbol,
                                 timeframe=timeframe, levels=tuple(levels)))
    return bars, window_start.isoformat()


def recommend_min_volume(bars: list[FootprintBar]) -> tuple[Decimal | None, int]:
    """全レベルの combined 出来高分布から P25 を床値として推奨する。"""
    combined = [
        lv.buy_volume + lv.sell_volume
        for bar in bars
        for lv in bar.levels
        if (lv.buy_volume + lv.sell_volume) > 0
    ]
    if not combined:
        return None, 0
    return _nearest_rank_percentile(combined, MIN_VOLUME_PERCENTILE), len(combined)


def recommend_stack_ref(
    bars: list[FootprintBar],
    min_volume: Decimal,
    ratio_threshold: Decimal,
    ratio_cap: Decimal,
) -> tuple[int | None, int]:
    """実運用と同一の ImbalanceDetector で stacked run 長の P80 を推奨する。

    stack_count=2 で「2 連以上の run」を全て観測対象にする (実運用の
    stack_count は表示/検出用で、ここでは分布そのものが欲しいため)。
    """
    detector = ImbalanceDetector(
        ratio_threshold=ratio_threshold,
        min_volume=min_volume,
        ratio_cap=ratio_cap,
        stack_count=2,
    )
    counts: list[int] = []
    for bar in bars:
        result = detector.detect(bar)
        for stacked in result.stacked_imbalances:
            counts.append(stacked.count)
    if not counts:
        return None, 0
    ref = _nearest_rank_percentile([Decimal(c) for c in counts], STACK_REF_PERCENTILE)
    return int(ref), len(counts)


def _write_yaml_key(config_path: Path, section: str, key: str, literal: str) -> None:
    """calibrate_cvd と同じ節単位置換 (コメント保持)。"""
    lines = config_path.read_text(encoding="utf-8").splitlines(keepends=True)
    in_section = False
    replaced = False
    for i, line in enumerate(lines):
        stripped = line.rstrip("\r\n")
        if stripped and not stripped[0].isspace() and not stripped.lstrip().startswith("#"):
            in_section = stripped.split(":", 1)[0] == section
            continue
        if in_section and line.lstrip().startswith(f"{key}:"):
            indent = line[: len(line) - len(line.lstrip())]
            eol = "\r\n" if line.endswith("\r\n") else "\n"
            lines[i] = f"{indent}{key}: {literal}{eol}"
            replaced = True
            break
    if not replaced:
        raise RuntimeError(f"{section}.{key} key not found in config")
    config_path.write_text("".join(lines), encoding="utf-8")


def _tf_seconds(tf: str) -> int:
    table = {"1s": 1, "1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
    if tf not in table:
        raise ValueError(f"unsupported timeframe: {tf}")
    return table[tf]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Calibrate stack_ref / imbalance.min_volume.")
    parser.add_argument("--days", type=int, default=7, help="recency window in days (default 7)")
    parser.add_argument("--config", default=_DEFAULT_CONFIG, help="config file path")
    parser.add_argument("--db", default=None, help="override DuckDB path (default: config)")
    parser.add_argument("--write", action="store_true",
                        help="persist to imbalance.min_volume and signal.stack_ref")
    args = parser.parse_args(argv[1:])

    if args.days < 1:
        print("--days must be >= 1", file=sys.stderr)
        return 2

    config = load_config(args.config)
    db_path = args.db or config.database.duckdb_path
    symbol = config.market.symbol
    timeframe = config.market.bar_timeframe

    bars, window_start = load_bars(db_path, symbol, _tf_seconds(timeframe), args.days, timeframe)
    if not bars:
        print(
            f"No trades for {symbol} in the last {args.days} day(s) (db={db_path}); "
            f"nothing to calibrate.",
            file=sys.stderr,
        )
        return 1

    min_vol, level_samples = recommend_min_volume(bars)
    if min_vol is None:
        print("No non-empty price levels found; nothing to calibrate.", file=sys.stderr)
        return 1

    stack_ref, stack_samples = recommend_stack_ref(
        bars, min_vol,
        Decimal(str(config.imbalance.ratio_threshold)),
        Decimal(str(config.imbalance.ratio_cap)),
    )

    min_vol_literal = format(min_vol.normalize(), "f")
    print(
        f"imbalance.min_volume (P{int(MIN_VOLUME_PERCENTILE)} of level combined volume): "
        f"{min_vol_literal}\n"
        f"  bars={len(bars)} level_samples={level_samples} window_start={window_start} "
        f"days={args.days}"
    )
    if stack_ref is None:
        print(
            "signal.stack_ref: 推奨値なし (窓内に stacked imbalance が検出されず)。"
            "現行値を維持してください。"
        )
    else:
        print(
            f"signal.stack_ref (P{int(STACK_REF_PERCENTILE)} of stacked run length): "
            f"{stack_ref}\n"
            f"  stacked_samples={stack_samples}"
        )

    if args.write:
        _write_yaml_key(Path(args.config), "imbalance", "min_volume", min_vol_literal)
        print(f"Wrote imbalance.min_volume = {min_vol_literal} to {args.config}")
        if stack_ref is not None:
            _write_yaml_key(Path(args.config), "signal", "stack_ref", str(stack_ref))
            print(f"Wrote signal.stack_ref = {stack_ref} to {args.config}")
    else:
        print("(dry run — re-run with --write to persist)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
