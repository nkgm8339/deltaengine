"""Real Binance Futures WebSocket transport (Phase6).

Spec: docs/30_Modules/WebSocket_v3.2.md (§5 lifecycle, §6 config),
terminology docs/40_Reference/ExchangeConnectorReference_v3.0.md. Concurrency:
single asyncio event loop (ADR-003). Errors: ErrorCodes_v3.1.

This is the thin, concrete transport that M4 left as the remaining runtime piece:
the ExchangeConnector is transport-agnostic and drives an injected
``connect(url, streams) -> AsyncIterator[dict]`` coroutine. Here that coroutine
opens a real ``websockets`` connection, sends the Binance SUBSCRIBE control frame,
and yields parsed message dicts. All connection/subscribe failures are surfaced as
``ConnectionError`` so the connector's existing lifecycle/reconnect logic applies
unchanged (WebSocket_v3.2 §5 RECONNECT). The library handles ping/pong
automatically (WebSocket_v3.2 §2 heartbeat).

Endpoint model: the config uses the raw single-connection endpoint
``wss://fstream.binance.com/ws`` and subscribes via a control frame
(``{"method":"SUBSCRIBE","params":[...],"id":1}``); messages then arrive
*unwrapped* (top-level ``e`` discriminates the event type). ``is_agg_trade``
is retained for backward compatibility but the live feed uses ``@trade``
(ADR-006). ``is_agg_trade_or_depth`` accepts both ``"aggTrade"`` and
``"trade"`` event types so tests using aggTrade fixtures continue to pass.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Awaitable, Callable, Optional

import websockets
from websockets.exceptions import (
    ConnectionClosed,
    ConnectionClosedOK,
    InvalidHandshake,
    InvalidURI,
    WebSocketException,
)

logger = logging.getLogger("acquisition.binance_ws")

# Errors reused from the connector's vocabulary (ErrorCodes_v3.1).
ERROR_CONNECTION_FAILED = "E2001"    # WebSocket connection failed
ERROR_INVALID_MARKET_DATA = "E2003"  # Invalid / unparseable market data

# WsConnect: the factory this module wraps (defaults to websockets.connect).
WsConnect = Callable[..., Awaitable[Any]]


def is_agg_trade(message: Any) -> bool:
    """True for a Binance aggTrade event — the trade feed the CVD path consumes.

    Used as the DataReceiver ``validate`` predicate so subscription-ack and
    order-book (depthUpdate) frames are filtered out (and counted) before
    normalization, keeping the CVD path aggTrade-only (Phase6 decision).
    Kept for backward compatibility; pipeline.py still uses this predicate.

    .. deprecated:: BugFix_Live
        Live feed uses @trade (ADR-006). Use ``is_agg_trade_or_depth`` instead.
    """
    return isinstance(message, dict) and message.get("e") == "aggTrade"


def is_agg_trade_or_depth(message: Any) -> bool:
    """True for trade events (aggTrade or trade), depthUpdate, or forceOrder — passes all feeds.

    B-1 addition: use this predicate when the pipeline should process both
    trade (CVD/Footprint/Imbalance path) and depthUpdate (Order Book /
    Absorption path). Subscription-ack frames and other control messages are
    rejected here so they are counted by DataReceiver as filtered, not silently lost.

    Accepts both "aggTrade" (@aggTrade stream) and "trade" (@trade stream) so the
    pipeline works with either Binance Futures trade stream variant.
    Also accepts "forceOrder" (@forceOrder stream, 清算注文ストリーム) for liquidation tracking.
    """
    if not isinstance(message, dict):
        return False
    return message.get("e") in ("aggTrade", "trade", "depthUpdate", "forceOrder")


async def _safe_close(ws: Any) -> None:
    try:
        await ws.close()
    except Exception:  # noqa: BLE001 - close is best-effort during teardown
        pass


class BinanceStream:
    """Async iterator over a live Binance WebSocket connection.

    Yields parsed message dicts. A clean server close ends iteration
    (``StopAsyncIteration`` — the connector treats it as a disconnect and
    reconnects); any abnormal close or protocol error is raised as
    ``ConnectionError`` (mapped to the connector's reconnect path). Malformed
    frames are logged and skipped (counted via the log, never silently lost)
    without dropping the connection.
    """

    def __init__(self, ws: Any) -> None:
        self._ws = ws
        self.malformed = 0

    def __aiter__(self) -> "BinanceStream":
        return self

    async def __anext__(self) -> dict:
        while True:
            try:
                raw = await self._ws.recv()
            except asyncio.CancelledError:
                await _safe_close(self._ws)
                raise
            except ConnectionClosedOK:
                await _safe_close(self._ws)
                raise StopAsyncIteration
            except (ConnectionClosed, WebSocketException, OSError) as exc:
                await _safe_close(self._ws)
                raise ConnectionError(f"binance stream error: {exc}") from exc
            try:
                msg = json.loads(raw)
            except (ValueError, TypeError) as exc:
                self.malformed += 1
                logger.warning("%s malformed frame skipped: %s", ERROR_INVALID_MARKET_DATA, exc)
                continue
            # Combined-stream endpoint wraps events as {"stream":...,"data":{...}}.
            if isinstance(msg, dict) and "data" in msg:
                return msg["data"]
            return msg


def make_binance_connect(
    *,
    ping_interval: Optional[float] = None,
    ping_timeout: Optional[float] = 20,
    subscribe_id: int = 1,
    ws_connect: Optional[WsConnect] = None,
) -> Callable[[str, list[str]], Awaitable[AsyncIterator[dict]]]:
    """Build a ConnectFn for the ExchangeConnector.

    The returned coroutine opens the connection, sends the Binance SUBSCRIBE
    control frame for ``streams``, and returns a ``BinanceStream``. Any failure
    to connect or subscribe is raised as ``ConnectionError``.

    ``ping_interval`` maps to the WebSocket_v3.2 heartbeat; ``ws_connect`` is
    injectable so the adapter is unit-testable without a network (defaults to
    ``websockets.connect``).
    """
    connector: WsConnect = ws_connect or websockets.connect

    async def connect(url: str, streams: list[str]) -> AsyncIterator[dict]:
        try:
            ws = await connector(url, ping_interval=ping_interval, ping_timeout=ping_timeout)
        except (OSError, InvalidURI, InvalidHandshake, WebSocketException) as exc:
            raise ConnectionError(f"binance connect failed: {exc}") from exc

        subscribe = {"method": "SUBSCRIBE", "params": list(streams), "id": subscribe_id}
        try:
            await ws.send(json.dumps(subscribe))
        except (WebSocketException, OSError) as exc:
            await _safe_close(ws)
            raise ConnectionError(f"binance subscribe failed: {exc}") from exc

        logger.info("binance subscribed streams=%s url=%s", streams, url)
        return BinanceStream(ws)

    return connect


# Default ConnectFn (heartbeat/ping left to the connector's configured interval
# when built via make_binance_connect(ping_interval=...)). Kept for convenience.
binance_connect = make_binance_connect()
