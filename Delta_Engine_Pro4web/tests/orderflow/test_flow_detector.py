"""Tests for FlowDetector Phase A — 15 test functions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.orderflow.flow_detector import (
    ExhaustionDetector,
    FlowEvent,
    LargeTradeDetector,
    SweepDetector,
    TapeAnalyzer,
    UnfinishedAuctionDetector,
)
from src.orderflow.footprint import FootprintBar, PriceLevel


# ── Helpers ───────────────────────────────────────────────────────────────────

def _dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


@dataclass
class _Trade:
    trade_id: int
    event_time: datetime
    symbol: str
    price: Decimal
    quantity: Decimal
    side: str


def _trade(qty: str, side: str, ms: int = 1_000_000_000_000, price: str = "100") -> _Trade:
    return _Trade(
        trade_id=ms,
        event_time=_dt(ms),
        symbol="BTCUSDT",
        price=Decimal(price),
        quantity=Decimal(qty),
        side=side,
    )


def _bar(levels: list[tuple[str, str, str]], bar_ms: int = 1_000_000_000_000) -> FootprintBar:
    """Build a FootprintBar. Each tuple: (price, buy_vol, sell_vol)."""
    lvls = tuple(
        PriceLevel(
            price=Decimal(p),
            buy_volume=Decimal(b),
            sell_volume=Decimal(s),
        )
        for p, b, s in levels
    )
    return FootprintBar(
        bar_time=_dt(bar_ms),
        symbol="BTCUSDT",
        timeframe="1m",
        levels=lvls,
    )


# ── 2-1. LargeTradeDetector ───────────────────────────────────────────────────

def test_large_trade_fires_above_threshold() -> None:
    det = LargeTradeDetector(min_qty=Decimal("5.0"))
    evt = det.process(_trade("6", "BUY"))
    assert evt is not None
    assert evt.kind == "large_trade"
    assert evt.side == "BUY"
    assert evt.strength > Decimal("0")


def test_large_trade_no_fire_below_threshold() -> None:
    det = LargeTradeDetector(min_qty=Decimal("5.0"))
    evt = det.process(_trade("4.9", "SELL"))
    assert evt is None


def test_large_trade_strength_capped_at_one() -> None:
    det = LargeTradeDetector(min_qty=Decimal("5.0"))
    # qty = 5 * 4 * 10 → way over cap
    evt = det.process(_trade("200", "BUY"))
    assert evt is not None
    assert evt.strength == Decimal("1")


# ── 2-2. SweepDetector ────────────────────────────────────────────────────────

def _sweep_det() -> SweepDetector:
    return SweepDetector(
        window_ms=1000,
        min_qty=Decimal("8.0"),
        min_levels=3,
        tick_size=Decimal("1"),
        cooldown_ms=5000,
    )


def test_sweep_fires_when_conditions_met() -> None:
    det = _sweep_det()
    base_ms = 1_000_000_000_000
    # 3 different price levels, total qty 9
    for i, price in enumerate(["100", "101", "102"]):
        evt = det.process(_trade("3", "BUY", ms=base_ms + i * 10, price=price))
    assert evt is not None
    assert evt.kind == "sweep"
    assert evt.side == "BUY"


def test_sweep_no_fire_insufficient_levels() -> None:
    det = _sweep_det()
    base_ms = 1_000_000_000_000
    # only 2 distinct levels but qty sufficient
    for i in range(4):
        evt = det.process(_trade("3", "BUY", ms=base_ms + i * 10, price="100" if i < 2 else "101"))
    # min_levels=3, only 2 → no fire
    assert evt is None


def test_sweep_cooldown_prevents_refiring() -> None:
    det = _sweep_det()
    base_ms = 1_000_000_000_000
    # First fire
    for i, price in enumerate(["100", "101", "102"]):
        det.process(_trade("3", "BUY", ms=base_ms + i * 10, price=price))
    # Immediately another sweep attempt (within cooldown)
    evt2 = det.process(_trade("3", "BUY", ms=base_ms + 100, price="103"))
    assert evt2 is None


# ── 2-3. ExhaustionDetector ───────────────────────────────────────────────────

def test_exhaustion_fires_on_up_bar_high_side_depletion() -> None:
    det = ExhaustionDetector(exhaustion_ratio=Decimal("0.25"))
    # Up bar: close > open means last price > first price.
    # avg vol ≈ (10+10+10+1+1)/5 = 6.4; top2 vol = 2; threshold = 6.4*0.25 = 1.6
    # top2 vol (2) > 1.6 → would NOT fire. Let's use very small top2.
    bar = _bar([
        ("100", "5", "5"),
        ("101", "5", "5"),
        ("102", "5", "5"),
        ("103", "0", "0"),   # top2 start
        ("104", "0", "0"),   # top = 0 vol
    ])
    evt = det.process(bar)
    assert evt is not None
    assert evt.kind == "exhaustion"
    assert evt.side == "SELL"   # BUY exhaustion → SELL warning
    assert Decimal("0") < evt.strength <= Decimal("1")


def test_exhaustion_no_fire_on_normal_bar() -> None:
    det = ExhaustionDetector(exhaustion_ratio=Decimal("0.25"))
    # Balanced bar: no exhaustion
    bar = _bar([
        ("100", "3", "3"),
        ("101", "3", "3"),
        ("102", "3", "3"),
        ("103", "3", "3"),
        ("104", "3", "3"),
    ])
    evt = det.process(bar)
    assert evt is None


# ── 2-4. UnfinishedAuctionDetector ───────────────────────────────────────────

def test_ua_fires_when_both_sides_at_high() -> None:
    det = UnfinishedAuctionDetector(ua_min_vol=Decimal("2.0"))
    # top level has both buy and sell >= 2.0
    bar = _bar([
        ("100", "1", "0"),
        ("101", "5", "5"),   # top: both >= 2 → UA at high
    ])
    evt = det.process(bar)
    assert evt is not None
    assert evt.kind == "unfinished_auction"
    assert evt.side == "BUY"
    assert evt.detail["at"] == "high"


def test_ua_no_fire_when_one_side_zero() -> None:
    det = UnfinishedAuctionDetector(ua_min_vol=Decimal("2.0"))
    # top level has sell_volume=0
    bar = _bar([
        ("100", "1", "0"),
        ("101", "5", "0"),   # ask=0 → no UA
    ])
    evt = det.process(bar)
    assert evt is None


# ── 2-5. TapeAnalyzer ────────────────────────────────────────────────────────

def _tape() -> TapeAnalyzer:
    return TapeAnalyzer(
        window_ms=5000,
        emit_interval_ms=0,       # emit on every trade for testing
        pause_threshold_ms=3000,
    )


def test_tape_aggression_buy_classification() -> None:
    det = _tape()
    base = 1_000_000_000_000
    # 6 BUY, 1 SELL → aggression ratio ≈ 6/7 ≈ 0.857 → BUY
    for i in range(6):
        det.process(_trade("1", "BUY", ms=base + i * 10))
    evt = det.process(_trade("1", "SELL", ms=base + 60))
    assert evt is not None
    assert evt.kind == "tape"
    assert evt.side == "BUY"
    assert Decimal(evt.detail["aggression_ratio"]) > Decimal("0.6")


def test_tape_aggression_sell_classification() -> None:
    det = _tape()
    base = 1_000_000_000_000
    for i in range(6):
        det.process(_trade("1", "SELL", ms=base + i * 10))
    evt = det.process(_trade("1", "BUY", ms=base + 60))
    assert evt is not None
    assert evt.side == "SELL"
    assert Decimal(evt.detail["aggression_ratio"]) < Decimal("0.4")


def test_tape_neutral_classification() -> None:
    det = _tape()
    base = 1_000_000_000_000
    evt = None
    for i in range(4):
        side = "BUY" if i < 2 else "SELL"
        evt = det.process(_trade("1", side, ms=base + i * 10))
    assert evt is not None
    assert evt.side == "NEUTRAL"


def test_tape_max_consecutive_count() -> None:
    det = _tape()
    base = 1_000_000_000_000
    # 3 BUY in a row then 1 SELL
    for i in range(3):
        det.process(_trade("1", "BUY", ms=base + i * 10))
    evt = det.process(_trade("1", "SELL", ms=base + 30))
    assert evt is not None
    assert evt.detail["max_consecutive_side"] == 3


def test_tape_pause_detection() -> None:
    det = TapeAnalyzer(
        window_ms=5000,
        emit_interval_ms=0,
        pause_threshold_ms=100,   # very short threshold
    )
    base = 1_000_000_000_000
    det.process(_trade("1", "BUY", ms=base))
    # Next trade 200ms later → pause > 100ms threshold
    evt = det.process(_trade("1", "BUY", ms=base + 200))
    assert evt is not None
    assert evt.detail.get("paused") is True
