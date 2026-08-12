"""Canonical serialization and deterministic Big Trades V2 identifiers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

from .constants import AGGREGATION_CANDLE_TIMEFRAME, AGGREGATION_WINDOW_MS
from .time_buckets import event_time_ms


def decimal_text(value: Decimal | str | int) -> str:
    parsed = Decimal(str(value))
    if not parsed.is_finite():
        raise ValueError("Decimal value must be finite")
    if parsed == 0:
        return "0"
    return format(parsed.normalize(), "f")


def utc_text(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    normalized = value.astimezone(timezone.utc)
    return normalized.isoformat(timespec="microseconds").replace("+00:00", "Z")


def canonical_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return decimal_text(value)
    if isinstance(value, datetime):
        return utc_text(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if type(value) is dict:
        return {str(key): canonical_value(value[key]) for key in sorted(value)}
    if isinstance(value, (tuple, list)):
        return [canonical_value(item) for item in value]
    if is_dataclass(value):
        return canonical_value(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): canonical_value(value[key]) for key in sorted(value)}
    raise TypeError(f"unsupported canonical value {type(value)!r}")


def canonical_json(value: Any) -> str:
    return json.dumps(
        canonical_value(value),
        ensure_ascii=False,
        sort_keys=False,
        separators=(",", ":"),
    )


def sha256_hex(value: str | bytes) -> str:
    encoded = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(encoded).hexdigest()


def content_hash(value: Any) -> str:
    return sha256_hex(canonical_json(value))


def flat_content_hash(value: Mapping[str, Any]) -> str:
    """Hash a flat record with the exact same wire canonicalization as content_hash."""

    canonical: dict[str, Any] = {}
    for key in sorted(value):
        item = value[key]
        if isinstance(item, Decimal):
            canonical[str(key)] = decimal_text(item)
        elif isinstance(item, datetime):
            canonical[str(key)] = utc_text(item)
        elif isinstance(item, Enum):
            canonical[str(key)] = item.value
        elif isinstance(item, (str, int, bool)) or item is None:
            canonical[str(key)] = item
        else:
            raise TypeError(f"flat canonical record contains {type(item)!r}")
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def event_id_for_cluster(cluster: Any) -> str:
    key = "|".join(
        (
            "BT2",
            cluster.logic_version,
            cluster.venue,
            cluster.symbol,
            cluster.input_mode,
            cluster.side,
            str(event_time_ms(cluster.first_time)),
            str(cluster.first_trade_id),
            str(event_time_ms(cluster.last_time)),
            str(cluster.last_trade_id),
            str(AGGREGATION_WINDOW_MS),
            AGGREGATION_CANDLE_TIMEFRAME,
        )
    )
    return "bt2_" + sha256_hex(key)


def zone_id_for_event(logic_version: str, event_id: str) -> str:
    return "btz2_" + sha256_hex(f"BTZ2|{logic_version}|{event_id}")


def interaction_id(
    zone_id: str,
    interaction_type: str,
    source_event_time: datetime,
    source_identity: int | str | None,
    ordinal: int,
) -> str:
    key = "|".join(
        (
            "BTI2",
            zone_id,
            interaction_type,
            utc_text(source_event_time),
            "" if source_identity is None else str(source_identity),
            str(ordinal),
        )
    )
    return "bti2_" + sha256_hex(key)


def link_id(zone_id: str, linked_event_id: str) -> str:
    return "btl2_" + sha256_hex(f"BTL2|{zone_id}|{linked_event_id}")


def snapshot_id(zone_id: str, horizon_seconds: int) -> str:
    return "btsnap2_" + sha256_hex(f"BTSNAP2|{zone_id}|{horizon_seconds}")


def candle_observation_id(zone_id: str, candle_identifier: int) -> str:
    return "btcobs2_" + sha256_hex(f"BTCOBS2|{zone_id}|{candle_identifier}")


def checkpoint_id(zone_id: str, source_bucket_time: datetime) -> str:
    return "btcp2_" + sha256_hex(f"BTCP2|{zone_id}|{utc_text(source_bucket_time)}")


def assessment_id_for_payload(payload: Mapping[str, Any]) -> str:
    return "btassess2_" + sha256_hex("BTASSESS2|" + canonical_json(payload))
