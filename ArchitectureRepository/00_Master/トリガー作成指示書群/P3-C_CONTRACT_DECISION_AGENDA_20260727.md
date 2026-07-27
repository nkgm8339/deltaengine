# P3-c Tier A材料契約 決裁議題書

作成日: 2026-07-27 JST  
対象: `VAR-CVD-BEAR-ABSFAIL-BIDBREAK-OIUNWIND-SHORT-VISIBLE_BOOK_WALL-001`

## 1. 議題

既存検出器が計算済みの値を、Snapshot Producer/Condition Adapterから新しいTier A condition keyとして公開する際の契約を確定する。

これは単なる命名規則ではない。keyの単位・window・方向・欠測挙動が、condition成立、不成立、calibration、Replay/Live一致性を決める。

## 2. なぜ今議題化するか

P1/P2では、既存の値をsnapshotへ運ぶ骨格までを完成させた。P3-cで初めて、既存値を新しいcondition keyとして正式公開するため、意味を固定する必要が生じた。

G16正本は自然言語定義を持つが、採否・threshold・windowはvariant検証で決める契約になっている（`ORDER_FLOW_CONDITION_DICTIONARY_V0_1_20260726.md:718,729-736`）。

## 3. 契約を誤る場合の影響

誤った契約は実際の判定結果を変える。

- price差・ticks・bpsの取り違え: thresholdの意味が変わる
- 300秒・60秒の取り違え: divergence成立頻度が変わる
- point-in-time wall値をwall崩壊と解釈: failure/defense判定を誤る
- stale OIを有効値として使用: E98 invalidationを誤る
- Live/Replayでwindowやresetが違う: 再現性が失われる

現時点はruntime有効化0・発注権限0のため即時の発注リスクはないが、契約を曖昧にしたまま較正すると後続工程全体が無効になる。

## 4. 決裁項目

### D5: Price response Tier A

決める項目:

- key名
- 値の単位（price / ticks / bps）
- 対象window（FlowResponseSnapshotのどの`window_sec`か）
- 符号方向
- 欠測・window未完成時はomit

実在素材: `FlowResponseSnapshot.price_change`等（`src/orderflow/flow_price_response.py:40-61`）。現行Producerはprice sampleを保持するが、新Tier A keyは未生成（`src/strategy_engine/ingestion/snapshot_producer.py:59-66,214-219`）。

### D6: Wall差分 Tier A

決める項目:

- bid/ask concentration・distanceのどの差分を公開するか
- 比較windowとbaseline
- 増減の符号方向
- depth gap・resync時の履歴reset
- freshnessと欠測時omit

現行Adapterはpoint-in-time値のみ生成（`src/strategy_engine/ingestion/condition_adapter.py:65-87`）。履歴差分は未実装。

### D7: OI供給契約

決める項目:

- OI入力イベントの型と供給点
- event/source timestamp
- 5分base sampleの保持方法
- stale/freshness判定
- 欠測時omit

`MarketStateSnapshot.oi_samples`は存在するが（`src/strategy_engine/ingestion/market_state.py:56-68`）、P2 Producer/pipelineは供給していない。Adapterはsampleがある場合のみOI keyを出力する（`condition_adapter.py:91-111`）。

### D8: G16 composite式

D5〜D7確定後に決める。

- Tier A材料のAND/OR式
- side解決
- thresholdはCalibrationBookから供給
- 未較正・欠測時はkeyを出力しない

## 5. 推奨方針

- D5〜D7は、まずTier Aの観測値を定義し、composite FLAGのthreshold判定は後段に分離する。
- 単位は既存Adapterの単位と一致させる。既存keyを別単位へ無言変換しない。
- window未完成、depth gap、OI staleはすべてomit（fail-closed）。
- D5〜D7の承認前にP3-c source実装・正本追記を開始しない。
- `production_status`列追加案は、正本schema変更として別議題にする。

## 6. 現在の状態

- P3-a: 完了、581 passed / 1 skipped
- P3-b E02: 完了、581 passed / 1 skipped
- P3-c Stage 1: 調査報告済み、契約未定義のため実装停止
- source/runtime/raw data/収録基盤: P3-cでは未変更
- commit/push: 未実施

## 7. 決裁後の実装順

1. D5〜D7承認
2. Tier A契約を正本へ追記
3. Snapshot Producer API追加
4. pipeline Live/Replay供給
5. Condition Adapter/MarketState統合
6. G16 composite式追記
7. mock試験・実データ形式試験・全回帰
8. CalibrationBook較正後にReplay検証
