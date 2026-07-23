# DERIVATION MANIFEST

## Boundary

- Audit ID: `DE-SEP-001-P0-003`
- 1M reference HEAD: `895a160c321f6d56d668b5a67774c89662242199`
- 30M files measured: 148
- 30M independent Git repository: absent
- Authoritative file-level evidence: `DERIVATION_FILE_MAP.csv`

## Relationship summary

| Relation | Files |
|---|---:|
| `IDENTICAL_RELATIVE_PATH` | 106 |
| `DIFFERENT_RELATIVE_PATH` | 29 |
| `THIRTY_M_ONLY` | 13 |
| Total | 148 |

`IDENTICAL_RELATIVE_PATH` means the same relative path and SHA-256 were observed in both product trees.
`DIFFERENT_RELATIVE_PATH` means the 30M file has the same relative path in 1M but different bytes.
`THIRTY_M_ONLY` means no 1M file at that relative path was found.

This manifest does not claim an unprovable source commit for the 30M tree. The file hashes and measured
relationship are the lineage evidence. Phase 0 does not approve existing 30M differences, initialize Git,
or treat the current tree as a completed separated product.