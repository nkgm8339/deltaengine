# Claude Code 指示書：Replay契約 拒否試験の実装

作成日: 2026-07-27 JST
対象プロジェクト: `Delta_Engine_Pro4web`（branch: ui-refresh-v2）
前段作業者: Codex（課金切れにより中断）。本作業はClaude Codeが引き継ぐ。

## ■ 必読（着手前）

1. `ArchitectureRepository/00_Master/PROJECT_MEMORY.md` 全文
2. `ArchitectureRepository/00_Master/トリガー作成指示書群/ORDER_FLOW_STATE_CONDITION_BINDING_POLICY_V0_1_20260727.md`
3. 同 `ORDER_FLOW_HOOK_VARIANT_ROUTING_POLICY_V0_1_20260727.md`
4. 同 `ORDER_FLOW_STRATEGY_CONDITION_SUBSETS_CHECKPOINT_20260727.md`（Codexの最終checkpoint。再開位置の正本）
5. 機械可読正本CSV群（Predicate/Binding/Routing registry）

**前提条件**: 本指示書の契約定義と上記正本の間に齟齬を見つけた場合、実装せず齟齬内容を報告して停止すること。正本が優先である。

## ■ 背景

Strategy Engineの設計骨格（365 variant / 3,336 edge / 25,664 route）まで完了した。全対象はUNVALIDATED・runtime有効化0・発注権限0。

Codexが宣言した次段階は「replay契約」である。すなわち、Strategy Engineが将来実装されたとき、設計ポリシーが定めた判定契約に**違反する入力・遷移・発注経路を確実に拒否する**ことを、決定論リプレイ上の試験として先に固定する。実装より先に契約試験を作ることで、後続実装が契約を破ったら即座にテストが落ちる状態を作る。

## ■ 実装するもの

### 1. Replay契約試験ハーネス

- 決定論リプレイ基盤の上に、合成イベント列（順序・時刻・event_idを完全制御した人工シーケンス）を流し込める試験用ドライバを作る
- 実データ由来の試験と合成イベント試験の両方を書けること
- Engineが未実装の現段階では、**契約を検証する参照実装（contract enforcer）の最小骨格**を試験対象として新設してよい。ただしこれはStrategy Engine本体の実装ではなく、edge遷移の受理/拒否判定だけを行う最小層に留めること

### 2. 拒否試験（以下の各カテゴリを網羅）

#### R1. 順序逆転の拒否
- 判定契約2「ADVANCEの使用evidenceは直前遷移より後でなければならない」に基づく
- 直前遷移より古いタイムスタンプ/event orderのevidenceでADVANCEを試みる → 拒否されること
- event到着順と発生時刻順が食い違うケース（遅延到着）も試験すること

#### R2. 同一eventの再利用拒否
- 判定契約3「同じsource_event_idを複数stateの成立証拠として再利用しない」に基づく
- 1つのevent_idでE01成立→同じevent_idでE02成立を試みる → 拒否されること
- 別instanceにまたがる再利用の扱いも正本の定義を確認して試験すること（正本に定義がなければ「未定義」として報告し、勝手に仕様を決めない）

#### R3. 途中反証（INVALIDATE）の強制
- 判定契約6「named guardのいずれかが成立した時点でObservation Instanceを終了する」に基づく
- ADVANCE途中のinstanceにinvalidation predicateを成立させる → instanceが終了し、以後のADVANCE・TERMINALが拒否されること
- INVALIDATE後に有効なevidenceが到着しても復活しないこと

#### R4. timeout（EXPIRE）の強制
- 判定契約7「EXPIREはversion付きdeadlineで終了し、Order Intentを出さない」に基づく
- deadline超過後のADVANCE試行 → 拒否。EXPIRE時にOrder Intentが生成されないこと
- monotonic engine timeで判定すること（壁時計の巻き戻しに影響されない）

#### R5. Hook直接発注の拒否
- routing policy「HookはOrder Triggerではない」「direct order authority 0」に基づく
- Hook発火からOrder Intent生成へ直行する経路が存在しないこと（型/API層で不可能なら、その事実を試験として固定）
- TERMINALすらLONG_READY/SHORT_READYをgateへ渡すだけで直接注文しない（判定契約8）ことの試験

#### R6. context-onlyによるhard advance拒否
- routing policy「SUSPECTED_CONTEXT_ONLYはhard stateを単独advanceしない」「CONTEXT_REFRESH_ONLYはhard stateを単独advanceしない」に基づく
- context-only route由来のevidenceのみでADVANCEを試みる → 拒否されること

#### R7. 未較正・未実装の拒否
- 全Predicate/BindingはUNVALIDATEDである。較正状態フラグが未較正のedgeを実発火扱いにできないこと
- `REGISTERED_UNIMPLEMENTED` Hookのrouteがruntimeで無効であること
- OI必須stateでhard sourceが`UNKNOWN / STALE`の場合に成立へ代用されないこと（判定契約9）

#### R8. LOCATION_ARM前のインスタンス生成拒否
- routing policy「location + first predicate + freshnessを満たした時だけarmする」に基づく
- location不成立のままFIRST_STATE_WAKEだけでObservation Instanceが作られないこと

### 3. 試験の記録

- 各拒否試験は「どのポリシー文書のどの条項に基づくか」をテスト内コメントで明記する
- 試験一覧（試験名×根拠条項×結果）をMarkdownの対照表として文書化する

## ■ 制約

- **runtime有効化0・発注権限0を維持**。本作業で作るのは試験と契約検証の最小骨格のみ。Strategy Engine本体の実装、Hookのruntime接続、発注系への接続は一切行わない
- 完成済みFlow Price Response、3段チャート、8パターン、OI、UI、既存runtime、raw dataは変更しない
- 保存済み記録の改変・削除は一切しない
- 収録中のHook Stage 2A/2B観測基盤（append-only収録）を止めない・変更しない
- 正本CSV/ポリシー文書は読み取りのみ。変更が必要と判断した場合は変更せず報告する
- 閾値・comparator・windowの較正は本作業の範囲外。契約の構造だけを試験する

## ■ 進め方（各段階でお館様の確認を取る）

1. **必読文書の確認結果と設計提案** — 齟齬の有無、contract enforcer骨格の設計（ファイル構成・配置）、試験一覧案（R1〜R8の具体テストケース列挙）を報告 → お館様OK後に着手
2. **実装＋試験実行** — 全拒否試験の合格を確認
3. **完了報告** — 試験×根拠条項の対照表、回帰試験結果（既存テストが全て通ること）、checkpoint更新、コミット（push はお館様の指示があるまで行わない）

一気に全部やらない。段階ごとに止まって報告すること。
