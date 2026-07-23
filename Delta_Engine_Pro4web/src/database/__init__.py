"""Storage (Parquet / DuckDB) — M5.

schema: canonical trades/candles schemas (ParquetSchema / DuckDBDDL).
storage: StorageWriter — batched Parquet + DuckDB writes (batch_size / flush_interval).
"""
