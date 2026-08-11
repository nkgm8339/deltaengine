from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.database.schema import TRADES_SCHEMA
from tools.backfill_big_trades import build_dry_run_report, select_completed_trade_files


UTC = timezone.utc
BASE = datetime(2026, 8, 11, 1, 2, 3, tzinfo=UTC)


def _write_trade_file(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows, schema=TRADES_SCHEMA), path)


def _trade(trade_id: int, offset_ms: int, quantity: str, side: str, price: str) -> dict:
    source_time = BASE + timedelta(milliseconds=offset_ms)
    return {
        "event_time": source_time,
        "trade_time": source_time,
        "trade_id": trade_id,
        "symbol": "BTCUSDT",
        "price": Decimal(price),
        "quantity": Decimal(quantity),
        "side": side,
    }


def _source_db(path: Path) -> None:
    connection = duckdb.connect(str(path))
    connection.execute(
        "CREATE TABLE trades (event_time TIMESTAMP, trade_time TIMESTAMP, "
        "trade_id BIGINT, symbol VARCHAR, price DECIMAL(20,8), "
        "quantity DECIMAL(20,8), side VARCHAR)"
    )
    connection.close()


def test_dry_run_reports_actual_isolated_predictions_and_deletes_output(tmp_path: Path) -> None:
    root = tmp_path / "parquet"
    day = root / "symbol=BTCUSDT" / "year=2026" / "month=08" / "day=11"
    _write_trade_file(
        day / "part-000001.parquet",
        [_trade(1, 0, "3", "BUY", "100"), _trade(2, 10, "3", "BUY", "100.1")],
    )
    _write_trade_file(
        day / "part-000002.parquet",
        [_trade(3, 100, "1", "SELL", "101"), _trade(4, 2_000, "1", "SELL", "102")],
    )
    source_db = tmp_path / "orderflow.duckdb"
    _source_db(source_db)

    report = build_dry_run_report(
        source_db=source_db,
        parquet_root=root,
        symbol="BTCUSDT",
        venue="BINANCE",
        tick_size=Decimal("0.1"),
        manual_min_quantity=Decimal("5"),
        manual_max_quantity=Decimal("0"),
        max_trade_files=2,
        safety_lag_seconds=0,
        horizons_seconds=(1,),
    )

    assert report["status"] == "PASS"
    assert report["input"]["trade_count"] == 4
    assert report["predicted_counts"]["clusters"] == 3
    assert report["predicted_counts"]["accepted_events"] == 1
    assert report["predicted_counts"]["event_fills"] == 2
    assert report["predicted_counts"]["reaction_zones"] == 1
    assert report["predicted_counts"]["result_snapshots"] == 1
    assert report["versions"]["replay_calibration_mode"] == "FIXED_RESEARCH"
    assert report["versions"]["production_activation"] is False
    assert report["disk_estimate"]["isolated_duckdb_bytes"] > 0
    assert report["disk_estimate"]["temporary_output_deleted"] is True
    assert report["production_mutations"] == 0
    assert report["production_backfill_performed"] is False


def test_selection_ignores_non_trade_parquet_schema(tmp_path: Path) -> None:
    root = tmp_path / "parquet"
    day = root / "symbol=BTCUSDT" / "year=2026" / "month=08" / "day=11"
    day.mkdir(parents=True)
    pq.write_table(
        pa.table({"signal_time": [BASE], "symbol": ["BTCUSDT"], "signal": ["BUY"]}),
        day / "part-000002.parquet",
    )
    _write_trade_file(day / "part-000001.parquet", [_trade(1, 0, "1", "BUY", "100")])

    selected, inspected = select_completed_trade_files(
        root,
        symbol="BTCUSDT",
        max_trade_files=1,
        safety_lag_seconds=0,
    )

    assert selected == ((day / "part-000001.parquet").resolve(),)
    assert inspected == 2


def test_selection_fails_closed_when_no_trade_shard_exists(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="no completed trade"):
        select_completed_trade_files(
            tmp_path,
            symbol="BTCUSDT",
            max_trade_files=1,
            safety_lag_seconds=0,
        )
