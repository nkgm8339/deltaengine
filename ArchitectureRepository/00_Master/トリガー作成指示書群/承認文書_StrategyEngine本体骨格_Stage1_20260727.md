# 承認文書：Strategy Engine 本体骨格（代表1型限定）Stage 1 設計提案

作成日: 2026-07-27 JST
対象: Claude Code Stage 1 報告（Strategy Engine 本体骨格 代表1型限定）
根拠指示書: `指示書_StrategyEngine本体骨格_代表1型_20260727.md`

---

## 判定：Stage 1 承認。Stage 2（実装＋試験実行）へ進んでよい。

正本（判定契約1〜9 / routing policy / binding policy / CSV群 / 拒否試験対照表 / src/strategy_contract/）との齟齬は0件。指示書の `replay/` 記述不正確の指摘は正確であり、本作業でいずれの既存リプレイ基盤にも接続しない方針は妥当。

## 質問への回答

### 質問1: C-1 配置（`src/strategy_engine/` 新規パッケージ）

**承認する。** 以下の構成で着手すること。

- `src/strategy_engine/`（`__init__.py` / `events.py` / `predicate_eval.py` / `engine.py` / `variant_runtime.py`）
- `tests/strategy_engine/`（`__init__.py` / `test_engine_representative_path.py` / `test_predicate_evaluator_stub.py`）
- `src/strategy_contract/` の既存ファイルは変更しない（再利用のみ）

### 質問2: C-2 enforcer関係（enforcerを内部で呼ぶ合成方式）

**承認する。** 推奨案を採用。

- ContractEnforcer を遷移契約の唯一の正として維持し、Engineは遷移判定を再実装しない
- Engineが追加する責務は ① Predicate Evaluator（述語評価）と ② イベント投入層 の2つのみ
- イベント流入 → PredicateEvaluator → Engineが遷移attemptを構築 → ContractEnforcer.submit() → StepResult/handoff
- 判定契約1〜9と拒否試験27件が構造的にEngineへ自動継承されること

### 質問3: D 較正フラグ注入（CalibrationBook コンストラクタ注入）

**承認する。**

- 通常動作時: CalibrationBook 空 → UNVALIDATED → enforcer が UNCALIBRATED_EDGE 拒否（契約R7-a整合）
- テスト時: 較正済み CalibrationBook をコンストラクタへ注入 → 述語評価ロジック自体を検証
- 閾値ハードコード禁止。較正値確定後は CalibrationBook の差し替えのみで有効化可能な構造を維持すること
- 既存 ThresholdBook パターンとの一貫性を維持すること

### 質問4: E イベントIF（pull型 EventSource protocol、本段階は定義のみ）

**承認する。**

- EngineInputEvent: source非依存。イベント源（Live/Replay）を区別する情報を持たない
- EventSource protocol: pull型（Iterator）を採用。決定論再生との相性を優先
- 本段階ではprotocol定義のみ。Live/Replay の EventSource 実装は行わない
- 試験は合成 EventSource から投入

### 質問5: B predicate一覧・F テスト一覧

**承認する。** 過不足なし。

predicate 9種（LOCATION_CONTEXT / FLOW_PRICE_DIVERGENCE / ABSORPTION_STATE / BREAK_ATTEMPT / WALL_STATE / OPEN_INTEREST_CHANGE / COMPOSITE_INVALIDATION / ENGINE_TERMINAL / ENGINE_EXPIRY）を対象とする。

テスト T1〜T7 を実施すること。特にT6（拒否試験27件回帰）とT7（既存516件回帰）は必須。

## Stage 2 の完了条件

1. T1〜T5 の全件合格
2. T6: Replay契約拒否試験 27 passed, 1 skipped が維持されること
3. T7: 既存テスト 516件が全件合格（回帰0件）
4. checkpoint更新
5. コミット作成（push はお館様の指示があるまで行わない）

## 制約の再確認（Stage 2 でも継続）

- runtime有効化0・発注権限0を維持
- Live pipeline・Hook runtime・発注系への接続禁止
- 代表1型のみ。他variantの個別実装は範囲外
- 完成済みFlow Price Response・3段チャート・8パターン・OI・UI・既存runtime・raw data変更禁止
- 収録中のHook Stage 2A/2B観測基盤の停止・変更禁止
- 正本CSV/ポリシー文書は読み取りのみ
- 閾値・comparator・window較正は範囲外（スタブのみ）
- `src/strategy_contract/` の既存コード・既存テストを壊さない
- Stage 2 完了時点で停止し、完了報告を提出してお館様の確認を待つこと
