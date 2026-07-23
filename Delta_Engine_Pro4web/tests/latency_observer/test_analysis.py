from __future__ import annotations

from src.latency_observer.analysis import Quote, build_report, load_quotes


def quote(source: str, ms: int, bid: float, ask: float) -> Quote:
    return Quote(source, "BTC", ms, ms * 1_000_000, bid, ask)


def test_load_quotes_rejects_invalid_rows(tmp_path) -> None:
    path = tmp_path / "quotes.csv"
    path.write_text(
        "source,symbol,exchange_time_ms,local_received_ns,bid,ask\n"
        "BINANCE,BTCUSDT,1,1000000,100,101\n"
        "HFM,BTCUSD,2,2000000,0,101\n",
        encoding="utf-8",
    )
    result = load_quotes(path)
    assert len(result) == 1
    assert result[0].source == "BINANCE"


def test_hfm_sequence_audit_detects_missing_quotes_and_restart() -> None:
    quotes = [
        Quote("HFM", "BTC", 1, 1_000_000, 100, 101, source_sequence=10),
        Quote("HFM", "BTC", 2, 2_000_000, 100, 101, source_sequence=12),
        Quote("HFM", "BTC", 3, 3_000_000, 100, 101, source_sequence=1),
        Quote("HFM", "BTC", 4, 4_000_000, 100, 101, source_sequence=1),
    ]
    audit = build_report(quotes)["hfm_bridge_sequence"]
    assert audit["quotes_with_sequence"] == 4
    assert audit["missing_sequence_count"] == 1
    assert audit["sequence_resets"] == 1
    assert audit["duplicates_or_reversals"] == 1


def test_report_separates_basis_spreads_and_execution_sides() -> None:
    quotes = [
        quote("BINANCE", 1000, 100.0, 101.0),
        quote("HFM", 1010, 102.0, 104.0),
    ]
    report = build_report(quotes, max_staleness_ms=100)
    assert report["basis_usd"]["mean"] == 2.5
    assert report["long_execution_difference_usd"]["mean"] == 3.0
    assert report["short_execution_difference_usd"]["mean"] == 2.0
    assert report["hfm_spread_usd"]["mean"] == 2.0


def test_positive_latency_means_hfm_followed_binance() -> None:
    quotes = [
        quote("BINANCE", 1000, 99.5, 100.5),
        quote("HFM", 1000, 99.5, 100.5),
        quote("BINANCE", 1200, 100.5, 101.5),
        quote("HFM", 1500, 100.5, 101.5),
    ]
    report = build_report(quotes, move_threshold_bps=50, match_window_ms=1000)
    assert report["latency_ms"]["count"] == 1
    assert report["latency_ms"]["median"] == 300.0
    assert report["latency_ms"]["match_rate_pct"] == 100.0


def test_candle_direction_agreement() -> None:
    quotes = [
        quote("BINANCE", 60_000, 100, 100),
        quote("HFM", 60_010, 101, 101),
        quote("BINANCE", 61_000, 102, 102),
        quote("HFM", 61_010, 103, 103),
    ]
    report = build_report(quotes)
    one_minute = report["candles"][0]
    assert one_minute["common_candles"] == 1
    assert one_minute["direction_agreement_pct"] == 100.0
    assert one_minute["ohlc_difference_usd"]["close"]["mean"] == 1.0
    assert one_minute["hfm_candle_range_usd"]["mean"] == 2.0


def test_candle_report_compares_hfm_spread_with_traded_range() -> None:
    quotes = [
        quote("BINANCE", 60_000, 99.5, 100.5),
        quote("HFM", 60_010, 99.0, 101.0),
        quote("BINANCE", 61_000, 109.5, 110.5),
        quote("HFM", 61_010, 109.0, 111.0),
    ]
    one_minute = build_report(quotes)["candles"][0]
    assert one_minute["hfm_candle_range_usd"]["mean"] == 10.0
    assert one_minute["hfm_median_spread_usd_by_candle"]["mean"] == 2.0
    assert one_minute["hfm_spread_to_candle_range_pct"]["mean"] == 20.0


def test_one_second_return_correlation() -> None:
    quotes = []
    for second, price in enumerate((100.0, 101.0, 100.0), start=1):
        quotes.append(quote("BINANCE", second * 1000, price, price))
        quotes.append(quote("HFM", second * 1000 + 10, price + 5, price + 5))
    report = build_report(quotes)
    correlation = report["one_second_return_correlation"]
    assert correlation["return_pairs"] == 2
    assert correlation["pearson"] is not None
    assert correlation["pearson"] > 0.99


def test_executable_outcome_uses_hfm_ask_to_bid_for_long() -> None:
    quotes = [
        quote("BINANCE", 1000, 99.5, 100.5),
        quote("HFM", 1000, 99.0, 101.0),
        quote("BINANCE", 2000, 109.5, 110.5),
        quote("HFM", 3000, 100.0, 102.0),
        quote("HFM", 33_000, 110.0, 112.0),
    ]
    report = build_report(
        quotes,
        move_threshold_bps=500,
        entry_delay_ms=1000,
        execution_horizons_seconds=(30,),
        max_staleness_ms=100,
    )
    outcome = report["executable_hfm_outcomes_after_binance_move"]
    result = outcome["horizons_seconds"]["30"]["long"]
    assert result["count"] == 1
    assert result["net_usd"]["mean"] == 8.0
    assert result["win_rate_pct"] == 100.0
