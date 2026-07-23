# Database Module

**Document ID**: MOD-003
**Version**: v3.2
**Status**: Draft

---

# 1. Purpose

Persist analytical and historical data using Parquet as the canonical storage format and DuckDB as the analytical database.

---

# 2. Responsibilities

- Write Parquet datasets
- Maintain DuckDB tables
- Buffer incoming records
- Recover from storage failures
- Support historical queries

---

# 3. Inputs

- Trade events
- Order Flow results (Candle records including delta / cvd)
- Signal results
- AI analysis results
## 3.5 Candle Schema

The canonical `candles` record is persisted to both Parquet and DuckDB.

| Field | Type | Description |
|---|---|---|
| `bar_time` | TIMESTAMP | UTC start time of the aggregated bar |
| `symbol` | VARCHAR | Canonical instrument identifier |
| `timeframe` | VARCHAR | Aggregation period from `market.bar_timeframe` |
| `open`, `high`, `low`, `close` | DECIMAL(20,8) | OHLC prices |
| `volume`, `delta`, `cvd` | DECIMAL(20,8) | Aggregated volume and order-flow values |

The DuckDB primary key and the canonical uniqueness rule are `(bar_time, symbol, timeframe)`. Parquet storage is partitioned by UTC date and timeframe; its schema is governed by ParquetSchema.

---

# 4. Outputs

- Parquet files
- DuckDB database
- Storage status events

---

# 5. Storage Policy

- Parquet is the canonical data source.
- DuckDB is regenerated from Parquet when necessary.
- UTC timestamps only.
- Schema changes are version controlled.
- Candle records are persisted per ParquetSchema Candle Schema and DuckDBDDL candles table.

---

# 6. Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `database.parquet_path` | string | data/parquet | Root directory for Parquet files |
| `database.duckdb_path` | string | data/duckdb/orderflow.duckdb | DuckDB database file path |
| `database.batch_size` | int ≥ 1 | 1000 | Maximum records per write batch |
| `database.flush_interval_sec` | int ≥ 1 | 5 | Maximum seconds before flushing a partial batch |

Write is triggered by whichever condition is met first: `batch_size` records accumulated, or `flush_interval_sec` elapsed since last write. This ensures low-latency persistence without excessive I/O.

---

# 7. Error Handling

- Write failure
- Schema mismatch
- Disk full
- Duplicate primary key

---

# 8. Performance Targets

- Batched writes
- Low-latency persistence
- Reliable recovery
- Long-running operation

---

# 9. References

- DuckDBDDL
- ParquetSchema
- DataDictionary
- ErrorCodes

Status: v3.2 — Candle schema specification added (Calibration_log_v1)
