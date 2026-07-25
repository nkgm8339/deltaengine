"""Causal forward labels for order-flow episode checkpoints.

The evaluator labels observed price paths only. It does not choose a trade
side, optimize thresholds, connect to HFM, or alter any live pipeline.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

from .orderflow_episode import EpisodeStage, OrderFlowEpisode

_BPS = 10_000.0


@dataclass(frozen=True)
class PriceObservation:
    event_time: datetime
    price: float


@dataclass(frozen=True)
class EpisodeOutcomeLabel:
    episode_id: str
    symbol: str
    window_sec: int
    pressure_side: str
    checkpoint_time: datetime
    checkpoint_stage: EpisodeStage
    checkpoint_index: int
    horizon_sec: int
    base_price: float
    status: str
    outcome_time: datetime | None
    outcome_price: float | None
    forward_return_bps: float | None
    pressure_signed_return_bps: float | None
    max_up_bps: float | None
    max_down_bps: float | None
    episode_terminal_stage: EpisodeStage
    episode_resolved: bool

    def to_row(self) -> dict[str, object]:
        return {
            "episode_id": self.episode_id,
            "symbol": self.symbol,
            "window_sec": self.window_sec,
            "pressure_side": self.pressure_side,
            "checkpoint_time": self.checkpoint_time,
            "checkpoint_stage": self.checkpoint_stage.value,
            "checkpoint_index": self.checkpoint_index,
            "horizon_sec": self.horizon_sec,
            "base_price": self.base_price,
            "status": self.status,
            "outcome_time": self.outcome_time,
            "outcome_price": self.outcome_price,
            "forward_return_bps": self.forward_return_bps,
            "pressure_signed_return_bps": self.pressure_signed_return_bps,
            "max_up_bps": self.max_up_bps,
            "max_down_bps": self.max_down_bps,
            "episode_terminal_stage": self.episode_terminal_stage.value,
            "episode_resolved": self.episode_resolved,
        }


class EpisodeOutcomeEvaluator:
    """Generate time-based forward labels from an ordered price stream."""

    def __init__(
        self,
        horizons_sec: Iterable[int] = (300, 600),
        *,
        max_outcome_lag_sec: int = 30,
        max_data_gap_sec: int = 120,
    ) -> None:
        self.horizons_sec = tuple(sorted(set(int(value) for value in horizons_sec)))
        if not self.horizons_sec or any(value < 1 for value in self.horizons_sec):
            raise ValueError("horizons_sec must contain positive values")
        if max_outcome_lag_sec < 0 or max_data_gap_sec < 1:
            raise ValueError("lag and gap limits must be valid")
        self.max_outcome_lag_sec = max_outcome_lag_sec
        self.max_data_gap_sec = max_data_gap_sec

    def _ordered_prices(self, prices: Iterable[PriceObservation]) -> list[PriceObservation]:
        ordered = list(prices)
        previous: datetime | None = None
        for observation in ordered:
            if observation.event_time.tzinfo is None:
                raise ValueError("price event_time must be timezone-aware")
            if observation.price <= 0:
                raise ValueError("price must be positive")
            if previous is not None and observation.event_time < previous:
                raise ValueError("prices must be chronological")
            previous = observation.event_time
        return ordered

    def _missing(
        self,
        episode: OrderFlowEpisode,
        checkpoint_index: int,
        checkpoint_time: datetime,
        checkpoint_stage: EpisodeStage,
        horizon: int,
        status: str,
        base_price: float,
    ) -> EpisodeOutcomeLabel:
        return EpisodeOutcomeLabel(
            episode.episode_id, episode.symbol, episode.window_sec,
            episode.pressure_side, checkpoint_time, checkpoint_stage,
            checkpoint_index, horizon, base_price, status, None, None,
            None, None, None, None, episode.stage, episode.resolved,
        )

    def evaluate(
        self,
        episodes: Iterable[OrderFlowEpisode],
        prices: Iterable[PriceObservation],
    ) -> tuple[EpisodeOutcomeLabel, ...]:
        ordered = self._ordered_prices(prices)
        times = [observation.event_time for observation in ordered]
        labels: list[EpisodeOutcomeLabel] = []
        for episode in episodes:
            for checkpoint_index, checkpoint in enumerate(episode.checkpoints):
                base = checkpoint.price
                for horizon in self.horizons_sec:
                    target = checkpoint.event_time + timedelta(seconds=horizon)
                    start_index = bisect.bisect_left(times, checkpoint.event_time)
                    outcome_index = bisect.bisect_left(times, target)
                    if base <= 0:
                        labels.append(self._missing(episode, checkpoint_index, checkpoint.event_time, checkpoint.stage, horizon, "INVALID_PRICE", base))
                        continue
                    if outcome_index >= len(ordered):
                        labels.append(self._missing(episode, checkpoint_index, checkpoint.event_time, checkpoint.stage, horizon, "MISSING_OUTCOME", base))
                        continue
                    outcome = ordered[outcome_index]
                    if (outcome.event_time - target).total_seconds() > self.max_outcome_lag_sec:
                        labels.append(self._missing(episode, checkpoint_index, checkpoint.event_time, checkpoint.stage, horizon, "MISSING_OUTCOME", base))
                        continue
                    path = ordered[start_index : outcome_index + 1]
                    if not path or (path[0].event_time - checkpoint.event_time).total_seconds() > self.max_data_gap_sec:
                        status = "DATA_GAP"
                    else:
                        gaps = [
                            (right.event_time - left.event_time).total_seconds()
                            for left, right in zip(path, path[1:])
                        ]
                        status = "DATA_GAP" if any(gap > self.max_data_gap_sec for gap in gaps) else "OK"
                    if status != "OK":
                        labels.append(self._missing(episode, checkpoint_index, checkpoint.event_time, checkpoint.stage, horizon, status, base))
                        continue
                    forward = (outcome.price - base) / base * _BPS
                    signed = forward if episode.pressure_side == "BUY" else -forward
                    max_up = (max(value.price for value in path) - base) / base * _BPS
                    max_down = (min(value.price for value in path) - base) / base * _BPS
                    labels.append(EpisodeOutcomeLabel(
                        episode.episode_id, episode.symbol, episode.window_sec,
                        episode.pressure_side, checkpoint.event_time, checkpoint.stage,
                        checkpoint_index, horizon, base, "OK", outcome.event_time,
                        outcome.price, forward, signed, max_up, max_down,
                        episode.stage, episode.resolved,
                    ))
        return tuple(labels)
