# MT5デモ検証 runbook

目的: `HFMSafeTestExecutor` の注文経路と安全制約だけをデモ口座で検証する。利益性・戦略優位性の検証ではない。

## 0. 事前条件

- HFM MT5デモ口座を使用する。
- 対象チャートのシンボル名を確認する（`BTCUSD`等を推測しない）。
- MetaEditorで `HFMSafeTestExecutor.mq5` をコンパイルする。
- `EnableLiveOrders=false` のままEAをチャートへ接続する。
- 自動売買を有効化するが、EAはSHADOWなので発注しない。

## 1. SHADOW確認

共通フォルダのコマンドファイルへ、現在価格に対して妥当なSLを持つデモ用コマンドを1件だけ出力する。EA監査ログに `SHADOW` が出て、ポジションが増えないことを確認する。

## 2. デモ発注確認

`EnableLiveOrders=true` と `LiveConfirmation=I_UNDERSTAND_LIVE_01_LOT` を設定する。volumeは0.01、MagicNumberは専用値、同時保有は1件に制限する。スプレッド上限を設定し、SLを必ず指定する。

注文が1件だけ作成され、監査ログに `SENT` またはブローカー拒否理由が残ることを確認する。拒否は失敗ではなく、理由を記録して終了する。

## 3. SL確認

デモ注文のSLがサーバー側に存在することをMT5画面で確認する。EA停止後もSLが残ることを確認する。

## 4. 緊急停止確認

共通フォルダに `DeltaEngine_HFM_EMERGENCY_STOP.flag` を作成する。EAが新規コマンドを処理せず、MagicNumber対象のデモポジションを決済することを確認する。確認後、flagを削除する。

## 5. LIVE移行条件

次の全てが揃うまでLIVEへ移行しない。

- MetaEditorコンパイル成功
- SHADOW確認済み
- デモ発注・SL・EA停止後のSL残存を確認
- 緊急停止確認済み
- HFMシンボル名・最小volume・契約仕様を確認
- スプレッド上限を事前固定
- LIVE移行の明示承認

本runbook実施前は、実口座での注文を行わない。
