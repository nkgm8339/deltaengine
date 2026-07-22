"""Measure direct Binance trade arrival against DeltaEngine browser delivery.

The tool opens two independent WebSockets on one local clock:

* Binance USD-M Futures BTCUSDT trade stream
* DeltaEngine's local /ws endpoint

Trade IDs added to TICK/BAR_UPDATE payloads make the comparison exact. Positive
internal_ms means DeltaEngine arrived after the same trade on the direct
Binance connection. The tool is observation-only and never sends an order.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from typing import Any

import websockets


@dataclass(frozen=True)
class Arrival:
    wall_ns: int
    monotonic_ns: int
    price: float
    exchange_time_ms: int | None = None


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _summary(values: list[float]) -> dict[str, float | int | None]:
    return {
        "count": len(values),
        "mean": fmean(values) if values else None,
        "median": _percentile(values, 0.5),
        "p95": _percentile(values, 0.95),
        "p99": _percentile(values, 0.99),
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
    }


class LatencyCollector:
    def __init__(self, max_pending: int = 100_000) -> None:
        self.max_pending = max_pending
        self.direct: dict[int, Arrival] = {}
        self.pending_ticks: dict[int, Arrival] = {}
        self.pending_bars: dict[int, Arrival] = {}
        self.tick_rows: list[dict[str, Any]] = []
        self.bar_rows: list[dict[str, Any]] = []
        self.direct_count = 0
        self.delta_tick_count = 0
        self.delta_bar_count = 0

    @staticmethod
    def _arrival(price: Any, exchange_time_ms: int | None = None) -> Arrival:
        return Arrival(
            wall_ns=time.time_ns(),
            monotonic_ns=time.perf_counter_ns(),
            price=float(price),
            exchange_time_ms=exchange_time_ms,
        )

    def on_direct(self, message: dict[str, Any]) -> None:
        if message.get("e") != "trade":
            return
        try:
            trade_id = int(message["t"])
            exchange_ms = int(message["E"])
            arrival = self._arrival(message["p"], exchange_ms)
        except (KeyError, TypeError, ValueError):
            return
        self.direct_count += 1
        self.direct[trade_id] = arrival
        self._match(trade_id, self.pending_ticks, self.tick_rows, "tick")
        self._match(trade_id, self.pending_bars, self.bar_rows, "bar")
        while len(self.direct) > self.max_pending:
            self.direct.pop(next(iter(self.direct)))

    def on_delta(self, message: dict[str, Any]) -> None:
        payload = message.get("payload") or {}
        msg_type = message.get("type")
        try:
            if msg_type == "TICK":
                trade_id = int(payload["trade_id"])
                arrival = self._arrival(payload["price"])
                self.delta_tick_count += 1
                self.pending_ticks[trade_id] = arrival
                self._match(trade_id, self.pending_ticks, self.tick_rows, "tick")
            elif msg_type == "BAR_UPDATE" and payload.get("source_trade_id") is not None:
                trade_id = int(payload["source_trade_id"])
                arrival = self._arrival(payload["close"])
                self.delta_bar_count += 1
                self.pending_bars[trade_id] = arrival
                self._match(trade_id, self.pending_bars, self.bar_rows, "bar")
        except (KeyError, TypeError, ValueError):
            return
        while len(self.pending_ticks) > self.max_pending:
            self.pending_ticks.pop(next(iter(self.pending_ticks)))
        while len(self.pending_bars) > self.max_pending:
            self.pending_bars.pop(next(iter(self.pending_bars)))

    def _match(
        self,
        trade_id: int,
        pending: dict[int, Arrival],
        rows: list[dict[str, Any]],
        kind: str,
    ) -> None:
        direct = self.direct.get(trade_id)
        delta = pending.get(trade_id)
        if direct is None or delta is None:
            return
        pending.pop(trade_id, None)
        exchange_ms = direct.exchange_time_ms
        rows.append({
            "kind": kind,
            "trade_id": trade_id,
            "price": delta.price,
            "direct_price": direct.price,
            "exchange_time_ms": exchange_ms,
            "direct_received_ns": direct.wall_ns,
            "delta_received_ns": delta.wall_ns,
            "internal_ms": (
                delta.monotonic_ns - direct.monotonic_ns
            ) / 1_000_000.0,
            "direct_network_age_ms": (
                direct.wall_ns / 1_000_000.0 - exchange_ms
                if exchange_ms is not None else None
            ),
            "delta_total_age_ms": (
                delta.wall_ns / 1_000_000.0 - exchange_ms
                if exchange_ms is not None else None
            ),
        })

    def report(self, duration_sec: float) -> dict[str, Any]:
        def values(rows: list[dict[str, Any]], key: str) -> list[float]:
            return [
                float(row[key])
                for row in rows
                if row.get(key) is not None and math.isfinite(float(row[key]))
            ]

        return {
            "measured_at": datetime.now(timezone.utc).isoformat(),
            "duration_sec": duration_sec,
            "method": {
                "clock": "one local process; time.perf_counter_ns for feed-to-feed delta",
                "sign": "positive internal_ms means DeltaEngine followed direct Binance",
                "matching": "exact Binance individual trade_id",
            },
            "counts": {
                "direct_binance_trades": self.direct_count,
                "delta_ticks_received": self.delta_tick_count,
                "delta_bar_updates_received": self.delta_bar_count,
                "matched_ticks": len(self.tick_rows),
                "matched_bar_updates": len(self.bar_rows),
            },
            "tick_internal_ms": _summary(values(self.tick_rows, "internal_ms")),
            "bar_update_internal_ms": _summary(values(self.bar_rows, "internal_ms")),
            "direct_binance_network_age_ms": _summary(
                values(self.tick_rows, "direct_network_age_ms")
            ),
            "delta_tick_total_age_ms": _summary(
                values(self.tick_rows, "delta_total_age_ms")
            ),
            "delta_bar_total_age_ms": _summary(
                values(self.bar_rows, "delta_total_age_ms")
            ),
            "tick_rows": self.tick_rows,
            "bar_rows": self.bar_rows,
        }


async def _receive_binance(url: str, collector: LatencyCollector) -> None:
    async with websockets.connect(url, ping_interval=20, ping_timeout=20) as websocket:
        async for raw in websocket:
            collector.on_direct(json.loads(raw))


async def _receive_delta(url: str, collector: LatencyCollector) -> None:
    async with websockets.connect(url, ping_interval=20, ping_timeout=20) as websocket:
        async for raw in websocket:
            collector.on_delta(json.loads(raw))


async def measure(args: argparse.Namespace) -> dict[str, Any]:
    collector = LatencyCollector()
    direct_task = asyncio.create_task(_receive_binance(args.binance_url, collector))
    delta_task = asyncio.create_task(_receive_delta(args.delta_url, collector))
    timer = asyncio.create_task(asyncio.sleep(args.duration_sec))
    tasks = {direct_task, delta_task, timer}
    done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    try:
        if timer not in done:
            failed = next(task for task in done if task is not timer)
            failed.result()
            raise RuntimeError("latency receiver stopped unexpectedly")
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    return collector.report(args.duration_sec)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-sec", type=float, default=120.0)
    parser.add_argument(
        "--binance-url",
        default="wss://fstream.binance.com/ws/btcusdt@trade",
    )
    parser.add_argument("--delta-url", default="ws://127.0.0.1:8080/ws")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/latency/internal_latency_after_brushup.json"),
    )
    args = parser.parse_args()
    if args.duration_sec <= 0:
        parser.error("--duration-sec must be greater than zero")
    return args


def main() -> None:
    args = parse_args()
    report = asyncio.run(measure(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    concise = {key: value for key, value in report.items() if not key.endswith("_rows")}
    print(json.dumps(concise, ensure_ascii=False, indent=2))
    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
