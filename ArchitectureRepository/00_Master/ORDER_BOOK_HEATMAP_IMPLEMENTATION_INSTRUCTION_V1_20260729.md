# DeltaEngine05M Order Book Heatmap 実装指示書 V1

version: 1.0  
作成日時: 2026-07-29 05:12 JST  
文書状態: **APPROVED IN PART — GO-H0／GO-H1 COMPLETED**
現在の承認範囲: **GO-H0 baseline／GO-H1 Book continuity contract**
source code実装承認: **GO-H1のみ完了。GO-H2以降は未承認**
deployment承認: **未承認**

本書は、DeltaEngine05MへBookmap系の時間×価格Order Book Heatmapを追加するための
authoritative implementation instruction候補である。

「Bookmap系」は機能分類を示す。第三者製品のlogo、名称、画像、配色、UI assetを複製しない。
本機能はDeltaEngine固有のデータ契約、fail-closed、表示体系で実装する。

---

## 0. 決定要約

V1では次を採用する。

| 項目 | V1決定 |
|---|---|
| 表示場所 | 中央領域の`FOOTPRINT | HEATMAP`切替 |
| 既存Footprint | renderer／stateを保持し、置換しない |
| Time & Sales | 右端232px固定を維持 |
| 下段indicator | FLOW／Absorption／Imbalance／Alertsの下段配置を維持 |
| 3段チャート | geometry、計算、操作を一切変更しない |
| Heat source | `BOOK_UPDATE`のresting bid／ask liquidity |
| Trade bubble source | `TAPE_UPDATE`のaccepted aggressive tradesのみ |
| Depth | bid／ask各top 50（現行設定） |
| Book cadence | 最大100ms（現行設定、変更時だけ配信） |
| 保持 | browser session内、直近15分か最大9,000 book frame |
| 永続化 | V1対象外。別GOで設計・容量測定する |
| default view | LIVE LOCK、直近5分、PRICE STEP AUTO |
| 表示timezone | JST、tooltipへUTC併記 |
| Primary font | price／time軸・tooltip・主要数量は基本14px |
| 描画 | Canvas、bounded typed-array store、DOM cell禁止 |
| 欠損 | blank／hatched gapとして必ず明示。古い板を延長しない |
| rollback | 独立feature flagで即時presentation rollback |

V1は「ブラウザを開いてから蓄積するLIVE session heatmap」である。
過去の板を存在するように見せてはならず、開始前領域は`SESSION START`として空白にする。

---

## 1. 目的

時間と価格に沿って、次の三つを同じ観測面へ置く。

1. passive liquidity
   - bid／askに待機している板数量
   - 板の追加、維持、減少、消失
2. aggressive execution
   - 実際に成立したBUY／SELL約定
   - quantity／notionalに応じたbubble
3. continuity state
   - book sync、reconnect、server restart、delivery gap
   - Tape gap、drop、stream restart

目的は、流動性の滞留と約定、その後の価格反応を人間が観測できるようにすることである。
予測、売買推奨、confidence、score、新規signalを生成する機能ではない。

---

## 2. 絶対に変更しない範囲

本機能の実装を理由に、次を変更してはならない。

- Flow Price Responseの6観測窓、状態分類、保存、事後成績
- 完成済みPRICE／CVD+Delta／VOLUMEの3段チャート
- PRICE・CVD・Deltaの8パターン判定
- CVD、Delta、Volume、OI、VWAPの計算
- FootprintのBID／ASK、POC、VA、Imbalance、Stacked Imbalance計算
- LIVE DOMのexisting fail-closed判定
- Time & Salesのaccepted trade、sequence、dedup、filter、selection contract
- Absorption、Imbalance、FLOW EVENTS、ALERTSの判定
- alert一時通知の右下配置と下段ALERTS履歴
- strategy runtime、発注権限、LIVE注文、MT5 algorithmic trading

Heatmap側から既存analysis objectへ値を書き戻してはならない。
Heatmapはread-only presentation consumerである。

---

## 3. 現行実装で確認済みの事実

### 3.1 Book

- `LatestBookProjectionPump`が最新Order Book stateをread-only projectionする。
- 設定は`live_dom_depth_levels: 50`、`book_update_interval_ms: 100`、
  `book_stale_after_ms: 2000`である。
- fingerprintが同じprojectionは送信抑制される。したがって固定100ms frameではなく、
  「最大100msで観測したchanged state stream」である。
- `SYNCED`時のみbid／ask各top 50をprice順で配信する。
- `NO_SNAPSHOT`、`RESYNCING`、`STALE`、`EMPTY`、`LOCKED`、`CROSSED`、`INVALID`は
  fail-closedでbids／asks、Best Bid／Ask、Spreadを空にする。
- reconnect時は最新`BOOK_UPDATE` 1件をcache再送する。

### 3.2 Tape

- `TAPE_UPDATE`が全accepted tradeをbatch配信する。
- payloadはstream UUID、連続sequence、accepted／dropped count、trade ID、event time、
  exact price／quantity／notional、aggressive `BUY`／`SELL`を持つ。
- `TAPE_UPDATE`はreconnect cacheへ入れない。
- Time & Salesは履歴500件、live dedup、same-stream gap、stream restartを実装済みである。

### 3.3 Frontend

- 中央はCanvas Footprint、右はvirtualized Time & Salesである。
- Footprint CanvasはLIVE DOMをdirty layerとして描画する。
- main rowは552px高、右列232pxである。
- FLOW／Absorption／Imbalance／Alertsはmain rowより下へ展開済みである。
- primary Footprint値とTape rowは基本14pxへ可読性修正済みである。

### 3.4 Storage／Replay

- tradesとFootprint historyはhydrate可能である。
- depth historyは永続化されていない。
- replayではLIVE DOM projectorを起動しないため、V1 Heatmapはreplay bookを持たない。

---

## 4. 用語と意味の分離

| 表示 | 意味 | authoritative source |
|---|---|---|
| Heat cell | その時点・価格帯のresting limit quantity | `BOOK_UPDATE` |
| BUY bubble | aggressor BUYとして成立したtrade | `TAPE_UPDATE.trades[].side` |
| SELL bubble | aggressor SELLとして成立したtrade | `TAPE_UPDATE.trades[].side` |
| Best Bid line | 最新有効bookのbest bid | `BOOK_UPDATE.best_bid` |
| Best Ask line | 最新有効bookのbest ask | `BOOK_UPDATE.best_ask` |
| Last price line | 直近成立価格 | accepted Tape／existing market price |
| Gap band | データを信用できない時間区間 | book／Tape continuity state |

禁止する意味混同:

- resting quantityを約定量として表示しない。
- bubbleを板数量として色付けしない。
- quantityの減少を約定と断定しない。cancel／move／executionを区別できないためである。
- `TICK`からbubbleを再構成しない。
- 非同期bookを最後の有効値で埋めない。

---

## 5. 目標レイアウト

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ existing topbar                                                          │
├──────────────────────────────────────────────────────────────────────────┤
│ completed three-stage chart — current position／geometry unchanged       │
├────────────────────────────────────────────────────────────┬─────────────┤
│ [FOOTPRINT] [HEATMAP]  HEATMAP · LIVE · 5M · STEP AUTO     │ TIME&SALES  │
│ ┌────────────────────────────────────────────────────────┐ │ existing    │
│ │ time →                                                 │ │ 232px fixed │
│ │ price ↑  resting-liquidity heat                        │ │ unchanged   │
│ │          ○ BUY / ○ SELL trade bubbles                  │ │             │
│ │          best bid / ask / last price                   │ │             │
│ └────────────────────────────────────────────────────────┘ │             │
│ status: BOOK SYNCED · DEPTH 50×2 · SESSION 08:41 · P95 ...│             │
├────────────────────────────────────────────────────────────┴─────────────┤
│ existing FLOW EVENTS                                                     │
├──────────────────────┬──────────────────────┬────────────────────────────┤
│ ABSORPTION           │ IMBALANCE            │ ALERTS                     │
└──────────────────────────────────────────────────────────────────────────┘
```

### 5.1 Mode switch

- `FOOTPRINT`と`HEATMAP`を同一中央panel headerへ置く。
- 初期modeは既存互換の`FOOTPRINT`とする。
- mode切替はCanvas visibilityだけを変え、WebSocket接続、Footprint state、selection、zoomをresetしない。
- Heatmap storeはfeature有効中、Footprint表示中もbounded蓄積を継続する。
- 切替でcentral panelの外形、高さ、right Tape、下段layoutを動かさない。

### 5.2 Heatmap controls

常設control:

- `1M`、`5M`、`15M`
- `STEP AUTO`、`1`、`2`、`5`、`10` tick
- `INTENSITY − / +`
- `BUBBLES ON/OFF`
- `LIVE LOCK`／`RETURN LIVE`

advanced settingはgearへ収納する。

- bubble minimum notional
- heat percentile scale
- bid／ask line visibility
- last price line visibility

---

## 6. 表示と可読性

### 6.1 Font

- price軸: 14px以上、font weight 800以上
- time軸: 14px以上、font weight 800以上
- tooltipの値: 14px以上
- mode／主要control: 12px以上
- status secondary text: 11px以上。ただし異常状態は12px以上
- heat cell内へ小さい数量文字を敷き詰めない

### 6.2 Color meaning

Heatはbid／ask共通のquantity intensity paletteとする。

```text
zero          transparent / background
low           deep blue
medium        cyan
high          yellow
at/above cap  near-white yellow
```

同じ色は同じvisible-window quantity scaleを意味する。
bid／askのsideは色強度でなく価格位置、Best line、tooltipで示す。

- Best Bid: green 1px line
- Best Ask: red 1px line
- Last price: white 1px line
- BUY bubble: green fill＋dark outline
- SELL bubble: red fill＋dark outline
- invalid／gap: gray hatch＋明示label

colorだけへ依存せず、tooltip、line pattern、labelを併用する。

---

## 7. Authoritative data source

### 7.1 Book

Heatmapは`BOOK_UPDATE`だけを受理する。

必須existing field:

- `event_time`
- `projection_time`
- `last_update_id`
- `sync_state`
- `bids[] {price, qty}`
- `asks[] {price, qty}`
- `depth_levels`
- `best_bid`
- `best_ask`
- `spread`
- `age_ms`

`CANDLE.orderbook`やFootprint levelから過去heatを合成してはならない。

### 7.2 Trades

Bubbleは`TAPE_UPDATE.trades[]`だけを受理する。

必須field:

- `stream_id`
- `first_sequence`／`last_sequence`
- `accepted_count`／`dropped_count`
- trade `sequence`／`trade_id`／`event_time`
- exact `price`／`quantity`／`notional`
- aggressive `side`

Time & Sales filterはlist表示だけへ適用する。
Heatmap bubbleは全accepted tradeを受け取り、Heatmap固有のminimum notionalだけを描画時に適用する。

---

## 8. BOOK_UPDATE additive continuity contract

正確なdelivery gap表示のため、existing payloadへ次の2 fieldをadditive追加する。

```json
{
  "book_stream_id": "server-process-uuid",
  "book_sequence": 12345
}
```

### 8.1 `book_stream_id`

- server process／PushBroker lifecycleごとに新しいUUIDを1個生成する。
- WebSocket client reconnectでは変えない。
- server restartで必ず変える。
- Tapeの`stream_id`とは独立scopeとする。

### 8.2 `book_sequence`

- 同一`book_stream_id`内で1から開始する。
- emitted `BOOK_UPDATE`ごとに1増やす。
- `SYNCED`だけでなくfail-closed state messageもsequence対象とする。
- reconnect cacheで同じmessageを再送するときは同じsequenceを保持する。
- exchange `last_update_id`の代用ではない。

### 8.3 Compatibility

- WebSocket envelope `v: 1`は維持する。
- payload revisionはadditive v1.4として仕様書へ記録する。
- existing Footprint LIVE DOM consumerは新fieldを無視してよい。
- Heatmapは2 fieldがないpayloadを描画せず、`BOOK CONTRACT UNSUPPORTED`を表示する。
- rollout時はbackend contract追加をfrontend有効化より先に配備する。

---

## 9. Client validationとcontinuity

受信messageごとに次を検証する。

### 9.1 SYNCED frame

- `book_stream_id`がnon-empty UUID string
- `book_sequence`が1以上のsafe integer
- `event_time`／`projection_time`がtimezone-aware parse可能
- `last_update_id`がnon-negative safe integer
- `depth_levels >= 1`
- bid／askが各1件以上、各件price／qtyがfiniteかつpositive
- bidsはprice降順、asksはprice昇順
- `best_bid < best_ask`
- payload先頭levelとBest Bid／Askが一致
- spreadが`best_ask - best_bid`とdecimal意味で一致

不正frameはstoreへ入れず、`INVALID BOOK PAYLOAD` gapを開始する。

### 9.2 Fail-closed frame

`sync_state !== SYNCED`では次を要求する。

- bids／asksは空
- Best Bid／Ask／Spreadはnull
- state名は既知集合内

受理時点でcarry-forwardを終了し、gap frameを追加する。

### 9.3 Sequence

- 同じstreamで`received === expected`: 正常
- 同じstreamで`received > expected`: `BOOK DELIVERY GAP`を開始
- 同じstreamで`received < expected`: duplicate／out-of-orderとして描画せずcounterを増やす
- stream ID変更: `BOOK STREAM RESTART` marker、expected reset、carry-forward終了
- reconnect cacheで既受理sequenceと同じmessage: duplicateとして無害に無視

exchange `last_update_id`の飛びをbrowser delivery gapと解釈しない。
exchange depth continuityは既存OrderBook managerの`sync_state`を正とする。

---

## 10. 時刻契約

- Storage／payloadはUTC timezone-awareを維持する。
- UI軸はJSTをdefaultとする。
- `SYNCED` Book frameのx座標は`event_time`を使う。
- fail-closed／contract gapの開始時刻は`projection_time`を使う。
- trade bubbleのx座標はtrade `event_time`を使う。
- 同時刻はbook sequence／Tape sequenceで安定順序にする。
- 時刻が前messageより100ms超過去へ戻る場合はout-of-orderとして描画しない。
- tooltipにはJST millisecondとUTC ISOを併記する。
- browser受信時刻をmarket timeとして使わない。診断latencyにのみ使う。

---

## 11. V1 session storage contract

### 11.1 Book ring

Heatmap専用`HeatmapBookStore`を作る。

- max age: 15分
- max frames: 9,000
- max depth: 50×2
- ageとframe countの両方でpruneする
- source object参照を保持せず、検証済みnumeric値だけをcopyする
- fixed-capacity typed arraysを優先する
- priceはFloat64、quantityはFloat32、time／sequence／update IDはFloat64、stateはUint8を基本とする
- update IDがsafe integerを超える場合はframeをrejectし、丸めない

概算上限はbook store単体16 MiB以内を目標とする。

### 11.2 Trade ring

Heatmap専用`HeatmapTradeStore`を作る。

- max age: 15分
- max accepted trades: 100,000
- sequence validationとdedupは既存Time Sales normalizer結果を再利用する
- source exact stringsを入口検証に使い、描画storeはnumeric typed arraysへ変換する
- max件数到達時はoldestをpruneし、age範囲を満たせない場合`BUBBLE RETENTION LIMITED`を表示する

### 11.3 Session boundary

- 初回valid book受信時を`SESSION START`とする。
- browser reloadでstoreは空へ戻る。
- session開始前のTape history 500件をbubble backfillしない。
- Heatmap statusへ常時`SESSION ONLY`を表示する。
- IndexedDB、localStorage、DuckDBへV1 dataを暗黙保存しない。

---

## 12. Price axisとbucket

### 12.1 Tick size

- payload値を文字列のまま勝手な小数丸めへ通さない。
- valid bid／ask隣接価格差とexisting Footprint tick inferenceからsource tickを決定する。
- tickが確定できない間は`WAITING FOR TICK`としheatを描画しない。
- source tickがsession途中で変わった場合はsegment boundaryを置き、既存frameを再解釈しない。

### 12.2 Display step

display bucketはsourceを変更しないpresentation aggregationである。

```text
bucket_index = floor(round(price / tick_size) / multiplier) * multiplier
bucket_qty   = sum(source level qty in the bucket)
```

- manual multiplier: 1、2、5、10
- AUTO: visible price heightに対して40〜90 heat rowとなる1／2／5×10^n stepを選ぶ
- Best Bid／Ask／trade priceはsource exact値を保持し、描画座標だけ同じbucket geometryへ写す
- bidとaskを同一bucketへ混ぜない。cross／lockedはupstream fail-closedを正とする

### 12.3 Visible price range

- LIVE LOCK時はmid priceを中心とし、受信top 50 depth範囲を含む。
- 最低上下paddingはdisplay bucket 3行分。
- manual vertical pan中はrangeを固定する。
- `RETURN LIVE`でcurrent mid中心へ戻す。
- price axis labelを省略しすぎず、14px labelが重ならない間隔で表示する。

---

## 13. Heat intensity contract

quantityの絶対値はsymbol／時間で変わるため、visible window全体へ一つのscaleを使う。

1. visible synced frameのnon-zero bucket quantityを集める
2. 20 sample以上なら`Q95 = percentile95(values)`
3. 20 sample未満なら`Q95 = max(values)`
4. `Q95 <= 0`ならheatを描画しない
5. 各cell intensityを次で計算する

```text
base = log1p(quantity) / log1p(Q95)
intensity = clamp(base * user_intensity_multiplier, 0, 1)
```

- default multiplier: 1.0
- control range: 0.5〜4.0
- 同一render内の全時刻・全価格で同じQ95を使う
- legendへ`0 / Q50 / Q95+`のquantityを表示する
- Q95変化でpaletteが変わるため、visible window／intensity変更時はlegendを必ず更新する
- quantity thresholdでsource frameを捨てない。thresholdは描画だけへ適用する

---

## 14. Trade bubble contract

### 14.1 Sourceと集約

- accepted／sequence-valid／deduplicated `TAPE_UPDATE` tradeだけをstoreする。
- BUYはgreen、SELLはred。
- 同一render pixel、同一price bucket、同一sideへ重なるtradeは描画時だけ集約する。
- aggregateはquantity sum、notional sum、trade count、first／last event timeを保持する。
- source raw tradeをaggregationで改変しない。

### 14.2 Radius

visible aggregate notionalの95 percentileを`N95`とする。

```text
radius = 3 + 15 * sqrt(clamp(aggregate_notional / N95, 0, 1))
```

- radius範囲: 3〜18px
- sample不足時はvisible maxをN95とする
- minimum notional default: 0
- minimum notionalは描画filterであり、accepted counter／storeから削除しない
- BUY／SELLが同じ座標なら左右へ最大4px offsetし、両方を見せる

### 14.3 Tapeとの同期

- bubble clickで、対応tradeが既存500件Time & Sales storeに残っていればそのrowを選択する。
- 複数trade aggregateの場合は最も新しいtradeを選ぶ。
- 既存Tapeから消えている場合は`TRADE OUTSIDE TAPE RETENTION`をdetailへ表示する。
- Time & Sales row click時、対応tradeがHeatmap 15分store内ならcursorをその時刻／価格へ移す。
- 既存Footprint selection contractは変更しない。

---

## 15. 時間rasterization

### 15.1 Step-held state

Book frameはsnapshot状態である。二つのvalid frame間は前frameが維持されたstep functionとして扱う。

```text
frame A at t0 is valid for [t0, t1)
frame B at t1 is valid for [t1, t2)
```

quantityをAとBの間で線形補間してはならない。

### 15.2 Pixel aggregation

複数state intervalが同じx pixelへ入る場合、各price bucket quantityは
**pixel内duration-weighted mean**を採用する。

```text
pixel_qty = Σ(quantity_i × covered_duration_i) / Σ(covered_duration_i)
```

これにより100msだけ現れた板を、1秒間存在した板と同じ強度へ誇張しない。
一方、10秒以下へzoomしたときは100ms segment自体が見える。

### 15.3 Open-ended latest frame

最新valid frameは次の条件をすべて満たす間だけbrowser現在時刻まで延長する。

- WebSocket connected
- 最新client continuity stateが正常
- latest `sync_state === SYNCED`
- `now - projection_time <= book_stale_after_ms + 250ms`

超過時はlocal `STALE` gapを開始する。後続valid frameが来るまで古いheatを伸ばさない。

---

## 16. Gap／invalid表示

### 16.1 Book gap

次のeventでvertical gap bandを開始する。

- fail-closed book state
- missing／invalid continuity field
- book sequence gap
- stream restart
- local stale timeout
- invalid payload
- WebSocket disconnect

gap band:

- backgroundをgray hatchにする
- 上部にreason labelを表示する
- tooltipへstart／end JST、duration、reason、expected／received sequenceを出す
- gap中はheat、Best lineを描かない
- recovery valid frameの時刻でgapを閉じる

### 16.2 Tape gap

- same-stream sequence gap、dropped count、invalid batchは`TAPE GAP` markerを追加する。
- stream ID変更は`TAPE STREAM RESTART` markerを追加する。
- Tape gap中もBook heatを消さない。
- bubbleだけが不完全であることを上端の赤い破線bandで示す。
- gap前後をbubbleで補間しない。

### 16.3 Startup／replay

- first valid frame前: `HEATMAP WARMING · SESSION START`
- replay mode: `HEATMAP UNAVAILABLE · NO BOOK REPLAY SOURCE`
- feature contract未配備: `HEATMAP WAITING FOR BOOK PAYLOAD v1.4`

空白を0 quantityと表現してはならない。0 quantityとunknownは異なる。

---

## 17. Rendering architecture

### 17.1 Module

新規`webapp/static/orderbook_heatmap.js`をUMD形式で作る。
browser globalとNode testの両方から同じpure coreを使えるようにする。

export候補:

- `validateBookPayload`
- `HeatmapBookStore`
- `HeatmapTradeStore`
- `selectDisplayStep`
- `bucketBookFrame`
- `buildTimeColumns`
- `durationWeightedCells`
- `computeHeatScale`
- `aggregateTradeBubbles`
- `OrderBookHeatmapCanvas`

### 17.2 Canvas layers

最低限、次を論理layerとして分ける。

1. static raster cache
   - historical heat cells
   - gap bands
   - time grid
2. live overlay
   - latest open-ended segment
   - Best Bid／Ask／Last line
   - trade bubbles
3. interaction overlay
   - crosshair
   - selection
   - tooltip anchor

実装は2〜3枚のCanvasまたはoffscreen backing canvasを使ってよい。
1 heat cellごとのDOM node作成は禁止する。

### 17.3 Dirty invalidation

- book update: live segment／必要な末尾rasterだけdirty
- Tape update: bubble layerだけdirty
- time pan／zoom: full viewport dirty
- price pan／step変更: full viewport dirty
- crosshair move: interaction layerだけdirty
- modeがFootprintでもstore ingestは続け、Heatmap drawは止める
- draw requestは`requestAnimationFrame`へcoalesceし、1 frameに複数full drawをしない

### 17.4 Resize

- CSS sizeとCanvas backing storeを分ける。
- DPRは1〜4へclampする。
- ResizeObserverでcentral stageだけを監視する。
- resize後もselected market time／priceを維持する。

---

## 18. 操作契約

### 18.1 Mouse／trackpad

- wheel: cursor中心にtime zoom
- Shift＋wheel: price zoom
- drag left/right: time pan、LIVE LOCK解除
- drag up/down: price pan、LIVE LOCK解除
- double click: RETURN LIVE
- hover: crosshair＋tooltip
- click: time／price selection固定
- Escape: selection解除

### 18.2 Keyboard

Canvasは`tabindex="0"`を持つ。

- Left／Right: 1 time pixel移動
- Up／Down: 1 display price bucket移動
- PageUp／PageDown: 10 price bucket移動
- Home: visible start
- End: latest／RETURN LIVE
- `+`／`-`: time zoom
- Escape: clear

### 18.3 Tooltip

Heat cell tooltip必須項目:

- JST millisecond／UTC ISO
- price bucket range
- side（BID／ASK）
- resting quantity
- source level count
- Best Bid／Ask／Spread
- book stream short ID／sequence／last update ID
- book age／sync state

Bubble tooltip必須項目:

- BUY／SELL
- first／last JST millisecond
- price bucket
- aggregate quantity／notional／trade count
- newest trade ID／sequence
- Tape gap state

Canvasと同内容のtext detail regionをCanvas直下へ置き、screen readerとcopyを可能にする。

---

## 19. Time & Sales連携の変更境界

existing `DeltaTimeSales.normalizeTrade`をauthoritative client normalizerとして再利用する。

推奨additive hook:

```text
TimeSalesView options.onAcceptedTrades(newTrades, batchResult)
```

条件:

- callback対象はvalidation／sequence／dedupを通過し、今回新規追加されたlive tradeだけ
- history mergeからcallbackしない
- callback failureでTime & Sales ingest／renderを失敗させない
- existing `ingestBatch` return field、filter、counter、selectionを変更しない
- Heatmap disabled時の追加workはcallbackのnull checkだけ

別normalizerをHeatmap側へ複製して二重判定を作ってはならない。

---

## 20. Feature flagとrollback boundary

新規独立flagを使う。

```javascript
const ORDER_BOOK_HEATMAP_ENABLED = false;
```

- backend continuity fieldが配備・検証されるまでfalse
- false時はmode button、Heatmap DOM、store、callbackを起動しない
- false時の初期表示、Footprint、Tape、lower indicators、3段チャートは現在と同一
- `PHASE5_FUSION_ENABLED`をHeatmap rollbackへ流用しない
- query parameterだけでproduction flagを有効化しない

presentation rollbackはHeatmap flagをfalseへ戻すだけで成立させる。
additive backend continuity fieldはexisting clientへ無害なので残してよい。

---

## 21. Performance contract

対象baseline viewportは1280×900以上、central stage 552px高とする。

### 21.1 Browser budget

- Book ingest p95: 2ms以下
- Tape bubble ingest p95: 2ms以下／batch
- visible full render p95: 16ms以下
- live incremental render p95: 8ms以下
- message-to-paint p95: 100ms以下（server cadenceを除くclient区間）
- Heatmap store推定memory: 32 MiB以下
- Heatmap全体追加JS heap: 64 MiB以下／15分soak
- 50ms超main-thread long task: 5分観測で0件
- horizontal page overflow: 0
- browser page error: 0

### 21.2 Boundedness

- book frame、trade、gap marker、render timing sample、diagnostic logはすべて上限を持つ。
- Canvas resizeごとのbacking store leakを禁止する。
- hidden Heatmap modeでRAF loopを回し続けない。
- status更新でDOM nodeを増殖させない。

### 21.3 Degradation

budget超過時は次の順で表示負荷だけを落とす。

1. bubble labelを省略
2. bubble aggregate粒度をrender pixelへ統合
3. historical rasterをcache
4. DPR上限を2へ下げる

source frame／accepted tradeを無言で捨てて性能を作ってはならない。
retention上限に達した場合はstatusへ明示する。

---

## 22. 実装対象file

### 22.1 Backend

- `Delta_Engine_Pro4web/webapp/push_broker.py`
  - book stream UUID／sequence
  - additive payload field
- 必要な場合のみ`Delta_Engine_Pro4web/webapp/book_projection.py`
  - projection意味は変更せず、continuity transportに必要な最小追加のみ
- `ArchitectureRepository/30_Modules/WebApp/Specifications/WebSocketPayload_Spec_v1.md`
  - `BOOK_UPDATE` payload v1.4記録

### 22.2 Frontend

- 新規`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js`
- `Delta_Engine_Pro4web/webapp/static/index.html`
  - mode switch、stage、status、wiring、feature flag
- `Delta_Engine_Pro4web/webapp/static/time_sales.js`
  - 新規accepted trade callbackだけ

### 22.3 Tests

- 新規`Delta_Engine_Pro4web/tests/webapp/test_orderbook_heatmap_ui.py`
- 既存`test_book_update.py`
- 既存`test_tape_update.py`
- 既存`test_dom_tape_fusion_ui.py`
- 必要に応じて新規JS fixture／golden test

### 22.4 Documents

- phaseごとのcheckpoint
- implementation completion report
- operational activation report
- `PROJECT_MEMORY.md`追記

### 22.5 明示的非対象

V1では次を変更しない。

- database schema
- DuckDB／Parquet writer
- depth raw archive retention
- replay pipeline
- strategy／execution code
- external JS／CSS dependency

---

## 23. Automated test contract

### 23.1 Backend continuity

- stream IDはprocess lifecycle内で不変
- sequenceは1から連続
- SYNCED／fail-closed双方をcount
- reconnect cacheは同一sequence message
- server restart fixtureでstream ID変更、sequence reset
- existing BOOK_UPDATE fieldがbyte意味上不変
- existing Book projection／broker testが全件PASS

### 23.2 Book validation／store

- valid top50 frame受理
- invalid sort、NaN、0／negative、cross、missing field拒否
- fail-closedでlevels空を強制
- duplicate／out-of-order／gap／restart
- 15分age pruneと9,000 frame cap
- local stale boundary
- source object mutationなし
- estimated bytes upper bound

### 23.3 Raster／scale

- source tickと1／2／5／10 aggregation
- AUTO 40〜90 row selection
- duration-weighted meanのgolden fixture
- gapを跨いでcarry-forwardしない
- Q95／log scale／legend
- visible window全体でscale一つ
- bid／askを混ぜない

### 23.4 Trades

- Time Sales normalizerとdedup結果を再利用
- history hydrateをbubbleへ混ぜない
- BUY／SELL、pixel／price bucket aggregation
- radius 3〜18px
- 100,000 capとretention warning
- Tape gap／drop／restart marker
- Tape rowとの双方向selection

### 23.5 UI contract

- default modeはFOOTPRINT
- mode切替でexisting Footprint stateを保持
- Time & Sales 232px固定
- lower indicator位置不変
- 3段チャートgeometry不変
- primary price／time／tooltip computed font 14px以上
- center alert復活なし
- horizontal overflow 0
- feature flag falseでHeatmap source未起動

### 23.6 Browser performance

- synthetic 9,000 book frame／100,000 trade load
- 1M／5M／15M view
- pan／zoom／STEP変更／mode switch
- DPR 1／2
- 5分liveまたはdeterministic accelerated soak
- render／ingest p50／p95／max、heap、long task、RAF countを保存

### 23.7 Regression

- WebApp全test PASS
- repository全testはbaselineからfailureを増やさない
- completed Flow Price Response／3段チャートgolden contract PASS
- Footprint／DOM／Tape Phase 1〜6 integration PASS
- storage／strategy／execution test PASS

test countだけでなく、対象test名と結果をcheckpointへ記録する。

---

## 24. 実Edge acceptance

1280px幅の実Edgeで最低限次を実測する。

- central stageとTapeが重ならない
- Heatmapとlower indicatorsが重ならない
- 3段チャート位置／高さが変更前と一致
- price／time label 14px以上
- 1M／5M／15M切替
- LIVE LOCK／pan／zoom／RETURN LIVE
- Heatとbubbleのtooltip
- Book fail-closed gap
- Book sequence gap／stream restart
- Tape gap／stream restart
- reconnect後に過去を捏造しない
- page error 0
- page horizontal overflow 0
- layout watchdog新規警告0

screenshotだけでPASSにせず、DOM geometry、Canvas state、status text、performance metricを数値保存する。

---

## 25. 段階実装とGO gate

本書承認後も、一括でproduction実装へ進めない。

### GO-H0 — Baseline／restore point

- dirty worktree監査
- intended／runtime／artifact分類
- current WebApp baseline（現時点122 passed）再確認
- 3段チャート／Footprint／Tape実Edge geometry保存
- commitは対象一覧提示後のユーザー明示承認が必要

### GO-H1 — Book continuity contract

- `book_stream_id`／`book_sequence`
- payload spec／unit／reconnect test
- frontend Heatmapはまだ有効化しない

### GO-H2 — Pure Heatmap core

- validator
- bounded book／trade store
- bucket／raster／scale／bubble pure function
- Node／Python contract test
- UI presentationはまだ既定OFF

### GO-H3 — Canvas／mode UI

- central mode switch
- Heatmap Canvas layers
- control／tooltip／keyboard
- default FOOTPRINT、feature flag falseのrollback確認

### GO-H4 — Tape linkage／gap visualization

- additive Time Sales callback
- bubble／Tape selection sync
- Book／Tape gap、restart、local stale表示

### GO-H5 — Integration／performance

- synthetic max load
- full regression
-実Edge geometry／performance
- restart／reconnect／soak

### GO-H6 — Operational activation

- backend contract先行配備
- runtime payload v1.4確認
- Heatmap flag enable
- 15分以上LIVE観測
- health／CPU／memory／browser error確認
- rollback rehearsal

各GOはユーザーの明示承認を必要とする。
「本指示書を作る」はGO-H0以降のsource実装承認を意味しない。

---

## 26. Rollback

### 26.1 Presentation rollback

1. `ORDER_BOOK_HEATMAP_ENABLED=false`
2. 初期modeがFOOTPRINTであることを確認
3. Heatmap store／callback／RAFが起動しないことを確認
4. current WebApp regressionを実行

### 26.2 Backend compatibility rollback

continuity fieldはadditiveなので、問題がfrontendだけならbackend fieldを残す。
backend自体に問題がある場合のみ、book sequence追加差分を独立revertする。

### 26.3 禁止操作

- dirty worktreeへ`git reset --hard`
- completed Footprint／Tapeを旧panelへ丸ごと戻す
- 3段チャートを巻き戻す
- user data／market data／DuckDBを削除する
- rollbackを理由にanalysis／strategy codeを変更する

---

## 27. Checkpoint contract

作業固有checkpointをPhase開始前に作り、次で逐次更新する。

- 最初のsource変更前
- 各GO開始／完了時
- test失敗時
- 長時間load／soak前後
- browser実測前後
- approval要求前
- deployment前後
- 未完了終了前

最低記録項目:

- 現在時刻／branch／HEAD
- 承認済みGO
- dirty worktree分類
- 完了／未完了
- 変更file
- test command／result
- browser geometry／performance
- blockerの限定範囲
- rollback状態
- 次の再開位置

一部blockerで、承認済み範囲の独立作業全体を停止しない。

---

## 28. V1 acceptance criteria

次をすべて満たしたときだけV1実装完成とする。

- [ ] resting liquidityとaggressive tradeの意味が混ざっていない
- [ ] Book delivery sequenceを検証できる
- [ ] fail-closed／disconnect／restart／gapを空白bandで明示する
- [ ] invalid区間へ古いbookを延長しない
- [ ] 直近15分／9,000 frame／100,000 tradeの上限がある
- [ ] duration-weighted time rasterがgolden testと一致する
- [ ] intensity scaleとlegendが一致する
- [ ] BUY／SELL bubbleとTape sequenceが一致する
- [ ] initial modeはFOOTPRINT
- [ ] Footprint stateがmode切替で失われない
- [ ] Time & Sales、lower indicators、3段チャートのgeometryが不変
- [ ] primary heatmap textが基本14px
- [ ] browser performance budgetを満たす
- [ ] browser error／horizontal overflowが0
- [ ] full regression PASS
- [ ] feature flag rollback PASS
- [ ] LIVE 15分以上でBook／Tape continuityを観測
- [ ] checkpoint／completion report／PROJECT_MEMORY更新済み

見た目がHeatmap風であることだけを完成条件にしない。
データ意味、欠損、boundedness、rollbackが同格の必須条件である。

---

## 29. V1対象外のpersistent history拡張

browser restartを跨ぐdepth historyは、V1完成後の別Instruction／別GOとする。

先に最低30分のlive sizingを行い、次を測る。

- changed book frame／秒
- level／frame分布
- raw snapshot bytes／hour
- diff encoding bytes／hour
- compression ratio
- writer CPU／I/O
- read hydration latency
- 1日／7日／30日容量
- retention／archive／purge安全性

top50 snapshotを100ms固定で無条件永続化する案を先に採用してはならない。
raw depth archive、diff、periodic keyframe、render tileの候補を実測比較する。

persistent phaseでも次を禁止する。

- 容量測定前のproduction schema追加
- silent drop
- 無承認の自動purge
- replayで存在しないdepthを補間生成
- current operational storageを試験用に使用

---

## 30. 実装開始前の最終確認

source実装前にユーザーへ次を提示する。

1. 本V1の採否
2. V1がsession-onlyであること
3. default layoutが`FOOTPRINT | HEATMAP`切替であること
4. backend payloadへadditive continuity fieldを入れること
5. GO-H0の対象file／test／restore point案
6. implementationとdeploymentが別承認であること

ユーザーの明示GO-H0までは、文書以外のsource codeを変更しない。

---

## 31. 2026-07-29 GO-H0／GO-H1 completion record

### 31.1 GO-H0

- restore point: `1134886430b7c48487cd4a9389a202acfa6ff53e`
- exact 57 file、artifact／別topic文書混入0
- WebApp 122 passed
- repository 664 passed／1 skipped
- 1280×900実Edge baseline geometry／font／errorを保存

### 31.2 GO-H1

- `BOOK_UPDATE` payload v1.4 additive
- `book_stream_id`: PushBroker lifecycle UUID
- `book_sequence`: 同一stream内1開始の連続message sequence
- SYNCED／fail-closed双方を連番対象
- validation拒否はsequence非消費
- reconnect cacheは同一ID／sequenceを再送
- targeted 45 passed
- WebApp 125 passed
- repository 667 passed／1 skipped
- runtime deployment未実施

GO-H2以降は未承認である。
