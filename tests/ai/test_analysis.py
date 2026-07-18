"""Unit tests for AnalysisEngine (MOD-009), 8 tests."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from src.ai.analysis import AnalysisEngine, AnalysisInput, AnalysisResult
from src.orderflow.absorption import AbsorptionResult
from src.orderflow.signal import SignalResult

UTC = timezone.utc
D = Decimal
_T0 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
_ENG = AnalysisEngine(confidence_threshold=D("0.70"))


def _inp(signal: str, confidence: str, absorption: bool = False) -> AnalysisInput:
    sr = SignalResult(
        composite=D("50") if signal == "BUY" else D("-50") if signal == "SELL" else D("0"),
        confidence=D(confidence),
        signal=signal,
        reasons=(),
    )
    return AnalysisInput(
        analysis_time=_T0,
        symbol="BTCUSDT",
        signal_result=sr,
        cvd_delta=D("0"),
        fp_buy_total=D("0"),
        fp_sell_total=D("0"),
        imbalance_result=None,
        absorption_result=AbsorptionResult("BUY_ABSORPTION", D("1.0")) if absorption else None,
    )


# ── 1. STRONG_BULL ────────────────────────────────────────────────────────────

def test_strong_bull() -> None:
    result = _ENG.evaluate(_inp("BUY", "0.95"))
    assert result.market_state == "STRONG_BULL"
    assert result.confidence == D("0.95")
    assert result.risk_level == "LOW"
    assert "STRONG_BULL" in result.summary
    assert "BUY" in result.summary


# ── 2. BULL ───────────────────────────────────────────────────────────────────

def test_bull() -> None:
    result = _ENG.evaluate(_inp("BUY", "0.75"))
    assert result.market_state == "BULL"
    assert result.risk_level == "LOW"


# ── 3. NEUTRAL from BUY (low confidence) ─────────────────────────────────────

def test_neutral_from_buy_low_confidence() -> None:
    result = _ENG.evaluate(_inp("BUY", "0.50"))
    assert result.market_state == "NEUTRAL"
    assert result.risk_level == "HIGH"   # confidence < threshold=0.70


# ── 4. STRONG_BEAR ───────────────────────────────────────────────────────────

def test_strong_bear() -> None:
    result = _ENG.evaluate(_inp("SELL", "0.92"))
    assert result.market_state == "STRONG_BEAR"
    assert result.risk_level == "LOW"
    assert "SELL" in result.summary


# ── 5. BEAR ───────────────────────────────────────────────────────────────────

def test_bear() -> None:
    result = _ENG.evaluate(_inp("SELL", "0.80"))
    assert result.market_state == "BEAR"
    assert result.risk_level == "LOW"


# ── 6. NEUTRAL from WAIT ─────────────────────────────────────────────────────

def test_neutral_from_wait() -> None:
    result = _ENG.evaluate(_inp("WAIT", "0.30"))
    assert result.market_state == "NEUTRAL"
    assert result.risk_level == "HIGH"


# ── 7. risk_level MEDIUM (absorption present, signal != WAIT) ────────────────

def test_risk_medium_absorption() -> None:
    result = _ENG.evaluate(_inp("BUY", "0.91", absorption=True))
    assert result.market_state == "STRONG_BULL"
    assert result.risk_level == "MEDIUM"
    assert "ABSORPTION_ACTIVE" in result.reasons


# ── 8. deterministic replay ───────────────────────────────────────────────────

def test_deterministic_replay() -> None:
    inp = _inp("SELL", "0.72")
    assert _ENG.evaluate(inp) == _ENG.evaluate(inp)
