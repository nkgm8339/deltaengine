"""Golden path contrast baseline for the replay contract enforcer.

A well-formed, in-order, calibrated Observation Instance for the user example
variant must be ACCEPTED all the way to a SHORT_READY gate handoff -- and must still
produce zero order intents (direct order authority 0). This is the positive control
against which every rejection test (R1..R8) contrasts.
"""

from __future__ import annotations

from src.strategy_contract.enforcer import ContractEnforcer, InstancePhase, OrderReadyHandoff
from src.strategy_contract.replay_driver import replay_synthetic

from ._helpers import (
    arm_event,
    golden_advance_events,
    golden_terminal_event,
    load_contract,
)


def _enforcer() -> ContractEnforcer:
    return ContractEnforcer(load_contract(), observation_instance_id="GP-1")


def test_contract_loads_user_example_variant_from_canon():
    contract = load_contract()
    assert contract.terminal_direction == "SHORT"
    assert len(contract.ordered_advance_edge_ids) == 4
    # Only the OI edge (E04) is a hard-source-required state (判定契約9).
    oi_edge = contract.edges[f"{contract.variant_id}::E04"]
    assert oi_edge.hard_source_required is True
    for suffix in ("E01", "E02", "E03"):
        assert contract.edges[f"{contract.variant_id}::{suffix}"].hard_source_required is False


def test_golden_path_reaches_short_ready_handoff():
    enforcer = _enforcer()
    events = [arm_event(), *golden_advance_events(), golden_terminal_event()]
    report = replay_synthetic(enforcer, events)

    assert report.rejected == 0
    assert report.accepted == len(events)
    assert enforcer.phase is InstancePhase.TERMINAL
    # R5-b: terminal yields a gate handoff (LONG_READY/SHORT_READY), not an order.
    assert len(report.handoffs) == 1
    handoff = report.handoffs[0]
    assert isinstance(handoff, OrderReadyHandoff)
    assert handoff.direction == "SHORT_READY"
    # direct order authority 0: no order intent is ever produced.
    assert report.order_intents == 0
