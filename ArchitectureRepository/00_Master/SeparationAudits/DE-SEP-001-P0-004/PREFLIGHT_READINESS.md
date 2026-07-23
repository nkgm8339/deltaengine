# DE-SEP-001-P0-004 Preflight Readiness

- Decision time: `2026-07-23T20:21:00+09:00`
- Policy: `ISOLATION_POLICY.md` `v1.5-review`
- Gate 0A: `APPROVED`
- Plan 1 readiness: `PASS`
- Plan 2 readiness: `PASS`
- Gate 0A-R: `NOT_REQUIRED_UNDER_CURRENT_RUNTIME_STATE`

## Approval boundary

The user selected strict full recapture option `1` and then explicitly replied `GO` to:

- audit ID `DE-SEP-001-P0-004`;
- local audit root
  `C:\Users\user\Desktop\DeltaEngine\ArchitectureRepository\00_Master\SeparationAudits\DE-SEP-001-P0-004`;
- external root
  `I:\マイドライブ\DeltaEngine_Preservation\DE-SEP-001-P0-004`;
- Gate 0A, Plan 1, and Plan 2;
- preserving the observed 1M RED state without repair, stop, restart, or product change;
- capturing fresh A, B, and C artifacts without overwriting or reusing P0-003 evidence.

## Fresh inventory

| Class/state | Files | Bytes |
|---|---:|---:|
| A | 101 | 831,314 |
| B | 34 | 189,139 |
| C | 56,945 | 1,285,980,572 |
| D | 3 | 1,591 |
| E | 1,692 | 479,745,444 |
| Total | 58,775 | 1,766,748,060 |
| C stable | 56,938 | 674,120,012 |
| C active | 7 | 611,860,560 |

- Enumeration errors: `0`
- Hash errors outside active runtime: `0`
- Unclassified files: `0`
- A/B/D files required in worktree ZIP: `138`
- E files are regenerable Python/pytest caches or temporary test artifacts and are excluded with a recorded reason.

## Live-safe snapshot decision

The raw preflight summary recorded `gate_0a_r_required=true` only because five known active files reject the
ordinary exclusive `Get-FileHash` open while their writers are alive. This is expected and is not used as their
capture method.

All seven known process-owned paths passed their approved application-consistent method:

- two observer log files: shared-read zero-length snapshot;
- observer CSV: shared-read complete-newline fixed prefix;
- observer status JSON: atomic read plus JSON parse;
- webapp stderr/stdout: shared-read complete-newline fixed prefix;
- daily anomaly JSONL: shared-read complete-newline fixed prefix.

DuckDB SHA-256 was stable across the activity sample. The Parquet set remained 56,888 files,
224,469,382 bytes with an unchanged latest timestamp. No unknown writer or unstable prefix was found.
Therefore Gate 0A-R is not required for the current state.

## Running state

- 1M uvicorn: PID `20356`, alive; no stop or restart.
- execution-cost observer: PID `13760`, alive; no stop or restart.
- `/api/health`: `RED`.
- The RED state remains the pre-existing OI Parquet atomic-rename Access Denied failure with a dead pipeline.
  It will be preserved as observed and is not repaired by this audit.

## Git and environment

- 1M branch: `master`
- 1M HEAD: `895a160c321f6d56d668b5a67774c89662242199`
- Modified files: `3`
- Untracked files: `9`
- Tags: `3`
- Remotes: `0`
- Python: `3.13.12`
- Executable: `C:\Users\user\AppData\Local\Programs\Python\Python313\python.exe`
- `requirements.txt` SHA-256:
  `D97B05378476E478FAD17F82392ABEC1412C234272480EA8A1724765232EE1D8`
- `pip freeze` evidence SHA-256:
  `1DCFCD8C83CF3FA8FA343841CEBE196C85A004509E95707C05A42AC8CD29353E`

## External destination and capacity

- The P0-004 external directory was absent before approval, then created new and empty.
- Canonical path equals the approved path.
- No directory component is a junction, symlink, or reparse point.
- Write/read/hash/delete probe: `PASS`; the probe was removed and the directory returned to zero items.
- Available external bytes: `11,769,667,584`.
- Available local bytes: `15,881,465,856`.
- Fresh estimated A-C payload: `1,288,803,889` bytes.
- Conservative external requirement (`2 × payload + 2 GiB`): `4,725,091,426` bytes.
- Capacity decision: `PASS`.

The I: destination is a Google Drive-backed logical external location. Provider availability, synchronization
latency, and cloud-account risk remain; archive hash reread from the final external paths is mandatory.

## Recorded risks

Three active paths currently have a second hardlink under the outer repository's `.tmp.driveupload` area:
the observer CSV, observer status JSON, and webapp stderr log. Capture must not write through either identity.
The fixed-prefix/atomic-read methods operate read-only and passed. All final archives must be written only to
the approved external P0-004 directory.

## Next operation

Capture a fresh `ONE_M_HISTORY.bundle`, verify all refs/tags and commit `895a160`, clone it to a temporary
restore root, then create a worktree ZIP containing all 138 A/B/D files and verify every restored path,
size, and SHA-256. Source pre/post hashes must remain identical.
