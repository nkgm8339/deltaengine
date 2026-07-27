"""Normalized, read-only market state consumed by the ingestion adapter.

The snapshot is source-agnostic: synthetic fixtures populate it now, and a future
replay/detector-fed producer will populate it later. Nothing here reconstructs raw
event streams; higher-order counters (book refresh/pull, price progress) are
supplied pre-aggregated and passed through by the adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Mapping

NS_PER_SECOND = 1_000_000_000


@dataclass(frozen=True)
class TimeSample:
    """One (monotonic engine time, value) sample of a scalar series."""

    engine_time_ns: int
    value: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.engine_time_ns, int):
            raise TypeError("engine_time_ns must be int (monotonic nanoseconds)")
        value = self.value if isinstance(self.value, Decimal) else Decimal(str(self.value))
        if not value.is_finite():
            raise ValueError("sample value must be finite")
        object.__setattr__(self, "value", value)


@dataclass(frozen=True)
class BookLevel:
    """One order book price level."""

    price: Decimal
    quantity: Decimal

    def __post_init__(self) -> None:
        price = self.price if isinstance(self.price, Decimal) else Decimal(str(self.price))
        qty = (
            self.quantity
            if isinstance(self.quantity, Decimal)
            else Decimal(str(self.quantity))
        )
        if not price.is_finite() or price <= 0:
            raise ValueError("level price must be finite and positive")
        if not qty.is_finite() or qty < 0:
            raise ValueError("level quantity must be finite and non-negative")
        object.__setattr__(self, "price", price)
        object.__setattr__(self, "quantity", qty)


@dataclass(frozen=True)
class MarketStateSnapshot:
    """A normalized view of the market at ``engine_time_ns``.

    Level sequences are best-first: ``bid_levels`` descending by price,
    ``ask_levels`` ascending. All series are monotonic-time samples. Missing data
    is expressed by empty sequences; the adapter is fail-closed on absence.
    """

    engine_time_ns: int
    cvd_samples: tuple[TimeSample, ...] = ()
    oi_samples: tuple[TimeSample, ...] = ()
    price_samples: tuple[TimeSample, ...] = ()
    bid_levels: tuple[BookLevel, ...] = ()
    ask_levels: tuple[BookLevel, ...] = ()
    tick_size: Decimal | None = None
    pre_aggregated: Mapping[str, Decimal] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.engine_time_ns, int):
            raise TypeError("engine_time_ns must be int (monotonic nanoseconds)")
        if self.tick_size is not None:
            tick = (
                self.tick_size
                if isinstance(self.tick_size, Decimal)
                else Decimal(str(self.tick_size))
            )
            if not tick.is_finite() or tick <= 0:
                raise ValueError("tick_size must be finite and positive when present")
            object.__setattr__(self, "tick_size", tick)
