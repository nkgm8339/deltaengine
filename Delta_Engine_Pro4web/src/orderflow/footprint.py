"""Footprint calculator — price-level BUY/SELL volume aggregation (MOD-005).

Spec: ArchitectureRepository/30_Modules/Footprint_v3.0.md.
Error codes: ArchitectureRepository/40_Reference/ErrorCodes_v3.1.md.
Test vectors: ArchitectureRepository/50_Test/TestSpecification_v3.2.md §4.2
(TV-FP-01 level aggregation, TV-FP-02 invalid trade).

Design (mirrors CvdCalculator, instruction §3):
    - Decimal arithmetic only — no float in the calculation path.
    - _to_decimal reused from cvd.py pattern.
    - Deterministic: identical input + identical config → identical output.
    - No estimation (Footprint_v3.0 §5).
    - No silent data loss: every rejection is counted and logged (§6).

Bar boundary logic (instruction §4 decision 1):
    - tick footprint  = current-bar running price-level snapshot.
    - bar footprint   = confirmed on bar boundary; levels reset for the new bar.
    - Bar alignment identical to CvdCalculator (UTC, bar_start from cvd.py).

Price levels (instruction §4 decision 2):
    - Price key = normalized trade price as-is (no tick_size rounding).

Error handling (instruction §4 decision 3):
    - E3001 invalid side / non-positive price — reject, state unchanged.
    - E3002 duplicate trade_id           — reject, state unchanged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from .cvd import _TIMEFRAME_SECONDS, _to_decimal, bar_start

logger = logging.getLogger("orderflow.footprint")

# --- Error codes (ErrorCodes_v3.1 §4) -----------------------------------------
ERROR_INVALID_TRADE = "E3001"
ERROR_DUPLICATE_TRADE = "E3002"

VALID_SIDES: frozenset[str] = frozenset({"BUY", "SELL"})

_ZERO = Decimal(0)


# --- Value types --------------------------------------------------------------
@dataclass(frozen=True)
class FootprintTrade:
    """Input trade for the Footprint calculator (instruction §3)."""

    trade_id: int
    event_time: datetime
    symbol: str
    price: Decimal
    quantity: Decimal
    side: str  # "BUY" | "SELL"

    def __post_init__(self) -> None:
        object.__setattr__(self, "price", _to_decimal(self.price))
        object.__setattr__(self, "quantity", _to_decimal(self.quantity))


@dataclass(frozen=True)
class PriceLevel:
    """Aggregated BUY and SELL volume at a single price level."""

    price: Decimal
    buy_volume: Decimal
    sell_volume: Decimal


@dataclass(frozen=True)
class FootprintBar:
    """Confirmed bar-footprint: price-level table for one closed bar."""

    bar_time: datetime
    symbol: str
    timeframe: str
    levels: tuple[PriceLevel, ...]  # sorted ascending by price


@dataclass(frozen=True)
class FootprintRejection:
    trade_id: int
    code: str
    reason: str


# --- Internal mutable bar accumulator -----------------------------------------
class _BarAccumulator:
    """Mutable price-level map for the in-progress bar."""

    __slots__ = ("bar_time", "_buys", "_sells")

    def __init__(self, bar_time: datetime) -> None:
        self.bar_time = bar_time
        self._buys: dict[Decimal, Decimal] = {}
        self._sells: dict[Decimal, Decimal] = {}

    def add(self, price: Decimal, quantity: Decimal, side: str) -> None:
        if side == "BUY":
            self._buys[price] = self._buys.get(price, _ZERO) + quantity
        else:
            self._sells[price] = self._sells.get(price, _ZERO) + quantity

    def to_levels(self) -> tuple[PriceLevel, ...]:
        prices = sorted(self._buys.keys() | self._sells.keys())
        return tuple(
            PriceLevel(
                price=p,
                buy_volume=self._buys.get(p, _ZERO),
                sell_volume=self._sells.get(p, _ZERO),
            )
            for p in prices
        )

    def to_bar(self, symbol: str, timeframe: str) -> FootprintBar:
        return FootprintBar(
            bar_time=self.bar_time,
            symbol=symbol,
            timeframe=timeframe,
            levels=self.to_levels(),
        )


# --- Deterministic calculator -------------------------------------------------
class FootprintCalculator:
    """Folds a stream of trades into tick snapshots and confirmed bar footprints.

    Single-instrument; constructed with the symbol and timeframe it serves.
    Deterministic and side-effect-free apart from logging rejections.
    """

    def __init__(self, symbol: str, timeframe: str = "1m") -> None:
        if timeframe not in _TIMEFRAME_SECONDS:
            raise ValueError(f"unknown timeframe: {timeframe!r}")
        self.symbol = symbol
        self.timeframe = timeframe
        self._bar: Optional[_BarAccumulator] = None
        self._seen_ids: set[int] = set()
        # counters (no silent loss)
        self.processed = 0
        self.rejected_invalid = 0
        self.duplicates = 0

    def _reject(self, trade: FootprintTrade, code: str, reason: str) -> None:
        logger.warning("%s footprint trade rejected trade_id=%s: %s", code, trade.trade_id, reason)

    def process_trade(self, trade: FootprintTrade) -> Optional[FootprintBar]:
        """Process one trade; return a confirmed FootprintBar on bar rollover, else None."""
        # 1. Invalid side (E3001)
        if trade.side not in VALID_SIDES:
            self.rejected_invalid += 1
            self._reject(trade, ERROR_INVALID_TRADE, f"invalid side {trade.side!r}")
            return None

        # 2. Non-positive price (E3001)
        if trade.price <= _ZERO:
            self.rejected_invalid += 1
            self._reject(trade, ERROR_INVALID_TRADE, f"non-positive price {trade.price}")
            return None

        # 3. Duplicate trade_id (E3002)
        if trade.trade_id in self._seen_ids:
            self.duplicates += 1
            self._reject(trade, ERROR_DUPLICATE_TRADE, "duplicate trade_id")
            return None

        # --- accept ---
        self._seen_ids.add(trade.trade_id)
        self.processed += 1

        start = bar_start(trade.event_time, self.timeframe)
        closed: Optional[FootprintBar] = None

        if self._bar is None:
            self._bar = _BarAccumulator(start)
        elif start > self._bar.bar_time:
            closed = self._bar.to_bar(self.symbol, self.timeframe)
            self._bar = _BarAccumulator(start)

        self._bar.add(trade.price, trade.quantity, trade.side)
        return closed

    def current_tick_snapshot(self) -> tuple[PriceLevel, ...]:
        """Price-level snapshot of the current in-progress bar (tick footprint)."""
        if self._bar is None:
            return ()
        return self._bar.to_levels()

    def finalize(self) -> Optional[FootprintBar]:
        """Confirm and return the final open bar (end of stream). Idempotent afterwards."""
        if self._bar is None:
            return None
        bar = self._bar.to_bar(self.symbol, self.timeframe)
        self._bar = None
        return bar
