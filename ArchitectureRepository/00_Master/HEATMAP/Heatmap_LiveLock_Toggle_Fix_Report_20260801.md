# Heatmap LIVE LOCK toggle fix — 2026-08-01

## 原因

`hmlock` のクリック処理が常に `chart.returnLive()` を呼んでおり、ロック解除分岐が存在しなかった。

## 修正

- `OrderBookHeatmapCanvas.toggleLiveLock()` を追加。
- 解除時は現在の表示終端を `lockedEndTime` として保持し、履歴表示を停止。
- 再クリックで `returnLive()` へ戻す。
- UI表示を `LIVE LOCK` / `HISTORY LOCK` で切替。

## 検証

- ヒートマップコア＋フレーム予算テスト: **11 passed**
