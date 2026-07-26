"""Shared helpers for independent Stage 2B observational detectors."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Mapping

from .models import (
    HookCandidate,
    HookQualityStatus,
    HookSide,
    as_utc,
)
from .registry import require_hook


ZERO = Decimal(0)
ONE = Decimal(1)
BPS = Decimal(10_000)


def decimal_value(value: Any, field_name: str) -> Decimal:
    parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    if not parsed.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return parsed


def observation_times(
    source_time: datetime,
    received_time: datetime,
    *,
    future_tolerance_ms: int = 0,
) -> tuple[datetime, datetime]:
    source = as_utc(source_time, "source_time")
    received = as_utc(received_time, "received_time")
    if future_tolerance_ms < 0:
        raise ValueError("future_tolerance_ms must be non-negative")
    if source > received + timedelta(milliseconds=future_tolerance_ms):
        raise ValueError("source_time cannot be later than received_time")
    return source, received


def bps_change(new: Decimal, old: Decimal) -> Decimal:
    if old <= ZERO:
        raise ValueError("bps denominator must be positive")
    return (new - old) / old * BPS


def make_candidate(
    hook_id: str,
    *,
    symbol: str,
    side: HookSide,
    source_time: datetime,
    received_time: datetime,
    metric_name: str,
    metric_value: Any,
    source_sequence: str | None = None,
    anchor_price: Any = None,
    bid: Any = None,
    ask: Any = None,
    episode_id: str | None = None,
    quality_status: HookQualityStatus = HookQualityStatus.VALID,
    quality_flags: tuple[str, ...] = (),
    evidence: Mapping[str, Any] | None = None,
) -> HookCandidate:
    definition = require_hook(hook_id)
    source, received = observation_times(source_time, received_time)
    parsed_bid = decimal_value(bid, "bid") if bid is not None else None
    parsed_ask = decimal_value(ask, "ask") if ask is not None else None
    mid = (
        (parsed_bid + parsed_ask) / Decimal(2)
        if parsed_bid is not None and parsed_ask is not None
        else None
    )
    return HookCandidate(
        hook_id=hook_id,
        symbol=symbol.upper(),
        side=side,
        direction_hint=definition.direction_hint,
        source_time=source,
        received_time=received,
        available_time=received,
        metric_name=metric_name,
        metric_value=decimal_value(metric_value, "metric_value"),
        source_sequence=source_sequence,
        anchor_price=(
            decimal_value(anchor_price, "anchor_price")
            if anchor_price is not None
            else None
        ),
        binance_bid=parsed_bid,
        binance_ask=parsed_ask,
        binance_mid=mid,
        episode_id=episode_id,
        quality_status=quality_status,
        quality_flags=quality_flags,
        evidence=dict(evidence or {}),
    )
