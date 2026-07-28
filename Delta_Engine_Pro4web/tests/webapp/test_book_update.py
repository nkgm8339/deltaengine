"""Phase 2 LIVE DOM projection, fail-closed, and BOOK_UPDATE contract."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.orderflow.orderbook import BookLevel, OrderBookStateManager, OrderBookUpdate
from webapp.book_projection import (
    BookProjection,
    LatestBookProjectionPump,
    build_book_projection,
)
from webapp.push_broker import PushBroker

UTC = timezone.utc
T0 = datetime(2026, 7, 28, 10, 0, tzinfo=UTC)
D = Decimal


def _update(
    update_type: str,
    final_id: int,
    *,
    first_id: int | None = None,
    previous_id: int | None = None,
    bids: tuple[tuple[str, str], ...] = (("100.0", "2.5"), ("99.9", "4.0")),
    asks: tuple[tuple[str, str], ...] = (("100.1", "3.5"), ("100.2", "5.0")),
    event_time: datetime = T0,
) -> OrderBookUpdate:
    return OrderBookUpdate(
        event_time=event_time,
        symbol="BTCUSDT",
        update_type=update_type,
        first_update_id=first_id,
        final_update_id=final_id,
        previous_final_update_id=previous_id,
        bids=tuple(BookLevel(D(price), D(qty)) for price, qty in bids),
        asks=tuple(BookLevel(D(price), D(qty)) for price, qty in asks),
    )


def _synced_manager(clock: list[float]) -> OrderBookStateManager:
    manager = OrderBookStateManager("BTCUSDT", clock=lambda: clock[0])
    manager.apply(_update("SNAPSHOT", 100))
    manager.apply_initial_sync(100)
    manager.apply(
        _update(
            "DIFF",
            101,
            first_id=101,
            previous_id=100,
            event_time=T0 + timedelta(milliseconds=100),
        )
    )
    return manager


def test_projection_sync_lifecycle_stale_gap_and_resync_are_fail_closed() -> None:
    clock = [10.0]
    manager = OrderBookStateManager("BTCUSDT", clock=lambda: clock[0])
    manager.apply(_update("SNAPSHOT", 100))
    manager.apply_initial_sync(100)

    initial = build_book_projection(
        manager, now_monotonic=clock[0], projection_time=T0
    )
    assert initial.sync_state == "NO_SNAPSHOT"
    assert initial.bids == initial.asks == ()

    clock[0] = 10.1
    manager.apply(
        _update(
            "DIFF",
            101,
            first_id=101,
            previous_id=100,
            event_time=T0 + timedelta(milliseconds=100),
        )
    )
    applied_counts = (manager.snapshots_applied, manager.diffs_applied)
    synced = build_book_projection(
        manager, now_monotonic=clock[0], projection_time=T0
    )
    assert synced.sync_state == "SYNCED"
    assert synced.best_bid == D("100.0")
    assert synced.best_ask == D("100.1")
    assert synced.spread == D("0.1")
    assert synced.bids[0] == (D("100.0"), D("2.5"))
    assert synced.asks[0] == (D("100.1"), D("3.5"))
    # Projection is read-only: the analysis-path counters do not change.
    assert (manager.snapshots_applied, manager.diffs_applied) == applied_counts

    clock[0] = 12.101
    stale = build_book_projection(
        manager,
        stale_after_ms=2000,
        now_monotonic=clock[0],
        projection_time=T0,
    )
    assert stale.sync_state == "STALE"
    assert stale.age_ms is not None and stale.age_ms >= 2000
    assert stale.bids == stale.asks == ()
    assert stale.best_bid is stale.best_ask is stale.spread is None

    clock[0] = 12.2
    gap = manager.apply(
        _update(
            "DIFF",
            105,
            first_id=105,
            previous_id=999,
            event_time=T0 + timedelta(seconds=2),
        )
    )
    assert gap.gap_detected is True
    resyncing = build_book_projection(
        manager, now_monotonic=clock[0], projection_time=T0
    )
    assert resyncing.sync_state == "RESYNCING"
    assert resyncing.bids == resyncing.asks == ()

    clock[0] = 12.3
    manager.apply(_update("SNAPSHOT", 200, event_time=T0 + timedelta(seconds=3)))
    manager.apply_initial_sync(200)
    assert build_book_projection(
        manager, now_monotonic=clock[0], projection_time=T0
    ).sync_state == "RESYNCING"
    clock[0] = 12.4
    manager.apply(
        _update(
            "DIFF",
            201,
            first_id=201,
            previous_id=200,
            event_time=T0 + timedelta(seconds=3, milliseconds=100),
        )
    )
    recovered = build_book_projection(
        manager, now_monotonic=clock[0], projection_time=T0
    )
    assert recovered.sync_state == "SYNCED"
    assert recovered.last_update_id == 201


@pytest.mark.parametrize(
    ("bids", "asks", "state"),
    [
        ((("100", "1"),), (), "EMPTY"),
        ((("100", "1"),), (("100", "1"),), "LOCKED"),
        ((("101", "1"),), (("100", "1"),), "CROSSED"),
    ],
)
def test_empty_locked_and_crossed_books_never_expose_quantities(
    bids, asks, state
) -> None:
    clock = [1.0]
    manager = OrderBookStateManager("BTCUSDT", clock=lambda: clock[0])
    manager.apply(_update("SNAPSHOT", 10, bids=bids, asks=asks))
    projection = build_book_projection(
        manager, now_monotonic=clock[0], projection_time=T0
    )
    assert projection.sync_state == state
    assert projection.bids == projection.asks == ()
    assert projection.best_bid is projection.best_ask is projection.spread is None


def test_projection_is_sorted_and_bounded_to_top_50_levels_per_side() -> None:
    clock = [2.0]
    bids = tuple(
        (str(D("100") - D(index) / D("10")), str(index + 1))
        for index in range(60)
    )
    asks = tuple(
        (str(D("100.1") + D(index) / D("10")), str(index + 1))
        for index in range(60)
    )
    manager = OrderBookStateManager("BTCUSDT", clock=lambda: clock[0])
    manager.apply(_update("SNAPSHOT", 10, bids=bids, asks=asks))

    projection = build_book_projection(
        manager,
        depth_levels=50,
        now_monotonic=clock[0],
        projection_time=T0,
    )

    assert projection.sync_state == "SYNCED"
    assert len(projection.bids) == len(projection.asks) == 50
    assert projection.bids[0][0] == D("100")
    assert projection.bids[-1][0] == D("95.1")
    assert projection.asks[0][0] == D("100.1")
    assert projection.asks[-1][0] == D("105.0")


def test_latest_pump_is_100ms_read_only_and_suppresses_unchanged_state() -> None:
    clock = [5.0]
    state = [None]
    sent: list[BookProjection] = []

    async def send(projection: BookProjection) -> None:
        sent.append(projection)

    pump = LatestBookProjectionPump(
        lambda: state[0],
        send,
        depth_levels=50,
        interval_sec=0.1,
        stale_after_ms=2000,
        monotonic=lambda: clock[0],
        utcnow=lambda: T0,
    )

    async def run() -> None:
        assert await pump.project_once() is True
        assert await pump.project_once() is False
        state[0] = _synced_manager(clock)
        counts = (state[0].snapshots_applied, state[0].diffs_applied)
        assert await pump.project_once() is True
        assert await pump.project_once() is False
        assert (state[0].snapshots_applied, state[0].diffs_applied) == counts

    asyncio.run(run())
    assert pump.interval_sec == pytest.approx(0.1)
    assert pump.samples == 4
    assert pump.sent == 2
    assert pump.synced_sent == 1
    assert pump.fail_closed_sent == 1
    assert pump.unchanged_suppressed == 2
    assert [item.sync_state for item in sent] == ["NO_SNAPSHOT", "SYNCED"]


def test_projection_send_failure_is_isolated_and_retried() -> None:
    attempts = [0]

    async def send(_projection: BookProjection) -> None:
        attempts[0] += 1
        if attempts[0] == 1:
            raise RuntimeError("temporary browser delivery failure")

    pump = LatestBookProjectionPump(
        lambda: None,
        send,
        interval_sec=0.1,
        monotonic=lambda: 1.0,
        utcnow=lambda: T0,
    )

    async def run() -> None:
        assert await pump.project_once() is False
        assert await pump.project_once() is True

    asyncio.run(run())
    assert pump.send_failures == 1
    assert pump.sent == 1
    assert pump.fail_closed_sent == 1


def test_book_update_payload_and_reconnect_cache_use_latest_projection() -> None:
    projection = BookProjection(
        projection_time=T0 + timedelta(milliseconds=200),
        event_time=T0 + timedelta(milliseconds=100),
        last_update_id=123456,
        sync_state="SYNCED",
        bids=((D("100.0"), D("2.5")), (D("99.9"), D("4.0"))),
        asks=((D("100.1"), D("3.5")), (D("100.2"), D("5.0"))),
        depth_levels=50,
        best_bid=D("100.0"),
        best_ask=D("100.1"),
        spread=D("0.1"),
        age_ms=100,
    )
    broker = PushBroker("BTCUSDT", depth_levels=15, live_dom_depth_levels=50)
    first_messages: list[dict] = []
    first_ws = MagicMock()
    first_ws.send_text = AsyncMock(
        side_effect=lambda text: first_messages.append(json.loads(text))
    )

    async def run() -> list[dict]:
        await broker.register(first_ws)
        await broker.on_book_update(projection)
        reconnect_messages: list[dict] = []
        reconnect_ws = MagicMock()
        reconnect_ws.send_text = AsyncMock(
            side_effect=lambda text: reconnect_messages.append(json.loads(text))
        )
        await broker.register(reconnect_ws)
        return reconnect_messages

    reconnect_messages = asyncio.run(run())
    assert len(first_messages) == 1
    message = first_messages[0]
    assert message["type"] == "BOOK_UPDATE"
    payload = message["payload"]
    assert payload["event_time"] == "2026-07-28T10:00:00.100000+00:00"
    assert payload["last_update_id"] == 123456
    assert payload["sync_state"] == "SYNCED"
    assert payload["bids"][0] == {"price": "100.0", "qty": "2.5"}
    assert payload["asks"][0] == {"price": "100.1", "qty": "3.5"}
    assert payload["best_bid"] == "100.0"
    assert payload["best_ask"] == "100.1"
    assert payload["spread"] == "0.1"
    assert payload["depth_levels"] == 50
    assert reconnect_messages == [message]
    assert broker.book_updates_broadcast == 1


def test_broker_defensively_clears_levels_for_fail_closed_message() -> None:
    stale = BookProjection(
        projection_time=T0,
        event_time=T0 - timedelta(seconds=3),
        last_update_id=9,
        sync_state="STALE",
        bids=((D("100"), D("99")),),
        asks=((D("101"), D("88")),),
        depth_levels=50,
        best_bid=D("100"),
        best_ask=D("101"),
        spread=D("1"),
        age_ms=3000,
    )
    broker = PushBroker("BTCUSDT")
    messages: list[dict] = []
    ws = MagicMock()
    ws.send_text = AsyncMock(side_effect=lambda text: messages.append(json.loads(text)))

    async def run() -> None:
        await broker.register(ws)
        await broker.on_book_update(stale)

    asyncio.run(run())
    payload = messages[0]["payload"]
    assert payload["sync_state"] == "STALE"
    assert payload["bids"] == payload["asks"] == []
    assert payload["best_bid"] is payload["best_ask"] is payload["spread"] is None
