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
)

DEPTH_EVENT = {
    "e": "depthUpdate", "E": 1722200000000, "T": 1722200000001, "s": "BTCUSDT",
    "U": 100, "u": 105, "pu": 99,
    "b": [["50000.10", "1.234"]], "a": [["50000.20", "0.500"]],
}
SNAPSHOT_EVENT = {
    "lastUpdateId": 99,
    "bids": [["50000.00", "2.000"]], "asks": [["50000.30", "1.000"]],
}


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
    assert manifest["schema_revision"] == "RAW_DEPTH_HISTORY_V1"
    assert manifest["sha256"] == hashlib.sha256(final.read_bytes()).hexdigest()
    assert manifest["byte_size"] == final.stat().st_size


def test_rotation_by_size(tmp_path):
    rec = DepthHistoryRecorder(tmp_path, "BTCUSDT", max_bytes=10)
    rec.write(DEPTH_EVENT)   # 1件でmax_bytes超過→rotate
    rec.write(DEPTH_EVENT)
    rec.close()
    root = tmp_path / "symbol=BTCUSDT"
    finals = sorted(root.glob("*.jsonl"))
    assert len(finals) == 2
    reasons = sorted(
        json.loads(f.with_suffix(f.suffix + ".manifest.json").read_text())["closed_reason"]
        for f in finals
    )
    assert reasons == ["close", "rotate"]
    assert not list(root.glob("*.part"))


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


def test_tee_writes_to_all_taps(tmp_path):
    seen = []

    class Tap:
        def __init__(self, name):
            self.name = name

        def write(self, obj):
            seen.append(self.name)

    RecorderTee([Tap("a"), None, Tap("b")]).write(DEPTH_EVENT)
    assert seen == ["a", "b"]
