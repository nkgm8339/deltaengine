# Claude Code 指示書：Strategy Engine 本体骨格の実装（代表1型限定）

作成日: 2026-07-27 JST
対象プロジェクト: `Delta_Engine_Pro4web`（branch: ui-refresh-v2）
前提: Replay契約拒否試験 完了済み（27 passed, 1 skipped、コミット aa1f43e〜0b6a263 push済み）

## ■ 必読（着手前）

1. `ArchitectureRepository/00_Master/PROJECT_MEMORY.md` 全文
2. `ArchitectureRepository/00_Master/トリガー作成指示書群/ORDER_FLOW_STATE_CONDITION_BINDING_POLICY_V0_1_20260727.md`（判定契約1〜9）
3. 同 `ORDER_FLOW_HOOK_VARIANT_ROUTING_POLICY_V0_1_20260727.md`（route role・context-only制約）
4. 同 `ORDER_FLOW_STRATEGY_CONDITION_SUBSETS_CHECKPOINT_20260727.md`（Codex最終checkpoint）
5. 同 `ORDER_FLOW_REPLAY_CONTRACT_REJECTION_MATRIX_V0_1_20260727.md`（拒否試験対照表）
6. 機械可読正本CSV群（FSM・binding・routing・predicate registry）
7. `src/strategy_contract/` 全ファイル（Replay契約拒否試験で作成した contract enforcer 骨格）

**前提条件**: 本指示書の内容と上記正本の間に齟齬を見つけた場合、実装せず齟齬内容を報告して停止すること。正本が優先である。

## ■ 背景

Replay契約拒否試験（27件）が完了し、判定契約1〜9に違反する入力・遷移・発注経路を拒否するテストが固定された。この壁がある状態で、Strategy Engine本体の骨格実装に着手する。

ただし365 variant全件を一度に実装するのではなく、**代表1型のみ**を端から端まで動かすことに限定する。

## ■ 対象variant

`VAR-CVD-BEAR-ABSFAIL-BIDBREAK-OIUNWIND-SHORT-VISIBLE_BOOK_WALL-001`

Replay契約拒否試験のゴールデンパス試験で使用済みのvariant。正本CSV上の全edge（E00 arm → E01〜E04 advance → E90 terminal / E98 invalidate / E99 expire）を対象とする。

## ■ 実装するもの

### 1. Strategy Engine本体の最小骨格

contract enforcer（`src/strategy_contract/`）とは別に、Strategy Engine本体の骨格を新設する。enforcerは試験専用の参照実装であり、Engine本体はこれを置き換えるのではなく、enforcerが検証した契約を満たす実装として作る。

設計提案で以下を報告すること:
- ファイル構成と配置（`src/` 配下のどこに置くか）
- contract enforcerとの関係（enforcerの判定ロジックをEngine内部に取り込むのか、enforcerをEngine内部で呼ぶのか、完全に独立するのか）
- 既存コード（pipeline.py等）への接続点の有無と方針

### 2. Predicate Evaluator のスタブ

代表1型が使うpredicateのevaluatorを実装する。ただし:

- **閾値は未較正**（収録完了前のため）。通常動作時は `UNVALIDATED` として拒否を返すこと（契約R7と整合）
- テスト時のみ較正済みフラグを注入し、predicate評価ロジック自体の正しさを検証できること
- 較正値が決まった後に差し替え可能な構造にすること（閾値をハードコードしない）

設計提案で以下を報告すること:
- 代表1型が必要とするpredicate class一覧（正本CSVから特定）
- 較正済みフラグの注入方法（テストfixture経由、コンストラクタ引数、etc.）

### 3. イベント投入の共通インターフェース

Engineは「イベント列がどこから来たか知らない」設計にすること。Live（Binance WebSocket）とReplay（決定論再生）の両方から同じインターフェースでイベントを受け取れるようにする。

- Engineは共通インターフェースからイベントを受け取り、イベント源を区別しない
- 現段階でLive pipelineへの接続は行わない（インターフェース定義のみ）
- Replay driver（`src/strategy_contract/replay_driver.py` または新設）から合成イベントを投入して試験する

設計提案で以下を報告すること:
- 共通インターフェースの型定義案
- 既存のReplay基盤（`replay/`）との関係

### 4. テスト

以下を最低限含むこと:
- 代表1型の全経路試験: arm → advance × 4 → terminal → SHORT_READY handoff
- 代表1型のinvalidation経路: advance途中でinvalidate → 終了
- 代表1型のexpire経路: deadline超過 → 終了、Order Intent 0件
- predicate evaluator のスタブ動作: 未較正時はUNVALIDATED拒否、較正済み注入時は評価実行
- **既存 Replay契約拒否試験 27件が全件引き続きPASS**すること（回帰保証）
- **既存テスト 516件が全件引き続きPASS**すること

## ■ 制約

- **runtime有効化0・発注権限0を維持**。Live pipelineへの接続・Hook runtime接続・発注系への接続は一切行わない
- **代表1型のみ**。他のvariantの個別実装は本作業の範囲外
- 完成済みFlow Price Response・3段チャート・8パターン・OI・UI・既存runtime・raw dataを変更しない
- 収録中のHook Stage 2A/2B観測基盤の停止・変更禁止
- 正本CSV/ポリシー文書は読み取りのみ
- 閾値・comparator・windowの較正は本作業の範囲外（スタブのみ）
- contract enforcer（`src/strategy_contract/`）の既存コード・既存テストを壊さない

## ■ 進め方（各段階でお館様の確認を取る）

1. **設計提案** — 必読文書の確認結果（齟齬の有無）、Engine骨格のファイル構成・配置案、contract enforcerとの関係、共通インターフェース案、代表1型のpredicate一覧、テスト一覧案を報告 → お館様OK後に着手
2. **実装＋試験実行** — 全テスト合格を確認（新規＋既存回帰）
3. **完了報告** — テスト結果、回帰結果、checkpoint更新、コミット（pushはお館様の指示があるまで行わない）

一気に全部やらない。段階ごとに止まって報告すること。
