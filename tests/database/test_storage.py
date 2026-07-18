"""Tests for src.database (M5).

Core criterion: written Parquet files and DuckDB tables match ParquetSchema_v3.1
/ DuckDBDDL_v3.1 exactly. Also covers batch/interval flush triggers, value
round-trip (Decimal precision), partition layout, and duplicate-PK handling.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pyarrow.parquet as pq

from src.database.schema import CANDLES_SCHEMA, SIGNALS_SCHEMA, TRADES_SCHEMA
from src.database.storage import StorageWriter

UTC = timezone.utc


def _trade_row(trade_id: int, ts=datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC)) -> dict:
    return {
        "event_time": ts, "trade_time": ts, "trade_id": trade_id, "symbol": "BTCUSDT",
        "price": Decimal("50000.5"), "quantity": Decimal("3"), "side": "BUY",
    }


def _candle_row(bar_time=datetime(2026, 1, 1, 0, 1, 0, tzinfo=UTC)) -> dict:
    return {
        "bar_time": bar_time, "symbol": "BTCUSDT", "timeframe": "1m",
        "open": Decimal("100000.00"), "high": Decimal("100050.00"),
        "low": Decimal("99980.00"), "close": Decimal("100020.00"),
        "volume": Decimal("12.5"), "delta": Decimal("0.8"), "cvd": Decimal("15.3"),
    }


def _one_parquet(base: Path) -> Path:
    files = list(base.rglob("*.parquet"))
    assert len(files) == 1, files
    return files[0]


def _read_file(base: Path):
    """Read the single written file directly (no dataset/partition inference)."""
    return pq.ParquetFile(str(_one_parquet(base))).read()


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def _writer(tmp_path: Path, **kw) -> StorageWriter:
    return StorageWriter(tmp_path / "parquet", tmp_path / "duck" / "of.duckdb", **kw)


# ============================ Parquet schema match ============================
def test_trades_parquet_schema_matches_spec(tmp_path: Path) -> None:
    sw = _writer(tmp_path, batch_size=10)
    sw.add_trade(_trade_row(1))
    sw.close()
    table = _read_file(tmp_path / "parquet")
    assert table.schema.equals(TRADES_SCHEMA, check_metadata=False)


def test_candles_parquet_schema_matches_spec(tmp_path: Path) -> None:
    sw = _writer(tmp_path, batch_size=10)
    sw.add_candle(_candle_row())
    sw.close()
    table = _read_file(tmp_path / "parquet")
    assert table.schema.equals(CANDLES_SCHEMA, check_metadata=False)


# ============================ DuckDB schema match =============================
def test_duckdb_trades_schema_matches_ddl(tmp_path: Path) -> None:
    sw = _writer(tmp_path)
    info = sw.duckdb.table_info("trades")
    sw.close()
    assert info == [
        ("event_time", "TIMESTAMP"), ("trade_time", "TIMESTAMP"), ("trade_id", "BIGINT"),
        ("symbol", "VARCHAR"), ("price", "DECIMAL(20,8)"), ("quantity", "DECIMAL(20,8)"),
        ("side", "VARCHAR"),
    ]


def test_duckdb_candles_schema_matches_ddl(tmp_path: Path) -> None:
    sw = _writer(tmp_path)
    info = sw.duckdb.table_info("candles")
    sw.close()
    assert info == [
        ("bar_time", "TIMESTAMP"), ("symbol", "VARCHAR"), ("timeframe", "VARCHAR"),
        ("open", "DECIMAL(20,8)"), ("high", "DECIMAL(20,8)"), ("low", "DECIMAL(20,8)"),
        ("close", "DECIMAL(20,8)"), ("volume", "DECIMAL(20,8)"), ("delta", "DECIMAL(20,8)"),
        ("cvd", "DECIMAL(20,8)"),
    ]


# ============================ value round-trip ================================
def test_candle_value_round_trip(tmp_path: Path) -> None:
    sw = _writer(tmp_path, batch_size=10)
    sw.add_candle(_candle_row())
    sw.close()
    table = _read_file(tmp_path / "parquet")
    row = table.to_pylist()[0]
    assert row["cvd"] == Decimal("15.3")           # precision preserved
    assert row["delta"] == Decimal("0.8")
    assert row["bar_time"] == datetime(2026, 1, 1, 0, 1, 0, tzinfo=UTC)
    assert row["timeframe"] == "1m"


# ============================ flush triggers ==================================
def test_flush_by_batch_size(tmp_path: Path) -> None:
    sw = _writer(tmp_path, batch_size=2)
    sw.add_trade(_trade_row(1))
    assert sw.flushes == 0            # below batch_size
    sw.add_trade(_trade_row(2))       # reaches batch_size -> auto flush
    assert sw.flushes == 1
    assert sw.trades_written == 2
    sw.close()


def test_flush_by_interval(tmp_path: Path) -> None:
    clock = FakeClock()
    sw = _writer(tmp_path, batch_size=1000, flush_interval_sec=5, clock=clock)
    sw.add_candle(_candle_row())
    clock.t = 3.0
    sw.tick()
    assert sw.flushes == 0            # interval not elapsed
    clock.t = 6.0
    sw.tick()
    assert sw.flushes == 1            # interval elapsed -> flush
    assert sw.candles_written == 1
    sw.close()


# ============================ partition layout ================================
def test_partition_layout(tmp_path: Path) -> None:
    sw = _writer(tmp_path, batch_size=10)
    sw.add_candle(_candle_row())
    sw.close()
    path = _one_parquet(tmp_path / "parquet")
    rel = path.relative_to(tmp_path / "parquet").as_posix()
    assert rel.startswith("symbol=BTCUSDT/timeframe=1m/year=2026/month=01/day=01/")


# ============================ signals (M11) ===================================
def _signal_row(ts=datetime(2026, 1, 1, 0, 1, 0, tzinfo=UTC)) -> dict:
    return {
        "signal_time": ts,
        "symbol": "BTCUSDT",
        "signal": "BUY",
        "confidence": 0.75,   # float (DOUBLE per spec, decision 12)
    }


def test_signals_parquet_schema_matches_spec(tmp_path: Path) -> None:
    sw = _writer(tmp_path, batch_size=10)
    sw.add_signal(_signal_row())
    sw.close()
    table = _read_file(tmp_path / "parquet")
    assert table.schema.equals(SIGNALS_SCHEMA, check_metadata=False)


def test_duckdb_signals_schema_matches_ddl(tmp_path: Path) -> None:
    sw = _writer(tmp_path)
    info = sw.duckdb.table_info("signals")
    sw.close()
    assert info == [
        ("signal_time", "TIMESTAMP"), ("symbol", "VARCHAR"),
        ("signal", "VARCHAR"), ("confidence", "DOUBLE"),
    ]


def test_signals_written_counter(tmp_path: Path) -> None:
    sw = _writer(tmp_path, batch_size=10)
    sw.add_signal(_signal_row())
    sw.add_signal(_signal_row())
    sw.close()
    assert sw.signals_written == 2


def test_signals_no_pk_allows_duplicate_insert(tmp_path: Path) -> None:
    """signals has no PRIMARY KEY (decision 12) — duplicate rows are stored."""
    sw = _writer(tmp_path, batch_size=10)
    sw.add_signal(_signal_row())
    sw.add_signal(_signal_row())  # identical row inserted twice
    sw.close()
    import duckdb as _ddb
    con = _ddb.connect(str(tmp_path / "duck" / "of.duckdb"), read_only=True)
    count = con.execute("SELECT count(*) FROM signals").fetchone()[0]
    con.close()
    assert count == 2   # both rows present — no dedup


# ============================ duplicate primary key ===========================
def test_duplicate_candle_pk_counted(tmp_path: Path) -> None:
    sw = _writer(tmp_path, batch_size=10)
    sw.add_candle(_candle_row())
    sw.flush()
    sw.add_candle(_candle_row())      # same (bar_time, symbol, timeframe)
    sw.flush()
    assert sw.duckdb.count("candles") == 1   # deduped on PK
    assert sw.duplicates == 1                 # counted, not silently lost
    sw.close()


def test_duplicate_trade_pk_counted(tmp_path: Path) -> None:
    sw = _writer(tmp_path, batch_size=10)
    sw.add_trade(_trade_row(1))
    sw.flush()
    sw.add_trade(_trade_row(1))       # same trade_id
    sw.flush()
    assert sw.duckdb.count("trades") == 1
    assert sw.duplicates == 1
    sw.close()
