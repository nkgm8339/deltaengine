# Persistent Depth History GO-PD2 completion report

完了: 2026-07-29 08:02 JST  
判定: **ISOLATED RECOVERY／REPLAY CONTRACT PASS／production未接続**

GO-PD2のisolated segment durability prototypeを追加した。

変更file:

- `Delta_Engine_Pro4web/tools/persistent_depth_recovery.py`
- `Delta_Engine_Pro4web/tests/tools/test_persistent_depth_recovery.py`
- `ArchitectureRepository/00_Master/PERSISTENT_DEPTH_HISTORY_PD2_CHECKPOINT_20260729.md`

検証対象:

- temp segmentへのwrite＋flush＋fsync＋atomic rename
- manifest（stream、sequence range、record count、byte count、SHA-256）
- checksum mismatch／truncated tail fail-closed
- replayがdurable segmentだけを返し、渡されたlive frameを混入しない
- temporary `.tmp`残留なし

PD2 tests: **4 passed**（PD1 prototype 2件を含む）。初回実行でread-only file descriptorへfsyncしていたprototype bugを検出し、write／flush後のfsyncへ修正した。production data path、DuckDB／Parquet、runtime、retention、purgeは変更していない。
