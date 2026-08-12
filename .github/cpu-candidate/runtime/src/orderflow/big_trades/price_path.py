"""Gap-aware source price path queries for fixed-horizon results."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from datetime import datetime
from decimal import Decimal
from typing import Optional

from .ids import sha256_hex, utc_text
from .models import BigTradeFill, PriceObservation, SourceGap
from .time_buckets import epoch_microseconds, require_aware_utc


SourceKey = tuple[int, int]


class SourcePricePathIndex:
    def __init__(self, *, symbol: str, venue: str) -> None:
        if not symbol or not venue:
            raise ValueError("symbol and venue must be non-empty")
        self.symbol = symbol
        self.venue = venue
        self._observations: list[PriceObservation] = []
        self._keys: list[tuple[int, int]] = []
        # Append-only segment tree.  Source keys remain in the bisected list;
        # exact Decimal extrema are queried by index in O(log M).  This avoids
        # allocating and recursively refreshing an AVL path on every trade.
        self._range_capacity = 1
        self._range_min: list[Optional[Decimal]] = [None, None]
        self._range_max: list[Optional[Decimal]] = [None, None]
        self._gaps: list[SourceGap] = []
        self._open_gap: Optional[SourceGap] = None

    def append(self, trade: BigTradeFill | PriceObservation) -> PriceObservation:
        observation = (
            trade
            if isinstance(trade, PriceObservation)
            else PriceObservation(
                event_time=trade.event_time,
                trade_id=trade.trade_id,
                price=trade.price,
                symbol=trade.symbol,
                venue=trade.venue,
            )
        )
        if observation.symbol != self.symbol or observation.venue != self.venue:
            raise ValueError("price observation identity mismatch")
        if self._keys and observation.source_key <= self._keys[-1]:
            raise ValueError("price observations must be strictly source ordered")
        position = len(self._observations)
        self._observations.append(observation)
        self._keys.append(observation.source_key)
        if position >= self._range_capacity:
            self._grow_range_tree()
        node = self._range_capacity + position
        self._range_min[node] = observation.price
        self._range_max[node] = observation.price
        node //= 2
        while node:
            current_min = self._range_min[node]
            current_max = self._range_max[node]
            if current_min is None or observation.price < current_min:
                self._range_min[node] = observation.price
            if current_max is None or observation.price > current_max:
                self._range_max[node] = observation.price
            node //= 2
        return observation

    def _grow_range_tree(self) -> None:
        self._range_capacity *= 2
        size = self._range_capacity * 2
        self._range_min = [None] * size
        self._range_max = [None] * size
        for position, observation in enumerate(self._observations[:-1]):
            leaf = self._range_capacity + position
            self._range_min[leaf] = observation.price
            self._range_max[leaf] = observation.price
        for node in range(self._range_capacity - 1, 0, -1):
            self._refresh_range_node(node)

    def _refresh_range_node(self, node: int) -> None:
        left = node * 2
        left_min = self._range_min[left]
        right_min = self._range_min[left + 1]
        if left_min is None:
            self._range_min[node] = right_min
        elif right_min is None:
            self._range_min[node] = left_min
        else:
            self._range_min[node] = min(left_min, right_min)
        left_max = self._range_max[left]
        right_max = self._range_max[left + 1]
        if left_max is None:
            self._range_max[node] = right_max
        elif right_max is None:
            self._range_max[node] = left_max
        else:
            self._range_max[node] = max(left_max, right_max)

    def _range_min_max_indices(self, start: int, end: int) -> tuple[Decimal, Decimal]:
        left = self._range_capacity + start
        right = self._range_capacity + end + 1
        minimum: Optional[Decimal] = None
        maximum: Optional[Decimal] = None
        while left < right:
            if left & 1:
                value_min = self._range_min[left]
                value_max = self._range_max[left]
                if value_min is not None:
                    minimum = value_min if minimum is None else min(minimum, value_min)
                    maximum = value_max if maximum is None else max(maximum, value_max)
                left += 1
            if right & 1:
                right -= 1
                value_min = self._range_min[right]
                value_max = self._range_max[right]
                if value_min is not None:
                    minimum = value_min if minimum is None else min(minimum, value_min)
                    maximum = value_max if maximum is None else max(maximum, value_max)
            left //= 2
            right //= 2
        assert minimum is not None and maximum is not None
        return minimum, maximum

    def last_at_or_before(self, target_time: datetime) -> Optional[PriceObservation]:
        target_us = epoch_microseconds(target_time)
        position = bisect_right(self._keys, (target_us, 2**63 - 1)) - 1
        return self._observations[position] if position >= 0 else None

    def range_min_max_by_source_key(
        self,
        start_inclusive: SourceKey,
        end_inclusive: SourceKey,
    ) -> Optional[tuple[Decimal, Decimal]]:
        """Return exact extrema over an inclusive source-key interval in O(log M)."""

        if end_inclusive < start_inclusive:
            raise ValueError("range end must not precede range start")
        start = bisect_left(self._keys, start_inclusive)
        end = bisect_right(self._keys, end_inclusive) - 1
        if start > end:
            return None
        return self._range_min_max_indices(start, end)

    def range_min_max(
        self,
        start_time_inclusive: datetime,
        end_time_inclusive: datetime,
    ) -> Optional[tuple[Decimal, Decimal]]:
        """Return extrema for all observations in an inclusive UTC time range."""

        start_us = epoch_microseconds(start_time_inclusive)
        end_us = epoch_microseconds(end_time_inclusive)
        return self.range_min_max_by_source_key(
            (start_us, -1),
            (end_us, 2**63 - 1),
        )

    def start_gap(self, start_time: datetime) -> SourceGap:
        normalized = require_aware_utc(start_time)
        if self._open_gap is not None:
            raise ValueError("a source gap is already open")
        gap = SourceGap(
            gap_epoch_id="btgap2_" + sha256_hex(f"BTGAP2|{self.venue}|{self.symbol}|{utc_text(normalized)}"),
            start_time=normalized,
            end_time=None,
        )
        self._open_gap = gap
        return gap

    def end_gap(self, end_time: datetime) -> SourceGap:
        normalized = require_aware_utc(end_time)
        if self._open_gap is None:
            raise ValueError("no source gap is open")
        if normalized < self._open_gap.start_time:
            raise ValueError("gap end must not precede gap start")
        closed = SourceGap(
            gap_epoch_id=self._open_gap.gap_epoch_id,
            start_time=self._open_gap.start_time,
            end_time=normalized,
        )
        self._gaps.append(closed)
        self._open_gap = None
        return closed

    def restore_open_gap(self, gap_epoch_id: str, start_time: datetime) -> SourceGap:
        """Restore a persisted open gap without deriving a new identity."""

        if self._open_gap is not None:
            raise ValueError("a source gap is already open")
        if not isinstance(gap_epoch_id, str) or not gap_epoch_id:
            raise ValueError("gap_epoch_id must be non-empty")
        gap = SourceGap(
            gap_epoch_id=gap_epoch_id,
            start_time=require_aware_utc(start_time),
            end_time=None,
        )
        self._open_gap = gap
        return gap

    def gap_intersects(self, start_exclusive: datetime, end_inclusive: datetime) -> bool:
        start = require_aware_utc(start_exclusive)
        end = require_aware_utc(end_inclusive)
        if end < start:
            raise ValueError("gap query end must not precede start")
        gaps = self._gaps + ([self._open_gap] if self._open_gap is not None else [])
        for gap in gaps:
            gap_end = gap.end_time
            if gap.start_time <= end and (gap_end is None or gap_end > start):
                return True
        return False

    @property
    def observations(self) -> tuple[PriceObservation, ...]:
        return tuple(self._observations)

    @property
    def last_observation(self) -> Optional[PriceObservation]:
        """Return the newest source observation without copying the history."""

        return self._observations[-1] if self._observations else None

    def __len__(self) -> int:
        """Return the retained source observation count in O(1)."""

        return len(self._observations)

    @property
    def gaps(self) -> tuple[SourceGap, ...]:
        return tuple(self._gaps + ([self._open_gap] if self._open_gap is not None else []))
