"""Synthetic event schema for replay contract testing.

A ContractEvent is an *attempt* to fire one named-variant FSM edge. It carries the
control fields the enforcer needs to apply the design contracts, with fully
controlled ordering (source_time), monotonic engine time (engine_time_ns), and
identity (event_id / source_event_id). Both synthetic sequences and journal-derived
sequences are expressed as ContractEvents.

The enforcer NEVER uses wall-clock ``received_time`` for expiry; expiry is judged by
``engine_time_ns`` only, so a wall-clock rewind cannot change contract outcomes
(判定契約7).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from src.orderflow.hooks.models import CalibrationStatus, as_utc

# routing§5 / routing§2: routes that only refresh context and must not, on their
# own, advance a hard state.
CONTEXT_ONLY_ROLES = frozenset(
    {
        "CONTEXT_REFRESH_ONLY",
        "GLOBAL_CONTEXT_REFRESH_ONLY",
        "ACTIVE_INSTANCE_RECHECK",
        "SUSPECTED_CONTEXT_ONLY",
    }
)

# Hook detector status values relevant to runtime gating (routing§5).
DETECTOR_STATUS_UNIMPLEMENTED = "REGISTERED_UNIMPLEMENTED"

# Hard-source availability states (判定契約9).
_HARD_SOURCE_STATES = frozenset({"OK", "UNKNOWN", "STALE"})


@dataclass(frozen=True)
class ContractEvent:
    """One controlled attempt to fire a single FSM edge of a named variant."""

    event_id: str
    source_event_id: str
    edge_id: str
    source_time: datetime  # exchange event time -- ordering evidence
    received_time: datetime  # wall clock arrival -- NEVER used for expiry
    engine_time_ns: int  # monotonic engine time -- expiry judgement
    calibration_status: CalibrationStatus = CalibrationStatus.UNCALIBRATED
    detector_status: str = "IMPLEMENTED_UNCALIBRATED"
    route_role: str = "ACTIVE_INSTANCE_UPDATE"
    hard_source_status: str = "OK"
    # LOCATION_ARM gating inputs (routing§2).
    arm_location_confirmed: bool = False
    arm_first_predicate_confirmed: bool = False
    arm_freshness_ok: bool = False
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.event_id:
            raise ValueError("event_id must be non-empty")
        if not self.source_event_id:
            raise ValueError("source_event_id must be non-empty")
        if not self.edge_id:
            raise ValueError("edge_id must be non-empty")
        object.__setattr__(self, "source_time", as_utc(self.source_time, "source_time"))
        object.__setattr__(
            self, "received_time", as_utc(self.received_time, "received_time")
        )
        if not isinstance(self.engine_time_ns, int):
            raise TypeError("engine_time_ns must be int (monotonic nanoseconds)")
        if self.engine_time_ns < 0:
            raise ValueError("engine_time_ns must be non-negative")
        if not isinstance(self.calibration_status, CalibrationStatus):
            raise TypeError("calibration_status must be a CalibrationStatus")
        if self.hard_source_status not in _HARD_SOURCE_STATES:
            raise ValueError(f"unsupported hard_source_status: {self.hard_source_status}")

    @property
    def is_context_only(self) -> bool:
        return self.route_role in CONTEXT_ONLY_ROLES

    @property
    def is_runtime_disabled_route(self) -> bool:
        return self.detector_status == DETECTOR_STATUS_UNIMPLEMENTED

    @property
    def is_calibrated(self) -> bool:
        return self.calibration_status is CalibrationStatus.CALIBRATED
