# Persistent Depth History PD6 30分 Soak 完了報告

実施日: 2026-07-29 (JST)  
対象: production writer を有効化した `Delta_Engine_Pro4web`

## 判定

30分の連続観測を完了し、PD6 の短時間 soak は PASS。データ削除、purge、schema migration は行っていない。

## 最終実測

- API health: `GREEN`
- sequence gap: `0`
- WS reconnect: `0`
- pipeline exceptions: `0`
- Tape: dropped `0`, pending `0`, send failures `0`, balanced `True`
- event lag: `436ms`
- memory RSS: `612MB`
- depth history: closed `.jsonl` `10`、manifest `10`、open `.part` `1`
- ファイル総数: `21`
- 使用量: `13,350,873 bytes`（約13.35MB）
- C: 空き: `97,350,770,688 bytes`

## ログ確認

観測期間のコンテナログに `ERROR`、`Traceback`、`Exception`、`CRITICAL`、gap/reconnect 異常は検出されなかった。

## 残課題

24時間 soak、保持期限と purge の設計・実装、replay API、ブラウザ hydration は PD7 以降で扱う。保持ポリシーが確定するまで自動削除は導入しない。
