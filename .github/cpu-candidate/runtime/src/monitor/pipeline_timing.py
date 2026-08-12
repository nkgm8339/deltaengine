"""Bounded, read-only timing observation for the live market pipeline.

The observer never changes a market event, scheduling decision, threshold, or
storage contract.  It retains only a bounded window for percentile reporting
while keeping all-time count/mean/maximum counters for incident diagnosis.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections import deque
from contextlib import contextmanager
from typing import Callable, Iterator


PIPELINE_TIMING_STAGES = (
    "normalize",
    "trade",
    "depth",
    "liquidation",
    "hook",
    "storage",
    "callback",
    "event_loop_lag",
)
DEFAULT_SAMPLE_CAPACITY = 4_096
DEFAULT_EVENT_LOOP_PROBE_INTERVAL_SEC = 0.1


class DurationWindow:
    """Bounded duration samples plus all-time aggregate counters."""

    def __init__(self, capacity: int = DEFAULT_SAMPLE_CAPACITY) -> None:
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
            raise ValueError("capacity must be an integer >= 1")
        self.capacity = capacity
        self._samples_ms: deque[float] = deque(maxlen=capacity)
        self.count = 0
        self.total_ms = 0.0
        self.max_ms = 0.0
        self.last_ms = 0.0

    def reset(self) -> None:
        self._samples_ms.clear()
        self.count = 0
        self.total_ms = 0.0
        self.max_ms = 0.0
        self.last_ms = 0.0

    def observe_ms(self, elapsed_ms: float) -> None:
        value = float(elapsed_ms)
        if not math.isfinite(value) or value < 0:
            raise ValueError("elapsed_ms must be finite and >= 0")
        self._samples_ms.append(value)
        self.count += 1
        self.total_ms += value
        self.max_ms = max(self.max_ms, value)
        self.last_ms = value

    def stats_snapshot(self) -> dict[str, int | float]:
        ordered = sorted(self._samples_ms)
        p95_ms = 0.0
        if ordered:
            # Nearest-rank p95: the smallest observed duration whose rank is
            # at least 95% of the bounded sample window.
            index = max(0, math.ceil(len(ordered) * 0.95) - 1)
            p95_ms = ordered[index]
        mean_ms = self.total_ms / self.count if self.count else 0.0
        return {
            "count": self.count,
            "window_count": len(ordered),
            "mean_ms": round(mean_ms, 6),
            "p95_ms": round(p95_ms, 6),
            "max_ms": round(self.max_ms, 6),
            "last_ms": round(self.last_ms, 6),
        }


class PipelineTimingObserver:
    """Fixed-vocabulary timing counters for one live pipeline run."""

    def __init__(
        self,
        *,
        sample_capacity: int = DEFAULT_SAMPLE_CAPACITY,
        clock_ns: Callable[[], int] = time.perf_counter_ns,
    ) -> None:
        self.sample_capacity = sample_capacity
        self._clock_ns = clock_ns
        self._windows = {
            stage: DurationWindow(sample_capacity)
            for stage in PIPELINE_TIMING_STAGES
        }

    def reset(self) -> None:
        for window in self._windows.values():
            window.reset()

    def observe_ms(self, stage: str, elapsed_ms: float) -> None:
        try:
            window = self._windows[stage]
        except KeyError as exc:
            raise ValueError(f"unknown pipeline timing stage: {stage!r}") from exc
        window.observe_ms(elapsed_ms)

    @contextmanager
    def measure(self, stage: str) -> Iterator[None]:
        if stage not in self._windows:
            raise ValueError(f"unknown pipeline timing stage: {stage!r}")
        started_ns = self._clock_ns()
        try:
            yield
        finally:
            elapsed_ms = max(0, self._clock_ns() - started_ns) / 1_000_000.0
            self._windows[stage].observe_ms(elapsed_ms)

    def stats_snapshot(self) -> dict[str, object]:
        return {
            "sample_capacity": self.sample_capacity,
            "stages": {
                stage: self._windows[stage].stats_snapshot()
                for stage in PIPELINE_TIMING_STAGES
            },
        }


async def observe_event_loop_lag(
    observer: PipelineTimingObserver,
    *,
    interval_sec: float = DEFAULT_EVENT_LOOP_PROBE_INTERVAL_SEC,
) -> None:
    """Record scheduler overshoot without changing pipeline work ordering."""

    if not math.isfinite(interval_sec) or interval_sec <= 0:
        raise ValueError("interval_sec must be finite and > 0")
    loop = asyncio.get_running_loop()
    while True:
        started = loop.time()
        await asyncio.sleep(interval_sec)
        overshoot_ms = max(0.0, loop.time() - started - interval_sec) * 1_000.0
        observer.observe_ms("event_loop_lag", overshoot_ms)
