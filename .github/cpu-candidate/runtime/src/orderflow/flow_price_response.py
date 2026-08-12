"""Rolling order-flow pressure versus price-response measurement.

This module deliberately emits observational states, not trading signals.
It answers two questions for each rolling window:

1. Which aggressor side dominated executed volume?
2. Did price move with that pressure, stall, or move against it?

The detector aggregates trades into one-second buckets so 30-minute windows do
not require rescanning or duplicating the raw tick stream on every trade.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Optional


_ZERO = Decimal("0")
_BPS = Decimal("10000")


class FlowResponseState(str, Enum):
    """Observed relationship between aggressive flow and price response."""

    UNCLEAR = "UNCLEAR"
    BUY_EFFECTIVE = "BUY_EFFECTIVE"
    SELL_EFFECTIVE = "SELL_EFFECTIVE"
    BUY_STALLED = "BUY_STALLED"
    SELL_STALLED = "SELL_STALLED"
    BUY_TRAPPED = "BUY_TRAPPED"
    SELL_TRAPPED = "SELL_TRAPPED"


@dataclass(frozen=True)
class FlowResponseSnapshot:
    event_time: datetime
    symbol: str
    window_sec: int
    state: FlowResponseState
    pressure_side: str
    buy_volume: Decimal
    sell_volume: Decimal
    total_volume: Decimal
    delta: Decimal
    pressure_ratio: Decimal
    persistence: Decimal
    first_price: Decimal
    last_price: Decimal
    high_price: Decimal
    low_price: Decimal
    price_change: Decimal
    price_change_bps: Decimal
    relative_volume: Optional[Decimal]
    trade_count: int
    observed_span_sec: int


@dataclass
class _SecondBucket:
    second: int
    first_time: datetime
    last_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    buy_volume: Decimal = _ZERO
    sell_volume: Decimal = _ZERO
    trade_count: int = 0

    @classmethod
    def from_trade(cls, trade: Any, second: int) -> "_SecondBucket":
        price = Decimal(str(trade.price))
        bucket = cls(
            second=second,
            first_time=trade.event_time,
            last_time=trade.event_time,
            open=price,
            high=price,
            low=price,
            close=price,
        )
        bucket.add(trade)
        return bucket

    def add(self, trade: Any) -> None:
        price = Decimal(str(trade.price))
        quantity = Decimal(str(trade.quantity))
        self.last_time = trade.event_time
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.trade_count += 1
        if trade.side == "BUY":
            self.buy_volume += quantity
        elif trade.side == "SELL":
            self.sell_volume += quantity

    @property
    def delta(self) -> Decimal:
        return self.buy_volume - self.sell_volume


class FlowPriceResponseDetector:
    """Build rolling pressure/response snapshots from normalized trades.

    A snapshot is emitted at most once per event-time second. ``finalize`` emits
    the last partial second for replay/shutdown paths.
    """

    def __init__(
        self,
        *,
        windows_sec: Iterable[int] = (30, 60, 180, 300, 900, 1800),
        baseline_window_sec: int = 1800,
        pressure_threshold: Decimal = Decimal("0.20"),
        persistence_threshold: Decimal = Decimal("0.60"),
        stall_bps: Decimal = Decimal("1.0"),
        effective_bps: Decimal = Decimal("2.0"),
        opposite_bps: Decimal = Decimal("1.0"),
        min_trades: int = 20,
    ) -> None:
        windows = tuple(sorted(set(windows_sec)))
        if not windows or any(not isinstance(v, int) or isinstance(v, bool) or v < 1 for v in windows):
            raise ValueError("windows_sec must contain positive integers")
        if baseline_window_sec < max(windows):
            raise ValueError("baseline_window_sec must be >= the largest window")
        if min_trades < 1:
            raise ValueError("min_trades must be >= 1")

        self.windows_sec = windows
        self.baseline_window_sec = baseline_window_sec
        self.pressure_threshold = self._ratio(pressure_threshold, "pressure_threshold")
        self.persistence_threshold = self._ratio(persistence_threshold, "persistence_threshold")
        self.stall_bps = self._nonnegative(stall_bps, "stall_bps")
        self.effective_bps = self._nonnegative(effective_bps, "effective_bps")
        self.opposite_bps = self._nonnegative(opposite_bps, "opposite_bps")
        self.min_trades = min_trades

        self._buckets: deque[_SecondBucket] = deque()
        self._last_event_time: Optional[datetime] = None
        self._last_emitted_second: Optional[int] = None
        self._symbol: Optional[str] = None
        self.rejected_out_of_order = 0
        self.rejected_invalid_side = 0
        self.rejected_invalid_trade = 0

    @staticmethod
    def _ratio(value: Decimal, name: str) -> Decimal:
        parsed = Decimal(str(value))
        if parsed < _ZERO or parsed > Decimal("1"):
            raise ValueError(f"{name} must be between 0 and 1")
        return parsed

    @staticmethod
    def _nonnegative(value: Decimal, name: str) -> Decimal:
        parsed = Decimal(str(value))
        if parsed < _ZERO:
            raise ValueError(f"{name} must be >= 0")
        return parsed

    def process(self, trade: Any) -> tuple[FlowResponseSnapshot, ...]:
        """Consume one trade and return snapshots when the previous second closes."""
        if trade.side not in ("BUY", "SELL"):
            self.rejected_invalid_side += 1
            return ()
        try:
            price = Decimal(str(trade.price))
            quantity = Decimal(str(trade.quantity))
        except (ValueError, TypeError, ArithmeticError, AttributeError):
            self.rejected_invalid_trade += 1
            return ()
        if (
            not price.is_finite()
            or price <= _ZERO
            or not quantity.is_finite()
            or quantity <= _ZERO
        ):
            self.rejected_invalid_trade += 1
            return ()
        if self._last_event_time is not None and trade.event_time < self._last_event_time:
            self.rejected_out_of_order += 1
            return ()
        if self._symbol is None:
            self._symbol = trade.symbol
        elif trade.symbol != self._symbol:
            raise ValueError("flow response detector cannot mix symbols")

        second = int(trade.event_time.timestamp())
        emitted: tuple[FlowResponseSnapshot, ...] = ()
        if self._buckets and second != self._buckets[-1].second:
            emitted = self._snapshot(self._buckets[-1].last_time)
            self._buckets.append(_SecondBucket.from_trade(trade, second))
        elif not self._buckets:
            self._buckets.append(_SecondBucket.from_trade(trade, second))
        else:
            self._buckets[-1].add(trade)

        self._last_event_time = trade.event_time
        self._prune(second)
        return emitted

    def finalize(self) -> tuple[FlowResponseSnapshot, ...]:
        """Emit the current partial second once, if any trades were received."""
        if not self._buckets:
            return ()
        return self._snapshot(self._buckets[-1].last_time)

    def warm_start(self, trades: Iterable[Any]) -> int:
        """Prime rolling buckets without exposing historical snapshots.

        Persisted trades are calculation context only. Calling ``finalize``
        marks the last seeded second as emitted so the live path cannot
        rebroadcast or re-persist a historical snapshot after startup.
        """
        loaded = 0
        for trade in trades:
            self.process(trade)
            loaded += 1
        if loaded:
            self.finalize()
        return loaded

    def _prune(self, end_second: int) -> None:
        cutoff = end_second - self.baseline_window_sec + 1
        while self._buckets and self._buckets[0].second < cutoff:
            self._buckets.popleft()

    def _snapshot(self, event_time: datetime) -> tuple[FlowResponseSnapshot, ...]:
        end_second = int(event_time.timestamp())
        if self._last_emitted_second == end_second:
            return ()
        self._last_emitted_second = end_second
        self._prune(end_second)

        baseline = self._window_buckets(self.baseline_window_sec, end_second)
        baseline_ready = self._ready(baseline, self.baseline_window_sec, end_second)
        baseline_total = sum((b.buy_volume + b.sell_volume for b in baseline), _ZERO)
        baseline_rate = (
            baseline_total / Decimal(self.baseline_window_sec)
            if baseline_ready and baseline_total > _ZERO
            else None
        )

        snapshots = []
        for window_sec in self.windows_sec:
            buckets = self._window_buckets(window_sec, end_second)
            if not self._ready(buckets, window_sec, end_second):
                continue
            snapshots.append(self._build_snapshot(event_time, window_sec, buckets, baseline_rate))
        return tuple(snapshots)

    def _window_buckets(self, window_sec: int, end_second: int) -> list[_SecondBucket]:
        cutoff = end_second - window_sec + 1
        return [b for b in self._buckets if b.second >= cutoff]

    @staticmethod
    def _ready(buckets: list[_SecondBucket], window_sec: int, end_second: int) -> bool:
        return bool(buckets) and (end_second - buckets[0].second + 1) >= window_sec

    def _build_snapshot(
        self,
        event_time: datetime,
        window_sec: int,
        buckets: list[_SecondBucket],
        baseline_rate: Optional[Decimal],
    ) -> FlowResponseSnapshot:
        buy_volume = sum((b.buy_volume for b in buckets), _ZERO)
        sell_volume = sum((b.sell_volume for b in buckets), _ZERO)
        total_volume = buy_volume + sell_volume
        delta = buy_volume - sell_volume
        pressure_ratio = delta / total_volume if total_volume > _ZERO else _ZERO
        pressure_side = "BUY" if delta > _ZERO else "SELL" if delta < _ZERO else "NEUTRAL"

        directional_seconds = [b.delta for b in buckets if b.delta != _ZERO]
        if not directional_seconds or pressure_side == "NEUTRAL":
            persistence = _ZERO
        elif pressure_side == "BUY":
            persistence = Decimal(sum(1 for d in directional_seconds if d > _ZERO)) / Decimal(len(directional_seconds))
        else:
            persistence = Decimal(sum(1 for d in directional_seconds if d < _ZERO)) / Decimal(len(directional_seconds))

        first_price = buckets[0].open
        last_price = buckets[-1].close
        high_price = max(b.high for b in buckets)
        low_price = min(b.low for b in buckets)
        price_change = last_price - first_price
        price_change_bps = price_change / first_price * _BPS if first_price != _ZERO else _ZERO
        trade_count = sum(b.trade_count for b in buckets)
        current_rate = total_volume / Decimal(window_sec)
        relative_volume = current_rate / baseline_rate if baseline_rate is not None else None

        state = self._classify(
            pressure_side=pressure_side,
            pressure_ratio=pressure_ratio,
            persistence=persistence,
            price_change_bps=price_change_bps,
            trade_count=trade_count,
        )
        return FlowResponseSnapshot(
            event_time=event_time,
            symbol=self._symbol or "",
            window_sec=window_sec,
            state=state,
            pressure_side=pressure_side,
            buy_volume=buy_volume,
            sell_volume=sell_volume,
            total_volume=total_volume,
            delta=delta,
            pressure_ratio=pressure_ratio,
            persistence=persistence,
            first_price=first_price,
            last_price=last_price,
            high_price=high_price,
            low_price=low_price,
            price_change=price_change,
            price_change_bps=price_change_bps,
            relative_volume=relative_volume,
            trade_count=trade_count,
            observed_span_sec=window_sec,
        )

    def _classify(
        self,
        *,
        pressure_side: str,
        pressure_ratio: Decimal,
        persistence: Decimal,
        price_change_bps: Decimal,
        trade_count: int,
    ) -> FlowResponseState:
        if (
            trade_count < self.min_trades
            or pressure_side == "NEUTRAL"
            # Equality is left UNCLEAR: a threshold is the boundary, not proof
            # that one side materially dominated the window.
            or abs(pressure_ratio) <= self.pressure_threshold
            or persistence < self.persistence_threshold
        ):
            return FlowResponseState.UNCLEAR

        directed_move = price_change_bps if pressure_side == "BUY" else -price_change_bps
        if directed_move >= self.effective_bps:
            return FlowResponseState.BUY_EFFECTIVE if pressure_side == "BUY" else FlowResponseState.SELL_EFFECTIVE
        if directed_move <= -self.opposite_bps:
            return FlowResponseState.BUY_TRAPPED if pressure_side == "BUY" else FlowResponseState.SELL_TRAPPED
        if abs(price_change_bps) <= self.stall_bps:
            return FlowResponseState.BUY_STALLED if pressure_side == "BUY" else FlowResponseState.SELL_STALLED
        return FlowResponseState.UNCLEAR


@dataclass(frozen=True)
class FlowResponseOutcome:
    event_time: datetime
    symbol: str
    window_sec: int
    state: FlowResponseState
    horizon_sec: int
    observed_price: Decimal
    outcome_time: datetime
    outcome_price: Decimal
    forward_return_bps: Decimal
    max_up_bps: Decimal
    max_down_bps: Decimal


@dataclass
class _PendingOutcome:
    snapshot: FlowResponseSnapshot
    remaining_horizons: set[int]
    high_price: Decimal
    low_price: Decimal


class FlowResponseOutcomeTracker:
    """Track raw forward outcomes for state transitions without judging success."""

    def __init__(self, horizons_sec: Iterable[int] = (60, 180, 300, 600)) -> None:
        horizons = tuple(sorted(set(horizons_sec)))
        if not horizons or any(not isinstance(v, int) or isinstance(v, bool) or v < 1 for v in horizons):
            raise ValueError("horizons_sec must contain positive integers")
        self.horizons_sec = horizons
        self._last_state: dict[int, FlowResponseState] = {}
        self._pending: list[_PendingOutcome] = []
        self.rejected_invalid_snapshot = 0
        self.rejected_invalid_trade = 0

    def register(self, snapshots: Iterable[FlowResponseSnapshot]) -> tuple[FlowResponseSnapshot, ...]:
        """Register non-UNCLEAR state transitions and return the new events."""
        events = []
        for snapshot in snapshots:
            try:
                base = Decimal(str(snapshot.last_price))
            except (ValueError, TypeError, ArithmeticError, AttributeError):
                self.rejected_invalid_snapshot += 1
                continue
            if not base.is_finite() or base <= _ZERO:
                self.rejected_invalid_snapshot += 1
                continue
            previous = self._last_state.get(snapshot.window_sec)
            self._last_state[snapshot.window_sec] = snapshot.state
            if snapshot.state is FlowResponseState.UNCLEAR or snapshot.state is previous:
                continue
            self._pending.append(_PendingOutcome(
                snapshot=snapshot,
                remaining_horizons=set(self.horizons_sec),
                high_price=snapshot.last_price,
                low_price=snapshot.last_price,
            ))
            events.append(snapshot)
        return tuple(events)

    def observe_trade(self, trade: Any) -> tuple[FlowResponseOutcome, ...]:
        """Update excursions and emit every horizon reached by this trade."""
        try:
            price = Decimal(str(trade.price))
            quantity = Decimal(str(trade.quantity))
        except (ValueError, TypeError, ArithmeticError, AttributeError):
            self.rejected_invalid_trade += 1
            return ()
        if (
            not price.is_finite()
            or price <= _ZERO
            or not quantity.is_finite()
            or quantity <= _ZERO
        ):
            self.rejected_invalid_trade += 1
            return ()
        outcomes = []
        keep = []
        for pending in self._pending:
            snapshot = pending.snapshot
            if trade.event_time < snapshot.event_time:
                keep.append(pending)
                continue
            pending.high_price = max(pending.high_price, price)
            pending.low_price = min(pending.low_price, price)
            elapsed = (trade.event_time - snapshot.event_time).total_seconds()
            due = sorted(h for h in pending.remaining_horizons if elapsed >= h)
            for horizon_sec in due:
                base = snapshot.last_price
                if not base.is_finite() or base <= _ZERO:
                    self.rejected_invalid_snapshot += 1
                    pending.remaining_horizons.clear()
                    break
                outcomes.append(FlowResponseOutcome(
                    event_time=snapshot.event_time,
                    symbol=snapshot.symbol,
                    window_sec=snapshot.window_sec,
                    state=snapshot.state,
                    horizon_sec=horizon_sec,
                    observed_price=base,
                    outcome_time=trade.event_time,
                    outcome_price=price,
                    forward_return_bps=(price - base) / base * _BPS,
                    max_up_bps=(pending.high_price - base) / base * _BPS,
                    max_down_bps=(pending.low_price - base) / base * _BPS,
                ))
                pending.remaining_horizons.remove(horizon_sec)
            if pending.remaining_horizons:
                keep.append(pending)
        self._pending = keep
        return tuple(outcomes)

    @property
    def pending_count(self) -> int:
        return len(self._pending)
