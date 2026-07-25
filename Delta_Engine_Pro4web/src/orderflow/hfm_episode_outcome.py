"""Causal HFM Bid/Ask outcome evaluation for a local-clock signal.

The caller must provide a signal time stamped on the same local clock as the
quotes. Binance exchange event time is intentionally not treated as that
clock; silently converting it would create lookahead and false latency data.
"""

from __future__ import annotations

import csv
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class HfmQuoteObservation:
    symbol: str
    received_time: datetime
    bid: float
    ask: float
    source_time: datetime | None = None
    sequence: int | None = None

    def __post_init__(self) -> None:
        if self.received_time.tzinfo is None:
            raise ValueError("received_time must be timezone-aware")
        if self.bid <= 0 or self.ask < self.bid:
            raise ValueError("HFM quote requires positive bid and ask >= bid")

    @property
    def spread(self) -> float:
        return self.ask - self.bid


@dataclass(frozen=True)
class HfmEpisodeOutcome:
    status: str
    horizon_sec: int
    entry_time: datetime | None
    outcome_time: datetime | None
    entry_bid: float | None
    entry_ask: float | None
    outcome_bid: float | None
    outcome_ask: float | None
    quote_lag_ms: int | None
    long_net_move: float | None
    short_net_move: float | None
    long_mfe: float | None
    long_mae: float | None
    short_mfe: float | None
    short_mae: float | None


def parse_hfm_csv(path: Path, *, symbol: str | None = None) -> tuple[HfmQuoteObservation, ...]:
    """Read historical quote rows without modifying the source file."""
    rows: list[HfmQuoteObservation] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if symbol is not None and row.get("symbol") != symbol:
                continue
            try:
                received = datetime.fromtimestamp(
                    int(row["local_received_ns"]) / 1_000_000_000, tz=timezone.utc
                )
                source = datetime.fromtimestamp(
                    int(row["exchange_time_ms"]) / 1_000, tz=timezone.utc
                )
                sequence = int(row["source_sequence"]) if row.get("source_sequence") else None
                quote = HfmQuoteObservation(
                    symbol=str(row["symbol"]),
                    received_time=received,
                    source_time=source,
                    sequence=sequence,
                    bid=float(row["bid"]),
                    ask=float(row["ask"]),
                )
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
            rows.append(quote)
    return tuple(sorted(rows, key=lambda quote: quote.received_time))


class HfmEpisodeOutcomeEvaluator:
    """Evaluate executable long/short paths after a local-clock entry."""

    def __init__(
        self,
        horizons_sec: Iterable[int] = (300, 600),
        *,
        max_entry_age_ms: int = 2_000,
        max_outcome_lag_ms: int = 2_000,
        max_quote_gap_sec: int = 10,
    ) -> None:
        self.horizons_sec = tuple(sorted(set(int(value) for value in horizons_sec)))
        if not self.horizons_sec or any(value < 1 for value in self.horizons_sec):
            raise ValueError("horizons_sec must contain positive values")
        if min(max_entry_age_ms, max_outcome_lag_ms) < 0 or max_quote_gap_sec < 1:
            raise ValueError("quote limits must be valid")
        self.max_entry_age_ms = max_entry_age_ms
        self.max_outcome_lag_ms = max_outcome_lag_ms
        self.max_quote_gap_sec = max_quote_gap_sec

    @staticmethod
    def _ordered(quotes: Iterable[HfmQuoteObservation]) -> list[HfmQuoteObservation]:
        ordered = list(quotes)
        if any(right.received_time < left.received_time for left, right in zip(ordered, ordered[1:])):
            raise ValueError("quotes must be chronological")
        return ordered

    def evaluate(
        self,
        quotes: Iterable[HfmQuoteObservation],
        *,
        signal_received_time: datetime,
    ) -> tuple[HfmEpisodeOutcome, ...]:
        if signal_received_time.tzinfo is None:
            raise ValueError("signal_received_time must be timezone-aware")
        ordered = self._ordered(quotes)
        times = [quote.received_time for quote in ordered]
        entry_index = bisect_right(times, signal_received_time) - 1
        entry = ordered[entry_index] if entry_index >= 0 else None
        if entry is None:
            return tuple(self._missing(horizon, "ENTRY_MISSING") for horizon in self.horizons_sec)
        entry_age_ms = int((signal_received_time - entry.received_time).total_seconds() * 1000)
        if entry_age_ms > self.max_entry_age_ms:
            return tuple(self._missing(horizon, "ENTRY_STALE") for horizon in self.horizons_sec)
        results: list[HfmEpisodeOutcome] = []
        for horizon in self.horizons_sec:
            target = entry.received_time + timedelta(seconds=horizon)
            outcome_index = bisect_left(times, target)
            if outcome_index >= len(ordered):
                results.append(self._missing(horizon, "OUTCOME_MISSING", entry))
                continue
            outcome = ordered[outcome_index]
            lag_ms = int((outcome.received_time - target).total_seconds() * 1000)
            path = ordered[entry_index : outcome_index + 1]
            gaps = [
                (right.received_time - left.received_time).total_seconds()
                for left, right in zip(path, path[1:])
            ]
            if lag_ms > self.max_outcome_lag_ms or any(gap > self.max_quote_gap_sec for gap in gaps):
                results.append(self._missing(horizon, "QUOTE_GAP", entry, outcome, lag_ms))
                continue
            long_values = [quote.bid - entry.ask for quote in path]
            short_values = [entry.bid - quote.ask for quote in path]
            results.append(HfmEpisodeOutcome(
                "OK", horizon, entry.received_time, outcome.received_time,
                entry.bid, entry.ask, outcome.bid, outcome.ask, lag_ms,
                outcome.bid - entry.ask, entry.bid - outcome.ask,
                max(long_values), min(long_values), max(short_values), min(short_values),
            ))
        return tuple(results)

    @staticmethod
    def _missing(
        horizon: int,
        status: str,
        entry: HfmQuoteObservation | None = None,
        outcome: HfmQuoteObservation | None = None,
        lag_ms: int | None = None,
    ) -> HfmEpisodeOutcome:
        return HfmEpisodeOutcome(
            status, horizon,
            entry.received_time if entry else None,
            outcome.received_time if outcome else None,
            entry.bid if entry else None, entry.ask if entry else None,
            outcome.bid if outcome else None, outcome.ask if outcome else None,
            lag_ms, None, None, None, None, None, None,
        )
