# Manual HFM JSONL ledger checkpoint

時刻: 2026-07-25 14:35 JST  
承認範囲: 手動HFM実測ログの追記・読込経路  
未承認: UI入力、DB接続、自動発注、実戦評価

## 完了

- `src/orderflow/manual_execution_ledger.py`を新規追加
- ManualExecutionRecordをJSONLへUTF-8追記
- 既存record_idの重複追記を拒否
- 行単位のdecode検証と破損行のline番号報告
- 空白行を無視し、欠落ファイルは空ledgerとして扱う
- `tests/orderflow/test_manual_execution_ledger.py`を追加

## 検証

- JSONL round-trip、欠落ledger、破損行、status不正: **6 passed**
- 実ファイルへの追記・再読込・重複ID拒否dry run: 成功

## 運用境界

- ledgerは研究用の監査ログであり、注文を送らない
- EXECUTED、SKIPPED、REJECTED、QUOTE_STALEを混ぜずに保存する
- 手動入力値は自動補正しない
- 既存Flow OutcomeやHFM Context Outcomeへ混ぜない

## 次の再開位置

手動ログを実際に収集する場合は、保存先を明示してこのJSONL ledgerへ追記する。
一定数が蓄積するまで、集計レポート、勝率、期待値、UI表示を追加しない。

