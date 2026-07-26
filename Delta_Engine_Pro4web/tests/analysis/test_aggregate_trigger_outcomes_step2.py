from __future__ import annotations

import pytest

from analysis.aggregate_trigger_outcomes_step2 import (
    check_count,
    directed_excursions,
    direction_result,
    state_hypotheses,
    threshold_20usd_bps,
)


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("BUY_EFFECTIVE", ((1, "EFFECTIVE_CONTINUATION", "ANALYSIS"),)),
        ("SELL_EFFECTIVE", ((-1, "EFFECTIVE_CONTINUATION", "ANALYSIS"),)),
        ("BUY_TRAPPED", ((-1, "TRAPPED_REVERSAL", "ANALYSIS"),)),
        ("SELL_TRAPPED", ((1, "TRAPPED_REVERSAL", "ANALYSIS"),)),
    ],
)
def test_primary_state_direction_is_fixed_before_outcomes(
    state: str,
    expected: tuple[tuple[int, str, str], ...],
) -> None:
    assert state_hypotheses(state) == expected


def test_stalled_is_two_labelled_probes_not_a_direction_claim() -> None:
    assert state_hypotheses("BUY_STALLED") == (
        (1, "STALLED_PRESSURE_PROBE", "ENTRY_PROBE"),
        (-1, "STALLED_REVERSAL_PROBE", "ENTRY_PROBE"),
    )
    assert state_hypotheses("SELL_STALLED") == (
        (-1, "STALLED_PRESSURE_PROBE", "ENTRY_PROBE"),
        (1, "STALLED_REVERSAL_PROBE", "ENTRY_PROBE"),
    )


def test_direction_relative_mfe_mae_for_buy_and_sell() -> None:
    assert directed_excursions(1, 8.0, -3.0) == (8.0, -3.0)
    assert directed_excursions(-1, 8.0, -3.0) == (3.0, -8.0)
    with pytest.raises(ValueError):
        directed_excursions(0, 8.0, -3.0)


def test_direction_result_keeps_flat_separate() -> None:
    assert direction_result(0.1) == "MATCH"
    assert direction_result(-0.1) == "MISMATCH"
    assert direction_result(0.0) == "FLAT"


def test_20usd_threshold_is_entry_price_specific() -> None:
    assert threshold_20usd_bps(64_000.0) == pytest.approx(3.125)
    with pytest.raises(ValueError):
        threshold_20usd_bps(0.0)


def test_strict_inventory_count_fails_closed() -> None:
    check_count("sample", 10, 10, strict=True)
    check_count("sample", 9, 10, strict=False)
    with pytest.raises(RuntimeError, match="count mismatch"):
        check_count("sample", 9, 10, strict=True)
