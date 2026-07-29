# Persistent Depth History GO-PD1 completion report

完了: 2026-07-29 07:52 JST  
判定: **ISOLATED PROTOTYPE PASS／production未接続**

GO-PD1のformat prototypeを追加した。

変更file:

- `Delta_Engine_Pro4web/tools/persistent_depth_prototype.py`
- `Delta_Engine_Pro4web/tests/tools/test_persistent_depth_prototype.py`
- `ArchitectureRepository/00_Master/PERSISTENT_DEPTH_HISTORY_PD1_CHECKPOINT_20260729.md`

実装候補:

- canonical JSONL
- length-prefixed binary envelope
- periodic keyframe／diff envelope

共通検証:

- exact JSON／decimal string round-trip
- source record count
- checksum material
- diff base sequence
- unsupported codec／format拒否

検証は **2 passed**。local Python環境に`zstandard` packageがないため、prototypeのcodecは明示的に`DEFLATE_FALLBACK`と表示される。これはZSTD圧縮率の採否を意味せず、実ZSTD benchmarkはPD1 follow-upでcodec依存を導入してから行う。production DB／Parquet／runtime／archive／retentionは変更していない。
