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
_PRICE_PROGRESS_WINDOWS = (
    (NS_PER_SECOND // 10, "100ms"),
    (NS_PER_SECOND, "1s"),
    (5 * NS_PER_SECOND, "5s"),
    (30 * NS_PER_SECOND, "30s"),
)
_TOP_N = 10

# price_oi_joint_state_5m ENUM encoded as a numeric code (documented mapping).
JOINT_STATE_CODES = {
    "PRICE_UP_OI_UP": Decimal(1),
    "PRICE_UP_OI_DOWN": Decimal(2),
    "PRICE_DOWN_OI_UP": Decimal(3),
    "PRICE_DOWN_OI_DOWN": Decimal(4),
    "FLAT": Decimal(0),
}
# G03 relation ENUM encoding. The signed distance uses the same orientation:
# positive means current price is above the reference.
RELATION_CODES = {
    "BELOW": Decimal(-1),
    "AT": Decimal(0),
    "ABOVE": Decimal(1),
}


class IngestionAdapter:
    """Maps a normalized market-state snapshot to a Tier A condition snapshot."""

    def to_conditions(self, snapshot: MarketStateSnapshot) -> dict[str, Decimal]:
        conditions: dict[str, Decimal] = {}
        self._add_cvd(snapshot, conditions)
        self._add_price_progress(snapshot, conditions)
        self._add_vwap_location(snapshot, conditions)
        self._add_walls(snapshot, conditions)
        self._add_open_interest(snapshot, conditions)
        self._add_pre_aggregated(snapshot, conditions)
        return conditions

    # -- CVD (AGGTRADE / DELTA_FOOTPRINT) ----------------------------------

    def _add_cvd(self, snapshot: MarketStateSnapshot, out: dict[str, Decimal]) -> None:
        now = snapshot.source_time_ns if snapshot.source_time_ns is not None else snapshot.engine_time_ns
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

    # -- Price response (AGGTRADE / PRICE_RESPONSE) ------------------------

    def _add_price_progress(
        self, snapshot: MarketStateSnapshot, out: dict[str, Decimal]
    ) -> None:
        if snapshot.tick_size is None or snapshot.tick_size <= 0:
            return
        now = (
            snapshot.source_time_ns
            if snapshot.source_time_ns is not None
            else snapshot.engine_time_ns
        )
        samples = _sorted(snapshot.price_samples)
        latest = _latest_at(samples, now)
        if latest is None:
            return
        for window_ns, label in _PRICE_PROGRESS_WINDOWS:
            base = _value_at_or_before(samples, now - window_ns)
            if base is None:
                continue
            delta_ticks = (latest.value - base.value) / snapshot.tick_size
            out[f"upward_progress_ticks_{label}"] = max(delta_ticks, Decimal(0))
            out[f"downward_progress_ticks_{label}"] = max(-delta_ticks, Decimal(0))

    # -- Session VWAP location (AGGTRADE / PROFILE) --------------------------

    def _add_vwap_location(
        self, snapshot: MarketStateSnapshot, out: dict[str, Decimal]
    ) -> None:
        now = (
            snapshot.source_time_ns
            if snapshot.source_time_ns is not None
            else snapshot.engine_time_ns
        )
        latest = _latest_at(_sorted(snapshot.price_samples), now)
        if latest is None:
            return

        references = (
            (
                "session_vwap",
                snapshot.session_vwap,
                "distance_to_session_vwap",
                "relation_to_session_vwap",
            ),
            (
                "session_open_avwap",
                snapshot.session_open_avwap,
                "distance_to_session_open_avwap",
                "relation_to_session_open_avwap",
            ),
        )
        for _name, reference, distance_key, relation_key in references:
            if reference is None:
                continue
            delta = latest.value - reference
            out[relation_key] = _relation_code(delta)
            if snapshot.tick_size is not None and snapshot.tick_size > 0:
                out[distance_key] = delta / snapshot.tick_size

    # -- Book walls (DEPTH / BOOK_SHAPE) -----------------------------------

    def _add_walls(self, snapshot: MarketStateSnapshot, out: dict[str, Decimal]) -> None:
        bids = sorted(
            (level for level in snapshot.bid_levels if level.quantity > 0),
            key=lambda level: level.price,
            reverse=True,
        )
        asks = sorted(
            (level for level in snapshot.ask_levels if level.quantity > 0),
            key=lambda level: level.price,
        )
        if not bids or not asks or bids[0].price >= asks[0].price:
            return
        self._add_side_walls(bids, snapshot, "bid", out)
        self._add_side_walls(asks, snapshot, "ask", out)

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
        if total <= 0:
            return
        maximum_quantity = max(level.quantity for level in top)
        # top is best-first, so the first maximum is the nearest tie candidate.
        wall = next(level for level in top if level.quantity == maximum_quantity)
        out[f"{side}_wall_concentration_top10"] = wall.quantity / total
        if snapshot.tick_size is None or snapshot.tick_size <= 0:
            return
        best_price = top[0].price
        price_distance = abs(best_price - wall.price)
        distance_ticks = price_distance / snapshot.tick_size
        if distance_ticks != distance_ticks.to_integral_value():
            return
        out[f"distance_to_nearest_{side}_wall"] = distance_ticks

    # -- Open interest (OI) -------------------------------------------------

    def _add_open_interest(
        self, snapshot: MarketStateSnapshot, out: dict[str, Decimal]
    ) -> None:
        now = snapshot.source_time_ns if snapshot.source_time_ns is not None else snapshot.engine_time_ns
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
            out.setdefault(key, value if isinstance(value, Decimal) else Decimal(str(value)))


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


def _relation_code(delta: Decimal) -> Decimal:
    if delta > 0:
        return RELATION_CODES["ABOVE"]
    if delta < 0:
        return RELATION_CODES["BELOW"]
    return RELATION_CODES["AT"]

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
