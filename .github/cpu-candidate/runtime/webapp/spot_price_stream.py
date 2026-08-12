"""Independent Binance Spot last-trade reference stream for the WebApp."""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

import websockets

logger = logging.getLogger("webapp.spot_price_stream")

DEFAULT_SPOT_STREAM_URL = "wss://stream.binance.com:9443/ws/{symbol}@trade"
SPOT_SOURCE = "BINANCE_SPOT"


@dataclass(frozen=True, slots=True)
class SpotTrade:
    source_time: datetime
    received_time: datetime
    symbol: str
    trade_id: int
    price: Decimal
    quantity: Decimal


def _utc_from_millis(value: Any) -> datetime:
    millis = int(value)
    if millis <= 0:
        raise ValueError("spot trade time must be positive")
    seconds, remainder = divmod(millis, 1000)
    return datetime.fromtimestamp(seconds, tz=timezone.utc) + timedelta(
        milliseconds=remainder
    )


def _positive_decimal(value: Any, field: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"spot {field} must be decimal") from exc
    if not number.is_finite() or number <= 0:
        raise ValueError(f"spot {field} must be finite and positive")
    return number


def normalize_spot_trade(
    raw: dict,
    expected_symbol: str,
    received_time: datetime,
) -> SpotTrade:
    """Validate one official ``<symbol>@trade`` payload."""
    if not isinstance(raw, dict) or raw.get("e") != "trade":
        raise ValueError("spot payload must be a trade event")
    symbol = str(raw.get("s", "")).upper()
    if symbol != expected_symbol.upper():
        raise ValueError(
            f"spot symbol mismatch: expected {expected_symbol}, got {symbol or 'missing'}"
        )
    trade_id = int(raw["t"])
    if trade_id < 0:
        raise ValueError("spot trade_id must be non-negative")
    if received_time.tzinfo is None:
        received_time = received_time.replace(tzinfo=timezone.utc)
    return SpotTrade(
        source_time=_utc_from_millis(raw["T"]),
        received_time=received_time.astimezone(timezone.utc),
        symbol=symbol,
        trade_id=trade_id,
        price=_positive_decimal(raw["p"], "price"),
        quantity=_positive_decimal(raw["q"], "quantity"),
    )


async def spot_price_stream_loop(
    publish: Callable[[SpotTrade], Any],
    symbol: str,
    *,
    url: str | None = None,
    connect: Callable[..., Any] = websockets.connect,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    sleep: Callable[[float], Any] = asyncio.sleep,
    max_backoff_sec: float = 30.0,
) -> None:
    """Reconnect forever and publish only validated Binance Spot trades."""
    stream_url = url or DEFAULT_SPOT_STREAM_URL.format(symbol=symbol.lower())
    backoff = 1.0
    while True:
        try:
            async with connect(
                stream_url,
                ping_interval=None,
                ping_timeout=20,
                close_timeout=10,
                max_queue=1024,
            ) as websocket:
                logger.info("spot reference connected symbol=%s url=%s", symbol, stream_url)
                backoff = 1.0
                async for frame in websocket:
                    try:
                        if isinstance(frame, bytes):
                            frame = frame.decode("utf-8")
                        raw = json.loads(frame)
                        trade = normalize_spot_trade(raw, symbol, clock())
                    except (ValueError, TypeError, KeyError, UnicodeDecodeError):
                        logger.warning("invalid Binance Spot trade discarded", exc_info=True)
                        continue
                    result = publish(trade)
                    if inspect.isawaitable(result):
                        await result
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Binance Spot reference disconnected: %s", exc)
        await sleep(backoff)
        backoff = min(backoff * 2, max_backoff_sec)
