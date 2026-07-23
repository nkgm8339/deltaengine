"""Tests for PushBroker."""
import asyncio
from unittest.mock import AsyncMock

from webapp.broker import PushBroker


def test_broadcast_reaches_connected_client():
    async def _run():
        broker = PushBroker()
        ws = AsyncMock()
        await broker.connect(ws)
        await broker.broadcast({"type": "TEST"})
        ws.send_text.assert_called_once()
        text = ws.send_text.call_args[0][0]
        assert '"TEST"' in text

    asyncio.run(_run())


def test_broadcast_removes_dead_client():
    async def _run():
        broker = PushBroker()
        ws = AsyncMock()
        ws.send_text = AsyncMock(side_effect=Exception("disconnected"))
        await broker.connect(ws)
        assert ws in broker._clients
        await broker.broadcast({"type": "TEST"})
        assert ws not in broker._clients

    asyncio.run(_run())


def test_disconnect_removes_client():
    async def _run():
        broker = PushBroker()
        ws = AsyncMock()
        await broker.connect(ws)
        assert ws in broker._clients
        await broker.disconnect(ws)
        assert ws not in broker._clients

    asyncio.run(_run())
