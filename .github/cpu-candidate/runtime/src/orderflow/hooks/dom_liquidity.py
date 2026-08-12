"""DOM depth, asymmetry, spread, and vacuum measurements."""

from __future__ import annotations

from decimal import Decimal

from .detector_utils import ZERO, make_candidate
from .dom_features import DomFeatureDelta, DomFeatures
from .models import HookCandidate, HookSide


def _common(frame: DomFeatures) -> dict:
    return {
        "symbol": frame.symbol,
        "source_time": frame.source_time,
        "received_time": frame.received_time,
        "source_sequence": str(frame.sequence),
        "anchor_price": frame.mid,
        "bid": frame.best_bid,
        "ask": frame.best_ask,
        "quality_status": frame.quality_status,
        "quality_flags": frame.quality_flags,
    }


class DomLiquidityDetector:
    def process(self, delta: DomFeatureDelta) -> tuple[HookCandidate, ...]:
        current, previous = delta.current, delta.previous
        common = _common(current)
        result: list[HookCandidate] = []

        if previous is not None:
            for bid_side in (True, False):
                before = previous.bid_total if bid_side else previous.ask_total
                after = current.bid_total if bid_side else current.ask_total
                if before <= ZERO or after == before:
                    continue
                change = (after - before) / before
                if change < ZERO:
                    hook_id = "A05" if bid_side else "A06"
                    metric_name = "depth_removed_fraction"
                else:
                    hook_id = "A07" if bid_side else "A08"
                    metric_name = "depth_added_fraction"
                result.append(make_candidate(
                    hook_id,
                    side=HookSide.BID if bid_side else HookSide.ASK,
                    metric_name=metric_name,
                    metric_value=abs(change),
                    evidence={
                        "previous_depth": before,
                        "current_depth": after,
                        "depth_levels": len(
                            current.bids if bid_side else current.asks
                        ),
                    },
                    **common,
                ))

            spread_change = current.spread_bps - previous.spread_bps
            if spread_change > ZERO:
                result.append(make_candidate(
                    "A15",
                    side=HookSide.NEUTRAL,
                    metric_name="spread_expansion_bps",
                    metric_value=spread_change,
                    evidence={
                        "previous_spread_bps": previous.spread_bps,
                        "current_spread_bps": current.spread_bps,
                    },
                    **common,
                ))
            elif spread_change < ZERO:
                result.append(make_candidate(
                    "A16",
                    side=HookSide.NEUTRAL,
                    metric_name="spread_contraction_bps",
                    metric_value=abs(spread_change),
                    evidence={
                        "previous_spread_bps": previous.spread_bps,
                        "current_spread_bps": current.spread_bps,
                    },
                    **common,
                ))

        if current.bid_total > ZERO and current.ask_total > ZERO:
            if current.bid_total >= current.ask_total:
                hook_id, side = "A09", HookSide.BID
                ratio = current.bid_total / current.ask_total
            else:
                hook_id, side = "A10", HookSide.ASK
                ratio = current.ask_total / current.bid_total
            result.append(make_candidate(
                hook_id,
                side=side,
                metric_name="dominant_to_opposite_depth_ratio",
                metric_value=ratio,
                evidence={
                    "bid_depth": current.bid_total,
                    "ask_depth": current.ask_total,
                },
                **common,
            ))

        result.extend((
            make_candidate(
                "A21",
                side=HookSide.ASK,
                metric_name="maximum_upside_level_gap_bps",
                metric_value=current.upside_gap_bps,
                evidence={"levels": len(current.asks)},
                **common,
            ),
            make_candidate(
                "A22",
                side=HookSide.BID,
                metric_name="maximum_downside_level_gap_bps",
                metric_value=current.downside_gap_bps,
                evidence={"levels": len(current.bids)},
                **common,
            ),
        ))
        return tuple(result)
