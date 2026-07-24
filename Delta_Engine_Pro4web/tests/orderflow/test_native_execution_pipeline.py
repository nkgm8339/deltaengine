from datetime import datetime, timezone
from decimal import Decimal

from src.orderflow.cvd import Trade
from src.orderflow.native_execution_pipeline import NativeExecutionCoordinator


class Storage:
    def __init__(self):
        self.candles, self.events, self.outcomes = [], [], []
    def add_candle(self, row): self.candles.append(row)
    def add_native_flow_event(self, row): self.events.append(row)
    def add_native_flow_outcome(self, row): self.outcomes.append(row)


def trade(i, sec, price, side):
    return Trade(i, datetime.fromtimestamp(sec, tz=timezone.utc), "BTCUSDT", Decimal(str(price)), Decimal("1"), side)


def test_coordinator_saves_native_candle_and_event_rows():
    c, s = NativeExecutionCoordinator("BTCUSDT", horizons_sec=(5,)), Storage()
    c.process(trade(1, 1, 100, "BUY"), s)
    c.process(trade(2, 299, 101, "BUY"), s)
    c.process(trade(3, 300, 101, "SELL"), s)
    c.finalize(s)
    assert any(row["timeframe"] == "5m" for row in s.candles)
    assert any(row["timeframe"] == "5m" for row in s.events)
    assert all("timeframe" in row for row in s.candles if row["timeframe"] in ("5m", "10m"))
