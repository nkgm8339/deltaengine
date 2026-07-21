"""Tests for src.normalization.normalizer.

Section 1 implements TestSpecification_v3.2 §4.6 TV-NRM-01..04 verbatim
(fixture "EX1", dedup_window=10000, reorder_tolerance=500 ms). Later sections
cover profile validation, side resolution, and deterministic replay.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.normalization.normalizer import (
    ERROR_CONFIG_VALIDATION,
    ERROR_INVALID_TRADE,
    ExchangeProfile,
    NormalizationError,
    ProfileError,
    DataNormalizer,
    normalize_raw,
    run,
)

# Fixture profile EX1: raw fields epoch_ms/sym/px/qty/aggr/id ; aggr holds BUY/SELL.
EX1 = ExchangeProfile.from_dict(
    {
        "profile_name": "EX1",
        "field_mapping": {
            "event_time": "epoch_ms",
            "trade_time": "epoch_ms",
            "trade_id": "id",
            "symbol": "sym",
            "price": "px",
            "quantity": "qty",
            "side_field": "aggr",
            "side_rule": "aggr holds BUY/SELL directly",
        },
        "timestamp_format": "epoch_ms",
    }
)


def _raw(epoch_ms: int, trade_id: int, side: str = "BUY", px=50000.5, qty=3, sym="BTCUSDT") -> dict:
    return {"epoch_ms": epoch_ms, "id": trade_id, "aggr": side, "px": px, "qty": qty, "sym": sym}


# ============================ TV-NRM-01..04 ===================================
def test_tv_nrm_01_normal_conversion() -> None:
    raw = {"epoch_ms": 1767225601000, "sym": "BTCUSDT", "px": 50000.5, "qty": 3, "aggr": "BUY", "id": 1}
    rec = normalize_raw(raw, EX1)
    assert rec.event_time == datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc)
    assert rec.symbol == "BTCUSDT"
    assert rec.price == Decimal("50000.5")
    assert rec.quantity == Decimal("3")
    assert rec.side == "BUY"


def test_tv_nrm_02_duplicate_discard() -> None:
    raws = [_raw(1767225601000, 1), _raw(1767225601000, 1)]  # same trade_id twice
    result = run(raws, EX1, dedup_window=10000, reorder_tolerance_ms=500)
    assert len(result.emitted) == 1
    assert result.duplicates == 1
    assert result.processed == 1


def test_tv_nrm_03_reorder_within_tolerance() -> None:
    normalizer = DataNormalizer(EX1, dedup_window=10000, reorder_tolerance_ms=500)
    normalizer.process(_raw(1767225610000, trade_id=2))       # B @ 00:00:10.000
    normalizer.process(_raw(1767225609600, trade_id=1))       # A @ 00:00:09.600 (400ms late)
    emitted = normalizer.flush()
    assert [t.trade_id for t in emitted] == [1, 2]            # output order A -> B
    assert normalizer.reordered == 1
    assert normalizer.rejected == 0


def test_tv_nrm_04_reorder_beyond_tolerance() -> None:
    normalizer = DataNormalizer(EX1, dedup_window=10000, reorder_tolerance_ms=500)
    normalizer.process(_raw(1767225610000, trade_id=2))       # B @ 00:00:10.000
    assert [t.trade_id for t in normalizer.flush()] == [2]    # B emitted; last_emitted = 10.000
    late = normalizer.process(_raw(1767225609400, trade_id=3))  # C @ 09.400 (600ms late)
    assert late == []
    assert normalizer.rejected == 1                           # C rejected, counted (no silent loss)


# ============================ profile validation ==============================
def test_profile_missing_fields_rejected() -> None:
    with pytest.raises(ProfileError) as exc:
        ExchangeProfile.from_dict(
            {"profile_name": "X", "field_mapping": {"symbol": "s"}, "timestamp_format": "epoch_ms"}
        )
    assert exc.value.code == ERROR_CONFIG_VALIDATION


def test_profile_invalid_timestamp_format_rejected() -> None:
    with pytest.raises(ProfileError):
        ExchangeProfile.from_dict(
            {
                "profile_name": "X",
                "field_mapping": {k: k for k in
                                  ["event_time", "trade_time", "trade_id", "symbol",
                                   "price", "quantity", "side_field", "side_rule"]},
                "timestamp_format": "nanoseconds",
            }
        )


# ============================ side resolution =================================
def test_invalid_side_rejected() -> None:
    with pytest.raises(NormalizationError) as exc:
        normalize_raw(_raw(1767225601000, 1, side="X"), EX1)
    assert exc.value.code == ERROR_INVALID_TRADE


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("px", 0),
        ("px", -1),
        ("px", "NaN"),
        ("px", "Infinity"),
        ("qty", 0),
        ("qty", -1),
        ("qty", "NaN"),
        ("qty", "Infinity"),
    ],
)
def test_nonpositive_or_nonfinite_trade_values_rejected(field: str, value) -> None:
    raw = _raw(1767225601000, 1)
    raw[field] = value
    with pytest.raises(NormalizationError) as exc:
        normalize_raw(raw, EX1)
    assert exc.value.code == ERROR_INVALID_TRADE


def test_data_normalizer_counts_zero_trade_as_rejected() -> None:
    normalizer = DataNormalizer(EX1)
    assert normalizer.process(_raw(1767225601000, 1, px=0, qty=0)) == []
    assert normalizer.flush() == []
    assert normalizer.processed == 0
    assert normalizer.rejected == 1


def test_binance_boolean_side_rule() -> None:
    binance = ExchangeProfile.from_dict(
        {
            "profile_name": "binance",
            "field_mapping": {
                "event_time": "E", "trade_time": "T", "trade_id": "t", "symbol": "s",
                "price": "p", "quantity": "q", "side_field": "m",
                "side_rule": "m == true → SELL, m == false → BUY",
            },
            "timestamp_format": "epoch_ms",
        }
    )
    base = {"E": 1767225601000, "T": 1767225601000, "t": 1, "s": "BTCUSDT", "p": 100, "q": 1}
    assert normalize_raw({**base, "m": True}, binance).side == "SELL"
    assert normalize_raw({**base, "m": False}, binance).side == "BUY"


def test_iso8601_timestamp_format() -> None:
    profile = ExchangeProfile.from_dict(
        {
            "profile_name": "ISO",
            "field_mapping": {
                "event_time": "ts", "trade_time": "ts", "trade_id": "id", "symbol": "sym",
                "price": "px", "quantity": "qty", "side_field": "aggr", "side_rule": "direct",
            },
            "timestamp_format": "iso8601",
        }
    )
    raw = {"ts": "2026-01-01T00:00:01Z", "id": 1, "sym": "BTCUSDT", "px": 100, "qty": 1, "aggr": "SELL"}
    rec = normalize_raw(raw, profile)
    assert rec.event_time == datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc)
    assert rec.side == "SELL"


# ============================ deterministic replay ============================
def test_deterministic_replay_identical() -> None:
    raws = [
        _raw(1767225610000, 2, side="BUY"),
        _raw(1767225609600, 1, side="SELL"),   # reorder within tolerance
        _raw(1767225610000, 2, side="BUY"),    # duplicate
        {"epoch_ms": 1767225611000, "id": 3, "aggr": "X", "px": 1, "qty": 1, "sym": "BTCUSDT"},  # invalid
    ]
    first = run(raws, EX1, reorder_tolerance_ms=500)
    second = run(raws, EX1, reorder_tolerance_ms=500)
    assert first == second
    assert [t.trade_id for t in first.emitted] == [1, 2]
    assert first.duplicates == 1
    assert first.reordered == 1
    assert first.rejected == 1
