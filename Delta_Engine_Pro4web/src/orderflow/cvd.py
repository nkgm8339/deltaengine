"""Cumulative Volume Delta (CVD) calculator.

Spec: docs/30_Modules/CVD_v3.2.md. Outputs conform to
docs/40_Reference/JSONSchema_v3.1.md (CVD Update Event §5, Candle Event §6) and
docs/40_Reference/MarketDataSchema_v3.1.md (Tick Record, Candle Record).
Timeframe values: docs/40_Reference/EnumDefinitions_v3.1.md §5.
Error codes: docs/40_Reference/ErrorCodes_v3.1.md.

Design (implementation instruction §5 determinism, CVD §7 zero drift):
    - Decimal arithmetic only — no float in the calculation path.
    - No wall-clock or randomness in the calculation path; identical input +
      identical config → identical output (deterministic replay).
    - Core numeric operations are pure functions; CvdCalculator is a
      deterministic fold over the input sequence holding only derived state.

Guards (CVD §6, verified by TestSpecification TV-CVD-02/03/04):
    - invalid side       → reject (E3001), no state change
    - duplicate trade_id → discard (E3002), CVD unchanged
    - out-of-order event → reject (E3004), CVD unchanged
    Every rejection is counted and logged (no silent data loss, §4).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

logger = logging.getLogger("orderflow.cvd")

# --- Error codes (ErrorCodes_v3.1 §4) -----------------------------------------
ERROR_INVALID_TRADE = "E3001"     # Invalid trade data (e.g. invalid side)
ERROR_DUPLICATE_TRADE = "E3002"   # Duplicate trade_id detected
ERROR_OUT_OF_ORDER = "E3004"      # Out-of-order event rejected

VALID_SIDES: frozenset[str] = frozenset({"BUY", "SELL"})  # EnumDefinitions TradeSide

# Timeframe (EnumDefinitions_v3.1 §5) -> seconds. Used for UTC bar alignment.
_TIMEFRAME_SECONDS: dict[str, int] = {
    "1s": 1,
    "1m": 60,
    "5m": 300,
    "10m": 600,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}


def _to_decimal(value: object) -> Decimal:
    """Coerce to Decimal without going through binary float (exact)."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


# --- Value types --------------------------------------------------------------
@dataclass(frozen=True)
class Trade:
    """A normalized trade event (CVD_v3.2 §3 inputs + symbol for output)."""

    trade_id: int
    event_time: datetime
    symbol: str
    price: Decimal
    quantity: Decimal
    side: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "price", _to_decimal(self.price))
        object.__setattr__(self, "quantity", _to_decimal(self.quantity))


@dataclass(frozen=True)
class CvdUpdate:
    """JSONSchema CVD Update Event (§5)."""

    event_time: datetime
    symbol: str
    tick_delta: Decimal
    tick_cvd: Decimal


@dataclass(frozen=True)
class Candle:
    """JSONSchema Candle Event (§6) / MarketDataSchema Candle Record."""

    bar_time: datetime
    symbol: str
    timeframe: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    delta: Decimal
    cvd: Decimal


@dataclass(frozen=True)
class Rejection:
    """A rejected/discarded trade (counted and logged, never silently lost)."""

    trade_id: int
    code: str
    reason: str


@dataclass(frozen=True)
class CvdResult:
    """Outcome of processing one trade.

    accepted True  -> `update` is set; `closed_candle` set if this trade rolled
                      over into a new bar (closing the previous one).
    accepted False -> `rejection` is set.
    """

    accepted: bool
    update: Optional[CvdUpdate] = None
    closed_candle: Optional[Candle] = None
    rejection: Optional[Rejection] = None


# --- Pure numeric helpers -----------------------------------------------------
def trade_delta(side: str, quantity: Decimal) -> Decimal:
    """Per-trade delta: +quantity for BUY, -quantity for SELL (CVD §5)."""
    if side == "BUY":
        return quantity
    if side == "SELL":
        return -quantity
    raise ValueError(f"invalid side: {side!r}")


def bar_start(event_time: datetime, timeframe: str) -> datetime:
    """UTC-aligned start of the bar containing `event_time` (CVD §5).

    e.g. 1m bars start at hh:mm:00 UTC; 1d bars at 00:00:00 UTC.
    """
    if timeframe not in _TIMEFRAME_SECONDS:
        raise ValueError(f"unknown timeframe: {timeframe!r}")
    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=timezone.utc)
    event_time = event_time.astimezone(timezone.utc)
    seconds = _TIMEFRAME_SECONDS[timeframe]
    epoch = int(event_time.timestamp())
    floored = epoch - (epoch % seconds)
    return datetime.fromtimestamp(floored, tz=timezone.utc)


# --- Internal mutable bar accumulator -----------------------------------------
class _BarAccumulator:
    __slots__ = ("bar_time", "open", "high", "low", "close", "volume", "delta", "cvd")

    def __init__(self, bar_time: datetime, price: Decimal) -> None:
        self.bar_time = bar_time
        self.open = price
        self.high = price
        self.low = price
        self.close = price
        self.volume = Decimal(0)
        self.delta = Decimal(0)      # bar delta — resets each bar
        self.cvd = Decimal(0)        # cumulative cvd as of the last trade in bar

    def add(self, price: Decimal, quantity: Decimal, delta: Decimal, cvd: Decimal) -> None:
        if price > self.high:
            self.high = price
        if price < self.low:
            self.low = price
        self.close = price
        self.volume += quantity
        self.delta += delta
        self.cvd = cvd

    def to_candle(self, symbol: str, timeframe: str) -> Candle:
        return Candle(
            bar_time=self.bar_time,
            symbol=symbol,
            timeframe=timeframe,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            delta=self.delta,
            cvd=self.cvd,
        )


# --- Deterministic calculator -------------------------------------------------
class CvdCalculator:
    """Folds a stream of normalized trades into tick CVD updates and bar candles.

    Single-instrument: constructed with the symbol it serves. Deterministic and
    side-effect free apart from logging rejections.
    """

    def __init__(self, symbol: str, timeframe: str = "1m") -> None:
        if timeframe not in _TIMEFRAME_SECONDS:
            raise ValueError(f"unknown timeframe: {timeframe!r}")
        self.symbol = symbol
        self.timeframe = timeframe
        self._cvd = Decimal(0)
        self._last_event_time: Optional[datetime] = None
        self._seen_ids: set[int] = set()
        self._bar: Optional[_BarAccumulator] = None
        # Counters (no silent loss — every non-processed trade is counted).
        self.processed = 0
        self.duplicates = 0
        self.rejected_invalid = 0
        self.rejected_out_of_order = 0

    @property
    def cvd(self) -> Decimal:
        return self._cvd

    def _reject(self, trade: Trade, code: str, reason: str) -> CvdResult:
        logger.warning("%s CVD trade rejected trade_id=%s: %s", code, trade.trade_id, reason)
        return CvdResult(accepted=False, rejection=Rejection(trade.trade_id, code, reason))

    def process(self, trade: Trade) -> CvdResult:
        # 1. Invalid side (E3001) — reject, no partial update (TV-CVD-03).
        if trade.side not in VALID_SIDES:
            self.rejected_invalid += 1
            return self._reject(trade, ERROR_INVALID_TRADE, f"invalid side {trade.side!r}")

        # 2. Duplicate trade_id (E3002) — discard, CVD unchanged (TV-CVD-02).
        if trade.trade_id in self._seen_ids:
            self.duplicates += 1
            return self._reject(trade, ERROR_DUPLICATE_TRADE, "duplicate trade_id")

        # 3. Out-of-order event (E3004) — reject, CVD unchanged (TV-CVD-04).
        if self._last_event_time is not None and trade.event_time < self._last_event_time:
            self.rejected_out_of_order += 1
            return self._reject(trade, ERROR_OUT_OF_ORDER, "event_time earlier than last processed")

        # --- accept ---
        delta = trade_delta(trade.side, trade.quantity)
        self._cvd += delta
        self._seen_ids.add(trade.trade_id)
        self._last_event_time = trade.event_time
        self.processed += 1

        closed = self._update_bar(trade, delta)

        update = CvdUpdate(
            event_time=trade.event_time,
            symbol=self.symbol,
            tick_delta=delta,
            tick_cvd=self._cvd,
        )
        return CvdResult(accepted=True, update=update, closed_candle=closed)

    def _update_bar(self, trade: Trade, delta: Decimal) -> Optional[Candle]:
        start = bar_start(trade.event_time, self.timeframe)
        closed: Optional[Candle] = None
        if self._bar is None:
            self._bar = _BarAccumulator(start, trade.price)
        elif start > self._bar.bar_time:
            closed = self._bar.to_candle(self.symbol, self.timeframe)
            self._bar = _BarAccumulator(start, trade.price)
        self._bar.add(trade.price, trade.quantity, delta, self._cvd)
        return closed

    def current_bar_snapshot(self) -> Optional[Candle]:
        """進行中バーの非破壊スナップショット (BAR_UPDATE 配信用)。

        バーは閉じない・状態は一切変更しない。バー未開始 (取引ゼロ) なら None。
        返る Candle の delta / cvd は「現時点まで」の値。
        """
        if self._bar is None:
            return None
        return self._bar.to_candle(self.symbol, self.timeframe)

    def finalize(self) -> Optional[Candle]:
        """Emit the final open bar (end of stream). Idempotent afterwards."""
        if self._bar is None:
            return None
        candle = self._bar.to_candle(self.symbol, self.timeframe)
        self._bar = None
        return candle


@dataclass(frozen=True)
class CvdRun:
    """Result of a full deterministic run over a trade sequence."""

    updates: list[CvdUpdate]
    candles: list[Candle]
    rejections: list[Rejection]
    final_cvd: Decimal
    processed: int
    duplicates: int
    rejected_invalid: int
    rejected_out_of_order: int


def run(trades: list[Trade], symbol: str, timeframe: str = "1m") -> CvdRun:
    """Pure fold: process a full trade sequence and return all outputs.

    Deterministic — same (trades, symbol, timeframe) always yields the same
    CvdRun. Used for unit tests and deterministic replay (M6).
    """
    calc = CvdCalculator(symbol=symbol, timeframe=timeframe)
    updates: list[CvdUpdate] = []
    candles: list[Candle] = []
    rejections: list[Rejection] = []
    for trade in trades:
        result = calc.process(trade)
        if result.closed_candle is not None:
            candles.append(result.closed_candle)
        if result.accepted and result.update is not None:
            updates.append(result.update)
        elif result.rejection is not None:
            rejections.append(result.rejection)
    final = calc.finalize()
    if final is not None:
        candles.append(final)
    return CvdRun(
        updates=updates,
        candles=candles,
        rejections=rejections,
        final_cvd=calc.cvd,
        processed=calc.processed,
        duplicates=calc.duplicates,
        rejected_invalid=calc.rejected_invalid,
        rejected_out_of_order=calc.rejected_out_of_order,
    )
