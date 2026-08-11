"""Pure Automatic Size Filter calibration math."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal, localcontext
from typing import Iterable, Mapping, Optional, Sequence

from .constants import AutomaticIntensity, CalibrationStatus


ZERO = Decimal("0")
ONE = Decimal("1")
LOW_FACTOR = Decimal("0.75")
HIGH_FACTOR = Decimal("1.50")


@dataclass(frozen=True)
class SessionQuantityDistribution:
    session_id: str
    cluster_quantities: tuple[Decimal, ...]
    session_volatility: Optional[Decimal]
    valid: bool = True

    def __post_init__(self) -> None:
        quantities = tuple(Decimal(str(value)) for value in self.cluster_quantities)
        if any(not value.is_finite() or value <= ZERO for value in quantities):
            raise ValueError("cluster quantities must be finite and positive")
        object.__setattr__(self, "cluster_quantities", quantities)
        if self.session_volatility is not None:
            volatility = Decimal(str(self.session_volatility))
            if not volatility.is_finite() or volatility < ZERO:
                raise ValueError("session volatility must be finite and non-negative")
            object.__setattr__(self, "session_volatility", volatility)


@dataclass(frozen=True)
class CalibrationResult:
    status: CalibrationStatus
    thresholds: Optional[Mapping[AutomaticIntensity, Decimal]]
    base_thresholds: Optional[Mapping[AutomaticIntensity, Decimal]]
    volatility_factor: Decimal
    volatility_status: str
    baseline_volatility: Optional[Decimal]
    recent_volatility: Optional[Decimal]
    valid_session_counts: Mapping[AutomaticIntensity, int]
    history_session_ids: tuple[str, ...]


def decimal_median(values: Iterable[Decimal]) -> Decimal:
    ordered = sorted(Decimal(str(value)) for value in values)
    if not ordered:
        raise ValueError("median requires at least one value")
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / Decimal("2")


def ceil_to_step(value: Decimal, step: Decimal) -> Decimal:
    parsed = Decimal(str(value))
    quantum = Decimal(str(step))
    if not parsed.is_finite() or parsed < ZERO:
        raise ValueError("value must be finite and non-negative")
    if not quantum.is_finite() or quantum <= ZERO:
        raise ValueError("step must be finite and positive")
    units = (parsed / quantum).to_integral_value(rounding=ROUND_CEILING)
    return units * quantum


def session_rank(quantities: Sequence[Decimal], rank: int) -> Optional[Decimal]:
    if not isinstance(rank, int) or isinstance(rank, bool) or rank < 1:
        raise ValueError("rank must be a positive integer")
    ordered = sorted((Decimal(str(value)) for value in quantities), reverse=True)
    if len(ordered) < rank:
        return None
    return ordered[rank - 1]


def normalized_true_range(
    high: Decimal,
    low: Decimal,
    close: Decimal,
    previous_close: Decimal,
) -> Decimal:
    values = tuple(Decimal(str(value)) for value in (high, low, close, previous_close))
    if any(not value.is_finite() or value <= ZERO for value in values):
        raise ValueError("OHLC values must be finite and positive")
    high_value, low_value, close_value, previous_value = values
    if high_value < low_value:
        raise ValueError("high must be >= low")
    true_range = max(
        high_value - low_value,
        abs(high_value - previous_value),
        abs(low_value - previous_value),
    )
    return true_range / close_value


def calibrate(
    sessions: Sequence[SessionQuantityDistribution],
    *,
    quantity_step: Decimal,
    minimum_valid_sessions: int = 10,
) -> CalibrationResult:
    step = Decimal(str(quantity_step))
    if not step.is_finite() or step <= ZERO:
        raise ValueError("quantity_step must be finite and positive")
    if minimum_valid_sessions < 1:
        raise ValueError("minimum_valid_sessions must be >= 1")
    history = tuple(session for session in sessions if session.valid)[-20:]
    rank_numbers = {
        AutomaticIntensity.LOW: 20,
        AutomaticIntensity.MEDIUM: 9,
        AutomaticIntensity.STRONG: 2,
    }
    ranked: dict[AutomaticIntensity, list[Decimal]] = {key: [] for key in AutomaticIntensity}
    for session in history:
        for intensity, rank in rank_numbers.items():
            value = session_rank(session.cluster_quantities, rank)
            if value is not None:
                ranked[intensity].append(value)
    counts = {intensity: len(values) for intensity, values in ranked.items()}
    if any(count < minimum_valid_sessions for count in counts.values()):
        return CalibrationResult(
            status=CalibrationStatus.INSUFFICIENT_HISTORY,
            thresholds=None,
            base_thresholds=None,
            volatility_factor=ONE,
            volatility_status="VOLATILITY_FALLBACK_1",
            baseline_volatility=None,
            recent_volatility=None,
            valid_session_counts=counts,
            history_session_ids=tuple(session.session_id for session in history),
        )

    base = {intensity: decimal_median(values) for intensity, values in ranked.items()}
    volatility_values = [
        session.session_volatility
        for session in history
        if session.session_volatility is not None
    ]
    if len(volatility_values) < 20:
        factor = ONE
        volatility_status = "VOLATILITY_FALLBACK_1"
        baseline = None
        recent = None
    else:
        baseline = decimal_median(volatility_values[-20:])
        recent = decimal_median(volatility_values[-5:])
        if baseline <= ZERO:
            factor = ONE
            volatility_status = "VOLATILITY_FALLBACK_1"
        else:
            with localcontext() as context:
                context.prec = 38
                factor = (recent / baseline).sqrt()
            factor = min(HIGH_FACTOR, max(LOW_FACTOR, factor))
            volatility_status = "VOLATILITY_APPLIED"

    low = ceil_to_step(base[AutomaticIntensity.LOW] * factor, step)
    medium = max(
        ceil_to_step(base[AutomaticIntensity.MEDIUM] * factor, step),
        low + step,
    )
    strong = max(
        ceil_to_step(base[AutomaticIntensity.STRONG] * factor, step),
        medium + step,
    )
    thresholds = {
        AutomaticIntensity.LOW: low,
        AutomaticIntensity.MEDIUM: medium,
        AutomaticIntensity.STRONG: strong,
    }
    return CalibrationResult(
        status=CalibrationStatus.VALID,
        thresholds=thresholds,
        base_thresholds=base,
        volatility_factor=factor,
        volatility_status=volatility_status,
        baseline_volatility=baseline,
        recent_volatility=recent,
        valid_session_counts=counts,
        history_session_ids=tuple(session.session_id for session in history),
    )
