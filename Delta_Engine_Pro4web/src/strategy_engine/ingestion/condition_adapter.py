"""Ingestion adapter: MarketStateSnapshot -> Tier A condition snapshot.

Emits only Tier A condition keys (single-stream, window-derived). Fail-closed: a
key is omitted whenever its source material is missing or insufficient, so a
downstream ConditionAtom over that key simply cannot pass. No threshold is applied
here; the adapter supplies raw/derived quantities only.

Tier B composite FLAGs are NOT produced here (documented gap; future composite
synthesis layer).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from .market_state import NS_PER_SECOND, BookLevel, MarketStateSnapshot, TimeSample

_WINDOW_5S_NS = 5 * NS_PER_SECOND
_WINDOW_5M_NS = 300 * NS_PER_SECOND
_TOP_N = 10

# price_oi_joint_state_5m ENUM encoded as a numeric code (documented mapping).
JOINT_STATE_CODES = {
    "PRICE_UP_OI_UP": Decimal(1),
    "PRICE_UP_OI_DOWN": Decimal(2),
    "PRICE_DOWN_OI_UP": Decimal(3),
    "PRICE_DOWN_OI_DOWN": Decimal(4),
    "FLAT": Decimal(0),
}


class IngestionAdapter:
    """Maps a normalized market-state snapshot to a Tier A condition snapshot."""

    def to_conditions(self, snapshot: MarketStateSnapshot) -> dict[str, Decimal]:
        conditions: dict[str, Decimal] = {}
        self._add_cvd(snapshot, conditions)
        self._add_walls(snapshot, conditions)
        self._add_open_interest(snapshot, conditions)
        self._add_pre_aggregated(snapshot, conditions)
        return conditions

    # -- CVD (AGGTRADE / DELTA_FOOTPRINT) ----------------------------------

    def _add_cvd(self, snapshot: MarketStateSnapshot, out: dict[str, Decimal]) -> None:
        now = snapshot.engine_time_ns
        samples = _sorted(snapshot.cvd_samples)
        latest = _latest_at(samples, now)
        base = _value_at_or_before(samples, now - _WINDOW_5S_NS)
        if latest is None or base is None:
            return
        out["cvd_change_5s"] = latest.value - base.value
        # slope per second across the samples inside the 5s window
        window = [s for s in samples if now - _WINDOW_5S_NS <= s.engine_time_ns <= now]
        if len(window) >= 2:
            first, last = window[0], window[-1]
            dt_ns = last.engine_time_ns - first.engine_time_ns
            if dt_ns > 0:
                dt_s = Decimal(dt_ns) / Decimal(NS_PER_SECOND)
                out["cvd_slope_5s"] = (last.value - first.value) / dt_s

    # -- Book walls (DEPTH / BOOK_SHAPE) -----------------------------------

    def _add_walls(self, snapshot: MarketStateSnapshot, out: dict[str, Decimal]) -> None:
        self._add_side_walls(snapshot.bid_levels, snapshot, "bid", out)
        self._add_side_walls(snapshot.ask_levels, snapshot, "ask", out)

    def _add_side_walls(
        self,
        levels: Sequence[BookLevel],
        snapshot: MarketStateSnapshot,
        side: str,
        out: dict[str, Decimal],
    ) -> None:
        if not levels:
            return
        top = list(levels[:_TOP_N])
        total = sum((lvl.quantity for lvl in top), Decimal(0))
        wall = max(top, key=lambda lvl: lvl.quantity)
        if total > 0:
            out[f"{side}_wall_concentration_top10"] = wall.quantity / total
        # distance from the best level to the largest (wall) level, in ticks
        if snapshot.tick_size is not None and snapshot.tick_size > 0:
            best_price = top[0].price
            distance = abs(best_price - wall.price) / snapshot.tick_size
            out[f"distance_to_nearest_{side}_wall"] = distance

    # -- Open interest (OI) -------------------------------------------------

    def _add_open_interest(
        self, snapshot: MarketStateSnapshot, out: dict[str, Decimal]
    ) -> None:
        now = snapshot.engine_time_ns
        samples = _sorted(snapshot.oi_samples)
        latest = _latest_at(samples, now)
        base = _value_at_or_before(samples, now - _WINDOW_5M_NS)
        if latest is None or base is None:
            return
        change = latest.value - base.value
        out["open_interest_change_5m"] = change
        if base.value != 0:
            out["open_interest_pct_change_5m"] = (change / base.value) * Decimal(100)

        price_samples = _sorted(snapshot.price_samples)
        price_now = _latest_at(price_samples, now)
        price_base = _value_at_or_before(price_samples, now - _WINDOW_5M_NS)
        if price_now is not None and price_base is not None:
            out["price_oi_joint_state_5m"] = _joint_state(
                price_now.value - price_base.value, change
            )

    # -- pre-aggregated pass-through ---------------------------------------

    def _add_pre_aggregated(
        self, snapshot: MarketStateSnapshot, out: dict[str, Decimal]
    ) -> None:
        for key, value in snapshot.pre_aggregated.items():
            out[key] = value if isinstance(value, Decimal) else Decimal(str(value))


def _sorted(samples: Sequence[TimeSample]) -> list[TimeSample]:
    return sorted(samples, key=lambda s: s.engine_time_ns)


def _latest_at(samples: Sequence[TimeSample], target_ns: int) -> TimeSample | None:
    return _value_at_or_before(samples, target_ns)


def _value_at_or_before(
    samples: Sequence[TimeSample], target_ns: int
) -> TimeSample | None:
    chosen: TimeSample | None = None
    for sample in samples:  # samples are time-sorted
        if sample.engine_time_ns <= target_ns:
            chosen = sample
        else:
            break
    return chosen


def _joint_state(price_delta: Decimal, oi_delta: Decimal) -> Decimal:
    if price_delta == 0 or oi_delta == 0:
        return JOINT_STATE_CODES["FLAT"]
    if price_delta > 0:
        return (
            JOINT_STATE_CODES["PRICE_UP_OI_UP"]
            if oi_delta > 0
            else JOINT_STATE_CODES["PRICE_UP_OI_DOWN"]
        )
    return (
        JOINT_STATE_CODES["PRICE_DOWN_OI_UP"]
        if oi_delta > 0
        else JOINT_STATE_CODES["PRICE_DOWN_OI_DOWN"]
    )
