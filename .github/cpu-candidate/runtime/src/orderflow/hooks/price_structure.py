"""Closed-candle price-structure and location candidates G01-G11."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from typing import Any

from .detector_utils import ZERO, decimal_value, make_candidate, observation_times
from .models import HookCandidate, HookQualityStatus, HookSide


class PriceStructureDetector:
    """Uses closed bars only; all distance cutoffs remain calibration-owned."""

    def __init__(
        self,
        *,
        lookback_bars: int,
        timeframe_sec: int,
        round_increment: Any,
        volume_node_bin_size: Any,
    ) -> None:
        if lookback_bars < 2 or timeframe_sec < 1:
            raise ValueError("lookback_bars >= 2 and timeframe_sec > 0 required")
        self.lookback_bars = int(lookback_bars)
        self.timeframe_sec = int(timeframe_sec)
        self.round_increment = decimal_value(round_increment, "round_increment")
        self.volume_node_bin_size = decimal_value(
            volume_node_bin_size, "volume_node_bin_size"
        )
        if self.round_increment <= ZERO or self.volume_node_bin_size <= ZERO:
            raise ValueError("price increments must be positive")
        self._history: deque[Any] = deque(maxlen=self.lookback_bars)
        self._last_bar_time: datetime | None = None
        self._pending_high_break: Decimal | None = None
        self._pending_low_break: Decimal | None = None
        self._vwap_day = None
        self._vwap_notional = ZERO
        self._vwap_volume = ZERO
        self.stale_bars = 0

    def _volume_node(self, bars: list[Any]) -> tuple[Decimal, Decimal]:
        profile: dict[Decimal, Decimal] = defaultdict(lambda: ZERO)
        for bar in bars:
            close = decimal_value(bar.close, "close")
            volume = decimal_value(bar.volume, "volume")
            bucket = (
                (close / self.volume_node_bin_size).to_integral_value(
                    rounding=ROUND_FLOOR
                )
                * self.volume_node_bin_size
            )
            profile[bucket] += max(ZERO, volume)
        node, node_volume = max(profile.items(), key=lambda row: (row[1], row[0]))
        return node, node_volume

    def process(
        self,
        candle: Any,
        *,
        received_time: datetime,
        quality_status: HookQualityStatus = HookQualityStatus.VALID,
        quality_flags: tuple[str, ...] = (),
    ) -> tuple[HookCandidate, ...]:
        bar_time = candle.bar_time
        close_time = bar_time + timedelta(seconds=self.timeframe_sec)
        source, received = observation_times(close_time, received_time)
        if self._last_bar_time is not None and bar_time <= self._last_bar_time:
            self.stale_bars += 1
            return ()
        self._last_bar_time = bar_time

        open_price = decimal_value(candle.open, "open")
        high = decimal_value(candle.high, "high")
        low = decimal_value(candle.low, "low")
        close = decimal_value(candle.close, "close")
        volume = decimal_value(candle.volume, "volume")
        if (
            min(open_price, high, low, close) <= ZERO
            or volume < ZERO
            or low > min(open_price, close)
            or high < max(open_price, close)
            or low > high
        ):
            return ()

        symbol = str(candle.symbol).upper()
        sequence = f"{getattr(candle, 'timeframe', self.timeframe_sec)}:{bar_time.isoformat()}"
        common = {
            "symbol": symbol,
            "source_time": source,
            "received_time": received,
            "source_sequence": sequence,
            "anchor_price": close,
            "quality_status": quality_status,
            "quality_flags": quality_flags,
        }
        result: list[HookCandidate] = []

        if self._pending_high_break is not None and close <= self._pending_high_break:
            result.append(make_candidate(
                "G05",
                side=HookSide.SELL,
                metric_name="failed_break_return_bps",
                metric_value=(self._pending_high_break - close)
                / self._pending_high_break
                * Decimal(10_000),
                episode_id=f"G05:{bar_time.isoformat()}",
                evidence={"broken_level": self._pending_high_break},
                **common,
            ))
            self._pending_high_break = None
        if self._pending_low_break is not None and close >= self._pending_low_break:
            result.append(make_candidate(
                "G06",
                side=HookSide.BUY,
                metric_name="failed_break_return_bps",
                metric_value=(close - self._pending_low_break)
                / self._pending_low_break
                * Decimal(10_000),
                episode_id=f"G06:{bar_time.isoformat()}",
                evidence={"broken_level": self._pending_low_break},
                **common,
            ))
            self._pending_low_break = None

        history = list(self._history)
        if history:
            recent_high = max(decimal_value(row.high, "history high") for row in history)
            recent_low = min(decimal_value(row.low, "history low") for row in history)
            result.extend((
                make_candidate(
                    "G01",
                    side=HookSide.ASK,
                    metric_name="distance_to_recent_high_bps",
                    metric_value=abs(recent_high - high) / recent_high * Decimal(10_000),
                    evidence={"recent_high": recent_high, "lookback_bars": len(history)},
                    **common,
                ),
                make_candidate(
                    "G02",
                    side=HookSide.BID,
                    metric_name="distance_to_recent_low_bps",
                    metric_value=abs(low - recent_low) / recent_low * Decimal(10_000),
                    evidence={"recent_low": recent_low, "lookback_bars": len(history)},
                    **common,
                ),
            ))
            if high > recent_high:
                result.append(make_candidate(
                    "G03",
                    side=HookSide.BUY,
                    metric_name="high_break_bps",
                    metric_value=(high - recent_high) / recent_high * Decimal(10_000),
                    episode_id=f"G03:{bar_time.isoformat()}:{recent_high}",
                    evidence={"broken_level": recent_high},
                    **common,
                ))
                self._pending_high_break = recent_high
            if low < recent_low:
                result.append(make_candidate(
                    "G04",
                    side=HookSide.SELL,
                    metric_name="low_break_bps",
                    metric_value=(recent_low - low) / recent_low * Decimal(10_000),
                    episode_id=f"G04:{bar_time.isoformat()}:{recent_low}",
                    evidence={"broken_level": recent_low},
                    **common,
                ))
                self._pending_low_break = recent_low

            upper_distance = abs(recent_high - close) / recent_high * Decimal(10_000)
            lower_distance = abs(close - recent_low) / recent_low * Decimal(10_000)
            upper = upper_distance <= lower_distance
            result.append(make_candidate(
                "G11",
                side=HookSide.ASK if upper else HookSide.BID,
                metric_name="distance_to_nearest_range_edge_bps",
                metric_value=upper_distance if upper else lower_distance,
                evidence={
                    "range_high": recent_high,
                    "range_low": recent_low,
                    "nearest_edge": "UPPER" if upper else "LOWER",
                },
                **common,
            ))

        day = source.date()
        if day != self._vwap_day:
            self._vwap_day = day
            self._vwap_notional = ZERO
            self._vwap_volume = ZERO
        typical = (high + low + close) / Decimal(3)
        self._vwap_notional += typical * volume
        self._vwap_volume += volume
        if self._vwap_volume > ZERO:
            vwap = self._vwap_notional / self._vwap_volume
            deviation_bps = abs(close - vwap) / vwap * Decimal(10_000)
            result.extend((
                make_candidate(
                    "G07",
                    side=HookSide.NEUTRAL,
                    metric_name="distance_to_session_vwap_bps",
                    metric_value=deviation_bps,
                    evidence={"session_vwap": vwap},
                    **common,
                ),
                make_candidate(
                    "G08",
                    side=HookSide.NEUTRAL,
                    metric_name="absolute_vwap_deviation_bps",
                    metric_value=deviation_bps,
                    evidence={
                        "session_vwap": vwap,
                        "signed_deviation": close - vwap,
                    },
                    **common,
                ),
            ))

        profile_bars = [*history, candle]
        node, node_volume = self._volume_node(profile_bars)
        result.append(make_candidate(
            "G09",
            side=HookSide.NEUTRAL,
            metric_name="distance_to_high_volume_node_bps",
            metric_value=abs(close - node) / close * Decimal(10_000),
            evidence={
                "node_price": node,
                "node_volume": node_volume,
                "profile_bars": len(profile_bars),
                "bin_size": self.volume_node_bin_size,
            },
            **common,
        ))
        round_price = (
            (close / self.round_increment).to_integral_value(rounding=ROUND_HALF_UP)
            * self.round_increment
        )
        result.append(make_candidate(
            "G10",
            side=HookSide.NEUTRAL,
            metric_name="distance_to_round_number_bps",
            metric_value=abs(close - round_price) / close * Decimal(10_000),
            evidence={
                "round_price": round_price,
                "round_increment": self.round_increment,
            },
            **common,
        ))

        self._history.append(candle)
        return tuple(result)
