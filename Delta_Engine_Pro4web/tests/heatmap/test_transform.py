from __future__ import annotations

from decimal import Decimal

import pytest

from src.heatmap.transform import (
    GridIndex,
    PixelViewport,
    grid_cell_bounds,
    grid_cell_raster_bounds,
    grid_to_pixel,
    pixel_to_grid,
)


def _viewport() -> PixelViewport:
    return PixelViewport(
        left=Decimal("185.25"),
        top=Decimal("20.5"),
        width=Decimal("800"),
        height=Decimal("400"),
    )


def test_grid_pixel_grid_round_trip_for_every_cell() -> None:
    viewport = _viewport()

    for price_index in range(5):
        for time_index in range(8):
            pixel = grid_to_pixel(
                price_index,
                time_index,
                price_count=5,
                time_count=8,
                viewport=viewport,
            )
            restored = pixel_to_grid(
                pixel.x,
                pixel.y,
                price_count=5,
                time_count=8,
                viewport=viewport,
            )

            assert restored == GridIndex(
                price_index=price_index,
                time_index=time_index,
            )
            assert isinstance(pixel.x, Decimal)
            assert isinstance(pixel.y, Decimal)


def test_cell_bounds_match_all_viewport_endpoints_exactly() -> None:
    viewport = _viewport()
    lowest_price_first_time = grid_cell_bounds(
        0,
        0,
        price_count=2,
        time_count=4,
        viewport=viewport,
    )
    highest_price_last_time = grid_cell_bounds(
        1,
        3,
        price_count=2,
        time_count=4,
        viewport=viewport,
    )

    assert lowest_price_first_time.left == viewport.left
    assert lowest_price_first_time.bottom == viewport.bottom
    assert highest_price_last_time.right == viewport.right
    assert highest_price_last_time.top == viewport.top


def test_viewport_corner_pixels_resolve_to_expected_grid_endpoints() -> None:
    viewport = _viewport()

    top_left = pixel_to_grid(
        viewport.left,
        viewport.top,
        price_count=3,
        time_count=4,
        viewport=viewport,
    )
    bottom_right = pixel_to_grid(
        viewport.right,
        viewport.bottom,
        price_count=3,
        time_count=4,
        viewport=viewport,
    )

    assert top_left == GridIndex(price_index=2, time_index=0)
    assert bottom_right == GridIndex(price_index=0, time_index=3)


def test_positive_plot_offset_never_becomes_negative_x_regression() -> None:
    viewport = _viewport()
    first_cell = grid_cell_bounds(
        0,
        0,
        price_count=5,
        time_count=8,
        viewport=viewport,
    )
    first_center = grid_to_pixel(
        0,
        0,
        price_count=5,
        time_count=8,
        viewport=viewport,
    )

    # Regression guard for the historical x=-185.25px offset error.
    assert first_cell.left == Decimal("185.25")
    assert first_center.x == Decimal("235.25")
    assert first_cell.left >= Decimal("0")
    assert first_center.x >= Decimal("0")

    for time_index in range(8):
        cell = grid_cell_bounds(
            0,
            time_index,
            price_count=5,
            time_count=8,
            viewport=viewport,
        )
        assert cell.left >= viewport.left
        assert cell.right <= viewport.right


def test_raster_bounds_share_edges_and_cover_integral_viewport() -> None:
    viewport = PixelViewport(
        left=Decimal("10"),
        top=Decimal("20"),
        width=Decimal("7"),
        height=Decimal("5"),
    )
    time_cells = [
        grid_cell_raster_bounds(
            0,
            time_index,
            price_count=1,
            time_count=3,
            viewport=viewport,
        )
        for time_index in range(3)
    ]
    price_cells = [
        grid_cell_raster_bounds(
            price_index,
            0,
            price_count=3,
            time_count=1,
            viewport=viewport,
        )
        for price_index in range(3)
    ]

    assert time_cells[0].left == 10
    assert time_cells[-1].right == 17
    assert time_cells[0].right == time_cells[1].left
    assert time_cells[1].right == time_cells[2].left
    assert price_cells[2].top == 20
    assert price_cells[0].bottom == 25
    assert price_cells[2].bottom == price_cells[1].top
    assert price_cells[1].bottom == price_cells[0].top


@pytest.mark.parametrize(
    "viewport",
    [
        PixelViewport(
            left=Decimal("0"),
            top=Decimal("0"),
            width=Decimal("1"),
            height=Decimal("1"),
        ),
        PixelViewport(
            left=Decimal("10.25"),
            top=Decimal("5.75"),
            width=Decimal("100"),
            height=Decimal("50"),
        ),
    ],
)
def test_all_generated_coordinates_are_non_negative(
    viewport: PixelViewport,
) -> None:
    for price_index in range(4):
        for time_index in range(6):
            cell = grid_cell_bounds(
                price_index,
                time_index,
                price_count=4,
                time_count=6,
                viewport=viewport,
            )
            center = grid_to_pixel(
                price_index,
                time_index,
                price_count=4,
                time_count=6,
                viewport=viewport,
            )
            assert min(
                cell.left,
                cell.top,
                cell.right,
                cell.bottom,
                center.x,
                center.y,
            ) >= Decimal("0")


def test_invalid_shape_indices_and_pixel_coordinates_are_rejected() -> None:
    viewport = _viewport()

    with pytest.raises(TypeError, match="not bool"):
        grid_to_pixel(
            0,
            False,
            price_count=2,
            time_count=2,
            viewport=viewport,
        )
    with pytest.raises(IndexError, match="outside"):
        grid_to_pixel(
            2,
            0,
            price_count=2,
            time_count=2,
            viewport=viewport,
        )
    with pytest.raises(ValueError, match="within"):
        pixel_to_grid(
            viewport.left - Decimal("0.01"),
            viewport.top,
            price_count=2,
            time_count=2,
            viewport=viewport,
        )
    with pytest.raises(ValueError, match="positive"):
        grid_to_pixel(
            0,
            0,
            price_count=0,
            time_count=2,
            viewport=viewport,
        )


def test_viewport_rejects_negative_origin_and_non_decimal_geometry() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        PixelViewport(
            left=Decimal("-0.01"),
            top=Decimal("0"),
            width=Decimal("10"),
            height=Decimal("10"),
        )
    with pytest.raises(TypeError, match="must be Decimal"):
        PixelViewport(
            left=0,
            top=Decimal("0"),
            width=Decimal("10"),
            height=Decimal("10"),
        )
