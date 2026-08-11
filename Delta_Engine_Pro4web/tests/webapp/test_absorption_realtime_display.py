from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from src.pipeline import _observe_absorption_state
from webapp.push_broker import PushBroker


ROOT = Path(__file__).parents[2]


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def _result(
    classification: str = "BUY_ABSORPTION",
    *,
    strength: str = "0.82",
    price_low: str = "118245.1",
    price_high: str = "118245.1",
) -> SimpleNamespace:
    return SimpleNamespace(
        classification=classification,
        strength=Decimal(strength),
        price_low=Decimal(price_low),
        price_high=Decimal(price_high),
    )


def _websocket_collector() -> tuple[MagicMock, list[dict]]:
    websocket = MagicMock()
    sent: list[dict] = []

    async def send_text(text: str) -> None:
        sent.append(json.loads(text))

    websocket.send_text = AsyncMock(side_effect=send_text)
    return websocket, sent


def test_broker_broadcasts_active_and_clear_and_caches_latest_state() -> None:
    async def run() -> None:
        broker = PushBroker("BTCUSDT")
        first_ws, first_sent = _websocket_collector()
        await broker.register(first_ws)

        observed_at = _utc("2026-07-31T02:23:10.123000")
        await broker.on_absorption_state(
            observed_at,
            _result(),
            window_sec=10,
        )
        await broker.wait_until_idle(first_ws)
        assert first_sent[-1]["type"] == "ABSORPTION_STATE"
        assert first_sent[-1]["payload"] == {
            "active": True,
            "classification": "BUY_ABSORPTION",
            "strength": "0.82",
            "price_low": "118245.1",
            "price_high": "118245.1",
            "observed_at": "2026-07-31T02:23:10.123000+00:00",
            "expires_at": "2026-07-31T02:23:20.123000+00:00",
            "window_sec": 10,
        }

        late_ws, late_sent = _websocket_collector()
        await broker.register(late_ws)
        assert late_sent == [first_sent[-1]]

        clear_time = _utc("2026-07-31T02:23:11")
        await broker.on_absorption_state(clear_time, None, window_sec=10)
        await broker.wait_until_idle()
        assert first_sent[-1]["payload"]["active"] is False
        assert first_sent[-1]["payload"]["classification"] is None
        assert first_sent[-1]["payload"]["expires_at"] is None
        assert late_sent[-1] == first_sent[-1]

        after_clear_ws, after_clear_sent = _websocket_collector()
        await broker.register(after_clear_ws)
        assert after_clear_sent == [first_sent[-1]]

    asyncio.run(run())


def test_tick_time_bridge_emits_detection_updates_and_one_clear_only() -> None:
    active = _result()

    class FakeDetector:
        def __init__(self) -> None:
            self.events_detected = 0
            self._current = None
            self._next = [
                (active, True),
                (active, True),
                (None, False),
                (None, False),
            ]

        def current(self):
            return self._current

        def observe_trade(self, _trade) -> None:
            self._current, detected = self._next.pop(0)
            if detected:
                self.events_detected += 1

    detector = FakeDetector()
    received = []
    trade = SimpleNamespace(event_time=_utc("2026-07-31T02:23:10"))

    for _ in range(4):
        _observe_absorption_state(
            detector,
            trade,
            lambda event_time, result: received.append((event_time, result)),
        )

    assert received == [
        (trade.event_time, active),
        (trade.event_time, active),
        (trade.event_time, None),
    ]


def test_webapp_wires_realtime_state_without_removing_analysis_fallback() -> None:
    main_source = (ROOT / "webapp" / "main.py").read_text(encoding="utf-8")
    html = (ROOT / "webapp" / "static" / "index.html").read_text(encoding="utf-8")

    assert "pipeline.on_absorption_state = on_absorption_state_cb" in main_source
    assert "broker.on_absorption_state(" in main_source
    assert 'case "ABSORPTION_STATE": onAbsorptionState(m,p); break;' in html
    assert "if(!ABS_REALTIME_SEEN){" in html
    assert "ABS=a.absorption||null;" in html
    assert "if(!on)resetAbsorptionRealtimeState();" in html
    assert "S.marketTime<ABS_EXPIRES_AT" in html
