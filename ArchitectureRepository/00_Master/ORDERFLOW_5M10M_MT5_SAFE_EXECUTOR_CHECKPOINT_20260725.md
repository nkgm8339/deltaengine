# MT5安全制約付きテスト発注器 checkpoint

実装日: 2026-07-25

## 実装内容

- `Delta_Engine_Pro4web/mt5/HFMSafeTestExecutor.mq5`
- `Delta_Engine_Pro4web/mt5/HFMSafeTestExecutor_README.md`

## 固定した制約

- 初期値はSHADOW（発注しない）
- volumeは0.01以外を拒否
- ブローカー最小volumeが0.01を超える場合は拒否
- MagicNumber対象の同時保有は1件まで
- Stop Loss必須、危険側のSLは拒否
- スプレッド上限を設定した場合は超過発注を拒否
- 共通フォルダの緊急停止flagで新規発注停止と対象ポジション決済
- LIVEには明示的な二重入力が必要
- 全ての判断を共通フォルダのJSONL監査ログへ記録

## 未完了・使用禁止条件

- MetaEditor/MT5実環境でのコンパイル確認は未実施
- HFMデモ口座での発注・SL・緊急停止試験は未実施
- LIVE入力は有効化していない
- 利益性は検証していない

MetaEditorでコンパイルし、デモ口座でSHADOW → 発注 → SL → 緊急停止の順に確認するまで、LIVE注文には使用しない。
