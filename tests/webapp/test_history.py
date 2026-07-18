"""Tests for DuckDB history query helpers."""
import duckdb
import pytest


_CANDLES_DDL = """
CREATE TABLE candles (
    bar_time TIMESTAMP,
    symbol VARCHAR,
    timeframe VARCHAR,
    open DECIMAL(20,8),
    high DECIMAL(20,8),
    low DECIMAL(20,8),
    close DECIMAL(20,8),
    volume DECIMAL(20,8),
    delta DECIMAL(20,8),
    cvd DECIMAL(20,8),
    PRIMARY KEY (bar_time, symbol, timeframe)
)
"""

_SIGNALS_DDL = """
CREATE TABLE signals (
    signal_time TIMESTAMP,
    symbol VARCHAR,
    signal VARCHAR,
    confidence DOUBLE
)
"""

_TRADES_DDL = """
CREATE TABLE trades (
    event_time TIMESTAMP,
    trade_time TIMESTAMP,
    trade_id BIGINT PRIMARY KEY,
    symbol VARCHAR,
    price DECIMAL(20,8),
    quantity DECIMAL(20,8),
    side VARCHAR
)
"""


def test_query_candles_returns_list(tmp_path):
    db_path = str(tmp_path / "test.duckdb")
    con = duckdb.connect(db_path)
    con.execute(_CANDLES_DDL)
    con.execute(
        "INSERT INTO candles VALUES "
        "('2026-07-09 00:00:00', 'BTCUSDT', '1m', 100.0, 110.0, 90.0, 105.0, 1000.0, 50.0, 200.0)"
    )
    con.close()

    from webapp.history import query_candles
    result = query_candles(db_path, "BTCUSDT", limit=10)

    assert isinstance(result, list)
    assert len(result) == 1
    assert "bar_time" in result[0]
    assert "cvd" in result[0]
    assert isinstance(result[0]["cvd"], str)


def test_query_signals_returns_list(tmp_path):
    db_path = str(tmp_path / "test.duckdb")
    con = duckdb.connect(db_path)
    con.execute(_SIGNALS_DDL)
    con.execute(
        "INSERT INTO signals VALUES ('2026-07-09 00:01:00', 'BTCUSDT', 'BUY', 0.75)"
    )
    con.close()

    from webapp.history import query_signals
    result = query_signals(db_path, "BTCUSDT", limit=10)

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["signal"] == "BUY"
    assert isinstance(result[0]["confidence"], str)


def test_query_trades_returns_list(tmp_path):
    db_path = str(tmp_path / "test.duckdb")
    con = duckdb.connect(db_path)
    con.execute(_TRADES_DDL)
    con.execute(
        "INSERT INTO trades VALUES "
        "('2026-07-09 00:00:01', '2026-07-09 00:00:01', 1001, 'BTCUSDT', 50000.0, 0.1, 'BUY')"
    )
    con.close()

    from webapp.history import query_trades
    result = query_trades(db_path, "BTCUSDT", limit=10)

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["side"] == "BUY"
    assert isinstance(result[0]["price"], str)
