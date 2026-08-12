"""Append-only JSONL ledger for manual HFM execution records."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .manual_execution_log import ManualExecutionRecord, ManualExecutionStatus

_TIME_FIELDS = (
    "checkpoint_time", "signal_displayed_time", "decision_time", "order_time",
    "fill_time", "exit_time",
)


def encode_record(record: ManualExecutionRecord) -> str:
    payload = record.to_row()
    for field in _TIME_FIELDS:
        value = payload[field]
        payload[field] = value.isoformat() if isinstance(value, datetime) else None
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def decode_record(line: str) -> ManualExecutionRecord:
    try:
        payload: dict[str, Any] = json.loads(line)
        for field in _TIME_FIELDS:
            value = payload.get(field)
            payload[field] = datetime.fromisoformat(value) if value else None
        payload["status"] = ManualExecutionStatus(str(payload["status"]))
        payload.pop("execution_delay_ms", None)
        for field in ("entry_price", "entry_bid", "entry_ask", "exit_price"):
            if payload.get(field) is not None:
                payload[field] = float(payload[field])
        payload["window_sec"] = int(payload["window_sec"])
        return ManualExecutionRecord(**payload)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("invalid manual execution record") from exc


def load_records(path: Path) -> tuple[ManualExecutionRecord, ...]:
    if not path.exists():
        return ()
    records: list[ManualExecutionRecord] = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = decode_record(line)
            except ValueError as exc:
                raise ValueError(f"invalid ledger line {line_number}") from exc
            if record.record_id in seen:
                raise ValueError(f"duplicate record_id on line {line_number}: {record.record_id}")
            seen.add(record.record_id)
            records.append(record)
    return tuple(records)


def append_record(path: Path, record: ManualExecutionRecord) -> None:
    existing = load_records(path)
    if any(item.record_id == record.record_id for item in existing):
        raise ValueError(f"record_id already exists: {record.record_id}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(encode_record(record) + "\n")
