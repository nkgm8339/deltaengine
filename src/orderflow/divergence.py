"""Deterministic regular price/CVD divergence detection on confirmed candles."""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from .cvd import Candle

logger = logging.getLogger("orderflow.divergence")

ERROR_INVALID_INPUT = "E3001"
ERROR_OUT_OF_ORDER = "E3004"


class DivergenceDirection(Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"


class DivergenceKind(Enum):
    REGULAR = "REGULAR"


@dataclass(frozen=True)
class DivergenceEvent:
    direction: DivergenceDirection
    kind: DivergenceKind
    symbol: str
    timeframe: str
    detected_time: datetime
    pivot_time: datetime
    previous_pivot_time: datetime
    pivot_price: Decimal
    previous_pivot_price: Decimal
    pivot_cvd: Decimal
    previous_pivot_cvd: Decimal
    price_change: Decimal
    cvd_change: Decimal
    bars_between: int


class CvdDivergenceDetector:
    """Detect regular divergence from the latest two same-kind swing pivots."""

    def __init__(
        self,
        *,
        equal_pivot_policy: str = "first",
        min_price_move: Decimal = Decimal("0"),
        min_bar_distance: int = 0,
    ) -> None:
        if equal_pivot_policy != "first":
            raise ValueError("equal_pivot_policy must be 'first'")
        if not isinstance(min_price_move, Decimal):
            min_price_move = Decimal(str(min_price_move))
        if min_price_move < Decimal("0"):
            raise ValueError("min_price_move must be >= 0")
        if not isinstance(min_bar_distance, int) or isinstance(min_bar_distance, bool) or min_bar_distance < 0:
            raise ValueError("min_bar_distance must be an integer >= 0")

        self.equal_pivot_policy = equal_pivot_policy
        self.min_price_move = min_price_move
        self.min_bar_distance = min_bar_distance
        self._candles: deque[Candle] = deque(maxlen=3)
        self._last_low: Optional[tuple[Candle, int]] = None
        self._last_high: Optional[tuple[Candle, int]] = None
        self._symbol: Optional[str] = None
        self._timeframe: Optional[str] = None
        self._last_time: Optional[datetime] = None
        self._bar_index = 0

        self.candles_in = 0
        self.pivots_low = 0
        self.pivots_high = 0
        self.events_detected = 0
        self.rejected_out_of_order = 0
        self.rejected_symbol_mismatch = 0
        self.rejected_timeframe_mismatch = 0
        self.rejected_min_price_move = 0
        self.rejected_min_bar_distance = 0

    def update(self, candle: Candle) -> Optional[DivergenceEvent]:
        """Accept a closed candle, returning a divergence event or ``None``."""
        if self._last_time is not None and candle.bar_time <= self._last_time:
            self.rejected_out_of_order += 1
            logger.warning("%s divergence candle rejected: non-monotonic bar_time", ERROR_OUT_OF_ORDER)
            return None
        if self._symbol is not None and candle.symbol != self._symbol:
            self.rejected_symbol_mismatch += 1
            logger.warning("%s divergence candle rejected: symbol mismatch", ERROR_INVALID_INPUT)
            return None
        if self._timeframe is not None and candle.timeframe != self._timeframe:
            self.rejected_timeframe_mismatch += 1
            logger.warning("%s divergence candle rejected: timeframe mismatch", ERROR_INVALID_INPUT)
            return None

        if self._symbol is None:
            self._symbol = candle.symbol
            self._timeframe = candle.timeframe
        self._last_time = candle.bar_time
        self.candles_in += 1
        self._candles.append(candle)
        current_index = self._bar_index
        self._bar_index += 1
        if len(self._candles) < 3:
            return None

        left, pivot, right = self._candles
        pivot_index = current_index - 1
        if left.low > pivot.low and right.low >= pivot.low:
            self.pivots_low += 1
            event = self._evaluate(DivergenceDirection.BULLISH, pivot, pivot_index, self._last_low)
            self._last_low = (pivot, pivot_index)
            if event is not None:
                return event
        if left.high < pivot.high and right.high <= pivot.high:
            self.pivots_high += 1
            event = self._evaluate(DivergenceDirection.BEARISH, pivot, pivot_index, self._last_high)
            self._last_high = (pivot, pivot_index)
            if event is not None:
                return event
        return None

    def _evaluate(
        self,
        direction: DivergenceDirection,
        pivot: Candle,
        pivot_index: int,
        previous: Optional[tuple[Candle, int]],
    ) -> Optional[DivergenceEvent]:
        if previous is None:
            return None
        previous_pivot, previous_index = previous
        pivot_price = pivot.low if direction is DivergenceDirection.BULLISH else pivot.high
        previous_price = previous_pivot.low if direction is DivergenceDirection.BULLISH else previous_pivot.high
        price_change = pivot_price - previous_price
        cvd_change = pivot.cvd - previous_pivot.cvd
        bars_between = pivot_index - previous_index
        is_regular = (
            (direction is DivergenceDirection.BULLISH and price_change < Decimal("0") and cvd_change > Decimal("0"))
            or (direction is DivergenceDirection.BEARISH and price_change > Decimal("0") and cvd_change < Decimal("0"))
        )
        if not is_regular:
            return None
        if abs(price_change) < self.min_price_move:
            self.rejected_min_price_move += 1
            logger.info("divergence rejected: min_price_move")
            return None
        if bars_between < self.min_bar_distance:
            self.rejected_min_bar_distance += 1
            logger.info("divergence rejected: min_bar_distance")
            return None
        self.events_detected += 1
        return DivergenceEvent(
            direction=direction,
            kind=DivergenceKind.REGULAR,
            symbol=pivot.symbol,
            timeframe=pivot.timeframe,
            detected_time=self._last_time,
            pivot_time=pivot.bar_time,
            previous_pivot_time=previous_pivot.bar_time,
            pivot_price=pivot_price,
            previous_pivot_price=previous_price,
            pivot_cvd=pivot.cvd,
            previous_pivot_cvd=previous_pivot.cvd,
            price_change=price_change,
            cvd_change=cvd_change,
            bars_between=bars_between,
        )
