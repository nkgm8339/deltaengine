"""BAR_UPDATE (ライブ進行中バー配信) + HEALTH 配信のテスト."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from webapp.push_broker import IntervalGate, PushBroker

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
    gate = IntervalGate(1)
    assert gate.ready(100.0) is True
    assert gate.ready(100.4) is False
    assert gate.ready(100.9) is False
    assert gate.ready(101.0) is True
    assert gate.ready(101.5) is False


def test_interval_gate_rejects_zero():
    try:
        IntervalGate(0)
    except ValueError:
        pass
    else:
        raise AssertionError("IntervalGate(0) must raise")


def test_bar_update_payload_shape():
    async def run():
        broker = PushBroker(symbol="BTCUSDT")
        ws = _FakeWs()
        await broker.register(ws)
        levels = [
            {"price": Decimal("101"), "bid": Decimal("1"), "ask": Decimal("4")},
            {"price": Decimal("100"), "bid": Decimal("2"), "ask": Decimal("1")},
        ]
        await broker.on_bar_update(_candle(), levels)
        assert len(ws.sent) == 1
        msg = json.loads(ws.sent[0])
        assert msg["type"] == "BAR_UPDATE"
        p = msg["payload"]
        assert p["in_progress"] is True
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
