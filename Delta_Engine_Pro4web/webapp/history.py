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
            "SELECT bar_time, timeframe, open, high, low, close, volume, delta, cvd, "
            "NULL AS vwap, NULL AS vwap_status "
            f"FROM candles {where} ORDER BY bar_time DESC LIMIT ?",
            params,
        ).fetchall()
        cols = [
            "bar_time", "timeframe", "open", "high", "low", "close",
            "volume", "delta", "cvd", "vwap", "vwap_status",
        ]
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


def _parse_utc_before(value: str | datetime | None) -> datetime | None:
    """Parse an API cursor and return a naive UTC value for DuckDB TIMESTAMP."""
    if value is None:
        return None
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(
        value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
    )
    if parsed.tzinfo is None:
        raise ValueError("before must be a timezone-aware ISO 8601 timestamp")
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def query_footprints(
    db_path: str,
    symbol: str,
    timeframe: str = "1m",
    limit: int = 40,
    before: str | datetime | None = None,
) -> list[dict]:
    """Return closed Footprint bars oldest-first with price levels high-to-low.

    ``before`` is an exclusive UTC cursor.  A CTE first limits manifests so a
    single outlier bar cannot turn the endpoint into an unbounded level scan.
    """
    safe_limit = max(1, min(int(limit), 100))
    before_utc = _parse_utc_before(before)
    con = duckdb.connect(db_path)
    try:
        available = {
            row[0]
            for row in con.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name IN ('footprint_bar_manifest', 'footprint_levels')"
            ).fetchall()
        }
        if available != {"footprint_bar_manifest", "footprint_levels"}:
            return []

        cursor_clause = ""
        params: list = [symbol, timeframe]
        if before_utc is not None:
            cursor_clause = " AND bar_time < ?"
            params.append(before_utc)
        params.append(safe_limit)
        rows = con.execute(
            "WITH selected AS ("
            " SELECT bar_time, symbol, timeframe, level_count, buy_volume, "
            " sell_volume, content_hash FROM footprint_bar_manifest "
            " WHERE symbol = ? AND timeframe = ?" + cursor_clause +
            " ORDER BY bar_time DESC LIMIT ?"
            ") "
            "SELECT s.bar_time, s.symbol, s.timeframe, s.level_count, "
            "s.buy_volume, s.sell_volume, s.content_hash, "
            "l.price, l.buy_volume, l.sell_volume "
            "FROM selected s JOIN footprint_levels l "
            "ON l.bar_time = s.bar_time AND l.symbol = s.symbol "
            "AND l.timeframe = s.timeframe "
            "ORDER BY s.bar_time ASC, l.price DESC",
            params,
        ).fetchall()

        bars: list[dict] = []
        by_time: dict[datetime, dict] = {}
        for row in rows:
            bar_time = row[0]
            bar = by_time.get(bar_time)
            if bar is None:
                bar = {
                    "bar_time": _utc_iso(bar_time),
                    "symbol": row[1],
                    "timeframe": row[2],
                    "level_count": int(row[3]),
                    "buy_volume": str(row[4]),
                    "sell_volume": str(row[5]),
                    "content_hash": row[6],
                    "levels": [],
                }
                by_time[bar_time] = bar
                bars.append(bar)
            bar["levels"].append({
                "price": str(row[7]),
                # WebSocket contract: bid=aggressive sell, ask=aggressive buy.
                "bid": str(row[9]),
                "ask": str(row[8]),
            })
        for bar in bars:
            if len(bar["levels"]) != bar["level_count"]:
                raise RuntimeError(
                    "footprint history manifest/level count mismatch "
                    f"for {bar['symbol']} {bar['timeframe']} {bar['bar_time']}"
                )
        return bars
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


def _query_optional_table(
    db_path: str,
    table: str,
    columns: list[str],
    symbol: str,
    timeframe: str,
    limit: int,
) -> list[dict]:
    con = duckdb.connect(db_path)
    try:
        exists = con.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = ?",
            [table],
        ).fetchone()[0]
        if not exists:
            return []
        rows = con.execute(
            f"SELECT {', '.join(columns)} FROM {table} "
            "WHERE symbol = ? AND timeframe = ? ORDER BY event_time DESC LIMIT ?",
            [symbol, timeframe, limit],
        ).fetchall()
        result = []
        for row in rows:
            item = {key: str(value) if value is not None else None for key, value in zip(columns, row)}
            for key, value in zip(columns, row):
                if isinstance(value, datetime):
                    item[key] = _utc_iso(value)
            result.append(item)
        return result
    finally:
        con.close()


def query_combined_context_events(
    db_path: str,
    symbol: str,
    timeframe: str = "5m",
    limit: int = 500,
) -> list[dict]:
    """Return stored four-axis native observations, newest first."""
    columns = [
        "event_time", "bar_time", "timeframe", "pattern_no", "pattern_name",
        "price_direction", "cvd_direction", "delta_direction", "oi_direction",
        "oi_open", "oi_close", "oi_change", "oi_change_pct", "oi_sample_count",
        "context_code", "context_title", "context_summary_ja",
        "hfm_entry_status", "hfm_symbol", "hfm_entry_time",
        "hfm_entry_source_time", "hfm_entry_sequence", "hfm_entry_bid",
        "hfm_entry_ask", "hfm_entry_spread", "hfm_entry_age_ms",
    ]
    return _query_optional_table(
        db_path, "combined_context_events", columns, symbol, timeframe, limit,
    )


def query_hfm_context_outcomes(
    db_path: str,
    symbol: str,
    timeframe: str = "5m",
    limit: int = 1500,
) -> list[dict]:
    """Return executable long/short HFM outcomes, newest first."""
    columns = [
        "event_time", "timeframe", "context_code", "horizon_sec", "status",
        "hfm_symbol", "entry_time", "entry_source_time", "entry_bid", "entry_ask",
        "outcome_time", "outcome_source_time", "outcome_bid", "outcome_ask",
        "quote_lag_ms", "long_net_usd", "short_net_usd", "long_return_bps",
        "short_return_bps", "long_mfe_usd", "long_mae_usd", "short_mfe_usd",
        "short_mae_usd",
    ]
    return _query_optional_table(
        db_path, "hfm_context_outcomes", columns, symbol, timeframe, limit,
    )


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


def query_time_sales(
    db_path: str,
    symbol: str,
    limit: int = 500,
    before: str | datetime | None = None,
    before_trade_id: int | None = None,
) -> list[dict]:
    """Return recent accepted trades oldest-first for Time & Sales hydration."""
    safe_limit = max(1, min(int(limit), 500))
    before_utc = _parse_utc_before(before)
    where = "WHERE symbol = ?"
    params: list = [symbol]
    if before_utc is not None:
        if before_trade_id is None:
            where += " AND event_time < ?"
            params.append(before_utc)
        else:
            where += " AND (event_time < ? OR (event_time = ? AND trade_id < ?))"
            params.extend([before_utc, before_utc, int(before_trade_id)])
    params.append(safe_limit)

    con = duckdb.connect(db_path)
    try:
        rows = con.execute(
            "SELECT event_time, trade_id, symbol, price, quantity, side "
            f"FROM trades {where} "
            "ORDER BY event_time DESC, trade_id DESC LIMIT ?",
            params,
        ).fetchall()
    finally:
        con.close()

    trades = []
    for event_time, trade_id, row_symbol, price, quantity, side in reversed(rows):
        trades.append({
            "event_time": _utc_iso(event_time),
            "trade_id": int(trade_id),
            "symbol": row_symbol,
            "price": str(price),
            "quantity": str(quantity),
            "notional": str(price * quantity),
            "side": side,
        })
    return trades
