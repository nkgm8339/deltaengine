"""Bounded inter-stage queue (ADR-002).

Pipeline stage boundaries communicate via bounded ``asyncio.Queue``. Overflow is
handled per ErrorCodes_v3.1 with no silent data loss: a dropped item is always
counted and logged (E9002). Overflow policy comes from ``queue.overflow_policy``
in configuration (YAMLReference_v3.1 §2).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import Counter
from typing import Any

logger = logging.getLogger("acquisition.queue")

ERROR_QUEUE_OVERFLOW = "E9002"  # Bounded queue overflow (ErrorCodes_v3.1)

# Supported overflow policies.
DROP_OLDEST_LOG = "drop_oldest_log"   # drop the oldest queued item, log + count
BLOCK = "block"                       # apply backpressure (await space)


class BoundedEventQueue:
    """A bounded async queue with an explicit, non-silent overflow policy."""

    def __init__(
        self,
        maxsize: int,
        overflow_policy: str = DROP_OLDEST_LOG,
        name: str = "queue",
    ) -> None:
        if maxsize < 1:
            raise ValueError("maxsize must be >= 1")
        if overflow_policy not in (DROP_OLDEST_LOG, BLOCK):
            raise ValueError(f"unsupported overflow_policy: {overflow_policy!r}")
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self.overflow_policy = overflow_policy
        self.name = name
        self.overflow_count = 0
        self.put_count = 0
        self.get_count = 0
        self.high_watermark = 0
        self.dropped_by_kind: Counter[str] = Counter()
        self._last_overflow_log_at = 0.0

    async def put(self, item: Any) -> None:
        if self.overflow_policy == BLOCK:
            await self._queue.put(item)
            self._record_put()
            return
        # DROP_OLDEST_LOG
        if self._queue.full():
            try:
                dropped = self._queue.get_nowait()  # drop oldest — never silent
            except asyncio.QueueEmpty:
                dropped = None
            self.overflow_count += 1
            dropped_kind = _event_kind(dropped)
            self.dropped_by_kind[dropped_kind] += 1
            now = time.monotonic()
            if (
                self.overflow_count == 1
                or self.overflow_count % 100 == 0
                or now - self._last_overflow_log_at >= 5.0
            ):
                self._last_overflow_log_at = now
                logger.warning(
                    "%s queue '%s' overflow: dropped oldest "
                    "(count=%d kind=%s qsize=%d/%d dropped_by_kind=%s)",
                    ERROR_QUEUE_OVERFLOW,
                    self.name,
                    self.overflow_count,
                    dropped_kind,
                    self._queue.qsize(),
                    self._queue.maxsize,
                    dict(sorted(self.dropped_by_kind.items())),
                )
        self._queue.put_nowait(item)
        self._record_put()

    async def get(self) -> Any:
        item = await self._queue.get()
        self.get_count += 1
        return item

    def get_nowait(self) -> Any:
        item = self._queue.get_nowait()
        self.get_count += 1
        return item

    def _record_put(self) -> None:
        self.put_count += 1
        self.high_watermark = max(self.high_watermark, self._queue.qsize())

    def stats_snapshot(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "maxsize": self._queue.maxsize,
            "qsize": self._queue.qsize(),
            "high_watermark": self.high_watermark,
            "put_count": self.put_count,
            "get_count": self.get_count,
            "overflow_count": self.overflow_count,
            "dropped_by_kind": dict(sorted(self.dropped_by_kind.items())),
        }

    def qsize(self) -> int:
        return self._queue.qsize()

    def full(self) -> bool:
        return self._queue.full()

    def empty(self) -> bool:
        return self._queue.empty()


def _event_kind(item: Any) -> str:
    if not isinstance(item, dict):
        return type(item).__name__
    payload = item.get("data")
    if not isinstance(payload, dict):
        payload = item
    event_type = payload.get("e")
    return {
        "aggTrade": "trade",
        "depthUpdate": "depth",
        "forceOrder": "liquidation",
    }.get(event_type, str(event_type or "unknown"))
