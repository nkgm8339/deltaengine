"""Gap-aware source price path queries for fixed-horizon results."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from .ids import sha256_hex, utc_text
from .models import BigTradeFill, PriceObservation, SourceGap
from .time_buckets import epoch_microseconds, require_aware_utc


SourceKey = tuple[int, int]


@dataclass
class _PriceNode:
    key: SourceKey
    price: Decimal
    minimum: Decimal
    maximum: Decimal
    first_key: SourceKey
    last_key: SourceKey
    height: int = 1
    left: Optional["_PriceNode"] = None
    right: Optional["_PriceNode"] = None


def _height(node: Optional[_PriceNode]) -> int:
    return node.height if node is not None else 0


def _refresh(node: _PriceNode) -> None:
    node.height = 1 + max(_height(node.left), _height(node.right))
    node.minimum = min(
        node.price,
        node.left.minimum if node.left is not None else node.price,
        node.right.minimum if node.right is not None else node.price,
    )
    node.maximum = max(
        node.price,
        node.left.maximum if node.left is not None else node.price,
        node.right.maximum if node.right is not None else node.price,
    )
    node.first_key = node.left.first_key if node.left is not None else node.key
    node.last_key = node.right.last_key if node.right is not None else node.key


def _rotate_left(node: _PriceNode) -> _PriceNode:
    root = node.right
    assert root is not None
    node.right = root.left
    root.left = node
    _refresh(node)
    _refresh(root)
    return root


def _insert(node: Optional[_PriceNode], key: SourceKey, price: Decimal) -> _PriceNode:
    if node is None:
        return _PriceNode(key, price, price, price, key, key)
    if key <= node.key:
        raise ValueError("price observations must be strictly source ordered")
    node.right = _insert(node.right, key, price)
    _refresh(node)
    if _height(node.right) - _height(node.left) > 1:
        assert node.right is not None
        if key < node.right.key:
            raise AssertionError("monotonic append cannot require a right-left rotation")
        return _rotate_left(node)
    return node


def _range_min_max(
    node: Optional[_PriceNode],
    start_inclusive: SourceKey,
    end_inclusive: SourceKey,
) -> Optional[tuple[Decimal, Decimal]]:
    if node is None or node.last_key < start_inclusive or node.first_key > end_inclusive:
        return None
    if start_inclusive <= node.first_key and node.last_key <= end_inclusive:
        return node.minimum, node.maximum
    values: list[tuple[Decimal, Decimal]] = []
    left = _range_min_max(node.left, start_inclusive, end_inclusive)
    if left is not None:
        values.append(left)
    if start_inclusive <= node.key <= end_inclusive:
        values.append((node.price, node.price))
    right = _range_min_max(node.right, start_inclusive, end_inclusive)
    if right is not None:
        values.append(right)
    if not values:
        return None
    return min(item[0] for item in values), max(item[1] for item in values)


class SourcePricePathIndex:
    def __init__(self, *, symbol: str, venue: str) -> None:
        if not symbol or not venue:
            raise ValueError("symbol and venue must be non-empty")
        self.symbol = symbol
        self.venue = venue
        self._observations: list[PriceObservation] = []
        self._keys: list[tuple[int, int]] = []
        self._range_root: Optional[_PriceNode] = None
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
        self._observations.append(observation)
        self._keys.append(observation.source_key)
        self._range_root = _insert(self._range_root, observation.source_key, observation.price)
        return observation

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
        return _range_min_max(self._range_root, start_inclusive, end_inclusive)

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
    def gaps(self) -> tuple[SourceGap, ...]:
        return tuple(self._gaps + ([self._open_gap] if self._open_gap is not None else []))
