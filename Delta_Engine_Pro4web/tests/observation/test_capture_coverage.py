from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.observation.capture_coverage import CaptureCoverageLedger


def _ledger(tmp_path):
    start = datetime(2026, 7, 26, 0, 0, tzinfo=timezone.utc)
    return (
        CaptureCoverageLedger(
            tmp_path / "campaign",
            original_deadlines={
                "full": start + timedelta(days=3),
                "liquidation": start + timedelta(days=14),
            },
            extension_caps={
                "full": timedelta(hours=72),
                "liquidation": timedelta(days=7),
            },
        ),
        start,
    )


def test_recovered_process_gap_extends_original_deadline_once(tmp_path):
    ledger, start = _ledger(tmp_path)
    stats = {
        "full": {
            "session_id": "session-a",
            "accepting": True,
            "accepted": 10,
            "persisted": 10,
            "durably_committed": 10,
            "dropped_queue_full": 0,
            "rejected_disk_low": 0,
            "writer_error": None,
        },
        "liquidation": {
            "session_id": "session-b",
            "accepting": True,
            "accepted": 1,
            "persisted": 1,
            "durably_committed": 1,
            "dropped_queue_full": 0,
            "rejected_disk_low": 0,
            "writer_error": None,
        },
    }
    ledger.record_start(
        ("full", "liquidation"),
        event_time=start,
        session_ids={"full": "session-a", "liquidation": "session-b"},
    )
    ledger.record_stop(stats, event_time=start + timedelta(hours=1))

    reopened = start + timedelta(hours=2)
    ledger.recover_downtime(reopened)
    ledger.recover_downtime(reopened)

    assert ledger.extension_seconds("full") == 3600
    assert ledger.extension_seconds("liquidation") == 3600
    assert ledger.effective_deadline("full") == start + timedelta(days=3, hours=1)
    assert len(ledger._read(ledger.extension_path)) == 2


def test_overlapping_extensions_are_unioned_and_capped(tmp_path):
    ledger, start = _ledger(tmp_path)
    ledger.record_extension(
        "full",
        started_at=start,
        ended_at=start + timedelta(hours=48),
        reason="TEST_A",
    )
    ledger.record_extension(
        "full",
        started_at=start + timedelta(hours=24),
        ended_at=start + timedelta(hours=96),
        reason="TEST_B",
    )
    assert ledger.extension_seconds("full") == 72 * 3600
    assert ledger.effective_deadline("full") == start + timedelta(days=6)


def test_trailing_partial_ledger_line_is_ignored_without_rewriting(tmp_path):
    ledger, start = _ledger(tmp_path)
    ledger.record_extension(
        "liquidation",
        started_at=start,
        ended_at=start + timedelta(minutes=5),
        reason="TEST",
    )
    with ledger.extension_path.open("ab") as handle:
        handle.write(b'{"partial":')

    assert ledger.extension_seconds("liquidation") == 300
    assert ledger.extension_path.read_bytes().endswith(b'{"partial":')
