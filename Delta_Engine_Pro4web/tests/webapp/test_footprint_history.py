"""Phase 1 Footprint history hydration and cursor contract."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.database.storage import StorageWriter
from src.orderflow.footprint import FootprintBar, PriceLevel
from webapp.history import query_footprints

UTC = timezone.utc
START = datetime(2026, 7, 28, 8, 15, tzinfo=UTC)


def _bar(minute: int) -> FootprintBar:
    base = Decimal("63500") + minute
    return FootprintBar(
        bar_time=START + timedelta(minutes=minute),
        symbol="BTCUSDT",
        timeframe="1m",
        levels=(
            PriceLevel(base, Decimal("1") + minute, Decimal("2") + minute),
            PriceLevel(base + Decimal("0.1"), Decimal("3") + minute, Decimal("4") + minute),
        ),
    )


def test_history_survives_writer_restart_and_pages_oldest_first(tmp_path) -> None:
    db_path = tmp_path / "duck" / "orderflow.duckdb"
    writer = StorageWriter(tmp_path / "parquet", db_path, batch_size=100)
    for minute in range(3):
        writer.add_footprint_bar(_bar(minute))
    writer.close()

    # query_footprints opens a new DuckDB connection: this is the restart path.
    latest = query_footprints(str(db_path), "BTCUSDT", "1m", limit=2)
    assert [row["bar_time"] for row in latest] == [
        (START + timedelta(minutes=1)).isoformat(),
        (START + timedelta(minutes=2)).isoformat(),
    ]
    assert all(row["level_count"] == 2 for row in latest)
    assert [level["price"] for level in latest[0]["levels"]] == [
        "63501.10000000",
        "63501.00000000",
    ]
    assert latest[0]["levels"][0]["bid"] == "5.00000000"
    assert latest[0]["levels"][0]["ask"] == "4.00000000"

    previous = query_footprints(
        str(db_path),
        "BTCUSDT",
        "1m",
        limit=2,
        before=latest[0]["bar_time"],
    )
    assert [row["bar_time"] for row in previous] == [START.isoformat()]


def test_history_is_empty_when_phase1_tables_do_not_exist(tmp_path) -> None:
    db_path = tmp_path / "empty.duckdb"
    assert query_footprints(str(db_path), "BTCUSDT", "1m") == []


def test_history_rejects_naive_before_cursor(tmp_path) -> None:
    db_path = tmp_path / "unused.duckdb"
    try:
        query_footprints(
            str(db_path),
            "BTCUSDT",
            "1m",
            before="2026-07-28T08:15:00",
        )
    except ValueError as exc:
        assert "timezone-aware" in str(exc)
    else:
        raise AssertionError("naive before cursor was accepted")
