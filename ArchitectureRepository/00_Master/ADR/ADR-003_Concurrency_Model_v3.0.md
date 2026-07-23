# ADR-003 — Concurrency Model

**Status**: Accepted  
**Version**: v3.0

---

# Context

The concurrency model of the Order Flow Analysis Platform was undefined. Candidates were:

- Single-process asyncio event loop
- Multi-threading
- Multi-processing

The workload is dominated by I/O (WebSocket ingestion, storage writes) with lightweight per-tick computation. NFR requires Tick Processing Latency <= 50 ms, AI Analysis Latency <= 200 ms, and 24/7 continuous operation.

---

# Decision

The platform adopts a **single-process asyncio event loop** as the concurrency model.

Rules:

1. All pipeline modules run as coroutines on one event loop.
2. Blocking or CPU-heavy operations (e.g., AI Analysis inference, batch Parquet writes) shall be offloaded via `loop.run_in_executor` and shall never block the event loop.
3. Coroutines shall not share mutable state directly; data passes only through the queues defined in ADR-002.
4. Long-running coroutines shall yield control cooperatively; any awaited operation on the tick path shall respect the 50 ms latency budget.
5. Multi-processing is deferred to a future ADR when distributed processing is introduced.

---

# Rationale

- The system is I/O-bound; asyncio handles WebSocket streams efficiently without thread overhead.
- A single event loop eliminates locks and data races, reducing defect risk for a single developer.
- Multi-threading offers little computational benefit under the GIL while adding shared-state complexity.
- Multi-processing is premature at current scale; the queue abstraction of ADR-002 preserves that migration path.

---

# Consequences

Positive

- No lock management, no data races
- Deterministic, testable execution order
- Direct compatibility with `asyncio.Queue` (ADR-002)

Trade-offs

- CPU-bound work must be explicitly offloaded to executors
- Single-core utilization until distributed processing is adopted
- Event loop starvation must be covered by monitoring (LoggingReference, MonitoringReference)

---

# Related Documents

- SystemArchitecture_v3.0.md
- ModuleDependency_v3.0.md
- NFR_v3.0.md
- LoggingReference_v3.0.md
- MonitoringReference_v3.0.md
- ADR-002_Module_Communication_v3.0.md
