from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from src.orderflow.hooks.adapters import FlowResponseHookAdapter
from src.orderflow.hooks.config import ThresholdBook
from src.orderflow.hooks.models import (
    CalibrationStatus,
    DirectionHint,
    HookCandidate,
    HookSide,
    HookThreshold,
)
from src.orderflow.hooks.quality import DomDataQualityGate, DomSyncState
from src.orderflow.hooks.registry import HOOK_REGISTRY
from src.orderflow.hooks.runtime import HookRuntime


def _candidate() -> HookCandidate:
    now = datetime(2026, 7, 26, tzinfo=timezone.utc)
    return HookCandidate(
        hook_id="A01",
        symbol="BTCUSDT",
        side=HookSide.BID,
        direction_hint=DirectionHint.UP,
        source_time=now,
        received_time=now,
        available_time=now,
        metric_name="level_notional_over_band_median",
        metric_value=Decimal("8"),
    )


def test_registry_contains_all_catalog_hooks_and_suspected_labels():
    assert len(HOOK_REGISTRY) == 88
    assert set(HOOK_REGISTRY) == {
        *(f"A{i:02d}" for i in range(1, 25)),
        *(f"B{i:02d}" for i in range(1, 21)),
        *(f"C{i:02d}" for i in range(1, 10)),
        *(f"D{i:02d}" for i in range(1, 9)),
        *(f"E{i:02d}" for i in range(1, 7)),
        *(f"F{i:02d}" for i in range(1, 6)),
        *(f"G{i:02d}" for i in range(1, 13)),
        *(f"H{i:02d}" for i in range(1, 5)),
    }
    for hook_id in ("A17", "A18", "A19", "A20"):
        assert HOOK_REGISTRY[hook_id].suspected is True
        assert "suspected" in HOOK_REGISTRY[hook_id].name


def test_uncalibrated_and_provisional_hooks_cannot_fire():
    candidate = _candidate()
    empty = ThresholdBook({}, config_hash="a" * 64)
    assert HookRuntime(empty).submit((candidate,)) == ()

    provisional = HookThreshold(
        hook_id="A01",
        metric_name=candidate.metric_name,
        operator="ge",
        quantile=Decimal("0.995"),
        value=Decimal("5"),
        status=CalibrationStatus.PROVISIONAL,
    )
    book = ThresholdBook({"A01": provisional}, config_hash="a" * 64)
    assert HookRuntime(book).submit((candidate,)) == ()
    assert book.suppressed_uncalibrated == 1


def test_calibrated_hook_requires_matching_manifest_and_is_deterministic():
    candidate = _candidate()
    threshold = HookThreshold(
        hook_id="A01",
        metric_name=candidate.metric_name,
        operator="ge",
        quantile=Decimal("0.995"),
        value=Decimal("5"),
        status=CalibrationStatus.CALIBRATED,
        input_manifest_sha256="b" * 64,
        sample_count=10_000,
        valid_days=3,
    )
    mismatch = ThresholdBook({"A01": threshold}, config_hash="a" * 64)
    assert HookRuntime(mismatch, input_manifest_hash="c" * 64).submit((candidate,)) == ()
    assert mismatch.suppressed_manifest_mismatch == 1

    runtime = HookRuntime(
        ThresholdBook({"A01": threshold}, config_hash="a" * 64),
        input_manifest_hash="b" * 64,
    )
    first = runtime.submit((candidate,))
    second = runtime.submit((candidate,))
    assert len(first) == 1
    assert second == ()
    assert runtime.duplicates_suppressed == 1


def test_dom_quality_gate_requires_snapshot_alignment_and_continuity():
    gate = DomDataQualityGate()
    applied = SimpleNamespace(applied=True, gap_detected=False)
    snapshot = SimpleNamespace(
        update_type="SNAPSHOT",
        final_update_id=100,
        first_update_id=None,
        previous_final_update_id=None,
    )
    assert gate.observe(snapshot, applied).state is DomSyncState.WAITING_FIRST_DIFF

    first = SimpleNamespace(
        update_type="DIFF",
        first_update_id=100,
        final_update_id=102,
        previous_final_update_id=None,
    )
    assert gate.observe(first, applied).state is DomSyncState.VALID

    gap = SimpleNamespace(
        update_type="DIFF",
        first_update_id=104,
        final_update_id=104,
        previous_final_update_id=103,
    )
    assert gate.observe(gap, applied).state is DomSyncState.INVALID


def test_flow_response_adapter_emits_only_state_transition_edges():
    now = datetime(2026, 7, 26, tzinfo=timezone.utc)
    state = SimpleNamespace(value="BUY_EFFECTIVE")
    snapshot = SimpleNamespace(
        state=state,
        event_time=now,
        window_sec=60,
        symbol="BTCUSDT",
        last_price=Decimal("118000"),
        pressure_side="BUY",
        pressure_ratio=Decimal("0.7"),
        persistence=Decimal("0.8"),
        price_change_bps=Decimal("2"),
    )
    adapter = FlowResponseHookAdapter()
    assert [item.hook_id for item in adapter.process((snapshot,))] == ["D01"]
    assert adapter.process((snapshot,)) == ()
