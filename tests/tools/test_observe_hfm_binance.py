from __future__ import annotations

import csv

from tools.observe_hfm_binance import HEADER, LEGACY_HEADER, QuoteWriter


def test_background_quote_writer_preserves_fifo_and_sequence(tmp_path) -> None:
    path = tmp_path / "quotes.csv"
    writer = QuoteWriter(
        path,
        batch_size=100,
        flush_interval_ms=1000,
        queue_depth=10,
    )
    writer.write(
        "HFM", "BTCUSD", 1000, 100.0, 101.0,
        received_ns=1, source_sequence=7,
    )
    writer.write(
        "HFM", "BTCUSD", 1001, 101.0, 102.0,
        received_ns=2, source_sequence=8,
    )
    writer.close()

    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0]) == HEADER
    assert [row["local_received_ns"] for row in rows] == ["1", "2"]
    assert [row["source_sequence"] for row in rows] == ["7", "8"]
    assert writer.rows_written == 2
    assert writer.flushes == 1


def test_background_quote_writer_appends_legacy_six_column_file(tmp_path) -> None:
    path = tmp_path / "legacy.csv"
    path.write_text(
        ",".join(LEGACY_HEADER) + "\nBINANCE,BTCUSDT,1,1,100,101\n",
        encoding="utf-8",
    )
    writer = QuoteWriter(path, flush_interval_ms=1000)
    writer.write(
        "HFM", "BTCUSD", 2, 100.0, 102.0,
        received_ns=2, source_sequence=9,
    )
    writer.close()

    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    assert all(len(row) == len(LEGACY_HEADER) for row in rows)
    assert rows[-1] == ["HFM", "BTCUSD", "2", "2", "100.0", "102.0"]
