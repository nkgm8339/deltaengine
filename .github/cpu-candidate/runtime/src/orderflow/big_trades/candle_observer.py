"""Pure 1-minute candle facts relative to a Reaction Zone."""

from __future__ import annotations

from decimal import Decimal

from .constants import CandleResultLabel
from .ids import candle_observation_id, content_hash
from .models import ClosedCandle, ReactionZone, ZoneCandleObservation, ZERO
from .reaction_zones import relation_for_price
from .time_buckets import candle_id as expected_candle_id


class CandleBoundaryMismatch(ValueError):
    pass


class ZoneCandleObserver:
    def __init__(self, *, tick_size: Decimal) -> None:
        self.tick_size = Decimal(str(tick_size))
        if not self.tick_size.is_finite() or self.tick_size <= ZERO:
            raise ValueError("tick_size must be finite and positive")

    def observe(
        self,
        zone: ReactionZone,
        candle: ClosedCandle,
    ) -> ZoneCandleObservation:
        calculated_id = expected_candle_id(candle.open_time)
        if calculated_id != candle.candle_id:
            raise CandleBoundaryMismatch(
                f"CANDLE_BOUNDARY_MISMATCH expected={calculated_id} actual={candle.candle_id}"
            )
        if candle.symbol != zone.symbol:
            raise ValueError("candle symbol does not match zone")
        body_low = min(candle.open, candle.close)
        body_high = max(candle.open, candle.close)
        body_overlaps = max(body_low, zone.zone_low) <= min(body_high, zone.zone_high)
        wick_overlaps = max(candle.low, zone.zone_low) <= min(candle.high, zone.zone_high)
        closed_above = candle.close > zone.zone_high
        closed_below = candle.close < zone.zone_low
        upper_return = candle.high > zone.zone_high and candle.close <= zone.zone_high
        lower_return = candle.low < zone.zone_low and candle.close >= zone.zone_low
        labels: list[CandleResultLabel] = []
        if closed_above:
            labels.append(CandleResultLabel.CLOSE_ABOVE)
        elif closed_below:
            labels.append(CandleResultLabel.CLOSE_BELOW)
        else:
            labels.append(CandleResultLabel.CLOSED_INSIDE)
        if upper_return:
            labels.append(CandleResultLabel.UPPER_WICK_RETURN)
        if lower_return:
            labels.append(CandleResultLabel.LOWER_WICK_RETURN)
        payload = {
            "candle_observation_id": candle_observation_id(zone.zone_id, candle.candle_id),
            "zone_id": zone.zone_id,
            "candle_id": candle.candle_id,
            "open_price": candle.open,
            "high_price": candle.high,
            "low_price": candle.low,
            "close_price": candle.close,
            "candle_open_relation": relation_for_price(zone, candle.open),
            "candle_close_relation": relation_for_price(zone, candle.close),
            "candle_high_above_ticks": max(ZERO, (candle.high - zone.zone_high) / self.tick_size),
            "candle_low_below_ticks": max(ZERO, (zone.zone_low - candle.low) / self.tick_size),
            "body_low": body_low,
            "body_high": body_high,
            "body_overlaps_zone": body_overlaps,
            "wick_overlaps_zone": wick_overlaps,
            "closed_above_zone": closed_above,
            "closed_below_zone": closed_below,
            "returned_inside_after_upper_excursion": upper_return,
            "returned_inside_after_lower_excursion": lower_return,
            "labels": tuple(labels),
        }
        return ZoneCandleObservation(content_hash=content_hash(payload), **payload)
