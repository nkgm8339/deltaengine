# 承認文書：Ingestion Adapter 骨格（代表1型 condition key）Stage 1 設計提案

作成日: 2026-07-27 JST
対象: Claude Code Stage 1 報告（Ingestion Adapter 骨格）
根拠指示書: お館様口頭指示（ingestion adapter設計を先行）

---

## 判定：Stage 1 承認。Stage 2（実装＋試験実行）へ進んでよい。

正本との齟齬0件。代表1型の9 classすべてがTier A候補routeを最低1つ持つという事実確認は正確であり、Tier Aのみ供給で代表1型を端から端まで通せる根拠として妥当。

## 質問への回答

### 質問1: C 方針（MarketStateSnapshot → Tier A condition snapshot の写像層）

**承認する。**

- MarketStateSnapshot（正規化された市場状態のread-onlyビュー）を入力に、Tier A condition snapshot を出力する写像層とする
- Live/detector に直結せず正規化snapshot経由とすること
- adapterは「condition snapshotの供給元」であり、evaluatorは「condition snapshotの消費先」。責務が明確に分離されている

### 質問2: B/D スコープ（Tier A のみ実装、Tier B は documented gap）

**承認する。**

- Tier A（生/派生の数値、窓計算で導出可能）のみ本工程で実装
- Tier B（STRATEGY_SPECIFIC 合成FLAG）は本工程の範囲外とし、documented gap として明記すること
- Tier B反証keyがsnapshotに現れないため evaluatorはfail-closedで「反証なし」と扱う。runtime有効化0の現段階では安全
- 将来の「composite synthesis 層」が必要であることを checkpoint に記録すること

### 質問3: C の pre-aggregated 分離

**承認する。**

- refresh_count / pull_ratio / progress_ticks / no_progress_ratio は MarketStateSnapshot に事前集計フィールドとして持たせ、adapterはそのまま写す
- 本計算（DEPTHイベント計数、price×tape秒次計数）は将来のreplay/detector統合工程で差し込む
- adapter骨格の責務を「窓導出＋素通し」に限定し、イベント列再構築を含めない

### 質問4: E ファイル構成（`src/strategy_engine/ingestion/` 新規サブパッケージ）

**承認する。**

- `src/strategy_engine/ingestion/`（`__init__.py` / `market_state.py` / `condition_adapter.py`）
- `tests/strategy_engine/test_ingestion_adapter.py`
- 既存 strategy_engine ファイルは変更しない（adapter出力は既存の PredicateObservation.conditions にそのまま入る）

### 質問5: F テスト一覧

**承認する。** 過不足なし。

- I1: CVD窓導出（change/slope）
- I2: wall導出（concentration/distance）
- I3: OI導出（change/pct/joint state）
- I4: pre-aggregated pass-through
- I5: 欠測/空snapshot（fail-closed）
- I6: Engine統合（adapter → evaluator → 代表1型全経路 → SHORT_READY）
- R-a/b/c: 回帰（engine 23 / 契約 27+1skip / 既存 516）

## Stage 2 の完了条件

1. I1〜I6 の全件合格
2. R-a: strategy_engine 既存23件 全PASS維持
3. R-b: Replay契約拒否試験 27 passed, 1 skipped 維持
4. R-c: 既存テスト 516件 全件合格（回帰0件）
5. documented gap（Tier B合成FLAG / composite synthesis層）をcheckpointに記録
6. checkpoint更新
7. コミット作成（push はお館様の指示があるまで行わない）

## 制約の再確認（Stage 2 でも継続）

- runtime有効化0・発注権限0を維持
- Live pipeline・Hook runtime・発注系への接続禁止
- 既存検出器のコード変更禁止
- `src/strategy_contract/` の既存コード・既存テスト変更禁止
- `src/strategy_engine/` の既存ファイル変更禁止（新規サブパッケージのみ追加）
- 完成済みFlow Price Response・3段チャート・8パターン・OI・UI・既存runtime・raw data変更禁止
- 収録中のHook Stage 2A/2B観測基盤の停止・変更禁止
- 正本CSV/ポリシー文書は読み取りのみ
- 閾値ハードコードなし（adapterは生量のみ供給、閾値はCalibrationBook経由）
- Stage 2 完了時点で停止し、完了報告を提出してお館様の確認を待つこと
