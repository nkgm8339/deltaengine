from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from src.acquisition.replay import ListTransport
from src.database.big_trades_storage import (
    BigTradesBackgroundStorageWriter,
    BigTradesDuckDbStore,
)
from src.normalization.normalizer import ExchangeProfile
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
from src.orderflow.big_trades.runtime import (
    BigTradesRuntimeV2,
    FixedActivationSettingsResolver,
    RuntimeMode,
)
from src.orderflow.big_trades.settings import SettingsVersion
from src.pipeline import LivePipeline, ReplayPipeline


UTC = timezone.utc
BASE_MS = 1_786_493_600_000
PROFILE = ExchangeProfile.from_dict(
    {
        "profile_name": "binance",
        "field_mapping": {
            "event_time": "E",
            "trade_time": "T",
            "trade_id": "a",
            "symbol": "s",
            "price": "p",
            "quantity": "q",
            "side_field": "m",
            "side_rule": "m == true → SELL, m == false → BUY",
        },
        "timestamp_format": "epoch_ms",
    }
)


def _raw(trade_id: int, offset_ms: int, quantity: str, maker: bool) -> dict:
    timestamp = BASE_MS + offset_ms
    return {
        "e": "aggTrade",
        "E": timestamp,
        "T": timestamp,
        "s": "BTCUSDT",
        "a": trade_id,
        "p": "100" if trade_id < 3 else "101",
        "q": quantity,
        "f": trade_id,
        "l": trade_id,
        "m": maker,
    }


def _write_replay(path: Path) -> None:
    rows = (
        _raw(1, 0, "6", False),
        _raw(2, 10, "6", False),
        _raw(3, 100, "1", True),
        _raw(4, 101, "1", True),
    )
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _pipeline(root: Path, runtime=None) -> ReplayPipeline:
    return ReplayPipeline(
        symbol="BTCUSDT",
        timeframe="1m",
        profile=PROFILE,
        parquet_path=root / "parquet",
        duckdb_path=root / "orderflow.duckdb",
        batch_size=10,
        flow_response_enabled=False,
        big_trades_runtime=runtime,
    )


def _enabled_runtime(root: Path, *, mode: RuntimeMode = RuntimeMode.REPLAY):
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
    effective = datetime.fromtimestamp(BASE_MS / 1000, tz=UTC)
    activation = ActivationArtifact.create(
        symbol="BTCUSDT",
        venue="BINANCE",
        effective_from_event_time=effective,
        effective_from_trade_id=0,
        settings_id=settings.settings_id,
        calibration_id=None,
        activation_reason=ActivationReason.USER_SETTINGS,
        activation_policy=CalibrationActivationPolicy.MANUAL_ONLY,
        requested_at_utc=effective,
    )
    store = BigTradesDuckDbStore(root / "big-trades.duckdb")
    writer = BigTradesBackgroundStorageWriter(store)
    runtime = BigTradesRuntimeV2(
        enabled=True,
        mode=mode,
        symbol="BTCUSDT",
        venue="BINANCE",
        tick_size=Decimal("0.1"),
        settings_resolver=FixedActivationSettingsResolver(settings, activation),
        storage_writer=writer,
        artifact_repository=BigTradesArtifactRepository(root / "artifacts"),
        horizons_seconds=(1,),
    )
    return store, writer, runtime


class _FakeConnect:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    async def __call__(self, url: str, streams: list[str]) -> ListTransport:
        return ListTransport(self.rows)


def test_replay_pipeline_enabled_keeps_existing_results_and_persists_big_trades(
    tmp_path: Path,
) -> None:
    replay_path = tmp_path / "fixture.jsonl"
    _write_replay(replay_path)
    baseline = _pipeline(tmp_path / "baseline").run(replay_path)
    store, writer, runtime = _enabled_runtime(tmp_path / "enabled")
    try:
        enabled = _pipeline(tmp_path / "enabled" / "existing", runtime).run(replay_path)
        assert enabled == baseline
        assert store.count("big_trade_events") == 1
        assert store.count("big_trade_event_fills") == 2
        assert store.count("big_trade_reaction_zones") == 1
        assert runtime.statistics()["origin_batches_committed"] == 1
    finally:
        writer.close()


def test_replay_pipeline_disabled_runtime_is_existing_output_equivalent(
    tmp_path: Path,
) -> None:
    replay_path = tmp_path / "fixture.jsonl"
    _write_replay(replay_path)
    baseline = _pipeline(tmp_path / "baseline").run(replay_path)
    disabled = BigTradesRuntimeV2(
        enabled=False,
        mode=RuntimeMode.REPLAY,
        symbol="BTCUSDT",
        venue="BINANCE",
        tick_size=Decimal("0.1"),
    )
    with_disabled = _pipeline(tmp_path / "disabled", disabled).run(replay_path)
    assert with_disabled == baseline
    assert disabled.statistics()["trades_observed"] == 0


def test_live_and_replay_pipeline_connections_persist_identical_big_trades(
    tmp_path: Path,
) -> None:
    replay_path = tmp_path / "fixture.jsonl"
    _write_replay(replay_path)
    rows = [json.loads(line) for line in replay_path.read_text(encoding="utf-8").splitlines()]
    replay_store, replay_writer, replay_runtime = _enabled_runtime(
        tmp_path / "replay", mode=RuntimeMode.REPLAY
    )
    live_store, live_writer, live_runtime = _enabled_runtime(
        tmp_path / "live", mode=RuntimeMode.LIVE
    )
    try:
        _pipeline(tmp_path / "replay" / "existing", replay_runtime).run(replay_path)
        live = LivePipeline(
            symbol="BTCUSDT",
            timeframe="1m",
            profile=PROFILE,
            ws_url="wss://test/ws",
            subscribe_streams=["btcusdt@aggTrade"],
            parquet_path=tmp_path / "live" / "existing" / "parquet",
            duckdb_path=tmp_path / "live" / "existing" / "orderflow.duckdb",
            batch_size=10,
            flush_interval_sec=1,
            reconnect=False,
            flow_response_enabled=False,
            big_trades_runtime=live_runtime,
        )
        live.run(connect=_FakeConnect(rows), poll_interval=0.01, fetch_snapshot=None)
        for table_name, order_by in (
            ("big_trade_events", "event_id"),
            ("big_trade_event_fills", "event_id, fill_ordinal"),
            ("big_trade_reaction_zones", "zone_id"),
            ("big_trade_zone_interactions", "zone_id, ordinal"),
        ):
            assert live_store.fetch_rows(table_name, order_by=order_by) == replay_store.fetch_rows(
                table_name, order_by=order_by
            )
    finally:
        replay_writer.close()
        live_writer.close()
