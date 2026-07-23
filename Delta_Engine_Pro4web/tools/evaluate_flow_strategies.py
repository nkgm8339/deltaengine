"""Evaluate cost-aware Flow Price Response strategies without sending orders.

The evaluator is independent from the live pipeline and UI. It reads stable
Parquet files, creates causal one-minute-bar entries, purges overlapping
positions, freezes training-period feature ranges, and reports untouched
chronological test-period results for 15, 30, and 60 minute holds.
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import random
import statistics
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import pyarrow.parquet as pq
import yaml


UTC = timezone.utc
MINUTE = timedelta(minutes=1)


@dataclass(frozen=True)
class FlowEvent:
    event_time: datetime
    symbol: str
    window_sec: int
    state: str
    pressure_side: str
    pressure_ratio: float
    persistence: float
    relative_volume: float | None
    last_price: float


@dataclass(frozen=True)
class Bar:
    bar_time: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class OISample:
    source_time: datetime
    open_interest: float


@dataclass(frozen=True)
class Signal:
    strategy: str
    source_event_time: datetime
    entry_time: datetime
    side: str
    entry_price: float
    state: str
    pressure_side: str
    pressure_ratio: float
    persistence: float
    relative_volume: float | None


@dataclass(frozen=True)
class Trade:
    strategy: str
    source_event_time: datetime
    entry_time: datetime
    exit_time: datetime
    side: str
    entry_price: float
    exit_price: float
    gross_bps: float
    mfe_bps: float
    mae_bps: float
    context_volatility_bps: float | None
    oi_change_pct_10m: float | None


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _number(value: Any) -> float | None:
    if value is None:
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _quantile(values: Iterable[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("cannot calculate a quantile from no values")
    position = fraction * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _ceil_minute(value: datetime) -> datetime:
    floor = value.replace(second=0, microsecond=0)
    return floor if value == floor else floor + MINUTE


def _read_stable_rows(
    folder: Path,
    columns: list[str],
    *,
    stable_before_epoch: float,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows: list[dict[str, Any]] = []
    audit = {"stable_files": 0, "active_files_skipped": 0, "invalid_files": 0}
    for path in folder.rglob("*.parquet"):
        try:
            if path.stat().st_mtime >= stable_before_epoch:
                audit["active_files_skipped"] += 1
                continue
            rows.extend(pq.ParquetFile(path).read(columns=columns).to_pylist())
            audit["stable_files"] += 1
        except Exception:
            audit["invalid_files"] += 1
    return rows, audit


def load_events(
    folder: Path, clean_start: datetime, stable_before_epoch: float
) -> tuple[list[FlowEvent], dict[str, int]]:
    rows, audit = _read_stable_rows(
        folder,
        [
            "event_time", "symbol", "window_sec", "state", "pressure_side",
            "pressure_ratio", "persistence", "relative_volume", "last_price",
        ],
        stable_before_epoch=stable_before_epoch,
    )
    unique: dict[tuple[Any, ...], FlowEvent] = {}
    rejected = 0
    for row in rows:
        try:
            event = FlowEvent(
                event_time=_as_utc(row["event_time"]),
                symbol=str(row["symbol"]),
                window_sec=int(row["window_sec"]),
                state=str(row["state"]),
                pressure_side=str(row["pressure_side"]),
                pressure_ratio=float(row["pressure_ratio"]),
                persistence=float(row["persistence"]),
                relative_volume=_number(row["relative_volume"]),
                last_price=float(row["last_price"]),
            )
            if event.event_time < clean_start or event.last_price <= 0:
                continue
            key = (event.event_time, event.symbol, event.window_sec, event.state)
            unique[key] = event
        except (KeyError, TypeError, ValueError):
            rejected += 1
    audit.update({"raw_rows": len(rows), "unique_clean_rows": len(unique), "rejected_rows": rejected})
    return sorted(unique.values(), key=lambda row: row.event_time), audit


def load_bars(
    folder: Path, clean_start: datetime, stable_before_epoch: float
) -> tuple[list[Bar], dict[str, int]]:
    rows, audit = _read_stable_rows(
        folder, ["bar_time", "open", "high", "low", "close"],
        stable_before_epoch=stable_before_epoch,
    )
    unique: dict[datetime, Bar] = {}
    rejected = 0
    for row in rows:
        try:
            bar = Bar(
                bar_time=_as_utc(row["bar_time"]),
                open=float(row["open"]), high=float(row["high"]),
                low=float(row["low"]), close=float(row["close"]),
            )
            if bar.bar_time < clean_start.replace(second=0, microsecond=0):
                continue
            if not (
                bar.low > 0
                and bar.low <= min(bar.open, bar.close)
                and max(bar.open, bar.close) <= bar.high
            ):
                raise ValueError
            unique[bar.bar_time] = bar
        except (KeyError, TypeError, ValueError):
            rejected += 1
    audit.update({"raw_rows": len(rows), "unique_clean_rows": len(unique), "rejected_rows": rejected})
    return sorted(unique.values(), key=lambda row: row.bar_time), audit


def load_oi(
    folder: Path, clean_start: datetime, stable_before_epoch: float
) -> tuple[list[OISample], dict[str, int]]:
    rows, audit = _read_stable_rows(
        folder, ["source_time", "open_interest"], stable_before_epoch=stable_before_epoch
    )
    unique: dict[datetime, OISample] = {}
    rejected = 0
    for row in rows:
        try:
            sample = OISample(_as_utc(row["source_time"]), float(row["open_interest"]))
            if sample.source_time >= clean_start and sample.open_interest > 0:
                unique[sample.source_time] = sample
        except (KeyError, TypeError, ValueError):
            rejected += 1
    audit.update({"raw_rows": len(rows), "unique_clean_rows": len(unique), "rejected_rows": rejected})
    return sorted(unique.values(), key=lambda row: row.source_time), audit


def chronological_split(events: list[FlowEvent], fraction: float) -> datetime:
    if not events or not 0 < fraction < 1:
        raise ValueError("events and a train fraction between zero and one are required")
    return events[0].event_time + (events[-1].event_time - events[0].event_time) * fraction


def derive_strategy_a_ranges(
    events: list[FlowEvent], split_time: datetime, settings: dict[str, Any]
) -> dict[str, tuple[float, float]]:
    candidates = [
        event for event in events
        if event.event_time < split_time
        and event.window_sec == int(settings["window_sec"])
        and event.state.endswith(str(settings["state_suffix"]))
        and event.relative_volume is not None
    ]
    low = float(settings["feature_quantile_low"])
    high = float(settings["feature_quantile_high"])
    if len(candidates) < 4:
        raise ValueError("not enough training events to derive Strategy A ranges")
    return {
        "pressure_strength": (
            _quantile((abs(event.pressure_ratio) for event in candidates), low),
            _quantile((abs(event.pressure_ratio) for event in candidates), high),
        ),
        "persistence": (
            _quantile((event.persistence for event in candidates), low),
            _quantile((event.persistence for event in candidates), high),
        ),
        "relative_volume": (
            _quantile((event.relative_volume for event in candidates if event.relative_volume is not None), low),
            _quantile((event.relative_volume for event in candidates if event.relative_volume is not None), high),
        ),
    }


def _between(value: float | None, bounds: tuple[float, float]) -> bool:
    return value is not None and bounds[0] <= value <= bounds[1]


def _bar_slice(
    bars: list[Bar], bar_times: list[datetime], start: datetime, end: datetime
) -> list[Bar]:
    left = bisect.bisect_left(bar_times, start)
    right = bisect.bisect_right(bar_times, end)
    return bars[left:right]


def build_strategy_a_signals(
    events: list[FlowEvent],
    bars: list[Bar],
    ranges: dict[str, tuple[float, float]],
    settings: dict[str, Any],
) -> list[Signal]:
    bar_times = [bar.bar_time for bar in bars]
    timeout = timedelta(seconds=int(settings["retest_timeout_sec"]))
    result: list[Signal] = []
    for event in events:
        if (
            event.window_sec != int(settings["window_sec"])
            or not event.state.endswith(str(settings["state_suffix"]))
        ):
            continue
        if not (
            _between(abs(event.pressure_ratio), ranges["pressure_strength"])
            and _between(event.persistence, ranges["persistence"])
            and _between(event.relative_volume, ranges["relative_volume"])
        ):
            continue
        start = _ceil_minute(event.event_time)
        for bar in _bar_slice(bars, bar_times, start, event.event_time + timeout):
            touched = (
                bar.low <= event.last_price
                if event.pressure_side == "BUY"
                else bar.high >= event.last_price
            )
            if touched:
                result.append(
                    Signal(
                        strategy=str(settings["name"]),
                        source_event_time=event.event_time,
                        entry_time=bar.bar_time + MINUTE,
                        side="LONG" if event.pressure_side == "BUY" else "SHORT",
                        entry_price=event.last_price,
                        state=event.state,
                        pressure_side=event.pressure_side,
                        pressure_ratio=event.pressure_ratio,
                        persistence=event.persistence,
                        relative_volume=event.relative_volume,
                    )
                )
                break
    return result


def build_strategy_b_signals(
    events: list[FlowEvent], bars: list[Bar], settings: dict[str, Any]
) -> list[Signal]:
    window_sec = int(settings["window_sec"])
    effective_suffix = str(settings["effective_suffix"])
    failure_suffixes = tuple(str(value) for value in settings["failure_suffixes"])
    lookback = timedelta(seconds=int(settings["effective_lookback_sec"]))
    confirmation_timeout = timedelta(seconds=int(settings["confirmation_timeout_sec"]))
    retest_timeout = timedelta(seconds=int(settings["retest_timeout_sec"]))
    confirmation_bps = float(settings["confirmation_bps"])
    bar_times = [bar.bar_time for bar in bars]
    last_effective: FlowEvent | None = None
    result: list[Signal] = []
    for event in events:
        if event.window_sec != window_sec:
            continue
        if event.state.endswith(effective_suffix):
            last_effective = event
            continue
        if not event.state.endswith(failure_suffixes):
            continue
        effective = last_effective
        if (
            effective is None
            or effective.pressure_side != event.pressure_side
            or event.event_time - effective.event_time > lookback
        ):
            last_effective = None
            continue
        last_effective = None
        trade_side = "SHORT" if event.pressure_side == "BUY" else "LONG"
        sign = -1.0 if trade_side == "SHORT" else 1.0
        confirmation: Bar | None = None
        for bar in _bar_slice(
            bars, bar_times, _ceil_minute(event.event_time),
            event.event_time + confirmation_timeout,
        ):
            reversal_bps = sign * (bar.close / event.last_price - 1.0) * 10_000.0
            if reversal_bps >= confirmation_bps:
                confirmation = bar
                break
        if confirmation is None:
            continue
        confirmation_price = confirmation.close
        retest_start = confirmation.bar_time + MINUTE
        for bar in _bar_slice(
            bars, bar_times, retest_start, retest_start + retest_timeout
        ):
            touched = (
                bar.high >= confirmation_price
                if trade_side == "SHORT"
                else bar.low <= confirmation_price
            )
            if touched:
                result.append(
                    Signal(
                        strategy=str(settings["name"]),
                        source_event_time=event.event_time,
                        entry_time=bar.bar_time + MINUTE,
                        side=trade_side,
                        entry_price=confirmation_price,
                        state=event.state,
                        pressure_side=event.pressure_side,
                        pressure_ratio=event.pressure_ratio,
                        persistence=event.persistence,
                        relative_volume=event.relative_volume,
                    )
                )
                break
    return result


def _context_volatility(
    entry_time: datetime, bars: list[Bar], bar_times: list[datetime]
) -> float | None:
    prior = _bar_slice(
        bars, bar_times, entry_time - timedelta(hours=1), entry_time - MINUTE
    )
    if len(prior) < 45:
        return None
    highest = max(bar.high for bar in prior)
    lowest = min(bar.low for bar in prior)
    return (highest / lowest - 1.0) * 10_000.0 if lowest > 0 else None


def _oi_change(
    entry_time: datetime, samples: list[OISample], sample_times: list[datetime]
) -> float | None:
    current_index = bisect.bisect_right(sample_times, entry_time) - 1
    prior_index = bisect.bisect_right(
        sample_times, entry_time - timedelta(minutes=10)
    ) - 1
    if current_index < 0 or prior_index < 0:
        return None
    current, prior = samples[current_index], samples[prior_index]
    if entry_time - current.source_time > timedelta(seconds=30) or prior.open_interest <= 0:
        return None
    return (current.open_interest / prior.open_interest - 1.0) * 100.0


def signals_to_trades(
    signals: list[Signal], bars: list[Bar], oi: list[OISample], horizon_sec: int
) -> tuple[list[Trade], dict[str, int]]:
    bar_times = [bar.bar_time for bar in bars]
    bar_by_time = {bar.bar_time: bar for bar in bars}
    oi_times = [sample.source_time for sample in oi]
    audit: dict[str, int] = defaultdict(int)
    result: list[Trade] = []
    expected_bars = horizon_sec // 60
    for signal in signals:
        exit_time = signal.entry_time + timedelta(seconds=horizon_sec)
        exit_bar = bar_by_time.get(exit_time - MINUTE)
        if exit_bar is None:
            audit["missing_exact_exit_bar"] += 1
            continue
        path = _bar_slice(bars, bar_times, signal.entry_time, exit_time - MINUTE)
        if len(path) < math.ceil(expected_bars * 0.90):
            audit["insufficient_bar_coverage"] += 1
            continue
        gaps = [
            (right.bar_time - left.bar_time).total_seconds()
            for left, right in zip(path, path[1:])
        ]
        if gaps and max(gaps) > 180:
            audit["bar_gap_over_180_sec"] += 1
            continue
        sign = 1.0 if signal.side == "LONG" else -1.0
        signed_extremes = [
            sign * (price / signal.entry_price - 1.0) * 10_000.0
            for bar in path for price in (bar.low, bar.high)
        ]
        result.append(
            Trade(
                strategy=signal.strategy,
                source_event_time=signal.source_event_time,
                entry_time=signal.entry_time,
                exit_time=exit_time,
                side=signal.side,
                entry_price=signal.entry_price,
                exit_price=exit_bar.close,
                gross_bps=sign * (exit_bar.close / signal.entry_price - 1.0) * 10_000.0,
                mfe_bps=max(signed_extremes),
                mae_bps=min(signed_extremes),
                context_volatility_bps=_context_volatility(
                    signal.entry_time, bars, bar_times
                ),
                oi_change_pct_10m=_oi_change(signal.entry_time, oi, oi_times),
            )
        )
    audit["trades_built"] = len(result)
    return result, dict(audit)


def purge_overlaps(trades: Iterable[Trade]) -> list[Trade]:
    kept: list[Trade] = []
    available_at = datetime.min.replace(tzinfo=UTC)
    for trade in sorted(trades, key=lambda row: (row.entry_time, row.source_event_time)):
        if trade.entry_time >= available_at:
            kept.append(trade)
            available_at = trade.exit_time
    return kept


def _bootstrap_ci(
    values: list[float], samples: int, seed: int
) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    rng = random.Random(seed)
    means = [
        sum(values[rng.randrange(len(values))] for _ in values) / len(values)
        for _ in range(samples)
    ]
    return _quantile(means, 0.025), _quantile(means, 0.975)


def _max_drawdown(values: Iterable[float]) -> float:
    equity = peak = 0.0
    drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = min(drawdown, equity - peak)
    return drawdown


def _metric(values: list[float], bootstrap_samples: int, seed: int) -> dict[str, Any]:
    if not values:
        return {
            "count": 0, "mean": None, "median": None, "win_rate_pct": None,
            "profit_factor": None, "max_drawdown_bps": None,
            "bootstrap_mean_95_low": None, "bootstrap_mean_95_high": None,
        }
    positive = sum(value for value in values if value > 0)
    negative = -sum(value for value in values if value < 0)
    low, high = _bootstrap_ci(values, bootstrap_samples, seed)
    return {
        "count": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "win_rate_pct": sum(value > 0 for value in values) / len(values) * 100.0,
        "profit_factor": positive / negative if negative else None,
        "max_drawdown_bps": _max_drawdown(values),
        "bootstrap_mean_95_low": low,
        "bootstrap_mean_95_high": high,
    }


def _segment(
    trades: list[Trade], key_function: Any, cost_bps: float
) -> dict[str, dict[str, float | int | None]]:
    groups: dict[str, list[float]] = defaultdict(list)
    for trade in trades:
        key = key_function(trade)
        if key is not None:
            groups[str(key)].append(trade.gross_bps - cost_bps)
    return {
        key: {
            "count": len(values),
            "mean_net_bps": statistics.fmean(values),
            "median_net_bps": statistics.median(values),
            "win_rate_pct": sum(value > 0 for value in values) / len(values) * 100.0,
        }
        for key, values in sorted(groups.items())
    }


def summarize_trades(
    trades: list[Trade],
    costs: list[float],
    stress_multiple: float,
    bootstrap_samples: int,
    *,
    volatility_threshold: float | None,
) -> dict[str, Any]:
    gross = [trade.gross_bps for trade in trades]
    scenarios: dict[str, Any] = {}
    scenario_costs = sorted(set(costs + [cost * stress_multiple for cost in costs]))
    for index, cost in enumerate(scenario_costs):
        scenarios[f"{cost:g}_bps"] = {
            "roundtrip_cost_bps": cost,
            **_metric([value - cost for value in gross], bootstrap_samples, 100 + index),
        }
    reference_cost = 3.0 if 3.0 in scenario_costs else scenario_costs[-1]
    jst = timezone(timedelta(hours=9))
    daily_net: dict[str, float] = defaultdict(float)
    for trade in trades:
        daily_net[trade.entry_time.astimezone(jst).date().isoformat()] += (
            trade.gross_bps - reference_cost
        )
    positive_total = sum(value for value in daily_net.values() if value > 0)
    best_day_share = (
        max(daily_net.values()) / positive_total
        if daily_net and positive_total > 0 and max(daily_net.values()) > 0
        else None
    )
    return {
        "gross": _metric(gross, bootstrap_samples, 71),
        "mfe_bps": _metric([trade.mfe_bps for trade in trades], bootstrap_samples, 72),
        "mae_bps": _metric([trade.mae_bps for trade in trades], bootstrap_samples, 73),
        "cost_scenarios": scenarios,
        "test_days": len(daily_net),
        "daily_net_bps_at_reference_cost": dict(sorted(daily_net.items())),
        "best_day_positive_profit_share": best_day_share,
        "by_side_at_reference_cost": _segment(
            trades, lambda trade: trade.side, reference_cost
        ),
        "by_jst_six_hour_block_at_reference_cost": _segment(
            trades,
            lambda trade: f"{(trade.entry_time.astimezone(jst).hour // 6) * 6:02d}:00",
            reference_cost,
        ),
        "by_volatility_at_reference_cost": _segment(
            trades,
            lambda trade: (
                None
                if trade.context_volatility_bps is None or volatility_threshold is None
                else "HIGH" if trade.context_volatility_bps >= volatility_threshold else "LOW"
            ),
            reference_cost,
        ),
        "by_oi_10m_at_reference_cost": _segment(
            trades,
            lambda trade: (
                None if trade.oi_change_pct_10m is None
                else "RISING" if trade.oi_change_pct_10m > 0 else "FALLING_OR_FLAT"
            ),
            reference_cost,
        ),
    }


def classify_test_result(summary: dict[str, Any], config: dict[str, Any]) -> str:
    validation = config["validation"]
    count = int(summary["gross"]["count"])
    days = int(summary["test_days"])
    reference = summary["cost_scenarios"].get("3_bps")
    stressed = summary["cost_scenarios"].get("4.5_bps")
    if reference is None or stressed is None:
        return "CONFIGURATION_ERROR"
    if count < int(validation["minimum_interim_test_trades"]) or days < 2:
        mean = reference["mean"]
        return "INSUFFICIENT_POSITIVE" if mean is not None and mean > 0 else "INSUFFICIENT_NEGATIVE"
    if reference["mean"] is None or reference["mean"] <= 0:
        return "REJECT_CURRENT_RULE"
    if reference["bootstrap_mean_95_low"] is None or reference["bootstrap_mean_95_low"] <= 0:
        return "UNPROVEN"
    if stressed["bootstrap_mean_95_low"] is None or stressed["bootstrap_mean_95_low"] <= 0:
        return "COST_FRAGILE"
    if (
        count >= int(validation["minimum_deployment_trades"])
        and days >= int(validation["minimum_deployment_days"])
        and summary["best_day_positive_profit_share"] is not None
        and summary["best_day_positive_profit_share"]
        <= float(validation["maximum_best_day_profit_share"])
    ):
        return "DEPLOYMENT_CANDIDATE"
    return "PROVISIONAL_EDGE"


def _trade_row(trade: Trade) -> dict[str, Any]:
    return {
        "strategy": trade.strategy,
        "source_event_time": trade.source_event_time.isoformat(),
        "entry_time": trade.entry_time.isoformat(),
        "exit_time": trade.exit_time.isoformat(),
        "side": trade.side,
        "entry_price": trade.entry_price,
        "exit_price": trade.exit_price,
        "gross_bps": trade.gross_bps,
        "mfe_bps": trade.mfe_bps,
        "mae_bps": trade.mae_bps,
        "context_volatility_bps": trade.context_volatility_bps,
        "oi_change_pct_10m": trade.oi_change_pct_10m,
    }


def evaluate(config: dict[str, Any], project: Path) -> dict[str, Any]:
    clean_start = _as_utc(
        datetime.fromisoformat(str(config["clean_start"]).replace("Z", "+00:00"))
    )
    stable_before = time.time() - int(config["stable_file_age_sec"])
    events, event_audit = load_events(
        project / "data/parquet/flow_response_events", clean_start, stable_before
    )
    bars, bar_audit = load_bars(
        project / "data/parquet/symbol=BTCUSDT/timeframe=1m", clean_start,
        stable_before,
    )
    oi, oi_audit = load_oi(
        project / "data/parquet/open_interest_samples", clean_start, stable_before
    )
    if not events or not bars:
        raise RuntimeError("clean Flow events and one-minute bars are required")
    split_time = chronological_split(events, float(config["train_fraction"]))
    embargo = timedelta(seconds=int(config["split_embargo_sec"]))
    ranges = derive_strategy_a_ranges(events, split_time, config["strategy_a"])
    signals = {
        str(config["strategy_a"]["name"]): build_strategy_a_signals(
            events, bars, ranges, config["strategy_a"]
        ),
        str(config["strategy_b"]["name"]): build_strategy_b_signals(
            events, bars, config["strategy_b"]
        ),
    }
    costs = [float(value) for value in config["roundtrip_cost_bps"]]
    stress = float(config["stress_cost_multiple"])
    bootstrap_samples = int(config["validation"]["bootstrap_samples"])
    results: dict[str, Any] = {}
    outcome_audit: dict[str, Any] = {}
    for strategy, strategy_signals in signals.items():
        strategy_results: dict[str, Any] = {}
        for horizon in (int(value) for value in config["horizons_sec"]):
            trades, audit = signals_to_trades(strategy_signals, bars, oi, horizon)
            train = purge_overlaps(
                trade for trade in trades if trade.exit_time <= split_time
            )
            test = purge_overlaps(
                trade for trade in trades if trade.entry_time >= split_time + embargo
            )
            training_volatility = [
                trade.context_volatility_bps for trade in train
                if trade.context_volatility_bps is not None
            ]
            volatility_threshold = (
                statistics.median(training_volatility) if training_volatility else None
            )
            train_summary = summarize_trades(
                train, costs, stress, bootstrap_samples,
                volatility_threshold=volatility_threshold,
            )
            test_summary = summarize_trades(
                test, costs, stress, bootstrap_samples,
                volatility_threshold=volatility_threshold,
            )
            test_summary["classification"] = classify_test_result(
                test_summary, config
            )
            train_net = train_summary["cost_scenarios"]["3_bps"]["mean"]
            test_net = test_summary["cost_scenarios"]["3_bps"]["mean"]
            strategy_results[str(horizon)] = {
                "horizon_sec": horizon,
                "signals_before_outcome_checks": len(strategy_signals),
                "training": train_summary,
                "test": test_summary,
                "train_test_sign_agreement_at_3bps": (
                    None if train_net is None or test_net is None
                    else (train_net >= 0) == (test_net >= 0)
                ),
                "training_trade_ledger": [_trade_row(trade) for trade in train],
                "test_trade_ledger": [_trade_row(trade) for trade in test],
                "training_volatility_median_bps": volatility_threshold,
            }
            outcome_audit[f"{strategy}:{horizon}"] = audit
        results[strategy] = strategy_results

    classifications = [
        horizon["test"]["classification"]
        for strategy in results.values() for horizon in strategy.values()
    ]
    if "DEPLOYMENT_CANDIDATE" in classifications:
        overall = "DEPLOYMENT_CANDIDATE_PRESENT"
    elif any(
        value in {"PROVISIONAL_EDGE", "COST_FRAGILE", "UNPROVEN"}
        for value in classifications
    ):
        overall = "RESEARCH_ONLY_NO_DEPLOYMENT"
    elif any(value.startswith("INSUFFICIENT") for value in classifications):
        overall = "INSUFFICIENT_DATA_NO_DEPLOYMENT"
    else:
        overall = "NO_CURRENT_RULE_PASSED"
    return {
        "observation_only": True,
        "orders_sent": False,
        "overall_classification": overall,
        "configuration": config,
        "split": {
            "train_before": split_time.isoformat(),
            "test_from_after_embargo": (split_time + embargo).isoformat(),
            "embargo_sec": int(config["split_embargo_sec"]),
        },
        "strategy_a_frozen_training_ranges": {
            key: {"low": value[0], "high": value[1]}
            for key, value in ranges.items()
        },
        "data_audit": {
            "events": event_audit,
            "bars": bar_audit,
            "open_interest": oi_audit,
            "event_time_min": events[0].event_time.isoformat(),
            "event_time_max": events[-1].event_time.isoformat(),
            "bar_time_min": bars[0].bar_time.isoformat(),
            "bar_time_max": bars[-1].bar_time.isoformat(),
            "oi_time_min": oi[0].source_time.isoformat() if oi else None,
            "oi_time_max": oi[-1].source_time.isoformat() if oi else None,
            "signals": {name: len(rows) for name, rows in signals.items()},
            "outcomes": outcome_audit,
        },
        "results": results,
        "limitations": [
            "The clean observation span is far shorter than the 30-day deployment requirement.",
            "One-minute bars cannot prove intrabar queue position or passive-limit fill quality.",
            "Spread, fee, and slippage are explicit roundtrip bps scenarios, not historical fills.",
            "Open-interest segmentation is unavailable before the first stored OI sample.",
            "No threshold was optimized on test-period returns.",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    audit = report["data_audit"]
    lines = [
        "# Flow strategy offline evaluation", "",
        f"Overall: **{report['overall_classification']}**", "",
        "This report is observation-only. No order was sent.", "",
        "## Data and split", "",
        f"- Events: {audit['events']['unique_clean_rows']} ({audit['event_time_min']} to {audit['event_time_max']})",
        f"- One-minute bars: {audit['bars']['unique_clean_rows']} ({audit['bar_time_min']} to {audit['bar_time_max']})",
        f"- Train before: {report['split']['train_before']}",
        f"- Test from: {report['split']['test_from_after_embargo']}", "",
        "## Untouched test results", "",
        "| Strategy | Hold | Trades | Gross mean | Net @1.5bp | Net @3bp | Net @4.5bp | Classification |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for strategy, horizons in report["results"].items():
        for horizon in horizons.values():
            test = horizon["test"]

            def value(*path: str) -> str:
                current: Any = test
                for key in path:
                    current = current[key]
                return "n/a" if current is None else f"{current:+.3f}"

            lines.append(
                f"| {strategy} | {horizon['horizon_sec'] // 60}m | "
                f"{test['gross']['count']} | {value('gross', 'mean')} | "
                f"{value('cost_scenarios', '1.5_bps', 'mean')} | "
                f"{value('cost_scenarios', '3_bps', 'mean')} | "
                f"{value('cost_scenarios', '4.5_bps', 'mean')} | "
                f"{test['classification']} |"
            )
    lines.extend(["", "## Frozen Strategy A ranges", ""])
    for name, bounds in report["strategy_a_frozen_training_ranges"].items():
        lines.append(f"- {name}: {bounds['low']:.6f} to {bounds['high']:.6f}")
    lines.extend(["", "## Limits", ""])
    lines.extend(f"- {item}" for item in report["limitations"])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path,
        default=Path("config/flow_strategy_evaluation.yaml"),
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path("data/strategy_research/flow_strategy_evaluation.json"),
    )
    parser.add_argument(
        "--markdown-output", type=Path,
        default=Path("data/strategy_research/flow_strategy_evaluation.md"),
    )
    args = parser.parse_args(argv)
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("strategy evaluation config must be a mapping")
    project = Path(__file__).resolve().parents[1]
    report = evaluate(config, project)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
