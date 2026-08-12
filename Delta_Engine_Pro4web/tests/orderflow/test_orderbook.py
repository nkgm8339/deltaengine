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


def test_ob_snapshot_is_reused_until_an_accepted_state_change() -> None:
    mgr = OrderBookStateManager("BTCUSDT")
    mgr.apply(_snapshot(final_id=100))

    first = mgr.snapshot()
    again = mgr.snapshot()
    assert first is again
    assert first.ordered_bids == (
        (D("99999.50"), D("1.250")),
        (D("99999.00"), D("3.100")),
    )
    assert first.ordered_asks == (
        (D("100000.00"), D("0.800")),
        (D("100000.50"), D("2.400")),
    )
    assert first.best_bids(1) == first.ordered_bids[:1]
    assert first.best_asks(1) == first.ordered_asks[:1]

    result = mgr.apply(_diff(101, 105, bids=[("99999.50", "9.999")]))
    assert result.applied is True
    changed = mgr.snapshot()
    assert changed is not first
    assert changed.bids[D("99999.50")] == D("9.999")
    assert first.bids[D("99999.50")] == D("1.250")

    gap = mgr.apply(_diff(200, 205))
    assert gap.gap_detected is True
    assert mgr.snapshot() is None


def test_ob_bounded_best_levels_are_exact_and_do_not_sort_the_full_book() -> None:
    bids = {
        D("1000") - D(index): D(index + 1)
        for index in range(75)
    }
    asks = {
        D("1001") + D(index): D(index + 1)
        for index in range(75)
    }
    snap = OrderBookSnapshot("BTCUSDT", 1, bids, asks)
    expected_bids = tuple(sorted(bids.items(), key=lambda row: row[0], reverse=True))
    expected_asks = tuple(sorted(asks.items(), key=lambda row: row[0]))

    assert snap.best_bids(50) == expected_bids[:50]
    assert snap.best_asks(50) == expected_asks[:50]
    assert "ordered_bids" not in snap.__dict__
    assert "ordered_asks" not in snap.__dict__
    assert snap.top_bids is snap.top_bids
    assert snap.top_asks is snap.top_asks

    assert snap.best_bids(51) == expected_bids[:51]
    assert snap.best_asks(51) == expected_asks[:51]
    assert "ordered_bids" in snap.__dict__
    assert "ordered_asks" in snap.__dict__


def test_ob_manager_precomputes_exact_bounded_levels_through_churn_and_resync() -> None:
    bids = [
        (str(D("1000") - D(index)), str(index + 1))
        for index in range(75)
    ]
    asks = [
        (str(D("1001") + D(index)), str(index + 1))
        for index in range(75)
    ]
    mgr = OrderBookStateManager("BTCUSDT")
    mgr.apply(_snapshot(final_id=100, bids=bids, asks=asks))

    first = mgr.snapshot()
    assert first is not None
    assert first.best_bids(50) == first.ordered_bids[:50]
    assert first.best_asks(50) == first.ordered_asks[:50]

    mgr.apply(_diff(
        101,
        105,
        bids=[("1000", "0"), ("1000.25", "7")],
        asks=[("1001", "0"), ("1000.50", "8")],
    ))
    changed = mgr.snapshot()
    assert changed is not None
    expected_bids = tuple(sorted(changed.bids.items(), reverse=True)[:50])
    expected_asks = tuple(sorted(changed.asks.items())[:50])
    assert changed.best_bids(50) == expected_bids
    assert changed.best_asks(50) == expected_asks
    assert "ordered_bids" not in changed.__dict__
    assert "ordered_asks" not in changed.__dict__
    assert first.bids[D("1000")] == D("1")

    assert mgr.apply(_diff(200, 205)).gap_detected is True
    mgr.apply(_snapshot(
        final_id=300,
        bids=[("900", "1")],
        asks=[("901", "2")],
    ))
    recovered = mgr.snapshot()
    assert recovered is not None
    assert recovered.best_bids(50) == ((D("900"), D("1")),)
    assert recovered.best_asks(50) == ((D("901"), D("2")),)


@pytest.mark.parametrize("method_name", ("best_bids", "best_asks"))
def test_ob_bounded_best_levels_reject_non_positive_limit(method_name: str) -> None:
    snap = OrderBookSnapshot("BTCUSDT", 1, {D("100"): D("1")}, {})
    method = getattr(snap, method_name)

    for limit in (0, -1):
        with pytest.raises(ValueError, match="limit must be >= 1"):
            method(limit)


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
