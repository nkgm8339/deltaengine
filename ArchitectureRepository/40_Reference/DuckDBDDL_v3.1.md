# DuckDB DDL

**Document ID**: REF-007
**Version**: v3.1
**Status**: Draft

---

# 1. Purpose

Define the canonical DuckDB table definitions for analytical storage.

---

# 2. trades

```sql
CREATE TABLE trades (
    event_time TIMESTAMP,
    trade_time TIMESTAMP,
    trade_id BIGINT PRIMARY KEY,
    symbol VARCHAR,
    price DECIMAL(20,8),
    quantity DECIMAL(20,8),
    side VARCHAR
);
```

---

# 3. signals

```sql
CREATE TABLE signals (
    signal_time TIMESTAMP,
    symbol VARCHAR,
    signal VARCHAR,
    confidence DOUBLE
);
```

---

# 4. ai_results

```sql
CREATE TABLE ai_results (
    analysis_time TIMESTAMP,
    market_state VARCHAR,
    confidence DOUBLE,
    summary VARCHAR
);
```

---

# 5. candles

```sql
CREATE TABLE candles (
    bar_time TIMESTAMP,
    symbol VARCHAR,
    timeframe VARCHAR,
    open DECIMAL(20,8),
    high DECIMAL(20,8),
    low DECIMAL(20,8),
    close DECIMAL(20,8),
    volume DECIMAL(20,8),
    delta DECIMAL(20,8),
    cvd DECIMAL(20,8),
    PRIMARY KEY (bar_time, symbol, timeframe)
);
```

---

# 6. open_interest_samples

    CREATE TABLE open_interest_samples (
        source_time TIMESTAMP,
        received_time TIMESTAMP,
        symbol VARCHAR,
        open_interest DECIMAL(20,8),
        source VARCHAR,
        PRIMARY KEY (source_time, symbol)
    );

---

# 7. Index Strategy

- Primary key on trade_id
- Time-based queries optimized by event_time
- Symbol filtering supported
- Candle queries optimized by bar_time and symbol
- Open Interest queries optimized by source_time and symbol

---

# 8. References

- DataDictionary
- ParquetSchema
- Documentation_Standard
