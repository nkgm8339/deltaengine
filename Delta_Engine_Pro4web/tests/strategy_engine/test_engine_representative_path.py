"""T1-T3: representative variant end-to-end through the Strategy Engine.

The Engine composes the contract enforcer as its transition gate. With a
calibrated evaluator injected (test only), a well-formed sequence reaches a
SHORT_READY handoff; invalidation and expiry terminate the instance and never
produce an order intent.
"""

from __future__ import annotations

from src.strategy_contract.enforcer import InstancePhase, OrderReadyHandoff
from src.strategy_contract.rejection_codes import RejectReason
from src.strategy_engine.engine import EngineOutcome, StrategyEngine

from ._helpers import (
    S_NS,
    advance_events,
    arm_event,
    calibrated_evaluator,
    load_variant,
    make_event,
    terminal_event,
)


def _engine(**kwargs) -> StrategyEngine:
    return StrategyEngine(
        load_variant(),
        observation_instance_id="ENG-1",
        evaluator=calibrated_evaluator(),
        **kwargs,
    )


def test_variant_runtime_exposes_representative_predicate_ids():
    variant = load_variant()
    ids = variant.predicate_ids()
    for pid in ("LOC::VISIBLE_BOOK_WALL", "OPR-019", "OPR-020", "OPR-021", "OPR-022", "INV-005"):
        assert pid in ids
    # E04 is the OI hard-source-required advance.
    assert variant.spec(f"{variant.contract.variant_id}::E04").hard_source_required is True


def test_T1_full_path_reaches_short_ready_handoff():
    engine = _engine()
    report = engine.run([arm_event(), *advance_events(), terminal_event()])

    assert all(d.outcome is EngineOutcome.TRANSITION for d in report.decisions)
    assert all(d.step.accepted for d in report.decisions), [
        (d.edge_id, d.step.reason) for d in report.decisions if not d.step.accepted
    ]
    assert engine.phase is InstancePhase.TERMINAL
    assert len(report.handoffs) == 1
    assert isinstance(report.handoffs[0], OrderReadyHandoff)
    assert report.handoffs[0].direction == "SHORT_READY"
    assert report.order_intents == 0


def test_T2_invalidation_midway_terminates_instance():
    engine = _engine()
    assert engine.on_event(arm_event()).step.accepted
    assert engine.on_event(advance_events()[0]).step.accepted  # at S01

    invalidate = make_event(
        "E98", source_event_id="inv", source_s=1.5, engine_ns=2_000_000
    )
    inv_decision = engine.on_event(invalidate)
    assert inv_decision.step.accepted
    assert engine.phase is InstancePhase.INVALIDATED

    # Any further advance is rejected; the instance does not revive.
    resume = make_event("E02", source_event_id="adv2b", source_s=3.0, engine_ns=3_000_000)
    resumed = engine.on_event(resume)
    assert resumed.step.reason is RejectReason.INSTANCE_TERMINATED_BY_INVALIDATION
    assert resumed.handoff is None
    assert engine.phase is InstancePhase.INVALIDATED


def test_T3_expiry_terminates_without_order_intent():
    engine = _engine(expiry_after_ns=60 * S_NS)
    assert engine.on_event(arm_event()).step.accepted

    expire = make_event("E99", source_event_id="exp", source_s=1.0, engine_ns=70 * S_NS)
    report = engine.run([expire])

    assert report.decisions[-1].step.accepted
    assert engine.phase is InstancePhase.EXPIRED
    assert report.handoffs == []
    assert report.order_intents == 0


def test_T3_advance_after_deadline_is_expired():
    engine = _engine(expiry_after_ns=60 * S_NS)
    assert engine.on_event(arm_event()).step.accepted
    late = make_event("E01", source_event_id="adv1", source_s=1.0, engine_ns=70 * S_NS)
    decision = engine.on_event(late)
    assert decision.step.reason is RejectReason.INSTANCE_EXPIRED
    assert engine.phase is InstancePhase.EXPIRED
