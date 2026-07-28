from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from src.database.schema import TRADES_DDL
from src.database.session_vwap_warm_start import load_latest_session_vwap_seed


BASE = datetime(2026, 7, 27, tzinfo=timezone.utc)


def _write_trades(path: Path, rows: list[tuple]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    con.execute("SET TimeZone='UTC'")
    try:
        con.execute(TRADES_DDL)
        for event_time, trade_id, symbol, price, quantity in rows:
            con.execute(
                "INSERT INTO trades VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    event_time,
                    event_time,
                    trade_id,
                    symbol,
                    Decimal(price),
                    Decimal(quantity),
                    "BUY",
                ],
            )
    finally:
        con.close()


def test_loader_aggregates_latest_utc_session_in_source_order(tmp_path: Path) -> None:
    path = tmp_path / "orderflow.duckdb"
    _write_trades(
        path,
        [
            (BASE - timedelta(seconds=1), 1, "BTCUSDT", "90", "10"),
            (BASE + timedelta(seconds=0.2), 2, "BTCUSDT", "100", "1"),
            (BASE + timedelta(hours=12), 3, "BTCUSDT", "110", "3"),
            (BASE + timedelta(hours=12), 4, "ETHUSDT", "999", "9"),
        ],
    )

    seed = load_latest_session_vwap_seed(path, "BTCUSDT")

    assert seed is not None
    assert seed.session_start == BASE
    assert seed.first_event_time == BASE + timedelta(seconds=0.2)
    assert seed.last_event_time == BASE + timedelta(hours=12)
    assert seed.notional == Decimal("430")
    assert seed.volume == Decimal("4")
    assert seed.trade_count == 2
    assert seed.last_trade_id == 3
    assert seed.session_complete is True


def test_loader_marks_mid_session_history_incomplete(tmp_path: Path) -> None:
    path = tmp_path / "partial.duckdb"
    _write_trades(
        path,
        [(BASE + timedelta(hours=6), 1, "BTCUSDT", "100", "1")],
    )

    seed = load_latest_session_vwap_seed(path, "BTCUSDT")

    assert seed is not None
    assert seed.session_complete is False


def test_loader_rejects_invalid_persisted_trade_without_partial_seed(
    tmp_path: Path,
) -> None:
    path = tmp_path / "invalid.duckdb"
    _write_trades(
        path,
        [(BASE + timedelta(seconds=0.2), 1, "BTCUSDT", "100", "0")],
    )

    with pytest.raises(ValueError, match="invalid trade"):
        load_latest_session_vwap_seed(path, "BTCUSDT")


def test_loader_treats_missing_database_as_first_start(tmp_path: Path) -> None:
    assert load_latest_session_vwap_seed(
        tmp_path / "missing.duckdb", "BTCUSDT"
    ) is None
