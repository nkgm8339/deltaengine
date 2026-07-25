# DeltaEngine UI Refresh v2.0 — Live Verification Checkpoint

- Current time: `2026-07-25T23:30:03.2485144+09:00`
- Approval scope: live browser verification and UI-only correction
- Source branch: `ui-refresh-v2`
- Source commit: `4bb5297`
- UI implementation commit: `66b51e3`
- Recovery tag: `pre-ui-refresh-v2-20260725`

## Completed

- Re-read the current `PROJECT_MEMORY.md` in full.
- Confirmed the completed Flow Price Response and three-stage chart remain
  protected.
- Confirmed `mt5.enabled: false`; live verification cannot send MT5 orders.
- Confirmed port `18080` is not currently listening.
- Confirmed the current worktree contains independent uncommitted analysis
  research changes that must not be touched or mixed into UI work.

## Authorization boundary

- Run the committed UI in an isolated worktree.
- Read live Binance market data and write only verification-run data inside
  that isolated worktree.
- Inspect and exercise the UI in a headless Edge browser.
- If a defect is found, change only
  `Delta_Engine_Pro4web/webapp/static/index.html`.

## Pending

1. Create an isolated worktree at commit `4bb5297`.
2. Start the web application in the isolated worktree.
3. Verify live data, WebSocket rendering, geometry, and browser errors.
4. Exercise chart selection, keyboard movement, clear, zoom, Flow window,
   guides, and lower panels.
5. Compare the resulting screenshot with the approved target.
6. Apply and re-test UI-only corrections if required.
7. Remove the isolated worktree and record final results.

## Blockers

- None.

## Exact resume position

Create a detached isolated worktree from `4bb5297`, then start
`uvicorn webapp.main:app` on localhost port `18080` from its
`Delta_Engine_Pro4web` directory.
