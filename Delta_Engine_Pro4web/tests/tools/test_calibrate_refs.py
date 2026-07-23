"""tools/calibrate_refs.py — stack_ref / min_volume 較正ロジックのテスト."""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import duckdb

_TOOL = Path(__file__).resolve().parents[2] / "tools" / "calibrate_refs.py"
spec = importlib.util.spec_from_file_location("calibrate_refs", _TOOL)
calibrate_refs = importlib.util.module_from_spec(spec)
sys.modules["calibrate_refs"] = calibrate_refs
spec.loader.exec_module(calibrate_refs)

from src.orderflow.footprint import FootprintBar, PriceLevel  # noqa: E402

T0 = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)


def _bar(levels, t=T0):
    return FootprintBar(bar_time=t, symbol="BTCUSDT", timeframe="1m", levels=tuple(
        PriceLevel(price=Decimal(p), buy_volume=Decimal(b), sell_volume=Decimal(s))
        for p, b, s in levels
    ))


def test_nearest_rank_percentile_decimal_only():
    vals = [Decimal(v) for v in ("1", "2", "3", "4")]
    assert calibrate_refs._nearest_rank_percentile(vals, Decimal("25")) == Decimal("1")
    assert calibrate_refs._nearest_rank_percentile(vals, Decimal("80")) == Decimal("4")


def test_recommend_min_volume_p25():
    # combined volumes: 1,2,3,4 → P25 (nearest-rank) = 1
    bars = [_bar([("100", "1", "0"), ("101", "1", "1"),
                  ("102", "2", "1"), ("103", "2", "2")])]
    ref, n = calibrate_refs.recommend_min_volume(bars)
    assert ref == Decimal("1")
    assert n == 4


def test_recommend_stack_ref_uses_real_detector():
    # 3 連続の BUY imbalance (対角: BuyVol(P) / SellVol(P-1) >= 3) を構成する。
    # levels 昇順: 99(base), 100..102 が対角比 >= 3 で qualify → run 長 3。
    bars = [_bar([
        ("99", "1", "1"),
        ("100", "6", "1"),   # buy 6 / sell(99)=1 → ratio 6
        ("101", "6", "1"),   # buy 6 / sell(100)=1 → 6
        ("102", "6", "1"),   # buy 6 / sell(101)=1 → 6
    ])]
    ref, samples = calibrate_refs.recommend_stack_ref(
        bars, min_volume=Decimal("1"),
        ratio_threshold=Decimal("3"), ratio_cap=Decimal("10"),
    )
    assert ref == 3
    assert samples == 1


def test_load_bars_reconstructs_footprint(tmp_path):
    db = str(tmp_path / "t.duckdb")
    con = duckdb.connect(db)
    con.execute("""
        CREATE TABLE trades (
            event_time TIMESTAMP, symbol VARCHAR,
            price DECIMAL(20,8), quantity DECIMAL(20,8), side VARCHAR
        )""")
    rows = [
        # bar 12:00 — price 100: BUY 2 / SELL 1, price 101: BUY 1
        (datetime(2026, 7, 18, 12, 0, 5), "BTCUSDT", "100", "2", "BUY"),
        (datetime(2026, 7, 18, 12, 0, 20), "BTCUSDT", "100", "1", "SELL"),
        (datetime(2026, 7, 18, 12, 0, 40), "BTCUSDT", "101", "1", "BUY"),
        # bar 12:01 — price 100: SELL 3
        (datetime(2026, 7, 18, 12, 1, 10), "BTCUSDT", "100", "3", "SELL"),
    ]
    con.executemany("INSERT INTO trades VALUES (?,?,?,?,?)", rows)
    con.close()

    bars, window_start = calibrate_refs.load_bars(db, "BTCUSDT", 60, 7)
    assert len(bars) == 2
    b1, b2 = bars
    assert [str(lv.price) for lv in b1.levels] == ["100.00000000", "101.00000000"]
    assert b1.levels[0].buy_volume == Decimal("2")
    assert b1.levels[0].sell_volume == Decimal("1")
    assert b1.levels[1].buy_volume == Decimal("1")
    assert b2.levels[0].sell_volume == Decimal("3")
    assert window_start is not None
