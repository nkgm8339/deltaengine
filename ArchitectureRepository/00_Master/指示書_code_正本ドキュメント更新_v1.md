
# 指示書: 正本ドキュメント更新

code kun,

calibration_log の反映に合わせ、正本ドキュメントの更新もお願いしたい。以下の手順を、確認や許可を求めずに即座に実行してくれ。

## 更新対象ファイル

以下の4ファイルのバージョンアップと、旧版ファイルの削除を行え。

1. `DataNormalizer` v3.3 → v3.4
   - 変更内容: §6 Parquet Schema に candles テーブル追記
2. `MarketDataSchema` v3.3 → v3.4 
   - 変更内容: Candle Record の timeframe フィールド追記
3. `WebSocket` v3.1 → v3.2
   - 変更内容: §4.8 TICK/CANDLE の仕様と §7 Config に candle パラメータ追記  
4. `Database` v3.1 → v3.2
   - 変更内容: §3.5 Candle スキーマ追記

## 手順

1. 上記4ファイルを新バージョンで作成せよ。ファイル名の数字部分をインクリメントし、変更内容を反映させること。

2. 対応する旧バージョンのファイルを削除せよ。
   - `DataNormalizer_v3.3.md`
   - `MarketDataSchema_v3.3.md`
   - `WebSocket_v3.1.md`
   - `Database_v3.1.md`

3. 作業完了後、以下のフォーマットで報告せよ。
```
お館様、
  
code です。正本ドキュメントの更新が完了しました。
  
- 新規作成: (4ファイルをリスト)
- 旧版削除: (4ファイルをリスト)
  
ご確認ください。
```

以上だ。念入りに、しかし迅速に頼む。web への確認は不要だ。

