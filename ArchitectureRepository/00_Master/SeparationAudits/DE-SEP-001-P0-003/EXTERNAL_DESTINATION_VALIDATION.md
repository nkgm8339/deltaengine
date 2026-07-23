# EXTERNAL DESTINATION VALIDATION

## Approved destination

`I:\マイドライブ\DeltaEngine_Preservation\DE-SEP-001-P0-003\`

The directory was new at audit start. It is outside the outer repository, both product roots, the audit root,
and restore temp root. No path component from the drive root to this directory was observed as a junction,
symlink, or reparse point. Existing A/B artifacts and failed/working C partials are never overwritten.

## Capacity and access

- volume: read/write remote-storage-capable FAT32 presentation
- account/display name: intentionally not recorded
- free bytes at preflight: 13,375,188,992
- conservative required bytes including archives, work area, restore extraction, and 50% margin: 3,759,472,472
- headroom at preflight: 9,615,716,520
- capacity verdict: PASS
- explicit ACL record: current Windows user FullControl; no other explicit rule recorded
- marker write/read/hash: PASS
- marker SHA-256: `16192246118790E73540ED23DED1E85BA3D1FBCC320D6A588BC7201A20F1EEA8`

C: physical disk identity could not be queried under the restricted CIM/fsutil permission set. The I: volume
is treated as a remote logical preservation destination. Each final artifact must be re-read from I: and have
its SHA-256 matched after write; this is the audit's cloud-backed write-completion evidence, not a claim about
provider-side long-term durability.

## Artifact state

- `ONE_M_HISTORY.bundle`: new; verify and clone checks PASS
- `ONE_M_WORKTREE_FORENSIC.zip`: new and readable; completeness FAIL (14 actual entries versus 138 required)
- `ONE_M_RUNTIME_FORENSIC.zip`: PASS; 405,563,839 bytes; SHA-256 `720758725714F8F41AEF9D2FDD927338F01BED31AB9208D0BEC9E02F0B93F4D7`;
  56,945-entry restore, DuckDB read-only verification, final rename, and external re-read hash all passed

No credential, account name, or secret content is written to the manifest.