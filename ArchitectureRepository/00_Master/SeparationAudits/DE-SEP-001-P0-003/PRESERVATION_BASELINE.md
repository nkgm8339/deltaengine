# PRESERVATION BASELINE

## Document control

- Audit ID: `DE-SEP-001-P0-003`
- Plan: `DE-SEP-001-RUN-2`
- Policy: `ISOLATION_POLICY.md` `v1.5-review`
- Inventory boundary UTC: `2026-07-23T09:11:37.3615827Z`
- Runtime C capture UTC: `2026-07-23T10:28:31.9366801Z` to `2026-07-23T10:43:36.6561258Z`
- Verdict: `C_PASS_B_COMPLETENESS_FAIL_GATE_0B_BLOCKED`

## Git and source identity

- outer HEAD/branch: `c133792031dca308e01b6c4824facc283bec3426` / `master`
- outer 1M gitlink: mode `160000`, object `895a160c321f6d56d668b5a67774c89662242199`
- outer `.gitmodules`: absent
- inner 1M HEAD/branch: `895a160c321f6d56d668b5a67774c89662242199` / `master`
- inner remotes: none
- inner modified/untracked: 3 / 9, unchanged at final recheck
- P0-003 dirty patch SHA-256: `30CF908E42E2A59F10F03D0F278F9C62D9172131066112C419F66FBE614B087F`
- P0-003 inner status artifact SHA-256: `404643F03195F41475A6F2A3DCA1ED56A7D1B9133A20B713A85C5C9DB5C81677`
- 30M independent `.git`: absent; Phase 1 not started

Classification A/B/D source capture-before and capture-after manifests each contain 138 files. Path, size, and
SHA-256 mismatch count is 0. The completed 1M logic/UI, config, and operational source did not change during capture.

## File inventory

| Class/state | Files | Bytes at inventory |
|---|---:|---:|
| A completed core | 101 | 831,314 |
| B continuing 1M research | 34 | 189,139 |
| C runtime/research data | 56,945 | 1,098,673,560 |
| D operations/separation boundary | 3 | 1,591 |
| E generated/excluded | 124 | 2,053,867 |
| Total | 57,207 | 1,101,749,471 |

Final C state is 56,938 `STABLE_DATA` files and 7 `ACTIVE_RUNTIME` files. Unclassified files, final hash
errors, reasonless omissions, and `PENDING_ACTIVE_SNAPSHOT` are all 0.

## Python and requirements

- executable: `C:\Users\user\AppData\Local\Programs\Python\Python313\python.exe`
- version: `Python 3.13.12`
- `requirements.txt` SHA-256: `D97B05378476E478FAD17F82392ABEC1412C234272480EA8A1724765232EE1D8`
- `RUN2_PIP_FREEZE.txt` SHA-256: `1DCFCD8C83CF3FA8FA343841CEBE196C85A004509E95707C05A42AC8CD29353E`
- Python environment and requirements were read only

## External artifact A: Git history

- path: external audit-specific `ONE_M_HISTORY.bundle`
- size: 1,801,273 bytes
- SHA-256: `830C4318B9379D4C5737B4F2865A1B635930E21306EF409B713F06310D65CCD4`
- `git bundle verify`: PASS; complete history
- restore clone: PASS
- covered refs include `master` and tags `SAFE-20260719`, `DELTAENGINE-REBIRTH-20260721`,
  `DELTAENGINE-REBIRTH-HOTFIX-20260721`
- required commit `895a160c321f6d56d668b5a67774c89662242199`: reachable

## External artifact B: working tree

- path: external audit-specific `ONE_M_WORKTREE_FORENSIC.zip`
- size: 30,581 bytes
- SHA-256: `FC7638BA7EA97CD2D328B528262AAFFC7BCA4FEBF1E13C14F2E8CD5FACD7D286`
- ZIP open and all actual entry hashes: PASS
- required A/B/D product entries: 138
- actual ZIP entries: 14
- matching required product entries: 12
- missing required product entries: 126
- mismatching present product entries: 0
- extra audit entries: 2
- `SEP-BASE-004`: FAIL

The existing B artifact was not overwritten, deleted, or silently accepted. B completeness and Gate 0B remain blocked.
Evidence: `RUN2_B_ARCHIVE_AUDIT.csv` and `RUN2_B_ARCHIVE_AUDIT.json`.

## External artifact C: runtime and research data

- path: external audit-specific `ONE_M_RUNTIME_FORENSIC.zip`
- size: 405,563,839 bytes
- SHA-256: `720758725714F8F41AEF9D2FDD927338F01BED31AB9208D0BEC9E02F0B93F4D7`
- external post-write re-read hash: matched
- archive entries: 56,945
- stable included: 56,938
- consistent active snapshots: 7
- pending active snapshots: 0
- restore path/size/SHA-256 PASS: 56,945
- source stable inventory/archive/post-hash matches: 56,938
- product source/runtime writes by snapshot process: 0
- product process stop/restart by snapshot process: 0

Active snapshot methods:

- fixed-newline prefix: observer CSV, two non-empty webapp logs, health anomaly JSONL
- zero-length shared-read: two observer logs
- atomic JSON parse: observer status JSON

Evidence: `RUN2_ACTIVE_SNAPSHOT_FINAL.csv`, `RUNTIME_PRESERVATION_MANIFEST.csv`,
`RUN2_RUNTIME_RESTORE_VERIFICATION.csv`, and `RUN2_RUNTIME_ARCHIVE_RESULT.json`.

## Restored DuckDB validation

Only the restored C copy was opened, with DuckDB `read_only=True`.

| Table | Rows | Period column | Minimum | Maximum |
|---|---:|---|---|---|
| candles | 6,198 | bar_time | 2026-07-08 12:08:00 | 2026-07-23 03:04:00 |
| flow_response_events | 11,461 | event_time | 2026-07-21 07:15:51 | 2026-07-23 03:05:20 |
| flow_response_outcomes | 44,737 | event_time | 2026-07-21 07:15:51 | 2026-07-23 03:04:15 |
| open_interest_samples | 6,154 | source_time | 2026-07-22 08:48:50 | 2026-07-23 03:05:18 |
| signals | 6,126 | signal_time | 2026-07-08 12:08:00 | 2026-07-23 03:04:00 |
| trades | 10,923,657 | event_time | 2026-07-08 12:08:32 | 2026-07-23 03:05:23 |

Schema enumeration, read probe, all table counts, and all six period probes passed. The temporary restored tree
was removed only after containment verification. Evidence: `RUN2_DUCKDB_RESTORE_VERIFICATION.json`.

## Process and health boundary

- 1M uvicorn PID 20356 remained alive
- execution-cost observer PID 13760 remained alive
- 1M health remained RED as the user-approved observed baseline
- no 1M/observer stop, restart, repair, checkpoint, migration, or product write occurred
- audit-owned intermediate robocopy was stopped after identity confirmation; it is not a product process

## Gate status and restart point

A and C are fully verified. B is not complete under the approved policy, so this audit cannot be called complete,
`AUDIT_ARTIFACTS_SHA256.txt` must not be generated yet, and Gate 0B must not be presented as pass.
The next authorized step requires a user decision between a strict new P0-004 full recapture or an explicit
policy deviation allowing a separately named supplemental full B artifact. Phase 1 remains unapproved.