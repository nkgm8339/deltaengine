from datetime import datetime, timezone

import pyarrow as pa
import pyarrow.parquet as pq

from tools.build_orderflow_manifest import inspect_trades


def _write(path, rows):
    pq.write_table(pa.table(rows), path)


def test_inspect_trades_skips_non_trade_parquet_and_reports_gaps(tmp_path):
    root = tmp_path / "raw"
    root.mkdir()
    _write(
        root / "trades.parquet",
        {
            "event_time": [
                datetime(2026, 7, 25, 0, 0, tzinfo=timezone.utc),
                datetime(2026, 7, 25, 0, 2, tzinfo=timezone.utc),
                datetime(2026, 7, 25, 0, 2, tzinfo=timezone.utc),
            ],
            "trade_id": ["1", "2", "2"],
            "price": [100.0, 101.0, 0.0],
            "quantity": [1.0, 2.0, 0.0],
            "side": ["BUY", "SELL", "OTHER"],
        },
    )
    _write(
        root / "signals.parquet",
        {"signal_time": [datetime(2026, 7, 25, tzinfo=timezone.utc)], "signal": ["old"]},
    )

    result = inspect_trades(root)

    assert result["files"] == 2
    assert result["trade_rows"] == 3
    assert result["unique_trade_ids"] == 2
    assert result["duplicate_trade_ids"] == 1
    assert result["invalid_nonpositive"] == 1
    assert result["invalid_side"] == 1
    assert result["minutes_with_trades"] == 2
    assert result["gap_count_over_1m"] == 1
    assert result["gap_count_over_10m"] == 0
    assert result["max_gap_seconds"] == 120
