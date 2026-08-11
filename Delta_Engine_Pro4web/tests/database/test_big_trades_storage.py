from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from threading import Event

import pyarrow.parquet as pq
import pytest

from src.database.big_trades_schema import (
    BIG_TRADES_ARROW_SCHEMAS,
    BigTradeOriginStorageBatch,
    checkpoint_to_row,
)
from src.database.big_trades_storage import (
    BigTradesBackgroundStorageWriter,
    BigTradesContentCollision,
    BigTradesDuckDbStore,
    BigTradesStorageIntegrityError,
    ParquetCommitStatus,
)
from src.orderflow.big_trades.aggregation import create_big_trade_event
from src.orderflow.big_trades.activation import (
    ActivationArtifact,
    ActivationReason,
    CalibrationActivationPolicy,
)
from src.orderflow.big_trades.constants import (
    AutomaticIntensity,
    ClusterCloseReason,
    FilterMode,
    MarkerPriceMode,
    PriceRelation,
    SideFilter,
)
from src.orderflow.big_trades.artifacts import BigTradesArtifactRepository
from src.orderflow.big_trades.filtering import ManualSizeFilter
from src.orderflow.big_trades.ids import content_hash
from src.orderflow.big_trades.models import (
    BigTradeFill,
    BigTradesSettingsSnapshot,
    ClosedCandle,
    ExecutionCluster,
    UserAssessment,
    ZoneStateCheckpoint,
)
from src.orderflow.big_trades.reaction_zones import ReactionZoneObserver, create_reaction_zone
from src.orderflow.big_trades.runtime import (
    BigTradesRuntimeV2,
    FixedActivationSettingsResolver,
    RuntimeMode,
)
from src.orderflow.big_trades.settings import (
    SettingsRequest,
    SettingsRequestSource,
    SettingsVersion,
)
from src.orderflow.big_trades.time_buckets import candle_id


UTC = timezone.utc
BASE = datetime(2026, 8, 12, 1, 2, 3, 456000, tzinfo=UTC)


def _origin(*, price: str = "67000.12345678") -> BigTradeOriginStorageBatch:
    settings = BigTradesSettingsSnapshot(
        settings_id="bts1_storage",
        symbol="BTCUSDT",
        venue="BINANCE",
        filter_mode=FilterMode.MANUAL,
        manual_min_quantity=Decimal("1.00000000"),
        activation_id="bta1_storage",
    )
    fills = (
        BigTradeFill(
            event_time=BASE,
            trade_time=BASE,
            trade_id=100,
            symbol="BTCUSDT",
            venue="BINANCE",
            price=Decimal(price),
            quantity=Decimal("1.12345678"),
            side="BUY",
        ),
        BigTradeFill(
            event_time=BASE + timedelta(milliseconds=25),
            trade_time=BASE + timedelta(milliseconds=25),
            trade_id=101,
            symbol="BTCUSDT",
            venue="BINANCE",
            price=Decimal("67001.12345678"),
            quantity=Decimal("2.00000000"),
            side="BUY",
        ),
    )
    cluster = ExecutionCluster(fills, settings, ClusterCloseReason.TIME_GAP_EXCEEDED)
    decision = ManualSizeFilter(Decimal("1"), Decimal("0")).decide(cluster.aggregate_quantity)
    event = create_big_trade_event(cluster, decision)
    zone = create_reaction_zone(event)
    created = ReactionZoneObserver(zone, tick_size=Decimal("0.1")).interactions[0]
    return BigTradeOriginStorageBatch.create(event, fills, zone, created)


def _checkpoint(*, zone_id: str = "btz2_one", touch_count: int = 1) -> ZoneStateCheckpoint:
    payload = {
        "checkpoint_id": "btcp2_one",
        "zone_id": zone_id,
        "source_bucket_time": BASE.replace(microsecond=0),
        "current_relation": PriceRelation.INSIDE,
        "first_exit_direction": None,
        "first_exit_time": None,
        "touch_count": touch_count,
        "cross_count": 0,
        "inside_buy_quantity": Decimal("1.25"),
        "inside_sell_quantity": Decimal("0"),
        "linked_event_count": 0,
        "gap_epoch_id": None,
    }
    return ZoneStateCheckpoint(content_hash=content_hash(payload), **payload)


def test_isolated_migration_has_all_authoritative_columns(tmp_path: Path) -> None:
    store = BigTradesDuckDbStore(tmp_path / "isolated.duckdb")
    try:
        for table_name, schema in BIG_TRADES_ARROW_SCHEMAS.items():
            rows = store._con.execute(f"PRAGMA table_info('{table_name}')").fetchall()
            assert [row[1] for row in rows] == schema.names
        metadata = store.fetch_rows("big_trades_schema_meta")
        assert metadata[0]["component"] == "big_trades"
        assert metadata[0]["schema_version"] == 2
        assert metadata[0]["logic_version"] == "BTLOGIC-2.0"
    finally:
        store.close()


def test_origin_batch_is_atomic_idempotent_and_decimal_utc_exact(tmp_path: Path) -> None:
    store = BigTradesDuckDbStore(tmp_path / "isolated.duckdb")
    batch = _origin()
    try:
        first = store.insert_origin_batch(batch)
        duplicate = store.insert_origin_batch(batch)
        assert first.inserted == {
            "big_trade_events": 1,
            "big_trade_event_fills": 2,
            "big_trade_reaction_zones": 1,
            "big_trade_zone_interactions": 1,
            "big_trade_zone_event_links": 0,
        }
        assert duplicate.duplicates == 5
        assert store.count("big_trade_events") == 1
        assert store.count("big_trade_event_fills") == 2
        event = store.fetch_rows("big_trade_events")[0]
        assert event["first_price"] == Decimal("67000.12345678")
        assert event["first_time"] == BASE
        assert event["marker_time"].tzinfo is UTC
    finally:
        store.close()


def test_origin_component_failure_rolls_back_every_table(tmp_path: Path) -> None:
    def fail(stage: str, table_name: str) -> None:
        if stage == "before_insert" and table_name == "big_trade_reaction_zones":
            raise OSError("injected zone failure")

    store = BigTradesDuckDbStore(tmp_path / "isolated.duckdb", fault_injector=fail)
    try:
        with pytest.raises(OSError, match="injected zone failure"):
            store.insert_origin_batch(_origin())
        for table_name in (
            "big_trade_events",
            "big_trade_event_fills",
            "big_trade_reaction_zones",
            "big_trade_zone_interactions",
        ):
            assert store.count(table_name) == 0
    finally:
        store.close()


def test_same_origin_id_with_different_content_is_collision(tmp_path: Path) -> None:
    store = BigTradesDuckDbStore(tmp_path / "isolated.duckdb")
    batch = _origin()
    try:
        store.insert_origin_batch(batch)
        changed_event = dict(batch.event)
        changed_event["content_hash"] = "different-content"
        changed = replace(batch, batch_id=batch.batch_id + "x", event=changed_event)
        with pytest.raises(BigTradesContentCollision):
            store.insert_origin_batch(changed)
        assert store.count("big_trade_events") == 1
    finally:
        store.close()


def test_checkpoint_is_idempotent_and_mismatch_collides(tmp_path: Path) -> None:
    store = BigTradesDuckDbStore(tmp_path / "isolated.duckdb")
    origin = _origin()
    first = checkpoint_to_row(_checkpoint(zone_id=origin.zone["zone_id"]))
    changed = checkpoint_to_row(
        _checkpoint(zone_id=origin.zone["zone_id"], touch_count=2)
    )
    try:
        store.insert_origin_batch(origin)
        result = store.insert_rows(
            batch_id="checkpoint-one",
            kind="big_trade_zone_checkpoints",
            table_name="big_trade_zone_state_checkpoints",
            rows=(first,),
        )
        duplicate = store.insert_rows(
            batch_id="checkpoint-one",
            kind="big_trade_zone_checkpoints",
            table_name="big_trade_zone_state_checkpoints",
            rows=(first,),
        )
        assert result.inserted["big_trade_zone_state_checkpoints"] == 1
        assert duplicate.duplicates == 1
        with pytest.raises(BigTradesContentCollision):
            store.insert_rows(
                batch_id="checkpoint-changed",
                kind="big_trade_zone_checkpoints",
                table_name="big_trade_zone_state_checkpoints",
                rows=(changed,),
            )
    finally:
        store.close()


def test_background_writer_ack_is_after_commit(tmp_path: Path) -> None:
    entered = Event()
    release = Event()

    def block_before_commit(stage: str, table_name: str) -> None:
        if stage == "before_commit" and table_name == "big_trade_origin_batch":
            entered.set()
            assert release.wait(5)

    store = BigTradesDuckDbStore(tmp_path / "isolated.duckdb", fault_injector=block_before_commit)
    writer = BigTradesBackgroundStorageWriter(store, queue_maxsize=2)
    try:
        future = writer.submit_origin_batch(_origin())
        assert entered.wait(5)
        assert future.done() is False
        release.set()
        ack = future.result(5)
        assert ack.success is True
        assert ack.duckdb_committed is True
        assert store.count("big_trade_events") == 1
    finally:
        release.set()
        writer.close()


def test_background_queue_full_returns_explicit_failed_ack(tmp_path: Path) -> None:
    entered = Event()
    release = Event()

    def block_first(stage: str, table_name: str) -> None:
        if stage == "before_commit" and table_name == "big_trade_origin_batch" and not release.is_set():
            entered.set()
            assert release.wait(5)

    store = BigTradesDuckDbStore(tmp_path / "isolated.duckdb", fault_injector=block_first)
    writer = BigTradesBackgroundStorageWriter(store, queue_maxsize=1)
    try:
        first = writer.submit_origin_batch(_origin())
        assert entered.wait(5)
        second = writer.submit_origin_batch(_origin())
        rejected = writer.submit_origin_batch(_origin()).result(1)
        assert rejected.success is False
        assert rejected.error_code == "QUEUE_FULL"
        assert writer.statistics()["queue_full"] == 1
        assert writer.statistics()["queue_high_watermark"] == 1
        release.set()
        assert first.result(5).success
        assert second.result(5).success
    finally:
        release.set()
        writer.close()


def test_parquet_requires_manifest_and_retries_after_duckdb_commit(tmp_path: Path) -> None:
    fail_manifest = {"enabled": True}

    def fail(stage: str, table_name: str) -> None:
        if fail_manifest["enabled"] and stage == "before_manifest":
            raise OSError("injected manifest failure")

    parquet_root = tmp_path / "parquet"
    store = BigTradesDuckDbStore(
        tmp_path / "isolated.duckdb",
        parquet_path=parquet_root,
        parquet_fault_injector=fail,
    )
    batch = _origin()
    try:
        result = store.insert_origin_batch(batch)
        assert result.parquet_status == ParquetCommitStatus.PENDING
        assert store.count("big_trade_events") == 1
        assert store.parquet_pending == 1
        assert not (parquet_root / "_commits" / f"{batch.batch_id}.json").exists()
        fail_manifest["enabled"] = False
        assert store.retry_parquet_pending() == 1
        manifest = parquet_root / "_commits" / f"{batch.batch_id}.json"
        assert manifest.is_file()
        assert store.parquet_pending == 0
        event_file = parquet_root / "big_trade_events" / f"{batch.batch_id}.parquet"
        zone_file = parquet_root / "big_trade_reaction_zones" / f"{batch.batch_id}.parquet"
        assert pq.ParquetFile(event_file).read().num_rows == 1
        assert pq.ParquetFile(zone_file).read().num_rows == 1
    finally:
        store.close()


def test_missing_manifest_member_is_detected(tmp_path: Path) -> None:
    parquet_root = tmp_path / "parquet"
    store = BigTradesDuckDbStore(tmp_path / "isolated.duckdb", parquet_path=parquet_root)
    batch = _origin()
    try:
        store.insert_origin_batch(batch)
        event_file = parquet_root / "big_trade_events" / f"{batch.batch_id}.parquet"
        event_file.unlink()
        with pytest.raises(BigTradesStorageIntegrityError, match="missing or corrupt"):
            store._parquet._verify_manifest(  # type: ignore[union-attr]
                parquet_root / "_commits" / f"{batch.batch_id}.json"
            )
    finally:
        store.close()


def test_assessment_parquet_is_committed_only_with_manifest(tmp_path: Path) -> None:
    parquet_root = tmp_path / "parquet"
    store = BigTradesDuckDbStore(tmp_path / "isolated.duckdb", parquet_path=parquet_root)
    writer = BigTradesBackgroundStorageWriter(store)
    origin = _origin()
    store.insert_origin_batch(origin)
    payload = {
        "assessment_id": "btassess2_one",
        "zone_id": origin.zone["zone_id"],
        "assessment": "WORKED",
        "assessed_at_utc": BASE,
        "assessed_against_source_time": BASE - timedelta(seconds=1),
        "user_note": "observed",
        "supersedes_assessment_id": None,
    }
    assessment = UserAssessment(content_hash=content_hash(payload), **payload)
    try:
        ack = writer.submit_user_assessments((assessment,)).result(5)
        assert ack.success is True
        assert ack.parquet_status == ParquetCommitStatus.COMMITTED
        manifests = tuple((parquet_root / "_commits").glob("*.json"))
        assert len(manifests) == 2
        files = tuple((parquet_root / "big_trade_user_assessments").glob("*.parquet"))
        assert len(files) == 1
        assert pq.ParquetFile(files[0]).read().to_pylist()[0]["assessment"] == "WORKED"
    finally:
        writer.close()


def test_settings_then_activation_mirrors_preserve_lineage(tmp_path: Path) -> None:
    store = BigTradesDuckDbStore(tmp_path / "isolated.duckdb")
    writer = BigTradesBackgroundStorageWriter(store)
    settings = SettingsVersion.create(
        symbol="BTCUSDT",
        venue="BINANCE",
        filter_mode=FilterMode.MANUAL,
        manual_min_quantity="5",
        manual_max_quantity="0",
        automatic_intensity=AutomaticIntensity.MEDIUM,
        side_filter=SideFilter.BOTH,
        marker_price_mode=MarkerPriceMode.LAST_PRICE,
    )
    request = SettingsRequest.create(
        settings,
        requested_at_utc=BASE,
        previous_settings_id=None,
        request_source=SettingsRequestSource.CONFIG,
    )
    activation = ActivationArtifact.create(
        symbol="BTCUSDT",
        venue="BINANCE",
        effective_from_event_time=BASE,
        effective_from_trade_id=100,
        settings_id=settings.settings_id,
        calibration_id=None,
        activation_reason=ActivationReason.USER_SETTINGS,
        activation_policy=CalibrationActivationPolicy.MANUAL_ONLY,
        requested_at_utc=BASE,
    )
    try:
        assert writer.submit_settings(request, settings).result(5).success
        assert writer.submit_activation(activation).result(5).success
        settings_row = store.fetch_rows("big_trade_settings_history")[0]
        activation_row = store.fetch_rows("big_trade_activation_history")[0]
        assert settings_row["settings_id"] == settings.settings_id
        assert activation_row["settings_id"] == settings.settings_id
        assert activation_row["activation_id"] == activation.activation_id
        assert activation_row["effective_from_event_time"] == BASE
    finally:
        writer.close()


def test_runtime_updates_round_trip_interaction_link_snapshot_and_candle_parquet(
    tmp_path: Path,
) -> None:
    parquet_root = tmp_path / "parquet"
    store = BigTradesDuckDbStore(
        tmp_path / "isolated.duckdb", parquet_path=parquet_root
    )
    writer = BigTradesBackgroundStorageWriter(store)
    configured = SettingsVersion.create(
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
        settings_id=configured.settings_id,
        calibration_id=None,
        activation_reason=ActivationReason.USER_SETTINGS,
        activation_policy=CalibrationActivationPolicy.MANUAL_ONLY,
        requested_at_utc=BASE,
    )
    runtime = BigTradesRuntimeV2(
        enabled=True,
        mode=RuntimeMode.REPLAY,
        symbol="BTCUSDT",
        venue="BINANCE",
        tick_size=Decimal("0.1"),
        settings_resolver=FixedActivationSettingsResolver(configured, activation),
        storage_writer=writer,
        artifact_repository=BigTradesArtifactRepository(tmp_path / "artifacts"),
        horizons_seconds=(1,),
    )

    def trade(trade_id: int, offset_ms: int, price: str, quantity: str, side: str):
        source_time = BASE + timedelta(milliseconds=offset_ms)
        return BigTradeFill(
            event_time=source_time,
            trade_time=source_time,
            trade_id=trade_id,
            symbol="BTCUSDT",
            venue="BINANCE",
            price=Decimal(price),
            quantity=Decimal(quantity),
            side=side,
        )

    try:
        for item in (
            trade(1, 0, "100", "6", "BUY"),
            trade(2, 10, "100", "6", "BUY"),
            trade(3, 100, "101", "1", "SELL"),
            trade(4, 200, "100", "6", "BUY"),
            trade(5, 210, "100", "6", "BUY"),
            trade(6, 300, "101", "1", "SELL"),
            trade(7, 2_000, "102", "1", "SELL"),
        ):
            runtime.process(item)
        runtime.flush()
        writer.join()
        runtime.drain_commit_acks()
        writer.join()
        runtime.drain_commit_acks()
        open_time = BASE.replace(second=0, microsecond=0)
        runtime.observe_closed_candle(
            ClosedCandle(
                candle_id=candle_id(open_time),
                open_time=open_time,
                symbol="BTCUSDT",
                open=Decimal("100"),
                high=Decimal("103"),
                low=Decimal("99"),
                close=Decimal("101"),
            )
        )
        writer.join()
        runtime.drain_commit_acks()
        writer.join()
        runtime.drain_commit_acks()
        assert runtime.statistics()["errors"] == 0
        for table_name in (
            "big_trade_zone_interactions",
            "big_trade_zone_event_links",
            "big_trade_result_snapshots",
            "big_trade_zone_candle_observations",
        ):
            files = tuple((parquet_root / table_name).glob("*.parquet"))
            assert files, table_name
            assert sum(pq.ParquetFile(path).read().num_rows for path in files) == store.count(
                table_name
            )
    finally:
        writer.close()
