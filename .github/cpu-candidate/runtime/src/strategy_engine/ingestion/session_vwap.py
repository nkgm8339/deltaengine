"""Trade-level UTC-session VWAP accumulation for Strategy Engine material."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal


NS_PER_SECOND = 1_000_000_000
NS_PER_DAY = 86_400 * NS_PER_SECOND
SESSION_START_COVERAGE_GRACE = timedelta(seconds=1)
_ZERO = Decimal("0")


@dataclass(frozen=True)
class SessionVwapSeed:
    """Read-only aggregate restored from one persisted UTC session."""

    symbol: str
    session_start: datetime
    first_event_time: datetime
    last_event_time: datetime
    notional: Decimal
    volume: Decimal
    trade_count: int
    last_trade_id: int

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("symbol must not be empty")
        session_start = _as_utc(self.session_start)
        first_event_time = _as_utc(self.first_event_time)
        last_event_time = _as_utc(self.last_event_time)
        if session_start != _utc_session_start(session_start):
            raise ValueError("session_start must be UTC 00:00")
        session_end = session_start + timedelta(days=1)
        if not session_start <= first_event_time <= last_event_time < session_end:
            raise ValueError("seed events must belong to one ordered UTC session")

        notional = _positive_decimal(self.notional, "notional")
        volume = _positive_decimal(self.volume, "volume")
        if not isinstance(self.trade_count, int) or self.trade_count < 1:
            raise ValueError("trade_count must be a positive int")
        if not isinstance(self.last_trade_id, int):
            raise TypeError("last_trade_id must be int")

        object.__setattr__(self, "session_start", session_start)
        object.__setattr__(self, "first_event_time", first_event_time)
        object.__setattr__(self, "last_event_time", last_event_time)
        object.__setattr__(self, "notional", notional)
        object.__setattr__(self, "volume", volume)

    @property
    def session_complete(self) -> bool:
        """Whether persisted coverage begins at the UTC session boundary."""

        return _covers_session_start(self.first_event_time, self.session_start)


class SessionVwapAccumulator:
    """Exact Decimal accumulator for ``sum(price*qty) / sum(qty)``.

    A value is exposed only when the first accepted trade covers the UTC 00:00
    boundary. Mid-session starts continue accumulating for observability but
    remain fail-closed for Strategy Engine conditions.
    """

    def __init__(self, symbol: str) -> None:
        if not symbol:
            raise ValueError("symbol must not be empty")
        self._symbol = symbol
        self._session_start_ns: int | None = None
        self._last_event_ns: int | None = None
        self._last_trade_id: int | None = None
        self._notional = _ZERO
        self._volume = _ZERO
        self._trade_count = 0
        self._session_complete = False

    @property
    def trade_count(self) -> int:
        return self._trade_count

    @property
    def session_complete(self) -> bool:
        return self._session_complete

    @property
    def current_value(self) -> Decimal | None:
        """Return the display-only aggregate, even for partial sessions.

        Strategy Engine material must continue to use ``value_at()``, which
        remains fail-closed until UTC-session boundary coverage is complete.
        """

        if self._volume <= _ZERO:
            return None
        return self._notional / self._volume

    def seed(self, seed: SessionVwapSeed) -> int:
        """Restore one aggregate before accepting live trades."""

        if seed.symbol != self._symbol:
            raise ValueError(f"seed symbol mismatch: {seed.symbol!r}")
        if self._session_start_ns is not None:
            raise RuntimeError("session VWAP accumulator is already initialized")

        self._session_start_ns = _datetime_ns(seed.session_start)
        self._last_event_ns = _datetime_ns(seed.last_event_time)
        self._last_trade_id = seed.last_trade_id
        self._notional = seed.notional
        self._volume = seed.volume
        self._trade_count = seed.trade_count
        self._session_complete = seed.session_complete
        return self._trade_count

    def observe_trade(self, trade: object) -> bool:
        """Fold one ordered normalized trade; return whether it was accepted."""

        symbol = getattr(trade, "symbol", None)
        if symbol != self._symbol:
            raise ValueError(f"trade symbol mismatch: {symbol!r}")
        event_time = getattr(trade, "event_time", None)
        if not isinstance(event_time, datetime):
            raise TypeError("trade event_time must be datetime")
        event_time = _as_utc(event_time)
        event_ns = _datetime_ns(event_time)
        session_start = _utc_session_start(event_time)
        session_start_ns = _datetime_ns(session_start)
        price = _positive_decimal(getattr(trade, "price", None), "trade price")
        quantity = _positive_decimal(
            getattr(trade, "quantity", None), "trade quantity"
        )
        trade_id = getattr(trade, "trade_id", None)
        if not isinstance(trade_id, int):
            raise TypeError("trade_id must be int")

        if self._session_start_ns is None or session_start_ns > self._session_start_ns:
            self._reset_session(
                session_start_ns=session_start_ns,
                first_event_time=event_time,
                session_start=session_start,
            )
        elif session_start_ns < self._session_start_ns:
            return False

        if self._last_event_ns is not None:
            if event_ns < self._last_event_ns:
                return False
            if (
                event_ns == self._last_event_ns
                and self._last_trade_id is not None
                and trade_id <= self._last_trade_id
            ):
                return False

        self._notional += price * quantity
        self._volume += quantity
        self._trade_count += 1
        self._last_event_ns = event_ns
        self._last_trade_id = trade_id
        return True

    def value_at(self, source_time_ns: int) -> Decimal | None:
        """Return the complete current-session VWAP as of ``source_time_ns``."""

        if not isinstance(source_time_ns, int):
            raise TypeError("source_time_ns must be int")
        if (
            self._session_start_ns is None
            or self._last_event_ns is None
            or not self._session_complete
            or self._volume <= _ZERO
        ):
            return None
        if self._last_event_ns > source_time_ns:
            return None
        if _session_start_ns(source_time_ns) != self._session_start_ns:
            return None
        return self._notional / self._volume

    def _reset_session(
        self,
        *,
        session_start_ns: int,
        first_event_time: datetime,
        session_start: datetime,
    ) -> None:
        self._session_start_ns = session_start_ns
        self._last_event_ns = None
        self._last_trade_id = None
        self._notional = _ZERO
        self._volume = _ZERO
        self._trade_count = 0
        self._session_complete = _covers_session_start(
            first_event_time, session_start
        )


def _positive_decimal(value: object, name: str) -> Decimal:
    parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    if not parsed.is_finite() or parsed <= _ZERO:
        raise ValueError(f"{name} must be finite and positive")
    return parsed


def _covers_session_start(first_event: datetime, session_start: datetime) -> bool:
    return session_start <= first_event <= session_start + SESSION_START_COVERAGE_GRACE


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _utc_session_start(value: datetime) -> datetime:
    utc = _as_utc(value)
    return utc.replace(hour=0, minute=0, second=0, microsecond=0)


def _datetime_ns(value: datetime) -> int:
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    delta = _as_utc(value) - epoch
    return (
        delta.days * 86_400 * NS_PER_SECOND
        + delta.seconds * NS_PER_SECOND
        + delta.microseconds * 1_000
    )


def _session_start_ns(source_time_ns: int) -> int:
    return (source_time_ns // NS_PER_DAY) * NS_PER_DAY
