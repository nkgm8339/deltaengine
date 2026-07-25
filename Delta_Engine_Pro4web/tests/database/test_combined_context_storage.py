from datetime import datetime, timedelta, timezone
from decimal import Decimal

import duckdb

from src.database.schema import (
    combined_context_event_to_row,
    hfm_context_outcome_to_row,
)
from src.database.storage import StorageWriter
from src.orderflow.combined_context_runtime import CombinedContextObserver, HfmQuote
from src.orderflow.cvd import Candle
from webapp.history import (
    query_combined_context_events,
    query_hfm_context_outcomes,
)


UTC = timezone.utc
START = datetime(2026, 7, 24, tzinfo=UTC)


def _candle(minutes: int, close: int) -> Candle:
    value = Decimal(close)
    return Candle(
        START + timedelta(minutes=minutes), "BTCUSDT", "5m",
        value - 1, value + 1, value - 2, value,
        Decimal("10"), Decimal("2"), value,
    )


def test_combined_event_and_hfm_outcome_round_trip_to_new_tables(tmp_path):
    observer = CombinedContextObserver("BTCUSDT", horizons_sec=(180,))
    for seconds, value in ((600, "100"), (890, "110")):
        observer.observe_oi_sample({
            "source_time": START + timedelta(seconds=seconds),
            "symbol": "BTCUSDT",
            "open_interest": Decimal(value),
        })
    observer.register_candle(_candle(0, 100))
    observer.register_candle(_candle(5, 101))
    entry_time = START + timedelta(minutes=15)
    observer.observe_hfm_quote(HfmQuote(
        "#BTCUSDr", entry_time, entry_time, 1, Decimal("100"), Decimal("102"),
    ))
    event = observer.register_candle(_candle(10, 103), decision_time=entry_time)
    outcome = observer.observe_hfm_quote(HfmQuote(
        "#BTCUSDr",
        entry_time + timedelta(seconds=180),
        entry_time + timedelta(seconds=180),
        2,
        Decimal("105"),
        Decimal("107"),
    ))[0]

    db_path = tmp_path / "orderflow.duckdb"
    writer = StorageWriter(tmp_path / "parquet", db_path, batch_size=100)
    writer.add_combined_context_event(combined_context_event_to_row(event))
    writer.add_hfm_context_outcome(hfm_context_outcome_to_row(outcome))
    writer.close()

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        stored_event = con.execute(
            "SELECT pattern_no, context_code, oi_change, hfm_entry_spread "
            "FROM combined_context_events"
        ).fetchone()
        stored_outcome = con.execute(
            "SELECT horizon_sec, status, long_net_usd, short_net_usd "
            "FROM hfm_context_outcomes"
        ).fetchone()
    finally:
        con.close()
    assert stored_event == (1, "P1_BUILDING", Decimal("10.00000000"), Decimal("2.00000000"))
    assert stored_outcome == (
        180, "OK", Decimal("3.00000000"), Decimal("-7.00000000"),
    )
    assert list((tmp_path / "parquet" / "combined_context_events").rglob("*.parquet"))
    assert list((tmp_path / "parquet" / "hfm_context_outcomes").rglob("*.parquet"))
    history_event = query_combined_context_events(
        str(db_path), "BTCUSDT", "5m", 10,
    )[0]
    history_outcome = query_hfm_context_outcomes(
        str(db_path), "BTCUSDT", "5m", 10,
    )[0]
    assert history_event["context_code"] == "P1_BUILDING"
    assert history_event["event_time"].endswith("+00:00")
    assert history_outcome["long_net_usd"] == "3.00000000"

