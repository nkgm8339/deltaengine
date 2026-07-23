# ADR-002 — Module Communication

**Status**: Accepted  
**Version**: v3.0

---

# Context

The Order Flow Analysis Platform consists of pipeline modules (Data Acquisition, Data Normalizer, Order Flow Engine, Signal Engine, AI Analysis, Storage, MT5 Adapter).

The communication mechanism between modules was undefined. Candidates were:

- Direct function calls
- In-process asynchronous queues
- External message broker (Redis, ZeroMQ, etc.)

NFR requires Tick Processing Latency <= 50 ms, loose coupling, independent module replacement, and support for future distributed processing.

---

# Decision

The platform adopts **in-process asynchronous queues** (`asyncio.Queue`) as the primary inter-module communication mechanism.

Rules:

1. Pipeline stage boundaries (Data Acquisition → Data Normalizer → Order Flow Engine → Signal Engine → AI Analysis) communicate via `asyncio.Queue`.
2. Within the Order Flow Engine, fan-out to the four calculators (CVD, Footprint, Imbalance, Absorption) uses **direct function calls**, since they share the same normalized tick and produce results synchronously.
3. Storage and MT5 Adapter consume from dedicated output queues.
4. All queue payloads shall conform to the contracts defined in `JSONSchema_v3.0.md`.
5. Queues shall be bounded. Overflow handling shall follow `ErrorCodes_v3.0.md` (no silent data loss).

---

# Rationale

- Queues decouple producers and consumers, satisfying the loose coupling and replaceable module principles.
- Direct calls inside the Order Flow Engine avoid unnecessary queue hops on the latency-critical tick path (<= 50 ms).
- The queue abstraction can later be replaced by an external broker without changing module contracts, supporting future distributed processing.
- An external broker at this stage adds operational cost and latency without benefit for a single-process, single-developer system.

---

# Consequences

Positive

- Loose coupling with minimal latency overhead
- Natural backpressure via bounded queues
- Clear migration path to distributed processing

Trade-offs

- Queue depth and overflow policies must be defined per stage in module specifications
- Single-process scope until a broker migration is decided (future ADR)

---

# Related Documents

- SystemArchitecture_v3.0.md
- ModuleDependency_v3.0.md
- NFR_v3.0.md
- JSONSchema_v3.0.md
- ErrorCodes_v3.0.md
- ADR-003_Concurrency_Model_v3.0.md
