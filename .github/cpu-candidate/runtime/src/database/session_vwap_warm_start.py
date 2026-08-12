"""Read-only DuckDB aggregate loader for UTC-session VWAP warm starts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb

from ..strategy_engine.ingestion.session_vwap import SessionVwapSeed


def load_latest_session_vwap_seed(
    db_path: str | Path,
    symbol: str,
) -> SessionVwapSeed | None:
    """Aggregate the latest persisted UTC session without loading every trade.

    The latest stored source timestamp selects the session. The accumulator will
    still omit conditions when ``first_event_time`` does not cover UTC 00:00.
    This function must run before the live writer opens DuckDB.
    """

    if not symbol:
        raise ValueError("symbol must not be empty")
    path = Path(db_path)
    if not path.is_file():
        return None

    con = duckdb.connect(str(path), read_only=True)
    con.execute("SET TimeZone='UTC'")
    try:
        table_exists = con.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_name = 'trades'"
        ).fetchone()[0]
        if not table_exists:
            return None

        latest = con.execute(
            "SELECT max(event_time) FROM trades WHERE symbol = ?",
            [symbol],
        ).fetchone()[0]
        if latest is None:
            return None
        latest = _as_utc(latest)
        session_start = latest.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        session_end = session_start + timedelta(days=1)

        invalid_count = con.execute(
            "SELECT count(*) FROM trades "
            "WHERE symbol = ? AND event_time >= ? AND event_time < ? "
            "AND (price <= 0 OR quantity <= 0)",
            [symbol, session_start, session_end],
        ).fetchone()[0]
        if invalid_count:
            raise ValueError(
                f"session VWAP seed contains {invalid_count} invalid trade(s)"
            )

        aggregate = con.execute(
            "SELECT min(event_time), max(event_time), "
            "sum(price * quantity), sum(quantity), count(*) "
            "FROM trades WHERE symbol = ? "
            "AND event_time >= ? AND event_time < ?",
            [symbol, session_start, session_end],
        ).fetchone()
        first_event, last_event, notional, volume, trade_count = aggregate
        if not trade_count:
            return None

        last_trade_id = con.execute(
            "SELECT trade_id FROM trades WHERE symbol = ? "
            "AND event_time >= ? AND event_time < ? "
            "ORDER BY event_time DESC, trade_id DESC LIMIT 1",
            [symbol, session_start, session_end],
        ).fetchone()[0]
    finally:
        con.close()

    return SessionVwapSeed(
        symbol=symbol,
        session_start=session_start,
        first_event_time=_as_utc(first_event),
        last_event_time=_as_utc(last_event),
        notional=notional,
        volume=volume,
        trade_count=int(trade_count),
        last_trade_id=int(last_trade_id),
    )


def _as_utc(value: datetime) -> datetime:
    # DuckDB TIMESTAMP is UTC wall time by the storage contract but is returned
    # without tzinfo; attach UTC rather than interpreting machine local time.
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
