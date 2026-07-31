from __future__ import annotations

import logging
import struct
import zlib
from decimal import Decimal
from pathlib import Path

from src.heatmap.binner import bin_samples
from src.heatmap.render_static import render_heatmap
from src.heatmap.transform import PixelViewport, grid_cell_raster_bounds
from src.orderflow.orderbook import OrderBookSnapshot


def _snapshot(
    update_id: int,
    *,
    bid_quantity: str,
    ask_quantity: str,
) -> OrderBookSnapshot:
    return OrderBookSnapshot(
        symbol="BTCUSDT",
        last_update_id=update_id,
        bids={Decimal("100"): Decimal(bid_quantity)},
        asks={Decimal("101"): Decimal(ask_quantity)},
        event_time=None,
    )


def _grid_with_gap():
    return bin_samples(
        [
            (0, _snapshot(1, bid_quantity="4", ask_quantity="2")),
            (1_000, _snapshot(2, bid_quantity="8", ask_quantity="3")),
            (3_000, _snapshot(3, bid_quantity="16", ask_quantity="5")),
        ],
        price_bin=Decimal("1"),
        max_time_cols=10,
    )


def _read_rgb_png(path: Path) -> tuple[int, int, list[list[tuple[int, int, int]]]]:
    data = path.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    width, height, bit_depth, color_type, _, _, _ = struct.unpack(
        ">IIBBBBB",
        data[16:29],
    )
    assert bit_depth == 8
    assert color_type == 2
    offset = 8
    compressed = bytearray()
    while offset < len(data):
        chunk_length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        payload_start = offset + 8
        payload_end = payload_start + chunk_length
        if chunk_type == b"IDAT":
            compressed.extend(data[payload_start:payload_end])
        offset = payload_end + 4
    raw = zlib.decompress(bytes(compressed))
    row_stride = width * 3
    rows: list[list[tuple[int, int, int]]] = []
    for row in range(height):
        row_start = row * (row_stride + 1)
        assert raw[row_start] == 0
        pixels = raw[row_start + 1 : row_start + 1 + row_stride]
        rows.append([
            tuple(pixels[index : index + 3])
            for index in range(0, row_stride, 3)
        ])
    return width, height, rows


def _pixels_in_rect(
    rows: list[list[tuple[int, int, int]]],
    *,
    left: int,
    top: int,
    right: int,
    bottom: int,
) -> list[tuple[int, int, int]]:
    return [
        rows[y][x]
        for y in range(top, bottom)
        for x in range(left, right)
    ]


def test_render_creates_visible_png_with_report_and_gap_blank(
    tmp_path: Path,
    caplog,
) -> None:
    grid = _grid_with_gap()
    viewport = PixelViewport(
        left=Decimal("2"),
        top=Decimal("3"),
        width=Decimal("20"),
        height=Decimal("12"),
    )
    output = tmp_path / "heatmap.png"

    with caplog.at_level(logging.INFO):
        report = render_heatmap(grid, viewport, output)

    width, height, rows = _read_rgb_png(output)
    assert output.exists()
    assert (width, height) == (22, 15)
    assert report.output_path == output
    assert report.width == width
    assert report.height == height
    assert report.price_bins == 2
    assert report.time_cols == 3
    assert report.gap_columns == 1
    assert report.bytes_written == output.stat().st_size
    assert report.aggregation_ms == Decimal("0")
    assert report.transform_ms >= Decimal("0")
    assert report.render_ms >= Decimal("0")
    assert report.total_ms >= Decimal("0")
    assert "aggregation_ms=" in caplog.text
    assert "transform_ms=" in caplog.text
    assert "render_ms=" in caplog.text
    assert "total_ms=" in caplog.text

    gap_cell = grid_cell_raster_bounds(
        0,
        2,
        price_count=grid.price_count,
        time_count=grid.time_count,
        viewport=viewport,
    )
    gap_pixels = _pixels_in_rect(
        rows,
        left=gap_cell.left,
        top=gap_cell.top,
        right=gap_cell.right,
        bottom=gap_cell.bottom,
    )
    assert gap_pixels
    assert set(gap_pixels) == {(0, 0, 0)}

    bid_cell = grid_cell_raster_bounds(
        0,
        0,
        price_count=grid.price_count,
        time_count=grid.time_count,
        viewport=viewport,
    )
    bid_pixels = _pixels_in_rect(
        rows,
        left=bid_cell.left,
        top=bid_cell.top,
        right=bid_cell.right,
        bottom=bid_cell.bottom,
    )
    assert any(blue > 0 and red == 0 for red, _, blue in bid_pixels)

    ask_cell = grid_cell_raster_bounds(
        1,
        0,
        price_count=grid.price_count,
        time_count=grid.time_count,
        viewport=viewport,
    )
    ask_pixels = _pixels_in_rect(
        rows,
        left=ask_cell.left,
        top=ask_cell.top,
        right=ask_cell.right,
        bottom=ask_cell.bottom,
    )
    assert any(red > 0 and blue == 0 for red, _, blue in ask_pixels)


def test_adjacent_raster_cells_are_half_open_and_cover_viewport_once() -> None:
    viewport = PixelViewport(
        left=Decimal("2"),
        top=Decimal("3"),
        width=Decimal("7"),
        height=Decimal("5"),
    )
    rectangles = [
        grid_cell_raster_bounds(
            price_index,
            time_index,
            price_count=2,
            time_count=3,
            viewport=viewport,
        )
        for price_index in range(2)
        for time_index in range(3)
    ]

    for price_index in range(2):
        first_row = [
            grid_cell_raster_bounds(
                price_index,
                time_index,
                price_count=2,
                time_count=3,
                viewport=viewport,
            )
            for time_index in range(3)
        ]
        assert first_row[0].left == 2
        assert first_row[-1].right == 9
        assert all(
            first_row[index].right == first_row[index + 1].left
            for index in range(2)
        )

    for time_index in range(3):
        first_column = [
            grid_cell_raster_bounds(
                price_index,
                time_index,
                price_count=2,
                time_count=3,
                viewport=viewport,
            )
            for price_index in range(2)
        ]
        assert first_column[1].bottom == first_column[0].top

    covered: set[tuple[int, int]] = set()
    for rectangle in rectangles:
        for y in range(rectangle.top, rectangle.bottom):
            for x in range(rectangle.left, rectangle.right):
                point = (x, y)
                assert point not in covered
                covered.add(point)
    expected = {
        (x, y)
        for x in range(2, 9)
        for y in range(3, 8)
    }
    assert covered == expected


def test_render_rejects_empty_grid(tmp_path: Path) -> None:
    grid = bin_samples(
        [],
        price_bin=Decimal("1"),
        max_time_cols=10,
    )
    viewport = PixelViewport(
        left=Decimal("0"),
        top=Decimal("0"),
        width=Decimal("10"),
        height=Decimal("10"),
    )

    try:
        render_heatmap(grid, viewport, tmp_path / "empty.png")
    except ValueError as exc:
        assert "empty" in str(exc)
    else:
        raise AssertionError("empty grid must be rejected")
