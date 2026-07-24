"""Native 5m/10m flow-vs-price observation.

This detector closes only on native execution-bar boundaries. It is separate
from the completed rolling-second Flow Price Response detector used by 1m.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from .cvd import Trade, bar_start
from .flow_price_response import FlowResponseState

_ZERO = Decimal("0")
_BPS = Decimal("10000")


@dataclass(frozen=True)
class NativeFlowSnapshot:
    event_time: datetime
    symbol: str
    timeframe: str
    state: FlowResponseState
    pressure_side: str
    buy_volume: Decimal
    sell_volume: Decimal
    delta: Decimal
    pressure_ratio: Decimal
    first_price: Decimal
    last_price: Decimal
    last_time: datetime
    price_change_bps: Decimal
    trade_count: int


@dataclass
class _Bar:
    start: datetime
    first_price: Decimal
    last_price: Decimal
    last_time: datetime
    buy: Decimal = _ZERO
    sell: Decimal = _ZERO
    count: int = 0

    def add(self, trade: Trade) -> None:
        self.last_price = trade.price
        self.last_time = trade.event_time
        self.count += 1
        if trade.side == "BUY":
            self.buy += trade.quantity
        elif trade.side == "SELL":
            self.sell += trade.quantity

    def snapshot(self, symbol: str, timeframe: str) -> NativeFlowSnapshot:
        total = self.buy + self.sell
        delta = self.buy - self.sell
        ratio = abs(delta) / total if total else _ZERO
        change = (self.last_price - self.first_price) / self.first_price * _BPS
        side = "BUY" if delta > _ZERO else "SELL" if delta < _ZERO else ""
        if self.count == 0 or not total:
            state = FlowResponseState.UNCLEAR
        elif side == "BUY":
            state = FlowResponseState.BUY_EFFECTIVE if change > _ZERO else FlowResponseState.BUY_TRAPPED if change < _ZERO else FlowResponseState.BUY_STALLED
        elif side == "SELL":
            state = FlowResponseState.SELL_EFFECTIVE if change < _ZERO else FlowResponseState.SELL_TRAPPED if change > _ZERO else FlowResponseState.SELL_STALLED
        else:
            state = FlowResponseState.UNCLEAR
        return NativeFlowSnapshot(self.last_time, symbol, timeframe, state, side, self.buy, self.sell, delta, ratio, self.first_price, self.last_price, self.last_time, change, self.count)



class NativeFlowDetector:
    """Emit one observational Flow snapshot per closed native bar."""

    def __init__(self, symbol: str, timeframe: str, *, min_trades: int = 1) -> None:
        if timeframe not in ("5m", "10m"):
            raise ValueError("native flow timeframe must be 5m or 10m")
        if min_trades < 1:
            raise ValueError("min_trades must be positive")
        self.symbol = symbol
        self.timeframe = timeframe
        self.min_trades = min_trades
        self._bar: Optional[_Bar] = None

    def process(self, trade: Trade) -> tuple[NativeFlowSnapshot, ...]:
        if trade.symbol != self.symbol or trade.side not in ("BUY", "SELL"):
            return ()
        start = bar_start(trade.event_time, self.timeframe)
        emitted: list[NativeFlowSnapshot] = []
        if self._bar is not None and start > self._bar.start:
            if self._bar.count >= self.min_trades:
                emitted.append(self._bar.snapshot(self.symbol, self.timeframe))
            self._bar = None
        if self._bar is None:
            self._bar = _Bar(start, trade.price, trade.price, trade.event_time)
        self._bar.add(trade)
        return tuple(emitted)

    def finalize(self) -> tuple[NativeFlowSnapshot, ...]:
        if self._bar is None:
            return ()
        bar = self._bar
        self._bar = None
        return (bar.snapshot(self.symbol, self.timeframe),) if bar.count >= self.min_trades else ()




@dataclass(frozen=True)
class NativeFlowOutcome:
    event_time: datetime
    symbol: str
    timeframe: str
    state: FlowResponseState
    horizon_sec: int
    observed_price: Decimal
    outcome_time: datetime
    outcome_price: Decimal
    forward_return_bps: Decimal
    max_up_bps: Decimal
    max_down_bps: Decimal


@dataclass
class _PendingNativeOutcome:
    snapshot: NativeFlowSnapshot
    remaining: set[int]
    high: Decimal
    low: Decimal


class NativeFlowOutcomeTracker:
    """Track native events and raw forward outcomes independently by timeframe."""

    def __init__(self, horizons_sec: tuple[int, ...] = (300, 600, 1800)) -> None:
        horizons = tuple(sorted(set(horizons_sec)))
        if not horizons or any(not isinstance(v, int) or isinstance(v, bool) or v < 1 for v in horizons):
            raise ValueError("horizons_sec must contain positive integers")
        self.horizons_sec = horizons
        self._last_state: dict[tuple[str, str], FlowResponseState] = {}
        self._pending: list[_PendingNativeOutcome] = []

    def register(self, snapshots: tuple[NativeFlowSnapshot, ...]) -> tuple[NativeFlowSnapshot, ...]:
        events: list[NativeFlowSnapshot] = []
        for snapshot in snapshots:
            key = (snapshot.symbol, snapshot.timeframe)
            previous = self._last_state.get(key)
            self._last_state[key] = snapshot.state
            if snapshot.state is FlowResponseState.UNCLEAR or snapshot.state is previous:
                continue
            self._pending.append(_PendingNativeOutcome(snapshot, set(self.horizons_sec), snapshot.last_price, snapshot.last_price))
            events.append(snapshot)
        return tuple(events)

    def observe_trade(self, trade: Trade) -> tuple[NativeFlowOutcome, ...]:
        if not trade.price.is_finite() or trade.price <= _ZERO or not trade.quantity.is_finite() or trade.quantity <= _ZERO:
            return ()
        outcomes: list[NativeFlowOutcome] = []
        keep: list[_PendingNativeOutcome] = []
        for pending in self._pending:
            snap = pending.snapshot
            if trade.event_time < snap.event_time:
                keep.append(pending)
                continue
            pending.high = max(pending.high, trade.price)
            pending.low = min(pending.low, trade.price)
            elapsed = (trade.event_time - snap.event_time).total_seconds()
            for horizon in sorted(h for h in pending.remaining if elapsed >= h):
                base = snap.last_price
                outcomes.append(NativeFlowOutcome(
                    event_time=snap.event_time, symbol=snap.symbol, timeframe=snap.timeframe,
                    state=snap.state, horizon_sec=horizon, observed_price=base,
                    outcome_time=trade.event_time, outcome_price=trade.price,
                    forward_return_bps=(trade.price - base) / base * _BPS,
                    max_up_bps=(pending.high - base) / base * _BPS,
                    max_down_bps=(pending.low - base) / base * _BPS,
                ))
                pending.remaining.remove(horizon)
            if pending.remaining:
                keep.append(pending)
        self._pending = keep
        return tuple(outcomes)

    @property
    def pending_count(self) -> int:
        return len(self._pending)
