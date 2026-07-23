# ISOLATION CHANGE MANIFEST

## Scope

Audit ID `DE-SEP-001-P0-003`, Phase 0 only. Gate 0A permits writes to this audit directory,
the approved external preservation directory, and a product-root-external restore verification temp directory.

## Product changes

| Resource | Planned Phase 0 action | Actual result |
|---|---|---|
| 1M application logic and UI | no change | unchanged |
| 1M config and Python environment | read/hash only | unchanged |
| 1M DB, Parquet, recordings, reports | read/hash/snapshot only | unchanged |
| 1M and observer processes | keep running | not stopped or restarted |
| outer/inner Git index and refs | read only | unchanged |
| 30M source and Git state | read/hash only | unchanged; independent `.git` not created |

No product file or hunk is authorized for modification in Plan 2.

## Audit and preservation writes

- Phase 0 evidence under `ArchitectureRepository/00_Master/SeparationAudits/DE-SEP-001-P0-003/`
- new external A/B artifacts under the approved audit-specific directory
- C staging and unique partial ZIPs under external `C_STAGE`
- final C name only after full restore and external re-read verification
- temporary restored C tree under the current user temp root, removed only after verified safe containment

## Operational helper actions

The audit-owned robocopy PID 23532 copied to an intermediate `C_STAGE`. It was stopped after executable,
PID, start time, source, and destination were confirmed, because direct manifest-driven ZIP capture made it
redundant and avoided remote file-by-file I/O contention. The partial stage remains preserved; it was not
deleted or reused as the final runtime archive. This did not stop or restart 1M or the observer.

## Failed attempts retained as evidence

- Windows PowerShell 5.1 preflight failed before archive creation because it misread the UTF-8 Japanese path.
- the first direct C partial failed after all stable files were written because of a local nullable-limit helper bug.
  The failed partial remains uniquely named and the final C name was not created.

## Phase 1 and later

All Git initialization, product foundation, launcher/process, MT5/Docker/browser work, service startup,
order enablement, and commits remain unapproved and unperformed.