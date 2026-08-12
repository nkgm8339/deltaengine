"""OI / Funding / MarkPrice / 24h Ticker polling loop (REST)."""
from __future__ import annotations

import asyncio
import logging
from decimal import Decimal

from src.acquisition.binance_rest import (
    fetch_open_interest,
    fetch_premium_index,
    fetch_ticker_24hr,
)

logger = logging.getLogger("webapp.market_poller")


async def market_polling_loop(
    broker,
    symbol: str,
    interval_sec: int = 10,
) -> None:
    """Fetch OI+Funding+Ticker every interval_sec and broadcast MARKET message.

    Failures are logged and the loop continues — never stops on fetch error.
    float() is forbidden: all numeric values go through Decimal(str(v)).
    """
    while True:
        try:
            oi_data, premium_data, ticker_data = await asyncio.gather(
                fetch_open_interest(symbol),
                fetch_premium_index(symbol),
                fetch_ticker_24hr(symbol),
            )
            msg = {
                "type": "MARKET",
                "open_interest": str(Decimal(str(oi_data["openInterest"]))),
                "mark_price": str(Decimal(str(premium_data["markPrice"]))),
                "funding_rate": str(Decimal(str(premium_data["lastFundingRate"]))),
                "next_funding_time": int(premium_data["nextFundingTime"]),
                "price_change_pct": str(Decimal(str(ticker_data["priceChangePercent"]))),
                "volume_24h": str(Decimal(str(ticker_data["volume"]))),
                "quote_volume_24h": str(Decimal(str(ticker_data["quoteVolume"]))),
            }
            await broker.broadcast(msg)
        except Exception as exc:
            logger.warning("market_polling_loop fetch failed: %s", exc)
        await asyncio.sleep(interval_sec)
