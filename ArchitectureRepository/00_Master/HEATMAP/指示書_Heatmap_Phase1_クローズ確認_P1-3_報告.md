# [完了] 指示書_Heatmap_Phase1_クローズ確認_P1-3

- 稼働時間: 2026-07-29 20:36:55 JST起動確認、20:38:45 JST停止要求
  - コンテナ稼働確認から約110秒
  - rawセグメント記録時間は20:37:05～20:38:52 JST、約107秒
- 停止方法: `docker compose stop deltaengine_clone`
- コンテナ終了コード: 0
- shutdown Traceback: 無
  - `AttributeError`: 無
  - `RecorderTee`由来エラー: 無
  - `depth history recorder failed`: 無
- 最新セグメント:
  - JSONL: `raw_depth.20260729T113705.315567Z.jsonl`
  - サイズ: 1,444,501 bytes
  - manifest: `raw_depth.20260729T113705.315567Z.jsonl.manifest.json`
  - manifestサイズ: 294 bytes
  - `.part`残存: 無
  - manifest `record_count`: 2,226
  - JSONL実行数: 2,226
  - record_count一致: Yes
  - manifest SHA-256: `4996675aadf74e1a65387203690bd000183f96ec6b5598f74c37665f67660adc`
  - 実ファイルSHA-256: `4996675aadf74e1a65387203690bd000183f96ec6b5598f74c37665f67660adc`
  - SHA-256一致: Yes
  - manifest `byte_size`: 1,444,501
  - 実ファイルサイズ: 1,444,501
  - byte_size一致: Yes
  - `closed_reason`: `close`
- 後始末:
  - `DEPTH_HISTORY_ENABLED=false`復帰: 確認済み
  - コンテナ停止: 確認済み
  - 記録データ: 削除せず保全

## 判定

**Phase 1完了**

## 逸脱事項

なし。
