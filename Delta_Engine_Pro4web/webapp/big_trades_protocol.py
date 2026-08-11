"""Strict Big Trades V2 WebSocket batching and JSON protocol validation.

Only records handed to :class:`BigTradesBatcherV2` by the runtime publication
callback are eligible for this stream.  The runtime invokes that callback only
after the corresponding DuckDB commit acknowledgement succeeds.
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Awaitable, Callable, Iterable, Mapping, Optional
from uuid import UUID, uuid4

from src.orderflow.big_trades.ids import decimal_text, utc_text
from src.orderflow.big_trades.runtime import BigTradesRuntimeStatus, RuntimeRecord


logger = logging.getLogger("webapp.big_trades")

BIG_TRADES_RECORD_KINDS = frozenset(
    {
        "EVENT_CREATED",
        "ZONE_CREATED",
        "ZONE_INTERACTION",
        "ZONE_EVENT_LINK",
        "RESULT_SNAPSHOT",
        "CANDLE_OBSERVATION",
        "USER_ASSESSMENT",
    }
)
BIG_TRADES_STATUSES = frozenset(item.value for item in BigTradesRuntimeStatus)
_RECORD_ID_FIELDS = {
    "EVENT_CREATED": "event_id",
    "ZONE_CREATED": "zone_id",
    "ZONE_INTERACTION": "interaction_id",
    "ZONE_EVENT_LINK": "link_id",
    "RESULT_SNAPSHOT": "snapshot_id",
    "CANDLE_OBSERVATION": "candle_observation_id",
    "USER_ASSESSMENT": "assessment_id",
}
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


class BigTradesProtocolError(ValueError):
    """A record or envelope violates the closed Big Trades wire contract."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _json_value(value: Any) -> Any:
    """Convert supported values without ever passing a binary float to JSON."""

    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return value
    if isinstance(value, Decimal):
        return decimal_text(value)
    if isinstance(value, datetime):
        return utc_text(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    raise BigTradesProtocolError(f"unsupported Big Trades JSON value: {type(value)!r}")


def big_trades_json_value(value: Any) -> Any:
    """Public strict serializer shared by WebSocket and REST responses."""

    return _json_value(value)


def _is_decimal_field(name: str) -> bool:
    lowered = name.lower()
    return any(
        token in lowered
        for token in ("price", "quantity", "notional", "vwap", "_bps", "_ticks", "threshold")
    ) and not lowered.endswith(("price_level_count",))


def _is_integer_field(name: str) -> bool:
    lowered = name.lower()
    return (
        lowered in {
            "sequence",
            "first_sequence",
            "last_sequence",
            "accepted_count",
            "dropped_count",
            "schema_version",
            "zone_schema_version",
            "source_trade_id",
            "first_trade_id",
            "last_trade_id",
            "trade_id",
            "snapshot_trade_id",
            "effective_from_trade_id",
            "fill_ordinal",
            "ordinal",
            "ordinal_for_zone",
            "horizon_seconds",
        }
        or lowered.endswith("_count")
        or lowered.endswith("_ms")
        or lowered.endswith("_milliseconds")
    )


def _validate_wire_types(value: Any, *, field_name: str = "") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise BigTradesProtocolError("JSON object keys must be strings")
            _validate_wire_types(item, field_name=key)
        return
    if isinstance(value, list):
        for item in value:
            _validate_wire_types(item, field_name=field_name)
        return
    if value is None:
        return
    if isinstance(value, float) or isinstance(value, Decimal):
        raise BigTradesProtocolError("wire payload cannot contain float or Decimal")
    if _is_decimal_field(field_name) and not isinstance(value, str):
        raise BigTradesProtocolError(f"{field_name} must be a JSON string")
    if _is_integer_field(field_name) and (
        isinstance(value, bool) or not isinstance(value, int)
    ):
        raise BigTradesProtocolError(f"{field_name} must be a JSON integer")


def validate_big_trades_update(message: Mapping[str, Any]) -> None:
    """Validate an already serialized ``BIG_TRADES_UPDATE`` envelope."""

    if set(message) != {"v", "type", "time", "symbol", "payload"}:
        raise BigTradesProtocolError("BIG_TRADES_UPDATE envelope fields do not match schema")
    if message["v"] != 1 or isinstance(message["v"], bool):
        raise BigTradesProtocolError("BIG_TRADES_UPDATE v must be integer 1")
    if message["type"] != "BIG_TRADES_UPDATE":
        raise BigTradesProtocolError("message type must be BIG_TRADES_UPDATE")
    if not isinstance(message["time"], str) or not isinstance(message["symbol"], str):
        raise BigTradesProtocolError("envelope time and symbol must be strings")
    payload = message["payload"]
    if not isinstance(payload, Mapping) or set(payload) != {
        "batch_time",
        "stream_id",
        "first_sequence",
        "last_sequence",
        "accepted_count",
        "dropped_count",
        "records",
    }:
        raise BigTradesProtocolError("BIG_TRADES_UPDATE payload fields do not match schema")
    try:
        UUID(str(payload["stream_id"]))
    except (TypeError, ValueError, AttributeError) as exc:
        raise BigTradesProtocolError("stream_id must be a UUID") from exc
    records = payload["records"]
    if not isinstance(records, list) or not records:
        raise BigTradesProtocolError("records must be a non-empty array")
    if payload["accepted_count"] != len(records):
        raise BigTradesProtocolError("accepted_count must equal records length")
    sequences: list[int] = []
    for record in records:
        if not isinstance(record, Mapping) or set(record) != {
            "kind",
            "sequence",
            "source_event_time",
            "source_trade_id",
            "record_id",
            "content_hash",
            "data",
        }:
            raise BigTradesProtocolError("record fields do not match schema")
        if record["kind"] not in BIG_TRADES_RECORD_KINDS:
            raise BigTradesProtocolError("unknown Big Trades record kind")
        if not isinstance(record["record_id"], str) or not record["record_id"]:
            raise BigTradesProtocolError("record_id must be non-empty")
        if not isinstance(record["content_hash"], str) or not _HEX_64.fullmatch(
            record["content_hash"]
        ):
            raise BigTradesProtocolError("content_hash must be lowercase SHA-256")
        if not isinstance(record["data"], Mapping):
            raise BigTradesProtocolError("record data must be an object")
        identity_field = _RECORD_ID_FIELDS[record["kind"]]
        if record["data"].get(identity_field) != record["record_id"]:
            raise BigTradesProtocolError("record identity does not match data")
        if record["data"].get("content_hash") != record["content_hash"]:
            raise BigTradesProtocolError("record content_hash does not match data")
        sequences.append(record["sequence"])
    expected = list(range(payload["first_sequence"], payload["last_sequence"] + 1))
    if sequences != expected:
        raise BigTradesProtocolError("record sequences must be contiguous")
    _validate_wire_types(message)


def build_big_trades_status(
    *,
    symbol: str,
    status: BigTradesRuntimeStatus | str,
    event_time: datetime,
    reason: Optional[str] = None,
    counters: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    parsed_status = BigTradesRuntimeStatus(status).value
    if not symbol:
        raise BigTradesProtocolError("symbol must be non-empty")
    if event_time.tzinfo is None:
        raise BigTradesProtocolError("status event_time must be timezone-aware")
    payload = {
        "status": parsed_status,
        "reason": reason,
        "counters": _json_value(dict(counters or {})),
    }
    message = {
        "v": 1,
        "type": "BIG_TRADES_STATUS",
        "time": utc_text(event_time),
        "symbol": symbol,
        "payload": payload,
    }
    _validate_wire_types(message)
    return message


@dataclass(frozen=True)
class BigTradesStreamRecord:
    sequence: int
    record: RuntimeRecord


@dataclass(frozen=True)
class BigTradesBatch:
    batch_time: datetime
    stream_id: str
    first_sequence: int
    last_sequence: int
    accepted_count: int
    dropped_count: int
    records: tuple[BigTradesStreamRecord, ...]

    def to_message(self, symbol: str) -> dict[str, Any]:
        message = {
            "v": 1,
            "type": "BIG_TRADES_UPDATE",
            "time": utc_text(self.batch_time),
            "symbol": symbol,
            "payload": {
                "batch_time": utc_text(self.batch_time),
                "stream_id": self.stream_id,
                "first_sequence": self.first_sequence,
                "last_sequence": self.last_sequence,
                "accepted_count": self.accepted_count,
                "dropped_count": self.dropped_count,
                "records": [
                    {
                        "kind": item.record.kind,
                        "sequence": item.sequence,
                        "source_event_time": utc_text(item.record.source_event_time),
                        "source_trade_id": item.record.source_trade_id,
                        "record_id": item.record.record_id,
                        "content_hash": item.record.content_hash,
                        "data": _json_value(item.record.payload),
                    }
                    for item in self.records
                ],
            },
        }
        validate_big_trades_update(message)
        return message


class BigTradesBatcherV2:
    """Thread-safe, bounded, drop-oldest unified committed-record stream."""

    def __init__(
        self,
        send: Callable[[dict[str, Any]], Awaitable[None]],
        *,
        symbol: str,
        interval_sec: float = 0.1,
        max_records_per_message: int = 200,
        pending_capacity: int = 10_000,
        stream_id: Optional[str] = None,
        utcnow: Callable[[], datetime] = _utc_now,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not symbol:
            raise ValueError("symbol must be non-empty")
        if interval_sec <= 0:
            raise ValueError("interval_sec must be > 0")
        for name, value in (
            ("max_records_per_message", max_records_per_message),
            ("pending_capacity", pending_capacity),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        resolved_stream_id = str(uuid4()) if stream_id is None else stream_id
        try:
            resolved_stream_id = str(UUID(resolved_stream_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("stream_id must be a UUID") from exc

        self._send = send
        self.symbol = symbol
        self.interval_sec = float(interval_sec)
        self.max_records_per_message = max_records_per_message
        self.pending_capacity = pending_capacity
        self.stream_id = resolved_stream_id
        self._utcnow = utcnow
        self._sleep = sleep
        self._lock = threading.Lock()
        self._pending: deque[BigTradesStreamRecord] = deque()
        self._next_sequence = 1
        self._unreported_dropped = 0
        self._closed = False

        self.accepted_records = 0
        self.sent_records = 0
        self.dropped_records = 0
        self.invalid_rejected = 0
        self.batches_sent = 0
        self.send_failures = 0
        self.inflight_records = 0
        self.pending_high_watermark = 0

    @staticmethod
    def _validate_record(record: RuntimeRecord) -> None:
        if not isinstance(record, RuntimeRecord):
            raise BigTradesProtocolError("publish accepts RuntimeRecord only")
        if record.kind not in BIG_TRADES_RECORD_KINDS:
            raise BigTradesProtocolError("unknown Big Trades record kind")
        if record.source_event_time.tzinfo is None:
            raise BigTradesProtocolError("record source_event_time must be timezone-aware")
        if record.source_trade_id is not None and (
            isinstance(record.source_trade_id, bool)
            or not isinstance(record.source_trade_id, int)
            or record.source_trade_id < 0
        ):
            raise BigTradesProtocolError("source_trade_id must be a non-negative integer")
        if not record.record_id:
            raise BigTradesProtocolError("record_id must be non-empty")
        if not _HEX_64.fullmatch(record.content_hash):
            raise BigTradesProtocolError("content_hash must be lowercase SHA-256")
        if not isinstance(record.payload, Mapping):
            raise BigTradesProtocolError("record payload must be a mapping")
        identity_field = _RECORD_ID_FIELDS[record.kind]
        if record.payload.get(identity_field) != record.record_id:
            raise BigTradesProtocolError("record identity does not match payload")
        if record.payload.get("content_hash") != record.content_hash:
            raise BigTradesProtocolError("record content_hash does not match payload")
        _json_value(record.payload)

    def publish(self, records: Iterable[RuntimeRecord]) -> int:
        """Queue committed records synchronously; return the accepted count."""

        materialized = tuple(records)
        try:
            for record in materialized:
                self._validate_record(record)
        except BigTradesProtocolError:
            with self._lock:
                self.invalid_rejected += len(materialized) or 1
            raise
        ordered = tuple(sorted(materialized, key=lambda item: item.sort_key))
        with self._lock:
            if self._closed:
                self.dropped_records += len(ordered)
                self._unreported_dropped += len(ordered)
                return 0
            for record in ordered:
                sequence = self._next_sequence
                self._next_sequence += 1
                self.accepted_records += 1
                if len(self._pending) >= self.pending_capacity:
                    self._pending.popleft()
                    self.dropped_records += 1
                    self._unreported_dropped += 1
                    logger.warning(
                        "Big Trades stream overflow: dropped oldest (count=%d)",
                        self.dropped_records,
                    )
                self._pending.append(BigTradesStreamRecord(sequence, record))
            self.pending_high_watermark = max(
                self.pending_high_watermark, len(self._pending)
            )
        return len(ordered)

    @property
    def pending(self) -> int:
        with self._lock:
            return len(self._pending)

    def continuation(self) -> dict[str, Any]:
        """Return the stream marker captured before a REST hydration query."""

        with self._lock:
            return {
                "stream_id": self.stream_id,
                "last_admitted_sequence": self._next_sequence - 1,
                "dropped_count": self.dropped_records,
            }

    def _take_batch(self) -> Optional[BigTradesBatch]:
        with self._lock:
            if not self._pending:
                return None
            count = min(len(self._pending), self.max_records_per_message)
            records = tuple(self._pending.popleft() for _ in range(count))
            dropped = self._unreported_dropped
            self._unreported_dropped = 0
            self.inflight_records += count
        now = self._utcnow()
        if now.tzinfo is None:
            raise BigTradesProtocolError("utcnow must return a timezone-aware datetime")
        return BigTradesBatch(
            batch_time=now.astimezone(timezone.utc),
            stream_id=self.stream_id,
            first_sequence=records[0].sequence,
            last_sequence=records[-1].sequence,
            accepted_count=len(records),
            dropped_count=dropped,
            records=records,
        )

    def _mark_success(self, batch: BigTradesBatch) -> None:
        with self._lock:
            self.inflight_records -= batch.accepted_count
            self.sent_records += batch.accepted_count
            self.batches_sent += 1

    def _mark_failure(self, batch: BigTradesBatch) -> None:
        with self._lock:
            self.inflight_records -= batch.accepted_count
            self.dropped_records += batch.accepted_count
            self._unreported_dropped += batch.dropped_count + batch.accepted_count
            self.send_failures += 1

    async def flush_once(self) -> bool:
        batch = self._take_batch()
        if batch is None:
            return False
        try:
            await self._send(batch.to_message(self.symbol))
        except asyncio.CancelledError:
            self._mark_failure(batch)
            raise
        except Exception:
            self._mark_failure(batch)
            logger.exception("BIG_TRADES_UPDATE send failed")
            return False
        self._mark_success(batch)
        return True

    async def run(self) -> None:
        try:
            while True:
                await self._sleep(self.interval_sec)
                while self.pending:
                    if not await self.flush_once():
                        break
        finally:
            self.close()

    def close(self) -> int:
        with self._lock:
            if self._closed:
                return 0
            self._closed = True
            pending = len(self._pending)
            self._pending.clear()
            self.dropped_records += pending
            self._unreported_dropped += pending
            return pending

    def stats_snapshot(self) -> dict[str, Any]:
        with self._lock:
            pending = len(self._pending)
            accounted = (
                self.sent_records
                + self.dropped_records
                + pending
                + self.inflight_records
            )
            return {
                "stream_id": self.stream_id,
                "accepted_records": self.accepted_records,
                "sent_records": self.sent_records,
                "batches_sent": self.batches_sent,
                "pending": pending,
                "pending_high_watermark": self.pending_high_watermark,
                "inflight_records": self.inflight_records,
                "dropped_records": self.dropped_records,
                "invalid_rejected": self.invalid_rejected,
                "send_failures": self.send_failures,
                "accounting_balanced": self.accepted_records == accounted,
            }
