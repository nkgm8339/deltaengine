"""PushBroker: pipeline hooks → WebSocket clients. Payload組立の唯一の場所。

WebSocketPayload仕様_v1 に完全準拠。数値は全て str(Decimal)。float() 禁止。
"""
from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Awaitable, Callable, Optional
from uuid import uuid4

from webapp.book_projection import BookProjection, FAIL_CLOSED_STATES, SYNCED
from webapp.tape import TapeBatch

PAYLOAD_VERSION = 1
CLIENT_SEND_TIMEOUT_SEC = 0.5
CLIENT_QUEUE_MAXSIZE = 256
_HEARTBEAT_PRIORITY = 0
_NORMAL_PRIORITY = 1


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


@dataclass(order=True)
class _QueuedMessage:
    priority: int
    sequence: int
    text: str = field(compare=False)
    completion: asyncio.Future | None = field(default=None, compare=False)


@dataclass(eq=False)
class _ClientState:
    ws: Any
    queue: asyncio.PriorityQueue = field(
        default_factory=lambda: asyncio.PriorityQueue(maxsize=CLIENT_QUEUE_MAXSIZE)
    )
    writer_task: asyncio.Task | None = None
    closing: bool = False
    close_socket_on_stop: bool = False
    queue_high_watermark: int = 0


class PushBroker:
    """WebSocketクライアント管理とPayload配信。asyncio単一ループ（ADR-003）。"""

    def __init__(
        self,
        symbol: str,
        depth_levels: int = 15,
        live_dom_depth_levels: int = 50,
        persistent_writer=None,
        client_send_timeout_sec: float = CLIENT_SEND_TIMEOUT_SEC,
    ) -> None:
        self.symbol = symbol
        self.persistent_writer = persistent_writer
        self.depth_levels = depth_levels
        self.live_dom_depth_levels = live_dom_depth_levels
        self._clients: dict[Any, _ClientState] = {}
        self._lock = asyncio.Lock()
        self._enqueue_lock = asyncio.Lock()
        self._enqueue_sequence = 0
        self._closed = False
        self.client_queue_high_watermark = 0
        self.client_send_timeout_sec = float(client_send_timeout_sec)
        if self.client_send_timeout_sec <= 0:
            raise ValueError("client_send_timeout_sec must be > 0")
        self._latest_hfm_message: dict | None = None
        self._latest_book_message: dict | None = None
        self._latest_absorption_message: dict | None = None
        self._latest_tick_message: dict | None = None
        self._latest_spot_message: dict | None = None
        self._latest_big_trades_status_message: dict | None = None
        self.book_stream_id = str(uuid4())
        self.book_updates_broadcast = 0
        self.tape_batches_broadcast = 0
        self.tape_trades_broadcast = 0
        self.market_heartbeat_sequence = 0

    async def register(self, ws: Any) -> None:
        cache_completion = None
        state = _ClientState(ws=ws)
        # Cache items are enqueued before this client becomes visible to later
        # normal broadcasts. No broker lock is held while network I/O runs.
        async with self._enqueue_lock:
            async with self._lock:
                if self._closed or ws in self._clients:
                    return
                cached = (
                    self._latest_big_trades_status_message,
                    self._latest_tick_message,
                    self._latest_spot_message,
                    self._latest_hfm_message,
                    self._latest_book_message,
                    self._latest_absorption_message,
                )
                cached = tuple(latest for latest in cached if latest is not None)
                if cached:
                    cache_completion = asyncio.get_running_loop().create_future()
                for index, latest in enumerate(cached):
                    completion = cache_completion if index == len(cached) - 1 else None
                    self._put_nowait(
                        state,
                        json.dumps(latest, separators=(",", ":")),
                        _NORMAL_PRIORITY,
                        completion=completion,
                    )
                state.writer_task = asyncio.create_task(
                    self._client_writer(state),
                    name=f"push-writer-{id(ws)}",
                )
                self._clients[ws] = state

        if cache_completion is not None:
            try:
                await asyncio.wait_for(
                    asyncio.shield(cache_completion),
                    timeout=self.client_send_timeout_sec,
                )
            except Exception:
                await self._stop_state(state, close_socket=True)

    async def unregister(self, ws: Any) -> None:
        async with self._lock:
            state = self._clients.pop(ws, None)
            if state is not None:
                state.closing = True
        if state is not None:
            await self._stop_state(state, close_socket=False)

    async def close(self) -> None:
        """Stop and await every per-client writer. Safe to call repeatedly."""
        async with self._enqueue_lock:
            async with self._lock:
                self._closed = True
                states = tuple(self._clients.values())
                self._clients.clear()
                for state in states:
                    state.closing = True
                    state.close_socket_on_stop = True
        if states:
            await asyncio.gather(
                *(self._stop_state(state, close_socket=True) for state in states),
                return_exceptions=True,
            )

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def wait_until_idle(self, ws: Any | None = None, *, timeout: float = 1.0) -> None:
        """Wait for queued sends; intended for deterministic tests and shutdown checks."""
        async with self._lock:
            if ws is None:
                states = tuple(self._clients.values())
            else:
                state = self._clients.get(ws)
                states = () if state is None else (state,)
        if states:
            await asyncio.wait_for(
                asyncio.gather(*(state.queue.join() for state in states)),
                timeout=timeout,
            )

    async def _send_text(self, ws: Any, text: str) -> None:
        await asyncio.wait_for(
            ws.send_text(text),
            timeout=self.client_send_timeout_sec,
        )

    def _put_nowait(
        self,
        state: _ClientState,
        text: str,
        priority: int,
        *,
        completion: asyncio.Future | None = None,
    ) -> None:
        self._enqueue_sequence += 1
        state.queue.put_nowait(_QueuedMessage(
            priority=priority,
            sequence=self._enqueue_sequence,
            text=text,
            completion=completion,
        ))
        state.queue_high_watermark = max(state.queue_high_watermark, state.queue.qsize())
        self.client_queue_high_watermark = max(
            self.client_queue_high_watermark,
            state.queue_high_watermark,
        )

    @staticmethod
    def _settle_completion(
        item: _QueuedMessage,
        error: BaseException | None = None,
    ) -> None:
        if item.completion is None or item.completion.done():
            return
        if error is None:
            item.completion.set_result(None)
        else:
            item.completion.set_exception(error)

    def _fail_pending(self, state: _ClientState, error: BaseException) -> None:
        while True:
            try:
                item = state.queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            self._settle_completion(item, error)
            state.queue.task_done()

    async def _close_socket(self, ws: Any) -> None:
        close = getattr(ws, "close", None)
        if not callable(close):
            return
        try:
            result = close(code=1013)
            if inspect.isawaitable(result):
                await asyncio.wait_for(result, timeout=self.client_send_timeout_sec)
        except Exception:
            pass

    async def _client_writer(self, state: _ClientState) -> None:
        failure: BaseException | None = None
        close_socket = False
        cancelled = False
        try:
            while True:
                item = await state.queue.get()
                try:
                    await self._send_text(state.ws, item.text)
                except asyncio.CancelledError:
                    self._settle_completion(
                        item,
                        RuntimeError("client writer cancelled"),
                    )
                    cancelled = True
                    break
                except Exception as exc:
                    self._settle_completion(item, exc)
                    failure = exc
                    close_socket = True
                    break
                else:
                    self._settle_completion(item)
                finally:
                    state.queue.task_done()
        finally:
            state.closing = True
            async with self._lock:
                if self._clients.get(state.ws) is state:
                    self._clients.pop(state.ws, None)
            pending_error = failure or RuntimeError("client writer stopped")
            self._fail_pending(state, pending_error)
            if close_socket or state.close_socket_on_stop:
                await self._close_socket(state.ws)
        if cancelled:
            raise asyncio.CancelledError

    async def _stop_state(self, state: _ClientState, *, close_socket: bool) -> None:
        state.closing = True
        state.close_socket_on_stop = state.close_socket_on_stop or close_socket
        async with self._lock:
            if self._clients.get(state.ws) is state:
                self._clients.pop(state.ws, None)
        task = state.writer_task
        if task is not None and task is not asyncio.current_task() and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        elif task is None:
            self._fail_pending(state, RuntimeError("client writer stopped"))
            if close_socket:
                await self._close_socket(state.ws)

    async def _enqueue(self, text: str, priority: int) -> None:
        overflow: list[_ClientState] = []
        async with self._lock:
            states = tuple(self._clients.values())
            for state in states:
                if state.closing:
                    continue
                try:
                    self._put_nowait(state, text, priority)
                except asyncio.QueueFull:
                    state.closing = True
                    state.close_socket_on_stop = True
                    if self._clients.get(state.ws) is state:
                        self._clients.pop(state.ws, None)
                    overflow.append(state)
        if overflow:
            await asyncio.gather(
                *(self._stop_state(state, close_socket=True) for state in overflow),
                return_exceptions=True,
            )

    async def _broadcast(self, msg: dict) -> None:
        text = json.dumps(msg, separators=(",", ":"))
        if msg.get("type") == "MARKET_HEARTBEAT":
            await self._enqueue(text, _HEARTBEAT_PRIORITY)
            return
        async with self._enqueue_lock:
            await self._enqueue(text, _NORMAL_PRIORITY)

    async def on_trade(self, trade) -> None:
        published_at = datetime.now(timezone.utc)
        event_time = trade.event_time.astimezone(timezone.utc)
        source_age_ms = max(0, int((published_at - event_time).total_seconds() * 1000))
        message = envelope("TICK", trade.event_time, self.symbol, {
            "trade_id": int(trade.trade_id),
            "price": d2s(trade.price),
            "quantity": d2s(trade.quantity),
            "side": trade.side,
            "tick_delta": d2s(getattr(trade, "tick_delta", None)),
            "tick_cvd": d2s(getattr(trade, "tick_cvd", None)),
            "published_time": published_at.isoformat(),
            "source_age_ms": source_age_ms,
        })
        self._latest_tick_message = message
        await self._broadcast(message)

    async def on_spot_price(self, trade) -> None:
        """Broadcast a display-only Binance Spot reference without analytics wiring."""
        published_at = datetime.now(timezone.utc)
        source_time = trade.source_time.astimezone(timezone.utc)
        source_age_ms = max(
            0,
            int((published_at - source_time).total_seconds() * 1000),
        )
        message = envelope("SPOT_PRICE", source_time, self.symbol, {
            "source": "BINANCE_SPOT",
            "spot_symbol": trade.symbol,
            "trade_id": int(trade.trade_id),
            "price": d2s(trade.price),
            "quantity": d2s(trade.quantity),
            "event_time": source_time.isoformat(),
            "received_time": trade.received_time.astimezone(timezone.utc).isoformat(),
            "published_time": published_at.isoformat(),
            "source_age_ms": source_age_ms,
        })
        self._latest_spot_message = message
        await self._broadcast(message)

    async def on_tape_update(self, batch: TapeBatch) -> None:
        """Broadcast one ordered, bounded Time & Sales batch without caching it."""
        if batch.accepted_count != len(batch.trades) or not batch.trades:
            raise ValueError("TAPE_UPDATE accepted_count must match non-empty trades")
        if batch.dropped_count < 0:
            raise ValueError("TAPE_UPDATE dropped_count must be >= 0")
        sequences = tuple(trade.sequence for trade in batch.trades)
        if sequences != tuple(range(batch.first_sequence, batch.last_sequence + 1)):
            raise ValueError("TAPE_UPDATE batch sequences must be contiguous")
        message = envelope(
            "TAPE_UPDATE",
            batch.batch_time,
            self.symbol,
            {
                "batch_time": batch.batch_time.astimezone(timezone.utc).isoformat(),
                "stream_id": batch.stream_id,
                "first_sequence": batch.first_sequence,
                "last_sequence": batch.last_sequence,
                "accepted_count": batch.accepted_count,
                "dropped_count": batch.dropped_count,
                "trades": [
                    {
                        "sequence": trade.sequence,
                        "trade_id": trade.trade_id,
                        "event_time": trade.event_time.astimezone(
                            timezone.utc
                        ).isoformat(),
                        "price": d2s(trade.price),
                        "quantity": d2s(trade.quantity),
                        "notional": d2s(trade.notional),
                        "side": trade.side,
                    }
                    for trade in batch.trades
                ],
            },
        )
        await self._broadcast(message)
        self.tape_batches_broadcast += 1
        self.tape_trades_broadcast += batch.accepted_count

    async def on_book_update(self, projection: BookProjection) -> None:
        """Broadcast one bounded LIVE DOM projection and cache it for reconnect."""
        if projection.sync_state != SYNCED and projection.sync_state not in FAIL_CLOSED_STATES:
            raise ValueError(f"unknown book sync_state: {projection.sync_state}")
        synced = projection.sync_state == SYNCED
        if synced and (
            projection.best_bid is None
            or projection.best_ask is None
            or projection.spread is None
        ):
            raise ValueError("SYNCED BOOK_UPDATE requires best bid, best ask, and spread")
        book_sequence = self.book_updates_broadcast + 1
        bids = projection.bids if synced else ()
        asks = projection.asks if synced else ()
        message = envelope(
            "BOOK_UPDATE",
            projection.projection_time,
            self.symbol,
            {
                "book_stream_id": self.book_stream_id,
                "book_sequence": book_sequence,
                "event_time": (
                    projection.event_time.astimezone(timezone.utc).isoformat()
                    if projection.event_time is not None else None
                ),
                "projection_time": projection.projection_time.astimezone(
                    timezone.utc
                ).isoformat(),
                "last_update_id": projection.last_update_id,
                "sync_state": projection.sync_state,
                "bids": [
                    {"price": d2s(price), "qty": d2s(quantity)}
                    for price, quantity in bids
                ],
                "asks": [
                    {"price": d2s(price), "qty": d2s(quantity)}
                    for price, quantity in asks
                ],
                "depth_levels": projection.depth_levels,
                "best_bid": d2s(projection.best_bid) if synced else None,
                "best_ask": d2s(projection.best_ask) if synced else None,
                "spread": d2s(projection.spread) if synced else None,
                "age_ms": projection.age_ms,
            },
        )
        self._latest_book_message = message
        self.book_updates_broadcast = book_sequence
        if self.persistent_writer is not None:
            self.persistent_writer.append(message["payload"])
        await self._broadcast(message)

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

    async def on_absorption_state(
        self,
        event_time: datetime,
        result: Any | None,
        *,
        window_sec: int,
    ) -> None:
        """Broadcast the tick-time absorption state and cache it for late clients."""

        if window_sec <= 0:
            raise ValueError("window_sec must be > 0")
        classification = None if result is None else str(result.classification)
        if classification not in {None, "BUY_ABSORPTION", "SELL_ABSORPTION"}:
            raise ValueError(f"unsupported absorption classification: {classification}")
        payload = {
            "active": result is not None,
            "classification": classification,
            "strength": None if result is None else d2s(result.strength),
            "price_low": None if result is None else d2s(result.price_low),
            "price_high": None if result is None else d2s(result.price_high),
            "aggression_qty": None if result is None else d2s(getattr(result, "aggression_qty", None)),
            "threshold_qty": None if result is None else d2s(getattr(result, "threshold_qty", None)),
            "distinct_prices": None if result is None else int(getattr(result, "distinct_prices", 0)),
            "observed_at": event_time.astimezone(timezone.utc).isoformat(),
            "expires_at": (
                None
                if result is None
                else (event_time + timedelta(seconds=window_sec))
                .astimezone(timezone.utc)
                .isoformat()
            ),
            "window_sec": window_sec,
        }
        # Keep compatibility with older result objects used by integrations;
        # enriched evidence fields are sent when the detector provides them.
        if result is None or not hasattr(result, "aggression_qty"):
            payload.pop("aggression_qty", None)
            payload.pop("threshold_qty", None)
            payload.pop("distinct_prices", None)
        message = envelope("ABSORPTION_STATE", event_time, self.symbol, payload)
        self._latest_absorption_message = message
        await self._broadcast(message)

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

    async def send_market_heartbeat(self, event_time: datetime, payload: dict) -> None:
        """Broadcast a non-cached delivery heartbeat on the normal client path."""
        self.market_heartbeat_sequence += 1
        body = dict(payload)
        body["heartbeat_sequence"] = self.market_heartbeat_sequence
        body["published_time"] = event_time.astimezone(timezone.utc).isoformat()
        await self._broadcast(
            envelope("MARKET_HEARTBEAT", event_time, self.symbol, body)
        )

    async def send_health(self, event_time: datetime, payload: dict) -> None:
        """SelfMonitor v1 の HEALTH メッセージ (payload は直列化可能な dict)。"""
        await self._broadcast(envelope("HEALTH", event_time, self.symbol, payload))

    async def send_stats(self, event_time: datetime, stats: dict) -> None:
        await self._broadcast(envelope("STATS", event_time, self.symbol,
                                       {k: str(v) for k, v in stats.items()}))

    async def on_big_trades_update(self, message: dict[str, Any]) -> None:
        """Broadcast one strictly validated batch of committed records."""

        from webapp.big_trades_protocol import validate_big_trades_update

        validate_big_trades_update(message)
        if message["symbol"] != self.symbol:
            raise ValueError("BIG_TRADES_UPDATE symbol mismatch")
        await self._broadcast(message)

    async def on_big_trades_status(
        self,
        status: str,
        *,
        event_time: datetime | None = None,
        reason: str | None = None,
        counters: dict[str, Any] | None = None,
    ) -> None:
        """Cache status so reconnecting clients receive it before snapshots."""

        from webapp.big_trades_protocol import build_big_trades_status

        message = build_big_trades_status(
            symbol=self.symbol,
            status=status,
            event_time=event_time or datetime.now(timezone.utc),
            reason=reason,
            counters=counters,
        )
        self._latest_big_trades_status_message = message
        await self._broadcast(message)
