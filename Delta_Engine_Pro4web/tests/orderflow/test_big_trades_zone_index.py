from __future__ import annotations

import random
from dataclasses import replace
from decimal import Decimal

from src.orderflow.big_trades.zone_index import ReactionZoneBoundaryIndex
from tests.orderflow._big_trades_helpers import event_zone


def _zone(identifier: int, low: int, high: int):
    _, template, _ = event_zone()
    return replace(
        template,
        zone_id=f"zone-{identifier}",
        zone_low=Decimal(low),
        zone_high=Decimal(high),
    )


def test_point_and_boundary_queries_match_brute_force_randomized_oracle() -> None:
    randomizer = random.Random(20260812)
    zones = []
    for identifier in range(400):
        low = randomizer.randint(1, 2_000)
        zones.append(_zone(identifier, low, low + randomizer.randint(0, 50)))
    index = ReactionZoneBoundaryIndex(zones)

    for _ in range(300):
        previous = Decimal(randomizer.randint(1, 2_100))
        current = Decimal(randomizer.randint(1, 2_100))
        lower, upper = sorted((previous, current))
        expected_containing = tuple(
            sorted(zone.zone_id for zone in zones if zone.zone_low <= current <= zone.zone_high)
        )
        expected_crossed = tuple(
            sorted(
                zone.zone_id
                for zone in zones
                if lower < zone.zone_low <= upper or lower < zone.zone_high <= upper
            )
        )
        assert index.containing(current) == expected_containing
        assert index.crossed_boundaries(previous, current) == expected_crossed
        assert index.candidates(previous, current) == tuple(
            sorted(
                set(expected_crossed)
                | {zone.zone_id for zone in zones if zone.zone_low <= previous <= zone.zone_high}
                | set(expected_containing)
            )
        )


def test_index_keeps_5000_zones_and_removes_only_explicit_target() -> None:
    zones = [_zone(identifier, identifier, identifier + 2) for identifier in range(5_000)]
    index = ReactionZoneBoundaryIndex(zones)
    assert len(index) == 5_000
    assert "zone-2500" in index.containing(Decimal("2501"))
    index.remove("zone-2500")
    assert len(index) == 4_999
    assert "zone-2500" not in index.containing(Decimal("2501"))


def test_interval_candidate_query_returns_only_overlap_and_tolerance_neighbors() -> None:
    zones = [
        _zone(1, 90, 99),
        _zone(2, 100, 101),
        _zone(3, 102, 103),
        _zone(4, 104, 105),
        _zone(5, 106, 120),
    ]
    index = ReactionZoneBoundaryIndex(zones)
    assert index.overlapping_or_adjacent(
        Decimal("101"), Decimal("103"), Decimal("1")
    ) == ("zone-2", "zone-3", "zone-4")
