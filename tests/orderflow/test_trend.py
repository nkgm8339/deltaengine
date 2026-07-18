from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.orderflow.cvd import Candle
from src.orderflow.trend import EmaTrendDetector


UTC = timezone.utc


def _candle(close: str, timeframe: str = "15m") -> Candle:
    value = Decimal(close)
    return Candle(datetime(2026, 1, 1, tzinfo=UTC), "BTCUSDT", timeframe,
                  value, value, value, value, Decimal("1"), Decimal("1"), Decimal("1"))


def test_trend_waits_for_slow_ema_history_then_detects_uptrend() -> None:
    detector = EmaTrendDetector(fast_period=2, slow_period=3)
    assert detector.update(_candle("100")).direction == "WARMUP"
    assert detector.update(_candle("101")).direction == "WARMUP"
    state = detector.update(_candle("102"))
    assert state.direction == "UP"
    assert state.samples == 3


def test_trend_detects_downtrend() -> None:
    detector = EmaTrendDetector(fast_period=2, slow_period=3)
    detector.update(_candle("102"))
    detector.update(_candle("101"))
    assert detector.update(_candle("100")).direction == "DOWN"


def test_trend_rejects_other_timeframe() -> None:
    with pytest.raises(ValueError, match="expected 15m"):
        EmaTrendDetector().update(_candle("100", "5m"))
