"""P9-P10: Engine integrated with the RealPredicateEvaluator.

P9: with a calibrated book and passing condition snapshots, the representative
    variant runs arm -> advance x4 -> terminal to a SHORT_READY handoff.
P10: a calibrated-but-non-holding advance makes the Engine STAY (no transition),
    while an uncalibrated edge is still rejected with UNCALIBRATED_EDGE (R7).
"""

from __future__ import annotations

from decimal import Decimal

from src.strategy_contract.enforcer import InstancePhase, OrderReadyHandoff
from src.strategy_contract.rejection_codes import RejectReason
from src.strategy_engine.engine import EngineOutcome, StrategyEngine
from src.strategy_engine.real_predicate_eval import RealPredicateEvaluator
from src.strategy_engine.predicate_eval import CalibrationBook

from ._helpers import (
    load_variant,
    make_event,
    real_advance_events,
    real_arm_event,
    real_evaluator,
    terminal_event,
)


def _engine(evaluator, **kwargs) -> StrategyEngine:
    return StrategyEngine(
        load_variant(),
        observation_instance_id="REAL-1",
        evaluator=evaluator,
        **kwargs,
    )


def test_P9_full_path_with_real_evaluator_reaches_short_ready():
    engine = _engine(real_evaluator())
    report = engine.run([real_arm_event(), *real_advance_events(), terminal_event()])

    assert all(d.outcome is EngineOutcome.TRANSITION for d in report.decisions)
    assert all(d.step.accepted for d in report.decisions), [
        (d.edge_id, d.step.reason) for d in report.decisions if not d.step.accepted
    ]
    assert engine.phase is InstancePhase.TERMINAL
    assert len(report.handoffs) == 1
    assert isinstance(report.handoffs[0], OrderReadyHandoff)
    assert report.handoffs[0].direction == "SHORT_READY"
    assert report.order_intents == 0


def test_P10_stay_when_calibrated_but_predicate_does_not_hold():
    engine = _engine(real_evaluator())
    assert engine.on_event(real_arm_event()).step.accepted

    # cvd_change_5s = -4 does not clear the <= -5 threshold -> STAY.
    stay = engine.on_event(
        make_event(
            "E01",
            source_event_id="adv1",
            source_s=1.0,
            engine_ns=1_000_000,
            conditions={"cvd_change_5s": Decimal("-4")},
        )
    )
    assert stay.outcome is EngineOutcome.STAY
    assert stay.step is None
    assert engine.phase is InstancePhase.ARMED

    # A passing snapshot then advances.
    go = engine.on_event(real_advance_events()[0])
    assert go.outcome is EngineOutcome.TRANSITION and go.step.accepted


def test_P10_uncalibrated_edge_still_rejected_not_stayed():
    # Empty book: even a "would-hold" advance is attempted and rejected (R7),
    # never silently stayed. First arm is impossible uncalibrated, so drive the
    # arm on a calibrated LOC while leaving advances uncalibrated.
    engine = _engine(RealPredicateEvaluator(CalibrationBook()))
    arm = engine.on_event(real_arm_event())
    # Arm itself is uncalibrated here -> rejected, instance stays UNARMED.
    assert arm.outcome is EngineOutcome.TRANSITION
    assert arm.step.reason is RejectReason.UNCALIBRATED_EDGE
    assert engine.phase is InstancePhase.UNARMED
