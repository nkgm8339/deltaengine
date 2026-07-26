"""Replay contract rejection tests (R1..R8).

Each test cites the governing clause of the canonical policy documents:
- 判定契約N  -> ORDER_FLOW_STATE_CONDITION_BINDING_POLICY_V0_1_20260727.md §2
- policy§N   -> ORDER_FLOW_STATE_CONDITION_BINDING_POLICY_V0_1_20260727.md §N
- routing§N  -> ORDER_FLOW_HOOK_VARIANT_ROUTING_POLICY_V0_1_20260727.md §N

The enforcer is a minimal contract layer (edge accept/reject only); it is NOT the
Strategy Engine and has NO order-send path. All routes stay UNVALIDATED / runtime 0
in the canon; these tests synthesize the control fields to fix the contract.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

import src.strategy_contract as strategy_contract
from src.orderflow.hooks.models import CalibrationStatus
from src.strategy_contract.enforcer import (
    ContractEnforcer,
    InstancePhase,
    OrderReadyHandoff,
    StepResult,
)
from src.strategy_contract.replay_driver import replay_synthetic
from src.strategy_contract.rejection_codes import REASON_CLAUSE, RejectReason
from src.strategy_contract.variant_contract import VariantContract

from ._helpers import (
    E_ADV,
    E_EXPIRE,
    E_INVALIDATE,
    E_TERMINAL,
    MS,
    S_NS,
    arm_event,
    load_contract,
    make_event,
)


def _enforcer(**kwargs) -> ContractEnforcer:
    return ContractEnforcer(load_contract(), observation_instance_id="R-1", **kwargs)


def _arm(enforcer: ContractEnforcer) -> StepResult:
    result = enforcer.submit(arm_event())
    assert result.accepted, result.reason
    return result


def _advance_through(enforcer: ContractEnforcer, count: int) -> None:
    """Advance E01..E0{count} with well-formed events."""
    for i in range(1, count + 1):
        result = enforcer.submit(
            make_event(
                E_ADV[i - 1],
                event_id=f"ok-evt-{i}",
                source_event_id=f"ok-src-{i}",
                source_s=float(i),
                engine_ns=i * MS,
            )
        )
        assert result.accepted, (E_ADV[i - 1], result.reason)


# --------------------------------------------------------------------------- #
# R1 -- 判定契約2: ADVANCE evidence must be after the prior transition.
# --------------------------------------------------------------------------- #

def test_R1a_older_source_time_is_rejected():
    # 判定契約2: evidence with an older exchange timestamp than the prior
    # transition must not advance.
    enforcer = _enforcer()
    enforcer.submit(arm_event(source_s=10.0, engine_ns=0))
    stale = make_event(
        E_ADV[0],
        event_id="e1",
        source_event_id="s1",
        source_s=5.0,  # older than the arm transition (10.0)
        engine_ns=5 * MS,
    )
    result = enforcer.submit(stale)
    assert result.reason is RejectReason.STALE_EVIDENCE_BEFORE_PRIOR_TRANSITION


def test_R1b_delayed_arrival_out_of_order_is_rejected():
    # 判定契約2: a late-arriving event (higher engine/arrival order) whose
    # occurrence time predates the prior transition is still rejected.
    enforcer = _enforcer()
    enforcer.submit(arm_event(source_s=10.0, engine_ns=1 * MS))
    delayed = make_event(
        E_ADV[0],
        event_id="e1",
        source_event_id="s1",
        source_s=5.0,  # occurred earlier...
        engine_ns=9 * MS,  # ...but arrived later
    )
    result = enforcer.submit(delayed)
    assert result.reason is RejectReason.STALE_EVIDENCE_BEFORE_PRIOR_TRANSITION


# --------------------------------------------------------------------------- #
# R2 -- 判定契約3: a source_event_id proves at most one state.
# --------------------------------------------------------------------------- #

def test_R2a_same_event_id_reuse_within_instance_is_rejected():
    # 判定契約3: reusing one source_event_id as evidence for E01 then E02 is rejected.
    enforcer = _enforcer()
    _arm(enforcer)
    first = make_event(
        E_ADV[0], event_id="e1", source_event_id="shared", source_s=1.0, engine_ns=MS
    )
    assert enforcer.submit(first).accepted
    reuse = make_event(
        E_ADV[1],
        event_id="e2",
        source_event_id="shared",  # reused id
        source_s=2.0,  # newer, so not a staleness rejection
        engine_ns=2 * MS,
    )
    result = enforcer.submit(reuse)
    assert result.reason is RejectReason.SOURCE_EVENT_ID_REUSED


def test_R2b_cross_instance_reuse_is_undefined_by_canon():
    # 判定契約3 defines reuse across *states* of one Observation Instance only.
    # Cross-instance source_event_id reuse is UNDEFINED_BY_CANON: the canon has no
    # rule, so the enforcer must not invent one. Approved 2026-07-27: mark as an
    # explicit skip and record it as a future canon update item.
    #
    # Observed (documented, not asserted as a contract): the enforcer scopes reuse
    # per instance, so a second instance would accept the same id. Whether that is
    # correct is not defined by the canon.
    pytest.skip(
        "UNDEFINED_BY_CANON: cross-instance source_event_id reuse is not defined in "
        "the canon (判定契約3 covers same-instance states only). Not decided here."
    )


# --------------------------------------------------------------------------- #
# R3 -- 判定契約6: invalidation ends the instance; no revival.
# --------------------------------------------------------------------------- #

def test_R3a_advance_and_terminal_after_invalidation_are_rejected():
    # 判定契約6: after a named guard fires, further ADVANCE/TERMINAL are rejected.
    enforcer = _enforcer()
    _arm(enforcer)
    _advance_through(enforcer, 1)  # at S01
    inval = make_event(
        E_INVALIDATE,
        event_id="inv",
        source_event_id="inv-src",
        source_s=1.5,
        engine_ns=2 * MS,
    )
    assert enforcer.submit(inval).accepted
    assert enforcer.phase is InstancePhase.INVALIDATED

    adv = make_event(
        E_ADV[1], event_id="e2", source_event_id="s2", source_s=3.0, engine_ns=3 * MS
    )
    assert enforcer.submit(adv).reason is RejectReason.INSTANCE_TERMINATED_BY_INVALIDATION

    term = make_event(
        E_TERMINAL, event_id="t", source_event_id="ts", source_s=4.0, engine_ns=4 * MS
    )
    assert enforcer.submit(term).reason is RejectReason.INSTANCE_TERMINATED_BY_INVALIDATION


def test_R3b_valid_evidence_after_invalidation_does_not_revive():
    # 判定契約6: even fully valid, in-order, calibrated evidence cannot revive an
    # invalidated instance.
    enforcer = _enforcer()
    _arm(enforcer)
    _advance_through(enforcer, 2)  # at S02
    inval = make_event(
        E_INVALIDATE,
        event_id="inv",
        source_event_id="inv-src",
        source_s=2.5,
        engine_ns=3 * MS,
    )
    assert enforcer.submit(inval).accepted
    revive = make_event(
        E_ADV[2], event_id="e3", source_event_id="s3", source_s=10.0, engine_ns=10 * MS
    )
    result = enforcer.submit(revive)
    assert result.reason is RejectReason.INSTANCE_TERMINATED_BY_INVALIDATION
    assert enforcer.phase is InstancePhase.INVALIDATED


# --------------------------------------------------------------------------- #
# R4 -- 判定契約7: EXPIRE on a versioned deadline (monotonic engine time); no OI.
# --------------------------------------------------------------------------- #

def test_R4a_advance_after_deadline_is_expired():
    # 判定契約7: an ADVANCE attempted past the deadline expires the instance.
    enforcer = _enforcer(expiry_after_ns=60 * S_NS)
    enforcer.submit(arm_event(source_s=0.0, engine_ns=0))
    late = make_event(
        E_ADV[0],
        event_id="e1",
        source_event_id="s1",
        source_s=1.0,  # newer occurrence, so not a staleness rejection
        engine_ns=70 * S_NS,  # past the 60s deadline
    )
    result = enforcer.submit(late)
    assert result.reason is RejectReason.INSTANCE_EXPIRED
    assert enforcer.phase is InstancePhase.EXPIRED


def test_R4b_expire_edge_produces_no_order_intent():
    # 判定契約7: EXPIRE terminates without any Order Intent / handoff.
    enforcer = _enforcer(expiry_after_ns=60 * S_NS)
    _arm(enforcer)
    expire = make_event(
        E_EXPIRE,
        event_id="x",
        source_event_id="xs",
        source_s=1.0,
        engine_ns=70 * S_NS,
    )
    report = replay_synthetic(enforcer, [expire])
    assert report.steps[-1].accepted
    assert enforcer.phase is InstancePhase.EXPIRED
    assert report.steps[-1].handoff is None
    assert report.handoffs == []
    assert report.order_intents == 0


def test_R4c_expiry_uses_monotonic_engine_time_not_wall_clock():
    # 判定契約7: expiry is judged by monotonic engine time. A wall-clock rewind
    # must neither cause a false expiry nor mask a real one.

    # (1) engine time within deadline, but received (wall) time rewound far back:
    #     the advance must still be ACCEPTED.
    e1 = _enforcer(expiry_after_ns=60 * S_NS)
    e1.submit(arm_event(source_s=10.0, engine_ns=0))
    rewound = make_event(
        E_ADV[0],
        event_id="e1",
        source_event_id="s1",
        source_s=20.0,
        received_s=-86_400.0,  # wall clock jumped a day into the past
        engine_ns=1 * MS,  # monotonic: still within deadline
    )
    assert e1.submit(rewound).accepted

    # (2) engine time past deadline while wall clock looks normal: EXPIRED.
    e2 = _enforcer(expiry_after_ns=60 * S_NS)
    e2.submit(arm_event(source_s=10.0, engine_ns=0))
    past = make_event(
        E_ADV[0],
        event_id="e1",
        source_event_id="s1",
        source_s=20.0,
        received_s=11.0,  # wall clock looks well within the window
        engine_ns=90 * S_NS,  # monotonic: past deadline
    )
    assert e2.submit(past).reason is RejectReason.INSTANCE_EXPIRED


# --------------------------------------------------------------------------- #
# R5 -- routing§0 / 判定契約8: Hook cannot order directly; terminal -> gate only.
# --------------------------------------------------------------------------- #

_FORBIDDEN_ORDER_ATTRS = (
    "send",
    "order",
    "orders",
    "execute",
    "place",
    "place_order",
    "submit_order",
    "order_send",
    "fill",
    "to_order",
)


def test_R5a_no_order_send_api_exists_on_enforcer_or_handoff():
    # routing§0: there is no direct path from a Hook to an Order Intent. The
    # enforcer and its terminal handoff expose no order-send behaviour.
    for obj in (ContractEnforcer, OrderReadyHandoff):
        for attr in _FORBIDDEN_ORDER_ATTRS:
            assert not hasattr(obj, attr), f"{obj.__name__}.{attr} must not exist"


def test_R5a_package_source_has_no_order_send_path():
    # routing§0: fix the absence structurally -- the package must not import the
    # execution/MT5 gateway or reference an order-send symbol.
    pkg_dir = Path(strategy_contract.__file__).resolve().parent
    forbidden = ("order_send", "Mt5MarketOrderGateway", "flow_hfm_executor", "src.execution")
    for path in pkg_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in text, f"{path.name} must not reference {needle}"


def test_R5b_terminal_hands_off_direction_ready_not_an_order():
    # 判定契約8: TERMINAL hands LONG_READY/SHORT_READY to the gate, never an order.
    enforcer = _enforcer()
    _arm(enforcer)
    _advance_through(enforcer, 4)
    term = make_event(
        E_TERMINAL, event_id="t", source_event_id="ts", source_s=5.0, engine_ns=5 * MS
    )
    result = enforcer.submit(term)
    assert result.accepted
    assert isinstance(result.handoff, OrderReadyHandoff)
    assert result.handoff.direction == "SHORT_READY"


def test_R5c_canon_routing_has_zero_direct_order_authority():
    # routing§0: every design route in the canon is runtime-disabled with no direct
    # order authority. Fix this fact as a regression test.
    canon = (
        Path(strategy_contract.__file__).resolve().parents[3]
        / "ArchitectureRepository"
        / "00_Master"
        / "トリガー作成指示書群"
        / "ORDER_FLOW_HOOK_VARIANT_OBSERVATION_ROUTING_V0_1_20260727.csv"
    )
    with canon.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = 0
        for row in reader:
            rows += 1
            assert row["direct_order_authority"] == "NO"
            assert row["runtime_route_enabled"] == "NO"
    assert rows == 25_664


# --------------------------------------------------------------------------- #
# R6 -- routing§5: context-only route must not advance a hard state alone.
# --------------------------------------------------------------------------- #

def test_R6a_context_only_route_cannot_advance():
    # routing§5: CONTEXT_REFRESH_ONLY (context-only) evidence must not advance.
    enforcer = _enforcer()
    _arm(enforcer)
    ctx = make_event(
        E_ADV[0],
        event_id="e1",
        source_event_id="s1",
        source_s=1.0,
        engine_ns=MS,
        route_role="CONTEXT_REFRESH_ONLY",
    )
    result = enforcer.submit(ctx)
    assert result.reason is RejectReason.CONTEXT_ONLY_CANNOT_ADVANCE_HARD_STATE


# --------------------------------------------------------------------------- #
# R7 -- policy§5 / routing§5 / 判定契約9: uncalibrated / unimplemented / stale.
# --------------------------------------------------------------------------- #

def test_R7a_uncalibrated_edge_cannot_fire():
    # policy§5: all edges are UNVALIDATED; an uncalibrated edge cannot fire.
    enforcer = _enforcer()
    _arm(enforcer)
    uncal = make_event(
        E_ADV[0],
        event_id="e1",
        source_event_id="s1",
        source_s=1.0,
        engine_ns=MS,
        calibration_status=CalibrationStatus.UNCALIBRATED,
    )
    assert enforcer.submit(uncal).reason is RejectReason.UNCALIBRATED_EDGE


def test_R7a_provisional_edge_cannot_fire():
    # policy§5: only CALIBRATED may fire; PROVISIONAL is still not a real firing.
    enforcer = _enforcer()
    _arm(enforcer)
    prov = make_event(
        E_ADV[0],
        event_id="e1",
        source_event_id="s1",
        source_s=1.0,
        engine_ns=MS,
        calibration_status=CalibrationStatus.PROVISIONAL,
    )
    assert enforcer.submit(prov).reason is RejectReason.UNCALIBRATED_EDGE


def test_R7b_registered_unimplemented_route_is_runtime_disabled():
    # routing§5: a REGISTERED_UNIMPLEMENTED Hook route is runtime-disabled.
    enforcer = _enforcer()
    _arm(enforcer)
    unimpl = make_event(
        E_ADV[0],
        event_id="e1",
        source_event_id="s1",
        source_s=1.0,
        engine_ns=MS,
        detector_status="REGISTERED_UNIMPLEMENTED",
    )
    assert enforcer.submit(unimpl).reason is RejectReason.ROUTE_RUNTIME_DISABLED


@pytest.mark.parametrize("status", ["UNKNOWN", "STALE"])
def test_R7c_oi_state_rejects_unknown_or_stale_hard_source(status: str):
    # 判定契約9: an OI-required (hard) state must not be satisfied by an
    # UNKNOWN/STALE hard source.
    enforcer = _enforcer()
    _arm(enforcer)
    _advance_through(enforcer, 3)  # at S03, next edge E04 is OI-required
    oi = make_event(
        E_ADV[3],
        event_id="e4",
        source_event_id="s4",
        source_s=4.0,
        engine_ns=4 * MS,
        hard_source_status=status,
    )
    assert enforcer.submit(oi).reason is RejectReason.HARD_SOURCE_UNKNOWN_OR_STALE


def test_R7c_oi_state_accepts_ok_hard_source():
    # Positive control: with an OK hard source the OI edge advances.
    enforcer = _enforcer()
    _arm(enforcer)
    _advance_through(enforcer, 3)
    oi = make_event(
        E_ADV[3],
        event_id="e4",
        source_event_id="s4",
        source_s=4.0,
        engine_ns=4 * MS,
        hard_source_status="OK",
    )
    assert enforcer.submit(oi).accepted


# --------------------------------------------------------------------------- #
# R8 -- routing§2: arm only on location + first predicate + freshness.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "location,first_predicate,freshness",
    [
        (False, True, True),
        (True, False, True),
        (True, True, False),
        (False, False, False),
    ],
)
def test_R8a_arm_requires_location_first_predicate_and_freshness(
    location: bool, first_predicate: bool, freshness: bool
):
    # routing§2: an Observation Instance is armed only when location + first
    # predicate + freshness are all satisfied.
    enforcer = _enforcer()
    result = enforcer.submit(
        arm_event(location=location, first_predicate=first_predicate, freshness=freshness)
    )
    assert result.reason is RejectReason.ARM_REQUIRES_LOCATION_FIRST_PRED_FRESHNESS
    assert enforcer.phase is InstancePhase.UNARMED


def test_R8a_arm_succeeds_when_all_conditions_hold():
    # Positive control: all three conditions satisfied -> armed.
    enforcer = _enforcer()
    result = enforcer.submit(arm_event(location=True, first_predicate=True, freshness=True))
    assert result.accepted
    assert enforcer.phase is InstancePhase.ARMED


# --------------------------------------------------------------------------- #
# Meta: every governed reject reason cites a canonical clause.
# --------------------------------------------------------------------------- #

def test_every_reject_reason_has_a_clause_citation():
    for reason in RejectReason:
        assert reason in REASON_CLAUSE and REASON_CLAUSE[reason]
