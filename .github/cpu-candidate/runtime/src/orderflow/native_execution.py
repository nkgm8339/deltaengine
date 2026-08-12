"""Native execution-timeframe aggregation.

Consumes normalized raw trades and builds independent 5m/10m candles, CVD,
and footprint bars. It never derives execution data from 1m output.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .cvd import Candle, CvdCalculator, Trade
from .footprint import FootprintBar, FootprintCalculator

NATIVE_EXECUTION_TIMEFRAMES: tuple[str, ...] = ("5m", "10m")


@dataclass(frozen=True)
class NativeExecutionUpdate:
    """Closed native bars emitted by one accepted raw trade."""

    closed: dict[str, Candle]
    closed_footprints: dict[str, FootprintBar]


class NativeExecutionAggregator:
    """Build independent native 5m/10m CVD and footprint bars."""

    def __init__(
        self,
        symbol: str,
        timeframes: Iterable[str] = NATIVE_EXECUTION_TIMEFRAMES,
    ) -> None:
        selected = tuple(dict.fromkeys(timeframes))
        if not selected:
            raise ValueError("at least one native execution timeframe is required")
        unknown = set(selected) - set(NATIVE_EXECUTION_TIMEFRAMES)
        if unknown:
            raise ValueError(f"unsupported native execution timeframe(s): {sorted(unknown)}")
        self.symbol = symbol
        self._calculators = {
            timeframe: CvdCalculator(symbol, timeframe) for timeframe in selected
        }
        self._footprints = {
            timeframe: FootprintCalculator(symbol, timeframe) for timeframe in selected
        }

    @property
    def timeframes(self) -> tuple[str, ...]:
        return tuple(self._calculators)

    def process(self, trade: Trade) -> NativeExecutionUpdate:
        """Consume one raw trade and return bars closed by that trade."""
        closed: dict[str, Candle] = {}
        closed_footprints: dict[str, FootprintBar] = {}
        for timeframe, calculator in self._calculators.items():
            result = calculator.process(trade)
            if not result.accepted:
                raise ValueError(
                    f"native execution trade rejected for {timeframe}: {result.rejection}"
                )
            if result.closed_candle is not None:
                closed[timeframe] = result.closed_candle
            footprint = self._footprints[timeframe].process_trade(trade)
            if footprint is not None:
                closed_footprints[timeframe] = footprint
        return NativeExecutionUpdate(
            closed=closed,
            closed_footprints=closed_footprints,
        )

    def snapshots(self) -> dict[str, Candle]:
        """Return forming CVD candles without mutating state."""
        return {
            timeframe: candle
            for timeframe, calculator in self._calculators.items()
            if (candle := calculator.current_bar_snapshot()) is not None
        }

    def finalize(self) -> dict[str, Candle]:
        """Close each started native CVD bar exactly once."""
        return {
            timeframe: candle
            for timeframe, calculator in self._calculators.items()
            if (candle := calculator.finalize()) is not None
        }

    def finalize_footprints(self) -> dict[str, FootprintBar]:
        """Close each started native footprint bar exactly once."""
        return {
            timeframe: footprint
            for timeframe, calculator in self._footprints.items()
            if (footprint := calculator.finalize()) is not None
        }
