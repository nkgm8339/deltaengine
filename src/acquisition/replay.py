"""Replay + in-memory transports for the acquisition layer.

Replay mode (YAMLReference_v3.1 §5): when enabled, the WebSocket module is
replaced by a file reader that reads recorded raw events (one JSON object per
line) from ``replay.data_path``. All downstream processing is identical to live
mode, enabling deterministic replay (M6).

``ListTransport`` is the in-memory equivalent used by unit tests and by
connecting a fixed message sequence to the ExchangeConnector.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import AsyncIterator, Iterable


class ListTransport:
    """An async iterator over a fixed list of raw message dicts."""

    def __init__(self, messages: Iterable[dict]) -> None:
        self._messages = list(messages)

    def __aiter__(self) -> "ListTransport":
        self._index = 0
        return self

    async def __anext__(self) -> dict:
        if self._index >= len(self._messages):
            raise StopAsyncIteration
        message = self._messages[self._index]
        self._index += 1
        return message


class ReplaySource:
    """Reads recorded JSON Lines and yields raw message dicts, in file order."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def __aiter__(self) -> AsyncIterator[dict]:
        self._lines = [
            line for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()
        ]
        self._index = 0
        return self

    async def __anext__(self) -> dict:
        if self._index >= len(self._lines):
            raise StopAsyncIteration
        line = self._lines[self._index]
        self._index += 1
        return json.loads(line)

    def read_all(self) -> list[dict]:
        """Synchronous helper: load the whole recording as a list (M6 replay)."""
        return [
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]


async def replay_connect(path: str | Path):
    """A ConnectFn-compatible factory that replays a JSON Lines file once.

    Usage: ExchangeConnector(..., connect=lambda url, streams: replay_connect(path),
    treat_stream_end_as_disconnect=False).
    """
    source = ReplaySource(path)
    return source
