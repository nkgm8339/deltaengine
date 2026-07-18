"""Tests for FlowScorer + SignalEngine.evaluate() flow integration (Phase E)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Sequence

import pytest

from src.orderflow.flow_detector import FlowEvent
from src.orderflow.signal import (
    FlowScorer,
    REASON_FLOW_BUY,
    REASON_FLOW_SELL,
    SimpleAverageFlowScorer,
    SignalEngine,
    SignalResult,
    score_flow_events,
)

D = Decimal


def _evt(side: str, strength: str, kind: str = "large_trade") -> FlowEvent:
    return FlowEvent(
        event_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
        kind=kind,
        side=side,
        price=D("100"),
        strength=D(strength),
        detail={},
    )


def _eng(w_flow: str = "1.0") -> SignalEngine:
    return SignalEngine(
        w_cvd=D("1.0"),
        w_fp=D("1.0"),
        w_imb=D("1.0"),
        w_flow=D(w_flow),
        confidence_threshold=D("0.6"),
        absorption_veto_threshold=D("0.5"),
    )


# ── SimpleAverageFlowScorer ───────────────────────────────────────────────────

def test_scorer_empty_returns_none() -> None:
    scorer = SimpleAverageFlowScorer()
    assert scorer.score([]) is None


def test_scorer_buy_events_positive_score() -> None:
    scorer = SimpleAverageFlowScorer()
    events = [_evt("BUY", "1.0"), _evt("BUY", "0.5")]
    result = scorer.score(events)
    assert result is not None
    assert result > D("0")


def test_scorer_sell_events_negative_score() -> None:
    scorer = SimpleAverageFlowScorer()
    events = [_evt("SELL", "1.0"), _evt("SELL", "1.0")]
    result = scorer.score(events)
    assert result is not None
    assert result == D("-100")


def test_scorer_neutral_dilutes_signal() -> None:
    scorer = SimpleAverageFlowScorer()
    # 1 BUY(1.0) + 1 NEUTRAL → average = (100 + 0)/2 = 50
    events = [_evt("BUY", "1.0"), _evt("NEUTRAL", "0.5")]
    result = scorer.score(events)
    assert result == D("50")


def test_scorer_mixed_buy_sell_averages() -> None:
    scorer = SimpleAverageFlowScorer()
    # BUY 100 + SELL -60 = 40 / 2 = 20
    events = [_evt("BUY", "1.0"), _evt("SELL", "0.6")]
    result = scorer.score(events)
    assert result == D("20")


def test_scorer_clamped_to_100() -> None:
    scorer = SimpleAverageFlowScorer()
    events = [_evt("BUY", "1.0")] * 5
    result = scorer.score(events)
    assert result == D("100")


# ── score_flow_events standalone function ─────────────────────────────────────

def test_score_flow_events_uses_default_scorer() -> None:
    events = [_evt("BUY", "1.0")]
    result = score_flow_events(events)
    assert result == D("100")


def test_score_flow_events_accepts_custom_scorer() -> None:
    """Demonstrates scorer swap-in via Protocol."""

    class ConstantScorer:
        def score(self, events: Sequence[FlowEvent]) -> Optional[Decimal]:
            return D("42") if events else None

    result = score_flow_events([_evt("SELL", "1.0")], scorer=ConstantScorer())
    assert result == D("42")


def test_custom_scorer_satisfies_protocol() -> None:
    class MyScorer:
        def score(self, events: Sequence[FlowEvent]) -> Optional[Decimal]:
            return D("0")

    assert isinstance(MyScorer(), FlowScorer)


# ── SignalEngine.evaluate() with flow_events ──────────────────────────────────

def test_flow_disabled_when_w_flow_zero() -> None:
    eng = SignalEngine(
        w_cvd=D("1.0"), w_fp=D("1.0"), w_imb=D("1.0"),
        w_flow=D("0.0"),
        confidence_threshold=D("0.6"), absorption_veto_threshold=D("0.5"),
    )
    events = [_evt("BUY", "1.0")] * 10
    result = eng.evaluate(D("60"), D("60"), D("60"), flow_events=events)
    assert result.flow_score is None


def test_flow_none_events_excluded_from_composite() -> None:
    eng = _eng("1.0")
    # No flow_events → flow_score=None → excluded from weighted average
    r_no_flow = eng.evaluate(D("60"), D("60"), D("60"))
    r_with_none = eng.evaluate(D("60"), D("60"), D("60"), flow_events=None)
    assert r_no_flow.flow_score is None
    assert r_with_none.flow_score is None
    assert r_no_flow.composite == r_with_none.composite


def test_flow_score_included_in_composite() -> None:
    eng = _eng("1.0")
    # cvd=60, fp=60, imb=60, flow=100 → composite = (60+60+60+100)/4 = 70
    events = [_evt("BUY", "1.0")]
    result = eng.evaluate(D("60"), D("60"), D("60"), flow_events=events)
    assert result.flow_score == D("100")
    assert result.composite == D("70")


def test_flow_reason_buy_added_above_threshold() -> None:
    eng = _eng("1.0")
    events = [_evt("BUY", "1.0")]  # flow_score=100 >= 50
    result = eng.evaluate(D("80"), D("80"), D("80"), flow_events=events)
    assert REASON_FLOW_BUY in result.reasons


def test_flow_reason_sell_added_above_threshold() -> None:
    eng = _eng("1.0")
    events = [_evt("SELL", "1.0")]  # flow_score=-100
    result = eng.evaluate(D("-80"), D("-80"), D("-80"), flow_events=events)
    assert REASON_FLOW_SELL in result.reasons


def test_flow_reason_absent_below_threshold() -> None:
    eng = _eng("1.0")
    events = [_evt("BUY", "0.4")]  # flow_score=40 < 50 → no FLOW_BUY reason
    result = eng.evaluate(D("60"), D("60"), D("60"), flow_events=events)
    assert REASON_FLOW_BUY not in result.reasons


def test_backward_compat_no_flow_args() -> None:
    """Existing call sites without flow_events/w_flow remain unaffected."""
    eng = SignalEngine(
        w_cvd=D("1.0"), w_fp=D("1.0"), w_imb=D("1.0"),
        confidence_threshold=D("0.6"), absorption_veto_threshold=D("0.5"),
    )
    result = eng.evaluate(D("80"), D("60"), D("70"))
    assert result.signal == "BUY"
    assert result.flow_score is None
