# 指示書_Heatmap_Phase1_クローズ確認_P1-3
**作成日: 2026-07-29 / 発行: Claude(統括) / 対象: Claude Code**
**前提: 欠陥1修正済み(`e358a0f`)。欠陥2は問題なし判定(u=lastUpdateId)。Phase 1最終確認。**

---

## 目的

shutdown修正後、ライブで**最終セグメントのmanifestが正常に書かれる**ことだけを短時間で確認し、Phase 1を閉じる。P1-2で記録内容自体は検証済みのため、今回はshutdown正常性に絞る。

## Task 1: 短時間ライブ+正常停止

- `DEPTH_HISTORY_ENABLED=true` で起動
- **90秒程度**稼働
- コンテナ/WebAppを**正常にshutdown**(kill -9等の強制終了ではなく通常停止)

## Task 2: shutdown正常性の確認

1. 停止時ログに `AttributeError` や `RecorderTee` 由来のTracebackが**出ないこと**
2. `data_05M/depth_history_raw/symbol=BTCUSDT/` の最新セグメントについて:
   - `.part` が残っていない(=正常にクローズされ拡張子が外れた)こと
   - 対応する `.manifest.json` が存在すること
   - manifest の `record_count` と `.jsonl` 実行数が一致
   - manifest の `sha256` と実ファイルのsha256が一致
   - manifest の `closed_reason` が `close`(正常停止)であること

## Task 3: 後始末

- `DEPTH_HISTORY_ENABLED` を **false** に戻す
- 記録データは保全(削除しない)

## 判定

- Traceback無し + 最新manifestが正常(.part無し、record_count一致、closed_reason=close) → **Phase 1完了**
- Traceback発生 or manifest不整合 or .part残存 → **停止して報告**

## 報告フォーマット

```
[完了/失敗/停止] 指示書_Heatmap_Phase1_クローズ確認_P1-3
- 稼働時間、停止方法
- shutdown Traceback: 無/有(有なら全文)
- 最新セグメント: .part残存有無、manifest record_count一致、sha256一致、closed_reason
- flag false復帰、データ保全
## 逸脱事項
```

## 禁止事項
- 強制終了(正常shutdownの確認が目的)
- 記録の常時有効化、データ削除
- index.html(別件UIテスト)変更、Phase 2着手
