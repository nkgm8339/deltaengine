"""Tests for src.orderflow.orderbook — B-1 Order Book State Manager.

All fixtures are fixture-driven (no network, decision 4). Decimal only, no float.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.orderflow.orderbook import (
    ApplyResult,
    BookLevel,
    OrderBookSnapshot,
    OrderBookStateManager,
    OrderBookUpdate,
)

UTC = timezone.utc
_T0 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
_T1 = datetime(2026, 1, 1, 0, 0, 0, 100000, tzinfo=UTC)

D = Decimal


def _snapshot(
    final_id: int = 100,
    bids: list[tuple] = None,
    asks: list[tuple] = None,
    symbol: str = "BTCUSDT",
) -> OrderBookUpdate:
    bids = bids or [("99999.50", "1.250"), ("99999.00", "3.100")]
    asks = asks or [("100000.00", "0.800"), ("100000.50", "2.400")]
    return OrderBookUpdate(
        event_time=_T0,
        symbol=symbol,
        update_type="SNAPSHOT",
        first_update_id=None,
        final_update_id=final_id,
        bids=tuple(BookLevel(D(p), D(q)) for p, q in bids),
        asks=tuple(BookLevel(D(p), D(q)) for p, q in asks),
    )


def _diff(
    first_id: int,
    final_id: int,
    bids: list[tuple] = None,
    asks: list[tuple] = None,
    symbol: str = "BTCUSDT",
) -> OrderBookUpdate:
    bids = bids or []
    asks = asks or []
    return OrderBookUpdate(
        event_time=_T1,
        symbol=symbol,
        update_type="DIFF",
        first_update_id=first_id,
        final_update_id=final_id,
        bids=tuple(BookLevel(D(p), D(q)) for p, q in bids),
        asks=tuple(BookLevel(D(p), D(q)) for p, q in asks),
    )


# ============================ snapshot =======================================
def test_ob_snapshot_establishes_state() -> None:
    mgr = OrderBookStateManager("BTCUSDT")
    assert mgr.snapshot() is None   # not yet initialized

    result = mgr.apply(_snapshot(final_id=100))

    assert result.applied is True
    assert result.reinitialized is False
    snap = mgr.snapshot()
    assert snap is not None
    assert snap.last_update_id == 100
    assert snap.bids[D("99999.50")] == D("1.250")
    assert snap.asks[D("100000.00")] == D("0.800")
    assert mgr.snapshots_applied == 1


def test_ob_snapshot_replaces_existing_state() -> None:
    mgr = OrderBookStateManager("BTCUSDT")
    mgr.apply(_snapshot(final_id=100))
    result = mgr.apply(_snapshot(final_id=200, bids=[("50000.00", "5.000")], asks=[]))
    assert result.reinitialized is True
    snap = mgr.snapshot()
    assert D("99999.50") not in snap.bids   # old bid gone
    assert D("50000.00") in snap.bids
    assert mgr.snapshots_applied == 2


# ============================ diff ============================================
def test_ob_diff_overwrites_quantity() -> None:
    mgr = OrderBookStateManager("BTCUSDT")
    mgr.apply(_snapshot(final_id=100))
    mgr.apply(_diff(101, 105, bids=[("99999.50", "9.999")]))
    snap = mgr.snapshot()
    assert snap.bids[D("99999.50")] == D("9.999")
    assert mgr.diffs_applied == 1


def test_ob_diff_zero_quantity_removes_level() -> None:
    mgr = OrderBookStateManager("BTCUSDT")
    mgr.apply(_snapshot(final_id=100))
    mgr.apply(_diff(101, 105, bids=[("99999.50", "0")]))
    snap = mgr.snapshot()
    assert D("99999.50") not in snap.bids


def test_ob_diff_adds_new_level() -> None:
    mgr = OrderBookStateManager("BTCUSDT")
    mgr.apply(_snapshot(final_id=100))
    mgr.apply(_diff(101, 105, bids=[("99998.00", "2.000")]))
    snap = mgr.snapshot()
    assert snap.bids[D("99998.00")] == D("2.000")


# ============================ rejection / gap =================================
def test_ob_diff_before_snapshot_rejected() -> None:
    mgr = OrderBookStateManager("BTCUSDT")
    result = mgr.apply(_diff(1, 5))
    assert result.applied is False
    assert result.gap_detected is False
    assert mgr.diffs_rejected_before_snapshot == 1
    assert mgr.snapshot() is None


def test_ob_gap_detection_triggers_reinit() -> None:
    mgr = OrderBookStateManager("BTCUSDT")
    mgr.apply(_snapshot(final_id=100))
    result = mgr.apply(_diff(200, 205))  # first_id=200 != expected 101
    assert result.applied is False
    assert result.gap_detected is True
    assert mgr.gaps_detected == 1
    assert mgr.snapshot() is None   # state cleared


def test_ob_after_gap_snapshot_recovers() -> None:
    mgr = OrderBookStateManager("BTCUSDT")
    mgr.apply(_snapshot(final_id=100))
    mgr.apply(_diff(200, 205))       # triggers gap
    mgr.apply(_snapshot(final_id=300))
    snap = mgr.snapshot()
    assert snap is not None
    assert snap.last_update_id == 300


def test_ob_stale_diff_rejected() -> None:
    mgr = OrderBookStateManager("BTCUSDT")
    mgr.apply(_snapshot(final_id=100))
    mgr.apply(_diff(101, 105))
    result = mgr.apply(_diff(101, 104))  # final_id=104 <= last_update_id=105
    assert result.applied is False
    assert mgr.diffs_stale == 1


# ============================ symbol mismatch =================================
def test_ob_symbol_mismatch_raises() -> None:
    mgr = OrderBookStateManager("BTCUSDT")
    with pytest.raises(ValueError, match="symbol mismatch"):
        mgr.apply(_snapshot(symbol="ETHUSDT"))


# ============================ deterministic replay ============================
def test_ob_deterministic_replay() -> None:
    updates = [
        _snapshot(final_id=100),
        _diff(101, 105, bids=[("99999.50", "9.0")], asks=[("100000.00", "0")]),
        _diff(106, 110, bids=[("99998.00", "1.5")]),
    ]

    def _run():
        m = OrderBookStateManager("BTCUSDT")
        for u in updates:
            m.apply(u)
        return m.snapshot()

    s1, s2 = _run(), _run()
    assert s1.last_update_id == s2.last_update_id
    assert s1.bids == s2.bids
    assert s1.asks == s2.asks


# ============================ query helpers ===================================
def test_ob_query_missing_price_returns_zero() -> None:
    mgr = OrderBookStateManager("BTCUSDT")
    mgr.apply(_snapshot(final_id=100))
    assert mgr.bid_quantity_at(D("12345.00")) == D("0")
    assert mgr.ask_quantity_at(D("12345.00")) == D("0")

    snap = mgr.snapshot()
    assert snap.bid_quantity_at(D("12345.00")) == D("0")
    assert snap.ask_quantity_at(D("12345.00")) == D("0")


# ============================ initial sync (BugFix_Live_v1) ==================
def test_initial_sync_stale_diffs_counted_not_gapped() -> None:
    """After apply_initial_sync, stale diffs (final <= snap_id) are skipped without
    gap detection; the first non-stale diff exits sync mode and is applied (lenient —
    Binance Futures batches can jump past snap_id+1 due to connection timing)."""
    mgr = OrderBookStateManager("BTCUSDT")
    mgr.apply(_snapshot(final_id=1000))
    mgr.apply_initial_sync(1000)

    # Diff whose final_id <= 1000 → stale check, no gap.
    r1 = mgr.apply(_diff(980, 995))
    assert r1.applied is False
    assert r1.gap_detected is False
    assert mgr.diffs_stale == 1
    assert mgr.gaps_detected == 0

    # First non-stale diff exits sync mode even when first_id > snap_id+1 (lenient).
    r2 = mgr.apply(_diff(1005, 1010))
    assert r2.applied is True
    assert mgr.diffs_applied == 1
    assert mgr.gaps_detected == 0

    # Normal gap detection resumes after sync (no pu field → U-based check).
    r3 = mgr.apply(_diff(2000, 2010))
    assert r3.gap_detected is True
    assert mgr.gaps_detected == 1


# ============================ Decimal only ====================================
def test_ob_no_float_in_snapshot() -> None:
    mgr = OrderBookStateManager("BTCUSDT")
    mgr.apply(_snapshot(final_id=100, bids=[("99999.12345678", "1.00000001")], asks=[]))
    snap = mgr.snapshot()
    for price, qty in snap.bids.items():
        assert isinstance(price, Decimal)
        assert isinstance(qty, Decimal)


def test_is_initialized_property_lifecycle() -> None:
    """is_initialized becomes false again when a sequence gap resets state."""
    mgr = OrderBookStateManager("BTCUSDT")
    assert mgr.is_initialized is False
    mgr.apply(_snapshot(final_id=100))
    assert mgr.is_initialized is True
    result = mgr.apply(_diff(300, 310))
    assert result.gap_detected is True
    assert mgr.is_initialized is False
