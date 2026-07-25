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

# --- native execution-timeframe Flow research records -----------------------
# Separate from the completed rolling-window tables. timeframe is part of every
# key so 5m and 10m observations cannot collide or be mixed.
NATIVE_FLOW_EVENTS_SCHEMA = pa.schema([
    ("event_time", TIMESTAMP), ("symbol", pa.string()), ("timeframe", pa.string()),
    ("state", pa.string()), ("pressure_side", pa.string()),
    ("buy_volume", DECIMAL), ("sell_volume", DECIMAL), ("delta", DECIMAL),
    ("pressure_ratio", DECIMAL), ("first_price", DECIMAL), ("last_price", DECIMAL),
    ("price_change_bps", DECIMAL), ("trade_count", pa.int64()),
])
NATIVE_FLOW_EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS native_flow_events (
    event_time TIMESTAMP, symbol VARCHAR, timeframe VARCHAR, state VARCHAR,
    pressure_side VARCHAR, buy_volume DECIMAL(20,8), sell_volume DECIMAL(20,8),
    delta DECIMAL(20,8), pressure_ratio DECIMAL(20,8), first_price DECIMAL(20,8),
    last_price DECIMAL(20,8), price_change_bps DECIMAL(20,8), trade_count BIGINT,
    PRIMARY KEY (event_time, symbol, timeframe)
);
"""
NATIVE_FLOW_OUTCOMES_SCHEMA = pa.schema([
    ("event_time", TIMESTAMP), ("symbol", pa.string()), ("timeframe", pa.string()),
    ("state", pa.string()), ("horizon_sec", pa.int32()), ("observed_price", DECIMAL),
    ("outcome_time", TIMESTAMP), ("outcome_price", DECIMAL),
    ("forward_return_bps", DECIMAL), ("max_up_bps", DECIMAL), ("max_down_bps", DECIMAL),
])
NATIVE_FLOW_OUTCOMES_DDL = """
CREATE TABLE IF NOT EXISTS native_flow_outcomes (
    event_time TIMESTAMP, symbol VARCHAR, timeframe VARCHAR, state VARCHAR,
    horizon_sec INTEGER, observed_price DECIMAL(20,8), outcome_time TIMESTAMP,
    outcome_price DECIMAL(20,8), forward_return_bps DECIMAL(20,8),
    max_up_bps DECIMAL(20,8), max_down_bps DECIMAL(20,8),
    PRIMARY KEY (event_time, symbol, timeframe, horizon_sec)
);
"""


def native_flow_event_to_row(snapshot: Any) -> dict:
    return {
        "event_time": snapshot.event_time, "symbol": snapshot.symbol,
        "timeframe": snapshot.timeframe, "state": snapshot.state.value,
        "pressure_side": snapshot.pressure_side, "buy_volume": snapshot.buy_volume,
        "sell_volume": snapshot.sell_volume, "delta": snapshot.delta,
        "pressure_ratio": _q8(snapshot.pressure_ratio),
        "first_price": snapshot.first_price, "last_price": snapshot.last_price,
        "price_change_bps": _q8(snapshot.price_change_bps),
        "trade_count": snapshot.trade_count,
    }


def native_flow_outcome_to_row(outcome: Any) -> dict:
    return {
        "event_time": outcome.event_time, "symbol": outcome.symbol,
        "timeframe": outcome.timeframe, "state": outcome.state.value,
        "horizon_sec": outcome.horizon_sec, "observed_price": outcome.observed_price,
        "outcome_time": outcome.outcome_time, "outcome_price": outcome.outcome_price,
        "forward_return_bps": _q8(outcome.forward_return_bps),
        "max_up_bps": _q8(outcome.max_up_bps), "max_down_bps": _q8(outcome.max_down_bps),
    }


# --- PRICE/CVD/Delta/OI context + executable HFM outcomes -------------------
# New tables are intentionally separate from candles/native_flow_* so the
# existing research records and their primary keys remain unchanged.
COMBINED_CONTEXT_EVENTS_SCHEMA = pa.schema([
    ("event_time", TIMESTAMP), ("bar_time", TIMESTAMP),
    ("symbol", pa.string()), ("timeframe", pa.string()),
    ("pattern_no", pa.int8()), ("pattern_name", pa.string()),
    ("price_direction", pa.int8()), ("cvd_direction", pa.int8()),
    ("delta_direction", pa.int8()), ("oi_direction", pa.string()),
    ("oi_open", DECIMAL), ("oi_close", DECIMAL), ("oi_change", DECIMAL),
    ("oi_change_pct", DECIMAL), ("oi_sample_count", pa.int32()),
    ("context_code", pa.string()), ("context_title", pa.string()),
    ("context_summary_ja", pa.string()), ("hfm_entry_status", pa.string()),
    ("hfm_symbol", pa.string()), ("hfm_entry_time", TIMESTAMP),
    ("hfm_entry_source_time", TIMESTAMP), ("hfm_entry_sequence", pa.int64()),
    ("hfm_entry_bid", DECIMAL), ("hfm_entry_ask", DECIMAL),
    ("hfm_entry_spread", DECIMAL), ("hfm_entry_age_ms", pa.int64()),
])
COMBINED_CONTEXT_EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS combined_context_events (
    event_time TIMESTAMP, bar_time TIMESTAMP, symbol VARCHAR, timeframe VARCHAR,
    pattern_no TINYINT, pattern_name VARCHAR, price_direction TINYINT,
    cvd_direction TINYINT, delta_direction TINYINT, oi_direction VARCHAR,
    oi_open DECIMAL(20,8), oi_close DECIMAL(20,8), oi_change DECIMAL(20,8),
    oi_change_pct DECIMAL(20,8), oi_sample_count INTEGER,
    context_code VARCHAR, context_title VARCHAR, context_summary_ja VARCHAR,
    hfm_entry_status VARCHAR, hfm_symbol VARCHAR, hfm_entry_time TIMESTAMP,
    hfm_entry_source_time TIMESTAMP, hfm_entry_sequence BIGINT,
    hfm_entry_bid DECIMAL(20,8), hfm_entry_ask DECIMAL(20,8),
    hfm_entry_spread DECIMAL(20,8), hfm_entry_age_ms BIGINT,
    PRIMARY KEY (event_time, symbol, timeframe)
);
"""

HFM_CONTEXT_OUTCOMES_SCHEMA = pa.schema([
    ("event_time", TIMESTAMP), ("symbol", pa.string()),
    ("timeframe", pa.string()), ("context_code", pa.string()),
    ("horizon_sec", pa.int32()), ("status", pa.string()),
    ("hfm_symbol", pa.string()), ("entry_time", TIMESTAMP),
    ("entry_source_time", TIMESTAMP), ("entry_bid", DECIMAL),
    ("entry_ask", DECIMAL), ("outcome_time", TIMESTAMP),
    ("outcome_source_time", TIMESTAMP), ("outcome_bid", DECIMAL),
    ("outcome_ask", DECIMAL), ("quote_lag_ms", pa.int64()),
    ("long_net_usd", DECIMAL), ("short_net_usd", DECIMAL),
    ("long_return_bps", DECIMAL), ("short_return_bps", DECIMAL),
    ("long_mfe_usd", DECIMAL), ("long_mae_usd", DECIMAL),
    ("short_mfe_usd", DECIMAL), ("short_mae_usd", DECIMAL),
])
HFM_CONTEXT_OUTCOMES_DDL = """
CREATE TABLE IF NOT EXISTS hfm_context_outcomes (
    event_time TIMESTAMP, symbol VARCHAR, timeframe VARCHAR,
    context_code VARCHAR, horizon_sec INTEGER, status VARCHAR,
    hfm_symbol VARCHAR, entry_time TIMESTAMP, entry_source_time TIMESTAMP,
    entry_bid DECIMAL(20,8), entry_ask DECIMAL(20,8),
    outcome_time TIMESTAMP, outcome_source_time TIMESTAMP,
    outcome_bid DECIMAL(20,8), outcome_ask DECIMAL(20,8),
    quote_lag_ms BIGINT, long_net_usd DECIMAL(20,8),
    short_net_usd DECIMAL(20,8), long_return_bps DECIMAL(20,8),
    short_return_bps DECIMAL(20,8), long_mfe_usd DECIMAL(20,8),
    long_mae_usd DECIMAL(20,8), short_mfe_usd DECIMAL(20,8),
    short_mae_usd DECIMAL(20,8),
    PRIMARY KEY (event_time, symbol, timeframe, horizon_sec)
);
"""


def combined_context_event_to_row(event: Any) -> dict:
    quote = event.hfm_entry
    return {
        "event_time": event.event_time, "bar_time": event.bar_time,
        "symbol": event.symbol, "timeframe": event.timeframe,
        "pattern_no": event.context.pattern.number,
        "pattern_name": event.context.pattern.name,
        "price_direction": event.context.pattern.price_direction,
        "cvd_direction": event.context.pattern.cvd_direction,
        "delta_direction": event.context.pattern.delta_direction,
        "oi_direction": event.context.oi_direction.value,
        "oi_open": _q8(event.oi_open), "oi_close": _q8(event.oi_close),
        "oi_change": _q8(event.oi_change),
        "oi_change_pct": _q8(event.oi_change_pct),
        "oi_sample_count": event.oi_sample_count,
        "context_code": event.context.code,
        "context_title": event.context.title,
        "context_summary_ja": event.context.summary_ja,
        "hfm_entry_status": event.hfm_entry_status,
        "hfm_symbol": quote.symbol if quote is not None else None,
        "hfm_entry_time": quote.received_time if quote is not None else None,
        "hfm_entry_source_time": quote.source_time if quote is not None else None,
        "hfm_entry_sequence": quote.sequence if quote is not None else None,
        "hfm_entry_bid": _q8(quote.bid) if quote is not None else None,
        "hfm_entry_ask": _q8(quote.ask) if quote is not None else None,
        "hfm_entry_spread": _q8(quote.spread) if quote is not None else None,
        "hfm_entry_age_ms": event.hfm_entry_age_ms,
    }


def hfm_context_outcome_to_row(outcome: Any) -> dict:
    return {
        "event_time": outcome.event_time, "symbol": outcome.symbol,
        "timeframe": outcome.timeframe, "context_code": outcome.context_code,
        "horizon_sec": outcome.horizon_sec, "status": outcome.status,
        "hfm_symbol": outcome.hfm_symbol, "entry_time": outcome.entry_time,
        "entry_source_time": outcome.entry_source_time,
        "entry_bid": _q8(outcome.entry_bid), "entry_ask": _q8(outcome.entry_ask),
        "outcome_time": outcome.outcome_time,
        "outcome_source_time": outcome.outcome_source_time,
        "outcome_bid": _q8(outcome.outcome_bid),
        "outcome_ask": _q8(outcome.outcome_ask),
        "quote_lag_ms": outcome.quote_lag_ms,
        "long_net_usd": _q8(outcome.long_net_usd),
        "short_net_usd": _q8(outcome.short_net_usd),
        "long_return_bps": _q8(outcome.long_return_bps),
        "short_return_bps": _q8(outcome.short_return_bps),
        "long_mfe_usd": _q8(outcome.long_mfe_usd),
        "long_mae_usd": _q8(outcome.long_mae_usd),
        "short_mfe_usd": _q8(outcome.short_mfe_usd),
        "short_mae_usd": _q8(outcome.short_mae_usd),
    }
