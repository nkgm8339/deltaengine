"""Raw official OI persistence and history-query coverage."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import duckdb
import pyarrow.parquet as pq
import pytest

from src.database.schema import OPEN_INTEREST_SAMPLES_SCHEMA
from src.database import storage as storage_module
from src.database.storage import StorageError, StorageWriter
from webapp.history import query_open_interest_samples

UTC = timezone.utc


def _row(source_time: datetime, value: str) -> dict:
    return {
        "source_time": source_time,
        "received_time": source_time,
        "symbol": "BTCUSDT",
        "open_interest": Decimal(value),
        "source": "BINANCE_USDM",
    }


def test_open_interest_sample_round_trips_to_parquet_and_duckdb(tmp_path) -> None:
    parquet_path = tmp_path / "parquet"
    db_path = tmp_path / "duck" / "orderflow.duckdb"
    first = datetime(2026, 7, 22, 8, 13, 20, tzinfo=UTC)
    second = datetime(2026, 7, 22, 8, 13, 30, tzinfo=UTC)
    writer = StorageWriter(parquet_path, db_path, batch_size=10)
    writer.add_open_interest_sample(_row(first, "103528.698"))
    writer.add_open_interest_sample(_row(second, "103518.771"))
    writer.close()

    files = list((parquet_path / "open_interest_samples").rglob("*.parquet"))
    assert len(files) == 1
    table = pq.ParquetFile(str(files[0])).read()
    assert table.schema.equals(OPEN_INTEREST_SAMPLES_SCHEMA, check_metadata=False)

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            "SELECT open_interest, source FROM open_interest_samples "
            "ORDER BY source_time"
        ).fetchall()
    finally:
        con.close()
    assert rows == [
        (Decimal("103528.69800000"), "BINANCE_USDM"),
        (Decimal("103518.77100000"), "BINANCE_USDM"),
    ]

    history = query_open_interest_samples(str(db_path), "BTCUSDT", 10)
    assert [row["open_interest"] for row in history] == [
        "103518.77100000",
        "103528.69800000",
    ]
    assert history[0]["source_time"] == "2026-07-22T08:13:30+00:00"


def test_open_interest_parquet_reuses_one_file_per_utc_hour(tmp_path) -> None:
    parquet_path = tmp_path / "parquet"
    db_path = tmp_path / "duck" / "orderflow.duckdb"
    first = datetime(2026, 7, 22, 8, 1, 0, tzinfo=UTC)
    second = datetime(2026, 7, 22, 8, 59, 50, tzinfo=UTC)

    writer = StorageWriter(parquet_path, db_path, batch_size=1)
    writer.add_open_interest_sample(_row(first, "100"))
    writer.close()
    writer = StorageWriter(parquet_path, db_path, batch_size=1)
    writer.add_open_interest_sample(_row(second, "101"))
    writer.close()

    files = list((parquet_path / "open_interest_samples").rglob("hour-*.parquet"))
    assert len(files) == 1
    table = pq.ParquetFile(str(files[0])).read()
    assert table.num_rows == 2


def test_open_interest_parquet_retries_transient_bad_file_descriptor(
    tmp_path, monkeypatch,
) -> None:
    parquet_path = tmp_path / "parquet"
    db_path = tmp_path / "duck" / "orderflow.duckdb"
    sample_time = datetime(2026, 7, 22, 8, 13, 20, tzinfo=UTC)
    real_write_table = storage_module.pq.write_table
    calls = 0

    def flaky_write_table(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError(9, "Bad file descriptor")
        return real_write_table(*args, **kwargs)

    monkeypatch.setattr(storage_module.pq, "write_table", flaky_write_table)
    monkeypatch.setattr(storage_module.time, "sleep", lambda _delay: None)

    writer = StorageWriter(parquet_path, db_path, batch_size=1)
    writer.add_open_interest_sample(_row(sample_time, "100"))
    writer.close()

    files = list((parquet_path / "open_interest_samples").rglob("hour-*.parquet"))
    assert calls == 2
    assert len(files) == 1
    assert pq.ParquetFile(str(files[0])).read().num_rows == 1
    assert not list((parquet_path / "open_interest_samples").rglob("*.tmp.parquet"))


def test_open_interest_parquet_exhausts_bounded_transient_retries(
    tmp_path, monkeypatch,
) -> None:
    parquet_path = tmp_path / "parquet"
    db_path = tmp_path / "duck" / "orderflow.duckdb"
    sample_time = datetime(2026, 7, 22, 8, 13, 20, tzinfo=UTC)
    calls = 0

    def broken_write_table(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise OSError(9, "Bad file descriptor")

    monkeypatch.setattr(storage_module.pq, "write_table", broken_write_table)
    monkeypatch.setattr(storage_module.time, "sleep", lambda _delay: None)

    writer = StorageWriter(parquet_path, db_path, batch_size=10)
    try:
        with pytest.raises(StorageError, match="OI parquet write failed"):
            writer._write_open_interest_parquet([_row(sample_time, "100")])
    finally:
        writer.close()

    assert calls == 4
    assert not list((parquet_path / "open_interest_samples").rglob("*.parquet"))


def test_open_interest_history_is_empty_before_table_exists(tmp_path) -> None:
    db_path = tmp_path / "empty.duckdb"
    assert query_open_interest_samples(str(db_path), "BTCUSDT", 10) == []
