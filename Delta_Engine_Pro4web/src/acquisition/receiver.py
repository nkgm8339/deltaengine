"""Data Receiver (MOD-001).

Spec: docs/30_Modules/DataReceiver_v3.1.md. Consumes raw messages from the
WebSocket output queue, validates payloads, optionally records them as JSON
Lines (for deterministic replay — implementation instruction §12 / replay.data_path),
and forwards valid events to the Data Normalizer via a bounded queue (ADR-002).

Errors: ErrorCodes_v3.1 (E2003 invalid market data). No silent loss — invalid
and out-of-order events are counted and logged.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Optional

from .event_queue import BoundedEventQueue

logger = logging.getLogger("acquisition.receiver")

ERROR_INVALID_MARKET_DATA = "E2003"  # Invalid market data received

# Sentinel placed on the source queue to signal end-of-stream to the receiver.
STOP = object()


class JsonlRecorder:
    """Append-only JSON Lines recorder with deterministic serialization.

    One JSON object per line, keys sorted, compact separators — so a recorded
    stream replays byte-identically (deterministic replay, M6).
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("w", encoding="utf-8")
        self.written = 0

    def write(self, obj: dict) -> None:
        self._handle.write(json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n")
        self.written += 1

    def close(self) -> None:
        self._handle.close()

    def __enter__(self) -> "JsonlRecorder":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def default_validate(message: Any) -> bool:
    """Minimal payload validation: a non-empty mapping (ExchangeConnectorReference)."""
    return isinstance(message, dict) and bool(message)


class DataReceiver:
    """Validate → (record) → forward raw events, preserving arrival order."""

    def __init__(
        self,
        source: BoundedEventQueue,
        destination: BoundedEventQueue,
        *,
        recorder: Optional[JsonlRecorder] = None,
        validate: Callable[[Any], bool] = default_validate,
        sequence_key: Optional[Callable[[dict], Any]] = None,
        on_valid_message: Optional[Callable[[dict], Any]] = None,
    ) -> None:
        self._source = source
        self._destination = destination
        self._recorder = recorder
        self._validate = validate
        self._sequence_key = sequence_key
        self._on_valid_message = on_valid_message
        self._last_seq: Any = None
        # counters
        self.forwarded = 0
        self.invalid = 0
        self.out_of_order = 0

    async def run(self) -> None:
        """Consume until the STOP sentinel; forward valid events in order."""
        while True:
            message = await self._source.get()
            if message is STOP:
                break
            if not self._validate(message):
                self.invalid += 1
                logger.warning("%s invalid payload discarded: %r", ERROR_INVALID_MARKET_DATA, message)
                continue
            if self._sequence_key is not None:
                key = self._sequence_key(message)
                if self._last_seq is not None and key < self._last_seq:
                    self.out_of_order += 1  # informational; reordering is the Normalizer's job
                self._last_seq = key
            if self._recorder is not None:
                self._recorder.write(message)
            if self._on_valid_message is not None:
                self._on_valid_message(message)
            await self._destination.put(message)
            self.forwarded += 1
