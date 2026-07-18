"""Regular price/CVD divergence detection on confirmed candles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .cvd import Candle


@dataclass(frozen=True)
class Divergence:
    direction: str  # BULLISH | BEARISH
    candle: Candle


class CvdDivergenceDetector:
    """Detect regular divergence between the two latest price swing points."""

    def __init__(self) -> None:
        self._candles: list[Candle] = []
        self._lows: list[Candle] = []
        self._highs: list[Candle] = []

    def update(self, candle: Candle) -> Optional[Divergence]:
        self._candles.append(candle)
        if len(self._candles) < 3:
            return None
        left, pivot, right = self._candles[-3:]
        if pivot.low < left.low and pivot.low < right.low:
            self._lows.append(pivot)
            if len(self._lows) >= 2:
                previous = self._lows[-2]
                if pivot.low < previous.low and pivot.cvd > previous.cvd:
                    return Divergence("BULLISH", pivot)
        if pivot.high > left.high and pivot.high > right.high:
            self._highs.append(pivot)
            if len(self._highs) >= 2:
                previous = self._highs[-2]
                if pivot.high > previous.high and pivot.cvd < previous.cvd:
                    return Divergence("BEARISH", pivot)
        return None
