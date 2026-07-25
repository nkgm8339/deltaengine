from dataclasses import dataclass
import json

from src.orderflow.shadow_signal_recorder import ShadowSignalRecorder


@dataclass
class Snapshot:
    window_sec: int
    state: str


def test_recorder_writes_shadow_without_order(tmp_path):
    path = tmp_path / "shadow.jsonl"
    count = ShadowSignalRecorder(path).append([Snapshot(300, "BUY_EFFECTIVE")])
    assert count == 1
    row = json.loads(path.read_text(encoding="utf-8"))
    assert row["status"] == "SHADOW"
    assert row["order_created"] is False
    assert row["event"]["window_sec"] == 300
