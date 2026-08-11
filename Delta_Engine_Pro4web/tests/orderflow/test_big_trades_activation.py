from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.orderflow.big_trades.activation import (
    ActivationArtifact,
    ActivationBoundaryCollision,
    ActivationHistoryError,
    ActivationReason,
    ActivationResolutionError,
    CalibrationActivationPolicy,
    CalibrationSchedule,
    FixedResearchSelection,
    ScheduleRunArtifact,
    ScheduleRunResult,
    SourceConfirmedSessionTracker,
    resolve_activation_at_boundary,
    schedule_period_id,
    scheduled_boundary_id,
    select_historical_activation,
    validate_activation_history,
)
from src.orderflow.big_trades.constants import FilterMode
from src.orderflow.big_trades.settings import SettingsVersion
from tests.orderflow._big_trades_helpers import fill


UTC = timezone.utc
CAL_OLD = "btcal1_" + "0" * 64
CAL_USER = "btcal1_" + "1" * 64
CAL_SCHEDULED = "btcal1_" + "2" * 64


def _version(*, minimum="5", automatic=False, calibration_id=None):
    return SettingsVersion.create(
        symbol="BTCUSDT",
        venue="BINANCE",
        filter_mode=FilterMode.AUTOMATIC if automatic else FilterMode.MANUAL,
        manual_min_quantity=minimum,
        manual_max_quantity="0",
        automatic_intensity="MEDIUM",
        side_filter="BOTH",
        marker_price_mode="LAST_PRICE",
        calibration_id=calibration_id,
    )


def _activation(second: int, trade_id: int, version: SettingsVersion, *, requested_day: int):
    return ActivationArtifact.create(
        symbol="BTCUSDT",
        venue="BINANCE",
        effective_from_event_time=datetime(2026, 1, 1, 0, 0, second, tzinfo=UTC),
        effective_from_trade_id=trade_id,
        settings_id=version.settings_id,
        calibration_id=version.calibration_id,
        activation_reason=ActivationReason.USER_SETTINGS,
        activation_policy=CalibrationActivationPolicy.MANUAL_ONLY,
        requested_at_utc=datetime(2026, 1, requested_day, tzinfo=UTC),
    )


def test_session_completion_is_triggered_only_by_next_session_first_source_trade() -> None:
    tracker = SourceConfirmedSessionTracker()
    assert tracker.observe(fill(0)) is None
    assert tracker.shutdown() is None
    assert tracker.observe(fill(1)) is None
    transition = tracker.observe(fill(0, base=datetime(2026, 1, 2, tzinfo=UTC)))
    assert transition is not None
    assert transition.previous_session_id == "2026-01-01"
    assert transition.next_session_id == "2026-01-02"
    assert transition.confirmed_by_trade_id == 0


def test_weekly_and_monthly_schedule_boundaries_use_source_sessions() -> None:
    tracker = SourceConfirmedSessionTracker()
    tracker.observe(fill(0, base=datetime(2026, 1, 30, tzinfo=UTC)))
    transition = tracker.observe(fill(0, base=datetime(2026, 2, 3, tzinfo=UTC)))
    assert transition is not None
    assert schedule_period_id(CalibrationSchedule.WEEKLY, "2026-02-03") == "2026-W06"
    assert scheduled_boundary_id(
        transition,
        schedule=CalibrationSchedule.WEEKLY,
        symbol="BTCUSDT",
        venue="BINANCE",
    ).startswith("WEEKLY|2026-W06|")
    assert scheduled_boundary_id(
        transition,
        schedule=CalibrationSchedule.MONTHLY,
        symbol="BTCUSDT",
        venue="BINANCE",
    ).startswith("MONTHLY|2026-02|")
    assert scheduled_boundary_id(
        transition,
        schedule=CalibrationSchedule.MANUAL,
        symbol="BTCUSDT",
        venue="BINANCE",
    ) is None


def test_schedule_run_id_deduplicates_boundary_and_manifest() -> None:
    values = {
        "schedule_boundary_id": "WEEKLY|2026-W06|BTCUSDT|BINANCE|AGGREGATE_TRADES|BTLOGIC-2.0",
        "source_manifest_sha256": "a" * 64,
        "attempted_at_source_event_time": datetime(2026, 2, 3, tzinfo=UTC),
        "candidate_calibration_id": "btcal1_" + "b" * 64,
        "result": ScheduleRunResult.GENERATED_PENDING,
    }
    assert ScheduleRunArtifact.create(**values).run_id == ScheduleRunArtifact.create(**values).run_id


def test_replay_selection_uses_effective_source_key_not_requested_time() -> None:
    first = _activation(0, 10, _version(minimum="5"), requested_day=20)
    second = _activation(10, 20, _version(minimum="20"), requested_day=2)
    selected = select_historical_activation(
        (second, first),
        symbol="BTCUSDT",
        venue="BINANCE",
        cluster_first_time=datetime(2026, 1, 1, 0, 0, 5, tzinfo=UTC),
        cluster_first_trade_id=99,
    )
    assert selected.activation_id == first.activation_id
    assert select_historical_activation(
        (second, first),
        symbol="BTCUSDT",
        venue="BINANCE",
        cluster_first_time=datetime(2026, 1, 1, 0, 0, 10, tzinfo=UTC),
        cluster_first_trade_id=20,
    ).activation_id == second.activation_id


def test_replay_missing_history_fails_closed() -> None:
    with pytest.raises(ActivationHistoryError, match="MISSING"):
        select_historical_activation(
            (),
            symbol="BTCUSDT",
            venue="BINANCE",
            cluster_first_time=datetime(2026, 1, 1, tzinfo=UTC),
            cluster_first_trade_id=1,
        )


def test_same_source_boundary_cannot_hold_two_activations() -> None:
    first = _activation(0, 1, _version(minimum="5"), requested_day=1)
    second = _activation(0, 1, _version(minimum="20"), requested_day=1)
    with pytest.raises(ActivationBoundaryCollision):
        validate_activation_history((first, second))


def test_user_calibration_wins_over_scheduled_candidate_at_same_boundary() -> None:
    active = _version(automatic=True, calibration_id=CAL_OLD)
    pending = _version(minimum="10", automatic=True, calibration_id=CAL_OLD)
    resolved = resolve_activation_at_boundary(
        active_settings=active,
        boundary_trade=fill(100, trade_id=10),
        policy=CalibrationActivationPolicy.SCHEDULED_SESSION_BOUNDARY,
        requested_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
        pending_settings=pending,
        pending_user_calibration_id=CAL_USER,
        scheduled_calibration_id=CAL_SCHEDULED,
        scheduled_reason=ActivationReason.SCHEDULED_WEEKLY,
    )
    assert resolved is not None
    assert resolved.settings.calibration_id == CAL_USER
    assert resolved.activation.activation_reason is ActivationReason.USER_SETTINGS_AND_CALIBRATION
    assert resolved.scheduled_candidate_superseded is True


def test_manual_only_keeps_scheduled_candidate_pending() -> None:
    active = _version(automatic=True, calibration_id=CAL_OLD)
    assert resolve_activation_at_boundary(
        active_settings=active,
        boundary_trade=fill(100, trade_id=10),
        policy=CalibrationActivationPolicy.MANUAL_ONLY,
        requested_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
        scheduled_calibration_id=CAL_SCHEDULED,
        scheduled_reason=ActivationReason.SCHEDULED_WEEKLY,
    ) is None


def test_manual_settings_reject_calibration_activation_conflict() -> None:
    with pytest.raises(ActivationResolutionError, match="MODE_CONFLICT"):
        resolve_activation_at_boundary(
            active_settings=_version(),
            boundary_trade=fill(100, trade_id=10),
            policy=CalibrationActivationPolicy.MANUAL_ONLY,
            requested_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
            pending_user_calibration_id=CAL_USER,
        )


def test_fixed_research_namespace_cannot_write_production_history() -> None:
    selection = FixedResearchSelection(
        "research-1", "bts1_" + "a" * 64, "btcal1_" + "b" * 64
    )
    assert selection.relative_output_path == "research/big_trades/research-1"
    assert selection.production_write_allowed is False
