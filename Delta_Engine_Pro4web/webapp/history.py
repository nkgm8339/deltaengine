"""DuckDB read-only history queries for REST endpoints."""
from __future__ import annotations
from datetime import datetime, timezone

import duckdb


def query_candles(
    db_path: str,
    symbol: str,
    limit: int = 200,
    timeframe: str | None = None,
) -> list[dict]:
    """Return latest `limit` candles for symbol, newest first. All values as str."""
    # Use the same default connection mode as StorageWriter. DuckDB rejects
    # mixed read_only/read_write configurations for the same file in-process.
    con = duckdb.connect(db_path)
    try:
        where = "WHERE symbol = ?"
        params: list = [symbol]
        if timeframe is not None:
            where += " AND timeframe = ?"
            params.append(timeframe)
        params.append(limit)
        rows = con.execute(
            "SELECT bar_time, timeframe, open, high, low, close, volume, delta, cvd "
            f"FROM candles {where} ORDER BY bar_time DESC LIMIT ?",
            params,
        ).fetchall()
        cols = ["bar_time", "timeframe", "open", "high", "low", "close", "volume", "delta", "cvd"]
        result = []
        for row in rows:
            item = {k: str(v) if v is not None else None for k, v in zip(cols, row)}
            bar_time = row[0]
            if isinstance(bar_time, datetime):
                if bar_time.tzinfo is None:
                    bar_time = bar_time.replace(tzinfo=timezone.utc)
                item["bar_time"] = bar_time.astimezone(timezone.utc).isoformat()
            result.append(item)
        return result
    finally:
        con.close()


def query_flow_response_events(
    db_path: str,
    symbol: str,
    limit: int = 5000,
) -> list[dict]:
    """Return recent persisted flow/price state transitions, newest first."""
    con = duckdb.connect(db_path)
    try:
        rows = con.execute(
            "SELECT event_time, window_sec, state, pressure_ratio, persistence, "
            "price_change_bps, relative_volume, buy_volume + sell_volume AS total_volume, "
            "delta, trade_count FROM flow_response_events "
            "WHERE symbol = ? ORDER BY event_time DESC LIMIT ?",
            [symbol, limit],
        ).fetchall()
        cols = [
            "event_time", "window_sec", "state", "pressure_ratio", "persistence",
            "price_change_bps", "relative_volume", "total_volume", "delta", "trade_count",
        ]
        result = []
        for row in rows:
            item = {k: str(v) if v is not None else None for k, v in zip(cols, row)}
            event_time = row[0]
            if isinstance(event_time, datetime):
                if event_time.tzinfo is None:
                    event_time = event_time.replace(tzinfo=timezone.utc)
                item["event_time"] = event_time.astimezone(timezone.utc).isoformat()
            result.append(item)
        return result
    finally:
        con.close()


def query_open_interest_samples(
    db_path: str,
    symbol: str,
    limit: int = 2500,
) -> list[dict]:
    """Return persisted exchange OI observations, newest first."""
    con = duckdb.connect(db_path)
    try:
        table_exists = con.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_name = 'open_interest_samples'"
        ).fetchone()[0]
        if not table_exists:
            return []
        rows = con.execute(
            "SELECT source_time, received_time, open_interest, source "
            "FROM open_interest_samples WHERE symbol = ? "
            "ORDER BY source_time DESC LIMIT ?",
            [symbol, limit],
        ).fetchall()
        result = []
        for source_time, received_time, open_interest, source in rows:
            result.append({
                "source_time": _utc_iso(source_time),
                "received_time": _utc_iso(received_time),
                "open_interest": str(open_interest) if open_interest is not None else None,
                "source": source,
            })
        return result
    finally:
        con.close()


def _utc_iso(value):
    if not isinstance(value, datetime):
        return str(value) if value is not None else None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def query_signals(db_path: str, symbol: str, limit: int = 200) -> list[dict]:
    """Return latest `limit` signals for symbol, newest first."""
    con = duckdb.connect(db_path, read_only=True)
    try:
        rows = con.execute(
            "SELECT signal_time, signal, confidence "
            "FROM signals WHERE symbol = ? ORDER BY signal_time DESC LIMIT ?",
            [symbol, limit],
        ).fetchall()
        cols = ["signal_time", "signal", "confidence"]
        return [{k: str(v) if v is not None else None for k, v in zip(cols, row)} for row in rows]
    finally:
        con.close()


def query_trades(db_path: str, symbol: str, limit: int = 500) -> list[dict]:
    """Return latest `limit` trades for symbol, newest first."""
    con = duckdb.connect(db_path, read_only=True)
    try:
        rows = con.execute(
            "SELECT event_time, price, quantity, side "
            "FROM trades WHERE symbol = ? ORDER BY event_time DESC LIMIT ?",
            [symbol, limit],
        ).fetchall()
        cols = ["event_time", "price", "quantity", "side"]
        return [{k: str(v) if v is not None else None for k, v in zip(cols, row)} for row in rows]
    finally:
        con.close()
