"""Record Binance bookTicker and HFM MT5 quotes on one local clock.

Run from the project root, then attach ``mt5/HFMQuoteObserver.mq5`` to the
desired HFM BTC chart. HFM quotes are read from MT5's FILE_COMMON folder, so
no socket permission is required. This tool never sends orders.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import os
import signal
import time
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event, Thread
from typing import Any

import websockets


LEGACY_HEADER = ["source", "symbol", "exchange_time_ms", "local_received_ns", "bid", "ask"]
HEADER = [*LEGACY_HEADER, "source_sequence"]
_WRITER_STOP = object()


class QuoteWriter:
    """Ordered background CSV writer for the observation-only collector.

    Disk flushes stay off the asyncio thread so the writer cannot delay reading
    the HFM bridge. Rows are stamped before enqueueing and written by one FIFO
    worker. Existing six-column recordings remain appendable; new recordings
    include source_sequence for MT5 bridge gap audits.
    """

    def __init__(
        self,
        path: Path,
        *,
        batch_size: int = 1000,
        flush_interval_ms: int = 100,
        queue_depth: int = 200_000,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        if flush_interval_ms < 1:
            raise ValueError("flush_interval_ms must be >= 1")
        if queue_depth < 1:
            raise ValueError("queue_depth must be >= 1")
        self.path = path
        self.batch_size = batch_size
        self.flush_interval_sec = flush_interval_ms / 1000.0
        self._queue: Queue[Any] = Queue(maxsize=queue_depth)
        self._ready = Event()
        self._error: BaseException | None = None
        self._closed = False
        self.rows_enqueued = 0
        self.rows_written = 0
        self.flushes = 0
        self.high_watermark = 0
        self.includes_source_sequence = True
        self._thread = Thread(
            target=self._run,
            name="hfm-observer-csv",
            daemon=True,
        )
        self._thread.start()
        if not self._ready.wait(timeout=10):
            raise RuntimeError("quote writer startup timed out")
        self._raise_if_failed()

    def _run(self) -> None:
        handle = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            existing_header: list[str] | None = None
            if self.path.exists() and self.path.stat().st_size:
                with self.path.open("r", newline="", encoding="utf-8") as existing:
                    existing_header = next(csv.reader(existing), None)
                if existing_header not in (HEADER, LEGACY_HEADER):
                    raise RuntimeError(
                        f"unsupported quote CSV header: {existing_header!r}"
                    )
            self.includes_source_sequence = existing_header != LEGACY_HEADER
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
        rows = pending if self.includes_source_sequence else [row[:6] for row in pending]
        writer.writerows(rows)
        handle.flush()
        self.rows_written += len(pending)
        self.flushes += 1
        pending.clear()

    def _raise_if_failed(self) -> None:
        if self._error is not None:
            raise RuntimeError(f"quote writer failed: {self._error}") from self._error

    def write(
        self,
        source: str,
        symbol: str,
        exchange_time_ms: int | None,
        bid: float,
        ask: float,
        *,
        received_ns: int | None = None,
        source_sequence: int | None = None,
    ) -> None:
        if not (math.isfinite(bid) and math.isfinite(ask) and bid > 0 and ask >= bid):
            return
        self._raise_if_failed()
        if self._closed:
            raise RuntimeError("quote writer is closed")
        received_ns = received_ns if received_ns is not None else time.time_ns()
        row = (
            source,
            symbol,
            exchange_time_ms or "",
            received_ns,
            bid,
            ask,
            source_sequence if source_sequence is not None else "",
        )
        try:
            self._queue.put_nowait(row)
        except Full as exc:
            raise RuntimeError(
                f"quote writer queue full (depth={self._queue.maxsize})"
            ) from exc
        self.rows_enqueued += 1
        self.high_watermark = max(self.high_watermark, self._queue.qsize())

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
            raise RuntimeError("quote writer shutdown timed out")
        self._raise_if_failed()


def default_hfm_file() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA is not available; pass --hfm-file explicitly")
    return (
        Path(appdata)
        / "MetaQuotes"
        / "Terminal"
        / "Common"
        / "Files"
        / "DeltaEngineClone_HFM_quotes_utf8.jsonl"
    )


async def run_hfm_file(
    path: Path, quote_writer: QuoteWriter, stop: asyncio.Event, poll_ms: int
) -> None:
    """Tail the MT5 FILE_COMMON quote stream without requiring socket permission."""
    offset = path.stat().st_size if path.exists() else 0
    pending = ""
    announced = False
    while not stop.is_set():
        try:
            if not path.exists():
                await asyncio.wait_for(stop.wait(), timeout=poll_ms / 1000.0)
                continue
            size = path.stat().st_size
            if size < offset:
                offset = 0
                pending = ""
            if size == offset:
                await asyncio.wait_for(stop.wait(), timeout=poll_ms / 1000.0)
                continue
            with path.open("r", encoding="utf-8") as handle:
                handle.seek(offset)
                chunk = handle.read()
                offset = handle.tell()
            if not announced:
                print(f"Reading HFM quotes from {path}")
                announced = True
            pending += chunk
            lines = pending.split("\n")
            pending = lines.pop()
            for line in lines:
                received_ns = time.time_ns()
                try:
                    message: dict[str, Any] = json.loads(line)
                    bid, ask = float(message["bid"]), float(message["ask"])
                    server_time = message.get("server_time_msc")
                    exchange_time_ms = (
                        int(server_time) if server_time not in (None, "") else None
                    )
                    sequence = message.get("sequence")
                    source_sequence = (
                        int(sequence) if sequence not in (None, "") else None
                    )
                    quote_writer.write(
                        "HFM",
                        str(message.get("symbol", "")),
                        exchange_time_ms,
                        bid,
                        ask,
                        received_ns=received_ns,
                        source_sequence=source_sequence,
                    )
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    continue
        except asyncio.TimeoutError:
            continue
        except (OSError, UnicodeError) as exc:
            print(f"HFM file retrying after: {exc}")
            await asyncio.sleep(1.0)


async def run_binance(symbol: str, quote_writer: QuoteWriter, stop: asyncio.Event) -> None:
    url = f"wss://fstream.binance.com/ws/{symbol.lower()}@bookTicker"
    while not stop.is_set():
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=20) as websocket:
                async for raw in websocket:
                    message = json.loads(raw)
                    quote_writer.write(
                        "BINANCE", symbol.upper(), int(message.get("E", 0)) or None,
                        float(message["b"]), float(message["a"]),
                    )
                    if stop.is_set():
                        return
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # network reconnect loop
            print(f"Binance reconnecting after: {exc}")
            try:
                await asyncio.wait_for(stop.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                pass


async def main_async(args: argparse.Namespace) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for name in ("SIGINT", "SIGTERM"):
        if hasattr(signal, name):
            try:
                loop.add_signal_handler(getattr(signal, name), stop.set)
            except NotImplementedError:
                pass

    quote_writer = QuoteWriter(
        args.output,
        batch_size=args.writer_batch_size,
        flush_interval_ms=args.writer_flush_ms,
        queue_depth=args.writer_queue_depth,
    )
    binance_task = asyncio.create_task(run_binance(args.symbol, quote_writer, stop))
    hfm_task = asyncio.create_task(
        run_hfm_file(args.hfm_file, quote_writer, stop, args.poll_ms)
    )
    duration_task = (
        asyncio.create_task(asyncio.sleep(args.duration_sec))
        if args.duration_sec is not None else None
    )
    print("Observation only; no orders.")
    print(f"HFM common file: {args.hfm_file}")
    print(f"Writing {args.output}. Press Ctrl+C to stop.")
    try:
        if duration_task is None:
            await stop.wait()
        else:
            await duration_task
            stop.set()
    except KeyboardInterrupt:
        stop.set()
    finally:
        binance_task.cancel()
        hfm_task.cancel()
        tasks = [binance_task, hfm_task]
        if duration_task is not None:
            if not duration_task.done():
                duration_task.cancel()
            tasks.append(duration_task)
        await asyncio.gather(*tasks, return_exceptions=True)
        quote_writer.close()
        print(
            "Quote writer: "
            f"rows={quote_writer.rows_written}, flushes={quote_writer.flushes}, "
            f"queue_high={quote_writer.high_watermark}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--hfm-file", type=Path, default=default_hfm_file())
    parser.add_argument("--poll-ms", type=int, default=10)
    parser.add_argument("--writer-batch-size", type=int, default=1000)
    parser.add_argument("--writer-flush-ms", type=int, default=100)
    parser.add_argument("--writer-queue-depth", type=int, default=200_000)
    parser.add_argument("--duration-sec", type=float)
    parser.add_argument("--output", type=Path, default=Path("data_clone/latency/quotes.csv"))
    args = parser.parse_args()
    if args.poll_ms < 1:
        parser.error("--poll-ms must be >= 1")
    if args.writer_batch_size < 1:
        parser.error("--writer-batch-size must be >= 1")
    if args.writer_flush_ms < 1:
        parser.error("--writer-flush-ms must be >= 1")
    if args.writer_queue_depth < 1:
        parser.error("--writer-queue-depth must be >= 1")
    if args.duration_sec is not None and args.duration_sec <= 0:
        parser.error("--duration-sec must be > 0")
    return args


if __name__ == "__main__":
    try:
        asyncio.run(main_async(parse_args()))
    except KeyboardInterrupt:
        pass
