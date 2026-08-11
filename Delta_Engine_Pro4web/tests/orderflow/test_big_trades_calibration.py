from __future__ import annotations

from decimal import Decimal

from src.orderflow.big_trades.calibration import (
    SessionQuantityDistribution,
    calibrate,
    ceil_to_step,
    decimal_median,
    normalized_true_range,
    session_rank,
)
from src.orderflow.big_trades.constants import AutomaticIntensity, CalibrationStatus


def distributions(count: int = 20, volatility: str = "0.01"):
    return tuple(
        SessionQuantityDistribution(
            session_id=f"2026-01-{index + 1:02d}",
            cluster_quantities=tuple(Decimal(value) for value in range(1, 31)),
            session_volatility=Decimal(volatility),
        )
        for index in range(count)
    )


def test_rank_is_one_based_descending() -> None:
    values = tuple(Decimal(value) for value in range(1, 31))
    assert session_rank(values, 2) == Decimal("29")
    assert session_rank(values, 9) == Decimal("22")
    assert session_rank(values, 20) == Decimal("11")


def test_decimal_median_never_uses_float() -> None:
    assert decimal_median((Decimal("1"), Decimal("2"))) == Decimal("1.5")


def test_calibration_uses_20_9_2_ranks_and_strict_order() -> None:
    result = calibrate(distributions(), quantity_step=Decimal("0.001"))
    assert result.status is CalibrationStatus.VALID
    assert result.base_thresholds == {
        AutomaticIntensity.LOW: Decimal("11"),
        AutomaticIntensity.MEDIUM: Decimal("22"),
        AutomaticIntensity.STRONG: Decimal("29"),
    }
    assert result.thresholds == result.base_thresholds


def test_insufficient_sessions_fail_closed() -> None:
    result = calibrate(distributions(9), quantity_step=Decimal("0.001"))
    assert result.status is CalibrationStatus.INSUFFICIENT_HISTORY
    assert result.thresholds is None


def test_exactly_ten_valid_sessions_is_valid() -> None:
    assert calibrate(
        distributions(10), quantity_step=Decimal("0.001")
    ).status is CalibrationStatus.VALID


def test_volatility_factor_is_clamped_and_ceil_to_step() -> None:
    sessions = list(distributions())
    sessions[-5:] = [
        SessionQuantityDistribution(
            session_id=session.session_id,
            cluster_quantities=session.cluster_quantities,
            session_volatility=Decimal("1"),
        )
        for session in sessions[-5:]
    ]
    result = calibrate(tuple(sessions), quantity_step=Decimal("0.1"))
    assert result.volatility_factor == Decimal("1.50")
    assert result.thresholds[AutomaticIntensity.LOW] == Decimal("16.5")
    assert ceil_to_step(Decimal("1.001"), Decimal("0.001")) == Decimal("1.001")


def test_volatility_factor_lower_clamp_and_strict_threshold_correction() -> None:
    sessions = list(distributions())
    sessions[-5:] = [
        SessionQuantityDistribution(
            session_id=session.session_id,
            cluster_quantities=(Decimal("1"),) * 30,
            session_volatility=Decimal("0.000001"),
        )
        for session in sessions[-5:]
    ]
    result = calibrate(tuple(sessions), quantity_step=Decimal("1"))
    assert result.volatility_factor == Decimal("0.75")
    assert result.thresholds[AutomaticIntensity.LOW] < result.thresholds[AutomaticIntensity.MEDIUM]
    assert result.thresholds[AutomaticIntensity.MEDIUM] < result.thresholds[AutomaticIntensity.STRONG]


def test_missing_volatility_uses_explicit_fallback() -> None:
    sessions = tuple(
        SessionQuantityDistribution(item.session_id, item.cluster_quantities, None)
        for item in distributions()
    )
    result = calibrate(sessions, quantity_step=Decimal("0.001"))
    assert result.volatility_factor == Decimal("1")
    assert result.volatility_status == "VOLATILITY_FALLBACK_1"


def test_nineteen_volatility_sessions_use_explicit_fallback() -> None:
    sessions = list(distributions())
    sessions[0] = SessionQuantityDistribution(
        sessions[0].session_id,
        sessions[0].cluster_quantities,
        None,
    )
    result = calibrate(tuple(sessions), quantity_step=Decimal("0.001"))
    assert result.volatility_factor == Decimal("1")
    assert result.volatility_status == "VOLATILITY_FALLBACK_1"
    assert result.baseline_volatility is None
    assert result.recent_volatility is None


def test_zero_volatility_baseline_uses_explicit_fallback() -> None:
    result = calibrate(distributions(volatility="0"), quantity_step=Decimal("0.001"))
    assert result.volatility_factor == Decimal("1")
    assert result.volatility_status == "VOLATILITY_FALLBACK_1"
    assert result.baseline_volatility == Decimal("0")
    assert result.recent_volatility == Decimal("0")


def test_normalized_true_range() -> None:
    assert normalized_true_range(
        Decimal("105"), Decimal("99"), Decimal("100"), Decimal("102")
    ) == Decimal("0.06")
