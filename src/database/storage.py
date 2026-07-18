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
from typing import Any, Callable

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from .schema import (
    CANDLES_DDL,
    CANDLES_SCHEMA,
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
        self._last_flush = clock()
        self._seq = 0
        # counters
        self.trades_written = 0
        self.candles_written = 0
        self.signals_written = 0
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

    def tick(self) -> None:
        """Time-based flush: call periodically; flushes if the interval elapsed."""
        if (self._clock() - self._last_flush) >= self.flush_interval_sec and (
            self._trades or self._candles or self._signals
        ):
            self.flush()

    # -- parquet --
    def _write_parquet(self, rows: list[dict], schema: pa.Schema, time_col: str, has_timeframe: bool) -> None:
        table = pa.Table.from_pylist(rows, schema=schema)
        # group row indices by partition
        groups: dict[Path, list[dict]] = {}
        for row in rows:
            when = row[time_col]
            timeframe = row["timeframe"] if has_timeframe else None
            directory = _partition_dir(self._pq_base, row["symbol"], when, timeframe)
            groups.setdefault(directory, []).append(row)
        for directory, group_rows in groups.items():
            directory.mkdir(parents=True, exist_ok=True)
            group_table = pa.Table.from_pylist(group_rows, schema=schema)
            target = directory / f"part-{self._seq:06d}.parquet"
            try:
                pq.write_table(group_table, target, compression="snappy")
            except Exception as exc:  # noqa: BLE001
                raise StorageError(ERROR_PARQUET_WRITE, f"parquet write failed: {exc}") from exc

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
