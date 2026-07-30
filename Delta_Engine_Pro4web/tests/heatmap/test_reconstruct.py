from __future__ import annotations

import hashlib
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

import pytest

from src.acquisition.depth_sync import DepthSyncInputError
from src.heatmap.reconstruct import (
    DepthHistoryReader,
    DepthReconstructor,
    SegmentIntegrityError,
)


REAL_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "real_validation"
EXPECTED_SNAPSHOT_U = 11165393552876
EXPECTED_BRIDGE_U = 11165393550921
EXPECTED_BRIDGE_FINAL_U = 11165393566438
EXPECTED_SOURCE_PROVENANCE = {
    "raw_depth.20260729T193154.046959Z.jsonl": (
        "58048404f36a7fcb4a2487cb87d8c9a9f95386d624c3d4bccb1c21b227747dd6"
    ),
    "raw_depth.20260729T193201.309417Z.jsonl": (
        "1aaf0643344a30338cfb8e7bced642a83751c52a95008c488b91c93e13741a6d"
    ),
}


def _depth(
    *,
    event_time: int,
    first_id: int,
    final_id: int,
    previous_id: int,
    bids: list[list[object]] | None = None,
    asks: list[list[object]] | None = None,
) -> dict:
    return {
        "e": "depthUpdate",
        "E": event_time,
        "s": "BTCUSDT",
        "U": first_id,
        "u": final_id,
        "pu": previous_id,
        "b": bids if bids is not None else [],
        "a": asks if asks is not None else [],
    }


def _snapshot(
    *,
    event_time: int,
    final_id: int,
    bids: list[list[object]] | None = None,
    asks: list[list[object]] | None = None,
) -> dict:
    return {
        "e": "depthSnapshot",
        "E": event_time,
        "s": "BTCUSDT",
        "u": final_id,
        "b": bids if bids is not None else [["100", "1"]],
        "a": asks if asks is not None else [["101", "1"]],
    }


def _write_segment(
    directory: Path,
    name: str,
    records: list[dict],
    *,
    started_at: str,
    schema_version: int | None = 2,
    sha256_override: str | None = None,
) -> tuple[Path, Path]:
    data = b"".join(
        (
            json.dumps(
                record,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
        for record in records
    )
    segment_path = directory / name
    segment_path.write_bytes(data)
    manifest = {
        "started_at": started_at,
        "record_count": len(records),
        "byte_size": len(data),
        "sha256": sha256_override or hashlib.sha256(data).hexdigest(),
    }
    if schema_version is not None:
        manifest["schema_version"] = schema_version
    manifest_path = Path(f"{segment_path}.manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return segment_path, manifest_path


def _assert_decimal_snapshot(snapshot) -> None:
    assert snapshot is not None
    for side in (snapshot.bids, snapshot.asks):
        assert all(isinstance(price, Decimal) for price in side)
        assert all(isinstance(quantity, Decimal) for quantity in side.values())
        assert not any(isinstance(price, float) for price in side)
        assert not any(isinstance(quantity, float) for quantity in side.values())


def test_synthetic_verified_bridge_applies_multiple_diffs() -> None:
    records = [
        _depth(
            event_time=1000,
            first_id=101,
            final_id=101,
            previous_id=100,
            bids=[["100", "2"]],
        ),
        _snapshot(event_time=1001, final_id=100),
        _depth(
            event_time=1100,
            first_id=102,
            final_id=102,
            previous_id=101,
            asks=[["101", "0"], ["102", "3"]],
        ),
        _depth(
            event_time=1200,
            first_id=103,
            final_id=103,
            previous_id=102,
            bids=[["99.5", "4"]],
        ),
    ]

    reconstructor = DepthReconstructor()
    events = list(reconstructor.run(records))
    snapshot = reconstructor.snapshot()

    assert [event.kind for event in events] == [
        "SYNC_STARTED",
        "SNAPSHOT_APPLIED",
        "DIFF_APPLIED",
        "DIFF_APPLIED",
        "DIFF_APPLIED",
    ]
    assert [event.last_update_id for event in events[1:]] == [100, 101, 102, 103]
    assert snapshot is not None
    assert snapshot.last_update_id == 103
    assert snapshot.bids == {
        Decimal("100"): Decimal("2"),
        Decimal("99.5"): Decimal("4"),
    }
    assert snapshot.asks == {Decimal("102"): Decimal("3")}
    assert reconstructor.counters == {
        "trades_skipped": 0,
        "diffs_applied": 3,
        "diffs_discarded_after_fail": 0,
        "gaps_detected": 0,
        "snapshots_applied": 1,
        "sync_failures": 0,
    }


def test_synthetic_missing_bridge_fails_at_single_attempt() -> None:
    records = [
        _depth(
            event_time=2000,
            first_id=105,
            final_id=105,
            previous_id=104,
        ),
        _snapshot(event_time=2001, final_id=100),
        _depth(
            event_time=2100,
            first_id=106,
            final_id=106,
            previous_id=105,
        ),
    ]

    reconstructor = DepthReconstructor(max_attempts=1)
    events = list(reconstructor.run(records))

    assert [event.kind for event in events] == ["SYNC_STARTED", "SYNC_FAILED"]
    assert reconstructor.snapshot() is None
    assert reconstructor.counters == {
        "trades_skipped": 0,
        "diffs_applied": 0,
        "diffs_discarded_after_fail": 1,
        "gaps_detected": 0,
        "snapshots_applied": 0,
        "sync_failures": 1,
    }


def test_synthetic_pu_gap_resyncs_from_recorded_snapshot() -> None:
    records = [
        _depth(
            event_time=3000,
            first_id=101,
            final_id=101,
            previous_id=100,
        ),
        _snapshot(event_time=3001, final_id=100),
        _depth(
            event_time=3100,
            first_id=102,
            final_id=102,
            previous_id=999,
            bids=[["100", "20"]],
        ),
        _snapshot(
            event_time=3200,
            final_id=101,
            bids=[["100", "10"]],
        ),
        _depth(
            event_time=3300,
            first_id=103,
            final_id=103,
            previous_id=102,
            asks=[["102", "4"]],
        ),
    ]

    reconstructor = DepthReconstructor()
    events = list(reconstructor.run(records))
    snapshot = reconstructor.snapshot()

    assert [event.kind for event in events] == [
        "SYNC_STARTED",
        "SNAPSHOT_APPLIED",
        "DIFF_APPLIED",
        "GAP_DETECTED",
        "RESYNC_STARTED",
        "SNAPSHOT_APPLIED",
        "DIFF_APPLIED",
        "DIFF_APPLIED",
    ]
    assert [event.epoch for event in events[3:]] == [1, 2, 2, 2, 2]
    assert snapshot is not None
    assert snapshot.last_update_id == 103
    assert snapshot.bids[Decimal("100")] == Decimal("20")
    assert reconstructor.counters == {
        "trades_skipped": 0,
        "diffs_applied": 3,
        "diffs_discarded_after_fail": 0,
        "gaps_detected": 1,
        "snapshots_applied": 2,
        "sync_failures": 0,
    }


def test_synthetic_pu_gap_without_snapshot_stays_uninitialized() -> None:
    records = [
        _depth(
            event_time=4000,
            first_id=101,
            final_id=101,
            previous_id=100,
        ),
        _snapshot(event_time=4001, final_id=100),
        _depth(
            event_time=4100,
            first_id=102,
            final_id=102,
            previous_id=999,
        ),
        _depth(
            event_time=4200,
            first_id=103,
            final_id=103,
            previous_id=102,
        ),
    ]

    reconstructor = DepthReconstructor()
    events = list(reconstructor.run(records))

    assert [event.kind for event in events] == [
        "SYNC_STARTED",
        "SNAPSHOT_APPLIED",
        "DIFF_APPLIED",
        "GAP_DETECTED",
        "RESYNC_STARTED",
    ]
    assert reconstructor.snapshot() is None
    assert reconstructor.counters == {
        "trades_skipped": 0,
        "diffs_applied": 1,
        "diffs_discarded_after_fail": 0,
        "gaps_detected": 1,
        "snapshots_applied": 1,
        "sync_failures": 0,
    }


def test_synthetic_stale_diff_is_rejected_and_reconstruction_continues() -> None:
    records = [
        _depth(
            event_time=5000,
            first_id=101,
            final_id=101,
            previous_id=100,
            bids=[["100", "2"]],
        ),
        _snapshot(event_time=5001, final_id=100),
        _depth(
            event_time=5100,
            first_id=101,
            final_id=101,
            previous_id=101,
            bids=[["100", "999"]],
        ),
        _depth(
            event_time=5200,
            first_id=102,
            final_id=102,
            previous_id=101,
            asks=[["102", "3"]],
        ),
    ]

    reconstructor = DepthReconstructor()
    events = list(reconstructor.run(records))
    snapshot = reconstructor.snapshot()

    assert Counter(event.kind for event in events) == {
        "SYNC_STARTED": 1,
        "SNAPSHOT_APPLIED": 1,
        "DIFF_APPLIED": 2,
    }
    assert reconstructor._book.diffs_stale == 1
    assert snapshot is not None
    assert snapshot.last_update_id == 102
    assert snapshot.bids[Decimal("100")] == Decimal("2")
    assert reconstructor.counters["gaps_detected"] == 0


def test_manifest_sha256_mismatch_raises_integrity_error(tmp_path: Path) -> None:
    _write_segment(
        tmp_path,
        "bad.jsonl",
        [{"e": "trade", "p": "100", "q": "1"}],
        started_at="20260730T000000.000000Z",
        sha256_override="0" * 64,
    )

    reader = DepthHistoryReader(tmp_path)
    with pytest.raises(SegmentIntegrityError, match="sha256"):
        reader.segments()


def test_manifestless_segments_are_skipped_and_v1_is_enumerated(
    tmp_path: Path,
) -> None:
    orphan = tmp_path / "orphan.jsonl"
    partial = tmp_path / "tail.jsonl.part"
    orphan.write_text("{}\n", encoding="utf-8")
    partial.write_text("{}\n", encoding="utf-8")
    valid, _ = _write_segment(
        tmp_path,
        "valid.jsonl",
        [{"e": "trade", "p": "100", "q": "1"}],
        started_at="20260730T000001.000000Z",
        schema_version=None,
    )

    reader = DepthHistoryReader(tmp_path)
    segments = reader.segments()

    assert [segment.path for segment in segments] == [valid]
    assert segments[0].manifest["schema_version"] == 1
    assert set(reader.skipped_segments) == {orphan, partial}


def test_float_value_in_record_is_rejected() -> None:
    record = _depth(
        event_time=6000,
        first_id=101,
        final_id=101,
        previous_id=100,
        bids=[[100.0, "1"]],
    )

    with pytest.raises(DepthSyncInputError, match="float value is forbidden"):
        list(DepthReconstructor().run([record]))


def test_real_fixture_matches_verified_bridge_and_final_state() -> None:
    reader = DepthHistoryReader(REAL_FIXTURE_DIR)
    segments = reader.segments()
    assert len(segments) == 2
    assert reader.skipped_segments == []
    assert [segment.started_at for segment in segments] == sorted(
        segment.started_at for segment in segments
    )

    for segment in segments:
        provenance = segment.manifest["_fixture_provenance"]
        assert provenance["source_filename"] == segment.path.name
        assert (
            provenance["source_sha256"]
            == EXPECTED_SOURCE_PROVENANCE[segment.path.name]
        )

    records = list(reader.iter_records())
    snapshot_record = next(
        record for record in records if record["e"] == "depthSnapshot"
    )
    assert snapshot_record["u"] == EXPECTED_SNAPSHOT_U
    bridge_target = EXPECTED_SNAPSHOT_U + 1
    bridge_index = next(
        index
        for index, record in enumerate(records)
        if record["e"] == "depthUpdate"
        and record["U"] <= bridge_target <= record["u"]
    )
    bridge_record = records[bridge_index]
    assert bridge_record["U"] == EXPECTED_BRIDGE_U
    assert bridge_record["u"] == EXPECTED_BRIDGE_FINAL_U

    pre_sync_depths = [
        record
        for record in records[:bridge_index]
        if record["e"] == "depthUpdate"
    ]
    assert len(pre_sync_depths) == 1
    pre_sync_u = pre_sync_depths[0]["u"]

    final_depth_u = next(
        record["u"]
        for record in reversed(records)
        if record["e"] == "depthUpdate"
    )
    reconstructor = DepthReconstructor()
    events = list(reconstructor.run(records))
    event_counts = Counter(event.kind for event in events)
    applied_diff_ids = [
        event.last_update_id
        for event in events
        if event.kind == "DIFF_APPLIED"
    ]
    snapshot = reconstructor.snapshot()

    assert event_counts["SYNC_STARTED"] == 1
    assert event_counts["SNAPSHOT_APPLIED"] == 1
    assert event_counts["DIFF_APPLIED"] == 135
    assert event_counts["GAP_DETECTED"] == 0
    assert event_counts["SYNC_FAILED"] == 0
    assert next(
        event.last_update_id
        for event in events
        if event.kind == "SNAPSHOT_APPLIED"
    ) == EXPECTED_SNAPSHOT_U
    assert applied_diff_ids[0] == EXPECTED_BRIDGE_FINAL_U
    assert pre_sync_u not in applied_diff_ids
    assert snapshot is not None
    assert snapshot.last_update_id == final_depth_u
    _assert_decimal_snapshot(snapshot)
    assert reconstructor.counters == {
        "trades_skipped": 5,
        "diffs_applied": 135,
        "diffs_discarded_after_fail": 0,
        "gaps_detected": 0,
        "snapshots_applied": 1,
        "sync_failures": 0,
    }


def test_real_fixture_sample_states_are_strictly_monotonic_and_decimal() -> None:
    reader = DepthHistoryReader(REAL_FIXTURE_DIR)
    reconstructor = DepthReconstructor()
    samples = list(
        reconstructor.sample_states(
            reader.iter_records(),
            interval_ms=1000,
        )
    )

    assert len(samples) > 1
    sample_times = [sample_time for sample_time, _ in samples]
    assert all(
        later > earlier
        for earlier, later in zip(sample_times, sample_times[1:])
    )
    assert all(
        later - earlier == 1000
        for earlier, later in zip(sample_times, sample_times[1:])
    )
    for _, snapshot in samples:
        _assert_decimal_snapshot(snapshot)
