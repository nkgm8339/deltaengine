# Order Book Heatmap V1 correction checkpoint

更新: 2026-07-29 11:26 JST  
branch: `feature/footprint-dom-tape`  
HEAD: `1134886430b7c48487cd4a9389a202acfa6ff53e`

## 承認範囲

ユーザーの2026-07-29 `GO`により、次を承認範囲とする。

- 現在の未完成Heatmap presentationをfeature flag OFFへ戻す
- GO-H2 pure coreの訂正
- GO-H3 Canvas／mode UIの訂正
- GO-H4 Tape linkage／gap visualizationの訂正
- GO-H5 integration／performance／実ブラウザ／回帰検証
- 訂正報告と再開可能なcheckpoint更新

GO-H6再配備、production flag enable、LIVE注文、Strategy runtime、MT5 algorithmic tradingは
今回の承認範囲外とする。

## 訂正開始時の確認済み事実

- `PROJECT_MEMORY.md`全1,318行とroot `AGENTS.md`を全文確認済み。
- Bookmap系V1正本は
  `ORDER_BOOK_HEATMAP_IMPLEMENTATION_INSTRUCTION_V1_20260729.md`。
- 旧`AA_仕様書_LiquidityHeatmap_WebUI_v1.md`は今回の判定基準に使用しない。
- 2026-07-29 10:42 JSTの実Chromium 1280×900で、HEATMAP mode選択後も
  Footprint Canvasが`hidden=true / display:block`で残った。
- Heatmap Canvasは親`#fpstage`の直下へ積まれ、親下端と同じ`y=1150`から開始し、
  `overflow:hidden`で全体がclipされた。
- live Time & Sales表示中もHeatmap trade storeは0件だった。
- price／time axis、Bookmap quantity palette、legend、bubble、Best／Ask／Last line、
  gap band、Heatmap固有control、tooltip、zoom／panは現描画経路に存在しない。
- H6文書はbrowser acceptanceを`UNCONFIRMED`と記録しながら
  `OPERATIONAL ACTIVATION PASS`としており、V1 acceptance criteriaと矛盾する。

## Dirty worktree保護

開始時worktreeにはHeatmap以前からの変更、persistent depth history、VWAP調査、
runtime／measurement artifactが混在する。broad stage、reset、checkout、cleanは行わない。
今回の変更はHeatmap訂正のexact fileだけへ限定し、既存のFlow Price Response、
3段チャート、Footprint、Tape、OIの計算意味を変更しない。

## 開始時検証

- runtime `/api/health`: GREEN
- current targeted Heatmap tests: `4 passed`
- browser page error: 0
- horizontal overflow: 0
- ただし上記はHeatmap表示完成を意味しない

## H2訂正完了

- `ORDER_BOOK_HEATMAP_ENABLED=false`へ戻した。
- `orderbook_heatmap.js`を次の契約で再実装した。
  - fail-closed validation
  - typed-array compact Book frame
  - 15分／9,000 Book frame／100,000 trade bounded store
  - historyを消さないBook gap／restart／disconnect／local stale marker
  - source Bookからのtick推定
  - 1／2／5／10 tick display bucket
  - event time step-held interval
  - gapを跨がないduration-weighted time column
  - visible Q50／Q95 logarithmic scale
  - bid／ask共通quantity palette
  - normalized Time Sales camelCaseとraw snake_case双方のTrade受理
  - trade bubble aggregation
  - `OrderBookHeatmapCanvas`の描画・操作core

H2検証:

- `node --check webapp/static/orderbook_heatmap.js`: PASS
- `tests/webapp/test_orderbook_heatmap_core.py`: **2 passed**

## H3／H4 source訂正完了

- feature flag false時はmode button、Heatmap Canvas、store、Tape callbackを起動しない。
- Footprint／Heatmap Canvasを同じ`#fpstage`へabsolute stackし、`hidden`をCSSで強制した。
- 1M／5M／15M、STEP AUTO／1／2／5／10、intensity、bubble、LIVE LOCKを追加した。
- price／time axis、Q50／Q95 legend、Best Bid／Ask／Last line、gap hatch、Tape marker、
  bubble、crosshair、copy可能detail、14px tooltipをCanvas rendererへ接続した。
- wheel／Shift+wheel、time／price drag、double click、keyboard、selectionを接続した。
- Time Sales正規化済みcamelCase tradeへTape stream IDを渡し、bubble storeへ受理できるようにした。
- Tape gap／restart resultを全batchでHeatmapへ渡すようにした。
- Tape row→Heatmap cursor、bubble→Tape rowの双方向selectionを接続した。

H3／H4 source検証:

- Heatmap core／UI contract: **11 passed**
- `orderbook_heatmap.js` syntax: PASS
- `index.html` inline script parse: PASS

## 現在の変更file

- `ArchitectureRepository/00_Master/ORDER_BOOK_HEATMAP_CORRECTION_CHECKPOINT_20260729.md`
- `Delta_Engine_Pro4web/webapp/static/index.html`
- `Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js`
- `Delta_Engine_Pro4web/tests/webapp/test_orderbook_heatmap_core.py`
- `Delta_Engine_Pro4web/tests/webapp/test_orderbook_heatmap_ui.py`

## 未完了

- H5検証
- completion correction report
- `PROJECT_MEMORY.md`訂正追記

## blocker

なし。

## 次の再開位置

`ORDER_BOOK_HEATMAP_ENABLED=false`へ戻し、H2 coreを正本仕様へ合わせて訂正する。
