"""Read-only persisted-trade loader for Flow Response warm starts."""

from __future__ import annotations

from datetime import timedelta, timezone
from decimal import Decimal
from pathlib import Path

import duckdb

from ..normalization.normalizer import NormalizedTrade


def load_recent_flow_response_trades(
    db_path: str | Path,
    symbol: str,
    baseline_window_sec: int,
) -> tuple[NormalizedTrade, ...]:
    """Load the latest persisted baseline window in detector order.

    The caller must run this before opening the live DuckDB writer. Missing or
    empty databases are normal on a first start and return no seed trades.
    """
    if baseline_window_sec < 1:
        raise ValueError("baseline_window_sec must be >= 1")

    path = Path(db_path)
    if not path.is_file():
        return ()

    con = duckdb.connect(str(path), read_only=True)
    try:
        table_exists = con.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = 'trades'"
        ).fetchone()[0]
        if not table_exists:
            return ()

        latest = con.execute(
            "SELECT max(event_time) FROM trades WHERE symbol = ?",
            [symbol],
        ).fetchone()[0]
        if latest is None:
            return ()

        # Include one full baseline duration before the latest timestamp. The
        # detector performs the final integer-second cutoff itself.
        cutoff = latest - timedelta(seconds=baseline_window_sec)
        rows = con.execute(
            "SELECT event_time, trade_time, trade_id, symbol, price, quantity, side "
            "FROM trades WHERE symbol = ? AND event_time >= ? AND event_time <= ? "
            "ORDER BY event_time ASC, trade_id ASC",
            [symbol, cutoff, latest],
        ).fetchall()
    finally:
        con.close()

    trades = []
    for event_time, trade_time, trade_id, row_symbol, price, quantity, side in rows:
        if event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=timezone.utc)
        else:
            event_time = event_time.astimezone(timezone.utc)
        if trade_time.tzinfo is None:
            trade_time = trade_time.replace(tzinfo=timezone.utc)
        else:
            trade_time = trade_time.astimezone(timezone.utc)
        trades.append(
            NormalizedTrade(
                event_time=event_time,
                trade_time=trade_time,
                trade_id=int(trade_id),
                symbol=str(row_symbol),
                price=Decimal(str(price)),
                quantity=Decimal(str(quantity)),
                side=str(side),
            )
        )
    return tuple(trades)
