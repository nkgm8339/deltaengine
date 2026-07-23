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
from decimal import Decimal
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

# --- open-interest raw observations -----------------------------------------
# Binance USD-M Futures snapshots are stored independently from candles so the
# original exchange observation remains available for later as-of joins and
# recalculation. Missing polls stay missing; no forward-filled value is stored.
OPEN_INTEREST_SAMPLES_SCHEMA = pa.schema(
    [
        ("source_time", TIMESTAMP),
        ("received_time", TIMESTAMP),
        ("symbol", pa.string()),
        ("open_interest", DECIMAL),
        ("source", pa.string()),
    ]
)

OPEN_INTEREST_SAMPLES_DDL = """
CREATE TABLE IF NOT EXISTS open_interest_samples (
    source_time TIMESTAMP,
    received_time TIMESTAMP,
    symbol VARCHAR,
    open_interest DECIMAL(20,8),
    source VARCHAR,
    PRIMARY KEY (source_time, symbol)
);
"""

OPEN_INTEREST_SAMPLES_COLUMNS = [f.name for f in OPEN_INTEREST_SAMPLES_SCHEMA]

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


_SCALE_8 = Decimal("0.00000001")


def _q8(value: Any):
    """Quantize derived Decimal metrics to the storage schema's scale."""
    if value is None:
        return None
    parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    return parsed.quantize(_SCALE_8)


# --- flow/price response research records ------------------------------------
# These tables preserve observations and raw forward outcomes. They contain no
# predicted probability and no inferred trade instruction.
FLOW_RESPONSE_EVENTS_SCHEMA = pa.schema(
    [
        ("event_time", TIMESTAMP),
        ("symbol", pa.string()),
        ("window_sec", pa.int32()),
        ("state", pa.string()),
        ("pressure_side", pa.string()),
        ("buy_volume", DECIMAL),
        ("sell_volume", DECIMAL),
        ("delta", DECIMAL),
        ("pressure_ratio", DECIMAL),
        ("persistence", DECIMAL),
        ("first_price", DECIMAL),
        ("last_price", DECIMAL),
        ("price_change", DECIMAL),
        ("price_change_bps", DECIMAL),
        ("relative_volume", DECIMAL),
        ("trade_count", pa.int64()),
    ]
)

FLOW_RESPONSE_EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS flow_response_events (
    event_time TIMESTAMP,
    symbol VARCHAR,
    window_sec INTEGER,
    state VARCHAR,
    pressure_side VARCHAR,
    buy_volume DECIMAL(20,8),
    sell_volume DECIMAL(20,8),
    delta DECIMAL(20,8),
    pressure_ratio DECIMAL(20,8),
    persistence DECIMAL(20,8),
    first_price DECIMAL(20,8),
    last_price DECIMAL(20,8),
    price_change DECIMAL(20,8),
    price_change_bps DECIMAL(20,8),
    relative_volume DECIMAL(20,8),
    trade_count BIGINT,
    PRIMARY KEY (event_time, symbol, window_sec)
);
"""

FLOW_RESPONSE_OUTCOMES_SCHEMA = pa.schema(
    [
        ("event_time", TIMESTAMP),
        ("symbol", pa.string()),
        ("window_sec", pa.int32()),
        ("state", pa.string()),
        ("horizon_sec", pa.int32()),
        ("observed_price", DECIMAL),
        ("outcome_time", TIMESTAMP),
        ("outcome_price", DECIMAL),
        ("forward_return_bps", DECIMAL),
        ("max_up_bps", DECIMAL),
        ("max_down_bps", DECIMAL),
    ]
)

FLOW_RESPONSE_OUTCOMES_DDL = """
CREATE TABLE IF NOT EXISTS flow_response_outcomes (
    event_time TIMESTAMP,
    symbol VARCHAR,
    window_sec INTEGER,
    state VARCHAR,
    horizon_sec INTEGER,
    observed_price DECIMAL(20,8),
    outcome_time TIMESTAMP,
    outcome_price DECIMAL(20,8),
    forward_return_bps DECIMAL(20,8),
    max_up_bps DECIMAL(20,8),
    max_down_bps DECIMAL(20,8),
    PRIMARY KEY (event_time, symbol, window_sec, horizon_sec)
);
"""


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


def flow_response_event_to_row(snapshot: Any) -> dict:
    return {
        "event_time": snapshot.event_time,
        "symbol": snapshot.symbol,
        "window_sec": snapshot.window_sec,
        "state": snapshot.state.value,
        "pressure_side": snapshot.pressure_side,
        "buy_volume": snapshot.buy_volume,
        "sell_volume": snapshot.sell_volume,
        "delta": snapshot.delta,
        "pressure_ratio": _q8(snapshot.pressure_ratio),
        "persistence": _q8(snapshot.persistence),
        "first_price": snapshot.first_price,
        "last_price": snapshot.last_price,
        "price_change": snapshot.price_change,
        "price_change_bps": _q8(snapshot.price_change_bps),
        "relative_volume": _q8(snapshot.relative_volume),
        "trade_count": snapshot.trade_count,
    }


def flow_response_outcome_to_row(outcome: Any) -> dict:
    return {
        "event_time": outcome.event_time,
        "symbol": outcome.symbol,
        "window_sec": outcome.window_sec,
        "state": outcome.state.value,
        "horizon_sec": outcome.horizon_sec,
        "observed_price": outcome.observed_price,
        "outcome_time": outcome.outcome_time,
        "outcome_price": outcome.outcome_price,
        "forward_return_bps": _q8(outcome.forward_return_bps),
        "max_up_bps": _q8(outcome.max_up_bps),
        "max_down_bps": _q8(outcome.max_down_bps),
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
