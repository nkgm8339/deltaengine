"""Minimal contract enforcer for one named-variant Observation Instance.

This is the reference "contract enforcer" skeleton: it decides accept/reject for
each FSM edge transition attempt and NOTHING else. It is not the Strategy Engine.

Order authority is zero by construction:
- there is no order-send method anywhere in this module;
- a TERMINAL edge returns only an ``OrderReadyHandoff`` (LONG_READY / SHORT_READY)
  to be handed to a downstream risk/execution gate (判定契約8);
- an EXPIRE edge returns no handoff and no order intent (判定契約7).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .events import ContractEvent
from .rejection_codes import RejectReason
from .variant_contract import ContractEdge, VariantContract

_ANY_ACTIVE_STATE = "ANY_ACTIVE_STATE"
_DEFAULT_EXPIRY_AFTER_NS = 60_000_000_000  # 60s synthetic deadline offset


class InstancePhase(str, Enum):
    UNARMED = "UNARMED"
    ARMED = "ARMED"
    ADVANCING = "ADVANCING"
    TERMINAL = "TERMINAL"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"


_ACTIVE_PHASES = frozenset({InstancePhase.ARMED, InstancePhase.ADVANCING})


@dataclass(frozen=True)
class OrderReadyHandoff:
    """Terminal output handed to the risk/execution gate. This is NOT an order.

    判定契約8: TERMINAL passes LONG_READY / SHORT_READY to the gate only. This
    object deliberately exposes no send/execute/order behaviour.
    """

    variant_id: str
    observation_instance_id: str
    direction: str  # LONG_READY / SHORT_READY
    terminal_state: str


@dataclass(frozen=True)
class StepResult:
    accepted: bool
    edge_id: str
    edge_type: str | None
    phase: InstancePhase
    reason: RejectReason | None = None
    handoff: OrderReadyHandoff | None = None

    @property
    def rejected(self) -> bool:
        return not self.accepted


class ContractEnforcer:
    """Enforces the design contracts for a single Observation Instance."""

    def __init__(
        self,
        contract: VariantContract,
        *,
        observation_instance_id: str,
        expiry_after_ns: int = _DEFAULT_EXPIRY_AFTER_NS,
    ) -> None:
        self.contract = contract
        self.observation_instance_id = observation_instance_id
        self._expiry_after_ns = expiry_after_ns
        self.phase = InstancePhase.UNARMED
        self.current_state = contract.armed_from_state
        self._last_source_time = None
        self._consumed_source_event_ids: set[str] = set()
        self._deadline_ns: int | None = None

    # -- public API ---------------------------------------------------------

    def submit(self, event: ContractEvent) -> StepResult:
        edge = self.contract.edges.get(event.edge_id)
        if edge is None:
            return self._reject(event, None, RejectReason.EDGE_NOT_IN_CONTRACT)

        # Absorbing phases: a terminated instance never revives (判定契約6 / 7).
        if self.phase is InstancePhase.INVALIDATED:
            return self._reject(
                event, edge, RejectReason.INSTANCE_TERMINATED_BY_INVALIDATION
            )
        if self.phase is InstancePhase.EXPIRED:
            return self._reject(event, edge, RejectReason.INSTANCE_EXPIRED)
        if self.phase is InstancePhase.TERMINAL:
            return self._reject(event, edge, RejectReason.OUT_OF_SEQUENCE)

        # Runtime gates applied to every firing attempt.
        # routing§5: REGISTERED_UNIMPLEMENTED routes are runtime-disabled (R7-b).
        if event.is_runtime_disabled_route:
            return self._reject(event, edge, RejectReason.ROUTE_RUNTIME_DISABLED)
        # policy§5: every edge is UNVALIDATED; an uncalibrated edge cannot fire (R7-a).
        if not event.is_calibrated:
            return self._reject(event, edge, RejectReason.UNCALIBRATED_EDGE)

        dispatch = {
            "LOCATION_ARM": self._arm,
            "ADVANCE": self._advance,
            "TERMINAL": self._terminal,
            "INVALIDATE": self._invalidate,
            "EXPIRE": self._expire,
        }.get(edge.edge_type)
        if dispatch is None:  # pragma: no cover - canon only has 5 edge types
            return self._reject(event, edge, RejectReason.EDGE_NOT_IN_CONTRACT)
        return dispatch(event, edge)

    # -- edge handlers ------------------------------------------------------

    def _arm(self, event: ContractEvent, edge: ContractEdge) -> StepResult:
        if self.phase is not InstancePhase.UNARMED:
            return self._reject(event, edge, RejectReason.INSTANCE_ALREADY_ARMED)
        # routing§2: arm only when location + first predicate + freshness hold (R8).
        if not (
            event.arm_location_confirmed
            and event.arm_first_predicate_confirmed
            and event.arm_freshness_ok
        ):
            return self._reject(
                event, edge, RejectReason.ARM_REQUIRES_LOCATION_FIRST_PRED_FRESHNESS
            )
        self._consume(event)
        self.phase = InstancePhase.ARMED
        self.current_state = edge.to_state
        self._last_source_time = event.source_time
        self._deadline_ns = event.engine_time_ns + self._expiry_after_ns
        return self._accept(event, edge)

    def _advance(self, event: ContractEvent, edge: ContractEdge) -> StepResult:
        guard = self._active_ordering_guard(event, edge)
        if guard is not None:
            return guard
        # routing§5: a context-only route cannot advance a hard state alone (R6).
        if event.is_context_only:
            return self._reject(
                event, edge, RejectReason.CONTEXT_ONLY_CANNOT_ADVANCE_HARD_STATE
            )
        # 判定契約9: an OI-required state cannot use an UNKNOWN/STALE hard source (R7-c).
        if edge.hard_source_required and event.hard_source_status in (
            "UNKNOWN",
            "STALE",
        ):
            return self._reject(
                event, edge, RejectReason.HARD_SOURCE_UNKNOWN_OR_STALE
            )
        self._consume(event)
        self.phase = InstancePhase.ADVANCING
        self.current_state = edge.to_state
        self._last_source_time = event.source_time
        return self._accept(event, edge)

    def _terminal(self, event: ContractEvent, edge: ContractEdge) -> StepResult:
        guard = self._active_ordering_guard(event, edge)
        if guard is not None:
            return guard
        self._consume(event)
        self.phase = InstancePhase.TERMINAL
        self.current_state = edge.to_state
        handoff = OrderReadyHandoff(
            variant_id=self.contract.variant_id,
            observation_instance_id=self.observation_instance_id,
            direction=f"{self.contract.terminal_direction}_READY",
            terminal_state=edge.to_state,
        )
        return self._accept(event, edge, handoff=handoff)

    def _invalidate(self, event: ContractEvent, edge: ContractEdge) -> StepResult:
        # 判定契約6: an invalidation guard may fire from ANY active state.
        if self.phase not in _ACTIVE_PHASES:
            return self._reject(event, edge, RejectReason.NOTHING_TO_INVALIDATE)
        self.phase = InstancePhase.INVALIDATED
        self.current_state = edge.to_state
        return self._accept(event, edge)

    def _expire(self, event: ContractEvent, edge: ContractEdge) -> StepResult:
        if self.phase not in _ACTIVE_PHASES:
            return self._reject(event, edge, RejectReason.INSTANCE_NOT_ARMED)
        # 判定契約7: EXPIRE terminates on the versioned deadline, judged by
        # monotonic engine time (not wall clock).
        assert self._deadline_ns is not None
        if event.engine_time_ns < self._deadline_ns:
            return self._reject(event, edge, RejectReason.DEADLINE_NOT_REACHED)
        self.phase = InstancePhase.EXPIRED
        self.current_state = edge.to_state
        # No handoff and no order intent are produced on expiry.
        return self._accept(event, edge)

    # -- shared guards ------------------------------------------------------

    def _active_ordering_guard(
        self, event: ContractEvent, edge: ContractEdge
    ) -> StepResult | None:
        """Ordering / freshness / reuse / expiry checks for ADVANCE & TERMINAL."""
        if self.phase not in _ACTIVE_PHASES:
            return self._reject(event, edge, RejectReason.INSTANCE_NOT_ARMED)
        if edge.from_state != _ANY_ACTIVE_STATE and edge.from_state != self.current_state:
            return self._reject(event, edge, RejectReason.OUT_OF_SEQUENCE)
        # 判定契約7: expire first, judged by monotonic engine time (R4-a / R4-c).
        assert self._deadline_ns is not None
        if event.engine_time_ns >= self._deadline_ns:
            self.phase = InstancePhase.EXPIRED
            return self._reject(event, edge, RejectReason.INSTANCE_EXPIRED)
        # 判定契約2: evidence must be strictly after the prior transition (R1).
        if self._last_source_time is not None and event.source_time <= self._last_source_time:
            return self._reject(
                event, edge, RejectReason.STALE_EVIDENCE_BEFORE_PRIOR_TRANSITION
            )
        # 判定契約3: a source_event_id proves at most one state (R2, same instance).
        if event.source_event_id in self._consumed_source_event_ids:
            return self._reject(event, edge, RejectReason.SOURCE_EVENT_ID_REUSED)
        return None

    # -- helpers ------------------------------------------------------------

    def _consume(self, event: ContractEvent) -> None:
        self._consumed_source_event_ids.add(event.source_event_id)

    def _accept(
        self,
        event: ContractEvent,
        edge: ContractEdge,
        *,
        handoff: OrderReadyHandoff | None = None,
    ) -> StepResult:
        return StepResult(
            accepted=True,
            edge_id=event.edge_id,
            edge_type=edge.edge_type,
            phase=self.phase,
            handoff=handoff,
        )

    def _reject(
        self,
        event: ContractEvent,
        edge: ContractEdge | None,
        reason: RejectReason,
    ) -> StepResult:
        return StepResult(
            accepted=False,
            edge_id=event.edge_id,
            edge_type=edge.edge_type if edge is not None else None,
            phase=self.phase,
            reason=reason,
        )
