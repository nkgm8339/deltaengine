"""Reaction Zone interval and boundary index.

The index avoids a full active-zone scan for each accepted trade. Point queries
use a centered interval tree; path changes use bisected boundary arrays.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Optional

from .models import ReactionZone


@dataclass(frozen=True)
class _IntervalNode:
    center: Decimal
    overlaps_by_low: tuple[ReactionZone, ...]
    overlaps_by_high: tuple[ReactionZone, ...]
    left: Optional["_IntervalNode"]
    right: Optional["_IntervalNode"]


def _build(zones: list[ReactionZone]) -> Optional[_IntervalNode]:
    if not zones:
        return None
    endpoints = sorted(
        [zone.zone_low for zone in zones] + [zone.zone_high for zone in zones]
    )
    center = endpoints[len(endpoints) // 2]
    left: list[ReactionZone] = []
    right: list[ReactionZone] = []
    overlaps: list[ReactionZone] = []
    for zone in zones:
        if zone.zone_high < center:
            left.append(zone)
        elif zone.zone_low > center:
            right.append(zone)
        else:
            overlaps.append(zone)
    return _IntervalNode(
        center=center,
        overlaps_by_low=tuple(sorted(overlaps, key=lambda zone: (zone.zone_low, zone.zone_id))),
        overlaps_by_high=tuple(
            sorted(overlaps, key=lambda zone: (zone.zone_high, zone.zone_id), reverse=True)
        ),
        left=_build(left),
        right=_build(right),
    )


def _query_point(node: Optional[_IntervalNode], price: Decimal, output: set[str]) -> None:
    if node is None:
        return
    if price < node.center:
        for zone in node.overlaps_by_low:
            if zone.zone_low > price:
                break
            output.add(zone.zone_id)
        _query_point(node.left, price, output)
    elif price > node.center:
        for zone in node.overlaps_by_high:
            if zone.zone_high < price:
                break
            output.add(zone.zone_id)
        _query_point(node.right, price, output)
    else:
        output.update(zone.zone_id for zone in node.overlaps_by_low)


class ReactionZoneBoundaryIndex:
    def __init__(self, zones: Iterable[ReactionZone] = ()) -> None:
        self._zones: dict[str, ReactionZone] = {}
        self._tree: Optional[_IntervalNode] = None
        self._boundaries: list[tuple[Decimal, str]] = []
        self._boundary_prices: list[Decimal] = []
        self._dirty = False
        for zone in zones:
            self.add(zone)

    def add(self, zone: ReactionZone) -> None:
        existing = self._zones.get(zone.zone_id)
        if existing is not None and existing != zone:
            raise ValueError(f"zone ID collision: {zone.zone_id}")
        self._zones[zone.zone_id] = zone
        self._dirty = True

    def remove(self, zone_id: str) -> None:
        if zone_id in self._zones:
            del self._zones[zone_id]
            self._dirty = True

    def get(self, zone_id: str) -> ReactionZone:
        return self._zones[zone_id]

    def containing(self, price: Decimal) -> tuple[str, ...]:
        self._ensure_built()
        result: set[str] = set()
        _query_point(self._tree, Decimal(str(price)), result)
        return tuple(sorted(result))

    def crossed_boundaries(self, previous_price: Decimal, current_price: Decimal) -> tuple[str, ...]:
        self._ensure_built()
        previous = Decimal(str(previous_price))
        current = Decimal(str(current_price))
        lower, upper = sorted((previous, current))
        start = bisect_right(self._boundary_prices, lower)
        end = bisect_right(self._boundary_prices, upper)
        return tuple(sorted({zone_id for _, zone_id in self._boundaries[start:end]}))

    def candidates(self, previous_price: Decimal, current_price: Decimal) -> tuple[str, ...]:
        return tuple(
            sorted(
                set(self.containing(previous_price))
                | set(self.containing(current_price))
                | set(self.crossed_boundaries(previous_price, current_price))
            )
        )

    def _ensure_built(self) -> None:
        if not self._dirty:
            return
        zones = list(self._zones.values())
        self._tree = _build(zones)
        self._boundaries = sorted(
            (price, zone.zone_id)
            for zone in zones
            for price in (zone.zone_low, zone.zone_high)
        )
        self._boundary_prices = [price for price, _ in self._boundaries]
        self._dirty = False

    def __len__(self) -> int:
        return len(self._zones)
