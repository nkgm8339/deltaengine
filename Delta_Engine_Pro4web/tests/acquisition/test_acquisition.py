"""Tests for the acquisition layer (M4).

Covers ADR-002 bounded queue overflow, WebSocket connector reconnect + lifecycle,
DataReceiver validation/ordering, JSON Lines recording and deterministic replay.
Async tests run via asyncio.run (no pytest-asyncio dependency). Reconnect delays
use an injected no-op sleep so tests are fast and deterministic.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.acquisition.connector import ConnectionState, ExchangeConnector
from src.acquisition.event_queue import BoundedEventQueue
from src.acquisition.receiver import STOP, DataReceiver, JsonlRecorder
from src.acquisition.replay import ListTransport, ReplaySource, replay_connect


async def _nosleep(_seconds: float) -> None:
    return None


class FlakyConnect:
    """A ConnectFn that raises ConnectionError `fail_times`, then serves messages."""

    def __init__(self, fail_times: int, messages: list[dict]) -> None:
        self.fail_times = fail_times
        self.messages = messages
        self.calls = 0

    async def __call__(self, url: str, streams: list[str]) -> ListTransport:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ConnectionError("simulated connect failure")
        return ListTransport(self.messages)


def _drain(queue: BoundedEventQueue) -> list:
    out = []
    while queue.qsize():
        out.append(queue.get_nowait())
    return out


# ============================ BoundedEventQueue ===============================
def test_queue_overflow_drops_oldest_and_counts() -> None:
    async def scenario():
        q = BoundedEventQueue(maxsize=2, name="test")
        await q.put(1)
        await q.put(2)
        await q.put(3)  # full -> drop oldest (1), count overflow
        return q, _drain(q)

    q, items = asyncio.run(scenario())
    assert items == [2, 3]
    assert q.overflow_count == 1


def test_queue_stats_expose_capacity_and_dropped_event_kind() -> None:
    async def scenario():
        q = BoundedEventQueue(maxsize=2, name="receiver_out")
        await q.put({"stream": "x", "data": {"e": "aggTrade"}})
        await q.put({"stream": "x", "data": {"e": "depthUpdate"}})
        await q.put({"stream": "x", "data": {"e": "forceOrder"}})
        items = _drain(q)
        return q.stats_snapshot(), items

    stats, items = asyncio.run(scenario())
    assert [item["data"]["e"] for item in items] == [
        "depthUpdate",
        "forceOrder",
    ]
    assert stats == {
        "name": "receiver_out",
        "maxsize": 2,
        "qsize": 0,
        "high_watermark": 2,
        "put_count": 3,
        "get_count": 2,
        "overflow_count": 1,
        "dropped_by_kind": {"trade": 1},
    }


def test_queue_fifo_order() -> None:
    async def scenario():
        q = BoundedEventQueue(maxsize=10)
        for i in range(5):
            await q.put(i)
        return [await q.get() for _ in range(5)]

    assert asyncio.run(scenario()) == [0, 1, 2, 3, 4]


# ============================ connector: reconnect ============================
def test_connector_reconnects_then_delivers_in_order() -> None:
    async def scenario():
        out = BoundedEventQueue(maxsize=100)
        connect = FlakyConnect(fail_times=2, messages=[{"t": 1}, {"t": 2}, {"t": 3}])
        conn = ExchangeConnector(
            url="wss://x", subscribe_streams=["s"], out_queue=out, connect=connect,
            reconnect=True, reconnect_max_retries=0,
            treat_stream_end_as_disconnect=False, sleep=_nosleep,
        )
        await conn.run()
        return conn, _drain(out)

    conn, messages = asyncio.run(scenario())
    assert messages == [{"t": 1}, {"t": 2}, {"t": 3}]      # order preserved
    assert conn.reconnect_count == 2
    assert conn.messages_out == 3
    assert ConnectionState.RECONNECTING in conn.state_history
    assert ConnectionState.SUBSCRIBED in conn.state_history
    assert conn.state is ConnectionState.DISCONNECTED


def test_connector_records_raw_frame_observability_before_queue_put() -> None:
    async def scenario():
        wall = datetime(2026, 8, 3, tzinfo=timezone.utc)
        monotonic = 100.25
        observed = {}

        class ObservingOut:
            async def put(self, message):
                observed["message"] = message
                observed["wall"] = conn.last_message_received_at
                observed["monotonic"] = conn.last_message_received_monotonic

        conn = ExchangeConnector(
            url="wss://x",
            subscribe_streams=["s"],
            out_queue=ObservingOut(),
            connect=FlakyConnect(fail_times=0, messages=[{"t": 1}]),
            reconnect=False,
            treat_stream_end_as_disconnect=False,
            wall_clock=lambda: wall,
            monotonic_clock=lambda: monotonic,
        )
        await conn.run()
        return conn, observed

    conn, observed = asyncio.run(scenario())
    assert observed == {
        "message": {"t": 1},
        "wall": datetime(2026, 8, 3, tzinfo=timezone.utc),
        "monotonic": 100.25,
    }
    assert conn.messages_out == 1


def test_connector_queue_wait_does_not_shift_receive_timestamp() -> None:
    async def scenario():
        wall = [datetime(2026, 8, 3, tzinfo=timezone.utc)]
        monotonic = [10.0]
        entered = asyncio.Event()
        release = asyncio.Event()

        class BlockingOut:
            async def put(self, _message):
                entered.set()
                await release.wait()

        conn = ExchangeConnector(
            url="wss://x",
            subscribe_streams=["s"],
            out_queue=BlockingOut(),
            connect=FlakyConnect(fail_times=0, messages=[{"t": 1}]),
            reconnect=False,
            treat_stream_end_as_disconnect=False,
            wall_clock=lambda: wall[0],
            monotonic_clock=lambda: monotonic[0],
        )
        task = asyncio.create_task(conn.run())
        await entered.wait()
        received_wall = conn.last_message_received_at
        received_monotonic = conn.last_message_received_monotonic
        wall[0] += timedelta(seconds=30)
        monotonic[0] += 30.0
        release.set()
        await task
        return conn, received_wall, received_monotonic

    conn, received_wall, received_monotonic = asyncio.run(scenario())
    assert received_wall == datetime(2026, 8, 3, tzinfo=timezone.utc)
    assert received_monotonic == 10.0
    assert conn.last_message_received_at == received_wall
    assert conn.last_message_received_monotonic == received_monotonic


def test_connector_message_age_uses_only_monotonic_clock() -> None:
    async def scenario():
        wall = [datetime(2026, 8, 3, tzinfo=timezone.utc)]
        monotonic = [50.0]
        out = BoundedEventQueue(maxsize=10)
        conn = ExchangeConnector(
            url="wss://x",
            subscribe_streams=["s"],
            out_queue=out,
            connect=FlakyConnect(fail_times=0, messages=[{"t": 1}]),
            reconnect=False,
            treat_stream_end_as_disconnect=False,
            wall_clock=lambda: wall[0],
            monotonic_clock=lambda: monotonic[0],
        )
        assert conn.message_age_ms() is None
        await conn.run()
        wall[0] += timedelta(hours=5)
        monotonic[0] += 0.375
        return conn.message_age_ms()

    assert asyncio.run(scenario()) == 375


def test_connector_gives_up_after_max_retries() -> None:
    class AlwaysFail:
        calls = 0

        async def __call__(self, url, streams):
            AlwaysFail.calls += 1
            raise ConnectionError("down")

    async def scenario():
        out = BoundedEventQueue(maxsize=10)
        conn = ExchangeConnector(
            url="wss://x", subscribe_streams=["s"], out_queue=out, connect=AlwaysFail(),
            reconnect=True, reconnect_max_retries=2, sleep=_nosleep,
        )
        await conn.run()
        return conn, _drain(out)

    conn, messages = asyncio.run(scenario())
    assert messages == []
    assert conn.reconnect_count == 2          # 2 reconnect attempts then escalate
    assert conn.errors == 3                    # initial + 2 reconnect failures
    assert conn.state is ConnectionState.DISCONNECTED


def test_connector_no_reconnect_when_disabled() -> None:
    async def scenario():
        out = BoundedEventQueue(maxsize=10)
        connect = FlakyConnect(fail_times=1, messages=[{"t": 1}])
        conn = ExchangeConnector(
            url="wss://x", subscribe_streams=["s"], out_queue=out, connect=connect,
            reconnect=False, sleep=_nosleep,
        )
        await conn.run()
        return conn

    conn = asyncio.run(scenario())
    assert conn.reconnect_count == 0
    assert conn.errors == 1


# ============================ DataReceiver ====================================
def test_receiver_forwards_in_order_and_drops_invalid() -> None:
    async def scenario():
        src = BoundedEventQueue(maxsize=100)
        dst = BoundedEventQueue(maxsize=100)
        for m in [{"trade_id": 1}, {"trade_id": 2}, "NOT_A_DICT", {}, {"trade_id": 3}]:
            await src.put(m)
        await src.put(STOP)
        receiver = DataReceiver(src, dst)
        await receiver.run()
        return receiver, _drain(dst)

    receiver, forwarded = asyncio.run(scenario())
    assert forwarded == [{"trade_id": 1}, {"trade_id": 2}, {"trade_id": 3}]
    assert receiver.invalid == 2        # "NOT_A_DICT" and empty dict
    assert receiver.forwarded == 3


def test_receiver_counts_out_of_order() -> None:
    async def scenario():
        src = BoundedEventQueue(maxsize=100)
        dst = BoundedEventQueue(maxsize=100)
        for tid in (1, 3, 2):
            await src.put({"trade_id": tid})
        await src.put(STOP)
        receiver = DataReceiver(src, dst, sequence_key=lambda m: m["trade_id"])
        await receiver.run()
        return receiver

    receiver = asyncio.run(scenario())
    assert receiver.out_of_order == 1   # trade_id 2 arrives after 3
    assert receiver.forwarded == 3      # still forwarded; reordering is the Normalizer's job


# ============================ recording + replay ==============================
def test_jsonl_recording_replays_identically(tmp_path: Path) -> None:
    path = tmp_path / "raw.jsonl"
    messages = [{"b": 2, "a": 1}, {"a": 3, "z": [1, 2]}]

    async def scenario():
        recorder = JsonlRecorder(path)
        for m in messages:
            recorder.write(m)
        recorder.close()
        return ReplaySource(path).read_all()

    assert asyncio.run(scenario()) == messages


def test_replay_source_feeds_connector(tmp_path: Path) -> None:
    path = tmp_path / "raw.jsonl"

    async def scenario():
        recorder = JsonlRecorder(path)
        for m in [{"t": 1}, {"t": 2}]:
            recorder.write(m)
        recorder.close()
        out = BoundedEventQueue(maxsize=100)
        conn = ExchangeConnector(
            url="replay", subscribe_streams=["s"], out_queue=out,
            connect=lambda url, streams: replay_connect(path),
            reconnect=False, treat_stream_end_as_disconnect=False, sleep=_nosleep,
        )
        await conn.run()
        return _drain(out)

    assert asyncio.run(scenario()) == [{"t": 1}, {"t": 2}]


# ============================ integration =====================================
def test_connector_to_receiver_pipeline(tmp_path: Path) -> None:
    record_path = tmp_path / "rec.jsonl"

    async def scenario():
        out = BoundedEventQueue(maxsize=100)
        dst = BoundedEventQueue(maxsize=100)
        connect = FlakyConnect(fail_times=1, messages=[{"trade_id": 1}, {"trade_id": 2}])
        conn = ExchangeConnector(
            url="wss://x", subscribe_streams=["s"], out_queue=out, connect=connect,
            reconnect=True, treat_stream_end_as_disconnect=False, sleep=_nosleep,
        )
        await conn.run()
        await out.put(STOP)
        receiver = DataReceiver(out, dst, recorder=JsonlRecorder(record_path))
        await receiver.run()
        return _drain(dst)

    forwarded = asyncio.run(scenario())
    assert forwarded == [{"trade_id": 1}, {"trade_id": 2}]
    # recorded stream replays identically (deterministic replay input for M6)
    assert ReplaySource(record_path).read_all() == [{"trade_id": 1}, {"trade_id": 2}]
