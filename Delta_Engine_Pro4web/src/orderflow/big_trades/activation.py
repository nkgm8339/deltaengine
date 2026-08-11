"""Source-boundary activation history, schedule detection, and Replay selection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
import re
from typing import Any, Iterable, Mapping, Optional

from .constants import INPUT_MODE_AGGREGATE_TRADES, LOGIC_VERSION, FilterMode
from .ids import canonical_json, content_hash, sha256_hex
from .models import BigTradeFill
from .settings import SettingsVersion
from .time_buckets import epoch_microseconds, require_aware_utc, session_id, source_key


ACTIVATION_SCHEMA_VERSION = 1


def _require_keys(raw: Mapping[str, Any], expected: set[str], name: str) -> None:
    if set(raw) != expected:
        raise ValueError(f"{name} artifact fields do not match schema")


class CalibrationSchedule(str, Enum):
    MANUAL = "MANUAL"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"


class CalibrationActivationPolicy(str, Enum):
    SCHEDULED_SESSION_BOUNDARY = "SCHEDULED_SESSION_BOUNDARY"
    MANUAL_ONLY = "MANUAL_ONLY"


class ReplayCalibrationMode(str, Enum):
    HISTORICAL_ACTIVATION = "HISTORICAL_ACTIVATION"
    FIXED_RESEARCH = "FIXED_RESEARCH"


class ActivationReason(str, Enum):
    PRODUCTION_INITIAL = "PRODUCTION_INITIAL"
    USER_SETTINGS = "USER_SETTINGS"
    USER_CALIBRATION = "USER_CALIBRATION"
    USER_SETTINGS_AND_CALIBRATION = "USER_SETTINGS_AND_CALIBRATION"
    SCHEDULED_WEEKLY = "SCHEDULED_WEEKLY"
    SCHEDULED_MONTHLY = "SCHEDULED_MONTHLY"
    ROLLBACK = "ROLLBACK"


class ScheduleRunResult(str, Enum):
    ACTIVATED = "ACTIVATED"
    GENERATED_PENDING = "GENERATED_PENDING"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    STORAGE_FAILED = "STORAGE_FAILED"
    SUPERSEDED_BY_USER_REQUEST = "SUPERSEDED_BY_USER_REQUEST"


class ActivationHistoryError(RuntimeError):
    pass


class ActivationBoundaryCollision(ActivationHistoryError):
    pass


class ActivationResolutionError(RuntimeError):
    pass


def activation_key(
    *,
    logic_version: str,
    symbol: str,
    venue: str,
    input_mode: str,
    effective_session_id: str,
    effective_from_event_time: datetime,
    effective_from_trade_id: int,
    settings_id: str,
    calibration_id: Optional[str],
    activation_reason: ActivationReason,
    activation_policy: CalibrationActivationPolicy,
) -> str:
    return "|".join(
        (
            "BTA1",
            logic_version,
            symbol,
            venue,
            input_mode,
            effective_session_id,
            str(epoch_microseconds(effective_from_event_time)),
            str(effective_from_trade_id),
            settings_id,
            calibration_id or "null",
            activation_reason.value,
            activation_policy.value,
        )
    )


@dataclass(frozen=True)
class ActivationArtifact:
    activation_id: str
    logic_version: str
    symbol: str
    venue: str
    input_mode: str
    effective_session_id: str
    effective_from_event_time: datetime
    effective_from_trade_id: int
    settings_id: str
    calibration_id: Optional[str]
    activation_reason: ActivationReason
    activation_policy: CalibrationActivationPolicy
    requested_at_utc: datetime
    content_hash: str
    schema_version: int = ACTIVATION_SCHEMA_VERSION

    @classmethod
    def create(
        cls,
        *,
        symbol: str,
        venue: str,
        effective_from_event_time: datetime,
        effective_from_trade_id: int,
        settings_id: str,
        calibration_id: Optional[str],
        activation_reason: ActivationReason | str,
        activation_policy: CalibrationActivationPolicy | str,
        requested_at_utc: datetime,
        input_mode: str = INPUT_MODE_AGGREGATE_TRADES,
        logic_version: str = LOGIC_VERSION,
    ) -> "ActivationArtifact":
        effective_time = require_aware_utc(
            effective_from_event_time, "effective_from_event_time"
        )
        requested = require_aware_utc(requested_at_utc, "requested_at_utc")
        if not isinstance(effective_from_trade_id, int) or isinstance(
            effective_from_trade_id, bool
        ) or effective_from_trade_id < 0:
            raise ValueError("effective_from_trade_id must be a non-negative integer")
        if logic_version != LOGIC_VERSION:
            raise ValueError(f"logic_version must be {LOGIC_VERSION}")
        if input_mode != INPUT_MODE_AGGREGATE_TRADES:
            raise ValueError("only AGGREGATE_TRADES is supported")
        if not symbol or not venue:
            raise ValueError("symbol and venue must be non-empty")
        if not re.fullmatch(r"bts1_[0-9a-f]{64}", settings_id):
            raise ValueError("settings_id has invalid format")
        if calibration_id is not None and not re.fullmatch(
            r"btcal1_[0-9a-f]{64}", calibration_id
        ):
            raise ValueError("calibration_id has invalid format")
        reason = ActivationReason(activation_reason)
        policy = CalibrationActivationPolicy(activation_policy)
        key = activation_key(
            logic_version=logic_version,
            symbol=symbol,
            venue=venue,
            input_mode=input_mode,
            effective_session_id=session_id(effective_time),
            effective_from_event_time=effective_time,
            effective_from_trade_id=effective_from_trade_id,
            settings_id=settings_id,
            calibration_id=calibration_id,
            activation_reason=reason,
            activation_policy=policy,
        )
        identifier = "bta1_" + sha256_hex(key)
        payload = {
            "activation_id": identifier,
            "logic_version": logic_version,
            "symbol": symbol,
            "venue": venue,
            "input_mode": input_mode,
            "effective_session_id": session_id(effective_time),
            "effective_from_event_time": effective_time,
            "effective_from_trade_id": effective_from_trade_id,
            "settings_id": settings_id,
            "calibration_id": calibration_id,
            "activation_reason": reason,
            "activation_policy": policy,
            "requested_at_utc": requested,
        }
        return cls(content_hash=content_hash(payload), **payload)

    @property
    def effective_key(self) -> tuple[int, int]:
        return source_key(self.effective_from_event_time, self.effective_from_trade_id)

    @property
    def identity_key(self) -> tuple[str, str, str, str]:
        return self.logic_version, self.symbol, self.venue, self.input_mode

    def to_artifact(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "activation_id": self.activation_id,
            "logic_version": self.logic_version,
            "symbol": self.symbol,
            "venue": self.venue,
            "input_mode": self.input_mode,
            "effective_session_id": self.effective_session_id,
            "effective_from_event_time": self.effective_from_event_time,
            "effective_from_trade_id": self.effective_from_trade_id,
            "settings_id": self.settings_id,
            "calibration_id": self.calibration_id,
            "activation_reason": self.activation_reason,
            "activation_policy": self.activation_policy,
            "requested_at_utc": self.requested_at_utc,
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_artifact(cls, raw: Mapping[str, Any]) -> "ActivationArtifact":
        _require_keys(
            raw,
            {
                "schema_version",
                "activation_id",
                "logic_version",
                "symbol",
                "venue",
                "input_mode",
                "effective_session_id",
                "effective_from_event_time",
                "effective_from_trade_id",
                "settings_id",
                "calibration_id",
                "activation_reason",
                "activation_policy",
                "requested_at_utc",
                "content_hash",
            },
            "activation",
        )
        if raw.get("schema_version") != ACTIVATION_SCHEMA_VERSION:
            raise ValueError("unsupported activation schema_version")
        expected = cls.create(
            symbol=str(raw["symbol"]),
            venue=str(raw["venue"]),
            input_mode=str(raw["input_mode"]),
            logic_version=str(raw["logic_version"]),
            effective_from_event_time=datetime.fromisoformat(
                str(raw["effective_from_event_time"]).replace("Z", "+00:00")
            ),
            effective_from_trade_id=int(raw["effective_from_trade_id"]),
            settings_id=str(raw["settings_id"]),
            calibration_id=raw.get("calibration_id"),
            activation_reason=str(raw["activation_reason"]),
            activation_policy=str(raw["activation_policy"]),
            requested_at_utc=datetime.fromisoformat(
                str(raw["requested_at_utc"]).replace("Z", "+00:00")
            ),
        )
        if raw.get("effective_session_id") != expected.effective_session_id:
            raise ValueError("activation effective_session_id mismatch")
        if raw.get("activation_id") != expected.activation_id:
            raise ValueError("activation_id mismatch")
        if raw.get("content_hash") != expected.content_hash:
            raise ValueError("activation content_hash mismatch")
        return expected


def validate_activation_history(
    activations: Iterable[ActivationArtifact],
) -> tuple[ActivationArtifact, ...]:
    by_id: dict[str, ActivationArtifact] = {}
    by_boundary: dict[tuple[tuple[str, str, str, str], tuple[int, int]], ActivationArtifact] = {}
    for activation in activations:
        existing_id = by_id.get(activation.activation_id)
        if existing_id is not None and existing_id.content_hash != activation.content_hash:
            raise ActivationHistoryError("activation ID content collision")
        by_id[activation.activation_id] = activation
        boundary = (activation.identity_key, activation.effective_key)
        existing_boundary = by_boundary.get(boundary)
        if existing_boundary is not None and existing_boundary.activation_id != activation.activation_id:
            raise ActivationBoundaryCollision("ACTIVATION_BOUNDARY_COLLISION")
        by_boundary[boundary] = activation
    return tuple(
        sorted(
            by_id.values(),
            key=lambda item: (*item.effective_key, item.activation_id),
        )
    )


def select_historical_activation(
    activations: Iterable[ActivationArtifact],
    *,
    symbol: str,
    venue: str,
    cluster_first_time: datetime,
    cluster_first_trade_id: int,
    input_mode: str = INPUT_MODE_AGGREGATE_TRADES,
    logic_version: str = LOGIC_VERSION,
) -> ActivationArtifact:
    target = source_key(cluster_first_time, cluster_first_trade_id)
    eligible = [
        item
        for item in validate_activation_history(activations)
        if item.identity_key == (logic_version, symbol, venue, input_mode)
        and item.effective_key <= target
    ]
    if not eligible:
        raise ActivationHistoryError("REPLAY_ACTIVATION_HISTORY_MISSING")
    return eligible[-1]


@dataclass(frozen=True)
class SessionTransition:
    previous_session_id: str
    next_session_id: str
    confirmed_by_event_time: datetime
    confirmed_by_trade_id: int


class SourceConfirmedSessionTracker:
    def __init__(self) -> None:
        self._current_session_id: Optional[str] = None

    def observe(self, trade: BigTradeFill) -> Optional[SessionTransition]:
        next_id = trade.session_id
        if self._current_session_id is None:
            self._current_session_id = next_id
            return None
        if next_id == self._current_session_id:
            return None
        if date.fromisoformat(next_id) < date.fromisoformat(self._current_session_id):
            raise ValueError("session_id moved backwards")
        transition = SessionTransition(
            previous_session_id=self._current_session_id,
            next_session_id=next_id,
            confirmed_by_event_time=trade.event_time,
            confirmed_by_trade_id=trade.trade_id,
        )
        self._current_session_id = next_id
        return transition

    def shutdown(self) -> None:
        """A shutdown never confirms the current source session."""

        return None


def schedule_period_id(schedule: CalibrationSchedule | str, session: str) -> str:
    parsed_schedule = CalibrationSchedule(schedule)
    parsed = date.fromisoformat(session)
    if parsed_schedule is CalibrationSchedule.WEEKLY:
        iso_year, iso_week, _ = parsed.isocalendar()
        return f"{iso_year:04d}-W{iso_week:02d}"
    if parsed_schedule is CalibrationSchedule.MONTHLY:
        return f"{parsed.year:04d}-{parsed.month:02d}"
    raise ValueError("MANUAL schedule has no period ID")


def scheduled_boundary_id(
    transition: SessionTransition,
    *,
    schedule: CalibrationSchedule | str,
    symbol: str,
    venue: str,
    input_mode: str = INPUT_MODE_AGGREGATE_TRADES,
    logic_version: str = LOGIC_VERSION,
) -> Optional[str]:
    parsed_schedule = CalibrationSchedule(schedule)
    if parsed_schedule is CalibrationSchedule.MANUAL:
        return None
    previous_period = schedule_period_id(parsed_schedule, transition.previous_session_id)
    next_period = schedule_period_id(parsed_schedule, transition.next_session_id)
    if previous_period == next_period:
        return None
    return "|".join(
        (
            parsed_schedule.value,
            next_period,
            symbol,
            venue,
            input_mode,
            logic_version,
        )
    )


@dataclass(frozen=True)
class ScheduleRunArtifact:
    run_id: str
    schedule_boundary_id: str
    source_manifest_sha256: str
    attempted_at_source_event_time: datetime
    candidate_calibration_id: Optional[str]
    result: ScheduleRunResult
    failure_code: Optional[str]
    content_sha256: str
    schema_version: int = 1

    @classmethod
    def create(
        cls,
        *,
        schedule_boundary_id: str,
        source_manifest_sha256: str,
        attempted_at_source_event_time: datetime,
        candidate_calibration_id: Optional[str],
        result: ScheduleRunResult | str,
        failure_code: Optional[str] = None,
    ) -> "ScheduleRunArtifact":
        attempted = require_aware_utc(attempted_at_source_event_time)
        if not re.fullmatch(r"[0-9a-f]{64}", source_manifest_sha256):
            raise ValueError("source_manifest_sha256 has invalid format")
        if candidate_calibration_id is not None and not re.fullmatch(
            r"btcal1_[0-9a-f]{64}", candidate_calibration_id
        ):
            raise ValueError("candidate_calibration_id has invalid format")
        identifier = schedule_run_id(schedule_boundary_id, source_manifest_sha256)
        payload = {
            "run_id": identifier,
            "schedule_boundary_id": schedule_boundary_id,
            "source_manifest_sha256": source_manifest_sha256,
            "attempted_at_source_event_time": attempted,
            "candidate_calibration_id": candidate_calibration_id,
            "result": ScheduleRunResult(result),
            "failure_code": failure_code,
        }
        return cls(content_sha256=content_hash(payload), **payload)

    def to_artifact(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "schedule_boundary_id": self.schedule_boundary_id,
            "source_manifest_sha256": self.source_manifest_sha256,
            "attempted_at_source_event_time": self.attempted_at_source_event_time,
            "candidate_calibration_id": self.candidate_calibration_id,
            "result": self.result,
            "failure_code": self.failure_code,
            "content_sha256": self.content_sha256,
        }

    @classmethod
    def from_artifact(cls, raw: Mapping[str, Any]) -> "ScheduleRunArtifact":
        _require_keys(
            raw,
            {
                "schema_version",
                "run_id",
                "schedule_boundary_id",
                "source_manifest_sha256",
                "attempted_at_source_event_time",
                "candidate_calibration_id",
                "result",
                "failure_code",
                "content_sha256",
            },
            "schedule run",
        )
        if raw.get("schema_version") != 1:
            raise ValueError("unsupported schedule run schema_version")
        expected = cls.create(
            schedule_boundary_id=str(raw["schedule_boundary_id"]),
            source_manifest_sha256=str(raw["source_manifest_sha256"]),
            attempted_at_source_event_time=datetime.fromisoformat(
                str(raw["attempted_at_source_event_time"]).replace("Z", "+00:00")
            ),
            candidate_calibration_id=raw.get("candidate_calibration_id"),
            result=str(raw["result"]),
            failure_code=raw.get("failure_code"),
        )
        if raw.get("run_id") != expected.run_id:
            raise ValueError("schedule run ID mismatch")
        if raw.get("content_sha256") != expected.content_sha256:
            raise ValueError("schedule run content hash mismatch")
        return expected


@dataclass(frozen=True)
class FixedResearchSelection:
    run_id: str
    settings_id: str
    calibration_id: Optional[str]

    @property
    def relative_output_path(self) -> str:
        allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
        if not self.run_id or any(character not in allowed for character in self.run_id):
            raise ValueError("invalid research run_id")
        return f"research/big_trades/{self.run_id}"

    @property
    def production_write_allowed(self) -> bool:
        return False


@dataclass(frozen=True)
class ResolvedActivation:
    settings: SettingsVersion
    activation: ActivationArtifact
    scheduled_candidate_superseded: bool


def schedule_run_id(schedule_boundary_id: str, source_manifest_sha256: str) -> str:
    return "btrun1_" + sha256_hex(schedule_boundary_id + "|" + source_manifest_sha256)


def resolve_activation_at_boundary(
    *,
    active_settings: SettingsVersion,
    boundary_trade: BigTradeFill,
    policy: CalibrationActivationPolicy | str,
    requested_at_utc: datetime,
    pending_settings: Optional[SettingsVersion] = None,
    pending_user_calibration_id: Optional[str] = None,
    scheduled_calibration_id: Optional[str] = None,
    scheduled_reason: Optional[ActivationReason] = None,
) -> Optional[ResolvedActivation]:
    activation_policy = CalibrationActivationPolicy(policy)
    base = pending_settings or active_settings
    if pending_user_calibration_id and base.filter_mode is FilterMode.MANUAL:
        raise ActivationResolutionError("BT_CALIBRATION_MODE_CONFLICT")

    chosen_calibration = base.calibration_id
    scheduled_superseded = False
    if pending_user_calibration_id:
        chosen_calibration = pending_user_calibration_id
        scheduled_superseded = scheduled_calibration_id is not None
    elif (
        scheduled_calibration_id
        and activation_policy is CalibrationActivationPolicy.SCHEDULED_SESSION_BOUNDARY
        and base.filter_mode is FilterMode.AUTOMATIC
    ):
        chosen_calibration = scheduled_calibration_id
    if base.filter_mode is FilterMode.MANUAL:
        chosen_calibration = None
    derived = base.with_calibration(chosen_calibration)

    if pending_settings and pending_user_calibration_id:
        reason = ActivationReason.USER_SETTINGS_AND_CALIBRATION
    elif pending_user_calibration_id:
        reason = ActivationReason.USER_CALIBRATION
    elif pending_settings:
        reason = ActivationReason.USER_SETTINGS
    elif chosen_calibration == scheduled_calibration_id and scheduled_calibration_id:
        if scheduled_reason not in {
            ActivationReason.SCHEDULED_WEEKLY,
            ActivationReason.SCHEDULED_MONTHLY,
        }:
            raise ActivationResolutionError("scheduled activation reason is required")
        reason = scheduled_reason
    else:
        return None

    activation = ActivationArtifact.create(
        symbol=derived.symbol,
        venue=derived.venue,
        input_mode=derived.input_mode,
        logic_version=derived.logic_version,
        effective_from_event_time=boundary_trade.event_time,
        effective_from_trade_id=boundary_trade.trade_id,
        settings_id=derived.settings_id,
        calibration_id=derived.calibration_id,
        activation_reason=reason,
        activation_policy=activation_policy,
        requested_at_utc=requested_at_utc,
    )
    return ResolvedActivation(derived, activation, scheduled_superseded)
