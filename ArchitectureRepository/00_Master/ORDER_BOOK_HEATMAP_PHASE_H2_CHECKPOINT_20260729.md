# Order Book Heatmap GO-H2 checkpoint

開始／更新: 2026-07-29 06:20 JST  
branch: `feature/footprint-dom-tape`  
承認範囲: user `GO-H2` — pure Heatmap core only

## 完了

- `webapp/static/orderbook_heatmap.js` を追加（UMD、Node／browser共通pure core）。
- `validateBookPayload`、bounded `HeatmapBookStore`／`HeatmapTradeStore`、display bucket、time columns、duration-weighted raster、Q95 logarithmic scale、trade bubble aggregationを実装。
- `tests/webapp/test_orderbook_heatmap_core.py` を追加し、Node／Python契約を固定。
- sequence gap保持の不具合を契約テストで検出・修正。

## 未実施（H2範囲外）

- Canvas、central mode switch、tooltip／keyboard UI
- Time & Sales callback接続
- runtime restart、image build、deployment、persistent depth history

## 検証

- H2 core＋H1 book update: **13 passed**。
- `pytest -q tests/webapp`: 111 passed、15 errors（既存テストfixtureが `C:\Users\user\AppData\Local\Temp\pytest-of-user` のPermission deniedで起動不能）。H2テスト起因のfailureは0。
- Node syntax check: PASS。

## rollback／次の再開位置

H2差分は新規JS／契約テストのみ。rollbackはこの2 fileを対象とし、H1・Footprint・Tape・3段チャートへ触れない。次はユーザー明示GO-H3でCanvas／mode UIへ進む。
