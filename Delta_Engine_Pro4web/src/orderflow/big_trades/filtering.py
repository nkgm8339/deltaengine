"""Manual and calibrated Automatic Size Filter decisions."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Optional

from .constants import AutomaticIntensity, FilterDecisionReason, FilterMode
from .models import ExecutionCluster, FilterDecision, ZERO


def _nonnegative(value: Decimal | str | int, name: str) -> Decimal:
    parsed = Decimal(str(value))
    if not parsed.is_finite() or parsed < ZERO:
        raise ValueError(f"{name} must be finite and non-negative")
    return parsed


@dataclass(frozen=True)
class ManualSizeFilter:
    minimum: Decimal
    maximum: Decimal = ZERO

    def __post_init__(self) -> None:
        object.__setattr__(self, "minimum", _nonnegative(self.minimum, "minimum"))
        object.__setattr__(self, "maximum", _nonnegative(self.maximum, "maximum"))
        if self.maximum > ZERO and self.maximum < self.minimum:
            raise ValueError("maximum must be zero or >= minimum")

    def decide(self, quantity: Decimal) -> FilterDecision:
        parsed = _nonnegative(quantity, "quantity")
        if parsed < self.minimum:
            reason = FilterDecisionReason.REJECT_BELOW_MIN
        elif self.maximum > ZERO and parsed > self.maximum:
            reason = FilterDecisionReason.REJECT_ABOVE_MAX
        else:
            reason = FilterDecisionReason.ACCEPT
        return FilterDecision(
            accepted=reason is FilterDecisionReason.ACCEPT,
            reason=reason,
            threshold_used=self.minimum,
            max_threshold_used=self.maximum,
            filter_mode=FilterMode.MANUAL,
            intensity=None,
            calibration_id=None,
        )


@dataclass(frozen=True)
class AutomaticSizeFilter:
    calibration_id: str
    thresholds: Mapping[AutomaticIntensity, Decimal]

    def __post_init__(self) -> None:
        if not self.calibration_id:
            raise ValueError("calibration_id must be non-empty")
        normalized = {
            AutomaticIntensity(key): _nonnegative(value, f"threshold {key}")
            for key, value in self.thresholds.items()
        }
        if set(normalized) != set(AutomaticIntensity):
            raise ValueError("thresholds must contain LOW, MEDIUM, and STRONG")
        if not (
            normalized[AutomaticIntensity.LOW]
            < normalized[AutomaticIntensity.MEDIUM]
            < normalized[AutomaticIntensity.STRONG]
        ):
            raise ValueError("Automatic thresholds must be strictly increasing")
        object.__setattr__(self, "thresholds", normalized)

    def decide(self, quantity: Decimal, intensity: AutomaticIntensity) -> FilterDecision:
        parsed = _nonnegative(quantity, "quantity")
        selected = AutomaticIntensity(intensity)
        threshold = self.thresholds[selected]
        reason = (
            FilterDecisionReason.ACCEPT
            if parsed >= threshold
            else FilterDecisionReason.REJECT_BELOW_MIN
        )
        return FilterDecision(
            accepted=reason is FilterDecisionReason.ACCEPT,
            reason=reason,
            threshold_used=threshold,
            max_threshold_used=ZERO,
            filter_mode=FilterMode.AUTOMATIC,
            intensity=selected,
            calibration_id=self.calibration_id,
        )


def decide_cluster(
    cluster: ExecutionCluster,
    automatic_filter: Optional[AutomaticSizeFilter] = None,
) -> FilterDecision:
    settings = cluster.settings
    if settings.filter_mode is FilterMode.MANUAL:
        return ManualSizeFilter(
            settings.manual_min_quantity,
            settings.manual_max_quantity,
        ).decide(cluster.aggregate_quantity)
    if automatic_filter is None or settings.calibration_id is None:
        return FilterDecision(
            accepted=False,
            reason=FilterDecisionReason.AUTOMATIC_UNAVAILABLE,
            threshold_used=ZERO,
            max_threshold_used=ZERO,
            filter_mode=FilterMode.AUTOMATIC,
            intensity=settings.automatic_intensity,
            calibration_id=settings.calibration_id,
        )
    if automatic_filter.calibration_id != settings.calibration_id:
        return FilterDecision(
            accepted=False,
            reason=FilterDecisionReason.AUTOMATIC_UNAVAILABLE,
            threshold_used=ZERO,
            max_threshold_used=ZERO,
            filter_mode=FilterMode.AUTOMATIC,
            intensity=settings.automatic_intensity,
            calibration_id=settings.calibration_id,
        )
    return automatic_filter.decide(cluster.aggregate_quantity, settings.automatic_intensity)
