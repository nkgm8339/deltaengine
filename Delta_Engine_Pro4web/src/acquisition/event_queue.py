"""Bounded inter-stage queue (ADR-002).

Pipeline stage boundaries communicate via bounded ``asyncio.Queue``. Overflow is
handled per ErrorCodes_v3.1 with no silent data loss: a dropped item is always
counted and logged (E9002). Overflow policy comes from ``queue.overflow_policy``
in configuration (YAMLReference_v3.1 §2).
"""

from __future__ import annotations

import asyncio
import logging
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

    async def put(self, item: Any) -> None:
        if self.overflow_policy == BLOCK:
            await self._queue.put(item)
            return
        # DROP_OLDEST_LOG
        if self._queue.full():
            try:
                self._queue.get_nowait()  # drop oldest — never silent
            except asyncio.QueueEmpty:
                pass
            self.overflow_count += 1
            logger.warning(
                "%s queue '%s' overflow: dropped oldest (count=%d)",
                ERROR_QUEUE_OVERFLOW, self.name, self.overflow_count,
            )
        self._queue.put_nowait(item)

    async def get(self) -> Any:
        return await self._queue.get()

    def get_nowait(self) -> Any:
        return self._queue.get_nowait()

    def qsize(self) -> int:
        return self._queue.qsize()

    def full(self) -> bool:
        return self._queue.full()

    def empty(self) -> bool:
        return self._queue.empty()
