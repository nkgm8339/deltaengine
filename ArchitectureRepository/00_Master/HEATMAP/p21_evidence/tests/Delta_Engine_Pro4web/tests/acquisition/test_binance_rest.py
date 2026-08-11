"""Unit tests for src.acquisition.binance_rest (3 tests, network-free).

1. rest_to_depth_event returns correct shape and is accepted by process_depth.
2. fetch_depth_snapshot raises ConnectionError on HTTP error (aiohttp mock).
3. snapshot -> diff apply order: rest_to_depth_event -> process_depth ->
   book_state.apply(SNAPSHOT) -> diff apply is accepted.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.acquisition.binance_rest import (
    fetch_depth_snapshot,
    fetch_open_interest,
    fetch_premium_index,
    fetch_ticker_24hr,
    rest_to_depth_event,
)
from src.acquisition.depth_sync import DepthSyncCoordinator
from src.normalization.normalizer import DataNormalizer, ExchangeProfile
from src.orderflow.orderbook import OrderBookStateManager

import yaml
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_binance_profile() -> ExchangeProfile:
    data = yaml.safe_load(
        (PROJECT_ROOT / "config" / "profiles" / "binance.yaml").read_text(encoding="utf-8")
    )
    return ExchangeProfile.from_dict(data)


# Minimal REST response shape from Binance Futures /fapi/v1/depth.
_REST_RESPONSE = {
    "lastUpdateId": 1234567,
    "E": 1767225600000,
    "T": 1767225600000,
    "bids": [["99999.50", "1.250"], ["99998.00", "2.100"]],
    "asks": [["100000.00", "0.800"], ["100001.00", "1.500"]],
}


# ── Test 1: rest_to_depth_event shape + process_depth acceptance ─────────────

def test_rest_to_depth_event_accepted_by_normalizer() -> None:
    """rest_to_depth_event output is accepted by DataNormalizer.process_depth."""
    profile = _load_binance_profile()
    normalizer = DataNormalizer(profile)

    evt = rest_to_depth_event(_REST_RESPONSE, "BTCUSDT")

    # Shape checks.
    assert evt["e"] == "depthSnapshot"
    assert evt["s"] == "BTCUSDT"
    assert evt["E"] == _REST_RESPONSE["E"]
    assert evt["u"] == _REST_RESPONSE["lastUpdateId"]
    assert evt["b"] == _REST_RESPONSE["bids"]
    assert evt["a"] == _REST_RESPONSE["asks"]

    # Normalizer must accept and return a SNAPSHOT-type OrderBookUpdate.
    update = normalizer.process_depth(evt)
    assert update is not None
    assert update.update_type == "SNAPSHOT"
    assert update.symbol == "BTCUSDT"
    assert update.final_update_id == 1234567
    assert update.first_update_id is None
    assert len(update.bids) == 2
    assert len(update.asks) == 2
    assert update.bids[0].price == Decimal("99999.50")
    assert update.asks[0].price == Decimal("100000.00")


# ── Test 2: fetch_depth_snapshot raises ConnectionError on HTTP error ─────────

def test_fetch_depth_snapshot_http_error_raises_connection_error() -> None:
    """HTTP non-200 response raises ConnectionError."""
    mock_response = AsyncMock()
    mock_response.status = 400
    mock_response.text = AsyncMock(return_value='{"code":-1100,"msg":"Bad request"}')
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("src.acquisition.binance_rest.aiohttp.ClientSession",
               return_value=mock_session):
        with pytest.raises(ConnectionError, match="HTTP 400"):
            asyncio.run(fetch_depth_snapshot("BTCUSDT"))


# ── Test 3: snapshot then diff apply order ────────────────────────────────────

def test_snapshot_then_diff_apply_sequence() -> None:
    """REST snapshot -> process_depth -> book_state.apply -> diff apply is accepted."""
    from datetime import datetime, timezone
    from src.orderflow.orderbook import BookLevel, OrderBookUpdate

    UTC = timezone.utc
    profile = _load_binance_profile()
    normalizer = DataNormalizer(profile)
    book_state = OrderBookStateManager("BTCUSDT")

    # Step 1: apply REST snapshot via rest_to_depth_event.
    evt = rest_to_depth_event(_REST_RESPONSE, "BTCUSDT")
    update = normalizer.process_depth(evt)
    assert update is not None
    result = book_state.apply(update)
    assert result.applied is True
    assert book_state.snapshots_applied == 1

    snap = book_state.snapshot()
    assert snap is not None
    assert snap.last_update_id == 1234567

    # Step 2: apply a DIFF that logically follows the snapshot.
    diff = OrderBookUpdate(
        event_time=datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC),
        symbol="BTCUSDT",
        update_type="DIFF",
        first_update_id=1234568,
        final_update_id=1234568,
        bids=(BookLevel(Decimal("99999.50"), Decimal("0")),),  # remove level
        asks=(),
    )
    diff_result = book_state.apply(diff)
    assert diff_result.applied is True
    assert book_state.diffs_applied == 1

    # Verify the level was removed.
    assert book_state.snapshot().bid_quantity_at(Decimal("99999.50")) == Decimal("0")


# ── Test 4: strict coordinator proof → snapshot + verified bridge apply ────────

def test_only_coordinator_verified_bridge_enters_initial_sync_apply() -> None:
    """The lenient manager branch receives only an externally verified bridge."""
    profile = _load_binance_profile()
    normalizer = DataNormalizer(profile)
    book_state = OrderBookStateManager("BTCUSDT")
    coordinator = DepthSyncCoordinator(max_buffered_diffs=8, max_attempts=2)

    bridge_raw = {
        "e": "depthUpdate",
        "E": 1767225601000,
        "s": "BTCUSDT",
        "U": 1234565,
        "u": 1234570,
        "pu": 1234564,
        "b": [["99999.50", "0"]],
        "a": [],
    }
    request = coordinator.observe_depth(bridge_raw).request
    snapshot_event = rest_to_depth_event(_REST_RESPONSE, "BTCUSDT")
    verified = coordinator.observe_snapshot(request, snapshot_event)
    assert verified.is_verified is True

    snapshot_update = normalizer.process_depth(verified.snapshot)
    bridge_update = normalizer.process_depth(verified.diffs[0])
    assert snapshot_update is not None and bridge_update is not None
    assert book_state.apply(snapshot_update).applied is True
    book_state.apply_initial_sync(snapshot_update.final_update_id)
    bridge_result = book_state.apply(bridge_update)

    assert bridge_result.applied is True
    assert book_state.diffs_applied == 1
    assert book_state.gaps_detected == 0
    assert book_state.snapshot().bid_quantity_at(Decimal("99999.50")) == Decimal("0")


# ── Test 5: fetch_open_interest ───────────────────────────────────────────────

def _mock_json_session(payload: dict):
    """Return a patched aiohttp.ClientSession that yields `payload` as JSON."""
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value=payload)
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return mock_session


def test_fetch_open_interest_returns_raw_dict() -> None:
    """fetch_open_interest returns the raw API dict without float conversion."""
    payload = {"symbol": "BTCUSDT", "openInterest": "12345.678", "time": 1767225600000}
    with patch("src.acquisition.binance_rest.aiohttp.ClientSession",
               return_value=_mock_json_session(payload)):
        data = asyncio.run(fetch_open_interest("BTCUSDT"))
    assert data == payload
    assert isinstance(data["openInterest"], str)


# ── Test 6: fetch_premium_index ───────────────────────────────────────────────

def test_fetch_premium_index_returns_raw_dict() -> None:
    """fetch_premium_index returns the raw API dict without float conversion."""
    payload = {
        "symbol": "BTCUSDT",
        "markPrice": "50000.12345678",
        "lastFundingRate": "0.00010000",
        "nextFundingTime": 1767240000000,
        "time": 1767225600000,
    }
    with patch("src.acquisition.binance_rest.aiohttp.ClientSession",
               return_value=_mock_json_session(payload)):
        data = asyncio.run(fetch_premium_index("BTCUSDT"))
    assert data == payload
    assert isinstance(data["markPrice"], str)
    assert isinstance(data["lastFundingRate"], str)


# ── Test 7: fetch_ticker_24hr ─────────────────────────────────────────────────

def test_fetch_ticker_24hr_returns_raw_dict() -> None:
    """fetch_ticker_24hr returns the raw API dict without float conversion."""
    payload = {
        "symbol": "BTCUSDT",
        "priceChange": "-500.00",
        "priceChangePercent": "-0.990",
        "weightedAvgPrice": "50250.00",
        "lastPrice": "50000.00",
        "lastQty": "0.100",
        "volume": "12345.678",
        "quoteVolume": "620000000.00",
        "openTime": 1767139200000,
        "closeTime": 1767225599999,
        "count": 98765,
    }
    with patch("src.acquisition.binance_rest.aiohttp.ClientSession",
               return_value=_mock_json_session(payload)):
        data = asyncio.run(fetch_ticker_24hr("BTCUSDT"))
    assert data == payload
    assert isinstance(data["lastPrice"], str)
    assert isinstance(data["volume"], str)


def test_rest_to_depth_event_accepts_real_binance_payload_without_timestamp() -> None:
    """A real /fapi/v1/depth response has no E/T fields but must initialize the book."""
    profile = _load_binance_profile()
    raw = {
        "lastUpdateId": 7654321,
        "bids": [["99999.50", "1.250"]],
        "asks": [["100000.00", "0.800"]],
    }
    event = rest_to_depth_event(raw, "BTCUSDT")
    assert isinstance(event["E"], int)
    update = DataNormalizer(profile).process_depth(event)
    assert update is not None
    book = OrderBookStateManager("BTCUSDT")
    assert book.apply(update).applied is True
    snapshot = book.snapshot()
    assert snapshot is not None
    assert len(snapshot.bids) == 1
    assert len(snapshot.asks) == 1
