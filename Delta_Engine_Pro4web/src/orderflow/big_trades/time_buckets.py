"""Integer-only UTC source-time helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


UTC = timezone.utc
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
MICROSECONDS_PER_SECOND = 1_000_000
MICROSECONDS_PER_MINUTE = 60 * MICROSECONDS_PER_SECOND
MICROSECONDS_PER_DAY = 86_400 * MICROSECONDS_PER_SECOND


def require_aware_utc(value: datetime, name: str = "datetime") -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def epoch_microseconds(value: datetime) -> int:
    normalized = require_aware_utc(value)
    delta = normalized - EPOCH
    return (
        delta.days * MICROSECONDS_PER_DAY
        + delta.seconds * MICROSECONDS_PER_SECOND
        + delta.microseconds
    )


def event_time_ms(value: datetime) -> int:
    return epoch_microseconds(value) // 1_000


def candle_id(value: datetime) -> int:
    return epoch_microseconds(value) // MICROSECONDS_PER_MINUTE


def candle_start(value_or_id: datetime | int) -> datetime:
    identifier = candle_id(value_or_id) if isinstance(value_or_id, datetime) else value_or_id
    if not isinstance(identifier, int) or isinstance(identifier, bool):
        raise ValueError("candle ID must be an integer")
    return EPOCH + timedelta(microseconds=identifier * MICROSECONDS_PER_MINUTE)


def session_id(value: datetime) -> str:
    return require_aware_utc(value).date().isoformat()


def session_start(value_or_id: datetime | str) -> datetime:
    identifier = session_id(value_or_id) if isinstance(value_or_id, datetime) else value_or_id
    try:
        parsed = datetime.strptime(identifier, "%Y-%m-%d")
    except (TypeError, ValueError) as exc:
        raise ValueError("session ID must be YYYY-MM-DD") from exc
    return parsed.replace(tzinfo=UTC)


def session_end(value_or_id: datetime | str) -> datetime:
    return session_start(value_or_id) + timedelta(days=1)


def source_key(event_time: datetime, trade_id: int) -> tuple[int, int]:
    if not isinstance(trade_id, int) or isinstance(trade_id, bool) or trade_id < 0:
        raise ValueError("trade_id must be a non-negative integer")
    return epoch_microseconds(event_time), trade_id


def milliseconds_between(start: datetime, end: datetime) -> int:
    difference = epoch_microseconds(end) - epoch_microseconds(start)
    return difference // 1_000
