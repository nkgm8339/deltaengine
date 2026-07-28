"""Threshold-free producer for detector observations.

This module is deliberately limited to public detector result objects.  It does
not reimplement detector logic or decide any calibrated predicate threshold.
Only complete, directly named Tier A materials and the approved absorption
composite flags are emitted; missing or unsupported observations are omitted.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable

from .condition_adapter import IngestionAdapter
from .market_state import BookLevel, MarketStateSnapshot, TimeSample
from .session_vwap import SessionVwapAccumulator, SessionVwapSeed

_ZERO = Decimal("0")
_ONE = Decimal("1")
_NS_PER_SECOND = 1_000_000_000
# Retention for the trade-price history. Decided at 600s (2026-07-27):
# covers the current 5m consumers with margin for longer windows.
_PRICE_HISTORY_NS = 600 * _NS_PER_SECOND
_BOOK_HISTORY_NS = 5 * _NS_PER_SECOND
_BOOK_TOP_N = 10
_BOOK_NEAR_BEST_N = 3
_BOOK_WINDOWS = (
    (_NS_PER_SECOND // 10, "100ms"),
    (_NS_PER_SECOND, "1s"),
    (5 * _NS_PER_SECOND, "5s"),
)
_SUPPORTED_TAPE_WINDOWS = (1, 5)
_SUPPORTED_DELTA_WINDOWS = (1, 5, 30, 300)
_WINDOW_LABELS = {1: "1s", 5: "5s", 30: "30s", 300: "5m"}


@dataclass(frozen=True)
class _BookSideState:
    top_prices: frozenset[Decimal]
    top_depth: Decimal


@dataclass(frozen=True)
class _BookStateSample:
    source_time_ns: int
    snapshot: object
    bid: _BookSideState
    ask: _BookSideState


@dataclass(frozen=True)
class _BookSideEvent:
    add_volume: Decimal
    cancel_volume: Decimal
    refresh_count: int
    changed_prices: frozenset[Decimal]


@dataclass(frozen=True)
class _BookEventSample:
    source_time_ns: int
    bid: _BookSideEvent
    ask: _BookSideEvent


class SnapshotProducer:
    """Collect public detector outputs and build a normalized market snapshot.

    ``engine_time_ns`` and ``tick_size`` are supplied by the caller.  The
    producer owns no clock and contains no calibration threshold.
    """

    def __init__(self, symbol: str) -> None:
        self._symbol = symbol
        self._cvd_updates: deque[object] = deque()
        self._price_history: deque[TimeSample] = deque()
        self._session_vwap = SessionVwapAccumulator(symbol)
        self._flow_snapshots: dict[int, object] = {}
        self._absorption_flags: dict[str, Decimal] = {}
        self._book_snapshot: object | None = None
        self._book_states: deque[_BookStateSample] = deque()
        self._book_events: deque[_BookEventSample] = deque()
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

    def seed_session_vwap(self, seed: SessionVwapSeed) -> int:
        """Restore the latest persisted UTC-session aggregate before live input."""

        return self._session_vwap.seed(seed)

    def observe_trade(self, trade: object) -> None:
        """Retain accepted trade prices and exact UTC-session VWAP material."""

        self._require_symbol(trade)
        event_time_ns = _datetime_ns(_required_datetime(trade, "event_time"))
        price = _decimal(getattr(trade, "price"))
        quantity = _decimal(getattr(trade, "quantity"))
        if not price.is_finite() or price <= _ZERO:
            raise ValueError("trade price must be finite and positive")
        if not quantity.is_finite() or quantity <= _ZERO:
            raise ValueError("trade quantity must be finite and positive")
        if (
            self._price_history
            and event_time_ns < self._price_history[-1].engine_time_ns
        ):
            return
        if not self._session_vwap.observe_trade(trade):
            return
        self._price_history.append(
            TimeSample(engine_time_ns=event_time_ns, value=price)
        )

        cutoff_ns = event_time_ns - _PRICE_HISTORY_NS
        # Preserve one as-of predecessor at/before the 5m boundary.
        while (
            len(self._price_history) > 1
            and self._price_history[1].engine_time_ns <= cutoff_ns
        ):
            self._price_history.popleft()

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

        This compatibility entrypoint accepts a point-in-time snapshot. Event
        flow is produced only by :meth:`observe_book_update`, which also has the
        applied update and reset lineage.
        """

        self._require_symbol(snapshot)
        self._set_approved_tick_size(approved_tick_size)
        self._book_snapshot = snapshot
        if approved_time is not None:
            if not isinstance(approved_time, int):
                raise TypeError("approved_time must be source epoch nanoseconds")
            self._reset_book_history(clear_snapshot=False)
            self._book_states.append(self._book_state(snapshot, approved_time))

    def observe_book_update(
        self,
        update: object,
        apply_result: object,
        snapshot: object | None,
        approved_tick_size: Decimal | None = None,
    ) -> None:
        """Observe one applied depth update with gap/resync lineage."""

        self._require_symbol(update)
        if snapshot is not None:
            self._require_symbol(snapshot)
        self._set_approved_tick_size(approved_tick_size)
        event_time_ns = _datetime_ns(_required_datetime(update, "event_time"))

        if bool(getattr(apply_result, "gap_detected", False)):
            self._reset_book_history(clear_snapshot=True)
            return
        if not bool(getattr(apply_result, "applied", False)):
            return
        if self._book_states and event_time_ns < self._book_states[-1].source_time_ns:
            return

        update_type = getattr(update, "update_type", None)
        if update_type == "SNAPSHOT" or bool(
            getattr(apply_result, "reinitialized", False)
        ):
            self._reset_book_history(clear_snapshot=True)
            if snapshot is not None:
                self._book_snapshot = snapshot
                self._book_states.append(self._book_state(snapshot, event_time_ns))
            return
        if update_type != "DIFF":
            raise ValueError(f"unsupported book update_type: {update_type!r}")
        if snapshot is None:
            self._reset_book_history(clear_snapshot=True)
            return

        previous = self._book_snapshot
        if previous is None:
            # The resync supervisor may apply its snapshot outside this producer.
            # Seed a fresh baseline from the first valid post-resync DIFF.
            self._reset_book_history(clear_snapshot=True)
            self._book_snapshot = snapshot
            self._book_states.append(self._book_state(snapshot, event_time_ns))
            return

        self._book_events.append(
            self._book_event(update, previous, snapshot, event_time_ns)
        )
        self._book_snapshot = snapshot
        self._book_states.append(self._book_state(snapshot, event_time_ns))
        self._prune_book_history(event_time_ns)

    def observe_imbalance(self, result: object) -> None:
        """Retain a public imbalance result; P1 omits its incompatible 1m keys."""

        self._require_symbol(result)
        self._imbalance_result = result

    def build_market_state(
        self, engine_time_ns: int, tick_size: Decimal | None = None, source_time_ns: int | None = None
    ) -> MarketStateSnapshot:
        """Build the existing normalized snapshot without changing its schema."""

        approved_tick = (
            _decimal(tick_size) if tick_size is not None else self._approved_tick_size
        )
        if approved_tick is not None and approved_tick <= _ZERO:
            raise ValueError("tick_size must be positive")

        observation_time_ns = (
            source_time_ns if source_time_ns is not None else engine_time_ns
        )
        book_levels = self._book_levels(observation_time_ns)
        session_vwap = self._session_vwap.value_at(observation_time_ns)
        return MarketStateSnapshot(
            engine_time_ns=engine_time_ns,
            source_time_ns=source_time_ns,
            cvd_samples=tuple(self._cvd_samples()),
            price_samples=tuple(self._price_samples(observation_time_ns)),
            bid_levels=book_levels[0],
            ask_levels=book_levels[1],
            tick_size=approved_tick,
            session_vwap=session_vwap,
            session_open_avwap=session_vwap,
            pre_aggregated=self._pre_aggregated(observation_time_ns),
        )

    def to_conditions(
        self, engine_time_ns: int, tick_size: Decimal | None = None, source_time_ns: int | None = None
    ) -> dict[str, Decimal]:
        """Build the condition dictionary through the existing adapter."""

        return IngestionAdapter().to_conditions(
            self.build_market_state(engine_time_ns, tick_size, source_time_ns)
        )

    def _pre_aggregated(self, source_time_ns: int | None) -> dict[str, Decimal]:
        values = self._cvd_conditions(source_time_ns)
        for window, snapshot in self._flow_snapshots.items():
            snapshot_time = _datetime_ns(_required_datetime(snapshot, "event_time"))
            if source_time_ns is not None and snapshot_time > source_time_ns:
                continue
            label = _WINDOW_LABELS[window]
            values.setdefault(f"trade_delta_{label}", _decimal(
                getattr(snapshot, "delta")
            ))
        values.update(self._absorption_flags)
        values.update(self._book_event_conditions(source_time_ns))
        return values

    def _cvd_conditions(self, source_time_ns: int | None) -> dict[str, Decimal]:
        if not self._cvd_updates:
            return {}
        updates = [
            item for item in self._cvd_updates
            if source_time_ns is None or _datetime_ns(_required_datetime(item, "event_time")) <= source_time_ns
        ]
        if not updates:
            return {}
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

    def _price_samples(self, source_time_ns: int) -> Iterable[TimeSample]:
        for sample in self._price_history:
            if sample.engine_time_ns <= source_time_ns:
                yield sample

    def _book_levels(
        self, source_time_ns: int
    ) -> tuple[tuple[BookLevel, ...], tuple[BookLevel, ...]]:
        snapshot = self._book_snapshot
        historical = _latest_book_state_at(self._book_states, source_time_ns)
        if historical is not None:
            snapshot = historical.snapshot
        elif self._book_states:
            snapshot = None
        if snapshot is None:
            return (), ()
        bids = getattr(snapshot, "bids", {})
        asks = getattr(snapshot, "asks", {})
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

    def _book_event_conditions(self, source_time_ns: int | None) -> dict[str, Decimal]:
        if source_time_ns is None:
            return {}
        states = [
            state
            for state in self._book_states
            if state.source_time_ns <= source_time_ns
        ]
        if not states:
            return {}
        current = states[-1]
        out: dict[str, Decimal] = {}
        for window_ns, label in _BOOK_WINDOWS:
            start_ns = source_time_ns - window_ns
            baseline = _latest_book_state_at(states, start_ns)
            if baseline is None or current.source_time_ns <= start_ns:
                continue
            events = [
                event
                for event in self._book_events
                if start_ns < event.source_time_ns <= source_time_ns
            ]
            for side in ("bid", "ask"):
                side_events = [getattr(event, side) for event in events]
                add_volume = sum(
                    (event.add_volume for event in side_events), _ZERO
                )
                cancel_volume = sum(
                    (event.cancel_volume for event in side_events), _ZERO
                )
                total_change = add_volume + cancel_volume
                out[f"{side}_add_volume_{label}"] = add_volume
                out[f"{side}_cancel_volume_{label}"] = cancel_volume
                out[f"{side}_net_flow_{label}"] = add_volume - cancel_volume
                out[f"{side}_refresh_count_{label}"] = Decimal(
                    sum(event.refresh_count for event in side_events)
                )
                if total_change > _ZERO:
                    out[f"{side}_pull_ratio_{label}"] = (
                        cancel_volume / total_change
                    )
                    out[f"{side}_stack_ratio_{label}"] = add_volume / total_change

                changed_prices: set[Decimal] = set()
                for event in side_events:
                    changed_prices.update(event.changed_prices)
                base_side = getattr(baseline, side)
                current_side = getattr(current, side)
                denominator = len(base_side.top_prices | current_side.top_prices)
                if denominator:
                    out[f"{side}_level_turnover_{label}"] = (
                        Decimal(len(changed_prices)) / Decimal(denominator)
                    )
                out[f"{side}_depth_change_{label}"] = (
                    current_side.top_depth - base_side.top_depth
                )
        return out

    @staticmethod
    def _book_event(
        update: object,
        previous: object,
        current: object,
        source_time_ns: int,
    ) -> _BookEventSample:
        return _BookEventSample(
            source_time_ns=source_time_ns,
            bid=_book_side_event(update, previous, current, "bid"),
            ask=_book_side_event(update, previous, current, "ask"),
        )

    @staticmethod
    def _book_state(snapshot: object, source_time_ns: int) -> _BookStateSample:
        return _BookStateSample(
            source_time_ns=source_time_ns,
            snapshot=snapshot,
            bid=_book_side_state(snapshot, "bid"),
            ask=_book_side_state(snapshot, "ask"),
        )

    def _prune_book_history(self, latest_time_ns: int) -> None:
        cutoff_ns = latest_time_ns - _BOOK_HISTORY_NS
        while (
            len(self._book_states) > 1
            and self._book_states[1].source_time_ns <= cutoff_ns
        ):
            self._book_states.popleft()
        while (
            self._book_events
            and self._book_events[0].source_time_ns <= cutoff_ns
        ):
            self._book_events.popleft()

    def _reset_book_history(self, *, clear_snapshot: bool) -> None:
        self._book_states.clear()
        self._book_events.clear()
        if clear_snapshot:
            self._book_snapshot = None

    def _set_approved_tick_size(
        self, approved_tick_size: Decimal | None
    ) -> None:
        if approved_tick_size is None:
            return
        tick = _decimal(approved_tick_size)
        if tick <= _ZERO:
            raise ValueError("approved_tick_size must be positive")
        self._approved_tick_size = tick

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


def _latest_book_state_at(
    states: Iterable[_BookStateSample], target_ns: int
) -> _BookStateSample | None:
    chosen: _BookStateSample | None = None
    for state in states:
        if state.source_time_ns <= target_ns:
            chosen = state
        else:
            break
    return chosen


def _book_side_state(snapshot: object, side: str) -> _BookSideState:
    levels = getattr(snapshot, f"{side}s", {})
    reverse = side == "bid"
    top_prices = tuple(sorted(levels, reverse=reverse)[:_BOOK_TOP_N])
    top_depth = sum((_decimal(levels[price]) for price in top_prices), _ZERO)
    return _BookSideState(
        top_prices=frozenset(_decimal(price) for price in top_prices),
        top_depth=top_depth,
    )


def _book_side_event(
    update: object, previous: object, current: object, side: str
) -> _BookSideEvent:
    previous_levels = getattr(previous, f"{side}s", {})
    current_levels = getattr(current, f"{side}s", {})
    update_levels = getattr(update, f"{side}s", ())
    reverse = side == "bid"
    previous_near = set(
        sorted(previous_levels, reverse=reverse)[:_BOOK_NEAR_BEST_N]
    )
    current_near = set(
        sorted(current_levels, reverse=reverse)[:_BOOK_NEAR_BEST_N]
    )
    near_best = {_decimal(price) for price in previous_near | current_near}

    add_volume = _ZERO
    cancel_volume = _ZERO
    refresh_count = 0
    changed_prices: set[Decimal] = set()
    for level in update_levels:
        price = _decimal(getattr(level, "price"))
        previous_quantity = _decimal(previous_levels.get(price, _ZERO))
        current_quantity = _decimal(current_levels.get(price, _ZERO))
        delta = current_quantity - previous_quantity
        if delta == _ZERO:
            continue
        changed_prices.add(price)
        if delta > _ZERO:
            add_volume += delta
            if price in near_best:
                refresh_count += 1
        else:
            cancel_volume += -delta
    return _BookSideEvent(
        add_volume=add_volume,
        cancel_volume=cancel_volume,
        refresh_count=refresh_count,
        changed_prices=frozenset(changed_prices),
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
