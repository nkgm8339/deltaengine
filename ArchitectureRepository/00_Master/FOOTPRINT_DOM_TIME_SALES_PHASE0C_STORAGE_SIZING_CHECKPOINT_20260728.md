# Footprint × LIVE DOM × Time & Sales Phase 0C storage sizing checkpoint

最終更新: 2026-07-28 18:25 JST
状態: GO-5承認済み（GO-6待ち）

## 承認範囲

ユーザーの2026-07-28「GO」に基づき、V2.1 Phase 0Cのread-only storage sizingを行う。

承認に含む:

- production DuckDB／Parquetのread-only inventory
- 24〜72時間のclean trades sample選定
- 1分足Footprint price levels分布
- normalized row tableとnested bar storageの隔離benchmark
- DuckDB／Parquet容量
- latest 40／previous 40／300 bars query latency
- index有無、write batch latency、queue想定の比較
- retention／schema提案
- report／checkpoint作成

承認に含まない:

- production DB／Parquetへの書込み
- raw trades／candles／derived dataの削除
- purge／archive job有効化
- retention日数の本決定
- production schema変更
- Phase 1 source実装
- git commit／push
- BAT／Docker／600秒retention差分の変更

## GO-5承認記録

2026-07-28、Phase 0C報告直後のユーザー「GO」をV2.1 §11のGO-5として受領した。

承認済み:

- normalized `footprint_levels` + small `footprint_bar_manifest`
- 4列level ART／unique indexを初期作成しない
- Hot DuckDB 30日
- UTC日次ZSTD Parquetを期間制限なしで保持
- Phase 1 automatic purge OFF
- raw trades／candles／Flow／Hook retentionを変更しない

GO-5に含まれない:

- Phase 1 source implementation
- production schema mutation
- archive／purge job有効化
- git commit／push

上記はGO-6の明示承認まで開始しない。

## 開始状態

```text
branch: feature/footprint-dom-tape
branch starting SHA: e6c0724e1297a8844c1edd75f5201d397a3232fc
HEAD: 92ee4eff823ba31e84f7fc0af197d39b877ec236
```

Phase 0Bの明示除外差分とartifactは保持し、今回のstage対象にしない。

## 完了済み

- V2.1 sizing要件確認
- production sourceをread-onlyで扱う方針確定
- production DuckDBは稼働プロセスのlockによりread-only接続不可と確認
- production Parquetから固定trade snapshotを隔離作成
  - 4,212,954 trades
  - 2026-07-23 18:23:42.595 UTC〜2026-07-28 08:17:33.939 UTC
  - trade_id重複0、無効price／quantity／side 0
- sample品質監査
  - wall-clock期間6,595分に対しactive minute 3,634本（55.10%）
  - 最長連続区間502分のため、連続24時間sampleは未達
  - 低変動・高変動の完全1時間区間は双方あり
- 1分足price levels分布
  - 599,563 level rows／3,634 active bars
  - min 2、median 124、p95 467、p99 758.02、max 2,592
  - 平均164.99 levels/bar
- storage artifact作成・整合性確認
  - normalized logical key重複0
  - nested level count差異0
  - 元trade 4,212,954件を両方式で復元
  - normalized DuckDB 7,876,608 bytes
  - normalized + unique index DuckDB 40,644,608 bytes
  - nested + bar key index DuckDB 7,090,176 bytes
  - normalized ZSTD Parquet 4,067,060 bytes
  - nested ZSTD Parquet 4,773,286 bytes
  - Parquet read-backの件数・期間一致
- query benchmark（各warm 50回）
  - normalized no index latest 40: median 16.38 ms／p95 21.26 ms
  - normalized no index previous 40: median 18.64 ms／p95 31.47 ms
  - normalized 300-bar summary: median 5.91 ms
  - nested latest／previous 40: median 31.11／32.18 ms
  - nested 300-bar summary: median 1.91 ms
  - 4-column ART indexは各range planで使用されず、latest／previous 40を改善しなかった
- write batch benchmark
  - normalized no index 1,000 levels: median 7.78 ms、82,764 rows/s
  - normalized unique index 1,000 levels: median 10.96 ms、78,469 rows/s
  - nested indexed 10 bars: median 116.41 ms、64.5 bars/s
- live baseline queueをread-only APIで確認
  - processed trades 1,041,106
  - pending 0
  - high watermark 798／capacity 10,000
- archive verification sample
  - normalized rows／logical keys 599,563／599,563
  - min／max price 63,050.8／65,700.2
  - buy／sell volume、bar_time範囲、SHA-256、read-backを確認
- Phase 0C sizing report作成
- 最終提案確定
  - normalized levels + small bar manifest
  - 4列level ARTは初期作成しない
  - Hot DuckDB 30日
  - UTC日次ZSTD Parquet無期限
  - Phase 1 automatic purge OFF
- 最終検証
  - report／checkpointの行末空白なし
  - production `/api/health` GREEN
  - storage queue pending 0、high watermark 798／10,000
  - benchmark artifactは隔離directory内のみ
  - production source code変更なし
  - V2／V2.1／report／checkpointのGO-5状態が一致
  - tracked文書`git diff --check` PASS、対象文書の行末空白なし

## 未完了

- Phase 0C承認範囲内の未完了なし
- GO-5 schema／retention承認済み
- GO-6 Phase 1 source implementationは未承認

## 今回変更file

- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_PHASE0C_STORAGE_SIZING_CHECKPOINT_20260728.md`
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_PHASE0C_STORAGE_SIZING_REPORT_20260728.md`
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_FUSION_IMPLEMENTATION_INSTRUCTION_V2_20260728.md`
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_FUSION_PREIMPLEMENTATION_AMENDMENT_V2_1_20260728.md`
- 隔離benchmark artifact（git対象外予定）:
  - `Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/source_trades.duckdb`
  - 同directory内のnormalized／indexed／nested DuckDBとZSTD Parquet

## blockerの限定範囲

- production DuckDBは稼働中プロセスのlockにより直接監査不可。ただし固定Parquet
  snapshotでstorage sizingは継続できるため、blockerはDB固有metadataの確認に限定。
- sourceは約109.9時間を跨ぐが欠損があり、最長連続区間は502分。V2.1が求める
  連続24時間sampleは未達。3,634 active barsの分布を1,440 bars/dayへ正規化し、
  連続性不足を最終報告で明示する。
- 現行production writerのqueue high-water markは798／10,000まで実測したが、
  Footprint追加後の増分は未実装のため実測不能。Phase 1にFootprint別counterを入れる。

## 次の再開位置

1. sourceは変更せず、GO-6 Phase 1実装の明示承認を待つ
2. GO-6受領後はPhase 1開始前checkpointから再開する
