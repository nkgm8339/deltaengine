"""Shared fixtures for replay contract tests.

The FSM structure is loaded read-only from the canonical CSVs; only the events are
synthetic. The golden variant is the user-provided example
``VAR-CVD-BEAR-ABSFAIL-BIDBREAK-OIUNWIND-SHORT-VISIBLE_BOOK_WALL-001`` (判定契約4 の例).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.orderflow.hooks.models import CalibrationStatus
from src.strategy_contract.events import ContractEvent
from src.strategy_contract.variant_contract import VariantContract

VARIANT_ID = "VAR-CVD-BEAR-ABSFAIL-BIDBREAK-OIUNWIND-SHORT-VISIBLE_BOOK_WALL-001"

# Ordered edges of the golden variant (verified against the canon).
E_ARM = f"{VARIANT_ID}::E00"
E_ADV = (
    f"{VARIANT_ID}::E01",
    f"{VARIANT_ID}::E02",
    f"{VARIANT_ID}::E03",
    f"{VARIANT_ID}::E04",  # OPEN_INTEREST_CHANGE -- hard source required
)
E_TERMINAL = f"{VARIANT_ID}::E90"
E_INVALIDATE = f"{VARIANT_ID}::E98"
E_EXPIRE = f"{VARIANT_ID}::E99"

BASE = datetime(2026, 7, 27, 0, 0, 0, tzinfo=timezone.utc)
MS = 1_000_000  # nanoseconds per millisecond
S_NS = 1_000_000_000  # nanoseconds per second


def load_contract() -> VariantContract:
    return VariantContract.load(VARIANT_ID)


def make_event(
    edge_id: str,
    *,
    event_id: str,
    source_event_id: str,
    source_s: float,
    engine_ns: int,
    received_s: float | None = None,
    calibration_status: CalibrationStatus = CalibrationStatus.CALIBRATED,
    detector_status: str = "IMPLEMENTED_UNCALIBRATED",
    route_role: str = "ACTIVE_INSTANCE_UPDATE",
    hard_source_status: str = "OK",
    arm_location_confirmed: bool = False,
    arm_first_predicate_confirmed: bool = False,
    arm_freshness_ok: bool = False,
) -> ContractEvent:
    received = received_s if received_s is not None else source_s
    return ContractEvent(
        event_id=event_id,
        source_event_id=source_event_id,
        edge_id=edge_id,
        source_time=BASE + timedelta(seconds=source_s),
        received_time=BASE + timedelta(seconds=received),
        engine_time_ns=engine_ns,
        calibration_status=calibration_status,
        detector_status=detector_status,
        route_role=route_role,
        hard_source_status=hard_source_status,
        arm_location_confirmed=arm_location_confirmed,
        arm_first_predicate_confirmed=arm_first_predicate_confirmed,
        arm_freshness_ok=arm_freshness_ok,
    )


def arm_event(
    *,
    engine_ns: int = 0,
    source_s: float = 0.0,
    location: bool = True,
    first_predicate: bool = True,
    freshness: bool = True,
    calibration_status: CalibrationStatus = CalibrationStatus.CALIBRATED,
) -> ContractEvent:
    return make_event(
        E_ARM,
        event_id="arm-evt",
        source_event_id="arm-src",
        source_s=source_s,
        engine_ns=engine_ns,
        calibration_status=calibration_status,
        arm_location_confirmed=location,
        arm_first_predicate_confirmed=first_predicate,
        arm_freshness_ok=freshness,
    )


def golden_advance_events() -> list[ContractEvent]:
    """A well-formed, in-order advance sequence E01..E04 for the golden variant."""
    events = []
    for i, edge_id in enumerate(E_ADV, start=1):
        events.append(
            make_event(
                edge_id,
                event_id=f"adv-evt-{i}",
                source_event_id=f"adv-src-{i}",
                source_s=float(i),
                engine_ns=i * MS,
            )
        )
    return events


def golden_terminal_event() -> ContractEvent:
    return make_event(
        E_TERMINAL,
        event_id="term-evt",
        source_event_id="term-src",
        source_s=float(len(E_ADV) + 1),
        engine_ns=(len(E_ADV) + 1) * MS,
    )
