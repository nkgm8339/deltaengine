"""Fixture-driven tests for strict live depth synchronization (no network)."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import Any

import pytest

from src.acquisition.depth_sync import (
    BOOK_RESYNC,
    INITIAL_BOOK_SYNC,
    DepthSyncCoordinator,
    DepthSyncInputError,
    DepthSyncState,
)
from src.acquisition.event_queue import BoundedEventQueue
from src.acquisition.receiver import STOP, DataReceiver


@pytest.fixture
def depth_update():
    def make(
        first_id: int,
        final_id: int,
        previous_id: int,
        *,
        bid_price: str = "50000.0",
        bid_quantity: str = "1.0",
    ) -> dict[str, Any]:
        return {
            "e": "depthUpdate",
            "E": 1767225600000 + final_id,
            "s": "BTCUSDT",
            "U": first_id,
            "u": final_id,
            "pu": previous_id,
            "b": [[bid_price, bid_quantity]],
            "a": [["50001.0", "2.0"]],
        }

    return make


@pytest.fixture
def depth_snapshot():
    def make(update_id: int) -> dict[str, Any]:
        return {
            "e": "depthSnapshot",
            "E": 1767225600000,
            "s": "BTCUSDT",
            "u": update_id,
            "b": [["49999.0", "3.0"]],
            "a": [["50002.0", "4.0"]],
        }

    return make


def _coordinator(*, max_attempts: int = 3) -> DepthSyncCoordinator:
    return DepthSyncCoordinator(max_buffered_diffs=16, max_attempts=max_attempts)


def _contains_float(value: object) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, dict):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_float(item) for item in value)
    return False


def test_depth_is_buffered_before_initial_snapshot_request(depth_update) -> None:
    coordinator = _coordinator()

    ignored = coordinator.observe_depth(
        depth_update(100, 100, 99)
    )

    assert ignored.request is not None
    assert ignored.request.reason == INITIAL_BOOK_SYNC
    assert ignored.request.epoch == 1
    assert ignored.request.attempt == 1
    assert coordinator.buffered_count == 1
    assert coordinator.state is DepthSyncState.FETCHING_INITIAL_SNAPSHOT


def test_buffer_bridge_establishes_strict_sync(
    depth_update, depth_snapshot
) -> None:
    coordinator = _coordinator()
    first = coordinator.observe_depth(depth_update(98, 101, 97))
    coordinator.observe_depth(depth_update(102, 103, 101))

    result = coordinator.observe_snapshot(first.request, depth_snapshot(100))

    assert result.is_verified is True
    assert result.state is DepthSyncState.SYNCED
    assert result.snapshot["u"] == 100
    assert [diff["u"] for diff in result.diffs] == [101, 103]
    assert coordinator.buffered_count == 0


def test_snapshot_is_refetched_when_buffer_passes_target_without_bridge(
    depth_update, depth_snapshot
) -> None:
    coordinator = _coordinator()
    first = coordinator.observe_depth(depth_update(105, 106, 104))

    rejected = coordinator.observe_snapshot(first.request, depth_snapshot(100))

    assert rejected.is_verified is False
    assert rejected.request is not None
    assert rejected.request.epoch == 1
    assert rejected.request.attempt == 2
    assert rejected.state is DepthSyncState.FETCHING_INITIAL_SNAPSHOT


def test_attempt_limit_fails_closed_with_explicit_reason(
    depth_update, depth_snapshot
) -> None:
    coordinator = _coordinator(max_attempts=2)
    first = coordinator.observe_depth(depth_update(105, 106, 104))
    retry = coordinator.observe_snapshot(first.request, depth_snapshot(100))

    failed = coordinator.observe_snapshot(retry.request, depth_snapshot(100))

    assert failed.state is DepthSyncState.SYNC_FAILED
    assert failed.is_verified is False
    assert failed.request is None
    assert "attempt limit reached (2/2)" in failed.failure_reason


def test_fetch_failures_share_the_finite_attempt_budget(depth_update) -> None:
    coordinator = _coordinator(max_attempts=2)
    first = coordinator.observe_depth(depth_update(100, 101, 99))

    retry = coordinator.observe_fetch_failure(first.request, "temporary")
    failed = coordinator.observe_fetch_failure(retry.request, "still down")

    assert retry.request.attempt == 2
    assert failed.state is DepthSyncState.SYNC_FAILED
    assert "snapshot fetch failed: still down" in failed.failure_reason


def test_pu_discontinuity_after_bridge_is_never_verified(
    depth_update, depth_snapshot
) -> None:
    coordinator = _coordinator()
    first = coordinator.observe_depth(depth_update(100, 101, 99))
    coordinator.observe_depth(depth_update(102, 103, 999))

    rejected = coordinator.observe_snapshot(first.request, depth_snapshot(100))

    assert rejected.is_verified is False
    assert rejected.request is not None
    assert rejected.request.attempt == 2
    assert "pu chain discontinuity" not in (rejected.failure_reason or "")
    assert coordinator.buffered_count == 0

    # The next attempt starts from a fresh diff, not the contaminated buffer.
    coordinator.observe_depth(depth_update(104, 105, 103))
    verified = coordinator.observe_snapshot(
        rejected.request, depth_snapshot(104)
    )
    assert verified.is_verified is True
    assert [diff["u"] for diff in verified.diffs] == [105]


def test_terminal_failure_clears_buffer_and_can_rearm_on_fresh_depth(
    depth_update, depth_snapshot
) -> None:
    coordinator = _coordinator(max_attempts=1)
    first = coordinator.observe_depth(depth_update(105, 106, 104))
    failed = coordinator.observe_snapshot(first.request, depth_snapshot(100))

    assert failed.state is DepthSyncState.SYNC_FAILED
    assert coordinator.buffered_count == 0

    rearmed = coordinator.rearm_after_failure(depth_update(200, 201, 199))
    assert rearmed.request is not None
    assert rearmed.request.epoch == 2
    assert rearmed.request.attempt == 1
    assert rearmed.request.reason == BOOK_RESYNC
    assert coordinator.buffered_count == 1

    recovered = coordinator.observe_snapshot(
        rearmed.request, depth_snapshot(200)
    )
    assert recovered.is_verified is True
    assert recovered.epoch == 2
    assert [diff["u"] for diff in recovered.diffs] == [201]


def test_candidate_waits_while_latest_buffer_u_is_before_target(
    depth_update, depth_snapshot
) -> None:
    coordinator = _coordinator()
    first = coordinator.observe_depth(depth_update(100, 103, 99))

    waiting = coordinator.observe_snapshot(first.request, depth_snapshot(104))

    assert waiting.state is DepthSyncState.VERIFYING_INITIAL_BRIDGE
    assert waiting.request is None
    assert waiting.failure_reason is None
    verified = coordinator.observe_depth(depth_update(104, 105, 103))
    assert verified.is_verified is True
    assert [diff["u"] for diff in verified.diffs] == [105]


def test_buffer_limit_is_explicit_sync_failure(depth_update) -> None:
    coordinator = DepthSyncCoordinator(max_buffered_diffs=1, max_attempts=2)
    coordinator.observe_depth(depth_update(100, 101, 99))

    failed = coordinator.observe_depth(depth_update(102, 103, 101))

    assert failed.state is DepthSyncState.SYNC_FAILED
    assert "buffer limit exceeded" in failed.failure_reason


def test_receiver_records_all_presync_diffs_before_buffer_tap(depth_update) -> None:
    async def run() -> None:
        source = BoundedEventQueue(8, "drop_oldest_log", name="source")
        destination = BoundedEventQueue(8, "drop_oldest_log", name="destination")
        coordinator = _coordinator()
        trace: list[tuple[str, int]] = []
        recorded: list[dict[str, Any]] = []

        class Recorder:
            def write(self, raw: dict[str, Any]) -> None:
                recorded.append(raw)
                trace.append(("record", raw["u"]))

        def buffer_tap(raw: dict[str, Any]) -> None:
            coordinator.observe_depth(raw)
            trace.append(("buffer", raw["u"]))

        receiver = DataReceiver(
            source,
            destination,
            recorder=Recorder(),
            on_valid_message=buffer_tap,
        )
        rows = [
            depth_update(100, 101, 99),
            depth_update(102, 103, 101),
        ]
        for row in rows:
            await source.put(row)
        await source.put(STOP)
        await receiver.run()

        assert recorded == rows
        assert coordinator.buffered_count == 2
        assert trace == [
            ("record", 101),
            ("buffer", 101),
            ("record", 103),
            ("buffer", 103),
        ]
        assert [destination.get_nowait(), destination.get_nowait()] == rows

    asyncio.run(run())


def test_book_resync_uses_the_same_strict_bridge_state_machine(
    depth_update, depth_snapshot
) -> None:
    coordinator = _coordinator()
    initial = coordinator.observe_depth(depth_update(100, 101, 99))
    assert coordinator.observe_snapshot(
        initial.request, depth_snapshot(100)
    ).is_verified

    resync_request = coordinator.start_resync(depth_update(200, 201, 150))
    coordinator.observe_depth(depth_update(202, 203, 201))
    resynced = coordinator.observe_snapshot(
        resync_request.request, depth_snapshot(199)
    )

    assert resync_request.request.reason == BOOK_RESYNC
    assert resync_request.request.epoch == 2
    assert resynced.is_verified is True
    assert resynced.state is DepthSyncState.SYNCED
    assert [diff["u"] for diff in resynced.diffs] == [201, 203]


def test_sync_metadata_has_no_float_and_float_ids_are_rejected(
    depth_update, depth_snapshot
) -> None:
    coordinator = _coordinator()
    request = coordinator.observe_depth(
        depth_update(
            100,
            101,
            99,
            bid_price="50000.125",
            bid_quantity="0.250",
        )
    ).request
    result = coordinator.observe_snapshot(request, depth_snapshot(100))

    assert result.diffs[0]["b"][0] == ["50000.125", "0.250"]
    assert _contains_float(asdict(result)) is False
    with pytest.raises(DepthSyncInputError, match="positive integer"):
        DepthSyncCoordinator(max_buffered_diffs=1.0, max_attempts=3)
    invalid = depth_update(102, 103, 101)
    invalid["u"] = 103.0
    with pytest.raises(DepthSyncInputError, match="non-negative integer"):
        _coordinator().observe_depth(invalid)
