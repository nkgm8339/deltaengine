"""Causal entry candidates and path evaluation for order-flow episodes.

This research module is deliberately isolated from the live pipeline.  It
turns already-observed episode checkpoints into reproducible candidates and
measures forward price paths without creating orders or changing Flow Price
Response.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

from .episode_dataset import PriceObservation
from .orderflow_episode import EpisodeCheckpoint, EpisodeStage, OrderFlowEpisode

ATTACK_ENTRY = "ATTACK_V1"
PERSIST_ENTRY = "PERSIST_PRESSURE_V1"
RESOLUTION_ENTRY = "RESOLUTION_CONFIRMED_V1"

_BPS = 10_000.0
_SIDES = {"BUY", "SELL"}
_RESOLUTION_STAGES = {
    EpisodeStage.AGGRESSOR_BREAKTHROUGH,
    EpisodeStage.DEFENDER_REVERSAL,
}


def opposite_side(side: str) -> str:
    normalized = side.upper()
    if normalized not in _SIDES:
        raise ValueError("side must be BUY or SELL")
    return "SELL" if normalized == "BUY" else "BUY"


@dataclass(frozen=True)
class EpisodeEntryCandidate:
    episode_id: str
    symbol: str
    window_sec: int
    candidate_type: str
    entry_time: datetime
    entry_stage: EpisodeStage
    trade_side: str
    pressure_side: str
    entry_price: float
    invalidation_price: float | None
    episode_terminal_stage: EpisodeStage
    episode_resolved: bool

    def __post_init__(self) -> None:
        if self.entry_time.tzinfo is None:
            raise ValueError("entry_time must be timezone-aware")
        if self.trade_side not in _SIDES or self.pressure_side not in _SIDES:
            raise ValueError("candidate sides must be BUY or SELL")
        if self.entry_price <= 0:
            raise ValueError("entry_price must be positive")
        if self.invalidation_price is not None and self.invalidation_price <= 0:
            raise ValueError("invalidation_price must be positive")

    def to_row(self) -> dict[str, object]:
        return {
            "episode_id": self.episode_id,
            "symbol": self.symbol,
            "window_sec": self.window_sec,
            "candidate_type": self.candidate_type,
            "entry_time": self.entry_time,
            "entry_stage": self.entry_stage.value,
            "trade_side": self.trade_side,
            "pressure_side": self.pressure_side,
            "entry_price": self.entry_price,
            "invalidation_price": self.invalidation_price,
            "episode_terminal_stage": self.episode_terminal_stage.value,
            "episode_resolved": self.episode_resolved,
        }


def _first_stage_after(
    checkpoints: tuple[EpisodeCheckpoint, ...],
    stage: EpisodeStage,
    after_index: int,
) -> tuple[int, EpisodeCheckpoint] | None:
    for index in range(after_index + 1, len(checkpoints)):
        checkpoint = checkpoints[index]
        if checkpoint.stage is stage:
            return index, checkpoint
    return None


def _first_resolution_after(
    checkpoints: tuple[EpisodeCheckpoint, ...],
    after_index: int,
) -> tuple[int, EpisodeCheckpoint] | None:
    for index in range(after_index + 1, len(checkpoints)):
        checkpoint = checkpoints[index]
        if checkpoint.stage in _RESOLUTION_STAGES:
            return index, checkpoint
    return None


def _candidate(
    episode: OrderFlowEpisode,
    *,
    candidate_type: str,
    checkpoint: EpisodeCheckpoint,
    trade_side: str,
    invalidation_price: float | None,
) -> EpisodeEntryCandidate:
    return EpisodeEntryCandidate(
        episode_id=episode.episode_id,
        symbol=episode.symbol,
        window_sec=episode.window_sec,
        candidate_type=candidate_type,
        entry_time=checkpoint.event_time,
        entry_stage=checkpoint.stage,
        trade_side=trade_side,
        pressure_side=episode.pressure_side.upper(),
        entry_price=checkpoint.price,
        invalidation_price=invalidation_price,
        episode_terminal_stage=episode.stage,
        episode_resolved=episode.resolved,
    )


def extract_entry_candidates(
    episodes: Iterable[OrderFlowEpisode],
) -> tuple[EpisodeEntryCandidate, ...]:
    """Extract pre-registered candidates without terminal-state filtering.

    ATTACK is emitted for every episode that actually has an AGGRESSION
    checkpoint.  PERSIST is emitted as soon as the ordered attack/stall/
    persistence sequence exists.  RESOLUTION additionally requires a causal
    resolution checkpoint after that sequence.
    """
    result: list[EpisodeEntryCandidate] = []
    for episode in episodes:
        checkpoints = episode.checkpoints
        attack = _first_stage_after(checkpoints, EpisodeStage.AGGRESSION, -1)
        if attack is None:
            continue
        attack_index, attack_point = attack
        result.append(
            _candidate(
                episode,
                candidate_type=ATTACK_ENTRY,
                checkpoint=attack_point,
                trade_side=episode.pressure_side.upper(),
                invalidation_price=None,
            )
        )

        non_response = _first_stage_after(
            checkpoints, EpisodeStage.NON_RESPONSE, attack_index
        )
        if non_response is None:
            continue
        non_response_index, non_response_point = non_response
        sustained = _first_stage_after(
            checkpoints, EpisodeStage.SUSTAINED_CONFLICT, non_response_index
        )
        if sustained is None:
            continue
        sustained_index, sustained_point = sustained

        conflict_prices = [non_response_point.price, sustained_point.price]
        pressure_side = episode.pressure_side.upper()
        persist_invalidation = (
            min(conflict_prices) if pressure_side == "BUY" else max(conflict_prices)
        )
        result.append(
            _candidate(
                episode,
                candidate_type=PERSIST_ENTRY,
                checkpoint=sustained_point,
                trade_side=pressure_side,
                invalidation_price=persist_invalidation,
            )
        )

        resolution = _first_resolution_after(checkpoints, sustained_index)
        if resolution is None:
            continue
        _, resolution_point = resolution
        trade_side = (
            pressure_side
            if resolution_point.stage is EpisodeStage.AGGRESSOR_BREAKTHROUGH
            else opposite_side(pressure_side)
        )
        resolution_invalidation = (
            min(conflict_prices) if trade_side == "BUY" else max(conflict_prices)
        )
        result.append(
            _candidate(
                episode,
                candidate_type=RESOLUTION_ENTRY,
                checkpoint=resolution_point,
                trade_side=trade_side,
                invalidation_price=resolution_invalidation,
            )
        )
    return tuple(sorted(result, key=lambda value: (value.entry_time, value.candidate_type)))


def purge_overlapping_candidates(
    candidates: Iterable[EpisodeEntryCandidate],
    *,
    horizon_sec: int = 600,
) -> tuple[EpisodeEntryCandidate, ...]:
    """Keep the first non-overlapping candidate per symbol and candidate type."""
    if horizon_sec < 1:
        raise ValueError("horizon_sec must be positive")
    blocked_until: dict[tuple[str, int, str], datetime] = {}
    kept: list[EpisodeEntryCandidate] = []
    for candidate in sorted(
        candidates, key=lambda value: (value.entry_time, value.candidate_type)
    ):
        key = (candidate.symbol, candidate.window_sec, candidate.candidate_type)
        blocked = blocked_until.get(key)
        if blocked is not None and candidate.entry_time < blocked:
            continue
        kept.append(candidate)
        blocked_until[key] = candidate.entry_time + timedelta(seconds=horizon_sec)
    return tuple(kept)


@dataclass(frozen=True)
class EntryPathOutcome:
    episode_id: str
    candidate_type: str
    window_sec: int
    entry_time: datetime
    entry_stage: EpisodeStage
    trade_side: str
    pressure_side: str
    horizon_sec: int
    entry_price: float
    status: str
    outcome_time: datetime | None
    outcome_price: float | None
    signed_return_bps: float | None
    mfe_bps: float | None
    mae_bps: float | None
    mfe_time: datetime | None
    mae_time: datetime | None
    proxy_cost_usd: float
    proxy_cost_bps: float
    proxy_net_return_bps: float | None
    favorable_hurdle_time: datetime | None
    adverse_hurdle_time: datetime | None
    hurdle_order: str | None
    price_invalidation_time: datetime | None
    price_invalidation_price: float | None
    invalidation_before_favorable: bool | None
    rule_exit_reason: str | None
    rule_exit_time: datetime | None
    rule_exit_price: float | None
    rule_signed_return_bps: float | None
    rule_proxy_net_return_bps: float | None

    def to_row(self) -> dict[str, object]:
        row = dict(self.__dict__)
        row["entry_stage"] = self.entry_stage.value
        return row


class EpisodeEntryPathEvaluator:
    """Measure trade-side paths after causal entry checkpoints."""

    def __init__(
        self,
        horizons_sec: Iterable[int] = (300, 600),
        *,
        proxy_cost_usd: float = 20.0,
        max_outcome_lag_sec: int = 30,
        max_data_gap_sec: int = 120,
    ) -> None:
        self.horizons_sec = tuple(sorted(set(int(value) for value in horizons_sec)))
        if not self.horizons_sec or any(value < 1 for value in self.horizons_sec):
            raise ValueError("horizons_sec must contain positive values")
        if proxy_cost_usd < 0 or max_outcome_lag_sec < 0 or max_data_gap_sec < 1:
            raise ValueError("cost, lag, and gap limits must be valid")
        self.proxy_cost_usd = float(proxy_cost_usd)
        self.max_outcome_lag_sec = max_outcome_lag_sec
        self.max_data_gap_sec = max_data_gap_sec

    @staticmethod
    def _ordered_prices(prices: Iterable[PriceObservation]) -> list[PriceObservation]:
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

    @staticmethod
    def _first_threshold_time(
        moves: list[tuple[datetime, float]], threshold: float, *, favorable: bool
    ) -> datetime | None:
        for event_time, move in moves:
            if (favorable and move >= threshold) or (
                not favorable and move <= -threshold
            ):
                return event_time
        return None

    @staticmethod
    def _hurdle_order(
        favorable_time: datetime | None, adverse_time: datetime | None
    ) -> str:
        if favorable_time is None and adverse_time is None:
            return "NEITHER"
        if favorable_time is None:
            return "ADVERSE_FIRST"
        if adverse_time is None:
            return "FAVORABLE_FIRST"
        if favorable_time < adverse_time:
            return "FAVORABLE_FIRST"
        if adverse_time < favorable_time:
            return "ADVERSE_FIRST"
        return "SAME_OBSERVATION"

    def _missing(
        self,
        candidate: EpisodeEntryCandidate,
        horizon_sec: int,
        status: str,
    ) -> EntryPathOutcome:
        cost_bps = self.proxy_cost_usd / candidate.entry_price * _BPS
        return EntryPathOutcome(
            episode_id=candidate.episode_id,
            candidate_type=candidate.candidate_type,
            window_sec=candidate.window_sec,
            entry_time=candidate.entry_time,
            entry_stage=candidate.entry_stage,
            trade_side=candidate.trade_side,
            pressure_side=candidate.pressure_side,
            horizon_sec=horizon_sec,
            entry_price=candidate.entry_price,
            status=status,
            outcome_time=None,
            outcome_price=None,
            signed_return_bps=None,
            mfe_bps=None,
            mae_bps=None,
            mfe_time=None,
            mae_time=None,
            proxy_cost_usd=self.proxy_cost_usd,
            proxy_cost_bps=cost_bps,
            proxy_net_return_bps=None,
            favorable_hurdle_time=None,
            adverse_hurdle_time=None,
            hurdle_order=None,
            price_invalidation_time=None,
            price_invalidation_price=None,
            invalidation_before_favorable=None,
            rule_exit_reason=None,
            rule_exit_time=None,
            rule_exit_price=None,
            rule_signed_return_bps=None,
            rule_proxy_net_return_bps=None,
        )

    def evaluate(
        self,
        candidates: Iterable[EpisodeEntryCandidate],
        prices: Iterable[PriceObservation],
    ) -> tuple[EntryPathOutcome, ...]:
        ordered = self._ordered_prices(prices)
        times = [value.event_time for value in ordered]
        outcomes: list[EntryPathOutcome] = []
        for candidate in candidates:
            direction = 1.0 if candidate.trade_side == "BUY" else -1.0
            for horizon_sec in self.horizons_sec:
                target = candidate.entry_time + timedelta(seconds=horizon_sec)
                start_index = bisect.bisect_left(times, candidate.entry_time)
                outcome_index = bisect.bisect_left(times, target)
                if outcome_index >= len(ordered):
                    outcomes.append(
                        self._missing(candidate, horizon_sec, "MISSING_OUTCOME")
                    )
                    continue
                outcome = ordered[outcome_index]
                if (outcome.event_time - target).total_seconds() > self.max_outcome_lag_sec:
                    outcomes.append(
                        self._missing(candidate, horizon_sec, "MISSING_OUTCOME")
                    )
                    continue
                path = ordered[start_index : outcome_index + 1]
                if not path or (
                    path[0].event_time - candidate.entry_time
                ).total_seconds() > self.max_data_gap_sec:
                    outcomes.append(self._missing(candidate, horizon_sec, "DATA_GAP"))
                    continue
                gaps = [
                    (right.event_time - left.event_time).total_seconds()
                    for left, right in zip(path, path[1:])
                ]
                if any(gap > self.max_data_gap_sec for gap in gaps):
                    outcomes.append(self._missing(candidate, horizon_sec, "DATA_GAP"))
                    continue

                moves = [(candidate.entry_time, 0.0)]
                moves.extend(
                    (
                        value.event_time,
                        direction
                        * (value.price - candidate.entry_price)
                        / candidate.entry_price
                        * _BPS,
                    )
                    for value in path
                )
                mfe_time, mfe = max(moves, key=lambda value: value[1])
                mae_time, mae = min(moves, key=lambda value: value[1])
                signed_return = (
                    direction
                    * (outcome.price - candidate.entry_price)
                    / candidate.entry_price
                    * _BPS
                )
                cost_bps = self.proxy_cost_usd / candidate.entry_price * _BPS
                favorable_time = self._first_threshold_time(
                    moves, cost_bps, favorable=True
                )
                adverse_time = self._first_threshold_time(
                    moves, cost_bps, favorable=False
                )
                invalidation_time: datetime | None = None
                invalidation_price: float | None = None
                if candidate.invalidation_price is not None:
                    for value in path:
                        invalidated = (
                            candidate.trade_side == "BUY"
                            and value.price < candidate.invalidation_price
                        ) or (
                            candidate.trade_side == "SELL"
                            and value.price > candidate.invalidation_price
                        )
                        if invalidated:
                            invalidation_time = value.event_time
                            invalidation_price = value.price
                            break
                if candidate.invalidation_price is None:
                    invalidation_before_favorable: bool | None = None
                elif invalidation_time is None:
                    invalidation_before_favorable = False
                else:
                    invalidation_before_favorable = (
                        favorable_time is None or invalidation_time <= favorable_time
                    )
                if invalidation_time is not None and invalidation_price is not None:
                    rule_exit_reason = "PRICE_INVALIDATION"
                    rule_exit_time = invalidation_time
                    rule_exit_price = invalidation_price
                    rule_signed_return = (
                        direction
                        * (invalidation_price - candidate.entry_price)
                        / candidate.entry_price
                        * _BPS
                    )
                else:
                    rule_exit_reason = "FIXED_HORIZON"
                    rule_exit_time = outcome.event_time
                    rule_exit_price = outcome.price
                    rule_signed_return = signed_return
                outcomes.append(
                    EntryPathOutcome(
                        episode_id=candidate.episode_id,
                        candidate_type=candidate.candidate_type,
                        window_sec=candidate.window_sec,
                        entry_time=candidate.entry_time,
                        entry_stage=candidate.entry_stage,
                        trade_side=candidate.trade_side,
                        pressure_side=candidate.pressure_side,
                        horizon_sec=horizon_sec,
                        entry_price=candidate.entry_price,
                        status="OK",
                        outcome_time=outcome.event_time,
                        outcome_price=outcome.price,
                        signed_return_bps=signed_return,
                        mfe_bps=mfe,
                        mae_bps=mae,
                        mfe_time=mfe_time,
                        mae_time=mae_time,
                        proxy_cost_usd=self.proxy_cost_usd,
                        proxy_cost_bps=cost_bps,
                        proxy_net_return_bps=signed_return - cost_bps,
                        favorable_hurdle_time=favorable_time,
                        adverse_hurdle_time=adverse_time,
                        hurdle_order=self._hurdle_order(
                            favorable_time, adverse_time
                        ),
                        price_invalidation_time=invalidation_time,
                        price_invalidation_price=invalidation_price,
                        invalidation_before_favorable=invalidation_before_favorable,
                        rule_exit_reason=rule_exit_reason,
                        rule_exit_time=rule_exit_time,
                        rule_exit_price=rule_exit_price,
                        rule_signed_return_bps=rule_signed_return,
                        rule_proxy_net_return_bps=rule_signed_return - cost_bps,
                    )
                )
        return tuple(outcomes)
