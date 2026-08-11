from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb


ROOT = Path(__file__).resolve().parents[3]
PARQUET_DAY = (
    ROOT
    / "Delta_Engine_Pro4web"
    / "data_05M"
    / "parquet"
    / "symbol=BTCUSDT"
    / "year=2026"
    / "month=08"
    / "day=11"
)
FILE_LIMIT = 1800
THRESHOLDS = (Decimal("1"), Decimal("2"), Decimal("5"), Decimal("8"), Decimal("10"), Decimal("20"), Decimal("50"))


def json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def scalar_row(connection: duckdb.DuckDBPyConnection, sql: str) -> dict[str, Any]:
    cursor = connection.execute(sql)
    columns = [column[0] for column in cursor.description]
    return dict(zip(columns, cursor.fetchone(), strict=True))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    files = sorted(PARQUET_DAY.glob("part-*.parquet"), key=lambda path: path.name)[-FILE_LIMIT:]
    if not files:
        raise RuntimeError(f"no parquet files under {PARQUET_DAY}")

    connection = duckdb.connect(":memory:")
    connection.execute("SET threads=4")
    connection.execute(
        """
        CREATE TEMP TABLE raw AS
        SELECT event_time, trade_time, trade_id, symbol, price, quantity, side
        FROM read_parquet(?, union_by_name = true)
        WHERE symbol = 'BTCUSDT'
          AND event_time IS NOT NULL
          AND trade_id IS NOT NULL
          AND quantity > 0
        """,
        [[str(path) for path in files]],
    )
    connection.execute(
        """
        CREATE TEMP TABLE clusters AS
        WITH lagged AS (
          SELECT *,
                 lag(event_time) OVER ordered AS previous_time,
                 lag(side) OVER ordered AS previous_side,
                 lag(date_trunc('minute', event_time)) OVER ordered AS previous_minute
          FROM raw
          WINDOW ordered AS (ORDER BY event_time, trade_id)
        ), marked AS (
          SELECT *,
                 CASE
                   WHEN previous_time IS NULL THEN 1
                   WHEN side <> previous_side THEN 1
                   WHEN date_diff('millisecond', previous_time, event_time) > 40 THEN 1
                   WHEN date_trunc('minute', event_time) <> previous_minute THEN 1
                   ELSE 0
                 END AS begins_cluster
          FROM lagged
        ), grouped AS (
          SELECT *,
                 sum(begins_cluster) OVER (
                   ORDER BY event_time, trade_id
                   ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                 ) AS cluster_number
          FROM marked
        )
        SELECT cluster_number,
               min(event_time) AS first_time,
               max(event_time) AS last_time,
               min(trade_id) AS first_trade_id,
               max(trade_id) AS last_trade_id,
               min(side) AS side,
               sum(quantity) AS quantity,
               min(price) AS low_price,
               max(price) AS high_price,
               count(*) AS fill_count
        FROM grouped
        GROUP BY cluster_number
        """
    )

    raw_stats = scalar_row(
        connection,
        """
        SELECT count(*) AS trade_count,
               min(event_time) AS first_time,
               max(event_time) AS last_time,
               min(quantity) AS minimum,
               max(quantity) AS maximum,
               quantile_disc(quantity, 0.50) AS p50,
               quantile_disc(quantity, 0.90) AS p90,
               quantile_disc(quantity, 0.95) AS p95,
               quantile_disc(quantity, 0.99) AS p99,
               quantile_disc(quantity, 0.995) AS p995,
               quantile_disc(quantity, 0.999) AS p999
        FROM raw
        """,
    )
    cluster_stats = scalar_row(
        connection,
        """
        SELECT count(*) AS cluster_count,
               min(quantity) AS minimum,
               max(quantity) AS maximum,
               quantile_disc(quantity, 0.50) AS p50,
               quantile_disc(quantity, 0.90) AS p90,
               quantile_disc(quantity, 0.95) AS p95,
               quantile_disc(quantity, 0.99) AS p99,
               quantile_disc(quantity, 0.995) AS p995,
               quantile_disc(quantity, 0.999) AS p999,
               max(fill_count) AS max_fill_count
        FROM clusters
        """,
    )
    ranked_quantities = connection.execute(
        """
        SELECT quantity
        FROM clusters
        ORDER BY quantity DESC, first_time, first_trade_id
        LIMIT 20
        """
    ).fetchall()

    elapsed_seconds = connection.execute(
        "SELECT date_diff('millisecond', min(event_time), max(event_time)) / 1000.0 FROM raw"
    ).fetchone()[0]
    elapsed_hours = float(elapsed_seconds) / 3600 if elapsed_seconds else 0.0
    threshold_counts = []
    for threshold in THRESHOLDS:
        count = connection.execute(
            "SELECT count(*) FROM clusters WHERE quantity >= ?",
            [threshold],
        ).fetchone()[0]
        threshold_counts.append(
            {
                "minimum_quantity": str(threshold),
                "cluster_count": count,
                "clusters_per_hour": round(count / elapsed_hours, 3) if elapsed_hours else None,
            }
        )

    output = {
        "source": "completed immutable Parquet files; production DuckDB was not opened",
        "directory": str(PARQUET_DAY),
        "selected_file_count": len(files),
        "first_file": files[0].name,
        "last_file": files[-1].name,
        "elapsed_hours": round(elapsed_hours, 6),
        "raw_trade_stats": raw_stats,
        "cluster_contract": "same symbol + same side + <=40ms chain gap + same UTC minute",
        "cluster_stats": cluster_stats,
        "sample_rank_quantities": {
            "rank_2": ranked_quantities[1][0] if len(ranked_quantities) >= 2 else None,
            "rank_9": ranked_quantities[8][0] if len(ranked_quantities) >= 9 else None,
            "rank_20": ranked_quantities[19][0] if len(ranked_quantities) >= 20 else None,
            "warning": "partial 2.9-hour sample; these are not Automatic calibration values",
        },
        "manual_minimum_scenarios": threshold_counts,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, default=json_default))
    connection.close()


if __name__ == "__main__":
    main()
