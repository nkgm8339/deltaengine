# Big Trades V2 工程5 UI 完了報告

取得日時: 2026-08-12 JST

## 実装結果

- 既存中央chartへ`FOOTPRINT / HEATMAP / BIG TRADES`の独立3modeを追加した。
- Big Tradesを選択した時だけ専用Canvasとkeyboard／pointer handlerを有効にする。Footprint／Heatmapへ戻すと専用handlerを解除する。
- headerへMODE、INPUT、SIDE、MIN、MAX、INTENSITY、MARK AT、ZONES、STATE、CAL、APPLYを固定配置した。
- Manual／Autoでcontrolを消さず、unused側だけdisabledにする。
- MIN／MAXへ未承認値を埋めていない。production configの既存inactive defaultをUI上の選択値として表示していない。
- Canvasへcandle、closed zone、active zone、gap hatch、exact range connector、BUY／SELL marker、aggregate quantity、linked ordinal badge、selection、crosshair、tooltipを実装した。
- single-price zoneのauthoritative rangeは変更せず、Canvas上のminimum 3pxだけをvisual heightとして分離した。
- event 5,000件、zone 5,000件、interaction 20,000件のbounded store、ID dedup、content collision拒否、source order、history＋live mergeを実装した。
- stream UUID変更、sequence gap、drop検出時は`GAP RECOVERING`へ入り、REST hydration markerまで回復してから解除する。
- selected detailをEFFORT、RESULT、REPEATED AREA ACTIVITY、CANDLE RESULT、CONTEXT、SYSTEM FACTS、USER ASSESSMENT、LINEAGEの固定領域へ表示する。
- user assessmentはsystem factsから別配色／別DOMへ分離し、append／supersedeだけをPOSTする。評価対象時刻は選択zoneに属する最新source timeを使用する。
- 右側の既存Live Observation外寸を変えず、Big Trades選択中だけ専用のeffort／price result／horizon／read-only context表示へ切り替える。
- `webapp/big_trades_history.py`のzone detailへordered interactionsと全assessment historyを追加し、zone listへclosed source endとgap segmentsを追加した。

## 実browser条件

- URL: `http://127.0.0.1:18080`
- Chromium viewport: 1280×900、device scale factor 1
- runtime container: `37ed40868792`
- container restart: 0件
- production feature: `big_trades.enabled: false`
- Big Trades表示data: synthetic committed-history fixtureをPlaywright routeで供給
- 既存market／Tape／Book／Flow data: 稼働中WebSocketをread-only観測
- production DB write／migration: 0件

fixtureはUI描画、history merge、detail、lineage、gap、single-price zoneを確認するためのものであり、production threshold／activationではない。

## before／after geometry

Footprint表示直後とBig Trades表示後を同一page、同一viewportで比較した。

| protected selector | Δx | Δy | Δwidth | Δheight |
|---|---:|---:|---:|---:|
| `#bottom` | 0 | 0 | 0 | 0 |
| `#chartwrap` | 0 | 0 | 0 | 0 |
| `#chart` | 0 | 0 | 0 | 0 |
| `#main` | 0 | 0 | 0 | 0 |
| `#center` | 0 | 0 | 0 | 0 |
| `#right` | 0 | 0 | 0 | 0 |
| `#tape` | 0 | 0 | 0 | 0 |
| `#liveobservation` | 0 | 0 | 0 | 0 |
| `#flowtop` | 0 | 0 | 0 | 0 |

Big Trades専用領域:

| selector | x | y | width | height |
|---|---:|---:|---:|---:|
| `#btworkspace` | 11 | 767 | 768 | 466 |
| `#btcanvas` | 11 | 767 | 481 | 422 |
| `#btdetail` | 493 | 767 | 286 | 466 |
| `#btobservation` | 1,043 | 129 | 216 | 1,094 |

- document horizontal overflow: 0px（scrollWidth 1280 = clientWidth 1280）
- Footprint → Heatmap → Footprint復帰後もprotected geometryは同一。
- Big Trades切替でLayout Watchdogが`#fpstage`の意図した表示停止をwarning記録した。browser errorではない。

## Browser／Network／WebSocket

- initial HTTP: 200
- `/static/big_trades.js`: 200
- Big Trades hydration: 200
- Big Trades settings read: 200
- selected zone detail: 200
- Console error: 0
- page error: 0
- failed request: 0
- WebSocketでHELLO、TICK、BAR_UPDATE、BOOK_UPDATE、TAPE_UPDATE、FLOW、FLOW_RESPONSE、HEALTH、STATS等を受信した。
- Canvas warm render p95: 6.4ms
- browser store: event 2／5,000、zone 2／5,000、interaction 2／20,000、collision 0

完全なNetwork／WebSocket frame count／全bounding boxは`browser_acceptance.json`に保存した。

## Screenshot

- before: `footprint_before_1280x900_full.png`
  - SHA-256: `F25F172BF0D4B8FBD2CE6B885CF89C16D97AF6341F426CE44D3B9211ECDA81E7`
- after: `big_trades_after_1280x900_full.png`
  - SHA-256: `258081239EBC9F8E0F55FEECFA36318A762B983678AC49F383BDC70729277C1B`

## Test結果

- Big Trades UI＋API: `51 passed in 11.12s`
- Big Trades UI単体: `42 passed in 1.50s`
- WebApp全体: `257 passed, 1 failed in 21.98s`
- 既知failure除外WebApp: `257 passed, 1 deselected in 21.54s`
- Node `big_trades.js`構文検査: PASS
- `index.html` inline script構文検査: PASS
- protected source SHA-256: 9／9 baseline一致
- `git diff --check`: whitespace error 0（CRLF warningのみ）

残る1 failureは工程0から固定済みの既知test:

```text
tests/webapp/test_dom_tape_fusion_ui.py::test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation
```

期待文字列`body.phase5-fusion #right>#left{display:none!important}`と、実装済みの構造的同値selectorとの差であり、Big Tradesによる新規failureではない。

## 非変更確認

- Flow Price Response、Flow detector、CVD、Footprint、Absorption、Imbalance、Time & Sales、Footprint Canvas、Heatmap Canvasのprotected source hashは9／9一致。
- 3段chart、Tape、中央外枠、右観測外枠、下段indicatorのgeometry deltaは0px。
- production DB最終更新時刻は2026-08-12 02:52:22のままで、工程5のtest／captureはproduction DBへ書いていない。
- container ID、start time、restart count 0は維持されている。

## Evidence files

- `browser_acceptance.json`
- `capture_browser_phase5.py`
- `footprint_before_1280x900_full.png`
- `big_trades_after_1280x900_full.png`
