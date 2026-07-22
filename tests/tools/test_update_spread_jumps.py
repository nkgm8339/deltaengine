"""Tests for the synchronized spread-jump export."""

from __future__ import annotations

import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path


_TOOL = Path(__file__).resolve().parents[2] / "tools" / "update_spread_jumps.py"
spec = importlib.util.spec_from_file_location("update_spread_jumps", _TOOL)
update_spread_jumps = importlib.util.module_from_spec(spec)
sys.modules["update_spread_jumps"] = update_spread_jumps
spec.loader.exec_module(update_spread_jumps)


def _snapshot(
    event_ms: int,
    update_id: int,
    *,
    bids: list[list[str]] | None = None,
    asks: list[list[str]] | None = None,
) -> dict:
    return {
        "e": "depthSnapshot",
        "E": event_ms,
        "s": "BTCUSDT",
        "u": update_id,
        "b": bids or [["98", "2"], ["99", "1"]],
        "a": asks or [["100", "1"], ["110", "2"]],
    }


def _diff(
    event_ms: int,
    update_id: int,
    previous_id: int,
    *,
    bids: list[list[str]] | None = None,
    asks: list[list[str]] | None = None,
) -> dict:
    return {
        "e": "depthUpdate",
        "E": event_ms,
        "s": "BTCUSDT",
        "U": update_id,
        "u": update_id,
        "pu": previous_id,
        "b": bids or [],
        "a": asks or [],
    }


def _write(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )


def _valid_rows() -> list[dict]:
    return [
        _snapshot(1_000, 100),
        _diff(2_000, 101, 100, bids=[["98", "3"]]),
        _diff(3_000, 102, 101, bids=[["98", "4"]]),
        _diff(4_000, 103, 102, asks=[["100", "0"], ["109", "1"]]),
        _diff(5_000, 104, 103, asks=[["100", "1"]]),
    ]


def test_reconstructs_top_of_book_and_applies_zero_quantity_deletes(tmp_path):
    source = tmp_path / "board.jsonl"
    _write(source, _valid_rows())

    frame = update_spread_jumps.load_board_frame(source, window=3)

    assert frame.snapshots == 1
    assert frame.diffs_applied == 4
    assert frame.gaps == 0
    assert frame.rows[0].bids_top[0][0] == Decimal("99")
    assert frame.rows[0].bids_top[1][0] == Decimal("98")
    assert frame.rows[3].best_ask == Decimal("109")
    assert frame.rows[3].spread == Decimal("10")
    assert frame.rows[4].best_ask == Decimal("100")


def test_diff_only_recording_is_rejected_and_exports_are_preserved(tmp_path, capsys):
    source = tmp_path / "diff-only.jsonl"
    jsonl = tmp_path / "spread_jumps.jsonl"
    csv = tmp_path / "spread_jumps.csv"
    _write(source, [_diff(1_000, 1, 0), _diff(2_000, 2, 1)])
    jsonl.write_text("trusted-old-jsonl\n", encoding="utf-8")
    csv.write_text("trusted-old-csv\n", encoding="utf-8")

    result = update_spread_jumps.main([
        "--source", str(source),
        "--jsonl", str(jsonl),
        "--csv", str(csv),
    ])

    assert result == 2
    assert jsonl.read_text(encoding="utf-8") == "trusted-old-jsonl\n"
    assert csv.read_text(encoding="utf-8") == "trusted-old-csv\n"
    assert "no depthSnapshot" in capsys.readouterr().err


def test_gap_suppresses_diffs_until_a_new_snapshot(tmp_path):
    source = tmp_path / "resync.jsonl"
    _write(source, [
        _snapshot(1_000, 100),
        _diff(2_000, 101, 100),
        _diff(3_000, 200, 999),
        _diff(4_000, 201, 200),
        _snapshot(5_000, 300),
        _diff(6_000, 301, 300),
    ])

    frame = update_spread_jumps.load_board_frame(source)

    assert frame.snapshots == 2
    assert frame.gaps == 1
    assert frame.diffs_skipped_unsynced == 1
    assert frame.diffs_applied == 2
    assert len(frame.rows) == 4


def test_update_spread_jumps_writes_only_reconstructed_candidates(tmp_path):
    source = tmp_path / "board.jsonl"
    jsonl = tmp_path / "spread_jumps.jsonl"
    csv = tmp_path / "spread_jumps.csv"
    _write(source, _valid_rows())

    result = update_spread_jumps.main([
        "--source", str(source),
        "--jsonl", str(jsonl),
        "--csv", str(csv),
        "--window", "3",
        "--threshold-z", "1.0",
    ])

    assert result == 0
    records = [
        json.loads(line)
        for line in jsonl.read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 1
    assert records[0]["best_bid"] == "99"
    assert records[0]["best_ask"] == "109"
    assert records[0]["spread"] == "10"
    assert records[0]["ma_window"] == 3
    assert records[0]["spread_ma"] == "4"
    assert records[0]["bids_top5"][0] == ["99", "1"]
    assert csv.is_file()
