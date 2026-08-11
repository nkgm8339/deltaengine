# 統計的大口候補判定 — Stage 1 調査指示書

**発行日**: 2026-08-09
**親文書**: `STATISTICAL_LARGE_CANDIDATE_IMPLEMENTATION_INSTRUCTION_DRAFT_20260809.md`
**対象ステップ**: 親文書 Section 8 Step 1
**種別**: Stage 1（調査のみ・コード変更禁止）

---

## 0. この調査の目的

統計的大口候補判定の実装に先立ち、既存コードベースの接続点、保護対象、回帰影響を調査し、実装設計の入力とする。

**この指示書ではコードを一切変更しない。** テストの追加・修正、ファイルの編集、依存の追加を行わない。調査結果をレポートファイルとして提出する。

---

## 1. 調査対象ファイル

以下のファイルを読み取り、指定された項目をレポートする。ファイルパスは `Delta_Engine_Pro4web/` からの相対パス。存在しないファイルは「不在」と記録する。

### 1.1 pipeline.py

**場所**: `src/orderflow/pipeline.py` または同等のメインパイプラインモジュール

調査項目:

- (P-1) trade正規化の関数名・行番号・入力型・出力型
- (P-2) 正規化済みtradeを既存detectorへ渡す箇所の関数名・行番号・呼び出し方法（直接呼び出し / イベントバス / queue等）
- (P-3) 既存detectorの一覧（クラス名・関数名・登録箇所）
- (P-4) detector処理後のstorage書き込み箇所（DuckDB / Parquet / JSONL）の関数名・行番号
- (P-5) detector処理後のpush_broker呼び出し箇所の関数名・行番号
- (P-6) asyncioタスク・thread・executor・queue consumerの有無と行番号
- (P-7) 新しい同期detectorを追加する場合の最小変更候補箇所（「ここにcallを1行追加すれば既存処理に影響なく渡せる」という箇所の特定）
- (P-8) pipeline.py内でfloat()を使用している箇所の行番号一覧（0件であるべき）

### 1.2 flow_detector.py / LargeTradeDetector

**場所**: `src/orderflow/flow_detector.py` または large_trade判定を含むモジュール

調査項目:

- (F-1) `large_trade_min_qty` の定義箇所・現在値・型（Decimal / float / int）
- (F-2) LargeTradeDetectorクラス（またはlarge_trade判定関数）の入力シグネチャ・出力型
- (F-3) 判定結果のイベント種別名（`FLOW` / `LARGE_TRADE` 等）
- (F-4) 判定結果がpush_brokerへ渡される経路（直接 / pipeline経由 / イベントバス）
- (F-5) float()使用箇所の行番号一覧

### 1.3 Hook Detector

**場所**: `src/orderflow/hook_detector.py` または同等モジュール

調査項目:

- (H-1) large_trade系フック（C01, C02等）の定義箇所・閾値参照・入力型
- (H-2) large_market_buy/sell、large_buy_cluster/sell_cluster のフック名・行番号
- (H-3) HookEventの出力payload構造（detector名フィールドの有無）
- (H-4) Hook判定がpipeline.pyのどの段階で呼ばれるか（trade正規化直後 / detector後 / 別段階）
- (H-5) Hook Detectorが分布・統計量を内部で持っているか（rolling window等）

### 1.4 push_broker.py

**場所**: `webapp/push_broker.py` または同等モジュール

調査項目:

- (B-1) PriorityQueueの定義箇所・キーの優先度定義・現在の優先度種別一覧
- (B-2) イベント種別の登録方式（enum / 文字列 / 自由）と現在登録済みの種別一覧
- (B-3) 新イベント種別 `STATISTICAL_LARGE_CANDIDATE` を追加する場合に変更が必要な箇所（登録、優先度設定、フィルタ等）
- (B-4) 送信失敗時のリトライ・ドロップ・ログの処理箇所
- (B-5) stale判定の閾値・判定箇所・現在値
- (B-6) ブラウザ側queueの制限（maxバッファサイズ等）が設定されている箇所
- (B-7) 現在のイベントpush頻度の概算（TICK、BOOK_UPDATE、FLOW等のpush/秒の目安。コードコメント・定数・テストから推定可能な範囲で）

### 1.5 Replay / EventSource

**場所**: `webapp/` 配下のReplay関連モジュール、EventSource配信モジュール

調査項目:

- (R-1) Replayモードの起動経路（API endpoint / CLI / 設定フラグ）
- (R-2) Replay時のtrade列の供給元（Parquet / DuckDB / JSONL / ファイル）
- (R-3) Replay時にdetectorが呼ばれる経路（liveと同じpipeline.pyを通るか、別経路か）
- (R-4) EventSource配信のイベント種別登録方式と現在の種別一覧
- (R-5) Replay時のevent_time順序保証の仕組み（ソート / ストリーム順 / 未保証）
- (R-6) Replay開始時の状態初期化処理（分布・detector内部状態のリセット有無）

### 1.6 既存テスト

**場所**: `tests/` 配下

調査項目:

- (T-1) `tests/webapp/test_api.py` のテスト関数一覧と、各テストが依存するイベント種別・detector・pipeline関数
- (T-2) `test_push_broker.py` の場所・テスト関数一覧・依存するイベント種別
- (T-3) `test_absorption_realtime_display.py` の場所・テスト関数一覧
- (T-4) `tests/orderflow/` 配下のテストファイル一覧と、pipeline.py / flow_detector.py / hook_detector.py に関連するテスト
- (T-5) 上記テストのうち、新モジュール追加（import追加、pipeline.pyへの1行call追加）で期待値が変わりうるテストの特定と理由

### 1.7 流動性関連データの棚卸し

**場所**: `src/orderflow/` 配下全体、`webapp/` 配下、設定ファイル

調査項目:

- (L-1) 現在コード内で計算・保持されている流動性指標の一覧（spread、板厚、出来高移動平均、VWAP、OI等）。各指標について: 変数名、計算箇所のファイル:行、型（Decimal / float / int）、更新タイミング（tradeごと / bookごと / 定期）、保持方式（メモリ / DB / 両方）
- (L-2) 流動性状態を分類・判定している既存コードの有無（「高流動性」「低流動性」等の区分が既にあるか）
- (L-3) rolling windowまたはstreaming統計を実装している既存コードの有無（クラス名・方式・窓サイズ）。統計的大口候補の分布収集器が再利用または参考にできるか
- (L-4) tickSizeの取得・保持箇所（exchangeInfo由来の値がどこに格納されているか）

---

## 2. レポート形式

調査結果は以下のファイル名で提出する。

```
STAT_LARGE_CANDIDATE_STAGE1_REPORT_YYYYMMDD.md
```

レポートは以下の構造とする。

```markdown
# 統計的大口候補判定 — Stage 1 調査レポート

## 調査環境
- commit SHA: (HEAD)
- branch: feature/footprint-dom-tape
- 調査日時: YYYY-MM-DD HH:MM UTC

## P. pipeline.py
### P-1: trade正規化
（回答）
### P-2: detector呼び出し
（回答）
...

## F. flow_detector.py
### F-1: large_trade_min_qty
（回答）
...

## H. Hook Detector
...

## B. push_broker.py
...

## R. Replay / EventSource
...

## T. 既存テスト
...

## L. 流動性関連データ
...

## 調査中に発見した問題・懸念
（予期しないfloat()使用、未テスト箇所、文書と実装の乖離など）
```

各項目は、ファイル名:行番号を必ず記載する。「確認した」「問題ない」だけの回答は不可。根拠となるコード片（5行以内の引用）を添える。

---

## 3. 禁止事項

- コードの変更、テストの追加・修正、ファイルの新規作成（レポートファイルを除く）
- 依存パッケージの追加
- git commitの作成（レポートファイルのcommitも不要）
- 調査範囲外のファイルへの変更提案（レポートに「懸念」として記録するのは可）
- float()違反を発見した場合の自主修正（レポートに記録し、別途修正指示を待つ）

---

## 4. 完了条件

- Section 1の全調査項目（P-1〜P-8、F-1〜F-5、H-1〜H-5、B-1〜B-7、R-1〜R-6、T-1〜T-5、L-1〜L-4）に対する回答がレポートに存在する
- 各回答にファイル名:行番号が記載されている
- 存在しないファイル・該当なしの項目は明示的に「不在」「該当なし」と記録されている
- レポートファイルのSHA-256とバイト数を報告する

---

## 5. 次のステップ（参考）

このレポートの提出後、以下を順に進める。お館様とClaudeがレポートを検証し、承認後に次の指示を発行する。

1. レポート検証・承認
2. 親文書 Section 10 の未決事項を、レポートの流動性データ棚卸し結果に基づいて順に設計判断
3. 設計判断完了後、Stage 2 実装指示書を発行
