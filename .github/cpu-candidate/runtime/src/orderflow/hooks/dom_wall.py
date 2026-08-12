"""DOM wall appearance, pull, suspected spoofing, and tracking measurements."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Mapping

from .detector_utils import BPS, ZERO, make_candidate
from .dom_features import DomFeatureDelta, DomFeatures
from .models import HookCandidate, HookSide


def _common(frame: DomFeatures) -> dict:
    return {
        "symbol": frame.symbol,
        "source_time": frame.source_time,
        "received_time": frame.received_time,
        "source_sequence": str(frame.sequence),
        "bid": frame.best_bid,
        "ask": frame.best_ask,
        "quality_status": frame.quality_status,
        "quality_flags": frame.quality_flags,
    }


class DomWallDetector:
    """Produces measured candidates; calibration decides what is actually large."""

    def __init__(self) -> None:
        self._untraded_pulls: dict[tuple[str, Decimal], int] = defaultdict(int)

    @staticmethod
    def _appearance(
        current: DomFeatures,
        previous: DomFeatures | None,
        *,
        bid_side: bool,
    ) -> HookCandidate | None:
        price = current.bid_wall_price if bid_side else current.ask_wall_price
        ratio = current.bid_wall_ratio if bid_side else current.ask_wall_ratio
        current_qty = (
            current.bid_quantity(price) if bid_side else current.ask_quantity(price)
        )
        previous_qty = (
            ZERO
            if previous is None
            else (
                previous.bid_quantity(price)
                if bid_side
                else previous.ask_quantity(price)
            )
        )
        if previous is not None and current_qty <= previous_qty:
            return None
        return make_candidate(
            "A01" if bid_side else "A02",
            side=HookSide.BID if bid_side else HookSide.ASK,
            metric_name="level_quantity_over_side_median",
            metric_value=ratio,
            anchor_price=price,
            episode_id=(
                f"{'BID' if bid_side else 'ASK'}:{price}:"
                f"{current.source_time.isoformat()}"
            ),
            evidence={
                "level_quantity": current_qty,
                "previous_quantity": previous_qty,
                "side_median_quantity": (
                    current.bid_median if bid_side else current.ask_median
                ),
            },
            **_common(current),
        )

    def _pull(
        self,
        current: DomFeatures,
        previous: DomFeatures,
        *,
        bid_side: bool,
        executed: Mapping[Decimal, Decimal],
    ) -> tuple[HookCandidate, ...]:
        price = previous.bid_wall_price if bid_side else previous.ask_wall_price
        before = (
            previous.bid_quantity(price)
            if bid_side
            else previous.ask_quantity(price)
        )
        after = (
            current.bid_quantity(price) if bid_side else current.ask_quantity(price)
        )
        executed_qty = executed.get(price, ZERO)
        if before <= ZERO or after >= before or executed_qty > ZERO:
            return ()

        removed_fraction = (before - after) / before
        side_name = "BID" if bid_side else "ASK"
        key = (side_name, price)
        self._untraded_pulls[key] += 1
        count = self._untraded_pulls[key]
        shared = {
            **_common(current),
            "side": HookSide.BID if bid_side else HookSide.ASK,
            "anchor_price": price,
            "episode_id": f"{side_name}:{price}:{count}",
            "evidence": {
                "before_quantity": before,
                "after_quantity": after,
                "executed_quantity": executed_qty,
                "untraded_pull_count": count,
            },
        }
        return (
            make_candidate(
                "A03" if bid_side else "A04",
                metric_name="untraded_removed_fraction",
                metric_value=removed_fraction,
                **shared,
            ),
            make_candidate(
                "A19" if bid_side else "A20",
                metric_name="untraded_pull_count",
                metric_value=count,
                **shared,
            ),
        )

    @staticmethod
    def _tracking(
        current: DomFeatures,
        previous: DomFeatures,
        *,
        bid_side: bool,
    ) -> HookCandidate | None:
        old = previous.bid_wall_price if bid_side else previous.ask_wall_price
        new = current.bid_wall_price if bid_side else current.ask_wall_price
        moved_in_tracking_direction = new > old if bid_side else new < old
        if not moved_in_tracking_direction:
            return None
        move_bps = abs(new - old) / previous.mid * BPS
        return make_candidate(
            "A23" if bid_side else "A24",
            side=HookSide.BID if bid_side else HookSide.ASK,
            metric_name="wall_tracking_move_bps",
            metric_value=move_bps,
            anchor_price=new,
            episode_id=(
                f"{'BID' if bid_side else 'ASK'}:{old}->{new}:"
                f"{current.source_time.isoformat()}"
            ),
            evidence={"previous_wall_price": old, "current_wall_price": new},
            **_common(current),
        )

    def process(
        self,
        delta: DomFeatureDelta,
        *,
        executed_bid: Mapping[Decimal, Decimal] | None = None,
        executed_ask: Mapping[Decimal, Decimal] | None = None,
    ) -> tuple[HookCandidate, ...]:
        current, previous = delta.current, delta.previous
        result: list[HookCandidate] = []
        for bid_side in (True, False):
            appeared = self._appearance(current, previous, bid_side=bid_side)
            if appeared is not None:
                result.append(appeared)
        if previous is None:
            return tuple(result)
        result.extend(
            self._pull(
                current,
                previous,
                bid_side=True,
                executed=executed_bid or {},
            )
        )
        result.extend(
            self._pull(
                current,
                previous,
                bid_side=False,
                executed=executed_ask or {},
            )
        )
        for bid_side in (True, False):
            tracked = self._tracking(current, previous, bid_side=bid_side)
            if tracked is not None:
                result.append(tracked)
        return tuple(result)
