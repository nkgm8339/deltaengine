"""Open-interest change versus price-quadrant candidates F01-F05."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Mapping

from .detector_utils import ZERO, decimal_value, make_candidate, observation_times
from .models import HookCandidate, HookQualityStatus, HookSide


@dataclass(frozen=True)
class _OiPoint:
    source_time: datetime
    open_interest: Decimal
    price: Decimal


class OpenInterestDetector:
    def __init__(self, *, comparison_window_sec: int) -> None:
        if comparison_window_sec < 1:
            raise ValueError("comparison_window_sec must be positive")
        self.comparison_window_sec = int(comparison_window_sec)
        self._points: deque[_OiPoint] = deque()
        self.stale_samples = 0

    def process(
        self,
        sample: Mapping[str, Any],
        *,
        price: Any,
        received_time: datetime,
        quality_status: HookQualityStatus = HookQualityStatus.VALID,
        quality_flags: tuple[str, ...] = (),
    ) -> tuple[HookCandidate, ...]:
        source, received = observation_times(sample["source_time"], received_time)
        if self._points and source <= self._points[-1].source_time:
            self.stale_samples += 1
            return ()
        oi = decimal_value(sample["open_interest"], "open_interest")
        current_price = decimal_value(price, "price")
        if oi <= ZERO or current_price <= ZERO:
            return ()

        cutoff = source - timedelta(seconds=self.comparison_window_sec)
        while len(self._points) > 1 and self._points[1].source_time <= cutoff:
            self._points.popleft()
        baseline = self._points[0] if self._points else None
        self._points.append(_OiPoint(source, oi, current_price))
        if baseline is None:
            return ()

        oi_change_pct = (oi - baseline.open_interest) / baseline.open_interest * Decimal(
            100
        )
        price_change_bps = (
            (current_price - baseline.price) / baseline.price * Decimal(10_000)
        )
        symbol = str(sample["symbol"]).upper()
        evidence = {
            "comparison_window_sec": self.comparison_window_sec,
            "baseline_time": baseline.source_time,
            "baseline_open_interest": baseline.open_interest,
            "current_open_interest": oi,
            "price_change_bps": price_change_bps,
        }
        result: list[HookCandidate] = [make_candidate(
            "F05",
            symbol=symbol,
            side=HookSide.NEUTRAL,
            source_time=source,
            received_time=received,
            metric_name="absolute_oi_change_pct",
            metric_value=abs(oi_change_pct),
            anchor_price=current_price,
            episode_id=f"F05:{source.isoformat()}",
            quality_status=quality_status,
            quality_flags=quality_flags,
            evidence=evidence,
        )]
        if oi_change_pct == ZERO or price_change_bps == ZERO:
            return tuple(result)
        if oi_change_pct > ZERO and price_change_bps > ZERO:
            hook_id, side = "F01", HookSide.BUY
        elif oi_change_pct > ZERO and price_change_bps < ZERO:
            hook_id, side = "F02", HookSide.SELL
        elif oi_change_pct < ZERO and price_change_bps > ZERO:
            hook_id, side = "F03", HookSide.BUY
        else:
            hook_id, side = "F04", HookSide.SELL
        result.append(make_candidate(
            hook_id,
            symbol=symbol,
            side=side,
            source_time=source,
            received_time=received,
            metric_name="absolute_oi_change_pct",
            metric_value=abs(oi_change_pct),
            anchor_price=current_price,
            episode_id=f"{hook_id}:{source.isoformat()}",
            quality_status=quality_status,
            quality_flags=quality_flags,
            evidence=evidence,
        ))
        return tuple(result)
