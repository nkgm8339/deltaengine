"""Exchange WebSocket connector (WebSocket module, MOD-002).

Spec: docs/30_Modules/WebSocket_v3.2.md (§5 lifecycle, §6 config). Terminology
and connection states: docs/40_Reference/ExchangeConnectorReference_v3.0.md.
Concurrency: single asyncio event loop (ADR-003). Errors: ErrorCodes_v3.1.

The connector is transport-agnostic: the actual socket is provided by an
injected ``connect`` coroutine (``connect(url, streams) -> AsyncIterator[dict]``)
that raises ``ConnectionError`` on failure. This keeps the lifecycle/reconnect
logic fully unit-testable with deterministic fakes and no network dependency.
A concrete websockets-based transport is a thin adapter added at deployment
(reported as the remaining runtime piece for M4).
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import Any, AsyncIterator, Awaitable, Callable, Optional

from .event_queue import BoundedEventQueue

logger = logging.getLogger("acquisition.connector")

ERROR_CONNECTION_FAILED = "E2001"   # WebSocket connection failed
ERROR_CONNECTION_TIMEOUT = "E2002"  # WebSocket timeout


class ConnectionState(str, Enum):
    """ExchangeConnectorReference connection lifecycle states."""

    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    SUBSCRIBED = "SUBSCRIBED"
    RECONNECTING = "RECONNECTING"


# connect(url, streams) -> async iterator of raw message dicts
ConnectFn = Callable[[str, list[str]], Awaitable[AsyncIterator[dict]]]
SleepFn = Callable[[float], Awaitable[None]]


class ExchangeConnector:
    """Manages a WebSocket connection lifecycle and reconnection.

    Delivers raw message dicts to ``out_queue`` (a BoundedEventQueue, ADR-002).
    """

    def __init__(
        self,
        url: str,
        subscribe_streams: list[str],
        out_queue: BoundedEventQueue,
        connect: ConnectFn,
        *,
        reconnect: bool = True,
        reconnect_delay_sec: int = 5,
        reconnect_max_retries: int = 0,   # 0 = unlimited
        connect_timeout_sec: int = 10,
        heartbeat_sec: int = 30,
        treat_stream_end_as_disconnect: bool = True,
        sleep: SleepFn = asyncio.sleep,
    ) -> None:
        if not url:
            raise ValueError("url is required")
        if not subscribe_streams:
            raise ValueError("subscribe_streams must be non-empty")
        self.url = url
        self.subscribe_streams = list(subscribe_streams)
        self._out = out_queue
        self._connect = connect
        self.reconnect = reconnect
        self.reconnect_delay_sec = reconnect_delay_sec
        self.reconnect_max_retries = reconnect_max_retries
        self.connect_timeout_sec = connect_timeout_sec
        self.heartbeat_sec = heartbeat_sec
        self.treat_stream_end_as_disconnect = treat_stream_end_as_disconnect
        self._sleep = sleep
        # observable state / counters
        self.state = ConnectionState.DISCONNECTED
        self.state_history: list[ConnectionState] = []
        self.reconnect_count = 0
        self.messages_out = 0
        self.errors = 0
        self._stopped = False

    @classmethod
    def from_config(
        cls,
        websocket_config: Any,
        out_queue: BoundedEventQueue,
        connect: ConnectFn,
        **overrides: Any,
    ) -> "ExchangeConnector":
        """Build from the `websocket` section of a validated Config (ConfigNode)."""
        params = dict(
            url=websocket_config.url,
            subscribe_streams=list(websocket_config.subscribe_streams),
            reconnect=websocket_config.reconnect,
            reconnect_delay_sec=websocket_config.reconnect_delay_sec,
            reconnect_max_retries=websocket_config.reconnect_max_retries,
            connect_timeout_sec=websocket_config.connect_timeout_sec,
            heartbeat_sec=websocket_config.heartbeat_sec,
        )
        params.update(overrides)
        return cls(out_queue=out_queue, connect=connect, **params)

    def stop(self) -> None:
        self._stopped = True

    def _set_state(self, state: ConnectionState) -> None:
        self.state = state
        self.state_history.append(state)
        logger.info("connector state -> %s", state.value)

    def _log_error(self, code: str, message: str) -> None:
        self.errors += 1
        logger.warning("%s %s", code, message)

    def _should_reconnect(self, attempts: int) -> bool:
        if not self.reconnect:
            return False
        return self.reconnect_max_retries == 0 or attempts < self.reconnect_max_retries

    async def _open(self) -> AsyncIterator[dict]:
        coro = self._connect(self.url, self.subscribe_streams)
        if self.connect_timeout_sec and self.connect_timeout_sec > 0:
            return await asyncio.wait_for(coro, self.connect_timeout_sec)
        return await coro

    async def run(self) -> None:
        """Run the connection lifecycle until stopped or reconnection is exhausted."""
        self._set_state(ConnectionState.CONNECTING)
        attempts = 0
        while not self._stopped:
            try:
                transport = await self._open()
            except asyncio.TimeoutError as exc:
                self._log_error(ERROR_CONNECTION_TIMEOUT, f"connect timeout: {exc}")
                if not self._should_reconnect(attempts):
                    break
                attempts += 1
                self.reconnect_count += 1
                self._set_state(ConnectionState.RECONNECTING)
                await self._sleep(self.reconnect_delay_sec)
                continue
            except ConnectionError as exc:
                self._log_error(ERROR_CONNECTION_FAILED, f"connect failed: {exc}")
                if not self._should_reconnect(attempts):
                    break
                attempts += 1
                self.reconnect_count += 1
                self._set_state(ConnectionState.RECONNECTING)
                await self._sleep(self.reconnect_delay_sec)
                continue

            # connected + subscribed
            self._set_state(ConnectionState.CONNECTED)
            self._set_state(ConnectionState.SUBSCRIBED)
            attempts = 0
            stream_error = False
            try:
                async for message in transport:  # RECEIVE / MONITOR
                    self.messages_out += 1
                    await self._out.put(message)
            except ConnectionError as exc:
                stream_error = True
                self._log_error(ERROR_CONNECTION_FAILED, f"stream error: {exc}")

            if not stream_error and not self.treat_stream_end_as_disconnect:
                break  # clean end of a finite stream (e.g. replay) — stop
            if not self._should_reconnect(attempts):
                break
            attempts += 1
            self.reconnect_count += 1
            self._set_state(ConnectionState.RECONNECTING)
            await self._sleep(self.reconnect_delay_sec)

        self._set_state(ConnectionState.DISCONNECTED)
