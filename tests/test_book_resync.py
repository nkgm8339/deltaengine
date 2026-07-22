"""Tests for _book_resync_supervisor (ADR-010)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.orderflow.orderbook import BookLevel, OrderBookStateManager, OrderBookUpdate
from src.pipeline import BookResyncCounters, _book_resync_supervisor

UTC = timezone.utc


class _Normalizer:
    def process_depth(self, raw):
        return OrderBookUpdate(
            event_time=datetime(2026, 1, 1, tzinfo=UTC),
            symbol=raw["s"], update_type="SNAPSHOT", first_update_id=None,
            final_update_id=raw["u"],
            bids=tuple(BookLevel(Decimal(p), Decimal(q)) for p, q in raw["b"]),
            asks=tuple(BookLevel(Decimal(p), Decimal(q)) for p, q in raw["a"]),
        )


class _Recorder:
    def __init__(self):
        self.rows = []

    def write(self, row):
        self.rows.append(row)


def _raw(update_id: int) -> dict:
    return {"lastUpdateId": update_id, "bids": [["50000.0", "1.0"]], "asks": [["50001.0", "1.0"]]}


def test_startup_retry_until_success():
    async def run():
        book = OrderBookStateManager("BTCUSDT")
        counters = BookResyncCounters()
        delays = []
        attempts = 0

        async def fetch(symbol):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise ConnectionError("temporary")
            return _raw(100)

        async def sleep(delay):
            delays.append(delay)
            if delay == 1:
                raise asyncio.CancelledError

        with pytest.raises(asyncio.CancelledError):
            await _book_resync_supervisor(symbol="BTCUSDT", book_state=book, normalizer=_Normalizer(), fetch_snapshot=fetch, counters=counters, sleep=sleep)
        assert book.is_initialized is True
        assert counters.fetch_failures == 2 and counters.resyncs == 0
        assert delays[:2] == [5, 10]
    asyncio.run(run())


def test_successful_snapshot_is_recorded_for_exact_depth_replay():
    async def run():
        book = OrderBookStateManager("BTCUSDT")
        recorder = _Recorder()

        async def fetch(symbol):
            return _raw(100)

        async def sleep(delay):
            raise asyncio.CancelledError

        with pytest.raises(asyncio.CancelledError):
            await _book_resync_supervisor(
                symbol="BTCUSDT",
                book_state=book,
                normalizer=_Normalizer(),
                fetch_snapshot=fetch,
                counters=BookResyncCounters(),
                recorder=recorder,
                sleep=sleep,
            )

        assert len(recorder.rows) == 1
        assert recorder.rows[0]["e"] == "depthSnapshot"
        assert recorder.rows[0]["u"] == 100
        assert recorder.rows[0]["b"] == [["50000.0", "1.0"]]

    asyncio.run(run())


def test_backoff_caps_at_30():
    async def run():
        counters = BookResyncCounters()
        delays = []

        async def fetch(symbol):
            raise ConnectionError("down")

        async def sleep(delay):
            delays.append(delay)
            if len(delays) == 4:
                raise asyncio.CancelledError

        with pytest.raises(asyncio.CancelledError):
            await _book_resync_supervisor(symbol="BTCUSDT", book_state=OrderBookStateManager("BTCUSDT"), normalizer=_Normalizer(), fetch_snapshot=fetch, counters=counters, sleep=sleep)
        assert delays == [5, 10, 30, 30]
        assert counters.fetch_failures == 4
    asyncio.run(run())


def test_resync_after_gap():
    async def run():
        book = OrderBookStateManager("BTCUSDT")
        counters = BookResyncCounters()
        fetches = 0
        sleeps = 0

        async def fetch(symbol):
            nonlocal fetches
            fetches += 1
            return _raw(100 if fetches == 1 else 500)

        async def sleep(delay):
            nonlocal sleeps
            sleeps += 1
            if sleeps == 1:
                sync_diff = OrderBookUpdate(datetime(2026, 1, 1, tzinfo=UTC), "BTCUSDT", "DIFF", 95, 101, (), (), 99)
                assert book.apply(sync_diff).applied is True
                gap = OrderBookUpdate(datetime(2026, 1, 1, tzinfo=UTC), "BTCUSDT", "DIFF", 300, 310, (), (), 250)
                assert book.apply(gap).gap_detected is True
            elif sleeps == 2:
                raise asyncio.CancelledError

        with pytest.raises(asyncio.CancelledError):
            await _book_resync_supervisor(symbol="BTCUSDT", book_state=book, normalizer=_Normalizer(), fetch_snapshot=fetch, counters=counters, sleep=sleep)
        assert book.is_initialized is True
        assert counters.resyncs == 1 and fetches == 2
    asyncio.run(run())


def test_no_fetch_while_healthy():
    async def run():
        book = OrderBookStateManager("BTCUSDT")
        counters = BookResyncCounters()
        fetches = 0
        polls = 0

        async def fetch(symbol):
            nonlocal fetches
            fetches += 1
            return _raw(100)

        async def sleep(delay):
            nonlocal polls
            polls += 1
            if polls == 6:
                raise asyncio.CancelledError

        with pytest.raises(asyncio.CancelledError):
            await _book_resync_supervisor(symbol="BTCUSDT", book_state=book, normalizer=_Normalizer(), fetch_snapshot=fetch, counters=counters, sleep=sleep)
        assert fetches == 1
    asyncio.run(run())


def test_cancel_terminates_cleanly():
    async def run():
        gate = asyncio.Event()

        async def fetch(symbol):
            return _raw(100)

        async def sleep(delay):
            await gate.wait()

        task = asyncio.create_task(_book_resync_supervisor(symbol="BTCUSDT", book_state=OrderBookStateManager("BTCUSDT"), normalizer=_Normalizer(), fetch_snapshot=fetch, counters=BookResyncCounters(), sleep=sleep))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())
