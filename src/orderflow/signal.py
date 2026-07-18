"""SignalEngine — weighted scoring + Absorption veto (MOD-007, SignalEngine_v3.1).

Spec: ArchitectureRepository/30_Modules/SignalEngine_v3.1.md.
Test vectors: ArchitectureRepository/50_Test/TestSpecification_v3.2.md §4.5
(TV-SIG-01 through TV-SIG-07).

Composite scoring (§4.2):
    composite  = Σ(w_i × score_i) / Σ(w_i)   — enabled modules only
    confidence = |composite| / 100
    direction  = sign(composite)

Absorption veto (§4.3):
    SELL_ABSORPTION while direction=+1, or BUY_ABSORPTION while direction=−1,
    with strength >= absorption_veto_threshold → forced WAIT + ABSORPTION_VETO.

Design (instruction §3 decisions 7/8/9):
    - All score inputs are Optional[Decimal]. None = module disabled/absent;
      excluded from both numerator and denominator (decision 7).
    - AbsorptionResult.classification distinguishes BUY/SELL absorption to avoid
      confusion with composite direction (decision 8).
    - reasons = union of all applicable codes; not mutually exclusive (decision 9).
    - Decimal arithmetic only — no float.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Protocol, runtime_checkable

from .absorption import AbsorptionResult
from .cvd import _to_decimal
from .flow_detector import FlowEvent
from .imbalance import ImbalanceResult

logger = logging.getLogger("orderflow.signal")

_ZERO = Decimal(0)
_ONE_HUNDRED = Decimal(100)

# Reason codes (SignalEngine_v3.1 §6).
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

# Score magnitude threshold for contributing reason codes (§6 table).
_REASON_SCORE_THRESHOLD = Decimal(50)

# Absorption classifications.
_BUY_ABSORPTION = "BUY_ABSORPTION"
_SELL_ABSORPTION = "SELL_ABSORPTION"


# ── FlowScorer strategy ──────────────────────────────────────────────────────

@runtime_checkable
class FlowScorer(Protocol):
    """Strategy for converting a sequence of FlowEvents to a score in [-100, +100].

    Implement this Protocol to swap in time-decay, volume-weighted,
    or detector-specific weighting in place of the default simple average.
    """

    def score(self, events: Sequence[FlowEvent]) -> Optional[Decimal]:
        """Return a score in [-100, +100], or None when events carry no signal."""
        ...


class SimpleAverageFlowScorer:
    """Default scorer: unweighted mean of (BUY→+strength×100, SELL→-strength×100, NEUTRAL→0).

    Extend or replace to support time decay, volume weighting, or per-kind weights.
    """

    def score(self, events: Sequence[FlowEvent]) -> Optional[Decimal]:
        """Average directional strength across all events; None when list is empty."""
        if not events:
            return None
        vals: list[Decimal] = []
        for e in events:
            if e.side == "BUY":
                vals.append(e.strength * _ONE_HUNDRED)
            elif e.side == "SELL":
                vals.append(-e.strength * _ONE_HUNDRED)
            else:  # NEUTRAL
                vals.append(_ZERO)
        raw = sum(vals, _ZERO) / Decimal(str(len(vals)))
        return _clamp(raw)


_DEFAULT_FLOW_SCORER: FlowScorer = SimpleAverageFlowScorer()


def score_flow_events(
    events: Sequence[FlowEvent],
    scorer: FlowScorer = _DEFAULT_FLOW_SCORER,
) -> Optional[Decimal]:
    """Convert FlowEvents to a composite score via the provided scorer strategy.

    Callable independently of SignalEngine — mirrors score_cvd / score_footprint /
    score_imbalance as a module-level utility. Pass a custom FlowScorer to swap
    the algorithm without touching SignalEngine.
    """
    return scorer.score(events)


# ── Output type ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SignalResult:
    """Output of SignalEngine.evaluate() — one result per evaluation window."""

    composite: Decimal
    confidence: Decimal
    signal: str             # "BUY" | "SELL" | "WAIT"
    reasons: tuple[str, ...]
    flow_score: Optional[Decimal] = None  # None when flow disabled or no events


class SignalEngine:
    """Combines normalised module scores into a trading signal.

    Inputs are pre-normalised scores in [-100, +100] (caller's responsibility).
    Stateless: evaluate() is deterministic and has no side effects.
    """

    def __init__(
        self,
        w_cvd: Decimal,
        w_fp: Decimal,
        w_imb: Decimal,
        confidence_threshold: Decimal,
        absorption_veto_threshold: Decimal,
        w_flow: Decimal = Decimal("0.0"),
        flow_scorer: Optional[FlowScorer] = None,
    ) -> None:
        self.w_cvd = _to_decimal(w_cvd)
        self.w_fp = _to_decimal(w_fp)
        self.w_imb = _to_decimal(w_imb)
        self.confidence_threshold = _to_decimal(confidence_threshold)
        self.absorption_veto_threshold = _to_decimal(absorption_veto_threshold)
        self.w_flow = _to_decimal(w_flow)
        self._flow_scorer: FlowScorer = flow_scorer if flow_scorer is not None else _DEFAULT_FLOW_SCORER

    @classmethod
    def from_config(cls, config) -> "SignalEngine":
        s = config.signal
        w = s.weight
        return cls(
            w_cvd=_to_decimal(w["cvd"]),
            w_fp=_to_decimal(w["footprint"]),
            w_imb=_to_decimal(w["imbalance"]),
            confidence_threshold=_to_decimal(s.confidence_threshold),
            absorption_veto_threshold=_to_decimal(s.absorption_veto_threshold),
            w_flow=_to_decimal(w.get("flow", 0.0)),
        )

    def evaluate(
        self,
        cvd_score: Optional[Decimal],
        fp_score: Optional[Decimal],
        imb_score: Optional[Decimal],
        absorption_result: Optional[AbsorptionResult] = None,
        flow_events: Optional[Sequence[FlowEvent]] = None,
    ) -> SignalResult:
        """Compute composite score, confidence, veto, and emit a SignalResult."""
        # --- flow score (computed before entries to allow None exclusion) ------
        flow_score: Optional[Decimal] = None
        if self.w_flow > _ZERO and flow_events is not None:
            flow_score = score_flow_events(flow_events, self._flow_scorer)

        # --- step 1: gather enabled modules (decision 7) ----------------------
        entries: list[tuple[Decimal, Decimal]] = []   # (weight, score)
        if cvd_score is not None:
            entries.append((self.w_cvd, _to_decimal(cvd_score)))
        if fp_score is not None:
            entries.append((self.w_fp, _to_decimal(fp_score)))
        if imb_score is not None:
            entries.append((self.w_imb, _to_decimal(imb_score)))
        if flow_score is not None:
            entries.append((self.w_flow, _to_decimal(flow_score)))

        # --- step 2: NO_INPUT guard (decision 9 priority 1) ------------------
        if not entries:
            return SignalResult(
                composite=_ZERO,
                confidence=_ZERO,
                signal="WAIT",
                reasons=(REASON_NO_INPUT,),
                flow_score=flow_score,
            )

        # --- step 3: composite & confidence -----------------------------------
        weight_sum = sum(w for w, _ in entries)
        composite = sum(w * s for w, s in entries) / weight_sum
        confidence = abs(composite) / _ONE_HUNDRED

        # direction: +1 BUY, -1 SELL, 0 neutral
        if composite > _ZERO:
            direction = 1
        elif composite < _ZERO:
            direction = -1
        else:
            direction = 0

        # --- step 4: reason codes (score-derived) -----------------------------
        reasons: list[str] = []

        if cvd_score is not None:
            score_cvd = _to_decimal(cvd_score)
            if abs(score_cvd) >= _REASON_SCORE_THRESHOLD:
                reasons.append(REASON_CVD_UP if score_cvd > _ZERO else REASON_CVD_DOWN)

        if fp_score is not None:
            score_fp = _to_decimal(fp_score)
            if abs(score_fp) >= _REASON_SCORE_THRESHOLD:
                reasons.append(REASON_FOOTPRINT_BUY if score_fp > _ZERO else REASON_FOOTPRINT_SELL)

        if imb_score is not None:
            score_imb = _to_decimal(imb_score)
            if abs(score_imb) >= _REASON_SCORE_THRESHOLD:
                reasons.append(REASON_STACKED_IMBALANCE)

        if flow_score is not None and abs(flow_score) >= _REASON_SCORE_THRESHOLD:
            reasons.append(REASON_FLOW_BUY if flow_score > _ZERO else REASON_FLOW_SELL)

        # --- step 5: absorption veto (decision 8, priority 2) ----------------
        veto = False
        if absorption_result is not None:
            cls_ = absorption_result.classification
            strength = _to_decimal(absorption_result.strength)
            against = (
                (direction == 1 and cls_ == _SELL_ABSORPTION)
                or (direction == -1 and cls_ == _BUY_ABSORPTION)
            )
            if against and strength >= self.absorption_veto_threshold:
                veto = True
                reasons.append(REASON_ABSORPTION_VETO)

        # --- step 6: low confidence (priority 3) ------------------------------
        low_conf = confidence < self.confidence_threshold
        if low_conf:
            reasons.append(REASON_LOW_CONFIDENCE)

        # --- step 7: final signal (decision 9 priority 4) --------------------
        if veto or low_conf or direction == 0:
            signal = "WAIT"
        elif direction == 1:
            signal = "BUY"
        else:
            signal = "SELL"

        return SignalResult(
            composite=composite,
            confidence=confidence,
            signal=signal,
            reasons=tuple(reasons),
            flow_score=flow_score,
        )


# --- Score normalisation functions (M11, SignalEngine_v3.1 §4.1) -------------
_CLAMP_MAX = Decimal(100)
_CLAMP_MIN = Decimal(-100)


def _clamp(value: Decimal) -> Decimal:
    if value > _CLAMP_MAX:
        return _CLAMP_MAX
    if value < _CLAMP_MIN:
        return _CLAMP_MIN
    return value


def score_cvd(delta: Decimal, cvd_slope_ref: Optional[Decimal]) -> Optional[Decimal]:
    """CVD score from confirmed Candle.delta and the reference slope.

    Returns None when cvd_slope_ref is None or zero (decision 11 — unref state).
    SignalEngine treats None as a disabled module (M10 decision 7).
    """
    ref = _to_decimal(cvd_slope_ref) if cvd_slope_ref is not None else None
    if ref is None or ref == _ZERO:
        return None
    return _clamp((_to_decimal(delta) / ref) * _CLAMP_MAX)


def score_footprint(buy_volume: Decimal, sell_volume: Decimal) -> Decimal:
    """Footprint score from total BUY/SELL volume across all price levels.

    Returns 0 when total volume is zero (SignalEngine_v3.1 §8 — scoring failure
    treated as 0, warning is emitted by the caller).
    """
    bv = _to_decimal(buy_volume)
    sv = _to_decimal(sell_volume)
    total = bv + sv
    if total == _ZERO:
        return _ZERO
    return _clamp(((bv - sv) / total) * _CLAMP_MAX)


def score_imbalance(imbalance_result: ImbalanceResult, stack_ref: int) -> Decimal:
    """Imbalance score from stacked imbalances (decision 10 — net generalisation).

    net = Σcount(BUY stacks) − Σcount(SELL stacks)
    score = clamp( sign(net) × min(|net| / stack_ref, 1) × 100, −100, +100 )
    """
    buy_total = sum(
        si.count for si in imbalance_result.stacked_imbalances if si.direction == "BUY"
    )
    sell_total = sum(
        si.count for si in imbalance_result.stacked_imbalances if si.direction == "SELL"
    )
    net = buy_total - sell_total
    if net == 0:
        return _ZERO
    sign = Decimal(1) if net > 0 else Decimal(-1)
    magnitude = min(Decimal(abs(net)) / Decimal(stack_ref), Decimal(1))
    return _clamp(sign * magnitude * _CLAMP_MAX)
