"""T4-T5: Predicate Evaluator stub and CalibrationBook fail-closed behaviour.

T4: normal operation (empty book) -> UNVALIDATED -> the enforcer rejects the edge
    with UNCALIBRATED_EDGE (contract R7-a); no instance can arm or advance.
T5: injecting a calibrated book runs the predicate logic and returns its verdict.
"""

from __future__ import annotations

from src.orderflow.hooks.models import CalibrationStatus
from src.strategy_contract.enforcer import InstancePhase
from src.strategy_contract.rejection_codes import RejectReason
from src.strategy_engine.engine import EngineOutcome, StrategyEngine
from src.strategy_engine.events import PredicateObservation
from src.strategy_engine.predicate_eval import (
    CalibrationBook,
    StubPredicateEvaluator,
)

from ._helpers import (
    MARKET_PREDICATE_IDS,
    advance_events,
    arm_event,
    calibrated_evaluator,
    load_variant,
    make_event,
    uncalibrated_evaluator,
)


# --- T4: fail-closed / normal operation cannot fire -------------------------

def test_T4_calibration_book_defaults_to_uncalibrated():
    book = CalibrationBook()
    assert book.is_empty
    assert book.status("OPR-019") is CalibrationStatus.UNCALIBRATED
    assert book.is_calibrated("OPR-019") is False


def test_T4_uncalibrated_evaluator_reports_unvalidated():
    evaluator = uncalibrated_evaluator()
    verdict = evaluator.evaluate(
        "OPR-019", ("FLOW_PRICE_DIVERGENCE",), PredicateObservation(holds=True)
    )
    # Even though the scenario predicate "holds", it is not calibrated.
    assert verdict.holds is True
    assert verdict.is_calibrated is False


def test_T4_engine_arm_rejected_when_uncalibrated():
    engine = StrategyEngine(
        load_variant(),
        observation_instance_id="T4",
        evaluator=uncalibrated_evaluator(),
    )
    decision = engine.on_event(arm_event())
    # The engine attempts the transition; the enforcer rejects it (contract R7-a).
    assert decision.outcome is EngineOutcome.TRANSITION
    assert decision.step.reason is RejectReason.UNCALIBRATED_EDGE
    assert engine.phase is InstancePhase.UNARMED


# --- T5: calibrated injection runs the predicate logic ----------------------

def test_T5_calibrated_book_marks_predicates_calibrated():
    book = CalibrationBook.all_calibrated(MARKET_PREDICATE_IDS)
    assert book.is_calibrated("OPR-019") is True
    # A predicate outside the book still defaults to uncalibrated.
    assert book.is_calibrated("OPR-999") is False


def test_T5_calibrated_evaluator_runs_and_passes_through_verdict():
    evaluator = calibrated_evaluator()
    holds = evaluator.evaluate(
        "OPR-020", ("ABSORPTION_STATE",), PredicateObservation(holds=True)
    )
    assert holds.holds is True and holds.is_calibrated is True

    not_holds = evaluator.evaluate(
        "OPR-020", ("ABSORPTION_STATE",), PredicateObservation(holds=False)
    )
    assert not_holds.holds is False and not_holds.is_calibrated is True

    stale = evaluator.evaluate(
        "OPR-022",
        ("OPEN_INTEREST_CHANGE",),
        PredicateObservation(holds=True, hard_source_status="STALE"),
    )
    assert stale.hard_source_status == "STALE"


def test_T5_engine_advance_stays_when_predicate_does_not_hold():
    engine = StrategyEngine(
        load_variant(),
        observation_instance_id="T5",
        evaluator=calibrated_evaluator(),
    )
    assert engine.on_event(arm_event()).step.accepted

    first_advance = advance_events()[0]
    # Predicate does not hold -> Engine stays (no transition attempted).
    stay = engine.on_event(
        make_event("E01", source_event_id="adv1", source_s=1.0, engine_ns=1_000_000, holds=False)
    )
    assert stay.outcome is EngineOutcome.STAY
    assert stay.step is None
    assert engine.phase is InstancePhase.ARMED

    # Predicate holds -> advance proceeds.
    go = engine.on_event(first_advance)
    assert go.outcome is EngineOutcome.TRANSITION and go.step.accepted
