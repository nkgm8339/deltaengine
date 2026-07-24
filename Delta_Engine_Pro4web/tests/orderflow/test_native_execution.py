from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.orderflow.cvd import Trade
from src.orderflow.native_execution import NativeExecutionAggregator


UTC = timezone.utc


def trade(minute: int, trade_id: int, price: str, side: str = "BUY") -> Trade:
    return Trade(
        trade_id=trade_id,
        event_time=datetime(2026, 1, 1, 0, minute, tzinfo=UTC),
        symbol="BTCUSDT",
        price=Decimal(price),
        quantity=Decimal("1"),
        side=side,
    )


def test_native_5m_and_10m_bars_close_from_raw_trade_boundaries() -> None:
    agg = NativeExecutionAggregator("BTCUSDT")

    assert agg.process(trade(0, 1, "100")).closed == {}
    assert agg.process(trade(4, 2, "104")).closed == {}
    closed_at_5m = agg.process(trade(5, 3, "105")).closed
    assert set(closed_at_5m) == {"5m"}
    assert closed_at_5m["5m"].bar_time == datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    assert closed_at_5m["5m"].open == Decimal("100")
    assert closed_at_5m["5m"].close == Decimal("104")
    assert closed_at_5m["5m"].timeframe == "5m"

    closed_at_10m = agg.process(trade(10, 4, "110")).closed
    assert set(closed_at_10m) == {"5m", "10m"}
    assert closed_at_10m["5m"].bar_time == datetime(2026, 1, 1, 0, 5, tzinfo=UTC)
    assert closed_at_10m["10m"].bar_time == datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    assert closed_at_10m["10m"].close == Decimal("105")


def test_native_profiles_keep_independent_cvd_and_forming_snapshots() -> None:
    agg = NativeExecutionAggregator("BTCUSDT")
    agg.process(trade(0, 1, "100", "BUY"))
    agg.process(trade(1, 2, "101", "SELL"))
    snapshots = agg.snapshots()

    assert set(snapshots) == {"5m", "10m"}
    assert snapshots["5m"].timeframe == "5m"
    assert snapshots["10m"].timeframe == "10m"
    assert snapshots["5m"].delta == Decimal("0")
    assert snapshots["10m"].delta == Decimal("0")
    assert agg.snapshots() == snapshots


def test_native_finalize_closes_started_profiles_once() -> None:
    agg = NativeExecutionAggregator("BTCUSDT")
    agg.process(trade(0, 1, "100"))
    finalized = agg.finalize()
    assert set(finalized) == {"5m", "10m"}
    assert agg.finalize() == {}


def test_native_aggregator_rejects_non_execution_timeframe() -> None:
    with pytest.raises(ValueError, match="unsupported native execution"):
        NativeExecutionAggregator("BTCUSDT", ("1m",))