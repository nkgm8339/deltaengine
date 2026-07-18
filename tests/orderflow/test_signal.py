"""Tests for src.orderflow.signal — M10 SignalEngine.

TV-SIG-01 through TV-SIG-07 are verbatim from TestSpecification_v3.2 §4.5.
Additional tests cover decisions 7 (None excluded from denominator), 8 (veto
direction logic + strength boundary), and deterministic replay.

Fixture (per TestSpecification §4.5):
    w_cvd=w_fp=w_imb=1.0, confidence_threshold=0.6, absorption_veto_threshold=0.5
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.orderflow.absorption import AbsorptionResult
from src.orderflow.signal import (
    REASON_ABSORPTION_VETO,
    REASON_CVD_DOWN,
    REASON_CVD_UP,
    REASON_FOOTPRINT_BUY,
    REASON_LOW_CONFIDENCE,
    REASON_NO_INPUT,
    REASON_STACKED_IMBALANCE,
    SignalEngine,
)

D = Decimal


def _eng() -> SignalEngine:
    return SignalEngine(
        w_cvd=D("1.0"),
        w_fp=D("1.0"),
        w_imb=D("1.0"),
        confidence_threshold=D("0.6"),
        absorption_veto_threshold=D("0.5"),
    )


def _absorption(cls: str, strength: str = "1.0") -> AbsorptionResult:
    return AbsorptionResult(classification=cls, strength=D(strength))


# ============================ TV-SIG-01 BUY signal ===========================
def test_tv_sig_01_buy_signal() -> None:
    r = _eng().evaluate(D(80), D(60), D(70))
    assert r.composite == D(70)
    assert r.confidence == D("0.70")
    assert r.signal == "BUY"
    assert REASON_CVD_UP in r.reasons
    assert REASON_FOOTPRINT_BUY in r.reasons
    assert REASON_STACKED_IMBALANCE in r.reasons


# ============================ TV-SIG-02 Confidence boundary (qualify) ========
def test_tv_sig_02_confidence_boundary_qualify() -> None:
    r = _eng().evaluate(D(60), D(60), D(60))
    assert r.composite == D(60)
    assert r.confidence == D("0.60")
    assert r.signal == "BUY"


# ============================ TV-SIG-03 Confidence boundary (not qualify) ====
def test_tv_sig_03_confidence_boundary_not_qualify() -> None:
    r = _eng().evaluate(D(50), D(50), D(50))
    assert r.composite == D(50)
    assert r.confidence == D("0.50")
    assert r.signal == "WAIT"
    assert REASON_LOW_CONFIDENCE in r.reasons


# ============================ TV-SIG-04 Absorption veto ======================
def test_tv_sig_04_absorption_veto() -> None:
    """Stub AbsorptionResult manually constructed (decision 8 / web-Code agreement)."""
    r = _eng().evaluate(
        D(80), D(80), D(80),
        absorption_result=_absorption("SELL_ABSORPTION", "1.0"),
    )
    assert r.signal == "WAIT"
    assert REASON_ABSORPTION_VETO in r.reasons


# ============================ TV-SIG-05 SELL signal ==========================
def test_tv_sig_05_sell_signal() -> None:
    r = _eng().evaluate(D(-90), D(-70), D(-80))
    assert r.composite == D(-80)
    assert r.confidence == D("0.80")
    assert r.signal == "SELL"


# ============================ TV-SIG-06 Missing input ========================
def test_tv_sig_06_missing_input_imbalance() -> None:
    """Imbalance disabled (None); cvd +90, fp +90 → composite = (90+90)/2 = 90."""
    r = _eng().evaluate(D(90), D(90), None)
    assert r.composite == D(90)
    assert r.confidence == D("0.90")
    assert r.signal == "BUY"


# ============================ TV-SIG-07 No input =============================
def test_tv_sig_07_no_input() -> None:
    r = _eng().evaluate(None, None, None)
    assert r.signal == "WAIT"
    assert r.reasons == (REASON_NO_INPUT,)


# ============================ Decision 7: None excluded from denominator =====
def test_decision7_none_excluded_from_denominator() -> None:
    """Two modules active (w=1.0 each); composite = (60+60)/2 = 60, not /3."""
    r = _eng().evaluate(D(60), D(60), None)
    # If None were treated as 0 and kept in denominator: (60+60+0)/3 = 40 → WAIT
    # Correct (excluded): (60+60)/2 = 60 → confidence=0.60 → BUY
    assert r.composite == D(60)
    assert r.signal == "BUY"


def test_decision7_single_module_active() -> None:
    """Only fp_score provided; composite = fp_score itself (weight /weight = 1)."""
    r = _eng().evaluate(None, D(70), None)
    assert r.composite == D(70)
    assert r.signal == "BUY"


# ============================ Decision 8: veto direction logic ===============
def test_decision8_same_direction_absorption_no_veto() -> None:
    """BUY_ABSORPTION while composite direction=+1 → same direction → no veto."""
    r = _eng().evaluate(
        D(80), D(80), D(80),
        absorption_result=_absorption("BUY_ABSORPTION", "1.0"),
    )
    assert r.signal == "BUY"
    assert REASON_ABSORPTION_VETO not in r.reasons


def test_decision8_strength_below_threshold_no_veto() -> None:
    """SELL_ABSORPTION strength=0.49 < veto_threshold=0.5 → no veto."""
    r = _eng().evaluate(
        D(80), D(80), D(80),
        absorption_result=_absorption("SELL_ABSORPTION", "0.49"),
    )
    assert r.signal == "BUY"
    assert REASON_ABSORPTION_VETO not in r.reasons


def test_decision8_strength_at_threshold_triggers_veto() -> None:
    """SELL_ABSORPTION strength=0.5 == veto_threshold → veto fires."""
    r = _eng().evaluate(
        D(80), D(80), D(80),
        absorption_result=_absorption("SELL_ABSORPTION", "0.5"),
    )
    assert r.signal == "WAIT"
    assert REASON_ABSORPTION_VETO in r.reasons


def test_decision8_sell_direction_buy_absorption_veto() -> None:
    """BUY_ABSORPTION while composite direction=−1 → against direction → veto."""
    r = _eng().evaluate(
        D(-80), D(-80), D(-80),
        absorption_result=_absorption("BUY_ABSORPTION", "1.0"),
    )
    assert r.signal == "WAIT"
    assert REASON_ABSORPTION_VETO in r.reasons


# ============================ Deterministic replay ===========================
def test_deterministic_replay() -> None:
    eng = _eng()
    r1 = eng.evaluate(D(80), D(60), D(70))
    r2 = eng.evaluate(D(80), D(60), D(70))
    assert r1 == r2


# ============================ Score-derived reason codes =====================
def test_cvd_down_reason_for_negative_score() -> None:
    r = _eng().evaluate(D(-80), D(-60), D(-70))
    assert REASON_CVD_DOWN in r.reasons


def test_score_below_50_no_reason_code() -> None:
    """Scores below |50| don't generate score-derived reason codes."""
    r = _eng().evaluate(D(40), D(40), D(40))
    assert REASON_CVD_UP not in r.reasons
    assert REASON_FOOTPRINT_BUY not in r.reasons
    assert REASON_STACKED_IMBALANCE not in r.reasons
