"""Tests for the request-driven depth snapshot fetch worker (network-free)."""

from __future__ import annotations

import asyncio

import pytest

from src.acquisition.depth_sync import (
    BOOK_RESYNC,
    INITIAL_BOOK_SYNC,
    SnapshotRequest,
)
from src.pipeline import BookResyncCounters, _book_resync_supervisor


class _Recorder:
    def __init__(self) -> None:
        self.rows: list[tuple[dict, str]] = []

    def write_snapshot(self, row: dict, *, reason: str) -> None:
        self.rows.append((row, reason))


def _raw(update_id: int) -> dict:
    return {
        "lastUpdateId": update_id,
        "E": 1767225600000,
        "bids": [["50000.0", "1.0"]],
        "asks": [["50001.0", "1.0"]],
    }


async def _cancel(task: asyncio.Task) -> None:
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_fetch_failure_is_reported_for_coordinator_retry() -> None:
    async def run() -> None:
        requests = asyncio.Queue()
        results = asyncio.Queue()
        counters = BookResyncCounters()
        delays: list[int] = []

        async def fetch(symbol: str) -> dict:
            raise ConnectionError(f"{symbol} temporary")

        async def sleep(delay: int) -> None:
            delays.append(delay)

        task = asyncio.create_task(
            _book_resync_supervisor(
                symbol="BTCUSDT",
                fetch_snapshot=fetch,
                requests=requests,
                results=results,
                counters=counters,
                sleep=sleep,
            )
        )
        request = SnapshotRequest(1, 1, INITIAL_BOOK_SYNC)
        await requests.put(request)
        result = await asyncio.wait_for(results.get(), timeout=1)

        assert result.request == request
        assert result.snapshot is None
        assert "temporary" in result.error
        assert counters.fetch_failures == 1
        assert delays == [5]
        await _cancel(task)

    asyncio.run(run())


def test_successful_snapshot_candidate_is_recorded_before_delivery() -> None:
    async def run() -> None:
        requests = asyncio.Queue()
        results = asyncio.Queue()
        recorder = _Recorder()

        async def fetch(symbol: str) -> dict:
            return _raw(100)

        task = asyncio.create_task(
            _book_resync_supervisor(
                symbol="BTCUSDT",
                fetch_snapshot=fetch,
                requests=requests,
                results=results,
                counters=BookResyncCounters(),
                recorder=recorder,
            )
        )
        request = SnapshotRequest(1, 1, INITIAL_BOOK_SYNC)
        await requests.put(request)
        result = await asyncio.wait_for(results.get(), timeout=1)

        assert result.request == request
        assert result.error is None
        assert result.snapshot["e"] == "depthSnapshot"
        assert result.snapshot["u"] == 100
        assert recorder.rows == [(result.snapshot, INITIAL_BOOK_SYNC)]
        await _cancel(task)

    asyncio.run(run())


def test_fetch_backoff_is_bounded_by_request_attempt() -> None:
    async def run() -> None:
        requests = asyncio.Queue()
        results = asyncio.Queue()
        delays: list[int] = []

        async def fetch(symbol: str) -> dict:
            raise ConnectionError("down")

        async def sleep(delay: int) -> None:
            delays.append(delay)

        task = asyncio.create_task(
            _book_resync_supervisor(
                symbol="BTCUSDT",
                fetch_snapshot=fetch,
                requests=requests,
                results=results,
                counters=BookResyncCounters(),
                sleep=sleep,
            )
        )
        for attempt in (1, 2, 3, 4):
            await requests.put(
                SnapshotRequest(1, attempt, INITIAL_BOOK_SYNC)
            )
            await asyncio.wait_for(results.get(), timeout=1)

        assert delays == [5, 10, 30, 30]
        await _cancel(task)

    asyncio.run(run())


def test_book_resync_candidate_uses_reason_without_mutating_book() -> None:
    async def run() -> None:
        requests = asyncio.Queue()
        results = asyncio.Queue()
        recorder = _Recorder()

        async def fetch(symbol: str) -> dict:
            return _raw(500)

        task = asyncio.create_task(
            _book_resync_supervisor(
                symbol="BTCUSDT",
                fetch_snapshot=fetch,
                requests=requests,
                results=results,
                counters=BookResyncCounters(),
                recorder=recorder,
            )
        )
        request = SnapshotRequest(2, 1, BOOK_RESYNC)
        await requests.put(request)
        result = await asyncio.wait_for(results.get(), timeout=1)

        assert result.snapshot["u"] == 500
        assert recorder.rows == [(result.snapshot, BOOK_RESYNC)]
        # The worker has no OrderBookStateManager argument: apply ownership stays
        # with LivePipeline's main consumer.
        await _cancel(task)

    asyncio.run(run())


def test_worker_does_not_fetch_without_an_explicit_request() -> None:
    async def run() -> None:
        requests = asyncio.Queue()
        results = asyncio.Queue()
        fetches = 0

        async def fetch(symbol: str) -> dict:
            nonlocal fetches
            fetches += 1
            return _raw(100)

        task = asyncio.create_task(
            _book_resync_supervisor(
                symbol="BTCUSDT",
                fetch_snapshot=fetch,
                requests=requests,
                results=results,
                counters=BookResyncCounters(),
            )
        )
        await asyncio.sleep(0)

        assert fetches == 0
        assert results.empty()
        await _cancel(task)

    asyncio.run(run())


def test_cancel_terminates_cleanly_while_waiting_for_request() -> None:
    async def run() -> None:
        task = asyncio.create_task(
            _book_resync_supervisor(
                symbol="BTCUSDT",
                fetch_snapshot=lambda symbol: _raw(100),
                requests=asyncio.Queue(),
                results=asyncio.Queue(),
                counters=BookResyncCounters(),
            )
        )
        await asyncio.sleep(0)
        await _cancel(task)

    asyncio.run(run())
