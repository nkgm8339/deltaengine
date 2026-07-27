"""Real Predicate Evaluator skeleton (representative variant, 9 classes).

Implements the same ``PredicateEvaluator`` protocol as the Stub, but derives the
verdict from the condition snapshot on the observation using calibrated
comparators supplied by the CalibrationBook. No threshold value is hardcoded; all
comparison parameters come from ``PredicateCalibration`` entries.

Evaluation (market predicates), fail-closed:
- uncalibrated predicate -> verdict.holds = False and status is non-CALIBRATED, so
  the Engine attempts and the enforcer rejects with UNCALIBRATED_EDGE (contract R7).
- calibrated predicate -> holds = (any required atom passes) AND (no contradiction
  atom passes). Required atoms are OR routes; contradiction atoms veto.

Lifecycle classes (ENGINE_TERMINAL / ENGINE_EXPIRY) are handled by the Engine, not
here; COMPOSITE_INVALIDATION uses the same any-atom / veto machinery.
"""

from __future__ import annotations

from typing import Mapping

from src.orderflow.hooks.models import CalibrationStatus

from .events import PredicateObservation
from .predicate_eval import CalibrationBook, PredicateVerdict
from .predicate_spec import PredicateClassSpec, load_class_specs


class RealPredicateEvaluator:
    """Condition-snapshot evaluator gated by calibrated comparators."""

    def __init__(
        self,
        calibration: CalibrationBook,
        specs: Mapping[str, PredicateClassSpec] | None = None,
    ) -> None:
        self.calibration = calibration
        self.specs = specs if specs is not None else load_class_specs()

    def evaluate(
        self,
        predicate_id: str,
        predicate_classes: tuple[str, ...],
        observation: PredicateObservation,
    ) -> PredicateVerdict:
        status = self.calibration.status(predicate_id)
        hard = observation.hard_source_status

        if status is not CalibrationStatus.CALIBRATED:
            # Uncalibrated: cannot fire; the enforcer will reject with
            # UNCALIBRATED_EDGE when the Engine attempts the edge.
            return PredicateVerdict(
                predicate_id=predicate_id,
                holds=False,
                calibration_status=status,
                hard_source_status=hard,
            )

        entry = self.calibration.calibration(predicate_id)
        if entry is None or not entry.atoms:
            # Calibrated status without comparators is a misconfiguration; stay
            # fail-closed rather than advancing on nothing.
            holds = False
        else:
            conditions = observation.conditions
            required_pass = any(atom.passes(conditions) for atom in entry.atoms)
            veto = any(atom.passes(conditions) for atom in entry.contradiction_atoms)
            holds = required_pass and not veto

        return PredicateVerdict(
            predicate_id=predicate_id,
            holds=holds,
            calibration_status=status,
            hard_source_status=hard,
        )
