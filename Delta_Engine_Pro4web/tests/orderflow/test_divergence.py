from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.orderflow.cvd import Candle
from src.orderflow.divergence import (
    CvdDivergenceDetector,
    DivergenceDirection,
    DivergenceKind,
)


BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _candle(index: int, low: int, high: int, cvd: int, *, symbol: str = "BTCUSDT", timeframe: str = "1m") -> Candle:
    low_d = Decimal(low)
    high_d = Decimal(high)
    return Candle(
        bar_time=BASE + timedelta(minutes=index), symbol=symbol, timeframe=timeframe,
        open=low_d, high=high_d, low=low_d, close=low_d,
        volume=Decimal(1), delta=Decimal(1), cvd=Decimal(cvd),
    )


def _bullish() -> list[Candle]:
    return [_candle(0, 101, 103, 0), _candle(1, 100, 102, 5), _candle(2, 101, 103, 7), _candle(3, 100, 102, 8), _candle(4, 99, 101, 10), _candle(5, 101, 103, 11)]


def _bearish() -> list[Candle]:
    return [_candle(0, 101, 103, 10), _candle(1, 100, 105, 8), _candle(2, 101, 104, 7), _candle(3, 100, 103, 6), _candle(4, 101, 106, 5), _candle(5, 100, 105, 4)]


def _events(detector: CvdDivergenceDetector, candles: list[Candle]):
    return [event for candle in candles if (event := detector.update(candle)) is not None]


def test_detects_bullish_regular_divergence_all_fields() -> None:
    event = _events(CvdDivergenceDetector(), _bullish())[0]
    assert event.direction is DivergenceDirection.BULLISH
    assert event.kind is DivergenceKind.REGULAR
    assert event.symbol == "BTCUSDT" and event.timeframe == "1m"
    assert event.previous_pivot_time == BASE + timedelta(minutes=1)
    assert event.pivot_time == BASE + timedelta(minutes=4)
    assert event.detected_time == BASE + timedelta(minutes=5)
    assert event.pivot_price == Decimal(99) and event.previous_pivot_price == Decimal(100)
    assert event.pivot_cvd == Decimal(10) and event.previous_pivot_cvd == Decimal(5)
    assert event.price_change == Decimal(-1) and event.cvd_change == Decimal(5)
    assert event.bars_between == 3


def test_detects_bearish_regular_divergence_all_fields() -> None:
    event = _events(CvdDivergenceDetector(), _bearish())[0]
    assert event.direction is DivergenceDirection.BEARISH
    assert event.kind is DivergenceKind.REGULAR
    assert event.previous_pivot_time == BASE + timedelta(minutes=1)
    assert event.pivot_time == BASE + timedelta(minutes=4)
    assert event.detected_time == BASE + timedelta(minutes=5)
    assert event.pivot_price == Decimal(106) and event.previous_pivot_price == Decimal(105)
    assert event.pivot_cvd == Decimal(5) and event.previous_pivot_cvd == Decimal(8)
    assert event.price_change == Decimal(1) and event.cvd_change == Decimal(-3)
    assert event.bars_between == 3


def test_no_event_when_price_and_cvd_make_lower_lows() -> None:
    candles = _bullish()
    candles[4] = _candle(4, 99, 101, 4)
    assert _events(CvdDivergenceDetector(), candles) == []


def test_no_event_with_only_one_swing() -> None:
    assert _events(CvdDivergenceDetector(), _bullish()[:3]) == []


def test_equal_low_cluster_uses_first_candle_as_pivot() -> None:
    detector = CvdDivergenceDetector()
    candles = [_candle(0, 101, 103, 0), _candle(1, 100, 102, 5), _candle(2, 100, 103, 6), _candle(3, 101, 102, 7)]
    _events(detector, candles)
    assert detector._last_low is not None
    assert detector._last_low[0].bar_time == BASE + timedelta(minutes=1)


def test_separated_double_bottom_is_registered_but_not_regular_divergence() -> None:
    candles = [_candle(0, 101, 103, 0), _candle(1, 100, 102, 5), _candle(2, 101, 103, 6), _candle(3, 101, 102, 7), _candle(4, 100, 101, 10), _candle(5, 101, 103, 11)]
    detector = CvdDivergenceDetector()
    assert _events(detector, candles) == []
    assert detector.pivots_low == 2


def test_rejections_are_counted_for_time_symbol_and_timeframe() -> None:
    detector = CvdDivergenceDetector()
    assert detector.update(_candle(0, 100, 101, 0)) is None
    assert detector.update(_candle(0, 100, 101, 0)) is None
    assert detector.update(_candle(1, 100, 101, 0, symbol="ETHUSDT")) is None
    assert detector.update(_candle(1, 100, 101, 0, timeframe="5m")) is None
    assert detector.rejected_out_of_order == 1
    assert detector.rejected_symbol_mismatch == 1
    assert detector.rejected_timeframe_mismatch == 1
    assert detector.candles_in == 1


def test_memory_is_bounded_after_many_candles() -> None:
    detector = CvdDivergenceDetector()
    for index in range(100):
        detector.update(_candle(index, 100 + (index % 3), 104 + (index % 3), index))
    assert len(detector._candles) == 3
    assert detector._last_low is not None or detector._last_high is not None


def test_min_price_move_and_distance_filters_are_counted() -> None:
    price_detector = CvdDivergenceDetector(min_price_move=Decimal(2))
    assert _events(price_detector, _bullish()) == []
    assert price_detector.rejected_min_price_move == 1
    distance_detector = CvdDivergenceDetector(min_bar_distance=4)
    assert _events(distance_detector, _bullish()) == []
    assert distance_detector.rejected_min_bar_distance == 1


def test_multiple_divergences_are_emitted_in_order() -> None:
    candles = _bullish() + [_candle(6, 100, 102, 12), _candle(7, 98, 101, 15), _candle(8, 101, 103, 16)]
    events = _events(CvdDivergenceDetector(), candles)
    assert [event.pivot_time for event in events] == [BASE + timedelta(minutes=4), BASE + timedelta(minutes=7)]


def test_deterministic_replay_has_identical_events_and_counters() -> None:
    first = CvdDivergenceDetector()
    second = CvdDivergenceDetector()
    assert _events(first, _bullish()) == _events(second, _bullish())
    counters = ("candles_in", "pivots_low", "pivots_high", "events_detected", "rejected_out_of_order", "rejected_symbol_mismatch", "rejected_timeframe_mismatch", "rejected_min_price_move", "rejected_min_bar_distance")
    assert tuple(getattr(first, name) for name in counters) == tuple(getattr(second, name) for name in counters)


def test_default_constructor_detects_both_directions() -> None:
    assert _events(CvdDivergenceDetector(), _bullish())[0].direction is DivergenceDirection.BULLISH
    assert _events(CvdDivergenceDetector(), _bearish())[0].direction is DivergenceDirection.BEARISH
