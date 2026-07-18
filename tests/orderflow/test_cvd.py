"""Tests for src.orderflow.cvd.

Section 1 implements TestSpecification_v3.2 §4.1 TV-CVD-01..04 verbatim (numbers
taken exactly from the spec). Later sections cover bar aggregation and
deterministic replay (CVD_v3.2 §5/§7), using non-spec sample inputs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.orderflow.cvd import (
    ERROR_DUPLICATE_TRADE,
    ERROR_INVALID_TRADE,
    ERROR_OUT_OF_ORDER,
    CvdCalculator,
    Trade,
    bar_start,
    run,
    trade_delta,
)

SYMBOL = "BTCUSDT"
T0 = datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc)


def _trade(trade_id: int, side: str, quantity, *, offset_sec: int = 0, price=100) -> Trade:
    return Trade(
        trade_id=trade_id,
        event_time=T0 + timedelta(seconds=offset_sec),
        symbol=SYMBOL,
        price=Decimal(str(price)),
        quantity=Decimal(str(quantity)),
        side=side,
    )


# ============================ TV-CVD-01..04 ===================================
def test_tv_cvd_01_normal_sequence() -> None:
    trades = [
        _trade(1, "BUY", 5, offset_sec=0),
        _trade(2, "SELL", 3, offset_sec=1),
        _trade(3, "BUY", 2, offset_sec=2),
        _trade(4, "SELL", 6, offset_sec=3),
    ]
    result = run(trades, SYMBOL)
    deltas = [u.tick_delta for u in result.updates]
    cvds = [u.tick_cvd for u in result.updates]
    assert deltas == [Decimal(5), Decimal(-3), Decimal(2), Decimal(-6)]
    assert cvds == [Decimal(5), Decimal(2), Decimal(4), Decimal(-2)]
    assert result.final_cvd == Decimal(-2)
    assert result.processed == 4
    assert not result.rejections


def test_tv_cvd_02_duplicate_trade_id() -> None:
    calc = CvdCalculator(SYMBOL)
    calc.process(_trade(1, "BUY", 5, offset_sec=0))
    dup = calc.process(_trade(1, "BUY", 5, offset_sec=0))  # same trade_id again
    assert dup.accepted is False
    assert dup.rejection is not None and dup.rejection.code == ERROR_DUPLICATE_TRADE
    assert calc.cvd == Decimal(5)           # unchanged
    assert calc.duplicates == 1
    assert calc.processed == 1


def test_tv_cvd_03_invalid_side() -> None:
    calc = CvdCalculator(SYMBOL)
    calc.process(_trade(1, "BUY", 5, offset_sec=0))     # establish CVD = +5
    bad = calc.process(_trade(5, "X", 4, offset_sec=1))
    assert bad.accepted is False
    assert bad.rejection is not None and bad.rejection.code == ERROR_INVALID_TRADE
    assert calc.cvd == Decimal(5)           # unchanged, no partial update
    assert calc.rejected_invalid == 1
    assert 5 not in calc._seen_ids          # invalid trade not registered


def test_tv_cvd_04_out_of_order_timestamp() -> None:
    calc = CvdCalculator(SYMBOL)
    calc.process(_trade(1, "BUY", 5, offset_sec=10))    # last event_time = T0+10s
    ooo = calc.process(_trade(6, "BUY", 4, offset_sec=5))  # earlier
    assert ooo.accepted is False
    assert ooo.rejection is not None and ooo.rejection.code == ERROR_OUT_OF_ORDER
    assert calc.cvd == Decimal(5)           # unchanged
    assert calc.rejected_out_of_order == 1


# ============================ pure helpers ====================================
def test_trade_delta_signs() -> None:
    assert trade_delta("BUY", Decimal(5)) == Decimal(5)
    assert trade_delta("SELL", Decimal(3)) == Decimal(-3)


def test_bar_start_utc_alignment() -> None:
    dt = datetime(2026, 1, 1, 0, 0, 37, tzinfo=timezone.utc)
    assert bar_start(dt, "1m") == datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert bar_start(dt, "1h") == datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    dt2 = datetime(2026, 1, 1, 13, 42, 5, tzinfo=timezone.utc)
    assert bar_start(dt2, "1d") == datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


# ============================ bar aggregation =================================
def test_bar_delta_resets_cvd_cumulative() -> None:
    # bar1 (00:00): BUY 5 @100, SELL 3 @101 ; bar2 (00:01): BUY 4 @102
    trades = [
        _trade(1, "BUY", 5, offset_sec=0, price=100),   # 00:00:01
        _trade(2, "SELL", 3, offset_sec=29, price=101),  # 00:00:30
        _trade(3, "BUY", 4, offset_sec=60, price=102),   # 00:01:01 -> new bar
    ]
    result = run(trades, SYMBOL, "1m")
    assert len(result.candles) == 2

    bar1, bar2 = result.candles
    # bar1 delta = +5-3 = +2 (bar delta), cvd as of bar close = +2
    assert bar1.delta == Decimal(2)
    assert bar1.cvd == Decimal(2)
    assert bar1.open == Decimal(100)
    assert bar1.high == Decimal(101)
    assert bar1.low == Decimal(100)
    assert bar1.close == Decimal(101)
    assert bar1.volume == Decimal(8)
    assert bar1.bar_time == datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    # bar2 delta resets to +4 ; cvd stays cumulative = +6
    assert bar2.delta == Decimal(4)
    assert bar2.cvd == Decimal(6)
    assert bar2.bar_time == datetime(2026, 1, 1, 0, 1, 0, tzinfo=timezone.utc)


# ============================ deterministic replay ============================
def test_deterministic_replay_identical() -> None:
    trades = [
        _trade(1, "BUY", 5, offset_sec=0),
        _trade(2, "SELL", 3, offset_sec=1),
        _trade(2, "SELL", 3, offset_sec=1),   # duplicate
        _trade(3, "X", 9, offset_sec=2),       # invalid
        _trade(4, "BUY", 2, offset_sec=3),
    ]
    first = run(trades, SYMBOL)
    second = run(trades, SYMBOL)
    assert first == second
    assert first.final_cvd == Decimal(4)      # 5 -3 +2
    assert first.duplicates == 1
    assert first.rejected_invalid == 1
