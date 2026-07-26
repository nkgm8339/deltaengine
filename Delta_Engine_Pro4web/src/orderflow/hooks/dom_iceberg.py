"""Trade-to-book replenishment measurements for suspected iceberg Hooks."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any

from .detector_utils import ZERO, decimal_value, make_candidate, observation_times
from .dom_features import DomFeatures
from .models import HookCandidate, HookSide


class DomIcebergDetector:
    """The name remains *suspected*; this detector never asserts hidden intent."""

    def __init__(self, *, episode_window_ms: int) -> None:
        if episode_window_ms < 1:
            raise ValueError("episode_window_ms must be positive")
        self.episode_window_ms = int(episode_window_ms)
        self._episodes: dict[tuple[str, Decimal], tuple[int, int]] = {}

    def process_trade(
        self,
        trade: Any,
        *,
        before: DomFeatures,
        after: DomFeatures,
        received_time: datetime,
    ) -> tuple[HookCandidate, ...]:
        event_time, received = observation_times(trade.event_time, received_time)
        if before.symbol != after.symbol or before.symbol != str(trade.symbol).upper():
            raise ValueError("trade and DOM symbols must match")
        if after.source_time < before.source_time:
            raise ValueError("after DOM cannot precede before DOM")
        side = str(trade.side)
        price = decimal_value(trade.price, "trade price")
        quantity = decimal_value(trade.quantity, "trade quantity")
        if quantity <= ZERO or side not in {"BUY", "SELL"}:
            return ()

        bid_iceberg = side == "SELL"
        before_qty = (
            before.bid_quantity(price)
            if bid_iceberg
            else before.ask_quantity(price)
        )
        after_qty = (
            after.bid_quantity(price)
            if bid_iceberg
            else after.ask_quantity(price)
        )
        expected_after = max(ZERO, before_qty - quantity)
        replenished = after_qty - expected_after
        if before_qty <= ZERO or replenished <= ZERO:
            return ()

        now_ms = int(event_time.timestamp() * 1000)
        key = ("BID" if bid_iceberg else "ASK", price)
        prior = self._episodes.get(key)
        repeat = (
            prior[1] + 1
            if prior is not None and now_ms - prior[0] <= self.episode_window_ms
            else 1
        )
        self._episodes[key] = (now_ms, repeat)
        ratio = replenished / quantity
        return (make_candidate(
            "A17" if bid_iceberg else "A18",
            symbol=after.symbol,
            side=HookSide.BID if bid_iceberg else HookSide.ASK,
            source_time=event_time,
            received_time=received,
            source_sequence=str(getattr(trade, "trade_id", after.sequence)),
            metric_name="replenished_to_executed_ratio",
            metric_value=ratio,
            anchor_price=price,
            bid=after.best_bid,
            ask=after.best_ask,
            episode_id=f"{key[0]}:{price}:{now_ms // self.episode_window_ms}",
            quality_status=after.quality_status,
            quality_flags=after.quality_flags,
            evidence={
                "before_quantity": before_qty,
                "executed_quantity": quantity,
                "expected_after_quantity": expected_after,
                "observed_after_quantity": after_qty,
                "replenished_quantity": replenished,
                "repeat_count": repeat,
                "classification": "ICEBERG_SUSPECTED",
            },
        ),)
