# MT5 Adapter Module

**Document ID**: MOD-011
**Version**: v3.0
**Status**: Draft

---

# 1. Purpose

Deliver processed analysis results and trading signals from the platform to MetaTrader 5 (MT5) for visualization, fulfilling FR-006.

Delivery is **one-directional** (platform → MT5). The adapter does not receive orders or execute trades (per Requirements Non-Goals).

---

# 2. Responsibilities

- Accept connections from MT5 Expert Advisors / Indicators
- Serialize analysis and signal data into visualization messages
- Push messages to connected MT5 clients in real time
- Maintain connection health (heartbeat, disconnect detection)
- Buffer and drop policy under slow-consumer conditions

---

# 3. Delivery Mechanism

## 3.1 Transport

Local TCP socket. The platform side runs a socket **server**; the MT5 side connects as a **client** using standard MQL5 Socket functions (no DLL required).

- The platform side remains OS-independent (NFR Portability).
- Push-based delivery satisfies UI Refresh ≤ 250 ms (NFR Performance).

## 3.2 Connection Lifecycle

Terminology follows `ExchangeConnectorReference_v3.0.md`:

```text
LISTEN → ACCEPTED → STREAMING → (HEARTBEAT MONITOR) → DISCONNECTED → LISTEN
```

| Item | Rule |
|------|------|
| Heartbeat | Server sends heartbeat every `mt5.heartbeat_interval`; missing 3 consecutive client acknowledgements marks the client disconnected |
| Reconnect | Client-initiated; server accepts reconnection at any time |
| Multiple clients | Up to `mt5.max_clients` simultaneous connections; each receives the full stream |

---

# 4. Inputs

- Signal Events from AI Analysis / Signal Engine (per `JSONSchema_v3.0.md` Section 3)
- Selected analysis values for display (CVD, Imbalance, Absorption events)
- Configuration

---

# 5. Outputs

## 5.1 Message Format

Newline-delimited JSON (one message per line, UTF-8). Base structure extends the Signal Event contract:

```json
{
  "type": "SIGNAL | CVD | IMBALANCE | ABSORPTION | HEARTBEAT",
  "time": "2026-01-01T00:00:01Z",
  "symbol": "BTCUSDT",
  "payload": { }
}
```

- `type = SIGNAL`: payload is the Signal Event per `JSONSchema_v3.0.md` (signal, confidence, reason[])
- `type = CVD / IMBALANCE / ABSORPTION`: payload carries the visualization fields of the respective module output
- `type = HEARTBEAT`: empty payload

Field definitions defer to `DataDictionary_v3.1.md` and `JSONSchema_v3.0.md` (SSOT).

## 5.2 Delivery Guarantee

- At-most-once per client. Visualization data is reproducible from Storage; retransmission is not performed.
- Slow consumer: when a client send buffer exceeds `mt5.max_buffer_messages`, oldest non-SIGNAL messages are dropped first, then SIGNAL messages; drops are counted and logged (no silent loss of statistics).

---

# 6. Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mt5.bind_address` | string | 127.0.0.1 | Listen address (localhost only by default) |
| `mt5.port` | int | 5555 | Listen port |
| `mt5.max_clients` | int ≥ 1 | 3 | Maximum simultaneous MT5 clients |
| `mt5.heartbeat_interval` | duration | 5 s | Heartbeat send interval |
| `mt5.max_buffer_messages` | int | 1000 | Per-client send buffer limit |
| `mt5.enabled` | feature flag | true | Enables/disables the adapter |

Defaults are initial values subject to calibration during implementation.

---

# 7. Error Handling

| Case | Handling |
|------|----------|
| Port already in use | Fail startup validation |
| Client disconnect | Release resources, return to LISTEN, log |
| Send failure | Mark client disconnected, log per `ErrorCodes_v3.0.md` |
| Buffer overflow | Apply drop policy (Section 5.2), count, log |

---

# 8. Performance Targets

- End-to-end delivery latency within UI Refresh budget (≤ 250 ms)
- Stable 24/7 operation
- No impact on the tick processing path (runs as an independent consumer coroutine per ADR-002 / ADR-003)

---

# 9. Dependencies

- AI Analysis (upstream, per ModuleDependency)
- Configuration

---

# 10. Security

- Binds to localhost by default (public market data only; NFR Security)
- No inbound commands are accepted; any received payload other than heartbeat acknowledgement is discarded and logged

---

# 11. References

- Requirements_v3.0.md (FR-006, Non-Goals)
- NFR_v3.0.md
- SystemArchitecture_v3.0.md
- ModuleDependency_v3.0.md
- JSONSchema_v3.0.md
- DataDictionary_v3.1.md
- ExchangeConnectorReference_v3.0.md
- ConfigurationReference_v3.0.md
- ErrorCodes_v3.0.md
- ADR-002_Module_Communication_v3.0.md
- ADR-003_Concurrency_Model_v3.0.md
