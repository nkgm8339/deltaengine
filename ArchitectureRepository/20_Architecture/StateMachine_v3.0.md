# State Machine

**Document ID**: ARC-004
**Version**: v3.0
**Status**: Draft

---

# 1. Purpose

Define the lifecycle states of the Order Flow Analysis Platform and the valid transitions between them.

---

# 2. System State Diagram

```text
INITIALIZING
      │
      ▼
CONFIGURATION_LOADED
      │
      ▼
CONNECTING
      │
      ▼
CONNECTED
      │
      ▼
RUNNING
      │
      ├──────────────┐
      ▼              │
RECOVERING           │
      │              │
      ▼              │
RUNNING ◀────────────┘
      │
      ▼
SHUTTING_DOWN
      │
      ▼
STOPPED
```

---

# 3. State Definitions

| State | Description |
|--------|-------------|
| INITIALIZING | Application startup |
| CONFIGURATION_LOADED | Configuration validated |
| CONNECTING | Establishing exchange connection |
| CONNECTED | Connection established |
| RUNNING | Normal event processing |
| RECOVERING | Recovering from recoverable errors |
| SHUTTING_DOWN | Graceful shutdown |
| STOPPED | Processing terminated |

---

# 4. Transition Rules

- INITIALIZING → CONFIGURATION_LOADED after successful configuration validation.
- CONFIGURATION_LOADED → CONNECTING after module initialization.
- CONNECTING → CONNECTED when communication is established.
- CONNECTED → RUNNING after data synchronization.
- RUNNING → RECOVERING on recoverable failures.
- RECOVERING → RUNNING after successful recovery.
- Any active state → SHUTTING_DOWN on shutdown request.
- SHUTTING_DOWN → STOPPED after all resources are released.

---

# 5. References

- SystemArchitecture_v3.0.md
- ModuleDependency_v3.0.md
- Sequence_v3.0.md