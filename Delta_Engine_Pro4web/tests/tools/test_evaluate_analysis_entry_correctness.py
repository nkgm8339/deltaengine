from __future__ import annotations

from datetime import datetime, timezone

from src.orderflow.analysis_entry_correctness import ZeroSpreadOutcome
from tools.evaluate_analysis_entry_correctness import _summary, render_markdown


UTC = timezone.utc
NOW = datetime(2026, 7, 25, tzinfo=UTC)


def outcome(result: str, signed: float) -> ZeroSpreadOutcome:
    return ZeroSpreadOutcome(
        market="BINANCE",
        decision_id=result,
        source_family="ROLLING_FLOW_RESPONSE",
        symbol="BTCUSDT",
        window_sec=300,
        state="BUY_EFFECTIVE",
        hypothesis="EFFECTIVE_CONTINUATION",
        decision_class="ANALYSIS",
        side="BUY",
        decision_time=NOW,
        horizon_sec=600,
        status="OK",
        entry_time=NOW,
        entry_price=100.0,
        entry_lag_ms=0,
        outcome_time=NOW,
        outcome_price=100.0,
        outcome_lag_ms=0,
        raw_return_bps=signed,
        signed_return_bps=signed,
        direction_result=result,
        mfe_bps=max(0.0, signed),
        mae_bps=min(0.0, signed),
        mfe_time=NOW,
        mae_time=NOW,
        mfe_after_entry_sec=0.0,
        mae_after_entry_sec=0.0,
    )


def test_summary_reports_direction_correctness_not_cost_result() -> None:
    rows = _summary(
        [outcome("CORRECT", 2.0), outcome("INCORRECT", -1.0)],
        scope="ALL_DECISIONS",
        detailed=False,
    )
    assert len(rows) == 1
    assert rows[0]["direction_correct_pct"] == 50.0
    assert rows[0]["median_signed_return_bps"] == 0.5
    assert "cost" not in rows[0]


def test_markdown_states_zero_spread_and_both_real_markets() -> None:
    summary = {
        "decision_class": "ANALYSIS",
        "market": "BINANCE",
        "source_family": "ROLLING_FLOW_RESPONSE",
        "window_sec": 300,
        "hypothesis": "EFFECTIVE_CONTINUATION",
        "horizon_sec": 600,
        "ok_count": 2,
        "correct_count": 1,
        "incorrect_count": 1,
        "direction_correct_pct": 50.0,
        "median_signed_return_bps": 0.5,
        "median_mfe_bps": 2.0,
        "median_mae_bps": -1.0,
    }
    report = {
        "metadata": {
            "generated_at": NOW.isoformat(),
            "decision_cutoff": NOW.isoformat(),
            "rolling_flow_rows": 2,
            "native_flow_rows": 0,
            "decision_count": 2,
            "binance_bar_count": 10,
            "binance_local_raw_price_count": 20,
            "hfm_price_count": 10,
        },
        "binance_bar_metadata": {"gap_count": 0},
        "binance_signal_price_audit": {
            "within_official_bar_range_pct": 100.0,
        },
        "market_agreement": [
            {
                "scope": "ALL_DECISIONS",
                "paired_ok_count": 2,
                "same_direction_result_pct": 100.0,
                "signed_return_correlation": 1.0,
                "median_absolute_signed_return_difference_bps": 0.1,
            }
        ],
        "analysis_summaries": [summary],
        "entry_summaries": [summary],
    }
    markdown = render_markdown(report)
    assert "Binance: Flow eventに保存されたsignal実約定価格" in markdown
    assert "HFM: 接続中MT5" in markdown
    assert "spread、手数料、slippage" in markdown

