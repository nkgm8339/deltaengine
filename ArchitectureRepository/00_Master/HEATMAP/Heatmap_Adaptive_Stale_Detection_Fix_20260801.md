# Adaptive stale detection fix — 2026-08-01

- Removed the unsubstantiated fixed `2.25s` local stale threshold.
- Book freshness now uses browser `receivedTime`, not server projection time.
- The threshold is adaptive: `max(10s floor, 3 × p95 recent projection gap)`.
- `BOOK_UPDATE` ingestion now records actual browser receive time via `Date.now()`.
- Normal 2–3 second projection cadence no longer creates false hatch gaps; a genuine pause still creates `LOCAL STALE`.

Verification: heatmap core + frame-budget tests **11 passed**.
