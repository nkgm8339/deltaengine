"""Immutable, versioned Big Trades settings and pending requests."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import Enum
import re
from typing import Any, Mapping, Optional

from .constants import (
    INPUT_MODE_AGGREGATE_TRADES,
    LOGIC_VERSION,
    AutomaticIntensity,
    FilterMode,
    MarkerPriceMode,
    SideFilter,
)
from .ids import canonical_json, content_hash, sha256_hex
from .models import BigTradesSettingsSnapshot, ZERO
from .time_buckets import require_aware_utc


SETTINGS_SCHEMA_VERSION = 1


def _require_keys(raw: Mapping[str, Any], expected: set[str], name: str) -> None:
    if set(raw) != expected:
        raise ValueError(f"{name} artifact fields do not match schema")


class SettingsRequestSource(str, Enum):
    UI = "UI"
    CONFIG = "CONFIG"
    REPLAY = "REPLAY"


class SettingsRequestStatus(str, Enum):
    PENDING = "PENDING"
    SUPERSEDED = "SUPERSEDED"
    ACTIVATED = "ACTIVATED"
    REJECTED = "REJECTED"


def _quantity(value: Decimal | str | int, name: str) -> Decimal:
    parsed = Decimal(str(value))
    if not parsed.is_finite() or parsed < ZERO:
        raise ValueError(f"{name} must be finite and non-negative")
    return parsed


@dataclass(frozen=True)
class SettingsVersion:
    settings_id: str
    content_sha256: str
    symbol: str
    venue: str
    filter_mode: FilterMode
    manual_min_quantity: Decimal
    manual_max_quantity: Decimal
    automatic_intensity: AutomaticIntensity
    side_filter: SideFilter
    marker_price_mode: MarkerPriceMode
    calibration_id: Optional[str]
    input_mode: str = INPUT_MODE_AGGREGATE_TRADES
    logic_version: str = LOGIC_VERSION
    schema_version: int = SETTINGS_SCHEMA_VERSION

    @classmethod
    def create(
        cls,
        *,
        symbol: str,
        venue: str,
        filter_mode: FilterMode | str,
        manual_min_quantity: Decimal | str,
        manual_max_quantity: Decimal | str,
        automatic_intensity: AutomaticIntensity | str,
        side_filter: SideFilter | str,
        marker_price_mode: MarkerPriceMode | str,
        calibration_id: Optional[str] = None,
        input_mode: str = INPUT_MODE_AGGREGATE_TRADES,
        logic_version: str = LOGIC_VERSION,
    ) -> "SettingsVersion":
        minimum = _quantity(manual_min_quantity, "manual_min_quantity")
        maximum = _quantity(manual_max_quantity, "manual_max_quantity")
        mode = FilterMode(filter_mode)
        if maximum > ZERO and maximum < minimum:
            raise ValueError("manual_max_quantity must be zero or >= manual_min_quantity")
        if input_mode != INPUT_MODE_AGGREGATE_TRADES:
            raise ValueError("only AGGREGATE_TRADES is supported")
        if logic_version != LOGIC_VERSION:
            raise ValueError(f"logic_version must be {LOGIC_VERSION}")
        if not symbol or not venue:
            raise ValueError("symbol and venue must be non-empty")
        if mode is FilterMode.MANUAL:
            calibration_id = None
        if calibration_id is not None and not re.fullmatch(
            r"btcal1_[0-9a-f]{64}", calibration_id
        ):
            raise ValueError("calibration_id has invalid format")
        identity = {
            "logic_version": logic_version,
            "symbol": symbol,
            "venue": venue,
            "input_mode": input_mode,
            "filter_mode": mode,
            "manual_min_quantity": minimum,
            "manual_max_quantity": maximum,
            "automatic_intensity": AutomaticIntensity(automatic_intensity),
            "side_filter": SideFilter(side_filter),
            "marker_price_mode": MarkerPriceMode(marker_price_mode),
            "calibration_id": calibration_id,
        }
        digest = sha256_hex(canonical_json(identity))
        return cls(
            settings_id="bts1_" + digest,
            content_sha256=digest,
            **identity,
        )

    @classmethod
    def from_config(
        cls,
        config: Any,
        *,
        symbol: str,
        venue: str,
        calibration_id: Optional[str] = None,
    ) -> "SettingsVersion":
        return cls.create(
            symbol=symbol,
            venue=venue,
            filter_mode=config.filter_mode,
            manual_min_quantity=config.manual_min_quantity,
            manual_max_quantity=config.manual_max_quantity,
            automatic_intensity=config.automatic_intensity,
            side_filter=config.side_filter,
            marker_price_mode=config.marker_price_mode,
            calibration_id=calibration_id,
            input_mode=config.input_mode,
        )

    def with_calibration(self, calibration_id: Optional[str]) -> "SettingsVersion":
        return SettingsVersion.create(
            symbol=self.symbol,
            venue=self.venue,
            filter_mode=self.filter_mode,
            manual_min_quantity=self.manual_min_quantity,
            manual_max_quantity=self.manual_max_quantity,
            automatic_intensity=self.automatic_intensity,
            side_filter=self.side_filter,
            marker_price_mode=self.marker_price_mode,
            calibration_id=calibration_id,
            input_mode=self.input_mode,
            logic_version=self.logic_version,
        )

    def to_runtime_snapshot(self, *, activation_id: str) -> BigTradesSettingsSnapshot:
        return BigTradesSettingsSnapshot(
            settings_id=self.settings_id,
            symbol=self.symbol,
            venue=self.venue,
            filter_mode=self.filter_mode,
            manual_min_quantity=self.manual_min_quantity,
            manual_max_quantity=self.manual_max_quantity,
            automatic_intensity=self.automatic_intensity,
            side_filter=self.side_filter,
            marker_price_mode=self.marker_price_mode,
            calibration_id=self.calibration_id,
            activation_id=activation_id,
            input_mode=self.input_mode,
            logic_version=self.logic_version,
        )

    def to_artifact(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "logic_version": self.logic_version,
            "settings_id": self.settings_id,
            "symbol": self.symbol,
            "venue": self.venue,
            "input_mode": self.input_mode,
            "filter_mode": self.filter_mode,
            "manual_min_quantity": self.manual_min_quantity,
            "manual_max_quantity": self.manual_max_quantity,
            "automatic_intensity": self.automatic_intensity,
            "side_filter": self.side_filter,
            "marker_price_mode": self.marker_price_mode,
            "calibration_id": self.calibration_id,
            "content_sha256": self.content_sha256,
        }

    @classmethod
    def from_artifact(cls, raw: Mapping[str, Any]) -> "SettingsVersion":
        _require_keys(
            raw,
            {
                "schema_version",
                "logic_version",
                "settings_id",
                "symbol",
                "venue",
                "input_mode",
                "filter_mode",
                "manual_min_quantity",
                "manual_max_quantity",
                "automatic_intensity",
                "side_filter",
                "marker_price_mode",
                "calibration_id",
                "content_sha256",
            },
            "settings",
        )
        expected = cls.create(
            symbol=str(raw["symbol"]),
            venue=str(raw["venue"]),
            filter_mode=str(raw["filter_mode"]),
            manual_min_quantity=str(raw["manual_min_quantity"]),
            manual_max_quantity=str(raw["manual_max_quantity"]),
            automatic_intensity=str(raw["automatic_intensity"]),
            side_filter=str(raw["side_filter"]),
            marker_price_mode=str(raw["marker_price_mode"]),
            calibration_id=raw.get("calibration_id"),
            input_mode=str(raw["input_mode"]),
            logic_version=str(raw["logic_version"]),
        )
        if raw.get("schema_version") != SETTINGS_SCHEMA_VERSION:
            raise ValueError("unsupported settings schema_version")
        if raw.get("settings_id") != expected.settings_id:
            raise ValueError("settings_id does not match canonical content")
        if raw.get("content_sha256") != expected.content_sha256:
            raise ValueError("settings content_sha256 mismatch")
        if raw.get("calibration_id") != expected.calibration_id:
            raise ValueError("settings calibration_id is invalid for filter mode")
        return expected


@dataclass(frozen=True)
class SettingsRequest:
    request_id: str
    settings_id: str
    requested_at_utc: datetime
    previous_settings_id: Optional[str]
    request_source: SettingsRequestSource
    request_status: SettingsRequestStatus
    content_hash: str

    @classmethod
    def create(
        cls,
        version: SettingsVersion,
        *,
        requested_at_utc: datetime,
        previous_settings_id: Optional[str],
        request_source: SettingsRequestSource | str,
        request_status: SettingsRequestStatus | str = SettingsRequestStatus.PENDING,
    ) -> "SettingsRequest":
        requested = require_aware_utc(requested_at_utc, "requested_at_utc")
        payload = {
            "settings_id": version.settings_id,
            "requested_at_utc": requested,
            "previous_settings_id": previous_settings_id,
            "request_source": SettingsRequestSource(request_source),
            "request_status": SettingsRequestStatus(request_status),
        }
        request_id = "btsreq1_" + sha256_hex(canonical_json(payload))
        return cls(
            request_id=request_id,
            content_hash=content_hash({"request_id": request_id, **payload}),
            **payload,
        )

    def with_status(self, status: SettingsRequestStatus | str) -> "SettingsRequest":
        return SettingsRequest.create_from_request(self, status=SettingsRequestStatus(status))

    @classmethod
    def create_from_request(
        cls,
        request: "SettingsRequest",
        *,
        status: SettingsRequestStatus,
    ) -> "SettingsRequest":
        payload = {
            "settings_id": request.settings_id,
            "requested_at_utc": request.requested_at_utc,
            "previous_settings_id": request.previous_settings_id,
            "request_source": request.request_source,
            "request_status": status,
        }
        request_id = "btsreq1_" + sha256_hex(canonical_json(payload))
        return replace(
            request,
            request_id=request_id,
            request_status=status,
            content_hash=content_hash({"request_id": request_id, **payload}),
        )

    def to_artifact(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "request_id": self.request_id,
            "settings_id": self.settings_id,
            "requested_at_utc": self.requested_at_utc,
            "previous_settings_id": self.previous_settings_id,
            "request_source": self.request_source,
            "request_status": self.request_status,
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_artifact(cls, raw: Mapping[str, Any]) -> "SettingsRequest":
        _require_keys(
            raw,
            {
                "schema_version",
                "request_id",
                "settings_id",
                "requested_at_utc",
                "previous_settings_id",
                "request_source",
                "request_status",
                "content_hash",
            },
            "settings request",
        )
        if raw.get("schema_version") != 1:
            raise ValueError("unsupported settings request schema_version")
        requested = datetime.fromisoformat(
            str(raw["requested_at_utc"]).replace("Z", "+00:00")
        )
        payload = {
            "settings_id": str(raw["settings_id"]),
            "requested_at_utc": require_aware_utc(requested),
            "previous_settings_id": raw.get("previous_settings_id"),
            "request_source": SettingsRequestSource(str(raw["request_source"])),
            "request_status": SettingsRequestStatus(str(raw["request_status"])),
        }
        identifier = "btsreq1_" + sha256_hex(canonical_json(payload))
        expected_hash = content_hash({"request_id": identifier, **payload})
        if raw.get("request_id") != identifier or raw.get("content_hash") != expected_hash:
            raise ValueError("settings request identity mismatch")
        return cls(request_id=identifier, content_hash=expected_hash, **payload)
