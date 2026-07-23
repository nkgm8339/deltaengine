from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tools.evaluate_flow_strategies import (
    Bar,
    FlowEvent,
    Signal,
    Trade,
    build_strategy_a_signals,
    build_strategy_b_signals,
    purge_overlaps,
    render_markdown,
    signals_to_trades,
)


UTC = timezone.utc
BASE = datetime(2026, 7, 23, tzinfo=UTC)


def event(
    minute: int,
    state: str,
    *,
    side: str = "BUY",
    price: float = 100.0,
) -> FlowEvent:
    return FlowEvent(
        event_time=BASE + timedelta(minutes=minute, seconds=10),
        symbol="BTCUSDT",
        window_sec=300,
        state=state,
        pressure_side=side,
        pressure_ratio=0.30,
        persistence=0.65,
        relative_volume=0.80,
        last_price=price,
    )


def bar(minute: int, open_: float, high: float, low: float, close: float) -> Bar:
    return Bar(BASE + timedelta(minutes=minute), open_, high, low, close)


def test_strategy_a_waits_for_future_retest_and_uses_pressure_side() -> None:
    ranges = {
        "pressure_strength": (0.20, 0.40),
        "persistence": (0.60, 0.70),
        "relative_volume": (0.50, 0.90),
    }
    settings = {
        "name": "A",
        "window_sec": 300,
        "state_suffix": "_EFFECTIVE",
        "retest_timeout_sec": 300,
    }
    signals = build_strategy_a_signals(
        [event(0, "BUY_EFFECTIVE")],
        [bar(1, 100.2, 100.3, 99.9, 100.1)],
        ranges,
        settings,
    )
    assert len(signals) == 1
    assert signals[0].side == "LONG"
    assert signals[0].entry_price == 100.0
    assert signals[0].entry_time == BASE + timedelta(minutes=2)


def test_strategy_b_requires_effective_failure_confirmation_and_retest() -> None:
    settings = {
        "name": "B",
        "window_sec": 300,
        "effective_suffix": "_EFFECTIVE",
        "failure_suffixes": ["_STALLED", "_TRAPPED"],
        "effective_lookback_sec": 900,
        "confirmation_bps": 2.0,
        "confirmation_timeout_sec": 300,
        "retest_timeout_sec": 300,
    }
    signals = build_strategy_b_signals(
        [event(0, "BUY_EFFECTIVE"), event(5, "BUY_STALLED")],
        [
            bar(6, 100.0, 100.0, 99.9, 99.95),
            bar(7, 99.94, 99.96, 99.90, 99.92),
        ],
        settings,
    )
    assert len(signals) == 1
    assert signals[0].side == "SHORT"
    assert signals[0].entry_price == 99.95
    assert signals[0].entry_time == BASE + timedelta(minutes=8)


def test_outcome_is_causal_and_overlap_purge_keeps_first_trade() -> None:
    signal = Signal(
        strategy="A",
        source_event_time=BASE - timedelta(minutes=1),
        entry_time=BASE,
        side="LONG",
        entry_price=100.0,
        state="BUY_EFFECTIVE",
        pressure_side="BUY",
        pressure_ratio=0.3,
        persistence=0.65,
        relative_volume=0.8,
    )
    bars = [
        bar(minute, 100.0, 102.0 if minute == 14 else 101.0, 99.0, 102.0 if minute == 14 else 100.0)
        for minute in range(15)
    ]
    trades, audit = signals_to_trades([signal], bars, [], 900)
    assert audit["trades_built"] == 1
    assert round(trades[0].gross_bps, 6) == 200.0
    overlapping = Trade(
        **{
            **trades[0].__dict__,
            "source_event_time": BASE,
            "entry_time": BASE + timedelta(minutes=5),
            "exit_time": BASE + timedelta(minutes=20),
        }
    )
    assert purge_overlaps([overlapping, trades[0]]) == [trades[0]]


def test_markdown_handles_decimal_cost_keys() -> None:
    metric = {"count": 1, "mean": 2.0}
    test = {
        "gross": metric,
        "cost_scenarios": {
            "1.5_bps": {"mean": 0.5},
            "3_bps": {"mean": -1.0},
            "4.5_bps": {"mean": -2.5},
        },
        "classification": "INSUFFICIENT_NEGATIVE",
    }
    report = {
        "overall_classification": "INSUFFICIENT_DATA_NO_DEPLOYMENT",
        "data_audit": {
            "events": {"unique_clean_rows": 1},
            "bars": {"unique_clean_rows": 1},
            "event_time_min": "a", "event_time_max": "b",
            "bar_time_min": "a", "bar_time_max": "b",
        },
        "split": {"train_before": "a", "test_from_after_embargo": "b"},
        "results": {"A": {"900": {"horizon_sec": 900, "test": test}}},
        "strategy_a_frozen_training_ranges": {},
        "limitations": [],
    }
    markdown = render_markdown(report)
    assert "+0.500" in markdown
    assert "-2.500" in markdown
