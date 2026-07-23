# Data Normalizer Module

**Document ID**: MOD-010
**Version**: v3.4
**Status**: Draft

---

# 1. Purpose

Convert exchange-specific raw market events received from the Data Receiver into canonical records defined by MarketDataSchema, and deliver them to the Order Flow Engine.

---

# 2. Responsibilities

- Receive raw trade, order book, and liquidation events from Data Receiver
- Map exchange-specific fields to canonical schema fields
- Normalize timestamps, prices, volumes, and sides
- Detect and discard duplicate events (trade path only)
- Detect out-of-order events and apply ordering policy (trade path only)
- Classify raw events into trade / depth / liquidation routing paths
- Publish normalized events to downstream queues

---

# 3. Inputs

- Raw trade events (exchange-specific format, e.g. Binance `@trade`)
- Raw order book events (exchange-specific format, e.g. Binance `@depth@100ms`)
- Raw liquidation events (exchange-specific format, e.g. Binance `@forceOrder`)
- Exchange profile configuration

---

# 4. Outputs

- Normalized Tick Records per MarketDataSchema (event_time, trade_time, trade_id, symbol, price, quantity, side)
- Normalized Order Book Update Records per MarketDataSchema
- Normalized Liquidation Event Records per MarketDataSchema
- Normalization statistics (processed, duplicates dropped, reordered, rejected)

---

# 5. Processing Rules

## 5.1 Event Classification (`classify_raw`)

Before normalization, each raw event is classified into a routing path:

| classify_raw result | Condition | Normalization path |
|--------------------|-----------|--------------------|
| `"liquidation"` | `e == "forceOrder"` | `normalize_raw_liquidation` |
| `"depth"` | Profile has `order_book_mapping` AND event type matches | `normalize_raw_depth` |
| `"trade"` | All other events | `normalize_raw` |

The `"liquidation"` check takes priority over depth classification to ensure forceOrder events are never misrouted to the depth path.

## 5.2 Normalization (Trade Path)

| Item | Rule |
|------|------|
| Timestamp | Convert to UTC datetime. Exchange epoch formats (ms/µs) resolved by exchange profile |
| Symbol | Map exchange symbol to canonical symbol identifier |
| Price | Apply instrument tick size precision per MarketDataSchema rules |
| Quantity | Convert to decimal quantity per MarketDataSchema rules |
| Side | Map exchange aggressor flag to canonical enum per EnumDefinitions |

## 5.3 Exchange Profiles

Per-exchange field mappings are defined as configuration-driven exchange profiles stored as YAML files under `config/profiles/` (see YAMLReference §4 for schema and sample). The active profile is selected by `normalizer.exchange_profile` in the main configuration.

Adding an exchange requires a new profile YAML file only, not code changes to downstream modules.

Profile validation rules:
- All fields in `field_mapping` must be present.
- `timestamp_format` must be one of: `epoch_ms`, `epoch_us`, `iso8601`.
- `side_rule` must map to EnumDefinitions TradeSide values (BUY / SELL).
- Unknown profile name at startup → fail with E1002.

## 5.4 Duplicate Handling

Events with an already-processed `trade_id` (per instrument) within the deduplication window are discarded and counted. Applies to trade path only; liquidation events are not deduplicated.

## 5.5 Out-of-Order Handling

| Condition | Action |
|-----------|--------|
| Timestamp older than last emitted, within `normalizer.reorder_tolerance` | Reorder within buffer and emit in order |
| Older than tolerance | Reject, count, log per ErrorCodes (no silent loss) |

Applies to trade path only.

## 5.6 Determinism

Identical raw input sequences with identical configuration shall produce identical normalized output (deterministic replay).

## 5.7 Liquidation Path (`normalize_raw_liquidation`)

Binance `@forceOrder` payload structure:
```json
{"e": "forceOrder", "E": <epoch_ms>, "o": {"s": "<symbol>", "S": "<side>", "p": "<price>", "q": "<qty>", "T": <epoch_ms>}}
```

Required `o` fields: `s` (symbol), `S` (side), `p` (price), `q` (quantity), `T` (trade time).

Side semantics:
- `S = "SELL"` — the liquidated position was **LONG** (a forced sell order closed a long position).
- `S = "BUY"` — the liquidated position was **SHORT** (a forced buy order closed a short position).

Decimal conversion rules:
- `price` and `quantity` are converted from the API string using `Decimal(str(...))`.
- `float()` calls are prohibited throughout (per platform-wide Decimal constraint).

Missing required fields → `NormalizationError` (E3001). The pipeline logs the error and discards the event without interrupting the stream.

---

# 6. Parquet Schema

## 6.1 Candles Dataset

Normalized candle records SHALL be persisted as the canonical `candles` Parquet dataset. The schema is aligned with MarketDataSchema Candle Record and ParquetSchema:

| Field | Type | Required | Description |
|---|---|---|---|
| `bar_time` | datetime | Yes | UTC start time of the aggregated bar |
| `symbol` | string | Yes | Canonical instrument identifier |
| `timeframe` | string | Yes | Aggregation period from `market.bar_timeframe` |
| `open` / `high` / `low` / `close` | decimal | Yes | OHLC prices |
| `volume` | decimal | Yes | Total traded quantity |
| `delta` | decimal | Yes | Buy volume minus sell volume |
| `cvd` | decimal | Yes | Cumulative volume delta at bar close |

Candles are partitioned by UTC date and timeframe. The canonical record key is `(bar_time, symbol, timeframe)`; Decimal conversion and UTC requirements in §5 remain applicable.

---

# 7. Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `normalizer.dedup_window` | int events | 10000 | Per-instrument trade_id deduplication window |
| `normalizer.reorder_tolerance` | duration | 500 ms | Maximum lateness accepted for reordering |
| `normalizer.exchange_profile` | string | — | Active exchange profile name |

Defaults are initial values subject to calibration during implementation.

---

# 8. Error Handling

- Unknown exchange profile → fail startup validation
- Unmappable field / invalid enum value → reject event, log per ErrorCodes
- Duplicate trade_id → discard, count
- Out-of-tolerance event → reject, count
- Liquidation missing required fields → reject event, log E3001
- No silent data loss (NFR Reliability)

---

# 9. Performance Targets

- Low-latency conversion within the tick processing budget (NFR: ≤ 50 ms end-to-end)
- Zero silent event loss
- Deterministic replay
- Continuous 24/7 operation

---

# 10. Dependencies

- Data Receiver (upstream, per ADR-002 queue)
- Order Flow Engine (downstream, per ADR-002 queue)
- Configuration

---

# 11. References

- DataReceiver
- MarketDataSchema
- EnumDefinitions
- ExchangeConnectorReference
- DataDictionary
- ConfigurationReference
- ErrorCodes
- ADR-002_Module_Communication
- ADR-004_DataNormalizer_Separation
- ADR-008_LiquidationStream

Status: v3.4 — Candle Parquet schema added (Calibration_log_v1)
