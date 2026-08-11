from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.database.big_trades_schema import BigTradeOriginStorageBatch
from src.database.big_trades_schema import calibration_to_row
from src.database.big_trades_storage import BigTradesContentCollision, BigTradesDuckDbStore
from src.orderflow.big_trades.activation import (
    ActivationArtifact,
    ActivationReason,
    CalibrationActivationPolicy,
)
from src.orderflow.big_trades.aggregation import create_big_trade_event
from src.orderflow.big_trades.artifacts import BigTradesArtifactRepository
from src.orderflow.big_trades.constants import ClusterCloseReason, FilterMode
from src.orderflow.big_trades.filtering import ManualSizeFilter
from src.orderflow.big_trades.models import (
    BigTradeFill,
    BigTradesSettingsSnapshot,
    ExecutionCluster,
)
from src.orderflow.big_trades.reaction_zones import ReactionZoneObserver, create_reaction_zone
from src.orderflow.big_trades.runtime import RuntimeRecord
from src.orderflow.big_trades.settings import SettingsVersion
from webapp.big_trades_api import install_big_trades_api
from webapp.big_trades_backend import BigTradesBackend
from webapp.big_trades_history import BigTradesHistoryService
from webapp.big_trades_protocol import BigTradesBatcherV2


UTC = timezone.utc
BASE = datetime(2026, 8, 12, 1, 2, 3, tzinfo=UTC)


def _origin(index: int) -> BigTradeOriginStorageBatch:
    base = BASE + timedelta(seconds=index)
    settings = BigTradesSettingsSnapshot(
        settings_id="bts1_" + "1" * 64,
        symbol="BTCUSDT",
        venue="BINANCE",
        filter_mode=FilterMode.MANUAL,
        manual_min_quantity=Decimal("1"),
        activation_id="bta1_" + "2" * 64,
    )
    fills = (
        BigTradeFill(
            event_time=base,
            trade_time=base,
            trade_id=index * 10 + 1,
            symbol="BTCUSDT",
            venue="BINANCE",
            price=Decimal(100 + index),
            quantity=Decimal("2"),
            side="BUY" if index % 2 else "SELL",
        ),
        BigTradeFill(
            event_time=base + timedelta(milliseconds=20),
            trade_time=base + timedelta(milliseconds=20),
            trade_id=index * 10 + 2,
            symbol="BTCUSDT",
            venue="BINANCE",
            price=Decimal(101 + index),
            quantity=Decimal("3"),
            side="BUY" if index % 2 else "SELL",
        ),
    )
    cluster = ExecutionCluster(fills, settings, ClusterCloseReason.TIME_GAP_EXCEEDED)
    decision = ManualSizeFilter(Decimal("1"), Decimal("0")).decide(
        cluster.aggregate_quantity
    )
    event = create_big_trade_event(cluster, decision)
    zone = create_reaction_zone(event)
    created = ReactionZoneObserver(zone, tick_size=Decimal("0.1")).interactions[0]
    return BigTradeOriginStorageBatch.create(event, fills, zone, created)


def _populate_details(
    store: BigTradesDuckDbStore,
    first: BigTradeOriginStorageBatch,
    second: BigTradeOriginStorageBatch,
) -> None:
    zone_id = first.zone["zone_id"]
    store.insert_rows(
        batch_id="interaction-extra",
        kind="big_trade_zone_interactions",
        table_name="big_trade_zone_interactions",
        rows=(
            {
                "interaction_id": "bti2_" + "3" * 64,
                "zone_id": zone_id,
                "interaction_type": "FIRST_EXIT_UP",
                "source_event_time": BASE + timedelta(seconds=10),
                "source_trade_id": 99,
                "source_candle_id": None,
                "price": Decimal("110"),
                "previous_relation": "INSIDE",
                "current_relation": "ABOVE",
                "direction": "UP",
                "ordinal": 2,
                "gap_epoch_id": None,
                "content_hash": "3" * 64,
            },
        ),
    )
    store.insert_rows(
        batch_id="link-extra",
        kind="big_trade_zone_links",
        table_name="big_trade_zone_event_links",
        rows=(
            {
                "link_id": "btl2_" + "4" * 64,
                "zone_id": zone_id,
                "origin_event_id": first.event["event_id"],
                "linked_event_id": second.event["event_id"],
                "linked_side": second.event["side"],
                "linked_quantity": second.event["aggregate_quantity"],
                "linked_low": second.event["low_price"],
                "linked_high": second.event["high_price"],
                "linked_time": second.event["last_time"],
                "interval_gap_ticks": Decimal("0"),
                "same_as_origin_side": False,
                "ordinal_for_zone": 1,
                "content_hash": "4" * 64,
            },
        ),
    )
    snapshots = []
    for horizon, digit in ((5, "5"), (1, "6")):
        snapshots.append(
            {
                "snapshot_id": "btsnap2_" + digit * 64,
                "zone_id": zone_id,
                "horizon_seconds": horizon,
                "target_time": BASE + timedelta(seconds=horizon),
                "snapshot_trade_id": 100 + horizon,
                "snapshot_trade_time": BASE + timedelta(seconds=horizon),
                "source_age_ms": 0,
                "snapshot_price": Decimal("105"),
                "relation": "ABOVE",
                "return_last_bps": Decimal("1"),
                "return_vwap_bps": Decimal("1"),
                "origin_side_signed_return_bps": Decimal("1"),
                "max_above_ticks": Decimal(horizon),
                "max_below_ticks": Decimal("0"),
                "touch_count": 1,
                "cross_count": 0,
                "linked_event_count": 1,
                "inside_buy_quantity": Decimal("0"),
                "inside_sell_quantity": Decimal("0"),
                "validity": "VALID",
                "content_hash": digit * 64,
            }
        )
    store.insert_rows(
        batch_id="snapshots-extra",
        kind="big_trade_result_snapshots",
        table_name="big_trade_result_snapshots",
        rows=snapshots,
    )
    candles = []
    for minute, digit in ((2, "7"), (1, "8")):
        candles.append(
            {
                "candle_observation_id": "btcobs2_" + digit * 64,
                "zone_id": zone_id,
                "candle_id": BASE.replace(second=0) + timedelta(minutes=minute),
                "open_price": Decimal("100"),
                "high_price": Decimal("110"),
                "low_price": Decimal("90"),
                "close_price": Decimal("105"),
                "open_relation": "INSIDE",
                "close_relation": "ABOVE",
                "high_above_ticks": Decimal("10"),
                "low_below_ticks": Decimal("10"),
                "body_overlaps_zone": True,
                "wick_overlaps_zone": True,
                "closed_above": True,
                "closed_below": False,
                "upper_wick_return": False,
                "lower_wick_return": False,
                "content_hash": digit * 64,
            }
        )
    store.insert_rows(
        batch_id="candles-extra",
        kind="big_trade_zone_candles",
        table_name="big_trade_zone_candle_observations",
        rows=candles,
    )


def _app(backend: BigTradesBackend) -> FastAPI:
    app = FastAPI()
    app.state.big_trades_backend = backend
    install_big_trades_api(app)
    return app


@pytest.fixture
def backend(tmp_path: Path):
    store = BigTradesDuckDbStore(tmp_path / "big-trades.duckdb")
    first, second, third = _origin(1), _origin(2), _origin(3)
    for item in (first, second, third):
        store.insert_origin_batch(item)
    _populate_details(store, first, second)
    sent = []

    async def send(message):
        sent.append(message)

    batcher = BigTradesBatcherV2(send, symbol="BTCUSDT")
    history = BigTradesHistoryService(
        store,
        symbol="BTCUSDT",
        venue="BINANCE",
        recent_records=lambda: (),
    )
    artifacts = BigTradesArtifactRepository(tmp_path / "artifacts")
    service = BigTradesBackend(
        enabled=True,
        symbol="BTCUSDT",
        venue="BINANCE",
        quantity_step="0.001",
        store=store,
        artifacts=artifacts,
        history=history,
        batcher=batcher,
        now=lambda: datetime(2026, 8, 12, 4, tzinfo=UTC),
    )
    try:
        yield service, first, second, third, sent
    finally:
        store.close()


def test_bt2_w220_w221_history_is_oldest_first_with_exclusive_time_id_cursor(backend):
    service, first, second, third, _ = backend
    client = TestClient(_app(service))
    latest = client.get("/api/history/big-trades/zones", params={"limit": 2})
    assert latest.status_code == 200
    zones = latest.json()["zones"]
    assert [item["zone_id"] for item in zones] == [
        second.zone["zone_id"],
        third.zone["zone_id"],
    ]
    cursor = latest.json()["next_cursor"]
    older = client.get(
        "/api/history/big-trades/zones",
        params={
            "limit": 2,
            "before_source_time": cursor["before_source_time"],
            "before_id": cursor["before_id"],
        },
    )
    assert older.status_code == 200
    assert [item["zone_id"] for item in older.json()["zones"]] == [
        first.zone["zone_id"]
    ]


def test_bt2_w222_durable_recent_merge_dedup_and_collision(tmp_path: Path):
    store = BigTradesDuckDbStore(tmp_path / "merge.duckdb")
    origin = _origin(1)
    store.insert_origin_batch(origin)
    same = RuntimeRecord(
        "EVENT_CREATED",
        origin.event["last_time"],
        origin.event["last_trade_id"],
        origin.event["event_id"],
        origin.event["content_hash"],
        origin.event,
    )
    recent = [same]
    history = BigTradesHistoryService(
        store,
        symbol="BTCUSDT",
        venue="BINANCE",
        recent_records=lambda: recent,
    )
    try:
        assert len(history.list_events()["events"]) == 1
        recent[0] = RuntimeRecord(
            same.kind,
            same.source_event_time,
            same.source_trade_id,
            same.record_id,
            "f" * 64,
            same.payload,
        )
        with pytest.raises(BigTradesContentCollision):
            history.list_events()
    finally:
        store.close()


def test_rest_hydration_captures_stream_marker_before_committed_history(backend):
    service, first, _, _, _ = backend
    service.batcher.publish(
        (
            RuntimeRecord(
                "EVENT_CREATED",
                first.event["last_time"],
                first.event["last_trade_id"],
                first.event["event_id"],
                first.event["content_hash"],
                first.event,
            ),
        )
    )
    client = TestClient(_app(service))
    response = client.get(
        "/api/history/big-trades/snapshot",
        params={"event_limit": 3, "zone_limit": 3},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["continuation"] == {
        "stream_id": service.batcher.stream_id,
        "last_admitted_sequence": 1,
        "dropped_count": 0,
    }
    assert len(body["events"]) == 3
    assert len(body["zones"]) == 3


def test_bt2_w223_to_w228_zone_detail_and_lazy_orders(backend):
    service, first, _, _, _ = backend
    client = TestClient(_app(service))
    zone_id = first.zone["zone_id"]
    detail = client.get(f"/api/history/big-trades/zones/{zone_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["lineage_ids"] == {
        "event_id": first.event["event_id"],
        "zone_id": zone_id,
        "settings_id": first.zone["settings_id"],
        "calibration_id": None,
        "activation_id": first.zone["activation_id"],
        "logic_version": "BTLOGIC-2.0",
    }
    fills = client.get(
        f"/api/history/big-trades/events/{first.event['event_id']}/fills",
        params={"after_ordinal": 1},
    ).json()["fills"]
    assert [item["fill_ordinal"] for item in fills] == [2]
    interactions = client.get(
        f"/api/history/big-trades/zones/{zone_id}/interactions"
    ).json()["interactions"]
    assert [item["ordinal"] for item in interactions] == [1, 2]
    links = client.get(
        f"/api/history/big-trades/zones/{zone_id}/linked-events"
    ).json()["linked_events"]
    assert [item["ordinal_for_zone"] for item in links] == [1]
    snapshots = client.get(
        f"/api/history/big-trades/zones/{zone_id}/snapshots"
    ).json()["snapshots"]
    assert [item["horizon_seconds"] for item in snapshots] == [1, 5]
    candles = client.get(
        f"/api/history/big-trades/zones/{zone_id}/candles"
    ).json()["candles"]
    assert [item["candle_id"] for item in candles] == sorted(
        item["candle_id"] for item in candles
    )


def test_bt2_w229_w230_assessment_append_supersede_and_no_mutation_routes(backend):
    service, first, _, _, _ = backend
    client = TestClient(_app(service))
    zone_id = first.zone["zone_id"]
    base_body = {
        "assessment": "EFFORT_REWARDED",
        "assessed_against_source_time": "2026-08-12T01:02:04Z",
        "user_note": "first",
        "supersedes_assessment_id": None,
    }
    first_response = client.post(
        f"/api/big-trades/zones/{zone_id}/assessments", json=base_body
    )
    assert first_response.status_code == 201
    first_assessment = first_response.json()["assessment"]
    second_response = client.post(
        f"/api/big-trades/zones/{zone_id}/assessments",
        json={
            **base_body,
            "assessment": "EFFORT_NOT_REWARDED",
            "user_note": "corrected",
            "supersedes_assessment_id": first_assessment["assessment_id"],
        },
    )
    assert second_response.status_code == 201
    history = client.get(
        f"/api/history/big-trades/zones/{zone_id}/assessments"
    ).json()
    assert len(history["assessments"]) == 2
    assert history["latest"]["assessment"] == "EFFORT_NOT_REWARDED"
    assert client.put(
        f"/api/big-trades/zones/{zone_id}/assessments/{first_assessment['assessment_id']}",
        json={},
    ).status_code == 404
    assert client.delete(
        f"/api/big-trades/zones/{zone_id}/assessments/{first_assessment['assessment_id']}"
    ).status_code == 404


def test_bt2_w231_settings_put_is_strict_atomic_pending(backend):
    service, _, _, _, _ = backend
    client = TestClient(_app(service))
    body = {
        "filter_mode": "MANUAL",
        "manual_min_quantity": "20.000",
        "manual_max_quantity": "50.000",
        "automatic_intensity": "MEDIUM",
        "side_filter": "BOTH",
        "marker_price_mode": "LAST_PRICE",
        "calibration_id": None,
    }
    response = client.put("/api/big-trades/settings", json=body)
    assert response.status_code == 202
    assert response.json()["status"] == "PENDING"
    assert response.json()["activation_boundary"] == "NEXT_SOURCE_SESSION"
    assert client.get("/api/big-trades/settings").json()["active"] is None
    assert service.store.count("big_trade_settings_history") == 1
    rejected = client.put(
        "/api/big-trades/settings", json={**body, "manual_min_quantity": 20}
    )
    assert rejected.status_code == 422
    assert service.store.count("big_trade_settings_history") == 1


def test_bt2_w232_manual_calibration_activation_returns_pending(backend):
    from tests.orderflow.test_big_trades_artifacts import _calibration

    service, _, _, _, _ = backend
    calibration = _calibration(created_at=datetime(2026, 8, 11, tzinfo=UTC))
    service.artifacts.write_calibration(calibration)
    service.store.insert_rows(
        batch_id="calibration-api",
        kind="big_trade_calibration",
        table_name="big_trade_calibrations",
        rows=(calibration_to_row(calibration),),
    )
    active = SettingsVersion.create(
        symbol="BTCUSDT",
        venue="BINANCE",
        filter_mode="AUTOMATIC",
        manual_min_quantity="5",
        manual_max_quantity="0",
        automatic_intensity="MEDIUM",
        side_filter="BOTH",
        marker_price_mode="LAST_PRICE",
        calibration_id=None,
    )
    service.artifacts.write_settings_version(active)
    activation = ActivationArtifact.create(
        symbol="BTCUSDT",
        venue="BINANCE",
        effective_from_event_time=datetime(2026, 8, 12, tzinfo=UTC),
        effective_from_trade_id=1,
        settings_id=active.settings_id,
        calibration_id=None,
        activation_reason=ActivationReason.PRODUCTION_INITIAL,
        activation_policy=CalibrationActivationPolicy.MANUAL_ONLY,
        requested_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
    )
    service.artifacts.commit_activation(activation)
    client = TestClient(_app(service))
    response = client.post(
        f"/api/big-trades/calibrations/{calibration.calibration_id}/activate"
    )
    assert response.status_code == 202
    assert response.json() == {
        "status": "PENDING",
        "request_id": response.json()["request_id"],
        "settings_id": response.json()["settings_id"],
        "calibration_id": calibration.calibration_id,
        "activation_boundary": "NEXT_SOURCE_SESSION",
    }
    assert service.artifacts.load_pending_settings(
        symbol="BTCUSDT", venue="BINANCE"
    )[1].calibration_id == calibration.calibration_id
    assert service._active_settings().calibration_id is None


def test_bt2_w233_activation_history_is_get_only_and_immutable(backend):
    service, _, _, _, _ = backend
    version = SettingsVersion.create(
        symbol="BTCUSDT",
        venue="BINANCE",
        filter_mode="MANUAL",
        manual_min_quantity="5",
        manual_max_quantity="0",
        automatic_intensity="MEDIUM",
        side_filter="BOTH",
        marker_price_mode="LAST_PRICE",
    )
    service.artifacts.write_settings_version(version)
    activation = ActivationArtifact.create(
        symbol="BTCUSDT",
        venue="BINANCE",
        effective_from_event_time=datetime(2026, 8, 12, tzinfo=UTC),
        effective_from_trade_id=1,
        settings_id=version.settings_id,
        calibration_id=None,
        activation_reason=ActivationReason.PRODUCTION_INITIAL,
        activation_policy=CalibrationActivationPolicy.MANUAL_ONLY,
        requested_at_utc=datetime(2026, 8, 11, tzinfo=UTC),
    )
    service.artifacts.commit_activation(activation)
    client = TestClient(_app(service))
    listing = client.get("/api/big-trades/activations")
    assert listing.status_code == 200
    assert listing.json()["activations"][0]["activation_id"] == activation.activation_id
    detail = client.get(f"/api/big-trades/activations/{activation.activation_id}")
    assert detail.status_code == 200
    assert client.post("/api/big-trades/activations", json={}).status_code == 405
    assert client.put(
        f"/api/big-trades/activations/{activation.activation_id}", json={}
    ).status_code == 405


def test_bt2_w234_w235_explicit_error_semantics_and_disabled_health(backend):
    service, _, _, _, _ = backend
    client = TestClient(_app(service))
    invalid = client.get("/api/history/big-trades/events", params={"limit": 5001})
    assert invalid.status_code == 422
    assert invalid.json() == {
        "error_code": "BT_VALIDATION_ERROR",
        "reason": "limit must be between 1 and 5000",
        "affected_subsystem": "history",
    }
    bad_id = client.get("/api/history/big-trades/zones/not-an-id")
    assert bad_id.status_code == 422
    zone_id = service.history.list_zones(limit=1)["zones"][0]["zone_id"]
    invalid_assessment = client.post(
        f"/api/big-trades/zones/{zone_id}/assessments",
        json={
            "assessment": "NOT_IN_CLOSED_ENUM",
            "assessed_against_source_time": "2026-08-12T01:02:04Z",
            "user_note": "x" * 2001,
            "supersedes_assessment_id": None,
        },
    )
    assert invalid_assessment.status_code == 422
    assert service.store.count("big_trade_user_assessments") == 0
    disabled = BigTradesBackend.disabled(
        symbol="BTCUSDT", venue="BINANCE", quantity_step="0.001"
    )
    disabled_client = TestClient(_app(disabled))
    assert disabled_client.get("/api/big-trades/health").json()["status"] == "DISABLED"
    assert disabled_client.get("/api/history/big-trades/events").status_code == 503
