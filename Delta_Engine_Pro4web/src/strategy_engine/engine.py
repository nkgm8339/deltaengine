"""Strategy Engine body for the representative variant.

Flow per event:

    EngineInputEvent
      -> PredicateEvaluator (market predicate: holds + calibration + hard source)
      -> build a ContractEvent transition attempt
      -> ContractEnforcer.submit()  (the transition contract gate)
      -> EngineDecision (STAY | TRANSITION with the enforcer StepResult)

The Engine never decides accept/reject itself: it delegates to the enforcer, so
judgement contracts 1-9 and the R1-R8 rejection tests are inherited structurally.

Edge calibration policy:
- LOCATION_ARM / ADVANCE / INVALIDATE  -> market predicates, gated by the
  CalibrationBook (empty => UNVALIDATED => enforcer rejects UNCALIBRATED_EDGE).
- TERMINAL / EXPIRE                     -> engine lifecycle, CALIBRATED by
  construction (no market threshold). They are only reachable after the market
  advances, which cannot happen while uncalibrated -- so runtime firing stays 0.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from src.orderflow.hooks.models import CalibrationStatus
from src.strategy_contract.enforcer import (
    ContractEnforcer,
    InstancePhase,
    OrderReadyHandoff,
    StepResult,
)
from src.strategy_contract.events import ContractEvent

from .events import EngineInputEvent, EventSource
from .predicate_eval import PredicateEvaluator, StubPredicateEvaluator
from .variant_runtime import RepresentativeVariant

_MARKET_PREDICATE_EDGES = frozenset({"LOCATION_ARM", "ADVANCE", "INVALIDATE"})
_LIFECYCLE_EDGES = frozenset({"TERMINAL", "EXPIRE"})
# Predicate evaluation may block an advance/invalidation without it being a
# contract violation; these edge types "stay" when the predicate does not hold.
_STAYABLE_EDGES = frozenset({"ADVANCE", "INVALIDATE"})


class EngineOutcome(str, Enum):
    STAY = "STAY"  # predicate did not hold; no transition attempted
    TRANSITION = "TRANSITION"  # a transition was attempted (see step for verdict)
    UNKNOWN_EDGE = "UNKNOWN_EDGE"


@dataclass(frozen=True)
class EngineDecision:
    outcome: EngineOutcome
    edge_id: str
    phase: InstancePhase
    step: StepResult | None = None
    handoff: OrderReadyHandoff | None = None


@dataclass
class EngineReport:
    decisions: list[EngineDecision] = field(default_factory=list)
    handoffs: list[OrderReadyHandoff] = field(default_factory=list)

    @property
    def order_intents(self) -> int:
        # No order path exists. Terminal outputs are gate handoffs only.
        return 0


class StrategyEngine:
    """Drives one Observation Instance of the representative variant."""

    def __init__(
        self,
        variant: RepresentativeVariant,
        *,
        observation_instance_id: str,
        evaluator: PredicateEvaluator | None = None,
        expiry_after_ns: int | None = None,
    ) -> None:
        self.variant = variant
        self.evaluator: PredicateEvaluator = evaluator or StubPredicateEvaluator()
        enforcer_kwargs = {"observation_instance_id": observation_instance_id}
        if expiry_after_ns is not None:
            enforcer_kwargs["expiry_after_ns"] = expiry_after_ns
        self._enforcer = ContractEnforcer(variant.contract, **enforcer_kwargs)

    @property
    def phase(self) -> InstancePhase:
        return self._enforcer.phase

    def on_event(self, event: EngineInputEvent) -> EngineDecision:
        spec = self.variant.spec(event.edge_id)
        if spec is None:
            return EngineDecision(
                outcome=EngineOutcome.UNKNOWN_EDGE,
                edge_id=event.edge_id,
                phase=self._enforcer.phase,
            )

        if spec.edge_type in _LIFECYCLE_EDGES:
            calibration_status = CalibrationStatus.CALIBRATED
            hard_source_status = "OK"
            holds = True
        else:  # market predicate edge
            verdict = self.evaluator.evaluate(
                spec.predicate_id, spec.predicate_classes, event.observation
            )
            calibration_status = verdict.calibration_status
            hard_source_status = verdict.hard_source_status
            holds = verdict.holds

        is_calibrated = calibration_status is CalibrationStatus.CALIBRATED

        # A calibrated-but-non-holding advance/invalidation predicate is "not yet",
        # not a violation: stay without attempting a transition. An *uncalibrated*
        # edge is NOT stayed -- it is attempted so the enforcer rejects it with
        # UNCALIBRATED_EDGE (contract R7), keeping runtime firing 0.
        if spec.edge_type in _STAYABLE_EDGES and is_calibrated and not holds:
            return EngineDecision(
                outcome=EngineOutcome.STAY,
                edge_id=event.edge_id,
                phase=self._enforcer.phase,
            )

        contract_event = ContractEvent(
            event_id=f"{event.source_event_id}:{event.edge_id}",
            source_event_id=event.source_event_id,
            edge_id=event.edge_id,
            source_time=event.source_time,
            received_time=event.received_time,
            engine_time_ns=event.engine_time_ns,
            calibration_status=calibration_status,
            detector_status=event.detector_status,
            route_role=event.route_role,
            hard_source_status=hard_source_status,
            arm_location_confirmed=event.observation.location_confirmed,
            arm_first_predicate_confirmed=event.observation.first_predicate_confirmed,
            arm_freshness_ok=event.observation.freshness_ok,
        )
        step = self._enforcer.submit(contract_event)
        return EngineDecision(
            outcome=EngineOutcome.TRANSITION,
            edge_id=event.edge_id,
            phase=self._enforcer.phase,
            step=step,
            handoff=step.handoff,
        )

    def run(self, source: EventSource) -> EngineReport:
        report = EngineReport()
        for event in source:
            decision = self.on_event(event)
            report.decisions.append(decision)
            if decision.handoff is not None:
                report.handoffs.append(decision.handoff)
        return report
