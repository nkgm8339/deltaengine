"""Higher-timeframe trend classification for the entry filter."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .cvd import Candle


@dataclass(frozen=True)
class TrendState:
    timeframe: str
    direction: str  # WARMUP | UP | DOWN | RANGE
    close: Decimal
    ema_fast: Decimal
    ema_slow: Decimal
    samples: int


class EmaTrendDetector:
    """Classify a confirmed candle using fast/slow EMAs and its close price."""

    def __init__(self, timeframe: str = "15m", fast_period: int = 20, slow_period: int = 50) -> None:
        if fast_period <= 0 or slow_period <= fast_period:
            raise ValueError("periods must satisfy 0 < fast_period < slow_period")
        self.timeframe = timeframe
        self.fast_period = fast_period
        self.slow_period = slow_period
        self._fast_alpha = Decimal(2) / Decimal(fast_period + 1)
        self._slow_alpha = Decimal(2) / Decimal(slow_period + 1)
        self._ema_fast: Decimal | None = None
        self._ema_slow: Decimal | None = None
        self._samples = 0

    def update(self, candle: Candle) -> TrendState:
        if candle.timeframe != self.timeframe:
            raise ValueError(f"expected {self.timeframe} candle, got {candle.timeframe}")
        close = candle.close
        if self._ema_fast is None:
            self._ema_fast = close
            self._ema_slow = close
        else:
            self._ema_fast += self._fast_alpha * (close - self._ema_fast)
            self._ema_slow += self._slow_alpha * (close - self._ema_slow)
        self._samples += 1

        if self._samples < self.slow_period:
            direction = "WARMUP"
        elif close > self._ema_fast and self._ema_fast > self._ema_slow:
            direction = "UP"
        elif close < self._ema_fast and self._ema_fast < self._ema_slow:
            direction = "DOWN"
        else:
            direction = "RANGE"
        return TrendState(
            timeframe=self.timeframe,
            direction=direction,
            close=close,
            ema_fast=self._ema_fast,
            ema_slow=self._ema_slow,
            samples=self._samples,
        )
