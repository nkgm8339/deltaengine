# Manual execution CLI checkpoint

時刻: 2026-07-25 14:55 JST  
承認範囲: 手動execution JSONの検証とJSONL追記CLI  
未承認: UI入力、DB接続、自動発注、成績集計

## 完了

- `tools/append_manual_execution.py`を新規追加
- JSON fileまたはstdinからrecordを受け取る
- ManualExecutionRecord schemaで検証してから追記する
- record_id重複時は追記せずエラー終了する
- 成功時は追加record_idをJSONで出力する
- `tests/tools/test_append_manual_execution.py`を追加

## 使用形式

```text
python -m tools.append_manual_execution \
  --ledger data_05M/manual/manual_execution.jsonl \
  --record manual_record.json
```

ledgerは追記専用であり、既存recordを上書きしない。

## 検証

- CLI関連テスト: **8 passed**
- 正常追記: exit 0、record_id出力
- 同一record_id再追記: exit 2、ledger不変

## 次の再開位置

ユーザーが手動実測を開始する場合、実際の保存先とrecord入力方法を決めて
ledgerへの記録を始める。データが蓄積するまでUI、DB、自動発注、成績集計は追加しない。

