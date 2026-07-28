"""PushBroker: pipeline hooks → WebSocket clients. Payload組立の唯一の場所。

WebSocketPayload仕様_v1 に完全準拠。数値は全て str(Decimal)。float() 禁止。
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Awaitable, Callable, Optional

PAYLOAD_VERSION = 1


def d2s(v: Optional[Decimal]) -> Optional[str]:
    """Decimal → str（None透過）。floatは受け付けない。"""
    if v is None:
        return None
    if not isinstance(v, (Decimal, int)):
        raise TypeError(f"d2s expects Decimal/int/None, got {type(v)}")
    return str(v)


def _vwap_status(value: Optional[Decimal], status: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if status not in {"EXACT", "PARTIAL"}:
        raise ValueError("vwap_status must be EXACT or PARTIAL when vwap is present")
    return status


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

    def __init__(self, interval_sec: float) -> None:
        if interval_sec <= 0:
            raise ValueError("interval_sec must be > 0")
        self.interval_sec = float(interval_sec)
        self._last = None  # monotonic clock value (loop.time())

    def ready(self, now) -> bool:
        if self._last is None or (now - self._last) >= self.interval_sec:
            self._last = now
            return True
        return False


class LatestValuePump:
    """Send only the newest market value at a bounded cadence.

    The analytics path still consumes every trade. This pump is only for the
    browser projection, where replaying thousands of stale ticks creates visual
    latency without adding information. Publish is intentionally synchronous
    and must be called from the event-loop thread.
    """

    def __init__(
        self,
        send: Callable[[Any], Awaitable[None]],
        interval_sec: float,
    ) -> None:
        if interval_sec <= 0:
            raise ValueError("interval_sec must be > 0")
        self._send = send
        self.interval_sec = float(interval_sec)
        self._wake = asyncio.Event()
        self._latest: Any = None
        self._version = 0
        self.published = 0
        self.sent = 0

    def publish(self, value: Any) -> None:
        self._latest = value
        self._version += 1
        self.published += 1
        self._wake.set()

    @property
    def coalesced(self) -> int:
        return max(0, self.published - self.sent)

    async def run(self) -> None:
        while True:
            await self._wake.wait()
            self._wake.clear()
            value = self._latest
            version = self._version
            await self._send(value)
            self.sent += 1
            if self._version != version:
                self._wake.set()
            await asyncio.sleep(self.interval_sec)


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
        self._latest_hfm_message: dict | None = None

    async def register(self, ws: Any) -> None:
        async with self._lock:
            self._clients.add(ws)
            latest_hfm = self._latest_hfm_message
        if latest_hfm is not None:
            try:
                await ws.send_text(json.dumps(latest_hfm, separators=(",", ":")))
            except Exception:
                await self.unregister(ws)

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
            "trade_id": int(trade.trade_id),
            "price": d2s(trade.price),
            "quantity": d2s(trade.quantity),
            "side": trade.side,
            "tick_delta": d2s(getattr(trade, "tick_delta", None)),
            "tick_cvd": d2s(getattr(trade, "tick_cvd", None)),
        }))

    async def on_candle(
        self,
        candle,
        footprint_levels,
        orderbook_snapshot,
        session_vwap: Optional[Decimal] = None,
        vwap_status: Optional[str] = None,
    ) -> None:
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
        quality = _vwap_status(session_vwap, vwap_status)
        await self._broadcast(envelope("CANDLE", candle.bar_time, self.symbol, {
            "bar_time": candle.bar_time.astimezone(timezone.utc).isoformat(),
            "timeframe": candle.timeframe,
            "open": d2s(candle.open), "high": d2s(candle.high),
            "low": d2s(candle.low), "close": d2s(candle.close),
            "volume": d2s(candle.volume), "delta": d2s(candle.delta), "cvd": d2s(candle.cvd),
            "vwap": d2s(session_vwap),
            "vwap_status": quality,
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

    async def on_hfm_quote(self, quote) -> None:
        """Broadcast the directly observed HFM Bid/Ask and USD spread."""
        message = envelope(
            "HFM_QUOTE",
            quote.received_time,
            self.symbol,
            {
                "hfm_symbol": quote.symbol,
                "source_time": (
                    quote.source_time.astimezone(timezone.utc).isoformat()
                    if quote.source_time is not None else None
                ),
                "received_time": quote.received_time.astimezone(timezone.utc).isoformat(),
                "sequence": quote.sequence,
                "bid": d2s(quote.bid),
                "ask": d2s(quote.ask),
                "spread_usd": d2s(quote.spread),
            },
        )
        self._latest_hfm_message = message
        await self._broadcast(message)

    async def on_combined_context(self, event) -> None:
        """Broadcast a closed native 5m/10m four-axis observation."""
        entry = event.hfm_entry
        await self._broadcast(envelope(
            "COMBINED_CONTEXT",
            event.event_time,
            self.symbol,
            {
                "event_time": event.event_time.astimezone(timezone.utc).isoformat(),
                "bar_time": event.bar_time.astimezone(timezone.utc).isoformat(),
                "timeframe": event.timeframe,
                "pattern_no": event.context.pattern.number,
                "pattern_name": event.context.pattern.name,
                "price_direction": event.context.pattern.price_direction,
                "cvd_direction": event.context.pattern.cvd_direction,
                "delta_direction": event.context.pattern.delta_direction,
                "oi_direction": event.context.oi_direction.value,
                "oi_open": d2s(event.oi_open),
                "oi_close": d2s(event.oi_close),
                "oi_change": d2s(event.oi_change),
                "oi_change_pct": d2s(event.oi_change_pct),
                "oi_sample_count": event.oi_sample_count,
                "context_code": event.context.code,
                "context_title": event.context.title,
                "context_summary_ja": event.context.summary_ja,
                "hfm_entry_status": event.hfm_entry_status,
                "hfm_symbol": entry.symbol if entry is not None else None,
                "hfm_entry_spread": d2s(entry.spread) if entry is not None else None,
            },
        ))


    async def on_bar_update(
        self,
        candle,
        footprint_levels,
        *,
        source_trade_id: Optional[int] = None,
        source_event_time: Optional[datetime] = None,
        session_vwap: Optional[Decimal] = None,
        vwap_status: Optional[str] = None,
    ) -> None:
        """進行中バーのスナップショット配信 (BAR_UPDATE)。

        CANDLE と同形の footprint 構造 (levels 価格降順) + in_progress=true。
        orderbook は含めない (板は CANDLE 配信に同梱済み・軽量化のため)。
        """
        levels = [
            {"price": lv["price"], "bid": lv["bid"], "ask": lv["ask"]}
            for lv in footprint_levels
        ]
        poc, vah, val = compute_value_area(levels)
        quality = _vwap_status(session_vwap, vwap_status)
        await self._broadcast(envelope("BAR_UPDATE", candle.bar_time, self.symbol, {
            "bar_time": candle.bar_time.astimezone(timezone.utc).isoformat(),
            "timeframe": candle.timeframe,
            "in_progress": True,
            "source_trade_id": source_trade_id,
            "source_event_time": (
                source_event_time.astimezone(timezone.utc).isoformat()
                if source_event_time is not None else None
            ),
            "open": d2s(candle.open), "high": d2s(candle.high),
            "low": d2s(candle.low), "close": d2s(candle.close),
            "volume": d2s(candle.volume), "delta": d2s(candle.delta), "cvd": d2s(candle.cvd),
            "vwap": d2s(session_vwap),
            "vwap_status": quality,
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
