from datetime import datetime, timezone
from decimal import Decimal

from src.orderflow.cvd import Trade
from src.orderflow.flow_price_response import FlowResponseState
from src.orderflow.native_flow import NativeFlowDetector


def t(i, sec, price, qty, side):
    return Trade(i, datetime.fromtimestamp(sec, tz=timezone.utc), "BTCUSDT", Decimal(str(price)), Decimal(str(qty)), side)


def test_native_flow_emits_only_on_native_boundary():
    d = NativeFlowDetector("BTCUSDT", "5m")
    assert d.process(t(1, 1, 100, 2, "BUY")) == ()
    assert d.process(t(2, 299, 101, 1, "BUY")) == ()
    out = d.process(t(3, 300, 101, 1, "SELL"))
    assert len(out) == 1
    assert out[0].timeframe == "5m"
    assert out[0].state is FlowResponseState.BUY_EFFECTIVE


def test_native_flow_is_independent_by_timeframe():
    d5 = NativeFlowDetector("BTCUSDT", "5m")
    d10 = NativeFlowDetector("BTCUSDT", "10m")
    trades = [t(1, 1, 100, 2, "BUY"), t(2, 300, 101, 2, "BUY"), t(3, 600, 102, 1, "SELL")]
    out5 = [x for tr in trades for x in d5.process(tr)]
    out10 = [x for tr in trades for x in d10.process(tr)]
    assert len(out5) == 2 and all(x.timeframe == "5m" for x in out5)
    assert len(out10) == 1 and out10[0].timeframe == "10m"
    assert out5[0].trade_count == 1
    assert out10[0].trade_count == 2



def test_native_flow_events_and_outcomes_keep_timeframe_key():
    from src.orderflow.native_flow import NativeFlowOutcomeTracker
    d = NativeFlowDetector("BTCUSDT", "5m")
    tracker = NativeFlowOutcomeTracker((5,))
    d.process(t(1, 1, 100, 2, "BUY"))
    snaps = d.process(t(2, 300, 101, 1, "SELL"))
    events = tracker.register(snaps)
    assert len(events) == 1
    out = tracker.observe_trade(t(3, 306, 102, 1, "BUY"))
    assert len(out) == 1
    assert out[0].timeframe == "5m"
    assert out[0].horizon_sec == 5


def test_native_flow_row_contains_timeframe():
    from src.database.schema import native_flow_event_to_row
    d = NativeFlowDetector("BTCUSDT", "10m")
    d.process(t(1, 1, 100, 2, "BUY"))
    snap = d.finalize()[0]
    row = native_flow_event_to_row(snap)
    assert row["timeframe"] == "10m"
    assert row["state"] == snap.state.value
