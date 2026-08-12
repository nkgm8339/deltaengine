"""Concurrent higher-timeframe candle aggregation for trend analysis."""

from __future__ import annotations

from collections.abc import Iterable

from .cvd import Candle, CvdCalculator, Trade


DEFAULT_TREND_TIMEFRAMES: tuple[str, ...] = ("5m", "15m")


class MultiTimeframeCandleAggregator:
    """Build closed candles for several timeframes from one accepted trade stream.

    Each timeframe has its own CVD calculator, so its candle delta and end-of-bar
    CVD remain consistent with the primary stream.  This class intentionally does
    not persist or publish candles; consumers decide when a higher-timeframe bar
    is ready to affect a strategy.
    """

    def __init__(self, symbol: str, timeframes: Iterable[str] = DEFAULT_TREND_TIMEFRAMES) -> None:
        unique = tuple(dict.fromkeys(timeframes))
        if not unique:
            raise ValueError("at least one timeframe is required")
        self._calculators = {timeframe: CvdCalculator(symbol, timeframe) for timeframe in unique}

    @property
    def timeframes(self) -> tuple[str, ...]:
        return tuple(self._calculators)

    def process(self, trade: Trade) -> dict[str, Candle]:
        """Process one accepted trade and return any bars closed by it."""
        closed: dict[str, Candle] = {}
        for timeframe, calculator in self._calculators.items():
            result = calculator.process(trade)
            if not result.accepted:
                raise ValueError(f"higher-timeframe trade rejected for {timeframe}")
            if result.closed_candle is not None:
                closed[timeframe] = result.closed_candle
        return closed

    def snapshots(self) -> dict[str, Candle]:
        """Return non-destructive snapshots for all started timeframes."""
        return {
            timeframe: candle
            for timeframe, calculator in self._calculators.items()
            if (candle := calculator.current_bar_snapshot()) is not None
        }
