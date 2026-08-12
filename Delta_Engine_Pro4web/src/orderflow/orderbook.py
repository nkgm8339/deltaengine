"""Order Book canonical types and state manager (B-1).

Spec: ArchitectureRepository/40_Reference/MarketDataSchema_v3.2.md
      §Order Book Update Record / §BookLevel / §Order Book State.
Errors: ArchitectureRepository/40_Reference/ErrorCodes_v3.1.md.

Design:
    - Decimal arithmetic only — no float.
    - OrderBookStateManager holds mutable internal state for performance;
      snapshot() returns an immutable copy.
    - Deterministic: identical update sequence → identical snapshot() content.
    - No silent data loss: every rejection / gap is counted and logged.

Gap handling (decision 1): E3004 (ERROR_OUT_OF_ORDER) is reused for both
"DIFF before SNAPSHOT" and sequence-gap cases, since both are ordering
failures. Log messages distinguish the two cases.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from functools import cached_property
from heapq import nlargest, nsmallest
from typing import Callable, Optional

logger = logging.getLogger("orderflow.orderbook")

ERROR_OUT_OF_ORDER = "E3004"   # reused per decision 1

_ZERO = Decimal(0)
_TOP_LEVEL_CACHE_SIZE = 50


# ---------------------------------------------------------------------------
# Value types (MarketDataSchema_v3.2)
# ---------------------------------------------------------------------------

def _to_decimal(v: object) -> Decimal:
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


@dataclass(frozen=True)
class BookLevel:
    price: Decimal
    quantity: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "price", _to_decimal(self.price))
        object.__setattr__(self, "quantity", _to_decimal(self.quantity))


@dataclass(frozen=True)
class OrderBookUpdate:
    """Canonical Order Book Update Record (MarketDataSchema_v3.2)."""

    event_time: datetime
    symbol: str
    update_type: str                    # "SNAPSHOT" | "DIFF"
    first_update_id: Optional[int]      # DIFF only; None for SNAPSHOT
    final_update_id: int
    bids: tuple[BookLevel, ...]         # input order preserved
    asks: tuple[BookLevel, ...]
    previous_final_update_id: Optional[int] = None  # pu field (Binance Futures)


@dataclass(frozen=True)
class OrderBookSnapshot:
    """Immutable point-in-time view of Order Book State."""

    symbol: str
    last_update_id: int
    bids: dict[Decimal, Decimal]        # price → quantity (quantity > 0 only)
    asks: dict[Decimal, Decimal]
    event_time: Optional[datetime] = None

    def bid_quantity_at(self, price: Decimal) -> Decimal:
        return self.bids.get(_to_decimal(price), _ZERO)

    def ask_quantity_at(self, price: Decimal) -> Decimal:
        return self.asks.get(_to_decimal(price), _ZERO)

    @cached_property
    def ordered_bids(self) -> tuple[tuple[Decimal, Decimal], ...]:
        """All bid levels in best-to-worst order, computed once per snapshot."""
        return tuple(sorted(self.bids.items(), key=lambda row: row[0], reverse=True))

    @cached_property
    def ordered_asks(self) -> tuple[tuple[Decimal, Decimal], ...]:
        """All ask levels in best-to-worst order, computed once per snapshot."""
        return tuple(sorted(self.asks.items(), key=lambda row: row[0]))

    @cached_property
    def top_bids(self) -> tuple[tuple[Decimal, Decimal], ...]:
        """Bounded best-bid cache for live consumers using at most 50 levels."""
        ordered = self.__dict__.get("ordered_bids")
        if ordered is not None:
            return ordered[:_TOP_LEVEL_CACHE_SIZE]
        return tuple(nlargest(
            _TOP_LEVEL_CACHE_SIZE,
            self.bids.items(),
            key=lambda row: row[0],
        ))

    @cached_property
    def top_asks(self) -> tuple[tuple[Decimal, Decimal], ...]:
        """Bounded best-ask cache for live consumers using at most 50 levels."""
        ordered = self.__dict__.get("ordered_asks")
        if ordered is not None:
            return ordered[:_TOP_LEVEL_CACHE_SIZE]
        return tuple(nsmallest(
            _TOP_LEVEL_CACHE_SIZE,
            self.asks.items(),
            key=lambda row: row[0],
        ))

    def best_bids(self, limit: int) -> tuple[tuple[Decimal, Decimal], ...]:
        """Return exact best-first bids without sorting the full book for small views."""
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if limit <= _TOP_LEVEL_CACHE_SIZE:
            return self.top_bids[:limit]
        return self.ordered_bids[:limit]

    def best_asks(self, limit: int) -> tuple[tuple[Decimal, Decimal], ...]:
        """Return exact best-first asks without sorting the full book for small views."""
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if limit <= _TOP_LEVEL_CACHE_SIZE:
            return self.top_asks[:limit]
        return self.ordered_asks[:limit]


@dataclass(frozen=True)
class ApplyResult:
    applied: bool
    reinitialized: bool
    gap_detected: bool


# ---------------------------------------------------------------------------
# State manager
# ---------------------------------------------------------------------------

class OrderBookStateManager:
    """Maintains live Order Book state by applying OrderBookUpdate records.

    SNAPSHOT establishes or re-establishes state. DIFF updates are applied
    as set-to-value (quantity > 0 overwrites, quantity = 0 removes level).
    Gap detection rejects out-of-sequence DIFFs and resets state.
    """

    def __init__(
        self,
        symbol: str,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.symbol = symbol
        self._clock = clock
        self._bids: dict[Decimal, Decimal] = {}
        self._asks: dict[Decimal, Decimal] = {}
        self._last_update_id: Optional[int] = None
        self._last_event_time: Optional[datetime] = None
        self._last_applied_monotonic: Optional[float] = None
        self._initialized: bool = False
        self._sync_id: Optional[int] = None   # set during initial Binance sync phase
        # ``OrderBookSnapshot`` is immutable by contract. Reuse the same copied
        # view until the next accepted state transition instead of rebuilding
        # both full side dictionaries for every consumer and every trade.
        self._snapshot_cache: Optional[OrderBookSnapshot] = None
        # counters (no silent loss)
        self.snapshots_applied: int = 0
        self.diffs_applied: int = 0
        self.diffs_rejected_before_snapshot: int = 0
        self.diffs_stale: int = 0
        self.gaps_detected: int = 0

    # -- public interface -------------------------------------------------------

    def apply(self, update: OrderBookUpdate) -> ApplyResult:
        """Apply one OrderBookUpdate; return ApplyResult describing what happened."""
        if update.symbol != self.symbol:
            raise ValueError(
                f"symbol mismatch: manager is {self.symbol!r}, update is {update.symbol!r}"
            )

        if update.update_type == "SNAPSHOT":
            return self._apply_snapshot(update)
        if update.update_type == "DIFF":
            return self._apply_diff(update)
        raise ValueError(f"unknown update_type: {update.update_type!r}")

    def apply_initial_sync(self, snapshot_update_id: int) -> None:
        """Enter initial sync mode after applying a REST snapshot.

        Enables Binance-spec buffer alignment: buffered diffs with
        final_update_id <= snapshot_update_id are counted as stale; the first
        diff where first_update_id <= snapshot_update_id+1 <= final_update_id
        exits sync mode and applies normally. Call immediately after
        apply(SNAPSHOT update).
        """
        self._sync_id = snapshot_update_id


    @property
    def is_initialized(self) -> bool:
        """True when Snapshot state exists, including initial alignment wait."""
        return self._initialized

    @property
    def is_synchronized(self) -> bool:
        """True only after initial/resync Snapshot alignment has completed."""
        return self._initialized and self._sync_id is None

    @property
    def last_event_time(self) -> Optional[datetime]:
        """Source time of the latest accepted state transition or detected gap."""
        return self._last_event_time

    def age_ms(self, now_monotonic: Optional[float] = None) -> Optional[int]:
        """Monotonic age of the latest applied Snapshot/DIFF."""
        if self._last_applied_monotonic is None:
            return None
        now = self._clock() if now_monotonic is None else now_monotonic
        return max(0, int((now - self._last_applied_monotonic) * 1000))

    def snapshot(self) -> Optional[OrderBookSnapshot]:
        """Return immutable snapshot of current state, or None if not initialized."""
        if not self._initialized:
            return None
        if self._snapshot_cache is None:
            self._snapshot_cache = OrderBookSnapshot(
                symbol=self.symbol,
                last_update_id=self._last_update_id,  # type: ignore[arg-type]
                bids=dict(self._bids),
                asks=dict(self._asks),
                event_time=self._last_event_time,
            )
        return self._snapshot_cache

    def bid_quantity_at(self, price: Decimal) -> Decimal:
        return self._bids.get(_to_decimal(price), _ZERO)

    def ask_quantity_at(self, price: Decimal) -> Decimal:
        return self._asks.get(_to_decimal(price), _ZERO)

    # -- private helpers --------------------------------------------------------

    def _apply_snapshot(self, update: OrderBookUpdate) -> ApplyResult:
        reinitialized = self._initialized
        self._bids = {}
        self._asks = {}
        for level in update.bids:
            if level.quantity > _ZERO:
                self._bids[level.price] = level.quantity
        for level in update.asks:
            if level.quantity > _ZERO:
                self._asks[level.price] = level.quantity
        self._last_update_id = update.final_update_id
        self._sync_id = None
        self._mark_applied(update)
        self._initialized = True
        self.snapshots_applied += 1
        return ApplyResult(applied=True, reinitialized=reinitialized, gap_detected=False)

    def _apply_diff(self, update: OrderBookUpdate) -> ApplyResult:
        # Reject if not yet initialized.
        if not self._initialized:
            self.diffs_rejected_before_snapshot += 1
            logger.warning(
                "%s order book diff before snapshot: symbol=%s final_id=%s",
                ERROR_OUT_OF_ORDER, self.symbol, update.final_update_id,
            )
            return ApplyResult(applied=False, reinitialized=False, gap_detected=False)

        # Stale: already applied.
        if update.final_update_id <= self._last_update_id:  # type: ignore[operator]
            self.diffs_stale += 1
            logger.warning(
                "%s order book stale diff: symbol=%s final_id=%s <= last_id=%s",
                ERROR_OUT_OF_ORDER, self.symbol,
                update.final_update_id, self._last_update_id,
            )
            return ApplyResult(applied=False, reinitialized=False, gap_detected=False)

        # Initial sync mode: accept first non-stale diff (lenient — Binance Futures
        # batches can start at first_update_id > snap_id+1 due to connection timing).
        if self._sync_id is not None:
            self._sync_id = None
            self._apply_levels(self._bids, update.bids)
            self._apply_levels(self._asks, update.asks)
            self._last_update_id = update.final_update_id
            self._mark_applied(update)
            self.diffs_applied += 1
            return ApplyResult(applied=True, reinitialized=False, gap_detected=False)

        # Gap: sequence discontinuity.
        # Prefer pu-based check (Binance Futures @depth: pu == prev_u guarantees
        # continuity; U may jump legitimately between batches).
        gap = False
        if update.previous_final_update_id is not None:
            gap = update.previous_final_update_id != self._last_update_id  # type: ignore[operator]
        elif update.first_update_id is not None:
            expected = self._last_update_id + 1  # type: ignore[operator]
            gap = update.first_update_id != expected
        if gap:
            prev_id = self._last_update_id
            self._bids = {}
            self._asks = {}
            self._last_update_id = None
            self._sync_id = None
            self._last_event_time = update.event_time
            self._last_applied_monotonic = None
            self._initialized = False
            self._snapshot_cache = None
            self.gaps_detected += 1
            logger.warning(
                "%s order book gap detected: symbol=%s last_id=%s pu=%s first_id=%s",
                ERROR_OUT_OF_ORDER, self.symbol,
                prev_id, update.previous_final_update_id, update.first_update_id,
            )
            return ApplyResult(applied=False, reinitialized=False, gap_detected=True)

        # Apply set-to-value semantics.
        self._apply_levels(self._bids, update.bids)
        self._apply_levels(self._asks, update.asks)
        self._last_update_id = update.final_update_id
        self._mark_applied(update)
        self.diffs_applied += 1
        return ApplyResult(applied=True, reinitialized=False, gap_detected=False)

    def _mark_applied(self, update: OrderBookUpdate) -> None:
        self._last_event_time = update.event_time
        self._last_applied_monotonic = self._clock()
        self._snapshot_cache = None

    @staticmethod
    def _apply_levels(
        side: dict[Decimal, Decimal], levels: tuple[BookLevel, ...]
    ) -> None:
        for level in levels:
            if level.quantity == _ZERO:
                side.pop(level.price, None)
            else:
                side[level.price] = level.quantity
