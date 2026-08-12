from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.database.schema import TRADES_DDL, TRADES_SCHEMA
from tools.recover_receiver_trades import (
    IncidentSpec,
    RecoveryError,
    TradeIdRange,
    apply_merge_bundle,
    build_merge_bundle,
    canonicalize_rest_rows,
    collect_rest_rows,
    load_incident_spec,
    stage_rest_rows,
)


UTC = timezone.utc
EVENT_MS = 1_754_974_506_168


def _spec(start: int = 10, end: int = 12) -> IncidentSpec:
    return IncidentSpec(
        schema_version=1,
        incident_id="test-incident",
        symbol="BTCUSDT",
        expected_trade_count=end - start + 1,
        ranges=(TradeIdRange(start, end),),
    )


def _raw(trade_id: int, *, price: str = "120000.10", maker: bool = False) -> dict:
    return {
        "id": trade_id,
        "price": price,
        "qty": "1.25000000",
        "quoteQty": "150000.125",
        "time": EVENT_MS + trade_id,
        "isBuyerMaker": maker,
        "isRPITrade": False,
    }


def _stage(tmp_path: Path, spec: IncidentSpec | None = None) -> tuple[Path, list[dict]]:
    selected = spec or _spec()
    raw_rows = [_raw(trade_id, maker=trade_id % 2 == 0) for trade_id in range(
        selected.ranges[0].start_id, selected.ranges[0].end_id + 1
    )]
    stage = tmp_path / "stage"
    stage_rest_rows(
        spec=selected,
        raw_rows=raw_rows,
        output_dir=stage,
        source="TEST_FIXTURE",
        accept_event_time_surrogate=True,
    )
    return stage, pq.read_table(stage / "trades.parquet").to_pylist()


def _create_db(path: Path, rows: list[dict] | None = None) -> None:
    connection = duckdb.connect(str(path))
    try:
        connection.execute(TRADES_DDL)
        if rows:
            table = pa.Table.from_pylist(rows, schema=TRADES_SCHEMA)
            connection.register("seed_rows", table)
            connection.execute("INSERT INTO trades SELECT * FROM seed_rows")
            connection.unregister("seed_rows")
    finally:
        connection.close()


def _write_trade_partition(root: Path, rows: list[dict], name: str = "part-seed.parquet") -> Path:
    when = rows[0]["event_time"].astimezone(UTC)
    day = (
        root
        / "symbol=BTCUSDT"
        / f"year={when.year:04d}"
        / f"month={when.month:02d}"
        / f"day={when.day:02d}"
    )
    day.mkdir(parents=True, exist_ok=True)
    target = day / name
    pq.write_table(pa.Table.from_pylist(rows, schema=TRADES_SCHEMA), target)
    return target


def test_production_incident_manifest_is_exact() -> None:
    root = Path(__file__).resolve().parents[2]
    path = root / "config/recovery/receiver_trade_gaps_20260812.json"
    spec = load_incident_spec(path)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert spec.symbol == "BTCUSDT"
    assert len(spec.ranges) == 28
    assert sum(item.count for item in spec.ranges) == 8_676
    assert payload["excluded"] == {
        "depth_messages": 412,
        "older_container_trade_messages": 50,
        "older_container_depth_messages": 1,
    }


def test_collection_paginates_exactly_and_rejects_shifted_ids() -> None:
    spec = _spec(1000, 1501)
    calls: list[tuple[int, int]] = []

    def fetch_page(from_id: int, limit: int) -> list[dict]:
        calls.append((from_id, limit))
        return [_raw(trade_id) for trade_id in range(from_id, from_id + limit)]

    rows = collect_rest_rows(spec, fetch_page)
    assert calls == [(1000, 500), (1500, 2)]
    assert [row["id"] for row in rows] == list(range(1000, 1502))

    with pytest.raises(RecoveryError, match="non-contiguous"):
        collect_rest_rows(_spec(), lambda start, limit: [_raw(i + 1) for i in range(start, start + limit)])


def test_canonical_mapping_requires_and_records_surrogate_semantics() -> None:
    with pytest.raises(RecoveryError, match="event time E"):
        canonicalize_rest_rows(
            [_raw(10)], symbol="BTCUSDT", accept_event_time_surrogate=False
        )

    buy, sell = canonicalize_rest_rows(
        [_raw(10, maker=False), _raw(11, maker=True)],
        symbol="BTCUSDT",
        accept_event_time_surrogate=True,
    )
    assert buy["event_time"] == buy["trade_time"]
    assert buy["event_time"].tzinfo == UTC
    assert buy["side"] == "BUY"
    assert sell["side"] == "SELL"
    assert buy["price"] == Decimal("120000.10")
    assert buy["quantity"] == Decimal("1.25000000")


def test_bundle_apply_and_repeat_are_idempotent(tmp_path: Path) -> None:
    stage, rows = _stage(tmp_path)
    database = tmp_path / "orderflow.duckdb"
    _create_db(database, [rows[1]])
    parquet_root = tmp_path / "parquet"
    _write_trade_partition(parquet_root, [rows[0]])

    bundle = tmp_path / "bundle"
    manifest = build_merge_bundle(
        stage_dir=stage,
        source_db=database,
        parquet_root=parquet_root,
        output_dir=bundle,
    )
    assert manifest["audit"]["duckdb"]["missing"] == 2
    assert manifest["audit"]["parquet"]["missing"] == 2
    assert manifest["audit"]["conflicts"] == 0

    first = apply_merge_bundle(
        bundle_dir=bundle,
        source_db=database,
        parquet_root=parquet_root,
        backup_dir=tmp_path / "backup-first",
        apply=True,
        maintenance_confirmed=True,
        accept_event_time_surrogate=True,
    )
    assert first["duckdb_rows_inserted"] == 2
    assert first["parquet_files_published"] == 1

    second = apply_merge_bundle(
        bundle_dir=bundle,
        source_db=database,
        parquet_root=parquet_root,
        backup_dir=tmp_path / "backup-second",
        apply=True,
        maintenance_confirmed=True,
        accept_event_time_surrogate=True,
    )
    assert second["duckdb_rows_inserted"] == 0
    assert second["parquet_files_published"] == 0
    assert second["parquet_files_already_present"] == 1

    connection = duckdb.connect(str(database), read_only=True)
    try:
        assert connection.execute("SELECT count(*) FROM trades").fetchone()[0] == 3
    finally:
        connection.close()
    files = list(parquet_root.rglob("*.parquet"))
    table = pa.concat_tables([pq.read_table(path, schema=TRADES_SCHEMA) for path in files])
    assert sorted(table.column("trade_id").to_pylist()) == [10, 11, 12]


def test_apply_conflict_rolls_back_new_parquet_publish(tmp_path: Path) -> None:
    spec = _spec(20, 20)
    stage, rows = _stage(tmp_path, spec)
    database = tmp_path / "orderflow.duckdb"
    _create_db(database)
    parquet_root = tmp_path / "parquet"
    parquet_root.mkdir()
    bundle = tmp_path / "bundle"
    build_merge_bundle(
        stage_dir=stage,
        source_db=database,
        parquet_root=parquet_root,
        output_dir=bundle,
    )

    conflicting = dict(rows[0])
    conflicting["price"] = Decimal("999.00")
    connection = duckdb.connect(str(database))
    try:
        table = pa.Table.from_pylist([conflicting], schema=TRADES_SCHEMA)
        connection.register("conflict_row", table)
        connection.execute("INSERT INTO trades SELECT * FROM conflict_row")
    finally:
        connection.close()

    backup = tmp_path / "backup"
    with pytest.raises(RecoveryError, match="DuckDB apply conflict"):
        apply_merge_bundle(
            bundle_dir=bundle,
            source_db=database,
            parquet_root=parquet_root,
            backup_dir=backup,
            apply=True,
            maintenance_confirmed=True,
            accept_event_time_surrogate=True,
        )

    assert list(parquet_root.rglob("recovery-*.parquet")) == []
    assert list((backup / "rolled-back-parquet").rglob("recovery-*.parquet"))
    connection = duckdb.connect(str(database), read_only=True)
    try:
        price = connection.execute("SELECT price FROM trades WHERE trade_id=20").fetchone()[0]
        assert price == Decimal("999.00000000")
    finally:
        connection.close()
