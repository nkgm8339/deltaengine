# P3-b E02 binding縮小チェックポイント

作成日: 2026-07-27 JST

## 変更対象

正本: `ArchitectureRepository/00_Master/トリガー作成指示書群/ORDER_FLOW_VARIANT_STATE_CONDITION_BINDINGS_V0_1_20260727.csv`

対象行: E02（CSV実測 line 364、0-based配列 index 363）

## Before

- candidate IDs: `CD-G16-001 CD-G16-002 CD-G09-026 CD-G09-030`
- candidate keys: `bid_absorption_like_active ask_absorption_like_active buy_no_progress_ratio_1s sell_no_progress_ratio_1s`
- contradiction IDs: `CD-G16-037 CD-G16-038`
- contradiction keys: `bid_passive_defense_failed ask_passive_defense_failed`

## After

- candidate IDs: `CD-G16-001 CD-G16-002`
- candidate keys: `bid_absorption_like_active ask_absorption_like_active`
- contradiction IDs: 空
- contradiction keys: 空

## 判断根拠

- absorption flagsは`src/strategy_engine/ingestion/snapshot_producer.py:68-83`でAbsorptionResultから直接生成される。
- ratio系・passive-defense系は突合表でNOT_AVAILABLE、欠測時omitと確認済み。
- point-in-time wall値やCVD slopeを別の意味のcompositeへ読み替えていない。
- E01/E03/E98のbindingは変更していない。

## 整合性確認

- CSV Import-Csv成功。
- E02のcandidate/contradiction値はAfterと一致。
- CSV総行数: 3336 data rows（header除く）。
- runtime有効化・発注権限: 0。
- commit/push: 未実施。

## 次の再開位置

P3-b変更後の全回帰テストを実行する。失敗があれば正本変更を追加せず、失敗箇所を報告する。
