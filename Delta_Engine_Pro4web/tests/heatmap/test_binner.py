from __future__ import annotations

from decimal import Decimal

import pytest

from src.heatmap.binner import HeatmapGrid, bin_samples
from src.orderflow.orderbook import OrderBookSnapshot


def _snapshot(
    *,
    update_id: int,
    bids: list[tuple[object, object]],
    asks: list[tuple[object, object]],
) -> OrderBookSnapshot:
    return OrderBookSnapshot(
        symbol="BTCUSDT",
        last_update_id=update_id,
        bids=dict(bids),
        asks=dict(asks),
        event_time=None,
    )


def _one_level_snapshot(update_id: int) -> OrderBookSnapshot:
    price = Decimal("100") + Decimal(update_id)
    return _snapshot(
        update_id=update_id,
        bids=[(price, Decimal("1"))],
        asks=[(price + Decimal("1"), Decimal("2"))],
    )


def test_bin_boundaries_keep_bid_ask_layers_separate_and_decimal() -> None:
    snapshot = _snapshot(
        update_id=1,
        bids=[
            (Decimal("100.09"), Decimal("1.25")),
            (Decimal("100.01"), Decimal("2.75")),
        ],
        asks=[
            (Decimal("100.09"), Decimal("9")),
            (Decimal("100.10"), Decimal("3.5")),
            (Decimal("100.19"), Decimal("0.5")),
        ],
    )

    grid = bin_samples(
        [(1_000, snapshot)],
        price_bin=Decimal("0.1"),
        max_time_cols=10,
    )

    assert grid.price_bins == (Decimal("100.0"), Decimal("100.1"))
    assert grid.sample_times_ms == (1_000,)
    assert grid.bid_quantities == (
        (Decimal("4.00"),),
        (Decimal("0"),),
    )
    assert grid.ask_quantities == (
        (Decimal("9"),),
        (Decimal("4.0"),),
    )
    assert grid.gap_columns == (False,)
    assert grid.price_count == 2
    assert grid.time_count == 1
    assert all(
        isinstance(quantity, Decimal)
        for layer in (grid.bid_quantities, grid.ask_quantities)
        for row in layer
        for quantity in row
    )


def test_time_thinning_uses_integer_spacing_and_keeps_endpoints() -> None:
    samples = [
        (index * 1_000, _one_level_snapshot(index))
        for index in range(7)
    ]

    grid = bin_samples(
        samples,
        price_bin=Decimal("1"),
        max_time_cols=4,
    )

    # i * (7 - 1) // (4 - 1) selects source indices 0, 2, 4, 6.
    assert grid.sample_times_ms == (0, 2_000, 4_000, 6_000)
    assert grid.gap_columns == (False, False, False, False)


def test_one_time_column_keeps_newest_sample() -> None:
    samples = [
        (index * 1_000, _one_level_snapshot(index))
        for index in range(4)
    ]

    grid = bin_samples(
        samples,
        price_bin=Decimal("1"),
        max_time_cols=1,
    )

    assert grid.sample_times_ms == (3_000,)


def test_gap_splits_independently_thinned_segments_and_keeps_boundaries() -> None:
    first_times = (0, 1_000, 2_000, 3_000, 4_000, 5_000)
    second_times = (10_000, 11_000, 12_000, 13_000)
    first_samples = [
        (sample_time, _one_level_snapshot(index))
        for index, sample_time in enumerate(first_times)
    ]
    second_samples = [
        (sample_time, _one_level_snapshot(index + len(first_times)))
        for index, sample_time in enumerate(second_times)
    ]

    grid = bin_samples(
        first_samples + second_samples,
        price_bin=Decimal("1"),
        max_time_cols=3,
    )
    first_grid = bin_samples(
        first_samples,
        price_bin=Decimal("1"),
        max_time_cols=3,
    )
    second_grid = bin_samples(
        second_samples,
        price_bin=Decimal("1"),
        max_time_cols=3,
    )

    assert first_grid.sample_times_ms == (0, 2_000, 5_000)
    assert second_grid.sample_times_ms == (10_000, 11_000, 13_000)
    assert grid.sample_times_ms == (
        *first_grid.sample_times_ms,
        *second_grid.sample_times_ms,
    )
    assert grid.sample_times_ms[0] == first_times[0]
    assert grid.sample_times_ms[2] == first_times[-1]
    assert grid.sample_times_ms[3] == second_times[0]
    assert grid.sample_times_ms[-1] == second_times[-1]
    assert grid.gap_columns == (False, False, False, True, False, False)
    assert grid.time_count == 6


def test_shuffled_level_insertion_order_produces_identical_grid() -> None:
    bids = [
        (Decimal("100.25"), Decimal("1")),
        (Decimal("100.05"), Decimal("2")),
        (Decimal("100.15"), Decimal("3")),
    ]
    asks = [
        (Decimal("100.35"), Decimal("4")),
        (Decimal("100.45"), Decimal("5")),
        (Decimal("100.25"), Decimal("6")),
    ]
    forward = _snapshot(update_id=1, bids=bids, asks=asks)
    shuffled = _snapshot(
        update_id=1,
        bids=[bids[1], bids[2], bids[0]],
        asks=[asks[2], asks[0], asks[1]],
    )

    forward_grid = bin_samples(
        [(1_000, forward)],
        price_bin=Decimal("0.1"),
        max_time_cols=10,
    )
    shuffled_grid = bin_samples(
        [(1_000, shuffled)],
        price_bin=Decimal("0.1"),
        max_time_cols=10,
    )

    assert shuffled_grid == forward_grid


def test_empty_samples_return_well_shaped_empty_grid() -> None:
    grid = bin_samples(
        [],
        price_bin=Decimal("0.5"),
        max_time_cols=100,
    )

    assert grid == HeatmapGrid(
        price_bin=Decimal("0.5"),
        price_bins=(),
        sample_times_ms=(),
        bid_quantities=(),
        ask_quantities=(),
        gap_columns=(),
    )


@pytest.mark.parametrize(
    ("price_bin", "max_time_cols", "exception"),
    [
        (Decimal("0"), 1, ValueError),
        (Decimal("-1"), 1, ValueError),
        (Decimal("NaN"), 1, ValueError),
        (Decimal("1"), 0, ValueError),
        (Decimal("1"), True, TypeError),
    ],
)
def test_invalid_grid_parameters_are_rejected(
    price_bin: Decimal,
    max_time_cols: int,
    exception: type[Exception],
) -> None:
    with pytest.raises(exception):
        bin_samples([], price_bin=price_bin, max_time_cols=max_time_cols)


def test_non_monotonic_times_and_float_levels_are_rejected() -> None:
    valid_snapshot = _one_level_snapshot(1)
    with pytest.raises(ValueError, match="strictly increasing"):
        bin_samples(
            [(1_000, valid_snapshot), (1_000, valid_snapshot)],
            price_bin=Decimal("1"),
            max_time_cols=2,
        )

    float_snapshot = _snapshot(
        update_id=2,
        bids=[(100.0, Decimal("1"))],
        asks=[],
    )
    with pytest.raises(TypeError, match="Decimal or str"):
        bin_samples(
            [(1_000, float_snapshot)],
            price_bin=Decimal("1"),
            max_time_cols=1,
        )
