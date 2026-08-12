"""Stable contracts shared by Hook detectors, replay, and Parquet storage."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping


class HookSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    BID = "BID"
    ASK = "ASK"
    NEUTRAL = "NEUTRAL"


class DirectionHint(str, Enum):
    """Observed market-direction implication; never an execution instruction."""

    UP = "UP"
    DOWN = "DOWN"
    BOTH = "BOTH"
    NONE = "NONE"


class HookQualityStatus(str, Enum):
    VALID = "VALID"
    DEGRADED = "DEGRADED"
    INVALID = "INVALID"


class CalibrationStatus(str, Enum):
    UNCALIBRATED = "UNCALIBRATED"
    PROVISIONAL = "PROVISIONAL"
    CALIBRATED = "CALIBRATED"
    DISABLED = "DISABLED"


_VALID_OPERATORS = frozenset({"ge", "gt", "le", "lt", "always"})


def as_utc(value: datetime, field_name: str = "time") -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def finite_decimal(value: Any, field_name: str, *, optional: bool = False) -> Decimal | None:
    if value is None and optional:
        return None
    parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    if not parsed.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return parsed


def _json_default(value: Any) -> str:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return as_utc(value).isoformat()
    if isinstance(value, Enum):
        return str(value.value)
    raise TypeError(f"unsupported evidence value: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_json_default,
    )


@dataclass(frozen=True)
class HookCandidate:
    """A measured observation before calibration gating."""

    hook_id: str
    symbol: str
    side: HookSide
    direction_hint: DirectionHint
    source_time: datetime
    received_time: datetime
    available_time: datetime
    metric_name: str
    metric_value: Decimal
    source_sequence: str | None = None
    anchor_price: Decimal | None = None
    binance_bid: Decimal | None = None
    binance_ask: Decimal | None = None
    binance_mid: Decimal | None = None
    episode_id: str | None = None
    quality_status: HookQualityStatus = HookQualityStatus.VALID
    quality_flags: tuple[str, ...] = ()
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        from .registry import require_hook

        require_hook(self.hook_id)
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("symbol must be non-empty uppercase")
        object.__setattr__(self, "source_time", as_utc(self.source_time, "source_time"))
        object.__setattr__(
            self, "received_time", as_utc(self.received_time, "received_time")
        )
        object.__setattr__(
            self, "available_time", as_utc(self.available_time, "available_time")
        )
        if not self.metric_name:
            raise ValueError("metric_name must be non-empty")
        object.__setattr__(
            self,
            "metric_value",
            finite_decimal(self.metric_value, "metric_value"),
        )
        for name in ("anchor_price", "binance_bid", "binance_ask", "binance_mid"):
            parsed = finite_decimal(getattr(self, name), name, optional=True)
            if parsed is not None and parsed <= 0:
                raise ValueError(f"{name} must be positive when present")
            object.__setattr__(self, name, parsed)
        if (
            self.binance_bid is not None
            and self.binance_ask is not None
            and self.binance_ask < self.binance_bid
        ):
            raise ValueError("binance_ask must be >= binance_bid")
        canonical_json(dict(self.evidence))


@dataclass(frozen=True)
class HookThreshold:
    hook_id: str
    metric_name: str
    operator: str
    quantile: Decimal | None
    value: Decimal | None
    status: CalibrationStatus
    input_manifest_sha256: str | None = None
    sample_count: int = 0
    valid_days: int = 0

    def __post_init__(self) -> None:
        from .registry import require_hook

        require_hook(self.hook_id)
        if not self.metric_name:
            raise ValueError("metric_name must be non-empty")
        if self.operator not in _VALID_OPERATORS:
            raise ValueError(f"unsupported threshold operator: {self.operator}")
        object.__setattr__(
            self, "quantile", finite_decimal(self.quantile, "quantile", optional=True)
        )
        object.__setattr__(
            self, "value", finite_decimal(self.value, "value", optional=True)
        )
        if self.quantile is not None and not Decimal(0) <= self.quantile <= Decimal(1):
            raise ValueError("quantile must be in [0, 1]")
        if self.sample_count < 0 or self.valid_days < 0:
            raise ValueError("sample_count and valid_days must be non-negative")
        if self.status is CalibrationStatus.CALIBRATED:
            if (
                self.input_manifest_sha256 is None
                or len(self.input_manifest_sha256) != 64
                or any(ch not in "0123456789abcdef" for ch in self.input_manifest_sha256)
            ):
                raise ValueError(
                    "calibrated threshold requires lowercase SHA-256 input manifest hash"
                )
            if self.operator != "always" and self.value is None:
                raise ValueError("calibrated numeric threshold requires value")
            if self.operator == "always" and self.value is not None:
                raise ValueError("always threshold must not define value")

    @property
    def allows_fire(self) -> bool:
        return self.status is CalibrationStatus.CALIBRATED

    def matches(self, candidate: HookCandidate) -> bool:
        if not self.allows_fire or candidate.metric_name != self.metric_name:
            return False
        if candidate.quality_status is not HookQualityStatus.VALID:
            return False
        if self.operator == "always":
            return True
        assert self.value is not None
        if self.operator == "ge":
            return candidate.metric_value >= self.value
        if self.operator == "gt":
            return candidate.metric_value > self.value
        if self.operator == "le":
            return candidate.metric_value <= self.value
        return candidate.metric_value < self.value


@dataclass(frozen=True)
class HookEvent:
    hook_event_id: str
    hook_id: str
    detector_version: str
    config_hash: str
    input_manifest_hash: str | None
    symbol: str
    side: HookSide
    direction_hint: DirectionHint
    source_time: datetime
    received_time: datetime
    available_time: datetime
    detected_time: datetime
    source_sequence: str | None
    anchor_price: Decimal | None
    binance_bid: Decimal | None
    binance_ask: Decimal | None
    binance_mid: Decimal | None
    metric_name: str
    metric_value: Decimal
    threshold_value: Decimal | None
    threshold_quantile: Decimal | None
    episode_id: str | None
    quality_status: HookQualityStatus
    quality_flags: tuple[str, ...]
    evidence: Mapping[str, Any]

    @classmethod
    def from_candidate(
        cls,
        candidate: HookCandidate,
        threshold: HookThreshold,
        *,
        detector_version: str,
        config_hash: str,
        input_manifest_hash: str | None = None,
        detected_time: datetime | None = None,
    ) -> "HookEvent":
        detected = as_utc(
            detected_time or candidate.available_time,
            "detected_time",
        )
        identity = {
            "hook_id": candidate.hook_id,
            "symbol": candidate.symbol,
            "side": candidate.side.value,
            "source_time": candidate.source_time.isoformat(),
            "source_sequence": candidate.source_sequence,
            "anchor_price": candidate.anchor_price,
            "episode_id": candidate.episode_id,
            "metric_name": candidate.metric_name,
            "metric_value": candidate.metric_value,
            "detector_version": detector_version,
            "config_hash": config_hash,
        }
        event_id = hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest()
        return cls(
            hook_event_id=event_id,
            hook_id=candidate.hook_id,
            detector_version=detector_version,
            config_hash=config_hash,
            input_manifest_hash=input_manifest_hash,
            symbol=candidate.symbol,
            side=candidate.side,
            direction_hint=candidate.direction_hint,
            source_time=candidate.source_time,
            received_time=candidate.received_time,
            available_time=candidate.available_time,
            detected_time=detected,
            source_sequence=candidate.source_sequence,
            anchor_price=candidate.anchor_price,
            binance_bid=candidate.binance_bid,
            binance_ask=candidate.binance_ask,
            binance_mid=candidate.binance_mid,
            metric_name=candidate.metric_name,
            metric_value=candidate.metric_value,
            threshold_value=threshold.value,
            threshold_quantile=threshold.quantile,
            episode_id=candidate.episode_id,
            quality_status=candidate.quality_status,
            quality_flags=candidate.quality_flags,
            evidence=dict(candidate.evidence),
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "hook_event_id": self.hook_event_id,
            "hook_id": self.hook_id,
            "detector_version": self.detector_version,
            "config_hash": self.config_hash,
            "input_manifest_hash": self.input_manifest_hash,
            "symbol": self.symbol,
            "side": self.side.value,
            "direction_hint": self.direction_hint.value,
            "source_time": self.source_time,
            "received_time": self.received_time,
            "available_time": self.available_time,
            "detected_time": self.detected_time,
            "source_sequence": self.source_sequence,
            "anchor_price": self.anchor_price,
            "binance_bid": self.binance_bid,
            "binance_ask": self.binance_ask,
            "binance_mid": self.binance_mid,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "threshold_value": self.threshold_value,
            "threshold_quantile": self.threshold_quantile,
            "episode_id": self.episode_id,
            "quality_status": self.quality_status.value,
            "quality_flags_json": canonical_json(self.quality_flags),
            "evidence_json": canonical_json(dict(self.evidence)),
        }
