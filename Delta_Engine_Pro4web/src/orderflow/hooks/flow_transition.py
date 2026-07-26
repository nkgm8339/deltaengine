"""Derived flow-response transition candidates D06-D08."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Iterable

from .detector_utils import make_candidate, observation_times
from .models import HookCandidate, HookQualityStatus, HookSide


_FAST_REVERSALS = {
    ("BUY_EFFECTIVE", "BUY_TRAPPED"): HookSide.BUY,
    ("SELL_EFFECTIVE", "SELL_TRAPPED"): HookSide.SELL,
}
_TRAPPED = {"BUY_TRAPPED": HookSide.BUY, "SELL_TRAPPED": HookSide.SELL}
_DIRECTION = {
    "BUY_EFFECTIVE": "UP",
    "SELL_TRAPPED": "UP",
    "SELL_EFFECTIVE": "DOWN",
    "BUY_TRAPPED": "DOWN",
}


class FlowTransitionDetector:
    def __init__(self, *, min_aligned_windows: int) -> None:
        if min_aligned_windows < 2:
            raise ValueError("min_aligned_windows must be at least 2")
        self.min_aligned_windows = int(min_aligned_windows)
        self._last: dict[int, tuple[str, datetime]] = {}
        self.stale_snapshots = 0

    def process(
        self,
        snapshots: Iterable[Any],
        *,
        received_time: datetime,
        quality_status: HookQualityStatus = HookQualityStatus.VALID,
        quality_flags: tuple[str, ...] = (),
    ) -> tuple[HookCandidate, ...]:
        batch = tuple(snapshots)
        result: list[HookCandidate] = []
        latest_by_window: dict[int, Any] = {}
        for snapshot in batch:
            source, received = observation_times(snapshot.event_time, received_time)
            window = int(snapshot.window_sec)
            state = getattr(snapshot.state, "value", str(snapshot.state))
            previous = self._last.get(window)
            if previous is not None and source <= previous[1]:
                self.stale_snapshots += 1
                continue
            latest_by_window[window] = snapshot
            self._last[window] = (state, source)
            if previous is None or previous[0] == state:
                continue

            common = {
                "symbol": snapshot.symbol,
                "source_time": source,
                "received_time": received,
                "source_sequence": f"{window}:{source.isoformat()}",
                "anchor_price": snapshot.last_price,
                "episode_id": f"{window}:{previous[0]}->{state}:{source.isoformat()}",
                "quality_status": quality_status,
                "quality_flags": quality_flags,
            }
            transition = (previous[0], state)
            elapsed_ms = max(
                0,
                int((source - previous[1]).total_seconds() * 1000),
            )
            if transition in _FAST_REVERSALS:
                result.append(make_candidate(
                    "D06",
                    side=_FAST_REVERSALS[transition],
                    metric_name="transition_elapsed_ms",
                    metric_value=elapsed_ms,
                    evidence={
                        "window_sec": window,
                        "previous_state": previous[0],
                        "current_state": state,
                    },
                    **common,
                ))
            if previous[0] in _TRAPPED and state not in _TRAPPED:
                result.append(make_candidate(
                    "D07",
                    side=_TRAPPED[previous[0]],
                    metric_name="trapped_duration_ms",
                    metric_value=elapsed_ms,
                    evidence={
                        "window_sec": window,
                        "previous_state": previous[0],
                        "current_state": state,
                    },
                    **common,
                ))

        grouped: dict[str, list[Any]] = {"UP": [], "DOWN": []}
        for window, (state, _time) in self._last.items():
            direction = _DIRECTION.get(state)
            if direction is not None:
                grouped[direction].append((window, state))
        for direction, aligned in grouped.items():
            if len(aligned) < self.min_aligned_windows or not latest_by_window:
                continue
            newest = max(latest_by_window.values(), key=lambda row: row.event_time)
            source, received = observation_times(newest.event_time, received_time)
            result.append(make_candidate(
                "D08",
                symbol=newest.symbol,
                side=HookSide.BUY if direction == "UP" else HookSide.SELL,
                source_time=source,
                received_time=received,
                source_sequence=(
                    f"D08:{direction}:"
                    + ",".join(str(row[0]) for row in sorted(aligned))
                    + f":{source.isoformat()}"
                ),
                metric_name="aligned_window_count",
                metric_value=Decimal(len(aligned)),
                anchor_price=newest.last_price,
                episode_id=f"D08:{direction}:{source.isoformat()}",
                quality_status=quality_status,
                quality_flags=quality_flags,
                evidence={
                    "direction": direction,
                    "windows": [row[0] for row in sorted(aligned)],
                    "states": [row[1] for row in sorted(aligned)],
                },
            ))
        return tuple(result)
