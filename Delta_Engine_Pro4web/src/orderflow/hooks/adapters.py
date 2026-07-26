"""Adapters that expose existing independent observations as Hook candidates.

They do not change legacy detector thresholds or UI payloads. Calibration
gating remains the responsibility of :class:`ThresholdBook`.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime
from decimal import Decimal
from typing import Any, Iterable

from .models import HookCandidate, HookSide, as_utc
from .registry import require_hook


_ZERO = Decimal(0)
_ONE = Decimal(1)


def _decimal(value: Any, default: Decimal = _ZERO) -> Decimal:
    if value is None:
        return default
    parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    if not parsed.is_finite():
        raise ValueError("adapter metric must be finite")
    return parsed


def _candidate(
    hook_id: str,
    *,
    symbol: str,
    side: HookSide,
    source_time: datetime,
    received_time: datetime,
    metric_name: str,
    metric_value: Any,
    source_sequence: str | None = None,
    anchor_price: Any = None,
    episode_id: str | None = None,
    evidence: dict[str, Any] | None = None,
) -> HookCandidate:
    definition = require_hook(hook_id)
    received = as_utc(received_time, "received_time")
    return HookCandidate(
        hook_id=hook_id,
        symbol=symbol.upper(),
        side=side,
        direction_hint=definition.direction_hint,
        source_time=as_utc(source_time, "source_time"),
        received_time=received,
        available_time=received,
        metric_name=metric_name,
        metric_value=_decimal(metric_value),
        source_sequence=source_sequence,
        anchor_price=_decimal(anchor_price) if anchor_price is not None else None,
        episode_id=episode_id,
        evidence=evidence or {},
    )


class TapeHookAdapter:
    """Side-aware ingredients corresponding to the catalog's existing B Hooks."""

    def __init__(self, window_ms: int = 5000) -> None:
        if window_ms < 1:
            raise ValueError("window_ms must be positive")
        self.window_ms = int(window_ms)
        self._window: deque[tuple[int, str, Decimal]] = deque()
        self._last_time_ms: int | None = None

    @staticmethod
    def _ms(value: datetime) -> int:
        return int(as_utc(value).timestamp() * 1000)

    def process(
        self,
        trade: Any,
        *,
        received_time: datetime | None = None,
    ) -> tuple[HookCandidate, ...]:
        side = str(trade.side)
        if side not in {"BUY", "SELL"}:
            return ()
        event_time = as_utc(trade.event_time, "trade.event_time")
        received = as_utc(received_time or event_time, "received_time")
        now_ms = self._ms(event_time)
        qty = _decimal(trade.quantity)
        self._window.append((now_ms, side, qty))
        while self._window and now_ms - self._window[0][0] > self.window_ms:
            self._window.popleft()

        streak_count = 0
        for _time_ms, trailing_side, _qty in reversed(self._window):
            if trailing_side != side:
                break
            streak_count += 1

        buy = sum(row[2] for row in self._window if row[1] == "BUY")
        sell = sum(row[2] for row in self._window if row[1] == "SELL")
        total = buy + sell
        buy_ratio = buy / total if total > _ZERO else Decimal("0.5")
        persistence = max(buy, sell) / total if total > _ZERO else _ZERO
        delta = buy - sell
        trades_per_sec = (
            Decimal(len(self._window)) / (Decimal(self.window_ms) / Decimal(1000))
        )
        sequence = str(getattr(trade, "trade_id", "")) or None
        price = trade.price
        result = [
            _candidate(
                "B01" if side == "BUY" else "B02",
                symbol=trade.symbol,
                side=HookSide(side),
                source_time=event_time,
                received_time=received,
                metric_name="consecutive_trade_count",
                metric_value=streak_count,
                source_sequence=sequence,
                anchor_price=price,
                evidence={"window_ms": self.window_ms},
            ),
            _candidate(
                "B03" if buy_ratio >= Decimal("0.5") else "B04",
                symbol=trade.symbol,
                side=HookSide.BUY if buy_ratio >= Decimal("0.5") else HookSide.SELL,
                source_time=event_time,
                received_time=received,
                metric_name="side_aggression_ratio",
                metric_value=buy_ratio if buy_ratio >= Decimal("0.5") else _ONE - buy_ratio,
                source_sequence=sequence,
                anchor_price=price,
                evidence={"buy_ratio": buy_ratio, "window_ms": self.window_ms},
            ),
            _candidate(
                "B05",
                symbol=trade.symbol,
                side=HookSide.NEUTRAL,
                source_time=event_time,
                received_time=received,
                metric_name="trades_per_sec",
                metric_value=trades_per_sec,
                source_sequence=sequence,
                anchor_price=price,
                evidence={"trade_count": len(self._window), "window_ms": self.window_ms},
            ),
            _candidate(
                "B15" if delta >= _ZERO else "B16",
                symbol=trade.symbol,
                side=HookSide.BUY if delta >= _ZERO else HookSide.SELL,
                source_time=event_time,
                received_time=received,
                metric_name="absolute_delta_quantity",
                metric_value=abs(delta),
                source_sequence=sequence,
                anchor_price=price,
                evidence={"delta": delta, "window_ms": self.window_ms},
            ),
            _candidate(
                "B19",
                symbol=trade.symbol,
                side=HookSide.BUY if buy >= sell else HookSide.SELL,
                source_time=event_time,
                received_time=received,
                metric_name="persistence",
                metric_value=persistence,
                source_sequence=sequence,
                anchor_price=price,
                evidence={"buy_quantity": buy, "sell_quantity": sell},
            ),
        ]
        if self._last_time_ms is not None:
            gap_ms = now_ms - self._last_time_ms
            if gap_ms >= 0:
                result.append(_candidate(
                    "B06",
                    symbol=trade.symbol,
                    side=HookSide.NEUTRAL,
                    source_time=event_time,
                    received_time=received,
                    metric_name="inter_trade_gap_ms",
                    metric_value=gap_ms,
                    source_sequence=sequence,
                    anchor_price=price,
                ))
        self._last_time_ms = now_ms
        return tuple(result)


class ExistingFlowEventAdapter:
    """Map existing large-trade/sweep/tape FlowEvents without mutating them."""

    def process(
        self,
        event: Any,
        *,
        symbol: str,
        received_time: datetime | None = None,
    ) -> tuple[HookCandidate, ...]:
        event_time = as_utc(event.event_time, "event.event_time")
        received = as_utc(received_time or event_time, "received_time")
        side = str(event.side)
        detail = dict(event.detail)
        common = dict(
            symbol=symbol,
            source_time=event_time,
            received_time=received,
            anchor_price=event.price,
            evidence={"legacy_kind": event.kind, **detail},
        )
        if event.kind == "large_trade" and side in {"BUY", "SELL"}:
            return (_candidate(
                "B07" if side == "BUY" else "B08",
                side=HookSide(side),
                metric_name="trade_notional",
                metric_value=detail.get("notional", 0),
                **common,
            ),)
        if event.kind == "sweep" and side in {"BUY", "SELL"}:
            return (_candidate(
                "B11" if side == "BUY" else "B12",
                side=HookSide(side),
                metric_name="sweep_quantity",
                metric_value=detail.get("total_qty", 0),
                **common,
            ),)
        if event.kind != "tape":
            return ()
        result: list[HookCandidate] = []
        if side in {"BUY", "SELL"}:
            ratio = _decimal(detail.get("aggression_ratio"), Decimal("0.5"))
            result.append(_candidate(
                "B03" if side == "BUY" else "B04",
                side=HookSide(side),
                metric_name="side_aggression_ratio",
                metric_value=ratio if side == "BUY" else _ONE - ratio,
                **common,
            ))
        result.append(_candidate(
            "B05",
            side=HookSide.NEUTRAL,
            metric_name="trades_per_sec",
            metric_value=detail.get("trades_per_sec", 0),
            **common,
        ))
        if detail.get("paused"):
            result.append(_candidate(
                "B06",
                side=HookSide.NEUTRAL,
                metric_name="inter_trade_gap_ms",
                metric_value=detail.get("pause_ms", 0),
                **common,
            ))
        return tuple(result)


class AbsorptionHookAdapter:
    """Emit only the start edge of an existing absorption episode."""

    def __init__(self) -> None:
        self._active: str | None = None

    def process(
        self,
        result: Any | None,
        *,
        event_time: datetime,
        received_time: datetime,
        symbol: str,
    ) -> tuple[HookCandidate, ...]:
        if result is None:
            self._active = None
            return ()
        classification = str(result.classification)
        if classification == self._active:
            return ()
        self._active = classification
        if classification == "BUY_ABSORPTION":
            hook_id, side = "C01", HookSide.BUY
        elif classification == "SELL_ABSORPTION":
            hook_id, side = "C02", HookSide.SELL
        else:
            return ()
        anchor = (result.price_low + result.price_high) / Decimal(2)
        episode = f"{classification}:{as_utc(event_time).isoformat()}:{anchor}"
        return (_candidate(
            hook_id,
            symbol=symbol,
            side=side,
            source_time=event_time,
            received_time=received_time,
            metric_name="absorption_strength",
            metric_value=result.strength,
            anchor_price=anchor,
            episode_id=episode,
            evidence={
                "classification": classification,
                "price_low": result.price_low,
                "price_high": result.price_high,
            },
        ),)


class FlowResponseHookAdapter:
    """Expose existing transition events D01-D05 without reclassifying Flow."""

    _STATE_HOOK = {
        "BUY_EFFECTIVE": ("D01", HookSide.BUY),
        "SELL_EFFECTIVE": ("D02", HookSide.SELL),
        "BUY_TRAPPED": ("D03", HookSide.BUY),
        "SELL_TRAPPED": ("D04", HookSide.SELL),
        "BUY_STALLED": ("D05", HookSide.BUY),
        "SELL_STALLED": ("D05", HookSide.SELL),
    }

    def __init__(self) -> None:
        self._last_state: dict[int, str] = {}

    def process(
        self,
        snapshots: Iterable[Any],
        *,
        received_time: datetime | None = None,
    ) -> tuple[HookCandidate, ...]:
        result = []
        for snapshot in snapshots:
            state = getattr(snapshot.state, "value", str(snapshot.state))
            previous = self._last_state.get(snapshot.window_sec)
            self._last_state[snapshot.window_sec] = state
            if state == previous:
                continue
            mapped = self._STATE_HOOK.get(state)
            if mapped is None:
                continue
            hook_id, side = mapped
            event_time = as_utc(snapshot.event_time)
            received = as_utc(received_time or event_time)
            result.append(_candidate(
                hook_id,
                symbol=snapshot.symbol,
                side=side,
                source_time=event_time,
                received_time=received,
                metric_name="state_transition",
                metric_value=1,
                source_sequence=f"{snapshot.window_sec}:{state}",
                anchor_price=snapshot.last_price,
                episode_id=f"{snapshot.window_sec}:{state}:{event_time.isoformat()}",
                evidence={
                    "window_sec": snapshot.window_sec,
                    "state": state,
                    "pressure_side": snapshot.pressure_side,
                    "pressure_ratio": snapshot.pressure_ratio,
                    "persistence": snapshot.persistence,
                    "price_change_bps": snapshot.price_change_bps,
                },
            ))
        return tuple(result)


def native_flow_context_candidate(
    snapshot: Any,
    *,
    received_time: datetime | None = None,
) -> HookCandidate:
    event_time = as_utc(snapshot.event_time)
    side = (
        HookSide.BUY if snapshot.pressure_side == "BUY"
        else HookSide.SELL if snapshot.pressure_side == "SELL"
        else HookSide.NEUTRAL
    )
    return _candidate(
        "G12",
        symbol=snapshot.symbol,
        side=side,
        source_time=event_time,
        received_time=received_time or event_time,
        metric_name="higher_timeframe_pressure_ratio",
        metric_value=snapshot.pressure_ratio,
        source_sequence=f"{snapshot.timeframe}:{event_time.isoformat()}",
        anchor_price=snapshot.last_price,
        evidence={
            "timeframe": snapshot.timeframe,
            "state": getattr(snapshot.state, "value", str(snapshot.state)),
            "price_change_bps": snapshot.price_change_bps,
        },
    )


def hfm_spread_candidate(
    quote: Any,
    *,
    symbol: str,
    received_time: datetime | None = None,
) -> HookCandidate:
    received = as_utc(received_time or quote.received_time)
    source = as_utc(quote.source_time or quote.received_time)
    return _candidate(
        "H04",
        symbol=symbol,
        side=HookSide.NEUTRAL,
        source_time=source,
        received_time=received,
        metric_name="hfm_spread",
        metric_value=quote.spread,
        source_sequence=str(quote.sequence) if quote.sequence is not None else None,
        evidence={
            "hfm_symbol": quote.symbol,
            "bid": quote.bid,
            "ask": quote.ask,
        },
    )
