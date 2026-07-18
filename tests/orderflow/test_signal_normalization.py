"""Tests for score normalisation functions in src.orderflow.signal (M11).

All functions return Decimal (no float). Test vectors are defined in
instruction §5 (no TV numbers in spec — named clearly per instruction).
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from src.orderflow.footprint import FootprintBar, PriceLevel
from src.orderflow.imbalance import ImbalanceDetector, StackedImbalance, ImbalanceResult
from src.orderflow.signal import score_cvd, score_footprint, score_imbalance

UTC = timezone.utc
_T0 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)

D = Decimal


def _imb_result(*stacked: StackedImbalance) -> ImbalanceResult:
    return ImbalanceResult(
        bar_time=_T0, symbol="BTCUSDT",
        buy_imbalances=(), sell_imbalances=(),
        stacked_imbalances=tuple(stacked),
    )


def _stacked(direction: str, count: int) -> StackedImbalance:
    return StackedImbalance(
        start_price=D("100"), end_price=D("102"),
        count=count, direction=direction,
    )


# ============================ score_cvd ======================================
def test_score_cvd_positive() -> None:
    assert score_cvd(D("5"), D("10")) == D("50")


def test_score_cvd_negative() -> None:
    assert score_cvd(D("-5"), D("10")) == D("-50")


def test_score_cvd_clamped_upper() -> None:
    assert score_cvd(D("30"), D("10")) == D("100")


def test_score_cvd_clamped_lower() -> None:
    assert score_cvd(D("-30"), D("10")) == D("-100")


def test_score_cvd_none_when_ref_none() -> None:
    assert score_cvd(D("5"), None) is None


def test_score_cvd_none_when_ref_zero() -> None:
    assert score_cvd(D("5"), D("0")) is None


def test_score_cvd_returns_decimal() -> None:
    result = score_cvd(D("5"), D("10"))
    assert isinstance(result, Decimal)


# ============================ score_footprint ================================
def test_score_footprint_all_buy() -> None:
    assert score_footprint(D("10"), D("0")) == D("100")


def test_score_footprint_all_sell() -> None:
    assert score_footprint(D("0"), D("10")) == D("-100")


def test_score_footprint_balanced() -> None:
    assert score_footprint(D("5"), D("5")) == D("0")


def test_score_footprint_zero_volume() -> None:
    assert score_footprint(D("0"), D("0")) == D("0")


def test_score_footprint_partial_buy() -> None:
    # (75-25)/(75+25) * 100 = 50
    assert score_footprint(D("75"), D("25")) == D("50")


def test_score_footprint_returns_decimal() -> None:
    assert isinstance(score_footprint(D("10"), D("5")), Decimal)


# ============================ score_imbalance ================================
def test_score_imbalance_single_buy_stack() -> None:
    result = _imb_result(_stacked("BUY", 3))
    assert score_imbalance(result, stack_ref=3) == D("100")


def test_score_imbalance_no_stacks() -> None:
    assert score_imbalance(_imb_result(), stack_ref=3) == D("0")


def test_score_imbalance_net_mixed() -> None:
    # net = 3 - 1 = 2; min(2/3, 1) * 100 = 66.66...
    result = _imb_result(_stacked("BUY", 3), _stacked("SELL", 1))
    s = score_imbalance(result, stack_ref=3)
    expected = (D(2) / D(3)) * D(100)
    assert s == expected


def test_score_imbalance_sell_dominant() -> None:
    result = _imb_result(_stacked("SELL", 3))
    assert score_imbalance(result, stack_ref=3) == D("-100")


def test_score_imbalance_net_zero() -> None:
    result = _imb_result(_stacked("BUY", 2), _stacked("SELL", 2))
    assert score_imbalance(result, stack_ref=3) == D("0")


def test_score_imbalance_returns_decimal() -> None:
    assert isinstance(score_imbalance(_imb_result(), stack_ref=3), Decimal)
