from __future__ import annotations

import csv

from tools.observe_execution_costs import (
    HEADER,
    MarketQuoteWriter,
    parse_binance_message,
    parse_bitflyer_message,
    parse_gmo_message,
    parse_hfm_line,
    parse_hfm_source,
)


def test_public_ticker_parsers_preserve_executable_sides() -> None:
    assert parse_binance_message({"E": 123, "b": "100", "a": "101"}, "btcusdt") == (
        "BTCUSDT", "USDT", 123, 100.0, 101.0
    )
    bitflyer = {
        "method": "channelMessage",
        "params": {
            "channel": "lightning_ticker_FX_BTC_JPY",
            "message": {
                "timestamp": "2026-07-23T00:00:00.123Z",
                "best_bid": 10_000_000,
                "best_ask": 10_001_000,
            },
        },
    }
    assert parse_bitflyer_message(
        bitflyer, "lightning_ticker_FX_BTC_JPY", "FX_BTC_JPY"
    ) == ("FX_BTC_JPY", "JPY", 1784764800123, 10_000_000.0, 10_001_000.0)
    gmo = {
        "channel": "ticker",
        "symbol": "BTC_JPY",
        "timestamp": "2026-07-23T00:00:00.123Z",
        "bid": "10000000",
        "ask": "10001000",
    }
    assert parse_gmo_message(gmo, "BTC_JPY") == (
        "BTC_JPY", "JPY", 1784764800123, 10_000_000.0, 10_001_000.0
    )


def test_writer_rejects_crossed_quote_and_preserves_currency(tmp_path) -> None:
    path = tmp_path / "quotes.csv"
    writer = MarketQuoteWriter(path, batch_size=10, flush_interval_ms=1000)
    assert writer.write(
        "BITFLYER_CFD", "FX_BTC_JPY", "JPY", 1, 10_000_000, 10_001_000,
        received_ns=2,
    )
    assert not writer.write(
        "BITFLYER_CFD", "FX_BTC_JPY", "JPY", 1, 10_001_000, 10_000_000,
        received_ns=3,
    )
    writer.close()
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0]) == HEADER
    assert len(rows) == 1
    assert rows[0]["quote_currency"] == "JPY"


def test_hfm_source_parser_does_not_split_windows_drive_letter() -> None:
    source, path = parse_hfm_source(r"HFM_INFINITYX=C:\quotes\infinity.jsonl")
    assert source == "HFM_INFINITYX"
    assert str(path) == r"C:\quotes\infinity.jsonl"


def test_hfm_parser_repairs_only_unambiguous_extra_opening_brace() -> None:
    parsed, sequence = parse_hfm_line(
        '{{"symbol":"#BTCUSDr","server_time_msc":10,"sequence":7,'
        '"bid":100,"ask":102}'
    )
    assert parsed == ("#BTCUSDr", "USD", 10, 100.0, 102.0)
    assert sequence == 7
