# ADR-007 — Order Book Initial Sync (Lenient Mode)

**Status**: Accepted
**Version**: v3.0

---

# Context

The Binance Spot documentation specifies a strict initial sync condition for order book depth diffs:

> Drop any event where `u` is <= `lastUpdateId` in the snapshot. The first processed event should have `U` <= `lastUpdateId`+1 AND `u` >= `lastUpdateId`+1.

This condition assumes contiguous `U` values between consecutive diffs. On Binance Futures, `@depth@100ms` diffs do not have contiguous `U` values; instead, continuity is guaranteed by the `pu` (previous final update id) field. The strict `U <= lastUpdateId+1` condition never matches, causing all diffs to be rejected permanently.

---

# Decision

`OrderBookStateManager.apply_initial_sync(snapshot_update_id)` uses a lenient sync mode:

1. After the REST snapshot is applied, diffs with `final_update_id <= snapshot_update_id` are counted as `diffs_stale` and discarded.
2. The first diff with `final_update_id > snapshot_update_id` completes the sync.
3. After sync, gap detection uses `pu`-based continuity (preferred) or `U == last_u + 1` fallback.

---

# Rationale

- The strict Spot-style condition is inapplicable to Futures `@depth@100ms`.
- The lenient mode correctly handles the Futures update id gap between REST snapshot and first WS diff.
- Post-sync gap detection via `pu` is the correct Futures continuity mechanism.
- Live verification confirmed: `book_diffs_applied: 292`, `book_gaps_detected: 0`, `book_diffs_rejected_before_snap: 0`.

---

# Consequences

Positive

- Order book sync works correctly on Binance Futures.

Trade-offs

- If the platform is ported to Binance Spot, the strict condition may need to be re-evaluated as an option.

---

# Related Documents

- Absorption
- DataNormalizer
- WebSocket
