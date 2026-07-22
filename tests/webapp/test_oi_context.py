"""Open-interest ingestion, validation, and payload tests."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from webapp.oi_poller import normalize_oi_sample, oi_polling_loop
from webapp.push_broker import PushBroker

UTC = timezone.utc


def test_normalize_oi_sample_keeps_binance_source_time_and_decimal() -> None:
    received = datetime(2026, 7, 22, 8, 13, 30, tzinfo=UTC)
    sample = normalize_oi_sample(
        {
            "symbol": "BTCUSDT",
            "openInterest": "103518.771",
            "time": 1784708009405,
        },
        "BTCUSDT",
        received,
    )
    assert sample["source_time"] == datetime(2026, 7, 22, 8, 13, 29, 405000, tzinfo=UTC)
    assert sample["received_time"] == received
    assert sample["open_interest"] == Decimal("103518.771")
    assert sample["source"] == "BINANCE_USDM"


@pytest.mark.parametrize(
    "payload",
    [
        {"symbol": "ETHUSDT", "openInterest": "100", "time": 1784708009405},
        {"symbol": "BTCUSDT", "openInterest": "0", "time": 1784708009405},
        {"symbol": "BTCUSDT", "openInterest": "NaN", "time": 1784708009405},
        {"symbol": "BTCUSDT", "openInterest": "100", "time": 0},
    ],
)
def test_normalize_oi_sample_rejects_wrong_or_nonpositive_data(payload: dict) -> None:
    with pytest.raises((ValueError, KeyError)):
        normalize_oi_sample(payload, "BTCUSDT", datetime(2026, 7, 22, tzinfo=UTC))


def test_oi_polling_persists_and_broadcasts_official_sample() -> None:
    async def run() -> None:
        broker = MagicMock()
        broker.on_oi = AsyncMock()
        stored = []

        async def stop_after_first(_interval):
            raise asyncio.CancelledError

        response = {
            "symbol": "BTCUSDT",
            "openInterest": "103518.771",
            "time": 1784708009405,
        }
        received = datetime(2026, 7, 22, 8, 13, 30, tzinfo=UTC)
        with patch("webapp.oi_poller.fetch_open_interest", new=AsyncMock(return_value=response)), \
             patch("webapp.oi_poller.asyncio.sleep", new=stop_after_first):
            with pytest.raises(asyncio.CancelledError):
                await oi_polling_loop(
                    broker,
                    "BTCUSDT",
                    interval_sec=10,
                    on_sample=stored.append,
                    clock=lambda: received,
                )

        assert len(stored) == 1
        broker.on_oi.assert_awaited_once_with(
            datetime(2026, 7, 22, 8, 13, 29, 405000, tzinfo=UTC),
            Decimal("103518.771"),
            None,
            received_time=received,
            source="BINANCE_USDM",
            poll_interval_sec=10,
        )

    asyncio.run(run())


def test_push_broker_oi_payload_has_source_and_real_change() -> None:
    broker = PushBroker("BTCUSDT")
    sent = []
    ws = MagicMock()

    async def send_text(value):
        import json
        sent.append(json.loads(value))

    ws.send_text = AsyncMock(side_effect=send_text)
    source_time = datetime(2026, 7, 22, 8, 13, 29, tzinfo=UTC)
    received_time = datetime(2026, 7, 22, 8, 13, 30, tzinfo=UTC)

    async def run() -> None:
        await broker.register(ws)
        await broker.on_oi(
            source_time,
            Decimal("103518.771"),
            Decimal("103528.698"),
            received_time=received_time,
            source="BINANCE_USDM",
            poll_interval_sec=10,
        )

    asyncio.run(run())
    payload = sent[0]["payload"]
    assert sent[0]["time"] == "2026-07-22T08:13:29+00:00"
    assert payload["open_interest"] == "103518.771"
    assert payload["change"] == "-9.927"
    assert payload["source_time"] == "2026-07-22T08:13:29+00:00"
    assert payload["received_time"] == "2026-07-22T08:13:30+00:00"
    assert payload["source"] == "BINANCE_USDM"
