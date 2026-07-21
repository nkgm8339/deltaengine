from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.orderflow.flow_price_response import (
    FlowPriceResponseDetector,
    FlowResponseOutcomeTracker,
    FlowResponseState,
)
from src.database.schema import flow_response_event_to_row, flow_response_outcome_to_row


UTC = timezone.utc
BASE = datetime(2026, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class Trade:
    event_time: datetime
    symbol: str
    price: Decimal
    quantity: Decimal
    side: str


def trade(second: int, price: str, quantity: str, side: str) -> Trade:
    return Trade(BASE + timedelta(seconds=second), "BTCUSDT", Decimal(price), Decimal(quantity), side)


def detector(**overrides) -> FlowPriceResponseDetector:
    params = dict(
        windows_sec=(5,), baseline_window_sec=5,
        pressure_threshold=Decimal("0.20"), persistence_threshold=Decimal("0.60"),
        stall_bps=Decimal("1"), effective_bps=Decimal("2"), opposite_bps=Decimal("1"),
        min_trades=5,
    )
    params.update(overrides)
    return FlowPriceResponseDetector(**params)


def run(det: FlowPriceResponseDetector, prices: list[str], side: str):
    for second, price in enumerate(prices):
        det.process(trade(second, price, "1", side))
    snapshots = det.finalize()
    assert len(snapshots) == 1
    return snapshots[0]


def test_buy_pressure_effective_when_price_advances() -> None:
    snapshot = run(detector(), ["100", "100.01", "100.02", "100.03", "100.04"], "BUY")
    assert snapshot.state is FlowResponseState.BUY_EFFECTIVE
    assert snapshot.pressure_ratio == Decimal("1")
    assert snapshot.persistence == Decimal("1")
    assert snapshot.price_change_bps == Decimal("4")


def test_buy_pressure_stalled_when_price_does_not_advance() -> None:
    snapshot = run(detector(), ["100", "100", "100", "100", "100"], "BUY")
    assert snapshot.state is FlowResponseState.BUY_STALLED
    assert snapshot.price_change_bps == Decimal("0")


def test_buy_pressure_trapped_when_price_moves_against_buys() -> None:
    snapshot = run(detector(), ["100", "99.99", "99.98", "99.97", "99.96"], "BUY")
    assert snapshot.state is FlowResponseState.BUY_TRAPPED


def test_sell_pressure_states_are_symmetric() -> None:
    effective = run(detector(), ["100", "99.99", "99.98", "99.97", "99.96"], "SELL")
    stalled = run(detector(), ["100", "100", "100", "100", "100"], "SELL")
    trapped = run(detector(), ["100", "100.01", "100.02", "100.03", "100.04"], "SELL")
    assert effective.state is FlowResponseState.SELL_EFFECTIVE
    assert stalled.state is FlowResponseState.SELL_STALLED
    assert trapped.state is FlowResponseState.SELL_TRAPPED


def test_mixed_pressure_is_unclear() -> None:
    det = detector()
    for second, side in enumerate(["BUY", "SELL", "BUY", "SELL", "BUY"]):
        det.process(trade(second, "100", "1", side))
    assert det.finalize()[0].state is FlowResponseState.UNCLEAR


def test_no_snapshot_before_full_window() -> None:
    det = detector()
    for second in range(4):
        assert det.process(trade(second, "100", "1", "BUY")) == ()
    assert det.finalize() == ()


def test_relative_volume_uses_long_baseline_rate() -> None:
    det = detector(windows_sec=(4, 10), baseline_window_sec=10, min_trades=1)
    for second in range(10):
        qty = "4" if second >= 6 else "1"
        det.process(trade(second, "100", qty, "BUY"))
    snapshots = {s.window_sec: s for s in det.finalize()}
    assert snapshots[10].relative_volume == Decimal("1")
    assert snapshots[4].relative_volume is not None
    assert snapshots[4].relative_volume > Decimal("1")


def test_out_of_order_trade_is_rejected_without_corrupting_window() -> None:
    det = detector(min_trades=1)
    det.process(trade(1, "100", "1", "BUY"))
    assert det.process(trade(0, "99", "1", "SELL")) == ()
    assert det.rejected_out_of_order == 1


def test_invalid_trade_is_rejected_without_corrupting_window() -> None:
    det = detector(min_trades=1)
    det.process(trade(0, "100", "1", "BUY"))
    det.process(trade(1, "100", "1", "BUY"))
    assert det.process(trade(2, "0", "0", "BUY")) == ()
    for second in range(2, 5):
        det.process(trade(second, "100", "1", "BUY"))

    snapshot = det.finalize()[0]
    assert snapshot.state is FlowResponseState.BUY_STALLED
    assert snapshot.first_price == Decimal("100")
    assert snapshot.last_price == Decimal("100")
    assert det.rejected_invalid_trade == 1


def test_outcome_tracker_records_raw_forward_returns_and_excursions() -> None:
    det = detector(min_trades=1)
    snapshot = run(det, ["100", "100", "100", "100", "100"], "BUY")
    tracker = FlowResponseOutcomeTracker((2, 4))
    assert tracker.register((snapshot,)) == (snapshot,)
    assert tracker.register((snapshot,)) == ()

    assert tracker.observe_trade(trade(5, "101", "1", "BUY")) == ()
    first = tracker.observe_trade(trade(6, "99", "1", "SELL"))
    assert len(first) == 1 and first[0].horizon_sec == 2
    assert first[0].forward_return_bps == Decimal("-100")
    assert first[0].max_up_bps == Decimal("100")
    assert first[0].max_down_bps == Decimal("-100")

    second = tracker.observe_trade(trade(8, "102", "1", "BUY"))
    assert len(second) == 1 and second[0].horizon_sec == 4
    assert second[0].forward_return_bps == Decimal("200")
    assert tracker.pending_count == 0


def test_outcome_tracker_ignores_zero_trade_and_keeps_pending_outcome() -> None:
    snapshot = run(detector(min_trades=1), ["100"] * 5, "BUY")
    tracker = FlowResponseOutcomeTracker((2,))
    assert tracker.register((snapshot,)) == (snapshot,)

    assert tracker.observe_trade(trade(6, "0", "0", "SELL")) == ()
    assert tracker.pending_count == 1
    assert tracker.rejected_invalid_trade == 1

    outcome = tracker.observe_trade(trade(7, "99", "1", "SELL"))[0]
    assert outcome.forward_return_bps == Decimal("-100")
    assert outcome.max_down_bps == Decimal("-100")
    assert tracker.pending_count == 0


def test_outcome_tracker_rejects_zero_base_snapshot() -> None:
    snapshot = run(detector(min_trades=1), ["100"] * 5, "BUY")
    invalid = replace(snapshot, last_price=Decimal("0"))
    tracker = FlowResponseOutcomeTracker((1,))

    assert tracker.register((invalid,)) == ()
    assert tracker.pending_count == 0
    assert tracker.rejected_invalid_snapshot == 1


def test_storage_rows_quantize_repeating_derived_decimals() -> None:
    det = detector(min_trades=1)
    for second, side in enumerate(["BUY", "BUY", "SELL", "BUY", "BUY"]):
        det.process(trade(second, "3", "1", side))
    snapshot = det.finalize()[0]
    event_row = flow_response_event_to_row(snapshot)
    assert event_row["pressure_ratio"].as_tuple().exponent == -8
    assert event_row["persistence"].as_tuple().exponent == -8

    tracker = FlowResponseOutcomeTracker((1,))
    tracker.register((snapshot,))
    outcome = tracker.observe_trade(trade(5, "2", "1", "SELL"))[0]
    outcome_row = flow_response_outcome_to_row(outcome)
    assert outcome_row["forward_return_bps"].as_tuple().exponent == -8


@pytest.mark.parametrize("bad", [(), (0,), (-1,), (True,)])
def test_invalid_windows_rejected(bad) -> None:
    with pytest.raises(ValueError):
        FlowPriceResponseDetector(windows_sec=bad)
