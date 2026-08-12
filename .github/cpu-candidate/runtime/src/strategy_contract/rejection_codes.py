"""Rejection reason codes for the replay contract enforcer.

Each reason is tied to a specific clause of the canonical policy documents:

- 判定契約N        -> ORDER_FLOW_STATE_CONDITION_BINDING_POLICY_V0_1_20260727.md §2
- policy§N          -> ORDER_FLOW_STATE_CONDITION_BINDING_POLICY_V0_1_20260727.md §N
- routing§N         -> ORDER_FLOW_HOOK_VARIANT_ROUTING_POLICY_V0_1_20260727.md §N

REASON_CLAUSE maps each code to its governing clause string so the completion
report and tests can render the 試験名×根拠条項×結果 comparison table.
"""

from __future__ import annotations

from enum import Enum


class RejectReason(str, Enum):
    """Deterministic rejection codes; every code cites a canonical clause."""

    # R1 -- 判定契約2: ADVANCE evidence must be *after* the prior transition.
    STALE_EVIDENCE_BEFORE_PRIOR_TRANSITION = "STALE_EVIDENCE_BEFORE_PRIOR_TRANSITION"
    # R2 -- 判定契約3: a source_event_id must not prove more than one state
    #        (same Observation Instance).
    SOURCE_EVENT_ID_REUSED = "SOURCE_EVENT_ID_REUSED"
    # R3 -- 判定契約6: once a named invalidation guard fires, the instance ends
    #        and never revives.
    INSTANCE_TERMINATED_BY_INVALIDATION = "INSTANCE_TERMINATED_BY_INVALIDATION"
    # R4 -- 判定契約7: EXPIRE terminates on a versioned deadline judged by
    #        monotonic engine time; no Order Intent is produced.
    INSTANCE_EXPIRED = "INSTANCE_EXPIRED"
    # R6 -- routing§5: SUSPECTED_CONTEXT_ONLY / CONTEXT_REFRESH_ONLY routes must
    #        not advance a hard state on their own.
    CONTEXT_ONLY_CANNOT_ADVANCE_HARD_STATE = "CONTEXT_ONLY_CANNOT_ADVANCE_HARD_STATE"
    # R7-a -- policy§5: all edges are UNVALIDATED; an uncalibrated edge cannot be
    #        treated as a real firing.
    UNCALIBRATED_EDGE = "UNCALIBRATED_EDGE"
    # R7-b -- routing§5: a REGISTERED_UNIMPLEMENTED Hook route is runtime-disabled.
    ROUTE_RUNTIME_DISABLED = "ROUTE_RUNTIME_DISABLED"
    # R7-c -- 判定契約9: an OI-required (hard) state must not be satisfied by a
    #        hard source that is UNKNOWN / STALE.
    HARD_SOURCE_UNKNOWN_OR_STALE = "HARD_SOURCE_UNKNOWN_OR_STALE"
    # R8 -- routing§2: an instance is armed only when location + first predicate +
    #        freshness are all satisfied.
    ARM_REQUIRES_LOCATION_FIRST_PRED_FRESHNESS = "ARM_REQUIRES_LOCATION_FIRST_PRED_FRESHNESS"

    # Structural ordering guards (support the above; not tied to a single R case).
    EDGE_NOT_IN_CONTRACT = "EDGE_NOT_IN_CONTRACT"
    OUT_OF_SEQUENCE = "OUT_OF_SEQUENCE"
    INSTANCE_NOT_ARMED = "INSTANCE_NOT_ARMED"
    INSTANCE_ALREADY_ARMED = "INSTANCE_ALREADY_ARMED"
    NOTHING_TO_INVALIDATE = "NOTHING_TO_INVALIDATE"
    DEADLINE_NOT_REACHED = "DEADLINE_NOT_REACHED"


REASON_CLAUSE: dict[RejectReason, str] = {
    RejectReason.STALE_EVIDENCE_BEFORE_PRIOR_TRANSITION: "判定契約2",
    RejectReason.SOURCE_EVENT_ID_REUSED: "判定契約3",
    RejectReason.INSTANCE_TERMINATED_BY_INVALIDATION: "判定契約6",
    RejectReason.INSTANCE_EXPIRED: "判定契約7",
    RejectReason.CONTEXT_ONLY_CANNOT_ADVANCE_HARD_STATE: "routing§5",
    RejectReason.UNCALIBRATED_EDGE: "policy§5 (全edge UNVALIDATED)",
    RejectReason.ROUTE_RUNTIME_DISABLED: "routing§5 (REGISTERED_UNIMPLEMENTED)",
    RejectReason.HARD_SOURCE_UNKNOWN_OR_STALE: "判定契約9",
    RejectReason.ARM_REQUIRES_LOCATION_FIRST_PRED_FRESHNESS: "routing§2",
    RejectReason.EDGE_NOT_IN_CONTRACT: "structural",
    RejectReason.OUT_OF_SEQUENCE: "structural (ordered State Transition)",
    RejectReason.INSTANCE_NOT_ARMED: "structural",
    RejectReason.INSTANCE_ALREADY_ARMED: "structural",
    RejectReason.NOTHING_TO_INVALIDATE: "structural",
    RejectReason.DEADLINE_NOT_REACHED: "判定契約7 (monotonic deadline)",
}
