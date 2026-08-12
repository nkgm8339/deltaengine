"""Fail-closed latest-value projection for the browser LIVE DOM."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from itertools import chain
from typing import Any, Awaitable, Callable

logger = logging.getLogger("webapp.book_projection")

SYNCED = "SYNCED"
FAIL_CLOSED_STATES = frozenset({
    "NO_SNAPSHOT",
    "RESYNCING",
    "STALE",
    "EMPTY",
    "LOCKED",
    "CROSSED",
    "INVALID",
})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class BookProjection:
    """One bounded LIVE DOM view, independent from the analysis update path."""

    projection_time: datetime
    event_time: datetime | None
    last_update_id: int | None
    sync_state: str
    bids: tuple[tuple[Decimal, Decimal], ...]
    asks: tuple[tuple[Decimal, Decimal], ...]
    depth_levels: int
    best_bid: Decimal | None
    best_ask: Decimal | None
    spread: Decimal | None
    age_ms: int | None

    @property
    def fingerprint(self) -> tuple:
        """State identity excluding projection wall time and increasing age."""
        return (
            self.last_update_id,
            self.sync_state,
            self.bids,
            self.asks,
            self.best_bid,
            self.best_ask,
            self.spread,
        )


def _closed_projection(
    *,
    projection_time: datetime,
    event_time: datetime | None,
    last_update_id: int | None,
    sync_state: str,
    depth_levels: int,
    age_ms: int | None,
) -> BookProjection:
    return BookProjection(
        projection_time=projection_time,
        event_time=event_time,
        last_update_id=last_update_id,
        sync_state=sync_state,
        bids=(),
        asks=(),
        depth_levels=depth_levels,
        best_bid=None,
        best_ask=None,
        spread=None,
        age_ms=age_ms,
    )


def build_book_projection(
    book_state: Any,
    *,
    depth_levels: int = 50,
    stale_after_ms: int = 2000,
    now_monotonic: float | None = None,
    projection_time: datetime | None = None,
) -> BookProjection:
    """Read the current state without mutating or queueing analysis updates."""
    if depth_levels < 1:
        raise ValueError("depth_levels must be >= 1")
    if stale_after_ms < 1:
        raise ValueError("stale_after_ms must be >= 1")
    projected_at = projection_time or _utc_now()
    if projected_at.tzinfo is None:
        raise ValueError("projection_time must be timezone-aware")
    projected_at = projected_at.astimezone(timezone.utc)

    if book_state is None:
        return _closed_projection(
            projection_time=projected_at,
            event_time=None,
            last_update_id=None,
            sync_state="NO_SNAPSHOT",
            depth_levels=depth_levels,
            age_ms=None,
        )

    snapshot = book_state.snapshot()
    event_time = getattr(book_state, "last_event_time", None)
    if isinstance(event_time, datetime) and event_time.tzinfo is not None:
        event_time = event_time.astimezone(timezone.utc)
    elif event_time is not None:
        event_time = None
    age_ms = book_state.age_ms(now_monotonic)

    if snapshot is None:
        state = "RESYNCING" if getattr(book_state, "gaps_detected", 0) else "NO_SNAPSHOT"
        return _closed_projection(
            projection_time=projected_at,
            event_time=event_time,
            last_update_id=None,
            sync_state=state,
            depth_levels=depth_levels,
            age_ms=age_ms,
        )

    if not getattr(book_state, "is_synchronized", False):
        state = "RESYNCING" if getattr(book_state, "gaps_detected", 0) else "NO_SNAPSHOT"
        return _closed_projection(
            projection_time=projected_at,
            event_time=event_time,
            last_update_id=snapshot.last_update_id,
            sync_state=state,
            depth_levels=depth_levels,
            age_ms=age_ms,
        )

    if age_ms is None or age_ms > stale_after_ms:
        return _closed_projection(
            projection_time=projected_at,
            event_time=event_time,
            last_update_id=snapshot.last_update_id,
            sync_state="STALE",
            depth_levels=depth_levels,
            age_ms=age_ms,
        )

    if event_time is None:
        return _closed_projection(
            projection_time=projected_at,
            event_time=None,
            last_update_id=snapshot.last_update_id,
            sync_state="INVALID",
            depth_levels=depth_levels,
            age_ms=age_ms,
        )

    if any(
        not price.is_finite()
        or not quantity.is_finite()
        or price <= 0
        or quantity <= 0
        for price, quantity in chain(snapshot.bids.items(), snapshot.asks.items())
    ):
        return _closed_projection(
            projection_time=projected_at,
            event_time=event_time,
            last_update_id=snapshot.last_update_id,
            sync_state="INVALID",
            depth_levels=depth_levels,
            age_ms=age_ms,
        )

    bounded_bids = getattr(snapshot, "best_bids", None)
    bounded_asks = getattr(snapshot, "best_asks", None)
    if callable(bounded_bids):
        raw_bids = tuple(bounded_bids(depth_levels))
    else:
        cached_bids = getattr(snapshot, "ordered_bids", None)
        raw_bids = (
            tuple(cached_bids[:depth_levels])
            if cached_bids is not None
            else tuple(sorted(
                snapshot.bids.items(),
                key=lambda level: level[0],
                reverse=True,
            )[:depth_levels])
        )
    if callable(bounded_asks):
        raw_asks = tuple(bounded_asks(depth_levels))
    else:
        cached_asks = getattr(snapshot, "ordered_asks", None)
        raw_asks = (
            tuple(cached_asks[:depth_levels])
            if cached_asks is not None
            else tuple(sorted(
                snapshot.asks.items(),
                key=lambda level: level[0],
            )[:depth_levels])
        )
    if not raw_bids or not raw_asks:
        return _closed_projection(
            projection_time=projected_at,
            event_time=event_time,
            last_update_id=snapshot.last_update_id,
            sync_state="EMPTY",
            depth_levels=depth_levels,
            age_ms=age_ms,
        )

    bids = raw_bids
    asks = raw_asks
    best_bid = bids[0][0]
    best_ask = asks[0][0]
    if best_bid == best_ask:
        state = "LOCKED"
    elif best_bid > best_ask:
        state = "CROSSED"
    else:
        state = SYNCED
    if state != SYNCED:
        return _closed_projection(
            projection_time=projected_at,
            event_time=event_time,
            last_update_id=snapshot.last_update_id,
            sync_state=state,
            depth_levels=depth_levels,
            age_ms=age_ms,
        )

    return BookProjection(
        projection_time=projected_at,
        event_time=event_time,
        last_update_id=snapshot.last_update_id,
        sync_state=SYNCED,
        bids=bids[:depth_levels],
        asks=asks[:depth_levels],
        depth_levels=depth_levels,
        best_bid=best_bid,
        best_ask=best_ask,
        spread=best_ask - best_bid,
        age_ms=age_ms,
    )


class LatestBookProjectionPump:
    """Sample the book at a bounded cadence and send only changed projections."""

    def __init__(
        self,
        get_book_state: Callable[[], Any],
        send: Callable[[BookProjection], Awaitable[None]],
        *,
        depth_levels: int = 50,
        interval_sec: float = 0.1,
        stale_after_ms: int = 2000,
        monotonic: Callable[[], float] = time.monotonic,
        utcnow: Callable[[], datetime] = _utc_now,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if interval_sec <= 0:
            raise ValueError("interval_sec must be > 0")
        self._get_book_state = get_book_state
        self._send = send
        self.depth_levels = depth_levels
        self.interval_sec = float(interval_sec)
        self.stale_after_ms = stale_after_ms
        self._monotonic = monotonic
        self._utcnow = utcnow
        self._sleep = sleep
        self._last_fingerprint: tuple | None = None
        self.latest_projection: BookProjection | None = None
        self.samples = 0
        self.sent = 0
        self.synced_sent = 0
        self.fail_closed_sent = 0
        self.unchanged_suppressed = 0
        self.send_failures = 0

    @property
    def current_state(self) -> str:
        return (
            self.latest_projection.sync_state
            if self.latest_projection is not None
            else "NO_SNAPSHOT"
        )

    async def project_once(self) -> bool:
        projection = build_book_projection(
            self._get_book_state(),
            depth_levels=self.depth_levels,
            stale_after_ms=self.stale_after_ms,
            now_monotonic=self._monotonic(),
            projection_time=self._utcnow(),
        )
        self.samples += 1
        if projection.fingerprint == self._last_fingerprint:
            self.unchanged_suppressed += 1
            return False
        try:
            await self._send(projection)
        except asyncio.CancelledError:
            raise
        except Exception:  # keep LIVE market analysis isolated from UI delivery
            self.send_failures += 1
            logger.exception("BOOK_UPDATE projection send failed")
            return False
        self._last_fingerprint = projection.fingerprint
        self.latest_projection = projection
        self.sent += 1
        if projection.sync_state == SYNCED:
            self.synced_sent += 1
        else:
            self.fail_closed_sent += 1
        return True

    async def run(self) -> None:
        while True:
            await self.project_once()
            await self._sleep(self.interval_sec)
