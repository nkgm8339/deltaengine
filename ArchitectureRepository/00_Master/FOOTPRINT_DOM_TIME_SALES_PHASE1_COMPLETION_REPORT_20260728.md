# Footprint × LIVE DOM × Time & Sales Phase 1 完了報告

完了時刻: 2026-07-28 18:54 JST  
対象branch: `feature/footprint-dom-tape`  
開始HEAD: `92ee4eff823ba31e84f7fc0af197d39b877ec236`  
承認: V2.1 GO-6

## 1. 結論

Phase 1「Footprint保存／履歴API／再起動後hydrate」を実装し、
全回帰試験まで完了した。

完成済みのFlow Price Response、3段チャート、現行WebSocket表示契約は変更していない。
Phase 2以降のLIVE DOM、Time & Sales backend、Canvas UIには着手していない。

## 2. 実装済み契約

### 2.1 DuckDB

`footprint_bar_manifest`

- key: `(bar_time, symbol, timeframe)`
- `level_count`
- bar合計`buy_volume`／`sell_volume`
- deterministic `content_hash`
- small primary keyでbar単位のidempotencyを担当

`footprint_levels`

- `bar_time`
- `symbol`
- `timeframe`
- `price`
- `buy_volume`
- `sell_volume`
- 4列level ART／unique indexは作成しない

manifestとlevelsは同一transactionでinsert／rollbackする。
同一contentの再処理はbar全体をskipし、content不一致、orphan、不完全barはE4002で拒否する。

### 2.2 保存境界

- BackgroundStorageWriterでは1 confirmed FootprintBarを1 queue itemとする。
- Replay／Liveとも、次の時間足へrolloverした時点の`fp_closed`だけを保存する。
- shutdown時の`finalize()` barは既存解析には使用するが、確定Footprint履歴へ保存しない。
- priceは正値、volumeは非負、全値finite、bar内priceはstrict ascending／unique。
- `DECIMAL(20,8)`のscaleと12整数桁上限を保存前に検証する。

### 2.3 Archive

- root: `footprint_levels`
- partition: `symbol/timeframe/UTC year/month/day`
- file: UTC日次`levels.parquet`
- compression: ZSTD
- atomic temporary-file replace
- 同一keyはmerge、content conflictは拒否
- 書込後にschemaとrow countをread-back検証

Archiveの保持期間は無期限である。Hot DuckDB 30日はtargetだが、
Phase 1ではautomatic purgeを実装・有効化していない。

### 2.4 履歴API

`GET /api/history/footprints`

query:

- `limit`: default 40、1〜100
- `before`: timezone付きISO 8601、exclusive cursor
- `timeframe`: supported timeframe。未指定時はmarket設定値

response:

- `footprints`: bar oldest-first
- bar内levels: price high-to-low
- `bid = sell_volume`
- `ask = buy_volume`
- `next_before`: 応答内のoldest `bar_time`
- time: timezone付きUTC ISO 8601

manifest `level_count`と実level数が一致しない場合はhydrateを失敗させ、
不完全履歴を正常データとして返さない。

新規DuckDB connectionからのqueryで、writer終了／server restart後も
保存済み確定barを取得できることを試験した。

## 3. 観測項目

StorageWriter／BackgroundStorageWriter:

- `footprint_bars_written`
- `footprint_levels_written`
- `footprint_duplicates`
- `footprint_write_failures`
- `footprint_flush_median_ms`
- `footprint_flush_p95_ms`

WebApp `/api/stats`へ全項目を投影し、WebSocket STATSには
bars writtenとwrite failuresを投影した。

## 4. 変更file

- `Delta_Engine_Pro4web/src/database/schema.py`
- `Delta_Engine_Pro4web/src/database/storage.py`
- `Delta_Engine_Pro4web/src/pipeline.py`
- `Delta_Engine_Pro4web/WebApp/history.py`
- `Delta_Engine_Pro4web/WebApp/main.py`
- `Delta_Engine_Pro4web/tests/database/test_footprint_storage.py`
- `Delta_Engine_Pro4web/tests/webapp/test_footprint_history.py`
- `Delta_Engine_Pro4web/tests/webapp/test_api.py`
- `Delta_Engine_Pro4web/tests/test_pipeline.py`
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_PHASE1_CHECKPOINT_20260728.md`
- 本報告

既存dirty／untracked fileはreset、checkout、削除、stageしていない。

## 5. 検証

- `py_compile`: schema／storage／pipeline／history／main PASS
- storage専用初回: 9 passed
- 境界追加後targeted suite: 36 passed
- full pytest: **622 passed, 1 skipped in 102.89s**
- `git diff --check`: PASS
- `add_footprint_bar(fp_closed)`: Replay／Liveのrollover経路だけに2箇所
- `add_footprint_bar(final_fp)`: 0箇所
- `footprint_levels`の明示index: 0

## 6. 運用上の注意

- Phase 1は過去raw tradesからのFootprint backfillを行わない。
  履歴は本実装稼働後にrollover確定したbarから蓄積される。
- APIは実装済みだが、既存フロントページはまだhydrateを呼ばない。
  Canvas Footprint UIとの接続はPhase 4で行う。
- production processは起動しておらず、production DuckDB／Parquetは変更していない。
- commit／pushは行っていない。

## 7. 次の承認境界

次はPhase 2「LIVE DOM」である。

GO-7まで未着手:

- `BOOK_UPDATE`
- latest Snapshot projection
- sync前のfail closed
- DOM cadence／payload／reconnect試験

Phase 2でも完成済みのFlow Price Responseと3段チャートは変更対象外とする。
