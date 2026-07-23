# ISOLATION AUDIT BEFORE

## Document control

- Audit ID: `DE-SEP-001-P0-003`
- Plan: `DE-SEP-001-RUN-2`
- Policy: `ISOLATION_POLICY.md` `v1.5-review`
- Product scope: existing 1M `Delta_Engine_Pro4web` and derived 30M `Delta_Engine_30M`
- Audit state: `PHASE_0_IN_PROGRESS_WITH_B_COMPLETENESS_BLOCKER`
- User decision: preserve the observed 1M RED state without repair, stop, restart, checkpoint, or migration

## Protected product state

The existing 1M Flow Price Response, three-panel chart, Price/CVD/Delta patterns, OI Context,
Flow Event, Footprint, source, config, DB, Parquet, and research data were not modified by this audit.
The 1M web process and execution-cost observer remained running. The health state remained RED because
the pre-existing storage worker had already failed on an OI Parquet atomic rename Access Denied error.
The audit did not repair that operational failure.

## Inventory result

- 1M normal files: 57,207; 1,101,749,471 bytes
- Classification A: 101 files; 831,314 bytes
- Classification B: 34 files; 189,139 bytes
- Classification C: 56,945 files; 1,098,673,560 bytes
- Classification D: 3 files; 1,591 bytes
- Classification E: 124 files; 2,053,867 bytes
- Unclassified: 0
- Classification C stable data: 56,938 files
- Classification C active runtime: 7 files
- Fresh inventory hash errors after live-safe reconciliation: 0

## Runtime and resource findings

- 1M process: PID 20356, Python/uvicorn, loopback port 8080
- execution-cost observer: PID 13760
- active at final capture boundary: observer CSV, observer atomic status JSON, three open logs, and health anomaly JSONL
- DuckDB inventory/current SHA-256 matched: `27E246039BA40C6FFDFB48A02BE6C7C09868D751E6E9A7F4C86DB80DAD2212D1`
- Parquet set remained 56,888 files and 224,469,382 bytes at the measured boundary
- Gate 0A-R was not required because the seven active files support fixed-prefix, zero-length, or atomic JSON snapshots
- two active files have an additional hardlink under the outer `.tmp.driveupload` area; no link was changed

## External preservation status

- A history bundle: created and verify/clone checked
- B worktree ZIP: ZIP open and its 14 entries hash correctly, but it contains only 12 of the required
  138 classification A/B/D product files; 126 are missing and 2 entries are audit metadata
- B verdict: `SEP-BASE-004 FAIL`; existing external ZIP was not overwritten
- C runtime archive: PASS; 56,945 entries restored and hashed, DuckDB read-only validation PASS, external re-read hash matched

The B failure blocks B completeness and Gate 0B only. Runtime preservation, derivation evidence, Git topology,
resource records, and audit documentation continue under the approved Gate 0A scope.

## Prohibited operations confirmed absent

- no 1M or observer stop/restart
- no product source/config/runtime write
- no 30M Git initialization or implementation
- no service, EA, Docker, live 30M port, order, migration, cleanup, or destructive product operation
- no P0-001 or P0-002 modification