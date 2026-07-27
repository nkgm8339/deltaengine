"""Predicate Evaluator stub and fail-closed CalibrationBook.

The evaluator gates market predicates on calibration and surfaces the scenario
verdict. Thresholds/comparators are NOT implemented here (out of scope,
uncalibrated). The CalibrationBook mirrors the existing ThresholdBook pattern
(fail-closed, default non-CALIBRATED) so that:

- normal operation (empty book) -> every market predicate is UNVALIDATED, and
  the enforcer rejects the edge with UNCALIBRATED_EDGE (contract R7-a);
- tests inject a calibrated book to exercise the predicate logic itself.

"UNVALIDATED" (the binding-CSV vocabulary) maps to any non-CALIBRATED
``CalibrationStatus`` here; only CALIBRATED may fire (models.HookThreshold.allows_fire).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping, Protocol, runtime_checkable

from src.orderflow.hooks.models import CalibrationStatus

from .events import PredicateObservation

_VALID_OPERATORS = frozenset({"ge", "gt", "le", "lt"})


@dataclass(frozen=True)
class ConditionAtom:
    """One calibrated comparator over a single condition key.

    The threshold value is supplied via calibration only; nothing is hardcoded.
    ``passes`` is fail-closed: a missing or non-finite condition value never passes.
    """

    condition_key: str
    operator: str
    threshold: Decimal

    def __post_init__(self) -> None:
        if not self.condition_key:
            raise ValueError("condition_key must be non-empty")
        if self.operator not in _VALID_OPERATORS:
            raise ValueError(f"unsupported operator: {self.operator}")
        threshold = (
            self.threshold
            if isinstance(self.threshold, Decimal)
            else Decimal(str(self.threshold))
        )
        if not threshold.is_finite():
            raise ValueError("threshold must be finite")
        object.__setattr__(self, "threshold", threshold)

    def passes(self, conditions: Mapping[str, Decimal]) -> bool:
        raw = conditions.get(self.condition_key)
        if raw is None:
            return False
        try:
            value = raw if isinstance(raw, Decimal) else Decimal(str(raw))
        except (TypeError, ValueError, ArithmeticError):
            return False
        if not value.is_finite():
            return False
        if self.operator == "ge":
            return value >= self.threshold
        if self.operator == "gt":
            return value > self.threshold
        if self.operator == "le":
            return value <= self.threshold
        return value < self.threshold


@dataclass(frozen=True)
class PredicateCalibration:
    """Calibrated comparator set for one predicate.

    ``atoms`` are OR routes (candidates are material routes, not simultaneous
    votes -- class registry contract). ``contradiction_atoms`` veto the predicate
    when any of them holds (判定契約5 allows reverse-comparator material).
    """

    predicate_id: str
    status: CalibrationStatus
    atoms: tuple[ConditionAtom, ...] = ()
    contradiction_atoms: tuple[ConditionAtom, ...] = ()

    def __post_init__(self) -> None:
        if not self.predicate_id:
            raise ValueError("predicate_id must be non-empty")


class CalibrationBook:
    """Fail-closed calibration lookup for predicates.

    A missing predicate_id returns ``default_status`` (UNCALIBRATED), so an empty
    book means nothing is calibrated and nothing can fire. Thresholds are never
    hardcoded; calibrated values are supplied by constructing a populated book.

    Backward compatible: constructed either from a plain ``predicate_id ->
    CalibrationStatus`` map (status-only, used by the Stub tests) or from a
    ``predicate_id -> PredicateCalibration`` map (full comparators).
    """

    def __init__(
        self,
        calibrations: Mapping[str, CalibrationStatus] | None = None,
        *,
        default_status: CalibrationStatus = CalibrationStatus.UNCALIBRATED,
        predicate_calibrations: Mapping[str, PredicateCalibration] | None = None,
    ) -> None:
        self._calibrations = MappingProxyType(dict(calibrations or {}))
        self._predicate_calibrations = MappingProxyType(
            dict(predicate_calibrations or {})
        )
        self.default_status = default_status

    def status(self, predicate_id: str) -> CalibrationStatus:
        entry = self._predicate_calibrations.get(predicate_id)
        if entry is not None:
            return entry.status
        return self._calibrations.get(predicate_id, self.default_status)

    def is_calibrated(self, predicate_id: str) -> bool:
        return self.status(predicate_id) is CalibrationStatus.CALIBRATED

    def calibration(self, predicate_id: str) -> PredicateCalibration | None:
        return self._predicate_calibrations.get(predicate_id)

    @property
    def is_empty(self) -> bool:
        return not self._calibrations and not self._predicate_calibrations

    @classmethod
    def all_calibrated(cls, predicate_ids: tuple[str, ...]) -> "CalibrationBook":
        """Test helper: a status-only book marking the given ids CALIBRATED."""
        return cls({pid: CalibrationStatus.CALIBRATED for pid in predicate_ids})

    @classmethod
    def from_calibrations(
        cls, calibrations: tuple[PredicateCalibration, ...]
    ) -> "CalibrationBook":
        """Build a book from full predicate comparators."""
        return cls(predicate_calibrations={c.predicate_id: c for c in calibrations})


@dataclass(frozen=True)
class PredicateVerdict:
    predicate_id: str
    holds: bool
    calibration_status: CalibrationStatus
    hard_source_status: str = "OK"

    @property
    def is_calibrated(self) -> bool:
        return self.calibration_status is CalibrationStatus.CALIBRATED


@runtime_checkable
class PredicateEvaluator(Protocol):
    def evaluate(
        self,
        predicate_id: str,
        predicate_classes: tuple[str, ...],
        observation: PredicateObservation,
    ) -> PredicateVerdict:
        ...


class StubPredicateEvaluator:
    """Scenario-driven evaluator: gates on the CalibrationBook and surfaces the
    observation's intended verdict. It computes no market maths (out of scope)."""

    def __init__(self, calibration: CalibrationBook | None = None) -> None:
        self.calibration = calibration or CalibrationBook()

    def evaluate(
        self,
        predicate_id: str,
        predicate_classes: tuple[str, ...],
        observation: PredicateObservation,
    ) -> PredicateVerdict:
        return PredicateVerdict(
            predicate_id=predicate_id,
            holds=observation.holds,
            calibration_status=self.calibration.status(predicate_id),
            hard_source_status=observation.hard_source_status,
        )
