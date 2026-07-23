"""Storage module (MOD-003) — batched Parquet + DuckDB persistence.

Spec: docs/30_Modules/Database_v3.2.md (§5 Storage Policy, §6 Config Parameters).
Schemas: docs/40_Reference/ParquetSchema_v3.1.md, DuckDBDDL_v3.1.md.
Errors: docs/40_Reference/ErrorCodes_v3.1.md (E4001/E4002/E4003).

Write is triggered by whichever comes first (Database §6): `batch_size` records
accumulated, or `flush_interval_sec` elapsed. The clock is injected so the
interval trigger is deterministically testable. Parquet is the canonical store
(Snappy, UTC, partitioned symbol[/timeframe]/year/month/day); DuckDB is the
analytical mirror. No silent loss: duplicate-primary-key rows are counted/logged.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event, Thread
from typing import Any, Callable, Optional

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from .schema import (
    CANDLES_DDL,
    CANDLES_SCHEMA,
    FLOW_RESPONSE_EVENTS_DDL,
    FLOW_RESPONSE_EVENTS_SCHEMA,
    FLOW_RESPONSE_OUTCOMES_DDL,
    FLOW_RESPONSE_OUTCOMES_SCHEMA,
    OPEN_INTEREST_SAMPLES_DDL,
    OPEN_INTEREST_SAMPLES_SCHEMA,
    SIGNALS_DDL,
    SIGNALS_SCHEMA,
    TRADES_DDL,
    TRADES_SCHEMA,
)

logger = logging.getLogger("database.storage")

ERROR_PARQUET_WRITE = "E4001"
ERROR_DUCKDB_WRITE = "E4002"
ERROR_STORAGE_UNAVAILABLE = "E4003"


class StorageError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"[{code}] {message}")


def _partition_dir(base: Path, symbol: str, when: datetime, timeframe: str | None = None) -> Path:
    """Hive-style partition path: symbol[/timeframe]/year/month/day (ParquetSchema §2/§6)."""
    parts = [f"symbol={symbol}"]
    if timeframe is not None:
        parts.append(f"timeframe={timeframe}")
    parts += [f"year={when.year:04d}", f"month={when.month:02d}", f"day={when.day:02d}"]
    return base.joinpath(*parts)


class DuckDbWriter:
    """DuckDB analytical mirror. Creates tables and inserts batches idempotently."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        try:
            self._con = duckdb.connect(self.db_path)
        except Exception as exc:  # noqa: BLE001 - surface as storage-unavailable
            raise StorageError(ERROR_STORAGE_UNAVAILABLE, f"cannot open DuckDB: {exc}") from exc
        # Pin the session to UTC so tz-aware timestamps land in the naive
        # TIMESTAMP columns as UTC wall-clock, independent of machine timezone
        # (UTC-only storage per Database §5 / ParquetSchema §2; and determinism).
        self._con.execute("SET TimeZone='UTC'")
        self._con.execute(TRADES_DDL)
        self._con.execute(CANDLES_DDL)
        self._con.execute(SIGNALS_DDL)
        self._con.execute(FLOW_RESPONSE_EVENTS_DDL)
        self._con.execute(FLOW_RESPONSE_OUTCOMES_DDL)
        self._con.execute(OPEN_INTEREST_SAMPLES_DDL)
        self.duplicates = 0

    def _insert(self, table: str, arrow_table: pa.Table) -> int:
        before = self._con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        self._con.register("_batch", arrow_table)
        try:
            # ON CONFLICT DO NOTHING dedups on the primary key; skipped rows are
            # counted below (never silently dropped).
            self._con.execute(f"INSERT INTO {table} SELECT * FROM _batch ON CONFLICT DO NOTHING")
        except Exception as exc:  # noqa: BLE001
            raise StorageError(ERROR_DUCKDB_WRITE, f"{table} insert failed: {exc}") from exc
        finally:
            self._con.unregister("_batch")
        after = self._con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        inserted = after - before
        skipped = arrow_table.num_rows - inserted
        if skipped > 0:
            self.duplicates += skipped
            logger.warning("duplicate primary key: %d row(s) skipped in %s", skipped, table)
        return inserted

    def insert_trades(self, arrow_table: pa.Table) -> int:
        return self._insert("trades", arrow_table)

    def insert_candles(self, arrow_table: pa.Table) -> int:
        return self._insert("candles", arrow_table)

    def insert_signals(self, arrow_table: pa.Table) -> int:
        """Insert signals rows. signals has no PRIMARY KEY (decision 12) — plain INSERT."""
        self._con.register("_batch", arrow_table)
        try:
            self._con.execute("INSERT INTO signals SELECT * FROM _batch")
        except Exception as exc:  # noqa: BLE001
            raise StorageError(ERROR_DUCKDB_WRITE, f"signals insert failed: {exc}") from exc
        finally:
            self._con.unregister("_batch")
        return arrow_table.num_rows

    def insert_flow_response_events(self, arrow_table: pa.Table) -> int:
        return self._insert("flow_response_events", arrow_table)

    def insert_flow_response_outcomes(self, arrow_table: pa.Table) -> int:
        return self._insert("flow_response_outcomes", arrow_table)

    def insert_open_interest_samples(self, arrow_table: pa.Table) -> int:
        return self._insert("open_interest_samples", arrow_table)

    def count(self, table: str) -> int:
        return self._con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]

    def table_info(self, table: str) -> list[tuple[str, str]]:
        rows = self._con.execute(f"PRAGMA table_info('{table}')").fetchall()
        return [(r[1], r[2]) for r in rows]  # (name, type)

    def close(self) -> None:
        self._con.close()


class StorageWriter:
    """Buffers records and flushes to Parquet + DuckDB by size or interval."""

    def __init__(
        self,
        parquet_path: str | Path,
        duckdb_path: str | Path,
        *,
        batch_size: int = 1000,
        flush_interval_sec: int = 5,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        if flush_interval_sec < 1:
            raise ValueError("flush_interval_sec must be >= 1")
        self._pq_base = Path(parquet_path)
        self._pq_base.mkdir(parents=True, exist_ok=True)
        self._duck = DuckDbWriter(duckdb_path)
        self.batch_size = batch_size
        self.flush_interval_sec = flush_interval_sec
        self._clock = clock
        self._trades: list[dict] = []
        self._candles: list[dict] = []
        self._signals: list[dict] = []
        self._flow_response_events: list[dict] = []
        self._flow_response_outcomes: list[dict] = []
        self._open_interest_samples: list[dict] = []
        self._last_flush = clock()
        self._seq = 0
        # counters
        self.trades_written = 0
        self.candles_written = 0
        self.signals_written = 0
        self.flow_response_events_written = 0
        self.flow_response_outcomes_written = 0
        self.open_interest_samples_written = 0
        self.flushes = 0

    @classmethod
    def from_config(cls, config: Any, **overrides: Any) -> "StorageWriter":
        """Build from a validated Config (ConfigNode): database.* section."""
        db = config.database
        params: dict[str, Any] = dict(
            parquet_path=db.parquet_path,
            duckdb_path=db.duckdb_path,
            batch_size=db.batch_size,
            flush_interval_sec=db.flush_interval_sec,
        )
        params.update(overrides)
        return cls(**params)

    # -- ingest --
    def add_trade(self, row: dict) -> None:
        self._trades.append(row)
        if len(self._trades) >= self.batch_size:
            self.flush()

    def add_candle(self, row: dict) -> None:
        self._candles.append(row)
        if len(self._candles) >= self.batch_size:
            self.flush()

    def add_signal(self, row: dict) -> None:
        self._signals.append(row)
        if len(self._signals) >= self.batch_size:
            self.flush()

    def add_flow_response_event(self, row: dict) -> None:
        self._flow_response_events.append(row)
        if len(self._flow_response_events) >= self.batch_size:
            self.flush()

    def add_flow_response_outcome(self, row: dict) -> None:
        self._flow_response_outcomes.append(row)
        if len(self._flow_response_outcomes) >= self.batch_size:
            self.flush()

    def add_open_interest_sample(self, row: dict) -> None:
        self._open_interest_samples.append(row)
        if len(self._open_interest_samples) >= self.batch_size:
            self.flush()

    def tick(self) -> None:
        """Time-based flush: call periodically; flushes if the interval elapsed."""
        if (self._clock() - self._last_flush) >= self.flush_interval_sec and (
            self._trades or self._candles or self._signals
            or self._flow_response_events or self._flow_response_outcomes
            or self._open_interest_samples
        ):
            self.flush()

    # -- parquet --
    def _write_parquet(
        self, rows: list[dict], schema: pa.Schema, time_col: str,
        has_timeframe: bool, dataset: str | None = None,
    ) -> None:
        table = pa.Table.from_pylist(rows, schema=schema)
        # group row indices by partition
        groups: dict[Path, list[dict]] = {}
        for row in rows:
            when = row[time_col]
            timeframe = row["timeframe"] if has_timeframe else None
            base = self._pq_base / dataset if dataset else self._pq_base
            directory = _partition_dir(base, row["symbol"], when, timeframe)
            groups.setdefault(directory, []).append(row)
        for directory, group_rows in groups.items():
            directory.mkdir(parents=True, exist_ok=True)
            group_table = pa.Table.from_pylist(group_rows, schema=schema)
            target = directory / f"part-{self._seq:06d}.parquet"
            try:
                pq.write_table(group_table, target, compression="snappy")
            except Exception as exc:  # noqa: BLE001
                raise StorageError(ERROR_PARQUET_WRITE, f"parquet write failed: {exc}") from exc

    def _write_open_interest_parquet(self, rows: list[dict]) -> None:
        """Upsert OI samples into one compact Parquet file per UTC hour.

        The shared five-second storage flush would otherwise create roughly one
        tiny file per ten-second OI poll. Rewriting a bounded hourly file keeps
        reload durability while avoiding thousands of one-row files per day.
        """
        groups: dict[tuple[Path, int], list[dict]] = {}
        for row in rows:
            when = row["source_time"]
            directory = _partition_dir(
                self._pq_base / "open_interest_samples", row["symbol"], when,
            )
            groups.setdefault((directory, when.hour), []).append(row)

        for (directory, hour), new_rows in groups.items():
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / f"hour-{hour:02d}.parquet"
            merged: dict[tuple[datetime, str], dict] = {}
            if target.exists():
                try:
                    for row in pq.ParquetFile(str(target)).read().to_pylist():
                        merged[(row["source_time"], row["symbol"])] = row
                except Exception as exc:  # noqa: BLE001
                    raise StorageError(
                        ERROR_PARQUET_WRITE, f"OI parquet read failed: {exc}"
                    ) from exc
            for row in new_rows:
                merged[(row["source_time"], row["symbol"])] = row
            ordered = sorted(merged.values(), key=lambda row: row["source_time"])
            table = pa.Table.from_pylist(ordered, schema=OPEN_INTEREST_SAMPLES_SCHEMA)
            temporary = directory / f".hour-{hour:02d}-{self._seq:06d}.tmp.parquet"
            try:
                pq.write_table(table, temporary, compression="snappy")
                temporary.replace(target)
            except Exception as exc:  # noqa: BLE001
                temporary.unlink(missing_ok=True)
                raise StorageError(
                    ERROR_PARQUET_WRITE, f"OI parquet write failed: {exc}"
                ) from exc

    def flush(self) -> None:
        if self._trades:
            arrow = pa.Table.from_pylist(self._trades, schema=TRADES_SCHEMA)
            self._write_parquet(self._trades, TRADES_SCHEMA, "event_time", has_timeframe=False)
            self._duck.insert_trades(arrow)
            self.trades_written += len(self._trades)
            self._trades = []
        if self._candles:
            arrow = pa.Table.from_pylist(self._candles, schema=CANDLES_SCHEMA)
            self._write_parquet(self._candles, CANDLES_SCHEMA, "bar_time", has_timeframe=True)
            self._duck.insert_candles(arrow)
            self.candles_written += len(self._candles)
            self._candles = []
        if self._signals:
            arrow = pa.Table.from_pylist(self._signals, schema=SIGNALS_SCHEMA)
            self._write_parquet(self._signals, SIGNALS_SCHEMA, "signal_time", has_timeframe=False)
            self._duck.insert_signals(arrow)
            self.signals_written += len(self._signals)
            self._signals = []
        if self._flow_response_events:
            arrow = pa.Table.from_pylist(self._flow_response_events, schema=FLOW_RESPONSE_EVENTS_SCHEMA)
            self._write_parquet(
                self._flow_response_events, FLOW_RESPONSE_EVENTS_SCHEMA, "event_time",
                has_timeframe=False, dataset="flow_response_events",
            )
            inserted = self._duck.insert_flow_response_events(arrow)
            self.flow_response_events_written += inserted
            self._flow_response_events = []
        if self._flow_response_outcomes:
            arrow = pa.Table.from_pylist(self._flow_response_outcomes, schema=FLOW_RESPONSE_OUTCOMES_SCHEMA)
            self._write_parquet(
                self._flow_response_outcomes, FLOW_RESPONSE_OUTCOMES_SCHEMA, "event_time",
                has_timeframe=False, dataset="flow_response_outcomes",
            )
            inserted = self._duck.insert_flow_response_outcomes(arrow)
            self.flow_response_outcomes_written += inserted
            self._flow_response_outcomes = []
        if self._open_interest_samples:
            arrow = pa.Table.from_pylist(
                self._open_interest_samples, schema=OPEN_INTEREST_SAMPLES_SCHEMA,
            )
            self._write_open_interest_parquet(self._open_interest_samples)
            inserted = self._duck.insert_open_interest_samples(arrow)
            self.open_interest_samples_written += inserted
            self._open_interest_samples = []
        self._seq += 1
        self._last_flush = self._clock()
        self.flushes += 1

    @property
    def duplicates(self) -> int:
        return self._duck.duplicates

    @property
    def duckdb(self) -> DuckDbWriter:
        return self._duck

    def close(self) -> None:
        self.flush()
        self._duck.close()

    def __enter__(self) -> "StorageWriter":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


_BACKGROUND_STOP = object()


class BackgroundStorageWriter:
    """Non-blocking live-pipeline facade around :class:`StorageWriter`.

    Parquet and DuckDB are synchronous libraries. Running their writes on the
    market-data asyncio loop pauses WebSocket receive, order-flow calculation,
    and browser delivery together. This facade preserves the existing storage
    contract while moving every storage operation to one dedicated thread. A
    bounded FIFO retains ordering and makes overload explicit instead of
    silently losing observations.

    The underlying ``StorageWriter`` is created, used, and closed by the same
    worker thread, so its DuckDB connection never crosses thread boundaries.
    """

    _METHODS = {
        "trade": "add_trade",
        "candle": "add_candle",
        "signal": "add_signal",
        "flow_response_event": "add_flow_response_event",
        "flow_response_outcome": "add_flow_response_outcome",
        "open_interest_sample": "add_open_interest_sample",
    }

    def __init__(
        self,
        parquet_path: str | Path,
        duckdb_path: str | Path,
        *,
        batch_size: int = 1000,
        flush_interval_sec: int = 5,
        queue_depth: int = 10000,
    ) -> None:
        if queue_depth < 1:
            raise ValueError("queue_depth must be >= 1")
        self._writer_args = (parquet_path, duckdb_path)
        self._writer_kwargs = {
            "batch_size": batch_size,
            "flush_interval_sec": flush_interval_sec,
        }
        self._queue: Queue[Any] = Queue(maxsize=queue_depth)
        self._ready = Event()
        self._writer: Optional[StorageWriter] = None
        self._error: Optional[BaseException] = None
        self._closed = False
        self.high_watermark = 0
        self._thread = Thread(
            target=self._run,
            name="deltaengine-storage",
            daemon=True,
        )
        self._thread.start()
        if not self._ready.wait(timeout=30):
            raise StorageError(ERROR_STORAGE_UNAVAILABLE, "storage worker startup timed out")
        self._raise_if_failed()

    def _run(self) -> None:
        writer: Optional[StorageWriter] = None
        try:
            writer = StorageWriter(*self._writer_args, **self._writer_kwargs)
            self._writer = writer
        except BaseException as exc:  # surface initialization failure to caller
            self._error = exc
        finally:
            self._ready.set()
        if writer is None:
            return

        try:
            while True:
                try:
                    command = self._queue.get(timeout=0.1)
                except Empty:
                    writer.tick()
                    continue
                if command is _BACKGROUND_STOP:
                    break
                kind, row = command
                getattr(writer, self._METHODS[kind])(row)
                writer.tick()
        except BaseException as exc:
            self._error = exc
        finally:
            try:
                writer.close()
            except BaseException as exc:
                if self._error is None:
                    self._error = exc

    def _raise_if_failed(self) -> None:
        if self._error is not None:
            raise StorageError(
                ERROR_STORAGE_UNAVAILABLE,
                f"background storage worker failed: {self._error}",
            ) from self._error

    def _enqueue(self, kind: str, row: dict) -> None:
        self._raise_if_failed()
        if self._closed:
            raise StorageError(ERROR_STORAGE_UNAVAILABLE, "background storage writer is closed")
        try:
            self._queue.put_nowait((kind, row))
        except Full as exc:
            raise StorageError(
                ERROR_STORAGE_UNAVAILABLE,
                f"background storage queue full (depth={self._queue.maxsize})",
            ) from exc
        self.high_watermark = max(self.high_watermark, self._queue.qsize())

    def add_trade(self, row: dict) -> None:
        self._enqueue("trade", row)

    def add_candle(self, row: dict) -> None:
        self._enqueue("candle", row)

    def add_signal(self, row: dict) -> None:
        self._enqueue("signal", row)

    def add_flow_response_event(self, row: dict) -> None:
        self._enqueue("flow_response_event", row)

    def add_flow_response_outcome(self, row: dict) -> None:
        self._enqueue("flow_response_outcome", row)

    def add_open_interest_sample(self, row: dict) -> None:
        self._enqueue("open_interest_sample", row)

    def tick(self) -> None:
        """Compatibility hook: only surface worker failure on the live path."""
        self._raise_if_failed()

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    def _counter(self, name: str) -> int:
        writer = self._writer
        return int(getattr(writer, name, 0)) if writer is not None else 0

    @property
    def trades_written(self) -> int:
        return self._counter("trades_written")

    @property
    def candles_written(self) -> int:
        return self._counter("candles_written")

    @property
    def signals_written(self) -> int:
        return self._counter("signals_written")

    @property
    def flow_response_events_written(self) -> int:
        return self._counter("flow_response_events_written")

    @property
    def flow_response_outcomes_written(self) -> int:
        return self._counter("flow_response_outcomes_written")

    @property
    def open_interest_samples_written(self) -> int:
        return self._counter("open_interest_samples_written")

    @property
    def flushes(self) -> int:
        return self._counter("flushes")

    def close(self, timeout: float = 120.0) -> None:
        if self._closed:
            self._raise_if_failed()
            return
        self._closed = True
        while True:
            self._raise_if_failed()
            try:
                self._queue.put(_BACKGROUND_STOP, timeout=0.1)
                break
            except Full:
                continue
        self._thread.join(timeout=timeout)
        if self._thread.is_alive():
            raise StorageError(ERROR_STORAGE_UNAVAILABLE, "storage worker shutdown timed out")
        self._raise_if_failed()

    def __enter__(self) -> "BackgroundStorageWriter":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
