"""Threshold-free producer for detector observations.

This module is deliberately limited to public detector result objects.  It does
not reimplement detector logic or decide any calibrated predicate threshold.
Only complete, directly named Tier A materials and the approved absorption
composite flags are emitted; missing or unsupported observations are omitted.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable

from .condition_adapter import IngestionAdapter
from .market_state import BookLevel, MarketStateSnapshot, TimeSample

_ZERO = Decimal("0")
_ONE = Decimal("1")
_NS_PER_SECOND = 1_000_000_000
_SUPPORTED_TAPE_WINDOWS = (1, 5)
_SUPPORTED_DELTA_WINDOWS = (1, 5, 30, 300)
_WINDOW_LABELS = {1: "1s", 5: "5s", 30: "30s", 300: "5m"}


class SnapshotProducer:
    """Collect public detector outputs and build a normalized market snapshot.

    ``engine_time_ns`` and ``tick_size`` are supplied by the caller.  The
    producer owns no clock and contains no calibration threshold.
    """

    def __init__(self, symbol: str) -> None:
        self._symbol = symbol
        self._cvd_updates: deque[object] = deque()
        self._flow_snapshots: dict[int, object] = {}
        self._absorption_flags: dict[str, Decimal] = {}
        self._book_snapshot: object | None = None
        self._approved_tick_size: Decimal | None = None
        self._imbalance_result: object | None = None

    def observe_cvd(self, update: object, candle: object | None = None) -> None:
        """Observe a public ``CvdUpdate`` and optionally its closed candle."""

        self._require_symbol(update)
        event_time = _required_datetime(update, "event_time")
        if self._cvd_updates and event_time < _required_datetime(
            self._cvd_updates[-1], "event_time"
        ):
            return
        self._cvd_updates.append(update)
        cutoff = event_time - timedelta(seconds=300)
        while self._cvd_updates and _required_datetime(
            self._cvd_updates[0], "event_time"
        ) < cutoff:
            self._cvd_updates.popleft()

    def observe_flow_response(self, snapshot: object) -> None:
        """Observe a public ``FlowResponseSnapshot`` for its declared window."""

        self._require_symbol(snapshot)
        window = _required_int(snapshot, "window_sec")
        if window not in _SUPPORTED_DELTA_WINDOWS:
            return
        self._flow_snapshots[window] = snapshot

    def observe_absorption(self, result: object | None) -> None:
        """Expose the approved detector-result-to-G16 flag mapping.

        ``BUY_ABSORPTION`` means sell aggression was absorbed at the bid;
        ``SELL_ABSORPTION`` means buy aggression was absorbed at the ask.
        Inactive/unknown results are omitted (fail-closed).
        """

        self._absorption_flags.clear()
        if result is None:
            return
        classification = getattr(result, "classification", None)
        if classification == "BUY_ABSORPTION":
            self._absorption_flags["bid_absorption_like_active"] = _ONE
        elif classification == "SELL_ABSORPTION":
            self._absorption_flags["ask_absorption_like_active"] = _ONE

    def observe_book(
        self,
        snapshot: object,
        approved_time: int | None = None,
        approved_tick_size: Decimal | None = None,
    ) -> None:
        """Observe a public ``OrderBookSnapshot`` and approved tick size.

        ``approved_time`` is accepted for call-site symmetry and future
        freshness enforcement; this threshold-free P1 layer does not infer
        freshness from it.
        """

        del approved_time
        self._require_symbol(snapshot)
        if approved_tick_size is not None:
            tick = _decimal(approved_tick_size)
            if tick <= _ZERO:
                raise ValueError("approved_tick_size must be positive")
            self._approved_tick_size = tick
        self._book_snapshot = snapshot

    def observe_imbalance(self, result: object) -> None:
        """Retain a public imbalance result; P1 omits its incompatible 1m keys."""

        self._require_symbol(result)
        self._imbalance_result = result

    def build_market_state(
        self, engine_time_ns: int, tick_size: Decimal | None = None
    ) -> MarketStateSnapshot:
        """Build the existing normalized snapshot without changing its schema."""

        approved_tick = (
            _decimal(tick_size) if tick_size is not None else self._approved_tick_size
        )
        if approved_tick is not None and approved_tick <= _ZERO:
            raise ValueError("tick_size must be positive")

        book_levels = self._book_levels()
        return MarketStateSnapshot(
            engine_time_ns=engine_time_ns,
            cvd_samples=tuple(self._cvd_samples()),
            price_samples=tuple(self._price_samples()),
            bid_levels=book_levels[0],
            ask_levels=book_levels[1],
            tick_size=approved_tick,
            pre_aggregated=self._pre_aggregated(),
        )

    def to_conditions(
        self, engine_time_ns: int, tick_size: Decimal | None = None
    ) -> dict[str, Decimal]:
        """Build the condition dictionary through the existing adapter."""

        return IngestionAdapter().to_conditions(
            self.build_market_state(engine_time_ns, tick_size)
        )

    def _pre_aggregated(self) -> dict[str, Decimal]:
        values = self._cvd_conditions()
        for window, snapshot in self._flow_snapshots.items():
            label = _WINDOW_LABELS[window]
            values[f"trade_delta_{label}"] = _decimal(
                getattr(snapshot, "delta")
            )
        values.update(self._absorption_flags)
        return values

    def _cvd_conditions(self) -> dict[str, Decimal]:
        if not self._cvd_updates:
            return {}
        updates = list(self._cvd_updates)
        latest_time = _required_datetime(updates[-1], "event_time")
        out: dict[str, Decimal] = {}
        for window in _SUPPORTED_DELTA_WINDOWS:
            start = latest_time - timedelta(seconds=window)
            window_updates = [
                item
                for item in updates
                if start <= _required_datetime(item, "event_time") <= latest_time
            ]
            if len(window_updates) < 2:
                continue
            first_time = _required_datetime(window_updates[0], "event_time")
            if latest_time - first_time < timedelta(seconds=window):
                continue
            label = _WINDOW_LABELS[window]
            deltas = [_decimal(getattr(item, "tick_delta")) for item in window_updates]
            out[f"trade_delta_{label}"] = sum(deltas, _ZERO)
            out[f"cvd_change_{label}"] = sum(deltas, _ZERO)
            dt = _seconds(latest_time - first_time)
            if dt > _ZERO:
                first_cvd = _decimal(getattr(window_updates[0], "tick_cvd"))
                last_cvd = _decimal(getattr(window_updates[-1], "tick_cvd"))
                out[f"cvd_slope_{label}"] = (last_cvd - first_cvd) / dt

            if window in _SUPPORTED_TAPE_WINDOWS:
                self._add_tape_conditions(window_updates, label, out)
        return out

    @staticmethod
    def _add_tape_conditions(
        updates: Iterable[object], label: str, out: dict[str, Decimal]
    ) -> None:
        deltas = [_decimal(getattr(item, "tick_delta")) for item in updates]
        buy = [value for value in deltas if value > _ZERO]
        sell = [-value for value in deltas if value < _ZERO]
        total = sum(buy, _ZERO) + sum(sell, _ZERO)
        seconds = Decimal(label[:-1])
        for side, values in (("buy", buy), ("sell", sell)):
            volume = sum(values, _ZERO)
            count = Decimal(len(values))
            out[f"{side}_market_volume_{label}"] = volume
            out[f"{side}_trade_count_{label}"] = count
            if count:
                out[f"{side}_average_trade_size_{label}"] = volume / count
                out[f"{side}_max_trade_size_{label}"] = max(values)
            out[f"{side}_trade_rate_{label}"] = count / seconds
            if total:
                out[f"{side}_side_share_{label}"] = volume / total

    def _cvd_samples(self) -> Iterable[TimeSample]:
        for update in self._cvd_updates:
            yield TimeSample(
                engine_time_ns=_datetime_ns(_required_datetime(update, "event_time")),
                value=_decimal(getattr(update, "tick_cvd")),
            )

    def _price_samples(self) -> Iterable[TimeSample]:
        for snapshot in self._flow_snapshots.values():
            yield TimeSample(
                engine_time_ns=_datetime_ns(_required_datetime(snapshot, "event_time")),
                value=_decimal(getattr(snapshot, "last_price")),
            )

    def _book_levels(self) -> tuple[tuple[BookLevel, ...], tuple[BookLevel, ...]]:
        if self._book_snapshot is None:
            return (), ()
        bids = getattr(self._book_snapshot, "bids", {})
        asks = getattr(self._book_snapshot, "asks", {})
        bid_levels = tuple(
            BookLevel(price=_decimal(price), quantity=_decimal(quantity))
            for price, quantity in sorted(bids.items(), reverse=True)
            if _decimal(quantity) > _ZERO
        )
        ask_levels = tuple(
            BookLevel(price=_decimal(price), quantity=_decimal(quantity))
            for price, quantity in sorted(asks.items())
            if _decimal(quantity) > _ZERO
        )
        return bid_levels, ask_levels

    def _require_symbol(self, value: object) -> None:
        symbol = getattr(value, "symbol", None)
        if symbol != self._symbol:
            raise ValueError(f"observation symbol mismatch: {symbol!r}")


def _decimal(value: object) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _required_datetime(value: object, name: str) -> datetime:
    result = getattr(value, name, None)
    if not isinstance(result, datetime):
        raise TypeError(f"{name} must be datetime")
    return result


def _required_int(value: object, name: str) -> int:
    result = getattr(value, name, None)
    if not isinstance(result, int):
        raise TypeError(f"{name} must be int")
    return result


def _seconds(delta: timedelta) -> Decimal:
    return Decimal(delta.days * 86400 + delta.seconds) + (
        Decimal(delta.microseconds) / Decimal(1_000_000)
    )


def _datetime_ns(value: datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    delta = value.astimezone(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (
        delta.days * 86400 * _NS_PER_SECOND
        + delta.seconds * _NS_PER_SECOND
        + delta.microseconds * 1000
    )
