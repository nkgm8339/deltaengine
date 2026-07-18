"""DuckDB read-only history queries for REST endpoints."""
from __future__ import annotations

import duckdb


def query_candles(db_path: str, symbol: str, limit: int = 200) -> list[dict]:
    """Return latest `limit` candles for symbol, newest first. All values as str."""
    con = duckdb.connect(db_path, read_only=True)
    try:
        rows = con.execute(
            "SELECT bar_time, open, high, low, close, volume, delta, cvd "
            "FROM candles WHERE symbol = ? ORDER BY bar_time DESC LIMIT ?",
            [symbol, limit],
        ).fetchall()
        cols = ["bar_time", "open", "high", "low", "close", "volume", "delta", "cvd"]
        return [{k: str(v) if v is not None else None for k, v in zip(cols, row)} for row in rows]
    finally:
        con.close()


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
