"""Phase 1 confirmed Footprint persistence contract."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.database.schema import (
    FOOTPRINT_BAR_MANIFEST_SCHEMA,
    FOOTPRINT_LEVELS_SCHEMA,
    footprint_bar_to_storage,
)
from src.database.storage import BackgroundStorageWriter, DuckDbWriter, StorageError, StorageWriter
from src.orderflow.footprint import FootprintBar, PriceLevel

UTC = timezone.utc
BAR_TIME = datetime(2026, 7, 28, 8, 15, tzinfo=UTC)


def _bar(
    *,
    bar_time: datetime = BAR_TIME,
    levels: tuple[PriceLevel, ...] | None = None,
) -> FootprintBar:
    return FootprintBar(
        bar_time=bar_time,
        symbol="BTCUSDT",
        timeframe="1m",
        levels=levels or (
            PriceLevel(Decimal("63499.9"), Decimal("1.25"), Decimal("2.5")),
            PriceLevel(Decimal("63500.0"), Decimal("3.75"), Decimal("0.5")),
        ),
    )


def _tables(bar: FootprintBar) -> tuple[pa.Table, pa.Table]:
    batch = footprint_bar_to_storage(bar)
    return (
        pa.Table.from_pylist([batch.manifest], schema=FOOTPRINT_BAR_MANIFEST_SCHEMA),
        pa.Table.from_pylist(list(batch.levels), schema=FOOTPRINT_LEVELS_SCHEMA),
    )


def test_confirmed_bar_round_trip_daily_zstd_without_level_index(tmp_path) -> None:
    db_path = tmp_path / "duck" / "orderflow.duckdb"
    writer = StorageWriter(tmp_path / "parquet", db_path, batch_size=10)
    writer.add_footprint_bar(_bar())
    writer.close()

    assert writer.footprint_bars_written == 1
    assert writer.footprint_levels_written == 2
    assert writer.footprint_duplicates == 0

    with duckdb.connect(str(db_path), read_only=True) as con:
        manifest = con.execute(
            "SELECT level_count, buy_volume, sell_volume, content_hash "
            "FROM footprint_bar_manifest"
        ).fetchone()
        rows = con.execute(
            "SELECT price, buy_volume, sell_volume "
            "FROM footprint_levels ORDER BY price"
        ).fetchall()
        level_indexes = con.execute(
            "SELECT index_name FROM duckdb_indexes() "
            "WHERE table_name = 'footprint_levels'"
        ).fetchall()
    assert manifest[:3] == (2, Decimal("5.00000000"), Decimal("3.00000000"))
    assert len(manifest[3]) == 64
    assert rows == [
        (Decimal("63499.90000000"), Decimal("1.25000000"), Decimal("2.50000000")),
        (Decimal("63500.00000000"), Decimal("3.75000000"), Decimal("0.50000000")),
    ]
    assert level_indexes == []

    files = list((tmp_path / "parquet" / "footprint_levels").rglob("*.parquet"))
    assert len(files) == 1
    rel = files[0].relative_to(tmp_path / "parquet").as_posix()
    assert rel == (
        "footprint_levels/symbol=BTCUSDT/timeframe=1m/"
        "year=2026/month=07/day=28/levels.parquet"
    )
    archive = pq.ParquetFile(str(files[0]))
    assert archive.schema_arrow.equals(FOOTPRINT_LEVELS_SCHEMA, check_metadata=False)
    assert archive.metadata.num_rows == 2
    assert archive.metadata.row_group(0).column(0).compression == "ZSTD"


def test_duplicate_confirmed_bar_is_idempotent_in_db_and_archive(tmp_path) -> None:
    db_path = tmp_path / "duck" / "orderflow.duckdb"
    writer = StorageWriter(tmp_path / "parquet", db_path, batch_size=10)
    writer.add_footprint_bar(_bar())
    writer.flush()
    writer.add_footprint_bar(_bar())
    writer.flush()
    writer.close()

    assert writer.footprint_bars_written == 1
    assert writer.footprint_levels_written == 2
    assert writer.footprint_duplicates == 1
    with duckdb.connect(str(db_path), read_only=True) as con:
        assert con.execute("SELECT count(*) FROM footprint_bar_manifest").fetchone()[0] == 1
        assert con.execute("SELECT count(*) FROM footprint_levels").fetchone()[0] == 2
    archive_path = next((tmp_path / "parquet" / "footprint_levels").rglob("*.parquet"))
    assert pq.ParquetFile(str(archive_path)).metadata.num_rows == 2


def test_conflicting_duplicate_rolls_back_without_changing_original(tmp_path) -> None:
    db_path = tmp_path / "duck" / "orderflow.duckdb"
    duck = DuckDbWriter(db_path)
    original_manifest, original_levels = _tables(_bar())
    assert duck.insert_footprint_bar(original_manifest, original_levels) == 2

    changed = _bar(levels=(
        PriceLevel(Decimal("63499.9"), Decimal("9"), Decimal("2.5")),
        PriceLevel(Decimal("63500.0"), Decimal("3.75"), Decimal("0.5")),
    ))
    changed_manifest, changed_levels = _tables(changed)
    with pytest.raises(StorageError, match="conflicting or incomplete content"):
        duck.insert_footprint_bar(changed_manifest, changed_levels)

    assert duck.count("footprint_bar_manifest") == 1
    assert duck.count("footprint_levels") == 2
    rows = duck._con.execute(
        "SELECT buy_volume FROM footprint_levels ORDER BY price"
    ).fetchall()
    assert rows[0][0] == Decimal("1.25000000")
    duck.close()


@pytest.mark.parametrize(
    "bar, message",
    [
        (
            _bar(bar_time=datetime(2026, 7, 28, 8, 15)),
            "timezone-aware",
        ),
        (
            _bar(levels=(
                PriceLevel(Decimal("0"), Decimal("1"), Decimal("0")),
            )),
            "price must be positive",
        ),
        (
            _bar(levels=(
                PriceLevel(Decimal("1"), Decimal("-1"), Decimal("0")),
            )),
            "volume must be non-negative",
        ),
        (
            _bar(levels=(
                PriceLevel(Decimal("2"), Decimal("1"), Decimal("0")),
                PriceLevel(Decimal("1"), Decimal("1"), Decimal("0")),
            )),
            "strictly ascending",
        ),
        (
            _bar(levels=(
                PriceLevel(Decimal("1"), Decimal("1"), Decimal("0")),
                PriceLevel(Decimal("1"), Decimal("0"), Decimal("1")),
            )),
            "strictly ascending",
        ),
        (
            _bar(levels=(
                PriceLevel(Decimal("1000000000000"), Decimal("1"), Decimal("0")),
            )),
            "exceeds DECIMAL",
        ),
        (
            _bar(levels=(
                PriceLevel(Decimal("1"), Decimal("1000000000000"), Decimal("0")),
            )),
            "exceeds DECIMAL",
        ),
    ],
)
def test_storage_boundary_rejects_invalid_bar(bar, message) -> None:
    with pytest.raises(ValueError, match=message):
        footprint_bar_to_storage(bar)


def test_background_queue_accepts_one_bar_command_and_drains(tmp_path) -> None:
    db_path = tmp_path / "duck" / "orderflow.duckdb"
    writer = BackgroundStorageWriter(
        tmp_path / "parquet",
        db_path,
        batch_size=1000,
        flush_interval_sec=5,
        queue_depth=10,
    )
    writer.add_footprint_bar(_bar())
    writer.close()

    assert writer.footprint_bars_written == 1
    assert writer.footprint_levels_written == 2
    assert writer.high_watermark >= 1
    with duckdb.connect(str(db_path), read_only=True) as con:
        assert con.execute("SELECT count(*) FROM footprint_levels").fetchone()[0] == 2
