# 目視確認手順: Phase 2-3 Stage 2 完了 — 動的ヒートマップ + Frame Budget 表示

- 作成: 2026-08-01
- 対象: お館様(PC上での操作)
- リポジトリ: DeltaEngine05M(`C:\Users\user\Desktop\DeltaEngine05M`)
- HEAD: `47a1dcd`(Task 3 commit済み)

---

## 目的

Stage 2 の3タスク(Task 1: frame source / Task 2: 動的供給 / Task 3: frame budget 表示)が揃った状態で、実際にブラウザ上でヒートマップが動作し、p95 `[PASS]`/`[OVER]` 表示が見えることを目視確認する。

---

## 手順

### Step 1: Docker 起動

```
cd C:\Users\user\Desktop\DeltaEngine05M\Delta_Engine_Pro4web
docker compose up --build
```

ビルド完了後、ログに起動メッセージが流れることを確認。エラーで停止した場合はログの最終20行をスクリーンショットで報告。

### Step 2: ブラウザアクセス

```
http://localhost:8080
```

### Step 3: 確認項目(スクリーンショット撮影)

以下の5点を確認し、各項目のスクリーンショットを撮影。

| # | 確認項目 | 期待 |
|---|---------|------|
| C1 | ページが表示される | localhost:8080 がエラーなく開く |
| C2 | ヒートマップ Canvas 領域 | Canvas が表示されている(データ有無は問わない) |
| C3 | `#heatmapstatus` バー | 画面上にステータス行が表示されている |
| C4 | p95 表示 | `RENDER P95 xxxms` の文字列が見える |
| C5 | Frame Budget ラベル | p95 の右に `[PASS]`(緑)または `[OVER]`(赤)が見える |

### Step 4: 動的フレームの確認

データが流れている場合(Binance WebSocket 接続中):
- ヒートマップが時間とともにスクロールしているか
- p95 値が周期的に更新されているか

データが流れていない場合(WebSocket 未接続 / recording なし):
- ヒートマップが静止または空でも C1-C3 が確認できれば OK
- p95 が `0.00ms` または表示なしでも、`#heatmapstatus` バー自体が存在すれば OK

### Step 5: 停止

```
docker compose down
```

---

## 報告

以下のいずれかで報告:
- スクリーンショット(C1-C5 が写っている画面キャプチャ)
- テキストで「C1-C5 OK」「Cx が NG: 状況説明」

動的フレームが流れていたかどうかも併せて教えてください。

---

## トラブル時

- Docker ビルドエラー: 以前の 14098 エラー再発の可能性あり。ログの最終20行を報告。
- ポート競合: `docker compose down` 後に再度 `up --build`。
- ページが開かない: `docker compose ps` の出力を報告。

以上。
