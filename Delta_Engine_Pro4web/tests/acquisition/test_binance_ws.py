"""Tests for the real Binance WebSocket transport adapter (Phase6).

No network: the ``websockets`` connection is replaced by an injected fake so the
adapter's subscribe frame, message parsing, error mapping (-> ConnectionError),
clean-close handling (-> StopAsyncIteration) and malformed-frame skipping are all
verified deterministically. Async tests run via asyncio.run (no pytest-asyncio).
"""

from __future__ import annotations

import asyncio
import json

import pytest
from websockets.exceptions import ConnectionClosedOK, WebSocketException

from src.acquisition.binance_ws import (
    BinanceStream,
    is_agg_trade,
    is_agg_trade_or_depth,
    make_binance_connect,
)


class FakeWS:
    """A minimal stand-in for a websockets client connection."""

    def __init__(self, frames, *, recv_exc=None, send_exc=None) -> None:
        self._frames = list(frames)
        self._recv_exc = recv_exc
        self._send_exc = send_exc
        self.sent: list[str] = []
        self.closed = False

    async def send(self, data: str) -> None:
        if self._send_exc is not None:
            raise self._send_exc
        self.sent.append(data)

    async def recv(self) -> str:
        if self._frames:
            return self._frames.pop(0)
        if self._recv_exc is not None:
            raise self._recv_exc
        raise ConnectionClosedOK(None, None)

    async def close(self) -> None:
        self.closed = True


def _agg(a: int, m: bool = False) -> str:
    return json.dumps(
        {"e": "aggTrade", "E": 1, "s": "BTCUSDT", "a": a, "p": "100", "q": "1", "T": 1, "m": m}
    )


# ============================ is_agg_trade filter =============================
def test_is_agg_trade_selects_only_aggtrade() -> None:
    assert is_agg_trade({"e": "aggTrade", "a": 1}) is True
    assert is_agg_trade({"e": "depthUpdate"}) is False
    assert is_agg_trade({"result": None, "id": 1}) is False   # subscription ack
    assert is_agg_trade("not a dict") is False
    assert is_agg_trade({}) is False


# ============================ connect + subscribe =============================
def test_connect_sends_subscribe_and_yields_parsed_dicts() -> None:
    fake = FakeWS([_agg(1), _agg(2)])

    async def fake_connect(url, **kwargs):
        return fake

    async def scenario():
        connect = make_binance_connect(ping_interval=30, ws_connect=fake_connect)
        stream = await connect("wss://x/ws", ["btcusdt@aggTrade"])
        out = []
        async for message in stream:
            out.append(message)
        return out

    messages = asyncio.run(scenario())
    # SUBSCRIBE control frame was sent with the requested params.
    assert len(fake.sent) == 1
    sub = json.loads(fake.sent[0])
    assert sub == {"method": "SUBSCRIBE", "params": ["btcusdt@aggTrade"], "id": 1}
    assert [m["a"] for m in messages] == [1, 2]   # parsed dicts, in order
    assert fake.closed is True                     # clean close on stream end


def test_connect_failure_maps_to_connection_error() -> None:
    async def failing_connect(url, **kwargs):
        raise OSError("refused")

    async def scenario():
        connect = make_binance_connect(ws_connect=failing_connect)
        await connect("wss://x/ws", ["s"])

    with pytest.raises(ConnectionError):
        asyncio.run(scenario())


def test_subscribe_failure_maps_to_connection_error_and_closes() -> None:
    fake = FakeWS([], send_exc=WebSocketException("send failed"))

    async def fake_connect(url, **kwargs):
        return fake

    async def scenario():
        connect = make_binance_connect(ws_connect=fake_connect)
        await connect("wss://x/ws", ["s"])

    with pytest.raises(ConnectionError):
        asyncio.run(scenario())
    assert fake.closed is True


# ============================ stream error mapping ============================
def test_stream_error_maps_to_connection_error_and_closes() -> None:
    fake = FakeWS([_agg(1)], recv_exc=WebSocketException("boom"))

    async def scenario():
        stream = BinanceStream(fake)
        first = await stream.__anext__()          # yields the one good frame
        with pytest.raises(ConnectionError):
            await stream.__anext__()               # then the injected error
        return first

    first = asyncio.run(scenario())
    assert first["a"] == 1
    assert fake.closed is True


def test_clean_close_ends_iteration() -> None:
    fake = FakeWS([_agg(1)])   # exhausts, then ConnectionClosedOK

    async def scenario():
        out = []
        async for message in BinanceStream(fake):
            out.append(message)
        return out

    assert [m["a"] for m in asyncio.run(scenario())] == [1]


def test_malformed_frame_skipped_not_fatal() -> None:
    fake = FakeWS(["{not json", _agg(7)])

    async def scenario():
        stream = BinanceStream(fake)
        out = []
        async for message in stream:
            out.append(message)
        return stream, out

    stream, out = asyncio.run(scenario())
    assert [m["a"] for m in out] == [7]   # bad frame skipped, good frame delivered
    assert stream.malformed == 1


# ============================ is_agg_trade_or_depth (B-1) ====================
def test_is_agg_trade_still_filters_depth() -> None:
    """Existing predicate remains unchanged — depth is still filtered out."""
    assert is_agg_trade({"e": "depthUpdate", "s": "BTCUSDT"}) is False
    assert is_agg_trade({"e": "aggTrade", "a": 1}) is True


def test_is_agg_trade_or_depth_accepts_aggtrade() -> None:
    assert is_agg_trade_or_depth({"e": "aggTrade", "a": 1}) is True


def test_is_agg_trade_or_depth_accepts_depth() -> None:
    assert is_agg_trade_or_depth({"e": "depthUpdate", "b": [], "a": []}) is True


def test_is_agg_trade_or_depth_rejects_subscription_ack() -> None:
    assert is_agg_trade_or_depth({"result": None, "id": 1}) is False
    assert is_agg_trade_or_depth("not a dict") is False
    assert is_agg_trade_or_depth({}) is False


# ============================ combined-stream unwrapping (BugFix_Live_v1) =====
def test_wrapped_combined_stream_message_is_unwrapped() -> None:
    """BinanceStream unwraps {"stream":...,"data":{...}} combined-stream format.

    The /ws endpoint with multiple subscriptions wraps each event; the inner
    ``data`` dict must be returned so is_agg_trade_or_depth can match ``e``.
    """
    inner = {"e": "aggTrade", "E": 1, "s": "BTCUSDT", "a": 42,
             "p": "100", "q": "1", "T": 1, "m": False}
    wrapped = json.dumps({"stream": "btcusdt@aggTrade", "data": inner})
    fake = FakeWS([wrapped])

    async def scenario():
        stream = BinanceStream(fake)
        return await stream.__anext__()

    msg = asyncio.run(scenario())
    assert msg.get("e") == "aggTrade"
    assert msg.get("a") == 42
    assert is_agg_trade_or_depth(msg) is True
