from datetime import datetime, timedelta, timezone

import pytest

from src.orderflow.hfm_episode_outcome import HfmEpisodeOutcomeEvaluator, HfmQuoteObservation

UTC = timezone.utc


def quote(start, seconds, bid, ask):
    return HfmQuoteObservation("#BTCUSDr", start + timedelta(seconds=seconds), bid, ask)


def test_hfm_outcome_uses_executable_bid_ask_and_tracks_mfe_mae():
    start = datetime(2026, 7, 25, tzinfo=UTC)
    quotes = [quote(start, 0, 100.0, 120.0), quote(start, 2, 101.0, 121.0), quote(start, 300, 130.0, 150.0)]
    result = HfmEpisodeOutcomeEvaluator((300,), max_quote_gap_sec=400).evaluate(
        quotes, signal_received_time=start + timedelta(seconds=1)
    )[0]
    assert result.status == "OK"
    assert result.long_net_move == pytest.approx(10.0)
    assert result.short_net_move == pytest.approx(-50.0)
    assert result.long_mfe == pytest.approx(10.0)
    assert result.long_mae == pytest.approx(-20.0)


def test_stale_entry_and_quote_gap_are_explicit():
    start = datetime(2026, 7, 25, tzinfo=UTC)
    quotes = [quote(start, 0, 100.0, 120.0), quote(start, 20, 101.0, 121.0), quote(start, 300, 130.0, 150.0)]
    evaluator = HfmEpisodeOutcomeEvaluator((300,), max_entry_age_ms=2_000, max_quote_gap_sec=10)
    assert evaluator.evaluate(quotes, signal_received_time=start + timedelta(seconds=5))[0].status == "ENTRY_STALE"
    assert evaluator.evaluate(quotes, signal_received_time=start + timedelta(seconds=1))[0].status == "QUOTE_GAP"


def test_missing_outcome_and_non_chronological_quotes_are_rejected():
    start = datetime(2026, 7, 25, tzinfo=UTC)
    evaluator = HfmEpisodeOutcomeEvaluator((300,))
    assert evaluator.evaluate([quote(start, 0, 100, 120)], signal_received_time=start)[0].status == "OUTCOME_MISSING"
    with pytest.raises(ValueError, match="chronological"):
        evaluator.evaluate([quote(start, 1, 100, 120), quote(start, 0, 100, 120)], signal_received_time=start)[0]
