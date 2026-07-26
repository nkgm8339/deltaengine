from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pyarrow.parquet as pq
import pytest

from src.observation.hook_replay import JournalIntegrityError, JournalReplay
from src.observation.hook_storage import HookEventStorage
from src.observation.raw_journal import AppendOnlyRawJournal
from src.orderflow.hooks.models import (
    CalibrationStatus,
    DirectionHint,
    HookCandidate,
    HookEvent,
    HookSide,
    HookThreshold,
)


def _journal(tmp_path, mode="full", include=lambda _row: True):
    return AppendOnlyRawJournal(
        stream_root=tmp_path / mode,
        campaign_id="stage2a_test",
        config_hash="a" * 64,
        mode=mode,
        deadline=datetime.now(timezone.utc) + timedelta(days=1),
        queue_depth=100,
        compression="xz",
        compression_level=1,
        flush_interval_sec=1,
        min_free_bytes=1,
        include=include,
    )


def _event() -> HookEvent:
    now = datetime(2026, 7, 26, 0, 0, tzinfo=timezone.utc)
    candidate = HookCandidate(
        hook_id="B07",
        symbol="BTCUSDT",
        side=HookSide.BUY,
        direction_hint=DirectionHint.UP,
        source_time=now,
        received_time=now,
        available_time=now,
        metric_name="trade_notional",
        metric_value=Decimal("123456.789"),
        source_sequence="42",
        anchor_price=Decimal("118000.25"),
        evidence={"quantity": Decimal("1.04624300")},
    )
    threshold = HookThreshold(
        hook_id="B07",
        metric_name="trade_notional",
        operator="ge",
        quantile=Decimal("0.99"),
        value=Decimal("100000"),
        status=CalibrationStatus.CALIBRATED,
        input_manifest_sha256="b" * 64,
        sample_count=1000,
        valid_days=3,
    )
    return HookEvent.from_candidate(
        candidate,
        threshold,
        detector_version="test-v1",
        config_hash="c" * 64,
        input_manifest_hash="b" * 64,
    )


def test_append_only_journal_round_trip_and_manifest(tmp_path):
    journal = _journal(tmp_path)
    rows = [
        {
            "e": "depthSnapshot",
            "s": "BTCUSDT",
            "E": 1,
            "u": 1,
            "b": [["1", "2"]],
            "a": [["2", "3"]],
            "_capture_reason": "INITIAL_BOOK_SYNC",
        },
        {"e": "depthUpdate", "U": 2, "u": 2, "b": [], "a": []},
        {"e": "forceOrder", "E": 123, "o": {"S": "SELL"}},
    ]
    for row in rows:
        journal.write(row)
    session_dir = journal.session_dir
    journal.close()

    summary = json.loads(
        (session_dir / "session_summary.json").read_text(encoding="utf-8")
    )
    assert summary["valid"] is True
    assert summary["persisted"] == 3
    assert summary["durably_committed"] == 3
    replayed = list(JournalReplay(session_dir).records())
    assert [record.payload for record in replayed] == rows
    assert [record.record_type for record in replayed] == [
        "DEPTH_SNAPSHOT",
        "DEPTH_UPDATE",
        "LIQUIDATION",
    ]
    manifest = (session_dir / "manifest_events.jsonl").read_text(encoding="utf-8")
    assert "FRAME_COMMIT" in manifest
    assert "SEGMENT_CLOSE" in manifest
    assert "SESSION_END" in manifest


def test_liquidation_filter_and_session_paths_are_create_new(tmp_path):
    first = _journal(
        tmp_path,
        mode="liquidation",
        include=lambda row: row.get("e") == "forceOrder",
    )
    first.write({"e": "aggTrade", "a": 1})
    first.write({"e": "forceOrder", "E": 2, "o": {"S": "BUY"}})
    first_dir = first.session_dir
    first.close()

    second = _journal(
        tmp_path,
        mode="liquidation",
        include=lambda row: row.get("e") == "forceOrder",
    )
    second_dir = second.session_dir
    second.close()

    assert first_dir != second_dir
    assert len(list(JournalReplay(first_dir).records())) == 1
    assert len(list(JournalReplay(second_dir).records())) == 0


def test_replay_rejects_crash_incomplete_session(tmp_path):
    journal = _journal(tmp_path)
    with pytest.raises(JournalIntegrityError, match="no summary"):
        JournalReplay(journal.session_dir)
    journal.close()


def test_crash_incomplete_xz_replays_only_durably_committed_frames(tmp_path):
    journal = _journal(tmp_path)
    rows = [
        {"e": "depthUpdate", "U": index, "u": index, "b": [], "a": []}
        for index in range(1, 4)
    ]
    for row in rows:
        journal.write(row)
    deadline = time.monotonic() + 5
    while journal.durably_committed < len(rows) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert journal.durably_committed == len(rows)
    session_dir = journal.session_dir
    journal.close()

    (session_dir / "session_summary.json").unlink()
    segment = next(session_dir.glob("raw-*.jsonl.xz"))
    with segment.open("ab") as handle:
        handle.write(b"uncommitted-crash-tail")

    with pytest.raises(JournalIntegrityError, match="no summary"):
        JournalReplay(session_dir)
    replay = JournalReplay(session_dir, allow_active=True)
    assert [record.payload for record in replay.records()] == rows
    assert replay.uncommitted_tail_bytes == len(b"uncommitted-crash-tail")


def test_committed_xz_frame_hash_mismatch_is_rejected(tmp_path):
    journal = _journal(tmp_path)
    journal.write({"e": "forceOrder", "E": 1, "o": {"S": "SELL"}})
    session_dir = journal.session_dir
    journal.close()

    manifest_rows = [
        json.loads(line)
        for line in (session_dir / "manifest_events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    frame = next(row for row in manifest_rows if row["event"] == "FRAME_COMMIT")
    segment = session_dir / frame["file"]
    with segment.open("r+b") as handle:
        handle.seek(frame["offset"] + 1)
        original = handle.read(1)
        handle.seek(frame["offset"] + 1)
        handle.write(bytes([original[0] ^ 0x01]))

    with pytest.raises(JournalIntegrityError, match="frame hash mismatch"):
        list(JournalReplay(session_dir).records())


def test_hook_event_storage_is_separate_append_only_parquet(tmp_path):
    storage = HookEventStorage(
        tmp_path / "hooks",
        queue_depth=10,
        batch_size=1,
        flush_interval_sec=1,
    )
    event = _event()
    assert storage.add_event(event) is True
    session_dir = storage.session_dir
    storage.close()

    parts = list(session_dir.glob("part-*.parquet"))
    assert len(parts) == 1
    row = pq.read_table(parts[0]).to_pylist()[0]
    assert row["hook_event_id"] == event.hook_event_id
    assert row["hook_id"] == "B07"
    assert row["metric_value"] == Decimal("123456.78900000")
    summary = json.loads(
        (session_dir / "session_summary.json").read_text(encoding="utf-8")
    )
    assert summary["valid"] is True
