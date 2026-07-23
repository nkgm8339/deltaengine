# ADR-004 — Data Normalizer Separation

**Status**: Accepted  
**Version**: v3.0

---

# Context

`SystemArchitecture_v3.0.md` and `ModuleDependency_v3.0.md` show Data Normalizer as an independent pipeline stage, and `DataReceiver_v3.0.md` states that valid events are forwarded to the Data Normalizer. However, no module specification existed for Data Normalizer, and it was undecided whether to:

- Define it as an independent module, or
- Merge its responsibility into Data Receiver.

NFR requires scalability to multiple exchanges, loose coupling, and independent module replacement.

---

# Decision

Data Normalizer is defined as an **independent module** (`DataNormalizer_v3.0.md`).

Responsibility boundary:

| Module | Responsibility |
|--------|----------------|
| WebSocket / Data Receiver | Transport: connectivity, payload format validation, forwarding raw exchange events |
| Data Normalizer | Semantics: converting exchange-specific events into canonical records per `MarketDataSchema_v3.0.md` |

---

# Rationale

- Existing architecture documents already depict Data Normalizer as a separate stage; separation requires no modification to `SystemArchitecture`, `ModuleDependency`, or `Sequence` diagrams.
- Multi-exchange support (NFR Scalability, `ExchangeConnectorReference_v3.0.md`) concentrates per-exchange conversion differences in a single module.
- Transport and semantic conversion are distinct concerns; merging them would violate loose coupling and high cohesion principles.

---

# Consequences

Positive

- No ripple changes to existing architecture documents
- Per-exchange normalizers can be added without touching Data Receiver
- Canonical schema enforcement occurs at exactly one stage (SSOT)

Trade-offs

- One additional module specification to maintain
- One additional queue hop on the tick path (within the 50 ms budget per ADR-002)

---

# Related Documents

- SystemArchitecture_v3.0.md
- ModuleDependency_v3.0.md
- DataReceiver_v3.1.md
- DataNormalizer_v3.0.md
- MarketDataSchema_v3.0.md
- ExchangeConnectorReference_v3.0.md
- NFR_v3.0.md
- ADR-002_Module_Communication_v3.0.md
