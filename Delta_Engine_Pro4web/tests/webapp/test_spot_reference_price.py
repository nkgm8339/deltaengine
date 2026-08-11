from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from webapp.push_broker import PushBroker
from webapp.spot_price_stream import (
    SPOT_SOURCE,
    SpotTrade,
    normalize_spot_trade,
    spot_price_stream_loop,
)


ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "webapp" / "static" / "index.html"
MAIN = ROOT / "webapp" / "main.py"
COMPOSE = ROOT / "docker-compose.yml"


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def _raw_trade(**overrides) -> dict:
    payload = {
        "e": "trade",
        "E": 1785650400124,
        "s": "BTCUSDT",
        "t": 123456,
        "p": "63449.33",
        "q": "0.002",
        "T": 1785650400123,
        "m": False,
    }
    payload.update(overrides)
    return payload


def test_normalize_spot_trade_preserves_official_identity_and_decimal_price():
    trade = normalize_spot_trade(
        _raw_trade(),
        "BTCUSDT",
        _utc("2026-08-02T06:00:00.200000"),
    )
    assert trade.symbol == "BTCUSDT"
    assert trade.trade_id == 123456
    assert trade.price == Decimal("63449.33")
    assert trade.quantity == Decimal("0.002")
    assert trade.source_time == datetime.fromtimestamp(
        1785650400.123,
        tz=timezone.utc,
    )


@pytest.mark.parametrize(
    "payload",
    [
        _raw_trade(e="aggTrade"),
        _raw_trade(s="ETHUSDT"),
        _raw_trade(t=-1),
        _raw_trade(p="0"),
        _raw_trade(p="NaN"),
        _raw_trade(q="0"),
        _raw_trade(T=0),
    ],
)
def test_normalize_spot_trade_rejects_wrong_or_non_positive_payload(payload):
    with pytest.raises(ValueError):
        normalize_spot_trade(payload, "BTCUSDT", datetime.now(timezone.utc))


class _FakeSpotSocket:
    def __init__(self, frames: list[str]):
        self.frames = iter(frames)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self.frames)
        except StopIteration:
            raise StopAsyncIteration


def test_spot_stream_publishes_only_validated_trade_and_uses_raw_stream_url():
    async def run():
        publish = AsyncMock()
        calls = []

        def connect(url, **kwargs):
            calls.append((url, kwargs))
            return _FakeSpotSocket([
                json.dumps({"result": None, "id": 1}),
                json.dumps(_raw_trade()),
            ])

        async def stop_after_connection(_):
            raise asyncio.CancelledError

        with pytest.raises(asyncio.CancelledError):
            await spot_price_stream_loop(
                publish,
                "BTCUSDT",
                connect=connect,
                sleep=stop_after_connection,
                clock=lambda: _utc("2026-08-02T06:00:00.200000"),
            )

        publish.assert_awaited_once()
        published = publish.await_args.args[0]
        assert published.trade_id == 123456
        assert calls[0][0] == "wss://stream.binance.com:9443/ws/btcusdt@trade"
        assert calls[0][1]["ping_interval"] is None

    asyncio.run(run())


def test_push_broker_caches_latest_spot_reference_for_late_browser():
    async def run():
        broker = PushBroker("BTCUSDT")
        first = SpotTrade(
            source_time=datetime.now(timezone.utc),
            received_time=datetime.now(timezone.utc),
            symbol="BTCUSDT",
            trade_id=11,
            price=Decimal("63449.30"),
            quantity=Decimal("0.1"),
        )
        second = SpotTrade(
            source_time=datetime.now(timezone.utc),
            received_time=datetime.now(timezone.utc),
            symbol="BTCUSDT",
            trade_id=12,
            price=Decimal("63449.33"),
            quantity=Decimal("0.2"),
        )
        await broker.on_spot_price(first)
        await broker.on_spot_price(second)

        sent = []
        websocket = MagicMock()
        websocket.send_text = AsyncMock(
            side_effect=lambda text: sent.append(json.loads(text))
        )
        await broker.register(websocket)

        assert len(sent) == 1
        message = sent[0]
        assert message["type"] == "SPOT_PRICE"
        assert message["payload"]["source"] == SPOT_SOURCE
        assert message["payload"]["spot_symbol"] == "BTCUSDT"
        assert message["payload"]["trade_id"] == 12
        assert message["payload"]["price"] == "63449.33"
        assert isinstance(message["payload"]["source_age_ms"], int)
        assert datetime.fromisoformat(message["payload"]["published_time"]).tzinfo

    asyncio.run(run())


def test_spot_reference_is_display_only_freshness_guarded_and_runtime_explicit():
    html = INDEX.read_text(encoding="utf-8")
    main = MAIN.read_text(encoding="utf-8")
    compose = COMPOSE.read_text(encoding="utf-8")

    assert 'id="spotgroup"' in html
    assert "BINANCE SPOT BTC/USDT" in html
    assert "SPOT-PERP" in html
    assert 'case "SPOT_PRICE": onSpotPrice(p); break;' in html
    assert "const SPOT_FRESHNESS=new MARKET_FRESHNESS_ID.MarketFreshnessGuard" in html
    assert "SPOT_FRESHNESS.check()" in html
    assert "spot_price_stream_loop(" in main
    assert "spot_push_pump.publish" in main
    assert 'os.getenv("BINANCE_SPOT_REFERENCE_ENABLED", "false")' in main
    assert "spot_reference_enabled and not config.replay.enabled" in main
    assert "BINANCE_SPOT_REFERENCE_ENABLED=true" in compose
    assert "pipeline.on_trade = None if config.replay.enabled else on_trade_cb" in main
