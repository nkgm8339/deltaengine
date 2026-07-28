"""Phase 3 Time & Sales batching, TAPE_UPDATE, and history contracts."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import duckdb

from webapp.history import query_time_sales
from webapp.push_broker import PushBroker
from webapp.tape import TapeBatch, TapeBatcher

UTC = timezone.utc
T0 = datetime(2026, 7, 28, 10, 0, tzinfo=UTC)
STREAM_ID = "52d4f9a2-1111-4222-8333-123456789abc"
D = Decimal


def _trade(
    trade_id: int,
    *,
    offset_ms: int = 0,
    price: str = "100.1",
    quantity: str = "2.5",
    side: str = "BUY",
):
    return SimpleNamespace(
        trade_id=trade_id,
        event_time=T0 + timedelta(milliseconds=offset_ms),
        symbol="BTCUSDT",
        price=D(price),
        quantity=D(quantity),
        side=side,
    )


def test_batcher_preserves_acceptance_order_sequence_and_message_cap() -> None:
    batches: list[TapeBatch] = []

    async def send(batch: TapeBatch) -> None:
        batches.append(batch)

    batcher = TapeBatcher(
        send,
        symbol="BTCUSDT",
        interval_sec=0.1,
        max_trades_per_message=3,
        pending_capacity=20,
        stream_id=STREAM_ID,
        utcnow=lambda: T0,
    )
    for trade_id in range(10, 17):
        assert batcher.publish(_trade(trade_id, offset_ms=trade_id)) is True

    async def run() -> None:
        assert await batcher.flush_once() is True
        assert await batcher.flush_once() is True
        assert await batcher.flush_once() is True
        assert await batcher.flush_once() is False

    asyncio.run(run())
    assert batcher.interval_sec == 0.1
    assert [batch.accepted_count for batch in batches] == [3, 3, 1]
    assert [
        trade.sequence for batch in batches for trade in batch.trades
    ] == list(range(1, 8))
    assert [
        trade.trade_id for batch in batches for trade in batch.trades
    ] == list(range(10, 17))
    assert all(batch.stream_id == STREAM_ID for batch in batches)
    assert all(batch.dropped_count == 0 for batch in batches)
    assert batcher.accepted_trades == batcher.sent_trades == 7
    assert batcher.batches_sent == 3
    assert batcher.max_batch_size == 3
    assert batcher.pending_high_watermark == 7
    assert batcher.accounting_balanced is True


def test_overflow_drops_oldest_and_exposes_real_sequence_gap() -> None:
    batches: list[TapeBatch] = []

    async def send(batch: TapeBatch) -> None:
        batches.append(batch)

    batcher = TapeBatcher(
        send,
        symbol="BTCUSDT",
        max_trades_per_message=10,
        pending_capacity=3,
        stream_id=STREAM_ID,
        utcnow=lambda: T0,
    )
    for trade_id in range(1, 6):
        batcher.publish(_trade(trade_id))

    asyncio.run(batcher.flush_once())
    (batch,) = batches
    assert batch.dropped_count == 2
    assert batch.first_sequence == 3
    assert batch.last_sequence == 5
    assert [trade.trade_id for trade in batch.trades] == [3, 4, 5]
    assert batcher.accepted_trades == 5
    assert batcher.sent_trades == 3
    assert batcher.dropped_trades == 2
    assert batcher.accounted_trades == 5
    assert batcher.accounting_balanced is True


def test_slow_sender_never_blocks_publish_and_overflow_remains_accounted() -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    batches: list[TapeBatch] = []

    async def send(batch: TapeBatch) -> None:
        batches.append(batch)
        started.set()
        await release.wait()

    batcher = TapeBatcher(
        send,
        symbol="BTCUSDT",
        max_trades_per_message=2,
        pending_capacity=2,
        stream_id=STREAM_ID,
        utcnow=lambda: T0,
    )
    batcher.publish(_trade(1))

    async def run() -> None:
        first_send = asyncio.create_task(batcher.flush_once())
        await started.wait()
        for trade_id in range(2, 6):
            batcher.publish(_trade(trade_id))
        assert batcher.inflight_trades == 1
        assert batcher.pending == 2
        assert batcher.dropped_trades == 2
        assert batcher.accounting_balanced is True
        release.set()
        assert await first_send is True
        assert await batcher.flush_once() is True

    asyncio.run(run())
    assert [trade.sequence for trade in batches[1].trades] == [4, 5]
    assert batches[1].dropped_count == 2
    assert batcher.sent_trades == 3
    assert batcher.dropped_trades == 2
    assert batcher.accounting_balanced is True


def test_send_failure_becomes_explicit_drop_on_next_batch() -> None:
    attempts: list[TapeBatch] = []

    async def send(batch: TapeBatch) -> None:
        attempts.append(batch)
        if len(attempts) == 1:
            raise RuntimeError("temporary serializer failure")

    batcher = TapeBatcher(
        send,
        symbol="BTCUSDT",
        max_trades_per_message=2,
        pending_capacity=10,
        stream_id=STREAM_ID,
        utcnow=lambda: T0,
    )
    for trade_id in range(1, 4):
        batcher.publish(_trade(trade_id))

    async def run() -> None:
        assert await batcher.flush_once() is False
        assert await batcher.flush_once() is True

    asyncio.run(run())
    assert batcher.send_failures == 1
    assert batcher.dropped_trades == 2
    assert batcher.sent_trades == 1
    assert attempts[1].first_sequence == 3
    assert attempts[1].dropped_count == 2
    assert batcher.accounting_balanced is True


def test_invalid_tap_input_is_rejected_without_consuming_sequence() -> None:
    batches: list[TapeBatch] = []

    async def send(batch: TapeBatch) -> None:
        batches.append(batch)

    batcher = TapeBatcher(
        send,
        symbol="BTCUSDT",
        stream_id=STREAM_ID,
        utcnow=lambda: T0,
    )
    assert batcher.publish(_trade(1, side="UNKNOWN")) is False
    assert batcher.publish(_trade(2, quantity="0")) is False
    assert batcher.publish(_trade(3)) is True
    asyncio.run(batcher.flush_once())

    assert batcher.invalid_rejected == 2
    assert batcher.accepted_trades == 1
    assert batches[0].first_sequence == batches[0].last_sequence == 1
    assert batches[0].trades[0].trade_id == 3


def test_new_batcher_creates_new_stream_and_restarts_sequence_at_one() -> None:
    batches_a: list[TapeBatch] = []
    batches_b: list[TapeBatch] = []

    async def send_a(batch: TapeBatch) -> None:
        batches_a.append(batch)

    async def send_b(batch: TapeBatch) -> None:
        batches_b.append(batch)

    first = TapeBatcher(send_a, symbol="BTCUSDT", utcnow=lambda: T0)
    second = TapeBatcher(send_b, symbol="BTCUSDT", utcnow=lambda: T0)
    first.publish(_trade(1))
    second.publish(_trade(1))

    asyncio.run(first.flush_once())
    asyncio.run(second.flush_once())
    assert first.stream_id != second.stream_id
    assert batches_a[0].first_sequence == 1
    assert batches_b[0].first_sequence == 1


def test_replay_batch_uses_last_trade_market_time_not_wall_clock() -> None:
    batches: list[TapeBatch] = []

    async def send(batch: TapeBatch) -> None:
        batches.append(batch)

    def wall_clock_must_not_run() -> datetime:
        raise AssertionError("replay batch must not use wall clock")

    batcher = TapeBatcher(
        send,
        symbol="BTCUSDT",
        stream_id=STREAM_ID,
        batch_time_mode="event",
        utcnow=wall_clock_must_not_run,
    )
    batcher.publish(_trade(1, offset_ms=10))
    batcher.publish(_trade(2, offset_ms=25))

    asyncio.run(batcher.flush_once())

    assert batches[0].batch_time == T0 + timedelta(milliseconds=25)
    assert batcher.stats_snapshot()["batch_time_mode"] == "event"


def test_push_broker_serializes_tape_and_does_not_replay_batch_on_reconnect() -> None:
    batches: list[TapeBatch] = []

    async def collect(batch: TapeBatch) -> None:
        batches.append(batch)

    batcher = TapeBatcher(
        collect,
        symbol="BTCUSDT",
        stream_id=STREAM_ID,
        utcnow=lambda: T0 + timedelta(milliseconds=100),
    )
    batcher.publish(_trade(123, offset_ms=1, price="100.1", quantity="2.5"))
    asyncio.run(batcher.flush_once())

    broker = PushBroker("BTCUSDT")
    messages: list[dict] = []
    first_ws = MagicMock()
    first_ws.send_text = AsyncMock(
        side_effect=lambda text: messages.append(json.loads(text))
    )

    async def run() -> list[dict]:
        await broker.register(first_ws)
        await broker.on_tape_update(batches[0])
        reconnect_messages: list[dict] = []
        reconnect_ws = MagicMock()
        reconnect_ws.send_text = AsyncMock(
            side_effect=lambda text: reconnect_messages.append(json.loads(text))
        )
        await broker.register(reconnect_ws)
        return reconnect_messages

    reconnect_messages = asyncio.run(run())
    assert len(messages) == 1
    message = messages[0]
    assert message["type"] == "TAPE_UPDATE"
    payload = message["payload"]
    assert payload["stream_id"] == STREAM_ID
    assert payload["first_sequence"] == payload["last_sequence"] == 1
    assert payload["accepted_count"] == 1
    assert payload["dropped_count"] == 0
    assert payload["trades"][0] == {
        "sequence": 1,
        "trade_id": 123,
        "event_time": "2026-07-28T10:00:00.001000+00:00",
        "price": "100.1",
        "quantity": "2.5",
        "notional": "250.25",
        "side": "BUY",
    }
    assert reconnect_messages == []
    assert broker.tape_batches_broadcast == 1
    assert broker.tape_trades_broadcast == 1


def test_time_sales_history_is_oldest_first_exact_and_before_is_exclusive(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "tape.duckdb")
    con = duckdb.connect(db_path)
    con.execute(
        "CREATE TABLE trades ("
        "event_time TIMESTAMP, trade_time TIMESTAMP, trade_id BIGINT PRIMARY KEY,"
        "symbol VARCHAR, price DECIMAL(20,8), quantity DECIMAL(20,8), side VARCHAR)"
    )
    for trade_id in range(1, 504):
        second = trade_id
        con.execute(
            "INSERT INTO trades VALUES (?, ?, ?, 'BTCUSDT', ?, ?, ?)",
            [
                T0.replace(tzinfo=None) + timedelta(seconds=second),
                T0.replace(tzinfo=None) + timedelta(seconds=second),
                trade_id,
                D("100.10000000"),
                D("2.50000000"),
                "BUY" if trade_id % 2 else "SELL",
            ],
        )
    con.close()

    latest = query_time_sales(db_path, "BTCUSDT", limit=999)
    assert len(latest) == 500
    assert latest[0]["trade_id"] == 4
    assert latest[-1]["trade_id"] == 503
    assert latest[0]["event_time"].endswith("+00:00")
    assert D(latest[0]["notional"]) == D("250.25")

    before = query_time_sales(
        db_path,
        "BTCUSDT",
        limit=2,
        before=latest[0]["event_time"],
    )
    assert [trade["trade_id"] for trade in before] == [2, 3]

    same_time = T0.replace(tzinfo=None) + timedelta(seconds=1000)
    con = duckdb.connect(db_path)
    for trade_id in (504, 505):
        con.execute(
            "INSERT INTO trades VALUES (?, ?, ?, 'BTCUSDT', 100, 1, 'BUY')",
            [same_time, same_time, trade_id],
        )
    con.close()
    newest = query_time_sales(db_path, "BTCUSDT", limit=1)
    assert newest[0]["trade_id"] == 505
    tied_page = query_time_sales(
        db_path,
        "BTCUSDT",
        limit=1,
        before=newest[0]["event_time"],
        before_trade_id=newest[0]["trade_id"],
    )
    assert tied_page[0]["trade_id"] == 504
