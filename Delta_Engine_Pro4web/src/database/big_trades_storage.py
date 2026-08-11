"""Transactional and asynchronous persistence for Big Trades V2.

This module is deliberately isolated from the existing market-data writer.  A
BigTradesDuckDbStore is created only by the Big Trades feature path, so keeping
``big_trades.enabled`` false cannot migrate or write the production database.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import statistics
import tempfile
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event, RLock, Thread
from typing import Any, Callable, Iterable, Mapping, Optional

import duckdb
import pyarrow.parquet as pq

from src.orderflow.big_trades.activation import ActivationArtifact
from src.orderflow.big_trades.artifacts import CalibrationArtifact, SessionStatsArtifact
from src.orderflow.big_trades.ids import canonical_json, content_hash
from src.orderflow.big_trades.models import (
    ResultSnapshot,
    UserAssessment,
    ZoneCandleObservation,
    ZoneEventLink,
    ZoneInteraction,
    ZoneStateCheckpoint,
)
from src.orderflow.big_trades.settings import SettingsRequest, SettingsVersion

from .big_trades_schema import (
    BIG_TRADES_ARROW_SCHEMAS,
    BIG_TRADES_INDEX_DDL,
    BIG_TRADES_SCHEMA_VERSION,
    BIG_TRADES_TABLE_DDLS,
    BigTradeOriginStorageBatch,
    activation_to_row,
    assessment_to_row,
    calibration_to_row,
    candle_observation_to_row,
    checkpoint_to_row,
    interaction_to_row,
    link_to_row,
    session_stats_to_row,
    settings_history_to_row,
    snapshot_to_row,
    table_from_rows,
)


logger = logging.getLogger("orderflow.big_trades.storage")
UTC = timezone.utc
BIG_TRADES_LOGIC_VERSION = "BTLOGIC-2.0"
_SAFE_BATCH_ID = re.compile(r"^[A-Za-z0-9_.-]+$")


class BigTradesStorageError(RuntimeError):
    """Base error for a failed Big Trades durable write."""


class BigTradesContentCollision(BigTradesStorageError):
    """The same identity was observed with different immutable content."""


class BigTradesStorageIntegrityError(BigTradesStorageError):
    """Persisted rows do not form a complete valid Big Trades record set."""


class ParquetCommitStatus(str, Enum):
    DISABLED = "DISABLED"
    COMMITTED = "COMMITTED"
    PENDING = "PENDING"


@dataclass(frozen=True)
class StorageCommitResult:
    batch_id: str
    kind: str
    inserted: Mapping[str, int]
    duplicates: int
    parquet_status: ParquetCommitStatus


@dataclass(frozen=True)
class CommitAck:
    batch_id: str
    kind: str
    success: bool
    duckdb_committed: bool
    parquet_status: ParquetCommitStatus
    submitted_at_monotonic: float
    completed_at_monotonic: float
    latency_ms: float
    inserted: Mapping[str, int] = field(default_factory=dict)
    duplicates: int = 0
    error_code: Optional[str] = None
    error: Optional[str] = None


class CommitFuture:
    """Small callback-capable future used without blocking the market loop."""

    def __init__(self) -> None:
        self._ready = Event()
        self._lock = RLock()
        self._ack: Optional[CommitAck] = None
        self._callbacks: list[Callable[[CommitAck], None]] = []

    def done(self) -> bool:
        return self._ready.is_set()

    def result(self, timeout: Optional[float] = None) -> CommitAck:
        if not self._ready.wait(timeout):
            raise TimeoutError("Big Trades storage acknowledgement timed out")
        assert self._ack is not None
        return self._ack

    def add_done_callback(self, callback: Callable[[CommitAck], None]) -> None:
        ack: Optional[CommitAck]
        with self._lock:
            ack = self._ack
            if ack is None:
                self._callbacks.append(callback)
                return
        callback(ack)

    def _set_result(self, ack: CommitAck) -> None:
        with self._lock:
            if self._ack is not None:
                raise RuntimeError("commit future already completed")
            self._ack = ack
            callbacks = tuple(self._callbacks)
            self._callbacks.clear()
            self._ready.set()
        for callback in callbacks:
            try:
                callback(ack)
            except Exception:  # noqa: BLE001 - callback failure cannot undo durability
                logger.exception("Big Trades commit callback failed batch_id=%s", ack.batch_id)


def _canonical_db_value(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, memoryview):
        return bytes(value).hex()
    return value


def _row_fingerprint(row: Mapping[str, Any], columns: Iterable[str]) -> str:
    return content_hash({name: _canonical_db_value(row.get(name)) for name in columns})


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class BigTradesParquetMirror:
    """Manifest-gated Parquet mirror; DuckDB remains the live authority."""

    def __init__(
        self,
        root: str | Path,
        *,
        fault_injector: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._manifest_root = self.root / "_commits"
        self._temporary_root = self.root / "_temporary"
        self._manifest_root.mkdir(parents=True, exist_ok=True)
        self._temporary_root.mkdir(parents=True, exist_ok=True)
        self._fault_injector = fault_injector

    def _fault(self, stage: str, table_name: str) -> None:
        if self._fault_injector is not None:
            self._fault_injector(stage, table_name)

    def manifest_path(self, batch_id: str) -> Path:
        if not _SAFE_BATCH_ID.fullmatch(batch_id):
            raise ValueError("unsafe Big Trades batch ID")
        return self._manifest_root / f"{batch_id}.json"

    def is_committed(self, batch_id: str) -> bool:
        return self.manifest_path(batch_id).is_file()

    def commit(
        self,
        batch_id: str,
        table_rows: Mapping[str, Iterable[Mapping[str, Any]]],
    ) -> None:
        manifest_path = self.manifest_path(batch_id)
        if manifest_path.exists():
            self._verify_manifest(manifest_path)
            return

        materialized: dict[str, tuple[dict[str, Any], ...]] = {}
        for table_name, rows in table_rows.items():
            buffered = tuple(dict(row) for row in rows)
            if buffered:
                materialized[table_name] = buffered
        if not materialized:
            raise BigTradesStorageIntegrityError("Parquet batch has no rows")

        with tempfile.TemporaryDirectory(prefix=f"{batch_id}-", dir=self._temporary_root) as raw:
            temporary_directory = Path(raw)
            staged: list[tuple[str, Path, Path, int]] = []
            for table_name in sorted(materialized):
                if table_name not in BIG_TRADES_ARROW_SCHEMAS:
                    raise BigTradesStorageIntegrityError(f"unknown Parquet table {table_name}")
                rows = materialized[table_name]
                table = table_from_rows(table_name, rows)
                temporary = temporary_directory / f"{table_name}.parquet"
                self._fault("before_write", table_name)
                pq.write_table(table, temporary, compression="zstd")
                self._fault("after_write", table_name)
                read_back = pq.ParquetFile(str(temporary)).read()
                if not read_back.schema.equals(table.schema, check_metadata=False):
                    raise BigTradesStorageIntegrityError(
                        f"Parquet schema read-back mismatch for {table_name}"
                    )
                if read_back.num_rows != table.num_rows:
                    raise BigTradesStorageIntegrityError(
                        f"Parquet row-count read-back mismatch for {table_name}"
                    )
                self._fault("after_readback", table_name)
                target_directory = self.root / table_name
                target_directory.mkdir(parents=True, exist_ok=True)
                target = target_directory / f"{batch_id}.parquet"
                staged.append((table_name, temporary, target, table.num_rows))

            files: list[dict[str, Any]] = []
            for table_name, temporary, target, row_count in staged:
                os.replace(temporary, target)
                files.append(
                    {
                        "table": table_name,
                        "path": target.relative_to(self.root).as_posix(),
                        "rows": row_count,
                        "sha256": _sha256_file(target),
                    }
                )
            self._fault("before_manifest", "_manifest")
            manifest = {
                "schema_version": BIG_TRADES_SCHEMA_VERSION,
                "batch_id": batch_id,
                "files": files,
            }
            temporary_manifest = temporary_directory / "manifest.tmp"
            with temporary_manifest.open("w", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_manifest, manifest_path)
            self._fault("after_manifest", "_manifest")

    def _verify_manifest(self, manifest_path: Path) -> None:
        try:
            document = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BigTradesStorageIntegrityError(f"invalid Parquet manifest: {manifest_path}") from exc
        if document.get("schema_version") != BIG_TRADES_SCHEMA_VERSION:
            raise BigTradesStorageIntegrityError("Parquet manifest schema mismatch")
        if document.get("batch_id") != manifest_path.stem:
            raise BigTradesStorageIntegrityError("Parquet manifest identity mismatch")
        files = document.get("files")
        if not isinstance(files, list) or not files:
            raise BigTradesStorageIntegrityError("Parquet manifest has no files")
        for item in files:
            relative = item.get("path")
            if not isinstance(relative, str):
                raise BigTradesStorageIntegrityError("Parquet manifest path missing")
            path = self.root / relative
            if not path.is_file() or _sha256_file(path) != item.get("sha256"):
                raise BigTradesStorageIntegrityError("Parquet manifest file missing or corrupt")
            table_name = item.get("table")
            table = pq.ParquetFile(str(path)).read()
            expected_schema = BIG_TRADES_ARROW_SCHEMAS.get(table_name)
            if expected_schema is None or not table.schema.equals(expected_schema, check_metadata=False):
                raise BigTradesStorageIntegrityError("Parquet committed schema mismatch")
            if table.num_rows != item.get("rows"):
                raise BigTradesStorageIntegrityError("Parquet committed row count mismatch")


_TABLE_KEYS: Mapping[str, tuple[str, ...]] = {
    "big_trade_events": ("event_id",),
    "big_trade_event_fills": ("event_id", "fill_ordinal"),
    "big_trade_reaction_zones": ("zone_id",),
    "big_trade_zone_interactions": ("interaction_id",),
    "big_trade_zone_event_links": ("link_id",),
    "big_trade_result_snapshots": ("snapshot_id",),
    "big_trade_zone_candle_observations": ("candle_observation_id",),
    "big_trade_zone_state_checkpoints": ("checkpoint_id",),
    "big_trade_user_assessments": ("assessment_id",),
    "big_trade_session_stats": ("logic_version", "symbol", "venue", "input_mode", "session_id"),
    "big_trade_calibrations": ("calibration_id",),
    "big_trade_settings_history": ("request_id",),
    "big_trade_activation_history": ("activation_id",),
}


class BigTradesDuckDbStore:
    """Owns the isolated Big Trades schema and atomic/idempotent transactions."""

    def __init__(
        self,
        duckdb_path: str | Path,
        *,
        parquet_path: str | Path | None = None,
        fault_injector: Optional[Callable[[str, str], None]] = None,
        parquet_fault_injector: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self.db_path = Path(duckdb_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._fault_injector = fault_injector
        self._parquet = (
            BigTradesParquetMirror(parquet_path, fault_injector=parquet_fault_injector)
            if parquet_path is not None
            else None
        )
        self._parquet_pending: dict[str, tuple[str, dict[str, tuple[dict[str, Any], ...]]]] = {}
        try:
            self._con = duckdb.connect(str(self.db_path))
            self._con.execute("SET TimeZone='UTC'")
            self._migrate()
        except Exception:
            connection = getattr(self, "_con", None)
            if connection is not None:
                connection.close()
            raise

    def _migrate(self) -> None:
        self._con.execute("BEGIN TRANSACTION")
        try:
            for ddl in BIG_TRADES_TABLE_DDLS:
                self._con.execute(ddl)
            for ddl in BIG_TRADES_INDEX_DDL:
                self._con.execute(ddl)
            current = self._con.execute(
                "SELECT schema_version, logic_version FROM big_trades_schema_meta WHERE component = ?",
                ["big_trades"],
            ).fetchone()
            if current is None:
                self._con.execute(
                    "INSERT INTO big_trades_schema_meta VALUES (?, ?, ?, ?)",
                    ["big_trades", BIG_TRADES_SCHEMA_VERSION, BIG_TRADES_LOGIC_VERSION, datetime.now(UTC)],
                )
            elif current != (BIG_TRADES_SCHEMA_VERSION, BIG_TRADES_LOGIC_VERSION):
                raise BigTradesStorageIntegrityError(
                    f"unsupported Big Trades schema metadata: {current!r}"
                )
            self._validate_schema_columns()
            self._con.execute("COMMIT")
        except Exception:
            self._con.execute("ROLLBACK")
            raise

    def _validate_schema_columns(self) -> None:
        for table_name, schema in BIG_TRADES_ARROW_SCHEMAS.items():
            columns = [
                row[1]
                for row in self._con.execute(f"PRAGMA table_info('{table_name}')").fetchall()
            ]
            if columns != schema.names:
                raise BigTradesStorageIntegrityError(
                    f"Big Trades schema column mismatch for {table_name}"
                )

    def _fault(self, stage: str, table_name: str) -> None:
        if self._fault_injector is not None:
            self._fault_injector(stage, table_name)

    def _existing_row(
        self,
        table_name: str,
        row: Mapping[str, Any],
        key_columns: tuple[str, ...],
    ) -> Optional[dict[str, Any]]:
        where = " AND ".join(f"{name} = ?" for name in key_columns)
        cursor = self._con.execute(
            f"SELECT * FROM {table_name} WHERE {where}",
            [row[name] for name in key_columns],
        )
        found = cursor.fetchone()
        if found is None:
            return None
        names = [item[0] for item in cursor.description]
        return dict(zip(names, found, strict=True))

    def _classify_rows(
        self,
        table_name: str,
        rows: tuple[dict[str, Any], ...],
    ) -> tuple[list[dict[str, Any]], int]:
        columns = BIG_TRADES_ARROW_SCHEMAS[table_name].names
        key_columns = _TABLE_KEYS[table_name]
        new_rows: list[dict[str, Any]] = []
        duplicates = 0
        seen: dict[tuple[Any, ...], str] = {}
        for row in rows:
            key = tuple(row[name] for name in key_columns)
            fingerprint = _row_fingerprint(row, columns)
            previous = seen.get(key)
            if previous is not None:
                if previous != fingerprint:
                    raise BigTradesContentCollision(f"in-batch identity collision in {table_name}: {key!r}")
                duplicates += 1
                continue
            seen[key] = fingerprint
            existing = self._existing_row(table_name, row, key_columns)
            if existing is None:
                new_rows.append(row)
                continue
            if _row_fingerprint(existing, columns) != fingerprint:
                raise BigTradesContentCollision(f"durable identity collision in {table_name}: {key!r}")
            duplicates += 1
        return new_rows, duplicates

    def _insert_rows(
        self,
        table_name: str,
        rows: tuple[dict[str, Any], ...],
    ) -> tuple[int, int]:
        if not rows:
            return 0, 0
        new_rows, duplicates = self._classify_rows(table_name, rows)
        if not new_rows:
            return 0, duplicates
        self._fault("before_insert", table_name)
        arrow_table = table_from_rows(table_name, new_rows)
        self._con.register("_big_trades_batch", arrow_table)
        try:
            self._con.execute(f"INSERT INTO {table_name} SELECT * FROM _big_trades_batch")
        except BigTradesStorageError:
            raise
        except Exception as exc:
            raise BigTradesContentCollision(f"{table_name} insert rejected: {exc}") from exc
        finally:
            self._con.unregister("_big_trades_batch")
        self._fault("after_insert", table_name)
        return len(new_rows), duplicates

    def _identity_exists(self, table_name: str, column: str, value: Any) -> bool:
        return (
            self._con.execute(
                f"SELECT 1 FROM {table_name} WHERE {column} = ? LIMIT 1", [value]
            ).fetchone()
            is not None
        )

    def _validate_foreign_key_equivalents(
        self,
        table_rows: Mapping[str, tuple[dict[str, Any], ...]],
    ) -> None:
        offered_events = {row["event_id"] for row in table_rows.get("big_trade_events", ())}
        offered_zones = {row["zone_id"] for row in table_rows.get("big_trade_reaction_zones", ())}
        offered_settings = {
            row["settings_id"] for row in table_rows.get("big_trade_settings_history", ())
        }
        offered_calibrations = {
            row["calibration_id"] for row in table_rows.get("big_trade_calibrations", ())
        }

        def event_exists(event_id: str) -> bool:
            return event_id in offered_events or self._identity_exists(
                "big_trade_events", "event_id", event_id
            )

        def zone_exists(zone_id: str) -> bool:
            return zone_id in offered_zones or self._identity_exists(
                "big_trade_reaction_zones", "zone_id", zone_id
            )

        for row in table_rows.get("big_trade_event_fills", ()):
            if not event_exists(row["event_id"]):
                raise BigTradesStorageIntegrityError("event fill references a missing event")
        for row in table_rows.get("big_trade_reaction_zones", ()):
            if not event_exists(row["origin_event_id"]):
                raise BigTradesStorageIntegrityError("reaction zone references a missing origin event")
        for table_name in (
            "big_trade_zone_interactions",
            "big_trade_result_snapshots",
            "big_trade_zone_candle_observations",
            "big_trade_zone_state_checkpoints",
            "big_trade_user_assessments",
        ):
            for row in table_rows.get(table_name, ()):
                if not zone_exists(row["zone_id"]):
                    raise BigTradesStorageIntegrityError(
                        f"{table_name} references a missing zone"
                    )
        for row in table_rows.get("big_trade_zone_event_links", ()):
            if not zone_exists(row["zone_id"]):
                raise BigTradesStorageIntegrityError("zone link references a missing zone")
            if not event_exists(row["origin_event_id"]):
                raise BigTradesStorageIntegrityError("zone link references a missing origin event")
            if not event_exists(row["linked_event_id"]):
                raise BigTradesStorageIntegrityError("zone link references a missing linked event")
            origin = self._con.execute(
                "SELECT origin_event_id FROM big_trade_reaction_zones WHERE zone_id = ?",
                [row["zone_id"]],
            ).fetchone()
            offered_origin = next(
                (
                    zone["origin_event_id"]
                    for zone in table_rows.get("big_trade_reaction_zones", ())
                    if zone["zone_id"] == row["zone_id"]
                ),
                None,
            )
            if (offered_origin if offered_origin is not None else origin[0] if origin else None) != row[
                "origin_event_id"
            ]:
                raise BigTradesStorageIntegrityError("zone link origin identity mismatch")
        for row in table_rows.get("big_trade_settings_history", ()):
            calibration_id = row.get("calibration_id")
            if calibration_id is not None and calibration_id not in offered_calibrations and not self._identity_exists(
                "big_trade_calibrations", "calibration_id", calibration_id
            ):
                raise BigTradesStorageIntegrityError("settings references a missing calibration")
        for row in table_rows.get("big_trade_activation_history", ()):
            if row["settings_id"] not in offered_settings and not self._identity_exists(
                "big_trade_settings_history", "settings_id", row["settings_id"]
            ):
                raise BigTradesStorageIntegrityError("activation references missing settings")
            calibration_id = row.get("calibration_id")
            if calibration_id is not None and calibration_id not in offered_calibrations and not self._identity_exists(
                "big_trade_calibrations", "calibration_id", calibration_id
            ):
                raise BigTradesStorageIntegrityError("activation references missing calibration")

    def _commit_rows(
        self,
        *,
        batch_id: str,
        kind: str,
        table_rows: Mapping[str, Iterable[Mapping[str, Any]]],
        strict_origin_duplicate: bool = False,
    ) -> StorageCommitResult:
        materialized = {
            table_name: tuple(dict(row) for row in rows)
            for table_name, rows in table_rows.items()
        }
        if not materialized or not any(materialized.values()):
            raise BigTradesStorageIntegrityError("storage batch has no rows")
        with self._lock:
            self._con.execute("BEGIN TRANSACTION")
            inserted: dict[str, int] = {}
            duplicates = 0
            try:
                self._validate_foreign_key_equivalents(materialized)
                if strict_origin_duplicate:
                    event_row = materialized["big_trade_events"][0]
                    parent_exists = self._existing_row(
                        "big_trade_events", event_row, _TABLE_KEYS["big_trade_events"]
                    ) is not None
                    classifications = {
                        table_name: self._classify_rows(table_name, rows)
                        for table_name, rows in materialized.items()
                    }
                    if parent_exists:
                        if any(new_rows for new_rows, _ in classifications.values()):
                            raise BigTradesStorageIntegrityError(
                                "existing origin parent has an incomplete durable batch"
                            )
                        duplicates = sum(count for _, count in classifications.values())
                        inserted = {table_name: 0 for table_name in materialized}
                    else:
                        if any(count for _, count in classifications.values()):
                            raise BigTradesStorageIntegrityError(
                                "new origin parent collides with an existing child row"
                            )
                        for table_name, rows in materialized.items():
                            count, duplicate_count = self._insert_rows(table_name, rows)
                            inserted[table_name] = count
                            duplicates += duplicate_count
                else:
                    for table_name, rows in materialized.items():
                        count, duplicate_count = self._insert_rows(table_name, rows)
                        inserted[table_name] = count
                        duplicates += duplicate_count
                self._fault("before_commit", kind)
                self._con.execute("COMMIT")
            except Exception:
                self._con.execute("ROLLBACK")
                raise

        parquet_status = ParquetCommitStatus.DISABLED
        if self._parquet is not None:
            parquet_status = ParquetCommitStatus.COMMITTED
            try:
                self._parquet.commit(batch_id, materialized)
                self._parquet_pending.pop(batch_id, None)
            except Exception as exc:  # noqa: BLE001 - DuckDB commit remains authoritative
                parquet_status = ParquetCommitStatus.PENDING
                self._parquet_pending[batch_id] = (kind, materialized)
                logger.error(
                    "Big Trades DuckDB committed but Parquet is pending batch_id=%s error=%r",
                    batch_id,
                    exc,
                )
        return StorageCommitResult(batch_id, kind, inserted, duplicates, parquet_status)

    def insert_origin_batch(self, batch: BigTradeOriginStorageBatch) -> StorageCommitResult:
        return self._commit_rows(
            batch_id=batch.batch_id,
            kind="big_trade_origin_batch",
            table_rows={
                "big_trade_events": (batch.event,),
                "big_trade_event_fills": batch.fills,
                "big_trade_reaction_zones": (batch.zone,),
                "big_trade_zone_interactions": (batch.created_interaction,),
                "big_trade_zone_event_links": batch.prior_zone_links,
            },
            strict_origin_duplicate=True,
        )

    def insert_rows(
        self,
        *,
        batch_id: str,
        kind: str,
        table_name: str,
        rows: Iterable[Mapping[str, Any]],
    ) -> StorageCommitResult:
        if table_name not in BIG_TRADES_ARROW_SCHEMAS:
            raise BigTradesStorageIntegrityError(f"unknown Big Trades table {table_name}")
        return self._commit_rows(
            batch_id=batch_id,
            kind=kind,
            table_rows={table_name: rows},
        )

    def retry_parquet_pending(self) -> int:
        if self._parquet is None:
            return 0
        committed = 0
        for batch_id, (_, table_rows) in tuple(self._parquet_pending.items()):
            try:
                self._parquet.commit(batch_id, table_rows)
            except Exception:  # noqa: BLE001 - remains pending and visible in status
                continue
            self._parquet_pending.pop(batch_id, None)
            committed += 1
        return committed

    @property
    def parquet_pending(self) -> int:
        return len(self._parquet_pending)

    def fetch_rows(
        self,
        table_name: str,
        *,
        where: str = "",
        parameters: Iterable[Any] = (),
        order_by: str = "",
    ) -> tuple[dict[str, Any], ...]:
        if table_name not in BIG_TRADES_ARROW_SCHEMAS and table_name != "big_trades_schema_meta":
            raise ValueError("unknown Big Trades table")
        sql = f"SELECT * FROM {table_name}"
        if where:
            sql += f" WHERE {where}"
        if order_by:
            sql += f" ORDER BY {order_by}"
        with self._lock:
            cursor = self._con.execute(sql, list(parameters))
            names = [item[0] for item in cursor.description]
            return tuple(
                {
                    name: _canonical_db_value(value)
                    for name, value in zip(names, values, strict=True)
                }
                for values in cursor.fetchall()
            )

    def count(self, table_name: str) -> int:
        if table_name not in BIG_TRADES_ARROW_SCHEMAS:
            raise ValueError("unknown Big Trades table")
        with self._lock:
            return int(self._con.execute(f"SELECT count(*) FROM {table_name}").fetchone()[0])

    def close(self) -> None:
        with self._lock:
            self._con.close()


@dataclass(frozen=True)
class _StorageCommand:
    batch_id: str
    kind: str
    payload: Any
    future: CommitFuture
    submitted_at: float


_STOP = object()


def _batch_id(kind: str, rows: Iterable[Mapping[str, Any]]) -> str:
    buffered = tuple(dict(row) for row in rows)
    return "btwrite2_" + content_hash({"kind": kind, "rows": buffered})


class BigTradesBackgroundStorageWriter:
    """Bounded FIFO writer that acknowledges actual DuckDB commits."""

    _ROW_KIND_TABLE = {
        "big_trade_zone_interactions": "big_trade_zone_interactions",
        "big_trade_zone_links": "big_trade_zone_event_links",
        "big_trade_result_snapshots": "big_trade_result_snapshots",
        "big_trade_zone_candles": "big_trade_zone_candle_observations",
        "big_trade_zone_checkpoints": "big_trade_zone_state_checkpoints",
        "big_trade_user_assessments": "big_trade_user_assessments",
        "big_trade_session_stats": "big_trade_session_stats",
        "big_trade_calibration": "big_trade_calibrations",
        "big_trade_settings": "big_trade_settings_history",
        "big_trade_activation": "big_trade_activation_history",
    }

    def __init__(
        self,
        store: BigTradesDuckDbStore,
        *,
        queue_maxsize: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
        start: bool = True,
    ) -> None:
        if not isinstance(queue_maxsize, int) or isinstance(queue_maxsize, bool) or queue_maxsize < 1:
            raise ValueError("queue_maxsize must be a positive integer")
        self.store = store
        self._queue: Queue[Any] = Queue(maxsize=queue_maxsize)
        self._clock = clock
        self._thread = Thread(target=self._run, name="big-trades-storage", daemon=True)
        self._started = False
        self._closed = False
        self._stats_lock = RLock()
        self._latencies_ms: deque[float] = deque(maxlen=4096)
        self.stats: dict[str, int] = {
            "origin_batches_committed": 0,
            "origin_batches_failed": 0,
            "events_written": 0,
            "fills_written": 0,
            "zones_written": 0,
            "interactions_written": 0,
            "links_written": 0,
            "snapshots_written": 0,
            "candle_observations_written": 0,
            "zone_checkpoints_written": 0,
            "assessments_written": 0,
            "duplicates": 0,
            "collisions": 0,
            "queue_full": 0,
            "parquet_pending": 0,
            "parquet_failures": 0,
        }
        if start:
            self.start()

    def start(self) -> None:
        if self._closed:
            raise RuntimeError("Big Trades storage writer is closed")
        if not self._started:
            self._thread.start()
            self._started = True

    def _submit(self, kind: str, batch_id: str, payload: Any) -> CommitFuture:
        if self._closed:
            raise RuntimeError("Big Trades storage writer is closed")
        if not self._started:
            self.start()
        future = CommitFuture()
        submitted = self._clock()
        command = _StorageCommand(batch_id, kind, payload, future, submitted)
        try:
            self._queue.put_nowait(command)
        except Full:
            completed = self._clock()
            with self._stats_lock:
                self.stats["queue_full"] += 1
            future._set_result(
                CommitAck(
                    batch_id=batch_id,
                    kind=kind,
                    success=False,
                    duckdb_committed=False,
                    parquet_status=ParquetCommitStatus.DISABLED,
                    submitted_at_monotonic=submitted,
                    completed_at_monotonic=completed,
                    latency_ms=(completed - submitted) * 1000,
                    error_code="QUEUE_FULL",
                    error="Big Trades storage queue is full",
                )
            )
        return future

    def submit_origin_batch(self, batch: BigTradeOriginStorageBatch) -> CommitFuture:
        return self._submit("big_trade_origin_batch", batch.batch_id, batch)

    def _submit_rows(self, kind: str, rows: Iterable[Mapping[str, Any]]) -> CommitFuture:
        buffered = tuple(dict(row) for row in rows)
        return self._submit(kind, _batch_id(kind, buffered), buffered)

    def submit_zone_interactions(self, items: Iterable[ZoneInteraction]) -> CommitFuture:
        return self._submit_rows("big_trade_zone_interactions", map(interaction_to_row, items))

    def submit_zone_links(self, items: Iterable[ZoneEventLink]) -> CommitFuture:
        return self._submit_rows("big_trade_zone_links", map(link_to_row, items))

    def submit_result_snapshots(self, items: Iterable[ResultSnapshot]) -> CommitFuture:
        return self._submit_rows("big_trade_result_snapshots", map(snapshot_to_row, items))

    def submit_zone_candles(self, items: Iterable[ZoneCandleObservation]) -> CommitFuture:
        return self._submit_rows("big_trade_zone_candles", map(candle_observation_to_row, items))

    def submit_zone_checkpoints(self, items: Iterable[ZoneStateCheckpoint]) -> CommitFuture:
        return self._submit_rows("big_trade_zone_checkpoints", map(checkpoint_to_row, items))

    def submit_user_assessments(self, items: Iterable[UserAssessment]) -> CommitFuture:
        return self._submit_rows("big_trade_user_assessments", map(assessment_to_row, items))

    def submit_session_stats(self, items: Iterable[SessionStatsArtifact]) -> CommitFuture:
        return self._submit_rows("big_trade_session_stats", map(session_stats_to_row, items))

    def submit_calibration(self, item: CalibrationArtifact) -> CommitFuture:
        return self._submit_rows("big_trade_calibration", (calibration_to_row(item),))

    def submit_settings(self, request: SettingsRequest, version: SettingsVersion) -> CommitFuture:
        return self._submit_rows("big_trade_settings", (settings_history_to_row(request, version),))

    def submit_activation(self, item: ActivationArtifact) -> CommitFuture:
        return self._submit_rows("big_trade_activation", (activation_to_row(item),))

    def _execute(self, command: _StorageCommand) -> StorageCommitResult:
        if command.kind == "big_trade_origin_batch":
            return self.store.insert_origin_batch(command.payload)
        table_name = self._ROW_KIND_TABLE.get(command.kind)
        if table_name is None:
            raise BigTradesStorageIntegrityError(f"unknown storage kind {command.kind}")
        return self.store.insert_rows(
            batch_id=command.batch_id,
            kind=command.kind,
            table_name=table_name,
            rows=command.payload,
        )

    def _record_success(self, result: StorageCommitResult, latency_ms: float) -> None:
        table_counter = {
            "big_trade_events": "events_written",
            "big_trade_event_fills": "fills_written",
            "big_trade_reaction_zones": "zones_written",
            "big_trade_zone_interactions": "interactions_written",
            "big_trade_zone_event_links": "links_written",
            "big_trade_result_snapshots": "snapshots_written",
            "big_trade_zone_candle_observations": "candle_observations_written",
            "big_trade_zone_state_checkpoints": "zone_checkpoints_written",
            "big_trade_user_assessments": "assessments_written",
        }
        with self._stats_lock:
            if result.kind == "big_trade_origin_batch":
                self.stats["origin_batches_committed"] += 1
            for table_name, count in result.inserted.items():
                counter = table_counter.get(table_name)
                if counter is not None:
                    self.stats[counter] += count
            self.stats["duplicates"] += result.duplicates
            self.stats["parquet_pending"] = self.store.parquet_pending
            if result.parquet_status == ParquetCommitStatus.PENDING:
                self.stats["parquet_failures"] += 1
            self._latencies_ms.append(latency_ms)

    def _run(self) -> None:
        while True:
            try:
                command = self._queue.get(timeout=0.25)
            except Empty:
                self.store.retry_parquet_pending()
                with self._stats_lock:
                    self.stats["parquet_pending"] = self.store.parquet_pending
                continue
            if command is _STOP:
                self._queue.task_done()
                break
            assert isinstance(command, _StorageCommand)
            try:
                result = self._execute(command)
                completed = self._clock()
                latency_ms = (completed - command.submitted_at) * 1000
                self._record_success(result, latency_ms)
                ack = CommitAck(
                    batch_id=command.batch_id,
                    kind=command.kind,
                    success=True,
                    duckdb_committed=True,
                    parquet_status=result.parquet_status,
                    submitted_at_monotonic=command.submitted_at,
                    completed_at_monotonic=completed,
                    latency_ms=latency_ms,
                    inserted=result.inserted,
                    duplicates=result.duplicates,
                )
            except Exception as exc:  # noqa: BLE001 - returned as explicit failed ack
                completed = self._clock()
                latency_ms = (completed - command.submitted_at) * 1000
                collision = isinstance(exc, BigTradesContentCollision)
                with self._stats_lock:
                    if command.kind == "big_trade_origin_batch":
                        self.stats["origin_batches_failed"] += 1
                    if collision:
                        self.stats["collisions"] += 1
                    self._latencies_ms.append(latency_ms)
                ack = CommitAck(
                    batch_id=command.batch_id,
                    kind=command.kind,
                    success=False,
                    duckdb_committed=False,
                    parquet_status=ParquetCommitStatus.DISABLED,
                    submitted_at_monotonic=command.submitted_at,
                    completed_at_monotonic=completed,
                    latency_ms=latency_ms,
                    error_code="CONTENT_COLLISION" if collision else "STORAGE_WRITE_FAILED",
                    error=str(exc),
                )
            finally:
                self._queue.task_done()
            command.future._set_result(ack)

    def statistics(self) -> dict[str, Any]:
        with self._stats_lock:
            result: dict[str, Any] = dict(self.stats)
            latencies = tuple(self._latencies_ms)
        result["commit_ack_latency_ms"] = {
            "p50": statistics.median(latencies) if latencies else None,
            "p95": _percentile(latencies, 0.95),
            "p99": _percentile(latencies, 0.99),
        }
        result["queue_pending"] = self._queue.qsize()
        return result

    def join(self) -> None:
        self._queue.join()

    def close(self, *, drain: bool = True, close_store: bool = True) -> None:
        if self._closed:
            return
        if drain:
            self.join()
        self._closed = True
        if self._started:
            self._queue.put(_STOP)
            self._thread.join(timeout=10)
            if self._thread.is_alive():
                raise RuntimeError("Big Trades storage writer did not stop")
        if close_store:
            self.store.close()

    def __enter__(self) -> "BigTradesBackgroundStorageWriter":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()


def _percentile(values: Iterable[float], percentile: float) -> Optional[float]:
    ordered = sorted(values)
    if not ordered:
        return None
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * percentile + 0.5)))
    return ordered[index]
