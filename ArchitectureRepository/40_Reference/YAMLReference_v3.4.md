# YAML Reference

**Document ID**: REF-005
**Version**: v3.4
**Status**: Draft

---

# 1. Purpose

Define the canonical configuration format for the Order Flow Analysis Platform.

---

# 2. Sample Configuration

```yaml
system:
  timezone: UTC
  log_level: INFO

market:
  symbol: BTCUSDT
  exchange: BINANCE
  bar_timeframe: 1m
  tick_size: "0.1"

websocket:
  url: "wss://fstream.binance.com/ws"
  reconnect: true
  reconnect_delay_sec: 5
  reconnect_max_retries: 0
  heartbeat_sec: 30
  connect_timeout_sec: 10
  subscribe_streams:
    - "btcusdt@trade"
    - "btcusdt@depth@100ms"
    - "btcusdt@forceOrder"

normalizer:
  exchange_profile: binance
  dedup_window: 10000
  reorder_tolerance_ms: 500

queue:
  default_depth: 10000
  overflow_policy: drop_oldest_log

database:
  parquet_path: data/parquet
  duckdb_path: data/duckdb/orderflow.duckdb
  batch_size: 1000
  flush_interval_sec: 5

signal:
  enabled: false
  weight:
    cvd: 1.0
    footprint: 1.0
    imbalance: 1.0
  confidence_threshold: 0.6
  cvd_slope_ref: null
  stack_ref: 3
  absorption_veto_threshold: 0.5
  evaluation_window: 1 bar

imbalance:
  ratio_threshold: 3.0
  min_volume: null
  ratio_cap: 10.0
  stack_count: 3

absorption:
  window_sec: 10
  price_stall_ticks: 1
  volume_multiplier: 2.0
  volume_ref_bars: 20

mt5:
  enabled: false
  bind_address: 127.0.0.1
  port: 5555
  max_clients: 3
  heartbeat_interval_sec: 5
  max_buffer_messages: 1000

ai:
  enabled: false
  confidence_threshold: 0.70

replay:
  enabled: false
  data_path: null
  speed: 1.0

calibration:
  cvd_slope_ref: null
```

### subscribe_streams notes

| Stream | Purpose |
|--------|---------|
| `btcusdt@trade` | Individual trade feed. Drives CVD / Footprint / Imbalance / Signal / Absorption paths. |
| `btcusdt@depth@100ms` | Order book depth diffs at 100 ms intervals. Requires `order_book_mapping` in the active exchange profile to be processed (see §4.1). |
| `btcusdt@forceOrder` | Liquidation order stream. Events are classified as `"liquidation"` by the DataNormalizer and held in an in-memory ring buffer (not persisted). See ADR-008. |

The `btcusdt@depth@100ms` and `btcusdt@forceOrder` streams are consumed by
downstream normalization only when the active exchange profile declares the
corresponding mapping blocks (see §4.1). Without `order_book_mapping`, depth
frames are filtered at the acquisition layer. `forceOrder` events are always
classified via the `e == "forceOrder"` discriminator regardless of profile.

---

# 3. Rules

- UTF-8 encoding.
- Two-space indentation.
- snake_case keys.
- Undefined keys SHALL cause startup validation failure (E1002). No unknown keys are silently ignored.

---

# 4. Exchange Profiles

Exchange-specific field mappings are defined as separate YAML files under `config/profiles/`. The active profile is selected by `normalizer.exchange_profile`.

Sample Binance profile (`config/profiles/binance.yaml`):

```yaml
profile_name: binance
field_mapping:
  event_time: E
  trade_time: T
  trade_id: t
  symbol: s
  price: p
  quantity: q
  side_field: m
  side_rule: "m == true → SELL, m == false → BUY"
timestamp_format: epoch_ms
```

`trade_id` は Binance Futures の `@trade` ストリームが返す**個別約定ID `t`** に対応させる（ADR-006）。`@aggTrade` は Binance Futures `/ws` + SUBSCRIBE エンドポイントでは配信されないことが確認されており、`@trade` を正式採用。

### 4.1 Order Book Field Mapping (optional)

Exchange profiles MAY declare an `order_book_mapping` block to enable Order Book
normalization. When absent, the Data Normalizer processes only trade events for
that profile (backward-compatible with trade-only profiles).

Sample Binance profile with Order Book mapping:

```yaml
profile_name: binance
field_mapping:
  event_time: E
  trade_time: T
  trade_id: t
  trade_id_fallback: a
  symbol: s
  price: p
  quantity: q
  side_field: m
  side_rule: "m == true → SELL, m == false → BUY"
timestamp_format: epoch_ms
order_book_mapping:
  event_type_field: e
  event_type_snapshot: depthSnapshot
  event_type_diff: depthUpdate
  symbol_field: s
  event_time_field: E
  first_update_id_field: U
  final_update_id_field: u
  previous_final_update_id_field: pu
  bids_field: b
  asks_field: a
  level_price_index: 0
  level_quantity_index: 1
```

Field semantics:

| Field | Description |
|-------|-------------|
| `event_type_field` | Top-level field carrying the event type discriminator |
| `event_type_snapshot` | Value indicating a snapshot event |
| `event_type_diff` | Value indicating a diff event |
| `symbol_field` | Raw field for symbol |
| `event_time_field` | Raw field for event timestamp (uses profile-level `timestamp_format`) |
| `first_update_id_field` | Raw field for exchange first update sequence id (DIFF only, optional if absent in snapshot) |
| `final_update_id_field` | Raw field for exchange final update sequence id |
| `previous_final_update_id_field` | Raw field for exchange-provided previous final update id (optional; Binance Futures `pu`). When present, gap detection uses this field in preference to `first_update_id` continuity for more robust sequencing. |
| `bids_field` | Raw field carrying the bid levels array |
| `asks_field` | Raw field carrying the ask levels array |
| `level_price_index` | Index into a level tuple where price appears (Binance-style `[price, qty]` arrays) |
| `level_quantity_index` | Index into a level tuple where quantity appears |
| `trade_id_fallback` | Optional fallback field for trade ID when the primary `trade_id` field is absent. Binance profile uses `trade_id: t` (primary, `@trade` stream) with `trade_id_fallback: a` for backward compat with `@aggTrade` test fixtures. |

Note: Binance's REST depth snapshot uses `lastUpdateId` and does not carry
`event_type_field`; a profile targeting the REST snapshot path resolves the
event type externally (typically at the acquisition layer) before handing the
record to normalization. Streaming depth updates carry `e = "depthUpdate"` and
are handled by the `event_type_diff` path directly.

---

# 5. Replay Mode

When `replay.enabled` is true, the WebSocket module is replaced by a file reader that reads recorded trade events (one JSON object per line, conforming to JSONSchema Trade Event) from `replay.data_path`. The `replay.speed` multiplier controls playback rate (1.0 = real-time, 0 = as fast as possible). All downstream processing is identical to live mode, enabling deterministic replay.

---

# 6. References

- ConfigurationReference
- EnumDefinitions
- ErrorCodes
- ADR-006_TradeStream_Selection
- ADR-008_LiquidationStream

Status: v3.4 — subscribe_streams sample updated with btcusdt@forceOrder; stream notes table added (MarketData拡張_v1)
