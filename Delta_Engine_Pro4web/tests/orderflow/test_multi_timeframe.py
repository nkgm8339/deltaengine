from datetime import datetime, timezone
from decimal import Decimal

from src.orderflow.cvd import Trade
from src.orderflow.multi_timeframe import MultiTimeframeCandleAggregator


UTC = timezone.utc


def _trade(trade_id: int, minute: int, price: str, quantity: str = "1") -> Trade:
    return Trade(
        event_time=datetime(2026, 1, 1, 0, minute, 1, tzinfo=UTC),
        symbol="BTCUSDT",
        trade_id=trade_id,
        price=Decimal(price),
        quantity=Decimal(quantity),
        side="BUY",
    )


def test_aggregates_5m_and_15m_without_cross_contamination() -> None:
    agg = MultiTimeframeCandleAggregator("BTCUSDT")

    assert agg.process(_trade(1, 0, "100")) == {}
    assert agg.process(_trade(2, 4, "105", "2")) == {}
    closed = agg.process(_trade(3, 5, "103"))

    five = closed["5m"]
    assert five.timeframe == "5m"
    assert five.open == Decimal("100")
    assert five.high == Decimal("105")
    assert five.low == Decimal("100")
    assert five.close == Decimal("105")
    assert five.volume == Decimal("3")
    assert "15m" not in closed

    snapshot = agg.snapshots()
    assert snapshot["5m"].bar_time == datetime(2026, 1, 1, 0, 5, tzinfo=UTC)
    assert snapshot["15m"].bar_time == datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
