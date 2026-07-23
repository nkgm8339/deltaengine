"""Tests for src.orderflow.imbalance — M8.

TV-IMB-01 through TV-IMB-06 are verbatim from TestSpecification_v3.2 §4.3.
Additional tests cover decision 4 (array-index adjacency), decision 6 (negative
volume rejection), and deterministic replay.

Fixture (per TestSpecification §4.3):
    ratio_threshold=3.0, min_volume=50, ratio_cap=10.0, stack_count=3
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.orderflow.footprint import FootprintBar, PriceLevel
from src.orderflow.imbalance import (
    BuyImbalance,
    ImbalanceDetector,
    SellImbalance,
    StackedImbalance,
)

UTC = timezone.utc
_T0 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)

# ---------- fixture detector (TestSpecification §4.3 defaults) ----------------
def _det(stack_count: int = 3) -> ImbalanceDetector:
    return ImbalanceDetector(
        ratio_threshold=Decimal("3.0"),
        min_volume=Decimal("50"),
        ratio_cap=Decimal("10.0"),
        stack_count=stack_count,
    )


# ---------- helper: build a FootprintBar from (price, buy, sell) triples -----
def _bar(*level_specs: tuple) -> FootprintBar:
    """Build a FootprintBar from (price, buy_volume, sell_volume) tuples."""
    levels = tuple(
        PriceLevel(
            price=Decimal(str(p)),
            buy_volume=Decimal(str(b)),
            sell_volume=Decimal(str(s)),
        )
        for p, b, s in level_specs
    )
    return FootprintBar(bar_time=_T0, symbol="BTCUSDT", timeframe="1m", levels=levels)


# ============================ TV-IMB-01 Ratio boundary (qualify) =============
def test_tv_imb_01_buy_imbalance_qualifies() -> None:
    """TV-IMB-01: SellVol(100)=100, BuyVol(101)=300. Combined 400>=50. ratio=3.0."""
    bar = _bar((100, 0, 100), (101, 300, 0))
    result = _det().detect(bar)

    assert len(result.buy_imbalances) == 1
    bi = result.buy_imbalances[0]
    assert bi.price == Decimal("101")
    assert bi.ratio == Decimal("3")
    assert len(result.sell_imbalances) == 0


# ============================ TV-IMB-02 Ratio boundary (not qualify) =========
def test_tv_imb_02_ratio_below_threshold() -> None:
    """TV-IMB-02: BuyVol(101)=299, SellVol(100)=100 → ratio 2.99 < 3.0."""
    bar = _bar((100, 0, 100), (101, 299, 0))
    result = _det().detect(bar)

    assert len(result.buy_imbalances) == 0
    assert len(result.sell_imbalances) == 0


# ============================ TV-IMB-03 Zero denominator (qualify) ===========
def test_tv_imb_03_zero_denominator_volume_ok() -> None:
    """TV-IMB-03: SellVol(100)=0, BuyVol(101)=60. Combined 60>=50 → ratio capped 10.0."""
    bar = _bar((100, 0, 0), (101, 60, 0))
    result = _det().detect(bar)

    assert len(result.buy_imbalances) == 1
    assert result.buy_imbalances[0].ratio == Decimal("10.0")


# ============================ TV-IMB-04 Zero denominator (not qualify) =======
def test_tv_imb_04_zero_denominator_volume_fail() -> None:
    """TV-IMB-04: SellVol(100)=0, BuyVol(101)=40. Combined 40<50 → no imbalance."""
    bar = _bar((100, 0, 0), (101, 40, 0))
    result = _det().detect(bar)

    assert len(result.buy_imbalances) == 0


# ============================ TV-IMB-05 Stacked (qualify) ====================
def test_tv_imb_05_stacked_imbalance_buy() -> None:
    """TV-IMB-05: qualifying Buy Imbalances at 101, 102, 103 → Stacked BUY count=3."""
    # Each adjacent pair: ratio = 60/20 = 3.0; combined >= 50.
    bar = _bar(
        (100,  0, 20),
        (101, 60, 20),
        (102, 60, 20),
        (103, 60,  0),
    )
    result = _det().detect(bar)

    assert len(result.buy_imbalances) == 3
    prices = {bi.price for bi in result.buy_imbalances}
    assert prices == {Decimal("101"), Decimal("102"), Decimal("103")}

    assert len(result.stacked_imbalances) == 1
    si = result.stacked_imbalances[0]
    assert si.direction == "BUY"
    assert si.count == 3
    assert si.start_price == Decimal("101")
    assert si.end_price == Decimal("103")


# ============================ TV-IMB-06 Stacked (not qualify) ================
def test_tv_imb_06_stacked_not_enough_consecutive() -> None:
    """TV-IMB-06: qualifying Buy Imbalances at 101, 102 only (2 < stack_count=3)."""
    bar = _bar(
        (100,  0, 20),
        (101, 60, 20),
        (102, 60,  0),
    )
    result = _det().detect(bar)

    assert len(result.buy_imbalances) == 2
    assert len(result.stacked_imbalances) == 0


# ============================ TV-IMB-07 Thin levels do not fire ==============
def test_tv_imb_07_thin_levels_no_fire() -> None:
    """TV-IMB-07 (Task-A): thin one-sided levels (0.01 vs 0.00) must not fire.

    Before the fix, a zero-denominator pair auto-qualified at ratio_cap whenever
    ``combined >= min_volume``, so thin bars with many 0.00 levels produced
    imbalances on every pair. With min_volume=0.5 a column of 0.01/0.00 levels
    now yields no imbalances and no stacks.
    """
    det = ImbalanceDetector(
        ratio_threshold=Decimal("3.0"),
        min_volume=Decimal("0.5"),
        ratio_cap=Decimal("10.0"),
        stack_count=3,
    )
    thin = _bar(
        (100, "0.01", "0.00"),
        (101, "0.01", "0.00"),
        (102, "0.01", "0.00"),
        (103, "0.01", "0.00"),
    )
    result = det.detect(thin)
    assert result.buy_imbalances == ()
    assert result.sell_imbalances == ()
    assert result.stacked_imbalances == ()

    # Numerator gate specifically: combined >= min_volume but the zero-denominator
    # numerator (0.3) is below min_volume → still no fire (previously would cap).
    gated = _bar((100, "0.4", "0.00"), (101, "0.3", "0.00"))
    gated_result = det.detect(gated)
    assert gated_result.buy_imbalances == ()


# ============================ Decision 4: array-index adjacency ==============
def test_decision4_non_unit_price_gap_still_compared() -> None:
    """Prices 100 and 105 (gap=5) are array-adjacent → compared as P and P-1tick."""
    bar = _bar((100, 0, 100), (105, 300, 0))
    result = _det().detect(bar)

    # BuyVol(105)/SellVol(100) = 300/100 = 3.0 → qualifies at price 105.
    assert len(result.buy_imbalances) == 1
    assert result.buy_imbalances[0].price == Decimal("105")
    assert result.buy_imbalances[0].ratio == Decimal("3")


# ============================ Decision 6: negative volume rejection ===========
def test_decision6_negative_volume_skipped_others_detected() -> None:
    """Negative sell_volume at price 100 → E3001 for that level.
    Other pairs (sell imbalance at 101 vs 102) still detected."""
    # Level 100: invalid (negative sell). Level 101 and 102: valid.
    # Sell imbalance at 101: SellVol(101)/BuyVol(102) = 100/0 → zero denom,
    #   combined = 300+100+0+300 = 700 >= 50 → ratio_cap.
    bar = _bar((100, 0, -5), (101, 300, 100), (102, 0, 300))
    det = _det()
    result = det.detect(bar)

    assert det.invalid_pairs >= 1             # level 100 counted
    # Buy imbalance at 101 uses prev=level 100 (invalid) → skipped.
    assert all(bi.price != Decimal("101") for bi in result.buy_imbalances)
    # Sell imbalance at 101 uses next=level 102 (valid) → detected.
    sell_prices = {si.price for si in result.sell_imbalances}
    assert Decimal("101") in sell_prices


# ============================ Deterministic replay ===========================
def test_deterministic_replay() -> None:
    """Same FootprintBar twice → identical ImbalanceResult."""
    bar = _bar(
        (100,  0, 20),
        (101, 60, 20),
        (102, 60, 20),
        (103, 60,  0),
    )
    r1 = _det().detect(bar)
    r2 = _det().detect(bar)
    assert r1 == r2


# ============================ Empty bar =======================================
def test_empty_levels_returns_empty_result() -> None:
    bar = FootprintBar(bar_time=_T0, symbol="BTCUSDT", timeframe="1m", levels=())
    result = _det().detect(bar)
    assert result.buy_imbalances == ()
    assert result.sell_imbalances == ()
    assert result.stacked_imbalances == ()


# ============================ Sell imbalance detection ========================
def test_sell_imbalance_detected() -> None:
    """SellVol(101)/BuyVol(102) = 300/100 = 3.0 → Sell Imbalance at 101.
    Level 100 has high BuyVol so SellVol(100)/BuyVol(101)=0/0 combined=0 < 50 → no imbalance there.
    """
    # Level 100: BuyVol=200, SellVol=0 → combined at (100,101) pair = 200+0+0+300=500.
    # SellVol(100)/BuyVol(101)=0/0 → zero denom, combined=200+0+0+300=500>=50 → cap.
    # To avoid that noise, give level 100 a large combined volume but keep SellVol=0
    # and ensure BuyVol(101) is large so ratio at 100 DOES qualify...
    # Simplest approach: only 2 levels, so sell imbalance can only be at level 0 (index 0 vs 1).
    bar = _bar((101, 0, 300), (102, 100, 0))
    result = _det().detect(bar)

    # SellVol(101)/BuyVol(102) = 300/100 = 3.0; combined=0+300+100+0=400>=50 → qualifies.
    assert len(result.sell_imbalances) == 1
    si = result.sell_imbalances[0]
    assert si.price == Decimal("101")
    assert si.ratio == Decimal("3")
