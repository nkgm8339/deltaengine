"""Big Trades V2 REST application service.

This service owns no order path.  It exposes committed observations, queues
source-boundary settings/calibration requests, and appends human assessments.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping, Optional

from src.database.big_trades_schema import assessment_to_row, settings_history_to_row
from src.database.big_trades_storage import (
    BigTradesBackgroundStorageWriter,
    BigTradesDuckDbStore,
    BigTradesStorageError,
)
from src.orderflow.big_trades.artifacts import BigTradesArtifactRepository
from src.orderflow.big_trades.constants import FilterMode
from src.orderflow.big_trades.models import UserAssessment
from src.orderflow.big_trades.runtime import BigTradesRuntimeStatus, RuntimeRecord
from src.orderflow.big_trades.settings import (
    SettingsRequest,
    SettingsRequestSource,
    SettingsRequestStatus,
    SettingsVersion,
)
from webapp.big_trades_history import (
    BigTradesHistoryService,
    parse_aware_time,
    validate_identifier,
)
from webapp.big_trades_protocol import BigTradesBatcherV2


UTC = timezone.utc


class BigTradesBackendUnavailable(RuntimeError):
    pass


class BigTradesBackend:
    """Synchronous service methods intended to run via ``asyncio.to_thread``."""

    SETTINGS_FIELDS = frozenset(
        {
            "filter_mode",
            "manual_min_quantity",
            "manual_max_quantity",
            "automatic_intensity",
            "side_filter",
            "marker_price_mode",
            "calibration_id",
        }
    )

    def __init__(
        self,
        *,
        enabled: bool,
        symbol: str,
        venue: str,
        quantity_step: Decimal | str,
        store: Optional[BigTradesDuckDbStore] = None,
        writer: Optional[BigTradesBackgroundStorageWriter] = None,
        artifacts: Optional[BigTradesArtifactRepository] = None,
        history: Optional[BigTradesHistoryService] = None,
        batcher: Optional[BigTradesBatcherV2] = None,
        runtime: Any = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.enabled = bool(enabled)
        self.symbol = symbol
        self.venue = venue
        self.quantity_step = Decimal(str(quantity_step))
        self.store = store
        self.writer = writer
        self.artifacts = artifacts
        self.history = history
        self.batcher = batcher
        self.runtime = runtime
        self._now = now
        self.last_error: Optional[str] = None

    @classmethod
    def disabled(cls, *, symbol: str, venue: str, quantity_step: Decimal | str) -> "BigTradesBackend":
        return cls(
            enabled=False,
            symbol=symbol,
            venue=venue,
            quantity_step=quantity_step,
        )

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise BigTradesBackendUnavailable("Big Trades is disabled")
        if self.store is None or self.history is None:
            raise BigTradesBackendUnavailable("Big Trades backend is unavailable")

    def _require_controls(self) -> None:
        self._require_enabled()
        if self.artifacts is None:
            raise BigTradesBackendUnavailable("Big Trades artifact repository is unavailable")

    def _now_utc(self) -> datetime:
        current = self._now()
        if current.tzinfo is None:
            raise ValueError("backend clock must be timezone-aware")
        return current.astimezone(UTC)

    def health(self) -> dict[str, Any]:
        if not self.enabled:
            return {
                "status": BigTradesRuntimeStatus.DISABLED.value,
                "enabled": False,
                "source_identity": {
                    "schema_version": 2,
                    "symbol": self.symbol,
                    "venue": self.venue,
                    "input_mode": "AGGREGATE_TRADES",
                    "logic_version": "BTLOGIC-2.0",
                },
                "last_error": self.last_error,
            }
        storage = self.writer.statistics() if self.writer is not None else {}
        stream = self.batcher.stats_snapshot() if self.batcher is not None else {}
        runtime_status = getattr(self.runtime, "status", None)
        status = getattr(runtime_status, "value", BigTradesRuntimeStatus.STARTING.value)
        if storage.get("parquet_pending", 0):
            status = BigTradesRuntimeStatus.DEGRADED_STORAGE.value
        if stream.get("dropped_records", 0) or stream.get("send_failures", 0):
            status = BigTradesRuntimeStatus.DEGRADED_STORAGE.value
        return {
            "status": status,
            "enabled": True,
            "source_identity": self.history.source_identity if self.history else None,
            "storage": storage,
            "stream": stream,
            "last_error": getattr(self.runtime, "last_error", None) or self.last_error,
        }

    def hydration_snapshot(self, *, event_limit: int = 500, zone_limit: int = 500) -> dict[str, Any]:
        self._require_enabled()
        continuation = (
            self.batcher.continuation()
            if self.batcher is not None
            else {"stream_id": None, "last_admitted_sequence": 0, "dropped_count": 0}
        )
        assert self.history is not None
        event_page = self.history.list_events(limit=event_limit)
        zone_page = self.history.list_zones(limit=zone_limit)
        return {
            "source_identity": self.history.source_identity,
            "continuation": continuation,
            "events": event_page["events"],
            "zones": zone_page["zones"],
            "event_cursor": event_page["next_cursor"],
            "zone_cursor": zone_page["next_cursor"],
        }

    def _active_settings(self) -> Optional[SettingsVersion]:
        if self.artifacts is None:
            return None
        matches = [
            item
            for item in self.artifacts.load_activations()
            if item.symbol == self.symbol
            and item.venue == self.venue
            and item.input_mode == "AGGREGATE_TRADES"
        ]
        if not matches:
            return None
        return self.artifacts.load_settings_version(matches[-1].settings_id)

    def get_settings(self) -> dict[str, Any]:
        self._require_controls()
        assert self.artifacts is not None
        active = self._active_settings()
        pending = self.artifacts.load_pending_settings(
            symbol=self.symbol,
            venue=self.venue,
        )
        history = [
            request.to_artifact()
            for request in self.artifacts.list_settings_requests()
            if self.artifacts.load_settings_version(request.settings_id).symbol == self.symbol
            and self.artifacts.load_settings_version(request.settings_id).venue == self.venue
        ]
        return {
            "active": active.to_artifact() if active is not None else None,
            "pending": (
                {
                    "request": pending[0].to_artifact(),
                    "settings": pending[1].to_artifact(),
                }
                if pending is not None
                else None
            ),
            "history": history,
        }

    def get_settings_history(self) -> dict[str, Any]:
        return {"history": self.get_settings()["history"]}

    @staticmethod
    def _decimal_string(value: Any, name: str) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a Decimal JSON string")
        try:
            parsed = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError(f"{name} must be a Decimal JSON string") from exc
        if not parsed.is_finite():
            raise ValueError(f"{name} must be finite")
        return value

    def _persist_pending_settings(
        self,
        version: SettingsVersion,
        *,
        requested_at: datetime,
        previous_settings_id: Optional[str],
    ) -> SettingsRequest:
        assert self.artifacts is not None and self.store is not None
        prior_pending = self.artifacts.load_pending_settings(
            symbol=self.symbol,
            venue=self.venue,
        )
        request = SettingsRequest.create(
            version,
            requested_at_utc=requested_at,
            previous_settings_id=previous_settings_id,
            request_source=SettingsRequestSource.UI,
            request_status=SettingsRequestStatus.PENDING,
        )
        self.artifacts.write_pending_settings(request, version)
        rows = []
        if prior_pending is not None and prior_pending[0].request_id != request.request_id:
            superseded = prior_pending[0].with_status(SettingsRequestStatus.SUPERSEDED)
            rows.append(settings_history_to_row(superseded, prior_pending[1]))
        rows.append(settings_history_to_row(request, version))
        self.store.insert_rows(
            batch_id="btsettings2_" + request.request_id,
            kind="big_trade_settings",
            table_name="big_trade_settings_history",
            rows=rows,
        )
        return request

    def put_settings(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        self._require_controls()
        if not isinstance(raw, Mapping) or set(raw) != self.SETTINGS_FIELDS:
            raise ValueError("settings fields do not match schema")
        calibration_id = raw.get("calibration_id")
        if calibration_id is not None:
            validate_identifier("calibration", calibration_id)
            assert self.artifacts is not None
            calibration = self.artifacts.load_calibration(calibration_id)
            calibration.validate_identity(
                symbol=self.symbol,
                venue=self.venue,
                input_mode="AGGREGATE_TRADES",
                logic_version="BTLOGIC-2.0",
                quantity_step=self.quantity_step,
            )
        version = SettingsVersion.create(
            symbol=self.symbol,
            venue=self.venue,
            filter_mode=raw["filter_mode"],
            manual_min_quantity=self._decimal_string(
                raw["manual_min_quantity"], "manual_min_quantity"
            ),
            manual_max_quantity=self._decimal_string(
                raw["manual_max_quantity"], "manual_max_quantity"
            ),
            automatic_intensity=raw["automatic_intensity"],
            side_filter=raw["side_filter"],
            marker_price_mode=raw["marker_price_mode"],
            calibration_id=calibration_id,
        )
        active = self._active_settings()
        request = self._persist_pending_settings(
            version,
            requested_at=self._now_utc(),
            previous_settings_id=active.settings_id if active else None,
        )
        return {
            "status": SettingsRequestStatus.PENDING.value,
            "request": request.to_artifact(),
            "settings": version.to_artifact(),
            "activation_boundary": "NEXT_SOURCE_SESSION",
        }

    def list_calibrations(self) -> dict[str, Any]:
        self._require_controls()
        assert self.artifacts is not None
        return {
            "calibrations": [item.to_artifact() for item in self.artifacts.list_calibrations()]
        }

    def calibration_detail(self, calibration_id: str) -> dict[str, Any]:
        self._require_controls()
        validate_identifier("calibration", calibration_id)
        assert self.artifacts is not None
        for item in self.artifacts.list_calibrations():
            if item.calibration_id == calibration_id:
                return {"calibration": item.to_artifact()}
        raise KeyError(calibration_id)

    def activate_calibration(self, calibration_id: str) -> dict[str, Any]:
        self._require_controls()
        validate_identifier("calibration", calibration_id)
        assert self.artifacts is not None
        calibration = next(
            (
                item
                for item in self.artifacts.list_calibrations()
                if item.calibration_id == calibration_id
            ),
            None,
        )
        if calibration is None:
            raise KeyError(calibration_id)
        calibration.validate_identity(
            symbol=self.symbol,
            venue=self.venue,
            input_mode="AGGREGATE_TRADES",
            logic_version="BTLOGIC-2.0",
            quantity_step=self.quantity_step,
        )
        active = self._active_settings()
        if active is None:
            raise ValueError("an active settings version is required")
        if active.filter_mode is not FilterMode.AUTOMATIC:
            raise ValueError("calibration activation requires AUTOMATIC active settings")
        version = active.with_calibration(calibration_id)
        request = self._persist_pending_settings(
            version,
            requested_at=self._now_utc(),
            previous_settings_id=active.settings_id,
        )
        return {
            "status": SettingsRequestStatus.PENDING.value,
            "request_id": request.request_id,
            "settings_id": version.settings_id,
            "calibration_id": calibration_id,
            "activation_boundary": "NEXT_SOURCE_SESSION",
        }

    def list_activations(self) -> dict[str, Any]:
        self._require_controls()
        assert self.artifacts is not None
        activations = [
            item.to_artifact()
            for item in self.artifacts.load_activations()
            if item.symbol == self.symbol and item.venue == self.venue
        ]
        return {"activations": activations}

    def activation_detail(self, activation_id: str) -> dict[str, Any]:
        self._require_controls()
        validate_identifier("activation", activation_id)
        assert self.artifacts is not None
        for item in self.artifacts.load_activations():
            if item.activation_id == activation_id:
                return {"activation": item.to_artifact()}
        raise KeyError(activation_id)

    def create_assessment(self, zone_id: str, raw: Mapping[str, Any]) -> dict[str, Any]:
        self._require_enabled()
        validate_identifier("zone", zone_id)
        expected = {
            "assessment",
            "assessed_against_source_time",
            "user_note",
            "supersedes_assessment_id",
        }
        if not isinstance(raw, Mapping) or set(raw) != expected:
            raise ValueError("assessment fields do not match schema")
        assert self.history is not None and self.store is not None
        self.history._one("big_trade_reaction_zones", "zone_id", zone_id)
        supersedes = raw.get("supersedes_assessment_id")
        if supersedes is not None:
            validate_identifier("assessment", supersedes)
            prior = self.store.fetch_rows(
                "big_trade_user_assessments",
                where="assessment_id = ?",
                parameters=(supersedes,),
                limit=1,
            )
            if not prior:
                raise ValueError("supersedes_assessment_id does not exist")
            if prior[0]["zone_id"] != zone_id:
                raise ValueError("supersedes_assessment_id belongs to another zone")
        assessment = UserAssessment.create(
            zone_id=zone_id,
            assessment=raw["assessment"],
            assessed_at_utc=self._now_utc(),
            assessed_against_source_time=parse_aware_time(
                raw["assessed_against_source_time"],
                "assessed_against_source_time",
            ),
            user_note=raw.get("user_note"),
            supersedes_assessment_id=supersedes,
        )
        inserted = 0
        if self.writer is not None:
            ack = self.writer.submit_user_assessments((assessment,)).result(timeout=10)
            if not ack.success:
                raise BigTradesStorageError(ack.error or ack.error_code or "assessment write failed")
            inserted = int(ack.inserted.get("big_trade_user_assessments", 0))
        else:
            result = self.store.insert_rows(
                batch_id="btassessment2_" + assessment.assessment_id,
                kind="big_trade_user_assessments",
                table_name="big_trade_user_assessments",
                rows=(assessment_to_row(assessment),),
            )
            inserted = int(result.inserted.get("big_trade_user_assessments", 0))
        row = assessment_to_row(assessment)
        if inserted and self.batcher is not None:
            self.batcher.publish(
                (
                    RuntimeRecord(
                        kind="USER_ASSESSMENT",
                        source_event_time=assessment.assessed_at_utc,
                        source_trade_id=None,
                        record_id=assessment.assessment_id,
                        content_hash=assessment.content_hash,
                        payload=row,
                    ),
                )
            )
        return {"assessment": row, "idempotent_duplicate": inserted == 0}
