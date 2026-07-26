# Analysis output retention

This directory may contain both curated research results and large local source snapshots.

- Curated final CSV tables and their `input_manifest.json` are versioned with the report that cites them.
- `source_snapshot_*` directories are immutable local research evidence. They are ignored by Git because
  they can contain DuckDB/WAL files larger than normal repository hosting limits.
- `provisional_authoritative_db` directories are preserved locally for audit but are not final results.
- Ignored evidence must not be deleted merely because it is absent from `git status`.

For `trigger_outcomes_step2_20260726`, the authoritative snapshot hashes and source counts are recorded in
`ArchitectureRepository/00_Master/ORDERFLOW_TRIGGER_OUTCOME_STEP2_CHECKPOINT_20260726.md` and the adjacent
`input_manifest.json`.
