# 実 Predicate Evaluator 骨格（代表1型 9 class）完了checkpoint

## 2026-07-27 JST Stage 2完了checkpoint

### 承認範囲

- お館様のStage 1承認書により、StubPredicateEvaluatorを実evaluator骨格へ拡張する（代表1型9 class）。
- A案（condition snapshot疎結合）。既存検出器を変更せず、Live接続もしない。ingestion adapterは範囲外。
- 閾値はCalibrationBook注入のみ。ロジック骨格のみ実装、較正値確定は範囲外。
- pushはお館様の指示があるまで行わない。

### 重要な事実（設計根拠）

- 正本の condition key（cvd_change_5s / bid_wall_concentration_top10 等）を生成するコードは現在存在しない（grep 0件）。既存検出器（DivergenceEvent / AbsorptionResult 等）は別構造を出力する。
- したがって検出器直参照（B案）は不可。A案（payloadに condition snapshot、evaluatorはそこを読む）を採用。検出器→condition key写像（ingestion adapter）は将来のLive/Replay EventSource実装時の別工程。

### 完了済み

- `src/strategy_engine/events.py` 拡張: `PredicateObservation` に `conditions: Mapping[str,Decimal]`（既定空）追加。後方互換。
- `src/strategy_engine/predicate_eval.py` 拡張: `ConditionAtom`（condition_key/operator∈{ge,gt,le,lt}/threshold, fail-closed）、`PredicateCalibration`（predicate_id/status/atoms/contradiction_atoms）追加。`CalibrationBook` に `calibration()` / `from_calibrations()` 追加。既存 `status()`/`is_calibrated()`/`all_calibrated()` は維持。
- `src/strategy_engine/predicate_spec.py` 新規: class registryから `PredicateClassSpec`（候補key/反証key/selector）を読み取り専用ロード。
- `src/strategy_engine/real_predicate_eval.py` 新規: `RealPredicateEvaluator`。calibrated時は「required atom OR route いずれか成立 かつ contradiction atom 不成立」でholds。未較正時はholds=False＋status非CALIBRATED（→enforcerがUNCALIBRATED_EDGE拒否）。閾値ハードコードなし。
- `src/strategy_engine/engine.py` 微修正: STAY条件を「較正済み かつ 不成立」に限定。未較正はattempt→enforcerがUNCALIBRATED_EDGE拒否（R7維持）。
- 試験 `tests/strategy_engine/test_real_predicate_evaluator.py`（P1〜P8）と `test_engine_real_evaluator_path.py`（P9〜P10）追加。`_helpers.py` に代表1型較正・condition snapshot fixtureを追加。

### 変更file

- `Delta_Engine_Pro4web/src/strategy_engine/events.py`（拡張）
- `Delta_Engine_Pro4web/src/strategy_engine/predicate_eval.py`（拡張）
- `Delta_Engine_Pro4web/src/strategy_engine/predicate_spec.py`（新規）
- `Delta_Engine_Pro4web/src/strategy_engine/real_predicate_eval.py`（新規）
- `Delta_Engine_Pro4web/src/strategy_engine/engine.py`（STAY条件微修正）
- `Delta_Engine_Pro4web/tests/strategy_engine/_helpers.py`（拡張）
- `Delta_Engine_Pro4web/tests/strategy_engine/test_real_predicate_evaluator.py`（新規）
- `Delta_Engine_Pro4web/tests/strategy_engine/test_engine_real_evaluator_path.py`（新規）
- 本checkpoint（新規）

### 検証結果（Stage 2完了条件）

1. P1〜P10 全件合格（新規 **12 passed**）。
2. R-a: strategy_engine骨格試験 11件維持（合計23 passed中）。
3. R-b: Replay契約拒否試験 **27 passed, 1 skipped** 維持。
4. R-c: 既存516件 全件合格（回帰0件）。
5. 全体回帰: **566 passed, 1 skipped**（＝既存516＋contract 27/1skip＋engine 23）。
- 既存検出器・`src/strategy_contract/`・完成済み機能・正本CSV/ポリシー・raw dataは無変更。
- 発注権限0（発注API無し、TERMINALはhandoffのみ、order_intents=0）、runtime有効化0（Live/Hook/発注系接続なし）。
- 閾値の具体値はテストfixtureのみに存在。production code はCalibrationBook経由でハードコードなし。

### Blockerの限定範囲

- blockerなし。
- 閾値・comparator・window較正値はDOM収録完了（7/29）後の較正ツールが供給（本骨格では注入のみ）。
- ingestion adapter（検出器→condition key写像）は未実装（範囲外・将来工程）。

### 未完了（別工程・ユーザー承認前に進めない）

- ingestion adapter設計（既存検出器出力→CD-G* condition key写像）とLive/Replay EventSource実装。
- 較正ツールによる閾値確定とCalibrationBookへの投入。
- 他364 variantへの一般化。
- historical replayによるvariant採用／棄却、risk/execution gate較正。

### 次の再開位置

代表1型の実evaluator骨格が enforcer 契約下で動作した。次はユーザー承認のうえ、
ingestion adapter設計、較正ツール、または他variant一般化のいずれを先行するかを決める。

### push状態

- コミット作成済み。**pushはお館様の指示があるまで行わない。**
