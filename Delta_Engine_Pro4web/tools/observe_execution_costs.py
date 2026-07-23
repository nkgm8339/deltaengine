"""Record public executable quotes from candidate BTC venues on one clock.

This process is deliberately observation-only.  It connects only to public
market-data streams and tails optional MT5 quote files.  It has no credentials,
private API client, position model, or order-sending function.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import os
import signal
import ssl
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event, Thread
from typing import Any, Callable

import websockets
import certifi


HEADER = [
    "source",
    "instrument",
    "quote_currency",
    "exchange_time_ms",
    "local_received_ns",
    "bid",
    "ask",
    "source_sequence",
]
_WRITER_STOP = object()
PUBLIC_TLS_CONTEXT = ssl.create_default_context(cafile=certifi.where())


def _iso_time_ms(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def parse_binance_message(message: dict[str, Any], symbol: str) -> tuple[str, str, int | None, float, float]:
    return (
        symbol.upper(),
        "USDT",
        int(message.get("E", 0)) or None,
        float(message["b"]),
        float(message["a"]),
    )


def parse_bitflyer_message(
    message: dict[str, Any], channel: str, product: str
) -> tuple[str, str, int | None, float, float] | None:
    if message.get("method") != "channelMessage":
        return None
    params = message.get("params") or {}
    if params.get("channel") != channel:
        return None
    ticker = params.get("message") or {}
    return (
        product,
        "JPY",
        _iso_time_ms(ticker.get("timestamp")),
        float(ticker["best_bid"]),
        float(ticker["best_ask"]),
    )


def parse_gmo_message(
    message: dict[str, Any], symbol: str
) -> tuple[str, str, int | None, float, float] | None:
    if message.get("channel") != "ticker" or message.get("symbol") != symbol:
        return None
    return (
        symbol,
        "JPY",
        _iso_time_ms(message.get("timestamp")),
        float(message["bid"]),
        float(message["ask"]),
    )


def parse_hfm_line(
    line: str,
) -> tuple[tuple[str, str, int | None, float, float], int | None]:
    # Two MT5 observers writing the same FILE_COMMON stream can leave an extra
    # opening brace.  That defect is unambiguous and safely recoverable; other
    # malformed records stay rejected and visible in health counters.
    payload = line.strip()
    if payload.startswith('{{"'):
        payload = payload[1:]
    message: dict[str, Any] = json.loads(payload)
    server_time = message.get("server_time_msc")
    sequence = message.get("sequence")
    return (
        (
            str(message.get("symbol", "")),
            "USD",
            int(server_time) if server_time not in (None, "") else None,
            float(message["bid"]),
            float(message["ask"]),
        ),
        int(sequence) if sequence not in (None, "") else None,
    )


class MarketQuoteWriter:
    """Write validated quotes in arrival order without blocking feed readers."""

    def __init__(
        self,
        path: Path,
        *,
        batch_size: int = 1000,
        flush_interval_ms: int = 100,
        queue_depth: int = 200_000,
    ) -> None:
        if batch_size < 1 or flush_interval_ms < 1 or queue_depth < 1:
            raise ValueError("writer sizes and intervals must be >= 1")
        self.path = path
        self.batch_size = batch_size
        self.flush_interval_sec = flush_interval_ms / 1000.0
        self._queue: Queue[Any] = Queue(maxsize=queue_depth)
        self._ready = Event()
        self._error: BaseException | None = None
        self._closed = False
        self.rows_written = 0
        self.flushes = 0
        self.high_watermark = 0
        self._thread = Thread(target=self._run, name="execution-cost-csv", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=10):
            raise RuntimeError("market quote writer startup timed out")
        self._raise_if_failed()

    def _run(self) -> None:
        handle = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists() and self.path.stat().st_size:
                with self.path.open("r", newline="", encoding="utf-8") as existing:
                    header = next(csv.reader(existing), None)
                if header != HEADER:
                    raise RuntimeError(f"unsupported cost-observer CSV header: {header!r}")
            handle = self.path.open("a", newline="", encoding="utf-8")
            writer = csv.writer(handle)
            if self.path.stat().st_size == 0:
                writer.writerow(HEADER)
                handle.flush()
            self._ready.set()
            pending: list[tuple[Any, ...]] = []
            flush_deadline = time.monotonic() + self.flush_interval_sec
            while True:
                timeout = max(0.0, flush_deadline - time.monotonic())
                try:
                    row = self._queue.get(timeout=timeout)
                except Empty:
                    row = None
                if row is _WRITER_STOP:
                    self._flush(writer, handle, pending)
                    break
                if row is not None:
                    pending.append(row)
                if len(pending) >= self.batch_size or time.monotonic() >= flush_deadline:
                    self._flush(writer, handle, pending)
                    flush_deadline = time.monotonic() + self.flush_interval_sec
        except BaseException as exc:
            self._error = exc
            self._ready.set()
        finally:
            if handle is not None:
                handle.close()

    def _flush(self, writer: Any, handle: Any, pending: list[tuple[Any, ...]]) -> None:
        if not pending:
            return
        writer.writerows(pending)
        handle.flush()
        self.rows_written += len(pending)
        self.flushes += 1
        pending.clear()

    def _raise_if_failed(self) -> None:
        if self._error is not None:
            raise RuntimeError(f"market quote writer failed: {self._error}") from self._error

    def write(
        self,
        source: str,
        instrument: str,
        quote_currency: str,
        exchange_time_ms: int | None,
        bid: float,
        ask: float,
        *,
        received_ns: int | None = None,
        source_sequence: int | None = None,
    ) -> bool:
        if not (math.isfinite(bid) and math.isfinite(ask) and bid > 0 and ask >= bid):
            return False
        self._raise_if_failed()
        if self._closed:
            raise RuntimeError("market quote writer is closed")
        row = (
            source,
            instrument,
            quote_currency,
            exchange_time_ms or "",
            received_ns if received_ns is not None else time.time_ns(),
            bid,
            ask,
            source_sequence if source_sequence is not None else "",
        )
        try:
            self._queue.put_nowait(row)
        except Full as exc:
            raise RuntimeError(
                f"market quote writer queue full (depth={self._queue.maxsize})"
            ) from exc
        self.high_watermark = max(self.high_watermark, self._queue.qsize())
        return True

    def close(self) -> None:
        if self._closed:
            self._raise_if_failed()
            return
        self._closed = True
        while True:
            self._raise_if_failed()
            try:
                self._queue.put(_WRITER_STOP, timeout=0.1)
                break
            except Full:
                continue
        self._thread.join(timeout=30)
        if self._thread.is_alive():
            raise RuntimeError("market quote writer shutdown timed out")
        self._raise_if_failed()


@dataclass
class SourceHealth:
    rows: int = 0
    reconnects: int = 0
    invalid_messages: int = 0
    duplicate_messages: int = 0
    last_received_ns: int | None = None
    last_error: str | None = None


@dataclass
class ObserverHealth:
    started_at: str
    output: str
    sources: dict[str, SourceHealth] = field(default_factory=dict)
    final_report: str | None = None
    report_error: str | None = None

    def source(self, name: str) -> SourceHealth:
        return self.sources.setdefault(name, SourceHealth())


def _record(
    writer: MarketQuoteWriter,
    health: ObserverHealth,
    source: str,
    parsed: tuple[str, str, int | None, float, float],
    *,
    received_ns: int | None = None,
    source_sequence: int | None = None,
) -> None:
    instrument, quote_currency, exchange_time_ms, bid, ask = parsed
    received_ns = received_ns if received_ns is not None else time.time_ns()
    state = health.source(source)
    if writer.write(
        source,
        instrument,
        quote_currency,
        exchange_time_ms,
        bid,
        ask,
        received_ns=received_ns,
        source_sequence=source_sequence,
    ):
        state.rows += 1
        state.last_received_ns = received_ns


async def _reconnect_delay(stop: asyncio.Event, seconds: float = 2.0) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


async def run_binance(
    symbol: str, writer: MarketQuoteWriter, health: ObserverHealth, stop: asyncio.Event
) -> None:
    source = "BINANCE_SENSOR"
    url = f"wss://fstream.binance.com/ws/{symbol.lower()}@bookTicker"
    while not stop.is_set():
        try:
            async with websockets.connect(
                url, ssl=PUBLIC_TLS_CONTEXT, ping_interval=20, ping_timeout=20
            ) as websocket:
                async for raw in websocket:
                    received_ns = time.time_ns()
                    _record(
                        writer,
                        health,
                        source,
                        parse_binance_message(json.loads(raw), symbol),
                        received_ns=received_ns,
                    )
                    if stop.is_set():
                        return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            state = health.source(source)
            state.reconnects += 1
            state.last_error = str(exc)[:500]
            await _reconnect_delay(stop)


async def run_bitflyer(
    product: str, writer: MarketQuoteWriter, health: ObserverHealth, stop: asyncio.Event
) -> None:
    source = "BITFLYER_CFD"
    channel = f"lightning_ticker_{product}"
    url = "wss://ws.lightstream.bitflyer.com/json-rpc"
    subscription = {"method": "subscribe", "params": {"channel": channel}, "id": 1}
    while not stop.is_set():
        try:
            async with websockets.connect(
                url, ssl=PUBLIC_TLS_CONTEXT, ping_interval=20, ping_timeout=20
            ) as websocket:
                await websocket.send(json.dumps(subscription, separators=(",", ":")))
                async for raw in websocket:
                    received_ns = time.time_ns()
                    try:
                        parsed = parse_bitflyer_message(json.loads(raw), channel, product)
                        if parsed is not None:
                            _record(writer, health, source, parsed, received_ns=received_ns)
                    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                        health.source(source).invalid_messages += 1
                    if stop.is_set():
                        return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            state = health.source(source)
            state.reconnects += 1
            state.last_error = str(exc)[:500]
            await _reconnect_delay(stop)


async def run_gmo(
    symbol: str, writer: MarketQuoteWriter, health: ObserverHealth, stop: asyncio.Event
) -> None:
    source = "GMO_LEVERAGE"
    url = "wss://api.coin.z.com/ws/public/v1"
    subscription = {"command": "subscribe", "channel": "ticker", "symbol": symbol}
    while not stop.is_set():
        try:
            async with websockets.connect(
                url, ssl=PUBLIC_TLS_CONTEXT, ping_interval=20, ping_timeout=20
            ) as websocket:
                await websocket.send(json.dumps(subscription, separators=(",", ":")))
                async for raw in websocket:
                    received_ns = time.time_ns()
                    try:
                        parsed = parse_gmo_message(json.loads(raw), symbol)
                        if parsed is not None:
                            _record(writer, health, source, parsed, received_ns=received_ns)
                    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                        health.source(source).invalid_messages += 1
                    if stop.is_set():
                        return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            state = health.source(source)
            state.reconnects += 1
            state.last_error = str(exc)[:500]
            await _reconnect_delay(stop)


async def run_hfm_file(
    source: str,
    path: Path,
    writer: MarketQuoteWriter,
    health: ObserverHealth,
    stop: asyncio.Event,
    poll_ms: int,
) -> None:
    """Tail one MT5 FILE_COMMON stream; absence is reported but is not fatal."""
    offset = path.stat().st_size if path.exists() else 0
    pending = ""
    state = health.source(source)
    previous_signature: tuple[Any, ...] | None = None
    while not stop.is_set():
        try:
            if not path.exists():
                state.last_error = f"waiting for MT5 quote file: {path}"
                await asyncio.wait_for(stop.wait(), timeout=poll_ms / 1000.0)
                continue
            size = path.stat().st_size
            if size < offset:
                offset, pending = 0, ""
            if size == offset:
                await asyncio.wait_for(stop.wait(), timeout=poll_ms / 1000.0)
                continue
            with path.open("r", encoding="utf-8") as handle:
                handle.seek(offset)
                chunk = handle.read()
                offset = handle.tell()
            pending += chunk
            lines = pending.split("\n")
            pending = lines.pop()
            for line in lines:
                received_ns = time.time_ns()
                try:
                    parsed, sequence = parse_hfm_line(line)
                    signature = (*parsed[2:], sequence)
                    if signature == previous_signature:
                        state.duplicate_messages += 1
                        continue
                    previous_signature = signature
                    _record(
                        writer,
                        health,
                        source,
                        parsed,
                        received_ns=received_ns,
                        source_sequence=sequence,
                    )
                    state.last_error = None
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    state.invalid_messages += 1
        except asyncio.TimeoutError:
            continue
        except (OSError, UnicodeError) as exc:
            state.reconnects += 1
            state.last_error = str(exc)[:500]
            await _reconnect_delay(stop, 1.0)


def _health_payload(health: ObserverHealth, writer: MarketQuoteWriter, *, completed: bool) -> dict[str, Any]:
    now_ns = time.time_ns()
    return {
        "observation_only": True,
        "completed": completed,
        "started_at": health.started_at,
        "updated_at": datetime.now().astimezone().isoformat(),
        "output": health.output,
        "final_report": health.final_report,
        "report_error": health.report_error,
        "writer": {
            "rows": writer.rows_written,
            "flushes": writer.flushes,
            "queue_high_watermark": writer.high_watermark,
        },
        "sources": {
            name: {
                "rows": state.rows,
                "reconnects": state.reconnects,
                "invalid_messages": state.invalid_messages,
                "duplicate_messages": state.duplicate_messages,
                "age_sec": (
                    round((now_ns - state.last_received_ns) / 1_000_000_000, 3)
                    if state.last_received_ns is not None
                    else None
                ),
                "last_error": state.last_error,
            }
            for name, state in sorted(health.sources.items())
        },
    }


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


async def write_status(
    path: Path,
    health: ObserverHealth,
    writer: MarketQuoteWriter,
    stop: asyncio.Event,
    interval_sec: float,
) -> None:
    while not stop.is_set():
        _atomic_json(path, _health_payload(health, writer, completed=False))
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_sec)
        except asyncio.TimeoutError:
            pass


def default_hfm_path(filename: str) -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA is not available; pass --hfm-source explicitly")
    return Path(appdata) / "MetaQuotes" / "Terminal" / "Common" / "Files" / filename


def parse_hfm_source(value: str) -> tuple[str, Path]:
    try:
        source, raw_path = value.split("=", 1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use SOURCE=PATH for --hfm-source") from exc
    source = source.strip().upper()
    if not source.startswith("HFM_") or not raw_path.strip():
        raise argparse.ArgumentTypeError("HFM source must be named HFM_*=PATH")
    return source, Path(raw_path.strip())


async def main_async(args: argparse.Namespace) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for name in ("SIGINT", "SIGTERM"):
        if hasattr(signal, name):
            try:
                loop.add_signal_handler(getattr(signal, name), stop.set)
            except NotImplementedError:
                pass

    args.pid_file.parent.mkdir(parents=True, exist_ok=True)
    args.pid_file.write_text(str(os.getpid()), encoding="ascii")
    writer = MarketQuoteWriter(
        args.output,
        batch_size=args.writer_batch_size,
        flush_interval_ms=args.writer_flush_ms,
        queue_depth=args.writer_queue_depth,
    )
    health = ObserverHealth(
        started_at=datetime.now().astimezone().isoformat(),
        output=str(args.output.resolve()),
    )
    tasks = [
        asyncio.create_task(run_binance(args.binance_symbol, writer, health, stop)),
        asyncio.create_task(run_bitflyer(args.bitflyer_product, writer, health, stop)),
        asyncio.create_task(run_gmo(args.gmo_symbol, writer, health, stop)),
    ]
    for source, path in args.hfm_source:
        tasks.append(
            asyncio.create_task(run_hfm_file(source, path, writer, health, stop, args.poll_ms))
        )
    tasks.append(
        asyncio.create_task(write_status(args.status, health, writer, stop, args.status_interval_sec))
    )

    duration_task = asyncio.create_task(asyncio.sleep(args.duration_sec))
    print("Observation only; public market data and local MT5 quote files; no orders.")
    print(f"Writing {args.output.resolve()}")
    try:
        await duration_task
        stop.set()
    except KeyboardInterrupt:
        stop.set()
    finally:
        for task in tasks:
            task.cancel()
        if not duration_task.done():
            duration_task.cancel()
        await asyncio.gather(*tasks, duration_task, return_exceptions=True)
        writer.close()
        try:
            from tools.report_execution_costs import build_report

            report = build_report(args.output, args.cost_config)
            _atomic_json(args.report_output, report)
            health.final_report = str(args.report_output.resolve())
        except Exception as exc:
            health.report_error = str(exc)[:1000]
        _atomic_json(args.status, _health_payload(health, writer, completed=True))
        if args.pid_file.exists():
            args.pid_file.unlink()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-sec", type=float, default=86_400)
    parser.add_argument("--output", type=Path, default=Path(f"data_clone/execution_costs/quotes_{stamp}.csv"))
    parser.add_argument("--status", type=Path, default=Path("data_clone/execution_costs/status.json"))
    parser.add_argument("--pid-file", type=Path, default=Path("data_clone/execution_costs/observer_clone.pid"))
    parser.add_argument("--cost-config", type=Path, default=Path("config/execution_costs.yaml"))
    parser.add_argument(
        "--report-output",
        type=Path,
        default=Path(f"data_clone/execution_costs/report_{stamp}.json"),
    )
    parser.add_argument("--status-interval-sec", type=float, default=10.0)
    parser.add_argument("--poll-ms", type=int, default=10)
    parser.add_argument("--writer-batch-size", type=int, default=1000)
    parser.add_argument("--writer-flush-ms", type=int, default=100)
    parser.add_argument("--writer-queue-depth", type=int, default=200_000)
    parser.add_argument("--binance-symbol", default="BTCUSDT")
    parser.add_argument("--bitflyer-product", default="FX_BTC_JPY")
    parser.add_argument("--gmo-symbol", default="BTC_JPY")
    parser.add_argument("--hfm-source", action="append", type=parse_hfm_source)
    args = parser.parse_args(argv)
    if args.duration_sec <= 0 or args.status_interval_sec <= 0 or args.poll_ms < 1:
        parser.error("durations and intervals must be positive")
    if args.writer_batch_size < 1 or args.writer_flush_ms < 1 or args.writer_queue_depth < 1:
        parser.error("writer sizes and intervals must be positive")
    if args.hfm_source is None:
        args.hfm_source = [
            ("HFM_CURRENT", default_hfm_path("DeltaEngineClone_HFM_quotes_utf8.jsonl")),
            ("HFM_INFINITYX", default_hfm_path("DeltaEngineClone_HFM_InfinityX_quotes_utf8.jsonl")),
        ]
    names = [source for source, _ in args.hfm_source]
    if len(names) != len(set(names)):
        parser.error("--hfm-source names must be unique")
    return args


if __name__ == "__main__":
    try:
        asyncio.run(main_async(parse_args()))
    except KeyboardInterrupt:
        pass
