from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.orderflow.big_trades.ids import (
    canonical_json,
    content_hash,
    decimal_text,
    flat_content_hash,
    zone_id_for_event,
)
from tests.orderflow._big_trades_helpers import event_zone


def test_decimal_canonicalization_removes_representation_noise() -> None:
    assert decimal_text(Decimal("1.000")) == "1"
    assert decimal_text(Decimal("0.000")) == "0"


def test_canonical_json_sorts_keys_and_uses_utc() -> None:
    value = {
        "z": Decimal("1.00"),
        "a": datetime(2026, 1, 1, 9, tzinfo=timezone(timedelta(hours=9))),
    }
    assert canonical_json(value) == '{"a":"2026-01-01T00:00:00.000000Z","z":"1"}'


def test_flat_content_hash_is_byte_equivalent_to_general_canonical_hash() -> None:
    value = {
        "decimal": Decimal("100.2500"),
        "time": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "text": "BTCUSDT",
        "integer": 42,
        "boolean": True,
        "missing": None,
    }
    assert flat_content_hash(value) == content_hash(value)


def test_zone_id_is_deterministic_and_versioned() -> None:
    first = zone_id_for_event("BTLOGIC-2.0", "bt2_x")
    second = zone_id_for_event("BTLOGIC-2.0", "bt2_x")
    assert first == second
    assert first.startswith("btz2_")
    assert first != zone_id_for_event("BTLOGIC-2.1", "bt2_x")


def test_same_event_input_has_same_ids_and_content_hashes() -> None:
    first_event, first_zone, _ = event_zone()
    second_event, second_zone, _ = event_zone()
    assert first_event.event_id == second_event.event_id
    assert first_event.content_hash == second_event.content_hash
    assert first_zone.zone_id == second_zone.zone_id
    assert first_zone.content_hash == second_zone.content_hash
