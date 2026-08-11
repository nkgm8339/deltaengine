# Big Trades V2 Phase 0 Runtime／Browser Baseline

取得日: 2026-08-12

## Runtime identity

- container: `delta_engine_pro4web-deltaengine_clone-1`
- container ID: `37ed40868792`
- observed uptime: 28 hours
- app URL: `http://127.0.0.1:18080`
- TCP 18080: open
- TCP 8080: closed
- TCP 15555: open
- app version: `v3.6.21`

工程0では既に稼働していたcontainerを再起動していない。config変更、image rebuild、service restartは0件。

## HTTP／health

| endpoint | HTTP | result |
|---|---:|---|
| `/health` | 200 | `{"status":"ok"}` |
| `/api/version` | 200 | `{"version":"v3.6.21"}` |
| `/api/health` | 200 | state `RED` |
| `/api/stats` | 200 | JSON response received |

`/api/health`のRED理由は開始前runtimeのmemory checkである。

```text
memory level = RED
rss = 2066 MB
detail = rss 2066MB
```

同じhealth sampleで次はGREENだった。

- sequence gap window: 0。
- WebSocket reconnect window: 0。
- pipeline exception window: 0。
- last bar age: 41 seconds。
- event lag: 0 ms。
- Tape: dropped 0、pending 1、send failures 0、balanced true。

これはBig Trades実装前baselineであり、工程0では修正しない。

## `/api/stats` selected baseline

| field | value |
|---|---:|
| `book_synced` | true |
| `book_gaps_detected` | 10 |
| `book_resyncs` | 10 |
| `book_projection_send_failures` | 0 |
| `tape_accepted_trades` | 2,640,652 |
| `tape_sent_trades` | 2,640,652 |
| `tape_dropped_trades` | 0 |
| `tape_send_failures` | 0 |
| `tape_accounting_balanced` | true |
| `ws_queue_qsize` | 4 |
| `ws_queue_high_watermark` | 2,355 |
| `ws_queue_overflow_count` | 0 |
| `receiver_queue_high_watermark` | 10,000 |
| `receiver_queue_overflow_count` | 9,122 |
| `receiver_queue_dropped_by_kind.depth` | 241 |
| `receiver_queue_dropped_by_kind.trade` | 8,881 |
| `storage_queue_pending` | 0 |
| `storage_queue_high_watermark` | 1,601 |
| `footprint_write_failures` | 0 |
| `ui_ticks_published` | 2,640,652 |
| `ui_ticks_sent` | 383,112 |
| `ui_ticks_coalesced` | 2,257,540 |

開始前runtimeにはreceiver queue overflow／drop累計が存在する。Big Trades実装後の比較で、この値を新規問題と誤分類しない。増加量と発生時間を別途比較する。

## Browser capture条件

- browser engine: Chromium 151.0.7922.76
- headless: true
- viewport: 1280×900
- device scale factor: 1
- initial navigation HTTP: 200
- observation: DOMContentLoaded後15秒
- screenshot: `existing_app_1280x900_full.png`
- screenshot dimensions: 1280×1644
- screenshot bytes: 576,123
- screenshot SHA-256: `BCE4A81E7A1AD279AAC0773B0E0ACE6519FBCF7E2A861B57B5F3C132B56F6831`

## Existing UI state

- body class: `notranslate phase5-fusion`
- chart title: `PRICE × FLOW RESPONSE`
- chart bars: `80 bars`
- page horizontal overflow: 0 px (`scrollWidth=clientWidth=1280`)
- full document height: 1,644 px
- visible banner: `MARKET DATA SYNCING — LIVE DECISION DATA DISABLED · WAITING_FOR_FRESH_TICK`
- Tape UI state: `TAPE GAP`
- Tape UI count: `HIST 1000 · LIVE 815 · KEPT 500/500 · SHOWN 500 · DOM 32/32 · GAPS 1 · RENDER P95 5.00ms`
- Console messages: 0
- page errors: 0
- failed browser requests: 0

## Fixed geometry at 1280×900

値はCSS pixel、page load後15秒時点。

| selector | x | y | width | height | display |
|---|---:|---:|---:|---:|---|
| `#topbar` | 10 | 44 | 1,260 | 62 | flex |
| `#bottom` | 10 | 118 | 1,010 | 552 | flex |
| `#chartwrap` | 11 | 273 | 1,008 | 396 | grid |
| `#chart` | 15 | 273 | 658 | 392 | block |
| `#liveobservation` | 1,032 | 118 | 238 | 1,116 | grid |
| `#main` | 10 | 682 | 1,010 | 552 | grid |
| `#center` | 10 | 682 | 770 | 552 | block |
| `#right` | 788 | 682 | 232 | 552 | block |
| `#fpstage` | 11 | 717 | 768 | 467 | block |
| `#fpcanvas` | 11 | 717 | 768 | 467 | block |
| `#heatmapcanvas` | 0 | 0 | 0 | 0 | none／hidden |
| `#tape` | 788 | 682 | 232 | 552 | flex |
| `#tapeviewport` | 789 | 872 | 230 | 293 | block |
| `#flowtop` | 10 | 1,246 | 1,260 | 388 | grid |
| `#flowpanel` | 10 | 1,246 | 1,260 | 198 | flex |
| `#flowbody` | 11 | 1,281 | 1,258 | 162 | block |

Big Trades実装後、protected 3段chartについて最低限`#bottom`、`#chartwrap`、`#chart`のx、y、width、heightを同じviewportで比較し、delta 0 pxを要求する。

## Local network responses

次のrequestは全てHTTP 200だった。

- `/`
- `/static/footprint_canvas.js`
- `/static/time_sales.js`
- `/static/market_freshness.js`
- `/static/orderbook_heatmap.js`
- `/api/history/candles?limit=300`
- `/api/history/candles?limit=3&timeframe=1d`
- `/api/history/time-sales?limit=500`
- `/api/history/footprints?limit=40&timeframe=1m`
- `/api/version`
- `/api/history/flow-response?limit=5000`
- `/api/history/open-interest?limit=2500`
- `/api/history/combined-context?timeframe=5m&limit=1`
- `/api/history/time-sales?limit=500&symbol=BTCUSDT`

## WebSocket baseline

- URL: `ws://127.0.0.1:18080/ws`
- browser observation中のsocket instance: 2
- failed WebSocket request: 0

15秒観測中の受信frame count:

| message type | count |
|---|---:|
| `HELLO` | 2 |
| `TICK` | 48 |
| `BAR_UPDATE` | 29 |
| `TAPE_UPDATE` | 37 |
| `BOOK_UPDATE` | 39 |
| `FLOW` | 8 |
| `FLOW_RESPONSE` | 8 |
| `HEALTH` | 3 |
| `STATS` | 3 |
| `SPOT_PRICE` | 25 |
| `MARKET_HEARTBEAT` | 10 |
| `ABSORPTION_STATE` | 2 |
| `ANALYSIS` | 1 |
| `CANDLE` | 1 |
| `HFM_QUOTE` | 2 |
| `OI` | 1 |

## Phase 0 classification

- UI render: PASS。
- HTTP resources: PASS。
- Console error: PASS、0件。
- page error: PASS、0件。
- browser request failure: PASS、0件。
- WebSocket receive: PASS。
- horizontal overflow: PASS、0 px。
- health GREEN: FAIL、memory RED。
- live freshness: FAIL、syncing banner／Tape gap表示。
- source changeによる回帰: 該当なし、source変更前baseline。
