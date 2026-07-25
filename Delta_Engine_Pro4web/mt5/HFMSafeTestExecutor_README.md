# HFMSafeTestExecutor

MT5上の制約付きテスト発注器。既存の観測EAや1Mコアには接続変更を加えない。

## 安全条件

- 初期状態は `EnableLiveOrders=false` のSHADOWモード
- `TestVolume` は0.01以外を拒否
- ブローカー最小volumeが0.01より大きい場合は拒否
- MagicNumber対象の同時保有は1件まで
- SL価格が必須で、現在価格の危険側なら拒否
- `MaxSpreadPoints` を設定した場合、超過時は拒否
- 共通フォルダに `DeltaEngine_HFM_EMERGENCY_STOP.flag` が存在すると新規発注を停止し、対象ポジションを決済
- LIVEには `EnableLiveOrders=true` と `LiveConfirmation=I_UNDERSTAND_LIVE_01_LOT` の両方が必要

## コマンド形式

共通フォルダの `DeltaEngine_HFM_order_command.txt` に最後の1行を書き込む。

```text
command_id|BUY|stop_loss_price|take_profit_price
```

例（価格は実際の現在価格に合わせて生成すること。手入力での架空テストは禁止）:

```text
episode-0001|BUY|60000.00|60100.00
```

実行結果は `DeltaEngine_HFM_execution_audit.jsonl` に追記される。SHADOWでは発注せず、`SHADOW` として記録する。

## 運用順序

1. MT5デモ口座でSHADOW確認
2. デモ口座で発注・SL・緊急停止を確認
3. LIVEを有効化する場合は、別途明示承認を受けてから2つのLIVE入力を変更

このEAは利益性を検証するものではなく、注文経路と安全制約を検証するためのもの。
