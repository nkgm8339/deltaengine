"""Summarize a multi-venue execution-cost observation CSV.

The report compares each venue's own executable Bid/Ask spread in basis points.
JPY and USD price levels are never subtracted directly.  JPY venues use an
implied JPY-per-USDT ratio versus Binance only to measure basis drift.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml


@dataclass
class MetricSample:
    limit: int = 500_000
    seed: int = 17
    count: int = 0
    total: float = 0.0
    minimum: float | None = None
    maximum: float | None = None
    values: list[float] = field(default_factory=list)
    _random: random.Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._random = random.Random(self.seed)

    def add(self, value: float) -> None:
        if not math.isfinite(value):
            return
        self.count += 1
        self.total += value
        self.minimum = value if self.minimum is None else min(self.minimum, value)
        self.maximum = value if self.maximum is None else max(self.maximum, value)
        if len(self.values) < self.limit:
            self.values.append(value)
            return
        replacement = self._random.randrange(self.count)
        if replacement < self.limit:
            self.values[replacement] = value

    def summary(self) -> dict[str, float | int | None]:
        ordered = sorted(self.values)
        return {
            "count": self.count,
            "mean": self.total / self.count if self.count else None,
            "min": self.minimum,
            "p50": _percentile(ordered, 0.50),
            "p95": _percentile(ordered, 0.95),
            "p99": _percentile(ordered, 0.99),
            "max": self.maximum,
            "quantile_sample_size": len(ordered),
        }


@dataclass
class SourceStats:
    quote_currencies: set[str] = field(default_factory=set)
    instruments: set[str] = field(default_factory=set)
    spread_bps: MetricSample = field(default_factory=MetricSample)
    receive_gap_ms: MetricSample = field(default_factory=lambda: MetricSample(seed=23))
    first_ns: int | None = None
    last_ns: int | None = None
    previous_ns: int | None = None
    per_second_mid: dict[int, float] = field(default_factory=dict)

    def add(self, instrument: str, currency: str, received_ns: int, bid: float, ask: float) -> None:
        mid = (bid + ask) / 2.0
        self.instruments.add(instrument)
        self.quote_currencies.add(currency)
        self.spread_bps.add((ask - bid) / mid * 10_000.0)
        self.first_ns = received_ns if self.first_ns is None else min(self.first_ns, received_ns)
        self.last_ns = received_ns if self.last_ns is None else max(self.last_ns, received_ns)
        if self.previous_ns is not None and received_ns >= self.previous_ns:
            self.receive_gap_ms.add((received_ns - self.previous_ns) / 1_000_000.0)
        self.previous_ns = received_ns
        self.per_second_mid[received_ns // 1_000_000_000] = mid


def _percentile(ordered: list[float], fraction: float) -> float | None:
    if not ordered:
        return None
    position = fraction * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) < 3 or len(left) != len(right):
        return None
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    left_scale = sum((x - left_mean) ** 2 for x in left)
    right_scale = sum((y - right_mean) ** 2 for y in right)
    denominator = math.sqrt(left_scale * right_scale)
    return numerator / denominator if denominator else None


def _paired_report(binance: SourceStats, venue: SourceStats) -> dict[str, Any]:
    common = sorted(set(binance.per_second_mid) & set(venue.per_second_mid))
    ratio = MetricSample(limit=200_000, seed=31)
    left_returns: list[float] = []
    right_returns: list[float] = []
    previous: tuple[int, float, float] | None = None
    for second in common:
        left_mid = binance.per_second_mid[second]
        right_mid = venue.per_second_mid[second]
        ratio.add(right_mid / left_mid)
        if previous is not None and second - previous[0] <= 2:
            left_returns.append((left_mid / previous[1] - 1.0) * 10_000.0)
            right_returns.append((right_mid / previous[2] - 1.0) * 10_000.0)
        previous = (second, left_mid, right_mid)
    currency = next(iter(venue.quote_currencies), None)
    ratio_summary = ratio.summary()
    if currency in {"USD", "USDT"}:
        basis = {
            key: ((value - 1.0) * 10_000.0 if isinstance(value, float) else value)
            for key, value in ratio_summary.items()
        }
        basis_name = "venue_minus_binance_basis_bps"
    else:
        basis = ratio_summary
        basis_name = "implied_jpy_per_usdt"
    return {
        "aligned_one_second_buckets": len(common),
        basis_name: basis,
        "one_second_return_correlation": _pearson(left_returns, right_returns),
        "return_pairs": len(left_returns),
    }


def _load_cost_config(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("execution cost config must be a mapping")
    return payload


def build_report(csv_path: Path, config_path: Path) -> dict[str, Any]:
    sources: dict[str, SourceStats] = {}
    invalid_rows = 0
    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {
            "source", "instrument", "quote_currency", "local_received_ns", "bid", "ask"
        }
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(f"unsupported execution-cost CSV header: {reader.fieldnames!r}")
        for row in reader:
            try:
                source = row["source"].strip().upper()
                currency = row["quote_currency"].strip().upper()
                received_ns = int(row["local_received_ns"])
                bid, ask = float(row["bid"]), float(row["ask"])
                if not source or not currency or bid <= 0 or ask < bid:
                    raise ValueError
                sources.setdefault(source, SourceStats()).add(
                    row["instrument"].strip(), currency, received_ns, bid, ask
                )
            except (KeyError, TypeError, ValueError):
                invalid_rows += 1

    config = _load_cost_config(config_path)
    venue_config = config.get("venues") or {}
    result_sources: dict[str, Any] = {}
    for source, stats in sorted(sources.items()):
        spread = stats.spread_bps.summary()
        source_config = venue_config.get(source) or {}
        fixed_cost = source_config.get("fixed_roundtrip_fee_bps")
        immediate = None
        if isinstance(fixed_cost, (int, float)) and isinstance(spread["p50"], float):
            immediate = spread["p50"] + float(fixed_cost)
        span_hours = (
            (stats.last_ns - stats.first_ns) / 3_600_000_000_000
            if stats.first_ns is not None and stats.last_ns is not None
            else 0.0
        )
        result_sources[source] = {
            "instruments": sorted(stats.instruments),
            "quote_currencies": sorted(stats.quote_currencies),
            "observation_span_hours": span_hours,
            "quotes_per_hour": stats.spread_bps.count / span_hours if span_hours > 0 else None,
            "spread_roundtrip_bps": spread,
            "receive_gap_ms": stats.receive_gap_ms.summary(),
            "fixed_roundtrip_fee_bps": fixed_cost,
            "median_immediate_roundtrip_bps": immediate,
            "holding_cost": source_config.get("holding_cost", "not_configured"),
            "role": source_config.get("role", "not_configured"),
            "reference": source_config.get("reference"),
        }

    comparisons: dict[str, Any] = {}
    binance = sources.get("BINANCE_SENSOR")
    if binance is not None:
        for source, stats in sorted(sources.items()):
            if source != "BINANCE_SENSOR":
                comparisons[source] = _paired_report(binance, stats)

    return {
        "observation_only": True,
        "source_csv": str(csv_path.resolve()),
        "cost_config": str(config_path.resolve()),
        "cost_config_as_of": config.get("as_of"),
        "invalid_rows": invalid_rows,
        "sources": result_sources,
        "versus_binance_sensor": comparisons,
        "decision": config.get("decision") or {},
        "limitations": [
            "Displayed Bid/Ask is not a guaranteed fill and contains no measured slippage.",
            "Holding costs marked not_included must be added for positions crossing their charge time.",
            "JPY and USD prices are not directly subtracted; the JPY/USDT ratio measures combined FX and local-market basis drift.",
            "Quantiles use deterministic reservoir sampling when a metric exceeds 500000 observations.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument(
        "--config", type=Path, default=Path("config/execution_costs.yaml")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("data/execution_costs/report.json")
    )
    args = parser.parse_args(argv)
    report = build_report(args.csv_path, args.config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
