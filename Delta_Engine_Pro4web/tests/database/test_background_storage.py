"""Live storage must not block the asyncio market-data loop."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import duckdb

from src.database.storage import BackgroundStorageWriter


def _trade_row(trade_id: int) -> dict:
    when = datetime(2026, 7, 23, 0, 0, trade_id, tzinfo=timezone.utc)
    return {
        "event_time": when,
        "trade_time": when,
        "trade_id": trade_id,
        "symbol": "BTCUSDT",
        "price": Decimal("50000.5"),
        "quantity": Decimal("0.1"),
        "side": "BUY",
    }


def test_background_writer_drains_fifo_before_close(tmp_path):
    db_path = tmp_path / "duck" / "orderflow.duckdb"
    writer = BackgroundStorageWriter(
        tmp_path / "parquet",
        db_path,
        batch_size=2,
        flush_interval_sec=5,
        queue_depth=10,
    )
    writer.add_trade(_trade_row(1))
    writer.add_trade(_trade_row(2))
    writer.add_trade(_trade_row(3))
    writer.close()

    assert writer.trades_written == 3
    assert writer.high_watermark >= 1
    with duckdb.connect(str(db_path), read_only=True) as connection:
        assert connection.execute("SELECT count(*) FROM trades").fetchone()[0] == 3
