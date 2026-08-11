from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.orderflow.big_trades.time_buckets import candle_id, candle_start
from src.orderflow.cvd import bar_start


UTC = timezone.utc


def test_offset_timestamp_normalizes_to_same_utc_minute_bucket() -> None:
    utc_time = datetime(2026, 8, 12, 1, 2, 59, 999999, tzinfo=UTC)
    offset_time = utc_time.astimezone(timezone(timedelta(hours=9)))
    assert candle_id(offset_time) == candle_id(utc_time)
    assert candle_start(candle_id(utc_time)) == datetime(2026, 8, 12, 1, 2, tzinfo=UTC)


def test_big_trades_candle_boundary_matches_cvd_one_minute_boundary() -> None:
    before = datetime(2026, 8, 12, 1, 2, 59, 999999, tzinfo=UTC)
    on_boundary = datetime(2026, 8, 12, 1, 3, 0, tzinfo=UTC)
    assert candle_start(candle_id(before)) == bar_start(before, "1m")
    assert candle_start(candle_id(on_boundary)) == bar_start(on_boundary, "1m")
    assert candle_id(before) != candle_id(on_boundary)
