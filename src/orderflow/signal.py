"""Compatibility signal result for the retired composite engine."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from .cvd import _to_decimal

_ZERO = Decimal(0)
REASON_CVD_UP = "CVD_UP"
REASON_CVD_DOWN = "CVD_DOWN"
REASON_FOOTPRINT_BUY = "FOOTPRINT_BUY"
REASON_FOOTPRINT_SELL = "FOOTPRINT_SELL"
REASON_STACKED_IMBALANCE = "STACKED_IMBALANCE"
REASON_ABSORPTION_VETO = "ABSORPTION_VETO"
REASON_LOW_CONFIDENCE = "LOW_CONFIDENCE"
REASON_NO_INPUT = "NO_INPUT"
REASON_FLOW_BUY = "FLOW_BUY"
REASON_FLOW_SELL = "FLOW_SELL"


@dataclass(frozen=True)
class SignalResult:
    composite: Decimal
    confidence: Decimal
    signal: str
    reasons: tuple[str, ...]
    flow_score: Optional[Decimal] = None


class SignalEngine:
    """Compatibility shell; all five indicators are independent."""

    def __init__(self, w_cvd, w_fp, w_imb, confidence_threshold,
                 absorption_veto_threshold, w_flow=Decimal("0.0"),
                 flow_scorer=None) -> None:
        self.w_cvd = _to_decimal(w_cvd)
        self.w_fp = _to_decimal(w_fp)
        self.w_imb = _to_decimal(w_imb)
        self.confidence_threshold = _to_decimal(confidence_threshold)
        self.absorption_veto_threshold = _to_decimal(absorption_veto_threshold)
        self.w_flow = _to_decimal(w_flow)

    @classmethod
    def from_config(cls, config) -> "SignalEngine":
        s = config.signal
        w = s.weight
        return cls(w["cvd"], w["footprint"], w["imbalance"],
                   s.confidence_threshold, s.absorption_veto_threshold,
                   w.get("flow", 0.0))

    def evaluate(self, cvd_score=None, fp_score=None, imb_score=None,
                 absorption_result=None, flow_events=None) -> SignalResult:
        """Return fixed NO_INPUT for backward-compatible storage callers."""
        return SignalResult(_ZERO, _ZERO, "WAIT", (REASON_NO_INPUT,), None)
