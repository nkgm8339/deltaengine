"""Integrity-checked deterministic replay for Hook raw journal sessions."""

from __future__ import annotations

import gzip
import hashlib
import json
import lzma
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator


class JournalIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True)
class JournalRecord:
    sequence: int
    record_type: str
    received_time: str
    payload: dict[str, Any]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class JournalReplay:
    """Replay one session only; session sequence numbers always begin at one."""

    def __init__(
        self,
        session_dir: str | Path,
        *,
        allow_invalid: bool = False,
        allow_active: bool = False,
    ) -> None:
        self.session_dir = Path(session_dir)
        if not (self.session_dir / "session_meta.json").is_file():
            raise JournalIntegrityError("session_meta.json is missing")
        summary_path = self.session_dir / "session_summary.json"
        if not summary_path.exists():
            if not allow_active:
                raise JournalIntegrityError(
                    "session has no summary and may be active or crash-incomplete"
                )
            self.summary = None
        else:
            self.summary = json.loads(summary_path.read_text(encoding="utf-8"))
            if not self.summary.get("valid", False) and not allow_invalid:
                raise JournalIntegrityError("session is marked invalid")
        self._closed_segments = self._load_closed_segments()

    def _load_closed_segments(self) -> dict[str, dict[str, Any]]:
        manifest_path = self.session_dir / "manifest_events.jsonl"
        if not manifest_path.exists():
            raise JournalIntegrityError("manifest_events.jsonl is missing")
        closed: dict[str, dict[str, Any]] = {}
        with manifest_path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, 1):
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise JournalIntegrityError(
                        f"invalid manifest JSON at line {line_no}"
                    ) from exc
                if row.get("event") == "SEGMENT_CLOSE":
                    closed[str(row["file"])] = row
        return closed

    def records(self) -> Iterator[JournalRecord]:
        expected = 1
        paths = sorted((
            *self.session_dir.glob("raw-*.jsonl.gz"),
            *self.session_dir.glob("raw-*.jsonl.xz"),
        ))
        for path in paths:
            closed = self._closed_segments.get(path.name)
            if closed is None:
                raise JournalIntegrityError(f"segment is not closed: {path.name}")
            if _sha256(path) != closed.get("sha256"):
                raise JournalIntegrityError(f"segment hash mismatch: {path.name}")
            opener = gzip.open if path.suffix == ".gz" else lzma.open
            with opener(path, "rt", encoding="utf-8") as handle:
                count = 0
                for line_no, line in enumerate(handle, 1):
                    try:
                        raw = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise JournalIntegrityError(
                            f"invalid journal JSON in {path.name}:{line_no}"
                        ) from exc
                    if raw.get("journal_version") != 1:
                        raise JournalIntegrityError("unsupported journal version")
                    sequence = raw.get("sequence")
                    if sequence != expected:
                        raise JournalIntegrityError(
                            f"sequence gap: expected {expected}, found {sequence}"
                        )
                    payload = raw.get("payload")
                    if not isinstance(payload, dict):
                        raise JournalIntegrityError("journal payload is not an object")
                    yield JournalRecord(
                        sequence=sequence,
                        record_type=str(raw.get("record_type")),
                        received_time=str(raw.get("received_time")),
                        payload=payload,
                    )
                    expected += 1
                    count += 1
            if count != closed.get("records"):
                raise JournalIntegrityError(
                    f"segment record count mismatch: {path.name}"
                )
        if self.summary is not None and expected - 1 != self.summary.get("persisted"):
            raise JournalIntegrityError("session persisted count mismatch")

    def replay(self, callback: Callable[[dict[str, Any]], None]) -> int:
        count = 0
        for record in self.records():
            callback(record.payload)
            count += 1
        return count
