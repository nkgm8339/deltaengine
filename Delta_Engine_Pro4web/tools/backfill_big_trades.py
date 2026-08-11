"""Big Trades V2 backfill dry-run reporter.

This command deliberately has no write/backfill mode.  It reads completed
trade Parquet shards, runs the production Big Trades runtime against an
isolated temporary DuckDB, reports predicted row counts and disk usage, and
deletes the temporary output before returning.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

import duckdb
import pyarrow.parquet as pq

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from src.database.big_trades_storage import (  # noqa: E402
    BigTradesBackgroundStorageWriter,
    BigTradesDuckDbStore,
)
from src.orderflow.big_trades.activation import (  # noqa: E402
    ActivationArtifact,
    ActivationReason,
    CalibrationActivationPolicy,
    ReplayCalibrationMode,
)
from src.orderflow.big_trades.artifacts import BigTradesArtifactRepository  # noqa: E402
from src.orderflow.big_trades.constants import (  # noqa: E402
    DEFAULT_HORIZONS_SECONDS,
    LOGIC_VERSION,
    AutomaticIntensity,
    FilterMode,
    MarkerPriceMode,
    SideFilter,
)
from src.orderflow.big_trades.models import BigTradeFill  # noqa: E402
from src.orderflow.big_trades.runtime import (  # noqa: E402
    BigTradesRuntimeV2,
    FixedActivationSettingsResolver,
    RuntimeMode,
)
from src.orderflow.big_trades.settings import SettingsVersion  # noqa: E402


UTC = timezone.utc
TRADE_COLUMNS = {
    "event_time",
    "trade_time",
    "trade_id",
    "symbol",
    "price",
    "quantity",
    "side",
}
COUNT_TABLES = (
    "big_trade_events",
    "big_trade_event_fills",
    "big_trade_reaction_zones",
    "big_trade_zone_interactions",
    "big_trade_zone_event_links",
    "big_trade_result_snapshots",
    "big_trade_zone_state_checkpoints",
)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _stat_identity(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.exists():
        return {"path": str(resolved), "status": "MISSING"}
    stat = resolved.stat()
    identity_material = f"{resolved}|{stat.st_size}|{stat.st_mtime_ns}".encode()
    result: dict[str, Any] = {
        "path": str(resolved),
        "status": "PRESENT",
        "size_bytes": stat.st_size,
        "mtime_utc": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
        "stat_identity_sha256": hashlib.sha256(identity_material).hexdigest(),
    }
    try:
        connection = duckdb.connect(str(resolved), read_only=True)
        try:
            tables = {row[0] for row in connection.execute("SHOW TABLES").fetchall()}
            result["read_only_probe"] = "OPENED"
            if "trades" in tables:
                row = connection.execute(
                    "SELECT count(*), min(event_time), max(event_time) FROM trades"
                ).fetchone()
                result["trades"] = {
                    "count": int(row[0]),
                    "start": None if row[1] is None else str(row[1]),
                    "end": None if row[2] is None else str(row[2]),
                }
        finally:
            connection.close()
    except Exception as exc:  # live DuckDB commonly holds an exclusive process lock
        result["read_only_probe"] = "LOCKED_OR_UNAVAILABLE"
        result["read_only_probe_error"] = f"{type(exc).__name__}: {exc}"
    return result


def _day_partitions(parquet_root: Path, symbol: str) -> tuple[Path, ...]:
    base = parquet_root.resolve() / f"symbol={symbol}"
    return tuple(
        sorted(
            (path for path in base.glob("year=*/month=*/day=*") if path.is_dir()),
            reverse=True,
        )
    )


def select_completed_trade_files(
    parquet_root: Path,
    *,
    symbol: str,
    max_trade_files: int,
    safety_lag_seconds: int,
    now_utc: datetime | None = None,
) -> tuple[tuple[Path, ...], int]:
    """Select the newest schema-confirmed, non-active trade shards."""

    if max_trade_files < 1:
        raise ValueError("max_trade_files must be positive")
    if safety_lag_seconds < 0:
        raise ValueError("safety_lag_seconds must be non-negative")
    cutoff = (now_utc or datetime.now(UTC)) - timedelta(seconds=safety_lag_seconds)
    cutoff_timestamp = cutoff.timestamp()
    selected: list[Path] = []
    inspected = 0
    for day in _day_partitions(parquet_root, symbol):
        with os.scandir(day) as entries:
            candidates = sorted(
                (
                    Path(entry.path)
                    for entry in entries
                    if entry.is_file(follow_symlinks=False)
                    and entry.name.endswith(".parquet")
                    and entry.stat(follow_symlinks=False).st_mtime <= cutoff_timestamp
                ),
                reverse=True,
            )
        for path in candidates:
            inspected += 1
            try:
                names = set(pq.ParquetFile(path).schema_arrow.names)
            except Exception:
                continue
            if TRADE_COLUMNS.issubset(names):
                selected.append(path.resolve())
                if len(selected) == max_trade_files:
                    return tuple(sorted(selected)), inspected
    if not selected:
        raise RuntimeError("no completed trade Parquet shards were found")
    return tuple(sorted(selected)), inspected


def _parquet_manifest(files: Iterable[Path], root: Path) -> dict[str, Any]:
    paths = tuple(files)
    digest = hashlib.sha256()
    total_bytes = 0
    newest_mtime = 0.0
    oldest_mtime: float | None = None
    for path in paths:
        stat = path.stat()
        total_bytes += stat.st_size
        newest_mtime = max(newest_mtime, stat.st_mtime)
        oldest_mtime = stat.st_mtime if oldest_mtime is None else min(oldest_mtime, stat.st_mtime)
        relative = path.relative_to(root.resolve()).as_posix()
        digest.update(f"{relative}|{stat.st_size}|{stat.st_mtime_ns}\n".encode())
    return {
        "root": str(root.resolve()),
        "selected_file_count": len(paths),
        "selected_bytes": total_bytes,
        "first_file": str(paths[0]),
        "last_file": str(paths[-1]),
        "oldest_file_mtime_utc": datetime.fromtimestamp(oldest_mtime or 0, tz=UTC).isoformat(),
        "newest_file_mtime_utc": datetime.fromtimestamp(newest_mtime, tz=UTC).isoformat(),
        "manifest_sha256": digest.hexdigest(),
    }


def _read_trades(files: tuple[Path, ...], *, symbol: str) -> tuple[list[tuple[Any, ...]], int]:
    connection = duckdb.connect()
    connection.execute("SET TimeZone='UTC'")
    try:
        paths = [str(path) for path in files]
        total = int(
            connection.execute(
                "SELECT count(*) FROM read_parquet(?) WHERE symbol = ?",
                [paths, symbol],
            ).fetchone()[0]
        )
        rows = connection.execute(
            """
            SELECT event_time, trade_time, trade_id, symbol, price, quantity, side
            FROM read_parquet(?)
            WHERE symbol = ?
            QUALIFY row_number() OVER (
                PARTITION BY trade_id ORDER BY event_time DESC, trade_time DESC
            ) = 1
            ORDER BY event_time, trade_id
            """,
            [paths, symbol],
        ).fetchall()
        return rows, total - len(rows)
    finally:
        connection.close()


def _settle(writer: BigTradesBackgroundStorageWriter, runtime: BigTradesRuntimeV2) -> None:
    for _ in range(50):
        writer.join()
        runtime.drain_commit_acks()
        runtime.take_publications()
        stats = runtime.statistics()
        if stats["pending_origins"] == 0 and stats["pending_updates"] == 0:
            return
    raise RuntimeError("dry-run runtime did not settle")


def build_dry_run_report(
    *,
    source_db: Path,
    parquet_root: Path,
    symbol: str,
    venue: str,
    tick_size: Decimal,
    manual_min_quantity: Decimal,
    manual_max_quantity: Decimal,
    max_trade_files: int,
    safety_lag_seconds: int,
    horizons_seconds: tuple[int, ...] = DEFAULT_HORIZONS_SECONDS,
) -> dict[str, Any]:
    started = time.perf_counter()
    source_database = _stat_identity(source_db)
    files, inspected = select_completed_trade_files(
        parquet_root,
        symbol=symbol,
        max_trade_files=max_trade_files,
        safety_lag_seconds=safety_lag_seconds,
    )
    mirror = _parquet_manifest(files, parquet_root)
    mirror["inspected_candidate_files"] = inspected
    rows, duplicate_rows_removed = _read_trades(files, symbol=symbol)
    if not rows:
        raise RuntimeError("selected trade Parquet shards contain no rows for symbol")

    first_time = rows[0][0].astimezone(UTC)
    last_time = rows[-1][0].astimezone(UTC)
    settings = SettingsVersion.create(
        symbol=symbol,
        venue=venue,
        filter_mode=FilterMode.MANUAL,
        manual_min_quantity=manual_min_quantity,
        manual_max_quantity=manual_max_quantity,
        automatic_intensity=AutomaticIntensity.MEDIUM,
        side_filter=SideFilter.BOTH,
        marker_price_mode=MarkerPriceMode.LAST_PRICE,
    )
    activation = ActivationArtifact.create(
        symbol=symbol,
        venue=venue,
        effective_from_event_time=first_time,
        effective_from_trade_id=0,
        settings_id=settings.settings_id,
        calibration_id=None,
        activation_reason=ActivationReason.USER_SETTINGS,
        activation_policy=CalibrationActivationPolicy.MANUAL_ONLY,
        requested_at_utc=first_time,
    )

    with tempfile.TemporaryDirectory(prefix="big-trades-v2-backfill-dry-run-") as temporary:
        temporary_root = Path(temporary)
        temporary_db = temporary_root / "predicted-output.duckdb"
        store = BigTradesDuckDbStore(temporary_db)
        writer = BigTradesBackgroundStorageWriter(store, queue_maxsize=10_000)
        runtime = BigTradesRuntimeV2(
            enabled=True,
            mode=RuntimeMode.REPLAY,
            symbol=symbol,
            venue=venue,
            tick_size=tick_size,
            settings_resolver=FixedActivationSettingsResolver(settings, activation),
            storage_writer=writer,
            artifact_repository=BigTradesArtifactRepository(temporary_root / "artifacts"),
            horizons_seconds=horizons_seconds,
        )
        try:
            for event_time, trade_time, trade_id, row_symbol, price, quantity, side in rows:
                runtime.process(
                    BigTradeFill(
                        event_time=event_time,
                        trade_time=trade_time,
                        trade_id=trade_id,
                        symbol=row_symbol,
                        venue=venue,
                        price=price,
                        quantity=quantity,
                        side=side,
                    )
                )
            runtime.flush()
            _settle(writer, runtime)
            runtime_stats = runtime.statistics()
            counts = {table: store.count(table) for table in COUNT_TABLES}
        finally:
            writer.close()
        temporary_output_bytes = temporary_db.stat().st_size
        temporary_output_path = str(temporary_db)

    if runtime_stats["errors"] or runtime_stats["invalid_trades"]:
        raise RuntimeError(f"dry-run runtime failed: {runtime_stats}")
    return {
        "report_type": "BIG_TRADES_V2_BACKFILL_DRY_RUN",
        "status": "PASS",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "elapsed_seconds": time.perf_counter() - started,
        "source": {
            "database_identity": source_database,
            "reader": "PARQUET_MIRROR_READ_ONLY",
            "parquet_manifest": mirror,
        },
        "period": {
            "start_utc": _iso_utc(first_time),
            "end_utc": _iso_utc(last_time),
            "selection": "latest completed schema-confirmed trade shards",
            "safety_lag_seconds": safety_lag_seconds,
        },
        "input": {
            "trade_count": len(rows),
            "duplicate_rows_removed": duplicate_rows_removed,
            "symbol": symbol,
            "venue": venue,
        },
        "predicted_counts": {
            "clusters": runtime_stats["clusters_finalized"],
            "accepted_events": counts["big_trade_events"],
            "event_fills": counts["big_trade_event_fills"],
            "reaction_zones": counts["big_trade_reaction_zones"],
            "interactions": counts["big_trade_zone_interactions"],
            "event_zone_links": counts["big_trade_zone_event_links"],
            "result_snapshots": counts["big_trade_result_snapshots"],
            "zone_state_checkpoints": counts["big_trade_zone_state_checkpoints"],
        },
        "disk_estimate": {
            "isolated_duckdb_bytes": temporary_output_bytes,
            "method": "actual isolated DuckDB produced for the selected period",
            "temporary_output_path": temporary_output_path,
            "temporary_output_deleted": not Path(temporary_output_path).exists(),
        },
        "versions": {
            "logic_version": LOGIC_VERSION,
            "settings_id": settings.settings_id,
            "calibration_id": None,
            "activation_id": activation.activation_id,
            "replay_calibration_mode": ReplayCalibrationMode.FIXED_RESEARCH.value,
            "filter_mode": settings.filter_mode.value,
            "manual_min_quantity": str(settings.manual_min_quantity),
            "manual_max_quantity": str(settings.manual_max_quantity),
            "activation_policy": activation.activation_policy.value,
            "production_activation": False,
        },
        "runtime": runtime_stats,
        "production_mutations": 0,
        "production_writer_connection_attempts": 0,
        "production_backfill_performed": False,
    }


def _horizons(value: str) -> tuple[int, ...]:
    parsed = tuple(int(item) for item in value.split(",") if item)
    if not parsed or any(item < 1 for item in parsed) or tuple(sorted(set(parsed))) != parsed:
        raise argparse.ArgumentTypeError("horizons must be unique ascending positive integers")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="required safety acknowledgement")
    parser.add_argument("--source-db", type=Path, required=True)
    parser.add_argument("--parquet-root", type=Path, required=True)
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--venue", default="BINANCE")
    parser.add_argument("--tick-size", type=Decimal, required=True)
    parser.add_argument("--manual-min", type=Decimal, required=True)
    parser.add_argument("--manual-max", type=Decimal, required=True)
    parser.add_argument("--max-trade-files", type=int, default=250)
    parser.add_argument("--safety-lag-seconds", type=int, default=300)
    parser.add_argument(
        "--horizons-seconds",
        type=_horizons,
        default=DEFAULT_HORIZONS_SECONDS,
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.dry_run:
        parser.error("--dry-run is required; this command has no production write mode")
    report = build_dry_run_report(
        source_db=args.source_db,
        parquet_root=args.parquet_root,
        symbol=args.symbol,
        venue=args.venue,
        tick_size=args.tick_size,
        manual_min_quantity=args.manual_min,
        manual_max_quantity=args.manual_max,
        max_trade_files=args.max_trade_files,
        safety_lag_seconds=args.safety_lag_seconds,
        horizons_seconds=args.horizons_seconds,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
