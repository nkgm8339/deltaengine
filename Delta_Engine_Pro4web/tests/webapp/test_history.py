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

_FLOW_RESPONSE_EVENTS_DDL = """
CREATE TABLE flow_response_events (
    event_time TIMESTAMP,
    symbol VARCHAR,
    window_sec INTEGER,
    state VARCHAR,
    pressure_ratio DECIMAL(20,8),
    persistence DECIMAL(20,8),
    price_change_bps DECIMAL(20,8),
    relative_volume DECIMAL(20,8),
    buy_volume DECIMAL(20,8),
    sell_volume DECIMAL(20,8),
    delta DECIMAL(20,8),
    trade_count BIGINT
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
    assert result[0]["bar_time"].endswith("+00:00")
    assert result[0]["timeframe"] == "1m"
    assert "cvd" in result[0]
    assert isinstance(result[0]["cvd"], str)
    assert result[0]["vwap"] is None
    assert result[0]["vwap_status"] is None


def test_query_candles_filters_timeframe(tmp_path):
    db_path = str(tmp_path / "test.duckdb")
    con = duckdb.connect(db_path)
    con.execute(_CANDLES_DDL)
    con.execute(
        "INSERT INTO candles VALUES "
        "('2026-07-09 00:00:00', 'BTCUSDT', '1m', 100, 101, 99, 100, 10, 1, 1),"
        "('2026-07-09 00:00:00', 'BTCUSDT', '5m', 100, 105, 95, 104, 50, 5, 5)"
    )
    con.close()

    from webapp.history import query_candles
    result = query_candles(db_path, "BTCUSDT", limit=10, timeframe="5m")

    assert len(result) == 1
    assert result[0]["timeframe"] == "5m"


def test_query_flow_response_events_returns_chart_metrics(tmp_path):
    db_path = str(tmp_path / "test.duckdb")
    con = duckdb.connect(db_path)
    con.execute(_FLOW_RESPONSE_EVENTS_DDL)
    con.execute(
        "INSERT INTO flow_response_events VALUES "
        "('2026-07-09 00:00:30', 'BTCUSDT', 30, 'BUY_STALLED', 0.4, 0.7, "
        "0.2, 1.5, 8, 2, 6, 42)"
    )
    con.close()

    from webapp.history import query_flow_response_events
    result = query_flow_response_events(db_path, "BTCUSDT", limit=10)

    assert len(result) == 1
    assert result[0]["state"] == "BUY_STALLED"
    assert result[0]["total_volume"] == "10.00000000"
    assert result[0]["event_time"].endswith("+00:00")


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
