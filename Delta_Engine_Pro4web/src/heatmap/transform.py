"""Pure grid-to-pixel transforms for heatmap rendering.

The heatmap grid stores prices in ascending order, while a screen places its
highest row at the top. These functions therefore map price index zero to the
bottom row and the highest price index to the top row. Time always advances
from left to right.

All exact pixel geometry uses ``Decimal``. The only integer conversion needed
by raster renderers is centralized in :func:`grid_cell_raster_bounds`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP


_ZERO = Decimal("0")
_TWO = Decimal("2")


@dataclass(frozen=True)
class PixelViewport:
    """Non-negative pixel-space drawing area."""

    left: Decimal
    top: Decimal
    width: Decimal
    height: Decimal

    def __post_init__(self) -> None:
        for field_name in ("left", "top", "width", "height"):
            value = getattr(self, field_name)
            if not isinstance(value, Decimal):
                raise TypeError(f"{field_name} must be Decimal")
            if not value.is_finite():
                raise ValueError(f"{field_name} must be finite")
        if self.left < _ZERO or self.top < _ZERO:
            raise ValueError("viewport origin must not be negative")
        if self.width <= _ZERO or self.height <= _ZERO:
            raise ValueError("viewport width and height must be positive")

    @property
    def right(self) -> Decimal:
        return self.left + self.width

    @property
    def bottom(self) -> Decimal:
        return self.top + self.height


@dataclass(frozen=True)
class GridIndex:
    """A heatmap cell index: ascending price row and ascending time column."""

    price_index: int
    time_index: int


@dataclass(frozen=True)
class PixelPoint:
    """Exact fixed-point pixel coordinate."""

    x: Decimal
    y: Decimal


@dataclass(frozen=True)
class PixelRect:
    """Exact half-open pixel rectangle ``[left, right) x [top, bottom)``."""

    left: Decimal
    top: Decimal
    right: Decimal
    bottom: Decimal


@dataclass(frozen=True)
class RasterRect:
    """Integer pixel rectangle for a raster drawing backend."""

    left: int
    top: int
    right: int
    bottom: int


def grid_to_pixel(
    price_index: int,
    time_index: int,
    *,
    price_count: int,
    time_count: int,
    viewport: PixelViewport,
) -> PixelPoint:
    """Map one grid cell to its exact pixel-space center."""

    cell = grid_cell_bounds(
        price_index,
        time_index,
        price_count=price_count,
        time_count=time_count,
        viewport=viewport,
    )
    return PixelPoint(
        x=(cell.left + cell.right) / _TWO,
        y=(cell.top + cell.bottom) / _TWO,
    )


def pixel_to_grid(
    x: Decimal,
    y: Decimal,
    *,
    price_count: int,
    time_count: int,
    viewport: PixelViewport,
) -> GridIndex:
    """Return the grid cell containing an exact pixel coordinate.

    The right and bottom viewport edges are inclusive and resolve to the last
    time column and lowest price row respectively.
    """

    _validate_shape(price_count=price_count, time_count=time_count)
    _validate_pixel_coordinate(x, name="x")
    _validate_pixel_coordinate(y, name="y")
    if x < viewport.left or x > viewport.right:
        raise ValueError("x must be within the viewport")
    if y < viewport.top or y > viewport.bottom:
        raise ValueError("y must be within the viewport")

    time_position = (
        (x - viewport.left) * Decimal(time_count) / viewport.width
    )
    row_from_top_position = (
        (y - viewport.top) * Decimal(price_count) / viewport.height
    )
    time_index = min(
        int(time_position.to_integral_value(rounding=ROUND_FLOOR)),
        time_count - 1,
    )
    row_from_top = min(
        int(row_from_top_position.to_integral_value(rounding=ROUND_FLOOR)),
        price_count - 1,
    )
    return GridIndex(
        price_index=price_count - row_from_top - 1,
        time_index=time_index,
    )


def grid_cell_bounds(
    price_index: int,
    time_index: int,
    *,
    price_count: int,
    time_count: int,
    viewport: PixelViewport,
) -> PixelRect:
    """Return exact bounds for a grid cell without binary floating point."""

    _validate_shape(price_count=price_count, time_count=time_count)
    _validate_index(price_index, count=price_count, name="price_index")
    _validate_index(time_index, count=time_count, name="time_index")

    time_denominator = Decimal(time_count)
    price_denominator = Decimal(price_count)
    row_from_top = price_count - price_index - 1
    left = (
        viewport.left
        + viewport.width * Decimal(time_index) / time_denominator
    )
    right = (
        viewport.left
        + viewport.width * Decimal(time_index + 1) / time_denominator
    )
    top = (
        viewport.top
        + viewport.height * Decimal(row_from_top) / price_denominator
    )
    bottom = (
        viewport.top
        + viewport.height * Decimal(row_from_top + 1) / price_denominator
    )
    return PixelRect(left=left, top=top, right=right, bottom=bottom)


def grid_cell_raster_bounds(
    price_index: int,
    time_index: int,
    *,
    price_count: int,
    time_count: int,
    viewport: PixelViewport,
) -> RasterRect:
    """Return consistently rounded integer bounds for a raster renderer."""

    cell = grid_cell_bounds(
        price_index,
        time_index,
        price_count=price_count,
        time_count=time_count,
        viewport=viewport,
    )
    return RasterRect(
        left=_pixel_edge_to_int(cell.left),
        top=_pixel_edge_to_int(cell.top),
        right=_pixel_edge_to_int(cell.right),
        bottom=_pixel_edge_to_int(cell.bottom),
    )


def _pixel_edge_to_int(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_HALF_UP))


def _validate_shape(*, price_count: int, time_count: int) -> None:
    for name, count in (
        ("price_count", price_count),
        ("time_count", time_count),
    ):
        if isinstance(count, bool) or not isinstance(count, int):
            raise TypeError(f"{name} must be an int, not bool")
        if count <= 0:
            raise ValueError(f"{name} must be positive")


def _validate_index(index: int, *, count: int, name: str) -> None:
    if isinstance(index, bool) or not isinstance(index, int):
        raise TypeError(f"{name} must be an int, not bool")
    if index < 0 or index >= count:
        raise IndexError(f"{name} is outside the grid")


def _validate_pixel_coordinate(value: Decimal, *, name: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be Decimal")
    if not value.is_finite():
        raise ValueError(f"{name} must be finite")
