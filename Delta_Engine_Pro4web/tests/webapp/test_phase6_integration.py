"""Phase 6 isolated restart, reconnect, replay, and no-loss integration."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from src.acquisition.replay import ListTransport
from src.normalization.normalizer import ExchangeProfile
from src.pipeline import LivePipeline
from webapp.book_projection import BookProjection
from webapp.history import query_footprints, query_time_sales
from webapp.push_broker import PushBroker
from webapp.tape import TapeBatcher


UTC = timezone.utc
T0 = datetime(2026, 7, 28, 10, 0, tzinfo=UTC)

PROFILE = ExchangeProfile.from_dict({
    "profile_name": "binance",
    "field_mapping": {
        "event_time": "E",
        "trade_time": "T",
        "trade_id": "a",
        "symbol": "s",
        "price": "p",
        "quantity": "q",
        "side_field": "m",
        "side_rule": "m == true → SELL, m == false → BUY",
    },
    "timestamp_format": "epoch_ms",
})


class FakeConnect:
    def __init__(self, messages: list[dict]) -> None:
        self.messages = messages

    async def __call__(self, _url: str, _streams: list[str]) -> ListTransport:
        return ListTransport(self.messages)


def raw_trades(first_id: int, start: datetime, count: int) -> list[dict]:
    rows = []
    for offset in range(count):
        event_time = start + timedelta(seconds=offset)
        epoch_ms = int(event_time.timestamp() * 1000)
        rows.append({
            "e": "aggTrade",
            "E": epoch_ms,
            "T": epoch_ms,
            "a": first_id + offset,
            "s": "BTCUSDT",
            "p": str(100 + (offset % 7) / 10),
            "q": "0.25",
            "m": bool(offset % 2),
        })
    return rows


def make_live(tmp_path, db_path, parquet_path) -> LivePipeline:
    return LivePipeline(
        symbol="BTCUSDT",
        timeframe="1m",
        profile=PROFILE,
        ws_url="wss://isolated.invalid/ws",
        subscribe_streams=["btcusdt@aggTrade"],
        parquet_path=parquet_path,
        duckdb_path=db_path,
        reorder_tolerance_ms=0,
        batch_size=64,
        flush_interval_sec=1,
        reconnect=False,
        flow_response_enabled=False,
    )


async def run_live_tape_session(pipeline, batcher, messages):
    pipeline.on_accepted_trade = batcher.publish
    stats = await asyncio.to_thread(
        pipeline.run,
        connect=FakeConnect(messages),
        poll_interval=0.001,
        fetch_snapshot=None,
    )
    while await batcher.flush_once():
        pass
    return stats


def test_live_restart_hydrates_storage_and_each_stream_balances(tmp_path) -> None:
    db_path = tmp_path / "restart.duckdb"
    parquet_path = tmp_path / "parquet"
    first_batches = []
    second_batches = []

    async def first_send(batch):
        first_batches.append(batch)

    async def second_send(batch):
        second_batches.append(batch)

    first_batcher = TapeBatcher(
        first_send,
        symbol="BTCUSDT",
        max_trades_per_message=31,
        pending_capacity=1000,
    )
    second_batcher = TapeBatcher(
        second_send,
        symbol="BTCUSDT",
        max_trades_per_message=31,
        pending_capacity=1000,
    )
    first_pipeline = make_live(tmp_path, db_path, parquet_path)
    second_pipeline = make_live(tmp_path, db_path, parquet_path)
    first_messages = raw_trades(1, T0 + timedelta(seconds=1), 122)
    second_messages = raw_trades(123, T0 + timedelta(minutes=4, seconds=1), 122)

    async def run_both():
        first_stats = await run_live_tape_session(
            first_pipeline, first_batcher, first_messages
        )
        second_stats = await run_live_tape_session(
            second_pipeline, second_batcher, second_messages
        )
        return first_stats, second_stats

    first_stats, second_stats = asyncio.run(run_both())

    for stats, batcher in (
        (first_stats, first_batcher),
        (second_stats, second_batcher),
    ):
        assert stats.normalized == 122
        assert batcher.accepted_trades == 122
        assert batcher.sent_trades == 122
        assert batcher.pending == batcher.inflight_trades == 0
        assert batcher.dropped_trades == 0
        assert batcher.accounting_balanced is True
    assert first_batcher.stream_id != second_batcher.stream_id
    assert [trade.sequence for batch in first_batches for trade in batch.trades] == list(
        range(1, 123)
    )
    assert [trade.sequence for batch in second_batches for trade in batch.trades] == list(
        range(1, 123)
    )

    history = query_time_sales(str(db_path), "BTCUSDT", limit=500)
    footprints = query_footprints(str(db_path), "BTCUSDT", "1m", limit=40)
    assert len(history) == 244
    assert [history[0]["trade_id"], history[-1]["trade_id"]] == [1, 244]
    assert len(footprints) == 4
    assert len({row["bar_time"] for row in footprints}) == 4


def test_reconnect_replays_latest_book_not_tape_and_exposes_sequence_gap() -> None:
    broker = PushBroker("BTCUSDT", live_dom_depth_levels=50)
    first_messages: list[dict] = []
    reconnect_messages: list[dict] = []
    first_ws = MagicMock()
    reconnect_ws = MagicMock()
    first_ws.send_text = AsyncMock(
        side_effect=lambda text: first_messages.append(json.loads(text))
    )
    reconnect_ws.send_text = AsyncMock(
        side_effect=lambda text: reconnect_messages.append(json.loads(text))
    )

    async def run() -> None:
        batcher = TapeBatcher(
            broker.on_tape_update,
            symbol="BTCUSDT",
            max_trades_per_message=2,
            pending_capacity=20,
        )
        await broker.register(first_ws)
        await broker.on_book_update(BookProjection(
            projection_time=T0,
            event_time=T0,
            last_update_id=10,
            sync_state="SYNCED",
            bids=((Decimal("100.0"), Decimal("2")),),
            asks=((Decimal("100.1"), Decimal("3")),),
            depth_levels=50,
            best_bid=Decimal("100.0"),
            best_ask=Decimal("100.1"),
            spread=Decimal("0.1"),
            age_ms=5,
        ))
        for trade_id in (1, 2):
            batcher.publish(SimpleNamespace(
                trade_id=trade_id,
                event_time=T0 + timedelta(milliseconds=trade_id),
                symbol="BTCUSDT",
                price=Decimal("100.1"),
                quantity=Decimal("1"),
                side="BUY",
            ))
        assert await batcher.flush_once() is True
        await broker.wait_until_idle(first_ws)
        await broker.unregister(first_ws)

        for trade_id in (3, 4):
            batcher.publish(SimpleNamespace(
                trade_id=trade_id,
                event_time=T0 + timedelta(milliseconds=trade_id),
                symbol="BTCUSDT",
                price=Decimal("100.1"),
                quantity=Decimal("1"),
                side="SELL",
            ))
        assert await batcher.flush_once() is True
        await broker.register(reconnect_ws)
        batcher.publish(SimpleNamespace(
            trade_id=5,
            event_time=T0 + timedelta(milliseconds=5),
            symbol="BTCUSDT",
            price=Decimal("100.2"),
            quantity=Decimal("1"),
            side="BUY",
        ))
        assert await batcher.flush_once() is True
        await broker.wait_until_idle(reconnect_ws)
        assert batcher.accounting_balanced is True

    asyncio.run(run())

    assert [message["type"] for message in first_messages] == [
        "BOOK_UPDATE", "TAPE_UPDATE"
    ]
    assert [message["type"] for message in reconnect_messages] == [
        "BOOK_UPDATE", "TAPE_UPDATE"
    ]
    first_tape = first_messages[-1]["payload"]
    reconnect_tape = reconnect_messages[-1]["payload"]
    assert first_tape["last_sequence"] == 2
    assert reconnect_tape["first_sequence"] == 5
    assert reconnect_tape["first_sequence"] != first_tape["last_sequence"] + 1
