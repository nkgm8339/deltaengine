"""Offline order-flow episode state machine.

This module does not alter the completed rolling Flow detector or connect to
live execution. It groups one selected Flow observation window into ordered
episodes so a multi-minute attack/stall/resolution can be studied without
counting every rolling update as an independent event.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Iterable


class EpisodeStage(str, Enum):
    AGGRESSION = "AGGRESSION"
    NON_RESPONSE = "NON_RESPONSE"
    SUSTAINED_CONFLICT = "SUSTAINED_CONFLICT"
    AGGRESSOR_BREAKTHROUGH = "AGGRESSOR_BREAKTHROUGH"
    DEFENDER_REVERSAL = "DEFENDER_REVERSAL"
    INVALIDATED = "INVALIDATED"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class FlowObservation:
    event_time: datetime
    symbol: str
    window_sec: int
    state: str
    pressure_side: str
    pressure_ratio: float
    persistence: float
    relative_volume: float | None
    price_change_bps: float
    last_price: float


@dataclass(frozen=True)
class EpisodeCheckpoint:
    event_time: datetime
    stage: EpisodeStage
    state: str
    observation_index: int
    price: float


@dataclass(frozen=True)
class OrderFlowEpisode:
    episode_id: str
    symbol: str
    window_sec: int
    pressure_side: str
    start_time: datetime
    end_time: datetime
    stage: EpisodeStage
    resolved: bool
    observation_count: int
    first_price: float
    last_price: float
    checkpoints: tuple[EpisodeCheckpoint, ...]


def _state_kind(observation: FlowObservation) -> str:
    side = observation.pressure_side.upper()
    state = observation.state.upper()
    if side not in {"BUY", "SELL"} or not state.startswith(f"{side}_"):
        return "UNCLEAR"
    suffix = state[len(side) + 1 :]
    if suffix in {"EFFECTIVE", "STALLED", "TRAPPED"}:
        return suffix
    return "UNCLEAR"


@dataclass
class _ActiveEpisode:
    sequence: int
    first: FlowObservation
    last: FlowObservation
    stage: EpisodeStage
    stalled_observations: int
    observation_count: int
    checkpoints: list[EpisodeCheckpoint]

    @property
    def episode_id(self) -> str:
        return (
            f"{self.first.symbol}:{self.first.window_sec}:"
            f"{self.first.event_time.isoformat()}:{self.sequence}"
        )

    def checkpoint(self, observation: FlowObservation, stage: EpisodeStage) -> None:
        self.checkpoints.append(
            EpisodeCheckpoint(
                event_time=observation.event_time,
                stage=stage,
                state=observation.state,
                observation_index=self.observation_count - 1,
                price=observation.last_price,
            )
        )

    def close(self, stage: EpisodeStage, resolved: bool) -> OrderFlowEpisode:
        return OrderFlowEpisode(
            episode_id=self.episode_id,
            symbol=self.first.symbol,
            window_sec=self.first.window_sec,
            pressure_side=self.first.pressure_side,
            start_time=self.first.event_time,
            end_time=self.last.event_time,
            stage=stage,
            resolved=resolved,
            observation_count=self.observation_count,
            first_price=self.first.last_price,
            last_price=self.last.last_price,
            checkpoints=tuple(self.checkpoints),
        )


class OrderFlowEpisodeBuilder:
    """Build causal episodes for one symbol and one Flow window."""

    def __init__(
        self,
        symbol: str,
        window_sec: int,
        *,
        max_gap_sec: int = 120,
        max_episode_sec: int | None = None,
    ) -> None:
        if (
            not symbol
            or window_sec < 1
            or max_gap_sec < 1
            or (max_episode_sec is not None and max_episode_sec < 1)
        ):
            raise ValueError("symbol, window_sec, and max_gap_sec must be valid")
        self.symbol = symbol
        self.window_sec = window_sec
        self.max_gap_sec = max_gap_sec
        self.max_episode_sec = max_episode_sec
        self._active: _ActiveEpisode | None = None
        self._last_time: datetime | None = None
        self._sequence = 0

    def _start(self, observation: FlowObservation, kind: str) -> None:
        stage = EpisodeStage.AGGRESSION if kind == "EFFECTIVE" else EpisodeStage.NON_RESPONSE
        self._sequence += 1
        active = _ActiveEpisode(
            sequence=self._sequence,
            first=observation,
            last=observation,
            stage=stage,
            stalled_observations=1 if kind == "STALLED" else 0,
            observation_count=1,
            checkpoints=[],
        )
        active.checkpoint(observation, stage)
        self._active = active

    def _close(self, stage: EpisodeStage, resolved: bool) -> OrderFlowEpisode:
        assert self._active is not None
        result = self._active.close(stage, resolved)
        self._active = None
        return result

    def process(self, observation: FlowObservation) -> tuple[OrderFlowEpisode, ...]:
        if observation.symbol != self.symbol or observation.window_sec != self.window_sec:
            return ()
        if observation.event_time.tzinfo is None:
            raise ValueError("event_time must be timezone-aware")
        if observation.last_price <= 0:
            raise ValueError("last_price must be positive")
        if self._last_time is not None and observation.event_time < self._last_time:
            raise ValueError("observations must be chronological")
        self._last_time = observation.event_time
        kind = _state_kind(observation)
        emitted: list[OrderFlowEpisode] = []

        if self._active is not None:
            elapsed = (observation.event_time - self._active.last.event_time).total_seconds()
            if elapsed > self.max_gap_sec:
                emitted.append(self._close(EpisodeStage.INVALIDATED, False))
        if self._active is not None and self.max_episode_sec is not None:
            duration = (
                observation.event_time - self._active.first.event_time
            ).total_seconds()
            if duration > self.max_episode_sec:
                emitted.append(self._close(EpisodeStage.INVALIDATED, False))

        if self._active is None:
            if kind in {"EFFECTIVE", "STALLED"}:
                self._start(observation, kind)
            return tuple(emitted)

        active = self._active
        if observation.pressure_side != active.first.pressure_side or kind == "UNCLEAR":
            emitted.append(self._close(EpisodeStage.INVALIDATED, False))
            if kind in {"EFFECTIVE", "STALLED"}:
                self._start(observation, kind)
            return tuple(emitted)

        active.last = observation
        active.observation_count += 1
        if kind == "STALLED":
            active.stalled_observations += 1
            next_stage = (
                EpisodeStage.SUSTAINED_CONFLICT
                if active.stalled_observations >= 2
                else EpisodeStage.NON_RESPONSE
            )
            if next_stage is not active.stage:
                active.stage = next_stage
                active.checkpoint(observation, next_stage)
            return tuple(emitted)

        if kind == "TRAPPED":
            active.checkpoint(observation, EpisodeStage.DEFENDER_REVERSAL)
            emitted.append(self._close(EpisodeStage.DEFENDER_REVERSAL, True))
            return tuple(emitted)

        if kind == "EFFECTIVE" and active.stage in {
            EpisodeStage.NON_RESPONSE,
            EpisodeStage.SUSTAINED_CONFLICT,
        }:
            active.checkpoint(observation, EpisodeStage.AGGRESSOR_BREAKTHROUGH)
            emitted.append(self._close(EpisodeStage.AGGRESSOR_BREAKTHROUGH, True))
        return tuple(emitted)

    def finalize(self) -> tuple[OrderFlowEpisode, ...]:
        if self._active is None:
            return ()
        return (self._close(EpisodeStage.UNRESOLVED, False),)


def build_episodes(
    observations: Iterable[FlowObservation],
    *,
    symbol: str,
    window_sec: int,
    max_gap_sec: int = 120,
    max_episode_sec: int | None = None,
) -> tuple[OrderFlowEpisode, ...]:
    builder = OrderFlowEpisodeBuilder(
        symbol,
        window_sec,
        max_gap_sec=max_gap_sec,
        max_episode_sec=max_episode_sec,
    )
    result: list[OrderFlowEpisode] = []
    for observation in observations:
        result.extend(builder.process(observation))
    result.extend(builder.finalize())
    return tuple(result)
