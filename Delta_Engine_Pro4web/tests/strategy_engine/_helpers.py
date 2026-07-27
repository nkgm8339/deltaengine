"""Shared fixtures for Strategy Engine tests (representative variant)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.strategy_engine.events import EngineInputEvent, PredicateObservation
from src.strategy_engine.predicate_eval import CalibrationBook, StubPredicateEvaluator
from src.strategy_engine.variant_runtime import (
    REPRESENTATIVE_VARIANT_ID,
    RepresentativeVariant,
)

BASE = datetime(2026, 7, 27, 0, 0, 0, tzinfo=timezone.utc)
MS = 1_000_000
S_NS = 1_000_000_000

# Market predicate ids of the representative variant (arm + advances + invalidation).
MARKET_PREDICATE_IDS = (
    "LOC::VISIBLE_BOOK_WALL",  # E00 LOCATION_CONTEXT
    "OPR-019",  # E01 FLOW_PRICE_DIVERGENCE
    "OPR-020",  # E02 ABSORPTION_STATE
    "OPR-021",  # E03 BREAK_ATTEMPT WALL_STATE
    "OPR-022",  # E04 OPEN_INTEREST_CHANGE
    "INV-005",  # E98 COMPOSITE_INVALIDATION ...
)


def edge(suffix: str) -> str:
    return f"{REPRESENTATIVE_VARIANT_ID}::{suffix}"


def load_variant() -> RepresentativeVariant:
    return RepresentativeVariant.load()


def calibrated_evaluator() -> StubPredicateEvaluator:
    return StubPredicateEvaluator(CalibrationBook.all_calibrated(MARKET_PREDICATE_IDS))


def uncalibrated_evaluator() -> StubPredicateEvaluator:
    return StubPredicateEvaluator()  # empty book -> UNVALIDATED


def make_event(
    suffix: str,
    *,
    source_event_id: str,
    source_s: float,
    engine_ns: int,
    holds: bool = True,
    hard_source_status: str = "OK",
    location_confirmed: bool = False,
    first_predicate_confirmed: bool = False,
    freshness_ok: bool = False,
    route_role: str = "ACTIVE_INSTANCE_UPDATE",
) -> EngineInputEvent:
    return EngineInputEvent(
        source_event_id=source_event_id,
        edge_id=edge(suffix),
        source_time=BASE + timedelta(seconds=source_s),
        received_time=BASE + timedelta(seconds=source_s),
        engine_time_ns=engine_ns,
        observation=PredicateObservation(
            holds=holds,
            hard_source_status=hard_source_status,
            location_confirmed=location_confirmed,
            first_predicate_confirmed=first_predicate_confirmed,
            freshness_ok=freshness_ok,
        ),
        route_role=route_role,
    )


def arm_event() -> EngineInputEvent:
    return make_event(
        "E00",
        source_event_id="arm",
        source_s=0.0,
        engine_ns=0,
        location_confirmed=True,
        first_predicate_confirmed=True,
        freshness_ok=True,
    )


def advance_events() -> list[EngineInputEvent]:
    return [
        make_event(
            f"E0{i}", source_event_id=f"adv{i}", source_s=float(i), engine_ns=i * MS
        )
        for i in range(1, 5)
    ]


def terminal_event() -> EngineInputEvent:
    return make_event("E90", source_event_id="term", source_s=5.0, engine_ns=5 * MS)
