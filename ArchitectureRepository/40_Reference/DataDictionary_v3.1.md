# DataDictionary

**Document ID**: REF-001
**Version**: v3.1
**Status**: Active

---

# 1. Purpose

This is the Single Source of Truth (SSOT) for all data entities, field definitions, and naming conventions used throughout the Order Flow Analysis Platform.

All documents shall reference this document rather than redefining terms.

---

# 2. Market Data Entities

| Entity | Description | Type |
|--------|-------------|------|
| Tick | Individual market event | Event |
| Trade | Executed transaction | Event |
| Bid | Best bid price | Quote |
| Ask | Best ask price | Quote |
| Volume | Executed quantity | Numeric |
| Delta | Ask Volume minus Bid Volume | Derived |
| CVD | Cumulative Volume Delta | Derived |
| OHLC | Aggregated candle | Aggregate |

---

# 3. Common Fields

| Name | Type | Description |
|------|------|-------------|
| event_time | TIMESTAMP | Time the exchange emitted the event (UTC) |
| trade_time | TIMESTAMP | Execution time of the trade (UTC) |
| trade_id | BIGINT | Exchange-unique trade identifier |
| symbol | STRING | Trading instrument identifier |
| price | DECIMAL | Executed or quoted price |
| quantity | DECIMAL | Executed quantity |
| side | ENUM | BUY or SELL aggressor side |
| delta | DECIMAL | BUY volume minus SELL volume |
| cvd | DECIMAL | Cumulative Volume Delta |
| volume | DECIMAL | Total traded volume |

---

# 4. Price Fields

| Field | Type | Unit |
|-------|------|------|
| price | DECIMAL | Instrument tick size |
| bid_price | DECIMAL | Instrument tick size |
| ask_price | DECIMAL | Instrument tick size |

---

# 5. Volume Fields

| Field | Type | Description |
|-------|------|-------------|
| volume | INTEGER | Total executed contracts |
| bid_volume | INTEGER | Executed at bid (sell aggressor) |
| ask_volume | INTEGER | Executed at ask (buy aggressor) |

---

# 6. Derived Metrics

| Metric | Formula |
|--------|---------|
| Delta | ask_volume - bid_volume |
| CVD | CVD(n-1) + Delta(n) |
| VWAP | Σ(price × volume) / Σ(volume) |

---

# 7. Time Standard

- All timestamps shall be stored in UTC.
- Display timezone is implementation-specific.
- Internal processing uses UTC only.

---

# 8. Naming Conventions

- snake_case for all identifiers
- Singular field names
- No abbreviations unless industry standard (CVD, VWAP, DOM, OHLC are permitted)

---

# 9. Ownership

Changes to definitions in this document shall propagate by reference only.

Duplicate definitions in other documents are prohibited.

---

# 10. References

- EnumDefinitions_v3.0.md
- MarketDataSchema_v3.0.md
- JSONSchema_v3.0.md
