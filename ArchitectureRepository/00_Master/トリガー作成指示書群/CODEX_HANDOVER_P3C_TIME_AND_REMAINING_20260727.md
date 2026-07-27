# Codex引継ぎ書: P3-C 時刻契約と残課題

作成日: 2026-07-27 JST
作成者: Codex
状態: 実装中断・次担当へ引継ぎ

## 1. 最重要事項

本書は現状報告であり、完了可否・保留可否・仕様採否を決定する文書ではない。最終判断者はお館様。次担当は、決裁前に正本やbindingを独断で変更しないこと。

## 2. 今回実施済み

### 時刻契約

仕様書:
`ENGINE_TIME_SOURCE_TIME_CONTRACT_V0_1_20260727.md`

契約案として以下を記録し、実装へ反映済み:

- `MarketStateSnapshot.engine_time_ns`: monotonic engine clock
- `MarketStateSnapshot.source_time_ns`: UTC epoch nanoseconds
- Replay: 最初の受理source eventを原点にした経過ns
- Live: `time.monotonic_ns()`
- Adapterの窓計算: source_time_ns優先、旧fixtureのみengine_time_nsへfallback

### コード変更

- `Delta_Engine_Pro4web/src/pipeline.py`
- `Delta_Engine_Pro4web/src/strategy_engine/ingestion/market_state.py`
- `Delta_Engine_Pro4web/src/strategy_engine/ingestion/snapshot_producer.py`
- `Delta_Engine_Pro4web/src/strategy_engine/ingestion/condition_adapter.py`

### 衝突処理

- `trade_delta_*`の二重書込み: producer側で既存値を保護
- pre_aggregatedの既存adapter出力上書き: `setdefault`で保護

## 3. 検証結果

- 対象テスト: 43 passed
- 全回帰: **583 passed, 1 skipped**
- py_compile: 対象source pass
- commit/push: 未実施

## 4. 未実装・未決裁

以下は「実装不要」と決めたものではない。G16正本の定義確認とお館様の決裁が必要な残課題。

### A: price response履歴

現状は`SnapshotProducer._flow_snapshots`がwindowごとに最新1件のみ保持するため、`_price_samples()`は履歴にならない。
根拠: `snapshot_producer.py:37,66,223-227`。

決める必要がある事項:
- 履歴保持単位
- window
- baseline
- freshness/reset
- price progressの正式key名・単位

### D: book履歴・時刻・reset

現状は最新book snapshot 1件のみ保持。
根拠: `snapshot_producer.py:39,85-105`。

決める必要がある事項:
- snapshot履歴の保持窓
- 差分baseline
- reset条件
- freshness
- refresh/pullのkey定義

### E: wall距離の意味

現状の`distance_to_nearest_*_wall`は、top10内の最大数量levelまでの距離を計算している。
根拠: `condition_adapter.py:80-83`。

正本でnearest wallの意味が確定した後、名称または計算を合わせる。無断読み替えは禁止。

## 5. 次担当の再開順序

1. `PROJECT_MEMORY.md`全文を読む。
2. 本引継ぎ書、時刻契約仕様書、P3-C gap registerを読む。
3. G16正本の該当箇所を全文確認する。
4. A/D/Eの各項目について、正本から一意に実装契約が導けるかを報告する。
5. 導けない項目は、推測実装せず、お館様へ決裁事項として提出する。
6. 導ける項目のみ、承認後に実装・テストする。
7. 回帰基準は現時点で583 passed, 1 skipped。

## 6. 禁止事項

- 未確定のG16仕様を推測して実装しない。
- 正本CSV・Condition Dictionaryを独断で変更しない。
- runtime有効化、発注権限、raw data、収録基盤を変更しない。
- commit/pushしない。

## 7. 関連ファイル

- `ENGINE_TIME_SOURCE_TIME_CONTRACT_V0_1_20260727.md`
- `ENGINE_TIME_SOURCE_TIME_CONTRACT_IMPLEMENTATION_CHECKPOINT_20260727.md`
- `P3-C_IMPLEMENTATION_GAP_REGISTER_20260727.md`
- `P3-C_CONTRACT_DECISION_AGENDA_20260727.md`

## 8. 解決追記（2026-07-27 20:46:47 JST）

本書§4のA/D/E未解決状態は、お館様の「ひとつひとつ解決しろ」という明示指示後に解消した。

- A: `PRICE_RESPONSE_HISTORY_CONTRACT_V0_1_20260727.md`
- D: `BOOK_EVENT_HISTORY_RESET_CONTRACT_V0_1_20260727.md`
- E: `WALL_DISTANCE_SEMANTICS_CONTRACT_V0_1_20260727.md`
- 詳細checkpoint: `P3-C_A_D_E_CONTRACT_AUDIT_CHECKPOINT_20260727.md`
- 全回帰: **590 passed, 1 skipped**

§5の「A/D/Eを報告して決裁待ち」は過去の再開位置であり、現在の再開位置ではない。
G16 composite、threshold較正、runtime有効化、発注権限は引き続き別工程である。
