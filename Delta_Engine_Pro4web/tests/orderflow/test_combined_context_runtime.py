from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.orderflow.combined_context_runtime import CombinedContextObserver, HfmQuote
from src.orderflow.cvd import Candle


UTC = timezone.utc
START = datetime(2026, 7, 24, 0, 0, tzinfo=UTC)


def candle(minutes: int, close: str, cvd: str, *, timeframe: str = "5m") -> Candle:
    value = Decimal(close)
    return Candle(
        bar_time=START + timedelta(minutes=minutes),
        symbol="BTCUSDT",
        timeframe=timeframe,
        open=value - Decimal("1"),
        high=value + Decimal("1"),
        low=value - Decimal("2"),
        close=value,
        volume=Decimal("10"),
        delta=Decimal("2"),
        cvd=Decimal(cvd),
    )


def quote(at: datetime, bid: str, ask: str, sequence: int = 1) -> HfmQuote:
    return HfmQuote(
        symbol="#BTCUSDr",
        source_time=at,
        received_time=at,
        sequence=sequence,
        bid=Decimal(bid),
        ask=Decimal(ask),
    )


def test_observer_builds_5m_context_and_both_executable_hfm_sides():
    observer = CombinedContextObserver("BTCUSDT", horizons_sec=(180,))
    for seconds, value in ((600, "100"), (890, "110")):
        observer.observe_oi_sample({
            "source_time": START + timedelta(seconds=seconds),
            "symbol": "BTCUSDT",
            "open_interest": Decimal(value),
        })

    assert observer.register_candle(candle(0, "100", "1")) is None
    assert observer.register_candle(candle(5, "101", "2")) is None
    entry_time = START + timedelta(minutes=15)
    observer.observe_hfm_quote(quote(entry_time, "100", "102"))
    event = observer.register_candle(
        candle(10, "103", "3"),
        decision_time=entry_time + timedelta(milliseconds=100),
    )

    assert event is not None
    assert event.context.code == "P1_BUILDING"
    assert event.oi_open == Decimal("100")
    assert event.oi_close == Decimal("110")
    assert event.oi_change == Decimal("10")
    assert event.oi_sample_count == 2
    assert event.hfm_entry_status == "LIVE"

    outcomes = observer.observe_hfm_quote(
        quote(entry_time + timedelta(seconds=180), "105", "107", sequence=2)
    )
    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome.status == "OK"
    assert outcome.long_net_usd == Decimal("3")  # entry Ask 102 -> exit Bid 105
    assert outcome.short_net_usd == Decimal("-7")  # entry Bid 100 -> exit Ask 107
    assert outcome.long_mfe_usd == Decimal("3")
    assert outcome.long_mae_usd == Decimal("-2")
    assert outcome.short_mfe_usd == Decimal("-2")
    assert outcome.short_mae_usd == Decimal("-7")


def test_observer_keeps_missing_oi_and_stale_hfm_explicit():
    observer = CombinedContextObserver("BTCUSDT", horizons_sec=(180,))
    assert observer.register_candle(candle(0, "100", "1")) is None
    assert observer.register_candle(candle(5, "101", "2")) is None
    old_quote = quote(START, "100", "102")
    observer.observe_hfm_quote(old_quote)
    event = observer.register_candle(
        candle(10, "103", "3"),
        decision_time=START + timedelta(minutes=15),
    )
    assert event is not None
    assert event.context.code == "P1_MISSING"
    assert event.hfm_entry_status == "STALE"
    assert event.hfm_entry is None
    assert observer.pending_outcomes == 0


def test_hfm_outcome_marks_late_first_quote_as_gap_without_hiding_values():
    observer = CombinedContextObserver(
        "BTCUSDT",
        horizons_sec=(180,),
        hfm_outcome_max_lag_ms=100,
    )
    for seconds, value in ((600, "100"), (890, "101")):
        observer.observe_oi_sample({
            "source_time": START + timedelta(seconds=seconds),
            "symbol": "BTCUSDT",
            "open_interest": Decimal(value),
        })
    observer.register_candle(candle(0, "100", "1"))
    observer.register_candle(candle(5, "101", "2"))
    entry_time = START + timedelta(minutes=15)
    observer.observe_hfm_quote(quote(entry_time, "100", "102"))
    observer.register_candle(candle(10, "103", "3"), decision_time=entry_time)

    outcome = observer.observe_hfm_quote(
        quote(entry_time + timedelta(seconds=181), "103", "105", sequence=2)
    )[0]
    assert outcome.status == "QUOTE_GAP"
    assert outcome.quote_lag_ms == 1000
    assert outcome.long_net_usd == Decimal("1")

