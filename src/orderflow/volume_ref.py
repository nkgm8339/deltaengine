"""VolumeRefTracker — shared moving-average volume reference (B-2).

Shared by Imbalance and Absorption per Absorption_v3.1 §6:
  "volume_ref is the moving average of per-level volume over the most recent
   volume_ref_bars bars, shared with the Imbalance module."

Design:
    - Decimal only — no float.
    - Deterministic: identical observe_bar sequence → identical current().
    - current() returns None until at least one bar has been observed.
    - Weight: level-weighted average across all bars in the window.
      i.e. Σ(all volumes across all window bars) / Σ(level counts per bar).
      This handles varying level counts per bar correctly.
"""

from __future__ import annotations

from collections import deque
from decimal import Decimal
from typing import Iterable, Optional

_ZERO = Decimal(0)


def _to_decimal(v: object) -> Decimal:
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


class VolumeRefTracker:
    """Computes a sliding per-level volume moving average over confirmed bars."""

    def __init__(self, bars: int) -> None:
        if bars < 1:
            raise ValueError(f"bars must be >= 1, got {bars}")
        self.bars = bars
        self.observations: int = 0
        # Each deque element: (sum_of_volumes_in_bar, level_count_in_bar)
        self._window: deque[tuple[Decimal, int]] = deque()

    def observe_bar(self, per_level_volumes: Iterable[Decimal]) -> None:
        """Record one confirmed bar's per-level volumes.

        Pass each level's (buy_volume + sell_volume) as elements.
        Zero-volume bars contribute a (0, 0) entry and do not inflate the average.
        """
        total = _ZERO
        count = 0
        for v in per_level_volumes:
            total += _to_decimal(v)
            count += 1
        self._window.append((total, count))
        if len(self._window) > self.bars:
            self._window.popleft()
        self.observations += 1

    def current(self) -> Optional[Decimal]:
        """Level-weighted average per-level volume across the window.

        Returns None if no bars have been observed yet.
        Returns 0 if total level count across window is 0 (all-empty bars).
        """
        if not self._window:
            return None
        total_volume = sum((s for s, _ in self._window), _ZERO)
        total_levels = sum(c for _, c in self._window)
        if total_levels == 0:
            return _ZERO
        return total_volume / Decimal(total_levels)
