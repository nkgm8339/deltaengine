"""forceOrder-derived liquidation measurement candidates E01-E06."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from .detector_utils import ZERO, decimal_value, make_candidate, observation_times
from .models import HookCandidate, HookQualityStatus, HookSide


@dataclass(frozen=True)
class _LiquidationPoint:
    event_time: datetime
    symbol: str
    side: str
    price: Decimal
    quantity: Decimal
    notional: Decimal
    received_time: datetime


class LiquidationDetector:
    """Window lengths are configuration inputs, never calibration thresholds."""

    def __init__(
        self,
        *,
        cascade_window_ms: int,
        response_window_ms: int,
        exhaustion_gap_ms: int,
    ) -> None:
        if min(cascade_window_ms, response_window_ms, exhaustion_gap_ms) < 1:
            raise ValueError("liquidation windows must be positive")
        self.cascade_window_ms = int(cascade_window_ms)
        self.response_window_ms = int(response_window_ms)
        self.exhaustion_gap_ms = int(exhaustion_gap_ms)
        self._windows: dict[str, deque[_LiquidationPoint]] = {
            "SELL": deque(),
            "BUY": deque(),
        }
        self._pending_response: deque[_LiquidationPoint] = deque()
        self._last_time: datetime | None = None
        self._exhaustion_emitted: set[tuple[str, datetime]] = set()
        self.stale_events = 0

    @staticmethod
    def _hook_side(side: str) -> HookSide:
        return HookSide.SELL if side == "SELL" else HookSide.BUY

    def _prune(self, side: str, now: datetime) -> None:
        cutoff = now - timedelta(milliseconds=self.cascade_window_ms)
        window = self._windows[side]
        while window and window[0].event_time < cutoff:
            window.popleft()

    def _exhaustion_candidates(
        self,
        *,
        source_time: datetime,
        received_time: datetime,
        symbol: str,
        price: Decimal,
        quality_status: HookQualityStatus,
        quality_flags: tuple[str, ...],
    ) -> list[HookCandidate]:
        result: list[HookCandidate] = []
        for side, window in self._windows.items():
            if not window:
                continue
            last = window[-1]
            gap_ms = int((source_time - last.event_time).total_seconds() * 1000)
            key = (side, last.event_time)
            if gap_ms < self.exhaustion_gap_ms or key in self._exhaustion_emitted:
                continue
            self._exhaustion_emitted.add(key)
            result.append(make_candidate(
                "E06",
                symbol=symbol,
                side=self._hook_side(side),
                source_time=source_time,
                received_time=received_time,
                metric_name="liquidation_quiet_gap_ms",
                metric_value=gap_ms,
                anchor_price=price,
                episode_id=f"E06:{side}:{last.event_time.isoformat()}",
                quality_status=quality_status,
                quality_flags=quality_flags,
                evidence={
                    "liquidation_side": side,
                    "prior_window_count": len(window),
                    "prior_window_notional": sum(
                        (point.notional for point in window), ZERO
                    ),
                    "last_liquidation_time": last.event_time,
                },
            ))
        return result

    def process(
        self,
        event: Any,
        *,
        received_time: datetime,
        quality_status: HookQualityStatus = HookQualityStatus.VALID,
        quality_flags: tuple[str, ...] = (),
    ) -> tuple[HookCandidate, ...]:
        source, received = observation_times(event.event_time, received_time)
        if self._last_time is not None and source < self._last_time:
            self.stale_events += 1
            return ()
        side = str(event.side)
        if side not in {"SELL", "BUY"}:
            return ()
        price = decimal_value(event.price, "liquidation price")
        quantity = decimal_value(event.quantity, "liquidation quantity")
        if price <= ZERO or quantity <= ZERO:
            return ()

        result = self._exhaustion_candidates(
            source_time=source,
            received_time=received,
            symbol=str(event.symbol).upper(),
            price=price,
            quality_status=quality_status,
            quality_flags=quality_flags,
        )
        point = _LiquidationPoint(
            event_time=source,
            symbol=str(event.symbol).upper(),
            side=side,
            price=price,
            quantity=quantity,
            notional=price * quantity,
            received_time=received,
        )
        self._windows[side].append(point)
        self._prune(side, source)
        self._pending_response.append(point)
        self._last_time = source
        window = self._windows[side]
        hook_side = self._hook_side(side)
        result.extend((
            make_candidate(
                "E01" if side == "SELL" else "E02",
                symbol=point.symbol,
                side=hook_side,
                source_time=source,
                received_time=received,
                metric_name="liquidation_notional",
                metric_value=point.notional,
                anchor_price=price,
                source_sequence=f"{side}:{source.isoformat()}",
                episode_id=f"{side}:{source.isoformat()}:{price}",
                quality_status=quality_status,
                quality_flags=quality_flags,
                evidence={"quantity": quantity, "forced_order_side": side},
            ),
            make_candidate(
                "E03" if side == "SELL" else "E04",
                symbol=point.symbol,
                side=hook_side,
                source_time=source,
                received_time=received,
                metric_name="cascade_window_notional",
                metric_value=sum((item.notional for item in window), ZERO),
                anchor_price=price,
                source_sequence=f"{side}:{source.isoformat()}",
                episode_id=(
                    f"{side}:{int(source.timestamp() * 1000) // self.cascade_window_ms}"
                ),
                quality_status=quality_status,
                quality_flags=quality_flags,
                evidence={
                    "window_ms": self.cascade_window_ms,
                    "event_count": len(window),
                    "forced_order_side": side,
                },
            ),
        ))
        return tuple(result)

    def observe_price(
        self,
        *,
        symbol: str,
        price: Any,
        source_time: datetime,
        received_time: datetime,
        quality_status: HookQualityStatus = HookQualityStatus.VALID,
        quality_flags: tuple[str, ...] = (),
    ) -> tuple[HookCandidate, ...]:
        source, received = observation_times(source_time, received_time)
        observed_price = decimal_value(price, "price")
        if observed_price <= ZERO:
            return ()
        result = self._exhaustion_candidates(
            source_time=source,
            received_time=received,
            symbol=symbol.upper(),
            price=observed_price,
            quality_status=quality_status,
            quality_flags=quality_flags,
        )
        cutoff = source - timedelta(milliseconds=self.response_window_ms)
        while self._pending_response and self._pending_response[0].event_time <= cutoff:
            point = self._pending_response.popleft()
            response_bps = abs(observed_price - point.price) / point.price * Decimal(
                10_000
            )
            result.append(make_candidate(
                "E05",
                symbol=point.symbol,
                side=self._hook_side(point.side),
                source_time=source,
                received_time=received,
                metric_name="absolute_post_liquidation_response_bps",
                metric_value=response_bps,
                anchor_price=point.price,
                episode_id=f"E05:{point.side}:{point.event_time.isoformat()}",
                quality_status=quality_status,
                quality_flags=quality_flags,
                evidence={
                    "liquidation_time": point.event_time,
                    "liquidation_side": point.side,
                    "liquidation_notional": point.notional,
                    "response_price": observed_price,
                    "response_window_ms": self.response_window_ms,
                },
            ))
        return tuple(result)
