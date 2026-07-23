# Sequence

**Document ID**: ARC-003
**Version**: v3.1
**Status**: Draft

---

# 1. Purpose

Define the end-to-end processing sequence for the Order Flow Analysis Platform.

---

# 2. Processing Sequence

```text
Application Start
        │
        ▼
Load Configuration
        │
        ▼
Initialize Modules
        │
        ▼
Start Connector + Receiver (WebSocket開始・depth diff バッファリング開始)
        │
        ▼
Fetch REST Snapshot (Order Book 初期スナップショット取得)
        │
        ▼
apply_initial_sync(snap_id) — lenient sync モード開始
(snap_id 以前の diff は棄却、以降の最初の有効 diff から適用)
        │
        ▼
Receive Market Data
        │
        ▼
Normalize Events
        │
        ▼
Update Order Flow Engine
   ├── CVD
   ├── Footprint
   ├── Imbalance
   └── Absorption
        │
        ▼
Generate Signals
        │
        ▼
Run AI Analysis
        │
        ├── Save Parquet
        ├── Update DuckDB
        └── Send MT5 Data
        │
        ▼
Wait Next Event
```

---

# 3. Sequence Rules

- Every market event follows the same processing path.
- Processing is event-driven.
- Pipeline stages run as concurrent coroutines connected by asyncio.Queue (ADR-002 / ADR-003). Within the Order Flow Engine, the four calculators (CVD, Footprint, Imbalance, Absorption) are called synchronously per ADR-002.
- Errors shall be logged and handled according to documented recovery policies.

---

# 4. Recovery Sequence

```text
Error
  │
  ▼
Log
  │
  ▼
Retry (if applicable)
  │
  ▼
Recover
  │
  ▼
Resume Processing
```

---

# 5. References

- SystemArchitecture
- ModuleDependency
- Documentation_Standard
- ADR-002_Module_Communication
- ADR-003_Concurrency_Model
