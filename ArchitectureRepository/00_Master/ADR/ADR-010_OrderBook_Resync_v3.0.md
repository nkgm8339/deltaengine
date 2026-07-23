# ADR-010 — Order Book Resync Supervisor

**Status**: Accepted
**Version**: v3.0

---

# Context

Order book initial sync (ADR-007 lenient mode) had no recovery path: the REST
depth snapshot was fetched exactly once at startup, and a gap-detection reset
left the book permanently uninitialized. Either failure mode resulted in a
permanently empty order book while the trade-side pipeline kept running.

---

# Decision

A resync supervisor coroutine owns order book synchronization for the lifetime
of the live pipeline:

- Whenever the book is uninitialized (startup, or after a gap reset), it
  fetches a REST depth snapshot and re-enters lenient initial-sync mode.
- Failures retry forever with bounded backoff (5s / 10s / 30s cap); every
  failure is logged with the HTTP status or exception text (no silent loss).
- Counters `resyncs` and `fetch_failures` are exposed via LiveStats,
  `/api/stats`, and the STATS WebSocket message.
- The sync algorithm itself (ADR-007 lenient alignment, pu-based gap
  detection) is unchanged. Backoff timings are module constants, not
  configuration, as they are operational values and not calibration targets.
- Replay mode is unaffected.

---

# Consequences

## Positive

- Transient REST failures and sequence gaps self-heal without restart.
- A permanently failing REST endpoint (e.g., HTTP 451 regional block) is now
  diagnosable from the logged status; a WS partial-book fallback is designed
  only if such a block is confirmed.

## Trade-offs

- Diffs arriving before the first snapshot application are rejected and
  counted (`diffs_rejected_before_snapshot`) instead of being buffered; the
  lenient first-diff acceptance converges the state immediately after.

---

# Related Documents

- ADR-007_OrderBook_Initial_Sync
- ErrorCodes
