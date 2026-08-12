"""Recover explicitly identified Binance USD-M receiver trade gaps.

The command is fail-closed.  Fetching only creates an immutable staging
directory.  Bundle construction reads a stopped/snapshotted DuckDB and Parquet
mirror.  Applying a bundle requires explicit maintenance and semantic-loss
acknowledgements; it never controls the production service itself.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import duckdb
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from src.database.schema import TRADES_SCHEMA  # noqa: E402


UTC = timezone.utc
TRADE_COLUMNS = tuple(field.name for field in TRADES_SCHEMA)
TRADE_COLUMN_SET = set(TRADE_COLUMNS)
MAX_BINANCE_PAGE = 500
DEFAULT_BASE_URL = "https://fapi.binance.com"


class RecoveryError(RuntimeError):
    """A recovery safety or integrity gate failed."""


@dataclass(frozen=True)
class TradeIdRange:
    start_id: int
    end_id: int

    @property
    def count(self) -> int:
        return self.end_id - self.start_id + 1


@dataclass(frozen=True)
class IncidentSpec:
    schema_version: int
    incident_id: str
    symbol: str
    expected_trade_count: int
    ranges: tuple[TradeIdRange, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "incident_id": self.incident_id,
            "symbol": self.symbol,
            "expected_trade_count": self.expected_trade_count,
            "ranges": [
                {"start_id": item.start_id, "end_id": item.end_id}
                for item in self.ranges
            ],
        }


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_incident_spec(path: Path) -> IncidentSpec:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise RecoveryError(f"cannot read incident manifest: {exc}") from exc
    try:
        ranges = tuple(
            TradeIdRange(int(item["start_id"]), int(item["end_id"]))
            for item in payload["ranges"]
        )
        spec = IncidentSpec(
            schema_version=int(payload["schema_version"]),
            incident_id=str(payload["incident_id"]),
            symbol=str(payload["symbol"]).upper(),
            expected_trade_count=int(payload["expected_trade_count"]),
            ranges=ranges,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RecoveryError(f"invalid incident manifest: {exc}") from exc
    if spec.schema_version != 1:
        raise RecoveryError("unsupported incident manifest schema_version")
    if not spec.incident_id or not spec.symbol or not spec.ranges:
        raise RecoveryError("incident_id, symbol, and ranges are required")
    previous_end: int | None = None
    for item in spec.ranges:
        if item.start_id < 0 or item.end_id < item.start_id:
            raise RecoveryError("invalid trade ID range")
        if previous_end is not None and item.start_id <= previous_end:
            raise RecoveryError("trade ID ranges must be sorted and non-overlapping")
        previous_end = item.end_id
    actual_count = sum(item.count for item in spec.ranges)
    if actual_count != spec.expected_trade_count:
        raise RecoveryError(
            f"range count mismatch: expected={spec.expected_trade_count} actual={actual_count}"
        )
    return spec


def _expected_ids(spec: IncidentSpec) -> tuple[int, ...]:
    return tuple(
        trade_id
        for item in spec.ranges
        for trade_id in range(item.start_id, item.end_id + 1)
    )


def collect_rest_rows(
    spec: IncidentSpec,
    fetch_page: Callable[[int, int], Sequence[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Collect all configured IDs and reject short, shifted, or duplicate pages."""

    collected: list[dict[str, Any]] = []
    for item in spec.ranges:
        cursor = item.start_id
        while cursor <= item.end_id:
            limit = min(MAX_BINANCE_PAGE, item.end_id - cursor + 1)
            page = list(fetch_page(cursor, limit))
            if len(page) != limit:
                raise RecoveryError(
                    f"short Binance page at fromId={cursor}: expected={limit} actual={len(page)}"
                )
            try:
                ids = [int(row["id"]) for row in page]
            except (KeyError, TypeError, ValueError) as exc:
                raise RecoveryError(f"invalid Binance page at fromId={cursor}") from exc
            expected = list(range(cursor, cursor + limit))
            if ids != expected:
                raise RecoveryError(
                    f"non-contiguous Binance page at fromId={cursor}: "
                    f"expected={expected[0]}..{expected[-1]}"
                )
            collected.extend(page)
            cursor += limit
    actual_ids = tuple(int(row["id"]) for row in collected)
    if actual_ids != _expected_ids(spec):
        raise RecoveryError("collected trade IDs do not exactly match incident manifest")
    return collected


class BinanceHistoricalTradeFetcher:
    """Rate-paced client for GET /fapi/v1/historicalTrades."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        min_request_interval_seconds: float = 5.1,
        timeout_seconds: float = 20.0,
        max_retries: int = 3,
    ) -> None:
        if not api_key:
            raise RecoveryError("Binance API key is empty")
        if min_request_interval_seconds < 0 or timeout_seconds <= 0 or max_retries < 0:
            raise RecoveryError("invalid Binance client timing/retry configuration")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._interval = min_request_interval_seconds
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._last_request_started: float | None = None

    def __call__(self, from_id: int, limit: int) -> Sequence[dict[str, Any]]:
        query = urllib.parse.urlencode(
            {"symbol": self.symbol, "fromId": from_id, "limit": limit}
        )
        url = f"{self._base_url}/fapi/v1/historicalTrades?{query}"
        for attempt in range(self._max_retries + 1):
            if self._last_request_started is not None:
                elapsed = time.monotonic() - self._last_request_started
                if elapsed < self._interval:
                    time.sleep(self._interval - elapsed)
            self._last_request_started = time.monotonic()
            request = urllib.request.Request(url, headers={"X-MBX-APIKEY": self._api_key})
            try:
                with urllib.request.urlopen(request, timeout=self._timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, list):
                    raise RecoveryError("Binance historicalTrades response is not an array")
                return payload
            except urllib.error.HTTPError as exc:
                retryable = exc.code == 429 or 500 <= exc.code < 600
                if not retryable or attempt == self._max_retries:
                    raise RecoveryError(f"Binance HTTP error {exc.code}") from exc
                retry_after = exc.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else min(60.0, 2.0**attempt)
                time.sleep(max(delay, self._interval))
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt == self._max_retries:
                    raise RecoveryError(f"Binance request failed: {type(exc).__name__}") from exc
                time.sleep(min(60.0, 2.0**attempt))
        raise AssertionError("unreachable")

    def bind_symbol(self, symbol: str) -> "BinanceHistoricalTradeFetcher":
        self.symbol = symbol
        return self


def _decimal(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise RecoveryError(f"invalid {field}") from exc
    if not result.is_finite() or result <= 0:
        raise RecoveryError(f"{field} must be finite and positive")
    normalized = result.as_tuple()
    fractional_digits = max(0, -normalized.exponent)
    integer_digits = max(0, len(normalized.digits) + normalized.exponent)
    if fractional_digits > 8 or integer_digits + fractional_digits > 20:
        raise RecoveryError(f"{field} does not fit DECIMAL(20,8)")
    return result


def canonicalize_rest_rows(
    rows: Iterable[dict[str, Any]],
    *,
    symbol: str,
    accept_event_time_surrogate: bool,
) -> list[dict[str, Any]]:
    if not accept_event_time_surrogate:
        raise RecoveryError(
            "Binance REST has no WebSocket event time E; "
            "--accept-event-time-surrogate is required"
        )
    result: list[dict[str, Any]] = []
    for raw in rows:
        try:
            trade_id = int(raw["id"])
            milliseconds = int(raw["time"])
            maker = raw["isBuyerMaker"]
        except (KeyError, TypeError, ValueError) as exc:
            raise RecoveryError("invalid Binance historical trade row") from exc
        if trade_id < 0 or milliseconds < 0 or type(maker) is not bool:
            raise RecoveryError("invalid trade id, time, or isBuyerMaker")
        trade_time = datetime.fromtimestamp(milliseconds / 1000, tz=UTC)
        result.append(
            {
                "event_time": trade_time,
                "trade_time": trade_time,
                "trade_id": trade_id,
                "symbol": symbol,
                "price": _decimal(raw.get("price"), "price"),
                "quantity": _decimal(raw.get("qty"), "quantity"),
                "side": "SELL" if maker else "BUY",
            }
        )
    return result


def _atomic_output_directory(output_dir: Path) -> Path:
    output = output_dir.resolve()
    if output.exists():
        raise RecoveryError(f"immutable output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp-{uuid.uuid4().hex}")
    temporary.mkdir()
    return temporary


def _finish_atomic_directory(temporary: Path, output_dir: Path) -> None:
    os.replace(temporary, output_dir.resolve())


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def stage_rest_rows(
    *,
    spec: IncidentSpec,
    raw_rows: Sequence[dict[str, Any]],
    output_dir: Path,
    source: str,
    accept_event_time_surrogate: bool,
) -> dict[str, Any]:
    raw_ids = tuple(int(row.get("id", -1)) for row in raw_rows)
    if raw_ids != _expected_ids(spec):
        raise RecoveryError("raw rows do not exactly cover the incident manifest")
    canonical = canonicalize_rest_rows(
        raw_rows,
        symbol=spec.symbol,
        accept_event_time_surrogate=accept_event_time_surrogate,
    )
    temporary = _atomic_output_directory(output_dir)
    try:
        raw_path = temporary / "raw.jsonl"
        with raw_path.open("w", encoding="utf-8", newline="\n") as stream:
            for row in raw_rows:
                stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        trades_path = temporary / "trades.parquet"
        pq.write_table(
            pa.Table.from_pylist(canonical, schema=TRADES_SCHEMA),
            trades_path,
            compression="snappy",
        )
        spec_digest = _sha256_bytes(_canonical_json(spec.as_dict()))
        manifest = {
            "schema_version": 1,
            "artifact_type": "RECEIVER_TRADE_RECOVERY_STAGE",
            "status": "READY",
            "created_at_utc": datetime.now(UTC).isoformat(),
            "incident": spec.as_dict(),
            "incident_sha256": spec_digest,
            "source": source,
            "trade_count": len(canonical),
            "raw_file": {"path": "raw.jsonl", "sha256": sha256_file(raw_path)},
            "canonical_file": {
                "path": "trades.parquet",
                "sha256": sha256_file(trades_path),
            },
            "semantic_deviation": {
                "event_time": "trade_time surrogate",
                "reason": "Binance historicalTrades does not expose WebSocket event time E",
                "explicitly_accepted": True,
            },
            "production_mutations": 0,
        }
        _write_json(temporary / "manifest.json", manifest)
        _finish_atomic_directory(temporary, output_dir)
        return manifest
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _load_stage(stage_dir: Path) -> tuple[dict[str, Any], Path, list[dict[str, Any]]]:
    root = stage_dir.resolve()
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise RecoveryError(f"cannot read stage manifest: {exc}") from exc
    if manifest.get("artifact_type") != "RECEIVER_TRADE_RECOVERY_STAGE":
        raise RecoveryError("invalid recovery stage artifact type")
    canonical = root / manifest["canonical_file"]["path"]
    if sha256_file(canonical) != manifest["canonical_file"]["sha256"]:
        raise RecoveryError("stage canonical file hash mismatch")
    raw = root / manifest["raw_file"]["path"]
    if sha256_file(raw) != manifest["raw_file"]["sha256"]:
        raise RecoveryError("stage raw file hash mismatch")
    table = pq.read_table(canonical, schema=TRADES_SCHEMA)
    rows = table.to_pylist()
    if len(rows) != int(manifest["trade_count"]):
        raise RecoveryError("stage trade count mismatch")
    ids = [int(row["trade_id"]) for row in rows]
    if len(ids) != len(set(ids)):
        raise RecoveryError("stage contains duplicate trade IDs")
    return manifest, canonical, rows


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _row_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        _utc(row["event_time"]),
        _utc(row["trade_time"]),
        int(row["trade_id"]),
        str(row["symbol"]),
        Decimal(str(row["price"])),
        Decimal(str(row["quantity"])),
        str(row["side"]),
    )


def _tuples_to_rows(rows: Iterable[tuple[Any, ...]]) -> list[dict[str, Any]]:
    return [dict(zip(TRADE_COLUMNS, row, strict=True)) for row in rows]


def _duckdb_matches(source_db: Path, stage_file: Path, symbol: str) -> list[dict[str, Any]]:
    if not source_db.is_file():
        raise RecoveryError(f"DuckDB does not exist: {source_db}")
    try:
        connection = duckdb.connect(str(source_db.resolve()), read_only=True)
        try:
            tables = {row[0] for row in connection.execute("SHOW TABLES").fetchall()}
            if "trades" not in tables:
                raise RecoveryError("DuckDB has no trades table")
            rows = connection.execute(
                """
                SELECT t.event_time, t.trade_time, t.trade_id, t.symbol,
                       t.price, t.quantity, t.side
                FROM trades t
                INNER JOIN read_parquet(?) s ON s.trade_id = t.trade_id
                WHERE t.symbol = ?
                """,
                [str(stage_file), symbol],
            ).fetchall()
        finally:
            connection.close()
    except RecoveryError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise RecoveryError(f"cannot audit DuckDB read-only: {exc}") from exc
    return _tuples_to_rows(rows)


def _trade_parquet_files(
    parquet_root: Path, symbol: str, stage_rows: Sequence[dict[str, Any]]
) -> tuple[Path, ...]:
    dates = {_utc(row["event_time"]).date() for row in stage_rows}
    files: list[Path] = []
    for day in sorted(dates):
        partition = (
            parquet_root.resolve()
            / f"symbol={symbol}"
            / f"year={day.year:04d}"
            / f"month={day.month:02d}"
            / f"day={day.day:02d}"
        )
        if not partition.exists():
            continue
        for path in sorted(partition.glob("*.parquet")):
            try:
                names = set(pq.ParquetFile(path).schema_arrow.names)
            except Exception as exc:  # noqa: BLE001
                raise RecoveryError(f"cannot inspect Parquet file {path}: {exc}") from exc
            if TRADE_COLUMN_SET.issubset(names):
                files.append(path.resolve())
    return tuple(files)


def _parquet_matches(
    parquet_root: Path,
    stage_file: Path,
    symbol: str,
    stage_rows: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], tuple[Path, ...]]:
    files = _trade_parquet_files(parquet_root, symbol, stage_rows)
    if not files:
        return [], files
    stage_ids = pa.array(
        [int(row["trade_id"]) for row in stage_rows], type=pa.int64()
    )
    rows: list[dict[str, Any]] = []
    try:
        for path in files:
            table = pq.read_table(path, columns=list(TRADE_COLUMNS))
            matching = table.filter(pc.is_in(table["trade_id"], value_set=stage_ids))
            rows.extend(
                row for row in matching.to_pylist() if row["symbol"] == symbol
            )
    except Exception as exc:  # noqa: BLE001
        raise RecoveryError(f"cannot audit Parquet read-only: {exc}") from exc
    return rows, files


def _classify_existing(
    stage_rows: Sequence[dict[str, Any]],
    existing_rows: Sequence[dict[str, Any]],
    *,
    store: str,
) -> tuple[set[int], int]:
    stage = {int(row["trade_id"]): _row_key(row) for row in stage_rows}
    present: set[int] = set()
    duplicates = 0
    for row in existing_rows:
        trade_id = int(row["trade_id"])
        expected = stage.get(trade_id)
        if expected is None:
            continue
        if _row_key(row) != expected:
            raise RecoveryError(f"{store} conflict for trade_id={trade_id}")
        if trade_id in present:
            duplicates += 1
        present.add(trade_id)
    return present, duplicates


def audit_stage(
    *, stage_dir: Path, source_db: Path, parquet_root: Path
) -> tuple[dict[str, Any], list[dict[str, Any]], set[int], set[int]]:
    stage_manifest, stage_file, stage_rows = _load_stage(stage_dir)
    symbol = str(stage_manifest["incident"]["symbol"])
    db_rows = _duckdb_matches(source_db, stage_file, symbol)
    parquet_rows, parquet_files = _parquet_matches(
        parquet_root, stage_file, symbol, stage_rows
    )
    db_present, db_duplicates = _classify_existing(
        stage_rows, db_rows, store="DuckDB"
    )
    parquet_present, parquet_duplicates = _classify_existing(
        stage_rows, parquet_rows, store="Parquet"
    )
    all_ids = {int(row["trade_id"]) for row in stage_rows}
    report = {
        "status": "PASS",
        "trade_count": len(stage_rows),
        "duckdb": {
            "already_present": len(db_present),
            "missing": len(all_ids - db_present),
            "duplicate_rows": db_duplicates,
        },
        "parquet": {
            "already_present": len(parquet_present),
            "missing": len(all_ids - parquet_present),
            "duplicate_rows": parquet_duplicates,
            "inspected_trade_files": len(parquet_files),
        },
        "conflicts": 0,
        "production_mutations": 0,
    }
    return report, stage_rows, all_ids - db_present, all_ids - parquet_present


def _write_trade_parquet(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    pq.write_table(
        pa.Table.from_pylist(list(rows), schema=TRADES_SCHEMA),
        path,
        compression="snappy",
    )


def build_merge_bundle(
    *,
    stage_dir: Path,
    source_db: Path,
    parquet_root: Path,
    output_dir: Path,
) -> dict[str, Any]:
    stage_manifest, _, _ = _load_stage(stage_dir)
    audit, stage_rows, db_missing, parquet_missing = audit_stage(
        stage_dir=stage_dir, source_db=source_db, parquet_root=parquet_root
    )
    temporary = _atomic_output_directory(output_dir)
    try:
        files: list[dict[str, Any]] = []
        db_rows = [row for row in stage_rows if int(row["trade_id"]) in db_missing]
        if db_rows:
            db_path = temporary / "duckdb-insert.parquet"
            _write_trade_parquet(db_path, db_rows)
            files.append(
                {
                    "role": "DUCKDB_INSERT",
                    "path": db_path.name,
                    "sha256": sha256_file(db_path),
                    "row_count": len(db_rows),
                }
            )
        symbol = str(stage_manifest["incident"]["symbol"])
        grouped: dict[Any, list[dict[str, Any]]] = {}
        for row in stage_rows:
            if int(row["trade_id"]) in parquet_missing:
                grouped.setdefault(_utc(row["event_time"]).date(), []).append(row)
        for day, rows in sorted(grouped.items()):
            relative_dir = Path(
                f"symbol={symbol}/year={day.year:04d}/month={day.month:02d}/day={day.day:02d}"
            )
            directory = temporary / "parquet" / relative_dir
            directory.mkdir(parents=True, exist_ok=True)
            provisional = directory / "recovery.parquet"
            _write_trade_parquet(provisional, rows)
            digest = sha256_file(provisional)
            filename = (
                f"recovery-{stage_manifest['incident']['incident_id']}-{digest[:16]}.parquet"
            )
            final_path = directory / filename
            provisional.replace(final_path)
            files.append(
                {
                    "role": "PARQUET_PUBLISH",
                    "path": final_path.relative_to(temporary).as_posix(),
                    "target_relative_path": (relative_dir / filename).as_posix(),
                    "sha256": digest,
                    "row_count": len(rows),
                }
            )
        manifest = {
            "schema_version": 1,
            "artifact_type": "RECEIVER_TRADE_RECOVERY_MERGE_BUNDLE",
            "status": "READY",
            "created_at_utc": datetime.now(UTC).isoformat(),
            "incident": stage_manifest["incident"],
            "stage_manifest_sha256": sha256_file(stage_dir.resolve() / "manifest.json"),
            "semantic_deviation": stage_manifest["semantic_deviation"],
            "audit": audit,
            "files": files,
            "production_mutations": 0,
        }
        _write_json(temporary / "manifest.json", manifest)
        _finish_atomic_directory(temporary, output_dir)
        return manifest
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _load_bundle(bundle_dir: Path) -> dict[str, Any]:
    root = bundle_dir.resolve()
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise RecoveryError(f"cannot read merge bundle: {exc}") from exc
    if manifest.get("artifact_type") != "RECEIVER_TRADE_RECOVERY_MERGE_BUNDLE":
        raise RecoveryError("invalid merge bundle artifact type")
    for item in manifest.get("files", []):
        path = root / item["path"]
        if not path.is_file() or sha256_file(path) != item["sha256"]:
            raise RecoveryError(f"merge bundle file hash mismatch: {path}")
        if pq.ParquetFile(path).metadata.num_rows != int(item["row_count"]):
            raise RecoveryError(f"merge bundle row count mismatch: {path}")
    return manifest


def apply_merge_bundle(
    *,
    bundle_dir: Path,
    source_db: Path,
    parquet_root: Path,
    backup_dir: Path,
    apply: bool,
    maintenance_confirmed: bool,
    accept_event_time_surrogate: bool,
) -> dict[str, Any]:
    if not apply or not maintenance_confirmed:
        raise RecoveryError("--apply and --maintenance-confirmed are both required")
    if not accept_event_time_surrogate:
        raise RecoveryError("--accept-event-time-surrogate is required")
    manifest = _load_bundle(bundle_dir)
    db_path = source_db.resolve()
    pq_root = parquet_root.resolve()
    backup = backup_dir.resolve()
    if not db_path.is_file() or not pq_root.is_dir():
        raise RecoveryError("production DuckDB and Parquet root must already exist")
    wal_path = Path(f"{db_path}.wal")
    if wal_path.exists():
        raise RecoveryError(f"DuckDB WAL exists; maintenance gate failed: {wal_path}")
    if backup.exists():
        raise RecoveryError(f"backup directory already exists: {backup}")
    backup.mkdir(parents=True)
    db_backup = backup / db_path.name
    shutil.copy2(db_path, db_backup)
    if sha256_file(db_path) != sha256_file(db_backup):
        raise RecoveryError("DuckDB backup verification failed")

    published_now: list[Path] = []
    already_published: list[Path] = []
    connection: duckdb.DuckDBPyConnection | None = None
    committed = False
    try:
        for item in manifest["files"]:
            if item["role"] != "PARQUET_PUBLISH":
                continue
            source = bundle_dir.resolve() / item["path"]
            target = pq_root / item["target_relative_path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if sha256_file(target) != item["sha256"]:
                    raise RecoveryError(f"Parquet target conflict: {target}")
                already_published.append(target)
                continue
            temporary = target.with_name(f".{target.name}.tmp-{uuid.uuid4().hex}")
            shutil.copy2(source, temporary)
            if sha256_file(temporary) != item["sha256"]:
                temporary.unlink(missing_ok=True)
                raise RecoveryError(f"Parquet publish verification failed: {target}")
            os.replace(temporary, target)
            published_now.append(target)

        inserts = [item for item in manifest["files"] if item["role"] == "DUCKDB_INSERT"]
        missing_before = 0
        if inserts:
            if len(inserts) != 1:
                raise RecoveryError("merge bundle has multiple DuckDB insert files")
            insert_path = bundle_dir.resolve() / inserts[0]["path"]
            connection = duckdb.connect(str(db_path))
            connection.execute("BEGIN TRANSACTION")
            conflict_count = int(
                connection.execute(
                    """
                    SELECT count(*)
                    FROM trades t
                    INNER JOIN read_parquet(?) s ON s.trade_id = t.trade_id
                    WHERE t.event_time IS DISTINCT FROM s.event_time
                       OR t.trade_time IS DISTINCT FROM s.trade_time
                       OR t.symbol IS DISTINCT FROM s.symbol
                       OR t.price IS DISTINCT FROM s.price
                       OR t.quantity IS DISTINCT FROM s.quantity
                       OR t.side IS DISTINCT FROM s.side
                    """,
                    [str(insert_path)],
                ).fetchone()[0]
            )
            if conflict_count:
                raise RecoveryError(f"DuckDB apply conflict count={conflict_count}")
            missing_before = int(
                connection.execute(
                    """
                    SELECT count(*) FROM read_parquet(?) s
                    WHERE NOT EXISTS (
                        SELECT 1 FROM trades t WHERE t.trade_id = s.trade_id
                    )
                    """,
                    [str(insert_path)],
                ).fetchone()[0]
            )
            connection.execute(
                """
                INSERT INTO trades
                SELECT s.event_time, s.trade_time, s.trade_id, s.symbol,
                       s.price, s.quantity, s.side
                FROM read_parquet(?) s
                WHERE NOT EXISTS (
                    SELECT 1 FROM trades t WHERE t.trade_id = s.trade_id
                )
                """,
                [str(insert_path)],
            )
            remaining = int(
                connection.execute(
                    """
                    SELECT count(*) FROM read_parquet(?) s
                    WHERE NOT EXISTS (
                        SELECT 1 FROM trades t WHERE t.trade_id = s.trade_id
                    )
                    """,
                    [str(insert_path)],
                ).fetchone()[0]
            )
            if remaining:
                raise RecoveryError(f"DuckDB apply verification missing={remaining}")
            connection.execute("COMMIT")
            committed = True
            connection.close()
            connection = None
        else:
            committed = True

        receipt = {
            "artifact_type": "RECEIVER_TRADE_RECOVERY_APPLY_RECEIPT",
            "status": "APPLIED",
            "applied_at_utc": datetime.now(UTC).isoformat(),
            "bundle_manifest_sha256": sha256_file(bundle_dir.resolve() / "manifest.json"),
            "duckdb_backup": {
                "path": str(db_backup),
                "sha256": sha256_file(db_backup),
            },
            "duckdb_rows_inserted": missing_before,
            "parquet_files_published": len(published_now),
            "parquet_files_already_present": len(already_published),
            "semantic_deviation_accepted": True,
        }
        _write_json(backup / "apply-receipt.json", receipt)
        return receipt
    except Exception:
        if connection is not None:
            try:
                if not committed:
                    connection.execute("ROLLBACK")
            finally:
                connection.close()
        if not committed:
            rollback_dir = backup / "rolled-back-parquet"
            for target in published_now:
                if target.exists():
                    rollback_target = rollback_dir / target.relative_to(pq_root)
                    rollback_target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(target), str(rollback_target))
        raise


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RecoveryError(f"invalid JSONL line {line_number}") from exc
            if not isinstance(row, dict):
                raise RecoveryError(f"JSONL line {line_number} is not an object")
            rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    stage_jsonl = commands.add_parser("stage-jsonl")
    stage_jsonl.add_argument("--incident-manifest", type=Path, required=True)
    stage_jsonl.add_argument("--input", type=Path, required=True)
    stage_jsonl.add_argument("--output", type=Path, required=True)
    stage_jsonl.add_argument("--accept-event-time-surrogate", action="store_true")

    fetch = commands.add_parser("fetch-stage")
    fetch.add_argument("--incident-manifest", type=Path, required=True)
    fetch.add_argument("--output", type=Path, required=True)
    fetch.add_argument("--api-key-env", default="BINANCE_API_KEY")
    fetch.add_argument("--base-url", default=DEFAULT_BASE_URL)
    fetch.add_argument("--min-request-interval-seconds", type=float, default=5.1)
    fetch.add_argument("--timeout-seconds", type=float, default=20.0)
    fetch.add_argument("--max-retries", type=int, default=3)
    fetch.add_argument("--accept-event-time-surrogate", action="store_true")

    bundle = commands.add_parser("build-bundle")
    bundle.add_argument("--stage", type=Path, required=True)
    bundle.add_argument("--source-db", type=Path, required=True)
    bundle.add_argument("--parquet-root", type=Path, required=True)
    bundle.add_argument("--output", type=Path, required=True)

    apply_parser = commands.add_parser("apply-bundle")
    apply_parser.add_argument("--bundle", type=Path, required=True)
    apply_parser.add_argument("--source-db", type=Path, required=True)
    apply_parser.add_argument("--parquet-root", type=Path, required=True)
    apply_parser.add_argument("--backup-dir", type=Path, required=True)
    apply_parser.add_argument("--apply", action="store_true")
    apply_parser.add_argument("--maintenance-confirmed", action="store_true")
    apply_parser.add_argument("--accept-event-time-surrogate", action="store_true")

    args = parser.parse_args()
    if args.command == "stage-jsonl":
        spec = load_incident_spec(args.incident_manifest)
        raw_rows = _read_jsonl(args.input)
        manifest = stage_rest_rows(
            spec=spec,
            raw_rows=raw_rows,
            output_dir=args.output,
            source=f"JSONL:{args.input.resolve()}",
            accept_event_time_surrogate=args.accept_event_time_surrogate,
        )
        print(json.dumps(manifest, ensure_ascii=False))
        return 0
    if args.command == "fetch-stage":
        spec = load_incident_spec(args.incident_manifest)
        api_key = os.environ.get(args.api_key_env, "")
        fetcher = BinanceHistoricalTradeFetcher(
            api_key=api_key,
            base_url=args.base_url,
            min_request_interval_seconds=args.min_request_interval_seconds,
            timeout_seconds=args.timeout_seconds,
            max_retries=args.max_retries,
        ).bind_symbol(spec.symbol)
        raw_rows = collect_rest_rows(spec, fetcher)
        manifest = stage_rest_rows(
            spec=spec,
            raw_rows=raw_rows,
            output_dir=args.output,
            source="BINANCE_USDM_HISTORICAL_TRADES",
            accept_event_time_surrogate=args.accept_event_time_surrogate,
        )
        print(json.dumps(manifest, ensure_ascii=False))
        return 0
    if args.command == "build-bundle":
        manifest = build_merge_bundle(
            stage_dir=args.stage,
            source_db=args.source_db,
            parquet_root=args.parquet_root,
            output_dir=args.output,
        )
        print(json.dumps(manifest, ensure_ascii=False))
        return 0
    receipt = apply_merge_bundle(
        bundle_dir=args.bundle,
        source_db=args.source_db,
        parquet_root=args.parquet_root,
        backup_dir=args.backup_dir,
        apply=args.apply,
        maintenance_confirmed=args.maintenance_confirmed,
        accept_event_time_surrogate=args.accept_event_time_surrogate,
    )
    print(json.dumps(receipt, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
