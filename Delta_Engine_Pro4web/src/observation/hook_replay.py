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


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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
        self._closed_segments, self._frame_commits = self._load_manifest()
        self.uncommitted_tail_bytes = self._measure_uncommitted_tail()

    def _load_manifest(
        self,
    ) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
        manifest_path = self.session_dir / "manifest_events.jsonl"
        if not manifest_path.exists():
            raise JournalIntegrityError("manifest_events.jsonl is missing")
        closed: dict[str, dict[str, Any]] = {}
        frames: list[dict[str, Any]] = []
        lines = manifest_path.read_bytes().splitlines(keepends=True)
        for index, raw_line in enumerate(lines):
            line_no = index + 1
            if not raw_line.endswith(b"\n"):
                if index == len(lines) - 1 and self.summary is None:
                    break
                raise JournalIntegrityError(
                    f"unterminated manifest line at {line_no}"
                )
            try:
                row = json.loads(raw_line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise JournalIntegrityError(
                    f"invalid manifest JSON at line {line_no}"
                ) from exc
            if row.get("event") == "SEGMENT_CLOSE":
                closed[str(row["file"])] = row
            elif row.get("event") == "FRAME_COMMIT":
                frames.append(row)
        return closed, frames

    def _measure_uncommitted_tail(self) -> int:
        committed_end: dict[str, int] = {}
        for row in self._frame_commits:
            name = str(row.get("file"))
            end = int(row.get("offset", 0)) + int(row.get("compressed_bytes", 0))
            committed_end[name] = max(committed_end.get(name, 0), end)
        tail = 0
        for path in self.session_dir.glob("raw-*.jsonl.xz"):
            if path.name in committed_end:
                tail += max(0, path.stat().st_size - committed_end[path.name])
        return tail

    @staticmethod
    def _record(raw: dict[str, Any], expected: int, location: str) -> JournalRecord:
        if raw.get("journal_version") != 1:
            raise JournalIntegrityError("unsupported journal version")
        sequence = raw.get("sequence")
        if sequence != expected:
            raise JournalIntegrityError(
                f"sequence gap: expected {expected}, found {sequence}"
            )
        payload = raw.get("payload")
        if not isinstance(payload, dict):
            raise JournalIntegrityError(f"journal payload is not an object: {location}")
        return JournalRecord(
            sequence=sequence,
            record_type=str(raw.get("record_type")),
            received_time=str(raw.get("received_time")),
            payload=payload,
        )

    def _frame_records(self) -> Iterator[JournalRecord]:
        expected = 1
        for frame_no, row in enumerate(self._frame_commits, 1):
            path = self.session_dir / str(row.get("file"))
            if not path.is_file():
                raise JournalIntegrityError(f"committed frame file is missing: {path.name}")
            try:
                offset = int(row["offset"])
                length = int(row["compressed_bytes"])
                declared_records = int(row["records"])
            except (KeyError, TypeError, ValueError) as exc:
                raise JournalIntegrityError(f"invalid frame metadata: {frame_no}") from exc
            with path.open("rb") as handle:
                handle.seek(offset)
                compressed = handle.read(length)
            if len(compressed) != length:
                raise JournalIntegrityError(f"committed frame is truncated: {frame_no}")
            if _sha256_bytes(compressed) != row.get("frame_sha256"):
                raise JournalIntegrityError(f"frame hash mismatch: {frame_no}")
            try:
                decoded = lzma.decompress(compressed).decode("utf-8")
            except (lzma.LZMAError, UnicodeDecodeError) as exc:
                raise JournalIntegrityError(f"frame decode failed: {frame_no}") from exc
            lines = decoded.splitlines()
            if len(lines) != declared_records:
                raise JournalIntegrityError(f"frame record count mismatch: {frame_no}")
            if declared_records:
                if row.get("first_sequence") != expected:
                    raise JournalIntegrityError(f"frame first sequence mismatch: {frame_no}")
                if row.get("last_sequence") != expected + declared_records - 1:
                    raise JournalIntegrityError(f"frame last sequence mismatch: {frame_no}")
            for line_no, line in enumerate(lines, 1):
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise JournalIntegrityError(
                        f"invalid journal JSON in frame {frame_no}:{line_no}"
                    ) from exc
                record = self._record(raw, expected, f"frame {frame_no}:{line_no}")
                yield record
                expected += 1
        if self.summary is not None:
            committed = self.summary.get(
                "durably_committed", self.summary.get("persisted")
            )
            if expected - 1 != committed:
                raise JournalIntegrityError("session committed count mismatch")

    def records(self) -> Iterator[JournalRecord]:
        if self._frame_commits:
            yield from self._frame_records()
            return
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
                    yield self._record(raw, expected, f"{path.name}:{line_no}")
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
