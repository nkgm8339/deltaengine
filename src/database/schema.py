"""Canonical storage schemas (single source, matching the specs).

Parquet: docs/40_Reference/ParquetSchema_v3.1.md (§3 Trade, §6 Candle, §4 Signal).
DuckDB:  docs/40_Reference/DuckDBDDL_v3.1.md (§2 trades, §5 candles, §3 signals).
Record fields: docs/40_Reference/MarketDataSchema_v3.1.md.

Phase5: CVD-path tables (trades, candles).
M11:    signals table added (SignalEngine output per confirmed bar).
        ai_results remains out of scope.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pyarrow as pa

# Shared Arrow types (ParquetSchema §2: UTC timestamps; DECIMAL(20,8)).
TIMESTAMP = pa.timestamp("us", tz="UTC")
DECIMAL = pa.decimal128(20, 8)

TRADES_SCHEMA = pa.schema(
    [
        ("event_time", TIMESTAMP),
        ("trade_time", TIMESTAMP),
        ("trade_id", pa.int64()),      # BIGINT
        ("symbol", pa.string()),
        ("price", DECIMAL),
        ("quantity", DECIMAL),
        ("side", pa.string()),
    ]
)

CANDLES_SCHEMA = pa.schema(
    [
        ("bar_time", TIMESTAMP),
        ("symbol", pa.string()),
        ("timeframe", pa.string()),
        ("open", DECIMAL),
        ("high", DECIMAL),
        ("low", DECIMAL),
        ("close", DECIMAL),
        ("volume", DECIMAL),
        ("delta", DECIMAL),
        ("cvd", DECIMAL),
    ]
)

# DuckDB DDL — verbatim from DuckDBDDL_v3.1 §2 / §5.
TRADES_DDL = """
CREATE TABLE IF NOT EXISTS trades (
    event_time TIMESTAMP,
    trade_time TIMESTAMP,
    trade_id BIGINT PRIMARY KEY,
    symbol VARCHAR,
    price DECIMAL(20,8),
    quantity DECIMAL(20,8),
    side VARCHAR
);
"""

CANDLES_DDL = """
CREATE TABLE IF NOT EXISTS candles (
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
);
"""

TRADES_COLUMNS = [f.name for f in TRADES_SCHEMA]
CANDLES_COLUMNS = [f.name for f in CANDLES_SCHEMA]

# --- signals (M11) -----------------------------------------------------------
# ParquetSchema_v3.1 §4 / DuckDBDDL_v3.1 §3.
# confidence is DOUBLE (not DECIMAL) per the spec — stored as float64 in Parquet.
# No PRIMARY KEY in the DDL (M11 decision 12): plain INSERT, no ON CONFLICT.
SIGNALS_SCHEMA = pa.schema(
    [
        ("signal_time", TIMESTAMP),
        ("symbol", pa.string()),
        ("signal", pa.string()),
        ("confidence", pa.float64()),    # DOUBLE per spec
    ]
)

SIGNALS_DDL = """
CREATE TABLE IF NOT EXISTS signals (
    signal_time TIMESTAMP,
    symbol VARCHAR,
    signal VARCHAR,
    confidence DOUBLE
);
"""

SIGNALS_COLUMNS = [f.name for f in SIGNALS_SCHEMA]


def signal_to_row(signal_time: datetime, symbol: str, signal_result: Any) -> dict:
    """SignalResult + metadata -> signals row dict (canonical column order).

    confidence is stored as float (DOUBLE per spec), not Decimal (decision 12).
    """
    return {
        "signal_time": signal_time,
        "symbol": symbol,
        "signal": signal_result.signal,
        "confidence": float(signal_result.confidence),
    }


def trade_to_row(trade: Any) -> dict:
    """NormalizedTrade -> trades row dict (canonical column order)."""
    return {
        "event_time": trade.event_time,
        "trade_time": trade.trade_time,
        "trade_id": trade.trade_id,
        "symbol": trade.symbol,
        "price": trade.price,
        "quantity": trade.quantity,
        "side": trade.side,
    }


def candle_to_row(candle: Any) -> dict:
    """Candle -> candles row dict (canonical column order)."""
    return {
        "bar_time": candle.bar_time,
        "symbol": candle.symbol,
        "timeframe": candle.timeframe,
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "volume": candle.volume,
        "delta": candle.delta,
        "cvd": candle.cvd,
    }
