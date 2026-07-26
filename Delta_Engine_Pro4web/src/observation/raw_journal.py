"""Bounded, append-only raw capture with explicit gaps and fixed deadlines."""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import lzma
import os
import queue
import shutil
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from src.orderflow.hooks.config import HookObserverConfig

logger = logging.getLogger("observation.raw_journal")

_STOP = object()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("campaign timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _write_new_json(path: Path, value: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(
            value,
            handle,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record_type(payload: dict[str, Any]) -> str:
    event_type = payload.get("e")
    if event_type == "depthSnapshot":
        return "DEPTH_SNAPSHOT"
    if event_type == "depthUpdate":
        return "DEPTH_UPDATE"
    if event_type in {"aggTrade", "trade"}:
        return "TRADE"
    if event_type == "forceOrder":
        return "LIQUIDATION"
    if payload.get("lastUpdateId") is not None and payload.get("bids") is not None:
        return "DEPTH_SNAPSHOT"
    return "RAW"


@dataclass(frozen=True)
class _QueuedRecord:
    sequence: int
    received_time: datetime
    payload: dict[str, Any]


class AppendOnlyRawJournal:
    """One process session of one capture stream.

    Every file name is session-unique and created with exclusive-create mode.
    Queue overflow, disk guard activation, writer errors, and missing graceful
    close are therefore visible integrity failures rather than silent loss.
    """

    def __init__(
        self,
        *,
        stream_root: Path,
        campaign_id: str,
        config_hash: str,
        mode: str,
        deadline: datetime,
        queue_depth: int,
        compression: str,
        compression_level: int,
        flush_interval_sec: int,
        min_free_bytes: int,
        include: Callable[[dict[str, Any]], bool],
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.mode = mode
        self.deadline = deadline.astimezone(timezone.utc)
        self._include = include
        self._now = now
        self._compression = compression
        self._compression_level = compression_level
        self._flush_interval_sec = flush_interval_sec
        self._min_free_bytes = min_free_bytes
        self._queue: queue.Queue[object] = queue.Queue(maxsize=queue_depth)
        self._state_lock = threading.Lock()
        self._manifest_lock = threading.Lock()
        self._closed = False
        self._accepting = True
        self._sequence = 0
        self.accepted = 0
        self.persisted = 0
        self.dropped_queue_full = 0
        self.rejected_disk_low = 0
        self.rejected_deadline = 0
        self.writer_error: str | None = None
        self.high_watermark = 0
        self._last_disk_check_monotonic = 0.0
        self._disk_ok = True
        self._gap_manifested = 0
        self._summary_written = False
        self._finalize_lock = threading.Lock()

        stream_root.mkdir(parents=True, exist_ok=True)
        session_stamp = self._now().strftime("%Y%m%dT%H%M%S.%fZ")
        self.session_id = f"session-{session_stamp}-{uuid.uuid4().hex[:8]}"
        self.session_dir = stream_root / self.session_id
        self.session_dir.mkdir(parents=False, exist_ok=False)
        self._manifest_path = self.session_dir / "manifest_events.jsonl"
        self._manifest_handle = self._manifest_path.open(
            "x", encoding="utf-8", newline="\n"
        )
        _write_new_json(
            self.session_dir / "session_meta.json",
            {
                "journal_version": 1,
                "campaign_id": campaign_id,
                "config_hash": config_hash,
                "mode": mode,
                "session_id": self.session_id,
                "started_at": _utc_text(self._now()),
                "deadline": _utc_text(self.deadline),
                "compression": compression,
                "compression_level": compression_level,
            },
        )
        self._manifest(
            "SESSION_START",
            campaign_id=campaign_id,
            config_hash=config_hash,
            deadline=_utc_text(self.deadline),
        )
        self._thread = threading.Thread(
            target=self._writer_loop,
            name=f"raw-journal-{mode}",
            daemon=True,
        )
        self._thread.start()

    @property
    def written(self) -> int:
        return self.persisted

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    @property
    def accepting(self) -> bool:
        with self._state_lock:
            return self._accepting and not self._closed

    def _manifest(self, event: str, **details: Any) -> None:
        row = {
            "journal_version": 1,
            "event": event,
            "recorded_at": _utc_text(self._now()),
            **details,
        }
        line = json.dumps(
            row,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        )
        with self._manifest_lock:
            self._manifest_handle.write(line + "\n")
            self._manifest_handle.flush()

    def _check_disk(self) -> bool:
        current = time.monotonic()
        if current - self._last_disk_check_monotonic < 1.0:
            return self._disk_ok
        self._last_disk_check_monotonic = current
        free = shutil.disk_usage(self.session_dir).free
        self._disk_ok = free >= self._min_free_bytes
        if not self._disk_ok:
            with self._state_lock:
                was_accepting = self._accepting
                self._accepting = False
            if was_accepting:
                self._manifest(
                    "DISK_GUARD_STOP",
                    free_bytes=free,
                    min_free_bytes=self._min_free_bytes,
                )
                logger.error(
                    "Hook raw capture %s stopped by disk guard: free=%d minimum=%d",
                    self.mode,
                    free,
                    self._min_free_bytes,
                )
        return self._disk_ok

    def write(self, obj: dict[str, Any]) -> None:
        if not isinstance(obj, dict) or not self._include(obj):
            return
        received = self._now()
        with self._state_lock:
            if self._closed:
                return
            if received >= self.deadline:
                self.rejected_deadline += 1
                was_accepting = self._accepting
                self._accepting = False
            else:
                was_accepting = False
            accepting = self._accepting
        if was_accepting:
            self._manifest("CAMPAIGN_DEADLINE_REACHED", deadline=_utc_text(self.deadline))
        if not accepting:
            return
        if not self._check_disk():
            with self._state_lock:
                self.rejected_disk_low += 1
            return
        with self._state_lock:
            self._sequence += 1
            record = _QueuedRecord(self._sequence, received, dict(obj))
        try:
            self._queue.put_nowait(record)
        except queue.Full:
            with self._state_lock:
                self.dropped_queue_full += 1
            return
        with self._state_lock:
            self.accepted += 1
            self.high_watermark = max(self.high_watermark, self._queue.qsize())

    def _writer_loop(self) -> None:
        segment_hour: str | None = None
        segment_path: Path | None = None
        raw_handle: Any = None
        compression_handle: Any = None
        text_handle: Any = None
        segment_count = 0
        last_flush = time.monotonic()

        def close_segment() -> None:
            nonlocal raw_handle, compression_handle, text_handle, segment_path, segment_count
            if text_handle is None or segment_path is None:
                return
            text_handle.flush()
            compression_handle.flush()
            text_handle.close()
            raw_handle.flush()
            os.fsync(raw_handle.fileno())
            raw_handle.close()
            raw_handle = None
            compression_handle = None
            text_handle = None
            digest = _sha256(segment_path)
            self._manifest(
                "SEGMENT_CLOSE",
                file=segment_path.name,
                records=segment_count,
                bytes=segment_path.stat().st_size,
                sha256=digest,
            )

        try:
            while True:
                timeout = max(0.05, min(1.0, float(self._flush_interval_sec)))
                try:
                    item = self._queue.get(timeout=timeout)
                except queue.Empty:
                    item = None
                if item is _STOP:
                    break
                if (
                    item is None
                    and self._now() >= self.deadline
                    and self._queue.empty()
                ):
                    with self._state_lock:
                        was_accepting = self._accepting
                        self._accepting = False
                    if was_accepting:
                        self._manifest(
                            "CAMPAIGN_DEADLINE_REACHED",
                            deadline=_utc_text(self.deadline),
                        )
                    break
                if isinstance(item, _QueuedRecord):
                    hour = item.received_time.strftime("%Y%m%dT%H")
                    if hour != segment_hour:
                        close_segment()
                        segment_hour = hour
                        segment_count = 0
                        extension = "gz" if self._compression == "gzip" else "xz"
                        segment_path = self.session_dir / f"raw-{hour}.jsonl.{extension}"
                        raw_handle = segment_path.open("xb")
                        if self._compression == "gzip":
                            compression_handle = gzip.GzipFile(
                                fileobj=raw_handle,
                                mode="wb",
                                compresslevel=self._compression_level,
                                mtime=0,
                            )
                        else:
                            compression_handle = lzma.LZMAFile(
                                raw_handle, mode="wb", preset=self._compression_level
                            )
                        import io

                        text_handle = io.TextIOWrapper(
                            compression_handle, encoding="utf-8", newline="\n"
                        )
                        self._manifest("SEGMENT_OPEN", file=segment_path.name)
                    envelope = {
                        "journal_version": 1,
                        "sequence": item.sequence,
                        "record_type": _record_type(item.payload),
                        "received_time": _utc_text(item.received_time),
                        "payload": item.payload,
                    }
                    text_handle.write(
                        json.dumps(
                            envelope,
                            sort_keys=True,
                            separators=(",", ":"),
                            ensure_ascii=False,
                            default=str,
                        )
                        + "\n"
                    )
                    segment_count += 1
                    with self._state_lock:
                        self.persisted += 1
                now_mono = time.monotonic()
                if text_handle is not None and now_mono - last_flush >= self._flush_interval_sec:
                    text_handle.flush()
                    compression_handle.flush()
                    last_flush = now_mono
                with self._state_lock:
                    dropped = self.dropped_queue_full
                if dropped != self._gap_manifested:
                    self._manifest(
                        "JOURNAL_GAP",
                        reason="QUEUE_FULL",
                        dropped_total=dropped,
                    )
                    self._gap_manifested = dropped
        except Exception as exc:
            self.writer_error = f"{type(exc).__name__}: {exc}"
            logger.exception("Hook raw capture writer failed for %s", self.mode)
            with self._state_lock:
                self._accepting = False
            try:
                self._manifest("WRITER_ERROR", error=self.writer_error)
            except Exception:
                logger.exception("Hook raw capture manifest write also failed")
        finally:
            try:
                close_segment()
            except Exception as exc:
                if self.writer_error is None:
                    self.writer_error = f"{type(exc).__name__}: {exc}"
                logger.exception("Hook raw capture segment close failed for %s", self.mode)
            self._finalize_session()

    def _finalize_session(self) -> None:
        with self._finalize_lock:
            if self._summary_written:
                return
            valid = (
                self.writer_error is None
                and self.dropped_queue_full == 0
                and self.rejected_disk_low == 0
            )
            self._manifest(
                "SESSION_END",
                accepted=self.accepted,
                persisted=self.persisted,
                dropped_queue_full=self.dropped_queue_full,
                rejected_disk_low=self.rejected_disk_low,
                rejected_deadline=self.rejected_deadline,
                valid=valid,
                writer_error=self.writer_error,
            )
            with self._manifest_lock:
                self._manifest_handle.flush()
                os.fsync(self._manifest_handle.fileno())
                self._manifest_handle.close()
            _write_new_json(
                self.session_dir / "session_summary.json",
                {
                    "journal_version": 1,
                    "session_id": self.session_id,
                    "mode": self.mode,
                    "closed_at": _utc_text(self._now()),
                    "accepted": self.accepted,
                    "persisted": self.persisted,
                    "dropped_queue_full": self.dropped_queue_full,
                    "rejected_disk_low": self.rejected_disk_low,
                    "rejected_deadline": self.rejected_deadline,
                    "high_watermark": self.high_watermark,
                    "writer_error": self.writer_error,
                    "valid": valid,
                    "manifest_sha256": _sha256(self._manifest_path),
                },
            )
            self._summary_written = True

    def close(self) -> None:
        with self._state_lock:
            if self._closed:
                return
            self._closed = True
            self._accepting = False
        if self._thread.is_alive():
            try:
                self._queue.put(_STOP, timeout=5)
            except queue.Full:
                self.writer_error = self.writer_error or "stop marker queue timeout"
        self._thread.join(timeout=30)
        if self._thread.is_alive():
            self.writer_error = self.writer_error or "writer did not stop within 30 seconds"
            logger.error("Hook raw capture writer did not stop for %s", self.mode)

    def stats(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "session_id": self.session_id,
            "deadline": _utc_text(self.deadline),
            "accepting": self.accepting,
            "accepted": self.accepted,
            "persisted": self.persisted,
            "pending": self.pending,
            "high_watermark": self.high_watermark,
            "dropped_queue_full": self.dropped_queue_full,
            "rejected_disk_low": self.rejected_disk_low,
            "rejected_deadline": self.rejected_deadline,
            "writer_error": self.writer_error,
        }


class CaptureCampaign:
    """Fan-out recorder for a finite full stream and a longer liquidation stream."""

    def __init__(
        self,
        *,
        campaign_dir: Path,
        campaign_id: str,
        config_hash: str,
        full_capture_until: datetime,
        liquidation_capture_until: datetime,
        journals: tuple[AppendOnlyRawJournal, ...],
    ) -> None:
        self.campaign_dir = campaign_dir
        self.campaign_id = campaign_id
        self.config_hash = config_hash
        self.full_capture_until = full_capture_until
        self.liquidation_capture_until = liquidation_capture_until
        self._journals = journals
        self._closed = False

    @classmethod
    def open(
        cls,
        config: HookObserverConfig,
        *,
        now: datetime | None = None,
    ) -> "CaptureCampaign":
        opened_at = (now or _utc_now()).astimezone(timezone.utc)
        campaign_dir = config.capture.root / config.capture.campaign_id
        campaign_dir.mkdir(parents=True, exist_ok=True)
        meta_path = campaign_dir / "campaign_meta.json"
        if meta_path.exists():
            raw = json.loads(meta_path.read_text(encoding="utf-8"))
            if raw.get("campaign_id") != config.capture.campaign_id:
                raise ValueError("campaign metadata id mismatch")
            if raw.get("config_hash") != config.config_hash:
                raise ValueError(
                    "capture config changed for an existing campaign; use a new campaign_id"
                )
            full_until = _parse_utc(raw["full_capture_until"])
            liquidation_until = _parse_utc(raw["liquidation_capture_until"])
        else:
            full_until = opened_at + timedelta(days=config.capture.full_capture_days)
            liquidation_until = opened_at + timedelta(
                days=config.capture.liquidation_capture_days
            )
            _write_new_json(
                meta_path,
                {
                    "campaign_version": 1,
                    "campaign_id": config.capture.campaign_id,
                    "config_hash": config.config_hash,
                    "created_at": _utc_text(opened_at),
                    "full_capture_days": config.capture.full_capture_days,
                    "liquidation_capture_days": config.capture.liquidation_capture_days,
                    "full_capture_until": _utc_text(full_until),
                    "liquidation_capture_until": _utc_text(liquidation_until),
                },
            )

        def create(mode: str, deadline: datetime, include: Callable[[dict], bool]):
            return AppendOnlyRawJournal(
                stream_root=campaign_dir / mode,
                campaign_id=config.capture.campaign_id,
                config_hash=config.config_hash,
                mode=mode,
                deadline=deadline,
                queue_depth=config.journal.queue_depth,
                compression=config.journal.compression,
                compression_level=config.journal.compression_level,
                flush_interval_sec=config.journal.flush_interval_sec,
                min_free_bytes=config.journal.min_free_bytes,
                include=include,
            )

        journals: list[AppendOnlyRawJournal] = []
        if opened_at < full_until:
            journals.append(create("full", full_until, lambda _payload: True))
        if opened_at < liquidation_until:
            journals.append(
                create(
                    "liquidation",
                    liquidation_until,
                    lambda payload: payload.get("e") == "forceOrder",
                )
            )
        return cls(
            campaign_dir=campaign_dir,
            campaign_id=config.capture.campaign_id,
            config_hash=config.config_hash,
            full_capture_until=full_until,
            liquidation_capture_until=liquidation_until,
            journals=tuple(journals),
        )

    @property
    def written(self) -> int:
        return sum(journal.written for journal in self._journals)

    def write(self, obj: dict[str, Any]) -> None:
        if self._closed:
            return
        for journal in self._journals:
            try:
                journal.write(obj)
            except Exception as exc:
                journal.writer_error = f"{type(exc).__name__}: {exc}"
                with journal._state_lock:
                    journal._accepting = False
                logger.exception(
                    "Hook capture tap failed for %s; live pipeline continues",
                    journal.mode,
                )
                try:
                    journal._manifest("TAP_ERROR", error=journal.writer_error)
                except Exception:
                    logger.exception("Hook capture error could not be manifested")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for journal in self._journals:
            journal.close()

    def stats(self) -> dict[str, Any]:
        streams = {journal.mode: journal.stats() for journal in self._journals}
        return {
            "campaign_id": self.campaign_id,
            "campaign_dir": str(self.campaign_dir),
            "full_capture_until": _utc_text(self.full_capture_until),
            "liquidation_capture_until": _utc_text(self.liquidation_capture_until),
            "closed": self._closed,
            "streams": streams,
        }
