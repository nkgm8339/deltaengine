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
from types import MappingProxyType
from typing import Mapping, Protocol, runtime_checkable

from src.orderflow.hooks.models import CalibrationStatus

from .events import PredicateObservation


class CalibrationBook:
    """Fail-closed calibration lookup for predicates.

    A missing predicate_id returns ``default_status`` (UNCALIBRATED), so an empty
    book means nothing is calibrated and nothing can fire. Thresholds are never
    hardcoded; calibrated values are supplied by constructing a populated book.
    """

    def __init__(
        self,
        calibrations: Mapping[str, CalibrationStatus] | None = None,
        *,
        default_status: CalibrationStatus = CalibrationStatus.UNCALIBRATED,
    ) -> None:
        self._calibrations = MappingProxyType(dict(calibrations or {}))
        self.default_status = default_status

    def status(self, predicate_id: str) -> CalibrationStatus:
        return self._calibrations.get(predicate_id, self.default_status)

    def is_calibrated(self, predicate_id: str) -> bool:
        return self.status(predicate_id) is CalibrationStatus.CALIBRATED

    @property
    def is_empty(self) -> bool:
        return len(self._calibrations) == 0

    @classmethod
    def all_calibrated(cls, predicate_ids: tuple[str, ...]) -> "CalibrationBook":
        """Test helper: a book that marks the given predicate ids CALIBRATED."""
        return cls({pid: CalibrationStatus.CALIBRATED for pid in predicate_ids})


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
