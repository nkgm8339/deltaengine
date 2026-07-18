"""OI polling loop — REST で Open Interest を取得し broker.on_oi を呼ぶ。"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from src.acquisition.binance_rest import fetch_open_interest

logger = logging.getLogger("webapp.oi_poller")


async def oi_polling_loop(broker, symbol: str, interval_sec: int = 15) -> None:
    """interval_sec ごとに OI を取得して broker.on_oi を呼ぶ。失敗は warning ログ＋継続。"""
    prev: Optional[Decimal] = None
    while True:
        try:
            oi_data = await fetch_open_interest(symbol)
            oi = Decimal(str(oi_data["openInterest"]))
            event_time = datetime.now(timezone.utc)
            await broker.on_oi(event_time, oi, prev)
            prev = oi
        except Exception as exc:
            logger.warning("oi_polling_loop fetch failed: %s", exc)
        await asyncio.sleep(interval_sec)
