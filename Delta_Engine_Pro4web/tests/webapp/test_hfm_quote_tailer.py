from datetime import datetime, timezone
from decimal import Decimal

from webapp.hfm_quote_tailer import _last_complete_line, parse_hfm_quote


def test_hfm_quote_parser_preserves_symbol_sequence_and_bid_ask():
    received = datetime(2026, 7, 24, 10, 0, tzinfo=timezone.utc)
    quote = parse_hfm_quote(
        '{"symbol":"#BTCUSDr","server_time_msc":1784888238789,'
        '"sequence":41,"bid":65751.411,"ask":65771.681}',
        received,
    )
    assert quote.symbol == "#BTCUSDr"
    assert quote.sequence == 41
    assert quote.bid == Decimal("65751.411")
    assert quote.ask == Decimal("65771.681")
    assert quote.spread == Decimal("20.270")
    assert quote.received_time == received


def test_last_complete_line_reads_latest_without_loading_whole_file(tmp_path):
    path = tmp_path / "hfm.jsonl"
    path.write_text('{"sequence":1}\n{"sequence":2}\n', encoding="utf-8")
    assert _last_complete_line(path) == '{"sequence":2}'


def test_bundled_hfm_observer_source_is_compilable_not_corrupted():
    import pathlib

    source = pathlib.Path(__file__).resolve().parents[2].joinpath(
        "mt5", "HFMQuoteObserver.mq5",
    ).read_text(encoding="utf-8")
    assert 'QuoteFileName = "DeltaEngine_HFM_quotes_utf8.jsonl"' in source
    assert "INVALID_HANDLE" in source
    assert "FILE_READ" in source
    assert "SEEK_END" in source
    assert "INIT_SUCCEEDED" in source
    assert "void OnDeinit(" in source
    assert "DoubleToString(tick.bid, _Digits)" in source
    assert "INVALIe_HANeLE" not in source
    assert "eoubleToString" not in source
