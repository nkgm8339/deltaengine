"""Tests for the depth normalisation path added in B-1.

Covers ExchangeProfile.from_dict with order_book_mapping, normalize_raw_depth,
DataNormalizer.process_depth, and DataNormalizer.classify_raw.
All test data is fixture-driven (no network). Decimal only.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.normalization.normalizer import (
    DataNormalizer,
    ExchangeProfile,
    NormalizationError,
    ProfileError,
    normalize_raw_depth,
)
from src.orderflow.orderbook import OrderBookUpdate

# ---------------------------------------------------------------------------
# Shared profiles
# ---------------------------------------------------------------------------

BINANCE_OB_PROFILE = ExchangeProfile.from_dict({
    "profile_name": "binance",
    "field_mapping": {
        "event_time": "E", "trade_time": "T", "trade_id": "a",
        "symbol": "s", "price": "p", "quantity": "q",
        "side_field": "m", "side_rule": "m == true → SELL, m == false → BUY",
    },
    "timestamp_format": "epoch_ms",
    "order_book_mapping": {
        "event_type_field": "e",
        "event_type_snapshot": "depthSnapshot",
        "event_type_diff": "depthUpdate",
        "symbol_field": "s",
        "event_time_field": "E",
        "first_update_id_field": "U",
        "final_update_id_field": "u",
        "bids_field": "b",
        "asks_field": "a",
        "level_price_index": 0,
        "level_quantity_index": 1,
    },
})

TRADE_ONLY_PROFILE = ExchangeProfile.from_dict({
    "profile_name": "trade_only",
    "field_mapping": {
        "event_time": "E", "trade_time": "T", "trade_id": "a",
        "symbol": "s", "price": "p", "quantity": "q",
        "side_field": "m", "side_rule": "m == true → SELL, m == false → BUY",
    },
    "timestamp_format": "epoch_ms",
})

# Minimal Binance-style depth payloads
_DIFF_RAW = {
    "e": "depthUpdate",
    "E": 1700000000123,
    "s": "BTCUSDT",
    "U": 100,
    "u": 105,
    "b": [["99999.50", "1.250"], ["99999.00", "0"]],
    "a": [["100000.00", "0.800"]],
}

_SNAPSHOT_RAW = {
    "e": "depthSnapshot",
    "E": 1700000000000,
    "s": "BTCUSDT",
    "u": 99,
    "b": [["99999.50", "1.250"]],
    "a": [["100000.00", "0.800"]],
}


# ============================ normalize_raw_depth ============================
def test_depth_diff_normalization() -> None:
    update = normalize_raw_depth(_DIFF_RAW, BINANCE_OB_PROFILE)
    assert isinstance(update, OrderBookUpdate)
    assert update.update_type == "DIFF"
    assert update.symbol == "BTCUSDT"
    assert update.first_update_id == 100
    assert update.final_update_id == 105
    assert len(update.bids) == 2
    assert len(update.asks) == 1


def test_depth_snapshot_normalization() -> None:
    update = normalize_raw_depth(_SNAPSHOT_RAW, BINANCE_OB_PROFILE)
    assert update.update_type == "SNAPSHOT"
    assert update.first_update_id is None   # not required for snapshot
    assert update.final_update_id == 99


def test_depth_bids_asks_preserve_input_order() -> None:
    update = normalize_raw_depth(_DIFF_RAW, BINANCE_OB_PROFILE)
    assert update.bids[0].price == Decimal("99999.50")
    assert update.bids[1].price == Decimal("99999.00")


def test_depth_decimal_values_exact() -> None:
    update = normalize_raw_depth(_DIFF_RAW, BINANCE_OB_PROFILE)
    assert isinstance(update.bids[0].price, Decimal)
    assert isinstance(update.bids[0].quantity, Decimal)
    assert update.bids[0].price == Decimal("99999.50")
    assert update.bids[0].quantity == Decimal("1.250")


def test_depth_unknown_event_type_rejected() -> None:
    bad = {**_DIFF_RAW, "e": "klineUpdate"}
    with pytest.raises(NormalizationError):
        normalize_raw_depth(bad, BINANCE_OB_PROFILE)


def test_depth_missing_final_update_id_rejected() -> None:
    bad = {k: v for k, v in _DIFF_RAW.items() if k != "u"}
    with pytest.raises(NormalizationError):
        normalize_raw_depth(bad, BINANCE_OB_PROFILE)


def test_depth_diff_missing_first_update_id_rejected() -> None:
    bad = {k: v for k, v in _DIFF_RAW.items() if k != "U"}
    with pytest.raises(NormalizationError):
        normalize_raw_depth(bad, BINANCE_OB_PROFILE)


# ============================ DataNormalizer.process_depth ===================
def test_depth_filtered_when_no_mapping() -> None:
    norm = DataNormalizer(TRADE_ONLY_PROFILE)
    result = norm.process_depth(_DIFF_RAW)
    assert result is None
    assert norm.depth_filtered == 1
    assert norm.depth_processed == 0


def test_process_depth_returns_update() -> None:
    norm = DataNormalizer(BINANCE_OB_PROFILE)
    result = norm.process_depth(_DIFF_RAW)
    assert result is not None
    assert result.update_type == "DIFF"
    assert norm.depth_processed == 1


def test_process_depth_counts_rejection() -> None:
    norm = DataNormalizer(BINANCE_OB_PROFILE)
    bad = {**_DIFF_RAW, "e": "klineUpdate"}
    result = norm.process_depth(bad)
    assert result is None
    assert norm.depth_rejected == 1


# ============================ DataNormalizer.classify_raw ====================
def test_classify_raw_trade() -> None:
    norm = DataNormalizer(BINANCE_OB_PROFILE)
    raw = {"e": "aggTrade", "E": 1, "s": "BTCUSDT", "a": 1, "p": "100", "q": "1", "m": False, "T": 1}
    assert norm.classify_raw(raw) == "trade"


def test_classify_raw_depth() -> None:
    norm = DataNormalizer(BINANCE_OB_PROFILE)
    assert norm.classify_raw(_DIFF_RAW) == "depth"
    assert norm.classify_raw(_SNAPSHOT_RAW) == "depth"


def test_classify_raw_no_mapping() -> None:
    norm = DataNormalizer(TRADE_ONLY_PROFILE)
    assert norm.classify_raw(_DIFF_RAW) == "trade"   # no ob mapping → always trade


# ============================ ExchangeProfile validation =====================
def test_profile_order_book_mapping_optional() -> None:
    # Profile without order_book_mapping loads fine (backward compat).
    prof = ExchangeProfile.from_dict({
        "profile_name": "minimal",
        "field_mapping": {
            "event_time": "E", "trade_time": "T", "trade_id": "a",
            "symbol": "s", "price": "p", "quantity": "q",
            "side_field": "m", "side_rule": "direct",
        },
        "timestamp_format": "epoch_ms",
    })
    assert prof.order_book_mapping is None


def test_profile_order_book_mapping_full_binance() -> None:
    # binance.yaml-style profile with order_book_mapping loads successfully.
    assert BINANCE_OB_PROFILE.order_book_mapping is not None
    assert BINANCE_OB_PROFILE.order_book_mapping["event_type_diff"] == "depthUpdate"


def test_profile_order_book_mapping_missing_field_rejected() -> None:
    bad_ob = {
        "event_type_field": "e",
        # event_type_snapshot MISSING
        "event_type_diff": "depthUpdate",
        "symbol_field": "s",
        "event_time_field": "E",
        "first_update_id_field": "U",
        "final_update_id_field": "u",
        "bids_field": "b",
        "asks_field": "a",
        "level_price_index": 0,
        "level_quantity_index": 1,
    }
    with pytest.raises(ProfileError) as exc_info:
        ExchangeProfile.from_dict({
            "profile_name": "bad",
            "field_mapping": {
                "event_time": "E", "trade_time": "T", "trade_id": "a",
                "symbol": "s", "price": "p", "quantity": "q",
                "side_field": "m", "side_rule": "direct",
            },
            "timestamp_format": "epoch_ms",
            "order_book_mapping": bad_ob,
        })
    assert "E1002" in str(exc_info.value)
