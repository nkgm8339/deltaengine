"""PRICE/CVD/Delta base patterns with Open Interest as a fourth axis.

The user's existing eight-pattern classification stays unchanged.  This module
adds an observational OI context to that base pattern without producing a
score, probability, or trade signal.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any


class OiDirection(Enum):
    BUILDING = "BUILDING"
    UNWINDING = "UNWINDING"
    UNCHANGED = "UNCHANGED"
    MISSING = "MISSING"


@dataclass(frozen=True)
class BasePattern:
    number: int
    name: str
    price_direction: int
    cvd_direction: int
    delta_direction: int


@dataclass(frozen=True)
class CombinedContext:
    pattern: BasePattern
    oi_direction: OiDirection
    code: str
    title: str
    summary_ja: str


BASE_PATTERNS: tuple[BasePattern, ...] = (
    BasePattern(1, "UPTREND", 1, 1, 1),
    BasePattern(2, "UPTREND PULLBACK", 1, 1, -1),
    BasePattern(3, "UPWARD REBOUND", 1, -1, 1),
    BasePattern(4, "UPWARD DIVERGENCE", 1, -1, -1),
    BasePattern(5, "DOWNWARD DIVERGENCE", -1, 1, 1),
    BasePattern(6, "DOWNTREND PULLBACK", -1, 1, -1),
    BasePattern(7, "DOWNWARD REBOUND", -1, -1, 1),
    BasePattern(8, "DOWNTREND", -1, -1, -1),
)

_PATTERN_BY_DIRECTIONS = {
    (
        pattern.price_direction,
        pattern.cvd_direction,
        pattern.delta_direction,
    ): pattern
    for pattern in BASE_PATTERNS
}

_CONTEXTS: dict[tuple[int, OiDirection], tuple[str, str]] = {
    (1, OiDirection.BUILDING): (
        "NEW LONG BUILDUP",
        "非常に強い上昇。新規ロングが積み上がっている。",
    ),
    (1, OiDirection.UNWINDING): (
        "SHORT-COVER RALLY",
        "ショートカバー主体。上昇は続かないことも多い。",
    ),
    (2, OiDirection.BUILDING): (
        "SELLING INTO STRENGTH",
        "上昇中に売りが増加。吸収や分配の可能性がある。",
    ),
    (2, OiDirection.UNWINDING): (
        "LONG PROFIT-TAKING",
        "ロングの利確が主体。上昇の勢いが鈍る可能性がある。",
    ),
    (3, OiDirection.BUILDING): (
        "REBOUND WITH NEW PARTICIPATION",
        "上昇反発に新規参加。直近買いとOI増加が反発を支えている。",
    ),
    (3, OiDirection.UNWINDING): (
        "SHORT-COVER REBOUND",
        "ショートカバーによる反発。新規買い主導とは限らない。",
    ),
    (4, OiDirection.BUILDING): (
        "SHORT PRESSURE ABSORBED",
        "OI増加中の売り圧力でも価格が上昇。ショート側が捕まる候補。",
    ),
    (4, OiDirection.UNWINDING): (
        "UNWINDING UPWARD DIVERGENCE",
        "ポジション解消を伴う上昇ダイバージェンス。継続には新規参加の確認が必要。",
    ),
    (5, OiDirection.BUILDING): (
        "LONG PRESSURE ABSORBED",
        "OI増加中の買い圧力でも価格が下落。ロング側が捕まる候補。",
    ),
    (5, OiDirection.UNWINDING): (
        "UNWINDING DOWNWARD DIVERGENCE",
        "ポジション解消を伴う下落ダイバージェンス。継続には新規参加の確認が必要。",
    ),
    (6, OiDirection.BUILDING): (
        "RENEWED SHORT BUILDUP",
        "下落再開に新規参加。直近売りとOI増加が下落を支えている。",
    ),
    (6, OiDirection.UNWINDING): (
        "LONG-LIQUIDATION LEG",
        "ロング解消による下落。新規ショート主導とは限らない。",
    ),
    (7, OiDirection.BUILDING): (
        "REBOUND ATTEMPT WITH NEW OI",
        "反発候補。買いが入り始め、新規資金も流入している。",
    ),
    (7, OiDirection.UNWINDING): (
        "SHORT PROFIT-TAKING",
        "ショートの利確による買い戻し。本格反転とは限らない。",
    ),
    (8, OiDirection.BUILDING): (
        "NEW SHORT BUILDUP",
        "非常に強い下落。新規ショートが積み上がっている。",
    ),
    (8, OiDirection.UNWINDING): (
        "LONG LIQUIDATION",
        "ロングの投げ売り・手仕舞い。売り一巡後に反発することもある。",
    ),
}


def _validate_direction(value: int, field: str) -> int:
    if isinstance(value, bool) or value not in (-1, 1):
        raise ValueError(f"{field} must be -1 or 1")
    return value


def classify_directions(
    price_direction: int,
    cvd_direction: int,
    delta_direction: int,
) -> BasePattern:
    """Return the unchanged base-eight pattern for three signed directions."""
    key = (
        _validate_direction(price_direction, "price_direction"),
        _validate_direction(cvd_direction, "cvd_direction"),
        _validate_direction(delta_direction, "delta_direction"),
    )
    return _PATTERN_BY_DIRECTIONS[key]


def classify_candles(current: Any, reference: Any) -> BasePattern:
    """Match the existing UI rule: PRICE/CVD compare two bars; Delta uses sign."""
    price_direction = (
        1
        if current.close > reference.close
        else -1
        if current.close < reference.close
        else 1
        if current.close >= current.open
        else -1
    )
    cvd_direction = (
        1
        if current.cvd > reference.cvd
        else -1
        if current.cvd < reference.cvd
        else 1
        if current.delta >= Decimal("0")
        else -1
    )
    delta_direction = 1 if current.delta >= Decimal("0") else -1
    return classify_directions(price_direction, cvd_direction, delta_direction)


def oi_direction_from_change(change: Decimal | None) -> OiDirection:
    if change is None:
        return OiDirection.MISSING
    if not isinstance(change, Decimal):
        change = Decimal(str(change))
    if not change.is_finite():
        return OiDirection.MISSING
    if change > Decimal("0"):
        return OiDirection.BUILDING
    if change < Decimal("0"):
        return OiDirection.UNWINDING
    return OiDirection.UNCHANGED


def combine_pattern_with_oi(
    pattern: BasePattern,
    oi_change: Decimal | None,
) -> CombinedContext:
    """Add OI context while retaining the base pattern as a separate field."""
    oi_direction = oi_direction_from_change(oi_change)
    code = f"P{pattern.number}_{oi_direction.value}"
    if oi_direction is OiDirection.MISSING:
        return CombinedContext(
            pattern,
            oi_direction,
            code,
            "OI DATA MISSING",
            "時刻同期できるOIがないため、既存8パターンだけを表示する。",
        )
    if oi_direction is OiDirection.UNCHANGED:
        return CombinedContext(
            pattern,
            oi_direction,
            code,
            "OI UNCHANGED",
            "OIは変化なし。既存8パターンの観測評価を維持する。",
        )
    title, summary_ja = _CONTEXTS[(pattern.number, oi_direction)]
    return CombinedContext(pattern, oi_direction, code, title, summary_ja)


def context_catalog() -> tuple[CombinedContext, ...]:
    """Return the sixteen directional OI combinations in stable order."""
    return tuple(
        combine_pattern_with_oi(pattern, change)
        for pattern in BASE_PATTERNS
        for change in (Decimal("1"), Decimal("-1"))
    )
