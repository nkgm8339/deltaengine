# Footprint × LIVE DOM × Time & Sales Phase 1 checkpoint

最終更新: 2026-07-28 18:55 JST
状態: 完了

## 承認

2026-07-28のユーザー「GO」をV2.1 GO-6として受領した。

承認範囲:

- normalized `footprint_levels`
- small `footprint_bar_manifest`
- confirmed 1m FootprintBarのBackgroundStorageWriter保存
- bar単位atomic idempotency
- UTC日次ZSTD Parquet archive
- `GET /api/history/footprints`
- `limit`／`before`／`timeframe`
- oldest-first response
- restart後の履歴query
- storage／API／pipeline試験
- Phase 1文書更新

承認範囲外:

- Phase 2 LIVE DOM
- Phase 3 Time & Sales backend
- Phase 4 Canvas Footprint Chart
- Phase 5 DOM／Tape融合
- existing 3段チャートの変更
- completed Flow Price Responseの変更
- automatic purge
- raw trades／candles／Flow／Hook retention変更
- production data削除
- git commit／push

## 開始状態

```text
branch: feature/footprint-dom-tape
HEAD: 92ee4eff823ba31e84f7fc0af197d39b877ec236
```

既存の意図的dirty／untracked状態は保持し、今回のstage対象にしない。

- `DeltaEngine05M.bat`
- `Delta_Engine_Pro4web/docker-compose.yml`
- `Delta_Engine_Pro4web/src/strategy_engine/ingestion/snapshot_producer.py`
- Phase 0C benchmark artifact
- VWAP audit artifact
- trigger関連untracked文書

## 確定設計

- level tableは6列のnormalized shape。
- 4列level ART／unique indexは初期作成しない。
- manifestのsmall primary keyでbar受理を一意化する。
- bar内priceはstrict ascending／uniqueを保存前検証する。
- manifest＋levelsは同一DuckDB transactionでcommit／rollbackする。
- background queueへは1 levelずつでなく1 confirmed FootprintBarを1 itemとして積む。
- forming barおよびshutdown時の未確定barはFootprint履歴へ保存しない。
- archiveはUTC日次1 file、ZSTD、atomic replace、duplicate mergeとする。
- Hot 30日はtargetだが、Phase 1 automatic purgeは実装・有効化しない。

## 完了済み

- `PROJECT_MEMORY.md`全文再確認
- 現行FootprintCalculator、Replay／Live pipeline、StorageWriter、
  BackgroundStorageWriter、history API配線監査
- Phase 0C sizing結果とGO-5 decision再確認
- storage schema／validation実装
  - 6列normalized `footprint_levels`
  - small `footprint_bar_manifest`
  - deterministic content hash
  - strict UTC／finite／positive price／non-negative volume／unique ascending price
- atomic storage実装
  - manifest＋levels single transaction
  - same-content duplicateはbar全体skip＋counter
  - conflicting duplicate／orphan levelsはrollback＋E4002
  - level tableの4列ARTなし
- UTC日次ZSTD archive実装
  - 1 partition 1 `levels.parquet`
  - atomic replace
  - duplicate merge／conflict reject／read-back schema・row count確認
- BackgroundStorageWriterへ1 FootprintBar = 1 queue itemで接続
- Footprint bars／levels／duplicates／failures／flush latency counter追加
- storage targeted tests 9件PASS
- Replay／Live rollover確定barをFootprint storageへ接続
  - shutdown `finalize()` barは既存解析だけに残し、Footprint履歴へ保存しない
- `query_footprints`実装
  - table存在確認
  - `limit`最大100／`before` exclusive UTC cursor／`timeframe`
  - bar oldest-first、level high-to-low
  - WebSocket契約どおり`bid=sell_volume`／`ask=buy_volume`
- `GET /api/history/footprints`実装
  - 初期40本
  - `next_before`
  - server restart後も新規DuckDB connectionからhydrate可能
- `/api/stats`とSTATS pushへFootprint保存counterを投影
- history／API／pipeline境界のtargeted testを追加
- DECIMAL(20,8)の12整数桁上限をstorage境界で明示検証
- history hydrate時にmanifest `level_count`と実level数を照合
- 全targeted suite: **36 passed**
- full regression: **622 passed, 1 skipped**
- V2指示書／V2.1補遺へGO-6完了記録を追記
- Phase 1完了報告を作成

## 未完了

Phase 1承認範囲内の未完了なし。

次Phase以降として未着手:

- Phase 2 LIVE DOM
- Phase 3 Time & Sales backend
- Phase 4 Canvas Footprint Chart／frontend hydrate
- automatic purge／historical backfill

## 変更file

- 本checkpointのみ
- `Delta_Engine_Pro4web/src/database/schema.py`
- `Delta_Engine_Pro4web/src/database/storage.py`
- `Delta_Engine_Pro4web/src/pipeline.py`
- `Delta_Engine_Pro4web/WebApp/history.py`
- `Delta_Engine_Pro4web/WebApp/main.py`
- `Delta_Engine_Pro4web/tests/database/test_footprint_storage.py`
- `Delta_Engine_Pro4web/tests/webapp/test_footprint_history.py`
- `Delta_Engine_Pro4web/tests/webapp/test_api.py`
- `Delta_Engine_Pro4web/tests/test_pipeline.py`
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_FUSION_IMPLEMENTATION_INSTRUCTION_V2_20260728.md`
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_FUSION_PREIMPLEMENTATION_AMENDMENT_V2_1_20260728.md`
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_PHASE1_COMPLETION_REPORT_20260728.md`

## 検証結果

- `py_compile` schema／storage PASS
- 初回pytestはWindows temp ACLで4 setup error、validation 5件はPASS
- workspace内basetempもsandbox ACLでsetup error
- 同一試験を許可済みelevated basetempで再実行: **9 passed**
- schema／storage／pipeline／history／mainの`py_compile`: PASS
- storage／history／API／Replay targeted suite: **36 passed in 8.21s**
- full pytest: **622 passed, 1 skipped in 102.89s**
- `git diff --check`: PASS
- `add_footprint_bar(fp_closed)`: Replay／Live rolloverの2箇所
- `add_footprint_bar(final_fp)`: 0箇所
- `footprint_levels`の明示index: 0
- production runtime／data未変更
- blockerなし

## 次の再開位置

1. ユーザーのGO-7を待つ
2. GO-7受領後、Phase 2 LIVE DOM開始前checkpointを作成
3. BOOK_UPDATE／latest Snapshot projection／fail-closedを実装・検証

commit／pushは別承認まで行わない。
