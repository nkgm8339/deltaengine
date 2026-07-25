# DeltaEngine UI Refresh v2.0 — Live Verification Checkpoint 3

- Current time: `2026-07-25T23:56:00+09:00`
- Approval scope: live browser verification and UI-only correction
- Verification source: isolated worktree from `4bb5297`
- UI source delta: inline empty data favicon only
- MT5 orders: disabled

## Completed

- Left the locked primary DuckDB untouched.
- Rebuilt an isolated verification database from read-only primary Parquet:
  - candles: 300
  - recent trades: 15,062
  - Flow Response events: 5,000
  - Open Interest samples: 2,500
  - combined context events: 284
- Repeated the live browser verification at `1536 x 1024`.
- Verified dense rendering with 300 closed bars plus one live bar.
- Verified simultaneous live rendering of:
  - three-stage chart
  - selected-candle fixed detail
  - Flow Response
  - Order Book with 30 rows
  - Footprint
  - Flow Events
  - Alerts
  - Open Interest
  - Live Observation
- Verified candle selection, left-arrow movement, right-click clear, wheel
  zoom, Flow window selection, and both guide dialogs.
- Confirmed fixed chart geometry before data, after population, and after
  interaction.
- Confirmed no page overflow.
- Confirmed browser runtime exceptions, console errors, browser log errors,
  and network errors are all zero.
- Confirmed live pipeline health is GREEN, book gaps are zero, and pipeline
  exceptions are zero.

## Observed missing value

Live Observation showed Relative Volume as `—`. This is the existing
missing-value behavior required by project memory. No calculation or fallback
was added.

## Pending

1. Stop the isolated live process.
2. Run JavaScript/DOM checks and regression tests.
3. Record the final verification result.
4. Commit only the favicon correction and UI verification records.
5. Remove temporary browser, screenshot, and isolated-worktree artifacts.

## Blockers

- None.

## Exact resume position

Stop isolated PID `21788`, then run the web UI tests and full repository test
suite from the primary worktree without staging or modifying the independent
analysis-correctness work.
