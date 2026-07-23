# WebSocket Module

**Document ID**: MOD-002
**Version**: v3.2
**Status**: Draft

---

# 1. Purpose

Manage persistent WebSocket connections to supported exchanges and deliver validated market events to the Data Receiver.

---

# 2. Responsibilities

- Open and maintain WebSocket connections
- Subscribe to required streams
- Receive messages
- Validate payload format
- Detect disconnects
- Reconnect automatically

---

# 3. Inputs

- Configuration
- Exchange endpoint definitions

---

# 4. Outputs

- Trade events
- Order book events
- Connection status events
- Candle events


## 4.8 TICK / CANDLE Event Specification

- `TICK` events carry normalized trade data: `event_time`, `trade_time`, `trade_id`, `symbol`, `price`, `quantity`, and aggressor `side`.
- `CANDLE` events are emitted when a bar closes and carry `bar_time`, `symbol`, `timeframe`, `open`, `high`, `low`, `close`, `volume`, `delta`, and `cvd`.
- `bar_time` is UTC and identifies the start of the aggregation interval. A candle is uniquely identified by `(bar_time, symbol, timeframe)`.
- The WebSocket transport forwards these records without recomputing OHLC, delta, or CVD; canonical field definitions are owned by MarketDataSchema.

---
# 5. Connection Lifecycle

INITIALIZE → CONNECT → SUBSCRIBE → RECEIVE → MONITOR → RECONNECT (if required)

---

# 5.1 Binance Combined Stream Message Unwrapping

Binance Futures combined stream endpoint (`wss://fstream.binance.com/ws`) wraps all event messages in an envelope:

```json
{"stream": "<stream_name>", "data": {...}}
```

BinanceStream automatically unwraps this envelope and yields only the inner `data` object to downstream consumers. This is transparent to the Data Receiver and all upstream modules.

---

# 7. Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `websocket.url` | string | — | Exchange WebSocket endpoint URL |
| `websocket.reconnect` | bool | true | Enable automatic reconnection |
| `websocket.reconnect_delay_sec` | int ≥ 1 | 5 | Seconds between reconnect attempts |
| `websocket.reconnect_max_retries` | int ≥ 0 | 0 (unlimited) | Maximum reconnect attempts; 0 = unlimited |
| `websocket.heartbeat_sec` | int ≥ 1 | 30 | Heartbeat / ping interval in seconds |
| `websocket.connect_timeout_sec` | int ≥ 1 | 10 | Timeout for initial connection |
| `websocket.subscribe_streams` | list of string | — | Exchange-specific stream names to subscribe |
| `market.bar_timeframe` | string | `1m` | Candle aggregation period; emitted CANDLE records carry this value |

Missing `websocket.url` or empty `subscribe_streams` shall cause startup validation failure (E1002).

---

# 8. Error Handling

- Connection refused
- Timeout
- Invalid message
- Sequence mismatch
- Unexpected disconnect

---

# 9. Performance Targets

- Automatic recovery
- Zero intentional data loss
- Stable long-running operation

---

# 10. References

- DataReceiver
- SystemArchitecture
- ExchangeConnectorReference
- ErrorCodes

Status: v3.2 — TICK/CANDLE event and candle configuration specification added (Calibration_log_v1)
