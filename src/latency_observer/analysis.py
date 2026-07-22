"""Offline statistics for Binance/HFM quote observations.

This module deliberately deals only in observed quotes.  It does not emit a
trading signal and it does not make an orderability claim from displayed prices.
"""

from __future__ import annotations

import csv
import math
from bisect import bisect_left
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean, pstdev
from typing import Iterable


@dataclass(frozen=True)
class Quote:
    source: str
    symbol: str
    exchange_time_ms: int | None
    local_received_ns: int
    bid: float
    ask: float
    source_sequence: int | None = None

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread(self) -> float:
        return self.ask - self.bid


def load_quotes(path: str | Path) -> list[Quote]:
    quotes: list[Quote] = []
    with Path(path).open("r", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            try:
                bid = float(row["bid"])
                ask = float(row["ask"])
                received = int(row["local_received_ns"])
                exchange_raw = row.get("exchange_time_ms", "").strip()
                exchange_ms = int(exchange_raw) if exchange_raw else None
                sequence_raw = row.get("source_sequence", "").strip()
                source_sequence = int(sequence_raw) if sequence_raw else None
            except (KeyError, TypeError, ValueError):
                continue
            if not (
                math.isfinite(bid)
                and math.isfinite(ask)
                and bid > 0
                and ask >= bid
                and received > 0
            ):
                continue
            quotes.append(
                Quote(
                    source=row["source"].strip().upper(),
                    symbol=row["symbol"].strip(),
                    exchange_time_ms=exchange_ms,
                    local_received_ns=received,
                    bid=bid,
                    ask=ask,
                    source_sequence=source_sequence,
                )
            )
    return sorted(quotes, key=lambda quote: quote.local_received_ns)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _summary(values: Iterable[float]) -> dict[str, float | int | None]:
    data = list(values)
    return {
        "count": len(data),
        "mean": fmean(data) if data else None,
        "stddev": pstdev(data) if len(data) > 1 else (0.0 if data else None),
        "median": _percentile(data, 0.5),
        "p95": _percentile(data, 0.95),
        "p99": _percentile(data, 0.99),
        "minimum": min(data) if data else None,
        "maximum": max(data) if data else None,
    }


def _aligned(quotes: list[Quote], max_staleness_ms: int) -> list[tuple[Quote, Quote]]:
    latest: dict[str, Quote] = {}
    pairs: list[tuple[Quote, Quote]] = []
    for quote in quotes:
        latest[quote.source] = quote
        if "BINANCE" not in latest or "HFM" not in latest:
            continue
        binance, hfm = latest["BINANCE"], latest["HFM"]
        age_ms = abs(binance.local_received_ns - hfm.local_received_ns) / 1_000_000
        if age_ms <= max_staleness_ms:
            pairs.append((binance, hfm))
    return pairs


def _move_events(quotes: list[Quote], threshold_bps: float) -> list[tuple[int, int]]:
    if not quotes:
        return []
    anchor = quotes[0].mid
    events: list[tuple[int, int]] = []
    for quote in quotes[1:]:
        move_bps = (quote.mid / anchor - 1.0) * 10_000.0
        if abs(move_bps) >= threshold_bps:
            direction = 1 if move_bps > 0 else -1
            events.append((quote.local_received_ns, direction))
            anchor = quote.mid
    return events


def _latencies(
    binance: list[Quote],
    hfm: list[Quote],
    threshold_bps: float,
    match_window_ms: int,
) -> tuple[list[float], int]:
    binance_events = _move_events(binance, threshold_bps)
    hfm_events = _move_events(hfm, threshold_bps)
    window_ns = match_window_ms * 1_000_000
    matched: list[float] = []
    used_hfm: set[int] = set()
    for binance_ns, direction in binance_events:
        candidates = [
            (index, hfm_ns)
            for index, (hfm_ns, hfm_direction) in enumerate(hfm_events)
            if index not in used_hfm
            and hfm_direction == direction
            and abs(hfm_ns - binance_ns) <= window_ns
        ]
        if candidates:
            index, nearest = min(candidates, key=lambda value: abs(value[1] - binance_ns))
            used_hfm.add(index)
            matched.append((nearest - binance_ns) / 1_000_000.0)
    return matched, len(binance_events)


def _candles(quotes: list[Quote], minutes: int) -> dict[int, tuple[float, float, float, float]]:
    width_ns = minutes * 60 * 1_000_000_000
    buckets: dict[int, list[float]] = {}
    for quote in quotes:
        bucket = quote.local_received_ns // width_ns
        buckets.setdefault(bucket, []).append(quote.mid)
    return {
        bucket: (values[0], max(values), min(values), values[-1])
        for bucket, values in buckets.items()
    }


def _candle_comparison(binance: list[Quote], hfm: list[Quote], minutes: int) -> dict:
    left, right = _candles(binance, minutes), _candles(hfm, minutes)
    common = sorted(set(left) & set(right))
    width_ns = minutes * 60 * 1_000_000_000
    hfm_quotes_by_bucket: dict[int, list[Quote]] = {}
    for quote in hfm:
        hfm_quotes_by_bucket.setdefault(quote.local_received_ns // width_ns, []).append(quote)
    hfm_ranges = [right[key][1] - right[key][2] for key in common]
    hfm_median_spreads = [
        _percentile([quote.spread for quote in hfm_quotes_by_bucket[key]], 0.5)
        for key in common
    ]
    spread_to_range = [
        spread / candle_range * 100.0
        for spread, candle_range in zip(hfm_median_spreads, hfm_ranges)
        if spread is not None and candle_range > 0
    ]
    labels = ("open", "high", "low", "close")
    ohlc_differences = {
        label: _summary(right[key][index] - left[key][index] for key in common)
        for index, label in enumerate(labels)
    }
    agreements = 0
    comparable = 0
    for key in common:
        left_direction = (left[key][3] > left[key][0]) - (left[key][3] < left[key][0])
        right_direction = (right[key][3] > right[key][0]) - (right[key][3] < right[key][0])
        if left_direction and right_direction:
            comparable += 1
            agreements += left_direction == right_direction
    return {
        "minutes": minutes,
        "common_candles": len(common),
        "hfm_candle_range_usd": _summary(hfm_ranges),
        "hfm_median_spread_usd_by_candle": _summary(
            spread for spread in hfm_median_spreads if spread is not None
        ),
        "hfm_spread_to_candle_range_pct": _summary(spread_to_range),
        "ohlc_difference_usd": ohlc_differences,
        "direction_comparable": comparable,
        "direction_agreement_pct": agreements / comparable * 100.0 if comparable else None,
    }


def _pearson(values_x: list[float], values_y: list[float]) -> float | None:
    if len(values_x) != len(values_y) or len(values_x) < 2:
        return None
    mean_x, mean_y = fmean(values_x), fmean(values_y)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(values_x, values_y))
    denominator = math.sqrt(
        sum((x - mean_x) ** 2 for x in values_x)
        * sum((y - mean_y) ** 2 for y in values_y)
    )
    return numerator / denominator if denominator else None


def _return_correlation(binance: list[Quote], hfm: list[Quote]) -> dict:
    """Pearson correlation of one-second last-mid returns on common buckets."""
    second_ns = 1_000_000_000
    by_source: list[dict[int, float]] = []
    for source_quotes in (binance, hfm):
        buckets: dict[int, float] = {}
        for quote in source_quotes:
            buckets[quote.local_received_ns // second_ns] = quote.mid
        by_source.append(buckets)
    common = sorted(set(by_source[0]) & set(by_source[1]))
    if len(common) < 2:
        return {"common_seconds": len(common), "return_pairs": 0, "pearson": None}
    left_returns: list[float] = []
    right_returns: list[float] = []
    for previous, current in zip(common, common[1:]):
        if current != previous + 1:
            continue
        left_returns.append(by_source[0][current] / by_source[0][previous] - 1.0)
        right_returns.append(by_source[1][current] / by_source[1][previous] - 1.0)
    return {
        "common_seconds": len(common),
        "return_pairs": len(left_returns),
        "pearson": _pearson(left_returns, right_returns),
    }


def _sequence_audit(quotes: list[Quote]) -> dict:
    sequences = [
        quote.source_sequence
        for quote in quotes
        if quote.source_sequence is not None
    ]
    missing = 0
    resets = 0
    duplicates_or_reversals = 0
    for previous, current in zip(sequences, sequences[1:]):
        if current == previous:
            duplicates_or_reversals += 1
        elif current < previous:
            resets += 1
        elif current > previous + 1:
            missing += current - previous - 1
    return {
        "quotes_with_sequence": len(sequences),
        "first_sequence": sequences[0] if sequences else None,
        "last_sequence": sequences[-1] if sequences else None,
        "missing_sequence_count": missing,
        "sequence_resets": resets,
        "duplicates_or_reversals": duplicates_or_reversals,
    }


def _lead_lag_correlation(
    binance: list[Quote],
    hfm: list[Quote],
    *,
    bucket_ms: int = 250,
    max_lag_ms: int = 5_000,
) -> dict:
    """Cross-correlate bucketed mid returns over positive and negative lags.

    Positive best_lag_ms means an HFM return best matches an earlier Binance
    return, i.e. HFM followed Binance. Negative means HFM led Binance.
    """
    bucket_ns = bucket_ms * 1_000_000

    def returns(quotes: list[Quote]) -> dict[int, float]:
        mids: dict[int, float] = {}
        for quote in quotes:
            mids[quote.local_received_ns // bucket_ns] = quote.mid
        result: dict[int, float] = {}
        for previous, current in zip(sorted(mids), sorted(mids)[1:]):
            if current == previous + 1 and mids[previous] > 0:
                result[current] = mids[current] / mids[previous] - 1.0
        return result

    left = returns(binance)
    right = returns(hfm)
    max_steps = max_lag_ms // bucket_ms
    rows: list[dict] = []
    for lag_steps in range(-max_steps, max_steps + 1):
        xs: list[float] = []
        ys: list[float] = []
        for bucket, value in left.items():
            other = right.get(bucket + lag_steps)
            if other is not None:
                xs.append(value)
                ys.append(other)
        correlation = _pearson(xs, ys) if len(xs) >= 20 else None
        rows.append(
            {
                "lag_ms": lag_steps * bucket_ms,
                "pairs": len(xs),
                "pearson": correlation,
            }
        )
    valid = [row for row in rows if row["pearson"] is not None]
    best = max(valid, key=lambda row: row["pearson"]) if valid else None
    return {
        "bucket_ms": bucket_ms,
        "searched_lag_ms": [-max_lag_ms, max_lag_ms],
        "best_lag_ms": best["lag_ms"] if best else None,
        "best_pearson": best["pearson"] if best else None,
        "pairs_at_best": best["pairs"] if best else 0,
        "lag_sign": "positive means HFM followed Binance; negative means HFM led",
    }


def _execution_summary(records: list[dict], side: int | None = None) -> dict:
    selected = records if side is None else [record for record in records if record["side"] == side]
    net = [record["net_usd"] for record in selected]
    return {
        "count": len(selected),
        "win_rate_pct": (
            sum(value > 0 for value in net) / len(net) * 100.0 if net else None
        ),
        "net_usd": _summary(net),
        "mfe_usd": _summary(record["mfe_usd"] for record in selected),
        "mae_usd": _summary(record["mae_usd"] for record in selected),
    }


def _execution_after_binance_moves(
    binance: list[Quote],
    hfm: list[Quote],
    *,
    threshold_bps: float,
    entry_delay_ms: int,
    horizons_seconds: tuple[int, ...],
    max_quote_gap_ms: int,
) -> dict:
    """Measure executable HFM outcomes after observed Binance price moves.

    An upward Binance move opens a hypothetical LONG at HFM Ask and closes at
    HFM Bid. A downward move opens at HFM Bid and closes at HFM Ask. Therefore
    the reported net result already includes the displayed HFM spread.
    """
    events = _move_events(binance, threshold_bps)
    hfm_times = [quote.local_received_ns for quote in hfm]
    gap_ns = max_quote_gap_ms * 1_000_000
    by_horizon: dict[str, dict] = {}
    for horizon_seconds in horizons_seconds:
        records: list[dict] = []
        horizon_ns = horizon_seconds * 1_000_000_000
        for event_ns, direction in events:
            desired_entry_ns = event_ns + entry_delay_ms * 1_000_000
            entry_index = bisect_left(hfm_times, desired_entry_ns)
            if entry_index >= len(hfm):
                continue
            entry = hfm[entry_index]
            if entry.local_received_ns - desired_entry_ns > gap_ns:
                continue
            desired_exit_ns = entry.local_received_ns + horizon_ns
            exit_index = bisect_left(hfm_times, desired_exit_ns)
            if exit_index >= len(hfm):
                continue
            exit_quote = hfm[exit_index]
            if exit_quote.local_received_ns - desired_exit_ns > gap_ns:
                continue
            interval = hfm[entry_index : exit_index + 1]
            if direction > 0:
                path = [quote.bid - entry.ask for quote in interval]
                net_usd = exit_quote.bid - entry.ask
            else:
                path = [entry.bid - quote.ask for quote in interval]
                net_usd = entry.bid - exit_quote.ask
            records.append(
                {
                    "side": direction,
                    "net_usd": net_usd,
                    "mfe_usd": max(path),
                    "mae_usd": min(path),
                }
            )
        by_horizon[str(horizon_seconds)] = {
            "all": _execution_summary(records),
            "long": _execution_summary(records, 1),
            "short": _execution_summary(records, -1),
        }
    return {
        "trigger": f"Binance mid moved {threshold_bps:g} bps from the prior anchor",
        "entry_delay_ms": entry_delay_ms,
        "entry_and_exit": "LONG Ask->Bid; SHORT Bid->Ask; displayed spread included",
        "max_quote_gap_ms": max_quote_gap_ms,
        "binance_move_events": len(events),
        "horizons_seconds": by_horizon,
        "limitation": "price-move follow-through test, not a Flow-conditioned strategy backtest",
    }


def build_report(
    quotes: list[Quote],
    *,
    move_threshold_bps: float = 1.0,
    match_window_ms: int = 5_000,
    max_staleness_ms: int = 1_000,
    entry_delay_ms: int = 1_000,
    execution_horizons_seconds: tuple[int, ...] = (30, 60, 180, 300),
) -> dict:
    binance = [quote for quote in quotes if quote.source == "BINANCE"]
    hfm = [quote for quote in quotes if quote.source == "HFM"]
    pairs = _aligned(quotes, max_staleness_ms)
    basis = [hfm_quote.mid - binance_quote.mid for binance_quote, hfm_quote in pairs]
    long_cost = [hfm_quote.ask - binance_quote.ask for binance_quote, hfm_quote in pairs]
    short_cost = [hfm_quote.bid - binance_quote.bid for binance_quote, hfm_quote in pairs]
    latencies, event_count = _latencies(
        binance, hfm, move_threshold_bps, match_window_ms
    )
    return {
        "method": {
            "clock": "local_received_ns stamped by the Python observer",
            "move_threshold_bps": move_threshold_bps,
            "match_window_ms": match_window_ms,
            "max_quote_staleness_ms": max_staleness_ms,
            "latency_sign": "positive means HFM followed Binance; negative means HFM moved first",
            "limitation": "quotes are observable prices, not proof of executable fill price",
        },
        "samples": {"binance": len(binance), "hfm": len(hfm), "aligned": len(pairs)},
        "basis_usd": _summary(basis),
        "long_execution_difference_usd": _summary(long_cost),
        "short_execution_difference_usd": _summary(short_cost),
        "binance_spread_usd": _summary(quote.spread for quote in binance),
        "hfm_spread_usd": _summary(quote.spread for quote in hfm),
        "hfm_bridge_sequence": _sequence_audit(hfm),
        "latency_ms": {
            **_summary(latencies),
            "binance_move_events": event_count,
            "match_rate_pct": len(latencies) / event_count * 100.0 if event_count else None,
        },
        "lead_lag_cross_correlation": _lead_lag_correlation(binance, hfm),
        "executable_hfm_outcomes_after_binance_move": _execution_after_binance_moves(
            binance,
            hfm,
            threshold_bps=move_threshold_bps,
            entry_delay_ms=entry_delay_ms,
            horizons_seconds=execution_horizons_seconds,
            max_quote_gap_ms=max_staleness_ms,
        ),
        "one_second_return_correlation": _return_correlation(binance, hfm),
        "candles": [_candle_comparison(binance, hfm, minutes) for minutes in (1, 3, 5)],
    }
