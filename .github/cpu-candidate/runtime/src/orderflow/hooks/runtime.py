"""Calibration-gated Hook event runtime."""

from __future__ import annotations

from collections import deque
from typing import Iterable, Protocol

from .config import ThresholdBook
from .models import HookCandidate, HookEvent


class HookEventSink(Protocol):
    def add_event(self, event: HookEvent) -> bool | None: ...


class HookRuntime:
    """Turns candidates into events only when an approved threshold allows it."""

    def __init__(
        self,
        thresholds: ThresholdBook,
        *,
        detector_version: str = "stage2a-contract-v1",
        input_manifest_hash: str | None = None,
        sink: HookEventSink | None = None,
        dedupe_capacity: int = 100_000,
    ) -> None:
        if dedupe_capacity < 1:
            raise ValueError("dedupe_capacity must be positive")
        self.thresholds = thresholds
        self.detector_version = detector_version
        self.input_manifest_hash = input_manifest_hash
        self.sink = sink
        self.candidates_seen = 0
        self.events_emitted = 0
        self.duplicates_suppressed = 0
        self.sink_rejected = 0
        self._ids: set[str] = set()
        self._id_order: deque[str] = deque()
        self._dedupe_capacity = dedupe_capacity

    def submit(self, candidates: Iterable[HookCandidate]) -> tuple[HookEvent, ...]:
        emitted: list[HookEvent] = []
        for candidate in candidates:
            self.candidates_seen += 1
            event = self.thresholds.evaluate(
                candidate,
                detector_version=self.detector_version,
                input_manifest_hash=self.input_manifest_hash,
            )
            if event is None:
                continue
            if event.hook_event_id in self._ids:
                self.duplicates_suppressed += 1
                continue
            if self.sink is not None:
                accepted = self.sink.add_event(event)
                if accepted is False:
                    self.sink_rejected += 1
                    continue
            self._ids.add(event.hook_event_id)
            self._id_order.append(event.hook_event_id)
            if len(self._id_order) > self._dedupe_capacity:
                self._ids.discard(self._id_order.popleft())
            emitted.append(event)
            self.events_emitted += 1
        return tuple(emitted)
