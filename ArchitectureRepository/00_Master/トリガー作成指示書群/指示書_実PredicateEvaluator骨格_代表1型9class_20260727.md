# Claude Code 指示書：実 Predicate Evaluator 骨格の実装（代表1型 9 class）

作成日: 2026-07-27 JST
対象プロジェクト: `Delta_Engine_Pro4web`（branch: ui-refresh-v2）
前提: Strategy Engine本体骨格 完了済み（コミット 28d5229 push済み、554 passed, 1 skipped）

## ■ 必読（着手前）

1. `ArchitectureRepository/00_Master/PROJECT_MEMORY.md` 全文
2. `ArchitectureRepository/00_Master/トリガー作成指示書群/ORDER_FLOW_STATE_CONDITION_BINDING_POLICY_V0_1_20260727.md`（判定契約1〜9）
3. 同 `ORDER_FLOW_HOOK_VARIANT_ROUTING_POLICY_V0_1_20260727.md`（route role・context-only制約）
4. 機械可読正本CSV群（predicate class registry / binding / routing）
5. `src/strategy_engine/` 全ファイル（Engine本体骨格＋StubPredicateEvaluator＋CalibrationBook）
6. `src/strategy_contract/` 全ファイル（contract enforcer）
7. 既存の検出器実装を確認すること（下記§背景を参照）

**前提条件**: 本指示書の内容と上記正本の間に齟齬を見つけた場合、実装せず齟齬内容を報告して停止すること。正本が優先である。

## ■ 背景

Strategy Engine本体骨格が代表1型で完動した。現在はStubPredicateEvaluatorが全predicateに対しCalibrationBook空→UNVALIDATED拒否を返すため、Engineは較正済みフラグ注入なしでは一切advanceしない。

次段階として、StubPredicateEvaluatorを**実際の市場データを評価するロジックを持つ実evaluator**に置き換える。ただし閾値はDOM収録完了（7/29）後の較正ツール実行まで確定しないため、ロジック骨格のみ実装し、閾値はCalibrationBook注入で外部から供給する構造を維持する。

既存の5指標独立化で実装済みの検出器（CVD divergence detector, absorption detector, imbalance detector等）が存在する。これらの検出器出力とpredicate evaluatorの関係を整理することが本作業の重要な設計判断となる。

## ■ 対象predicate class（9種）

代表1型 VAR-CVD-BEAR-ABSFAIL-BIDBREAK-OIUNWIND-SHORT-VISIBLE_BOOK_WALL-001 が使用する全predicate class:

### 市場predicate（7種、較正依存）
1. **LOCATION_CONTEXT** — E00 arm。可視板壁の存在判定
2. **FLOW_PRICE_DIVERGENCE** — E01。CVD divergence（フローと価格の乖離）
3. **ABSORPTION_STATE** — E02。吸収の成功/失敗状態
4. **BREAK_ATTEMPT** — E03。板壁への攻撃試行
5. **WALL_STATE** — E03（observation）/ E98（invalidation）。板壁の状態変化
6. **OPEN_INTEREST_CHANGE** — E04（observation、hard source=OI）/ E98（invalidation）。OI変化
7. **COMPOSITE_INVALIDATION** — E98。複合反証条件

### Lifecycle predicate（2種、較正非依存）
8. **ENGINE_TERMINAL** — E90。全advance完了時のengine内部判定
9. **ENGINE_EXPIRY** — E99。monotonic deadline超過のengine内部判定

Lifecycle predicateは前回の報告で構造的にCALIBRATED扱いが確認済み。本作業の対象は主に市場predicate 7種のロジック骨格。

## ■ 実装するもの

### 1. 実 Predicate Evaluator

StubPredicateEvaluatorと同じPredicateEvaluator protocolを実装する実evaluator。各predicate classに対し、市場データ（EngineInputEvent.payload）から述語の成立/不成立を評価するロジックを持つ。

設計提案で以下を報告すること:
- **既存検出器との関係**: 5指標独立化で実装済みの検出器（CVD divergence, absorption, imbalance等）の出力を、evaluatorがどう受け取るか。選択肢として考えられるのは:
  - A: 検出器の出力をEngineInputEventのpayloadに載せ、evaluatorはpayloadから読む（疎結合）
  - B: evaluatorが検出器を直接参照する（密結合）
  - C: 別の方式
  - 推奨を根拠付きで報告すること。ただし本作業でLive pipelineへの接続は行わない
- **ファイル構成**: predicate_eval.py内に全class分を書くか、class別にファイル分割するか
- **較正依存部分の分離**: 閾値を参照する箇所がCalibrationBook経由のみであることを構造で保証する方法

### 2. CalibrationBook の拡張（必要な場合）

既存CalibrationBookの構造が7種の市場predicateの較正パラメータを保持するのに十分か確認し、不足があれば拡張すること。較正パラメータの種類（閾値、ウィンドウ幅、パーセンタイル等）はpredicate classごとに異なる可能性がある。

### 3. テスト

以下を最低限含むこと:
- 各市場predicate class（7種）の評価ロジック試験: 較正済みCalibrationBookを注入し、成立/不成立の境界条件を合成データで検証
- CalibrationBook空（既定）の場合にUNVALIDATED拒否が維持されること
- Engine経由の統合試験: 実evaluatorを組み込んだEngineで代表1型の全経路（arm→advance×4→terminal）が動くこと（較正済み注入時）
- **回帰: Strategy Engine骨格試験 11件が全PASS維持**
- **回帰: Replay契約拒否試験 27 passed, 1 skipped が維持**
- **回帰: 既存テスト 516件が全件合格**

## ■ 制約

- **runtime有効化0・発注権限0を維持**。Live pipeline・Hook runtime・発注系への接続禁止
- 既存検出器（CVD divergence, absorption, imbalance等）のコードを変更しない
- `src/strategy_contract/` の既存コード・既存テストを変更しない
- `src/strategy_engine/` の既存テスト（11件）を壊さない
- 完成済みFlow Price Response・3段チャート・8パターン・OI・UI・既存runtime・raw data変更禁止
- 収録中のHook Stage 2A/2B観測基盤の停止・変更禁止
- 正本CSV/ポリシー文書は読み取りのみ
- 閾値の具体値をハードコードしない。すべてCalibrationBook経由
- 閾値・comparator・windowの較正値確定は本作業の範囲外（ロジック骨格のみ）

## ■ 進め方（各段階でお館様の確認を取る）

1. **設計提案** — 必読文書の確認結果（齟齬の有無）、既存検出器との関係の推奨案、ファイル構成、CalibrationBook拡張要否、テスト一覧案を報告 → お館様OK後に着手
2. **実装＋試験実行** — 全テスト合格を確認（新規＋既存回帰）
3. **完了報告** — テスト結果、回帰結果、checkpoint更新、コミット（pushはお館様の指示があるまで行わない）

一気に全部やらない。段階ごとに止まって報告すること。
