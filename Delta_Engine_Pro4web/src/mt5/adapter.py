"""MT5 Adapter — asyncio TCP server that pushes analysis results to MT5 clients.

Spec: MT5Adapter_v3.0.md §5.
Message format (§5.1): newline-delimited JSON {"type":..., "time":..., "symbol":..., "payload":{...}}
Types: SIGNAL | CVD | IMBALANCE | ABSORPTION | HEARTBEAT

Drop policy (§5.2): per-client buffer of max_buffer_messages.
  Full + new message: evict oldest non-SIGNAL first; if none, drop incoming.

Heartbeat: sent every heartbeat_interval seconds.
  3 consecutive missed ACKs from a client → disconnect.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from ..ai.analysis import AnalysisResult

logger = logging.getLogger("mt5.adapter")


class _ClientSession:
    """Per-client send buffer with SIGNAL-priority drop policy."""

    def __init__(self, maxsize: int) -> None:
        self.maxsize = maxsize
        self._buffer: list[dict] = []
        self._event = asyncio.Event()
        self.consecutive_missed_acks: int = 0
        self.dropped: int = 0

    def put_nowait(self, msg: dict) -> bool:
        """Enqueue msg. Returns True if a message was dropped (new or existing)."""
        if len(self._buffer) < self.maxsize:
            self._buffer.append(msg)
            self._event.set()
            return False
        # Buffer full: evict oldest non-SIGNAL to make room.
        for i, item in enumerate(self._buffer):
            if item.get("type") != "SIGNAL":
                self._buffer.pop(i)
                self._buffer.append(msg)
                self.dropped += 1
                self._event.set()
                return True
        # All buffered messages are SIGNAL: drop incoming.
        self.dropped += 1
        return True

    async def get(self) -> dict:
        """Wait for and return the next message."""
        while not self._buffer:
            self._event.clear()
            if not self._buffer:
                await self._event.wait()
        msg = self._buffer.pop(0)
        if not self._buffer:
            self._event.clear()
        return msg


class MT5Server:
    """Asyncio TCP server that broadcasts trading signals to MT5 clients."""

    def __init__(
        self,
        bind_address: str = "127.0.0.1",
        port: int = 5555,
        max_clients: int = 3,
        heartbeat_interval: float = 5.0,
        max_buffer_messages: int = 1000,
    ) -> None:
        self._bind_address = bind_address
        self._port = port
        self._max_clients = max_clients
        self._heartbeat_interval = heartbeat_interval
        self._max_buffer_messages = max_buffer_messages

        self._server: Optional[asyncio.AbstractServer] = None
        self._clients: dict[asyncio.StreamWriter, _ClientSession] = {}
        self._lock = asyncio.Lock()
        self._heartbeat_task: Optional[asyncio.Task] = None

        self.clients_rejected: int = 0
        self.messages_dropped: int = 0

    @property
    def local_port(self) -> int:
        """Actual bound port (useful when port=0 was requested)."""
        if self._server and self._server.sockets:
            return self._server.sockets[0].getsockname()[1]
        return self._port

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_client,
            self._bind_address,
            self._port,
        )
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("MT5Server listening on %s:%d", self._bind_address, self.local_port)

    async def stop(self) -> None:
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task

        async with self._lock:
            writers = list(self._clients.keys())

        for writer in writers:
            with contextlib.suppress(Exception):
                writer.close()
                await writer.wait_closed()

        if self._server:
            self._server.close()
            await self._server.wait_closed()
        logger.info("MT5Server stopped")

    async def broadcast(self, msg: dict) -> None:
        """Enqueue msg to all connected clients' buffers."""
        async with self._lock:
            items = list(self._clients.items())
        for _, session in items:
            if session.put_nowait(msg):
                self.messages_dropped += 1
                logger.warning(
                    "MT5 buffer overflow: dropped type=%s", msg.get("type")
                )

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        peer = writer.get_extra_info("peername")
        async with self._lock:
            if len(self._clients) >= self._max_clients:
                self.clients_rejected += 1
                logger.warning(
                    "MT5 max_clients=%d reached, rejecting %s",
                    self._max_clients, peer,
                )
                writer.close()
                with contextlib.suppress(Exception):
                    await writer.wait_closed()
                return
            session = _ClientSession(self._max_buffer_messages)
            self._clients[writer] = session

        logger.info("MT5 client connected: %s (total=%d)", peer, len(self._clients))
        sender = asyncio.create_task(self._sender(writer, session))
        receiver = asyncio.create_task(self._receiver(reader, session))
        try:
            await asyncio.wait([sender, receiver], return_when=asyncio.FIRST_COMPLETED)
        finally:
            for t in [sender, receiver]:
                if not t.done():
                    t.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await t
            async with self._lock:
                self._clients.pop(writer, None)
            with contextlib.suppress(Exception):
                writer.close()
                await writer.wait_closed()
            logger.info("MT5 client disconnected: %s", peer)

    async def _sender(
        self, writer: asyncio.StreamWriter, session: _ClientSession
    ) -> None:
        try:
            while True:
                msg = await session.get()
                line = json.dumps(msg, default=str) + "\n"
                writer.write(line.encode())
                await writer.drain()
        except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
            pass
        except Exception as exc:
            logger.debug("MT5 sender error: %s", exc)

    async def _receiver(
        self, reader: asyncio.StreamReader, session: _ClientSession
    ) -> None:
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                with contextlib.suppress(Exception):
                    msg = json.loads(line.decode())
                    if msg.get("type") == "ACK":
                        session.consecutive_missed_acks = 0
        except (asyncio.CancelledError, ConnectionResetError):
            pass
        except Exception as exc:
            logger.debug("MT5 receiver error: %s", exc)

    async def _heartbeat_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._heartbeat_interval)
                ts = datetime.now(timezone.utc).isoformat()
                hb = {"type": "HEARTBEAT", "time": ts}

                async with self._lock:
                    items = list(self._clients.items())

                to_drop: list[asyncio.StreamWriter] = []
                for writer, session in items:
                    session.consecutive_missed_acks += 1
                    if session.consecutive_missed_acks >= 3:
                        to_drop.append(writer)
                        continue
                    if session.put_nowait(hb):
                        self.messages_dropped += 1

                for writer in to_drop:
                    logger.warning(
                        "MT5 disconnecting client after 3 missed ACKs: %s",
                        writer.get_extra_info("peername"),
                    )
                    async with self._lock:
                        self._clients.pop(writer, None)
                    with contextlib.suppress(Exception):
                        writer.close()
                        await writer.wait_closed()
        except asyncio.CancelledError:
            pass


def analysis_to_mt5_message(result: AnalysisResult) -> dict:
    """Convert AnalysisResult to SIGNAL message for MT5 broadcast."""
    return {
        "type": "SIGNAL",
        "time": result.analysis_time.isoformat(),
        "symbol": result.symbol,
        "payload": {
            "market_state": result.market_state,
            "confidence": str(result.confidence),
            "risk_level": result.risk_level,
            "summary": result.summary,
            "reasons": list(result.reasons),
        },
    }
