from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from threading import Event

from src.database.big_trades_storage import (
    BigTradesBackgroundStorageWriter,
    BigTradesDuckDbStore,
)
from src.orderflow.big_trades.activation import (
    ActivationArtifact,
    ActivationReason,
    CalibrationActivationPolicy,
)
from src.orderflow.big_trades.artifacts import BigTradesArtifactRepository
from src.orderflow.big_trades.constants import (
    AutomaticIntensity,
    FilterMode,
    MarkerPriceMode,
    SideFilter,
)
from src.orderflow.big_trades.models import BigTradeFill, ClosedCandle
from src.orderflow.big_trades.runtime import (
    BigTradesRuntimeStatus,
    BigTradesRuntimeV2,
    FixedActivationSettingsResolver,
    RecordedActivationSettingsResolver,
    RuntimeMode,
    runtime_records_canonical,
)
from src.orderflow.big_trades.settings import SettingsVersion
from src.orderflow.big_trades.time_buckets import candle_id


UTC = timezone.utc
BASE = datetime(2026, 8, 12, tzinfo=UTC)


def _settings_activation():
    settings = SettingsVersion.create(
        symbol="BTCUSDT",
        venue="BINANCE",
        filter_mode=FilterMode.MANUAL,
        manual_min_quantity="10",
        manual_max_quantity="0",
        automatic_intensity=AutomaticIntensity.MEDIUM,
        side_filter=SideFilter.BOTH,
        marker_price_mode=MarkerPriceMode.LAST_PRICE,
    )
    activation = ActivationArtifact.create(
        symbol="BTCUSDT",
        venue="BINANCE",
        effective_from_event_time=BASE,
        effective_from_trade_id=0,
        settings_id=settings.settings_id,
        calibration_id=None,
        activation_reason=ActivationReason.USER_SETTINGS,
        activation_policy=CalibrationActivationPolicy.MANUAL_ONLY,
        requested_at_utc=BASE,
    )
    return settings, activation


def _fill(ms: int, trade_id: int, price: str, quantity: str, side: str, *, base=BASE):
    when = base + timedelta(milliseconds=ms)
    return BigTradeFill(
        event_time=when,
        trade_time=when,
        trade_id=trade_id,
        symbol="BTCUSDT",
        venue="BINANCE",
        price=Decimal(price),
        quantity=Decimal(quantity),
        side=side,
    )


def _fixture(base=BASE):
    return (
        _fill(0, 1, "100", "6", "BUY", base=base),
        _fill(10, 2, "101", "6", "BUY", base=base),
        _fill(100, 3, "102", "1", "SELL", base=base),
        _fill(101, 4, "102", "1", "SELL", base=base),
    )


def _runtime(
    root: Path,
    *,
    mode: RuntimeMode,
    resolver,
    fault_injector=None,
    horizons=(1,),
    queue_maxsize=100,
):
    store = BigTradesDuckDbStore(root / "big-trades.duckdb", fault_injector=fault_injector)
    writer = BigTradesBackgroundStorageWriter(store, queue_maxsize=queue_maxsize)
    runtime = BigTradesRuntimeV2(
        enabled=True,
        mode=mode,
        symbol="BTCUSDT",
        venue="BINANCE",
        tick_size=Decimal("0.1"),
        settings_resolver=resolver,
        storage_writer=writer,
        artifact_repository=BigTradesArtifactRepository(root / "artifacts"),
        horizons_seconds=horizons,
    )
    return store, writer, runtime


def _settle(writer: BigTradesBackgroundStorageWriter, runtime: BigTradesRuntimeV2):
    records = []
    for _ in range(8):
        writer.join()
        runtime.drain_commit_acks()
        records.extend(runtime.take_publications())
        stats = runtime.statistics()
        if stats["pending_origins"] == 0 and stats["pending_updates"] == 0:
            break
    return tuple(records)


def test_origin_is_not_published_until_duckdb_commit_ack(tmp_path: Path) -> None:
    entered = Event()
    release = Event()

    def block(stage: str, table_name: str) -> None:
        if stage == "before_commit" and table_name == "big_trade_origin_batch":
            entered.set()
            assert release.wait(5)

    settings, activation = _settings_activation()
    store, writer, runtime = _runtime(
        tmp_path,
        mode=RuntimeMode.LIVE,
        resolver=FixedActivationSettingsResolver(settings, activation),
        fault_injector=block,
    )
    try:
        for trade in _fixture():
            assert runtime.process(trade) == ()
        runtime.flush()
        assert entered.wait(5)
        runtime.drain_commit_acks()
        assert runtime.recent_records == ()
        release.set()
        published = _settle(writer, runtime)
        assert [record.kind for record in published[:2]] == ["EVENT_CREATED", "ZONE_CREATED"]
        assert store.count("big_trade_events") == 1
        assert store.count("big_trade_reaction_zones") == 1
    finally:
        release.set()
        writer.close()


def test_live_and_recorded_replay_use_identical_core_and_durable_rows(tmp_path: Path) -> None:
    settings, activation = _settings_activation()
    live_store, live_writer, live = _runtime(
        tmp_path / "live",
        mode=RuntimeMode.LIVE,
        resolver=FixedActivationSettingsResolver(settings, activation),
    )
    replay_store, replay_writer, replay = _runtime(
        tmp_path / "replay",
        mode=RuntimeMode.REPLAY,
        resolver=RecordedActivationSettingsResolver(
            activations=(activation,),
            settings={settings.settings_id: settings},
            calibrations={},
        ),
    )
    try:
        live_records = []
        replay_records = []
        for trade in _fixture():
            live_records.extend(live.process(trade))
            replay_records.extend(replay.process(trade))
        live_records.extend(live.flush())
        replay_records.extend(replay.flush())
        live_records.extend(_settle(live_writer, live))
        replay_records.extend(_settle(replay_writer, replay))
        assert runtime_records_canonical(live_records) == runtime_records_canonical(replay_records)
        for table_name, order_by in (
            ("big_trade_events", "event_id"),
            ("big_trade_event_fills", "event_id, fill_ordinal"),
            ("big_trade_reaction_zones", "zone_id"),
            ("big_trade_zone_interactions", "zone_id, ordinal"),
            ("big_trade_zone_state_checkpoints", "zone_id, source_bucket_time"),
        ):
            assert live_store.fetch_rows(table_name, order_by=order_by) == replay_store.fetch_rows(
                table_name, order_by=order_by
            )
    finally:
        live_writer.close()
        replay_writer.close()


def test_source_gap_invalidates_crossing_horizon(tmp_path: Path) -> None:
    settings, activation = _settings_activation()
    store, writer, runtime = _runtime(
        tmp_path,
        mode=RuntimeMode.LIVE,
        resolver=FixedActivationSettingsResolver(settings, activation),
    )
    try:
        for trade in _fixture():
            runtime.process(trade)
        _settle(writer, runtime)
        runtime.start_source_gap(BASE + timedelta(milliseconds=200))
        runtime.process(_fill(2_000, 10, "105", "1", "BUY"))
        runtime.process(_fill(2_001, 11, "105", "1", "BUY"))
        runtime.flush()
        _settle(writer, runtime)
        rows = store.fetch_rows("big_trade_result_snapshots")
        assert len(rows) == 1
        assert rows[0]["validity"] == "MISSING_SOURCE_GAP"
        assert runtime.status == BigTradesRuntimeStatus.DEGRADED_SOURCE_GAP
        interactions = store.fetch_rows(
            "big_trade_zone_interactions", order_by="ordinal"
        )
        types = [row["interaction_type"] for row in interactions]
        assert "SOURCE_GAP_STARTED" in types
        assert "SOURCE_GAP_ENDED" in types
    finally:
        writer.close()


def test_source_confirmed_next_session_closes_zone_and_saves_stats(tmp_path: Path) -> None:
    settings, activation = _settings_activation()
    store, writer, runtime = _runtime(
        tmp_path,
        mode=RuntimeMode.LIVE,
        resolver=FixedActivationSettingsResolver(settings, activation),
    )
    next_session = BASE + timedelta(days=1)
    try:
        for trade in _fixture():
            runtime.process(trade)
        runtime.process(_fill(0, 100, "110", "1", "BUY", base=next_session))
        runtime.process(_fill(1, 101, "110", "1", "BUY", base=next_session))
        runtime.flush()
        _settle(writer, runtime)
        assert store.count("big_trade_session_stats") == 1
        interaction_types = {
            row["interaction_type"]
            for row in store.fetch_rows("big_trade_zone_interactions")
        }
        assert "ZONE_SESSION_CLOSED" in interaction_types
        checkpoints = store.fetch_rows("big_trade_zone_state_checkpoints")
        assert checkpoints
        artifacts = tuple((tmp_path / "artifacts").rglob("*.json"))
        assert any("session" in path.as_posix() for path in artifacts)
        assert runtime.statistics()["sessions_source_confirmed"] == 1
    finally:
        writer.close()


def test_delayed_candle_observation_is_idempotent(tmp_path: Path) -> None:
    settings, activation = _settings_activation()
    store, writer, runtime = _runtime(
        tmp_path,
        mode=RuntimeMode.LIVE,
        resolver=FixedActivationSettingsResolver(settings, activation),
    )
    try:
        for trade in _fixture():
            runtime.process(trade)
        runtime.flush()
        _settle(writer, runtime)
        open_time = BASE.replace(second=0, microsecond=0)
        candle = ClosedCandle(
            candle_id=candle_id(open_time),
            open_time=open_time,
            symbol="BTCUSDT",
            open=Decimal("100"),
            high=Decimal("104"),
            low=Decimal("99"),
            close=Decimal("102"),
        )
        runtime.observe_closed_candle(candle)
        _settle(writer, runtime)
        runtime.observe_closed_candle(candle)
        _settle(writer, runtime)
        assert store.count("big_trade_zone_candle_observations") == 1
        assert writer.statistics()["duplicates"] >= 1
        matching = [
            record
            for record in runtime.recent_records
            if record.kind == "CANDLE_OBSERVATION"
        ]
        assert len(matching) == 1
    finally:
        writer.close()


def test_restart_recovers_zone_without_republishing_origin_and_marks_gap(
    tmp_path: Path,
) -> None:
    settings, activation = _settings_activation()
    resolver = FixedActivationSettingsResolver(settings, activation)
    store, writer, runtime = _runtime(
        tmp_path,
        mode=RuntimeMode.LIVE,
        resolver=resolver,
    )
    trades = _fixture()
    try:
        for trade in trades:
            runtime.process(trade)
        _settle(writer, runtime)
        assert store.count("big_trade_events") == 1
        assert store.count("big_trade_reaction_zones") == 1
    finally:
        writer.close()

    restarted_store, restarted_writer, restarted = _runtime(
        tmp_path,
        mode=RuntimeMode.LIVE,
        resolver=FixedActivationSettingsResolver(settings, activation),
    )
    try:
        restarted.recover_current_session(
            session_id=BASE.date().isoformat(), source_trades=trades
        )
        recovery_records = _settle(restarted_writer, restarted)
        assert all(record.kind not in {"EVENT_CREATED", "ZONE_CREATED"} for record in recovery_records)
        assert restarted_store.count("big_trade_events") == 1
        assert restarted_store.count("big_trade_reaction_zones") == 1
        assert restarted.status == BigTradesRuntimeStatus.DEGRADED_SOURCE_GAP
        assert restarted.statistics()["restart_recoveries"] == 1

        restarted.process(_fill(2_000, 10, "105", "1", "BUY"))
        restarted.process(_fill(2_001, 11, "105", "1", "BUY"))
        restarted.flush()
        _settle(restarted_writer, restarted)
        snapshot = restarted_store.fetch_rows("big_trade_result_snapshots")[0]
        assert snapshot["validity"] == "MISSING_SOURCE_GAP"
        interactions = restarted_store.fetch_rows(
            "big_trade_zone_interactions", order_by="ordinal"
        )
        assert [row["ordinal"] for row in interactions] == list(
            range(1, len(interactions) + 1)
        )
    finally:
        restarted_writer.close()


def test_disabled_runtime_performs_no_storage_or_resolution(tmp_path: Path) -> None:
    runtime = BigTradesRuntimeV2(
        enabled=False,
        mode=RuntimeMode.LIVE,
        symbol="BTCUSDT",
        venue="BINANCE",
        tick_size=Decimal("0.1"),
    )
    for trade in _fixture():
        assert runtime.process(trade) == ()
    assert runtime.status == BigTradesRuntimeStatus.DISABLED
    assert runtime.statistics()["trades_observed"] == 0


def test_delayed_same_area_link_keeps_source_order_and_restart_recovery(
    tmp_path: Path,
) -> None:
    settings, activation = _settings_activation()
    resolver = FixedActivationSettingsResolver(settings, activation)
    store, writer, runtime = _runtime(
        tmp_path,
        mode=RuntimeMode.LIVE,
        resolver=resolver,
    )
    trades = (
        _fill(0, 1, "100", "6", "BUY"),
        _fill(10, 2, "100", "6", "BUY"),
        _fill(100, 3, "101", "1", "SELL"),
        _fill(200, 4, "100", "6", "BUY"),
        _fill(210, 5, "100", "6", "BUY"),
        _fill(300, 6, "101", "1", "SELL"),
    )
    try:
        for trade in trades:
            runtime.process(trade)
        runtime.flush()
        _settle(writer, runtime)
        assert runtime.statistics()["errors"] == 0
        assert store.count("big_trade_events") == 2
        assert store.count("big_trade_reaction_zones") == 2
        assert store.count("big_trade_zone_event_links") == 1
    finally:
        writer.close()

    recovered_store, recovered_writer, recovered = _runtime(
        tmp_path,
        mode=RuntimeMode.LIVE,
        resolver=resolver,
    )
    try:
        recovered.recover_current_session(
            session_id=BASE.date().isoformat(), source_trades=trades
        )
        _settle(recovered_writer, recovered)
        assert recovered.statistics()["errors"] == 0
        assert recovered.statistics()["restart_recoveries"] == 1
        assert recovered_store.count("big_trade_events") == 2
        assert recovered_store.count("big_trade_zone_event_links") == 1
    finally:
        recovered_writer.close()


def test_reconnect_flushes_open_cluster_without_deleting_active_zone(
    tmp_path: Path,
) -> None:
    settings, activation = _settings_activation()
    store, writer, runtime = _runtime(
        tmp_path,
        mode=RuntimeMode.LIVE,
        resolver=FixedActivationSettingsResolver(settings, activation),
    )
    try:
        runtime.process(_fill(0, 1, "100", "6", "BUY"))
        runtime.process(_fill(10, 2, "100", "6", "BUY"))
        runtime.start_source_gap(BASE + timedelta(milliseconds=10))
        runtime.process(_fill(100, 3, "100", "6", "BUY"))
        runtime.process(_fill(110, 4, "100", "6", "BUY"))
        runtime.process(_fill(200, 5, "101", "1", "SELL"))
        runtime.flush()
        _settle(writer, runtime)
        events = store.fetch_rows("big_trade_events", order_by="first_trade_id")
        assert [(row["first_trade_id"], row["fill_count"]) for row in events] == [
            (1, 2),
            (3, 2),
        ]
        assert store.count("big_trade_reaction_zones") == 2
        assert runtime.statistics()["source_gap_epochs"] == 1
    finally:
        writer.close()


def test_candle_boundary_mismatch_errors_only_big_trades_runtime(tmp_path: Path) -> None:
    settings, activation = _settings_activation()
    store, writer, runtime = _runtime(
        tmp_path,
        mode=RuntimeMode.LIVE,
        resolver=FixedActivationSettingsResolver(settings, activation),
    )
    try:
        for trade in _fixture():
            runtime.process(trade)
        runtime.flush()
        _settle(writer, runtime)
        open_time = BASE.replace(second=0, microsecond=0)
        runtime.observe_closed_candle(
            ClosedCandle(
                candle_id=candle_id(open_time) + 1,
                open_time=open_time,
                symbol="BTCUSDT",
                open=Decimal("100"),
                high=Decimal("104"),
                low=Decimal("99"),
                close=Decimal("102"),
            )
        )
        assert runtime.status is BigTradesRuntimeStatus.ERROR
        assert runtime.statistics()["errors"] == 1
        assert store.count("big_trade_events") == 1
    finally:
        writer.close()
