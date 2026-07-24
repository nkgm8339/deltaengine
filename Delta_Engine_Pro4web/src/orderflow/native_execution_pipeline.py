"""Coordinator for native 5m/10m execution observations.

Keeps native candle, Flow Event, and Outcome processing isolated from the
completed 1m pipeline. The caller supplies a storage facade exposing
add_candle/add_native_flow_event/add_native_flow_outcome.
"""
from __future__ import annotations

from collections import deque
from typing import Any

from ..database.schema import candle_to_row, native_flow_event_to_row, native_flow_outcome_to_row
from .native_execution import NativeExecutionAggregator
from .native_flow import NativeFlowDetector, NativeFlowOutcomeTracker


class NativeExecutionCoordinator:
    def __init__(self, symbol: str, *, horizons_sec: tuple[int, ...] = (300, 600, 1800)) -> None:
        self.aggregator = NativeExecutionAggregator(symbol)
        self.detectors = {tf: NativeFlowDetector(symbol, tf) for tf in self.aggregator.timeframes}
        self.tracker = NativeFlowOutcomeTracker(horizons_sec)
        self.candles: dict[str, Any] = {}
        self.events = deque(maxlen=5000)
        self.outcomes = deque(maxlen=5000)
        self.candles_written = 0

    def process(self, trade: Any, storage: Any) -> None:
        update = self.aggregator.process(trade)
        for timeframe, candle in update.closed.items():
            self.candles[timeframe] = candle
            storage.add_candle(candle_to_row(candle))
            self.candles_written += 1
        snapshots = []
        for detector in self.detectors.values():
            snapshots.extend(detector.process(trade))
        if snapshots:
            events = self.tracker.register(tuple(snapshots))
            self.events.extend(events)
            for event in events:
                storage.add_native_flow_event(native_flow_event_to_row(event))
        outcomes = self.tracker.observe_trade(trade)
        self.outcomes.extend(outcomes)
        for outcome in outcomes:
            storage.add_native_flow_outcome(native_flow_outcome_to_row(outcome))

    def finalize(self, storage: Any) -> None:
        for timeframe, candle in self.aggregator.finalize().items():
            self.candles[timeframe] = candle
            storage.add_candle(candle_to_row(candle))
            self.candles_written += 1
        snapshots = []
        for detector in self.detectors.values():
            snapshots.extend(detector.finalize())
        if snapshots:
            events = self.tracker.register(tuple(snapshots))
            self.events.extend(events)
            for event in events:
                storage.add_native_flow_event(native_flow_event_to_row(event))


