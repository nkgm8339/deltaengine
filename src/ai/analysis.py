"""AI Analysis Engine (MOD-009, AIAnalysisPipelineReference_v3.0).

Deterministic rule-based evaluation (§5): aggregates SignalResult, CVD, Footprint,
Imbalance, and Absorption into a human-readable market state assessment.

market_state thresholds (AIAnalysisPipelineReference §MarketState + §Confidence):
    BUY  + confidence >= 0.90 -> STRONG_BULL
    BUY  + confidence >= 0.70 -> BULL
    BUY  + confidence <  0.70 -> NEUTRAL
    SELL + confidence >= 0.90 -> STRONG_BEAR
    SELL + confidence >= 0.70 -> BEAR
    SELL + confidence <  0.70 -> NEUTRAL
    WAIT + any                -> NEUTRAL
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from ..orderflow.absorption import AbsorptionResult
from ..orderflow.imbalance import ImbalanceResult
from ..orderflow.signal import SignalResult

_ZERO = Decimal(0)


@dataclass(frozen=True)
class AnalysisInput:
    analysis_time: datetime
    symbol: str
    signal_result: SignalResult
    cvd_delta: Decimal
    fp_buy_total: Decimal
    fp_sell_total: Decimal
    imbalance_result: Optional[ImbalanceResult]
    absorption_result: Optional[AbsorptionResult]


@dataclass(frozen=True)
class AnalysisResult:
    analysis_time: datetime
    symbol: str
    market_state: str       # STRONG_BULL | BULL | NEUTRAL | BEAR | STRONG_BEAR
    confidence: Decimal     # 0.0-1.0
    risk_level: str         # LOW | MEDIUM | HIGH
    summary: str
    reasons: tuple[str, ...]


class AnalysisEngine:
    """Rule-based aggregation of module outputs into a market state."""

    def __init__(self, confidence_threshold: Decimal = Decimal("0.70")) -> None:
        self.confidence_threshold = Decimal(str(confidence_threshold))

    def evaluate(self, inp: AnalysisInput) -> AnalysisResult:
        sr = inp.signal_result
        conf = sr.confidence
        sig = sr.signal

        # market_state
        if sig == "BUY":
            if conf >= Decimal("0.90"):
                market_state = "STRONG_BULL"
            elif conf >= Decimal("0.70"):
                market_state = "BULL"
            else:
                market_state = "NEUTRAL"
        elif sig == "SELL":
            if conf >= Decimal("0.90"):
                market_state = "STRONG_BEAR"
            elif conf >= Decimal("0.70"):
                market_state = "BEAR"
            else:
                market_state = "NEUTRAL"
        else:
            market_state = "NEUTRAL"

        # risk_level
        if sig != "WAIT" and inp.absorption_result is not None:
            risk_level = "MEDIUM"
        elif sig == "WAIT" or conf < self.confidence_threshold:
            risk_level = "HIGH"
        else:
            risk_level = "LOW"

        # reasons: inherit from SignalResult + ABSORPTION_ACTIVE if present
        reasons = list(sr.reasons)
        if inp.absorption_result is not None:
            reasons.append("ABSORPTION_ACTIVE")

        # summary
        summary = f"{market_state}: {sig} signal at {conf:.0%} confidence"

        return AnalysisResult(
            analysis_time=inp.analysis_time,
            symbol=inp.symbol,
            market_state=market_state,
            confidence=conf,
            risk_level=risk_level,
            summary=summary,
            reasons=tuple(reasons),
        )
