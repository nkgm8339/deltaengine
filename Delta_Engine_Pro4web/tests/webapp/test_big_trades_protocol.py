from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from src.orderflow.big_trades.runtime import RuntimeRecord
from webapp.big_trades_protocol import (
    BigTradesBatcherV2,
    BigTradesProtocolError,
    build_big_trades_status,
    validate_big_trades_update,
)
from webapp.push_broker import PushBroker


UTC = timezone.utc


def _record(kind: str, identifier: str, *, trade_id: int = 1) -> RuntimeRecord:
    digest = (identifier[-1] if identifier[-1] in "abcdef" else "a") * 64
    identity_field = {
        "EVENT_CREATED": "event_id",
        "ZONE_CREATED": "zone_id",
        "ZONE_INTERACTION": "interaction_id",
        "ZONE_EVENT_LINK": "link_id",
        "RESULT_SNAPSHOT": "snapshot_id",
        "CANDLE_OBSERVATION": "candle_observation_id",
        "USER_ASSESSMENT": "assessment_id",
        "UNKNOWN": "event_id",
    }[kind]
    return RuntimeRecord(
        kind=kind,
        source_event_time=datetime(2026, 8, 12, 0, 0, tzinfo=UTC),
        source_trade_id=trade_id,
        record_id=identifier,
        content_hash=digest,
        payload={
            identity_field: identifier,
            "content_hash": digest,
            "marker_price": Decimal("123.4500"),
            "marker_price_mode": "LAST_PRICE",
            "aggregate_quantity": Decimal("7.5"),
            "fill_count": 2,
            "duration_ms": 40,
            "same_as_origin_side": True,
        },
    )


def test_bt2_w211_to_w214_unified_envelope_precedence_and_strict_types():
    async def run() -> None:
        sent = []

        async def send(message):
            sent.append(message)

        batcher = BigTradesBatcherV2(
            send,
            symbol="BTCUSDT",
            stream_id="12345678-1234-5678-1234-567812345678",
        )
        batcher.publish(
            (
                _record("ZONE_CREATED", "btz2_b"),
                _record("EVENT_CREATED", "bt2_a"),
            )
        )
        assert await batcher.flush_once()
        message = sent[0]
        validate_big_trades_update(message)
        UUID(message["payload"]["stream_id"])
        assert message["type"] == "BIG_TRADES_UPDATE"
        assert [item["kind"] for item in message["payload"]["records"]] == [
            "EVENT_CREATED",
            "ZONE_CREATED",
        ]
        assert [item["sequence"] for item in message["payload"]["records"]] == [1, 2]
        data = message["payload"]["records"][0]["data"]
        assert data["marker_price"] == "123.45"
        assert data["marker_price_mode"] == "LAST_PRICE"
        assert data["aggregate_quantity"] == "7.5"
        assert type(data["fill_count"]) is int
        assert type(data["duration_ms"]) is int
        assert type(data["same_as_origin_side"]) is bool

    asyncio.run(run())


def test_status_numeric_price_path_size_is_not_misclassified_as_decimal() -> None:
    message = build_big_trades_status(
        symbol="BTCUSDT",
        status="MANUAL_READY",
        event_time=datetime(2026, 8, 12, tzinfo=UTC),
        counters={"price_path_index_size": 25_000},
    )
    assert message["payload"]["counters"]["price_path_index_size"] == 25_000


def test_bt2_w212_unknown_record_kind_is_rejected():
    batcher = BigTradesBatcherV2(AsyncMock(), symbol="BTCUSDT")
    with pytest.raises(BigTradesProtocolError, match="unknown"):
        batcher.publish((_record("UNKNOWN", "bt2_a"),))


def test_bt2_w213_boolean_is_not_accepted_as_integer():
    async def run() -> None:
        sent = []
        batcher = BigTradesBatcherV2(
            lambda message: sent.append(message),  # type: ignore[arg-type]
            symbol="BTCUSDT",
        )
        batch = batcher._take_batch()
        assert batch is None

        valid = BigTradesBatcherV2(AsyncMock(), symbol="BTCUSDT")
        valid.publish((_record("EVENT_CREATED", "bt2_a"),))
        built = valid._take_batch()
        assert built is not None
        message = built.to_message("BTCUSDT")
        message["payload"]["records"][0]["data"]["fill_count"] = True
        with pytest.raises(BigTradesProtocolError, match="fill_count"):
            validate_big_trades_update(message)

    asyncio.run(run())


def test_bt2_w215_w216_stream_restart_and_drop_gap_are_visible():
    async def run() -> None:
        first_messages = []
        first = BigTradesBatcherV2(
            lambda message: _append(first_messages, message),
            symbol="BTCUSDT",
            pending_capacity=2,
            max_records_per_message=2,
        )
        first.publish(
            (
                _record("EVENT_CREATED", "bt2_a", trade_id=1),
                _record("EVENT_CREATED", "bt2_b", trade_id=2),
                _record("EVENT_CREATED", "bt2_c", trade_id=3),
            )
        )
        await first.flush_once()
        payload = first_messages[0]["payload"]
        assert payload["first_sequence"] == 2
        assert payload["last_sequence"] == 3
        assert payload["dropped_count"] == 1
        assert first.stats_snapshot()["accounting_balanced"] is True

        second = BigTradesBatcherV2(AsyncMock(), symbol="BTCUSDT")
        assert second.stream_id != first.stream_id
        assert second.continuation()["last_admitted_sequence"] == 0

    asyncio.run(run())


async def _append(target, value):
    target.append(value)


def test_bt2_w217_status_is_cached_first_for_reconnect():
    async def run() -> None:
        broker = PushBroker("BTCUSDT")
        await broker.on_trade(
            SimpleNamespace(
                event_time=datetime(2026, 8, 12, tzinfo=UTC),
                trade_id=1,
                price=Decimal("1"),
                quantity=Decimal("1"),
                side="BUY",
            )
        )
        await broker.on_big_trades_status("MANUAL_READY", reason="test")
        messages = []

        class Socket:
            async def send_text(self, text):
                messages.append(json.loads(text))

        ws = Socket()
        await broker.register(ws)
        await broker.wait_until_idle(ws)
        assert [message["type"] for message in messages[:2]] == [
            "BIG_TRADES_STATUS",
            "TICK",
        ]
        await broker.unregister(ws)

    asyncio.run(run())
