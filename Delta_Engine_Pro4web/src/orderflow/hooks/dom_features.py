"""Deterministic DOM feature cache above the existing order-book state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from statistics import median
from typing import Any, Mapping

from .detector_utils import BPS, ZERO, decimal_value, observation_times
from .models import HookQualityStatus


Level = tuple[Decimal, Decimal]


def _levels(
    values: Mapping[Any, Any],
    *,
    reverse: bool,
    limit: int,
) -> tuple[Level, ...]:
    parsed = [
        (decimal_value(price, "level price"), decimal_value(qty, "level quantity"))
        for price, qty in values.items()
    ]
    parsed = [(price, qty) for price, qty in parsed if price > ZERO and qty > ZERO]
    return tuple(sorted(parsed, key=lambda row: row[0], reverse=reverse)[:limit])


def _snapshot_levels(
    snapshot: Any,
    side: str,
    *,
    reverse: bool,
    limit: int,
) -> tuple[Level, ...]:
    bounded = getattr(snapshot, f"best_{side}", None)
    if callable(bounded):
        selected = tuple(
            (decimal_value(price, "level price"), decimal_value(qty, "level quantity"))
            for price, qty in bounded(limit)
        )
        if all(price > ZERO and qty > ZERO for price, qty in selected):
            return selected
        # Preserve the original positive-level filtering semantics. A non-positive
        # level inside the bounded window may hide a valid deeper level, so the
        # full mapping is consulted only for this invalid-data fallback.
        return _levels(getattr(snapshot, side), reverse=reverse, limit=limit)
    cached = getattr(snapshot, f"ordered_{side}", None)
    if cached is None:
        return _levels(getattr(snapshot, side), reverse=reverse, limit=limit)
    selected: list[Level] = []
    for price, quantity in cached:
        if price > ZERO and quantity > ZERO:
            selected.append((price, quantity))
            if len(selected) == limit:
                break
    return tuple(selected)


def _median_quantity(levels: tuple[Level, ...]) -> Decimal:
    return median([quantity for _price, quantity in levels]) if levels else ZERO


def _max_gap_bps(levels: tuple[Level, ...], mid: Decimal) -> Decimal:
    if len(levels) < 2 or mid <= ZERO:
        return ZERO
    return max(
        abs(levels[index][0] - levels[index - 1][0]) / mid * BPS
        for index in range(1, len(levels))
    )


@dataclass(frozen=True)
class DomFeatures:
    symbol: str
    source_time: datetime
    received_time: datetime
    sequence: int
    bids: tuple[Level, ...]
    asks: tuple[Level, ...]
    best_bid: Decimal
    best_ask: Decimal
    mid: Decimal
    spread: Decimal
    spread_bps: Decimal
    bid_total: Decimal
    ask_total: Decimal
    bid_median: Decimal
    ask_median: Decimal
    bid_wall_price: Decimal
    ask_wall_price: Decimal
    bid_wall_ratio: Decimal
    ask_wall_ratio: Decimal
    downside_gap_bps: Decimal
    upside_gap_bps: Decimal
    quality_status: HookQualityStatus
    quality_flags: tuple[str, ...]

    def bid_quantity(self, price: Decimal) -> Decimal:
        return dict(self.bids).get(price, ZERO)

    def ask_quantity(self, price: Decimal) -> Decimal:
        return dict(self.asks).get(price, ZERO)


@dataclass(frozen=True)
class DomFeatureDelta:
    previous: DomFeatures | None
    current: DomFeatures


class DomFeatureCache:
    """Rejects invalid, stale, crossed, or future DOM before feature use."""

    def __init__(self, *, depth_levels: int = 50) -> None:
        if depth_levels < 2:
            raise ValueError("depth_levels must be at least 2")
        self.depth_levels = int(depth_levels)
        self._previous: DomFeatures | None = None
        self.invalid_frames = 0
        self.stale_frames = 0

    @property
    def latest(self) -> DomFeatures | None:
        return self._previous

    def reset(self) -> None:
        self._previous = None

    def process(
        self,
        snapshot: Any,
        *,
        source_time: datetime,
        received_time: datetime,
        quality_status: HookQualityStatus = HookQualityStatus.VALID,
        quality_flags: tuple[str, ...] = (),
    ) -> DomFeatureDelta | None:
        source, received = observation_times(source_time, received_time)
        if quality_status is not HookQualityStatus.VALID:
            self.invalid_frames += 1
            self.reset()
            return None
        if self._previous is not None and source <= self._previous.source_time:
            self.stale_frames += 1
            return None

        bids = _snapshot_levels(
            snapshot, "bids", reverse=True, limit=self.depth_levels
        )
        asks = _snapshot_levels(
            snapshot, "asks", reverse=False, limit=self.depth_levels
        )
        if not bids or not asks or bids[0][0] >= asks[0][0]:
            self.invalid_frames += 1
            self.reset()
            return None

        best_bid, best_ask = bids[0][0], asks[0][0]
        mid = (best_bid + best_ask) / Decimal(2)
        spread = best_ask - best_bid
        bid_median = _median_quantity(bids)
        ask_median = _median_quantity(asks)
        bid_wall = max(bids, key=lambda row: row[1])
        ask_wall = max(asks, key=lambda row: row[1])
        current = DomFeatures(
            symbol=str(snapshot.symbol).upper(),
            source_time=source,
            received_time=received,
            sequence=int(snapshot.last_update_id),
            bids=bids,
            asks=asks,
            best_bid=best_bid,
            best_ask=best_ask,
            mid=mid,
            spread=spread,
            spread_bps=spread / mid * BPS,
            bid_total=sum((qty for _price, qty in bids), ZERO),
            ask_total=sum((qty for _price, qty in asks), ZERO),
            bid_median=bid_median,
            ask_median=ask_median,
            bid_wall_price=bid_wall[0],
            ask_wall_price=ask_wall[0],
            bid_wall_ratio=(
                bid_wall[1] / bid_median if bid_median > ZERO else ZERO
            ),
            ask_wall_ratio=(
                ask_wall[1] / ask_median if ask_median > ZERO else ZERO
            ),
            downside_gap_bps=_max_gap_bps(bids, mid),
            upside_gap_bps=_max_gap_bps(asks, mid),
            quality_status=quality_status,
            quality_flags=quality_flags,
        )
        delta = DomFeatureDelta(previous=self._previous, current=current)
        self._previous = current
        return delta
