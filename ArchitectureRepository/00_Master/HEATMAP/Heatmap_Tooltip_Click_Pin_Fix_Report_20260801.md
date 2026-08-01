# Heatmap tooltip click pin fix — 2026-08-01

## 変更

`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js` のCanvas操作を修正。

- 左クリック時に現在点の説明をツールチップへ表示。
- 選択中はマウス移動・mouseleaveでツールチップを上書き／消去しない。
- 既存どおり `Esc` で選択とツールチップを解除。
- 同じ位置を左クリックすると固定を解除し、別位置のクリックでは固定位置を切り替える。

## 検証

- 既存ヒートマップコアテスト: 6 passed（時刻軸修正時点）。
- 変更は未コミット。
