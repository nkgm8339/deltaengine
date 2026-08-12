"""Enabled/disabled Big Trades V2 application composition.

Construction is isolated so an enabled boot can be verified against temporary
DuckDB, Parquet, and artifact roots while the shipped production flag remains
false.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

import duckdb

from src.database.big_trades_storage import (
    BigTradesBackgroundStorageWriter,
    BigTradesDuckDbStore,
)
from src.orderflow.big_trades.activation import ReplayCalibrationMode
from src.orderflow.big_trades.artifacts import BigTradesArtifactRepository
from src.orderflow.big_trades.runtime import (
    BigTradesRuntimeV2,
    LiveActivationSettingsResolver,
    RecordedActivationSettingsResolver,
    RuntimeMode,
)
from src.orderflow.big_trades.models import BigTradeFill
from src.orderflow.big_trades.settings import SettingsVersion
from webapp.big_trades_backend import BigTradesBackend
from webapp.big_trades_history import BigTradesHistoryService
from webapp.big_trades_protocol import BigTradesBatcherV2


@dataclass
class BigTradesComposition:
    backend: BigTradesBackend
    runtime: Optional[BigTradesRuntimeV2] = None
    batcher: Optional[BigTradesBatcherV2] = None
    writer: Optional[BigTradesBackgroundStorageWriter] = None
    store: Optional[BigTradesDuckDbStore] = None
    artifacts: Optional[BigTradesArtifactRepository] = None

    @property
    def enabled(self) -> bool:
        return self.runtime is not None and self.runtime.enabled

    def close(self) -> None:
        if self.batcher is not None:
            self.batcher.close()
        if self.writer is not None:
            self.writer.close(drain=True, close_store=True)
        elif self.store is not None:
            self.store.close()


def _artifact_root(parquet_path: str | Path) -> Path:
    path = Path(parquet_path)
    return path.parent if path.name == "parquet" else path.parent / "artifacts"


def _aware_utc(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def _recovery_source_trades(
    store: BigTradesDuckDbStore,
    *,
    duckdb_path: Path,
    symbol: str,
    venue: str,
) -> tuple[str, tuple[BigTradeFill, ...]] | None:
    """Read only the source range needed to restore current active zones."""

    connection = duckdb.connect(str(duckdb_path))
    try:
        if not connection.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = 'trades'"
        ).fetchone()[0]:
            return None
        latest = connection.execute(
            "SELECT event_time FROM trades WHERE symbol = ? "
            "ORDER BY event_time DESC, trade_id DESC LIMIT 1",
            [symbol],
        ).fetchone()
        if latest is None:
            return None
        latest_time = _aware_utc(latest[0])
        session_id = latest_time.date().isoformat()
        zone_starts = [
            row["zone_source_start"]
            for row in store.fetch_rows("big_trade_reaction_zones")
            if row["symbol"] == symbol
            and row["venue"] == venue
            and row["session_id"] == session_id
        ]
        start_time = min(zone_starts) if zone_starts else latest_time
        rows = connection.execute(
            "SELECT event_time, trade_time, trade_id, price, quantity, side "
            "FROM trades WHERE symbol = ? AND event_time >= ? "
            "ORDER BY event_time, trade_id",
            [symbol, start_time.replace(tzinfo=None)],
        ).fetchall()
        trades = tuple(
            BigTradeFill(
                event_time=_aware_utc(row[0]),
                trade_time=_aware_utc(row[1]),
                trade_id=int(row[2]),
                symbol=symbol,
                venue=venue,
                price=Decimal(str(row[3])),
                quantity=Decimal(str(row[4])),
                side=str(row[5]),
            )
            for row in rows
            if _aware_utc(row[0]).date().isoformat() == session_id
        )
        return (session_id, trades) if trades else None
    finally:
        connection.close()


def build_big_trades_composition(
    config: Any,
    broker: Any,
    *,
    duckdb_path: str | Path | None = None,
    parquet_path: str | Path | None = None,
    artifact_root: str | Path | None = None,
) -> BigTradesComposition:
    big = config.big_trades
    symbol = config.market.symbol
    venue = config.market.exchange
    quantity_step = Decimal(str(big.quantity_step))
    if not big.enabled:
        return BigTradesComposition(
            backend=BigTradesBackend.disabled(
                symbol=symbol,
                venue=venue,
                quantity_step=quantity_step,
            )
        )

    resolved_duckdb = Path(duckdb_path or config.database.duckdb_path)
    resolved_parquet = Path(parquet_path or config.database.parquet_path)
    resolved_artifacts = Path(artifact_root or _artifact_root(resolved_parquet))
    store: Optional[BigTradesDuckDbStore] = None
    writer: Optional[BigTradesBackgroundStorageWriter] = None
    try:
        store = BigTradesDuckDbStore(
            resolved_duckdb,
            parquet_path=resolved_parquet,
        )
        writer = BigTradesBackgroundStorageWriter(store)
        artifacts = BigTradesArtifactRepository(resolved_artifacts)
        initial_settings = SettingsVersion.from_config(
            big,
            symbol=symbol,
            venue=venue,
        )
        replay_enabled = bool(config.replay.enabled)
        if replay_enabled:
            mode = ReplayCalibrationMode(big.replay_calibration_mode)
            if mode is not ReplayCalibrationMode.HISTORICAL_ACTIVATION:
                raise ValueError(
                    "FIXED_RESEARCH requires an explicit isolated research selection"
                )
            activations = tuple(
                item
                for item in artifacts.load_activations()
                if item.symbol == symbol and item.venue == venue
            )
            if not activations:
                raise ValueError("REPLAY_ACTIVATION_HISTORY_MISSING")
            settings = {
                item.settings_id: artifacts.load_settings_version(item.settings_id)
                for item in activations
            }
            calibrations = {
                item.calibration_id: artifacts.load_calibration(item.calibration_id)
                for item in settings.values()
                if item.calibration_id is not None
            }
            resolver = RecordedActivationSettingsResolver(
                activations=activations,
                settings=settings,
                calibrations=calibrations,
            )
            runtime_mode = RuntimeMode.REPLAY
        else:
            resolver = LiveActivationSettingsResolver(
                repository=artifacts,
                storage_writer=writer,
                initial_settings=initial_settings,
                quantity_step=quantity_step,
                calibration_schedule=big.calibration_schedule,
                activation_policy=big.calibration_activation_policy,
            )
            runtime_mode = RuntimeMode.LIVE

        batcher = BigTradesBatcherV2(
            broker.on_big_trades_update,
            symbol=symbol,
            interval_sec=big.batch_interval_ms / 1000.0,
            max_records_per_message=big.batch_max_records,
            pending_capacity=big.batch_pending_capacity,
        )
        runtime = BigTradesRuntimeV2(
            enabled=True,
            mode=runtime_mode,
            symbol=symbol,
            venue=venue,
            tick_size=Decimal(str(config.market.tick_size)),
            settings_resolver=resolver,
            storage_writer=writer,
            artifact_repository=artifacts,
            horizons_seconds=tuple(big.result_horizons_seconds),
            max_staleness_ms=big.result_snapshot_max_staleness_ms,
            zone_capacity=big.active_zone_capacity,
            link_tolerance_ticks=big.reaction_zone_match_tolerance_ticks,
            recent_capacity=max(
                big.recent_event_capacity,
                big.recent_interaction_capacity,
            ),
            max_fills_per_cluster=big.max_fills_per_cluster,
            publication_callback=batcher.publish,
        )
        if runtime_mode is RuntimeMode.LIVE and resolver.activation is not None:
            recovery = _recovery_source_trades(
                store,
                duckdb_path=resolved_duckdb,
                symbol=symbol,
                venue=venue,
            )
            if recovery is not None:
                runtime.recover_current_session(
                    session_id=recovery[0],
                    source_trades=recovery[1],
                )
        history = BigTradesHistoryService(
            store,
            symbol=symbol,
            venue=venue,
            max_limit=big.history_api_max_limit,
            recent_records=lambda: runtime.recent_records,
        )
        backend = BigTradesBackend(
            enabled=True,
            symbol=symbol,
            venue=venue,
            quantity_step=quantity_step,
            store=store,
            writer=writer,
            artifacts=artifacts,
            history=history,
            batcher=batcher,
            runtime=runtime,
        )
        return BigTradesComposition(
            backend=backend,
            runtime=runtime,
            batcher=batcher,
            writer=writer,
            store=store,
            artifacts=artifacts,
        )
    except Exception:
        if writer is not None:
            writer.close(drain=True, close_store=True)
        elif store is not None:
            store.close()
        raise
