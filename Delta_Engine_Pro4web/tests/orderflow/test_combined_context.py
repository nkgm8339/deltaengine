from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.orderflow.combined_context import (
    BASE_PATTERNS,
    OiDirection,
    classify_candles,
    classify_directions,
    combine_pattern_with_oi,
    context_catalog,
)
from src.orderflow.cvd import Candle


def candle(
    *,
    close: str,
    cvd: str,
    delta: str,
    open_: str = "100",
) -> Candle:
    return Candle(
        bar_time=datetime(2026, 7, 24, tzinfo=timezone.utc),
        symbol="BTCUSDT",
        timeframe="5m",
        open=Decimal(open_),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal(close),
        volume=Decimal("10"),
        delta=Decimal(delta),
        cvd=Decimal(cvd),
    )


@pytest.mark.parametrize(
    ("directions", "number", "name"),
    [
        ((1, 1, 1), 1, "UPTREND"),
        ((1, 1, -1), 2, "UPTREND PULLBACK"),
        ((1, -1, 1), 3, "UPWARD REBOUND"),
        ((1, -1, -1), 4, "UPWARD DIVERGENCE"),
        ((-1, 1, 1), 5, "DOWNWARD DIVERGENCE"),
        ((-1, 1, -1), 6, "DOWNTREND PULLBACK"),
        ((-1, -1, 1), 7, "DOWNWARD REBOUND"),
        ((-1, -1, -1), 8, "DOWNTREND"),
    ],
)
def test_existing_eight_patterns_are_unchanged(directions, number, name):
    pattern = classify_directions(*directions)
    assert pattern.number == number
    assert pattern.name == name


def test_candle_tie_breaks_match_existing_ui_rule():
    reference = candle(close="100", cvd="10", delta="-1")
    current = candle(close="100", cvd="10", delta="0", open_="99")
    assert classify_candles(current, reference).number == 1


def test_all_sixteen_directional_oi_contexts_are_defined():
    catalog = context_catalog()
    assert len(catalog) == 16
    assert len({item.code for item in catalog}) == 16
    assert {item.pattern for item in catalog} == set(BASE_PATTERNS)
    assert {item.oi_direction for item in catalog} == {
        OiDirection.BUILDING,
        OiDirection.UNWINDING,
    }


def test_oi_unchanged_and_missing_remain_explicit():
    base = classify_directions(1, -1, -1)
    unchanged = combine_pattern_with_oi(base, Decimal("0"))
    missing = combine_pattern_with_oi(base, None)
    assert unchanged.pattern is base
    assert unchanged.oi_direction is OiDirection.UNCHANGED
    assert unchanged.title == "OI UNCHANGED"
    assert missing.pattern is base
    assert missing.oi_direction is OiDirection.MISSING
    assert missing.title == "OI DATA MISSING"


@pytest.mark.parametrize("bad", [0, 2, -2, True])
def test_invalid_directions_are_rejected(bad):
    with pytest.raises(ValueError):
        classify_directions(bad, 1, 1)
