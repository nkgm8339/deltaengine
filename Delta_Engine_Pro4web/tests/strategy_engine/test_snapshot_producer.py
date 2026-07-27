from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.orderflow.absorption import AbsorptionResult
from src.orderflow.cvd import CvdUpdate, Trade
from src.orderflow.flow_price_response import FlowResponseSnapshot, FlowResponseState
from src.orderflow.orderbook import (
    ApplyResult,
    BookLevel as OrderBookLevel,
    OrderBookSnapshot,
    OrderBookStateManager,
    OrderBookUpdate,
)
from src.strategy_engine.ingestion.snapshot_producer import SnapshotProducer


BASE = datetime(2026, 7, 27, tzinfo=timezone.utc)
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
BASE_NS = ((BASE - EPOCH).days * 86400 + (BASE - EPOCH).seconds) * 1_000_000_000


def _cvd(second: int, delta: str, cvd: str) -> CvdUpdate:
    return CvdUpdate(
        event_time=BASE + timedelta(seconds=second),
        symbol="BTCUSDT",
        tick_delta=Decimal(delta),
        tick_cvd=Decimal(cvd),
    )


def _flow(window_sec: int, delta: str, price_change: str = "1") -> FlowResponseSnapshot:
    price = Decimal("100")
    return FlowResponseSnapshot(
        event_time=BASE + timedelta(seconds=300),
        symbol="BTCUSDT",
        window_sec=window_sec,
        state=FlowResponseState.UNCLEAR,
        pressure_side="BUY",
        buy_volume=Decimal("3"),
        sell_volume=Decimal("2"),
        total_volume=Decimal("5"),
        delta=Decimal(delta),
        pressure_ratio=Decimal("1"),
        persistence=Decimal("1"),
        first_price=price,
        last_price=price + Decimal(price_change),
        high_price=price + Decimal(price_change),
        low_price=price,
        price_change=Decimal(price_change),
        price_change_bps=Decimal("100"),
        relative_volume=None,
        trade_count=2,
        observed_span_sec=window_sec,
    )


def _trade(second: int, price: str, trade_id: int = 1) -> Trade:
    return Trade(
        trade_id=trade_id,
        event_time=BASE + timedelta(seconds=second),
        symbol="BTCUSDT",
        price=Decimal(price),
        quantity=Decimal("1"),
        side="BUY",
    )


def _book_update(
    second: int,
    update_type: str,
    final_update_id: int,
    *,
    first_update_id: int | None = None,
    previous_final_update_id: int | None = None,
    bids: tuple[tuple[str, str], ...] = (),
    asks: tuple[tuple[str, str], ...] = (),
) -> OrderBookUpdate:
    return OrderBookUpdate(
        event_time=BASE + timedelta(seconds=second),
        symbol="BTCUSDT",
        update_type=update_type,
        first_update_id=first_update_id,
        final_update_id=final_update_id,
        previous_final_update_id=previous_final_update_id,
        bids=tuple(OrderBookLevel(Decimal(p), Decimal(q)) for p, q in bids),
        asks=tuple(OrderBookLevel(Decimal(p), Decimal(q)) for p, q in asks),
    )


def test_cvd_window_materials_are_decimal_and_fail_closed_until_complete():
    producer = SnapshotProducer("BTCUSDT")
    producer.observe_cvd(_cvd(0, "2", "2"))
    producer.observe_cvd(_cvd(5, "-3", "-1"))

    conditions = producer.to_conditions(engine_time_ns=BASE_NS + 5 * 1_000_000_000)

    assert conditions["trade_delta_5s"] == Decimal("-1")
    assert conditions["cvd_change_5s"] == Decimal("-3")
    assert conditions["cvd_slope_5s"] == Decimal("-0.6")
    assert conditions["buy_market_volume_5s"] == Decimal("2")
    assert conditions["sell_market_volume_5s"] == Decimal("3")
    assert all(isinstance(value, Decimal) for value in conditions.values())

    incomplete = SnapshotProducer("BTCUSDT")
    incomplete.observe_cvd(_cvd(4, "2", "2"))
    incomplete.observe_cvd(_cvd(5, "-3", "-1"))
    assert "cvd_change_5s" not in incomplete.to_conditions(BASE_NS + 5 * 1_000_000_000)


def test_conditions_do_not_leak_future_observations():
    producer = SnapshotProducer("BTCUSDT")
    producer.observe_cvd(_cvd(0, "1", "1"))
    producer.observe_cvd(_cvd(5, "2", "3"))
    producer.observe_flow_response(_flow(30, "7"))

    assert producer.to_conditions(0) == {}


def test_trade_price_history_emits_progress_and_excludes_future_samples():
    producer = SnapshotProducer("BTCUSDT")
    producer.observe_trade(_trade(0, "100", trade_id=1))
    producer.observe_trade(_trade(1, "99.6", trade_id=2))

    at_one_second = producer.to_conditions(
        engine_time_ns=1_000_000_000,
        source_time_ns=BASE_NS + 1_000_000_000,
        tick_size=Decimal("0.1"),
    )
    assert at_one_second["upward_progress_ticks_1s"] == Decimal("0")
    assert at_one_second["downward_progress_ticks_1s"] == Decimal("4")

    before_second_trade = producer.build_market_state(
        engine_time_ns=500_000_000,
        source_time_ns=BASE_NS + 500_000_000,
        tick_size=Decimal("0.1"),
    )
    assert [sample.value for sample in before_second_trade.price_samples] == [
        Decimal("100")
    ]
    assert "downward_progress_ticks_1s" not in producer.to_conditions(
        engine_time_ns=500_000_000,
        source_time_ns=BASE_NS + 500_000_000,
        tick_size=Decimal("0.1"),
    )

def test_flow_response_direct_delta_and_absorption_mapping_are_fail_closed():
    producer = SnapshotProducer("BTCUSDT")
    producer.observe_flow_response(_flow(30, "7"))
    producer.observe_flow_response(_flow(300, "9"))
    producer.observe_absorption(
        AbsorptionResult(
            classification="BUY_ABSORPTION",
            strength=Decimal("0.8"),
            price_low=Decimal("99"),
            price_high=Decimal("100"),
        )
    )
    conditions = producer.to_conditions(BASE_NS + 300 * 1_000_000_000)

    assert conditions["trade_delta_30s"] == Decimal("7")
    assert conditions["trade_delta_5m"] == Decimal("9")
    assert conditions["bid_absorption_like_active"] == Decimal("1")
    assert "ask_absorption_like_active" not in conditions

    producer.observe_absorption(None)
    cleared = producer.to_conditions(BASE_NS + 300 * 1_000_000_000)
    assert "bid_absorption_like_active" not in cleared
    assert "ask_absorption_like_active" not in cleared


def test_book_public_snapshot_is_converted_without_detector_changes():
    producer = SnapshotProducer("BTCUSDT")
    producer.observe_book(
        OrderBookSnapshot(
            symbol="BTCUSDT",
            last_update_id=10,
            bids={Decimal("99.9"): Decimal("2"), Decimal("99.8"): Decimal("1")},
            asks={Decimal("100.1"): Decimal("1"), Decimal("100.2"): Decimal("3")},
        ),
        approved_tick_size=Decimal("0.1"),
    )

    conditions = producer.to_conditions(0)

    assert conditions["bid_wall_concentration_top10"] == Decimal("2") / Decimal("3")
    assert conditions["ask_wall_concentration_top10"] == Decimal("3") / Decimal("4")
    assert conditions["distance_to_nearest_bid_wall"] == Decimal("0")
    assert conditions["distance_to_nearest_ask_wall"] == Decimal("1")


def test_book_event_windows_are_derived_from_applied_diffs():
    producer = SnapshotProducer("BTCUSDT")
    manager = OrderBookStateManager("BTCUSDT")
    initial = _book_update(
        0,
        "SNAPSHOT",
        10,
        bids=(("100", "10"),),
        asks=(("100.1", "10"),),
    )
    initial_result = manager.apply(initial)
    producer.observe_book_update(
        initial,
        initial_result,
        manager.snapshot(),
        approved_tick_size=Decimal("0.1"),
    )

    diff = _book_update(
        1,
        "DIFF",
        11,
        first_update_id=11,
        previous_final_update_id=10,
        bids=(("100", "15"), ("99.9", "2")),
        asks=(("100.1", "4"),),
    )
    diff_result = manager.apply(diff)
    producer.observe_book_update(
        diff,
        diff_result,
        manager.snapshot(),
        approved_tick_size=Decimal("0.1"),
    )

    conditions = producer.to_conditions(
        engine_time_ns=1_000_000_000,
        source_time_ns=BASE_NS + 1_000_000_000,
        tick_size=Decimal("0.1"),
    )
    assert conditions["bid_add_volume_1s"] == Decimal("7")
    assert conditions["bid_cancel_volume_1s"] == Decimal("0")
    assert conditions["bid_net_flow_1s"] == Decimal("7")
    assert conditions["bid_refresh_count_1s"] == Decimal("2")
    assert conditions["bid_stack_ratio_1s"] == Decimal("1")
    assert conditions["bid_depth_change_1s"] == Decimal("7")
    assert conditions["ask_add_volume_1s"] == Decimal("0")
    assert conditions["ask_cancel_volume_1s"] == Decimal("6")
    assert conditions["ask_pull_ratio_1s"] == Decimal("1")
    assert conditions["ask_depth_change_1s"] == Decimal("-6")
    assert "bid_add_volume_5s" not in conditions


def test_book_gap_clears_history_until_new_window_completes():
    producer = SnapshotProducer("BTCUSDT")
    producer.observe_book_update(
        _book_update(0, "SNAPSHOT", 10),
        ApplyResult(applied=True, reinitialized=False, gap_detected=False),
        OrderBookSnapshot("BTCUSDT", 10, {Decimal("100"): Decimal("1")}, {}),
        approved_tick_size=Decimal("0.1"),
    )
    producer.observe_book_update(
        _book_update(
            1,
            "DIFF",
            11,
            first_update_id=11,
            previous_final_update_id=10,
            bids=(("100", "2"),),
        ),
        ApplyResult(applied=True, reinitialized=False, gap_detected=False),
        OrderBookSnapshot("BTCUSDT", 11, {Decimal("100"): Decimal("2")}, {}),
        approved_tick_size=Decimal("0.1"),
    )
    producer.observe_book_update(
        _book_update(
            2,
            "DIFF",
            20,
            first_update_id=20,
            previous_final_update_id=99,
        ),
        ApplyResult(applied=False, reinitialized=False, gap_detected=True),
        None,
        approved_tick_size=Decimal("0.1"),
    )

    conditions = producer.to_conditions(
        engine_time_ns=2_000_000_000,
        source_time_ns=BASE_NS + 2_000_000_000,
        tick_size=Decimal("0.1"),
    )
    assert not any("_add_volume_" in key for key in conditions)
    assert not any("_depth_change_" in key for key in conditions)


def test_book_snapshot_does_not_leak_future_levels():
    producer = SnapshotProducer("BTCUSDT")
    producer.observe_book_update(
        _book_update(0, "SNAPSHOT", 10),
        ApplyResult(applied=True, reinitialized=False, gap_detected=False),
        OrderBookSnapshot("BTCUSDT", 10, {Decimal("100"): Decimal("1")}, {}),
        approved_tick_size=Decimal("0.1"),
    )
    producer.observe_book_update(
        _book_update(
            1,
            "DIFF",
            11,
            first_update_id=11,
            previous_final_update_id=10,
            bids=(("100", "9"),),
        ),
        ApplyResult(applied=True, reinitialized=False, gap_detected=False),
        OrderBookSnapshot("BTCUSDT", 11, {Decimal("100"): Decimal("9")}, {}),
        approved_tick_size=Decimal("0.1"),
    )

    before_diff = producer.build_market_state(
        engine_time_ns=500_000_000,
        source_time_ns=BASE_NS + 500_000_000,
        tick_size=Decimal("0.1"),
    )
    assert before_diff.bid_levels[0].quantity == Decimal("1")


def test_unknown_or_mismatched_observations_do_not_create_flags():
    producer = SnapshotProducer("BTCUSDT")
    producer.observe_absorption(
        AbsorptionResult(
            classification="UNKNOWN",
            strength=Decimal("1"),
            price_low=Decimal("99"),
            price_high=Decimal("100"),
        )
    )
    assert producer.to_conditions(0) == {}

    with pytest.raises(ValueError):
        producer.observe_cvd(
            CvdUpdate(
                event_time=BASE,
                symbol="ETHUSDT",
                tick_delta=Decimal("1"),
                tick_cvd=Decimal("1"),
            )
        )
