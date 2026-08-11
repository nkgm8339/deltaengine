"""depth_history_recorder のfixture駆動テスト。ライブ接続禁止(R8)。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.acquisition.depth_history_recorder import (
    DepthHistoryRecorder,
    RecorderTee,
    SafeRecorder,
    load_depth_history_manifest,
    parse_depth_history_max_bytes,
)
from src.acquisition.depth_sync import DepthSyncCoordinator, DepthSyncState

DEPTH_EVENT = {
    "e": "depthUpdate", "E": 1722200000000, "T": 1722200000001, "s": "BTCUSDT",
    "U": 100, "u": 105, "pu": 99,
    "b": [["50000.10", "1.234"]], "a": [["50000.20", "0.500"]],
}
SNAPSHOT_EVENT = {
    "lastUpdateId": 99,
    "bids": [["50000.00", "2.000"]], "asks": [["50000.30", "1.000"]],
}
SYNC_SNAPSHOT_EVENT = {
    "e": "depthSnapshot", "E": 1722200000002, "s": "BTCUSDT", "u": 99,
    "b": [["50000.00", "2.000"]], "a": [["50000.30", "1.000"]],
}


@pytest.fixture(autouse=True)
def _clear_depth_history_max_bytes(monkeypatch):
    monkeypatch.delenv("DEPTH_HISTORY_MAX_BYTES", raising=False)


def _read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_passthrough_preserves_strings(tmp_path):
    rec = DepthHistoryRecorder(tmp_path, "BTCUSDT")
    rec.write(DEPTH_EVENT)
    rec.write(SNAPSHOT_EVENT)
    rec.close()
    finals = sorted((tmp_path / "symbol=BTCUSDT").glob("*.jsonl"))
    assert len(finals) == 1
    rows = _read_jsonl(finals[0])
    assert rows[0]["b"] == [["50000.10", "1.234"]]  # 文字列のまま(R3)
    assert rows[0]["pu"] == 99                      # 生フィールド保持(R1/R2)
    assert rows[1]["lastUpdateId"] == 99            # snapshot素通し(D7)
    assert not any(
        isinstance(v, float) for row in rows for v in _flatten(row)
    )


def _flatten(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _flatten(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _flatten(v)
    else:
        yield obj


def test_manifest_matches_content(tmp_path):
    rec = DepthHistoryRecorder(tmp_path, "BTCUSDT")
    rec.write(DEPTH_EVENT)
    rec.close()
    root = tmp_path / "symbol=BTCUSDT"
    final = next(root.glob("*.jsonl"))
    manifest = json.loads(final.with_suffix(final.suffix + ".manifest.json").read_text())
    assert manifest["record_count"] == 1
    assert manifest["closed_reason"] == "close"
    assert manifest["schema_version"] == 2
    assert manifest["schema_revision"] == "RAW_DEPTH_HISTORY_V2"
    assert manifest["sync_events"] == []
    assert manifest["sync_failures"] == []
    assert manifest["sha256"] == hashlib.sha256(final.read_bytes()).hexdigest()
    assert manifest["byte_size"] == final.stat().st_size


def _verified_action():
    coordinator = DepthSyncCoordinator(max_buffered_diffs=8, max_attempts=2)
    request = coordinator.observe_depth(DEPTH_EVENT).request
    return coordinator.observe_snapshot(request, SYNC_SNAPSHOT_EVENT)


def _failed_action():
    coordinator = DepthSyncCoordinator(max_buffered_diffs=8, max_attempts=1)
    missed_bridge = dict(DEPTH_EVENT, U=110, u=115, pu=109)
    request = coordinator.observe_depth(missed_bridge).request
    return coordinator.observe_snapshot(request, SYNC_SNAPSHOT_EVENT)


def test_manifest_v2_contains_verified_sync_event_from_coordinator(tmp_path):
    action = _verified_action()
    assert action.is_verified is True
    rec = DepthHistoryRecorder(tmp_path, "BTCUSDT")
    rec.write(DEPTH_EVENT)
    rec.write(SYNC_SNAPSHOT_EVENT)
    rec.record_sync_action(action)
    rec.close()

    manifest_path = next(
        (tmp_path / "symbol=BTCUSDT").glob("*.manifest.json")
    )
    manifest = load_depth_history_manifest(manifest_path)
    assert manifest["schema_version"] == 2
    assert manifest["sync_events"] == [{
        "epoch": 1,
        "reason": "INITIAL_BOOK_SYNC",
        "snapshot_u": 99,
        "bridge_U": 100,
        "bridge_u": 105,
        "sync_verified": True,
        "attempts": 1,
    }]
    assert manifest["sync_failures"] == []


def test_manifest_v2_records_initial_and_book_resync_epochs(tmp_path):
    coordinator = DepthSyncCoordinator(max_buffered_diffs=8, max_attempts=2)
    initial_request = coordinator.observe_depth(DEPTH_EVENT).request
    initial = coordinator.observe_snapshot(
        initial_request, SYNC_SNAPSHOT_EVENT
    )
    gap_diff = dict(DEPTH_EVENT, U=200, u=205, pu=150)
    resync_request = coordinator.start_resync(gap_diff).request
    resync_snapshot = dict(SYNC_SNAPSHOT_EVENT, u=199)
    resync = coordinator.observe_snapshot(resync_request, resync_snapshot)
    assert initial.is_verified and resync.is_verified

    rec = DepthHistoryRecorder(tmp_path, "BTCUSDT")
    rec.write(DEPTH_EVENT)
    rec.record_sync_action(initial)
    rec.write(gap_diff)
    rec.write(resync_snapshot)
    rec.record_sync_action(resync)
    rec.close()

    manifest_path = next(
        (tmp_path / "symbol=BTCUSDT").glob("*.manifest.json")
    )
    events = load_depth_history_manifest(manifest_path)["sync_events"]
    assert [(event["epoch"], event["reason"]) for event in events] == [
        (1, "INITIAL_BOOK_SYNC"),
        (2, "BOOK_RESYNC"),
    ]


def test_manifest_v1_without_schema_version_loads_backward_compatibly(tmp_path):
    path = tmp_path / "legacy.manifest.json"
    legacy = {
        "schema_revision": "RAW_DEPTH_HISTORY_V1",
        "symbol": "BTCUSDT",
        "record_count": 1,
        "byte_size": 100,
        "sha256": "a" * 64,
        "closed_reason": "close",
    }
    path.write_text(json.dumps(legacy), encoding="utf-8")

    loaded = load_depth_history_manifest(path)

    assert loaded["schema_version"] == 1
    assert loaded["schema_revision"] == "RAW_DEPTH_HISTORY_V1"
    assert "sync_events" not in loaded


def test_sync_failed_enters_failures_not_verified_events(tmp_path):
    action = _failed_action()
    assert action.state is DepthSyncState.SYNC_FAILED
    rec = DepthHistoryRecorder(tmp_path, "BTCUSDT")
    rec.write(dict(DEPTH_EVENT, U=110, u=115, pu=109))
    rec.write(SYNC_SNAPSHOT_EVENT)
    rec.record_sync_action(action)
    rec.close()

    manifest_path = next(
        (tmp_path / "symbol=BTCUSDT").glob("*.manifest.json")
    )
    manifest = load_depth_history_manifest(manifest_path)
    assert manifest["sync_events"] == []
    assert manifest["sync_failures"] == [{
        "epoch": 1,
        "reason": "INITIAL_BOOK_SYNC",
        "failure_reason": action.failure_reason,
        "attempts": 1,
    }]


def test_rotation_by_size(tmp_path):
    # 1レコード=148バイト。max_bytes=200なら2件目書込み後(累積296)で1回rotate、
    # 残り1件はcloseで確定 → セグメント2つ、理由 ["close", "rotate"]。
    rec = DepthHistoryRecorder(tmp_path, "BTCUSDT", max_bytes=200)
    rec.write(DEPTH_EVENT)   # 累積148: rotateなし
    rec.write(DEPTH_EVENT)   # 累積296: rotate(1つ目closed, reason=rotate)
    rec.write(DEPTH_EVENT)   # 2つ目セグメントへ追記
    rec.close()              # 2つ目をclose(reason=close)
    root = tmp_path / "symbol=BTCUSDT"
    finals = sorted(root.glob("*.jsonl"))
    assert len(finals) == 2
    reasons = sorted(
        json.loads(f.with_suffix(f.suffix + ".manifest.json").read_text())["closed_reason"]
        for f in finals
    )
    assert reasons == ["close", "rotate"]
    assert not list(root.glob("*.part"))


def test_rotation_keeps_sync_metadata_on_threshold_segment(tmp_path):
    action = _verified_action()
    rec = DepthHistoryRecorder(tmp_path, "BTCUSDT", max_bytes=1)
    rec.write(DEPTH_EVENT)
    rec.record_sync_action(action)
    rec.write(DEPTH_EVENT)
    rec.close()

    manifests = [
        load_depth_history_manifest(path)
        for path in sorted(
            (tmp_path / "symbol=BTCUSDT").glob("*.manifest.json")
        )
    ]
    assert len(manifests) == 2
    assert [len(manifest["sync_events"]) for manifest in manifests] == [1, 0]
    assert sum(manifest["record_count"] for manifest in manifests) == 2


def test_explicit_max_bytes_overrides_environment_and_rotates(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("DEPTH_HISTORY_MAX_BYTES", "invalid")
    rec = DepthHistoryRecorder(tmp_path, "BTCUSDT", max_bytes=1)
    rec.write(DEPTH_EVENT)
    rec.write(DEPTH_EVENT)
    rec.close()

    assert len(list((tmp_path / "symbol=BTCUSDT").glob("*.jsonl"))) == 2


def test_environment_max_bytes_is_used_when_constructor_is_unspecified(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("DEPTH_HISTORY_MAX_BYTES", "1")
    rec = DepthHistoryRecorder(tmp_path, "BTCUSDT")
    assert rec.max_bytes == 1
    rec.write(DEPTH_EVENT)
    rec.write(DEPTH_EVENT)
    rec.close()

    assert len(list((tmp_path / "symbol=BTCUSDT").glob("*.jsonl"))) == 2


def test_unset_max_bytes_keeps_64_mib_default(tmp_path):
    rec = DepthHistoryRecorder(tmp_path, "BTCUSDT")
    assert rec.max_bytes == 64 * 1024 * 1024
    rec.close()


def test_environment_max_bytes_parser_accepts_positive_integer_text():
    assert parse_depth_history_max_bytes(" 524288 ") == 524288


@pytest.mark.parametrize("value", [0, -1, 1.5, True])
def test_explicit_max_bytes_rejects_non_positive_or_float(tmp_path, value):
    with pytest.raises(ValueError, match="positive integer"):
        DepthHistoryRecorder(tmp_path, "BTCUSDT", max_bytes=value)


@pytest.mark.parametrize("value", ["0", "-1", "1.5", ""])
def test_environment_max_bytes_parser_rejects_invalid_values(value):
    with pytest.raises(ValueError, match="positive integer"):
        parse_depth_history_max_bytes(value)


def test_manifest_v2_contains_no_float_values(tmp_path):
    rec = DepthHistoryRecorder(tmp_path, "BTCUSDT")
    rec.write(DEPTH_EVENT)
    rec.record_sync_action(_verified_action())
    rec.close()
    manifest_path = next(
        (tmp_path / "symbol=BTCUSDT").glob("*.manifest.json")
    )
    manifest = load_depth_history_manifest(manifest_path)

    assert not any(isinstance(value, float) for value in _flatten(manifest))


def test_flush_is_periodic_not_per_write(tmp_path):
    t = {"now": 0.0}
    rec = DepthHistoryRecorder(tmp_path, "BTCUSDT", clock=lambda: t["now"])
    flushes = {"n": 0}
    rec.write(DEPTH_EVENT)  # open
    orig_flush = rec._handle.flush
    rec._handle.flush = lambda: (flushes.__setitem__("n", flushes["n"] + 1), orig_flush())[1]
    rec.write(DEPTH_EVENT)          # t=0: 周期未達→flushなし
    assert flushes["n"] == 0
    t["now"] = 1.5
    rec.write(DEPTH_EVENT)          # 周期到達→flush 1回
    assert flushes["n"] == 1


def test_safe_recorder_isolates_failure(tmp_path):
    class Boom:
        def write(self, obj):
            raise OSError("disk gone")

        def close(self):
            pass

    safe = SafeRecorder(Boom())
    safe.write(DEPTH_EVENT)   # 例外は伝播しない(R5)
    assert safe.disabled is True
    assert "disk gone" in safe.error
    safe.write(DEPTH_EVENT)   # 以後は静かにno-op
    safe.close()


def test_safe_recorder_forwards_sync_action(tmp_path):
    inner = DepthHistoryRecorder(tmp_path, "BTCUSDT")
    safe = SafeRecorder(inner)
    safe.write(DEPTH_EVENT)
    safe.record_sync_action(_verified_action())
    safe.close()

    manifest_path = next(
        (tmp_path / "symbol=BTCUSDT").glob("*.manifest.json")
    )
    assert len(load_depth_history_manifest(manifest_path)["sync_events"]) == 1


def test_tee_writes_to_all_taps(tmp_path):
    seen = []

    class Tap:
        def __init__(self, name):
            self.name = name

        def write(self, obj):
            seen.append(self.name)

    RecorderTee([Tap("a"), None, Tap("b")]).write(DEPTH_EVENT)
    assert seen == ["a", "b"]


def test_tee_close_is_noop():
    closed = []

    class Tap:
        def close(self):
            closed.append(True)

    tee = RecorderTee([Tap()])
    tee.close()  # 呼んでも例外なし、配下tapは所有者が個別にcloseする
    assert closed == []


def test_tee_forwards_sync_action_only_to_capable_taps():
    observed = []

    class SyncTap:
        def record_sync_action(self, action):
            observed.append(action)

    RecorderTee([object(), SyncTap()]).record_sync_action(_verified_action())
    assert len(observed) == 1
    assert observed[0].is_verified is True
