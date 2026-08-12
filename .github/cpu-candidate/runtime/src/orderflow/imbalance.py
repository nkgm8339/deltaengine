"""Imbalance detector — diagonal BUY/SELL volume comparison across price levels (MOD-006).

Spec: ArchitectureRepository/30_Modules/Imbalance_v3.1.md.
Error codes: ArchitectureRepository/40_Reference/ErrorCodes_v3.1.md.
Test vectors: ArchitectureRepository/50_Test/TestSpecification_v3.2.md §4.3
(TV-IMB-01 through TV-IMB-06).

Diagonal comparison (Imbalance_v3.1 §5.1):
    Buy Imbalance  @P : BuyVol(P)  / SellVol(P−1tick) >= ratio_threshold
    Sell Imbalance @P : SellVol(P) / BuyVol(P+1tick)  >= ratio_threshold

Adjacency (instruction §3 decision 4): "P±1tick" resolves to array-index
neighbours in FootprintBar.levels (price-ascending, no duplicates). No
tick_size validation is performed.

min_volume (instruction §3 decision 5): mandatory Decimal constructor
parameter. null→volume_ref auto-resolution is the caller's responsibility
(deferred to M9 Absorption shared utility).

Error handling (instruction §3 decision 6):
    - Empty levels            → no imbalances (not an error).
    - Negative volume level   → E3001, skip all pairs involving that level,
                                continue detection on remaining pairs.
    - Levels not price-ascending between consecutive indices → E3001, skip
                                that pair, continue.

Design:
    - Decimal arithmetic only — no float in the calculation path.
    - Deterministic: identical FootprintBar input → identical ImbalanceResult.
    - No silent data loss: invalid levels are counted and logged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from .cvd import _to_decimal
from .footprint import FootprintBar
from .volume_ref import VolumeRefTracker

logger = logging.getLogger("orderflow.imbalance")

ERROR_INVALID_TRADE = "E3001"

_ZERO = Decimal(0)


# --- Value types --------------------------------------------------------------
@dataclass(frozen=True)
class BuyImbalance:
    price: Decimal
    ratio: Decimal


@dataclass(frozen=True)
class SellImbalance:
    price: Decimal
    ratio: Decimal


@dataclass(frozen=True)
class StackedImbalance:
    start_price: Decimal
    end_price: Decimal
    count: int
    direction: str  # "BUY" | "SELL"


@dataclass(frozen=True)
class ImbalanceResult:
    bar_time: datetime
    symbol: str
    buy_imbalances: tuple[BuyImbalance, ...]
    sell_imbalances: tuple[SellImbalance, ...]
    stacked_imbalances: tuple[StackedImbalance, ...]


# --- Internal helpers ---------------------------------------------------------
def _qualify(
    numerator: Decimal,
    denominator: Decimal,
    combined: Decimal,
    ratio_threshold: Decimal,
    ratio_cap: Decimal,
    min_volume: Decimal,
) -> Optional[Decimal]:
    """Return reported ratio if the level pair qualifies, else None.

    Qualification gates (Task-A saturation fix):
        1. combined < min_volume → None (applies to zero-denominator too).
        2. zero denominator → ratio_cap ONLY when the numerator itself carries
           real volume (numerator >= min_volume); otherwise None. Thin one-sided
           levels (e.g. 0.01 vs 0.00) previously auto-qualified at ratio_cap on
           every pair, saturating strength/score. The numerator gate suppresses
           that noise.
        3. otherwise ratio >= ratio_threshold.
    """
    if combined < min_volume:
        return None
    if denominator == _ZERO:
        # zero-denominator qualifies only if the numerator carries real volume.
        return ratio_cap if numerator >= min_volume else None
    ratio = numerator / denominator
    return ratio if ratio >= ratio_threshold else None


def _find_stacked(
    qualifying: list[tuple[int, Decimal]],  # (level_index, price), sorted by index
    stack_count: int,
    direction: str,
) -> list[StackedImbalance]:
    """Find maximal consecutive runs (by level index) of length >= stack_count."""
    if not qualifying:
        return []
    result: list[StackedImbalance] = []
    run_start = 0
    for i in range(1, len(qualifying)):
        if qualifying[i][0] != qualifying[i - 1][0] + 1:
            _maybe_emit(qualifying, run_start, i, stack_count, direction, result)
            run_start = i
    _maybe_emit(qualifying, run_start, len(qualifying), stack_count, direction, result)
    return result


def _maybe_emit(
    qualifying: list[tuple[int, Decimal]],
    start: int,
    end: int,
    stack_count: int,
    direction: str,
    out: list[StackedImbalance],
) -> None:
    run_len = end - start
    if run_len >= stack_count:
        out.append(
            StackedImbalance(
                start_price=qualifying[start][1],
                end_price=qualifying[end - 1][1],
                count=run_len,
                direction=direction,
            )
        )


# --- Detector -----------------------------------------------------------------
class ImbalanceDetector:
    """Detects BUY/SELL imbalances and stacked imbalances from a confirmed FootprintBar.

    Stateless per-bar: detect() is deterministic and has no side effects beyond
    incrementing the invalid_pairs counter.
    """

    def __init__(
        self,
        ratio_threshold: Decimal,
        min_volume: Decimal,
        ratio_cap: Decimal,
        stack_count: int,
        *,
        volume_ref: Optional[VolumeRefTracker] = None,
    ) -> None:
        if stack_count < 2:
            raise ValueError("stack_count must be >= 2")
        self.ratio_threshold = _to_decimal(ratio_threshold)
        self.min_volume = _to_decimal(min_volume)
        self.ratio_cap = _to_decimal(ratio_cap)
        self.stack_count = stack_count
        self._volume_ref = volume_ref
        self.invalid_pairs = 0  # levels skipped due to negative volume or ordering
        self.last_effective_min_volume = self.min_volume

    def detect(self, bar: FootprintBar) -> ImbalanceResult:
        """Run diagonal comparison over bar.levels; return ImbalanceResult."""
        # Resolve effective min_volume: when volume_ref is calibrated, use the
        # larger of the calibrated reference and the configured floor so the
        # floor is never undercut (Task-A). Uncalibrated → the floor itself.
        if (self._volume_ref is not None
                and self._volume_ref.current() is not None):
            effective_min_volume = max(self._volume_ref.current(), self.min_volume)
        else:
            effective_min_volume = self.min_volume
        # Expose the floor actually used (may be raised by volume_ref) so the
        # webapp client can recompute walls faithfully (Imbalance独立化: ★罠2).
        self.last_effective_min_volume = effective_min_volume

        levels = bar.levels
        n = len(levels)

        # Track which level indices have valid (non-negative) volumes.
        valid: list[bool] = []
        for lv in levels:
            if lv.buy_volume < _ZERO or lv.sell_volume < _ZERO:
                self.invalid_pairs += 1
                logger.warning(
                    "%s imbalance: negative volume at price %s, pairs skipped",
                    ERROR_INVALID_TRADE, lv.price,
                )
                valid.append(False)
            else:
                valid.append(True)

        buy_results: list[BuyImbalance] = []
        sell_results: list[SellImbalance] = []
        buy_qualifying: list[tuple[int, Decimal]] = []
        sell_qualifying: list[tuple[int, Decimal]] = []

        for i in range(n):
            if not valid[i]:
                continue
            lv = levels[i]

            # --- Buy Imbalance @P: compare with array-predecessor (P-1tick) ---
            if i >= 1 and valid[i - 1]:
                prev = levels[i - 1]
                if prev.price >= lv.price:
                    self.invalid_pairs += 1
                    logger.warning(
                        "%s imbalance: levels not ascending (%s >= %s), pair skipped",
                        ERROR_INVALID_TRADE, prev.price, lv.price,
                    )
                else:
                    combined = (
                        lv.buy_volume + lv.sell_volume
                        + prev.buy_volume + prev.sell_volume
                    )
                    ratio = _qualify(
                        lv.buy_volume, prev.sell_volume, combined,
                        self.ratio_threshold, self.ratio_cap, effective_min_volume,
                    )
                    if ratio is not None:
                        buy_results.append(BuyImbalance(price=lv.price, ratio=ratio))
                        buy_qualifying.append((i, lv.price))

            # --- Sell Imbalance @P: compare with array-successor (P+1tick) ---
            if i < n - 1 and valid[i + 1]:
                nxt = levels[i + 1]
                combined = (
                    lv.buy_volume + lv.sell_volume
                    + nxt.buy_volume + nxt.sell_volume
                )
                ratio = _qualify(
                    lv.sell_volume, nxt.buy_volume, combined,
                    self.ratio_threshold, self.ratio_cap, effective_min_volume,
                )
                if ratio is not None:
                    sell_results.append(SellImbalance(price=lv.price, ratio=ratio))
                    sell_qualifying.append((i, lv.price))

        stacked = (
            _find_stacked(buy_qualifying, self.stack_count, "BUY")
            + _find_stacked(sell_qualifying, self.stack_count, "SELL")
        )

        return ImbalanceResult(
            bar_time=bar.bar_time,
            symbol=bar.symbol,
            buy_imbalances=tuple(buy_results),
            sell_imbalances=tuple(sell_results),
            stacked_imbalances=tuple(stacked),
        )
