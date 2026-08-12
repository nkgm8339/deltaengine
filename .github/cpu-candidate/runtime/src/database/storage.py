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
import statistics
import time
import uuid
from collections import deque
from datetime import datetime
from decimal import Decimal
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
    COMBINED_CONTEXT_EVENTS_DDL,
    COMBINED_CONTEXT_EVENTS_SCHEMA,
    FLOW_RESPONSE_EVENTS_DDL,
    FLOW_RESPONSE_EVENTS_SCHEMA,
    FLOW_RESPONSE_OUTCOMES_DDL,
    FLOW_RESPONSE_OUTCOMES_SCHEMA,
    FOOTPRINT_BAR_MANIFEST_DDL,
    FOOTPRINT_BAR_MANIFEST_SCHEMA,
    FOOTPRINT_LEVELS_DDL,
    FOOTPRINT_LEVELS_SCHEMA,
    FootprintStorageBatch,
    HFM_CONTEXT_OUTCOMES_DDL,
    HFM_CONTEXT_OUTCOMES_SCHEMA,
    OPEN_INTEREST_SAMPLES_DDL,
    NATIVE_FLOW_EVENTS_DDL,
    NATIVE_FLOW_EVENTS_SCHEMA,
    NATIVE_FLOW_OUTCOMES_DDL,
    NATIVE_FLOW_OUTCOMES_SCHEMA,
    OPEN_INTEREST_SAMPLES_SCHEMA,
    SIGNALS_DDL,
    SIGNALS_SCHEMA,
    TRADES_DDL,
    TRADES_SCHEMA,
    footprint_bar_to_storage,
)

logger = logging.getLogger("database.storage")

ERROR_PARQUET_WRITE = "E4001"
ERROR_DUCKDB_WRITE = "E4002"
ERROR_STORAGE_UNAVAILABLE = "E4003"

_TRANSIENT_PARQUET_ERRNOS = {5, 9}  # EIO / EBADF from Docker Desktop bind mounts
_OI_PARQUET_RETRY_DELAYS_SEC = (0.1, 0.5, 1.0)


class StorageError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"[{code}] {message}")


def _is_transient_parquet_io_error(exc: BaseException) -> bool:
    """Return true only for retryable file-handle/I/O failures.

    PyArrow can replace the original ``OSError(errno)`` with a final
    ``OSError('error closing file')``. Walk both exception chains so the
    underlying EIO/EBADF is not lost, while schema/content failures remain
    fail-closed and are never retried.
    """

    pending: list[BaseException] = [exc]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, OSError):
            if current.errno in _TRANSIENT_PARQUET_ERRNOS:
                return True
            detail = str(current).lower()
            if any(
                marker in detail
                for marker in (
                    "bad file descriptor",
                    "input/output error",
                    "error closing file",
                )
            ):
                return True
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)
    return False


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
        self._con.execute(NATIVE_FLOW_EVENTS_DDL)
        self._con.execute(NATIVE_FLOW_OUTCOMES_DDL)
        self._con.execute(COMBINED_CONTEXT_EVENTS_DDL)
        self._con.execute(HFM_CONTEXT_OUTCOMES_DDL)
        self._con.execute(FOOTPRINT_BAR_MANIFEST_DDL)
        self._con.execute(FOOTPRINT_LEVELS_DDL)
        self.duplicates = 0
        self.footprint_duplicates = 0

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

    def insert_native_flow_events(self, arrow_table: pa.Table) -> int:
        return self._insert("native_flow_events", arrow_table)

    def insert_native_flow_outcomes(self, arrow_table: pa.Table) -> int:
        return self._insert("native_flow_outcomes", arrow_table)

    def insert_open_interest_samples(self, arrow_table: pa.Table) -> int:
        return self._insert("open_interest_samples", arrow_table)

    def insert_combined_context_events(self, arrow_table: pa.Table) -> int:
        return self._insert("combined_context_events", arrow_table)

    def insert_hfm_context_outcomes(self, arrow_table: pa.Table) -> int:
        return self._insert("hfm_context_outcomes", arrow_table)

    def insert_footprint_bar(
        self,
        manifest_table: pa.Table,
        levels_table: pa.Table,
    ) -> int:
        """Atomically insert one manifest and all normalized price levels.

        The manifest primary key is the physical idempotency guard. The large
        level table intentionally has no four-column ART; strict incoming
        price validation plus this single-writer transaction preserves its
        logical key without the measured index amplification.
        """

        manifest = manifest_table.to_pylist()[0]
        key = [manifest["bar_time"], manifest["symbol"], manifest["timeframe"]]
        self._con.register("_footprint_manifest_batch", manifest_table)
        self._con.register("_footprint_levels_batch", levels_table)
        try:
            self._con.execute("BEGIN")
            existing = self._con.execute(
                "SELECT level_count, content_hash FROM footprint_bar_manifest "
                "WHERE bar_time = ? AND symbol = ? AND timeframe = ?",
                key,
            ).fetchone()
            if existing is not None:
                stored_levels = self._con.execute(
                    "SELECT count(*) FROM footprint_levels "
                    "WHERE bar_time = ? AND symbol = ? AND timeframe = ?",
                    key,
                ).fetchone()[0]
                if (
                    int(existing[0]) != int(manifest["level_count"])
                    or str(existing[1]) != str(manifest["content_hash"])
                    or int(stored_levels) != int(manifest["level_count"])
                ):
                    raise StorageError(
                        ERROR_DUCKDB_WRITE,
                        "footprint duplicate key has conflicting or incomplete content",
                    )
                self._con.execute("COMMIT")
                self.duplicates += 1
                self.footprint_duplicates += 1
                logger.warning(
                    "duplicate confirmed footprint bar skipped: %s %s %s",
                    manifest["bar_time"], manifest["symbol"], manifest["timeframe"],
                )
                return 0

            orphan_levels = self._con.execute(
                "SELECT count(*) FROM footprint_levels "
                "WHERE bar_time = ? AND symbol = ? AND timeframe = ?",
                key,
            ).fetchone()[0]
            if orphan_levels:
                raise StorageError(
                    ERROR_DUCKDB_WRITE,
                    "footprint levels exist without a manifest",
                )

            self._con.execute(
                "INSERT INTO footprint_bar_manifest "
                "SELECT * FROM _footprint_manifest_batch"
            )
            self._con.execute(
                "INSERT INTO footprint_levels SELECT * FROM _footprint_levels_batch"
            )
            self._con.execute("COMMIT")
            return levels_table.num_rows
        except StorageError:
            try:
                self._con.execute("ROLLBACK")
            except Exception:
                pass
            raise
        except Exception as exc:  # noqa: BLE001
            try:
                self._con.execute("ROLLBACK")
            except Exception:
                pass
            raise StorageError(
                ERROR_DUCKDB_WRITE, f"footprint bar insert failed: {exc}"
            ) from exc
        finally:
            self._con.unregister("_footprint_levels_batch")
            self._con.unregister("_footprint_manifest_batch")

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
        self._native_flow_events: list[dict] = []
        self._native_flow_outcomes: list[dict] = []
        self._combined_context_events: list[dict] = []
        self._hfm_context_outcomes: list[dict] = []
        self._footprint_bars: list[FootprintStorageBatch] = []
        self._last_flush = clock()
        self._seq = 0
        # ``_seq`` restarts with each process and is also shared by every
        # dataset flushed in one cycle, so it cannot safely identify durable
        # append-only shards.  A run-unique, time-sortable prefix plus a
        # per-file counter prevents both restart and same-flush collisions.
        self._parquet_run_id = f"{time.time_ns():020d}-{uuid.uuid4().hex}"
        self._parquet_part_seq = 0
        # counters
        self.trades_written = 0
        self.candles_written = 0
        self.signals_written = 0
        self.flow_response_events_written = 0
        self.flow_response_outcomes_written = 0
        self.open_interest_samples_written = 0
        self.native_flow_events_written = 0
        self.native_flow_outcomes_written = 0
        self.combined_context_events_written = 0
        self.hfm_context_outcomes_written = 0
        self.footprint_bars_written = 0
        self.footprint_levels_written = 0
        self.footprint_write_failures = 0
        self._footprint_flush_latencies_ms: deque[float] = deque(maxlen=512)
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

    def add_native_flow_event(self, row: dict) -> None:
        self._native_flow_events.append(row)
        if len(self._native_flow_events) >= self.batch_size:
            self.flush()

    def add_native_flow_outcome(self, row: dict) -> None:
        self._native_flow_outcomes.append(row)
        if len(self._native_flow_outcomes) >= self.batch_size:
            self.flush()

    def add_combined_context_event(self, row: dict) -> None:
        self._combined_context_events.append(row)
        if len(self._combined_context_events) >= self.batch_size:
            self.flush()

    def add_hfm_context_outcome(self, row: dict) -> None:
        self._hfm_context_outcomes.append(row)
        if len(self._hfm_context_outcomes) >= self.batch_size:
            self.flush()

    def add_open_interest_sample(self, row: dict) -> None:
        self._open_interest_samples.append(row)
        if len(self._open_interest_samples) >= self.batch_size:
            self.flush()

    def add_footprint_bar(self, bar: Any) -> None:
        self._footprint_bars.append(footprint_bar_to_storage(bar))
        if len(self._footprint_bars) >= self.batch_size:
            self.flush()

    def tick(self) -> None:
        """Time-based flush: call periodically; flushes if the interval elapsed."""
        if (self._clock() - self._last_flush) >= self.flush_interval_sec and (
            self._trades or self._candles or self._signals
            or self._flow_response_events or self._flow_response_outcomes
            or self._open_interest_samples
            or self._native_flow_events or self._native_flow_outcomes
            or self._combined_context_events or self._hfm_context_outcomes
            or self._footprint_bars
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
            part_seq = self._parquet_part_seq
            self._parquet_part_seq += 1
            target = directory / (
                f"part-{self._parquet_run_id}-{part_seq:06d}.parquet"
            )
            temporary = directory / f".{target.name}.tmp"
            try:
                if target.exists():
                    raise FileExistsError(f"Parquet target already exists: {target}")
                pq.write_table(group_table, temporary, compression="snappy")
                temporary.replace(target)
            except Exception as exc:  # noqa: BLE001
                raise StorageError(ERROR_PARQUET_WRITE, f"parquet write failed: {exc}") from exc
            finally:
                temporary.unlink(missing_ok=True)

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
            attempts = len(_OI_PARQUET_RETRY_DELAYS_SEC) + 1
            for attempt in range(attempts):
                try:
                    pq.write_table(table, temporary, compression="snappy")
                    temporary.replace(target)
                    break
                except Exception as exc:  # noqa: BLE001
                    temporary.unlink(missing_ok=True)
                    if (
                        attempt >= len(_OI_PARQUET_RETRY_DELAYS_SEC)
                        or not _is_transient_parquet_io_error(exc)
                    ):
                        raise StorageError(
                            ERROR_PARQUET_WRITE, f"OI parquet write failed: {exc}"
                        ) from exc
                    delay = _OI_PARQUET_RETRY_DELAYS_SEC[attempt]
                    logger.warning(
                        "transient OI parquet I/O failure; retrying "
                        "attempt=%d/%d delay_sec=%.1f target=%s error=%r",
                        attempt + 1,
                        attempts,
                        delay,
                        target,
                        exc,
                    )
                    time.sleep(delay)

    def _write_footprint_parquet(
        self, batches: list[FootprintStorageBatch]
    ) -> None:
        """Merge normalized levels into one atomic ZSTD file per UTC day."""

        groups: dict[Path, list[dict]] = {}
        for batch in batches:
            for row in batch.levels:
                directory = _partition_dir(
                    self._pq_base / "footprint_levels",
                    row["symbol"],
                    row["bar_time"],
                    row["timeframe"],
                )
                groups.setdefault(directory, []).append(row)

        for directory, new_rows in groups.items():
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / "levels.parquet"
            merged: dict[tuple[datetime, Decimal], dict] = {}
            try:
                if target.exists():
                    existing_table = pq.ParquetFile(str(target)).read()
                    if not existing_table.schema.equals(
                        FOOTPRINT_LEVELS_SCHEMA, check_metadata=False
                    ):
                        raise StorageError(
                            ERROR_PARQUET_WRITE,
                            f"footprint archive schema mismatch: {target}",
                        )
                    for row in existing_table.to_pylist():
                        key = (row["bar_time"], row["price"])
                        if key in merged and merged[key] != row:
                            raise StorageError(
                                ERROR_PARQUET_WRITE,
                                "conflicting duplicate in existing footprint archive",
                            )
                        merged[key] = row
                for row in new_rows:
                    key = (row["bar_time"], row["price"])
                    existing = merged.get(key)
                    if existing is not None and existing != row:
                        raise StorageError(
                            ERROR_PARQUET_WRITE,
                            "footprint archive key has conflicting content",
                        )
                    merged[key] = row

                ordered = sorted(
                    merged.values(), key=lambda row: (row["bar_time"], row["price"])
                )
                table = pa.Table.from_pylist(ordered, schema=FOOTPRINT_LEVELS_SCHEMA)
                temporary = directory / f".levels-{self._seq:06d}.tmp.parquet"
                pq.write_table(
                    table,
                    temporary,
                    compression="zstd",
                    row_group_size=100_000,
                )
                temporary.replace(target)
                readback = pq.ParquetFile(str(target))
                if (
                    readback.metadata.num_rows != len(ordered)
                    or not readback.schema_arrow.equals(
                        FOOTPRINT_LEVELS_SCHEMA, check_metadata=False
                    )
                ):
                    raise StorageError(
                        ERROR_PARQUET_WRITE,
                        f"footprint archive read-back failed: {target}",
                    )
            except StorageError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise StorageError(
                    ERROR_PARQUET_WRITE, f"footprint parquet write failed: {exc}"
                ) from exc
            finally:
                temporary = directory / f".levels-{self._seq:06d}.tmp.parquet"
                temporary.unlink(missing_ok=True)

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
        if self._native_flow_events:
            arrow = pa.Table.from_pylist(self._native_flow_events, schema=NATIVE_FLOW_EVENTS_SCHEMA)
            self._write_parquet(self._native_flow_events, NATIVE_FLOW_EVENTS_SCHEMA, "event_time", has_timeframe=True, dataset="native_flow_events")
            inserted = self._duck.insert_native_flow_events(arrow)
            self.native_flow_events_written += inserted
            self._native_flow_events = []
        if self._native_flow_outcomes:
            arrow = pa.Table.from_pylist(self._native_flow_outcomes, schema=NATIVE_FLOW_OUTCOMES_SCHEMA)
            self._write_parquet(self._native_flow_outcomes, NATIVE_FLOW_OUTCOMES_SCHEMA, "event_time", has_timeframe=True, dataset="native_flow_outcomes")
            inserted = self._duck.insert_native_flow_outcomes(arrow)
            self.native_flow_outcomes_written += inserted
            self._native_flow_outcomes = []
        if self._combined_context_events:
            arrow = pa.Table.from_pylist(
                self._combined_context_events, schema=COMBINED_CONTEXT_EVENTS_SCHEMA,
            )
            self._write_parquet(
                self._combined_context_events, COMBINED_CONTEXT_EVENTS_SCHEMA,
                "event_time", has_timeframe=True, dataset="combined_context_events",
            )
            inserted = self._duck.insert_combined_context_events(arrow)
            self.combined_context_events_written += inserted
            self._combined_context_events = []
        if self._hfm_context_outcomes:
            arrow = pa.Table.from_pylist(
                self._hfm_context_outcomes, schema=HFM_CONTEXT_OUTCOMES_SCHEMA,
            )
            self._write_parquet(
                self._hfm_context_outcomes, HFM_CONTEXT_OUTCOMES_SCHEMA,
                "event_time", has_timeframe=True, dataset="hfm_context_outcomes",
            )
            inserted = self._duck.insert_hfm_context_outcomes(arrow)
            self.hfm_context_outcomes_written += inserted
            self._hfm_context_outcomes = []
        if self._open_interest_samples:
            arrow = pa.Table.from_pylist(
                self._open_interest_samples, schema=OPEN_INTEREST_SAMPLES_SCHEMA,
            )
            self._write_open_interest_parquet(self._open_interest_samples)
            inserted = self._duck.insert_open_interest_samples(arrow)
            self.open_interest_samples_written += inserted
            self._open_interest_samples = []
        if self._footprint_bars:
            started = time.perf_counter()
            try:
                self._write_footprint_parquet(self._footprint_bars)
                for batch in self._footprint_bars:
                    manifest = pa.Table.from_pylist(
                        [batch.manifest], schema=FOOTPRINT_BAR_MANIFEST_SCHEMA
                    )
                    levels = pa.Table.from_pylist(
                        list(batch.levels), schema=FOOTPRINT_LEVELS_SCHEMA
                    )
                    inserted = self._duck.insert_footprint_bar(manifest, levels)
                    if inserted:
                        self.footprint_bars_written += 1
                        self.footprint_levels_written += inserted
                self._footprint_bars = []
            except Exception:
                self.footprint_write_failures += 1
                raise
            finally:
                self._footprint_flush_latencies_ms.append(
                    (time.perf_counter() - started) * 1000.0
                )
        self._seq += 1
        self._last_flush = self._clock()
        self.flushes += 1

    @property
    def duplicates(self) -> int:
        return self._duck.duplicates

    @property
    def footprint_duplicates(self) -> int:
        return self._duck.footprint_duplicates

    @property
    def footprint_flush_median_ms(self) -> float:
        values = tuple(self._footprint_flush_latencies_ms)
        return float(statistics.median(values)) if values else 0.0

    @property
    def footprint_flush_p95_ms(self) -> float:
        values = sorted(self._footprint_flush_latencies_ms)
        if not values:
            return 0.0
        return float(values[max(0, min(len(values) - 1, int(len(values) * 0.95)))])

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
        "native_flow_event": "add_native_flow_event",
        "native_flow_outcome": "add_native_flow_outcome",
        "open_interest_sample": "add_open_interest_sample",
        "combined_context_event": "add_combined_context_event",
        "hfm_context_outcome": "add_hfm_context_outcome",
        "footprint_bar": "add_footprint_bar",
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

    def _enqueue(self, kind: str, row: Any) -> None:
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

    def add_native_flow_event(self, row: dict) -> None:
        self._enqueue("native_flow_event", row)

    def add_native_flow_outcome(self, row: dict) -> None:
        self._enqueue("native_flow_outcome", row)

    def add_open_interest_sample(self, row: dict) -> None:
        self._enqueue("open_interest_sample", row)

    def add_combined_context_event(self, row: dict) -> None:
        self._enqueue("combined_context_event", row)

    def add_hfm_context_outcome(self, row: dict) -> None:
        self._enqueue("hfm_context_outcome", row)

    def add_footprint_bar(self, bar: Any) -> None:
        self._enqueue("footprint_bar", bar)

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
    def combined_context_events_written(self) -> int:
        return self._counter("combined_context_events_written")

    @property
    def hfm_context_outcomes_written(self) -> int:
        return self._counter("hfm_context_outcomes_written")

    @property
    def footprint_bars_written(self) -> int:
        return self._counter("footprint_bars_written")

    @property
    def footprint_levels_written(self) -> int:
        return self._counter("footprint_levels_written")

    @property
    def footprint_duplicates(self) -> int:
        return self._counter("footprint_duplicates")

    @property
    def footprint_write_failures(self) -> int:
        return self._counter("footprint_write_failures")

    def _metric(self, name: str) -> float:
        writer = self._writer
        return float(getattr(writer, name, 0.0)) if writer is not None else 0.0

    @property
    def footprint_flush_median_ms(self) -> float:
        return self._metric("footprint_flush_median_ms")

    @property
    def footprint_flush_p95_ms(self) -> float:
        return self._metric("footprint_flush_p95_ms")

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








