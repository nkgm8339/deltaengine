from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.orderflow.cvd import Candle
from src.orderflow.divergence import CvdDivergenceDetector


def _candle(index: int, low: int, high: int, cvd: int) -> Candle:
    price = Decimal(low)
    return Candle(datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=index), "BTCUSDT", "1m", price, Decimal(high), price, price, Decimal(1), Decimal(1), Decimal(cvd))


def test_detects_bullish_regular_divergence() -> None:
    detector = CvdDivergenceDetector()
    candles = [_candle(0, 101, 103, 10), _candle(1, 100, 102, 5), _candle(2, 101, 103, 8), _candle(3, 100, 102, 12), _candle(4, 99, 101, 9), _candle(5, 101, 103, 13)]
    results = [detector.update(c) for c in candles]
    assert results[-1] is not None
    assert results[-1].direction == "BULLISH"
