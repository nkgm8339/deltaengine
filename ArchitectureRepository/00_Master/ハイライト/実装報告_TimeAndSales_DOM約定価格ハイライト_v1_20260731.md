# Time & Sales → LIVE DOM 約定価格ハイライト v1 実装報告

完了時刻: 2026-07-31 09:56:49 JST  
対象branch: `feature/footprint-dom-tape`  
開始HEAD: `ad4b47d59b4805048c1c6f5f2929480ef396ddc5`  
状態: **source実装・自動試験・実Edge・実WebSocket検証PASS**

## 1. 結論

Time & Salesの新規受理約定を、同じ価格bucketのLIVE DOM受け側半セルへ
400msの黄色pulseとして結び付ける機能を実装した。

- `BUY`はpassive `ASK`
- `SELL`はpassive `BID`
- sourceは正常化・dedup後の新規`TAPE_UPDATE` tradeだけ
- history hydrate、`TICK`、Flowからは発火しない
- 約定後に板levelが消えても、DOMが`SYNCED`で同price rowが存在すればpulseだけを満了まで残す
- DOM数量は保持・復元しない
- fail-closed、disconnect、stream／symbol変更時は古いpulseをclear
- 最大256 active entry、Canvas当たり一個のRAF scheduler
- 同price／same sideの連続約定はcoalesceして最新約定から400msへ延長

Flow Price Response、3段チャート、8パターン、OI、Footprint計算、
Tape acceptance、Heatmap、Hook、Strategy、executionは変更していない。

## 2. 実装構造

### 2.1 Pulse domain

`footprint_canvas.js`へ`DomTradePulseStore`を追加した。

責務:

- aggressive sideからpassive DOM sideへの変換
- exact priceからnative tick indexへの正規化
- current display multiplierへのbucket投影
- monotonic 400ms expiry
- coalesce
- capacity 256
- lifecycle clear
- diagnostic counter

### 2.2 Canvas overlay

既存static Footprint baseを再構築せず、`domTradePulse` dirty layerで描画する。

描画順:

```text
Footprint base
  -> current LIVE DOM
    -> DOM Trade Pulse
      -> current price reference
        -> user selection
```

色:

- fill: `#FFD54A`、初期alpha 0.5
- border: `#FFD54A`、初期alpha 0.96
- 70% hold、残り30% fade

### 2.3 accepted trade coordinator

`index.html`へ`onAcceptedTapeTrades()`を追加し、
既存`TimeSalesView.onAcceptedTrades`から次のoptional consumerへ分配する。

- DOM Trade Pulse
- Order Book Heatmap

consumerごとに独立した例外境界を持ち、一方の表示失敗で
Tape acceptanceや他方のconsumerを停止させない。

`time_sales.js`は本件では変更していない。
開始前から存在したHeatmap用`onAcceptedTrades`契約をそのまま利用した。

## 3. 機能境界

feature flag:

```text
DOM_TRADE_PULSE_ENABLED = true
DOM_TRADE_PULSE_DURATION_MS = 400
```

rollbackはflagをfalseへ変更するだけで、Tape、DOM、Heatmap、storageを止めない。

V1ではbackend、WebSocket payload、history API、DuckDB／Parquet schemaを変更していない。

## 4. 新規自動試験

新規:

- `Delta_Engine_Pro4web/tests/webapp/test_dom_trade_pulse_ui.py`

結果:

- **5 passed**

確認内容:

- BUY→ASK／SELL→BID
- invalid side／price拒否
- exact tick／display bucket
- 399ms active／400ms expiry
- same price／same side coalesce
- opposite side独立
- capacityとeviction
- ASK／BIDのCanvas半セル座標
- 現在book levelが無い場合のoverlay
- named accepted-trade coordinator
- `TICK`／history非発火
- Tape stream／Book stream／fail-closed／feature境界clear

## 5. 回帰

### 5.1 JavaScript

- `node --check footprint_canvas.js`: PASS
- `index.html` inline script compile: PASS
- `git diff --check footprint_canvas.js`: PASS

### 5.2 WebApp

- **142 passed, 1 failed**

failure 1件はHL-0で実装前から確認済みの既存Heatmap差分である。

```text
test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation
```

旧testは`body.phase5-fusion #right>#left`を要求するが、
開始前の現sourceは`body.phase5-fusion #main>#left`である。
本件による新規failureではない。

### 5.3 repository全体

- **770 passed, 1 failed, 1 skipped**
- failureは上記と同じbaseline 1件
- 新規failure 0

## 6. 6,000 trade負荷

同一時刻の正常trade 6,000件をPulse Storeへ投入した。

- trades received: 6,000
- pulses started: 40
- coalesced: 5,960
- active entries: 40
- max capacity: 256
- eviction: 0
- skipped: 0
- ingest: 5.994ms
- overlay draw p95: 0.138ms
- overlay draw max: 1.348ms

無制限Map、trade単位timer、Canvas全面base再構築は発生していない。

## 7. deterministic実Edge

環境:

- Microsoft Edge headless
- viewport: 900×600
- Canvas: 768×467
- DOM `domX`: 618
- DOM center `domMid`: 691
- DOM width: 146
- row height: 18.95

### 7.1 BUY

入力:

```text
BUY 2.914 @ 64900.0
```

結果:

- passive side: ASK
- draw x: 692
- `692 > domMid 691`
- active確認: 169.4ms
- 約定後に64900.0のAsk levelをbookから削除
- `askStillPresent == false`
- pulse `activeEntries == 1`
- 数量を復元せず黄色overlayだけを維持

### 7.2 SELL

入力:

```text
SELL 1.250 @ 64899.9
```

結果:

- passive side: BID
- draw x: 619
- `619 < domMid 691`
- active確認: 100.3ms
- 最初のexpiry pollで406.4msに消去確認

### 7.3 描画品質

- Canvas render p95: 0.5ms
- page overflow: 0
- Tape gap: false
- Tape dropped: 0
- browser error: 0
- schedulerはexpiry後に停止

## 8. 実ライブWebSocket

local runtimeの実`/ws`へ独立Edge harnessを接続し、
実`BOOK_UPDATE`と実`TAPE_UPDATE`を現行Canvas／Tape moduleへ流した。

### 8.1 LIVE SELL

- trade ID: `7941933073`
- event time: `2026-07-31T00:51:43.196Z`
- price: `64687.20`
- quantity: `0.001`
- side: `SELL`
- passive side: `BID`
- draw x: 619
- DOM center: 691
- Book state: `SYNCED`
- Tape gap: false
- dropped: 0

### 8.2 LIVE BUY

- trade ID: `7941935464`
- event time: `2026-07-31T00:53:19.019Z`
- price: `64678.30`
- quantity: `0.002`
- side: `BUY`
- passive side: `ASK`
- draw x: 692
- DOM center: 691
- Book state: `SYNCED`
- Tape gap: false
- dropped: 0

両sideともtrade ID、side、price、passive side、Canvas座標を同一browser session内で照合した。

## 9. 証拠画像

- `EVIDENCE_DOM_PULSE_BUY_ASK_LEVEL_REMOVED_20260731.png`
  - Ask quantity level削除後も黄色pulseが残るframe
  - SHA-256:
    `62ADABDBD21F95B019022AF68F72C8D47536E7613C00ABD624D2BBCAC3E70506`
- `EVIDENCE_DOM_PULSE_SELL_BID_20260731.png`
  - Sell約定に対応するBid半セルpulse
  - SHA-256:
    `DC9701FB196851C872057E6DB2E0A52BDDDB6F0FAFA3947FC352250888965E31`
- `EVIDENCE_DOM_PULSE_EXPIRED_20260731.png`
  - expiry後にpulseが消えたframe
  - SHA-256:
    `4D6EEE8DC2CE09198F87FD8D02719502D17AC55B7D19789938E4BD40B8A5B6D2`

3画像の内容とhashが異なることを確認した。

## 10. Runtime状態

- container:
  `delta_engine_pro4web-deltaengine_clone-1`
- container status: Up
- sourceは既存static bind mountへ置かれている
- runtime pageが新`ingestDomTradePulses` APIとenabled flagを読み込むことを実Edgeで確認済み
- container restart、image build、deploymentは行っていない

検証中、root `FileResponse`が断続的にtimeoutし、logに`OSError: [Errno 9] Bad file descriptor`が
一度記録された。これは本件開始前からdirtyな`main.py`／runtime側の限定運用問題であり、
Pulse sourceのCanvas／Tape経路とは独立している。

その後:

- `/api/health`: HTTP 200
- overall: YELLOW
- pipeline: GREEN
- Tape: GREEN
- Tape dropped: 0
- direct `/ws`: 接続・実約定検証PASS

root responseの安定化目的でcontainer restartは行っていない。

## 11. 変更file

本件source:

- `Delta_Engine_Pro4web/webapp/static/footprint_canvas.js`
- `Delta_Engine_Pro4web/webapp/static/index.html`
- `Delta_Engine_Pro4web/tests/webapp/test_dom_trade_pulse_ui.py`

文書／証拠:

- `ArchitectureRepository/00_Master/ハイライト/指示書_TimeAndSales_DOM約定価格ハイライト_v1_20260731.md`
- `ArchitectureRepository/00_Master/ハイライト/実装_CHECKPOINT_TimeAndSales_DOM約定価格ハイライト_v1_20260731.md`
- 本報告
- 証拠PNG 3件
- `ArchitectureRepository/00_Master/PROJECT_MEMORY.md`

開始前dirtyのため本件変更扱いにしない:

- `Delta_Engine_Pro4web/webapp/static/time_sales.js`
  - Heatmap作業由来の`onAcceptedTrades`追加
  - 本件は内容を変更していない

## 12. 保護境界

- Flow Price Response無変更
- 完成済み3段チャート無変更
- 8パターン無変更
- OI無変更
- Footprint／POC／VA／Imbalance計算無変更
- Tape normalization／dedup／gap／drop accounting無変更
- Heatmap consumer維持
- backend／storage／payload schema無変更
- Hook／Strategy／execution無変更
- LIVE注文0

## 13. 未実施

- container restart
- image build
- commit
- push
- ユーザー側browserでの最終目視

source実装、direct live data経路、Canvas実描画はPASSしている。
root FileResponseの断続的timeoutを解消するruntime restartは、
本件とは別の明示承認境界として残す。
