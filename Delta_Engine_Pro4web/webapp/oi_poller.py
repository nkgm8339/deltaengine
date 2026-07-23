"""OI polling loop — REST で Open Interest を取得し broker.on_oi を呼ぶ。"""
from __future__ import annotations

import asyncio
import inspect
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable, Optional

from src.acquisition.binance_rest import fetch_open_interest

logger = logging.getLogger("webapp.oi_poller")
OI_SOURCE = "BINANCE_USDM"


def normalize_oi_sample(
    raw: dict,
    expected_symbol: str,
    received_time: datetime,
) -> dict:
    """Validate one official Binance OI response without fabricating fields."""
    symbol = str(raw.get("symbol", "")).upper()
    if symbol != expected_symbol.upper():
        raise ValueError(
            f"OI symbol mismatch: expected {expected_symbol}, got {symbol or 'missing'}"
        )
    value = Decimal(str(raw["openInterest"]))
    if not value.is_finite() or value <= 0:
        raise ValueError("openInterest must be finite and positive")
    time_ms = int(raw["time"])
    if time_ms <= 0:
        raise ValueError("OI source time must be positive")
    seconds, millis = divmod(time_ms, 1000)
    source_time = (
        datetime.fromtimestamp(seconds, tz=timezone.utc)
        + timedelta(milliseconds=millis)
    )
    if received_time.tzinfo is None:
        received_time = received_time.replace(tzinfo=timezone.utc)
    return {
        "source_time": source_time,
        "received_time": received_time.astimezone(timezone.utc),
        "symbol": symbol,
        "open_interest": value,
        "source": OI_SOURCE,
    }


async def oi_polling_loop(
    broker,
    symbol: str,
    interval_sec: int = 15,
    on_sample: Optional[Callable[[dict], object]] = None,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> None:
    """Poll official OI, persist the raw observation, then broadcast it."""
    prev: Optional[Decimal] = None
    while True:
        try:
            oi_data = await fetch_open_interest(symbol)
            sample = normalize_oi_sample(oi_data, symbol, clock())
            if on_sample is not None:
                try:
                    stored = on_sample(sample)
                    if inspect.isawaitable(stored):
                        await stored
                except Exception:
                    logger.exception("OI sample persistence failed")
            await broker.on_oi(
                sample["source_time"],
                sample["open_interest"],
                prev,
                received_time=sample["received_time"],
                source=sample["source"],
                poll_interval_sec=interval_sec,
            )
            prev = sample["open_interest"]
        except Exception as exc:
            logger.warning("oi_polling_loop fetch failed: %s", exc)
        await asyncio.sleep(interval_sec)
