"""Board/trade, absorption, wall, and liquidation interaction candidates."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any

from .detector_utils import ZERO, decimal_value, make_candidate, observation_times
from .models import HookCandidate, HookQualityStatus, HookSide


class InteractionDetector:
    """Independent relationship layer; existing AbsorptionDetector is untouched."""

    def __init__(self) -> None:
        self._absorption_counts: dict[tuple[str, Decimal], int] = defaultdict(int)

    def observe_absorption(
        self,
        *,
        classification: str,
        symbol: str,
        anchor_price: Any,
        strength: Any,
        event_time: datetime,
        received_time: datetime,
        broken: bool,
        bid: Any = None,
        ask: Any = None,
        quality_status: HookQualityStatus = HookQualityStatus.VALID,
        quality_flags: tuple[str, ...] = (),
    ) -> tuple[HookCandidate, ...]:
        source, received = observation_times(event_time, received_time)
        price = decimal_value(anchor_price, "anchor_price")
        measured_strength = decimal_value(strength, "strength")
        if classification not in {"BUY_ABSORPTION", "SELL_ABSORPTION"}:
            return ()
        side = (
            HookSide.BUY
            if classification == "BUY_ABSORPTION"
            else HookSide.SELL
        )
        key = (classification, price)
        self._absorption_counts[key] += 1
        count = self._absorption_counts[key]
        common = {
            "symbol": symbol,
            "source_time": source,
            "received_time": received,
            "side": side,
            "anchor_price": price,
            "bid": bid,
            "ask": ask,
            "episode_id": f"{classification}:{price}",
            "quality_status": quality_status,
            "quality_flags": quality_flags,
        }
        result = [make_candidate(
            "C05",
            metric_name="same_band_absorption_count",
            metric_value=count,
            evidence={
                "classification": classification,
                "absorption_strength": measured_strength,
            },
            **common,
        )]
        if broken:
            result.append(make_candidate(
                "C03" if classification == "BUY_ABSORPTION" else "C04",
                metric_name="failed_absorption_strength",
                metric_value=measured_strength,
                evidence={
                    "classification": classification,
                    "same_band_absorption_count": count,
                    "broken": True,
                },
                **common,
            ))
        return tuple(result)

    def observe_wall_trade(
        self,
        *,
        symbol: str,
        wall_side: HookSide,
        price: Any,
        before_quantity: Any,
        after_quantity: Any,
        aggressive_quantity: Any,
        event_time: datetime,
        received_time: datetime,
        source_sequence: str | None = None,
        bid: Any = None,
        ask: Any = None,
        quality_status: HookQualityStatus = HookQualityStatus.VALID,
        quality_flags: tuple[str, ...] = (),
    ) -> tuple[HookCandidate, ...]:
        if wall_side not in {HookSide.BID, HookSide.ASK}:
            raise ValueError("wall_side must be BID or ASK")
        source, received = observation_times(event_time, received_time)
        anchor = decimal_value(price, "price")
        before = decimal_value(before_quantity, "before_quantity")
        after = decimal_value(after_quantity, "after_quantity")
        aggressive = decimal_value(aggressive_quantity, "aggressive_quantity")
        if before <= ZERO or aggressive <= ZERO:
            return ()
        common = {
            "symbol": symbol,
            "source_time": source,
            "received_time": received,
            "side": wall_side,
            "source_sequence": source_sequence,
            "anchor_price": anchor,
            "bid": bid,
            "ask": ask,
            "episode_id": f"{wall_side.value}:{anchor}:{source.isoformat()}",
            "quality_status": quality_status,
            "quality_flags": quality_flags,
        }
        consumed_fraction = max(ZERO, before - max(after, ZERO)) / before
        result = [make_candidate(
            "C06",
            metric_name="aggressive_to_wall_quantity_ratio",
            metric_value=aggressive / before,
            evidence={
                "before_quantity": before,
                "after_quantity": after,
                "aggressive_quantity": aggressive,
            },
            **common,
        )]
        if after <= ZERO:
            result.append(make_candidate(
                "C07" if wall_side is HookSide.ASK else "C08",
                metric_name="wall_consumed_fraction",
                metric_value=consumed_fraction,
                evidence={
                    "before_quantity": before,
                    "after_quantity": after,
                    "aggressive_quantity": aggressive,
                },
                **common,
            ))
        return tuple(result)

    def observe_liquidation_response(
        self,
        liquidation: Any,
        *,
        response_price: Any,
        received_time: datetime,
        absorption_side: HookSide,
        bid: Any = None,
        ask: Any = None,
        quality_status: HookQualityStatus = HookQualityStatus.VALID,
        quality_flags: tuple[str, ...] = (),
    ) -> tuple[HookCandidate, ...]:
        if absorption_side not in {HookSide.BID, HookSide.ASK}:
            raise ValueError("absorption_side must be BID or ASK")
        source, received = observation_times(liquidation.event_time, received_time)
        initial = decimal_value(liquidation.price, "liquidation price")
        response = decimal_value(response_price, "response price")
        if initial <= ZERO or response <= ZERO:
            return ()
        response_bps = abs(response - initial) / initial * Decimal(10_000)
        return (make_candidate(
            "C09",
            symbol=liquidation.symbol,
            side=absorption_side,
            source_time=source,
            received_time=received,
            metric_name="absolute_post_liquidation_response_bps",
            metric_value=response_bps,
            anchor_price=initial,
            bid=bid,
            ask=ask,
            episode_id=f"C09:{source.isoformat()}:{initial}",
            quality_status=quality_status,
            quality_flags=quality_flags,
            evidence={
                "liquidation_side": str(liquidation.side),
                "liquidation_quantity": decimal_value(
                    liquidation.quantity, "liquidation quantity"
                ),
                "response_price": response,
                "absorption_side": absorption_side.value,
            },
        ),)
