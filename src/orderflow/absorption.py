"""Absorption detector — sliding-window sell/buy aggression absorption (MOD-006, M9).

Spec: ArchitectureRepository/30_Modules/Absorption_v3.1.md.
Test vectors: ArchitectureRepository/50_Test/TestSpecification_v3.2.md §4.4
(TV-ABS-01 through TV-ABS-05).

Detection logic (Absorption_v3.1 §5.2):
    1. Sliding window (window_sec) of trades.
    2. Directional aggression aggregation (agg_buy / agg_sell).
    3. Stall condition: distinct executed prices <= price_stall_ticks.
    4. Aggression condition: agg_side >= volume_ref.current() * volume_multiplier.
    5. Replenish condition: current bid/ask quantity >= window_start bid/ask quantity.
    6. Result: AbsorptionResult with strength = min(aggr / threshold, 1.0).

Design decisions (instruction §4):
    1. price_stall_ticks = max distinct executed price count (not tick_size-based).
    2. volume_ref.current() None => threshold undetermined, sink (no counter incr).
    3. window_start_snapshot captured when window head advances or at first trade.
    4. Absorption is tick-driven; SignalEngine queries current() at bar close.
    5. Both-direction tie => BUY_ABSORPTION priority, double_direction_events++.

classification values (Absorption_v3.1 §5.3):
    "BUY_ABSORPTION"  — sell-side aggression is being absorbed (bullish signal).
    "SELL_ABSORPTION" — buy-side aggression is being absorbed (bearish signal).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any, Optional

from .orderbook import OrderBookSnapshot, OrderBookStateManager
from .volume_ref import VolumeRefTracker

_ZERO = Decimal(0)
_ONE = Decimal(1)


@dataclass(frozen=True)
class AbsorptionResult:
    """Outcome reported by the Absorption module to SignalEngine.

    classification: "BUY_ABSORPTION" | "SELL_ABSORPTION"
    strength: 0.0-1.0 (normalised absorption strength)
    """

    classification: str
    strength: Decimal


class AbsorptionDetector:
    """Sliding-window absorption detector (Absorption_v3.1 §5.2).

    Tick-driven: observe_trade() updates the sliding window and evaluates the
    three detection conditions on every tick. current() returns the latest result.
    """

    def __init__(
        self,
        *,
        window_sec: int,
        price_stall_ticks: int,
        volume_multiplier: Decimal,
        volume_ref: VolumeRefTracker,
        book_state: OrderBookStateManager,
    ) -> None:
        self._window_sec = window_sec
        self._price_stall_ticks = price_stall_ticks
        self._volume_multiplier = Decimal(str(volume_multiplier))
        self._volume_ref = volume_ref
        self._book_state = book_state
        # sliding window of trades (any duck-typed trade with event_time/price/quantity/side)
        self._window: deque[Any] = deque()
        self._window_start_snapshot: Optional[OrderBookSnapshot] = None
        self._last_result: Optional[AbsorptionResult] = None
        # counters (no silent loss)
        self.events_detected: int = 0
        self.aggression_condition_fails: int = 0
        self.stall_condition_fails: int = 0
        self.replenish_condition_fails: int = 0
        self.double_direction_events: int = 0

    def observe_trade(self, trade: Any) -> None:
        """Process one trade; update the sliding window and evaluate detection."""
        cutoff = trade.event_time - timedelta(seconds=self._window_sec)

        was_empty = not self._window

        # Prune trades outside the window from the left.
        old_head = self._window[0].event_time if self._window else None
        while self._window and self._window[0].event_time <= cutoff:
            self._window.popleft()
        new_head = self._window[0].event_time if self._window else None

        window_advanced = old_head != new_head  # True when any trade was pruned

        # Capture window_start_snapshot when window head advances or at first trade.
        if was_empty or window_advanced:
            snap = self._book_state.snapshot()
            if snap is not None:
                self._window_start_snapshot = snap

        self._window.append(trade)

        current_snap = self._book_state.snapshot()
        if current_snap is None or self._window_start_snapshot is None:
            self._last_result = None
            return

        self._last_result = self._evaluate(current_snap)

    def current(self) -> Optional[AbsorptionResult]:
        """Return the most recent AbsorptionResult, or None if no detection active."""
        return self._last_result

    def _evaluate(self, current_snap: OrderBookSnapshot) -> Optional[AbsorptionResult]:
        # Step 2: Directional aggression over the window.
        agg_buy = _ZERO
        agg_sell = _ZERO
        distinct_prices: set[Decimal] = set()
        for t in self._window:
            q = Decimal(str(t.quantity)) if not isinstance(t.quantity, Decimal) else t.quantity
            p = Decimal(str(t.price)) if not isinstance(t.price, Decimal) else t.price
            if t.side == "BUY":
                agg_buy += q
            else:
                agg_sell += q
            distinct_prices.add(p)

        # Step 3: Stall condition.
        if len(distinct_prices) > self._price_stall_ticks:
            self.stall_condition_fails += 1
            return None

        # Step 4: Aggression condition.
        vol_ref = self._volume_ref.current()
        if vol_ref is None:
            return None  # threshold undetermined — sink, no counter increment

        threshold = vol_ref * self._volume_multiplier

        buy_abs_cand = agg_sell >= threshold   # SELL aggression -> BUY_ABSORPTION candidate
        sell_abs_cand = agg_buy >= threshold   # BUY aggression -> SELL_ABSORPTION candidate

        if not buy_abs_cand and not sell_abs_cand:
            self.aggression_condition_fails += 1
            return None

        # Step 5: Replenish condition.
        ws = self._window_start_snapshot
        buy_replenished = buy_abs_cand and all(
            current_snap.bid_quantity_at(p) >= ws.bid_quantity_at(p)
            for p in distinct_prices
        )
        sell_replenished = sell_abs_cand and all(
            current_snap.ask_quantity_at(p) >= ws.ask_quantity_at(p)
            for p in distinct_prices
        )

        if not buy_replenished and not sell_replenished:
            self.replenish_condition_fails += 1
            return None

        # Step 6: Judgment — BUY_ABSORPTION priority on double-direction tie (decision 5).
        if buy_replenished and sell_replenished:
            self.double_direction_events += 1
            sell_replenished = False

        if buy_replenished:
            strength = min(agg_sell / threshold, _ONE)
            self.events_detected += 1
            return AbsorptionResult(classification="BUY_ABSORPTION", strength=strength)
        else:
            strength = min(agg_buy / threshold, _ONE)
            self.events_detected += 1
            return AbsorptionResult(classification="SELL_ABSORPTION", strength=strength)
