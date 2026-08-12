"""Durable capture coverage and bounded deadline-extension ledger."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


STREAMS = ("full", "liquidation")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("coverage timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def _utc_text(value: datetime) -> str:
    return _utc(value).isoformat()


def _parse_utc(value: str) -> datetime:
    return _utc(datetime.fromisoformat(value))


class CaptureCoverageLedger:
    """Append-only, fsync-backed heartbeat and deadline-extension records."""

    def __init__(
        self,
        campaign_dir: str | Path,
        *,
        original_deadlines: Mapping[str, datetime],
        extension_caps: Mapping[str, timedelta],
    ) -> None:
        self.campaign_dir = Path(campaign_dir)
        self.campaign_dir.mkdir(parents=True, exist_ok=True)
        self.coverage_path = self.campaign_dir / "coverage_events.jsonl"
        self.extension_path = self.campaign_dir / "deadline_extension_events.jsonl"
        self._original = {
            stream: _utc(original_deadlines[stream]) for stream in STREAMS
        }
        self._caps = {
            stream: max(timedelta(0), extension_caps[stream]) for stream in STREAMS
        }
        self._lock = threading.Lock()

    @staticmethod
    def _read(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        lines = path.read_bytes().splitlines(keepends=True)
        for index, raw_line in enumerate(lines):
            if not raw_line.endswith(b"\n"):
                if index == len(lines) - 1:
                    break
                raise ValueError(f"unterminated ledger line: {path}:{index + 1}")
            rows.append(json.loads(raw_line.decode("utf-8")))
        return rows

    def _append(self, path: Path, row: dict[str, Any]) -> None:
        line = json.dumps(
            row,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        )
        with self._lock:
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line + "\n")
                handle.flush()
                os.fsync(handle.fileno())

    @staticmethod
    def _event_id(
        stream: str,
        started_at: datetime,
        ended_at: datetime,
        reason: str,
    ) -> str:
        canonical = "|".join(
            (stream, _utc_text(started_at), _utc_text(ended_at), reason)
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def record_extension(
        self,
        stream: str,
        *,
        started_at: datetime,
        ended_at: datetime,
        reason: str,
        evidence: Mapping[str, Any] | None = None,
        recorded_at: datetime | None = None,
    ) -> bool:
        if stream not in STREAMS:
            raise ValueError(f"unknown coverage stream: {stream}")
        start = _utc(started_at)
        end = _utc(ended_at)
        if end <= start:
            raise ValueError("deadline extension interval must be positive")
        event_id = self._event_id(stream, start, end, reason)
        if any(
            row.get("event_id") == event_id for row in self._read(self.extension_path)
        ):
            return False
        self._append(
            self.extension_path,
            {
                "ledger_version": 1,
                "event": "DEADLINE_EXTENSION",
                "event_id": event_id,
                "stream": stream,
                "started_at": _utc_text(start),
                "ended_at": _utc_text(end),
                "duration_seconds": (end - start).total_seconds(),
                "reason": reason,
                "evidence": dict(evidence or {}),
                "recorded_at": _utc_text(recorded_at or datetime.now(timezone.utc)),
            },
        )
        return True

    def _last_coverage_by_stream(self) -> dict[str, dict[str, Any]]:
        last: dict[str, dict[str, Any]] = {}
        for row in self._read(self.coverage_path):
            stream = row.get("stream")
            if stream in STREAMS:
                last[str(stream)] = row
        return last

    def recover_downtime(self, opened_at: datetime) -> None:
        opened = _utc(opened_at)
        for stream, row in self._last_coverage_by_stream().items():
            event_time = _parse_utc(str(row["event_time"]))
            if event_time >= opened:
                continue
            self.record_extension(
                stream,
                started_at=event_time,
                ended_at=opened,
                reason="CAPTURE_PROCESS_UNAVAILABLE",
                evidence={
                    "previous_coverage_event": row.get("event"),
                    "previous_event_id": row.get("event_id"),
                },
                recorded_at=opened,
            )

    def record_start(
        self,
        streams: tuple[str, ...],
        *,
        event_time: datetime,
        session_ids: Mapping[str, str],
    ) -> None:
        when = _utc(event_time)
        for stream in streams:
            self._append(
                self.coverage_path,
                {
                    "ledger_version": 1,
                    "event": "COVERAGE_START",
                    "event_id": hashlib.sha256(
                        f"{stream}|start|{_utc_text(when)}|{session_ids[stream]}".encode(
                            "utf-8"
                        )
                    ).hexdigest(),
                    "stream": stream,
                    "event_time": _utc_text(when),
                    "session_id": session_ids[stream],
                },
            )

    def record_heartbeat(
        self,
        stream_stats: Mapping[str, Mapping[str, Any]],
        *,
        event_time: datetime,
    ) -> None:
        when = _utc(event_time)
        for stream, stats in stream_stats.items():
            if stream not in STREAMS:
                continue
            self._append(
                self.coverage_path,
                {
                    "ledger_version": 1,
                    "event": "COVERAGE_HEARTBEAT",
                    "event_id": hashlib.sha256(
                        f"{stream}|heartbeat|{_utc_text(when)}".encode("utf-8")
                    ).hexdigest(),
                    "stream": stream,
                    "event_time": _utc_text(when),
                    "session_id": stats.get("session_id"),
                    "accepting": bool(stats.get("accepting")),
                    "accepted": int(stats.get("accepted", 0)),
                    "persisted": int(stats.get("persisted", 0)),
                    "durably_committed": int(stats.get("durably_committed", 0)),
                    "dropped_queue_full": int(stats.get("dropped_queue_full", 0)),
                    "rejected_disk_low": int(stats.get("rejected_disk_low", 0)),
                    "writer_error": stats.get("writer_error"),
                },
            )

    def record_stop(
        self,
        stream_stats: Mapping[str, Mapping[str, Any]],
        *,
        event_time: datetime,
    ) -> None:
        when = _utc(event_time)
        for stream, stats in stream_stats.items():
            if stream not in STREAMS:
                continue
            self._append(
                self.coverage_path,
                {
                    "ledger_version": 1,
                    "event": "COVERAGE_STOP",
                    "event_id": hashlib.sha256(
                        f"{stream}|stop|{_utc_text(when)}|{stats.get('session_id')}".encode(
                            "utf-8"
                        )
                    ).hexdigest(),
                    "stream": stream,
                    "event_time": _utc_text(when),
                    "session_id": stats.get("session_id"),
                    "accepted": int(stats.get("accepted", 0)),
                    "persisted": int(stats.get("persisted", 0)),
                    "durably_committed": int(stats.get("durably_committed", 0)),
                    "dropped_queue_full": int(stats.get("dropped_queue_full", 0)),
                    "rejected_disk_low": int(stats.get("rejected_disk_low", 0)),
                    "writer_error": stats.get("writer_error"),
                },
            )

    def extension_seconds(self, stream: str) -> float:
        if stream not in STREAMS:
            raise ValueError(f"unknown coverage stream: {stream}")
        intervals = sorted(
            (
                _parse_utc(str(row["started_at"])),
                _parse_utc(str(row["ended_at"])),
            )
            for row in self._read(self.extension_path)
            if row.get("stream") == stream
            and row.get("event") == "DEADLINE_EXTENSION"
        )
        merged: list[tuple[datetime, datetime]] = []
        for start, end in intervals:
            if not merged or start > merged[-1][1]:
                merged.append((start, end))
            else:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        total = sum((end - start).total_seconds() for start, end in merged)
        return min(total, self._caps[stream].total_seconds())

    def effective_deadline(self, stream: str) -> datetime:
        return self._original[stream] + timedelta(
            seconds=self.extension_seconds(stream)
        )

    def stats(self) -> dict[str, Any]:
        return {
            stream: {
                "original_deadline": _utc_text(self._original[stream]),
                "extension_seconds": self.extension_seconds(stream),
                "extension_cap_seconds": self._caps[stream].total_seconds(),
                "effective_deadline": _utc_text(self.effective_deadline(stream)),
            }
            for stream in STREAMS
        }
