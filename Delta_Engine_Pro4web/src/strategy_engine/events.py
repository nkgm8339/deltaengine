"""Source-agnostic event ingestion for the Strategy Engine.

The Engine must not know where events come from. Live (Binance WebSocket) and
Replay (deterministic re-play) will both implement ``EventSource`` (pull-based
iterator) and yield ``EngineInputEvent``. This stage defines the interface only;
no Live/Replay source is implemented here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterator, Protocol, runtime_checkable

from src.orderflow.hooks.models import as_utc


@dataclass(frozen=True)
class PredicateObservation:
    """Scenario-controlled observation the Predicate Evaluator inspects.

    In this stage the observation carries the intended predicate outcome for a
    synthetic sequence; the real market-derived computation is the calibrated
    evaluator's job and is out of scope (thresholds uncalibrated).
    """

    holds: bool = True  # does the market predicate hold (advance / invalidation)?
    hard_source_status: str = "OK"  # OK / UNKNOWN / STALE (judgement contract 9)
    location_confirmed: bool = False  # LOCATION_ARM gate (routing 2)
    first_predicate_confirmed: bool = False
    freshness_ok: bool = False


@dataclass(frozen=True)
class EngineInputEvent:
    """One ingestion event, agnostic to its source (Live vs Replay)."""

    source_event_id: str
    edge_id: str  # which FSM edge this observation targets
    source_time: datetime  # exchange event time (ordering evidence)
    received_time: datetime  # wall clock arrival (never used for expiry)
    engine_time_ns: int  # monotonic engine time (expiry judgement)
    observation: PredicateObservation = PredicateObservation()
    route_role: str = "ACTIVE_INSTANCE_UPDATE"
    detector_status: str = "IMPLEMENTED_UNCALIBRATED"

    def __post_init__(self) -> None:
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


@runtime_checkable
class EventSource(Protocol):
    """Pull-based source of engine input events (Live and Replay both implement)."""

    def __iter__(self) -> Iterator[EngineInputEvent]:
        ...
