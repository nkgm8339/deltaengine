"""Source-agnostic event ingestion for the Strategy Engine.

The Engine must not know where events come from. Live (Binance WebSocket) and
Replay (deterministic re-play) will both implement ``EventSource`` (pull-based
iterator) and yield ``EngineInputEvent``. This stage defines the interface only;
no Live/Replay source is implemented here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Iterator, Mapping, Protocol, runtime_checkable

from src.orderflow.hooks.models import as_utc


@dataclass(frozen=True)
class PredicateObservation:
    """Observation the Predicate Evaluator inspects.

    ``conditions`` carries a condition snapshot (condition_key -> value) that the
    real evaluator reads and compares against calibrated comparators. It is empty
    by default, so the StubPredicateEvaluator (which ignores it and uses ``holds``)
    and any code that does not supply conditions keep working unchanged.

    ``holds`` remains the scenario switch used by the StubPredicateEvaluator; the
    real evaluator ignores it and derives the verdict from ``conditions``.
    """

    holds: bool = True  # scenario switch for the Stub evaluator only
    hard_source_status: str = "OK"  # OK / UNKNOWN / STALE (judgement contract 9)
    location_confirmed: bool = False  # LOCATION_ARM gate (routing 2)
    first_predicate_confirmed: bool = False
    freshness_ok: bool = False
    conditions: Mapping[str, Decimal] = field(default_factory=dict)


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
