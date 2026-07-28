"""Bounded, no-silent-loss Time & Sales batching for accepted trades."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Awaitable, Callable
from uuid import UUID, uuid4

logger = logging.getLogger("webapp.tape")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class TapeTrade:
    """One accepted canonical trade with a stream-local UI sequence."""

    sequence: int
    trade_id: int
    event_time: datetime
    price: Decimal
    quantity: Decimal
    notional: Decimal
    side: str


@dataclass(frozen=True)
class TapeBatch:
    """One ordered TAPE_UPDATE payload before JSON serialization."""

    batch_time: datetime
    stream_id: str
    first_sequence: int
    last_sequence: int
    accepted_count: int
    dropped_count: int
    trades: tuple[TapeTrade, ...]


class TapeBatcher:
    """Thread-safe accepted-trade tap with a bounded drop-oldest queue.

    ``publish`` never awaits and can be called by the live event-loop thread or
    the replay worker thread.  The async consumer drains at a bounded cadence.
    """

    def __init__(
        self,
        send: Callable[[TapeBatch], Awaitable[None]],
        *,
        symbol: str,
        interval_sec: float = 0.1,
        max_trades_per_message: int = 250,
        pending_capacity: int = 10_000,
        stream_id: str | None = None,
        batch_time_mode: str = "wall",
        utcnow: Callable[[], datetime] = _utc_now,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not symbol:
            raise ValueError("symbol must be non-empty")
        if interval_sec <= 0:
            raise ValueError("interval_sec must be > 0")
        if max_trades_per_message < 1:
            raise ValueError("max_trades_per_message must be >= 1")
        if pending_capacity < 1:
            raise ValueError("pending_capacity must be >= 1")
        if batch_time_mode not in {"wall", "event"}:
            raise ValueError("batch_time_mode must be 'wall' or 'event'")
        resolved_stream_id = str(uuid4()) if stream_id is None else stream_id
        try:
            resolved_stream_id = str(UUID(resolved_stream_id))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("stream_id must be a UUID") from exc

        self._send = send
        self.symbol = symbol
        self.interval_sec = float(interval_sec)
        self.max_trades_per_message = int(max_trades_per_message)
        self.pending_capacity = int(pending_capacity)
        self.stream_id = resolved_stream_id
        self.batch_time_mode = batch_time_mode
        self._utcnow = utcnow
        self._sleep = sleep
        self._lock = threading.Lock()
        self._pending: deque[TapeTrade] = deque()
        self._next_sequence = 1
        self._unreported_dropped = 0
        self._closed = False

        self.accepted_trades = 0
        self.sent_trades = 0
        self.dropped_trades = 0
        self.invalid_rejected = 0
        self.batches_sent = 0
        self.max_batch_size = 0
        self.pending_high_watermark = 0
        self.send_failures = 0
        self.inflight_trades = 0

    def _validated_values(
        self, trade: Any
    ) -> tuple[int, datetime, Decimal, Decimal, str] | None:
        try:
            trade_id = trade.trade_id
            event_time = trade.event_time
            symbol = trade.symbol
            price = trade.price
            quantity = trade.quantity
            side = trade.side
        except AttributeError:
            return None
        if (
            isinstance(trade_id, bool)
            or not isinstance(trade_id, int)
            or not isinstance(event_time, datetime)
            or event_time.tzinfo is None
            or symbol != self.symbol
            or not isinstance(price, Decimal)
            or not isinstance(quantity, Decimal)
            or not price.is_finite()
            or not quantity.is_finite()
            or price <= 0
            or quantity <= 0
            or side not in {"BUY", "SELL"}
        ):
            return None
        return (
            trade_id,
            event_time.astimezone(timezone.utc),
            price,
            quantity,
            side,
        )

    def publish(self, trade: Any) -> bool:
        """Queue one accepted trade without blocking the analysis path."""
        values = self._validated_values(trade)
        if values is None:
            with self._lock:
                self.invalid_rejected += 1
            logger.warning("invalid trade rejected by Time & Sales tap")
            return False
        trade_id, event_time, price, quantity, side = values

        with self._lock:
            sequence = self._next_sequence
            self._next_sequence += 1
            self.accepted_trades += 1
            entry = TapeTrade(
                sequence=sequence,
                trade_id=trade_id,
                event_time=event_time,
                price=price,
                quantity=quantity,
                notional=price * quantity,
                side=side,
            )
            if self._closed:
                self.dropped_trades += 1
                self._unreported_dropped += 1
                return False
            if len(self._pending) >= self.pending_capacity:
                self._pending.popleft()
                self.dropped_trades += 1
                self._unreported_dropped += 1
                logger.warning(
                    "E9002 tape queue overflow: dropped oldest (count=%d)",
                    self.dropped_trades,
                )
            self._pending.append(entry)
            self.pending_high_watermark = max(
                self.pending_high_watermark, len(self._pending)
            )
            return True

    @property
    def pending(self) -> int:
        with self._lock:
            return len(self._pending)

    @property
    def accounted_trades(self) -> int:
        with self._lock:
            return (
                self.sent_trades
                + self.dropped_trades
                + len(self._pending)
                + self.inflight_trades
            )

    @property
    def accounting_balanced(self) -> bool:
        with self._lock:
            return self.accepted_trades == (
                self.sent_trades
                + self.dropped_trades
                + len(self._pending)
                + self.inflight_trades
            )

    def stats_snapshot(self) -> dict[str, int | bool | str]:
        """Return one lock-consistent accounting snapshot for health output."""
        with self._lock:
            pending = len(self._pending)
            accounted = (
                self.sent_trades
                + self.dropped_trades
                + pending
                + self.inflight_trades
            )
            return {
                "stream_id": self.stream_id,
                "batch_time_mode": self.batch_time_mode,
                "accepted_trades": self.accepted_trades,
                "sent_trades": self.sent_trades,
                "batches_sent": self.batches_sent,
                "max_batch_size": self.max_batch_size,
                "pending": pending,
                "pending_high_watermark": self.pending_high_watermark,
                "inflight_trades": self.inflight_trades,
                "dropped_trades": self.dropped_trades,
                "invalid_rejected": self.invalid_rejected,
                "send_failures": self.send_failures,
                "accounted_trades": accounted,
                "accounting_balanced": self.accepted_trades == accounted,
            }

    def _take_batch(self) -> TapeBatch | None:
        with self._lock:
            if not self._pending:
                return None
            count = min(len(self._pending), self.max_trades_per_message)
            trades = tuple(self._pending.popleft() for _ in range(count))
            dropped_count = self._unreported_dropped
            self._unreported_dropped = 0
            self.inflight_trades += len(trades)
        if self.batch_time_mode == "event":
            batch_time = trades[-1].event_time
        else:
            batch_time = self._utcnow()
            if batch_time.tzinfo is None:
                raise ValueError("utcnow must return a timezone-aware datetime")
            batch_time = batch_time.astimezone(timezone.utc)
        return TapeBatch(
            batch_time=batch_time,
            stream_id=self.stream_id,
            first_sequence=trades[0].sequence,
            last_sequence=trades[-1].sequence,
            accepted_count=len(trades),
            dropped_count=dropped_count,
            trades=trades,
        )

    def _mark_send_success(self, batch: TapeBatch) -> None:
        with self._lock:
            self.inflight_trades -= batch.accepted_count
            self.sent_trades += batch.accepted_count
            self.batches_sent += 1
            self.max_batch_size = max(self.max_batch_size, batch.accepted_count)

    def _mark_send_failure(self, batch: TapeBatch) -> None:
        with self._lock:
            self.inflight_trades -= batch.accepted_count
            self.dropped_trades += batch.accepted_count
            self._unreported_dropped += (
                batch.dropped_count + batch.accepted_count
            )
            self.send_failures += 1

    async def flush_once(self) -> bool:
        """Send one bounded batch. Return True only when it was sent."""
        batch = self._take_batch()
        if batch is None:
            return False
        try:
            await self._send(batch)
        except asyncio.CancelledError:
            self._mark_send_failure(batch)
            raise
        except Exception:
            self._mark_send_failure(batch)
            logger.exception("TAPE_UPDATE send failed")
            return False
        self._mark_send_success(batch)
        return True

    async def run(self) -> None:
        try:
            while True:
                await self._sleep(self.interval_sec)
                while self.pending:
                    if not await self.flush_once():
                        break
        finally:
            self.close()

    def close(self) -> int:
        """Stop accepting queueable work and account pending trades as dropped."""
        with self._lock:
            if self._closed:
                return 0
            self._closed = True
            pending = len(self._pending)
            self._pending.clear()
            self.dropped_trades += pending
            self._unreported_dropped += pending
            return pending
