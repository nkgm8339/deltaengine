# Strategy Engine 実装 引き継ぎ書（Claude Code → Codex）

作成日: 2026-07-27 JST
作成者: Claude Code（本4工程の実装担当）
対象: Codex（以後の実装担当）
運用: 実装=Codex / 検証・指示書・承認=Claude web / 最終決定=お館様

本書はCodexが新セッションの最初に読む「再開位置の正本」である。すべての主張は
ファイルパス・コミットハッシュ・テスト実測値に基づく。推測は含まない。

---

## §1 現在地（事実）

- ブランチ: `ui-refresh-v2`
- 最新コミット: `e001031`（push済み。`cf00f2e..e001031 ui-refresh-v2 -> ui-refresh-v2`）
- リポジトリ: `https://github.com/nkgm8339/deltaengine.git`

### テスト実測値

実行コマンド（実行ディレクトリ = `Delta_Engine_Pro4web/`）:

```
python -m pytest -q -p no:cacheprovider
```

結果: **574 passed, 1 skipped**。内訳（各suite個別実測）:

| suite | 実測 |
|---|---|
| 既存（strategy_contract/strategy_engine を除く） | 516 passed |
| `tests/strategy_contract/` | 27 passed, 1 skipped |
| `tests/strategy_engine/` | 31 passed |

- skip 1件は `tests/strategy_contract/test_replay_contract_rejection.py::test_R2b_cross_instance_reuse_is_undefined_by_canon`（UNDEFINED_BY_CANON、§5参照）。

### 収録状況（停止・変更禁止）

- Hook Stage 2A/2B の append-only 収録が稼働中。**停止・変更・truncate 禁止**。
- full（DOM）current effective deadline: **2026-07-29 13:34:16 JST**
- liquidation current effective deadline: **2026-08-09 13:34:16 JST**
- 出典: `ORDER_FLOW_STRATEGY_ENGINE_SKELETON_CHECKPOINT` 系および PROJECT_MEMORY「Hook Stage 2C着手承認と2C-1待機境界」節。
- 全 threshold は `UNCALIBRATED`、HookEvent 発火 0、Playbook は `OBSERVE`、`execution_enabled: false`。

---

## §2 完了済み4工程の要約

### 工程1: Replay契約 拒否試験（contract enforcer 参照実装）

- 目的: Strategy Engine 実装前に、判定契約1〜9に違反する入力・遷移・発注経路を拒否するテストを固定（後続実装が契約を破れば即落ちる壁）。
- コミット: `aa1f43e`
- 成果物:
  - `Delta_Engine_Pro4web/src/strategy_contract/__init__.py`
  - `Delta_Engine_Pro4web/src/strategy_contract/rejection_codes.py`
  - `Delta_Engine_Pro4web/src/strategy_contract/events.py`
  - `Delta_Engine_Pro4web/src/strategy_contract/variant_contract.py`
  - `Delta_Engine_Pro4web/src/strategy_contract/enforcer.py`
  - `Delta_Engine_Pro4web/src/strategy_contract/replay_driver.py`
  - `Delta_Engine_Pro4web/tests/strategy_contract/test_replay_contract_rejection.py`（R1〜R8）
  - `Delta_Engine_Pro4web/tests/strategy_contract/test_replay_contract_golden_path.py`（GP）
  - `Delta_Engine_Pro4web/tests/strategy_contract/_helpers.py`
- checkpoint / 対照表:
  - `ORDER_FLOW_REPLAY_CONTRACT_REJECTION_CHECKPOINT_20260727.md`
  - `ORDER_FLOW_REPLAY_CONTRACT_REJECTION_MATRIX_V0_1_20260727.md`（試験名×根拠条項×結果）
- 関連: 正本CSV群を `e67a2c1` で追跡開始、PROJECT_MEMORY を `0b6a263` で追記、gitignore を `8ee8af9`。

### 工程2: Strategy Engine 本体骨格（代表1型限定）

- 目的: 代表1型 variant を arm→advance×4→terminal で端から端まで動かす最小骨格。enforcer を遷移ゲートとして内部で呼ぶ合成方式。
- コミット: `28d5229`
- 成果物:
  - `Delta_Engine_Pro4web/src/strategy_engine/__init__.py`
  - `Delta_Engine_Pro4web/src/strategy_engine/events.py`（EngineInputEvent / EventSource protocol / PredicateObservation）
  - `Delta_Engine_Pro4web/src/strategy_engine/predicate_eval.py`（PredicateEvaluator protocol / StubPredicateEvaluator / CalibrationBook）
  - `Delta_Engine_Pro4web/src/strategy_engine/variant_runtime.py`（代表1型を正本FSM+bindingから読み取り専用ロード）
  - `Delta_Engine_Pro4web/src/strategy_engine/engine.py`（StrategyEngine）
  - `Delta_Engine_Pro4web/tests/strategy_engine/test_engine_representative_path.py`
  - `Delta_Engine_Pro4web/tests/strategy_engine/test_predicate_evaluator_stub.py`
  - `Delta_Engine_Pro4web/tests/strategy_engine/_helpers.py`
- checkpoint: `ORDER_FLOW_STRATEGY_ENGINE_SKELETON_CHECKPOINT_20260727.md`

### 工程3: 実 Predicate Evaluator 骨格（代表1型 9 class）

- 目的: Stub を、condition snapshot から calibrated comparator で述語を評価する実 evaluator へ拡張。閾値は CalibrationBook 注入のみ。
- コミット: `cf00f2e`
- 成果物:
  - 拡張: `src/strategy_engine/events.py`（PredicateObservation に `conditions` 追加）
  - 拡張: `src/strategy_engine/predicate_eval.py`（ConditionAtom / PredicateCalibration / CalibrationBook.calibration()・from_calibrations()）
  - 新規: `src/strategy_engine/predicate_spec.py`（class registry から PredicateClassSpec を読み取り専用ロード）
  - 新規: `src/strategy_engine/real_predicate_eval.py`（RealPredicateEvaluator）
  - 微修正: `src/strategy_engine/engine.py`（STAY条件を「較正済みかつ不成立」に限定）
  - 拡張: `tests/strategy_engine/_helpers.py`（代表1型較正・condition snapshot fixture）
  - 新規: `tests/strategy_engine/test_real_predicate_evaluator.py`（P1〜P8）
  - 新規: `tests/strategy_engine/test_engine_real_evaluator_path.py`（P9〜P10）
- checkpoint: `ORDER_FLOW_REAL_PREDICATE_EVALUATOR_CHECKPOINT_20260727.md`

### 工程4: Ingestion Adapter 骨格（代表1型 condition key）

- 目的: 正規化 MarketStateSnapshot → Tier A condition snapshot の写像層。「CD-G* condition key を生成するコードが存在しない」gap を閉じる。
- コミット: `e001031`
- 成果物:
  - `Delta_Engine_Pro4web/src/strategy_engine/ingestion/__init__.py`
  - `Delta_Engine_Pro4web/src/strategy_engine/ingestion/market_state.py`（MarketStateSnapshot / TimeSample / BookLevel）
  - `Delta_Engine_Pro4web/src/strategy_engine/ingestion/condition_adapter.py`（IngestionAdapter）
  - `Delta_Engine_Pro4web/tests/strategy_engine/test_ingestion_adapter.py`（I1〜I6）
- checkpoint: `ORDER_FLOW_INGESTION_ADAPTER_CHECKPOINT_20260727.md`

---

## §3 アーキテクチャ関係図

```
[正本CSV群]  ORDER_FLOW_*_V0_1_20260727.csv（FSM / binding / routing / predicate class registry）
   │ 読み取り専用ロード
   ▼
src/strategy_contract/                （契約 oracle。拒否試験の参照実装。単一の正）
   ├ variant_contract.VariantContract   FSM edge構造を正本から読取専用ロード
   ├ events.ContractEvent               遷移attempt（source非依存の合成イベント）
   ├ enforcer.ContractEnforcer          受理/拒否判定のみ。TERMINAL→OrderReadyHandoff（発注APIなし）
   └ rejection_codes.RejectReason       各codeに根拠条項（判定契約N / policy§ / routing§）

src/strategy_engine/                  （本体骨格。enforcer を内部で呼ぶ合成方式）
   ├ variant_runtime.RepresentativeVariant  contract + edgeごとpredicate_id
   ├ predicate_eval                      CalibrationBook（fail-closed）/ ConditionAtom / PredicateCalibration
   │                                     StubPredicateEvaluator（scenario駆動、既存骨格テスト用）
   ├ real_predicate_eval.RealPredicateEvaluator  condition snapshot → verdict（OR route + veto）
   ├ predicate_spec                      class registry から候補key/反証key/selector
   └ engine.StrategyEngine               遷移判定を再実装しない（enforcerが唯一の正）

src/strategy_engine/ingestion/        （condition snapshot 供給層）
   ├ market_state.MarketStateSnapshot    正規化read-onlyビュー（CVD/book/OI/price/pre_aggregated）
   └ condition_adapter.IngestionAdapter  MarketStateSnapshot → Tier A condition dict（fail-closed）

データフロー（代表1型）:

  MarketStateSnapshot
    → IngestionAdapter.to_conditions()            [Tier A condition_key → Decimal]
    → PredicateObservation.conditions
    → RealPredicateEvaluator.evaluate()           [CalibrationBook 参照で calibrated comparator 適用]
    → StrategyEngine.on_event()                   [holds/calibration/hard_source で ContractEvent 構築]
    → ContractEnforcer.submit()                   [判定契約1〜9 の受理/拒否 = 唯一の正]
    → StepResult（accept/reject reason） / OrderReadyHandoff（TERMINAL時 LONG_READY/SHORT_READY）
```

**不変条件**: Engine は accept/reject を自前判定しない。すべて ContractEnforcer に委譲するため、
判定契約1〜9 と拒否試験 R1〜R8 は Engine へ構造的に自動継承される。TERMINAL は gate 行き
handoff のみで、発注 API はどこにも存在しない（runtime有効化0・発注権限0）。

---

## §4 設計判断の記録（なぜそうしたか）

1. **enforcer 合成方式**（Engine が enforcer を内部で呼ぶ）
   - 理由: 遷移契約を二重実装すると乖離リスクが生じる。enforcer を唯一の正とし Engine は
     predicate 評価とイベント投入だけを足すことで、判定契約1〜9・R1〜R8 が Engine へ自動継承される。
   - 根拠: `engine.py` は `ContractEnforcer.submit()` に委譲し、受理/拒否ロジックを持たない。

2. **condition snapshot 疎結合**（Ingestion Adapter が payload に snapshot を載せる）
   - 理由: 正本 condition key（cvd_change_5s 等）を生成するコードが**存在しない**（grep 0件、
     既存検出器 DivergenceEvent / AbsorptionResult は別構造を出力）。検出器直参照は不可。
   - 効果: 既存検出器を変更せず、Live 非接続で、合成 snapshot により今すぐ試験可能。

3. **Tier A / Tier B の2層構造**
   - Tier A = 単一ストリームから窓計算で導出できる数値（CVD/wall/OI/progress）。
   - Tier B = STRATEGY_SPECIFIC 合成FLAG（divergence_active 等、Tier A＋location＋price response の合成）。
   - 事実: 代表1型の9 class すべてが Tier A 候補 route を最低1つ持つ（class registry の
     candidate_keys で確認）。よって Tier A のみで arm→advance×4→terminal を通せる（I6 で実証）。

4. **CalibrationBook 注入方式**
   - 理由: 閾値ハードコード禁止。既存 `src/orderflow/hooks/config.py` の ThresholdBook と同じ
     fail-closed 様式（既定 UNCALIBRATED、空 book では何も発火しない）に合わせ一貫性を確保。
   - 効果: 較正値確定（収録完了後）は CalibrationBook 差し替えのみで有効化可能。

5. **lifecycle predicate が構造的に CALIBRATED**（ENGINE_TERMINAL / ENGINE_EXPIRY）
   - 理由: これらは engine 内部イベントで市場閾値に依存しない（class registry の
     implementation_status = ENGINE_NATIVE、selector = ENGINE_STATE / ENGINE_TIME）。
   - 安全性: 通常動作では arm/advance が未較正で進めないため lifecycle には到達せず、
     runtime firing は 0 を維持する。

---

## §5 documented gap 一覧（全件）

1. **Tier B 合成FLAG 未生成**（flow_price_divergence_active / bid・ask_absorption_like_active /
   upside・downside_breakout_attempt・failure・follow_through / bid・ask_passive_defense_holding・failed）
   - 将来「composite synthesis 層」が必要（Tier A＋location＋price response の合成）。
   - 代表1型の**反証route**（downside_breakout_follow_through / bid_passive_defense_failed /
     downside_breakout_failure）は Tier B のため現状 snapshot に現れず、evaluator は fail-closed で
     「反証なし（veto=False）」と扱う。**runtime有効化0の現段階では安全**。実データで反証を効かせるには
     composite synthesis 層が前提。
2. **pre-aggregated 本計算 未実装**（bid・ask_refresh_count_1s / pull_ratio_1s /
   upward・downward_progress_ticks_1s / buy・sell_no_progress_ratio_1s）
   - 現状は MarketStateSnapshot に事前集計値として渡し adapter は素通し。DEPTHイベント計数・
     price×tape 秒次計数の本計算は、snapshot producer（replay/detector 統合）側の将来実装。
3. **price_oi_joint_state_5m の ENUM 数値符号化が便宜的**
   - `condition_adapter.JOINT_STATE_CODES`（FLAT=0 / UP_UP=1 / UP_DOWN=2 / DOWN_UP=3 / DOWN_DOWN=4）。
     正本 ENUM 定義との正式な対応確定が将来必要（正本 ENUM は未変更）。
4. **Ingestion Adapter が Live/Replay に未接続**
   - `EventSource` は protocol 定義のみ。MarketStateSnapshot を replay/detector から埋める
     producer と Live/Replay の EventSource 実装は将来工程。
5. **【未定義-1】cross-instance の source_event_id 再利用が正本未定義**
   - 判定契約3は同一 Observation Instance 内の再利用のみ禁止。別instanceにまたがる再利用は
     正本に定義なし。拒否試験では `UNDEFINED_BY_CANON` として明示スキップ（勝手に仕様化しない）。
     正本側の将来更新事項。
6. **他364 variant が未実装**
   - 実装済みは代表1型 `VAR-CVD-BEAR-ABSFAIL-BIDBREAK-OIUNWIND-SHORT-VISIBLE_BOOK_WALL-001` のみ。
7. **閾値・comparator・window の較正値は未確定**
   - 全 predicate/binding は `UNVALIDATED`。CalibrationBook は骨格が comparator 構造だけを持ち、
     値は未投入。較正は収録完了後の較正ツール工程。

---

## §6 次工程の候補と推奨順序

依存関係:

- **composite synthesis 層**（Tier B 生成）: Tier A（実装済み）を入力に合成。実データで反証route を
  効かせるために必要。adapter の上位に載る。
- **snapshot producer（replay 統合）**: MarketStateSnapshot を replay/detector から埋める。
  pre-aggregated 本計算（refresh/pull/progress）を含む。EventSource の実装を伴う。
- **較正ツール**: 収録完了後が本番（DOM 2026-07-29 / 清算 2026-08-09）。CalibrationBook へ閾値投入。
- **他variant一般化**: 代表1型で骨格が確立済み。横展開は adapter/評価/較正の型が固まってからが手戻り少。

推奨順序（**決定はお館様が行う。以下は根拠付きの提案にすぎない**）:

1. snapshot producer（replay 統合）— 骨格が合成 snapshot 依存のままでは実データ検証に進めない。
   pre-aggregated 本計算もここで閉じる。ただし収録・completed 判定と整合させること。
2. composite synthesis 層 — 反証route を実データで効かせ、Tier B route を有効化。
3. 較正ツール — 収録完了（7/29 DOM）後。CalibrationBook へ実測閾値を投入し UNVALIDATED を解く。
4. 他variant一般化 — 上記の型確定後。

（順序は依存関係からの提案。較正は収録完了が前提のため時間軸で後段になる点のみ確実。）

---

## §7 Codex が守るべき制約・運用ルール

1. **runtime有効化0・発注権限0の維持**。Live pipeline・Hook runtime・発注系への接続、live化は
   お館様の明示指示があるまで封印。発注 API を新設しない。
2. **完成済み機能・既存検出器・正本CSV/ポリシー・raw data・収録基盤を変更しない**。
   Flow Price Response / 3段チャート / 8パターン / OI / UI / 既存runtime は明示依頼なしに触らない。
   Hook Stage 2A/2B append-only 収録を止めない。
3. **fail-closed 運用**。齟齬・欠測・未定義を発見したら勝手に仕様を決めず、原文を引用して報告し停止する。
   正本が本文書・指示書より優先。
4. **1工程1指示書・段階停止**。Stage 1（設計提案）→ お館様OK → Stage 2（実装＋試験）→ 完了報告 →
   お館様確認。一気に進めない。
5. **push はお館様の指示があるまで行わない**。
6. **根拠なき断定禁止**。すべての主張はファイル:行番号または実測値で示す。確認済み事実・未確認事項・
   検討候補を分ける。
7. **回帰保証**。全工程で既存テスト全件 PASS を完了条件とする。現基準:
   `python -m pytest -q -p no:cacheprovider`（`Delta_Engine_Pro4web/`）で **574 passed, 1 skipped**。
   既存516 / 契約27+1skip / engine31 の内訳を維持すること。
8. **閾値ハードコード禁止**。すべて CalibrationBook 経由。

---

## 付録: checkpoint 文書一覧（トリガー作成指示書群/）

- `ORDER_FLOW_REPLAY_CONTRACT_REJECTION_CHECKPOINT_20260727.md`
- `ORDER_FLOW_REPLAY_CONTRACT_REJECTION_MATRIX_V0_1_20260727.md`
- `ORDER_FLOW_STRATEGY_ENGINE_SKELETON_CHECKPOINT_20260727.md`
- `ORDER_FLOW_REAL_PREDICATE_EVALUATOR_CHECKPOINT_20260727.md`
- `ORDER_FLOW_INGESTION_ADAPTER_CHECKPOINT_20260727.md`
- 本書 `ORDER_FLOW_STRATEGY_ENGINE_HANDOVER_TO_CODEX_20260727.md`
