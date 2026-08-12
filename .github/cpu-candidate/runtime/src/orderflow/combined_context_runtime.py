"""Runtime accumulation for PRICE/CVD/Delta/OI and executable HFM outcomes."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from .combined_context import CombinedContext, classify_candles, combine_pattern_with_oi


_TIMEFRAME_SECONDS = {"5m": 300, "10m": 600}
_BPS = Decimal("10000")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class HfmQuote:
    symbol: str
    source_time: datetime | None
    received_time: datetime
    sequence: int | None
    bid: Decimal
    ask: Decimal

    def __post_init__(self) -> None:
        source_time = _utc(self.source_time) if self.source_time is not None else None
        received_time = _utc(self.received_time)
        bid = self.bid if isinstance(self.bid, Decimal) else Decimal(str(self.bid))
        ask = self.ask if isinstance(self.ask, Decimal) else Decimal(str(self.ask))
        if not bid.is_finite() or not ask.is_finite() or bid <= 0 or ask < bid:
            raise ValueError("HFM quote requires finite positive bid and ask >= bid")
        object.__setattr__(self, "source_time", source_time)
        object.__setattr__(self, "received_time", received_time)
        object.__setattr__(self, "bid", bid)
        object.__setattr__(self, "ask", ask)

    @property
    def spread(self) -> Decimal:
        return self.ask - self.bid


@dataclass(frozen=True)
class CombinedContextEvent:
    event_time: datetime
    bar_time: datetime
    symbol: str
    timeframe: str
    context: CombinedContext
    oi_open: Decimal | None
    oi_close: Decimal | None
    oi_change: Decimal | None
    oi_change_pct: Decimal | None
    oi_sample_count: int
    hfm_entry_status: str
    hfm_entry: HfmQuote | None
    hfm_entry_age_ms: int | None


@dataclass(frozen=True)
class HfmContextOutcome:
    event_time: datetime
    symbol: str
    timeframe: str
    context_code: str
    horizon_sec: int
    status: str
    hfm_symbol: str
    entry_time: datetime
    entry_source_time: datetime | None
    entry_bid: Decimal
    entry_ask: Decimal
    outcome_time: datetime
    outcome_source_time: datetime | None
    outcome_bid: Decimal
    outcome_ask: Decimal
    quote_lag_ms: int
    long_net_usd: Decimal
    short_net_usd: Decimal
    long_return_bps: Decimal
    short_return_bps: Decimal
    long_mfe_usd: Decimal
    long_mae_usd: Decimal
    short_mfe_usd: Decimal
    short_mae_usd: Decimal


@dataclass
class _PendingOutcome:
    event: CombinedContextEvent
    entry: HfmQuote
    horizon_sec: int
    target_time: datetime
    long_mfe_usd: Decimal
    long_mae_usd: Decimal
    short_mfe_usd: Decimal
    short_mae_usd: Decimal

    def observe(self, quote: HfmQuote) -> None:
        long_value = quote.bid - self.entry.ask
        short_value = self.entry.bid - quote.ask
        self.long_mfe_usd = max(self.long_mfe_usd, long_value)
        self.long_mae_usd = min(self.long_mae_usd, long_value)
        self.short_mfe_usd = max(self.short_mfe_usd, short_value)
        self.short_mae_usd = min(self.short_mae_usd, short_value)


@dataclass
class CombinedContextObserver:
    """Accumulate native bars and aligned OI; evaluate both HFM sides later."""

    symbol: str
    horizons_sec: tuple[int, ...] = (180, 300, 600)
    oi_max_age_sec: int = 20
    hfm_entry_max_age_ms: int = 2_000
    hfm_outcome_max_lag_ms: int = 2_000
    _candles: dict[str, list[Any]] = field(
        default_factory=lambda: {timeframe: [] for timeframe in _TIMEFRAME_SECONDS},
        init=False,
    )
    _oi_samples: list[dict] = field(default_factory=list, init=False)
    _latest_hfm: HfmQuote | None = field(default=None, init=False)
    _pending: list[_PendingOutcome] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        horizons = tuple(sorted(set(int(value) for value in self.horizons_sec)))
        if not horizons or any(value <= 0 for value in horizons):
            raise ValueError("horizons_sec must contain positive values")
        self.horizons_sec = horizons
        self.symbol = self.symbol.upper()

    @property
    def latest_hfm(self) -> HfmQuote | None:
        return self._latest_hfm

    @property
    def pending_outcomes(self) -> int:
        return len(self._pending)

    def observe_oi_sample(self, sample: dict) -> None:
        symbol = str(sample["symbol"]).upper()
        if symbol != self.symbol:
            raise ValueError(f"OI symbol mismatch: expected {self.symbol}, got {symbol}")
        source_time = _utc(sample["source_time"])
        value = sample["open_interest"]
        value = value if isinstance(value, Decimal) else Decimal(str(value))
        if not value.is_finite() or value <= 0:
            raise ValueError("OI value must be finite and positive")
        normalized = {"source_time": source_time, "open_interest": value}
        for index, current in enumerate(self._oi_samples):
            if current["source_time"] == source_time:
                self._oi_samples[index] = normalized
                break
        else:
            self._oi_samples.append(normalized)
        self._oi_samples.sort(key=lambda row: row["source_time"])
        if len(self._oi_samples) > 10_000:
            del self._oi_samples[:-10_000]

    def _oi_as_of(self, target: datetime) -> dict | None:
        max_age = timedelta(seconds=self.oi_max_age_sec)
        for sample in reversed(self._oi_samples):
            if sample["source_time"] <= target:
                return sample if target - sample["source_time"] <= max_age else None
        return None

    def register_candle(
        self,
        candle: Any,
        *,
        decision_time: datetime | None = None,
    ) -> CombinedContextEvent | None:
        """Register one genuinely closed native candle.

        The first two bars only establish history. Each later bar compares with
        two bars earlier, exactly like the existing UI eight-pattern rule.
        """
        timeframe = str(candle.timeframe)
        if timeframe not in _TIMEFRAME_SECONDS:
            return None
        bars = self._candles[timeframe]
        if bars and bars[-1].bar_time == candle.bar_time:
            return None
        bars.append(candle)
        if len(bars) > 3:
            del bars[:-3]
        if len(bars) < 3:
            return None

        pattern = classify_candles(candle, bars[-3])
        bar_time = _utc(candle.bar_time)
        event_time = bar_time + timedelta(seconds=_TIMEFRAME_SECONDS[timeframe])
        close_target = event_time - timedelta(microseconds=1)
        oi_open_sample = self._oi_as_of(bar_time)
        oi_close_sample = self._oi_as_of(close_target)
        oi_open = oi_open_sample["open_interest"] if oi_open_sample is not None else None
        oi_close = oi_close_sample["open_interest"] if oi_close_sample is not None else None
        oi_change = (
            oi_close - oi_open
            if oi_open is not None and oi_close is not None
            and oi_close_sample["source_time"] >= oi_open_sample["source_time"]
            else None
        )
        oi_change_pct = (
            oi_change / oi_open * Decimal("100")
            if oi_change is not None and oi_open is not None and oi_open > 0
            else None
        )
        oi_sample_count = sum(
            bar_time <= row["source_time"] < event_time for row in self._oi_samples
        )
        context = combine_pattern_with_oi(pattern, oi_change)

        decided = _utc(decision_time or datetime.now(timezone.utc))
        entry = self._latest_hfm
        entry_age_ms = None
        entry_status = "MISSING"
        if entry is not None:
            entry_age_ms = int((decided - entry.received_time).total_seconds() * 1000)
            if 0 <= entry_age_ms <= self.hfm_entry_max_age_ms:
                entry_status = "LIVE"
            else:
                entry_status = "STALE"
                entry = None

        event = CombinedContextEvent(
            event_time=event_time,
            bar_time=bar_time,
            symbol=self.symbol,
            timeframe=timeframe,
            context=context,
            oi_open=oi_open,
            oi_close=oi_close,
            oi_change=oi_change,
            oi_change_pct=oi_change_pct,
            oi_sample_count=oi_sample_count,
            hfm_entry_status=entry_status,
            hfm_entry=entry,
            hfm_entry_age_ms=entry_age_ms,
        )
        if entry is not None:
            immediate = entry.bid - entry.ask
            for horizon in self.horizons_sec:
                self._pending.append(_PendingOutcome(
                    event=event,
                    entry=entry,
                    horizon_sec=horizon,
                    target_time=entry.received_time + timedelta(seconds=horizon),
                    long_mfe_usd=immediate,
                    long_mae_usd=immediate,
                    short_mfe_usd=immediate,
                    short_mae_usd=immediate,
                ))
        return event

    def observe_hfm_quote(self, quote: HfmQuote) -> tuple[HfmContextOutcome, ...]:
        self._latest_hfm = quote
        outcomes: list[HfmContextOutcome] = []
        remaining: list[_PendingOutcome] = []
        for pending in self._pending:
            if quote.received_time < pending.entry.received_time:
                remaining.append(pending)
                continue
            pending.observe(quote)
            if quote.received_time < pending.target_time:
                remaining.append(pending)
                continue
            lag_ms = int((quote.received_time - pending.target_time).total_seconds() * 1000)
            long_net = quote.bid - pending.entry.ask
            short_net = pending.entry.bid - quote.ask
            outcomes.append(HfmContextOutcome(
                event_time=pending.event.event_time,
                symbol=pending.event.symbol,
                timeframe=pending.event.timeframe,
                context_code=pending.event.context.code,
                horizon_sec=pending.horizon_sec,
                status="OK" if lag_ms <= self.hfm_outcome_max_lag_ms else "QUOTE_GAP",
                hfm_symbol=quote.symbol,
                entry_time=pending.entry.received_time,
                entry_source_time=pending.entry.source_time,
                entry_bid=pending.entry.bid,
                entry_ask=pending.entry.ask,
                outcome_time=quote.received_time,
                outcome_source_time=quote.source_time,
                outcome_bid=quote.bid,
                outcome_ask=quote.ask,
                quote_lag_ms=lag_ms,
                long_net_usd=long_net,
                short_net_usd=short_net,
                long_return_bps=long_net / pending.entry.ask * _BPS,
                short_return_bps=short_net / pending.entry.bid * _BPS,
                long_mfe_usd=pending.long_mfe_usd,
                long_mae_usd=pending.long_mae_usd,
                short_mfe_usd=pending.short_mfe_usd,
                short_mae_usd=pending.short_mae_usd,
            ))
        self._pending = remaining
        return tuple(outcomes)
