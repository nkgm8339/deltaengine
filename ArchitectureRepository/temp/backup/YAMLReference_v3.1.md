# YAML Reference

**Document ID**: REF-005
**Version**: v3.1
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

websocket:
  url: "wss://fstream.binance.com/ws"
  reconnect: true
  reconnect_delay_sec: 5
  reconnect_max_retries: 0
  heartbeat_sec: 30
  connect_timeout_sec: 10
  subscribe_streams:
    - "btcusdt@aggTrade"
    - "btcusdt@depth@100ms"

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
  trade_id: a
  symbol: s
  price: p
  quantity: q
  side_field: m
  side_rule: "m == true → SELL, m == false → BUY"
timestamp_format: epoch_ms
```

`trade_id` は Binance Futures の `@aggTrade` ストリームが返す**集約取引ID `a`** に対応させる（`@aggTrade` ペイロードは個別約定IDフィールド `t` を持たず、集約IDは `a`）。約定単位で購読する場合は `@trade` ストリーム＋ `trade_id: t` を用いる。

---

# 5. Replay Mode

When `replay.enabled` is true, the WebSocket module is replaced by a file reader that reads recorded trade events (one JSON object per line, conforming to JSONSchema Trade Event) from `replay.data_path`. The `replay.speed` multiplier controls playback rate (1.0 = real-time, 0 = as fast as possible). All downstream processing is identical to live mode, enabling deterministic replay.

---

# 6. References

- ConfigurationReference
- EnumDefinitions
- ErrorCodes
