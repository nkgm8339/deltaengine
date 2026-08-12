"""Deterministic source-time millisecond ordering for Big Trades V2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .models import BigTradeFill


@dataclass(frozen=True)
class OrderingRejection:
    reason: str
    trade: BigTradeFill


class SameMillisecondTradeOrderBuffer:
    """Sort one event-time millisecond by integer trade ID before release.

    The normalized source is expected to be non-decreasing by event-time
    millisecond. A trade for an older millisecond cannot be repaired after a
    newer bucket has been observed and is rejected visibly.
    """

    def __init__(self) -> None:
        self._bucket_ms: Optional[int] = None
        self._bucket: list[BigTradeFill] = []
        self._last_released_ms: Optional[int] = None
        self.rejections: list[OrderingRejection] = []

    def push(self, trade: BigTradeFill) -> tuple[BigTradeFill, ...]:
        current_ms = trade.event_time_ms
        if self._last_released_ms is not None and current_ms <= self._last_released_ms:
            self.rejections.append(OrderingRejection("LATE_AFTER_RELEASE", trade))
            return ()
        if self._bucket_ms is not None and current_ms < self._bucket_ms:
            self.rejections.append(OrderingRejection("LATE_AFTER_RELEASE", trade))
            return ()

        if self._bucket_ms is None:
            self._bucket_ms = current_ms
            self._bucket.append(trade)
            return ()
        if current_ms == self._bucket_ms:
            self._bucket.append(trade)
            return ()

        released = self._release_bucket()
        self._bucket_ms = current_ms
        self._bucket.append(trade)
        return released

    def flush(self) -> tuple[BigTradeFill, ...]:
        return self._release_bucket()

    def _release_bucket(self) -> tuple[BigTradeFill, ...]:
        if self._bucket_ms is None:
            return ()
        released = tuple(sorted(self._bucket, key=lambda trade: trade.trade_id))
        self._last_released_ms = self._bucket_ms
        self._bucket_ms = None
        self._bucket = []
        return released

    @property
    def pending_count(self) -> int:
        return len(self._bucket)

    @property
    def rejected_count(self) -> int:
        return len(self.rejections)
