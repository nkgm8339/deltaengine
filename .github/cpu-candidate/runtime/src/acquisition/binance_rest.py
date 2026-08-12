"""Binance Futures REST depth snapshot fetcher (LiveVerification,課題 #2).

Fetches the current order-book snapshot via GET /fapi/v1/depth and converts
the response to the shape the normalizer's process_depth() expects
(binance.yaml order_book_mapping: e="depthSnapshot", s, E, u, b, a).

This fills the gap between the WS depthUpdate stream (DIFFs) and the initial
state the OrderBookStateManager needs before DIFFs can be applied.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import aiohttp

logger = logging.getLogger("acquisition.binance_rest")

_DEFAULT_BASE_URL = "https://fapi.binance.com"
_DEPTH_PATH = "/fapi/v1/depth"
_OI_PATH = "/fapi/v1/openInterest"
_PREMIUM_PATH = "/fapi/v1/premiumIndex"
_TICKER_PATH = "/fapi/v1/ticker/24hr"
_TIMEOUT_SEC = 10.0


async def _get(path: str, params: dict, base_url: str = _DEFAULT_BASE_URL) -> dict:
    """Shared GET helper: returns raw dict; raises ConnectionError on failure."""
    url = f"{base_url}{path}"
    timeout = aiohttp.ClientTimeout(total=_TIMEOUT_SEC)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    text = await response.text()
                    raise ConnectionError(
                        f"{path} HTTP {response.status}: {text[:200]}"
                    )
                return await response.json()
    except aiohttp.ClientError as exc:
        raise ConnectionError(f"{path} request failed: {exc}") from exc
    except asyncio.TimeoutError:
        raise ConnectionError(f"{path} timeout after {_TIMEOUT_SEC}s")


async def fetch_depth_snapshot(
    symbol: str,
    limit: int = 1000,
    base_url: str = _DEFAULT_BASE_URL,
) -> dict:
    """GET /fapi/v1/depth?symbol={symbol}&limit={limit} -> raw dict.

    Raises ConnectionError on HTTP error or timeout.
    Numbers are returned as-is (strings) — the caller performs Decimal conversion.
    """
    url = f"{base_url}{_DEPTH_PATH}"
    params = {"symbol": symbol, "limit": limit}
    timeout = aiohttp.ClientTimeout(total=_TIMEOUT_SEC)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    text = await response.text()
                    raise ConnectionError(
                        f"depth snapshot HTTP {response.status}: {text[:200]}"
                    )
                data = await response.json()
                logger.info(
                    "depth snapshot fetched symbol=%s lastUpdateId=%s",
                    symbol, data.get("lastUpdateId"),
                )
                return data
    except aiohttp.ClientError as exc:
        raise ConnectionError(f"depth snapshot request failed: {exc}") from exc
    except asyncio.TimeoutError as exc:
        raise ConnectionError(f"depth snapshot timeout after {_TIMEOUT_SEC}s") from exc


async def fetch_open_interest(
    symbol: str,
    base_url: str = _DEFAULT_BASE_URL,
) -> dict:
    """GET /fapi/v1/openInterest?symbol={symbol} -> raw dict.

    Raises ConnectionError on HTTP error or timeout.
    Numbers are returned as API strings — the caller performs Decimal conversion.
    """
    data = await _get(_OI_PATH, {"symbol": symbol}, base_url)
    logger.info("open interest fetched symbol=%s", symbol)
    return data


async def fetch_premium_index(
    symbol: str,
    base_url: str = _DEFAULT_BASE_URL,
) -> dict:
    """GET /fapi/v1/premiumIndex?symbol={symbol} -> raw dict (mark price + funding rate).

    Raises ConnectionError on HTTP error or timeout.
    Numbers are returned as API strings — the caller performs Decimal conversion.
    """
    data = await _get(_PREMIUM_PATH, {"symbol": symbol}, base_url)
    logger.info("premium index fetched symbol=%s", symbol)
    return data


async def fetch_ticker_24hr(
    symbol: str,
    base_url: str = _DEFAULT_BASE_URL,
) -> dict:
    """GET /fapi/v1/ticker/24hr?symbol={symbol} -> raw dict (24-hour statistics).

    Raises ConnectionError on HTTP error or timeout.
    Numbers are returned as API strings — the caller performs Decimal conversion.
    """
    data = await _get(_TICKER_PATH, {"symbol": symbol}, base_url)
    logger.info("24hr ticker fetched symbol=%s", symbol)
    return data


def rest_to_depth_event(raw_rest: dict, symbol: str) -> dict:
    """Convert a REST /fapi/v1/depth response to normalizer depthSnapshot format.

    Binance Futures REST response shape:
        {"lastUpdateId": int, "E": epoch_ms, "T": epoch_ms,
         "bids": [[price, qty], ...], "asks": [[price, qty], ...]}

    binance.yaml order_book_mapping expects:
        e="depthSnapshot", s=symbol, E=event_time_ms, u=lastUpdateId,
        b=bids, a=asks.
    """
    # Binance Futures REST depth payloads provide lastUpdateId/bids/asks but
    # no event timestamp. Supply the local receipt time for the normalizer's
    # canonical event_time; it is metadata only and never drives book ordering.
    event_time_ms = raw_rest.get("E", raw_rest.get("T", time.time_ns() // 1_000_000))
    return {
        "e": "depthSnapshot",
        "s": symbol,
        "E": event_time_ms,
        "u": raw_rest["lastUpdateId"],
        "b": raw_rest["bids"],
        "a": raw_rest["asks"],
    }
