"""Flow event detectors — Phase A (FlowDetector_v1).

Five detectors that emit FlowEvent from trade-stream / footprint / orderbook data.
All Decimal arithmetic; float() is never called. Synchronous (ADR-003).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional


@dataclass(frozen=True)
class FlowEvent:
    event_time: datetime
    kind: str       # "large_trade" | "sweep" | "exhaustion" | "unfinished_auction" | "tape"
    side: str       # "BUY" | "SELL" | "NEUTRAL"
    price: Decimal
    strength: Decimal   # 0–1
    detail: dict


_ZERO = Decimal("0")
_ONE = Decimal("1")
_HALF = Decimal("0.5")


def _clamp(value: Decimal, lo: Decimal = _ZERO, hi: Decimal = _ONE) -> Decimal:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


# ── 2-1. LargeTradeDetector ──────────────────────────────────────────────────

class LargeTradeDetector:
    def __init__(self, min_qty: Decimal) -> None:
        self._min_qty = Decimal(str(min_qty))

    def process(self, trade: Any) -> Optional[FlowEvent]:
        qty = trade.quantity
        if qty < self._min_qty:
            return None
        strength = _clamp(qty / (self._min_qty * Decimal("4")))
        notional = trade.price * qty
        return FlowEvent(
            event_time=trade.event_time,
            kind="large_trade",
            side=trade.side,
            price=trade.price,
            strength=strength,
            detail={"quantity": str(qty), "notional": str(notional)},
        )


# ── 2-2. SweepDetector ───────────────────────────────────────────────────────

class SweepDetector:
    def __init__(
        self,
        window_ms: int,
        min_qty: Decimal,
        min_levels: int,
        tick_size: Decimal,
        cooldown_ms: int,
    ) -> None:
        self._window_ms = window_ms
        self._min_qty = Decimal(str(min_qty))
        self._min_levels = min_levels
        self._tick_size = Decimal(str(tick_size))
        self._cooldown_ms = cooldown_ms
        # trades per side: deque of (epoch_ms, price, qty)
        self._buys: deque[tuple[int, Decimal, Decimal]] = deque()
        self._sells: deque[tuple[int, Decimal, Decimal]] = deque()
        self._last_fire_ms: dict[str, int] = {"BUY": -999999999, "SELL": -999999999}

    def _epoch_ms(self, dt: datetime) -> int:
        return int(dt.timestamp() * 1000)

    def _prune(self, buf: deque, now_ms: int) -> None:
        while buf and (now_ms - buf[0][0]) > self._window_ms:
            buf.popleft()

    def process(self, trade: Any) -> Optional[FlowEvent]:
        side = trade.side
        if side not in ("BUY", "SELL"):
            return None
        now_ms = self._epoch_ms(trade.event_time)
        buf = self._buys if side == "BUY" else self._sells
        buf.append((now_ms, trade.price, trade.quantity))
        self._prune(buf, now_ms)

        # cooldown guard
        if now_ms - self._last_fire_ms[side] < self._cooldown_ms:
            return None

        total_qty = sum(e[2] for e in buf)
        if total_qty < self._min_qty:
            return None

        prices = {e[1] for e in buf}
        if self._tick_size > _ZERO:
            levels = len({(p / self._tick_size).to_integral_value() for p in prices})
        else:
            levels = len(prices)

        if levels < self._min_levels:
            return None

        duration_ms = now_ms - buf[0][0]
        strength = _clamp(Decimal(str(levels)) / (Decimal(str(self._min_levels)) * Decimal("3")))
        self._last_fire_ms[side] = now_ms
        return FlowEvent(
            event_time=trade.event_time,
            kind="sweep",
            side=side,
            price=trade.price,
            strength=strength,
            detail={"levels": levels, "total_qty": str(total_qty), "duration_ms": duration_ms},
        )


# ── 2-3. ExhaustionDetector ──────────────────────────────────────────────────

class ExhaustionDetector:
    def __init__(self, exhaustion_ratio: Decimal) -> None:
        self._ratio = Decimal(str(exhaustion_ratio))

    def process(self, bar: Any) -> Optional[FlowEvent]:
        levels = bar.levels
        if len(levels) < 3:
            return None

        total_vol = sum(lv.buy_volume + lv.sell_volume for lv in levels)
        n = Decimal(str(len(levels)))
        avg_vol = total_vol / n

        if avg_vol == _ZERO:
            return None

        open_price = levels[0].price   # levels sorted ascending
        close_price = levels[-1].price

        if close_price > open_price:
            # up bar: check top 2 levels
            extreme = levels[-2:]
            signal_side = "SELL"
        else:
            # down bar: check bottom 2 levels
            extreme = levels[:2]
            signal_side = "BUY"

        extreme_vol = sum(lv.buy_volume + lv.sell_volume for lv in extreme)
        threshold = avg_vol * self._ratio

        if extreme_vol > threshold:
            return None

        if threshold == _ZERO:
            return None

        raw_strength = _ONE - (extreme_vol / threshold)
        strength = _clamp(raw_strength)
        rep_price = extreme[-1].price if signal_side == "SELL" else extreme[0].price

        return FlowEvent(
            event_time=bar.bar_time,
            kind="exhaustion",
            side=signal_side,
            price=rep_price,
            strength=strength,
            detail={
                "extreme_levels_vol": str(extreme_vol),
                "avg_level_vol": str(avg_vol),
                "bar_time": str(bar.bar_time),
            },
        )


# ── 2-4. UnfinishedAuctionDetector ───────────────────────────────────────────

class UnfinishedAuctionDetector:
    def __init__(self, ua_min_vol: Decimal) -> None:
        self._min_vol = Decimal(str(ua_min_vol))

    def process(self, bar: Any) -> Optional[FlowEvent]:
        levels = bar.levels
        if not levels:
            return None

        results: list[FlowEvent] = []

        # Check high (top level): bid=buy_volume, ask=sell_volume
        top = levels[-1]
        if top.buy_volume >= self._min_vol and top.sell_volume >= self._min_vol:
            bid_v = top.buy_volume
            ask_v = top.sell_volume
            strength = _clamp(min(bid_v, ask_v) / (self._min_vol * Decimal("4")))
            results.append(FlowEvent(
                event_time=bar.bar_time,
                kind="unfinished_auction",
                side="BUY",
                price=top.price,
                strength=strength,
                detail={"level_price": str(top.price), "bid": str(bid_v), "ask": str(ask_v), "at": "high"},
            ))

        # Check low (bottom level)
        bot = levels[0]
        if bot.buy_volume >= self._min_vol and bot.sell_volume >= self._min_vol:
            bid_v = bot.buy_volume
            ask_v = bot.sell_volume
            strength = _clamp(min(bid_v, ask_v) / (self._min_vol * Decimal("4")))
            results.append(FlowEvent(
                event_time=bar.bar_time,
                kind="unfinished_auction",
                side="SELL",
                price=bot.price,
                strength=strength,
                detail={"level_price": str(bot.price), "bid": str(bid_v), "ask": str(ask_v), "at": "low"},
            ))

        return results[0] if results else None


# ── 2-5. TapeAnalyzer ────────────────────────────────────────────────────────

class TapeAnalyzer:
    def __init__(
        self,
        window_ms: int,
        emit_interval_ms: int,
        pause_threshold_ms: int,
        aggression_buy_threshold: Decimal = Decimal("0.6"),
        aggression_sell_threshold: Decimal = Decimal("0.4"),
    ) -> None:
        self._window_ms = window_ms
        self._emit_interval_ms = emit_interval_ms
        self._pause_threshold_ms = pause_threshold_ms
        self._buy_thresh = Decimal(str(aggression_buy_threshold))
        self._sell_thresh = Decimal(str(aggression_sell_threshold))
        # deque of (epoch_ms, side, qty)
        self._buf: deque[tuple[int, str, Decimal]] = deque()
        self._last_emit_ms: int = 0
        self._last_trade_ms: int = 0

    def _epoch_ms(self, dt: datetime) -> int:
        return int(dt.timestamp() * 1000)

    def _prune(self, now_ms: int) -> None:
        while self._buf and (now_ms - self._buf[0][0]) > self._window_ms:
            self._buf.popleft()

    def process(self, trade: Any) -> Optional[FlowEvent]:
        now_ms = self._epoch_ms(trade.event_time)
        self._buf.append((now_ms, trade.side, trade.quantity))
        self._prune(now_ms)
        prev_trade_ms = self._last_trade_ms
        self._last_trade_ms = now_ms

        if now_ms - self._last_emit_ms < self._emit_interval_ms:
            return None

        return self._emit(trade.event_time, trade.price, now_ms, prev_trade_ms)

    def _emit(self, event_time: datetime, price: Decimal, now_ms: int, prev_trade_ms: int = 0) -> FlowEvent:
        self._last_emit_ms = now_ms

        window_sec = Decimal(str(self._window_ms)) / Decimal("1000")
        trades_per_sec = Decimal(str(len(self._buf))) / window_sec if window_sec > _ZERO else _ZERO

        # max consecutive same side
        max_consec = 0
        cur_consec = 0
        cur_side = None
        for _, side, _ in self._buf:
            if side == cur_side:
                cur_consec += 1
            else:
                cur_side = side
                cur_consec = 1
            if cur_consec > max_consec:
                max_consec = cur_consec

        pause_ms = now_ms - prev_trade_ms if prev_trade_ms else 0
        paused = pause_ms > self._pause_threshold_ms

        buy_vol = sum(e[2] for e in self._buf if e[1] == "BUY")
        total_vol = sum(e[2] for e in self._buf)
        aggression_ratio = (buy_vol / total_vol) if total_vol > _ZERO else _HALF

        strength = _clamp(abs(aggression_ratio - _HALF) * Decimal("2"))

        if aggression_ratio >= self._buy_thresh:
            side = "BUY"
        elif aggression_ratio <= self._sell_thresh:
            side = "SELL"
        else:
            side = "NEUTRAL"

        detail: dict[str, Any] = {
            "trades_per_sec": str(trades_per_sec),
            "max_consecutive_side": max_consec,
            "pause_ms": pause_ms,
            "aggression_ratio": str(aggression_ratio),
        }
        if paused:
            detail["paused"] = True

        return FlowEvent(
            event_time=event_time,
            kind="tape",
            side=side,
            price=price,
            strength=strength,
            detail=detail,
        )
