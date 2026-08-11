from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.orderflow.big_trades.aggregation import ExecutionClusterAggregator, create_big_trade_event
from src.orderflow.big_trades.constants import ClusterCloseReason, MarkerPriceMode, SideFilter
from src.orderflow.big_trades.filtering import ManualSizeFilter, decide_cluster
from tests.orderflow._big_trades_helpers import fill, settings


def test_fixed_vector_chains_from_previous_fill_and_builds_event() -> None:
    configured = settings(minimum="50")
    aggregator = ExecutionClusterAggregator()
    assert aggregator.process(fill(0, "100", "18", "BUY", trade_id=1), configured) == ()
    assert aggregator.process(fill(25, "101", "17", "BUY", trade_id=2), configured) == ()
    assert aggregator.process(fill(60, "102", "20", "BUY", trade_id=3), configured) == ()
    closed = aggregator.process(fill(70, "101", "5", "SELL", trade_id=4), configured)
    assert len(closed) == 1
    cluster = closed[0]
    assert cluster.aggregate_quantity == Decimal("55")
    assert cluster.aggregate_notional == Decimal("5557")
    assert cluster.vwap == Decimal("5557") / Decimal("55")
    assert cluster.fill_count == 3
    assert cluster.duration_ms == 60
    assert cluster.low_price == Decimal("100")
    assert cluster.high_price == Decimal("102")
    assert cluster.close_reason is ClusterCloseReason.SIDE_CHANGED
    decision = ManualSizeFilter(Decimal("50")).decide(cluster.aggregate_quantity)
    event = create_big_trade_event(cluster, decision)
    assert event.aggregate_quantity == Decimal("55")
    assert event.marker_price == Decimal("102")
    assert event.event_id.startswith("bt2_")


def test_41ms_gap_closes_cluster() -> None:
    configured = settings()
    aggregator = ExecutionClusterAggregator()
    aggregator.process(fill(0, trade_id=1), configured)
    closed = aggregator.process(fill(41, trade_id=2), configured)
    assert closed[0].close_reason is ClusterCloseReason.TIME_GAP_EXCEEDED
    assert closed[0].fill_count == 1


def test_exact_40ms_gap_joins_cluster() -> None:
    configured = settings()
    aggregator = ExecutionClusterAggregator()
    aggregator.process(fill(0, trade_id=1), configured)
    assert aggregator.process(fill(40, trade_id=2), configured) == ()
    assert aggregator.flush()[0].fill_count == 2


def test_same_side_same_millisecond_joins_cluster() -> None:
    configured = settings()
    aggregator = ExecutionClusterAggregator()
    aggregator.process(fill(0, trade_id=1), configured)
    assert aggregator.process(fill(0, trade_id=2), configured) == ()
    assert [item.trade_id for item in aggregator.flush()[0].fills] == [1, 2]


def test_settings_change_does_not_force_split_and_next_natural_cluster_uses_new_snapshot() -> None:
    aggregator = ExecutionClusterAggregator()
    first = settings(settings_id="one")
    second = settings(settings_id="two")
    aggregator.process(fill(0, trade_id=1), first)
    assert aggregator.process(fill(1, trade_id=2), second) == ()
    closed = aggregator.process(fill(2, side="SELL", trade_id=3), second)
    assert closed[0].settings.settings_id == "one"
    assert closed[0].close_reason is ClusterCloseReason.SIDE_CHANGED
    assert closed[0].fill_count == 2
    assert aggregator.flush()[0].settings.settings_id == "two"


def test_max_fill_limit_flushes_without_losing_trigger_trade() -> None:
    configured = settings()
    aggregator = ExecutionClusterAggregator(max_fills_per_cluster=2)
    aggregator.process(fill(0, trade_id=1), configured)
    aggregator.process(fill(1, trade_id=2), configured)
    closed = aggregator.process(fill(2, trade_id=3), configured)
    assert closed[0].fill_count == 2
    assert closed[0].close_reason is ClusterCloseReason.MAX_FILLS_EXCEEDED
    assert aggregator.flush()[0].first_trade_id == 3
    decision = ManualSizeFilter(Decimal("0")).decide(closed[0].aggregate_quantity)
    with pytest.raises(ValueError, match="invalid max-fills"):
        create_big_trade_event(closed[0], decision)


def test_utc_minute_boundary_closes_even_within_40ms() -> None:
    configured = settings()
    base = datetime(2026, 1, 1, 0, 0, 59, 990000, tzinfo=timezone.utc)
    aggregator = ExecutionClusterAggregator()
    aggregator.process(fill(0, trade_id=1, base=base), configured)
    closed = aggregator.process(fill(20, trade_id=2, base=base), configured)
    assert closed[0].close_reason is ClusterCloseReason.CANDLE_CHANGED


def test_marker_price_modes() -> None:
    for mode, expected in (
        (MarkerPriceMode.START_PRICE, Decimal("100")),
        (MarkerPriceMode.LAST_PRICE, Decimal("102")),
        (MarkerPriceMode.VWAP_PRICE, Decimal("101")),
    ):
        configured = settings(minimum="1", marker_price_mode=mode)
        aggregator = ExecutionClusterAggregator()
        aggregator.process(fill(0, "100", "1", trade_id=1), configured)
        aggregator.process(fill(10, "102", "1", trade_id=2), configured)
        cluster = aggregator.flush()[0]
        event = create_big_trade_event(cluster, ManualSizeFilter(Decimal("1")).decide(Decimal("2")))
        assert event.marker_price == expected


def test_zero_35_70ms_is_one_chain_and_price_does_not_split() -> None:
    configured = settings()
    aggregator = ExecutionClusterAggregator()
    aggregator.process(fill(0, "100", trade_id=1), configured)
    aggregator.process(fill(35, "500", trade_id=2), configured)
    aggregator.process(fill(70, "50", trade_id=3), configured)
    cluster = aggregator.flush()[0]
    assert cluster.fill_count == 3
    assert cluster.price_level_count == 3
    assert cluster.low_price == Decimal("50")
    assert cluster.high_price == Decimal("500")


def test_disconnect_closes_cluster_explicitly_and_prevents_rejoin() -> None:
    configured = settings()
    aggregator = ExecutionClusterAggregator()
    aggregator.process(fill(0, trade_id=1), configured)
    assert aggregator.disconnect()[0].close_reason is ClusterCloseReason.STREAM_DISCONNECTED
    aggregator.process(fill(1, trade_id=2), configured)
    assert aggregator.flush()[0].first_trade_id == 2


def test_session_boundary_closes_cluster() -> None:
    configured = settings()
    first_base = datetime(2026, 1, 1, 23, 59, 59, 999000, tzinfo=timezone.utc)
    aggregator = ExecutionClusterAggregator()
    aggregator.process(fill(0, trade_id=1, base=first_base), configured)
    closed = aggregator.process(fill(1, trade_id=2, base=first_base), configured)
    assert closed[0].close_reason is ClusterCloseReason.SESSION_CHANGED


def test_trade_and_settings_identity_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError, match="identity"):
        ExecutionClusterAggregator().process(fill(0, symbol="ETHUSDT"), settings())


def test_side_filter_is_display_metadata_after_quantity_decision() -> None:
    configured = replace(settings(minimum="5"), side_filter=SideFilter.BUY)
    cluster = ExecutionClusterAggregator()
    cluster.process(fill(0, quantity="6", side="SELL", trade_id=1), configured)
    finalized = cluster.flush()[0]
    decision = decide_cluster(finalized)
    event = create_big_trade_event(finalized, decision)
    assert decision.accepted is True
    assert event.side == "SELL"
    assert event.side_filter is SideFilter.BUY
