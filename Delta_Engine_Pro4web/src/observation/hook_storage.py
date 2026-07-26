"""Separate append-only Parquet storage for calibrated Hook events."""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from src.orderflow.hooks.models import HookEvent

logger = logging.getLogger("observation.hook_storage")

_STOP = object()
_Q8 = Decimal("0.00000001")

HOOK_EVENT_SCHEMA = pa.schema(
    [
        pa.field("hook_event_id", pa.string(), nullable=False),
        pa.field("hook_id", pa.string(), nullable=False),
        pa.field("detector_version", pa.string(), nullable=False),
        pa.field("config_hash", pa.string(), nullable=False),
        pa.field("input_manifest_hash", pa.string()),
        pa.field("symbol", pa.string(), nullable=False),
        pa.field("side", pa.string(), nullable=False),
        pa.field("direction_hint", pa.string(), nullable=False),
        pa.field("source_time", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("received_time", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("available_time", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("detected_time", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("source_sequence", pa.string()),
        pa.field("anchor_price", pa.decimal128(38, 8)),
        pa.field("binance_bid", pa.decimal128(38, 8)),
        pa.field("binance_ask", pa.decimal128(38, 8)),
        pa.field("binance_mid", pa.decimal128(38, 8)),
        pa.field("metric_name", pa.string(), nullable=False),
        pa.field("metric_value", pa.decimal128(38, 8), nullable=False),
        pa.field("threshold_value", pa.decimal128(38, 8)),
        pa.field("threshold_quantile", pa.decimal128(18, 8)),
        pa.field("episode_id", pa.string()),
        pa.field("quality_status", pa.string(), nullable=False),
        pa.field("quality_flags_json", pa.string(), nullable=False),
        pa.field("evidence_json", pa.string(), nullable=False),
    ]
)


def _quantize(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(_Q8, rounding=ROUND_HALF_EVEN)


class HookEventStorage:
    """Background Hook writer isolated from all existing storage tables."""

    def __init__(
        self,
        root: str | Path,
        *,
        queue_depth: int = 10_000,
        batch_size: int = 250,
        flush_interval_sec: int = 5,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        self.session_id = f"session-{stamp}-{uuid.uuid4().hex[:8]}"
        self.session_dir = self.root / self.session_id
        self.session_dir.mkdir(exist_ok=False)
        self._queue: queue.Queue[object] = queue.Queue(maxsize=queue_depth)
        self._batch_size = batch_size
        self._flush_interval_sec = flush_interval_sec
        self._lock = threading.Lock()
        self._closed = False
        self._part = 0
        self.accepted = 0
        self.written = 0
        self.dropped = 0
        self.high_watermark = 0
        self.writer_error: str | None = None
        self._thread = threading.Thread(
            target=self._writer_loop,
            name="hook-event-storage",
            daemon=True,
        )
        self._thread.start()

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    def add_event(self, event: HookEvent) -> bool:
        if not isinstance(event, HookEvent):
            raise TypeError("event must be HookEvent")
        with self._lock:
            if self._closed or self.writer_error is not None:
                return False
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            with self._lock:
                self.dropped += 1
            logger.error("Hook event storage queue is full; event was not persisted")
            return False
        with self._lock:
            self.accepted += 1
            self.high_watermark = max(self.high_watermark, self._queue.qsize())
        return True

    def _write_batch(self, events: list[HookEvent]) -> None:
        rows = []
        for event in events:
            row = event.to_row()
            for key in (
                "anchor_price",
                "binance_bid",
                "binance_ask",
                "binance_mid",
                "metric_value",
                "threshold_value",
                "threshold_quantile",
            ):
                row[key] = _quantize(row[key])
            rows.append(row)
        table = pa.Table.from_pylist(rows, schema=HOOK_EVENT_SCHEMA)
        self._part += 1
        path = self.session_dir / f"part-{self._part:06d}.parquet"
        with path.open("xb") as sink:
            pq.write_table(table, sink, compression="snappy")
            sink.flush()
            os.fsync(sink.fileno())
        with self._lock:
            self.written += len(events)

    def _writer_loop(self) -> None:
        batch: list[HookEvent] = []
        last_flush = time.monotonic()
        try:
            while True:
                remaining = max(
                    0.05,
                    self._flush_interval_sec - (time.monotonic() - last_flush),
                )
                try:
                    item = self._queue.get(timeout=remaining)
                except queue.Empty:
                    item = None
                if item is _STOP:
                    if batch:
                        self._write_batch(batch)
                    break
                if isinstance(item, HookEvent):
                    batch.append(item)
                if batch and (
                    len(batch) >= self._batch_size
                    or time.monotonic() - last_flush >= self._flush_interval_sec
                ):
                    self._write_batch(batch)
                    batch = []
                    last_flush = time.monotonic()
        except Exception as exc:
            self.writer_error = f"{type(exc).__name__}: {exc}"
            logger.exception("Hook event storage writer failed")

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        if self._thread.is_alive():
            try:
                self._queue.put(_STOP, timeout=5)
            except queue.Full:
                self.writer_error = self.writer_error or "stop marker queue timeout"
        self._thread.join(timeout=30)
        if self._thread.is_alive():
            self.writer_error = self.writer_error or "writer did not stop within 30 seconds"
        summary = {
            "schema_version": 1,
            "session_id": self.session_id,
            "closed_at": datetime.now(timezone.utc).isoformat(),
            "accepted": self.accepted,
            "written": self.written,
            "dropped": self.dropped,
            "high_watermark": self.high_watermark,
            "writer_error": self.writer_error,
            "valid": (
                self.writer_error is None
                and self.dropped == 0
                and self.accepted == self.written
            ),
        }
        with (self.session_dir / "session_summary.json").open(
            "x", encoding="utf-8", newline="\n"
        ) as handle:
            json.dump(summary, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

    def stats(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "pending": self.pending,
            "accepted": self.accepted,
            "written": self.written,
            "dropped": self.dropped,
            "high_watermark": self.high_watermark,
            "writer_error": self.writer_error,
        }
