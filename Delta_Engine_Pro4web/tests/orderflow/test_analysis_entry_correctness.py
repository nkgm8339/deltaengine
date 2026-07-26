from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.orderflow.analysis_entry_correctness import (
    AnalysisDecision,
    ObservedEntryBarReplayEvaluator,
    ReplayBar,
    ReplayPrice,
    ZeroSpreadReplayEvaluator,
    decisions_from_flow_rows,
    purge_overlapping_decisions,
)


UTC = timezone.utc
BASE = datetime(2026, 7, 25, tzinfo=UTC)


@dataclass(frozen=True)
class Row:
    event_time: datetime
    symbol: str
    window_sec: int
    state: str
    pressure_side: str
    last_price: float


def decision(
    second: int,
    *,
    side: str = "BUY",
    hypothesis: str = "EFFECTIVE_CONTINUATION",
) -> AnalysisDecision:
    return AnalysisDecision(
        decision_id=f"d-{second}-{side}-{hypothesis}",
        source_family="ROLLING_FLOW_RESPONSE",
        symbol="BTCUSDT",
        window_sec=300,
        state="BUY_EFFECTIVE",
        hypothesis=hypothesis,
        decision_class="ANALYSIS",
        side=side,
        decision_time=BASE + timedelta(seconds=second),
        observed_price=100.0,
    )


def test_flow_states_keep_analysis_and_stalled_probe_meanings_separate() -> None:
    rows = [
        Row(BASE, "BTCUSDT", 300, "BUY_EFFECTIVE", "BUY", 100.0),
        Row(BASE + timedelta(seconds=1), "BTCUSDT", 300, "BUY_TRAPPED", "BUY", 99.0),
        Row(BASE + timedelta(seconds=2), "BTCUSDT", 300, "SELL_STALLED", "SELL", 99.0),
    ]
    decisions = decisions_from_flow_rows(rows, source_family="ROLLING_FLOW_RESPONSE")
    assert [(value.hypothesis, value.side, value.decision_class) for value in decisions] == [
        ("EFFECTIVE_CONTINUATION", "BUY", "ANALYSIS"),
        ("TRAPPED_REVERSAL", "SELL", "ANALYSIS"),
        ("STALLED_PRESSURE_PROBE", "SELL", "ENTRY_PROBE"),
        ("STALLED_REVERSAL_PROBE", "BUY", "ENTRY_PROBE"),
    ]


def test_zero_spread_replay_uses_first_causal_prices_and_fixed_exit() -> None:
    prices = [
        ReplayPrice(BASE + timedelta(seconds=1), 100.0),
        ReplayPrice(BASE + timedelta(seconds=5), 99.0),
        ReplayPrice(BASE + timedelta(seconds=8), 103.0),
        ReplayPrice(BASE + timedelta(seconds=11), 102.0),
    ]
    outcome = ZeroSpreadReplayEvaluator(
        "BINANCE",
        prices,
        max_entry_lag_sec=2,
        max_outcome_lag_sec=2,
        max_data_gap_sec=10,
    ).evaluate([decision(0)], [10])[0]
    assert outcome.status == "OK"
    assert outcome.entry_time == BASE + timedelta(seconds=1)
    assert outcome.outcome_time == BASE + timedelta(seconds=11)
    assert outcome.direction_result == "CORRECT"
    assert round(outcome.signed_return_bps, 6) == 200.0
    assert round(outcome.mfe_bps, 6) == 300.0
    assert round(outcome.mae_bps, 6) == -100.0
    assert outcome.mfe_after_entry_sec == 7.0
    assert outcome.mae_after_entry_sec == 4.0


def test_sell_direction_is_scored_without_spread_or_exit_rule() -> None:
    prices = [
        ReplayPrice(BASE, 100.0),
        ReplayPrice(BASE + timedelta(seconds=10), 98.0),
    ]
    outcome = ZeroSpreadReplayEvaluator("HFM_MT5", prices).evaluate(
        [decision(0, side="SELL", hypothesis="TRAPPED_REVERSAL")],
        [10],
    )[0]
    assert outcome.status == "OK"
    assert outcome.direction_result == "CORRECT"
    assert round(outcome.signed_return_bps, 6) == 200.0


def test_entry_lag_and_path_gap_are_explicit() -> None:
    late = ZeroSpreadReplayEvaluator(
        "BINANCE",
        [ReplayPrice(BASE + timedelta(seconds=3), 100.0)],
        max_entry_lag_sec=2,
    ).evaluate([decision(0)], [10])[0]
    assert late.status == "ENTRY_LAG"

    gap = ZeroSpreadReplayEvaluator(
        "BINANCE",
        [
            ReplayPrice(BASE, 100.0),
            ReplayPrice(BASE + timedelta(seconds=10), 101.0),
        ],
        max_data_gap_sec=5,
    ).evaluate([decision(0)], [10])[0]
    assert gap.status == "DATA_GAP"


def test_nonoverlap_keeps_boundary_decision() -> None:
    values = [decision(0), decision(9), decision(10)]
    kept = purge_overlapping_decisions(values, horizon_sec=10)
    assert [value.decision_time for value in kept] == [
        BASE,
        BASE + timedelta(seconds=10),
    ]



def bar(minute: int, *, high: float, low: float, close: float) -> ReplayBar:
    open_time = BASE + timedelta(minutes=minute)
    return ReplayBar(
        open_time=open_time,
        close_time=open_time + timedelta(seconds=59, milliseconds=999),
        open=100.0,
        high=high,
        low=low,
        close=close,
    )


def test_observed_entry_bar_replay_uses_signal_trade_and_causal_full_bars() -> None:
    value = decision(10)
    outcome = ObservedEntryBarReplayEvaluator(
        "BINANCE",
        [
            bar(0, high=999.0, low=1.0, close=100.0),
            bar(1, high=103.0, low=99.0, close=102.0),
            bar(2, high=102.0, low=100.0, close=101.0),
        ],
    ).evaluate([value], [100])[0]
    assert outcome.status == "OK"
    assert outcome.entry_time == value.decision_time
    assert outcome.entry_price == value.observed_price
    assert outcome.entry_lag_ms == 0
    assert outcome.outcome_time == BASE + timedelta(minutes=1, seconds=59, milliseconds=999)
    assert outcome.outcome_lag_ms == 9999
    assert outcome.direction_result == "CORRECT"
    assert round(outcome.signed_return_bps, 6) == 200.0
    assert round(outcome.mfe_bps, 6) == 300.0
    assert round(outcome.mae_bps, 6) == -100.0


def test_observed_entry_bar_replay_rejects_missing_minute() -> None:
    outcome = ObservedEntryBarReplayEvaluator(
        "BINANCE",
        [
            bar(0, high=101.0, low=99.0, close=100.0),
            bar(2, high=102.0, low=100.0, close=101.0),
        ],
    ).evaluate([decision(0)], [100])[0]
    assert outcome.status == "OUTCOME_LAG"
