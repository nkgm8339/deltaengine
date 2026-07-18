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


def _signal(signal: str):
    from src.orderflow.signal import SignalResult
    return SignalResult(Decimal("70"), Decimal("0.7"), signal, ())


def test_filter_allows_only_signals_aligned_with_trend() -> None:
    from src.orderflow.trend import TrendState, apply_trend_filter
    up = TrendState("15m", "UP", Decimal("100"), Decimal("99"), Decimal("98"), 50)
    down = TrendState("15m", "DOWN", Decimal("100"), Decimal("101"), Decimal("102"), 50)
    assert apply_trend_filter(_signal("BUY"), up).signal == "BUY"
    assert apply_trend_filter(_signal("SELL"), down).signal == "SELL"
    assert apply_trend_filter(_signal("SELL"), up).signal == "WAIT"
    assert apply_trend_filter(_signal("BUY"), down).signal == "WAIT"


def test_filter_blocks_signal_until_trend_is_ready() -> None:
    from src.orderflow.trend import apply_trend_filter
    filtered = apply_trend_filter(_signal("BUY"), None)
    assert filtered.signal == "WAIT"
    assert "TREND_FILTER_WARMUP" in filtered.reasons