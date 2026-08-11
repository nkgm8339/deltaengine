from __future__ import annotations

import random
from datetime import timedelta
from decimal import Decimal

import pytest

from src.orderflow.big_trades.price_path import SourcePricePathIndex
from tests.orderflow._big_trades_helpers import BASE, fill


def test_last_at_or_before_and_exact_range_extrema() -> None:
    path = SourcePricePathIndex(symbol="BTCUSDT", venue="BINANCE")
    trades = [
        fill(0, "100", trade_id=1),
        fill(10, "105", trade_id=2),
        fill(20, "98", trade_id=3),
        fill(30, "102", trade_id=4),
    ]
    for trade in trades:
        path.append(trade)
    assert path.last_at_or_before(BASE + timedelta(milliseconds=25)).trade_id == 3
    assert path.range_min_max(
        BASE + timedelta(milliseconds=10), BASE + timedelta(milliseconds=30)
    ) == (Decimal("98"), Decimal("105"))
    assert path.range_min_max_by_source_key(trades[1].source_key, trades[2].source_key) == (
        Decimal("98"),
        Decimal("105"),
    )


def test_range_index_matches_randomized_oracle() -> None:
    randomizer = random.Random(20260812)
    path = SourcePricePathIndex(symbol="BTCUSDT", venue="BINANCE")
    prices: list[Decimal] = []
    trades = []
    for index in range(1_000):
        price = Decimal(randomizer.randint(1, 100_000)) / Decimal("10")
        prices.append(price)
        trade = fill(index, str(price), trade_id=index + 1)
        trades.append(trade)
        path.append(trade)
    for _ in range(300):
        start = randomizer.randint(0, 999)
        end = randomizer.randint(start, 999)
        assert path.range_min_max_by_source_key(
            trades[start].source_key, trades[end].source_key
        ) == (min(prices[start : end + 1]), max(prices[start : end + 1]))


def test_price_path_rejects_non_increasing_source_keys() -> None:
    path = SourcePricePathIndex(symbol="BTCUSDT", venue="BINANCE")
    path.append(fill(10, trade_id=2))
    with pytest.raises(ValueError, match="strictly source ordered"):
        path.append(fill(10, trade_id=1))


def test_gap_intersection_uses_open_left_closed_right_interval() -> None:
    path = SourcePricePathIndex(symbol="BTCUSDT", venue="BINANCE")
    path.start_gap(BASE + timedelta(seconds=20))
    assert path.gap_intersects(BASE, BASE + timedelta(seconds=30)) is True
    path.end_gap(BASE + timedelta(seconds=40))
    assert path.gap_intersects(BASE + timedelta(seconds=40), BASE + timedelta(seconds=50)) is False
    assert path.gap_intersects(BASE, BASE + timedelta(seconds=20)) is True
