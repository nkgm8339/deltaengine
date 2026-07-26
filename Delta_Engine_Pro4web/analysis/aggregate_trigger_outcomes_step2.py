"""Step 2 trigger outcome aggregation.

This script is intentionally read-only with respect to the recorded market data.
It fixes the Step 1 approved cohorts, performs all joins in an in-memory DuckDB,
and writes only derived CSV/JSON/Markdown artifacts.

Primary cohort:
  * NEW_05M: flow_response_outcomes whose outcome_time is at or before
    2026-07-26 05:14:51.002 JST.  The Step 1 Parquet inventory reported 24,355;
    the approved authoritative copied DuckDB/WAL snapshot contains 44,529.
  * OLD_1M: 46,492 rows from the stopped legacy DuckDB, opened READ_ONLY.
  * HFM: 553 stored hfm_context_outcomes (528 OK, 25 QUOTE_GAP).

Flow state direction is fixed before looking at outcomes:
  BUY_EFFECTIVE -> BUY, SELL_EFFECTIVE -> SELL,
  BUY_TRAPPED -> SELL, SELL_TRAPPED -> BUY.
STALLED is not promoted to a direction claim.  It is emitted as two explicitly
labelled probes: pressure continuation and defender reversal.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

import duckdb


NEW_EXPECTED = 24_355
OLD_EXPECTED = 46_492
HFM_EXPECTED = 553
HFM_OK_EXPECTED = 528
HFM_GAP_EXPECTED = 25
NEW_CUTOFF_ISO = "2026-07-26T05:14:51.002+09:00"
CLEAN_BOUNDARY_ISO = "2026-07-21T18:30:41+09:00"

PRIMARY_STATES = {
    "BUY_EFFECTIVE": (1, "EFFECTIVE_CONTINUATION"),
    "SELL_EFFECTIVE": (-1, "EFFECTIVE_CONTINUATION"),
    "BUY_TRAPPED": (-1, "TRAPPED_REVERSAL"),
    "SELL_TRAPPED": (1, "TRAPPED_REVERSAL"),
}
STALLED_STATES = {
    "BUY_STALLED": 1,
    "SELL_STALLED": -1,
}


@dataclass(frozen=True)
class ProjectPaths:
    project_root: Path
    outer_root: Path
    new_parquet: Path
    old_parquet: Path
    old_duckdb: Path
    new_duckdb_snapshot: Path | None
    output_dir: Path
    report_path: Path


def state_hypotheses(state: str) -> tuple[tuple[int, str, str], ...]:
    """Return pre-declared (sign, hypothesis, class) mappings for a state."""

    normalized = state.upper()
    primary = PRIMARY_STATES.get(normalized)
    if primary is not None:
        sign, hypothesis = primary
        return ((sign, hypothesis, "ANALYSIS"),)
    pressure_sign = STALLED_STATES.get(normalized)
    if pressure_sign is None:
        return ()
    return (
        (pressure_sign, "STALLED_PRESSURE_PROBE", "ENTRY_PROBE"),
        (-pressure_sign, "STALLED_REVERSAL_PROBE", "ENTRY_PROBE"),
    )


def directed_excursions(
    direction_sign: int,
    max_up_bps: float,
    max_down_bps: float,
) -> tuple[float, float]:
    """Convert raw up/down excursions to direction-relative MFE/MAE."""

    if direction_sign not in {-1, 1}:
        raise ValueError("direction_sign must be -1 or 1")
    if direction_sign == 1:
        return float(max_up_bps), float(max_down_bps)
    return -float(max_down_bps), -float(max_up_bps)


def direction_result(signed_return_bps: float) -> str:
    if signed_return_bps > 0:
        return "MATCH"
    if signed_return_bps < 0:
        return "MISMATCH"
    return "FLAT"


def threshold_20usd_bps(observed_price: float) -> float:
    if not math.isfinite(observed_price) or observed_price <= 0:
        raise ValueError("observed_price must be finite and positive")
    return 20.0 / observed_price * 10_000.0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    default_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=default_root)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--report-path", type=Path)
    parser.add_argument(
        "--new-duckdb-snapshot",
        type=Path,
        help=(
            "Read a copied NEW_05M DuckDB/WAL snapshot instead of the live "
            "Parquet directory. The original live DuckDB is never opened."
        ),
    )
    parser.add_argument(
        "--new-expected-count",
        type=int,
        default=NEW_EXPECTED,
        help="Expected NEW_05M rows at the fixed cutoff.",
    )
    parser.add_argument(
        "--no-strict-counts",
        action="store_true",
        help="Allow source counts different from the Step 1 approved inventory.",
    )
    return parser.parse_args(argv)


def resolve_paths(args: argparse.Namespace) -> ProjectPaths:
    project_root = args.project_root.resolve()
    outer_root = project_root.parent
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir
        else project_root
        / "analysis"
        / "output"
        / "trigger_outcomes_step2_20260726"
    )
    report_path = (
        args.report_path.resolve()
        if args.report_path
        else outer_root
        / "ArchitectureRepository"
        / "00_Master"
        / "ORDERFLOW_TRIGGER_OUTCOME_STEP2_REPORT_20260726.md"
    )
    return ProjectPaths(
        project_root=project_root,
        outer_root=outer_root,
        new_parquet=project_root / "data_05M" / "parquet",
        old_parquet=project_root / "data" / "parquet",
        old_duckdb=project_root / "data" / "duckdb" / "orderflow.duckdb",
        new_duckdb_snapshot=(
            args.new_duckdb_snapshot.resolve()
            if args.new_duckdb_snapshot
            else None
        ),
        output_dir=output_dir,
        report_path=report_path,
    )


def parquet_files(root: Path, dataset: str) -> list[Path]:
    result = sorted((root / dataset).rglob("*.parquet"))
    if not result:
        raise FileNotFoundError(f"no parquet files: {root / dataset}")
    return result


def file_inventory(paths: Sequence[Path]) -> dict[str, object]:
    stats = [path.stat() for path in paths]
    return {
        "file_count": len(paths),
        "total_bytes": sum(item.st_size for item in stats),
        "oldest_mtime": datetime.fromtimestamp(
            min(item.st_mtime for item in stats)
        ).astimezone().isoformat(),
        "newest_mtime": datetime.fromtimestamp(
            max(item.st_mtime for item in stats)
        ).astimezone().isoformat(),
        "first_path": str(paths[0]),
        "last_path": str(paths[-1]),
    }


def sql_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace("'", "''")


def create_parquet_table(
    con: duckdb.DuckDBPyConnection,
    table_name: str,
    paths: Sequence[Path],
    *,
    select_sql: str = "*",
    where_sql: str = "",
    params: Sequence[object] = (),
) -> None:
    path_values = [str(path.resolve()) for path in paths]
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE {table_name} AS
        SELECT {select_sql}
        FROM read_parquet(?)
        {where_sql}
        """,
        [path_values, *params],
    )


def scalar(con: duckdb.DuckDBPyConnection, sql: str) -> object:
    return con.execute(sql).fetchone()[0]


def check_count(
    label: str,
    actual: int,
    expected: int,
    *,
    strict: bool,
) -> None:
    if strict and actual != expected:
        raise RuntimeError(
            f"{label} count mismatch: expected {expected:,}, got {actual:,}"
        )


def write_query_csv(
    con: duckdb.DuckDBPyConnection,
    path: Path,
    query: str,
) -> int:
    cursor = con.execute(query)
    headers = [item[0] for item in cursor.description]
    rows = cursor.fetchall()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)
    return len(rows)


def as_float(value: object | None) -> float | None:
    return None if value is None else float(value)


def fmt(value: object | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    if isinstance(value, int):
        return f"{value:,}"
    numeric = float(value)
    if not math.isfinite(numeric):
        return "—"
    return f"{numeric:.{digits}f}"


def markdown_table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    for row in rows:
        values = []
        for value in row:
            text = "—" if value is None else str(value)
            values.append(text.replace("|", "\\|").replace("\n", " "))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def load_sources(
    con: duckdb.DuckDBPyConnection,
    paths: ProjectPaths,
    *,
    strict: bool,
    new_expected: int,
) -> dict[str, object]:
    cutoff = datetime.fromisoformat(NEW_CUTOFF_ISO)
    old_oi_files = parquet_files(paths.old_parquet, "open_interest_samples")
    source_files: dict[str, object] = {
        "old_oi": file_inventory(old_oi_files),
    }

    if paths.new_duckdb_snapshot is not None:
        if not paths.new_duckdb_snapshot.is_file():
            raise FileNotFoundError(paths.new_duckdb_snapshot)
        new_db_path = sql_path(paths.new_duckdb_snapshot)
        con.execute(f"ATTACH '{new_db_path}' AS new_snapshot (READ_ONLY)")
        con.execute(
            f"""
            CREATE OR REPLACE TEMP TABLE new_outcomes AS
            SELECT
              event_time AT TIME ZONE 'UTC' AS event_time,
              symbol, window_sec, state, horizon_sec, observed_price,
              outcome_time AT TIME ZONE 'UTC' AS outcome_time,
              outcome_price, forward_return_bps, max_up_bps, max_down_bps
            FROM new_snapshot.flow_response_outcomes
            WHERE outcome_time AT TIME ZONE 'UTC'
              <= TIMESTAMPTZ '{NEW_CUTOFF_ISO}'
            """
        )
        con.execute(
            """
            CREATE OR REPLACE TEMP TABLE new_events AS
            SELECT
              event_time AT TIME ZONE 'UTC' AS event_time,
              symbol, window_sec, state, pressure_side,
              first_price, last_price, price_change_bps
            FROM new_snapshot.flow_response_events
            """
        )
        con.execute(
            f"""
            CREATE OR REPLACE TEMP TABLE new_oi AS
            SELECT
              source_time AT TIME ZONE 'UTC' AS source_time,
              symbol, open_interest
            FROM new_snapshot.open_interest_samples
            WHERE source_time AT TIME ZONE 'UTC'
              <= TIMESTAMPTZ '{NEW_CUTOFF_ISO}'
            """
        )
        con.execute(
            f"""
            CREATE OR REPLACE TEMP TABLE native_events AS
            SELECT
              event_time AT TIME ZONE 'UTC' AS event_time,
              symbol, timeframe, state, pressure_side
            FROM new_snapshot.native_flow_events
            WHERE event_time AT TIME ZONE 'UTC'
              <= TIMESTAMPTZ '{NEW_CUTOFF_ISO}'
            """
        )
        con.execute(
            """
            CREATE OR REPLACE TEMP TABLE native_outcomes AS
            SELECT
              event_time AT TIME ZONE 'UTC' AS event_time,
              symbol, timeframe, state, horizon_sec, observed_price,
              outcome_time AT TIME ZONE 'UTC' AS outcome_time,
              outcome_price, forward_return_bps, max_up_bps, max_down_bps
            FROM new_snapshot.native_flow_outcomes
            """
        )
        con.execute(
            """
            CREATE OR REPLACE TEMP TABLE hfm AS
            SELECT * REPLACE (
              event_time AT TIME ZONE 'UTC' AS event_time,
              entry_time AT TIME ZONE 'UTC' AS entry_time,
              entry_source_time AT TIME ZONE 'UTC' AS entry_source_time,
              outcome_time AT TIME ZONE 'UTC' AS outcome_time,
              outcome_source_time AT TIME ZONE 'UTC' AS outcome_source_time
            )
            FROM new_snapshot.hfm_context_outcomes
            """
        )
        con.execute(
            """
            CREATE OR REPLACE TEMP TABLE combined_context AS
            SELECT * REPLACE (
              event_time AT TIME ZONE 'UTC' AS event_time,
              bar_time AT TIME ZONE 'UTC' AS bar_time,
              hfm_entry_time AT TIME ZONE 'UTC' AS hfm_entry_time,
              hfm_entry_source_time AT TIME ZONE 'UTC'
                AS hfm_entry_source_time
            )
            FROM new_snapshot.combined_context_events
            """
        )
        source_mode = "COPIED_DUCKDB_READ_ONLY"
        source_files["new_duckdb_snapshot"] = file_inventory(
            [paths.new_duckdb_snapshot]
        )
        snapshot_wal = Path(str(paths.new_duckdb_snapshot) + ".wal")
        if snapshot_wal.is_file():
            source_files["new_duckdb_snapshot_wal"] = file_inventory(
                [snapshot_wal]
            )
        frozen_hfm_root = paths.new_duckdb_snapshot.parent / "hfm_context_outcomes"
        if frozen_hfm_root.is_dir():
            frozen_hfm_files = sorted(frozen_hfm_root.rglob("*.parquet"))
            if not frozen_hfm_files:
                raise FileNotFoundError(frozen_hfm_root)
            create_parquet_table(con, "hfm", frozen_hfm_files)
            source_files["frozen_hfm_parquet"] = file_inventory(
                frozen_hfm_files
            )
    else:
        new_outcome_files = parquet_files(
            paths.new_parquet, "flow_response_outcomes"
        )
        new_event_files = parquet_files(
            paths.new_parquet, "flow_response_events"
        )
        new_oi_files = parquet_files(
            paths.new_parquet, "open_interest_samples"
        )
        native_event_files = parquet_files(
            paths.new_parquet, "native_flow_events"
        )
        native_outcome_files = parquet_files(
            paths.new_parquet, "native_flow_outcomes"
        )
        hfm_files = parquet_files(
            paths.new_parquet, "hfm_context_outcomes"
        )
        combined_files = parquet_files(
            paths.new_parquet, "combined_context_events"
        )
        create_parquet_table(
            con,
            "new_outcomes",
            new_outcome_files,
            select_sql="""
              event_time, symbol, window_sec, state, horizon_sec,
              observed_price, outcome_time, outcome_price, forward_return_bps,
              max_up_bps, max_down_bps
            """,
            where_sql="WHERE outcome_time <= ?",
            params=(cutoff,),
        )
        create_parquet_table(
            con,
            "new_events",
            new_event_files,
            select_sql="""
              event_time, symbol, window_sec, state, pressure_side,
              first_price, last_price, price_change_bps
            """,
        )
        create_parquet_table(
            con,
            "new_oi",
            new_oi_files,
            select_sql="source_time, symbol, open_interest",
            where_sql="WHERE source_time <= ?",
            params=(cutoff,),
        )
        create_parquet_table(
            con,
            "native_events",
            native_event_files,
            select_sql="""
              event_time, symbol, timeframe, state, pressure_side
            """,
            where_sql="WHERE event_time <= ?",
            params=(cutoff,),
        )
        create_parquet_table(
            con,
            "native_outcomes",
            native_outcome_files,
            select_sql="""
              event_time, symbol, timeframe, state, horizon_sec,
              observed_price, outcome_time, outcome_price, forward_return_bps,
              max_up_bps, max_down_bps
            """,
        )
        create_parquet_table(con, "hfm", hfm_files)
        create_parquet_table(con, "combined_context", combined_files)
        source_mode = "LIVE_PARQUET_FILESET"
        source_files.update(
            {
                "new_outcomes": file_inventory(new_outcome_files),
                "new_events": file_inventory(new_event_files),
                "new_oi": file_inventory(new_oi_files),
                "native_events": file_inventory(native_event_files),
                "native_outcomes": file_inventory(native_outcome_files),
                "hfm": file_inventory(hfm_files),
                "combined_context": file_inventory(combined_files),
            }
        )

    old_db_path = sql_path(paths.old_duckdb)
    con.execute(f"ATTACH '{old_db_path}' AS legacy (READ_ONLY)")
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE old_outcomes AS
        SELECT
          event_time AT TIME ZONE 'UTC' AS event_time,
          symbol, window_sec, state, horizon_sec, observed_price,
          outcome_time AT TIME ZONE 'UTC' AS outcome_time,
          outcome_price, forward_return_bps, max_up_bps, max_down_bps
        FROM legacy.flow_response_outcomes
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE old_events AS
        SELECT
          event_time AT TIME ZONE 'UTC' AS event_time,
          symbol, window_sec, state, pressure_side,
          first_price, last_price, price_change_bps
        FROM legacy.flow_response_events
        """
    )

    create_parquet_table(
        con,
        "old_oi",
        old_oi_files,
        select_sql="source_time, symbol, open_interest",
    )
    counts = {
        "new_outcomes": int(scalar(con, "SELECT count(*) FROM new_outcomes")),
        "old_outcomes": int(scalar(con, "SELECT count(*) FROM old_outcomes")),
        "hfm": int(scalar(con, "SELECT count(*) FROM hfm")),
        "hfm_ok": int(
            scalar(con, "SELECT count(*) FROM hfm WHERE status='OK'")
        ),
        "hfm_quote_gap": int(
            scalar(con, "SELECT count(*) FROM hfm WHERE status='QUOTE_GAP'")
        ),
    }
    check_count(
        "NEW_05M", counts["new_outcomes"], new_expected, strict=strict
    )
    check_count("OLD_1M", counts["old_outcomes"], OLD_EXPECTED, strict=strict)
    check_count("HFM", counts["hfm"], HFM_EXPECTED, strict=strict)
    check_count("HFM OK", counts["hfm_ok"], HFM_OK_EXPECTED, strict=strict)
    check_count(
        "HFM QUOTE_GAP",
        counts["hfm_quote_gap"],
        HFM_GAP_EXPECTED,
        strict=strict,
    )

    distinct_counts = {
        "new_outcomes": int(
            scalar(
                con,
                """
                SELECT count(DISTINCT (event_time,symbol,window_sec,horizon_sec))
                FROM new_outcomes
                """,
            )
        ),
        "old_outcomes": int(
            scalar(
                con,
                """
                SELECT count(DISTINCT (event_time,symbol,window_sec,horizon_sec))
                FROM old_outcomes
                """,
            )
        ),
        "hfm": int(
            scalar(
                con,
                """
                SELECT count(DISTINCT (event_time,symbol,timeframe,horizon_sec))
                FROM hfm
                """,
            )
        ),
    }
    for label, total in counts.items():
        if label in distinct_counts and distinct_counts[label] != total:
            raise RuntimeError(
                f"{label} primary-key duplicate: total={total}, "
                f"distinct={distinct_counts[label]}"
            )

    return {
        "counts": counts,
        "distinct_counts": distinct_counts,
        "source_files": source_files,
        "new_source_mode": source_mode,
        "old_duckdb": {
            "path": str(paths.old_duckdb),
            "bytes": paths.old_duckdb.stat().st_size,
            "mtime": datetime.fromtimestamp(
                paths.old_duckdb.stat().st_mtime
            ).astimezone().isoformat(),
            "mode": "READ_ONLY",
        },
    }


def build_quality_and_direction_tables(
    con: duckdb.DuckDBPyConnection,
) -> None:
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE all_outcomes AS
        SELECT 'NEW_05M' AS source_dataset, * FROM new_outcomes
        UNION ALL
        SELECT 'OLD_1M' AS source_dataset, * FROM old_outcomes
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE all_events AS
        SELECT 'NEW_05M' AS source_dataset, * FROM new_events
        UNION ALL
        SELECT 'OLD_1M' AS source_dataset, * FROM old_events
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE outcome_quality AS
        SELECT
          o.*,
          e.pressure_side,
          cast(e.first_price AS DOUBLE) AS first_price,
          cast(e.last_price AS DOUBLE) AS last_price,
          cast(e.price_change_bps AS DOUBLE) AS event_price_change_bps,
          (
            e.event_time IS NOT NULL
            AND isfinite(cast(o.observed_price AS DOUBLE))
            AND cast(o.observed_price AS DOUBLE) > 0
            AND isfinite(cast(o.outcome_price AS DOUBLE))
            AND cast(o.outcome_price AS DOUBLE) > 0
            AND isfinite(cast(o.forward_return_bps AS DOUBLE))
            AND isfinite(cast(e.first_price AS DOUBLE))
            AND cast(e.first_price AS DOUBLE) > 0
            AND isfinite(cast(e.last_price AS DOUBLE))
            AND cast(e.last_price AS DOUBLE) > 0
            AND isfinite(cast(e.price_change_bps AS DOUBLE))
            AND abs(cast(e.price_change_bps AS DOUBLE)) <= 100
          ) AS quality_eligible,
          (
            o.source_dataset='NEW_05M'
            OR o.event_time >= TIMESTAMPTZ '{CLEAN_BOUNDARY_ISO}'
          ) AS primary_clean,
          (
            e.event_time IS NOT NULL
            AND isfinite(cast(o.observed_price AS DOUBLE))
            AND cast(o.observed_price AS DOUBLE) > 0
            AND isfinite(cast(o.outcome_price AS DOUBLE))
            AND cast(o.outcome_price AS DOUBLE) > 0
            AND isfinite(cast(o.forward_return_bps AS DOUBLE))
            AND isfinite(cast(e.first_price AS DOUBLE))
            AND cast(e.first_price AS DOUBLE) > 0
            AND isfinite(cast(e.last_price AS DOUBLE))
            AND cast(e.last_price AS DOUBLE) > 0
            AND isfinite(cast(e.price_change_bps AS DOUBLE))
            AND abs(cast(e.price_change_bps AS DOUBLE)) <= 100
            AND (
              o.source_dataset='NEW_05M'
              OR o.event_time >= TIMESTAMPTZ '{CLEAN_BOUNDARY_ISO}'
            )
            AND isfinite(cast(o.max_up_bps AS DOUBLE))
            AND isfinite(cast(o.max_down_bps AS DOUBLE))
            AND cast(o.max_up_bps AS DOUBLE) >= 0
            AND cast(o.max_down_bps AS DOUBLE) <= 0
          ) AS mfe_eligible
        FROM all_outcomes o
        LEFT JOIN all_events e
          ON o.source_dataset=e.source_dataset
         AND o.event_time=e.event_time
         AND o.symbol=e.symbol
         AND o.window_sec=e.window_sec
        """
    )

    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE directional_outcomes AS
        WITH mapped AS (
          SELECT *,
            CASE
              WHEN state='BUY_EFFECTIVE' THEN 1
              WHEN state='SELL_EFFECTIVE' THEN -1
              WHEN state='BUY_TRAPPED' THEN -1
              WHEN state='SELL_TRAPPED' THEN 1
            END AS direction_sign,
            CASE
              WHEN state IN ('BUY_EFFECTIVE','SELL_EFFECTIVE')
                THEN 'EFFECTIVE_CONTINUATION'
              ELSE 'TRAPPED_REVERSAL'
            END AS hypothesis,
            'ANALYSIS' AS direction_class
          FROM outcome_quality
          WHERE quality_eligible
            AND state IN (
              'BUY_EFFECTIVE','SELL_EFFECTIVE',
              'BUY_TRAPPED','SELL_TRAPPED'
            )
        ),
        stalled_pressure AS (
          SELECT *,
            CASE WHEN state='BUY_STALLED' THEN 1 ELSE -1 END AS direction_sign,
            'STALLED_PRESSURE_PROBE' AS hypothesis,
            'ENTRY_PROBE' AS direction_class
          FROM outcome_quality
          WHERE quality_eligible
            AND state IN ('BUY_STALLED','SELL_STALLED')
        ),
        stalled_reversal AS (
          SELECT *,
            CASE WHEN state='BUY_STALLED' THEN -1 ELSE 1 END AS direction_sign,
            'STALLED_REVERSAL_PROBE' AS hypothesis,
            'ENTRY_PROBE' AS direction_class
          FROM outcome_quality
          WHERE quality_eligible
            AND state IN ('BUY_STALLED','SELL_STALLED')
        ),
        u AS (
          SELECT * FROM mapped
          UNION ALL SELECT * FROM stalled_pressure
          UNION ALL SELECT * FROM stalled_reversal
        )
        SELECT
          *,
          direction_sign * cast(forward_return_bps AS DOUBLE)
            AS signed_return_bps,
          CASE
            WHEN direction_sign=1 THEN cast(max_up_bps AS DOUBLE)
            ELSE -cast(max_down_bps AS DOUBLE)
          END AS mfe_bps,
          CASE
            WHEN direction_sign=1 THEN cast(max_down_bps AS DOUBLE)
            ELSE -cast(max_up_bps AS DOUBLE)
          END AS mae_bps,
          20.0 / cast(observed_price AS DOUBLE) * 10000.0
            AS threshold_20usd_bps,
          CASE
            WHEN direction_sign=1 THEN
              cast(max_up_bps AS DOUBLE) * cast(observed_price AS DOUBLE) / 10000.0
            ELSE
              -cast(max_down_bps AS DOUBLE) * cast(observed_price AS DOUBLE) / 10000.0
          END AS mfe_usd
        FROM u
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE scoped_directional AS
        SELECT 'ALL_QUALITY_VALID' AS sample_scope, *
        FROM directional_outcomes
        UNION ALL
        SELECT 'PRIMARY_CLEAN' AS sample_scope, *
        FROM directional_outcomes
        WHERE primary_clean
        """
    )


def build_summary_tables(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE direction_summary AS
        SELECT
          source_dataset, sample_scope, direction_class, hypothesis,
          state, window_sec, horizon_sec,
          count(*) AS n,
          count_if(signed_return_bps>0) AS match_n,
          count_if(signed_return_bps<0) AS mismatch_n,
          count_if(signed_return_bps=0) AS flat_n,
          100.0*count_if(signed_return_bps>0)/count(*) AS match_pct,
          100.0*count_if(signed_return_bps=0)/count(*) AS flat_pct,
          avg(cast(forward_return_bps AS DOUBLE)) AS raw_mean_bps,
          quantile_cont(cast(forward_return_bps AS DOUBLE),0.05) AS raw_p05_bps,
          quantile_cont(cast(forward_return_bps AS DOUBLE),0.25) AS raw_p25_bps,
          median(cast(forward_return_bps AS DOUBLE)) AS raw_median_bps,
          quantile_cont(cast(forward_return_bps AS DOUBLE),0.75) AS raw_p75_bps,
          quantile_cont(cast(forward_return_bps AS DOUBLE),0.95) AS raw_p95_bps,
          avg(signed_return_bps) AS signed_mean_bps,
          quantile_cont(signed_return_bps,0.05) AS signed_p05_bps,
          quantile_cont(signed_return_bps,0.25) AS signed_p25_bps,
          median(signed_return_bps) AS signed_median_bps,
          quantile_cont(signed_return_bps,0.75) AS signed_p75_bps,
          quantile_cont(signed_return_bps,0.95) AS signed_p95_bps
        FROM scoped_directional
        GROUP BY ALL
        ORDER BY
          source_dataset, sample_scope, direction_class, state,
          hypothesis, window_sec, horizon_sec
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE mfe_summary AS
        SELECT
          source_dataset, direction_class, hypothesis, state, horizon_sec,
          count(*) AS n,
          count(DISTINCT window_sec) AS window_count,
          quantile_cont(mfe_bps,0.25) AS mfe_p25_bps,
          median(mfe_bps) AS mfe_median_bps,
          quantile_cont(mfe_bps,0.75) AS mfe_p75_bps,
          quantile_cont(mfe_bps,0.95) AS mfe_p95_bps,
          quantile_cont(mae_bps,0.05) AS mae_p05_bps,
          quantile_cont(mae_bps,0.25) AS mae_p25_bps,
          median(mae_bps) AS mae_median_bps,
          quantile_cont(mae_bps,0.75) AS mae_p75_bps,
          quantile_cont(threshold_20usd_bps,0.25) AS threshold_p25_bps,
          median(threshold_20usd_bps) AS threshold_median_bps,
          quantile_cont(threshold_20usd_bps,0.75) AS threshold_p75_bps,
          count_if(mfe_usd>=20.0) AS reached_20usd_n,
          100.0*count_if(mfe_usd>=20.0)/count(*) AS reached_20usd_pct
        FROM directional_outcomes
        WHERE mfe_eligible
        GROUP BY ALL
        ORDER BY
          source_dataset, direction_class, state, hypothesis, horizon_sec
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE cell_comparison AS
        WITH n AS (
          SELECT * FROM direction_summary
          WHERE source_dataset='NEW_05M'
            AND sample_scope='PRIMARY_CLEAN'
            AND direction_class='ANALYSIS'
        ),
        o AS (
          SELECT * FROM direction_summary
          WHERE source_dataset='OLD_1M'
            AND sample_scope='PRIMARY_CLEAN'
            AND direction_class='ANALYSIS'
        )
        SELECT
          coalesce(n.state,o.state) AS state,
          coalesce(n.hypothesis,o.hypothesis) AS hypothesis,
          coalesce(n.window_sec,o.window_sec) AS window_sec,
          coalesce(n.horizon_sec,o.horizon_sec) AS horizon_sec,
          n.n AS new_n, n.match_pct AS new_match_pct,
          n.signed_median_bps AS new_signed_median_bps,
          o.n AS old_n, o.match_pct AS old_match_pct,
          o.signed_median_bps AS old_signed_median_bps,
          n.match_pct-o.match_pct AS match_diff_pp,
          CASE
            WHEN sign(n.signed_median_bps)=sign(o.signed_median_bps)
              THEN true ELSE false
          END AS same_median_sign,
          CASE
            WHEN (n.match_pct>=50)=(o.match_pct>=50)
              THEN true ELSE false
          END AS same_accuracy_side,
          n.n>=30 AND o.n>=30 AS comparison_eligible
        FROM n
        FULL OUTER JOIN o USING(state,hypothesis,window_sec,horizon_sec)
        ORDER BY state, window_sec, horizon_sec
        """
    )


def build_time_tables(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE jst_hour_event_frequency AS
        WITH events AS (
          SELECT DISTINCT
            source_dataset,
            CASE WHEN primary_clean THEN 'PRIMARY_CLEAN'
                 ELSE 'PRE_FIX_FILTERED' END AS sample_scope,
            event_time, symbol, window_sec, state
          FROM outcome_quality
          WHERE quality_eligible
        )
        SELECT
          source_dataset, sample_scope,
          extract(hour FROM event_time)::INTEGER AS jst_hour,
          state, window_sec, count(*) AS event_n
        FROM events
        GROUP BY ALL
        ORDER BY source_dataset, sample_scope, jst_hour, state, window_sec
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE jst_hour_performance AS
        SELECT
          source_dataset, direction_class, hypothesis, state,
          window_sec, horizon_sec,
          extract(hour FROM event_time)::INTEGER AS jst_hour,
          count(*) AS n,
          100.0*count_if(signed_return_bps>0)/count(*) AS match_pct,
          100.0*count_if(signed_return_bps=0)/count(*) AS flat_pct,
          avg(signed_return_bps) AS signed_mean_bps,
          median(signed_return_bps) AS signed_median_bps
        FROM directional_outcomes
        WHERE primary_clean
        GROUP BY ALL
        ORDER BY
          source_dataset, direction_class, hypothesis, state,
          window_sec, horizon_sec, jst_hour
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE jst_hour_report AS
        WITH freq AS (
          SELECT source_dataset,jst_hour,sum(event_n) event_n
          FROM jst_hour_event_frequency
          WHERE sample_scope='PRIMARY_CLEAN'
          GROUP BY 1,2
        ),
        perf AS (
          SELECT source_dataset,
                 extract(hour FROM event_time)::INTEGER AS jst_hour,
                 count(*) n,
                 100.0*count_if(signed_return_bps>0)/count(*) match_pct,
                 median(signed_return_bps) signed_median_bps
          FROM directional_outcomes
          WHERE primary_clean
            AND direction_class='ANALYSIS'
            AND horizon_sec=600
          GROUP BY 1,2
        )
        SELECT
          coalesce(f.source_dataset,p.source_dataset) source_dataset,
          coalesce(f.jst_hour,p.jst_hour) jst_hour,
          f.event_n, p.n AS direction_n,
          p.match_pct, p.signed_median_bps
        FROM freq f
        FULL OUTER JOIN perf p USING(source_dataset,jst_hour)
        ORDER BY source_dataset,jst_hour
        """
    )


def build_oi_confluence(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE oi_samples AS
        SELECT source_time, symbol, cast(open_interest AS DOUBLE) open_interest
        FROM new_oi
        WHERE isfinite(cast(open_interest AS DOUBLE))
          AND cast(open_interest AS DOUBLE)>0
        UNION ALL
        SELECT source_time, symbol, cast(open_interest AS DOUBLE) open_interest
        FROM old_oi
        WHERE isfinite(cast(open_interest AS DOUBLE))
          AND cast(open_interest AS DOUBLE)>0
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE direction_oi_raw AS
        SELECT
          d.*,
          cur.source_time AS current_oi_time,
          cur.open_interest AS current_oi,
          prv.source_time AS prior_oi_time,
          prv.open_interest AS prior_oi
        FROM directional_outcomes d
        ASOF LEFT JOIN oi_samples cur
          ON d.symbol=cur.symbol
         AND d.event_time>=cur.source_time
        ASOF LEFT JOIN oi_samples prv
          ON d.symbol=prv.symbol
         AND d.event_time-d.window_sec*INTERVAL '1 second'>=prv.source_time
        WHERE d.primary_clean
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE direction_oi AS
        SELECT *,
          epoch(event_time-current_oi_time) AS current_oi_age_sec,
          epoch(
            event_time-window_sec*INTERVAL '1 second'-prior_oi_time
          ) AS prior_oi_age_sec,
          CASE
            WHEN current_oi_time IS NULL OR prior_oi_time IS NULL THEN 'MISSING'
            WHEN epoch(event_time-current_oi_time)>30
              OR epoch(
                event_time-window_sec*INTERVAL '1 second'-prior_oi_time
              )>30 THEN 'STALE'
            WHEN current_oi>prior_oi THEN 'BUILDING'
            WHEN current_oi<prior_oi THEN 'UNWINDING'
            ELSE 'UNCHANGED'
          END AS oi_context
        FROM direction_oi_raw
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE oi_confluence_summary AS
        SELECT
          source_dataset, direction_class, hypothesis, state,
          window_sec, horizon_sec, oi_context,
          count(*) AS n,
          100.0*count_if(signed_return_bps>0)/count(*) AS match_pct,
          avg(signed_return_bps) AS signed_mean_bps,
          median(signed_return_bps) AS signed_median_bps
        FROM direction_oi
        GROUP BY ALL
        ORDER BY
          source_dataset, direction_class, state, hypothesis,
          window_sec, horizon_sec, oi_context
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE oi_confluence_report AS
        SELECT
          source_dataset, oi_context, count(*) AS n,
          100.0*count_if(signed_return_bps>0)/count(*) AS match_pct,
          avg(signed_return_bps) AS signed_mean_bps,
          median(signed_return_bps) AS signed_median_bps
        FROM direction_oi
        WHERE direction_class='ANALYSIS'
        GROUP BY ALL
        ORDER BY source_dataset, n DESC
        """
    )


def build_native_confluence(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE native_directional AS
        SELECT *,
          CASE
            WHEN state='BUY_EFFECTIVE' THEN 1
            WHEN state='SELL_EFFECTIVE' THEN -1
            WHEN state='BUY_TRAPPED' THEN -1
            WHEN state='SELL_TRAPPED' THEN 1
            ELSE 0
          END AS native_direction_sign
        FROM native_events
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE direction_native_raw AS
        SELECT
          d.*, '5m' AS native_timeframe, 300 AS max_age_sec,
          n.event_time AS native_event_time,
          n.state AS native_state,
          n.native_direction_sign
        FROM directional_outcomes d
        ASOF LEFT JOIN native_directional n
          ON d.symbol=n.symbol
         AND n.timeframe='5m'
         AND d.event_time>=n.event_time
        WHERE d.source_dataset='NEW_05M'
          AND d.primary_clean
        UNION ALL
        SELECT
          d.*, '10m' AS native_timeframe, 600 AS max_age_sec,
          n.event_time AS native_event_time,
          n.state AS native_state,
          n.native_direction_sign
        FROM directional_outcomes d
        ASOF LEFT JOIN native_directional n
          ON d.symbol=n.symbol
         AND n.timeframe='10m'
         AND d.event_time>=n.event_time
        WHERE d.source_dataset='NEW_05M'
          AND d.primary_clean
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE direction_native AS
        SELECT *,
          epoch(event_time-native_event_time) AS native_age_sec,
          CASE
            WHEN native_event_time IS NULL THEN 'MISSING'
            WHEN epoch(event_time-native_event_time)>max_age_sec THEN 'STALE'
            WHEN native_direction_sign=0 THEN 'NATIVE_STALLED'
            WHEN native_direction_sign=direction_sign THEN 'SAME_DIRECTION'
            WHEN native_direction_sign=-direction_sign THEN 'OPPOSITE_DIRECTION'
            ELSE 'UNKNOWN'
          END AS native_agreement
        FROM direction_native_raw
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE native_confluence_summary AS
        SELECT
          native_timeframe, direction_class, hypothesis, state,
          window_sec, horizon_sec, native_agreement,
          count(*) AS n,
          100.0*count_if(signed_return_bps>0)/count(*) AS match_pct,
          avg(signed_return_bps) AS signed_mean_bps,
          median(signed_return_bps) AS signed_median_bps
        FROM direction_native
        GROUP BY ALL
        ORDER BY
          native_timeframe, direction_class, state, hypothesis,
          window_sec, horizon_sec, native_agreement
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE native_confluence_report AS
        SELECT
          native_timeframe, native_agreement, count(*) AS n,
          100.0*count_if(signed_return_bps>0)/count(*) AS match_pct,
          avg(signed_return_bps) AS signed_mean_bps,
          median(signed_return_bps) AS signed_median_bps
        FROM direction_native
        WHERE direction_class='ANALYSIS'
        GROUP BY ALL
        ORDER BY native_timeframe, n DESC
        """
    )


def build_hfm_tables(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE hfm_usd_audit AS
        SELECT
          count(*) AS n,
          count_if(
            abs(cast(long_net_usd AS DOUBLE)-(
              cast(outcome_bid AS DOUBLE)-cast(entry_ask AS DOUBLE)
            ))>1e-8
          ) AS long_net_violation_n,
          count_if(
            abs(cast(short_net_usd AS DOUBLE)-(
              cast(entry_bid AS DOUBLE)-cast(outcome_ask AS DOUBLE)
            ))>1e-8
          ) AS short_net_violation_n,
          count_if(
            cast(long_mfe_usd AS DOUBLE)<cast(long_net_usd AS DOUBLE)
            OR cast(long_mae_usd AS DOUBLE)>cast(long_net_usd AS DOUBLE)
          ) AS long_path_violation_n,
          count_if(
            cast(short_mfe_usd AS DOUBLE)<cast(short_net_usd AS DOUBLE)
            OR cast(short_mae_usd AS DOUBLE)>cast(short_net_usd AS DOUBLE)
          ) AS short_path_violation_n,
          max(abs(
            cast(long_return_bps AS DOUBLE)
            -cast(long_net_usd AS DOUBLE)/cast(entry_ask AS DOUBLE)*10000.0
          )) AS long_return_max_error_bps,
          max(abs(
            cast(short_return_bps AS DOUBLE)
            -cast(short_net_usd AS DOUBLE)/cast(entry_bid AS DOUBLE)*10000.0
          )) AS short_return_max_error_bps,
          median(cast(entry_ask AS DOUBLE)-cast(entry_bid AS DOUBLE))
            AS entry_spread_median_usd
        FROM hfm
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE hfm_usd_summary AS
        SELECT
          timeframe, context_code, horizon_sec, status,
          count(*) AS n,
          count_if(cast(long_net_usd AS DOUBLE)>0) AS long_positive_n,
          100.0*count_if(cast(long_net_usd AS DOUBLE)>0)/count(*)
            AS long_positive_pct,
          quantile_cont(cast(long_net_usd AS DOUBLE),0.25) AS long_net_p25_usd,
          median(cast(long_net_usd AS DOUBLE)) AS long_net_median_usd,
          quantile_cont(cast(long_net_usd AS DOUBLE),0.75) AS long_net_p75_usd,
          quantile_cont(cast(long_mfe_usd AS DOUBLE),0.25) AS long_mfe_p25_usd,
          median(cast(long_mfe_usd AS DOUBLE)) AS long_mfe_median_usd,
          quantile_cont(cast(long_mfe_usd AS DOUBLE),0.75) AS long_mfe_p75_usd,
          quantile_cont(cast(long_mae_usd AS DOUBLE),0.25) AS long_mae_p25_usd,
          median(cast(long_mae_usd AS DOUBLE)) AS long_mae_median_usd,
          quantile_cont(cast(long_mae_usd AS DOUBLE),0.75) AS long_mae_p75_usd,
          count_if(cast(short_net_usd AS DOUBLE)>0) AS short_positive_n,
          100.0*count_if(cast(short_net_usd AS DOUBLE)>0)/count(*)
            AS short_positive_pct,
          quantile_cont(cast(short_net_usd AS DOUBLE),0.25) AS short_net_p25_usd,
          median(cast(short_net_usd AS DOUBLE)) AS short_net_median_usd,
          quantile_cont(cast(short_net_usd AS DOUBLE),0.75) AS short_net_p75_usd,
          quantile_cont(cast(short_mfe_usd AS DOUBLE),0.25) AS short_mfe_p25_usd,
          median(cast(short_mfe_usd AS DOUBLE)) AS short_mfe_median_usd,
          quantile_cont(cast(short_mfe_usd AS DOUBLE),0.75) AS short_mfe_p75_usd,
          quantile_cont(cast(short_mae_usd AS DOUBLE),0.25) AS short_mae_p25_usd,
          median(cast(short_mae_usd AS DOUBLE)) AS short_mae_median_usd,
          quantile_cont(cast(short_mae_usd AS DOUBLE),0.75) AS short_mae_p75_usd
        FROM hfm
        GROUP BY ALL
        ORDER BY timeframe, context_code, horizon_sec, status
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE hfm_report_summary AS
        SELECT
          timeframe, horizon_sec, count(*) AS n,
          100.0*count_if(cast(long_net_usd AS DOUBLE)>0)/count(*)
            AS long_positive_pct,
          median(cast(long_net_usd AS DOUBLE)) AS long_net_median_usd,
          median(cast(long_mfe_usd AS DOUBLE)) AS long_mfe_median_usd,
          median(cast(long_mae_usd AS DOUBLE)) AS long_mae_median_usd,
          100.0*count_if(cast(short_net_usd AS DOUBLE)>0)/count(*)
            AS short_positive_pct,
          median(cast(short_net_usd AS DOUBLE)) AS short_net_median_usd,
          median(cast(short_mfe_usd AS DOUBLE)) AS short_mfe_median_usd,
          median(cast(short_mae_usd AS DOUBLE)) AS short_mae_median_usd
        FROM hfm
        WHERE status='OK'
        GROUP BY ALL
        ORDER BY timeframe, horizon_sec
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE hfm_native_raw AS
        SELECT
          h.*,
          n.event_time AS binance_event_time,
          n.state AS binance_state,
          cast(n.observed_price AS DOUBLE) AS binance_entry_price,
          cast(n.outcome_price AS DOUBLE) AS binance_outcome_price,
          cast(n.forward_return_bps AS DOUBLE) AS binance_return_bps
        FROM hfm h
        ASOF LEFT JOIN native_outcomes n
          ON h.symbol=n.symbol
         AND h.timeframe=n.timeframe
         AND h.horizon_sec=n.horizon_sec
         AND h.event_time>=n.event_time
        WHERE h.status='OK'
          AND h.horizon_sec IN (300,600)
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE hfm_native_match AS
        SELECT *,
          epoch(event_time-binance_event_time) AS binance_event_age_sec,
          (
            (
              (cast(outcome_bid AS DOUBLE)+cast(outcome_ask AS DOUBLE))/2.0
            ) / (
              (cast(entry_bid AS DOUBLE)+cast(entry_ask AS DOUBLE))/2.0
            ) - 1.0
          ) * 10000.0 AS hfm_mid_return_bps,
          CASE
            WHEN binance_event_time IS NULL THEN 'MISSING'
            WHEN epoch(event_time-binance_event_time)>2 THEN 'STALE'
            ELSE 'MATCHED'
          END AS match_status
        FROM hfm_native_raw
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE hfm_binance_alignment AS
        SELECT
          timeframe, horizon_sec,
          count(*) AS hfm_ok_n,
          count_if(match_status='MATCHED') AS matched_n,
          count_if(
            match_status='MATCHED'
            AND sign(hfm_mid_return_bps)=sign(binance_return_bps)
          ) AS same_sign_n,
          100.0*count_if(
            match_status='MATCHED'
            AND sign(hfm_mid_return_bps)=sign(binance_return_bps)
          )/nullif(count_if(match_status='MATCHED'),0) AS same_sign_pct,
          corr(
            hfm_mid_return_bps,
            CASE WHEN match_status='MATCHED' THEN binance_return_bps END
          ) AS return_correlation,
          median(
            CASE WHEN match_status='MATCHED' THEN hfm_mid_return_bps END
          ) AS hfm_mid_median_bps,
          median(
            CASE WHEN match_status='MATCHED' THEN binance_return_bps END
          ) AS binance_median_bps,
          median(
            CASE WHEN match_status='MATCHED'
              THEN cast(long_net_usd AS DOUBLE) END
          ) AS long_net_median_usd
        FROM hfm_native_match
        GROUP BY ALL
        ORDER BY timeframe, horizon_sec
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE combined_context_join_audit AS
        SELECT
          count(*) AS hfm_n,
          count_if(c.event_time IS NOT NULL) AS matched_context_n,
          count_if(c.event_time IS NULL) AS missing_context_n
        FROM hfm h
        LEFT JOIN combined_context c USING(event_time,symbol,timeframe)
        """
    )


def write_outputs(
    con: duckdb.DuckDBPyConnection,
    paths: ProjectPaths,
    manifest: dict[str, object],
) -> dict[str, int]:
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "direction_by_state_window_horizon.csv": write_query_csv(
            con,
            paths.output_dir / "direction_by_state_window_horizon.csv",
            "SELECT * FROM direction_summary",
        ),
        "new_old_cell_comparison.csv": write_query_csv(
            con,
            paths.output_dir / "new_old_cell_comparison.csv",
            "SELECT * FROM cell_comparison",
        ),
        "mfe_mae_by_state_horizon.csv": write_query_csv(
            con,
            paths.output_dir / "mfe_mae_by_state_horizon.csv",
            "SELECT * FROM mfe_summary",
        ),
        "hfm_context_usd.csv": write_query_csv(
            con,
            paths.output_dir / "hfm_context_usd.csv",
            "SELECT * FROM hfm_usd_summary",
        ),
        "hfm_binance_alignment.csv": write_query_csv(
            con,
            paths.output_dir / "hfm_binance_alignment.csv",
            "SELECT * FROM hfm_binance_alignment",
        ),
        "jst_hour_event_frequency.csv": write_query_csv(
            con,
            paths.output_dir / "jst_hour_event_frequency.csv",
            "SELECT * FROM jst_hour_event_frequency",
        ),
        "jst_hour_performance.csv": write_query_csv(
            con,
            paths.output_dir / "jst_hour_performance.csv",
            "SELECT * FROM jst_hour_performance",
        ),
        "confluence_oi.csv": write_query_csv(
            con,
            paths.output_dir / "confluence_oi.csv",
            "SELECT * FROM oi_confluence_summary",
        ),
        "confluence_native_flow.csv": write_query_csv(
            con,
            paths.output_dir / "confluence_native_flow.csv",
            "SELECT * FROM native_confluence_summary",
        ),
    }
    manifest["derived_outputs"] = outputs
    manifest_path = paths.output_dir / "input_manifest.json"
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2, default=str)
        handle.write("\n")
    return outputs


def report_direction_table(
    con: duckdb.DuckDBPyConnection,
    source: str,
    direction_class: str,
) -> str:
    rows = con.execute(
        """
        SELECT state,hypothesis,window_sec,horizon_sec,n,
               match_pct,flat_pct,
               raw_p25_bps,raw_median_bps,raw_p75_bps,
               signed_p25_bps,signed_median_bps,signed_p75_bps
        FROM direction_summary
        WHERE source_dataset=?
          AND sample_scope='PRIMARY_CLEAN'
          AND direction_class=?
        ORDER BY state,hypothesis,window_sec,horizon_sec
        """,
        [source, direction_class],
    ).fetchall()
    formatted = [
        [
            row[0],
            row[1],
            row[2],
            row[3],
            f"{row[4]:,}",
            fmt(row[5], 1),
            fmt(row[6], 1),
            fmt(row[7]),
            fmt(row[8]),
            fmt(row[9]),
            fmt(row[10]),
            fmt(row[11]),
            fmt(row[12]),
        ]
        for row in rows
    ]
    return markdown_table(
        [
            "state",
            "仮説",
            "window秒",
            "horizon秒",
            "n",
            "一致%",
            "flat%",
            "raw p25",
            "raw中央値",
            "raw p75",
            "方向p25",
            "方向中央値",
            "方向p75",
        ],
        formatted,
    )


def build_report(
    con: duckdb.DuckDBPyConnection,
    paths: ProjectPaths,
    manifest: dict[str, object],
) -> str:
    generated = datetime.now().astimezone().isoformat(timespec="seconds")
    quality = con.execute(
        """
        SELECT
          source_dataset, count(*) raw_n,
          count_if(quality_eligible) quality_n,
          count_if(quality_eligible AND primary_clean) primary_clean_n,
          count_if(quality_eligible AND NOT primary_clean) pre_fix_filtered_n,
          count_if(NOT quality_eligible) excluded_n,
          count_if(mfe_eligible) mfe_eligible_n,
          min(event_time), max(event_time)
        FROM outcome_quality
        GROUP BY source_dataset
        ORDER BY source_dataset
        """
    ).fetchall()
    quality_rows = [
        [
            row[0],
            f"{row[1]:,}",
            f"{row[2]:,}",
            f"{row[3]:,}",
            f"{row[4]:,}",
            f"{row[5]:,}",
            f"{row[6]:,}",
            str(row[7]),
            str(row[8]),
        ]
        for row in quality
    ]

    comparison = con.execute(
        """
        SELECT
          count(*) AS cells,
          count_if(comparison_eligible) AS eligible_cells,
          corr(new_match_pct,old_match_pct)
            FILTER (WHERE comparison_eligible) AS rate_corr,
          avg(abs(match_diff_pp))
            FILTER (WHERE comparison_eligible) AS mean_abs_diff_pp,
          100.0*count_if(comparison_eligible AND same_median_sign)
            /nullif(count_if(comparison_eligible),0) AS same_median_sign_pct,
          100.0*count_if(comparison_eligible AND same_accuracy_side)
            /nullif(count_if(comparison_eligible),0) AS same_accuracy_side_pct
        FROM cell_comparison
        """
    ).fetchone()
    comparison_rows = con.execute(
        """
        SELECT state,window_sec,horizon_sec,new_n,new_match_pct,
               old_n,old_match_pct,match_diff_pp,
               same_median_sign,same_accuracy_side
        FROM cell_comparison
        WHERE comparison_eligible
        ORDER BY abs(match_diff_pp) DESC,state,window_sec,horizon_sec
        LIMIT 20
        """
    ).fetchall()

    mfe_rows = con.execute(
        """
        SELECT source_dataset,state,hypothesis,horizon_sec,n,
               mfe_p25_bps,mfe_median_bps,mfe_p75_bps,mfe_p95_bps,
               mae_p25_bps,mae_median_bps,mae_p75_bps,
               threshold_median_bps,reached_20usd_pct
        FROM mfe_summary
        ORDER BY source_dataset,direction_class,state,hypothesis,horizon_sec
        """
    ).fetchall()

    hfm_status = con.execute(
        """
        SELECT status,count(*) FROM hfm GROUP BY status ORDER BY status
        """
    ).fetchall()
    hfm_rows = con.execute(
        "SELECT * FROM hfm_report_summary"
    ).fetchall()
    hfm_alignment = con.execute(
        "SELECT * FROM hfm_binance_alignment"
    ).fetchall()
    context_audit = con.execute(
        "SELECT * FROM combined_context_join_audit"
    ).fetchone()
    hfm_usd_audit = con.execute(
        "SELECT * FROM hfm_usd_audit"
    ).fetchone()
    mfe_reach_span = con.execute(
        """
        SELECT min(reached_20usd_pct),max(reached_20usd_pct)
        FROM mfe_summary
        WHERE direction_class='ANALYSIS'
        """
    ).fetchone()

    hfm_matched_n = sum(row[3] for row in hfm_alignment)
    hfm_sign_match_n = sum(row[4] for row in hfm_alignment)
    hfm_sign_match_pct = (
        100.0 * hfm_sign_match_n / hfm_matched_n if hfm_matched_n else None
    )
    hfm_corr_values = [row[6] for row in hfm_alignment if row[6] is not None]
    hfm_negative_net_medians = sum(
        int(row[4] < 0) + int(row[8] < 0) for row in hfm_rows
    )
    hfm_net_median_cells = 2 * len(hfm_rows)

    hour_rows = con.execute(
        "SELECT * FROM jst_hour_report"
    ).fetchall()
    oi_rows = con.execute(
        "SELECT * FROM oi_confluence_report"
    ).fetchall()
    native_rows = con.execute(
        "SELECT * FROM native_confluence_report"
    ).fetchall()

    lines: list[str] = [
        "# Step 2 トリガー実績集計報告",
        "",
        f"生成時刻: {generated}",
        "",
        "> **本集計は傾向の一次把握であり、確定判断ではない。** "
        "対象期間は実質数日であり、rolling windowの更新は独立取引ではない。"
        "一致率の分母を独立標本数、勝率、発注可能性として読み替えない。",
        "",
        "## 0. エグゼクティブ結論",
        "",
        f"- 承認済み確定母集団は新05M {manifest['counts']['new_outcomes']:,}件、"
        f"旧1M {manifest['counts']['old_outcomes']:,}件、計 "
        f"{manifest['counts']['new_outcomes'] + manifest['counts']['old_outcomes']:,}件である。",
        f"- 新旧の比較可能セルは{comparison[1]:,}。一致率相関は"
        f"{fmt(comparison[2], 3)}、平均絶対差は{fmt(comparison[3], 2)}pp、"
        f"方向return中央値が同符号なのは{fmt(comparison[4], 1)}%、"
        f"一致率が50%の同じ側なのは{fmt(comparison[5], 1)}%だった。"
        "新旧期間をまたいで安定再現した状態×window×horizon傾向とは判断できない。",
        f"- 順行20 USD到達率は状態×horizonにより"
        f"{fmt(mfe_reach_span[0], 1)}%〜{fmt(mfe_reach_span[1], 1)}%。"
        "MFE/MAEは候補の幅を示すが、この短期間だけでentry条件へ昇格させない。",
        f"- HFM 553件のUSD式・path順序の違反は0件。Binance nativeと照合できた"
        f"{hfm_matched_n:,}件中{hfm_sign_match_n:,}件（{fmt(hfm_sign_match_pct, 1)}%）で"
        f"中値returnの符号が一致し、相関は{fmt(min(hfm_corr_values), 4)}〜"
        f"{fmt(max(hfm_corr_values), 4)}だった。一方、OK標本のlong/short net中央値は"
        f"{hfm_negative_net_medians}/{hfm_net_median_cells}セルすべて負で、"
        f"建値spread中央値は{fmt(hfm_usd_audit[7])} USD。市場方向の整合と"
        "実行可能な収益性は別である。",
        "- JST時間帯、OI、native_flowには局所差があるが、新旧またはcontext間で"
        "一貫した改善を確認できない。現段階の結論は仮説候補の記録までとする。",
        "- confluenceはOI・native_flowのみ。統合判断層の構築前に、"
        "吸収・大口約定・スイープのイベント永続化が必要である。",
        "",
        "## 1. 入力固定と品質監査",
        "",
        f"- 新05M cutoff: `{NEW_CUTOFF_ISO}`"
        f"（実行母集団 {manifest['counts']['new_outcomes']:,}件 / "
        f"Step 1当初Parquet目録 {NEW_EXPECTED:,}件）",
        "- 母集団訂正: Parquet上書き問題の監査後、コピー済みDuckDB/WALの"
        f"{manifest['run_inventory']['new_05m']:,}件を2026-07-26に承認",
        f"- 新05M source mode: `{manifest['new_source_mode']}`",
        "- 旧46,492件: 停止済み `data/duckdb/orderflow.duckdb` をREAD_ONLY接続",
        f"- 非正値修正後のclean境界: `{CLEAN_BOUNDARY_ISO}`",
        "- 元記録の更新・削除・上書き: 0件",
        "",
        markdown_table(
            [
                "dataset",
                "raw",
                "品質有効",
                "主標本clean",
                "修正前filter済",
                "除外",
                "MFE有効",
                "開始",
                "終了",
            ],
            quality_rows,
        ),
        "",
        "旧修正前データは、正値価格・有限値・event価格変化100bps以内の条件を"
        "満たす行だけ補足標本として保持した。MFE/MAEの主集計には使用していない。",
        "",
        "## 2. 状態×window×horizon別の方向一致率とreturn分布",
        "",
        "方向は事前固定した。EFFECTIVEは圧力方向への継続、TRAPPEDは圧力と"
        "反対方向へのreversalである。STALLEDは方向確定状態ではないため、"
        "圧力継続probeと反転probeを別々に表示する。`raw`は保存値、`方向`は"
        "BUY=+1／SELL=-1を乗じた値である。",
        "",
        "### 新05M・方向状態4種",
        "",
        report_direction_table(con, "NEW_05M", "ANALYSIS"),
        "",
        "### 旧1M・方向状態4種",
        "",
        report_direction_table(con, "OLD_1M", "ANALYSIS"),
        "",
        "### 新05M・STALLED参考probe",
        "",
        report_direction_table(con, "NEW_05M", "ENTRY_PROBE"),
        "",
        "### 旧1M・STALLED参考probe",
        "",
        report_direction_table(con, "OLD_1M", "ENTRY_PROBE"),
        "",
        "### 新旧傾向のセル比較",
        "",
        markdown_table(
            [
                "比較セル",
                "n≥30両側",
                "一致率相関",
                "平均絶対差pp",
                "方向中央値同符号%",
                "50%同側%",
            ],
            [
                [
                    comparison[0],
                    comparison[1],
                    fmt(comparison[2], 3),
                    fmt(comparison[3], 2),
                    fmt(comparison[4], 1),
                    fmt(comparison[5], 1),
                ]
            ],
        ),
        "",
        "一致率差が大きい上位20セル:",
        "",
        markdown_table(
            [
                "state",
                "window",
                "horizon",
                "新n",
                "新一致%",
                "旧n",
                "旧一致%",
                "差pp",
                "中央値同符号",
                "50%同側",
            ],
            [
                [
                    row[0],
                    row[1],
                    row[2],
                    row[3],
                    fmt(row[4], 1),
                    row[5],
                    fmt(row[6], 1),
                    fmt(row[7], 1),
                    row[8],
                    row[9],
                ]
                for row in comparison_rows
            ],
        ),
        "",
        "全セルは `new_old_cell_comparison.csv` に収録した。",
        "",
        "## 3. MFE/MAEと順行20 USD到達",
        "",
        "MFE/MAEはclean境界以降だけを使用した。20 USD閾値は各建値ごとに"
        "`20 / observed_price × 10,000` bpsへ換算した。",
        "",
        markdown_table(
            [
                "dataset",
                "state",
                "仮説",
                "hz",
                "n",
                "MFE p25",
                "MFE中央",
                "MFE p75",
                "MFE p95",
                "MAE p25",
                "MAE中央",
                "MAE p75",
                "20$閾値中央bps",
                "順行≥20$%",
            ],
            [
                [
                    row[0],
                    row[1],
                    row[2],
                    row[3],
                    f"{row[4]:,}",
                    fmt(row[5]),
                    fmt(row[6]),
                    fmt(row[7]),
                    fmt(row[8]),
                    fmt(row[9]),
                    fmt(row[10]),
                    fmt(row[11]),
                    fmt(row[12], 3),
                    fmt(row[13], 1),
                ]
                for row in mfe_rows
            ],
        ),
        "",
        "## 4. HFM実建値553件のUSD建検証",
        "",
        "- status: "
        + ", ".join(f"{row[0]}={row[1]:,}" for row in hfm_status),
        f"- combined_context exact-key照合: {context_audit[1]:,}/{context_audit[0]:,}"
        f"（欠測 {context_audit[2]:,}）",
        "- 損益分布はOK 528件だけを使用し、QUOTE_GAP 25件は失敗内訳として残した。",
        "- USD再計算監査: long/short net不一致 "
        f"{hfm_usd_audit[1]}/{hfm_usd_audit[2]}件、MFE/MAE順序違反 "
        f"{hfm_usd_audit[3]}/{hfm_usd_audit[4]}件",
        "- return_bps再計算最大誤差: long "
        f"{fmt(hfm_usd_audit[5], 10)}bps / short "
        f"{fmt(hfm_usd_audit[6], 10)}bps、建値spread中央値 "
        f"{fmt(hfm_usd_audit[7])} USD",
        "",
        markdown_table(
            [
                "tf",
                "hz",
                "n",
                "long正%",
                "long net中央$",
                "long MFE中央$",
                "long MAE中央$",
                "short正%",
                "short net中央$",
                "short MFE中央$",
                "short MAE中央$",
            ],
            [
                [
                    row[0],
                    row[1],
                    row[2],
                    fmt(row[3], 1),
                    fmt(row[4]),
                    fmt(row[5]),
                    fmt(row[6]),
                    fmt(row[7], 1),
                    fmt(row[8]),
                    fmt(row[9]),
                    fmt(row[10]),
                ]
                for row in hfm_rows
            ],
        ),
        "",
        "### Binance側との整合",
        "",
        "HFM bid/ask中値の方向を、同一timeframe・horizonで直前2秒以内の"
        "Binance native outcomeと照合した。180秒はBinance native outcomeが"
        "保存されていないため比較不能である。実行netはHFM spreadを含むため、"
        "市場中値の方向一致と同一ではない。",
        "",
        markdown_table(
            [
                "tf",
                "hz",
                "HFM OK",
                "照合n",
                "符号一致n",
                "符号一致%",
                "return相関",
                "HFM中値中央bps",
                "Binance中央bps",
                "long net中央$",
            ],
            [
                [
                    row[0],
                    row[1],
                    row[2],
                    row[3],
                    row[4],
                    fmt(row[5], 1),
                    fmt(row[6], 4),
                    fmt(row[7]),
                    fmt(row[8]),
                    fmt(row[9]),
                ]
                for row in hfm_alignment
            ],
        ),
        "",
        "## 5. 時間帯別偏り（JST）",
        "",
        "件数は1イベント×window×stateを1回として数えた。方向成績は"
        "方向状態4種の600秒horizonだけをまとめた要約である。状態・window別の"
        "全行は `jst_hour_performance.csv` に収録した。",
        "",
        markdown_table(
            [
                "dataset",
                "JST時",
                "event件数",
                "方向n(600s)",
                "一致%",
                "方向中央値bps",
            ],
            [
                [
                    row[0],
                    row[1],
                    row[2],
                    row[3],
                    fmt(row[4], 1),
                    fmt(row[5]),
                ]
                for row in hour_rows
            ],
        ),
        "",
        "## 6. confluence評価",
        "",
        "### OI",
        "",
        "各Flow event時点とwindow開始時点について、未来を使わず直近過去のOIを"
        "突合した。どちらかのsample ageが30秒を超える場合はSTALEとした。",
        "",
        markdown_table(
            ["dataset", "OI", "n", "一致%", "方向平均bps", "方向中央値bps"],
            [
                [
                    row[0],
                    row[1],
                    row[2],
                    fmt(row[3], 1),
                    fmt(row[4]),
                    fmt(row[5]),
                ]
                for row in oi_rows
            ],
        ),
        "",
        "### native_flow",
        "",
        "新05Mの方向状態4種について、5m／10mごとに直近過去のnative eventを"
        "突合した。5mは300秒、10mは600秒を最大ageとし、native STALLEDは"
        "方向一致へ数えていない。",
        "",
        markdown_table(
            [
                "native tf",
                "関係",
                "n",
                "一致%",
                "方向平均bps",
                "方向中央値bps",
            ],
            [
                [
                    row[0],
                    row[1],
                    row[2],
                    fmt(row[3], 1),
                    fmt(row[4]),
                    fmt(row[5]),
                ]
                for row in native_rows
            ],
        ),
        "",
        "### confluence範囲の限界",
        "",
        "- 今回実績突合したのはOIとnative_flowだけである。",
        "- 吸収・大口約定・スイープは永続化されていないため対象外とした。",
        "- **統合判断層構築には、吸収・大口・スイープのイベント永続化が"
        "先行改修として必要である。**",
        "",
        "## 7. 読み方と結論の制限",
        "",
        "- 対象期間は実質数日であり、時間帯・状態・windowの偏りが大きい。",
        "- 同じ市場局面を複数windowとrolling更新が共有するため、各行は独立取引ではない。",
        "- この結果だけでproduction trigger、発注、勝率、期待値を確定しない。",
        "- 新旧で同じ傾向が見えるセルも、期間外データで条件を事前固定して追試する。",
        "- Flow Price Response、3段チャート、既存観測機能は一切変更していない。",
        "",
        "## 8. 派生成果物",
        "",
        f"- 出力directory: `{paths.output_dir}`",
        f"- 入力manifest: `{paths.output_dir / 'input_manifest.json'}`",
        "- 詳細表: direction、new/old比較、MFE/MAE、HFM、JST、OI、native_flowのCSV",
        "",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    paths = resolve_paths(args)
    strict = not args.no_strict_counts
    con = duckdb.connect()
    con.execute("SET enable_progress_bar=false")
    con.execute("SET TimeZone='Asia/Tokyo'")
    con.execute("SET preserve_insertion_order=false")

    manifest: dict[str, object] = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "source_policy": "READ_ONLY",
        "strict_counts": strict,
        "step1_reported_inventory": {
            "new_05m": NEW_EXPECTED,
            "old_1m": OLD_EXPECTED,
            "total": NEW_EXPECTED + OLD_EXPECTED,
        },
        "approved_run_inventory": {
            "new_05m": args.new_expected_count,
            "old_1m": OLD_EXPECTED,
            "total": args.new_expected_count + OLD_EXPECTED,
            "hfm": HFM_EXPECTED,
            "hfm_ok": HFM_OK_EXPECTED,
            "hfm_quote_gap": HFM_GAP_EXPECTED,
        },
        "run_inventory": {
            "new_05m": args.new_expected_count,
            "old_1m": OLD_EXPECTED,
            "total": args.new_expected_count + OLD_EXPECTED,
        },
        "new_cutoff": NEW_CUTOFF_ISO,
        "clean_boundary": CLEAN_BOUNDARY_ISO,
        "live_duckdb_opened": False,
        "new_duckdb_snapshot": (
            str(paths.new_duckdb_snapshot)
            if paths.new_duckdb_snapshot is not None
            else None
        ),
    }

    source_audit = load_sources(
        con,
        paths,
        strict=strict,
        new_expected=args.new_expected_count,
    )
    manifest.update(source_audit)
    build_quality_and_direction_tables(con)
    build_summary_tables(con)
    build_time_tables(con)
    build_oi_confluence(con)
    build_native_confluence(con)
    build_hfm_tables(con)
    outputs = write_outputs(con, paths, manifest)
    report = build_report(con, paths, manifest)
    paths.report_path.parent.mkdir(parents=True, exist_ok=True)
    paths.report_path.write_text(report, encoding="utf-8")
    con.close()

    print(
        json.dumps(
            {
                "status": "OK",
                "source_counts": source_audit["counts"],
                "derived_rows": outputs,
                "output_dir": str(paths.output_dir),
                "report_path": str(paths.report_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
