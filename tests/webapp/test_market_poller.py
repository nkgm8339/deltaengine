"""Tests for market_polling_loop."""
import asyncio
from unittest.mock import AsyncMock, patch

from webapp.broker import PushBroker


def test_market_polling_broadcasts_on_success():
    async def _run():
        broker = PushBroker()
        received = []

        async def fake_broadcast(msg):
            received.append(msg)

        broker.broadcast = fake_broadcast

        sleep_calls = []

        async def fake_sleep(t):
            sleep_calls.append(t)
            if len(sleep_calls) >= 2:
                raise asyncio.CancelledError

        mock_oi = {"openInterest": "1000.0"}
        mock_prem = {"markPrice": "50000.0", "lastFundingRate": "0.0001", "nextFundingTime": 1234567890}
        mock_tick = {"priceChangePercent": "1.5", "volume": "5000.0", "quoteVolume": "250000000.0"}

        with patch("webapp.market_poller.fetch_open_interest", new=AsyncMock(return_value=mock_oi)), \
             patch("webapp.market_poller.fetch_premium_index", new=AsyncMock(return_value=mock_prem)), \
             patch("webapp.market_poller.fetch_ticker_24hr", new=AsyncMock(return_value=mock_tick)), \
             patch("webapp.market_poller.asyncio.sleep", new=fake_sleep):
            try:
                from webapp.market_poller import market_polling_loop
                await market_polling_loop(broker, "BTCUSDT", interval_sec=10)
            except asyncio.CancelledError:
                pass

        assert len(received) >= 1
        assert received[0]["type"] == "MARKET"
        assert "open_interest" in received[0]
        assert "funding_rate" in received[0]

    asyncio.run(_run())


def test_market_polling_continues_on_fetch_error():
    async def _run():
        broker = PushBroker()
        received = []

        async def fake_broadcast(msg):
            received.append(msg)

        broker.broadcast = fake_broadcast

        sleep_calls = []

        async def fake_sleep(t):
            sleep_calls.append(t)
            if len(sleep_calls) >= 3:
                raise asyncio.CancelledError

        fetch_calls = []

        async def mock_oi_fail_first(symbol):
            fetch_calls.append(symbol)
            if len(fetch_calls) == 1:
                raise ConnectionError("fetch failed")
            return {"openInterest": "1000.0"}

        mock_prem = {"markPrice": "50000.0", "lastFundingRate": "0.0001", "nextFundingTime": 1234567890}
        mock_tick = {"priceChangePercent": "1.5", "volume": "5000.0", "quoteVolume": "250000000.0"}

        with patch("webapp.market_poller.fetch_open_interest", new=mock_oi_fail_first), \
             patch("webapp.market_poller.fetch_premium_index", new=AsyncMock(return_value=mock_prem)), \
             patch("webapp.market_poller.fetch_ticker_24hr", new=AsyncMock(return_value=mock_tick)), \
             patch("webapp.market_poller.asyncio.sleep", new=fake_sleep):
            try:
                from webapp.market_poller import market_polling_loop
                await market_polling_loop(broker, "BTCUSDT", interval_sec=10)
            except asyncio.CancelledError:
                pass

        assert len(fetch_calls) >= 2
        assert any(m.get("type") == "MARKET" for m in received)

    asyncio.run(_run())
