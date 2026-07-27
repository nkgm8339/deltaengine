# 承認文書：Replay契約 拒否試験 Stage 1 設計提案

作成日: 2026-07-27 JST
対象: Claude Code Stage 1 報告（Replay契約 拒否試験）
根拠指示書: `replay_contract_rejection_tests_instruction.md`

---

## 判定：Stage 1 承認。Stage 2（実装＋試験実行）へ進んでよい。

Stage 1 報告を指示書および正本（PROJECT_MEMORY.md / 判定契約1〜9 / routing policy / Codex checkpoint / 機械可読CSV群）と照合した。齟齬報告0件は妥当、CSV実測値（edge 3,336 / route 25,664 / predicate 37件全UNVALIDATED）は正本と一致していることを確認した。

## 質問への回答

### 質問1: 骨格設計（`src/strategy_contract/` 新規隔離パッケージ）

**承認する。** 以下の構成で着手すること。

- `Delta_Engine_Pro4web/src/strategy_contract/`（events.py / rejection_codes.py / variant_contract.py / enforcer.py / replay_driver.py）
- `Delta_Engine_Pro4web/tests/strategy_contract/`（test_replay_contract_rejection.py / test_replay_contract_golden_path.py / fixtures/）
- enforcerに order_send 相当のAPIを実装しないこと（TERMINALは LONG_READY/SHORT_READY handoffオブジェクトの返却のみ）。この構造保証を維持すること
- 正本CSVは読み取り専用ロードのみ。既存runtime・収録基盤・発注系への接続は一切行わない

### 質問2: 【未定義-1】cross-instance の source_event_id 再利用

**承認する。** R2試験では同一instance内の再利用のみを拒否（SOURCE_EVENT_ID_REUSED）として固定し、cross-instance は **UNDEFINED_BY_CANON として明示スキップ** で扱うこと。仕様は決めない。

- テスト内コメントおよび完了報告の対照表に「UNDEFINED_BY_CANON（正本に定義なし）」と明記すること
- 本未定義点は正本側の将来更新事項として完了報告に記載すること（正本文書の変更は行わない）

### 質問3: 試験一覧 R1〜R8 + GP

**承認する。** 過不足なし。以下の通り実施すること。

- R1-a/b（判定契約2）、R2-a/b（判定契約3・未定義-1）、R3-a/b（判定契約6）、R4-a/b/c（判定契約7）、R5-a/b（routing§0・判定契約8）、R6-a（routing§5）、R7-a/b/c（policy§5・routing§5・判定契約9）、R8-a（routing§2）、GP（対照基準）
- 各RejectReasonのenum docstringとテスト内コメントに根拠条項を明記すること

## Stage 2 の完了条件（指示書「3. 試験の記録」「進め方3」）

1. 全拒否試験＋golden path試験の合格
2. 既存テスト全件の回帰合格（既存テストへの影響0件）
3. 試験名×根拠条項×結果の対照表Markdown作成
4. checkpoint更新
5. コミット作成（**push はお館様の指示があるまで行わない**)

## 制約の再確認（Stage 2 でも継続）

- runtime有効化0・発注権限0を維持
- 完成済みFlow Price Response・3段チャート・8パターン・OI・UI・既存runtime・raw data変更禁止
- 収録中のHook Stage 2A/2B観測基盤の停止・変更禁止
- 正本CSV/ポリシー文書は読み取りのみ
- 閾値・comparator・window較正は範囲外
- Stage 2 完了時点で停止し、完了報告を提出してお館様の確認を待つこと
