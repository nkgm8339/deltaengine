from __future__ import annotations

from decimal import Decimal

from src.orderflow.big_trades.constants import (
    AutomaticIntensity,
    ClusterCloseReason,
    FilterDecisionReason,
    FilterMode,
)
from src.orderflow.big_trades.filtering import AutomaticSizeFilter, ManualSizeFilter, decide_cluster
from src.orderflow.big_trades.models import ExecutionCluster
from tests.orderflow._big_trades_helpers import fill, settings


def test_manual_min_and_max_are_inclusive() -> None:
    filter_ = ManualSizeFilter(Decimal("5"), Decimal("10"))
    assert filter_.decide(Decimal("5")).accepted
    assert filter_.decide(Decimal("10")).accepted


def test_manual_rejection_reasons_are_exact() -> None:
    filter_ = ManualSizeFilter(Decimal("5"), Decimal("10"))
    assert filter_.decide(Decimal("4.999")).reason is FilterDecisionReason.REJECT_BELOW_MIN
    assert filter_.decide(Decimal("10.001")).reason is FilterDecisionReason.REJECT_ABOVE_MAX


def test_manual_zero_max_is_unbounded() -> None:
    assert ManualSizeFilter(Decimal("5"), Decimal("0")).decide(Decimal("999999")).accepted


def test_automatic_intensity_selects_versioned_threshold() -> None:
    filter_ = AutomaticSizeFilter(
        "cal-1",
        {
            AutomaticIntensity.LOW: Decimal("10"),
            AutomaticIntensity.MEDIUM: Decimal("20"),
            AutomaticIntensity.STRONG: Decimal("50"),
        },
    )
    decision = filter_.decide(Decimal("20"), AutomaticIntensity.MEDIUM)
    assert decision.accepted
    assert decision.threshold_used == Decimal("20")
    assert decision.calibration_id == "cal-1"


def test_automatic_requires_strictly_increasing_thresholds() -> None:
    try:
        AutomaticSizeFilter(
            "cal-1",
            {
                AutomaticIntensity.LOW: Decimal("10"),
                AutomaticIntensity.MEDIUM: Decimal("10"),
                AutomaticIntensity.STRONG: Decimal("20"),
            },
        )
    except ValueError as exc:
        assert "strictly increasing" in str(exc)
    else:
        raise AssertionError("expected strict threshold validation")


def test_automatic_without_matching_active_calibration_fails_closed() -> None:
    configured = settings(
        filter_mode=FilterMode.AUTOMATIC,
        calibration_id="required-calibration",
    )
    cluster = ExecutionCluster(
        (fill(0, quantity="100"),), configured, ClusterCloseReason.STREAM_ENDED
    )
    missing = decide_cluster(cluster)
    assert missing.accepted is False
    assert missing.reason is FilterDecisionReason.AUTOMATIC_UNAVAILABLE

    wrong = AutomaticSizeFilter(
        "different-calibration",
        {
            AutomaticIntensity.LOW: Decimal("1"),
            AutomaticIntensity.MEDIUM: Decimal("2"),
            AutomaticIntensity.STRONG: Decimal("3"),
        },
    )
    assert decide_cluster(cluster, wrong).reason is FilterDecisionReason.AUTOMATIC_UNAVAILABLE
