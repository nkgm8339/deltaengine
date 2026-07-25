# Manual HFM collection runbook

作成時刻: 2026-07-25 15:10 JST  
承認範囲: 手動実測の記録運用  
既定ledger: `Delta_Engine_Pro4web/data_05M/manual/manual_execution.jsonl`

## 1. 記録対象

記録するのは、DeltaEngineが観測したEpisodeに対する人間の判断とHFM実約定である。
観測だけで見送った場合もSKIPPEDとして記録する。

EXECUTEDの場合:

- `episode_id`
- `checkpoint_time`、`checkpoint_stage`
- `signal_displayed_time`
- `decision_time`
- `order_time`
- `fill_time`
- `entry_side`
- `entry_price`
- entry時のHFM Bid／Ask
- `exit_time`
- `exit_price`

SKIPPED、REJECTED、QUOTE_STALEの場合:

- シグナルと判断時刻
- `status`
- `skip_reason`
- 分かる範囲のBid／Ask

## 2. 時刻規則

- `checkpoint_time`はBinance観測時刻として保存する
- signal表示、判断、注文、約定、決済は同じlocal clockで保存する
- Binance時刻をHFM local clockへ推測変換しない
- 秒・ミリ秒を丸めず、取得できる精度で保存する
- 取引後に都合よく時刻を書き換えない

## 3. 追記方法

1. 1件のrecord JSONを作る
2. schemaの全必須項目を埋める
3. CLIでledgerへ追記する

```text
python -m tools.append_manual_execution `
  --ledger data_05M/manual/manual_execution.jsonl `
  --record manual_record.json
```

成功時はrecord IDを表示する。同じrecord IDは二度追記できない。

## 4. やってはいけないこと

- 実際には約定していないEXECUTEDを作る
- 見送ったシグナルを削除する
- stale quoteを通常約定として扱う
- entry Ask／exit Bidを無視してmid価格だけで記録する
- 既存Flow Outcomeへ手動結果を混ぜる
- 手動記録が少ない段階で勝率・期待値を算出する
- 一件の記録から5M・10Mの有効性を宣言する

## 5. 収集後の判定

一定期間と十分な独立Episodeが蓄積した後に、次を分けて集計する。

1. Binance Episodeの事後ラベル
2. 手動判断による見送り率・判断遅延
3. HFM実約定のspread・slippage・net結果

この3つを混ぜずに、手動執行がオーダーフロー原理の検証を歪めていないか確認する。

## 6. 現在の状態

- 架空の手動取引記録は作成していない
- ledgerは最初の実記録時にCLIが作成する
- UI、DB、自動発注は未接続
- 成績集計は未開始

