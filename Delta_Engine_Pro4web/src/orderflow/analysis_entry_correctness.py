"""Zero-spread replay for analysis direction and entry timing.

This research module does not place orders, apply costs, optimize exits, or
change Flow Price Response.  It evaluates a direction decision at fixed future
times on an ordered real-price stream.
"""

from __future__ import annotations

import bisect
from array import array
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import inf
from typing import Iterable


_BPS = 10_000.0
_SIDES = {"BUY", "SELL"}
_DIRECTIONAL_STATES = {
    "BUY_EFFECTIVE": ("BUY", "EFFECTIVE_CONTINUATION", "ANALYSIS"),
    "SELL_EFFECTIVE": ("SELL", "EFFECTIVE_CONTINUATION", "ANALYSIS"),
    "BUY_TRAPPED": ("SELL", "TRAPPED_REVERSAL", "ANALYSIS"),
    "SELL_TRAPPED": ("BUY", "TRAPPED_REVERSAL", "ANALYSIS"),
}


@dataclass(frozen=True)
class AnalysisDecision:
    decision_id: str
    source_family: str
    symbol: str
    window_sec: int
    state: str
    hypothesis: str
    decision_class: str
    side: str
    decision_time: datetime
    observed_price: float

    def __post_init__(self) -> None:
        if self.decision_time.tzinfo is None:
            raise ValueError("decision_time must be timezone-aware")
        if self.side not in _SIDES:
            raise ValueError("side must be BUY or SELL")
        if self.window_sec < 1 or self.observed_price <= 0:
            raise ValueError("window_sec and observed_price must be positive")


@dataclass(frozen=True)
class ReplayPrice:
    event_time: datetime
    price: float

    def __post_init__(self) -> None:
        if self.event_time.tzinfo is None:
            raise ValueError("price event_time must be timezone-aware")
        if self.price <= 0:
            raise ValueError("price must be positive")


@dataclass(frozen=True)
class ReplayBar:
    open_time: datetime
    close_time: datetime
    open: float
    high: float
    low: float
    close: float

    def __post_init__(self) -> None:
        if self.open_time.tzinfo is None or self.close_time.tzinfo is None:
            raise ValueError("bar times must be timezone-aware")
        if self.close_time <= self.open_time:
            raise ValueError("bar close_time must follow open_time")
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("bar prices must be positive")
        if self.high < max(self.open, self.low, self.close):
            raise ValueError("bar high is inconsistent")
        if self.low > min(self.open, self.high, self.close):
            raise ValueError("bar low is inconsistent")


@dataclass(frozen=True)
class ZeroSpreadOutcome:
    market: str
    decision_id: str
    source_family: str
    symbol: str
    window_sec: int
    state: str
    hypothesis: str
    decision_class: str
    side: str
    decision_time: datetime
    horizon_sec: int
    status: str
    entry_time: datetime | None
    entry_price: float | None
    entry_lag_ms: int | None
    outcome_time: datetime | None
    outcome_price: float | None
    outcome_lag_ms: int | None
    raw_return_bps: float | None
    signed_return_bps: float | None
    direction_result: str | None
    mfe_bps: float | None
    mae_bps: float | None
    mfe_time: datetime | None
    mae_time: datetime | None
    mfe_after_entry_sec: float | None
    mae_after_entry_sec: float | None

    def to_row(self) -> dict[str, object]:
        return dict(self.__dict__)


def decisions_from_flow_rows(
    rows: Iterable[object],
    *,
    source_family: str,
    include_stalled_probes: bool = True,
) -> tuple[AnalysisDecision, ...]:
    """Convert stored Flow observations into pre-defined direction decisions.

    EFFECTIVE and TRAPPED retain their completed state meanings.  STALLED is
    not promoted to a direction claim; two explicitly-labelled entry probes
    are emitted so pressure continuation and defender reversal are compared
    without choosing the better direction after seeing outcomes.
    """

    result: list[AnalysisDecision] = []
    seen: set[tuple[object, ...]] = set()
    for row in rows:
        event_time = getattr(row, "event_time")
        symbol = str(getattr(row, "symbol"))
        window_sec = int(getattr(row, "window_sec"))
        state = str(getattr(row, "state")).upper()
        pressure_side = str(getattr(row, "pressure_side")).upper()
        observed_price = float(getattr(row, "last_price"))
        key = (source_family, event_time, symbol, window_sec, state)
        if key in seen:
            continue
        seen.add(key)

        mapped = _DIRECTIONAL_STATES.get(state)
        candidates: list[tuple[str, str, str]] = []
        if mapped is not None:
            candidates.append(mapped)
        elif include_stalled_probes and state in {"BUY_STALLED", "SELL_STALLED"}:
            if pressure_side not in _SIDES:
                continue
            opposite = "SELL" if pressure_side == "BUY" else "BUY"
            candidates.extend(
                (
                    (pressure_side, "STALLED_PRESSURE_PROBE", "ENTRY_PROBE"),
                    (opposite, "STALLED_REVERSAL_PROBE", "ENTRY_PROBE"),
                )
            )
        for side, hypothesis, decision_class in candidates:
            result.append(
                AnalysisDecision(
                    decision_id=(
                        f"{source_family}:{symbol}:{window_sec}:"
                        f"{event_time.isoformat()}:{state}:{hypothesis}"
                    ),
                    source_family=source_family,
                    symbol=symbol,
                    window_sec=window_sec,
                    state=state,
                    hypothesis=hypothesis,
                    decision_class=decision_class,
                    side=side,
                    decision_time=event_time,
                    observed_price=observed_price,
                )
            )
    return tuple(
        sorted(
            result,
            key=lambda value: (
                value.decision_time,
                value.source_family,
                value.window_sec,
                value.hypothesis,
            ),
        )
    )


def purge_overlapping_decisions(
    decisions: Iterable[AnalysisDecision],
    *,
    horizon_sec: int,
) -> tuple[AnalysisDecision, ...]:
    """Replay at most one open position per fixed candidate policy."""

    if horizon_sec < 1:
        raise ValueError("horizon_sec must be positive")
    blocked_until: dict[tuple[str, str, int, str], datetime] = {}
    kept: list[AnalysisDecision] = []
    for decision in sorted(
        decisions,
        key=lambda value: (
            value.decision_time,
            value.source_family,
            value.window_sec,
            value.hypothesis,
        ),
    ):
        key = (
            decision.symbol,
            decision.source_family,
            decision.window_sec,
            decision.hypothesis,
        )
        blocked = blocked_until.get(key)
        if blocked is not None and decision.decision_time < blocked:
            continue
        kept.append(decision)
        blocked_until[key] = decision.decision_time + timedelta(seconds=horizon_sec)
    return tuple(kept)


class _ExtremaIndex:
    """Range minimum/maximum index with O(log n) queries."""

    def __init__(self, values: list[float]) -> None:
        size = 1
        while size < len(values):
            size <<= 1
        self.size = size
        length = size * 2
        self.minimum = array("d", [inf]) * length
        self.maximum = array("d", [-inf]) * length
        self.minimum_index = array("q", [-1]) * length
        self.maximum_index = array("q", [-1]) * length
        for index, value in enumerate(values):
            target = size + index
            self.minimum[target] = value
            self.maximum[target] = value
            self.minimum_index[target] = index
            self.maximum_index[target] = index
        for node in range(size - 1, 0, -1):
            left = node * 2
            right = left + 1
            if self.minimum[left] <= self.minimum[right]:
                self.minimum[node] = self.minimum[left]
                self.minimum_index[node] = self.minimum_index[left]
            else:
                self.minimum[node] = self.minimum[right]
                self.minimum_index[node] = self.minimum_index[right]
            if self.maximum[left] >= self.maximum[right]:
                self.maximum[node] = self.maximum[left]
                self.maximum_index[node] = self.maximum_index[left]
            else:
                self.maximum[node] = self.maximum[right]
                self.maximum_index[node] = self.maximum_index[right]

    def query(self, start: int, end: int) -> tuple[int, int]:
        """Return earliest min and max indices over inclusive bounds."""

        if start < 0 or end < start:
            raise ValueError("invalid extrema query")
        left = start + self.size
        right = end + self.size + 1
        min_value = inf
        max_value = -inf
        min_index = max_index = -1
        while left < right:
            if left & 1:
                value = self.minimum[left]
                index = self.minimum_index[left]
                if value < min_value or (
                    value == min_value and (min_index < 0 or index < min_index)
                ):
                    min_value, min_index = value, index
                value = self.maximum[left]
                index = self.maximum_index[left]
                if value > max_value or (
                    value == max_value and (max_index < 0 or index < max_index)
                ):
                    max_value, max_index = value, index
                left += 1
            if right & 1:
                right -= 1
                value = self.minimum[right]
                index = self.minimum_index[right]
                if value < min_value or (
                    value == min_value and (min_index < 0 or index < min_index)
                ):
                    min_value, min_index = value, index
                value = self.maximum[right]
                index = self.maximum_index[right]
                if value > max_value or (
                    value == max_value and (max_index < 0 or index < max_index)
                ):
                    max_value, max_index = value, index
            left //= 2
            right //= 2
        if min_index < 0 or max_index < 0:
            raise ValueError("empty extrema query")
        return min_index, max_index


class ObservedEntryBarReplayEvaluator:
    """Evaluate a stored signal price against later real OHLC bars.

    The entry is the actual last trade stored in the Flow decision, so entry
    lag is zero.  The first complete bar after the decision is used for
    MFE/MAE to avoid including pre-decision movement from a partial minute.
    """

    def __init__(
        self,
        market: str,
        bars: Iterable[ReplayBar],
        *,
        max_outcome_lag_sec: float = 60.0,
        max_first_bar_lag_sec: float = 60.0,
        max_data_gap_sec: float = 60.5,
    ) -> None:
        if (
            not market
            or max_outcome_lag_sec < 0
            or max_first_bar_lag_sec <= 0
            or max_data_gap_sec <= 0
        ):
            raise ValueError("market and lag/gap limits must be valid")
        self.market = market
        self.bars = list(bars)
        previous: ReplayBar | None = None
        for value in self.bars:
            if previous is not None:
                if value.open_time < previous.open_time:
                    raise ValueError("bars must be chronological")
                if value.close_time < previous.close_time:
                    raise ValueError("bar close times must be chronological")
            previous = value
        self.open_times = [value.open_time for value in self.bars]
        self.close_times = [value.close_time for value in self.bars]
        self.high_values = [value.high for value in self.bars]
        self.low_values = [value.low for value in self.bars]
        self.max_outcome_lag_sec = max_outcome_lag_sec
        self.max_first_bar_lag_sec = max_first_bar_lag_sec
        self.max_data_gap_sec = max_data_gap_sec
        self.high_index = (
            _ExtremaIndex(self.high_values) if self.high_values else None
        )
        self.low_index = _ExtremaIndex(self.low_values) if self.low_values else None
        bad_gap_prefix = [0]
        for left, right in zip(self.open_times, self.open_times[1:]):
            bad_gap_prefix.append(
                bad_gap_prefix[-1]
                + int((right - left).total_seconds() > max_data_gap_sec)
            )
        self.bad_gap_prefix = bad_gap_prefix

    def _missing(
        self,
        decision: AnalysisDecision,
        horizon_sec: int,
        status: str,
        *,
        outcome_index: int | None = None,
    ) -> ZeroSpreadOutcome:
        outcome = self.bars[outcome_index] if outcome_index is not None else None
        target = decision.decision_time + timedelta(seconds=horizon_sec)
        return ZeroSpreadOutcome(
            market=self.market,
            decision_id=decision.decision_id,
            source_family=decision.source_family,
            symbol=decision.symbol,
            window_sec=decision.window_sec,
            state=decision.state,
            hypothesis=decision.hypothesis,
            decision_class=decision.decision_class,
            side=decision.side,
            decision_time=decision.decision_time,
            horizon_sec=horizon_sec,
            status=status,
            entry_time=decision.decision_time,
            entry_price=decision.observed_price,
            entry_lag_ms=0,
            outcome_time=outcome.close_time if outcome else None,
            outcome_price=outcome.close if outcome else None,
            outcome_lag_ms=(
                int((outcome.close_time - target).total_seconds() * 1000)
                if outcome
                else None
            ),
            raw_return_bps=None,
            signed_return_bps=None,
            direction_result=None,
            mfe_bps=None,
            mae_bps=None,
            mfe_time=None,
            mae_time=None,
            mfe_after_entry_sec=None,
            mae_after_entry_sec=None,
        )

    def evaluate(
        self,
        decisions: Iterable[AnalysisDecision],
        horizons_sec: Iterable[int],
    ) -> tuple[ZeroSpreadOutcome, ...]:
        horizons = tuple(sorted(set(int(value) for value in horizons_sec)))
        if not horizons or any(value < 1 for value in horizons):
            raise ValueError("horizons_sec must contain positive values")
        decisions = tuple(decisions)
        if not self.bars or self.high_index is None or self.low_index is None:
            return tuple(
                self._missing(decision, horizon, "OUTCOME_MISSING")
                for decision in decisions
                for horizon in horizons
            )

        results: list[ZeroSpreadOutcome] = []
        for decision in decisions:
            first_full_index = bisect.bisect_left(
                self.open_times, decision.decision_time
            )
            for horizon in horizons:
                target = decision.decision_time + timedelta(seconds=horizon)
                outcome_index = bisect.bisect_left(self.close_times, target)
                if outcome_index >= len(self.bars):
                    results.append(
                        self._missing(decision, horizon, "OUTCOME_MISSING")
                    )
                    continue
                outcome = self.bars[outcome_index]
                outcome_lag = (outcome.close_time - target).total_seconds()
                if outcome_lag > self.max_outcome_lag_sec:
                    results.append(
                        self._missing(
                            decision,
                            horizon,
                            "OUTCOME_LAG",
                            outcome_index=outcome_index,
                        )
                    )
                    continue
                if first_full_index >= len(self.bars) or first_full_index > outcome_index:
                    results.append(
                        self._missing(
                            decision,
                            horizon,
                            "DATA_GAP",
                            outcome_index=outcome_index,
                        )
                    )
                    continue
                first_bar_lag = (
                    self.open_times[first_full_index] - decision.decision_time
                ).total_seconds()
                if (
                    first_bar_lag > self.max_first_bar_lag_sec
                    or self.bad_gap_prefix[outcome_index]
                    - self.bad_gap_prefix[first_full_index]
                    > 0
                ):
                    results.append(
                        self._missing(
                            decision,
                            horizon,
                            "DATA_GAP",
                            outcome_index=outcome_index,
                        )
                    )
                    continue

                low_index, _ = self.low_index.query(
                    first_full_index, outcome_index
                )
                _, high_index = self.high_index.query(
                    first_full_index, outcome_index
                )
                sign = 1.0 if decision.side == "BUY" else -1.0
                entry_price = decision.observed_price
                raw_return = (outcome.close / entry_price - 1.0) * _BPS
                signed_return = sign * raw_return
                if signed_return > 0:
                    direction_result = "CORRECT"
                elif signed_return < 0:
                    direction_result = "INCORRECT"
                else:
                    direction_result = "FLAT"

                favorable_index = high_index if sign > 0 else low_index
                adverse_index = low_index if sign > 0 else high_index
                favorable_price = (
                    self.high_values[favorable_index]
                    if sign > 0
                    else self.low_values[favorable_index]
                )
                adverse_price = (
                    self.low_values[adverse_index]
                    if sign > 0
                    else self.high_values[adverse_index]
                )
                favorable = sign * (favorable_price / entry_price - 1.0) * _BPS
                adverse = sign * (adverse_price / entry_price - 1.0) * _BPS
                if favorable > 0:
                    mfe = favorable
                    mfe_time = self.bars[favorable_index].close_time
                else:
                    mfe = 0.0
                    mfe_time = decision.decision_time
                if adverse < 0:
                    mae = adverse
                    mae_time = self.bars[adverse_index].close_time
                else:
                    mae = 0.0
                    mae_time = decision.decision_time
                results.append(
                    ZeroSpreadOutcome(
                        market=self.market,
                        decision_id=decision.decision_id,
                        source_family=decision.source_family,
                        symbol=decision.symbol,
                        window_sec=decision.window_sec,
                        state=decision.state,
                        hypothesis=decision.hypothesis,
                        decision_class=decision.decision_class,
                        side=decision.side,
                        decision_time=decision.decision_time,
                        horizon_sec=horizon,
                        status="OK",
                        entry_time=decision.decision_time,
                        entry_price=entry_price,
                        entry_lag_ms=0,
                        outcome_time=outcome.close_time,
                        outcome_price=outcome.close,
                        outcome_lag_ms=int(outcome_lag * 1000),
                        raw_return_bps=raw_return,
                        signed_return_bps=signed_return,
                        direction_result=direction_result,
                        mfe_bps=mfe,
                        mae_bps=mae,
                        mfe_time=mfe_time,
                        mae_time=mae_time,
                        mfe_after_entry_sec=(
                            mfe_time - decision.decision_time
                        ).total_seconds(),
                        mae_after_entry_sec=(
                            mae_time - decision.decision_time
                        ).total_seconds(),
                    )
                )
        return tuple(results)


class ZeroSpreadReplayEvaluator:
    """Evaluate fixed-time direction correctness on one real-price stream."""

    def __init__(
        self,
        market: str,
        prices: Iterable[ReplayPrice],
        *,
        max_entry_lag_sec: float = 2.0,
        max_outcome_lag_sec: float = 5.0,
        max_data_gap_sec: float = 120.0,
    ) -> None:
        if (
            not market
            or max_entry_lag_sec < 0
            or max_outcome_lag_sec < 0
            or max_data_gap_sec <= 0
        ):
            raise ValueError("market and lag/gap limits must be valid")
        self.market = market
        self.prices = list(prices)
        previous: datetime | None = None
        for value in self.prices:
            if previous is not None and value.event_time < previous:
                raise ValueError("prices must be chronological")
            previous = value.event_time
        self.times = [value.event_time for value in self.prices]
        self.values = [value.price for value in self.prices]
        self.max_entry_lag_sec = max_entry_lag_sec
        self.max_outcome_lag_sec = max_outcome_lag_sec
        self.max_data_gap_sec = max_data_gap_sec
        self.extrema = _ExtremaIndex(self.values) if self.values else None
        bad_gap_prefix = [0]
        for left, right in zip(self.times, self.times[1:]):
            bad_gap_prefix.append(
                bad_gap_prefix[-1]
                + int((right - left).total_seconds() > max_data_gap_sec)
            )
        if self.times:
            bad_gap_prefix.append(bad_gap_prefix[-1])
        self.bad_gap_prefix = bad_gap_prefix

    def _missing(
        self,
        decision: AnalysisDecision,
        horizon_sec: int,
        status: str,
        *,
        entry_index: int | None = None,
        outcome_index: int | None = None,
    ) -> ZeroSpreadOutcome:
        entry = self.prices[entry_index] if entry_index is not None else None
        outcome = self.prices[outcome_index] if outcome_index is not None else None
        return ZeroSpreadOutcome(
            market=self.market,
            decision_id=decision.decision_id,
            source_family=decision.source_family,
            symbol=decision.symbol,
            window_sec=decision.window_sec,
            state=decision.state,
            hypothesis=decision.hypothesis,
            decision_class=decision.decision_class,
            side=decision.side,
            decision_time=decision.decision_time,
            horizon_sec=horizon_sec,
            status=status,
            entry_time=entry.event_time if entry else None,
            entry_price=entry.price if entry else None,
            entry_lag_ms=(
                int((entry.event_time - decision.decision_time).total_seconds() * 1000)
                if entry
                else None
            ),
            outcome_time=outcome.event_time if outcome else None,
            outcome_price=outcome.price if outcome else None,
            outcome_lag_ms=None,
            raw_return_bps=None,
            signed_return_bps=None,
            direction_result=None,
            mfe_bps=None,
            mae_bps=None,
            mfe_time=None,
            mae_time=None,
            mfe_after_entry_sec=None,
            mae_after_entry_sec=None,
        )

    def evaluate(
        self,
        decisions: Iterable[AnalysisDecision],
        horizons_sec: Iterable[int],
    ) -> tuple[ZeroSpreadOutcome, ...]:
        horizons = tuple(sorted(set(int(value) for value in horizons_sec)))
        if not horizons or any(value < 1 for value in horizons):
            raise ValueError("horizons_sec must contain positive values")
        if not self.prices or self.extrema is None:
            return tuple(
                self._missing(decision, horizon, "ENTRY_MISSING")
                for decision in decisions
                for horizon in horizons
            )

        results: list[ZeroSpreadOutcome] = []
        for decision in decisions:
            entry_index = bisect.bisect_left(self.times, decision.decision_time)
            if entry_index >= len(self.prices):
                results.extend(
                    self._missing(decision, horizon, "ENTRY_MISSING")
                    for horizon in horizons
                )
                continue
            entry = self.prices[entry_index]
            entry_lag = (entry.event_time - decision.decision_time).total_seconds()
            if entry_lag > self.max_entry_lag_sec:
                results.extend(
                    self._missing(
                        decision,
                        horizon,
                        "ENTRY_LAG",
                        entry_index=entry_index,
                    )
                    for horizon in horizons
                )
                continue

            for horizon in horizons:
                target = entry.event_time + timedelta(seconds=horizon)
                outcome_index = bisect.bisect_left(self.times, target)
                if outcome_index >= len(self.prices):
                    results.append(
                        self._missing(
                            decision,
                            horizon,
                            "OUTCOME_MISSING",
                            entry_index=entry_index,
                        )
                    )
                    continue
                outcome = self.prices[outcome_index]
                outcome_lag = (outcome.event_time - target).total_seconds()
                if outcome_lag > self.max_outcome_lag_sec:
                    results.append(
                        self._missing(
                            decision,
                            horizon,
                            "OUTCOME_LAG",
                            entry_index=entry_index,
                            outcome_index=outcome_index,
                        )
                    )
                    continue
                if (
                    self.bad_gap_prefix[outcome_index]
                    - self.bad_gap_prefix[entry_index]
                    > 0
                ):
                    results.append(
                        self._missing(
                            decision,
                            horizon,
                            "DATA_GAP",
                            entry_index=entry_index,
                            outcome_index=outcome_index,
                        )
                    )
                    continue

                min_index, max_index = self.extrema.query(entry_index, outcome_index)
                sign = 1.0 if decision.side == "BUY" else -1.0
                raw_return = (
                    self.values[outcome_index] / self.values[entry_index] - 1.0
                ) * _BPS
                signed_return = sign * raw_return
                if signed_return > 0:
                    direction_result = "CORRECT"
                elif signed_return < 0:
                    direction_result = "INCORRECT"
                else:
                    direction_result = "FLAT"
                favorable_index = max_index if sign > 0 else min_index
                adverse_index = min_index if sign > 0 else max_index
                mfe = sign * (
                    self.values[favorable_index] / self.values[entry_index] - 1.0
                ) * _BPS
                mae = sign * (
                    self.values[adverse_index] / self.values[entry_index] - 1.0
                ) * _BPS
                results.append(
                    ZeroSpreadOutcome(
                        market=self.market,
                        decision_id=decision.decision_id,
                        source_family=decision.source_family,
                        symbol=decision.symbol,
                        window_sec=decision.window_sec,
                        state=decision.state,
                        hypothesis=decision.hypothesis,
                        decision_class=decision.decision_class,
                        side=decision.side,
                        decision_time=decision.decision_time,
                        horizon_sec=horizon,
                        status="OK",
                        entry_time=entry.event_time,
                        entry_price=entry.price,
                        entry_lag_ms=int(entry_lag * 1000),
                        outcome_time=outcome.event_time,
                        outcome_price=outcome.price,
                        outcome_lag_ms=int(outcome_lag * 1000),
                        raw_return_bps=raw_return,
                        signed_return_bps=signed_return,
                        direction_result=direction_result,
                        mfe_bps=mfe,
                        mae_bps=mae,
                        mfe_time=self.times[favorable_index],
                        mae_time=self.times[adverse_index],
                        mfe_after_entry_sec=(
                            self.times[favorable_index] - entry.event_time
                        ).total_seconds(),
                        mae_after_entry_sec=(
                            self.times[adverse_index] - entry.event_time
                        ).total_seconds(),
                    )
                )
        return tuple(results)

