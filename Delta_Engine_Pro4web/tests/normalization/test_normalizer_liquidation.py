"""Unit tests for liquidation normalization (forceOrder stream).

3 tests:
1. forceOrder 正常系 — LiquidationEvent の全フィールド検証
2. 必須フィールド欠損で NormalizationError
3. classify_raw が forceOrder を "liquidation" と分類
"""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone

import pytest

from src.normalization.normalizer import (
    DataNormalizer,
    ExchangeProfile,
    LiquidationEvent,
    NormalizationError,
    normalize_raw_liquidation,
)

_UTC = timezone.utc

# Minimal profile (timestamp_format is used by normalize_raw_liquidation).
_PROFILE = ExchangeProfile.from_dict(
    {
        "profile_name": "test",
        "field_mapping": {
            "event_time": "E",
            "trade_time": "T",
            "trade_id": "a",
            "symbol": "s",
            "price": "p",
            "quantity": "q",
            "side_field": "m",
            "side_rule": "m == true → SELL, m == false → BUY",
        },
        "timestamp_format": "epoch_ms",
    }
)

_FORCE_ORDER_RAW = {
    "e": "forceOrder",
    "E": 1767225600000,
    "o": {
        "s": "BTCUSDT",
        "S": "SELL",
        "p": "50000.00",
        "q": "0.500",
        "T": 1767225600000,
    },
}


# ── Test 1: forceOrder 正常系 ─────────────────────────────────────────────────

def test_normalize_raw_liquidation_all_fields() -> None:
    """normalize_raw_liquidation produces a correct LiquidationEvent for a valid payload."""
    evt = normalize_raw_liquidation(_FORCE_ORDER_RAW, _PROFILE)

    assert isinstance(evt, LiquidationEvent)
    assert evt.symbol == "BTCUSDT"
    # SELL side = long position was liquidated (forced sell to close long).
    assert evt.side == "SELL"
    assert evt.price == Decimal("50000.00")
    assert evt.quantity == Decimal("0.500")
    expected_time = datetime(2026, 1, 1, 0, 0, 0, tzinfo=_UTC)
    assert evt.event_time == expected_time


# ── Test 2: 必須フィールド欠損で NormalizationError ──────────────────────────

@pytest.mark.parametrize("missing_field", ["s", "S", "p", "q", "T"])
def test_normalize_raw_liquidation_missing_field_raises(missing_field: str) -> None:
    """normalize_raw_liquidation raises NormalizationError when a required 'o' field is missing."""
    raw = {
        "e": "forceOrder",
        "E": 1767225600000,
        "o": {k: v for k, v in _FORCE_ORDER_RAW["o"].items() if k != missing_field},
    }
    with pytest.raises(NormalizationError, match="missing fields"):
        normalize_raw_liquidation(raw, _PROFILE)


def test_normalize_raw_liquidation_missing_event_time_raises() -> None:
    """normalize_raw_liquidation raises NormalizationError when 'E' (event_time) is absent."""
    raw = {"e": "forceOrder", "o": dict(_FORCE_ORDER_RAW["o"])}
    with pytest.raises(NormalizationError, match="missing event_time"):
        normalize_raw_liquidation(raw, _PROFILE)


# ── Test 3: classify_raw が forceOrder を "liquidation" と分類 ────────────────

def test_classify_raw_force_order_returns_liquidation() -> None:
    """DataNormalizer.classify_raw returns 'liquidation' for a forceOrder event."""
    normalizer = DataNormalizer(_PROFILE)
    result = normalizer.classify_raw(_FORCE_ORDER_RAW)
    assert result == "liquidation"


def test_classify_raw_force_order_takes_priority_over_depth() -> None:
    """'liquidation' classification precedes depth check even with order_book_mapping present."""
    from pathlib import Path
    import yaml

    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    profile_data = yaml.safe_load(
        (PROJECT_ROOT / "config" / "profiles" / "binance.yaml").read_text(encoding="utf-8")
    )
    binance_profile = ExchangeProfile.from_dict(profile_data)
    normalizer = DataNormalizer(binance_profile)

    result = normalizer.classify_raw({"e": "forceOrder", "E": 1000, "o": {}})
    assert result == "liquidation"
