"""Deterministic Decimal-only aggregation for heatmap samples.

The output matrix orientation is price row by time column. Bid and ask
quantities remain in separate layers, and all public axes are ascending.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

from src.orderflow.orderbook import OrderBookSnapshot


_ZERO = Decimal("0")


@dataclass(frozen=True)
class HeatmapGrid:
    """Price-by-time quantity grid consumed by the rendering layer.

    ``gap_columns[index]`` marks a discontinuity immediately before the
    corresponding time column. A renderer can therefore leave that column
    blank instead of visually bridging a missing interval.
    """

    price_bin: Decimal
    price_bins: tuple[Decimal, ...]
    sample_times_ms: tuple[int, ...]
    bid_quantities: tuple[tuple[Decimal, ...], ...]
    ask_quantities: tuple[tuple[Decimal, ...], ...]
    gap_columns: tuple[bool, ...]

    def __post_init__(self) -> None:
        time_count = len(self.sample_times_ms)
        price_count = len(self.price_bins)
        if len(self.gap_columns) != time_count:
            raise ValueError("gap_columns must match the time-axis length")
        if len(self.bid_quantities) != price_count:
            raise ValueError("bid_quantities must match the price-axis length")
        if len(self.ask_quantities) != price_count:
            raise ValueError("ask_quantities must match the price-axis length")
        if any(len(row) != time_count for row in self.bid_quantities):
            raise ValueError("every bid row must match the time-axis length")
        if any(len(row) != time_count for row in self.ask_quantities):
            raise ValueError("every ask row must match the time-axis length")

    @property
    def price_count(self) -> int:
        return len(self.price_bins)

    @property
    def time_count(self) -> int:
        return len(self.sample_times_ms)


def bin_samples(
    samples: Iterable[tuple[int, OrderBookSnapshot]],
    price_bin: Decimal,
    max_time_cols: int,
) -> HeatmapGrid:
    """Aggregate sampled books into a deterministic heatmap grid.

    Time thinning keeps both endpoints and chooses each retained source index
    with ``i * (sample_count - 1) // (max_time_cols - 1)``. This integer-only
    rule is deterministic and introduces no binary floating-point values. If
    only one column is requested, the newest sample is retained.

    A nominal sample interval is inferred as the smallest adjacent event-time
    delta before thinning. Larger deltas are gaps. The input is split
    immediately before each gap column, and every resulting segment is thinned
    independently with ``max_time_cols`` as its own upper bound. This retains
    both sides of a discontinuity instead of selecting across it.
    """

    normalized_price_bin = _decimal_value(price_bin, field="price_bin")
    if normalized_price_bin <= _ZERO:
        raise ValueError("price_bin must be greater than zero")
    if isinstance(max_time_cols, bool) or not isinstance(max_time_cols, int):
        raise TypeError("max_time_cols must be an int, not bool")
    if max_time_cols <= 0:
        raise ValueError("max_time_cols must be greater than zero")

    source_samples = tuple(samples)
    _validate_sample_times(source_samples)
    source_gaps = _detect_source_gaps(source_samples)
    selected_indices = _select_segment_indices(source_gaps, max_time_cols)
    selected_gaps = tuple(source_gaps[index] for index in selected_indices)

    selected_times: list[int] = []
    bid_columns: list[dict[Decimal, Decimal]] = []
    ask_columns: list[dict[Decimal, Decimal]] = []
    all_price_bins: set[Decimal] = set()

    for source_index in selected_indices:
        sample_time_ms, snapshot = source_samples[source_index]
        if not isinstance(snapshot, OrderBookSnapshot):
            raise TypeError("each sample snapshot must be an OrderBookSnapshot")

        selected_times.append(sample_time_ms)
        bid_column = _aggregate_side(
            snapshot.bids,
            price_bin=normalized_price_bin,
            descending=True,
            side_name="bids",
        )
        ask_column = _aggregate_side(
            snapshot.asks,
            price_bin=normalized_price_bin,
            descending=False,
            side_name="asks",
        )
        bid_columns.append(bid_column)
        ask_columns.append(ask_column)
        all_price_bins.update(bid_column)
        all_price_bins.update(ask_column)

    price_axis = tuple(sorted(all_price_bins))
    bid_rows = tuple(
        tuple(column.get(price, _ZERO) for column in bid_columns)
        for price in price_axis
    )
    ask_rows = tuple(
        tuple(column.get(price, _ZERO) for column in ask_columns)
        for price in price_axis
    )

    return HeatmapGrid(
        price_bin=normalized_price_bin,
        price_bins=price_axis,
        sample_times_ms=tuple(selected_times),
        bid_quantities=bid_rows,
        ask_quantities=ask_rows,
        gap_columns=selected_gaps,
    )


def _validate_sample_times(
    samples: tuple[tuple[int, OrderBookSnapshot], ...],
) -> None:
    previous: int | None = None
    for sample in samples:
        if not isinstance(sample, tuple) or len(sample) != 2:
            raise TypeError("each sample must be a (sample_time_ms, snapshot) tuple")
        sample_time_ms = sample[0]
        if isinstance(sample_time_ms, bool) or not isinstance(sample_time_ms, int):
            raise TypeError("sample_time_ms must be an int, not bool")
        if sample_time_ms < 0:
            raise ValueError("sample_time_ms must not be negative")
        if previous is not None and sample_time_ms <= previous:
            raise ValueError("sample_time_ms values must be strictly increasing")
        previous = sample_time_ms


def _select_time_indices(sample_count: int, max_time_cols: int) -> tuple[int, ...]:
    if sample_count <= max_time_cols:
        return tuple(range(sample_count))
    if max_time_cols == 1:
        return (sample_count - 1,)
    return tuple(
        retained_index * (sample_count - 1) // (max_time_cols - 1)
        for retained_index in range(max_time_cols)
    )


def _detect_source_gaps(
    samples: tuple[tuple[int, OrderBookSnapshot], ...],
) -> tuple[bool, ...]:
    if len(samples) < 2:
        return (False,) * len(samples)
    deltas = tuple(
        samples[index][0] - samples[index - 1][0]
        for index in range(1, len(samples))
    )
    nominal_interval = min(deltas)
    return (False,) + tuple(delta > nominal_interval for delta in deltas)


def _select_segment_indices(
    source_gaps: tuple[bool, ...],
    max_time_cols: int,
) -> tuple[int, ...]:
    """Thin each continuous segment without selecting across a gap."""

    if not source_gaps:
        return ()

    segment_starts = (0,) + tuple(
        index
        for index in range(1, len(source_gaps))
        if source_gaps[index]
    )
    segment_ends = segment_starts[1:] + (len(source_gaps),)
    selected_indices: list[int] = []

    for start, end in zip(segment_starts, segment_ends):
        segment_count = end - start
        selected_indices.extend(
            start + local_index
            for local_index in _select_time_indices(
                segment_count,
                max_time_cols,
            )
        )
    return tuple(selected_indices)


def _aggregate_side(
    levels: Mapping[object, object],
    *,
    price_bin: Decimal,
    descending: bool,
    side_name: str,
) -> dict[Decimal, Decimal]:
    normalized_levels: list[tuple[Decimal, Decimal]] = []
    for raw_price, raw_quantity in levels.items():
        price = _decimal_value(raw_price, field=f"{side_name}.price")
        quantity = _decimal_value(raw_quantity, field=f"{side_name}.quantity")
        if price <= _ZERO:
            raise ValueError(f"{side_name} prices must be greater than zero")
        if quantity < _ZERO:
            raise ValueError(f"{side_name} quantities must not be negative")
        normalized_levels.append((price, quantity))

    # Normalize input explicitly instead of relying on mapping insertion order.
    normalized_levels.sort(key=lambda level: level[0], reverse=descending)

    aggregated: dict[Decimal, Decimal] = {}
    for price, quantity in normalized_levels:
        if quantity == _ZERO:
            continue
        bin_price = (
            (price / price_bin).to_integral_value(rounding=ROUND_FLOOR)
            * price_bin
        )
        aggregated[bin_price] = aggregated.get(bin_price, _ZERO) + quantity
    return aggregated


def _decimal_value(value: object, *, field: str) -> Decimal:
    if isinstance(value, bool):
        raise TypeError(f"{field} must be Decimal or str, not bool")
    if isinstance(value, Decimal):
        decimal_value = value
    elif isinstance(value, str):
        try:
            decimal_value = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError(f"{field} is not a valid Decimal string") from exc
    else:
        raise TypeError(f"{field} must be Decimal or str")
    if not decimal_value.is_finite():
        raise ValueError(f"{field} must be finite")
    return decimal_value
