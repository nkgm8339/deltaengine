# Parquet Schema

**Document ID**: REF-006
**Version**: v3.1
**Status**: Draft

---

# 1. Purpose

Define the canonical Parquet schema used as the primary persistent data store.

---

# 2. General Rules

- Format: Apache Parquet
- Compression: Snappy
- Timezone: UTC
- Partition: symbol/year/month/day
- Schema evolution shall be version controlled.

---

# 3. Trade Schema

| Column | Type |
|---------|------|
| event_time | TIMESTAMP |
| trade_time | TIMESTAMP |
| trade_id | BIGINT |
| symbol | STRING |
| price | DECIMAL(20,8) |
| quantity | DECIMAL(20,8) |
| side | STRING |

---

# 4. Signal Schema

| Column | Type |
|---------|------|
| signal_time | TIMESTAMP |
| symbol | STRING |
| signal | STRING |
| confidence | DOUBLE |

---

# 5. AI Result Schema

| Column | Type |
|---------|------|
| analysis_time | TIMESTAMP |
| market_state | STRING |
| confidence | DOUBLE |
| summary | STRING |

---

# 6. Candle Schema

| Column | Type |
|---------|------|
| bar_time | TIMESTAMP |
| symbol | STRING |
| timeframe | STRING |
| open | DECIMAL(20,8) |
| high | DECIMAL(20,8) |
| low | DECIMAL(20,8) |
| close | DECIMAL(20,8) |
| volume | DECIMAL(20,8) |
| delta | DECIMAL(20,8) |
| cvd | DECIMAL(20,8) |

Partition: symbol/timeframe/year/month/day

---

# 7. Open Interest Sample Schema

Dataset: open_interest_samples

| Column | Type |
|---------|------|
| source_time | TIMESTAMP |
| received_time | TIMESTAMP |
| symbol | STRING |
| open_interest | DECIMAL(20,8) |
| source | STRING |

Partition: symbol/year/month/day

source_time is the exchange timestamp. Missing polls are not interpolated,
forward-filled, or stored as zero.
Samples in the same UTC hour are upserted into one hour-HH Parquet file to avoid
ten-second observations producing thousands of one-row files.

---

# 8. References

- DataDictionary
- JSONSchema
- Documentation_Standard
