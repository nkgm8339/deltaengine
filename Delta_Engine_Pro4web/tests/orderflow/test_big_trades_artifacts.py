from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.orderflow.big_trades.activation import (
    ActivationArtifact,
    ActivationReason,
    CalibrationActivationPolicy,
    CalibrationSchedule,
    FixedResearchSelection,
    ScheduleRunResult,
    SessionTransition,
)
from src.orderflow.big_trades.artifacts import (
    ArtifactCollisionError,
    ArtifactIntegrityError,
    BigTradesArtifactRepository,
    CalibrationArtifact,
    SessionCompletionStatus,
    SessionStatsBuilder,
    execute_scheduled_calibration,
)
from src.orderflow.big_trades.constants import ClusterCloseReason, FilterMode
from src.orderflow.big_trades.models import ExecutionCluster
from src.orderflow.big_trades.settings import (
    SettingsRequest,
    SettingsRequestSource,
    SettingsVersion,
)
from tests.orderflow._big_trades_helpers import fill, settings


UTC = timezone.utc
CAL_OLD = "btcal1_" + "0" * 64


def _settings_version(*, minimum: str = "5", automatic: bool = False, calibration_id=None):
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


def _session_stats(day: int, *, gap: bool = False, scale: int = 1):
    base = datetime(2026, 1, day, tzinfo=UTC)
    builder = SessionStatsBuilder(
        session_id=base.date().isoformat(), symbol="BTCUSDT", venue="BINANCE"
    )
    configured = settings(minimum="0")
    for index in range(1, 31):
        trade = fill(index, quantity=str(index * scale), trade_id=index, base=base)
        builder.observe_trade(trade)
        builder.observe_cluster(
            ExecutionCluster((trade,), configured, ClusterCloseReason.STREAM_ENDED)
        )
    if gap:
        builder.mark_source_gap()
    next_day = base + timedelta(days=1)
    return builder.finalize(
        confirmed_by_session_id=next_day.date().isoformat(),
        confirmed_by_event_time=next_day,
        confirmed_by_trade_id=999,
    )


def _calibration(*, created_at: datetime | None = None):
    return CalibrationArtifact.create(
        (_session_stats(day) for day in range(1, 21)),
        symbol="BTCUSDT",
        venue="BINANCE",
        quantity_step="0.001",
        as_of_session="2026-01-21",
        created_at_utc=created_at or datetime(2026, 1, 21, tzinfo=UTC),
    )


def test_settings_id_is_deterministic_and_manual_discards_calibration() -> None:
    first = _settings_version(calibration_id="unused")
    second = _settings_version()
    assert first == second
    assert first.settings_id.startswith("bts1_")
    assert first.calibration_id is None


def test_settings_version_and_pending_pointer_are_atomic(tmp_path) -> None:
    repository = BigTradesArtifactRepository(tmp_path)
    version = _settings_version()
    request = SettingsRequest.create(
        version,
        requested_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
        previous_settings_id=None,
        request_source=SettingsRequestSource.CONFIG,
    )
    version_path = repository.write_settings_version(version)
    pending_path = repository.write_pending_settings(request, version)
    assert repository.load_settings_version(version.settings_id) == version
    assert json.loads(pending_path.read_text(encoding="utf-8"))["settings_id"] == version.settings_id
    assert not list(version_path.parent.glob(".tmp-bt2-*"))


def test_new_pending_settings_preserves_superseded_request_history(tmp_path) -> None:
    repository = BigTradesArtifactRepository(tmp_path)
    first_version = _settings_version(minimum="5")
    second_version = _settings_version(minimum="20")
    first = SettingsRequest.create(
        first_version,
        requested_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
        previous_settings_id=None,
        request_source=SettingsRequestSource.UI,
    )
    second = SettingsRequest.create(
        second_version,
        requested_at_utc=datetime(2026, 1, 2, tzinfo=UTC),
        previous_settings_id=first_version.settings_id,
        request_source=SettingsRequestSource.UI,
    )
    repository.write_pending_settings(first, first_version)
    repository.write_pending_settings(second, second_version)
    history = list((repository.settings_root / "history").glob("*.json"))
    statuses = {
        json.loads(path.read_text(encoding="utf-8"))["request_status"] for path in history
    }
    assert statuses == {"PENDING", "SUPERSEDED"}


def test_session_stats_require_next_session_source_and_gap_is_excluded() -> None:
    complete = _session_stats(1)
    excluded = _session_stats(2, gap=True)
    assert complete.completion_status is SessionCompletionStatus.SOURCE_CONFIRMED_COMPLETE
    assert complete.rank_2_quantity == Decimal("29")
    assert complete.rank_9_quantity == Decimal("22")
    assert complete.rank_20_quantity == Decimal("11")
    assert excluded.completion_status is SessionCompletionStatus.SOURCE_CONFIRMED_EXCLUDED_SOURCE_GAP
    assert excluded.calibration_valid is False


def test_restart_truncated_session_is_persisted_but_excluded() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    builder = SessionStatsBuilder(
        session_id="2026-01-01", symbol="BTCUSDT", venue="BINANCE"
    )
    builder.observe_trade(fill(0, base=base))
    builder.mark_restart_truncated()
    stats = builder.finalize(
        confirmed_by_session_id="2026-01-02",
        confirmed_by_event_time=datetime(2026, 1, 2, tzinfo=UTC),
        confirmed_by_trade_id=1,
    )
    assert stats.completion_status is SessionCompletionStatus.SOURCE_CONFIRMED_EXCLUDED_RESTART_TRUNCATED
    assert stats.calibration_valid is False


def test_session_stats_artifact_round_trip_and_collision(tmp_path) -> None:
    repository = BigTradesArtifactRepository(tmp_path)
    stats = _session_stats(1)
    path = repository.write_session_stats(stats)
    assert repository.load_session_stats(path) == stats
    assert repository.write_session_stats(stats) == path
    tampered = json.loads(path.read_text(encoding="utf-8"))
    tampered["cluster_count"] += 1
    path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ArtifactCollisionError):
        repository.write_session_stats(stats)


def test_session_candle_coverage_boundary_controls_only_volatility() -> None:
    def build(valid_bars: int):
        base = datetime(2026, 1, 1, tzinfo=UTC)
        builder = SessionStatsBuilder(
            session_id="2026-01-01", symbol="BTCUSDT", venue="BINANCE"
        )
        builder.observe_trade(fill(0, base=base))
        for _ in range(valid_bars):
            builder.observe_candle_ntr(Decimal("0.01"))
        return builder.finalize(
            confirmed_by_session_id="2026-01-02",
            confirmed_by_event_time=datetime(2026, 1, 2, tzinfo=UTC),
            confirmed_by_trade_id=1,
        )

    assert build(1_367).session_ntr_median is None
    assert build(1_368).session_ntr_median == Decimal("0.01")


def test_calibration_artifact_is_deterministic_and_created_time_is_non_identity(tmp_path) -> None:
    first = _calibration(created_at=datetime(2026, 1, 21, tzinfo=UTC))
    second = _calibration(created_at=datetime(2026, 2, 1, tzinfo=UTC))
    assert first.calibration_id == second.calibration_id
    assert first.content_sha256 == second.content_sha256
    assert first.auto_low == Decimal("11")
    assert first.auto_medium == Decimal("22")
    assert first.auto_strong == Decimal("29")

    repository = BigTradesArtifactRepository(tmp_path)
    path = repository.write_calibration(first)
    assert repository.write_calibration(second) == path
    assert repository.load_calibration(first.calibration_id).calibration_id == first.calibration_id


def test_calibration_validation_rejects_wrong_symbol_logic_and_step() -> None:
    artifact = _calibration()
    with pytest.raises(ArtifactIntegrityError, match="symbol"):
        artifact.validate_identity(symbol="ETHUSDT", venue="BINANCE", quantity_step="0.001")
    with pytest.raises(ArtifactIntegrityError, match="logic"):
        artifact.validate_identity(
            symbol="BTCUSDT",
            venue="BINANCE",
            quantity_step="0.001",
            logic_version="BTLOGIC-9.0",
        )
    with pytest.raises(ArtifactIntegrityError, match="step"):
        artifact.validate_identity(symbol="BTCUSDT", venue="BINANCE", quantity_step="0.01")


def test_only_completed_valid_sessions_enter_calibration_population() -> None:
    population = [_session_stats(day) for day in range(1, 10)]
    population.append(_session_stats(10, gap=True))
    with pytest.raises(ValueError, match="insufficient"):
        CalibrationArtifact.create(
            population,
            symbol="BTCUSDT",
            venue="BINANCE",
            quantity_step="0.001",
            as_of_session="2026-01-11",
            created_at_utc=datetime(2026, 1, 11, tzinfo=UTC),
        )


def test_calibration_excludes_current_and_future_sessions() -> None:
    history = [_session_stats(day) for day in range(1, 21)]
    history.append(_session_stats(21, scale=100))
    history.append(_session_stats(22, scale=1000))
    artifact = CalibrationArtifact.create(
        history,
        symbol="BTCUSDT",
        venue="BINANCE",
        quantity_step="0.001",
        as_of_session="2026-01-21",
        created_at_utc=datetime(2026, 1, 21, tzinfo=UTC),
    )
    assert artifact.history_end_session == "2026-01-20"
    assert artifact.auto_low == Decimal("11")


def test_calibration_rejects_same_session_with_different_content() -> None:
    with pytest.raises(ArtifactCollisionError, match="SESSION_STATS_COLLISION"):
        CalibrationArtifact.create(
            (_session_stats(1), _session_stats(1, scale=2)),
            symbol="BTCUSDT",
            venue="BINANCE",
            quantity_step="0.001",
            as_of_session="2026-01-02",
            created_at_utc=datetime(2026, 1, 2, tzinfo=UTC),
        )


def test_activation_artifact_is_commit_point_and_pointer_is_derived_cache(tmp_path) -> None:
    repository = BigTradesArtifactRepository(tmp_path)
    version = _settings_version()
    repository.write_settings_version(version)
    activation = ActivationArtifact.create(
        symbol="BTCUSDT",
        venue="BINANCE",
        effective_from_event_time=datetime(2026, 1, 1, tzinfo=UTC),
        effective_from_trade_id=1,
        settings_id=version.settings_id,
        calibration_id=None,
        activation_reason=ActivationReason.PRODUCTION_INITIAL,
        activation_policy=CalibrationActivationPolicy.SCHEDULED_SESSION_BOUNDARY,
        requested_at_utc=datetime(2025, 12, 31, tzinfo=UTC),
    )
    result = repository.commit_activation(activation)
    assert result.committed is True
    assert result.pointer_cache_updated is True
    assert repository.load_activations() == (activation,)
    result.artifact_path.parent.parent.joinpath("active").glob("*.json")
    pointer = next((repository.settings_root / "active").glob("*.json"))
    pointer.unlink()
    assert repository.rebuild_active_pointer(
        symbol="BTCUSDT", venue="BINANCE"
    ) == pointer


def test_calibration_activation_requires_expected_quantity_step(tmp_path) -> None:
    repository = BigTradesArtifactRepository(tmp_path)
    calibration = _calibration()
    repository.write_calibration(calibration)
    version = _settings_version(automatic=True, calibration_id=calibration.calibration_id)
    repository.write_settings_version(version)
    activation = ActivationArtifact.create(
        symbol="BTCUSDT",
        venue="BINANCE",
        effective_from_event_time=datetime(2026, 1, 21, tzinfo=UTC),
        effective_from_trade_id=1,
        settings_id=version.settings_id,
        calibration_id=calibration.calibration_id,
        activation_reason=ActivationReason.USER_CALIBRATION,
        activation_policy=CalibrationActivationPolicy.MANUAL_ONLY,
        requested_at_utc=datetime(2026, 1, 20, tzinfo=UTC),
    )
    with pytest.raises(ArtifactIntegrityError, match="quantity step"):
        repository.commit_activation(activation)
    with pytest.raises(ArtifactIntegrityError, match="step"):
        repository.commit_activation(activation, expected_quantity_step="0.01")
    assert repository.commit_activation(
        activation, expected_quantity_step="0.001"
    ).committed


def test_historical_replay_resolves_committed_activation_and_ignores_created_time(tmp_path) -> None:
    repository = BigTradesArtifactRepository(tmp_path)
    calibration = _calibration(created_at=datetime(2026, 1, 21, tzinfo=UTC))
    same_identity_later_time = _calibration(created_at=datetime(2030, 1, 1, tzinfo=UTC))
    repository.write_calibration(calibration)
    repository.write_calibration(same_identity_later_time)
    version = _settings_version(automatic=True, calibration_id=calibration.calibration_id)
    repository.write_settings_version(version)
    activation = ActivationArtifact.create(
        symbol="BTCUSDT",
        venue="BINANCE",
        effective_from_event_time=datetime(2026, 1, 21, tzinfo=UTC),
        effective_from_trade_id=1,
        settings_id=version.settings_id,
        calibration_id=calibration.calibration_id,
        activation_reason=ActivationReason.PRODUCTION_INITIAL,
        activation_policy=CalibrationActivationPolicy.SCHEDULED_SESSION_BOUNDARY,
        requested_at_utc=datetime(2026, 1, 20, tzinfo=UTC),
    )
    repository.commit_activation(activation, expected_quantity_step="0.001")
    resolved = repository.resolve_historical_replay_snapshot(
        symbol="BTCUSDT",
        venue="BINANCE",
        cluster_first_time=datetime(2026, 1, 21, 0, 0, 1, tzinfo=UTC),
        cluster_first_trade_id=2,
        expected_quantity_step="0.001",
    )
    assert resolved.activation == activation
    assert resolved.calibration is not None
    assert resolved.calibration.created_at_utc == datetime(2026, 1, 21, tzinfo=UTC)
    assert resolved.production_write_allowed is True


def test_historical_replay_missing_reference_fails_closed(tmp_path) -> None:
    repository = BigTradesArtifactRepository(tmp_path)
    version = _settings_version()
    repository.write_settings_version(version)
    activation = ActivationArtifact.create(
        symbol="BTCUSDT",
        venue="BINANCE",
        effective_from_event_time=datetime(2026, 1, 1, tzinfo=UTC),
        effective_from_trade_id=1,
        settings_id=version.settings_id,
        calibration_id=None,
        activation_reason=ActivationReason.PRODUCTION_INITIAL,
        activation_policy=CalibrationActivationPolicy.MANUAL_ONLY,
        requested_at_utc=datetime(2025, 12, 31, tzinfo=UTC),
    )
    repository.commit_activation(activation)
    (repository.settings_root / "versions" / f"{version.settings_id}.json").unlink()
    with pytest.raises(ArtifactIntegrityError, match="REPLAY_ACTIVATION_HISTORY_INVALID"):
        repository.resolve_historical_replay_snapshot(
            symbol="BTCUSDT",
            venue="BINANCE",
            cluster_first_time=datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC),
            cluster_first_trade_id=2,
            expected_quantity_step="0.001",
        )


def test_fixed_research_resolution_has_isolated_output_and_no_activation(tmp_path) -> None:
    repository = BigTradesArtifactRepository(tmp_path)
    version = _settings_version()
    repository.write_settings_version(version)
    resolved = repository.resolve_fixed_research_snapshot(
        FixedResearchSelection("run-1", version.settings_id, None),
        expected_quantity_step="0.001",
    )
    assert resolved.activation is None
    assert resolved.production_write_allowed is False
    assert resolved.research_output_path == tmp_path / "research" / "big_trades" / "run-1"
    assert repository.load_activations() == ()


def _weekly_transition() -> SessionTransition:
    return SessionTransition(
        previous_session_id="2026-01-20",
        next_session_id="2026-01-26",
        confirmed_by_event_time=datetime(2026, 1, 26, tzinfo=UTC),
        confirmed_by_trade_id=100,
    )


def test_scheduled_success_auto_activates_from_same_source_boundary(tmp_path) -> None:
    repository = BigTradesArtifactRepository(tmp_path)
    for day in range(1, 21):
        repository.write_session_stats(_session_stats(day))
    active = _settings_version(automatic=True, calibration_id=CAL_OLD)
    boundary_trade = fill(0, trade_id=100, base=datetime(2026, 1, 26, tzinfo=UTC))
    execution = execute_scheduled_calibration(
        repository,
        transition=_weekly_transition(),
        schedule=CalibrationSchedule.WEEKLY,
        policy=CalibrationActivationPolicy.SCHEDULED_SESSION_BOUNDARY,
        active_settings=active,
        boundary_trade=boundary_trade,
        quantity_step="0.001",
    )
    assert execution is not None
    assert execution.run.result is ScheduleRunResult.ACTIVATED
    assert execution.resolved_activation is not None
    assert execution.resolved_activation.activation.activation_reason is ActivationReason.SCHEDULED_WEEKLY
    assert execution.resolved_activation.activation.effective_key == boundary_trade.source_key
    assert len(repository.load_activations()) == 1


def test_manual_only_generates_candidate_without_activation(tmp_path) -> None:
    repository = BigTradesArtifactRepository(tmp_path)
    for day in range(1, 21):
        repository.write_session_stats(_session_stats(day))
    execution = execute_scheduled_calibration(
        repository,
        transition=_weekly_transition(),
        schedule=CalibrationSchedule.WEEKLY,
        policy=CalibrationActivationPolicy.MANUAL_ONLY,
        active_settings=_settings_version(automatic=True, calibration_id=CAL_OLD),
        boundary_trade=fill(0, trade_id=100, base=datetime(2026, 1, 26, tzinfo=UTC)),
        quantity_step="0.001",
    )
    assert execution is not None
    assert execution.run.result is ScheduleRunResult.GENERATED_PENDING
    assert execution.candidate is not None
    assert execution.resolved_activation is None
    assert repository.load_activations() == ()


def test_missing_durable_previous_session_stops_schedule_and_keeps_old_activation(tmp_path) -> None:
    repository = BigTradesArtifactRepository(tmp_path)
    for day in range(1, 20):
        repository.write_session_stats(_session_stats(day))
    execution = execute_scheduled_calibration(
        repository,
        transition=_weekly_transition(),
        schedule=CalibrationSchedule.WEEKLY,
        policy=CalibrationActivationPolicy.SCHEDULED_SESSION_BOUNDARY,
        active_settings=_settings_version(automatic=True, calibration_id=CAL_OLD),
        boundary_trade=fill(0, trade_id=100, base=datetime(2026, 1, 26, tzinfo=UTC)),
        quantity_step="0.001",
    )
    assert execution is not None
    assert execution.run.result is ScheduleRunResult.STORAGE_FAILED
    assert execution.run.failure_code == "SESSION_STATS_NOT_DURABLE"
    assert repository.load_activations() == ()


def test_scheduled_validation_failure_does_not_activate_or_retry(tmp_path) -> None:
    repository = BigTradesArtifactRepository(tmp_path)
    repository.write_session_stats(_session_stats(20))
    arguments = {
        "transition": _weekly_transition(),
        "schedule": CalibrationSchedule.WEEKLY,
        "policy": CalibrationActivationPolicy.SCHEDULED_SESSION_BOUNDARY,
        "active_settings": _settings_version(automatic=True, calibration_id=CAL_OLD),
        "boundary_trade": fill(0, trade_id=100, base=datetime(2026, 1, 26, tzinfo=UTC)),
        "quantity_step": "0.001",
    }
    first = execute_scheduled_calibration(repository, **arguments)
    second = execute_scheduled_calibration(repository, **arguments)
    assert first is not None and second is not None
    assert first.run.result is ScheduleRunResult.VALIDATION_FAILED
    assert second.reused_run is True
    assert repository.load_activations() == ()


def test_same_schedule_boundary_and_manifest_reuses_terminal_run(tmp_path) -> None:
    repository = BigTradesArtifactRepository(tmp_path)
    for day in range(1, 21):
        repository.write_session_stats(_session_stats(day))
    arguments = {
        "transition": _weekly_transition(),
        "schedule": CalibrationSchedule.WEEKLY,
        "policy": CalibrationActivationPolicy.MANUAL_ONLY,
        "active_settings": _settings_version(automatic=True, calibration_id=CAL_OLD),
        "boundary_trade": fill(0, trade_id=100, base=datetime(2026, 1, 26, tzinfo=UTC)),
        "quantity_step": "0.001",
    }
    first = execute_scheduled_calibration(repository, **arguments)
    second = execute_scheduled_calibration(repository, **arguments)
    assert first is not None and second is not None
    assert second.reused_run is True
    assert second.run.run_id == first.run.run_id
