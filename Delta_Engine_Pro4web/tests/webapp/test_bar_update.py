"""BAR_UPDATE (ライブ進行中バー配信) + HEALTH 配信のテスト."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from webapp.main import _chart_session_vwap
from webapp.push_broker import IntervalGate, LatestValuePump, PushBroker

T0 = datetime(2026, 7, 18, 12, 0, 30, tzinfo=timezone.utc)


class _FakeWs:
    def __init__(self):
        self.sent: list[str] = []

    async def send_text(self, text: str) -> None:
        self.sent.append(text)


def _candle(**over):
    base = dict(
        bar_time=datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc),
        symbol="BTCUSDT", timeframe="1m",
        open=Decimal("100"), high=Decimal("102"), low=Decimal("99"),
        close=Decimal("101"), volume=Decimal("7"),
        delta=Decimal("1.5"), cvd=Decimal("12.25"),
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_interval_gate_throttles():
    gate = IntervalGate(0.2)
    assert gate.ready(100.0) is True
    assert gate.ready(100.1) is False
    assert gate.ready(100.19) is False
    assert gate.ready(100.2) is True
    assert gate.ready(100.3) is False


def test_interval_gate_rejects_zero():
    try:
        IntervalGate(0)
    except ValueError:
        pass
    else:
        raise AssertionError("IntervalGate(0) must raise")


def test_latest_value_pump_coalesces_browser_ticks():
    async def run():
        sent = []

        async def send(value):
            sent.append(value)

        pump = LatestValuePump(send, 0.01)
        pump.publish(1)
        pump.publish(2)
        pump.publish(3)
        task = asyncio.create_task(pump.run())
        await asyncio.sleep(0.005)
        assert sent == [3]
        pump.publish(4)
        pump.publish(5)
        await asyncio.sleep(0.02)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert sent == [3, 5]
        assert pump.published == 5
        assert pump.sent == 2
        assert pump.coalesced == 3

    asyncio.run(run())


def test_bar_update_payload_shape():
    async def run():
        broker = PushBroker(symbol="BTCUSDT")
        ws = _FakeWs()
        await broker.register(ws)
        levels = [
            {"price": Decimal("101"), "bid": Decimal("1"), "ask": Decimal("4")},
            {"price": Decimal("100"), "bid": Decimal("2"), "ask": Decimal("1")},
        ]
        await broker.on_bar_update(
            _candle(),
            levels,
            source_trade_id=123,
            source_event_time=T0,
        )
        assert len(ws.sent) == 1
        msg = json.loads(ws.sent[0])
        assert msg["type"] == "BAR_UPDATE"
        p = msg["payload"]
        assert p["in_progress"] is True
        assert p["source_trade_id"] == 123
        assert p["source_event_time"] == T0.isoformat()
        assert p["open"] == "100" and p["close"] == "101"
        assert p["delta"] == "1.5" and p["cvd"] == "12.25"
        fp = p["footprint"]
        # 価格降順のまま (WebSocketPayload仕様 §4.3)
        assert [l["price"] for l in fp["levels"]] == ["101", "100"]
        assert fp["poc_price"] is not None
        assert "orderbook" not in p  # 軽量化: 板は CANDLE のみ

    asyncio.run(run())


def test_bar_update_empty_levels():
    async def run():
        broker = PushBroker(symbol="BTCUSDT")
        ws = _FakeWs()
        await broker.register(ws)
        await broker.on_bar_update(_candle(), [])
        p = json.loads(ws.sent[0])["payload"]
        assert p["footprint"]["levels"] == []
        assert p["footprint"]["poc_price"] is None

    asyncio.run(run())


def test_send_health_payload():
    async def run():
        broker = PushBroker(symbol="BTCUSDT")
        ws = _FakeWs()
        await broker.register(ws)
        payload = {"state": "GREEN", "checks": {"latency": {"level": "GREEN"}},
                   "anomalies_today": 0}
        await broker.send_health(T0, payload)
        msg = json.loads(ws.sent[0])
        assert msg["type"] == "HEALTH"
        assert msg["symbol"] == "BTCUSDT"
        assert msg["payload"]["state"] == "GREEN"

    asyncio.run(run())


def test_bar_update_numbers_are_strings():
    """float 混入防止: 数値は全て str(Decimal) で配信される。"""
    async def run():
        broker = PushBroker(symbol="BTCUSDT")
        ws = _FakeWs()
        await broker.register(ws)
        await broker.on_bar_update(
            _candle(),
            [{"price": Decimal("100.5"), "bid": Decimal("0.1"), "ask": Decimal("0.2")}],
        )
        p = json.loads(ws.sent[0])["payload"]
        for key in ("open", "high", "low", "close", "volume", "delta", "cvd"):
            assert isinstance(p[key], str)
        lv = p["footprint"]["levels"][0]
        assert isinstance(lv["price"], str) and isinstance(lv["bid"], str)

    asyncio.run(run())


def test_bar_update_carries_vwap_value_and_quality():
    """表示値とexact／partialの品質を同じpayloadで固定する。"""
    async def run():
        broker = PushBroker(symbol="BTCUSDT")
        ws = _FakeWs()
        await broker.register(ws)
        await broker.on_bar_update(
            _candle(),
            [],
            source_trade_id=456,
            source_event_time=T0,
            session_vwap=Decimal("100.25"),
            vwap_status="PARTIAL",
        )
        payload = json.loads(ws.sent[0])["payload"]
        assert payload["source_trade_id"] == 456
        assert payload["vwap"] == "100.25"
        assert payload["vwap_status"] == "PARTIAL"

    asyncio.run(run())


def test_candle_carries_exact_vwap_quality():
    async def run():
        broker = PushBroker(symbol="BTCUSDT")
        ws = _FakeWs()
        await broker.register(ws)
        await broker.on_candle(
            _candle(),
            [],
            None,
            session_vwap=Decimal("100.25"),
            vwap_status="EXACT",
        )
        payload = json.loads(ws.sent[0])["payload"]
        assert payload["vwap"] == "100.25"
        assert payload["vwap_status"] == "EXACT"

    asyncio.run(run())


def test_chart_session_vwap_prefers_exact_and_labels_partial_fallback():
    exact_pipeline = SimpleNamespace(
        _last_market_state=SimpleNamespace(session_vwap=Decimal("101")),
        _snapshot_producer=SimpleNamespace(
            _session_vwap=SimpleNamespace(
                current_value=Decimal("99"),
                session_complete=False,
            )
        ),
    )
    assert _chart_session_vwap(exact_pipeline) == (Decimal("101"), "EXACT")

    partial_pipeline = SimpleNamespace(
        _last_market_state=SimpleNamespace(session_vwap=None),
        _snapshot_producer=SimpleNamespace(
            _session_vwap=SimpleNamespace(
                current_value=Decimal("99"),
                session_complete=False,
            )
        ),
    )
    assert _chart_session_vwap(partial_pipeline) == (Decimal("99"), "PARTIAL")


def test_chart_session_vwap_returns_empty_pair_without_trades():
    pipeline = SimpleNamespace(
        _last_market_state=None,
        _snapshot_producer=SimpleNamespace(
            _session_vwap=SimpleNamespace(
                current_value=None,
                session_complete=False,
            )
        ),
    )
    assert _chart_session_vwap(pipeline) == (None, None)


def test_static_vwap_overlay_is_orange_dashed_and_has_no_debug_trace():
    html = (
        Path(__file__).parents[2] / "webapp" / "static" / "index.html"
    ).read_text(encoding="utf-8")

    assert 'VWAP (~ PARTIAL)' in html
    assert 'stroke="${WARN}"' in html
    assert 'stroke-dasharray="7,5"' in html
    assert "VWAP_TRACE" not in html
    assert "LAST_PRICE_RX" not in html
