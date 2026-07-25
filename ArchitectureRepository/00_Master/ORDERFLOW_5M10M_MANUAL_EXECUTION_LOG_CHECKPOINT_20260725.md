# Manual HFM execution-log checkpoint

時刻: 2026-07-25 14:15 JST  
承認範囲: 手動HFM実測ログのschemaと入力検証  
未承認: UI入力、DB接続、自動発注、実戦評価

## 完了

- `src/orderflow/manual_execution_log.py`を新規追加
- EXECUTED、SKIPPED、REJECTED、QUOTE_STALEを区別
- Episode ID、checkpoint、signal表示時刻、判断時刻、注文時刻、約定時刻を保持
- entry side、entry fill、観測Bid／Ask、exit fillを保持
- 非執行理由を必須化
- 同一local clock上の人間執行時刻を検証
- entry ask >= entry bid、価格正値を検証
- execution delayを表示時刻からfill時刻で計算
- `to_row()`で後続のJSONL／Parquet境界へ渡せる列を固定
- `tests/orderflow/test_manual_execution_log.py`を追加

## 検証

- Manual execution log tests: **3 passed**
- 実行・見送り・時刻逆行・理由欠落を確認

## 変更しない範囲

- 既存1M Flow Price Response
- Episode BuilderとBinance outcome labels
- HFM quote parser
- UI、DB、API、Live pipeline
- 自動発注経路

## 次の再開位置

手動実測を開始する場合は、まずこのschemaを入力できる監査ログ経路を選ぶ。
初期段階ではローカルJSONLまたは手動CSVを許容し、実約定データが蓄積するまで
UI・DB・発注APIへの接続は行わない。

