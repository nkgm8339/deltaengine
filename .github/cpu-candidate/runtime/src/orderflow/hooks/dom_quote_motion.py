"""Best bid/ask retreat and advance measurements."""

from __future__ import annotations

from .detector_utils import BPS, make_candidate
from .dom_features import DomFeatureDelta
from .models import HookCandidate, HookSide


class DomQuoteMotionDetector:
    def process(self, delta: DomFeatureDelta) -> tuple[HookCandidate, ...]:
        current, previous = delta.current, delta.previous
        if previous is None:
            return ()
        result: list[HookCandidate] = []
        common = {
            "symbol": current.symbol,
            "source_time": current.source_time,
            "received_time": current.received_time,
            "source_sequence": str(current.sequence),
            "anchor_price": current.mid,
            "bid": current.best_bid,
            "ask": current.best_ask,
            "quality_status": current.quality_status,
            "quality_flags": current.quality_flags,
        }
        movements = (
            (
                current.best_bid - previous.best_bid,
                "A13",
                "A11",
                HookSide.BID,
                previous.best_bid,
                current.best_bid,
            ),
            (
                current.best_ask - previous.best_ask,
                "A12",
                "A14",
                HookSide.ASK,
                previous.best_ask,
                current.best_ask,
            ),
        )
        for change, positive_hook, negative_hook, side, old, new in movements:
            if change == 0:
                continue
            result.append(make_candidate(
                positive_hook if change > 0 else negative_hook,
                side=side,
                metric_name="best_quote_move_bps",
                metric_value=abs(change) / previous.mid * BPS,
                evidence={"previous_quote": old, "current_quote": new},
                **common,
            ))
        return tuple(result)
