"""Unit tests for AbsorptionDetector (B-2 M9).

11 tests: TV-ABS-01..05 (TestSpecification_v3.2 §4.4) + 6 additional.

Fixture defaults (per §4.4):
    window_sec=10, price_stall_ticks=1, volume_multiplier=2.0,
    volume_ref calibrated so current()=Decimal("50") -> threshold=100.
    book_state initialized via SNAPSHOT with bid@100=500, ask@100=500.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.orderflow.absorption import AbsorptionDetector, AbsorptionResult
from src.orderflow.orderbook import BookLevel, OrderBookStateManager, OrderBookUpdate
from src.orderflow.volume_ref import VolumeRefTracker

UTC = timezone.utc
D = Decimal

# Epoch anchor for all test trades.
_T0 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_snapshot(
    symbol: str = "BTCUSDT",
    final_id: int = 1,
    bid_price: str = "100",
    bid_qty: str = "500",
    ask_price: str = "101",
    ask_qty: str = "500",
) -> OrderBookUpdate:
    return OrderBookUpdate(
        event_time=_T0,
        symbol=symbol,
        update_type="SNAPSHOT",
        first_update_id=None,
        final_update_id=final_id,
        bids=(BookLevel(D(bid_price), D(bid_qty)),),
        asks=(BookLevel(D(ask_price), D(ask_qty)),),
    )


def _make_diff(
    symbol: str = "BTCUSDT",
    first_id: int = 2,
    final_id: int = 2,
    bids: list[tuple[str, str]] | None = None,
    asks: list[tuple[str, str]] | None = None,
    dt: datetime | None = None,
) -> OrderBookUpdate:
    bids = bids or []
    asks = asks or []
    return OrderBookUpdate(
        event_time=dt or _T0,
        symbol=symbol,
        update_type="DIFF",
        first_update_id=first_id,
        final_update_id=final_id,
        bids=tuple(BookLevel(D(p), D(q)) for p, q in bids),
        asks=tuple(BookLevel(D(p), D(q)) for p, q in asks),
    )


class _FakeTrade:
    """Lightweight trade object for injection into AbsorptionDetector."""

    def __init__(
        self,
        event_time: datetime,
        price: str | Decimal,
        quantity: str | Decimal,
        side: str,
        trade_id: int = 0,
    ) -> None:
        self.event_time = event_time
        self.price = D(str(price))
        self.quantity = D(str(quantity))
        self.side = side
        self.trade_id = trade_id


def _calibrated_volume_ref(value: str = "50", bars: int = 1) -> VolumeRefTracker:
    """Return a VolumeRefTracker with current() == Decimal(value)."""
    tracker = VolumeRefTracker(bars=bars)
    tracker.observe_bar([D(value)])
    assert tracker.current() == D(value)
    return tracker


def _make_detector(
    book_state: OrderBookStateManager | None = None,
    volume_ref: VolumeRefTracker | None = None,
    *,
    window_sec: int = 10,
    price_stall_ticks: int = 1,
    volume_multiplier: str = "2.0",
    symbol: str = "BTCUSDT",
) -> AbsorptionDetector:
    if book_state is None:
        book_state = OrderBookStateManager(symbol)
        book_state.apply(_make_snapshot(symbol=symbol))
    if volume_ref is None:
        volume_ref = _calibrated_volume_ref()
    return AbsorptionDetector(
        window_sec=window_sec,
        price_stall_ticks=price_stall_ticks,
        volume_multiplier=D(volume_multiplier),
        volume_ref=volume_ref,
        book_state=book_state,
    )


# ---------------------------------------------------------------------------
# TV-ABS-01: BUY_ABSORPTION qualifies
# ---------------------------------------------------------------------------

def test_tv_abs_01_buy_absorption_qualifies() -> None:
    """SELL 120@100, distinct=1, bid replenished -> BUY_ABSORPTION, strength=1.0."""
    detector = _make_detector()
    # Single SELL trade exceeding threshold (100); distinct prices = 1.
    trade = _FakeTrade(_T0, "100", "120", "SELL", trade_id=1)
    detector.observe_trade(trade)

    result = detector.current()
    assert result is not None
    assert result.classification == "BUY_ABSORPTION"
    assert result.strength == D("1")
    assert result.price_low == D("100")
    assert result.price_high == D("100")
    assert (result.price_low, result.price_high) == (D("100"), D("100"))
    assert detector.events_detected == 1
    assert detector.aggression_condition_fails == 0
    assert detector.stall_condition_fails == 0
    assert detector.replenish_condition_fails == 0


# ---------------------------------------------------------------------------
# TV-ABS-02: aggression condition fails
# ---------------------------------------------------------------------------

def test_tv_abs_02_aggression_fails() -> None:
    """SELL 80 < threshold 100 -> no event, aggression_condition_fails==1."""
    detector = _make_detector()
    trade = _FakeTrade(_T0, "100", "80", "SELL", trade_id=1)
    detector.observe_trade(trade)

    assert detector.current() is None
    assert detector.aggression_condition_fails == 1
    assert detector.events_detected == 0


# ---------------------------------------------------------------------------
# TV-ABS-03: stall condition fails (2 distinct prices)
# ---------------------------------------------------------------------------

def test_tv_abs_03_stall_fails() -> None:
    """Two distinct prices in window -> stall_condition_fails==1."""
    detector = _make_detector()
    # Two trades at different prices; total SELL >= threshold but 2 distinct prices.
    t1 = _FakeTrade(_T0, "100", "70", "SELL", trade_id=1)
    t2 = _FakeTrade(_T0 + timedelta(seconds=1), "101", "60", "SELL", trade_id=2)
    detector.observe_trade(t1)
    detector.observe_trade(t2)

    assert detector.current() is None
    assert detector.stall_condition_fails >= 1
    assert detector.events_detected == 0


# ---------------------------------------------------------------------------
# TV-ABS-04: replenish condition fails (bid decreased)
# ---------------------------------------------------------------------------

def test_tv_abs_04_replenish_fails() -> None:
    """bid at 100 decreases after window_start -> replenish_condition_fails==1."""
    book_state = OrderBookStateManager("BTCUSDT")
    # Initial SNAPSHOT: bid@100=500
    book_state.apply(_make_snapshot(bid_price="100", bid_qty="500"))

    detector = _make_detector(book_state=book_state)

    # First trade (small SELL) establishes window_start_snapshot with bid@100=500.
    t1 = _FakeTrade(_T0, "100", "1", "SELL", trade_id=1)
    detector.observe_trade(t1)
    # agg_sell=1 < threshold=100 -> aggression fails (aggression_condition_fails=1)

    # Reduce bid at 100 in the book (market maker withdrew).
    book_state.apply(_make_diff(
        bids=[("100", "10")],  # reduce bid@100 from 500 to 10
        first_id=2, final_id=2,
    ))

    # Second trade: total SELL > threshold but bid dropped.
    t2 = _FakeTrade(_T0 + timedelta(seconds=1), "100", "100", "SELL", trade_id=2)
    detector.observe_trade(t2)
    # agg_sell=1+100=101 >= 100, distinct={100} <=1
    # current bid@100=10 < window_start bid@100=500 -> replenish FAILS

    assert detector.current() is None
    assert detector.replenish_condition_fails == 1
    assert detector.events_detected == 0


# ---------------------------------------------------------------------------
# TV-ABS-05: SELL_ABSORPTION qualifies
# ---------------------------------------------------------------------------

def test_tv_abs_05_sell_absorption_qualifies() -> None:
    """BUY 150@200, ask replenished -> SELL_ABSORPTION, strength=1.0."""
    book_state = OrderBookStateManager("BTCUSDT")
    book_state.apply(_make_snapshot(
        bid_price="199", bid_qty="500",
        ask_price="200", ask_qty="500",
    ))
    detector = _make_detector(book_state=book_state)

    trade = _FakeTrade(_T0, "200", "150", "BUY", trade_id=1)
    detector.observe_trade(trade)

    result = detector.current()
    assert result is not None
    assert result.classification == "SELL_ABSORPTION"
    assert result.strength == D("1")
    assert result.price_low == D("200")
    assert result.price_high == D("200")
    assert (result.price_low, result.price_high) == (D("200"), D("200"))
    assert detector.events_detected == 1


# ---------------------------------------------------------------------------
# Additional test 1: window expiry clears result
# ---------------------------------------------------------------------------

def test_absorption_window_expiry() -> None:
    """After window_sec passes, current() returns None once old trades are pruned."""
    detector = _make_detector(window_sec=5)

    # Detect BUY_ABSORPTION at T0.
    t1 = _FakeTrade(_T0, "100", "120", "SELL", trade_id=1)
    detector.observe_trade(t1)
    assert detector.current() is not None

    # New trade at T0 + window_sec + 1 -> t1 is pruned, re-eval fails (agg_sell=1 < 100).
    t2 = _FakeTrade(_T0 + timedelta(seconds=6), "100", "1", "SELL", trade_id=2)
    detector.observe_trade(t2)
    assert detector.current() is None


# ---------------------------------------------------------------------------
# Additional test 2: uncalibrated volume_ref -> sink, no counter increment
# ---------------------------------------------------------------------------

def test_absorption_volume_ref_not_calibrated() -> None:
    """volume_ref.current() is None -> no event, no counter increments."""
    book_state = OrderBookStateManager("BTCUSDT")
    book_state.apply(_make_snapshot())
    uncalibrated_ref = VolumeRefTracker(bars=1)  # no observe_bar called
    assert uncalibrated_ref.current() is None

    detector = AbsorptionDetector(
        window_sec=10,
        price_stall_ticks=1,
        volume_multiplier=D("2.0"),
        volume_ref=uncalibrated_ref,
        book_state=book_state,
    )
    trade = _FakeTrade(_T0, "100", "9999", "SELL", trade_id=1)
    detector.observe_trade(trade)

    assert detector.current() is None
    assert detector.aggression_condition_fails == 0
    assert detector.stall_condition_fails == 0
    assert detector.replenish_condition_fails == 0
    assert detector.events_detected == 0


# ---------------------------------------------------------------------------
# Additional test 3: uninitialized book_state -> no event
# ---------------------------------------------------------------------------

def test_absorption_book_state_uninitialized() -> None:
    """book_state.snapshot() is None (no SNAPSHOT applied) -> no event."""
    book_state = OrderBookStateManager("BTCUSDT")
    # No SNAPSHOT applied -> book_state.snapshot() is None.
    volume_ref = _calibrated_volume_ref()

    detector = AbsorptionDetector(
        window_sec=10,
        price_stall_ticks=1,
        volume_multiplier=D("2.0"),
        volume_ref=volume_ref,
        book_state=book_state,
    )
    trade = _FakeTrade(_T0, "100", "9999", "SELL", trade_id=1)
    detector.observe_trade(trade)

    assert detector.current() is None
    assert detector.events_detected == 0


# ---------------------------------------------------------------------------
# Additional test 4: deterministic replay
# ---------------------------------------------------------------------------

def test_absorption_deterministic_replay() -> None:
    """Identical trade sequence twice -> identical events_detected and current()."""
    def run() -> tuple[int, AbsorptionResult | None]:
        book_state = OrderBookStateManager("BTCUSDT")
        book_state.apply(_make_snapshot())
        volume_ref = _calibrated_volume_ref()
        detector = AbsorptionDetector(
            window_sec=10,
            price_stall_ticks=1,
            volume_multiplier=D("2.0"),
            volume_ref=volume_ref,
            book_state=book_state,
        )
        trades = [
            _FakeTrade(_T0, "100", "60", "SELL", trade_id=1),
            _FakeTrade(_T0 + timedelta(seconds=1), "100", "70", "SELL", trade_id=2),
        ]
        for t in trades:
            detector.observe_trade(t)
        return detector.events_detected, detector.current()

    r1 = run()
    r2 = run()
    assert r1[0] == r2[0]
    assert r1[1] == r2[1]
    # Also verify detection occurred (agg_sell=130 >= threshold=100).
    assert r1[0] == 1
    assert r1[1] is not None
    assert r1[1].classification == "BUY_ABSORPTION"


def test_absorption_set_params_preserves_window() -> None:
    detector = _make_detector()
    trade = _FakeTrade(_T0, "100", "1", "SELL", trade_id=1)
    detector.observe_trade(trade)
    before = tuple(detector._window)
    detector.set_params(price_stall_ticks=2, volume_multiplier=D("3.0"))
    assert detector._price_stall_ticks == 2
    assert detector._volume_multiplier == D("3.0")
    assert tuple(detector._window) == before


def test_absorption_reports_full_stalled_price_range() -> None:
    """Native reading preserves min/max across the qualifying stalled-price set."""
    detector = _make_detector(price_stall_ticks=2)
    detector.observe_trade(_FakeTrade(_T0, "100", "60", "SELL", trade_id=1))
    detector.observe_trade(
        _FakeTrade(_T0 + timedelta(seconds=1), "101", "60", "SELL", trade_id=2)
    )

    result = detector.current()
    assert result is not None
    assert (result.price_low, result.price_high) == (D("100"), D("101"))


def test_set_params_updates_thresholds_without_touching_window() -> None:
    """Gear updates thresholds in place without rebuilding the live trade window."""
    detector = _make_detector()
    detector.observe_trade(_FakeTrade(_T0, "100", "1", "SELL", trade_id=1))
    window = detector._window
    contents = tuple(window)
    start_snapshot = detector._window_start_snapshot

    detector.set_params(price_stall_ticks=2, volume_multiplier=D("3.0"))

    assert detector._price_stall_ticks == 2
    assert detector._volume_multiplier == D("3.0")
    assert detector._window is window
    assert tuple(detector._window) == contents
    assert detector._window_start_snapshot is start_snapshot
