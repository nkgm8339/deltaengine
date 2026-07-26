from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.orderflow.hooks.dom_features import DomFeatureCache
from src.orderflow.hooks.dom_iceberg import DomIcebergDetector
from src.orderflow.hooks.dom_liquidity import DomLiquidityDetector
from src.orderflow.hooks.dom_quote_motion import DomQuoteMotionDetector
from src.orderflow.hooks.dom_wall import DomWallDetector
from src.orderflow.hooks.models import HookQualityStatus
from src.orderflow.orderbook import OrderBookSnapshot


D = Decimal
T0 = datetime(2026, 7, 26, 7, 0, tzinfo=timezone.utc)


def _snapshot(
    sequence: int,
    bids: list[tuple[str, str]],
    asks: list[tuple[str, str]],
) -> OrderBookSnapshot:
    return OrderBookSnapshot(
        symbol="BTCUSDT",
        last_update_id=sequence,
        bids={D(price): D(quantity) for price, quantity in bids},
        asks={D(price): D(quantity) for price, quantity in asks},
    )


def _frame(
    cache: DomFeatureCache,
    sequence: int,
    bids: list[tuple[str, str]],
    asks: list[tuple[str, str]],
):
    when = T0 + timedelta(seconds=sequence)
    return cache.process(
        _snapshot(sequence, bids, asks),
        source_time=when,
        received_time=when,
    )


def test_dom_feature_cache_rejects_invalid_stale_crossed_and_future_data():
    cache = DomFeatureCache(depth_levels=10)
    valid = _frame(
        cache,
        1,
        [("100", "2"), ("99", "1")],
        [("101", "2"), ("102", "1")],
    )
    assert valid is not None
    assert valid.current.best_bid == D("100")
    assert valid.current.best_ask == D("101")

    stale_time = T0 + timedelta(seconds=1)
    stale = cache.process(
        _snapshot(2, [("100", "2")], [("101", "2")]),
        source_time=stale_time,
        received_time=stale_time,
    )
    assert stale is None
    assert cache.stale_frames == 1

    invalid = cache.process(
        _snapshot(3, [("100", "2")], [("101", "2")]),
        source_time=T0 + timedelta(seconds=3),
        received_time=T0 + timedelta(seconds=3),
        quality_status=HookQualityStatus.INVALID,
        quality_flags=("SEQUENCE_GAP",),
    )
    assert invalid is None
    assert cache.latest is None

    crossed = _frame(cache, 4, [("102", "1")], [("101", "1")])
    assert crossed is None
    assert cache.latest is None

    with pytest.raises(ValueError, match="source_time"):
        cache.process(
            _snapshot(5, [("100", "1")], [("101", "1")]),
            source_time=T0 + timedelta(seconds=6),
            received_time=T0 + timedelta(seconds=5),
        )


def test_dom_wall_pull_spoof_suspect_and_tracking_candidates_cover_a01_a04_a19_a24():
    cache = DomFeatureCache(depth_levels=10)
    wall = DomWallDetector()
    first = _frame(
        cache,
        10,
        [("100", "1"), ("99", "10"), ("98", "1")],
        [("101", "1"), ("102", "10"), ("103", "1")],
    )
    assert first is not None
    first_ids = {item.hook_id for item in wall.process(first)}
    assert {"A01", "A02"} <= first_ids

    second = _frame(
        cache,
        11,
        [("100", "1"), ("99", "1"), ("98", "1")],
        [("101", "1"), ("102", "1"), ("103", "1")],
    )
    assert second is not None
    candidates = wall.process(second)
    ids = {item.hook_id for item in candidates}
    assert {"A03", "A04", "A19", "A20", "A23", "A24"} <= ids
    for item in candidates:
        assert item.quality_status is HookQualityStatus.VALID


def test_dom_liquidity_quote_motion_and_vacuum_candidates_cover_a05_a16_a21_a22():
    cache = DomFeatureCache(depth_levels=10)
    liquidity = DomLiquidityDetector()
    quotes = DomQuoteMotionDetector()
    base = _frame(
        cache,
        20,
        [("100", "10"), ("99", "10")],
        [("101", "10"), ("102", "10")],
    )
    assert base is not None
    ids = {item.hook_id for item in liquidity.process(base)}
    assert {"A09", "A21", "A22"} <= ids

    wide = _frame(
        cache,
        21,
        [("99", "5"), ("98", "5")],
        [("102", "20"), ("103", "20")],
    )
    assert wide is not None
    ids = {
        *(item.hook_id for item in liquidity.process(wide)),
        *(item.hook_id for item in quotes.process(wide)),
    }
    assert {"A05", "A08", "A10", "A11", "A12", "A15", "A21", "A22"} <= ids

    tight = _frame(
        cache,
        22,
        [("100", "20"), ("99", "20")],
        [("101", "5"), ("102", "5")],
    )
    assert tight is not None
    ids = {
        *(item.hook_id for item in liquidity.process(tight)),
        *(item.hook_id for item in quotes.process(tight)),
    }
    assert {"A06", "A07", "A09", "A13", "A14", "A16", "A21", "A22"} <= ids


def test_dom_iceberg_suspected_requires_actual_replenishment_on_correct_side():
    cache = DomFeatureCache(depth_levels=10)
    first = _frame(
        cache,
        30,
        [("100", "10"), ("99", "1")],
        [("101", "10"), ("102", "1")],
    )
    second = _frame(
        cache,
        31,
        [("100", "9"), ("99", "1")],
        [("101", "10"), ("102", "1")],
    )
    third = _frame(
        cache,
        32,
        [("100", "9"), ("99", "1")],
        [("101", "9"), ("102", "1")],
    )
    fourth = _frame(
        cache,
        33,
        [("100", "9"), ("99", "1")],
        [("101", "8"), ("102", "1")],
    )
    assert first and second and third and fourth
    detector = DomIcebergDetector(episode_window_ms=5_000)
    sell = SimpleNamespace(
        event_time=T0 + timedelta(seconds=30, milliseconds=500),
        trade_id=1,
        symbol="BTCUSDT",
        side="SELL",
        price=D("100"),
        quantity=D("2"),
    )
    buy = SimpleNamespace(
        event_time=T0 + timedelta(seconds=31, milliseconds=500),
        trade_id=2,
        symbol="BTCUSDT",
        side="BUY",
        price=D("101"),
        quantity=D("2"),
    )
    assert [item.hook_id for item in detector.process_trade(
        sell,
        before=first.current,
        after=second.current,
        received_time=sell.event_time,
    )] == ["A17"]
    assert [item.hook_id for item in detector.process_trade(
        buy,
        before=second.current,
        after=third.current,
        received_time=buy.event_time,
    )] == ["A18"]

    no_replenishment = SimpleNamespace(
        event_time=T0 + timedelta(seconds=32, milliseconds=500),
        trade_id=3,
        symbol="BTCUSDT",
        side="BUY",
        price=D("101"),
        quantity=D("1"),
    )
    assert detector.process_trade(
        no_replenishment,
        before=third.current,
        after=fourth.current,
        received_time=no_replenishment.event_time,
    ) == ()
