"""Tests for src.orderflow.footprint — M7.

TV-FP-01 and TV-FP-02 are verbatim from TestSpecification_v3.2 §4.2.
Additional tests (duplicate rejection, bar-boundary reset, deterministic replay)
follow the CV-CVD pattern per instruction §5.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.orderflow.footprint import (
    FootprintCalculator,
    FootprintTrade,
    PriceLevel,
)

UTC = timezone.utc

# Two distinct 1m bar starts.
_T0 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)   # bar 00:00
_T1 = datetime(2026, 1, 1, 0, 1, 0, tzinfo=UTC)   # bar 00:01


def _trade(
    trade_id: int,
    price,
    quantity,
    side: str,
    event_time: datetime = _T0,
    symbol: str = "BTCUSDT",
) -> FootprintTrade:
    return FootprintTrade(
        trade_id=trade_id,
        event_time=event_time,
        symbol=symbol,
        price=price,
        quantity=quantity,
        side=side,
    )


def _calc(timeframe: str = "1m") -> FootprintCalculator:
    return FootprintCalculator(symbol="BTCUSDT", timeframe=timeframe)


# ============================ TV-FP-01 Level aggregation =====================
def test_tv_fp_01_level_aggregation() -> None:
    """TestSpecification_v3.2 §4.2 TV-FP-01."""
    calc = _calc()
    assert calc.process_trade(_trade(1, 100, 5, "BUY")) is None
    assert calc.process_trade(_trade(2, 100, 3, "SELL")) is None
    assert calc.process_trade(_trade(3, 101, 2, "BUY")) is None

    levels = calc.current_tick_snapshot()
    assert len(levels) == 2

    lvl100 = next(lv for lv in levels if lv.price == Decimal("100"))
    lvl101 = next(lv for lv in levels if lv.price == Decimal("101"))

    assert lvl100.buy_volume == Decimal("5")
    assert lvl100.sell_volume == Decimal("3")
    assert lvl101.buy_volume == Decimal("2")
    assert lvl101.sell_volume == Decimal("0")


# ============================ TV-FP-02 Invalid trade =========================
def test_tv_fp_02_invalid_trade_rejected() -> None:
    """TestSpecification_v3.2 §4.2 TV-FP-02 — side missing / invalid."""
    calc = _calc()
    calc.process_trade(_trade(1, 100, 5, "BUY"))

    before = calc.current_tick_snapshot()
    calc.process_trade(_trade(2, 100, 3, "NEITHER"))   # invalid side
    after = calc.current_tick_snapshot()

    assert after == before          # totals unchanged
    assert calc.rejected_invalid == 1
    assert calc.processed == 1


# ============================ Duplicate trade_id ==============================
def test_duplicate_trade_id_rejected() -> None:
    calc = _calc()
    calc.process_trade(_trade(1, 100, 5, "BUY"))
    calc.process_trade(_trade(1, 100, 5, "BUY"))   # duplicate

    levels = calc.current_tick_snapshot()
    lvl = levels[0]
    assert lvl.buy_volume == Decimal("5")           # only counted once
    assert calc.duplicates == 1
    assert calc.processed == 1


# ============================ Bar boundary reset ==============================
def test_bar_boundary_returns_confirmed_bar_and_resets() -> None:
    calc = _calc()
    calc.process_trade(_trade(1, 100, 5, "BUY",  event_time=_T0))
    calc.process_trade(_trade(2, 100, 3, "SELL", event_time=_T0))

    # First trade of next bar triggers rollover → confirmed bar returned.
    confirmed = calc.process_trade(_trade(3, 101, 2, "BUY", event_time=_T1))

    assert confirmed is not None
    assert confirmed.bar_time == _T0
    assert len(confirmed.levels) == 1
    lv = confirmed.levels[0]
    assert lv.price == Decimal("100")
    assert lv.buy_volume == Decimal("5")
    assert lv.sell_volume == Decimal("3")

    # New bar contains only the T1 trade.
    snap = calc.current_tick_snapshot()
    assert len(snap) == 1
    assert snap[0].price == Decimal("101")
    assert snap[0].buy_volume == Decimal("2")
    assert snap[0].sell_volume == Decimal("0")


def test_finalize_returns_final_bar() -> None:
    calc = _calc()
    calc.process_trade(_trade(1, 100, 5, "BUY"))
    final = calc.finalize()

    assert final is not None
    assert final.bar_time == _T0
    assert final.levels[0].buy_volume == Decimal("5")
    assert calc.finalize() is None    # idempotent


# ============================ Price levels sorted ascending ===================
def test_levels_sorted_ascending() -> None:
    calc = _calc()
    for tid, price in enumerate([103, 101, 102, 100], start=1):
        calc.process_trade(_trade(tid, price, 1, "BUY"))
    prices = [lv.price for lv in calc.current_tick_snapshot()]
    assert prices == sorted(prices)


# ============================ Decimal arithmetic (no float) ==================
def test_no_float_in_output() -> None:
    calc = _calc()
    calc.process_trade(_trade(1, "50000.12345678", "0.00100001", "SELL"))
    lv = calc.current_tick_snapshot()[0]
    assert isinstance(lv.price, Decimal)
    assert isinstance(lv.sell_volume, Decimal)
    assert lv.sell_volume == Decimal("0.00100001")


# ============================ Deterministic replay ===========================
def test_deterministic_replay() -> None:
    """Same input sequence twice → identical output."""
    trades = [
        _trade(1, 100, 5,  "BUY",  event_time=_T0),
        _trade(2, 100, 3,  "SELL", event_time=_T0),
        _trade(3, 101, 2,  "BUY",  event_time=_T1),
    ]

    def _run():
        calc = _calc()
        bars = []
        for t in trades:
            b = calc.process_trade(t)
            if b is not None:
                bars.append(b)
        final = calc.finalize()
        if final is not None:
            bars.append(final)
        return bars

    first, second = _run(), _run()
    assert len(first) == len(second) == 2
    for b1, b2 in zip(first, second):
        assert b1 == b2


# ============================ Non-positive price rejected ====================
def test_non_positive_price_rejected() -> None:
    calc = _calc()
    calc.process_trade(_trade(1, 0, 1, "BUY"))
    calc.process_trade(_trade(2, -1, 1, "SELL"))
    assert calc.rejected_invalid == 2
    assert calc.processed == 0
    assert calc.current_tick_snapshot() == ()
