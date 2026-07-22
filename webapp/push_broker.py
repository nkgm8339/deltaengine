"""PushBroker: pipeline hooks → WebSocket clients. Payload組立の唯一の場所。

WebSocketPayload仕様_v1 に完全準拠。数値は全て str(Decimal)。float() 禁止。
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

PAYLOAD_VERSION = 1


def d2s(v: Optional[Decimal]) -> Optional[str]:
    """Decimal → str（None透過）。floatは受け付けない。"""
    if v is None:
        return None
    if not isinstance(v, (Decimal, int)):
        raise TypeError(f"d2s expects Decimal/int/None, got {type(v)}")
    return str(v)


def envelope(msg_type: str, time_: datetime, symbol: str, payload: dict) -> dict:
    return {
        "v": PAYLOAD_VERSION,
        "type": msg_type,
        "time": time_.astimezone(timezone.utc).isoformat(),
        "symbol": symbol,
        "payload": payload,
    }


def compute_value_area(levels: list[dict]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """POC/VAH/VAL（WebSocketPayload仕様_v1 §4.3）。levelsは価格降順、各要素 Decimal。"""
    if not levels:
        return None, None, None
    totals = [(lv["price"], lv["bid"] + lv["ask"]) for lv in levels]
    poc_i = 0
    for i, (_, tot) in enumerate(totals):
        if tot > totals[poc_i][1]:
            poc_i = i
    grand = sum(t for _, t in totals)
    target = grand * Decimal("0.7")
    lo = hi = poc_i
    acc = totals[poc_i][1]
    while acc < target and (hi > 0 or lo < len(totals) - 1):
        up = totals[hi - 1][1] if hi > 0 else Decimal("-1")
        dn = totals[lo + 1][1] if lo < len(totals) - 1 else Decimal("-1")
        if up >= dn:
            hi -= 1
            acc += up
        else:
            lo += 1
            acc += dn
    return str(totals[poc_i][0]), str(totals[hi][0]), str(totals[lo][0])



class IntervalGate:
    """単調時刻ベースの間引きゲート (BAR_UPDATE スロットリング)。

    ready(now) は前回 True からの経過が interval_sec 以上のときだけ True。
    純粋ロジック (時刻は呼び出し側が渡す) — テスト可能。
    """

    def __init__(self, interval_sec: int) -> None:
        if interval_sec < 1:
            raise ValueError("interval_sec must be >= 1")
        self.interval_sec = interval_sec
        self._last = None  # monotonic clock value (loop.time())

    def ready(self, now) -> bool:
        if self._last is None or (now - self._last) >= self.interval_sec:
            self._last = now
            return True
        return False


class PushBroker:
    """WebSocketクライアント管理とPayload配信。asyncio単一ループ（ADR-003）。"""

    def __init__(
        self,
        symbol: str,
        depth_levels: int = 15,
    ) -> None:
        self.symbol = symbol
        self.depth_levels = depth_levels
        self._clients: set[Any] = set()
        self._lock = asyncio.Lock()

    async def register(self, ws: Any) -> None:
        async with self._lock:
            self._clients.add(ws)

    async def unregister(self, ws: Any) -> None:
        async with self._lock:
            self._clients.discard(ws)

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def _broadcast(self, msg: dict) -> None:
        text = json.dumps(msg, separators=(",", ":"))
        async with self._lock:
            dead = []
            for ws in self._clients:
                try:
                    await ws.send_text(text)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._clients.discard(ws)

    async def on_trade(self, trade) -> None:
        await self._broadcast(envelope("TICK", trade.event_time, self.symbol, {
            "price": d2s(trade.price),
            "quantity": d2s(trade.quantity),
            "side": trade.side,
            "tick_delta": d2s(getattr(trade, "tick_delta", None)),
            "tick_cvd": d2s(getattr(trade, "tick_cvd", None)),
        }))

    async def on_candle(self, candle, footprint_levels, orderbook_snapshot) -> None:
        levels = [
            {"price": lv["price"], "bid": lv["bid"], "ask": lv["ask"]}
            for lv in footprint_levels
        ]
        poc, vah, val = compute_value_area(levels)
        book = {"last_update_id": None, "bids": [], "asks": [], "depth_levels": self.depth_levels}
        if orderbook_snapshot is not None:
            bids = sorted(orderbook_snapshot.bids.items(), key=lambda x: x[0], reverse=True)
            asks = sorted(orderbook_snapshot.asks.items(), key=lambda x: x[0])
            book = {
                "last_update_id": orderbook_snapshot.last_update_id,
                "bids": [{"price": str(p), "qty": str(q)} for p, q in bids[: self.depth_levels]],
                "asks": [{"price": str(p), "qty": str(q)} for p, q in asks[: self.depth_levels]],
                "depth_levels": self.depth_levels,
            }
        await self._broadcast(envelope("CANDLE", candle.bar_time, self.symbol, {
            "bar_time": candle.bar_time.astimezone(timezone.utc).isoformat(),
            "timeframe": candle.timeframe,
            "open": d2s(candle.open), "high": d2s(candle.high),
            "low": d2s(candle.low), "close": d2s(candle.close),
            "volume": d2s(candle.volume), "delta": d2s(candle.delta), "cvd": d2s(candle.cvd),
            "footprint": {
                "levels": [{"price": str(l["price"]), "bid": str(l["bid"]), "ask": str(l["ask"])} for l in levels],
                "poc_price": poc, "vah_price": vah, "val_price": val,
            },
            "orderbook": book,
        }))

    async def on_analysis(self, analysis_result, signal_result, module_scores, absorption_result, divergence=None, imbalance_result=None, imbalance_detector=None, flow_events=None) -> None:
        now = analysis_result.analysis_time
        await self._broadcast(envelope("ANALYSIS", now, self.symbol, {
            "divergence": None if divergence is None else {
                "direction": divergence.direction.value,
                "kind": divergence.kind.value,
                "pivot_time": divergence.pivot_time.astimezone(timezone.utc).isoformat(),
                "previous_pivot_time": divergence.previous_pivot_time.astimezone(timezone.utc).isoformat(),
                "pivot_price": d2s(divergence.pivot_price),
                "previous_pivot_price": d2s(divergence.previous_pivot_price),
                "pivot_cvd": d2s(divergence.pivot_cvd),
                "previous_pivot_cvd": d2s(divergence.previous_pivot_cvd),
                "price_change": d2s(divergence.price_change),
                "cvd_change": d2s(divergence.cvd_change),
                "bars_between": divergence.bars_between,
            },
            "imbalance": None if imbalance_result is None else {
                "walls": [
                    {
                        "side": si.direction,
                        "count": si.count,
                        "price_start": d2s(si.start_price),
                        "price_end": d2s(si.end_price),
                    }
                    for si in imbalance_result.stacked_imbalances
                ],
                "ratio_threshold": d2s(imbalance_detector.ratio_threshold) if imbalance_detector is not None else None,
                "stack_count": imbalance_detector.stack_count if imbalance_detector is not None else None,
                "ratio_cap": d2s(imbalance_detector.ratio_cap) if imbalance_detector is not None else None,
                "min_volume": d2s(imbalance_detector.last_effective_min_volume) if imbalance_detector is not None else None,
            },
            "absorption": None if absorption_result is None else {
                "classification": absorption_result.classification,
                "strength": d2s(absorption_result.strength),
                "price_low": d2s(absorption_result.price_low),
                "price_high": d2s(absorption_result.price_high),
            },
            "flow_events": None if not flow_events else [
                {"event_time": fe.event_time.astimezone(timezone.utc).isoformat(),
                 "category": fe.kind.upper(), "kind": fe.kind, "side": fe.side,
                 "strength": d2s(fe.strength), "price": d2s(fe.price),
                 "detector": fe.kind,
                 "detail": fe.detail if isinstance(fe.detail, dict) else {}}
                for fe in flow_events
            ],
        }))

    async def on_flow_event(self, ev) -> None:
        category = str(getattr(ev, "category", getattr(ev, "kind", "UNKNOWN"))).upper()
        detector = str(getattr(ev, "detector", getattr(ev, "kind", category)))
        detail = getattr(ev, "detail", {})
        await self._broadcast(envelope("FLOW", ev.event_time, self.symbol, {
            "event_time": ev.event_time.astimezone(timezone.utc).isoformat(),
            "category": category, "side": ev.side,
            "strength": d2s(ev.strength), "price": d2s(getattr(ev, "price", None)),
            "detector": detector, "detail": detail,
        }))

    async def on_flow_response(self, snapshots) -> None:
        """Broadcast observational order-flow/price-response windows."""
        snapshots = tuple(snapshots)
        if not snapshots:
            return
        now = max(s.event_time for s in snapshots)
        await self._broadcast(envelope("FLOW_RESPONSE", now, self.symbol, {
            "windows": [
                {
                    "window_sec": s.window_sec,
                    "state": s.state.value,
                    "pressure_side": s.pressure_side,
                    "buy_volume": d2s(s.buy_volume),
                    "sell_volume": d2s(s.sell_volume),
                    "total_volume": d2s(s.total_volume),
                    "delta": d2s(s.delta),
                    "pressure_ratio": d2s(s.pressure_ratio),
                    "persistence": d2s(s.persistence),
                    "first_price": d2s(s.first_price),
                    "last_price": d2s(s.last_price),
                    "price_change": d2s(s.price_change),
                    "price_change_bps": d2s(s.price_change_bps),
                    "relative_volume": d2s(s.relative_volume),
                    "trade_count": s.trade_count,
                }
                for s in snapshots
            ],
            "note": "observed state; not a trade signal or probability",
        }))

    async def on_liquidation(self, liq) -> None:
        await self._broadcast(envelope("LIQUIDATION", liq.event_time, self.symbol, {
            "side": liq.side, "price": d2s(liq.price), "quantity": d2s(liq.quantity),
        }))

    async def on_oi(
        self,
        event_time: datetime,
        open_interest: Decimal,
        prev: Optional[Decimal],
        *,
        received_time: Optional[datetime] = None,
        source: str = "BINANCE_USDM",
        poll_interval_sec: int = 10,
    ) -> None:
        change = open_interest - prev if prev is not None else None
        change_pct = (
            (change / prev) * Decimal("100")
            if change is not None and prev is not None and prev > 0 else None
        )
        await self._broadcast(envelope("OI", event_time, self.symbol, {
            "open_interest": d2s(open_interest), "prev": d2s(prev),
            "change": d2s(change), "change_pct": d2s(change_pct),
            "source_time": event_time.astimezone(timezone.utc).isoformat(),
            "received_time": (
                received_time or datetime.now(timezone.utc)
            ).astimezone(timezone.utc).isoformat(),
            "source": source,
            "poll_interval_sec": poll_interval_sec,
        }))


    async def on_bar_update(self, candle, footprint_levels) -> None:
        """進行中バーのスナップショット配信 (BAR_UPDATE)。

        CANDLE と同形の footprint 構造 (levels 価格降順) + in_progress=true。
        orderbook は含めない (板は CANDLE 配信に同梱済み・軽量化のため)。
        """
        levels = [
            {"price": lv["price"], "bid": lv["bid"], "ask": lv["ask"]}
            for lv in footprint_levels
        ]
        poc, vah, val = compute_value_area(levels)
        await self._broadcast(envelope("BAR_UPDATE", candle.bar_time, self.symbol, {
            "bar_time": candle.bar_time.astimezone(timezone.utc).isoformat(),
            "timeframe": candle.timeframe,
            "in_progress": True,
            "open": d2s(candle.open), "high": d2s(candle.high),
            "low": d2s(candle.low), "close": d2s(candle.close),
            "volume": d2s(candle.volume), "delta": d2s(candle.delta), "cvd": d2s(candle.cvd),
            "footprint": {
                "levels": [{"price": str(l["price"]), "bid": str(l["bid"]), "ask": str(l["ask"])} for l in levels],
                "poc_price": poc, "vah_price": vah, "val_price": val,
            },
        }))

    async def send_health(self, event_time: datetime, payload: dict) -> None:
        """SelfMonitor v1 の HEALTH メッセージ (payload は直列化可能な dict)。"""
        await self._broadcast(envelope("HEALTH", event_time, self.symbol, payload))

    async def send_stats(self, event_time: datetime, stats: dict) -> None:
        await self._broadcast(envelope("STATS", event_time, self.symbol,
                                       {k: str(v) for k, v in stats.items()}))
