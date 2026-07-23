"""Unit tests for MT5Server and helpers (6 tests, network-free except local loopback)."""

from __future__ import annotations

import asyncio
import json

import pytest

from src.mt5.adapter import MT5Server, _ClientSession, analysis_to_mt5_message
from src.ai.analysis import AnalysisResult
from datetime import datetime, timezone
from decimal import Decimal

UTC = timezone.utc


async def _make_server(**kwargs) -> MT5Server:
    defaults = dict(
        bind_address="127.0.0.1",
        port=0,
        max_clients=3,
        heartbeat_interval=60.0,
        max_buffer_messages=10,
    )
    defaults.update(kwargs)
    srv = MT5Server(**defaults)
    await srv.start()
    return srv


# ── 1. start / stop ──────────────────────────────────────────────────────────

def test_server_start_stop() -> None:
    async def _test():
        srv = await _make_server()
        assert srv.local_port > 0
        await srv.stop()
    asyncio.run(_test())


# ── 2. broadcast → client receives SIGNAL ────────────────────────────────────

def test_broadcast_received() -> None:
    async def _test():
        srv = await _make_server(max_clients=1)
        port = srv.local_port

        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        await asyncio.sleep(0.05)

        msg = {"type": "SIGNAL", "time": "2026-01-01T00:00:00+00:00",
               "symbol": "BTCUSDT", "payload": {"market_state": "BULL"}}
        await srv.broadcast(msg)

        line = await asyncio.wait_for(reader.readline(), timeout=2.0)
        received = json.loads(line.decode())
        assert received["type"] == "SIGNAL"
        assert received["symbol"] == "BTCUSDT"

        writer.close()
        await asyncio.sleep(0.05)
        await srv.stop()
    asyncio.run(_test())


# ── 3. HEARTBEAT received ─────────────────────────────────────────────────────

def test_heartbeat_received() -> None:
    async def _test():
        srv = await _make_server(max_clients=1, heartbeat_interval=0.1)
        port = srv.local_port

        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        await asyncio.sleep(0.05)

        line = await asyncio.wait_for(reader.readline(), timeout=2.0)
        received = json.loads(line.decode())
        assert received["type"] == "HEARTBEAT"
        assert "time" in received

        writer.close()
        await asyncio.sleep(0.05)
        await srv.stop()
    asyncio.run(_test())


# ── 4. max_clients exceeded → connection rejected ────────────────────────────

def test_max_clients_exceeded() -> None:
    async def _test():
        srv = await _make_server(max_clients=1)
        port = srv.local_port

        r1, w1 = await asyncio.open_connection("127.0.0.1", port)
        await asyncio.sleep(0.05)
        assert srv.client_count == 1

        r2, w2 = await asyncio.open_connection("127.0.0.1", port)
        await asyncio.sleep(0.1)

        # Server closed the 2nd connection; client reads EOF.
        data = await asyncio.wait_for(r2.read(100), timeout=1.0)
        assert data == b""
        assert srv.clients_rejected >= 1

        w1.close()
        w2.close()
        await asyncio.sleep(0.05)
        await srv.stop()
    asyncio.run(_test())


# ── 5. buffer full → non-SIGNAL dropped first ────────────────────────────────

def test_buffer_drop_policy() -> None:
    session = _ClientSession(maxsize=3)

    # Fill buffer with non-SIGNAL messages.
    session.put_nowait({"type": "CVD"})
    session.put_nowait({"type": "IMBALANCE"})
    session.put_nowait({"type": "CVD"})
    assert session.dropped == 0

    # Add a SIGNAL when buffer is full → oldest non-SIGNAL (CVD) evicted.
    dropped = session.put_nowait({"type": "SIGNAL"})
    assert dropped is True
    assert session.dropped == 1
    # Buffer should now be [IMBALANCE, CVD, SIGNAL].
    assert session._buffer[0]["type"] == "IMBALANCE"
    assert session._buffer[2]["type"] == "SIGNAL"


# ── 6. client disconnect → resource released ─────────────────────────────────

def test_client_disconnect_cleanup() -> None:
    async def _test():
        srv = await _make_server(max_clients=2)
        port = srv.local_port

        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        await asyncio.sleep(0.05)
        assert srv.client_count == 1

        writer.close()
        await asyncio.sleep(0.15)
        assert srv.client_count == 0

        await srv.stop()
    asyncio.run(_test())
