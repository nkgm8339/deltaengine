"""Strict depth snapshot/diff synchronization coordinator.

The coordinator owns only synchronization metadata and buffered raw depth
events.  It never mutates an order book.  A caller must apply a verified
snapshot and the returned bridge-and-later diffs from one coroutine.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


INITIAL_BOOK_SYNC = "INITIAL_BOOK_SYNC"
BOOK_RESYNC = "BOOK_RESYNC"


class DepthSyncState(str, Enum):
    """Lifecycle of one live depth synchronization coordinator."""

    WAITING_FOR_FIRST_DEPTH = "WAITING_FOR_FIRST_DEPTH"
    FETCHING_INITIAL_SNAPSHOT = "FETCHING_INITIAL_SNAPSHOT"
    VERIFYING_INITIAL_BRIDGE = "VERIFYING_INITIAL_BRIDGE"
    SYNCED = "SYNCED"
    RESYNC_BUFFERING = "RESYNC_BUFFERING"
    FETCHING_RESYNC_SNAPSHOT = "FETCHING_RESYNC_SNAPSHOT"
    VERIFYING_RESYNC_BRIDGE = "VERIFYING_RESYNC_BRIDGE"
    SYNC_FAILED = "SYNC_FAILED"


class DepthSyncInputError(ValueError):
    """Raised when synchronization input violates the integer/raw-event contract."""


@dataclass(frozen=True)
class SnapshotRequest:
    """A request for one REST depth snapshot candidate."""

    epoch: int
    attempt: int
    reason: str

    def __post_init__(self) -> None:
        _require_positive_int("epoch", self.epoch)
        _require_positive_int("attempt", self.attempt)
        if self.reason not in {INITIAL_BOOK_SYNC, BOOK_RESYNC}:
            raise DepthSyncInputError(f"unsupported snapshot reason: {self.reason!r}")


@dataclass(frozen=True)
class DepthSyncAction:
    """Result of one coordinator input.

    ``snapshot`` and ``diffs`` are populated only after strict verification.
    ``request`` asks the fetch worker for another candidate.  ``failure_reason``
    is populated only in ``SYNC_FAILED``.
    """

    state: DepthSyncState
    epoch: int
    attempt: int
    request: SnapshotRequest | None = None
    snapshot: dict[str, Any] | None = None
    diffs: tuple[dict[str, Any], ...] = ()
    failure_reason: str | None = None

    @property
    def is_verified(self) -> bool:
        return (
            self.state is DepthSyncState.SYNCED
            and self.snapshot is not None
            and bool(self.diffs)
            and self.failure_reason is None
        )


class DepthSyncCoordinator:
    """Validate strict Binance snapshot/diff bridges without owning book state."""

    def __init__(self, *, max_buffered_diffs: int, max_attempts: int) -> None:
        self.max_buffered_diffs = _require_positive_int(
            "max_buffered_diffs", max_buffered_diffs
        )
        self.max_attempts = _require_positive_int("max_attempts", max_attempts)
        self.state = DepthSyncState.WAITING_FOR_FIRST_DEPTH
        self.epoch = 0
        self.attempt = 0
        self.failure_reason: str | None = None
        self._reason = INITIAL_BOOK_SYNC
        self._buffer: list[dict[str, Any]] = []
        self._snapshot: dict[str, Any] | None = None

    @property
    def buffered_count(self) -> int:
        return len(self._buffer)

    @staticmethod
    def is_valid_depth_update(raw: object) -> bool:
        try:
            _depth_ids(raw)
        except DepthSyncInputError:
            return False
        return True

    def notify_first_depth(self, raw: object) -> DepthSyncAction:
        """Open the initial snapshot barrier after the first valid depth event.

        This notification deliberately does not buffer the event.  It is safe
        for a receiver tap to call it after raw recording and before forwarding;
        the main consumer later supplies the same event to :meth:`observe_depth`.
        """

        if self.state is not DepthSyncState.WAITING_FOR_FIRST_DEPTH:
            return self._action()
        if not self.is_valid_depth_update(raw):
            return self._action()

        self.epoch = 1
        self.attempt = 1
        self._reason = INITIAL_BOOK_SYNC
        self.state = DepthSyncState.FETCHING_INITIAL_SNAPSHOT
        return self._action(request=self._current_request())

    def observe_depth(self, raw: Mapping[str, Any]) -> DepthSyncAction:
        """Buffer one unsynchronized raw diff, or open the initial barrier."""

        _depth_ids(raw)
        request: SnapshotRequest | None = None

        if self.state is DepthSyncState.SYNC_FAILED:
            return self._action()
        if self.state is DepthSyncState.SYNCED:
            raise RuntimeError("observe_depth is only valid while synchronization is pending")
        if self.state is DepthSyncState.WAITING_FOR_FIRST_DEPTH:
            barrier = self.notify_first_depth(raw)
            request = barrier.request

        if len(self._buffer) >= self.max_buffered_diffs:
            return self._fail(
                "depth sync buffer limit exceeded "
                f"(max_buffered_diffs={self.max_buffered_diffs})"
            )
        self._buffer.append(dict(raw))

        if self._snapshot is not None:
            return self._verify_candidate()
        return self._action(request=request)

    def observe_snapshot(
        self, request: SnapshotRequest, snapshot: Mapping[str, Any]
    ) -> DepthSyncAction:
        """Accept a fetched candidate and verify it against buffered diffs."""

        snapshot_u = _snapshot_id(snapshot)
        if self.state is DepthSyncState.SYNC_FAILED:
            return self._action()
        if request.epoch != self.epoch or request.attempt != self.attempt:
            raise DepthSyncInputError(
                "stale snapshot candidate: "
                f"candidate epoch/attempt={request.epoch}/{request.attempt}, "
                f"current={self.epoch}/{self.attempt}"
            )
        if request.reason != self._reason:
            raise DepthSyncInputError(
                f"snapshot reason mismatch: {request.reason!r} != {self._reason!r}"
            )
        expected_state = (
            DepthSyncState.FETCHING_INITIAL_SNAPSHOT
            if self._reason == INITIAL_BOOK_SYNC
            else DepthSyncState.FETCHING_RESYNC_SNAPSHOT
        )
        if self.state is not expected_state:
            raise RuntimeError(
                f"snapshot candidate received in {self.state.value}; "
                f"expected {expected_state.value}"
            )

        self._snapshot = dict(snapshot)
        self.state = (
            DepthSyncState.VERIFYING_INITIAL_BRIDGE
            if self._reason == INITIAL_BOOK_SYNC
            else DepthSyncState.VERIFYING_RESYNC_BRIDGE
        )
        # Validate before storing the candidate and keep the local value used so
        # static analysis can prove that the integer contract was checked.
        if snapshot_u < 0:
            raise DepthSyncInputError("snapshot u must be non-negative")
        return self._verify_candidate()

    def observe_fetch_failure(
        self, request: SnapshotRequest, reason: str
    ) -> DepthSyncAction:
        """Reject a failed REST attempt under the same finite attempt budget."""

        if not isinstance(reason, str) or not reason.strip():
            raise DepthSyncInputError("fetch failure reason must be a non-empty string")
        if self.state is DepthSyncState.SYNC_FAILED:
            return self._action()
        if request.epoch != self.epoch or request.attempt != self.attempt:
            raise DepthSyncInputError(
                "stale snapshot fetch failure: "
                f"candidate epoch/attempt={request.epoch}/{request.attempt}, "
                f"current={self.epoch}/{self.attempt}"
            )
        if request.reason != self._reason:
            raise DepthSyncInputError(
                f"snapshot reason mismatch: {request.reason!r} != {self._reason!r}"
            )
        expected_state = (
            DepthSyncState.FETCHING_INITIAL_SNAPSHOT
            if self._reason == INITIAL_BOOK_SYNC
            else DepthSyncState.FETCHING_RESYNC_SNAPSHOT
        )
        if self.state is not expected_state:
            raise RuntimeError(
                f"snapshot fetch failure received in {self.state.value}; "
                f"expected {expected_state.value}"
            )
        return self._reject_candidate(f"snapshot fetch failed: {reason}")

    def start_resync(self, first_gap_diff: Mapping[str, Any]) -> DepthSyncAction:
        """Begin a new strict epoch after the sole book owner detects a gap."""

        _depth_ids(first_gap_diff)
        if self.state is DepthSyncState.SYNC_FAILED:
            return self._action()
        if self.state is not DepthSyncState.SYNCED:
            raise RuntimeError(f"cannot start resync from {self.state.value}")

        self.epoch += 1
        self.attempt = 1
        self._reason = BOOK_RESYNC
        self._snapshot = None
        self._buffer = []
        self.state = DepthSyncState.RESYNC_BUFFERING

        if len(self._buffer) >= self.max_buffered_diffs:
            return self._fail(
                "depth sync buffer limit exceeded "
                f"(max_buffered_diffs={self.max_buffered_diffs})"
            )
        self._buffer.append(dict(first_gap_diff))
        self.state = DepthSyncState.FETCHING_RESYNC_SNAPSHOT
        return self._action(request=self._current_request())

    def rearm_after_failure(
        self, first_depth: Mapping[str, Any]
    ) -> DepthSyncAction:
        """Start a fresh recovery epoch after a terminal sync failure.

        This method is intentionally separate from :meth:`observe_depth` so
        offline reconstruction can keep its existing contract of discarding
        depth after ``SYNC_FAILED``.  LivePipeline calls it only for the next
        valid depth received after the terminal failure; the failed epoch's
        buffer is never reused.
        """

        _depth_ids(first_depth)
        if self.state is not DepthSyncState.SYNC_FAILED:
            raise RuntimeError(f"cannot rearm from {self.state.value}")

        self.epoch += 1
        self.attempt = 1
        self._reason = BOOK_RESYNC
        self.failure_reason = None
        self._snapshot = None
        self._buffer = [dict(first_depth)]
        self.state = DepthSyncState.FETCHING_RESYNC_SNAPSHOT
        return self._action(request=self._current_request())

    def fail(self, reason: str) -> DepthSyncAction:
        """Fail explicitly when a caller cannot complete synchronization."""

        if not isinstance(reason, str) or not reason.strip():
            raise DepthSyncInputError("failure reason must be a non-empty string")
        return self._fail(reason)

    def _verify_candidate(self) -> DepthSyncAction:
        if self._snapshot is None:
            return self._action()
        if not self._buffer:
            return self._action()

        snapshot_u = _snapshot_id(self._snapshot)
        target = snapshot_u + 1
        bridge_index: int | None = None
        for index, diff in enumerate(self._buffer):
            first_id, final_id, _ = _depth_ids(diff)
            if first_id <= target <= final_id:
                bridge_index = index
                break

        if bridge_index is None:
            _, latest_u, _ = _depth_ids(self._buffer[-1])
            if latest_u < target:
                return self._action()
            return self._reject_candidate(
                "snapshot bridge missing after buffered updates passed target "
                f"(snapshot_u={snapshot_u}, target={target}, latest_u={latest_u})"
            )

        verified_diffs = self._buffer[bridge_index:]
        previous_u = _depth_ids(verified_diffs[0])[1]
        for offset, diff in enumerate(verified_diffs[1:], start=bridge_index + 1):
            _, current_u, current_pu = _depth_ids(diff)
            if current_pu != previous_u:
                return self._reject_candidate(
                    "depth pu chain discontinuity after bridge "
                    f"(buffer_index={offset}, previous_u={previous_u}, "
                    f"current_pu={current_pu})",
                    discard_buffer=True,
                )
            previous_u = current_u

        snapshot = dict(self._snapshot)
        diffs = tuple(dict(diff) for diff in verified_diffs)
        self._snapshot = None
        self._buffer = []
        self.state = DepthSyncState.SYNCED
        return self._action(snapshot=snapshot, diffs=diffs)

    def _reject_candidate(
        self, reason: str, *, discard_buffer: bool = False
    ) -> DepthSyncAction:
        self._snapshot = None
        if discard_buffer:
            self._buffer = []
        if self.attempt >= self.max_attempts:
            return self._fail(
                f"depth sync attempt limit reached ({self.attempt}/"
                f"{self.max_attempts}): {reason}"
            )

        self.attempt += 1
        self.state = (
            DepthSyncState.FETCHING_INITIAL_SNAPSHOT
            if self._reason == INITIAL_BOOK_SYNC
            else DepthSyncState.FETCHING_RESYNC_SNAPSHOT
        )
        return self._action(request=self._current_request())

    def _fail(self, reason: str) -> DepthSyncAction:
        self.state = DepthSyncState.SYNC_FAILED
        self.failure_reason = reason
        self._snapshot = None
        self._buffer = []
        return self._action()

    def _current_request(self) -> SnapshotRequest:
        return SnapshotRequest(
            epoch=self.epoch,
            attempt=self.attempt,
            reason=self._reason,
        )

    def _action(
        self,
        *,
        request: SnapshotRequest | None = None,
        snapshot: dict[str, Any] | None = None,
        diffs: tuple[dict[str, Any], ...] = (),
    ) -> DepthSyncAction:
        return DepthSyncAction(
            state=self.state,
            epoch=self.epoch,
            attempt=self.attempt,
            request=request,
            snapshot=snapshot,
            diffs=diffs,
            failure_reason=self.failure_reason,
        )


def _require_positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise DepthSyncInputError(f"{name} must be a positive integer")
    return value


def _require_non_negative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DepthSyncInputError(f"{name} must be a non-negative integer")
    return value


def _depth_ids(raw: object) -> tuple[int, int, int]:
    if not isinstance(raw, Mapping) or raw.get("e") != "depthUpdate":
        raise DepthSyncInputError("expected a depthUpdate mapping")
    first_id = _require_non_negative_int("depthUpdate.U", raw.get("U"))
    final_id = _require_non_negative_int("depthUpdate.u", raw.get("u"))
    previous_id = _require_non_negative_int("depthUpdate.pu", raw.get("pu"))
    if first_id > final_id:
        raise DepthSyncInputError(
            f"depthUpdate U must be <= u (U={first_id}, u={final_id})"
        )
    return first_id, final_id, previous_id


def _snapshot_id(snapshot: object) -> int:
    if not isinstance(snapshot, Mapping) or snapshot.get("e") != "depthSnapshot":
        raise DepthSyncInputError("expected a depthSnapshot mapping")
    return _require_non_negative_int("depthSnapshot.u", snapshot.get("u"))


__all__ = [
    "BOOK_RESYNC",
    "INITIAL_BOOK_SYNC",
    "DepthSyncAction",
    "DepthSyncCoordinator",
    "DepthSyncInputError",
    "DepthSyncState",
    "SnapshotRequest",
]
