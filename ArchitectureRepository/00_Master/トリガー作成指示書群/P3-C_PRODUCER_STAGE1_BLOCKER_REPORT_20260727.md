# P3-c Producer Stage 1 調査報告

作成日: 2026-07-27 JST
対象: 代表variantの未生成Tier A材料

## 1. 調査結果

### 1.1 Price response

`FlowResponseSnapshot`は`price_change`、`last_price`、`event_time`、`window_sec`を公開している（`Delta_Engine_Pro4web/src/orderflow/flow_price_response.py:40-61`）。300秒窓のprice response素材自体は実在する。

現行SnapshotProducerはprice samplesへ`last_price`を保存するが、price_changeをcondition keyへ変換しない（`src/strategy_engine/ingestion/snapshot_producer.py:59-66,214-219`）。既存AdapterもCVD・wall・OI・pre_aggregatedのみを出力する（`src/strategy_engine/ingestion/condition_adapter.py:36-42`）。

**未定義:** 新Tier A key名、単位、符号方向、欠測時挙動。G16の`flow_price_divergence_active`は自然言語定義のみで、閾値/window/採否式はvariant検証で決める契約（`ORDER_FLOW_CONDITION_DICTIONARY_V0_1_20260726.md:718,729-736`）。推測追加は不可。

### 1.2 Wall差分

Adapterは最新bookから`bid/ask_wall_concentration_top10`と`distance_to_nearest_*_wall`をpoint-in-timeで算出する（`src/strategy_engine/ingestion/condition_adapter.py:65-87`）。SnapshotProducerは最新book一つを保持し、履歴差分を保持しない（`src/strategy_engine/ingestion/snapshot_producer.py:85-105,113-133`）。

**未定義:** 差分key名、比較window、baseline、reset条件、depth freshness、欠測時挙動。G16のbreakout/failure/defense定義は「reference」「price progress」「補充」等の自然言語であり、一意の論理式ではない（`ORDER_FLOW_CONDITION_DICTIONARY_V0_1_20260726.md:679-708`）。既存point-in-time keyを差分keyへ読み替えない。

### 1.3 OI供給

`MarketStateSnapshot`は`oi_samples`フィールドを持つ（`src/strategy_engine/ingestion/market_state.py:56-68`）。Adapterは5分のOI sampleが存在する場合のみOI keyを出力する（`src/strategy_engine/ingestion/condition_adapter.py:91-111`）。

現行SnapshotProducerの`build_market_state()`はOI sampleを設定せず（`snapshot_producer.py:113-133`）、observe_oi APIもない。P2 pipelineにもOI sample供給点はない。

**未定義:** OI入力イベントの正規化型、timestamp承認、5分base sample保持、stale/freshness契約。既存schemaだけでは供給経路を推測できない。

## 2. Stage 1判定

P3-cの3候補はいずれも「public出力を読むだけ」で完結しない。

- price response: 素材は存在するが、Tier A key契約が未定義。
- wall差分: 履歴・window・reset契約が未定義。
- OI: 入力経路とfreshness契約が未定義。

したがって、**producer sourceの実装はここで停止**する。これはfail-closed停止であり、コード不具合ではない。

## 3. 次に必要な決定

1. price response Tier A keyの正本追加（key名・単位・window・符号）。
2. wall差分の正本追加（baseline/window/reset/freshness）。
3. OI供給契約（入力型・時刻・欠測/stale挙動）。
4. 上記Tier A契約を前提にしたG16 composite式（thresholdはCalibrationBook経由）。

## 4. 検証・変更状態

- P3-a/P3-b完了後回帰: 581 passed, 1 skipped。
- 本Stage 1でsource、正本、runtime、raw dataは変更していない。
- commit/push: 未実施。

## 5. 再開位置

上記3契約が正本へ追記された後、SnapshotProducer API・pipeline供給・テストを個別に実装する。
