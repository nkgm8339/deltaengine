# Strategy Engine 本体骨格（代表1型限定）完了checkpoint

## 2026-07-27 JST Stage 2完了checkpoint

### 承認範囲

- お館様のStage 1承認書により、Strategy Engine本体の最小骨格を代表1型限定で実装する。
- contract enforcer（`src/strategy_contract/`）を遷移契約の唯一の正として内部で呼ぶ合成方式。
- runtime有効化0・発注権限0を維持。Live pipeline・Hook runtime・発注系へは接続しない。
- pushはお館様の指示があるまで行わない。

### 対象variant

`VAR-CVD-BEAR-ABSFAIL-BIDBREAK-OIUNWIND-SHORT-VISIBLE_BOOK_WALL-001`
（E00 arm → E01–E04 advance → E90 terminal / E98 invalidate / E99 expire）

### 完了済み

- 新規パッケージ `Delta_Engine_Pro4web/src/strategy_engine/` を追加。
  - `events.py`: `EngineInputEvent`（source非依存）+ `EventSource` protocol（pull型Iterator）+ `PredicateObservation`。本段階はprotocol定義のみでLive/Replay実装なし。
  - `predicate_eval.py`: `PredicateEvaluator` protocol / `StubPredicateEvaluator` / `CalibrationBook`（fail-closed、既定UNVALIDATED、閾値ハードコードなし）。
  - `variant_runtime.py`: 代表1型の契約を正本FSM+binding CSVから読み取り専用ロード（`strategy_contract.VariantContract`再利用、edgeごとのpredicate_id付与）。
  - `engine.py`: `StrategyEngine` 本体。`ingestion → PredicateEvaluator → ContractEvent構築 → ContractEnforcer.submit()` の流れ。遷移判定は再実装せずenforcerへ委譲。TERMINALは`OrderReadyHandoff`のみ返却、発注API無し。
- 試験 `Delta_Engine_Pro4web/tests/strategy_engine/` を追加（`_helpers.py` / `test_engine_representative_path.py` / `test_predicate_evaluator_stub.py`）。

### 代表1型のpredicate（正本CSVから特定）

| edge | predicate_id | class | 種別 |
|---|---|---|---|
| E00 | LOC::VISIBLE_BOOK_WALL | LOCATION_CONTEXT | 市場（arm） |
| E01 | OPR-019 | FLOW_PRICE_DIVERGENCE | 市場（advance） |
| E02 | OPR-020 | ABSORPTION_STATE | 市場（advance） |
| E03 | OPR-021 | BREAK_ATTEMPT, WALL_STATE | 市場（advance） |
| E04 | OPR-022 | OPEN_INTEREST_CHANGE | 市場（advance, OI hard source） |
| E90 | ENGINE-TERMINAL | ENGINE_TERMINAL | engine lifecycle |
| E98 | INV-005 | COMPOSITE_INVALIDATION, OPEN_INTEREST_CHANGE, WALL_STATE | 市場（invalidation） |
| E99 | ENGINE-EXPIRY | ENGINE_EXPIRY | engine lifecycle |

- calibration方針: 市場predicate（arm/advance/invalidate）はCalibrationBookで較正判定（空＝UNVALIDATED）。lifecycle（terminal/expire）は構造的にCALIBRATED。通常動作では arm/advance が未較正で進めないため、lifecycleは実データ上到達しない（runtime firing 0）。

### 変更file

- `Delta_Engine_Pro4web/src/strategy_engine/__init__.py`（新規）
- `Delta_Engine_Pro4web/src/strategy_engine/events.py`（新規）
- `Delta_Engine_Pro4web/src/strategy_engine/predicate_eval.py`（新規）
- `Delta_Engine_Pro4web/src/strategy_engine/variant_runtime.py`（新規）
- `Delta_Engine_Pro4web/src/strategy_engine/engine.py`（新規）
- `Delta_Engine_Pro4web/tests/strategy_engine/__init__.py`（新規）
- `Delta_Engine_Pro4web/tests/strategy_engine/_helpers.py`（新規）
- `Delta_Engine_Pro4web/tests/strategy_engine/test_engine_representative_path.py`（新規）
- `Delta_Engine_Pro4web/tests/strategy_engine/test_predicate_evaluator_stub.py`（新規）
- 本checkpoint（新規）

### 検証結果（Stage 2完了条件）

1. T1〜T5（Engine全経路 / invalidation / expiry / evaluator未較正 / evaluator較正済み）: **11 passed**。
2. T6 Replay契約拒否試験: **27 passed, 1 skipped** 維持。
3. T7 全体回帰: **554 passed, 1 skipped**。内訳＝既存516（全件合格・回帰0）＋contract 27/1skip＋engine 11。
- `src/strategy_contract/` の既存コード・既存テストは無変更。既存source code、config、runtime、UI、raw data、正本CSV/ポリシー文書の変更0。
- 発注権限0: EngineにもEnforcerにも発注API無し。TERMINALはSHORT_READY handoffのみ。order_intents=0。
- runtime有効化0: Live/Hook/発注系へ接続なし。EventSourceはprotocol定義のみ。

### Blockerの限定範囲

- blockerなし。
- 閾値・comparator・windowは未較正（スタブのみ）。CalibrationBook差し替えで較正値注入可能な構造。
- native MBO・OI 10秒poll・external calendarの既知制約は継続。

### 未完了（別工程・ユーザー承認前に進めない）

- 他364 variantの個別実装。
- 実predicate evaluator（market maths / comparator）の実装と閾値較正。
- EventSourceのLive/Replay実装、Live pipeline接続。
- historical replayによるvariant採用／棄却／統合、risk/execution gate較正。

### 次の再開位置

代表1型のEngine骨格が enforcer 契約を満たす形で動作した。次はユーザー承認のうえ、
実predicate evaluatorの設計、または他variantへの骨格一般化のいずれを先行するかを決める。

### push状態

- コミット作成済み。**pushはお館様の指示があるまで行わない。**
