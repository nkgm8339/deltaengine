from __future__ import annotations

import argparse
import json
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    return str(value)


def quoted(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()

    db_path = Path(args.db).resolve(strict=True)
    output_path = Path(args.output).resolve()
    if db_path == output_path:
        raise SystemExit('database and output paths must differ')

    result: dict[str, Any] = {
        'database_path': str(db_path),
        'opened_read_only': True,
        'verified_at_utc': datetime.utcnow().isoformat(timespec='microseconds') + 'Z',
        'tables': [],
        'views': [],
        'read_probe': 'PENDING',
        'schema_probe': 'PENDING',
        'count_probe': 'PENDING',
        'period_probe': 'PENDING',
        'status': 'FAIL',
    }

    connection = duckdb.connect(str(db_path), read_only=True)
    try:
        connection.execute('SELECT 1').fetchone()
        result['read_probe'] = 'PASS'

        objects = connection.execute(
            """
            SELECT table_schema, table_name, table_type
            FROM information_schema.tables
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
            ORDER BY table_schema, table_name
            """
        ).fetchall()
        result['schema_probe'] = 'PASS'

        base_tables = [row for row in objects if row[2] == 'BASE TABLE']
        result['views'] = [
            {'schema': row[0], 'name': row[1], 'type': row[2]}
            for row in objects
            if row[2] != 'BASE TABLE'
        ]

        count_ok = True
        period_attempted = 0
        period_ok = True
        for schema_name, table_name, table_type in base_tables:
            columns = connection.execute(
                """
                SELECT column_name, data_type, ordinal_position
                FROM information_schema.columns
                WHERE table_schema = ? AND table_name = ?
                ORDER BY ordinal_position
                """,
                [schema_name, table_name],
            ).fetchall()
            qualified = f'{quoted(schema_name)}.{quoted(table_name)}'
            table_result: dict[str, Any] = {
                'schema': schema_name,
                'name': table_name,
                'type': table_type,
                'columns': [
                    {'name': column[0], 'type': column[1], 'ordinal_position': column[2]}
                    for column in columns
                ],
                'row_count': None,
                'period_column': None,
                'period_min': None,
                'period_max': None,
                'status': 'PASS',
            }
            try:
                table_result['row_count'] = connection.execute(
                    f'SELECT COUNT(*) FROM {qualified}'
                ).fetchone()[0]
            except Exception as exc:  # evidence, not silent acceptance
                count_ok = False
                table_result['status'] = 'FAIL'
                table_result['count_error'] = f'{type(exc).__name__}: {exc}'[:500]

            timestamp_columns = [
                column for column in columns
                if 'TIMESTAMP' in column[1].upper()
                or column[0].lower() in {
                    'timestamp', 'event_time', 'event_time_utc', 'created_at',
                    'created_at_utc', 'received_at', 'received_at_utc',
                    'exchange_time', 'exchange_time_utc', 'open_time', 'close_time',
                    'ts', 'time',
                }
            ]
            if timestamp_columns:
                period_attempted += 1
                period_column = timestamp_columns[0][0]
                table_result['period_column'] = period_column
                try:
                    period = connection.execute(
                        f'SELECT MIN({quoted(period_column)}), MAX({quoted(period_column)}) '
                        f'FROM {qualified}'
                    ).fetchone()
                    table_result['period_min'] = json_safe(period[0])
                    table_result['period_max'] = json_safe(period[1])
                except Exception as exc:  # preserve exact limitation
                    period_ok = False
                    table_result['status'] = 'FAIL'
                    table_result['period_error'] = f'{type(exc).__name__}: {exc}'[:500]
            result['tables'].append(table_result)

        result['count_probe'] = 'PASS' if count_ok else 'FAIL'
        result['period_probe'] = (
            'PASS' if period_ok and period_attempted > 0
            else 'NOT_APPLICABLE' if period_attempted == 0
            else 'FAIL'
        )
        result['table_count'] = len(base_tables)
        result['view_count'] = len(result['views'])
        result['period_table_count'] = period_attempted
        result['status'] = (
            'PASS'
            if result['read_probe'] == 'PASS'
            and result['schema_probe'] == 'PASS'
            and result['count_probe'] == 'PASS'
            and result['period_probe'] in {'PASS', 'NOT_APPLICABLE'}
            else 'FAIL'
        )
    finally:
        connection.close()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    return 0 if result['status'] == 'PASS' else 2


if __name__ == '__main__':
    raise SystemExit(main())