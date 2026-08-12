"""Strict configuration and calibration gating for the independent Hook layer."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import yaml

from .models import CalibrationStatus, HookCandidate, HookEvent, HookThreshold
from .registry import HOOK_REGISTRY, require_hook


_CAMPAIGN_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")


class HookConfigError(ValueError):
    pass


def _strict_keys(raw: Mapping[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise HookConfigError(f"{path} unknown keys: {unknown}")


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HookConfigError(f"{path} must be a mapping")
    return value


def _positive_int(value: Any, path: str, *, minimum: int = 1) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise HookConfigError(f"{path} must be an integer >= {minimum}")
    return value


@dataclass(frozen=True)
class CaptureSettings:
    campaign_id: str
    root: Path
    full_capture_days: int
    liquidation_capture_days: int


@dataclass(frozen=True)
class JournalSettings:
    queue_depth: int
    compression: str
    compression_level: int
    flush_interval_sec: int
    min_free_bytes: int


@dataclass(frozen=True)
class HookStorageSettings:
    enabled: bool
    root: Path
    queue_depth: int
    batch_size: int
    flush_interval_sec: int


@dataclass(frozen=True)
class HookObserverConfig:
    enabled: bool
    capture: CaptureSettings
    journal: JournalSettings
    storage: HookStorageSettings
    thresholds_path: Path
    playbooks_path: Path
    config_hash: str


def load_hook_observer_config(path: str | Path) -> HookObserverConfig:
    source = Path(path)
    raw_text = source.read_text(encoding="utf-8")
    raw = _mapping(yaml.safe_load(raw_text), "root")
    _strict_keys(
        raw,
        {"schema_version", "enabled", "capture", "journal", "storage", "thresholds_path", "playbooks_path"},
        "root",
    )
    if raw.get("schema_version") != 1:
        raise HookConfigError("schema_version must be 1")
    if not isinstance(raw.get("enabled"), bool):
        raise HookConfigError("enabled must be boolean")

    capture = _mapping(raw.get("capture"), "capture")
    _strict_keys(
        capture,
        {"campaign_id", "root", "full_capture_days", "liquidation_capture_days"},
        "capture",
    )
    campaign_id = capture.get("campaign_id")
    if not isinstance(campaign_id, str) or not _CAMPAIGN_RE.fullmatch(campaign_id):
        raise HookConfigError("capture.campaign_id is invalid")

    journal = _mapping(raw.get("journal"), "journal")
    _strict_keys(
        journal,
        {"queue_depth", "compression", "compression_level", "flush_interval_sec", "min_free_bytes"},
        "journal",
    )
    compression = journal.get("compression")
    if compression not in {"gzip", "xz"}:
        raise HookConfigError("journal.compression must be gzip or xz")
    compression_level = _positive_int(
        journal.get("compression_level"), "journal.compression_level"
    )
    if compression_level > 9:
        raise HookConfigError("journal.compression_level must be <= 9")

    storage = _mapping(raw.get("storage"), "storage")
    _strict_keys(
        storage,
        {"enabled", "root", "queue_depth", "batch_size", "flush_interval_sec"},
        "storage",
    )
    if not isinstance(storage.get("enabled"), bool):
        raise HookConfigError("storage.enabled must be boolean")

    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return HookObserverConfig(
        enabled=raw["enabled"],
        capture=CaptureSettings(
            campaign_id=campaign_id,
            root=Path(str(capture.get("root", ""))),
            full_capture_days=_positive_int(
                capture.get("full_capture_days"), "capture.full_capture_days"
            ),
            liquidation_capture_days=_positive_int(
                capture.get("liquidation_capture_days"),
                "capture.liquidation_capture_days",
            ),
        ),
        journal=JournalSettings(
            queue_depth=_positive_int(
                journal.get("queue_depth"), "journal.queue_depth"
            ),
            compression=compression,
            compression_level=compression_level,
            flush_interval_sec=_positive_int(
                journal.get("flush_interval_sec"), "journal.flush_interval_sec"
            ),
            min_free_bytes=_positive_int(
                journal.get("min_free_bytes"), "journal.min_free_bytes"
            ),
        ),
        storage=HookStorageSettings(
            enabled=storage["enabled"],
            root=Path(str(storage.get("root", ""))),
            queue_depth=_positive_int(
                storage.get("queue_depth"), "storage.queue_depth"
            ),
            batch_size=_positive_int(
                storage.get("batch_size"), "storage.batch_size"
            ),
            flush_interval_sec=_positive_int(
                storage.get("flush_interval_sec"), "storage.flush_interval_sec"
            ),
        ),
        thresholds_path=Path(str(raw.get("thresholds_path", ""))),
        playbooks_path=Path(str(raw.get("playbooks_path", ""))),
        config_hash=digest,
    )


class ThresholdBook:
    """Fail-closed threshold lookup. Missing/provisional entries never fire."""

    def __init__(
        self,
        thresholds: Mapping[str, HookThreshold],
        *,
        config_hash: str,
        default_status: CalibrationStatus = CalibrationStatus.UNCALIBRATED,
    ) -> None:
        self._thresholds = MappingProxyType(dict(thresholds))
        self.config_hash = config_hash
        self.default_status = default_status
        self.suppressed_uncalibrated = 0
        self.suppressed_metric_mismatch = 0
        self.suppressed_threshold = 0
        self.suppressed_quality = 0
        self.suppressed_manifest_mismatch = 0

    @classmethod
    def load(cls, path: str | Path) -> "ThresholdBook":
        source = Path(path)
        raw_text = source.read_text(encoding="utf-8")
        raw = _mapping(yaml.safe_load(raw_text), "thresholds root")
        _strict_keys(raw, {"schema_version", "default_status", "thresholds"}, "thresholds root")
        if raw.get("schema_version") != 1:
            raise HookConfigError("threshold schema_version must be 1")
        try:
            default_status = CalibrationStatus(str(raw.get("default_status")))
        except ValueError as exc:
            raise HookConfigError("invalid default_status") from exc
        entries = _mapping(raw.get("thresholds"), "thresholds")
        parsed: dict[str, HookThreshold] = {}
        for hook_id, value in entries.items():
            require_hook(hook_id)
            row = _mapping(value, f"thresholds.{hook_id}")
            _strict_keys(
                row,
                {
                    "metric", "operator", "quantile", "value", "status",
                    "input_manifest_sha256", "sample_count", "valid_days",
                },
                f"thresholds.{hook_id}",
            )
            try:
                status = CalibrationStatus(str(row.get("status")))
                parsed[hook_id] = HookThreshold(
                    hook_id=hook_id,
                    metric_name=str(row.get("metric", "")),
                    operator=str(row.get("operator", "")),
                    quantile=(
                        Decimal(str(row["quantile"]))
                        if row.get("quantile") is not None else None
                    ),
                    value=(
                        Decimal(str(row["value"]))
                        if row.get("value") is not None else None
                    ),
                    status=status,
                    input_manifest_sha256=row.get("input_manifest_sha256"),
                    sample_count=int(row.get("sample_count", 0)),
                    valid_days=int(row.get("valid_days", 0)),
                )
            except (TypeError, ValueError, ArithmeticError) as exc:
                raise HookConfigError(f"invalid threshold {hook_id}: {exc}") from exc
        canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return cls(parsed, config_hash=digest, default_status=default_status)

    def threshold(self, hook_id: str) -> HookThreshold | None:
        require_hook(hook_id)
        return self._thresholds.get(hook_id)

    def status(self, hook_id: str) -> CalibrationStatus:
        threshold = self.threshold(hook_id)
        return threshold.status if threshold is not None else self.default_status

    def evaluate(
        self,
        candidate: HookCandidate,
        *,
        detector_version: str,
        input_manifest_hash: str | None = None,
    ) -> HookEvent | None:
        threshold = self.threshold(candidate.hook_id)
        if threshold is None or not threshold.allows_fire:
            self.suppressed_uncalibrated += 1
            return None
        if (
            input_manifest_hash is not None
            and threshold.input_manifest_sha256 != input_manifest_hash
        ):
            self.suppressed_manifest_mismatch += 1
            return None
        if candidate.quality_status.value != "VALID":
            self.suppressed_quality += 1
            return None
        if candidate.metric_name != threshold.metric_name:
            self.suppressed_metric_mismatch += 1
            return None
        if not threshold.matches(candidate):
            self.suppressed_threshold += 1
            return None
        return HookEvent.from_candidate(
            candidate,
            threshold,
            detector_version=detector_version,
            config_hash=self.config_hash,
            input_manifest_hash=input_manifest_hash,
        )

    def calibrated_hook_ids(self) -> tuple[str, ...]:
        return tuple(
            hook_id
            for hook_id in HOOK_REGISTRY
            if self.status(hook_id) is CalibrationStatus.CALIBRATED
        )


def validate_observe_only_playbooks(path: str | Path) -> str:
    """Reject any Stage 2/3 playbook configuration that can request execution."""

    source = Path(path)
    raw_text = source.read_text(encoding="utf-8")
    raw = _mapping(yaml.safe_load(raw_text), "playbooks root")
    _strict_keys(
        raw,
        {"schema_version", "mode", "execution_enabled", "playbooks"},
        "playbooks root",
    )
    if raw.get("schema_version") != 1:
        raise HookConfigError("playbook schema_version must be 1")
    if raw.get("mode") != "OBSERVE":
        raise HookConfigError("playbook mode must be OBSERVE")
    if raw.get("execution_enabled") is not False:
        raise HookConfigError("playbook execution_enabled must be false")
    _mapping(raw.get("playbooks"), "playbooks")
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
