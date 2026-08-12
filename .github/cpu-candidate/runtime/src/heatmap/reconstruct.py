"""Offline depth-history reconstructor (Phase 2-1).

Input: JSONL segments + manifest V2 written by DepthHistoryRecorder.
Output: deterministic book-state timeline for Phase 2-2 rendering.
Decimal only — no float(). asyncio is intentionally not used.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from src.acquisition.depth_history_recorder import load_depth_history_manifest
from src.acquisition.depth_sync import (
    DepthSyncAction,
    DepthSyncCoordinator,
    DepthSyncInputError,
    DepthSyncState,
    SnapshotRequest,
)
from src.orderflow.orderbook import (
    BookLevel,
    OrderBookSnapshot,
    OrderBookStateManager,
    OrderBookUpdate,
)


class SegmentIntegrityError(RuntimeError):
    """Raised when a segment does not match its authoritative manifest."""


@dataclass(frozen=True)
class SegmentInfo:
    """One finalized, integrity-checked depth-history segment."""

    path: Path
    manifest: dict
    started_at: str


class DepthHistoryReader:
    """Enumerate and validate segments in one recording directory."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.skipped_segments: list[Path] = []

    def segments(self) -> list[SegmentInfo]:
        """Return finalized segments sorted by manifest ``started_at``."""

        if not self.directory.exists():
            raise FileNotFoundError(self.directory)
        if not self.directory.is_dir():
            raise NotADirectoryError(self.directory)

        self.skipped_segments = []
        segments: list[SegmentInfo] = []
        candidates = sorted(
            (
                path
                for path in self.directory.iterdir()
                if path.is_file() and _is_segment_path(path)
            ),
            key=lambda path: path.name,
        )

        for path in candidates:
            manifest_path = Path(f"{path}.manifest.json")
            if not manifest_path.is_file():
                self.skipped_segments.append(path)
                continue

            manifest = load_depth_history_manifest(manifest_path)
            started_at = manifest.get("started_at")
            if not isinstance(started_at, str) or not started_at:
                raise SegmentIntegrityError(
                    f"{manifest_path}: manifest started_at must be a non-empty string"
                )
            self._validate_integrity(path, manifest)
            segments.append(
                SegmentInfo(
                    path=path,
                    manifest=manifest,
                    started_at=started_at,
                )
            )

        return sorted(segments, key=lambda segment: segment.started_at)

    def iter_records(self) -> Iterator[dict]:
        """Yield JSON object records from all validated segments in order."""

        for segment in self.segments():
            with segment.path.open("r", encoding="utf-8", newline="") as handle:
                for line_number, line in enumerate(handle, start=1):
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise DepthSyncInputError(
                            f"{segment.path}:{line_number}: invalid JSON record: {exc.msg}"
                        ) from exc
                    if not isinstance(record, dict):
                        raise DepthSyncInputError(
                            f"{segment.path}:{line_number}: JSON record must be an object"
                        )
                    yield record

    @staticmethod
    def _validate_integrity(path: Path, manifest: Mapping[str, Any]) -> None:
        expected_bytes = _manifest_non_negative_int(manifest, "byte_size", path)
        expected_records = _manifest_non_negative_int(
            manifest, "record_count", path
        )
        expected_sha = manifest.get("sha256")
        if not isinstance(expected_sha, str) or len(expected_sha) != 64:
            raise SegmentIntegrityError(
                f"{path}: manifest sha256 must be a 64-character string"
            )

        hasher = hashlib.sha256()
        actual_records = 0
        with path.open("rb") as handle:
            for line in handle:
                hasher.update(line)
                actual_records += 1

        actual_bytes = path.stat().st_size
        actual_sha = hasher.hexdigest()
        mismatches: list[str] = []
        if actual_bytes != expected_bytes:
            mismatches.append(
                f"byte_size expected={expected_bytes} actual={actual_bytes}"
            )
        if actual_records != expected_records:
            mismatches.append(
                f"record_count expected={expected_records} actual={actual_records}"
            )
        if actual_sha.lower() != expected_sha.lower():
            mismatches.append(
                f"sha256 expected={expected_sha.lower()} actual={actual_sha.lower()}"
            )
        if mismatches:
            raise SegmentIntegrityError(f"{path}: " + "; ".join(mismatches))


@dataclass(frozen=True)
class ReconstructionEvent:
    """Phase 2-2 output contract: one event per accepted transition."""

    kind: str
    event_time_ms: int
    last_update_id: int | None
    epoch: int


class DepthReconstructor:
    """Consume raw records and drive strict synchronization plus book state."""

    def __init__(
        self,
        *,
        symbol: str = "BTCUSDT",
        max_buffered_diffs: int = 10_000,
        max_attempts: int = 1,
    ) -> None:
        if not isinstance(symbol, str) or not symbol:
            raise DepthSyncInputError("symbol must be a non-empty string")
        self.symbol = symbol
        self._max_buffered_diffs = max_buffered_diffs
        self._max_attempts = max_attempts
        self._reset_runtime()

    def run(
        self, records: Iterable[dict]
    ) -> Iterator[ReconstructionEvent]:
        """Yield a deterministic reconstruction event stream."""

        self._reset_runtime()
        for record in records:
            if not isinstance(record, Mapping):
                raise DepthSyncInputError("depth-history record must be a mapping")
            _reject_float_values(record)

            kind = record.get("e")
            if kind == "trade":
                self._trades_skipped += 1
                continue
            if kind == "depthUpdate":
                yield from self._observe_depth(record)
                continue
            if kind == "depthSnapshot":
                yield from self._observe_snapshot(record)
                continue
            raise DepthSyncInputError(f"unsupported depth-history event: {kind!r}")

    def snapshot(self) -> OrderBookSnapshot | None:
        """Return the current immutable order-book snapshot."""

        return self._book.snapshot()

    def sample_states(
        self,
        records: Iterable[dict],
        *,
        interval_ms: int,
    ) -> Iterator[tuple[int, OrderBookSnapshot]]:
        """Yield synchronized state copies at a fixed event-time interval."""

        interval = _positive_int("interval_ms", interval_ms)
        next_sample_time: int | None = None
        last_sample_time: int | None = None

        for event in self.run(records):
            if event.kind in {"GAP_DETECTED", "SYNC_FAILED"}:
                next_sample_time = None
                continue
            if event.kind != "DIFF_APPLIED":
                continue

            if next_sample_time is None:
                next_sample_time = event.event_time_ms
                if (
                    last_sample_time is not None
                    and next_sample_time <= last_sample_time
                ):
                    next_sample_time = last_sample_time + interval
            if event.event_time_ms < next_sample_time:
                continue

            snapshot = self.snapshot()
            if snapshot is None:
                raise RuntimeError("DIFF_APPLIED emitted without initialized book state")
            while next_sample_time <= event.event_time_ms:
                yield next_sample_time, snapshot
                last_sample_time = next_sample_time
                next_sample_time += interval

    @property
    def counters(self) -> dict[str, int]:
        """Return explicit accounting for every intentionally omitted input."""

        return {
            "trades_skipped": self._trades_skipped,
            "diffs_applied": self._book.diffs_applied,
            "diffs_discarded_after_fail": self._diffs_discarded_after_fail,
            "gaps_detected": self._book.gaps_detected,
            "snapshots_applied": self._book.snapshots_applied,
            "sync_failures": self._sync_failures,
        }

    def _reset_runtime(self) -> None:
        self._coordinator = DepthSyncCoordinator(
            max_buffered_diffs=self._max_buffered_diffs,
            max_attempts=self._max_attempts,
        )
        self._book = OrderBookStateManager(self.symbol)
        self._request: SnapshotRequest | None = None
        self._failure_reported = False
        self._trades_skipped = 0
        self._diffs_discarded_after_fail = 0
        self._sync_failures = 0

    def _observe_depth(
        self, record: Mapping[str, Any]
    ) -> Iterator[ReconstructionEvent]:
        event_time_ms = _event_time_ms(record)
        state = self._coordinator.state

        if state is DepthSyncState.WAITING_FOR_FIRST_DEPTH:
            barrier = self._coordinator.notify_first_depth(record)
            if barrier.request is None:
                # observe_depth supplies the authoritative input exception.
                self._coordinator.observe_depth(record)
                raise RuntimeError("valid first depth did not open a sync barrier")
            self._request = barrier.request
            yield ReconstructionEvent(
                kind="SYNC_STARTED",
                event_time_ms=event_time_ms,
                last_update_id=None,
                epoch=barrier.epoch,
            )
            action = self._coordinator.observe_depth(record)
            yield from self._handle_sync_action(action, event_time_ms)
            return

        if state is DepthSyncState.SYNCED:
            update = self._book_update(record, update_type="DIFF")
            result = self._book.apply(update)
            if result.gap_detected:
                yield ReconstructionEvent(
                    kind="GAP_DETECTED",
                    event_time_ms=event_time_ms,
                    last_update_id=None,
                    epoch=self._coordinator.epoch,
                )
                action = self._coordinator.start_resync(record)
                if action.request is None:
                    raise RuntimeError("resync did not produce a snapshot request")
                self._request = action.request
                yield ReconstructionEvent(
                    kind="RESYNC_STARTED",
                    event_time_ms=event_time_ms,
                    last_update_id=None,
                    epoch=action.epoch,
                )
                return
            if result.applied:
                yield ReconstructionEvent(
                    kind="DIFF_APPLIED",
                    event_time_ms=event_time_ms,
                    last_update_id=update.final_update_id,
                    epoch=self._coordinator.epoch,
                )
            return

        failed_before_input = state is DepthSyncState.SYNC_FAILED
        action = self._coordinator.observe_depth(record)
        if failed_before_input:
            self._diffs_discarded_after_fail += 1
            return
        yield from self._handle_sync_action(action, event_time_ms)

    def _observe_snapshot(
        self, record: Mapping[str, Any]
    ) -> Iterator[ReconstructionEvent]:
        event_time_ms = _event_time_ms(record)
        if self._request is None:
            raise DepthSyncInputError(
                "depthSnapshot received without an active snapshot request"
            )
        action = self._coordinator.observe_snapshot(self._request, record)
        yield from self._handle_sync_action(action, event_time_ms)

    def _handle_sync_action(
        self,
        action: DepthSyncAction,
        trigger_event_time_ms: int,
    ) -> Iterator[ReconstructionEvent]:
        if action.request is not None:
            self._request = action.request

        if action.is_verified:
            self._request = None
            yield from self._apply_verified(action)
            return

        if (
            action.state is DepthSyncState.SYNC_FAILED
            and not self._failure_reported
        ):
            self._failure_reported = True
            self._sync_failures += 1
            snapshot = self._book.snapshot()
            yield ReconstructionEvent(
                kind="SYNC_FAILED",
                event_time_ms=trigger_event_time_ms,
                last_update_id=(
                    snapshot.last_update_id if snapshot is not None else None
                ),
                epoch=action.epoch,
            )

    def _apply_verified(
        self, action: DepthSyncAction
    ) -> Iterator[ReconstructionEvent]:
        snapshot_record = action.snapshot
        if snapshot_record is None or not action.diffs:
            raise RuntimeError("verified sync action is missing snapshot or diffs")

        # Fixed Phase 2-1 application contract:
        # 1. apply verified SNAPSHOT
        # 2. enter initial-sync alignment
        # 3. apply verified bridge-and-later DIFFs in arrival order
        snapshot_update = self._book_update(
            snapshot_record, update_type="SNAPSHOT"
        )
        snapshot_result = self._book.apply(snapshot_update)
        if not snapshot_result.applied:
            raise RuntimeError("verified snapshot was rejected by order book")
        self._book.apply_initial_sync(snapshot_update.final_update_id)

        yield ReconstructionEvent(
            kind="SNAPSHOT_APPLIED",
            event_time_ms=_event_time_ms(snapshot_record),
            last_update_id=snapshot_update.final_update_id,
            epoch=action.epoch,
        )

        for diff_record in action.diffs:
            diff_update = self._book_update(diff_record, update_type="DIFF")
            result = self._book.apply(diff_update)
            if not result.applied or result.gap_detected:
                raise RuntimeError(
                    "coordinator-verified diff was rejected by order book "
                    f"(u={diff_update.final_update_id})"
                )
            yield ReconstructionEvent(
                kind="DIFF_APPLIED",
                event_time_ms=_event_time_ms(diff_record),
                last_update_id=diff_update.final_update_id,
                epoch=action.epoch,
            )

    def _book_update(
        self,
        record: Mapping[str, Any],
        *,
        update_type: str,
    ) -> OrderBookUpdate:
        symbol = record.get("s", self.symbol)
        if not isinstance(symbol, str) or symbol != self.symbol:
            raise DepthSyncInputError(
                f"record symbol must match {self.symbol!r}: {symbol!r}"
            )

        bids = _book_levels(record.get("b"), "b")
        asks = _book_levels(record.get("a"), "a")
        event_time = _event_datetime(_event_time_ms(record))

        if update_type == "SNAPSHOT":
            return OrderBookUpdate(
                event_time=event_time,
                symbol=self.symbol,
                update_type="SNAPSHOT",
                first_update_id=None,
                final_update_id=_non_negative_int(
                    "depthSnapshot.u", record.get("u")
                ),
                bids=bids,
                asks=asks,
                previous_final_update_id=None,
            )
        if update_type != "DIFF":
            raise ValueError(f"unsupported book update type: {update_type!r}")
        return OrderBookUpdate(
            event_time=event_time,
            symbol=self.symbol,
            update_type="DIFF",
            first_update_id=_non_negative_int(
                "depthUpdate.U", record.get("U")
            ),
            final_update_id=_non_negative_int(
                "depthUpdate.u", record.get("u")
            ),
            bids=bids,
            asks=asks,
            previous_final_update_id=_non_negative_int(
                "depthUpdate.pu", record.get("pu")
            ),
        )


def _is_segment_path(path: Path) -> bool:
    return path.name.endswith(".jsonl") or path.name.endswith(".jsonl.part")


def _manifest_non_negative_int(
    manifest: Mapping[str, Any],
    key: str,
    path: Path,
) -> int:
    value = manifest.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SegmentIntegrityError(
            f"{path}: manifest {key} must be a non-negative integer"
        )
    return value


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise DepthSyncInputError(f"{name} must be a positive integer")
    return value


def _non_negative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DepthSyncInputError(f"{name} must be a non-negative integer")
    return value


def _event_time_ms(record: Mapping[str, Any]) -> int:
    event_name = record.get("e")
    return _non_negative_int(f"{event_name}.E", record.get("E"))


def _event_datetime(event_time_ms: int) -> datetime:
    seconds, milliseconds = divmod(event_time_ms, 1000)
    return datetime.fromtimestamp(seconds, tz=timezone.utc).replace(
        microsecond=milliseconds * 1000
    )


def _book_levels(raw_levels: object, field_name: str) -> tuple[BookLevel, ...]:
    if (
        not isinstance(raw_levels, Sequence)
        or isinstance(raw_levels, (str, bytes, bytearray))
    ):
        raise DepthSyncInputError(f"{field_name} must be a sequence of levels")

    levels: list[BookLevel] = []
    for index, raw_level in enumerate(raw_levels):
        if (
            not isinstance(raw_level, Sequence)
            or isinstance(raw_level, (str, bytes, bytearray))
            or len(raw_level) != 2
        ):
            raise DepthSyncInputError(
                f"{field_name}[{index}] must be a two-item sequence"
            )
        price = _decimal_string(
            raw_level[0],
            f"{field_name}[{index}].price",
            allow_zero=False,
        )
        quantity = _decimal_string(
            raw_level[1],
            f"{field_name}[{index}].quantity",
            allow_zero=True,
        )
        levels.append(BookLevel(price=price, quantity=quantity))
    return tuple(levels)


def _decimal_string(
    value: object,
    name: str,
    *,
    allow_zero: bool,
) -> Decimal:
    if not isinstance(value, str):
        raise DepthSyncInputError(f"{name} must be a decimal string")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise DepthSyncInputError(f"{name} must be a valid decimal string") from exc
    if not result.is_finite():
        raise DepthSyncInputError(f"{name} must be finite")
    if result < 0 or (not allow_zero and result == 0):
        requirement = "non-negative" if allow_zero else "positive"
        raise DepthSyncInputError(f"{name} must be {requirement}")
    return result


def _reject_float_values(value: object, path: str = "$") -> None:
    if isinstance(value, float):
        raise DepthSyncInputError(f"float value is forbidden at {path}")
    if isinstance(value, Mapping):
        for key, child in value.items():
            _reject_float_values(child, f"{path}.{key}")
        return
    if (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes, bytearray))
    ):
        for index, child in enumerate(value):
            _reject_float_values(child, f"{path}[{index}]")


__all__ = [
    "DepthHistoryReader",
    "DepthReconstructor",
    "ReconstructionEvent",
    "SegmentInfo",
    "SegmentIntegrityError",
]
