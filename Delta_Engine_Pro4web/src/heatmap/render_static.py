"""Dependency-free static PNG renderer for :class:`HeatmapGrid`.

The renderer deliberately keeps all coordinate arithmetic in ``transform``.
It paints half-open integer rectangles into an RGB buffer and emits a small,
deterministic PNG using only the Python standard library.
"""

from __future__ import annotations

import binascii
import logging
import struct
import time
import zlib
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable

from src.heatmap.binner import HeatmapGrid
from src.heatmap.transform import (
    PixelViewport,
    RasterRect,
    grid_cell_raster_bounds,
)


_LOGGER = logging.getLogger(__name__)
_ZERO = Decimal("0")
_ONE = Decimal("1")
_HUNDRED = Decimal("100")
_MIN_INTENSITY = Decimal("32")
_INTENSITY_SPAN = Decimal("223")
_BACKGROUND = (0, 0, 0)


@dataclass(frozen=True)
class RenderReport:
    """Measured output contract for one static render."""

    output_path: Path
    width: int
    height: int
    price_bins: int
    time_cols: int
    gap_columns: int
    bytes_written: int
    aggregation_ms: Decimal
    transform_ms: Decimal
    render_ms: Decimal
    total_ms: Decimal


@dataclass(frozen=True)
class _LayerScale:
    lower: Decimal
    upper: Decimal


def render_heatmap(
    grid: HeatmapGrid,
    viewport: PixelViewport,
    out_path: Path | str,
) -> RenderReport:
    """Render ``grid`` to an RGB PNG using ``viewport`` geometry.

    ``grid`` is already aggregated by ``bin_samples``; therefore
    ``aggregation_ms`` is explicitly reported as zero. Transform timing covers
    all calls to ``grid_cell_raster_bounds``. Render timing covers color-scale
    preparation, half-open pixel painting, PNG encoding, and file output.
    """

    if not isinstance(grid, HeatmapGrid):
        raise TypeError("grid must be a HeatmapGrid")
    if not isinstance(viewport, PixelViewport):
        raise TypeError("viewport must be a PixelViewport")
    if grid.price_count == 0 or grid.time_count == 0:
        raise ValueError("cannot render an empty heatmap grid")

    output_path = Path(out_path)
    total_start_ns = time.perf_counter_ns()

    transform_start_ns = time.perf_counter_ns()
    raster_cells = tuple(
        tuple(
            grid_cell_raster_bounds(
                price_index,
                time_index,
                price_count=grid.price_count,
                time_count=grid.time_count,
                viewport=viewport,
            )
            for time_index in range(grid.time_count)
        )
        for price_index in range(grid.price_count)
    )
    transform_ms = _elapsed_ms(transform_start_ns, time.perf_counter_ns())

    width = max(cell.right for row in raster_cells for cell in row)
    height = max(cell.bottom for row in raster_cells for cell in row)
    if width <= 0 or height <= 0:
        raise ValueError("viewport produces an empty raster")

    render_start_ns = time.perf_counter_ns()
    bid_scale = _build_scale(
        quantity
        for row in grid.bid_quantities
        for quantity in row
    )
    ask_scale = _build_scale(
        quantity
        for row in grid.ask_quantities
        for quantity in row
    )
    pixels = bytearray(width * height * 3)

    for price_index, row_cells in enumerate(raster_cells):
        for time_index, cell in enumerate(row_cells):
            if grid.gap_columns[time_index]:
                continue
            bid_intensity = _intensity(
                grid.bid_quantities[price_index][time_index],
                bid_scale,
            )
            ask_intensity = _intensity(
                grid.ask_quantities[price_index][time_index],
                ask_scale,
            )
            if bid_intensity == 0 and ask_intensity == 0:
                continue
            _paint_cell(
                pixels,
                width=width,
                height=height,
                cell=cell,
                bid_intensity=bid_intensity,
                ask_intensity=ask_intensity,
            )

    png_bytes = _encode_rgb_png(width, height, pixels)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(png_bytes)
    render_ms = _elapsed_ms(render_start_ns, time.perf_counter_ns())
    total_ms = _elapsed_ms(total_start_ns, time.perf_counter_ns())
    report = RenderReport(
        output_path=output_path,
        width=width,
        height=height,
        price_bins=grid.price_count,
        time_cols=grid.time_count,
        gap_columns=sum(grid.gap_columns),
        bytes_written=len(png_bytes),
        aggregation_ms=_ZERO,
        transform_ms=transform_ms,
        render_ms=render_ms,
        total_ms=total_ms,
    )
    _LOGGER.info(
        "heatmap render output=%s width=%d height=%d "
        "aggregation_ms=%s transform_ms=%s render_ms=%s total_ms=%s",
        report.output_path,
        report.width,
        report.height,
        report.aggregation_ms,
        report.transform_ms,
        report.render_ms,
        report.total_ms,
    )
    return report


def _build_scale(quantities: Iterable[Decimal]) -> _LayerScale | None:
    transformed = sorted(
        ((_ONE + quantity).ln() for quantity in quantities if quantity > _ZERO),
    )
    if not transformed:
        return None
    return _LayerScale(
        lower=_quantile(transformed, Decimal("1")),
        upper=_quantile(transformed, Decimal("99")),
    )


def _quantile(values: list[Decimal], percentile: Decimal) -> Decimal:
    if not values:
        raise ValueError("quantile requires at least one value")
    if percentile < _ZERO or percentile > _HUNDRED:
        raise ValueError("percentile must be between zero and one hundred")
    if len(values) == 1:
        return values[0]
    position = Decimal(len(values) - 1) * percentile / _HUNDRED
    lower_index = int(position.to_integral_value(rounding=ROUND_FLOOR))
    upper_index = int(position.to_integral_value(rounding=ROUND_CEILING))
    if lower_index == upper_index:
        return values[lower_index]
    fraction = position - Decimal(lower_index)
    return values[lower_index] + (
        (values[upper_index] - values[lower_index]) * fraction
    )


def _intensity(quantity: Decimal, scale: _LayerScale | None) -> int:
    if quantity <= _ZERO or scale is None:
        return 0
    transformed = (_ONE + quantity).ln()
    if scale.lower == scale.upper:
        return 255
    clipped = min(max(transformed, scale.lower), scale.upper)
    normalized = (clipped - scale.lower) / (scale.upper - scale.lower)
    value = _MIN_INTENSITY + (_INTENSITY_SPAN * normalized)
    return int(value.to_integral_value(rounding=ROUND_HALF_UP))


def _paint_cell(
    pixels: bytearray,
    *,
    width: int,
    height: int,
    cell: RasterRect,
    bid_intensity: int,
    ask_intensity: int,
) -> None:
    left = max(0, cell.left)
    top = max(0, cell.top)
    right = min(width, cell.right)
    bottom = min(height, cell.bottom)
    if left >= right or top >= bottom:
        return
    for y in range(top, bottom):
        row_offset = y * width * 3
        for x in range(left, right):
            pixel_offset = row_offset + x * 3
            # Separate layer channels are combined without adding quantities.
            pixels[pixel_offset] = max(pixels[pixel_offset], ask_intensity)
            pixels[pixel_offset + 1] = max(pixels[pixel_offset + 1], 0)
            pixels[pixel_offset + 2] = max(
                pixels[pixel_offset + 2],
                bid_intensity,
            )


def _encode_rgb_png(width: int, height: int, pixels: bytearray) -> bytes:
    row_stride = width * 3
    scanlines = bytearray()
    for row in range(height):
        scanlines.append(0)
        start = row * row_stride
        scanlines.extend(pixels[start : start + row_stride])
    signature = b"\x89PNG\r\n\x1a\n"
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return signature + _png_chunk(b"IHDR", header) + _png_chunk(
        b"IDAT",
        zlib.compress(bytes(scanlines)),
    ) + _png_chunk(b"IEND", b"")


def _png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    length = struct.pack(">I", len(payload))
    checksum = struct.pack(">I", binascii.crc32(chunk_type + payload) & 0xFFFFFFFF)
    return length + chunk_type + payload + checksum


def _elapsed_ms(start_ns: int, end_ns: int) -> Decimal:
    return Decimal(end_ns - start_ns) / Decimal("1000000")
