"""P1-P8: RealPredicateEvaluator logic (representative variant, 9 classes).

Each market predicate is evaluated from a condition snapshot using calibrated
comparators. Tests exercise the threshold boundary, the OR-route and
contradiction-veto structure, hard-source passthrough, and the fail-closed
empty-book behaviour (UNVALIDATED maintained).
"""

from __future__ import annotations

from decimal import Decimal

from src.orderflow.hooks.models import CalibrationStatus
from src.strategy_engine.events import PredicateObservation
from src.strategy_engine.predicate_eval import (
    CalibrationBook,
    ConditionAtom,
    PredicateCalibration,
)
from src.strategy_engine.predicate_spec import load_class_specs
from src.strategy_engine.real_predicate_eval import RealPredicateEvaluator

from ._helpers import real_evaluator


def _obs(conditions=None, *, hard="OK") -> PredicateObservation:
    return PredicateObservation(conditions=dict(conditions or {}), hard_source_status=hard)


# --- P1-P5: boundary + OR route + contradiction veto per market class -------

def test_P1_flow_price_divergence_boundary_and_veto():
    ev = real_evaluator()
    # boundary: cvd_change_5s <= -5 passes at exactly -5, fails at -4.
    assert ev.evaluate("OPR-019", ("FLOW_PRICE_DIVERGENCE",), _obs({"cvd_change_5s": Decimal("-5")})).holds
    assert not ev.evaluate("OPR-019", ("FLOW_PRICE_DIVERGENCE",), _obs({"cvd_change_5s": Decimal("-4")})).holds
    # contradiction veto: follow-through present cancels the divergence.
    veto = ev.evaluate(
        "OPR-019",
        ("FLOW_PRICE_DIVERGENCE",),
        _obs({"cvd_change_5s": Decimal("-9"), "downside_breakout_follow_through": Decimal("1")}),
    )
    assert veto.holds is False


def test_P2_absorption_state_boundary():
    ev = real_evaluator()
    assert ev.evaluate("OPR-020", ("ABSORPTION_STATE",), _obs({"buy_no_progress_ratio_1s": Decimal("0.8")})).holds
    assert not ev.evaluate("OPR-020", ("ABSORPTION_STATE",), _obs({"buy_no_progress_ratio_1s": Decimal("0.79")})).holds
    veto = ev.evaluate(
        "OPR-020",
        ("ABSORPTION_STATE",),
        _obs({"buy_no_progress_ratio_1s": Decimal("0.95"), "bid_passive_defense_failed": Decimal("1")}),
    )
    assert veto.holds is False


def test_P3_break_attempt_wall_state_boundary():
    ev = real_evaluator()
    assert ev.evaluate("OPR-021", ("BREAK_ATTEMPT", "WALL_STATE"), _obs({"downward_progress_ticks_1s": Decimal("3")})).holds
    assert not ev.evaluate("OPR-021", ("BREAK_ATTEMPT", "WALL_STATE"), _obs({"downward_progress_ticks_1s": Decimal("2")})).holds


def test_P4_open_interest_change_sign_and_hard_source_passthrough():
    ev = real_evaluator()
    down = ev.evaluate("OPR-022", ("OPEN_INTEREST_CHANGE",), _obs({"open_interest_change_5m": Decimal("-1")}))
    assert down.holds
    # sign boundary + contradiction (positive OI) veto
    up = ev.evaluate("OPR-022", ("OPEN_INTEREST_CHANGE",), _obs({"open_interest_change_5m": Decimal("5")}))
    assert up.holds is False
    # hard-source status is passed through for the enforcer's contract-9 check.
    stale = ev.evaluate(
        "OPR-022",
        ("OPEN_INTEREST_CHANGE",),
        _obs({"open_interest_change_5m": Decimal("-3")}, hard="STALE"),
    )
    assert stale.holds is True and stale.hard_source_status == "STALE"


def test_P5_composite_invalidation_any_atom():
    ev = real_evaluator()
    fired = ev.evaluate("INV-005", ("COMPOSITE_INVALIDATION",), _obs({"bid_wall_concentration_top10": Decimal("120")}))
    assert fired.holds
    not_fired = ev.evaluate("INV-005", ("COMPOSITE_INVALIDATION",), _obs({"bid_wall_concentration_top10": Decimal("50")}))
    assert not_fired.holds is False


# --- P6: missing condition material is fail-closed ---------------------------

def test_P6_missing_condition_value_does_not_pass():
    ev = real_evaluator()
    # No cvd_change_5s in the snapshot -> the atom cannot pass.
    assert ev.evaluate("OPR-019", ("FLOW_PRICE_DIVERGENCE",), _obs({})).holds is False


# --- P7: OR route (multiple required atoms) ----------------------------------

def test_P7_or_route_any_required_atom_passes():
    book = CalibrationBook.from_calibrations(
        (
            PredicateCalibration(
                predicate_id="OPR-019",
                status=CalibrationStatus.CALIBRATED,
                atoms=(
                    ConditionAtom("cvd_change_5s", "le", Decimal("-5")),
                    ConditionAtom("cvd_slope_5s", "le", Decimal("-2")),
                ),
            ),
        )
    )
    ev = RealPredicateEvaluator(book)
    # Only the second route holds; OR semantics still yield holds.
    v = ev.evaluate(
        "OPR-019",
        ("FLOW_PRICE_DIVERGENCE",),
        _obs({"cvd_change_5s": Decimal("0"), "cvd_slope_5s": Decimal("-3")}),
    )
    assert v.holds is True


# --- P8: empty CalibrationBook keeps UNVALIDATED -----------------------------

def test_P8_empty_book_is_uncalibrated_and_not_holding():
    ev = RealPredicateEvaluator(CalibrationBook())
    v = ev.evaluate("OPR-019", ("FLOW_PRICE_DIVERGENCE",), _obs({"cvd_change_5s": Decimal("-9")}))
    assert v.calibration_status is CalibrationStatus.UNCALIBRATED
    assert v.is_calibrated is False
    assert v.holds is False


def test_P8_class_specs_load_from_canon():
    specs = load_class_specs()
    # The nine target classes are present with the expected candidate material.
    assert "cvd_change_5s" in specs["FLOW_PRICE_DIVERGENCE"].candidate_keys
    assert "open_interest_change_5m" in specs["OPEN_INTEREST_CHANGE"].candidate_keys
    assert specs["ENGINE_TERMINAL"].selector == "ENGINE_STATE"
