# 指示書: Snapshot Producer（既存検出器出力のcondition key化）

日付: 2026-07-27
発行: Claude web
実行: Codex
承認: お館様

---

## 目的

G16 Composite合成式の入力材料となるTier A conditionを生産するため、
既存検出器の出力をcondition keyとして整理・供給するSnapshot Producerを構築する。

背景:
- 現Ingestion Adapterの固定出力は9 keyのみ（condition_adapter.py:53-119）
- G16合成に必要な材料（aggression量、price progress、book refresh/pull、efficiency等）の
  producerが存在しない
- 既存検出器（absorption_detector, imbalance_detector, footprint, cvd等）は
  これらの値を既に計算しているが、condition keyとして外部公開されていない
- Composite Synthesis層はproducer完成後に定義・実装する（工程順序変更済み）

---

## 制約

- 既存検出器のロジック・出力・インターフェースを変更しない
- 検出器の出力を読み取り、condition keyに変換するだけ。検出器内部には手を入れない
- source, 正本CSV/ポリシー, runtime, raw data, 収録基盤の変更禁止
- 閾値ハードコード禁止
- commit/push禁止（お館様の指示まで）
- 全主張にファイル:行番号の根拠
- 回帰保証: 全テスト全件PASS維持

---

## Stage 1: 既存検出器出力の棚卸し（承認なしで着手してよい）

### 1.1 読み取り対象

以下のファイルを読み、各検出器が「何を計算し、何を出力しているか」を棚卸しする。

#### パイプライン本体
- `Delta_Engine_Pro4web/src/pipeline.py` — 各検出器のインスタンス化・呼び出し箇所
- `Delta_Engine_Pro4web/src/replay_pipeline.py` — Replayパイプラインの同等箇所

#### 検出器
- `Delta_Engine_Pro4web/src/cvd.py` — CVD計算
- `Delta_Engine_Pro4web/src/absorption.py` — 吸収検出
- `Delta_Engine_Pro4web/src/imbalance.py` — インバランス検出
- `Delta_Engine_Pro4web/src/footprint.py` — フットプリント（バー集計、VA%）
- `Delta_Engine_Pro4web/src/orderbook.py` — オーダーブック状態管理

#### 既存adapter
- `Delta_Engine_Pro4web/src/strategy_engine/ingestion/condition_adapter.py` — 現Tier A adapter

#### G16正本（参照用）
- `ArchitectureRepository/00_Master/トリガー作成指示書群/ORDER_FLOW_CONDITION_DICTIONARY_V0_1_20260726.md`
  — G06〜G11の材料カテゴリ定義（G16が必要とする入力の参照）

### 1.2 棚卸しの出力形式

検出器ごとに以下の表を作成する:

| 検出器 | 出力属性/メソッド | 型 | 値の意味 | 対応するG01-G15 family | 対応するcondition key候補 | 根拠（ファイル:行） |
|---|---|---|---|---|---|---|

「対応するcondition key候補」は、G01-G15の512 keyの中から意味が一致するものを特定する。
一致するものがなければ「対応なし: [理由]」と記載する。

### 1.3 ギャップ分析

棚卸し結果とG16草案（DRAFT_G16_COMPOSITE_RULES_AND_E98_UPDATE_20260727.md §4）の
depends_on候補を照合し、以下を整理する:

| G16 key | 必要な材料カテゴリ | 既存検出器で計算済みか | 検出器名と出力属性 | condition keyへの変換方法 |
|---|---|---|---|---|

変換方法は以下のいずれか:
- **DIRECT:** 検出器の出力値をそのままcondition keyの値として使える
- **DERIVE:** 検出器の出力値から単純な計算（比率、差分等）で導出可能
- **NOT_AVAILABLE:** 既存検出器が該当する値を計算していない

NOT_AVAILABLEの場合は、何が不足しているかを具体的に記載する。

### 1.4 pre_aggregated経路の現状

condition_adapter.pyのpre_aggregated経路（115-119行付近）について:
- 現在この経路に値を渡しているコードが存在するか
- pipeline.py / replay_pipeline.pyからの呼び出し時にpre_aggregatedに何が入っているか
を実コードから確認し報告する。

### 1.5 報告

以下を1ファイルにまとめて報告する:

出力先: `ArchitectureRepository/00_Master/トリガー作成指示書群/SNAPSHOT_PRODUCER_STAGE1_INVENTORY_20260727.md`

内容:
1. 検出器ごとの出力棚卸し表（§1.2）
2. ギャップ分析表（§1.3）
3. pre_aggregated経路の現状（§1.4）
4. NOT_AVAILABLE一覧（新規実装が必要な材料）
5. 推奨するproducer設計方針（読み取り結果に基づく提案。確定ではない）
6. 全主張のファイル:行番号根拠

---

## Stage 2: Producer実装（お館様の承認後に着手。承認なしでの着手禁止）

Stage 1報告をClaude webが検証し、お館様が承認した後に実装する。
実装内容はStage 1の結果に依存するため、ここでは方針のみ記載する。

### 2.1 想定する配置

- `src/strategy_engine/ingestion/snapshot_producer.py`（新規）
  — 各検出器の出力を読み取り、condition key辞書を生成する
- `condition_adapter.py`への統合
  — snapshot_producerの出力をpre_aggregated経路またはmergeで供給

### 2.2 設計原則

- 検出器の内部には手を入れない（読み取り専用）
- 検出器のpublic属性/メソッドのみ使用する。private属性（_prefix）は使わない
- key名はCondition Dictionary正本のG01-G15に準拠する
- 型変換: 検出器がDecimalで出力するものはstr変換（float()禁止）
- Live/Replayの両パイプラインで同一のproducerを使う
- テストは検出器のmock出力 → producer → condition key辞書の変換を検証する

### 2.3 完了報告

- 変更ファイル一覧（before/after）
- 新規生成されるcondition key一覧
- テスト結果（既存全件PASS + 新規テスト件数）
- NOT_AVAILABLEのまま残った材料一覧

---

## 停止条件

以下のいずれかに該当したら実装を停止し、該当箇所と理由を報告する:

- 検出器の出力が意味的にcondition keyと対応しない（変換ロジックが推測になる）
- 検出器のpublic属性だけでは必要な値にアクセスできない
- Live/Replayで検出器のインターフェースが異なり統一producerが作れない
- 正本のcondition key定義と検出器の計算内容に矛盾がある
- その他、推測が必要になる箇所
