# Time & Sales → LIVE DOM 約定価格ハイライト 実装指示書 v1

作成日: 2026-07-31 JST  
状態: **実装済み／検証済み／コミット対象**  
対象: DeltaEngine05M WebApp  
機能名: **DOM Trade Pulse**

---

## 0. この指示書の決定

Time & Salesへ新しい約定が表示された瞬間、その約定価格に対応する
LIVE DOMの受け側セルを、黄色で一度だけ短時間ハイライトする。

例:

```text
Time & Sales
BUY 2.914 @ 64.9K

LIVE DOM
64.9K の ASKセルを黄色で400msハイライト
```

side対応は固定する。

| Time & Salesのside | 市場で起きたこと | ハイライト対象 |
|---|---|---|
| `BUY` | aggressive buyerがpassive Askを取った | 同価格の`ASK`半セル |
| `SELL` | aggressive sellerがpassive Bidへぶつけた | 同価格の`BID`半セル |

既定表示時間は **400ms** とする。  
許容調整範囲は300〜500msだが、初期実装は400msへ固定する。

この機能は売買シグナル、Large Trade判定、吸収判定、板消滅判定ではない。
目的は、約定とDOM価格セルの視覚対応を即座に読めるようにすることだけである。

---

## 1. 場当たり的な実装の禁止

次の方法は禁止する。

- `onTapeUpdate()`内へCanvas座標計算を直接書く
- Time & SalesのDOM rowから表示文字列を読み戻して価格を推測する
- `TICK`から約定を再構成する
- BUY／SELLの色だけをDOM全体へ一括点滅させる
- 約定ごとに独立した`setTimeout`を無制限に生成する
- 現在のDOM数量が存在する場合だけ、その数量セルへ一時CSS classを付ける
- 約定価格を文字列一致だけでDOM rowへ結び付ける
- highlightのためにBOOK／TAPEの新規backend経路を重複実装する
- highlightのためにWebSocket payloadへ同じ価格・sideを再追加する
- highlightをFlow Event、Hook、Strategy、Order Triggerへ接続する
- highlightの都合でFootprint／DOM共通価格geometryを分離する
- highlightの都合でDOM、Time & Sales、3段チャートの位置・高さ・幅を変える

実装は次の一方向経路へ統一する。

```text
authoritative accepted trade
  -> TAPE_UPDATE
    -> TapeStore normalization / dedup / sequence accounting
      -> accepted-live-trades callback
        -> DOM Trade Pulse coordinator
          -> CanvasChart pulse store
            -> LIVE DOM専用overlay layer
```

データ受理、状態保持、価格bucket化、描画、寿命管理を分ける。
受信handlerへ描画の都合を混ぜない。

---

## 2. 着手前に必ず読む正本

実装担当者は変更前に、最低限次を全文または該当正本範囲まで確認する。

1. `ArchitectureRepository/00_Master/PROJECT_MEMORY.md`
2. `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_FUSION_IMPLEMENTATION_INSTRUCTION_V2_20260728.md`
3. `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_FUSION_PREIMPLEMENTATION_AMENDMENT_V2_1_20260728.md`
4. `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_PHASE5_COMPLETION_REPORT_20260728.md`
5. `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_PHASE6_COMPLETION_REPORT_20260728.md`
6. `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_READABILITY_CHECKPOINT_20260729.md`
7. `ArchitectureRepository/30_Modules/WebApp/Specifications/WebSocketPayload_Spec_v1.md`
8. `Delta_Engine_Pro4web/webapp/static/time_sales.js`
9. `Delta_Engine_Pro4web/webapp/static/footprint_canvas.js`
10. `Delta_Engine_Pro4web/webapp/static/index.html`
11. `Delta_Engine_Pro4web/tests/webapp/test_dom_tape_fusion_ui.py`

ユーザーの最新の明示指示と本指示書が、過去の一般的なUI案より優先する。

---

## 3. 現行実装について確認済みの事実

2026-07-31時点の現行実装は次の構造である。

- `TAPE_UPDATE`だけがTime & Salesのライブsourceである
- `time_sales.js`の`normalizeTrade()`がprice、quantity、notional、side、event timeを検証する
- `TapeStore`がhistory／live dedup、sequence gap、restart、500件保持を管理する
- `TimeSalesView.ingestBatch()`は新規受理約定を`onAcceptedTrades`へ渡せる
- history hydrateの`mergeHistory()`は`onAcceptedTrades`を呼ばない
- LIVE DOMは`footprint_canvas.js`の`CanvasChart`内へ描画される
- FootprintとLIVE DOMは同じ`frame.rows`、tick、display multiplier、price stepを使う
- DOMは左半分がpassive Bid、右半分がpassive Askである
- `prepareBook()`は`SYNCED`以外を空levelにする
- `BOOK_UPDATE`は`liveDom` dirty layerで更新される
- Canvasはstatic Footprint baseとLIVE DOM overlayを分けて再利用する
- `index.html`ではTime & Salesの`onAcceptedTrades`がHeatmap trade ingestionにも使われている

したがって、V1ではbackend、storage、WebSocket schemaの変更は不要である。
既存`onAcceptedTrades`を正式な分岐点として使う。

---

## 4. 表示が意味する事実

黄色ハイライトが意味するのは、次の事実だけである。

> DataNormalizerとTape acceptance guardを通過したaggressive tradeが、
> この価格bucketのpassive sideで約定した。

黄色ハイライトは次を意味しない。

- 画面に現在表示されている数量が、その約定前に存在した正確なqueue数量である
- その価格の板数量が全量消滅した
- iceberg、absorption、sweepが成立した
- 次の価格方向がBUY／SELL sideと一致する
- entryすべきである

`BOOK_UPDATE`は最新同期Snapshotの100ms投影、`TAPE_UPDATE`は受理約定のbatchであり、
両messageは同一の原子的snapshotではない。
この制約を隠して「表示中のこの数量を食い切った」と断定してはならない。

ただしaggressive sideの意味は既存正本で確定しているため、
`BUY -> ASK`、`SELL -> BID`の対応は推測ではない。

---

## 5. 機能要件

### 5.1 発火source

ハイライト対象は、`TAPE_UPDATE`を通り、`TapeStore`で正常化・重複排除された
**新規受理約定**だけとする。

発火してよい:

- 新規live `TAPE_UPDATE` trade
- replayが独立した同期済みreplay DOMを提供している場合のreplay accepted trade

発火してはいけない:

- `TICK`
- `CANDLE`
- `BAR_UPDATE`
- `FLOW`
- `FLOW_RESPONSE`
- history APIのhydrate
- historyとliveのduplicate
- invalid trade
- sequence不整合によりtrade要素自体がrejectされたもの
- 現在のlive DOMを過去replayへ混ぜたもの

Time & SalesのALL／BUY／SELL、minimum quantity、minimum notional、large-only filterは
TapeStoreの受理事実を変更しない。
V1のDOM Trade Pulseもfilterとは独立し、正常受理された全tradeを対象とする。

将来filter連動が必要になった場合は、既存filterへ暗黙結合せず、
別のユーザー設定と別仕様として追加する。

### 5.2 side

sideをmaker flagや価格変化から再推定しない。
正常化済みtradeの`side`をそのまま使う。

```text
BUY  -> passive ASK half-cell
SELL -> passive BID half-cell
```

未知side、空side、`WAIT`、`NEUTRAL`は描画しない。

### 5.3 price

raw trade priceをcompact表示文字列から逆変換しない。
正常化済みtradeのexact Decimal priceを数値化し、
CanvasChartが現在使っているtickとdisplay multiplierへ渡す。

対応bucketは既存`bucketIndex()`と同じ規則にする。

```text
native_tick_index = round(trade_price / tick_size)
display_bucket_index =
  floor(native_tick_index / display_multiplier) * display_multiplier
```

独自の`toFixed()`文字列一致や近傍row検索を追加してはならない。

AUTO／手動PRICE STEPによって複数tickが一つの表示rowへ集約されている場合、
その表示bucketの該当side半セルをハイライトする。
exact priceが独立rowとして存在するように偽装しない。

### 5.4 寿命

時間基準はbrowser受理時のmonotonic clockとする。

- 推奨: `performance.now()`
- duration: 400ms
- exchange `event_time`を寿命開始には使わない
- `Date.now()`とexchange clockの差で寿命を計算しない

TAPEはbatch配信なので、同一batch内tradeはbrowser受理時にまとめてパルス開始してよい。
過去event timeへ合わせた遅延timerを作らない。

初期表示:

- 0〜280ms: 明瞭な黄色fill＋黄色border
- 280〜400ms: 線形fade out
- 400ms以降: 完全消去

点滅を複数回繰り返すstrobeにはしない。
一回の黄色pulseとして実装する。

### 5.5 連続約定

同じexact price、同じpassive sideのtradeが400ms以内に続いた場合:

- cellを重複描画しない
- pulse開始を最新trade受理時刻へ更新する
- expiryを最新trade受理時刻＋400msへ延長する
- 内部hit countは増やしてよい
- hit countを色の強さ、売買score、確率へ変換しない

display stepにより複数exact priceが同じbucketへ集約された場合も、
画面では一つの半セルpulseへ集約する。

反対sideは別keyとする。
同一bucketでBUYとSELLが近接した場合、ASKとBIDを独立してハイライトする。

継続約定により同じcellが黄色のまま延長されることは、
連続してそのsideで約定している事実の表示であり、ちらつき不良とは扱わない。

### 5.6 板level消滅時

aggressive tradeの直後、次の`BOOK_UPDATE`で該当数量levelが0または削除される場合がある。

この場合も:

- `sync_state == SYNCED`
- 該当price bucketが現在の`frame.rows`内
- pulse expiry前

であれば、数量が`—`になっても黄色overlayは満了まで残す。

Pulse Storeを`book.byIndex`の現存levelだけに結び付けてはならない。
これにより「約定後に板が消えたため、ハイライトも一フレームで消える」という
場当たり的不具合を防ぐ。

黄色overlayは過去数量を復元・保持してはならない。
数量文字は現在の正常なDOM stateに従い、無ければ`—`のままとする。

### 5.7 fail closed

次の場合はハイライトを描かない。

- DOM `sync_state != SYNCED`
- disconnect／`NO_CONNECTION`
- initial frame未構築
- priceまたはsideがinvalid
- price bucketが現在の`frame.rows`外
- symbol／stream切替境界を越えた古いpulse
- live DOMとreplay tapeのsourceが一致しない

DOMが`STALE`、`RESYNCING`、`CROSSED`等へ遷移した瞬間、
保持中pulseを全消去する。
古い黄色cellを正常なDOM対応として延長してはならない。

price bucketが画面外の場合、pulseのためにviewportをpan、zoom、recenterしない。
ユーザーのFootprint表示位置とLIVE LOCKを勝手に変更しない。

### 5.8 reconnect／restart／symbol／mode

次の境界で保持中pulseをclearする。

- WebSocket disconnect
- Tape `stream_id` restart
- Book `book_stream_id` restartまたはfail-closed transition
- symbol change
- live／replay mode change
- feature flag OFF
- Canvas破棄

history hydrateはpulseを再生成しない。
再接続直後に過去500件が一斉点滅する動作を絶対に作らない。

Tape gapが存在しても、正常受理できた個々のtradeのpulseは表示してよい。
ただし既存`TAPE GAP`表示とdrop counterを消したり正常扱いへ戻したりしない。

---

## 6. 描画仕様

### 6.1 対象領域

対象はLIVE DOMの該当side半セルだけとする。

- BUY: `domMid`から右のASK半セル
- SELL: `domX`から`domMid`までのBID半セル

次は黄色にしない。

- Footprint bar cell
- 価格軸全体
- DOM row全幅
- Time & Sales row
- Best Bid／Ask以外の無関係なcell

### 6.2 色

初期推奨:

```text
fill:   #FFD54A, alpha 0.45〜0.55
border: #FFD54A, alpha 0.90〜1.00, 2px
```

既存のpassive Bid緑、passive Ask赤、Best cyan、wall／POC yellowを変更しない。
既存wallはoutlineだけなので、DOM Trade Pulseはtranslucent fill＋明るいborderで区別する。

数量文字を読めなくする不透明fillは禁止する。
色だけでsideを伝えず、左右どちらの半セルが点灯したかを維持する。

### 6.3 layer順

Canvasの推奨描画順:

1. static Footprint base
2. current LIVE DOM quantities
3. Best／wall outline
4. **DOM Trade Pulse overlay**
5. current price reference
6. user selection outline
7. detail／status更新

selectionはユーザー操作状態なので、pulseより上で視認できるようにする。
Pulseはstatic Footprint baseをinvalidにして全面再構築してはならない。

### 6.4 layout

次は1pxも変更しない。

- 3段チャートの高さとPRICE／CVD+Delta／VOLUME比率
- Flow Response固定行
- Footprint／LIVE DOM共通価格geometry
- DOM固定幅
- Time & Sales 14px文字／28px行
- Time & Sales 32 row pool
- 下段FLOW／Absorption／Imbalance／Alerts配置
- page横幅とoverflow

Pulse用の新しい常設panel、legend、toastは追加しない。

---

## 7. 実装構造

### 7.1 `footprint_canvas.js`

Canvas module内に、描画から独立して試験可能なPulse Storeを追加する。

推奨class:

```text
DomTradePulseStore
```

最低限の責務:

- duration、active entry上限、monotonic timeを保持
- aggressive sideをpassive DOM sideへ変換
- exact trade priceをnative tick indexへ正規化
- 同一price／sideをcoalesce
- expiry prune
- 現在frameのdisplay bucketへ投影
- clear reasonと統計を保持

推奨公開関数／method:

```text
passiveSideForAggressor(side)
DomTradePulseStore.ingest(trades, context)
DomTradePulseStore.activeCells(frame, now)
DomTradePulseStore.clear(reason)
DomTradePulseStore.snapshot()
CanvasChart.ingestDomTradePulses(trades, meta)
CanvasChart.clearDomTradePulses(reason)
CanvasChart.getDomTradePulseStats()
```

命名は実装整合性のため変更してよいが、
責務を`onTapeUpdate()`へ戻してはならない。

Pulse Storeは最大256 active exact-price entryを上限とする。
上限到達時はexpiredを先にpruneし、それでも超える場合だけ最古entryを明示的にevictし、
eviction counterを増やす。
無制限Mapは禁止する。

### 7.2 animation scheduler

一つの`CanvasChart`につき、pulse用schedulerは最大一個とする。

- active pulseが0→1になったときだけ開始
- `requestAnimationFrame`でoverlay redrawを予約
- active pulseが0になったら停止
- 約定一件ごとの独立timerは禁止
- background tab復帰時はmonotonic expiryを再評価し、古いpulseを即消去

既存dirty-layer最適化へ`domTradePulse`相当のoverlay layerを追加する。
`viewport`／`history`を毎frame invalidにしない。

### 7.3 `index.html`

既存inline callbackを肥大化させず、accepted tradeの分配を一つのnamed coordinatorへまとめる。

推奨:

```text
onAcceptedTapeTrades(trades, result)
```

責務:

1. Tape stream restartなら古いDOM pulseをclear
2. `FP.chart`が存在し、feature enabledならpulse APIへ渡す
3. Heatmap UIが存在すれば既存どおりtradeを渡す
4. 一方のoptional consumer失敗で他方を停止させない
5. backend acceptance／TapeStore内容を変更しない

`onTapeUpdate()`は引き続きbatch ingestionとcontinuity結果の受け渡しだけを担当する。

推奨設定:

```text
DOM_TRADE_PULSE_ENABLED = true
DOM_TRADE_PULSE_DURATION_MS = 400
```

duration変更で描画ロジックを編集しなくてよい構造にする。
localStorage、ユーザーcontrol、backend configはV1では追加しない。

### 7.4 `time_sales.js`

現行`onAcceptedTrades`契約で要件を満たせるため、原則変更しない。

変更が必要だと判断した場合は、先に次を証明する。

- history hydrateがcallbackへ混入しない
- history/live dedup後の新規tradeだけが渡る
- sequence／restart／gap accountingが変わらない
- Heatmap既存consumerが壊れない

単にハイライトを付けるためだけにTradeStoreを二重化しない。

### 7.5 backend／schema

V1では変更禁止:

- `webapp/main.py`
- `push_broker.py`
- `TAPE_UPDATE` payload
- `BOOK_UPDATE` payload
- history API
- DuckDB／Parquet schema
- trade recorder

現在のpayloadだけでprice、side、stream、sequenceが足りる。
不足していないデータを追加してsourceを二重化しない。

---

## 8. 診断可能性

Pulse Storeは最低限、次を数えられるようにする。

- `trades_received`
- `pulses_started`
- `pulses_coalesced`
- `skipped_unsynced`
- `skipped_invalid`
- `skipped_offscreen`
- `cleared_on_boundary`
- `evicted_capacity`
- `active_entries`
- `max_active_entries`

常設UIを増やす必要はない。
unit testとDeveloper Overlay診断から取得可能な`snapshot()`でよい。

このcounterはTape accepted／sent／droppedの正本counterを置き換えない。
Pulseは表示projectionなので、Pulse skipを市場trade dropとして数えない。

---

## 9. 変更予定file

必須候補:

- `Delta_Engine_Pro4web/webapp/static/footprint_canvas.js`
- `Delta_Engine_Pro4web/webapp/static/index.html`
- `Delta_Engine_Pro4web/tests/webapp/test_dom_trade_pulse_ui.py`（新規推奨）

必要な場合だけ:

- `Delta_Engine_Pro4web/tests/webapp/test_dom_tape_fusion_ui.py`

原則変更しない:

- `Delta_Engine_Pro4web/webapp/static/time_sales.js`
- backend／storage／payload正本
- 完成済み3段チャート関連file

実装完了と実ブラウザ検証後だけ更新候補:

- `ArchitectureRepository/00_Master/PROJECT_MEMORY.md`
- `ArchitectureRepository/00_Master/ハイライト/実装完了報告_TimeAndSales_DOM約定価格ハイライト_v1_YYYYMMDD.md`

指示書作成だけの時点でPROJECT_MEMORYへ「完成」と追記してはならない。

---

## 10. 必須試験

### 10.1 pure logic

1. `BUY -> ASK`
2. `SELL -> BID`
3. unknown side reject
4. 非正値／非有限price reject
5. exact priceからnative tick indexを決定
6. 現行`bucketIndex()`とdisplay bucketが一致
7. 399msではactive、400ms以降はexpired
8. 同price／same sideはcoalesceしexpiry延長
9. same price／opposite sideは別entry
10. active上限256とeviction counter
11. clearで全entry消去

clockは注入可能にし、sleepへ依存しない決定論的testにする。

### 10.2 source routing

1. `TAPE_UPDATE`の新規受理tradeだけがpulse APIへ渡る
2. `TICK`ではpulseしない
3. history hydrateではpulseしない
4. history/live duplicateではpulseしない
5. invalid batch tradeではpulseしない
6. Heatmapへの既存accepted trade routeを維持
7. Tape gap／restart counterを変更しない

### 10.3 Canvas

1. BUY tradeでASK半セルだけが黄色
2. SELL tradeでBID半セルだけが黄色
3. 反対半セルは変化しない
4. AUTO STEPで同じdisplay bucketへ正しく集約
5. 手動STEPでも正しく集約
6. 数量level削除後もexpiryまではpulseが残る
7. 数量levelを捏造せず`—`のまま
8. 400ms後に完全消去
9. `SYNCED`以外では描画0
10. offscreen priceでviewport不変
11. selection outlineがpulseより上
12. wall／Best outlineの意味と色が不変

### 10.4 lifecycle

1. disconnectでclear
2. Tape stream restartでclear
3. Book fail-closed transitionでclear
4. symbol changeでclear
5. live／replay切替でclear
6. background tab復帰時にexpired pulseが残らない
7. reconnect history 500件が一斉点滅しない
8. replay DOMが無いときlive DOMを点灯しない

### 10.5 performance

既存Phase 5／6基準を維持する。

- Tape ring 500件不変
- DOM row pool 32件不変
- pulse active entry最大256
- pulse scheduler最大1
- 6,000 live trade no-loss accounting不変
- Tape accepted／sent／pending／in-flight／droppedの等式不変
- Canvas warm render p95を変更前後同条件で比較
- 目標: pulse active時Canvas p95 4ms以下
- 変更前からの増加: 2ms以下
- console error 0
- page horizontal overflow 0
- DOM／Time & Sales／3段チャートgeometry不変

性能基準を満たせない場合、duration短縮で隠さず、
overlay redraw、grouping、scheduler設計を是正する。

### 10.6 実Edge

syntheticだけで完成扱いしない。

同一の実約定について最低限、次を記録する。

- trade ID
- event time
- browser受理時刻
- exact price
- aggressive side
- target passive side
- current display tick／multiplier／bucket
- pulse開始と消去時刻
- DOM sync state
- pulse中のDOM quantity有無

実Edgeで次を動画または時刻付き連続screenshotとして確認する。

```text
BUY trade arrival
  -> same price bucketのASK半セルが黄色
  -> 約400ms後に消える

SELL trade arrival
  -> same price bucketのBID半セルが黄色
  -> 約400ms後に消える
```

levelが約定直後に消える実例またはdeterministic injectionでも、
黄色overlayだけが満了まで残り、数量を保持しないことを確認する。

---

## 11. 完成条件

次を全て満たした場合だけ実装完了とする。

- BUY／SELLとpassive sideの対応が全試験で一致
- accepted live trade以外からpulseしない
- history hydrateでpulseしない
- display bucketが既存Canvas geometryと一致
- level消滅後もpulse寿命が独立
- fail closed中の誤点灯0
- lifecycle境界のstale pulse 0
- active storeとschedulerがbounded
- Heatmap、Tape、Footprintの既存consumerが回帰合格
- completed Flow Price Responseと3段チャートが無変更
- 実Edgeで視認性と400ms寿命を確認
- performance基準を満たす
- 変更file、試験結果、未確認事項を完了報告へ記録

単体testだけ、黄色pixelだけ、source markerだけでは完成扱いしない。

---

## 12. 段階実装とcheckpoint

### HL-0 — Baseline audit

- 必読正本を確認
- current branch／HEAD／dirty worktreeを記録
- `index.html`、`time_sales.js`等の既存ユーザー変更を保全
- 関連testと実Edge geometryの変更前baselineを取得
- 実装checkpointを本フォルダへ作成

source変更は禁止。

### HL-1 — Pulse domain／Canvas overlay

- pure `DomTradePulseStore`
- side mapping
- price bucket
- bounded state
- monotonic expiry
- Canvas overlay
- unit test

Tape wiringはまだ行わず、deterministic injectionで検証する。

### HL-2 — Tape coordinator wiring

- accepted trade callbackへ接続
- Heatmap既存route維持
- disconnect／restart／symbol／mode clear
- history non-pulse
- integration test

### HL-3 — Full verification

- WebApp関連回帰
- full pytest
- performance比較
- 実Edge live確認
- completion report
- PROJECT_MEMORY更新

### HL-4 — Runtime反映

static bind mount反映、container restart、image build、production deploymentは
現runtime構成を確認し、ユーザーが明示承認した範囲だけ行う。

文書作成、source実装、runtime反映、commit、pushを同じ承認と解釈しない。

各Phase開始前、完了後、長時間試験前後、承認要求前、未完了終了前に、
次をcheckpointへ逐次記録する。

- 現在時刻
- 承認範囲
- 完了済み
- 未完了
- 変更file
- 検証結果
- blockerの限定範囲
- 次の再開位置

---

## 13. Worktree保護

2026-07-31の指示書作成時点で、repositoryには本件以外の変更が存在する。
実装担当者はそれらを本件へ混ぜない。

- `git reset --hard`禁止
- `git checkout --`による他者変更破棄禁止
- broad `git add -A`禁止
- unrelated fileのformat／cleanup禁止
- exact path単位でdiff、test、stage候補を確認
- 既存dirty fileへ触れる前に差分と所有範囲をcheckpointへ記録

本件で必要な最小差分だけを作る。

---

## 14. Rollback

表示機能だけを戻せるよう、独立feature flagを持つ。

機能rollback:

```text
DOM_TRADE_PULSE_ENABLED = false
```

flag OFF時:

- Pulse Storeへ新規tradeを入れない
- active pulseをclear
- schedulerを停止
- DOM／Tape／Heatmap／Footprintは従来どおり動作

code rollbackは、本件で変更した正確なhunk／fileだけを対象とする。
backend schema、保存データ、BOOK／TAPE contractを巻き戻す作業は発生させない。

---

## 15. 保護境界

本件では次を変更しない。

- Flow Price Responseの計算、状態、色、6窓
- 3段チャートの構造、比率、zoom、pan、selection
- Price／CVD／Delta 8パターン
- OI計算と表示契約
- Footprint aggregation、POC、VA、Imbalance
- Order Book同期state machine
- Tape acceptance、sequence、gap、drop accounting
- Heatmapのbook／trade意味
- Absorption／Imbalance／Flow Event detector
- Hook／Strategy／Condition／Pattern
- Order Trigger／execution／MT5発注

DOM Trade Pulseは観測UIの一時overlayであり、分析値や発注判断へ入力しない。

---

## 16. 本指示書作成時点の承認境界

今回のユーザー指示により承認されたのは、

```text
ArchitectureRepository/00_Master/ハイライト
```

への本実装指示書作成までである。

この時点では次を実施していない。

- source code変更
- test code変更
- runtime再読込
- container restart
- image build
- deployment
- commit
- push
- PROJECT_MEMORYへの完成追記

実装開始は、ユーザーの次の明示指示を受けてからとする。
