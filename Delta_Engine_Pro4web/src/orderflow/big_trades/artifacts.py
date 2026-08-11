"""Immutable Big Trades artifacts and fsync-backed atomic repository."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from .activation import (
    ActivationArtifact,
    ActivationBoundaryCollision,
    ActivationHistoryError,
    ActivationReason,
    CalibrationActivationPolicy,
    CalibrationSchedule,
    FixedResearchSelection,
    ReplayCalibrationMode,
    ResolvedActivation,
    ScheduleRunArtifact,
    ScheduleRunResult,
    SessionTransition,
    resolve_activation_at_boundary,
    schedule_run_id,
    scheduled_boundary_id,
    select_historical_activation,
    validate_activation_history,
)
from .calibration import (
    CalibrationStatus,
    SessionQuantityDistribution,
    calibrate,
    decimal_median,
    session_rank,
)
from .constants import (
    AGGREGATION_CANDLE_TIMEFRAME,
    AGGREGATION_WINDOW_MS,
    INPUT_MODE_AGGREGATE_TRADES,
    LOGIC_VERSION,
    QUANTITY_UNIT,
    SESSION_TEMPLATE,
    AutomaticIntensity,
)
from .ids import canonical_json, content_hash, sha256_hex
from .models import BigTradeFill, ExecutionCluster, ZERO
from .settings import SettingsRequest, SettingsRequestStatus, SettingsVersion
from .time_buckets import require_aware_utc, session_end, session_id, session_start


SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9_.-]+$")
SAFE_IDENTIFIERS = {
    "settings": re.compile(r"^bts1_[0-9a-f]{64}$"),
    "settings_request": re.compile(r"^btsreq1_[0-9a-f]{64}$"),
    "calibration": re.compile(r"^btcal1_[0-9a-f]{64}$"),
    "activation": re.compile(r"^bta1_[0-9a-f]{64}$"),
    "schedule_run": re.compile(r"^btrun1_[0-9a-f]{64}$"),
}


class ArtifactError(RuntimeError):
    pass


class ArtifactIntegrityError(ArtifactError):
    pass


class ArtifactCollisionError(ArtifactError):
    pass


class SessionCompletionStatus(str, Enum):
    SOURCE_CONFIRMED_COMPLETE = "SOURCE_CONFIRMED_COMPLETE"
    SOURCE_CONFIRMED_EXCLUDED_RESTART_TRUNCATED = (
        "SOURCE_CONFIRMED_EXCLUDED_RESTART_TRUNCATED"
    )
    SOURCE_CONFIRMED_EXCLUDED_SOURCE_GAP = "SOURCE_CONFIRMED_EXCLUDED_SOURCE_GAP"


SESSION_COMPLETION_TRIGGER = "NEXT_SESSION_FIRST_ACCEPTED_TRADE"


def _require_keys(raw: Mapping[str, Any], expected: set[str], name: str) -> None:
    if set(raw) != expected:
        raise ArtifactIntegrityError(f"{name} artifact fields do not match schema")


@dataclass(frozen=True)
class SessionStatsArtifact:
    logic_version: str
    symbol: str
    venue: str
    input_mode: str
    session_id: str
    session_start: datetime
    session_end: datetime
    completion_status: SessionCompletionStatus
    completion_trigger: str
    confirmed_by_session_id: str
    confirmed_by_event_time: datetime
    confirmed_by_trade_id: int
    cluster_count: int
    rank_2_quantity: Optional[Decimal]
    rank_9_quantity: Optional[Decimal]
    rank_20_quantity: Optional[Decimal]
    top_quantities: tuple[Decimal, ...]
    valid_1m_bars: int
    invalid_1m_bars: int
    invalid_trades: int
    source_gap_count: int
    session_ntr_median: Optional[Decimal]
    source_first_time: datetime
    source_last_time: datetime
    content_hash: str
    schema_version: int = 1

    @property
    def calibration_valid(self) -> bool:
        return self.completion_status is SessionCompletionStatus.SOURCE_CONFIRMED_COMPLETE

    def to_artifact(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "logic_version": self.logic_version,
            "symbol": self.symbol,
            "venue": self.venue,
            "input_mode": self.input_mode,
            "session_id": self.session_id,
            "session_start": self.session_start,
            "session_end": self.session_end,
            "completion_status": self.completion_status,
            "completion_trigger": self.completion_trigger,
            "confirmed_by_session_id": self.confirmed_by_session_id,
            "confirmed_by_event_time": self.confirmed_by_event_time,
            "confirmed_by_trade_id": self.confirmed_by_trade_id,
            "cluster_count": self.cluster_count,
            "rank_2_quantity": self.rank_2_quantity,
            "rank_9_quantity": self.rank_9_quantity,
            "rank_20_quantity": self.rank_20_quantity,
            "top_quantities": self.top_quantities,
            "valid_1m_bars": self.valid_1m_bars,
            "invalid_1m_bars": self.invalid_1m_bars,
            "invalid_trades": self.invalid_trades,
            "source_gap_count": self.source_gap_count,
            "session_ntr_median": self.session_ntr_median,
            "source_first_time": self.source_first_time,
            "source_last_time": self.source_last_time,
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_artifact(cls, raw: Mapping[str, Any]) -> "SessionStatsArtifact":
        _require_keys(
            raw,
            {
                "schema_version",
                "logic_version",
                "symbol",
                "venue",
                "input_mode",
                "session_id",
                "session_start",
                "session_end",
                "completion_status",
                "completion_trigger",
                "confirmed_by_session_id",
                "confirmed_by_event_time",
                "confirmed_by_trade_id",
                "cluster_count",
                "rank_2_quantity",
                "rank_9_quantity",
                "rank_20_quantity",
                "top_quantities",
                "valid_1m_bars",
                "invalid_1m_bars",
                "invalid_trades",
                "source_gap_count",
                "session_ntr_median",
                "source_first_time",
                "source_last_time",
                "content_hash",
            },
            "session stats",
        )
        if raw.get("schema_version") != 1:
            raise ArtifactIntegrityError("unsupported session stats schema_version")
        payload = {
            "logic_version": str(raw["logic_version"]),
            "symbol": str(raw["symbol"]),
            "venue": str(raw["venue"]),
            "input_mode": str(raw["input_mode"]),
            "session_id": str(raw["session_id"]),
            "session_start": datetime.fromisoformat(
                str(raw["session_start"]).replace("Z", "+00:00")
            ),
            "session_end": datetime.fromisoformat(
                str(raw["session_end"]).replace("Z", "+00:00")
            ),
            "completion_status": SessionCompletionStatus(str(raw["completion_status"])),
            "completion_trigger": str(raw["completion_trigger"]),
            "confirmed_by_session_id": str(raw["confirmed_by_session_id"]),
            "confirmed_by_event_time": datetime.fromisoformat(
                str(raw["confirmed_by_event_time"]).replace("Z", "+00:00")
            ),
            "confirmed_by_trade_id": int(raw["confirmed_by_trade_id"]),
            "cluster_count": int(raw["cluster_count"]),
            "rank_2_quantity": (
                Decimal(str(raw["rank_2_quantity"]))
                if raw.get("rank_2_quantity") is not None
                else None
            ),
            "rank_9_quantity": (
                Decimal(str(raw["rank_9_quantity"]))
                if raw.get("rank_9_quantity") is not None
                else None
            ),
            "rank_20_quantity": (
                Decimal(str(raw["rank_20_quantity"]))
                if raw.get("rank_20_quantity") is not None
                else None
            ),
            "top_quantities": tuple(Decimal(str(value)) for value in raw["top_quantities"]),
            "valid_1m_bars": int(raw["valid_1m_bars"]),
            "invalid_1m_bars": int(raw["invalid_1m_bars"]),
            "invalid_trades": int(raw["invalid_trades"]),
            "source_gap_count": int(raw["source_gap_count"]),
            "session_ntr_median": (
                Decimal(str(raw["session_ntr_median"]))
                if raw.get("session_ntr_median") is not None
                else None
            ),
            "source_first_time": datetime.fromisoformat(
                str(raw["source_first_time"]).replace("Z", "+00:00")
            ),
            "source_last_time": datetime.fromisoformat(
                str(raw["source_last_time"]).replace("Z", "+00:00")
            ),
        }
        expected_hash = content_hash(payload)
        if raw.get("content_hash") != expected_hash:
            raise ArtifactIntegrityError("session stats content_hash mismatch")
        expected_start = session_start(payload["session_id"])
        expected_end = session_end(payload["session_id"])
        if payload["session_start"] != expected_start or payload["session_end"] != expected_end:
            raise ArtifactIntegrityError("session stats UTC boundary mismatch")
        if payload["completion_trigger"] != SESSION_COMPLETION_TRIGGER:
            raise ArtifactIntegrityError("session stats completion trigger mismatch")
        if session_id(payload["confirmed_by_event_time"]) != payload["confirmed_by_session_id"]:
            raise ArtifactIntegrityError("session stats confirmation source mismatch")
        top = payload["top_quantities"]
        if len(top) > 20 or tuple(sorted(top, reverse=True)) != top:
            raise ArtifactIntegrityError("session stats top quantities are invalid")
        if payload["cluster_count"] < len(top):
            raise ArtifactIntegrityError("session stats cluster count is invalid")
        if (
            payload["rank_2_quantity"] != session_rank(top, 2)
            or payload["rank_9_quantity"] != session_rank(top, 9)
            or payload["rank_20_quantity"] != session_rank(top, 20)
        ):
            raise ArtifactIntegrityError("session stats ranks are invalid")
        counts = (
            payload["valid_1m_bars"],
            payload["invalid_1m_bars"],
            payload["invalid_trades"],
            payload["source_gap_count"],
        )
        if any(value < 0 for value in counts) or sum(counts[:2]) > 1_440:
            raise ArtifactIntegrityError("session stats counters are invalid")
        return cls(content_hash=expected_hash, **payload)


class SessionStatsBuilder:
    """Accumulates one open session but cannot complete it without next-session source."""

    def __init__(
        self,
        *,
        session_id: str,
        symbol: str,
        venue: str,
        input_mode: str = INPUT_MODE_AGGREGATE_TRADES,
        logic_version: str = LOGIC_VERSION,
    ) -> None:
        session_start(session_id)
        if input_mode != INPUT_MODE_AGGREGATE_TRADES or logic_version != LOGIC_VERSION:
            raise ValueError("session stats identity is unsupported")
        self.session_id = session_id
        self.symbol = symbol
        self.venue = venue
        self.input_mode = input_mode
        self.logic_version = logic_version
        self._cluster_quantities: list[Decimal] = []
        self._ntr_values: list[Decimal] = []
        self._valid_1m_bars = 0
        self._invalid_1m_bars = 0
        self._invalid_trades = 0
        self._source_gap_count = 0
        self._restart_truncated = False
        self._source_first_time: Optional[datetime] = None
        self._source_last_time: Optional[datetime] = None

    def observe_trade(self, trade: BigTradeFill) -> None:
        if (
            trade.session_id != self.session_id
            or trade.symbol != self.symbol
            or trade.venue != self.venue
        ):
            raise ValueError("trade does not belong to open session stats")
        if self._source_last_time is not None and trade.event_time < self._source_last_time:
            raise ValueError("session stats trades must be source ordered")
        self._source_first_time = self._source_first_time or trade.event_time
        self._source_last_time = trade.event_time

    def observe_cluster(self, cluster: ExecutionCluster) -> None:
        if (
            cluster.session_id != self.session_id
            or cluster.symbol != self.symbol
            or cluster.venue != self.venue
            or cluster.input_mode != self.input_mode
            or cluster.logic_version != self.logic_version
        ):
            raise ValueError("cluster does not belong to open session stats")
        self._cluster_quantities.append(cluster.aggregate_quantity)

    def observe_candle_ntr(self, value: Optional[Decimal]) -> None:
        if self._valid_1m_bars + self._invalid_1m_bars >= 1_440:
            raise ValueError("session cannot contain more than 1440 one-minute candles")
        if value is None:
            self._invalid_1m_bars += 1
            return
        parsed = Decimal(str(value))
        if not parsed.is_finite() or parsed < ZERO:
            self._invalid_1m_bars += 1
            return
        self._ntr_values.append(parsed)
        self._valid_1m_bars += 1

    def record_invalid_trade(self) -> None:
        self._invalid_trades += 1

    def mark_source_gap(self) -> None:
        self._source_gap_count += 1

    def mark_restart_truncated(self) -> None:
        self._restart_truncated = True

    def finalize(
        self,
        *,
        confirmed_by_session_id: str,
        confirmed_by_event_time: datetime,
        confirmed_by_trade_id: int,
    ) -> SessionStatsArtifact:
        confirmed_time = require_aware_utc(confirmed_by_event_time)
        if confirmed_by_session_id == self.session_id:
            raise ValueError("session completion requires a different next session")
        if confirmed_time < session_end(self.session_id):
            raise ValueError("confirmation source time must be after the old session")
        if session_id(confirmed_time) != confirmed_by_session_id:
            raise ValueError("confirmation session ID does not match source time")
        if self._source_first_time is None or self._source_last_time is None:
            raise ValueError("cannot finalize session stats without accepted source trades")
        if self._source_gap_count:
            status = SessionCompletionStatus.SOURCE_CONFIRMED_EXCLUDED_SOURCE_GAP
        elif self._restart_truncated:
            status = SessionCompletionStatus.SOURCE_CONFIRMED_EXCLUDED_RESTART_TRUNCATED
        else:
            status = SessionCompletionStatus.SOURCE_CONFIRMED_COMPLETE
        top = tuple(sorted(self._cluster_quantities, reverse=True)[:20])
        payload = {
            "logic_version": self.logic_version,
            "symbol": self.symbol,
            "venue": self.venue,
            "input_mode": self.input_mode,
            "session_id": self.session_id,
            "session_start": session_start(self.session_id),
            "session_end": session_end(self.session_id),
            "completion_status": status,
            "completion_trigger": SESSION_COMPLETION_TRIGGER,
            "confirmed_by_session_id": confirmed_by_session_id,
            "confirmed_by_event_time": confirmed_time,
            "confirmed_by_trade_id": confirmed_by_trade_id,
            "cluster_count": len(self._cluster_quantities),
            "rank_2_quantity": session_rank(top, 2),
            "rank_9_quantity": session_rank(top, 9),
            "rank_20_quantity": session_rank(top, 20),
            "top_quantities": top,
            "valid_1m_bars": self._valid_1m_bars,
            "invalid_1m_bars": self._invalid_1m_bars,
            "invalid_trades": self._invalid_trades,
            "source_gap_count": self._source_gap_count,
            "session_ntr_median": (
                decimal_median(self._ntr_values)
                if self._valid_1m_bars >= 1_368
                else None
            ),
            "source_first_time": self._source_first_time,
            "source_last_time": self._source_last_time,
        }
        return SessionStatsArtifact(content_hash=content_hash(payload), **payload)


@dataclass(frozen=True)
class CalibrationArtifact:
    calibration_id: str
    logic_version: str
    symbol: str
    venue: str
    input_mode: str
    session_template: str
    quantity_unit: str
    quantity_step: Decimal
    history_start_session: str
    history_end_session: str
    valid_sessions_low: int
    valid_sessions_medium: int
    valid_sessions_strong: int
    base_low: Decimal
    base_medium: Decimal
    base_strong: Decimal
    baseline_volatility: Optional[Decimal]
    recent_volatility: Optional[Decimal]
    volatility_factor: Decimal
    volatility_status: str
    auto_low: Decimal
    auto_medium: Decimal
    auto_strong: Decimal
    aggregation_window_ms: int
    aggregation_candle_timeframe: str
    target_events: Mapping[str, int]
    source_manifest_sha256: str
    created_at_utc: datetime
    content_sha256: str
    schema_version: int = 1

    @classmethod
    def create(
        cls,
        session_stats: Iterable[SessionStatsArtifact],
        *,
        symbol: str,
        venue: str,
        quantity_step: Decimal | str,
        as_of_session: str,
        created_at_utc: datetime,
        input_mode: str = INPUT_MODE_AGGREGATE_TRADES,
        logic_version: str = LOGIC_VERSION,
    ) -> "CalibrationArtifact":
        step = Decimal(str(quantity_step))
        if not step.is_finite() or step <= ZERO:
            raise ValueError("quantity_step must be finite and positive")
        session_start(as_of_session)
        unique: dict[str, SessionStatsArtifact] = {}
        for item in session_stats:
            existing = unique.get(item.session_id)
            if existing is not None and existing.content_hash != item.content_hash:
                raise ArtifactCollisionError("SESSION_STATS_COLLISION")
            unique[item.session_id] = item
        eligible = sorted(
            (
                item
                for item in unique.values()
                if item.calibration_valid
                and item.session_id < as_of_session
                and item.symbol == symbol
                and item.venue == venue
                and item.input_mode == input_mode
                and item.logic_version == logic_version
            ),
            key=lambda item: item.session_id,
        )[-20:]
        distributions = tuple(
            SessionQuantityDistribution(
                item.session_id,
                item.top_quantities,
                item.session_ntr_median,
            )
            for item in eligible
        )
        result = calibrate(distributions, quantity_step=step)
        if result.status is not CalibrationStatus.VALID:
            raise ValueError("calibration has insufficient valid history")
        assert result.base_thresholds is not None and result.thresholds is not None
        manifest = sha256_hex(
            canonical_json(
                [
                    {"session_id": item.session_id, "content_hash": item.content_hash}
                    for item in eligible
                ]
            )
        )
        identity = {
            "logic_version": logic_version,
            "symbol": symbol,
            "venue": venue,
            "input_mode": input_mode,
            "session_template": SESSION_TEMPLATE,
            "quantity_unit": QUANTITY_UNIT,
            "quantity_step": step,
            "history_start_session": eligible[0].session_id,
            "history_end_session": eligible[-1].session_id,
            "valid_sessions_low": result.valid_session_counts[AutomaticIntensity.LOW],
            "valid_sessions_medium": result.valid_session_counts[AutomaticIntensity.MEDIUM],
            "valid_sessions_strong": result.valid_session_counts[AutomaticIntensity.STRONG],
            "base_low": result.base_thresholds[AutomaticIntensity.LOW],
            "base_medium": result.base_thresholds[AutomaticIntensity.MEDIUM],
            "base_strong": result.base_thresholds[AutomaticIntensity.STRONG],
            "baseline_volatility": result.baseline_volatility,
            "recent_volatility": result.recent_volatility,
            "volatility_factor": result.volatility_factor,
            "volatility_status": result.volatility_status,
            "auto_low": result.thresholds[AutomaticIntensity.LOW],
            "auto_medium": result.thresholds[AutomaticIntensity.MEDIUM],
            "auto_strong": result.thresholds[AutomaticIntensity.STRONG],
            "aggregation_window_ms": AGGREGATION_WINDOW_MS,
            "aggregation_candle_timeframe": AGGREGATION_CANDLE_TIMEFRAME,
            "target_events": {"LOW": 20, "MEDIUM": 9, "STRONG": 2},
            "source_manifest_sha256": manifest,
        }
        digest = sha256_hex(canonical_json(identity))
        artifact = cls(
            calibration_id="btcal1_" + digest,
            created_at_utc=require_aware_utc(created_at_utc),
            content_sha256=digest,
            **identity,
        )
        return artifact

    @property
    def thresholds(self) -> Mapping[AutomaticIntensity, Decimal]:
        return {
            AutomaticIntensity.LOW: self.auto_low,
            AutomaticIntensity.MEDIUM: self.auto_medium,
            AutomaticIntensity.STRONG: self.auto_strong,
        }

    def validate_identity(
        self,
        *,
        symbol: str,
        venue: str,
        quantity_step: Decimal | str,
        input_mode: str = INPUT_MODE_AGGREGATE_TRADES,
        logic_version: str = LOGIC_VERSION,
    ) -> None:
        if self.symbol != symbol or self.venue != venue:
            raise ArtifactIntegrityError("calibration symbol or venue mismatch")
        if self.logic_version != logic_version or self.input_mode != input_mode:
            raise ArtifactIntegrityError("calibration logic or input mode mismatch")
        if self.quantity_step != Decimal(str(quantity_step)):
            raise ArtifactIntegrityError("calibration quantity step mismatch")
        if (
            self.session_template != SESSION_TEMPLATE
            or self.quantity_unit != QUANTITY_UNIT
            or self.aggregation_window_ms != AGGREGATION_WINDOW_MS
            or self.aggregation_candle_timeframe != AGGREGATION_CANDLE_TIMEFRAME
            or dict(self.target_events) != {"LOW": 20, "MEDIUM": 9, "STRONG": 2}
        ):
            raise ArtifactIntegrityError("calibration logic constants mismatch")
        if not self.auto_low < self.auto_medium < self.auto_strong:
            raise ArtifactIntegrityError("calibration thresholds are not strictly increasing")

    def to_artifact(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "logic_version": self.logic_version,
            "calibration_id": self.calibration_id,
            "symbol": self.symbol,
            "venue": self.venue,
            "input_mode": self.input_mode,
            "session_template": self.session_template,
            "quantity_unit": self.quantity_unit,
            "quantity_step": self.quantity_step,
            "history_start_session": self.history_start_session,
            "history_end_session": self.history_end_session,
            "valid_sessions_low": self.valid_sessions_low,
            "valid_sessions_medium": self.valid_sessions_medium,
            "valid_sessions_strong": self.valid_sessions_strong,
            "base_low": self.base_low,
            "base_medium": self.base_medium,
            "base_strong": self.base_strong,
            "baseline_volatility": self.baseline_volatility,
            "recent_volatility": self.recent_volatility,
            "volatility_factor": self.volatility_factor,
            "volatility_status": self.volatility_status,
            "auto_low": self.auto_low,
            "auto_medium": self.auto_medium,
            "auto_strong": self.auto_strong,
            "aggregation_window_ms": self.aggregation_window_ms,
            "aggregation_candle_timeframe": self.aggregation_candle_timeframe,
            "target_events": self.target_events,
            "source_manifest_sha256": self.source_manifest_sha256,
            "created_at_utc": self.created_at_utc,
            "content_sha256": self.content_sha256,
        }

    @classmethod
    def from_artifact(cls, raw: Mapping[str, Any]) -> "CalibrationArtifact":
        _require_keys(
            raw,
            {
                "schema_version",
                "logic_version",
                "calibration_id",
                "symbol",
                "venue",
                "input_mode",
                "session_template",
                "quantity_unit",
                "quantity_step",
                "history_start_session",
                "history_end_session",
                "valid_sessions_low",
                "valid_sessions_medium",
                "valid_sessions_strong",
                "base_low",
                "base_medium",
                "base_strong",
                "baseline_volatility",
                "recent_volatility",
                "volatility_factor",
                "volatility_status",
                "auto_low",
                "auto_medium",
                "auto_strong",
                "aggregation_window_ms",
                "aggregation_candle_timeframe",
                "target_events",
                "source_manifest_sha256",
                "created_at_utc",
                "content_sha256",
            },
            "calibration",
        )
        if raw.get("schema_version") != 1:
            raise ArtifactIntegrityError("unsupported calibration schema_version")
        identity = {
            key: raw[key]
            for key in (
                "logic_version",
                "symbol",
                "venue",
                "input_mode",
                "session_template",
                "quantity_unit",
                "quantity_step",
                "history_start_session",
                "history_end_session",
                "valid_sessions_low",
                "valid_sessions_medium",
                "valid_sessions_strong",
                "base_low",
                "base_medium",
                "base_strong",
                "baseline_volatility",
                "recent_volatility",
                "volatility_factor",
                "volatility_status",
                "auto_low",
                "auto_medium",
                "auto_strong",
                "aggregation_window_ms",
                "aggregation_candle_timeframe",
                "target_events",
                "source_manifest_sha256",
            )
        }
        digest = sha256_hex(canonical_json(identity))
        if raw.get("calibration_id") != "btcal1_" + digest:
            raise ArtifactIntegrityError("calibration_id mismatch")
        if raw.get("content_sha256") != digest:
            raise ArtifactIntegrityError("calibration content_sha256 mismatch")
        artifact = cls(
            calibration_id=str(raw["calibration_id"]),
            logic_version=str(raw["logic_version"]),
            symbol=str(raw["symbol"]),
            venue=str(raw["venue"]),
            input_mode=str(raw["input_mode"]),
            session_template=str(raw["session_template"]),
            quantity_unit=str(raw["quantity_unit"]),
            quantity_step=Decimal(str(raw["quantity_step"])),
            history_start_session=str(raw["history_start_session"]),
            history_end_session=str(raw["history_end_session"]),
            valid_sessions_low=int(raw["valid_sessions_low"]),
            valid_sessions_medium=int(raw["valid_sessions_medium"]),
            valid_sessions_strong=int(raw["valid_sessions_strong"]),
            base_low=Decimal(str(raw["base_low"])),
            base_medium=Decimal(str(raw["base_medium"])),
            base_strong=Decimal(str(raw["base_strong"])),
            baseline_volatility=(
                Decimal(str(raw["baseline_volatility"]))
                if raw.get("baseline_volatility") is not None
                else None
            ),
            recent_volatility=(
                Decimal(str(raw["recent_volatility"]))
                if raw.get("recent_volatility") is not None
                else None
            ),
            volatility_factor=Decimal(str(raw["volatility_factor"])),
            volatility_status=str(raw["volatility_status"]),
            auto_low=Decimal(str(raw["auto_low"])),
            auto_medium=Decimal(str(raw["auto_medium"])),
            auto_strong=Decimal(str(raw["auto_strong"])),
            aggregation_window_ms=int(raw["aggregation_window_ms"]),
            aggregation_candle_timeframe=str(raw["aggregation_candle_timeframe"]),
            target_events={str(key): int(value) for key, value in raw["target_events"].items()},
            source_manifest_sha256=str(raw["source_manifest_sha256"]),
            created_at_utc=datetime.fromisoformat(
                str(raw["created_at_utc"]).replace("Z", "+00:00")
            ),
            content_sha256=digest,
        )
        artifact.validate_identity(
            symbol=artifact.symbol,
            venue=artifact.venue,
            input_mode=artifact.input_mode,
            logic_version=artifact.logic_version,
            quantity_step=artifact.quantity_step,
        )
        if artifact.history_start_session > artifact.history_end_session:
            raise ArtifactIntegrityError("calibration history range is invalid")
        if min(
            artifact.valid_sessions_low,
            artifact.valid_sessions_medium,
            artifact.valid_sessions_strong,
        ) < 10:
            raise ArtifactIntegrityError("calibration valid session count is insufficient")
        if not re.fullmatch(r"[0-9a-f]{64}", artifact.source_manifest_sha256):
            raise ArtifactIntegrityError("calibration source manifest is invalid")
        return artifact


@dataclass(frozen=True)
class ActivationCommitResult:
    artifact_path: Path
    committed: bool
    pointer_cache_updated: bool
    pointer_cache_error: Optional[str]


@dataclass(frozen=True)
class ReplayResolvedSnapshot:
    mode: ReplayCalibrationMode
    settings: SettingsVersion
    calibration: Optional[CalibrationArtifact]
    activation: Optional[ActivationArtifact]
    research_output_path: Optional[Path]

    @property
    def production_write_allowed(self) -> bool:
        return self.mode is ReplayCalibrationMode.HISTORICAL_ACTIVATION


class BigTradesArtifactRepository:
    def __init__(self, data_root: Path | str) -> None:
        self.data_root = Path(data_root)
        self.calibration_root = self.data_root / "calibration" / "big_trades"
        self.settings_root = self.data_root / "settings" / "big_trades"

    @staticmethod
    def _component(value: str) -> str:
        if not SAFE_COMPONENT.fullmatch(value):
            raise ValueError(f"unsafe artifact path component: {value!r}")
        return value

    @staticmethod
    def _identifier(kind: str, value: str) -> str:
        if not SAFE_IDENTIFIERS[kind].fullmatch(value):
            raise ValueError(f"invalid {kind} ID")
        return value

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ArtifactIntegrityError(f"cannot read artifact {path}") from exc
        if not isinstance(loaded, dict):
            raise ArtifactIntegrityError(f"artifact must be an object: {path}")
        return loaded

    @staticmethod
    def _atomic_replace(path: Path, payload: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = (canonical_json(payload) + "\n").encode("utf-8")
        temporary: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=path.parent, prefix=".tmp-bt2-", delete=False
            ) as handle:
                temporary = Path(handle.name)
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            read_back = temporary.read_bytes()
            if read_back != encoded:
                raise ArtifactIntegrityError("artifact temporary read-back mismatch")
            os.replace(temporary, path)
            temporary = None
        finally:
            if temporary is not None:
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass

    def _write_immutable(
        self,
        path: Path,
        payload: Mapping[str, Any],
        *,
        hash_field: str,
        ignored_idempotency_fields: tuple[str, ...] = (),
    ) -> Path:
        if path.exists():
            existing = self._read_json(path)
            if existing.get(hash_field) == payload.get(hash_field):
                existing_authoritative = {
                    key: value
                    for key, value in existing.items()
                    if key not in ignored_idempotency_fields
                }
                payload_authoritative = {
                    key: value
                    for key, value in payload.items()
                    if key not in ignored_idempotency_fields
                }
                if canonical_json(existing_authoritative) == canonical_json(
                    payload_authoritative
                ):
                    return path
            raise ArtifactCollisionError(f"immutable artifact collision: {path}")
        self._atomic_replace(path, payload)
        stored = self._read_json(path)
        if canonical_json(stored) != canonical_json(payload):
            raise ArtifactIntegrityError(f"artifact final read-back mismatch: {path}")
        return path

    def write_settings_version(self, version: SettingsVersion) -> Path:
        identifier = self._identifier("settings", version.settings_id)
        return self._write_immutable(
            self.settings_root / "versions" / f"{identifier}.json",
            version.to_artifact(),
            hash_field="content_sha256",
        )

    def load_settings_version(self, settings_id: str) -> SettingsVersion:
        identifier = self._identifier("settings", settings_id)
        raw = self._read_json(self.settings_root / "versions" / f"{identifier}.json")
        return SettingsVersion.from_artifact(raw)

    def list_settings_versions(self) -> tuple[SettingsVersion, ...]:
        directory = self.settings_root / "versions"
        if not directory.exists():
            return ()
        versions = []
        for path in sorted(directory.glob("*.json")):
            if not SAFE_IDENTIFIERS["settings"].fullmatch(path.stem):
                raise ArtifactIntegrityError(f"invalid settings artifact filename: {path.name}")
            version = self.load_settings_version(path.stem)
            if version.settings_id != path.stem:
                raise ArtifactIntegrityError("settings filename and ID mismatch")
            versions.append(version)
        return tuple(sorted(versions, key=lambda item: item.settings_id))

    def list_settings_requests(self) -> tuple[SettingsRequest, ...]:
        directory = self.settings_root / "history"
        if not directory.exists():
            return ()
        requests = []
        for path in sorted(directory.glob("*.json")):
            if not SAFE_IDENTIFIERS["settings_request"].fullmatch(path.stem):
                raise ArtifactIntegrityError(
                    f"invalid settings request artifact filename: {path.name}"
                )
            request = SettingsRequest.from_artifact(self._read_json(path))
            if request.request_id != path.stem:
                raise ArtifactIntegrityError("settings request filename and ID mismatch")
            requests.append(request)
        return tuple(
            sorted(requests, key=lambda item: (item.requested_at_utc, item.request_id))
        )

    def load_pending_settings(
        self,
        *,
        symbol: str,
        venue: str,
        input_mode: str = INPUT_MODE_AGGREGATE_TRADES,
    ) -> tuple[SettingsRequest, SettingsVersion] | None:
        key = "_".join(
            self._component(value) for value in (symbol, venue, input_mode)
        )
        path = self.settings_root / "pending" / f"{key}.json"
        if not path.exists():
            return None
        request = SettingsRequest.from_artifact(self._read_json(path))
        if request.request_status is not SettingsRequestStatus.PENDING:
            raise ArtifactIntegrityError("pending settings pointer is not PENDING")
        version = self.load_settings_version(request.settings_id)
        if (
            version.symbol != symbol
            or version.venue != venue
            or version.input_mode != input_mode
        ):
            raise ArtifactIntegrityError("pending settings identity mismatch")
        return request, version

    def write_pending_settings(self, request: SettingsRequest, version: SettingsVersion) -> Path:
        if request.settings_id != version.settings_id:
            raise ArtifactIntegrityError("pending request settings mismatch")
        self.write_settings_version(version)
        key = "_".join(
            self._component(value)
            for value in (version.symbol, version.venue, version.input_mode)
        )
        path = self.settings_root / "pending" / f"{key}.json"
        if path.exists():
            previous = SettingsRequest.from_artifact(self._read_json(path))
            if (
                previous.request_id != request.request_id
                and previous.request_status is SettingsRequestStatus.PENDING
            ):
                self.write_settings_request_history(
                    previous.with_status(SettingsRequestStatus.SUPERSEDED)
                )
        self.write_settings_request_history(request)
        self._atomic_replace(path, request.to_artifact())
        return path

    def write_settings_request_history(self, request: SettingsRequest) -> Path:
        if not SAFE_IDENTIFIERS["settings_request"].fullmatch(request.request_id):
            raise ValueError("invalid settings request ID")
        return self._write_immutable(
            self.settings_root / "history" / f"{request.request_id}.json",
            request.to_artifact(),
            hash_field="content_hash",
        )

    def write_session_stats(self, stats: SessionStatsArtifact) -> Path:
        components = tuple(
            self._component(value)
            for value in (
                stats.logic_version,
                stats.venue,
                stats.symbol,
                stats.input_mode,
                stats.session_id,
            )
        )
        path = (
            self.calibration_root
            / "session_stats"
            / components[0]
            / components[1]
            / components[2]
            / components[3]
            / f"{components[4]}.json"
        )
        return self._write_immutable(path, stats.to_artifact(), hash_field="content_hash")

    def load_session_stats(self, path: Path | str) -> SessionStatsArtifact:
        return SessionStatsArtifact.from_artifact(self._read_json(Path(path)))

    def list_session_stats(
        self,
        *,
        logic_version: str,
        venue: str,
        symbol: str,
        input_mode: str = INPUT_MODE_AGGREGATE_TRADES,
    ) -> tuple[SessionStatsArtifact, ...]:
        directory = (
            self.calibration_root
            / "session_stats"
            / self._component(logic_version)
            / self._component(venue)
            / self._component(symbol)
            / self._component(input_mode)
        )
        if not directory.exists():
            return ()
        return tuple(
            sorted(
                (self.load_session_stats(path) for path in directory.glob("*.json")),
                key=lambda item: item.session_id,
            )
        )

    def write_calibration(self, artifact: CalibrationArtifact) -> Path:
        identifier = self._identifier("calibration", artifact.calibration_id)
        return self._write_immutable(
            self.calibration_root / "calibrations" / f"{identifier}.json",
            artifact.to_artifact(),
            hash_field="content_sha256",
            ignored_idempotency_fields=("created_at_utc",),
        )

    def load_calibration(self, calibration_id: str) -> CalibrationArtifact:
        identifier = self._identifier("calibration", calibration_id)
        raw = self._read_json(
            self.calibration_root / "calibrations" / f"{identifier}.json"
        )
        return CalibrationArtifact.from_artifact(raw)

    def list_calibrations(self) -> tuple[CalibrationArtifact, ...]:
        directory = self.calibration_root / "calibrations"
        if not directory.exists():
            return ()
        calibrations = []
        for path in sorted(directory.glob("*.json")):
            if not SAFE_IDENTIFIERS["calibration"].fullmatch(path.stem):
                raise ArtifactIntegrityError(
                    f"invalid calibration artifact filename: {path.name}"
                )
            calibration = self.load_calibration(path.stem)
            if calibration.calibration_id != path.stem:
                raise ArtifactIntegrityError("calibration filename and ID mismatch")
            calibrations.append(calibration)
        return tuple(
            sorted(
                calibrations,
                key=lambda item: (item.history_end_session, item.calibration_id),
            )
        )

    def write_schedule_run(self, run: ScheduleRunArtifact) -> Path:
        identifier = self._identifier("schedule_run", run.run_id)
        return self._write_immutable(
            self.calibration_root / "schedule_runs" / f"{identifier}.json",
            run.to_artifact(),
            hash_field="content_sha256",
        )

    def load_schedule_run(self, run_id: str) -> ScheduleRunArtifact:
        identifier = self._identifier("schedule_run", run_id)
        return ScheduleRunArtifact.from_artifact(
            self._read_json(
                self.calibration_root / "schedule_runs" / f"{identifier}.json"
            )
        )

    def load_activations(self) -> tuple[ActivationArtifact, ...]:
        directory = self.settings_root / "activations"
        if not directory.exists():
            return ()
        activations: list[ActivationArtifact] = []
        for path in sorted(directory.glob("*.json")):
            if not SAFE_IDENTIFIERS["activation"].fullmatch(path.stem):
                raise ArtifactIntegrityError(f"invalid activation artifact filename: {path.name}")
            activation = ActivationArtifact.from_artifact(self._read_json(path))
            if activation.activation_id != path.stem:
                raise ArtifactIntegrityError("activation filename and ID mismatch")
            activations.append(activation)
        return validate_activation_history(activations)

    def commit_activation(
        self,
        activation: ActivationArtifact,
        *,
        expected_quantity_step: Decimal | str | None = None,
    ) -> ActivationCommitResult:
        settings = self.load_settings_version(activation.settings_id)
        if (
            settings.symbol != activation.symbol
            or settings.venue != activation.venue
            or settings.input_mode != activation.input_mode
            or settings.logic_version != activation.logic_version
            or settings.calibration_id != activation.calibration_id
        ):
            raise ArtifactIntegrityError("activation and settings identity mismatch")
        if activation.calibration_id is not None:
            if expected_quantity_step is None:
                raise ArtifactIntegrityError(
                    "expected quantity step is required for calibration activation"
                )
            calibration = self.load_calibration(activation.calibration_id)
            calibration.validate_identity(
                symbol=activation.symbol,
                venue=activation.venue,
                quantity_step=expected_quantity_step,
                input_mode=activation.input_mode,
                logic_version=activation.logic_version,
            )
        for existing in self.load_activations():
            if (
                existing.identity_key == activation.identity_key
                and existing.effective_key == activation.effective_key
                and existing.activation_id != activation.activation_id
            ):
                raise ActivationBoundaryCollision("ACTIVATION_BOUNDARY_COLLISION")
        identifier = self._identifier("activation", activation.activation_id)
        artifact_path = self._write_immutable(
            self.settings_root / "activations" / f"{identifier}.json",
            activation.to_artifact(),
            hash_field="content_hash",
        )

        key = "_".join(
            self._component(value)
            for value in (activation.symbol, activation.venue, activation.input_mode)
        )
        pointer = {
            "activation_id": activation.activation_id,
            "settings_id": activation.settings_id,
            "calibration_id": activation.calibration_id,
            "effective_session_id": activation.effective_session_id,
            "effective_from_event_time": activation.effective_from_event_time,
            "effective_from_trade_id": activation.effective_from_trade_id,
            "content_hash": content_hash(activation.to_artifact()),
        }
        try:
            self._atomic_replace(self.settings_root / "active" / f"{key}.json", pointer)
        except OSError as exc:
            return ActivationCommitResult(artifact_path, True, False, str(exc))
        return ActivationCommitResult(artifact_path, True, True, None)

    def rebuild_active_pointer(
        self,
        *,
        symbol: str,
        venue: str,
        input_mode: str = INPUT_MODE_AGGREGATE_TRADES,
    ) -> Optional[Path]:
        matches = [
            item
            for item in self.load_activations()
            if item.symbol == symbol and item.venue == venue and item.input_mode == input_mode
        ]
        if not matches:
            return None
        latest = matches[-1]
        key = "_".join(self._component(value) for value in (symbol, venue, input_mode))
        pointer = {
            "activation_id": latest.activation_id,
            "settings_id": latest.settings_id,
            "calibration_id": latest.calibration_id,
            "effective_session_id": latest.effective_session_id,
            "effective_from_event_time": latest.effective_from_event_time,
            "effective_from_trade_id": latest.effective_from_trade_id,
            "content_hash": content_hash(latest.to_artifact()),
        }
        path = self.settings_root / "active" / f"{key}.json"
        self._atomic_replace(path, pointer)
        return path

    def resolve_historical_replay_snapshot(
        self,
        *,
        symbol: str,
        venue: str,
        cluster_first_time: datetime,
        cluster_first_trade_id: int,
        expected_quantity_step: Decimal | str,
        input_mode: str = INPUT_MODE_AGGREGATE_TRADES,
        logic_version: str = LOGIC_VERSION,
    ) -> ReplayResolvedSnapshot:
        try:
            activation = select_historical_activation(
                self.load_activations(),
                symbol=symbol,
                venue=venue,
                input_mode=input_mode,
                logic_version=logic_version,
                cluster_first_time=cluster_first_time,
                cluster_first_trade_id=cluster_first_trade_id,
            )
        except ActivationHistoryError as exc:
            code = (
                "REPLAY_ACTIVATION_HISTORY_MISSING"
                if "MISSING" in str(exc)
                else "REPLAY_ACTIVATION_HISTORY_INVALID"
            )
            raise ArtifactIntegrityError(code) from exc
        try:
            settings = self.load_settings_version(activation.settings_id)
        except (OSError, ValueError, ArtifactError) as exc:
            raise ArtifactIntegrityError("REPLAY_ACTIVATION_HISTORY_INVALID") from exc
        if (
            settings.symbol != symbol
            or settings.venue != venue
            or settings.input_mode != input_mode
            or settings.logic_version != logic_version
            or settings.calibration_id != activation.calibration_id
        ):
            raise ArtifactIntegrityError("REPLAY_ACTIVATION_HISTORY_INVALID")
        calibration = None
        if activation.calibration_id is not None:
            calibration = self.load_calibration(activation.calibration_id)
            calibration.validate_identity(
                symbol=symbol,
                venue=venue,
                input_mode=input_mode,
                logic_version=logic_version,
                quantity_step=expected_quantity_step,
            )
        return ReplayResolvedSnapshot(
            mode=ReplayCalibrationMode.HISTORICAL_ACTIVATION,
            settings=settings,
            calibration=calibration,
            activation=activation,
            research_output_path=None,
        )

    def resolve_fixed_research_snapshot(
        self,
        selection: FixedResearchSelection,
        *,
        expected_quantity_step: Decimal | str,
    ) -> ReplayResolvedSnapshot:
        settings = self.load_settings_version(selection.settings_id)
        if settings.calibration_id != selection.calibration_id:
            raise ArtifactIntegrityError("FIXED_RESEARCH settings/calibration mismatch")
        calibration = None
        if selection.calibration_id is not None:
            calibration = self.load_calibration(selection.calibration_id)
            calibration.validate_identity(
                symbol=settings.symbol,
                venue=settings.venue,
                input_mode=settings.input_mode,
                logic_version=settings.logic_version,
                quantity_step=expected_quantity_step,
            )
        output = self.data_root / selection.relative_output_path
        return ReplayResolvedSnapshot(
            mode=ReplayCalibrationMode.FIXED_RESEARCH,
            settings=settings,
            calibration=calibration,
            activation=None,
            research_output_path=output,
        )


@dataclass(frozen=True)
class ScheduledCalibrationExecution:
    run: ScheduleRunArtifact
    candidate: Optional[CalibrationArtifact]
    resolved_activation: Optional[ResolvedActivation]
    reused_run: bool = False


def _stats_source_manifest(stats: Iterable[SessionStatsArtifact]) -> str:
    ordered = sorted(stats, key=lambda item: item.session_id)
    return sha256_hex(
        canonical_json(
            [
                {"session_id": item.session_id, "content_hash": item.content_hash}
                for item in ordered
            ]
        )
    )


def execute_scheduled_calibration(
    repository: BigTradesArtifactRepository,
    *,
    transition: SessionTransition,
    schedule: CalibrationSchedule | str,
    policy: CalibrationActivationPolicy | str,
    active_settings: SettingsVersion,
    boundary_trade: BigTradeFill,
    quantity_step: Decimal | str,
    pending_settings: Optional[SettingsVersion] = None,
    pending_user_calibration_id: Optional[str] = None,
) -> Optional[ScheduledCalibrationExecution]:
    """Run one deduplicated source-confirmed schedule boundary.

    Only already durable session summary artifacts are read. Failures create a
    terminal run artifact and leave the active activation ledger untouched.
    """

    parsed_schedule = CalibrationSchedule(schedule)
    activation_policy = CalibrationActivationPolicy(policy)
    boundary_id = scheduled_boundary_id(
        transition,
        schedule=parsed_schedule,
        symbol=active_settings.symbol,
        venue=active_settings.venue,
        input_mode=active_settings.input_mode,
        logic_version=active_settings.logic_version,
    )
    if boundary_id is None:
        return None
    persisted = repository.list_session_stats(
        logic_version=active_settings.logic_version,
        venue=active_settings.venue,
        symbol=active_settings.symbol,
        input_mode=active_settings.input_mode,
    )
    completed_before_boundary = tuple(
        item for item in persisted if item.session_id < transition.next_session_id
    )
    calibration_population = tuple(
        item for item in completed_before_boundary if item.calibration_valid
    )[-20:]
    manifest = _stats_source_manifest(calibration_population)
    expected_run_id = schedule_run_id(boundary_id, manifest)
    run_path = repository.calibration_root / "schedule_runs" / f"{expected_run_id}.json"
    if run_path.exists():
        return ScheduledCalibrationExecution(
            repository.load_schedule_run(expected_run_id), None, None, True
        )

    if not any(
        item.session_id == transition.previous_session_id
        for item in completed_before_boundary
    ):
        run = ScheduleRunArtifact.create(
            schedule_boundary_id=boundary_id,
            source_manifest_sha256=manifest,
            attempted_at_source_event_time=boundary_trade.event_time,
            candidate_calibration_id=None,
            result=ScheduleRunResult.STORAGE_FAILED,
            failure_code="SESSION_STATS_NOT_DURABLE",
        )
        repository.write_schedule_run(run)
        return ScheduledCalibrationExecution(run, None, None)

    try:
        candidate = CalibrationArtifact.create(
            completed_before_boundary,
            symbol=active_settings.symbol,
            venue=active_settings.venue,
            input_mode=active_settings.input_mode,
            logic_version=active_settings.logic_version,
            quantity_step=quantity_step,
            as_of_session=transition.next_session_id,
            created_at_utc=boundary_trade.event_time,
        )
        repository.write_calibration(candidate)
    except ValueError as exc:
        run = ScheduleRunArtifact.create(
            schedule_boundary_id=boundary_id,
            source_manifest_sha256=manifest,
            attempted_at_source_event_time=boundary_trade.event_time,
            candidate_calibration_id=None,
            result=ScheduleRunResult.VALIDATION_FAILED,
            failure_code=type(exc).__name__,
        )
        repository.write_schedule_run(run)
        return ScheduledCalibrationExecution(run, None, None)
    except ArtifactError as exc:
        run = ScheduleRunArtifact.create(
            schedule_boundary_id=boundary_id,
            source_manifest_sha256=manifest,
            attempted_at_source_event_time=boundary_trade.event_time,
            candidate_calibration_id=None,
            result=ScheduleRunResult.STORAGE_FAILED,
            failure_code=type(exc).__name__,
        )
        repository.write_schedule_run(run)
        return ScheduledCalibrationExecution(run, None, None)

    reason = (
        ActivationReason.SCHEDULED_WEEKLY
        if parsed_schedule is CalibrationSchedule.WEEKLY
        else ActivationReason.SCHEDULED_MONTHLY
    )
    resolved = resolve_activation_at_boundary(
        active_settings=active_settings,
        boundary_trade=boundary_trade,
        policy=activation_policy,
        requested_at_utc=boundary_trade.event_time,
        pending_settings=pending_settings,
        pending_user_calibration_id=pending_user_calibration_id,
        scheduled_calibration_id=candidate.calibration_id,
        scheduled_reason=reason,
    )
    if resolved is None:
        run_result = ScheduleRunResult.GENERATED_PENDING
    else:
        try:
            repository.write_settings_version(resolved.settings)
            repository.commit_activation(
                resolved.activation,
                expected_quantity_step=quantity_step,
            )
        except ArtifactError as exc:
            run = ScheduleRunArtifact.create(
                schedule_boundary_id=boundary_id,
                source_manifest_sha256=manifest,
                attempted_at_source_event_time=boundary_trade.event_time,
                candidate_calibration_id=candidate.calibration_id,
                result=ScheduleRunResult.STORAGE_FAILED,
                failure_code=type(exc).__name__,
            )
            repository.write_schedule_run(run)
            return ScheduledCalibrationExecution(run, candidate, None)
        if resolved.settings.calibration_id == candidate.calibration_id:
            run_result = ScheduleRunResult.ACTIVATED
        else:
            run_result = ScheduleRunResult.SUPERSEDED_BY_USER_REQUEST

    run = ScheduleRunArtifact.create(
        schedule_boundary_id=boundary_id,
        source_manifest_sha256=manifest,
        attempted_at_source_event_time=boundary_trade.event_time,
        candidate_calibration_id=candidate.calibration_id,
        result=run_result,
    )
    repository.write_schedule_run(run)
    return ScheduledCalibrationExecution(run, candidate, resolved)
