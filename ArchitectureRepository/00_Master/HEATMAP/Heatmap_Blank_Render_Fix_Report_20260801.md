# Heatmap blank-render fix — 2026-08-01

## 結論

板データは空ではなかった。WebSocket の `BOOK_UPDATE` は `SYNCED`、50 bid / 50 ask、数量非ゼロで到着していた。一方、表示軸と区間生成に取引所 `event_time` を使っていたため、配信遅延時に有効な板フレームがライブ表示区間から外れ、ラスタが全ゼロ (`Q95 0.000`) になる不具合があった。

## 修正

対象: `Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js`

- `frameRenderTime()` を追加。
- 表示対象フレーム選択、描画区間生成、最新表示時刻を `projection_time` 優先に変更。
- `event_time` は市場イベント時刻として保持し、表示時刻と混同しないようにした。

対象: `Delta_Engine_Pro4web/tests/webapp/test_orderbook_heatmap_core.py`

- event time が遅れている板でも projection time で描画区間が生成される回帰テストを追加。

## 検証

- `tests/webapp/test_orderbook_heatmap_core.py`: **6 passed**
- フレーム予算 + コア: **11 passed**
- 全体 pytest: 実行時間上限で完了せず（テスト失敗ではなく、pytest 出力 flush の `OSError: [Errno 22]` でタイムアウト）。

未コミット。ブラウザ確認はコンテナの静的JSへ反映後、ページをハードリロードして行う。
