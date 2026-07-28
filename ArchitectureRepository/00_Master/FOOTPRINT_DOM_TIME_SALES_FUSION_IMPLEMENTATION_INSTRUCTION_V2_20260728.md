# DeltaEngine05M Footprint × LIVE DOM × Time & Sales 融合実装指示書 V2

version: 2.0
作成日時: 2026-07-28 15:09:11 JST
文書状態: **APPROVED — V2.1 AMENDMENT APPLIES**
現在の承認範囲: **V2＋V2.1設計、OI A、Phase 0A remediation**
source code実装状態: **未着手**
実装開始条件: Phase 0C sizing後のschema／retention承認とPhase 1の明示GO

本V2は、次のV1を監査記録として残したまま正本候補を更新する。

- V1:
  `ArchitectureRepository/00_Master/FOOTPRINT_CHART_DOM_FUSION_IMPLEMENTATION_INSTRUCTION_20260728.md`
- V2:
  `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_FUSION_IMPLEMENTATION_INSTRUCTION_V2_20260728.md`

参照モック:

- `ArchitectureRepository/30_Modules/WebApp/Design/footprint_chart_dom_fusion_mock.html`

V2で正式追加した対象:

- 右端固定Time & Sales
- 全受理約定を順序保持する`TAPE_UPDATE` batch
- Time & Sales履歴hydrate
- reconnect時dedup
- replay時のmarket-time同期
- Footprint足・価格帯との選択同期
- 表示filter、large trade強調、欠落明示

---

## 1. 目的

DeltaEngine05Mの注文フロー観測を、次の三つへ分けたまま一画面へ配置する。

1. **Footprint**
   - 過去の各足で成立した約定分布
   - 各価格帯のaggressive sell／buy volume
2. **LIVE DOM**
   - 現在板に待機しているpassive bid／ask liquidity
3. **Time & Sales**
   - 直近に成立した約定の時系列
   - 攻撃が今どの価格へ、どの数量で、どちら側から流れているか

```text
共通価格軸
  ├─ Footprint複数足
  │    ├─ BID × ASK
  │    ├─ candle
  │    ├─ POC / VA
  │    └─ Imbalance
  ├─ LIVE DOM
  │    ├─ passive bid / ask
  │    ├─ best bid / ask
  │    ├─ spread
  │    └─ visible wall candidate
  └─ Time & Sales
       ├─ time
       ├─ price
       ├─ quantity / notional
       └─ aggressive side
```

この画面の目的は、約定分布、現在板、直近約定を同時に観測し、
価格反応との関係を人間が読めるようにすることである。

売買シグナル、単一score、confidence、予測確率を生成する画面ではない。

---

## 2. ユーザー確定事項

次をV2の確定要求として扱う。

- Footprintを複数足の連続Footprint Chartにする。
- 標準表示は約10本。
- 最大拡大では約3本を詳細表示する。
- 最大縮小は20本を目安とする。
- 各足の内部へ`BID × ASK`を表示する。
- 中央へローソク足実体とヒゲを表示する。
- 足別POC、Value Area、Imbalance、Stacked Imbalanceを表示する。
- LIVE DOMをFootprint右端へ融合する。
- FootprintとDOMは同じ価格軸／同じ価格行へ揃える。
- Time & Salesを同じ画面へ載せる。
- Time & Salesは時間順のため、価格行へ混ぜず右端固定列へ置く。
- 既存の独立指標を新しい売買シグナルへ統合しない。

---

## 3. 絶対に変更しない範囲

本実装では次を変更しない。

- Flow Price Responseの検出条件
- 30秒、1分、3分、5分、15分、30分の6観測窓
- Flow状態分類、保存、事後成績
- 完成済み3段チャートの計算意味
- PRICE・CVD・Deltaの8パターン判定
- CVD、Delta、Volume、OIの計算
- Footprint raw aggregation
- Imbalance detectorの判定条件
- Absorption detectorの判定条件
- Flow Event detectorの判定条件
- Strategy Engine、Hook、Condition、Pattern、Order Trigger
- execution権限、HFM発注、`execution_enabled`
- raw trade、raw book、Hook journalの削除、修正、truncate

Time & Salesへ表示するside、large trade、filterは観測表示であり、
entry side、signal side、order authorityへ接続してはならない。

---

## 4. 現行実装で確認済みの事実

### 4.1 Footprint

- `src/orderflow/footprint.py`は正規化約定価格ごとにvolumeを集計する。
- BUY約定は`buy_volume`、SELL約定は`sell_volume`へ入る。
- 形成中足は`current_tick_snapshot()`で得られる。
- 確定足は`FootprintBar.levels`で得られる。
- WebSocketの`CANDLE`／`BAR_UPDATE`は`footprint.levels[]`を配信する。
- payloadの`bid`はsell volume、`ask`はbuy volumeである。

### 4.2 Footprint履歴

- 現行`candles`tableはOHLC、Volume、Delta、CVDを保存する。
- 価格帯別Footprintは永続化されていない。
- `/api/history/candles`はFootprint levelsを返さない。
- 再読込後の過去足Footprint復元には専用保存と履歴APIが必要である。

### 4.3 Order Book

- `OrderBookStateManager`は同期済みSnapshotを保持する。
- `CANDLE` payloadはOrder Bookを同梱する。
- `BAR_UPDATE`は軽量化のためOrder Bookを含めない。
- 現状の画面用Order Bookは、確定足時点だけではLIVE DOMとして不十分である。

### 4.4 現行TICK配信

- 現在のブラウザ向け`TICK`は画面応答性のためlatest-value projectionを使用する。
- 重複する画面更新を間引き、最新値だけを送る。
- 分析・保存側は全受理約定を処理する。
- latest-value `TICK`は価格表示には適するが、途中約定が省略されるため
  authoritative Time & Salesとして使用できない。

### 4.5 保存済みtrades

- 正規化済み受理約定は既存trades経路へ保存される。
- Time & Sales履歴hydrateは既存tradesをread-onlyで利用できる。
- 新しいTime & Sales専用DB tableを重複作成する必要はない。

### 4.6 既存未コミット変更

次の関連fileにはSession VWAP等の未コミット変更がある。

- `Delta_Engine_Pro4web/src/pipeline.py`
- `Delta_Engine_Pro4web/webapp/history.py`
- `Delta_Engine_Pro4web/webapp/main.py`
- `Delta_Engine_Pro4web/webapp/push_broker.py`
- `Delta_Engine_Pro4web/webapp/static/index.html`

これらをreset、checkout、上書き、巻き戻ししてはならない。
本機能の差分を既存変更へ追加する。

---

## 5. 目標レイアウト

```text
┌───────────────────────────────────────────────────────────────────────────┐
│ FOOTPRINT · 3 / 10 / 20 · PRICE STEP · VA · VWAP · LIVE LOCK             │
├────────┬───────────────────────────────────────┬─────────────┬────────────┤
│ PRICE  │ FOOTPRINT BARS                        │ LIVE DOM    │ TIME&SALES │
│        │ 09:20 09:21 ... 09:29 LIVE           │ PASSIVE     │ 15:12:...  │
│ 64540  │ 12×18 18×38 ...                       │ — │ 256.3   │ BUY ...    │
│ 64520  │ 18×12 28×30 ...                       │ SPREAD      │ SELL ...   │
│ 64500  │ 38×8  33×18 ...                       │ 23.4 │ —    │ BUY ...    │
├────────┴───────────────────────────────────────┴─────────────┴────────────┤
│ BAR FACTS: DELTA · VOLUME · CVD Δ · OI Δ · EVENTS                        │
├───────────────────────────────────────────────────────────────────────────┤
│ 完成済み3段チャート                                                       │
└───────────────────────────────────────────────────────────────────────────┘
```

### 5.1 固定位置

- PRICE: 左端
- Footprint bars: 中央
- LIVE DOM: Footprint LIVE足の右隣
- Time & Sales: DOMのさらに右
- 既存3段チャート: 下段で維持

LIVE DOMとTime & Salesは、過去ドラッグで横へ流さない。
常に右側へ固定する。

### 5.2 項目の常設

- データが無くてもpanel／header／column名を消さない。
- 値だけを`—`にする。
- sync状態、filter状態、gap状態を固定位置へ表示する。
- データ到着で画面の高さや列幅を変えない。

---

## 6. 表示本数と操作

- 初期値: 最新10本
- 最大拡大: 3本
- 最大縮小: 20本
- wheel: カーソル位置をanchorとして3〜20本
- drag: 過去へ移動
- LIVE LOCK: 最新形成中足へ復帰
- bar click: Footprint足を選択
- price row click: 足内価格帯を選択
- Time & Sales row click: 該当足と価格帯を選択

10本表示で数字を読めない幅へ縮めない。
対象画面幅で10本表示が成立しない場合は、文字を消すのではなく、
PRICE STEPまたはbar幅を調整する。

---

## 7. Footprint表示

各足は次を表示する。

- bar time
- CLOSED／FORMING
- 各価格帯`BID × ASK`
- candle body／wick
- POC
- VAH／VAL／Value Area
- BUY／SELL Imbalance
- Stacked Imbalance
- Delta
- Volume
- CVD change
- OI change
- observation event marker

項目名は`SIGNAL`ではなく`EVENTS`とする。

Event marker候補:

- Absorption
- Imbalance
- Exhaustion
- Large Trade
- Sweep
- Unfinished Auction
- Tape event
- Divergence

表示するEventが履歴に存在しない場合、推測や再生成で埋めず`—`とする。

---

## 8. 色と意味

### 8.1 Footprint

| target | color | meaning |
|---|---|---|
| BID background | `#FF4058` | aggressive sell volume |
| ASK background | `#19C979` | aggressive buy volume |
| BUY Imbalance outline | `#72FFC0` | diagonal buy imbalance |
| SELL Imbalance outline | `#FF7A8D` | diagonal sell imbalance |
| POC / VA | `#F4C542` | volume concentration |
| VWAP / current price | `#25B7E8` | reference line |
| selected bar | white outline | user selection |
| live bar | cyan outline | forming bar |

背景濃度はvolumeの大きさだけを表す。
Imbalance成立は輪郭、矢印、stack railで表す。

### 8.2 LIVE DOM

- Passive Bid Depth: green
- Passive Ask Depth: red
- Best Bid／Ask: cyan outline
- visible wall candidate: yellow outline
- stale／unsynced: quantity `—`、status warning

### 8.3 Time & Sales

- Aggressive BUY: green
- Aggressive SELL: red
- Large Trade: yellow outline
- selected trade: white outline
- stale／gap: fixed warning
- filter active: `FILTERED`を黄色で表示

Time & Salesの色は約定sideを表し、将来価格方向を表さない。

---

## 9. 表示PRICE STEP

Footprintのraw計算は正規化済み約定価格を維持する。

画面だけにprice bucketを導入する。

設定:

- AUTO
- 1 tick
- 2 ticks
- 5 ticks
- 10 ticks
- 20 ticks
- 必要に応じてそれ以上

AUTOは表示価格範囲を概ね20〜40行に収める。

同一bucket内では次を加算する。

- buy volume
- sell volume
- passive bid depth
- passive ask depth

raw Footprint、detector、storage、Hookへbucket値を渡してはならない。

表示POC／VAはbucket後volumeから再計算し、
画面に`DISPLAY STEP`を明示する。

---

## 10. Footprint履歴保存

新規table:

`footprint_levels`

最低限のcolumns:

| column | meaning |
|---|---|
| bar_time | UTC bar start |
| symbol | instrument |
| timeframe | bar timeframe |
| price | raw normalized price |
| buy_volume | aggressive buy volume |
| sell_volume | aggressive sell volume |

論理一意key:

`(bar_time, symbol, timeframe, price)`

保存条件:

- confirmed FootprintBarだけ
- forming barを確定履歴として保存しない
- 同一bar再処理で二重加算しない
- BackgroundStorageWriter経由
- 非正値price、負volume、非有限値を拒否
- 既存candles、trades、Flow tablesを変更しない
- 保存失敗をhealth／logへ残す

履歴API:

`GET /api/history/footprints`

query:

- `limit`
- `before`
- `timeframe`

- 初回40本
- drag時lazy load
- oldest-first response
- 無制限rowを一括返却しない

---

## 11. LIVE DOM配信

新規WebSocket type:

`BOOK_UPDATE`

payload例:

```json
{
  "event_time": "2026-07-28T06:10:01.123+00:00",
  "last_update_id": 123456,
  "sync_state": "SYNCED",
  "bids": [{"price": "64500.0", "qty": "23.4"}],
  "asks": [{"price": "64520.0", "qty": "45.7"}],
  "depth_levels": 50
}
```

配信:

- analysis: 全depth update
- UI: latest synced Snapshotを100ms推奨でprojection
- UI用に全Snapshotをqueueへ積まない
- detector／Hook／storageへUI間引きを適用しない

fail closed:

- no initial snapshot
- update ID gap
- resyncing
- empty
- locked
- crossed
- stale

fail closed中は古い数量をLIVE表示しない。

---

## 12. Time & Salesのauthoritative source

Time & Salesへ使用するのは、
DataNormalizerと既存acceptance guardを通過した受理約定とする。

含める値:

- symbol
- trade_id
- event_time
- received_timeまたはserver send time
- price
- quantity
- side
- notional = price × quantity
- UI tape sequence

side定義:

- `BUY`: aggressive buyerがAskを取った
- `SELL`: aggressive sellerがBidへぶつけた

非正値、非有限、invalid side、duplicateとしてrejectされたtradeを表示しない。
reject件数は既存counterを隠さない。

現行latest-value `TICK`はTime & Sales sourceとして使用禁止とする。

---

## 13. TAPE_UPDATE WebSocket契約

新規WebSocket type:

`TAPE_UPDATE`

payload例:

```json
{
  "batch_time": "2026-07-28T06:10:01.200+00:00",
  "first_sequence": 91201,
  "last_sequence": 91218,
  "accepted_count": 18,
  "dropped_count": 0,
  "trades": [
    {
      "sequence": 91201,
      "trade_id": 501234,
      "event_time": "2026-07-28T06:10:01.103+00:00",
      "price": "64520.1",
      "quantity": "0.184",
      "notional": "11871.6984",
      "side": "BUY"
    }
  ]
}
```

### 13.1 batching

- 受理約定をacceptance orderでappendする。
- 100msを推奨batch周期とする。
- batch内順序を保持する。
- latest trade一件へのcoalesceは禁止する。
- 一batchの上限を設ける場合、残りを次messageへ順番に送る。
- 上限超過分を黙って破棄しない。

推奨初期値:

- batch interval: 100ms
- max trades per message: 250
- server pending capacity: 10,000

数値は実負荷試験で確認し、根拠なくproduction値へ固定しない。

### 13.2 sequence

- UI tape専用の単調増加sequenceを付ける。
- trade_idとsequenceを混同しない。
- reconnect後のgapを検出できるようにする。
- batchの`accepted_count`とtrades件数を照合する。

### 13.3 overflow

queue overflowまたはclient遅延で完全配信できない場合:

- `dropped_count`を増加
- healthへ反映
- UIへ`TAPE GAP`を表示
- 欠落後も連続したように偽装しない

市場分析pipelineをTime & Sales client遅延でblockしてはならない。

---

## 14. Time & Sales UI

### 14.1 固定列

Time & SalesはDOM右側へ固定する。

推奨幅:

- 240〜280px

表示行:

- 直近20〜40行

ブラウザ保持:

- 直近500件

新しいtradeを上、古いtradeを下へ置く。
表示方向はheaderへ明示する。

### 14.2 一行の情報

最低限:

- `HH:mm:ss.SSS`
- price
- quantity
- side

追加:

- compact notional
- large marker
- source age

狭い画面でnotionalを非表示にする場合も、
tooltipまたはrow detailで値を確認できるようにする。

### 14.3 filter

表示filter:

- ALL／BUY／SELL
- minimum quantity
- minimum notional
- large only

filterはブラウザ表示だけに適用する。
server受理、storage、detectorへ適用しない。

filter中:

- headerへ`FILTERED`
- 条件を常時表示
- 非表示tradeを欠落として扱わない

### 14.4 Large Trade

large tradeは黄色outlineで表示する。

- probabilityではない
- BUY／SELL signalではない
- thresholdは設定値として明示
- 既存Flow EventのLARGE TRADE detectorと同じthresholdを使う場合も、
  category eventとraw tape rowを二重の独立票にしない

---

## 15. Time & Sales履歴hydrate

新規endpoint:

`GET /api/history/time-sales`

source:

- 既存`trades`table

query:

- `limit`
- `before`
- `symbol`

推奨初期limit:

- 500

応答:

- oldest-first
- event_time
- trade_id
- price
- quantity
- side
- notional

hydrate後にLIVE `TAPE_UPDATE`を接続する。

dedup key:

`(symbol, trade_id)`

同一tradeをhistoryとLIVEの両方へ重複表示しない。

---

## 16. reconnectとreplay

### 16.1 reconnect

- WebSocket切断をheaderへ表示
- reconnect後にrecent historyをhydrate
- `(symbol, trade_id)`でdedup
- tape sequence gapを確認
- gapが残る場合は`TAPE GAP`を消さない

### 16.2 replay

- replay tradeを同じTAPE batcherへ通す。
- event time順序はreplay market timeを使用する。
- 現在のLIVE tradeを過去replayへ混ぜない。
- replay speedに応じてbatchを送るが、約定順序を壊さない。
- pause中に新しいLIVE rowを追加しない。

---

## 17. 画面内同期

### 17.1 Tape row click

Time & Sales rowをクリックすると:

1. event_timeを含むFootprint barを選択
2. priceを含む表示bucketを選択
3. 対応価格行へ白いoutline
4. rowとbar detailに同じtrade情報を表示

対象barが未読込の場合:

- history pageを取得
- 存在しなければ`BAR NOT LOADED`
- 別barを推測選択しない

### 17.2 Footprint row click

Footprint価格帯を選択した場合:

- 同価格bucketのDOM rowを強調
- 同bar／price bucketに含まれる保持中Tape rowsを強調
- 全市場履歴が存在するように偽装しない

### 17.3 LIVE DOM row click

- 同価格bucketをFootprint側で強調
- Time & Sales filterを自動変更しない
- 選択は表示上のhighlightに限定

---

## 18. Performanceとno-silent-loss

### 18.1 Server

- market analysis loopをblockしない。
- TAPE batcherはbounded queue。
- batch sendはasync。
- slow clientのために全pipelineを停止しない。
- overflowをcounterとhealthへ残す。

### 18.2 Browser

- 受信済み500件をring bufferへ保持。
- DOM nodeは20〜40行だけ描画。
- 古いrowをDOMから外してもdata retention countを明示。
- 毎tradeで画面全体を再描画しない。
- Footprint Chart、DOM、3段チャートをTape row追加ごとに全面再描画しない。

### 18.3 Measurement

最低限計測:

- accepted trades
- TAPE trades sent
- batches sent
- max batch size
- pending high watermark
- dropped trades
- browser rows received
- browser sequence gaps
- render time p95

acceptedとsentの差を説明できない状態で完成扱いしない。

---

## 19. 既存3段チャートとOI

### 19.1 3段チャート

- PRICE／CVD+Delta／VOLUME比率を変更しない。
- Flow Response背景帯を変更しない。
- 8パターンを変更しない。
- Footprint Chartは上側の独立表示。
- bar time選択同期だけ許可する。

### 19.2 OI pane

2026-07-28ユーザー確定:

- **A（採用）**: 既存OI top bar、足別`OI Δ`、選択足詳細を使用し、新規OI paneを作らない
- Bは不採用

Time & Sales追加により横幅と描画負荷が増えるため、
Footprint価格行の可読性を守る観点ではAを引き続き推奨する。

---

## 20. 既存Order Book panel

融合LIVE DOMが正常に入った後、旧Order Book panelを二重表示しない。

- sourceとOrderBookStateManagerは維持
- detectorは維持
- 旧panelだけpresentationから外す
- gap時に旧panelを自動出現させない
- 融合DOMの項目を固定し、値だけ`—`

---

## 21. 実装対象file（予定）

### Backend

- `Delta_Engine_Pro4web/src/database/schema.py`
- `Delta_Engine_Pro4web/src/database/storage.py`
- `Delta_Engine_Pro4web/src/pipeline.py`
- `Delta_Engine_Pro4web/src/config.py`
- `Delta_Engine_Pro4web/config/config.yaml`
- `Delta_Engine_Pro4web/webapp/history.py`
- `Delta_Engine_Pro4web/webapp/main.py`
- `Delta_Engine_Pro4web/webapp/push_broker.py`

### Frontend

- `Delta_Engine_Pro4web/webapp/static/index.html`

### Tests

- Footprint storage
- Footprint history
- BOOK_UPDATE
- TAPE_UPDATE
- batch order
- no-loss accounting
- overflow／gap
- reconnect dedup
- replay isolation
- Time & Sales filters
- Tape-to-Footprint selection sync
- browser layout

不要なfileを触らない。

---

## 22. 試験条件

### 22.1 Footprint

- raw levelsが実装前後で一致
- Imbalance結果が一致
- POC／VA表示bucket計算
- confirmed barだけ保存
- duplicate保存なし
- reload復元
- lazy history順序

### 22.2 LIVE DOM

- SnapshotとBest Bid／Ask一致
- Spread一致
- 100ms projection
- analysis depth count不変
- gap／resync／stale fail closed
- crossed／locked／empty拒否

### 22.3 TAPE_UPDATE

- 全受理tradeが順序どおりbatchへ入る
- batch境界で順序が壊れない
- one-message上限後も次messageへ継続
- accepted countとsent count照合
- duplicateなし
- invalid tradeなし
- overflow明示
- slow clientがpipelineをblockしない

### 22.4 Time & Sales履歴

- 最新500件
- oldest-first API
- notional一致
- history＋LIVE dedup
- reconnect gap表示
- replayへLIVE trade混入なし

### 22.5 UI

- 3／10／20本
- wheel anchor
- drag history
- LIVE LOCK
- PRICE STEP
- Footprint／DOM価格行一致
- Time & Sales固定位置
- 20〜40行virtual display
- filter条件常設
- large outline
- click selection sync
- data無しで項目位置不変
- console errorなし
- 対象画面幅で横overflowなし

### 22.6 回帰

- orderflow tests
- webapp tests
- storage tests
- replay tests
- full pytest
- 実Edge live test

実データでtrade_id、event_time、price、quantity、side、DOM price rowを照合する。

---

## 23. 段階実装

### Phase 1 — Footprint保存

- `footprint_levels`
- BackgroundStorageWriter
- history API
- reload

### Phase 2 — LIVE DOM

- BOOK_UPDATE
- latest Snapshot projection
- fail closed

### Phase 3 — TAPE backend

- authoritative accepted-trade tap
- bounded batcher
- TAPE_UPDATE
- accounting
- Time & Sales history API

### Phase 4 — Footprint Chart

- common price axis
- 3／10／20
- PRICE STEP
- candle、POC、VA、Imbalance
- lazy history

### Phase 5 — DOM／Tape融合

- fixed LIVE DOM
- fixed Time & Sales
- filters
- large marker
- selection sync
- old Order Book panel presentation removal

### Phase 6 — 統合検証

- restart hydration
- reconnect
- replay
- live no-loss accounting
- browser layout
- full regression
- documents

各Phase完了後にcheckpointを更新する。

---

## 24. Rollback

- Footprint Chart feature flag
- BOOK_UPDATE feature flag
- TAPE_UPDATE feature flag
- old single-bar Footprint rendererをrollback候補として維持
- old Order Book sourceを維持
- new`footprint_levels`を既存tableから分離
- rollbackでraw dataを削除しない
- Tape表示停止でtrade storageを停止しない
- DOM表示停止でbook analysisを停止しない

rollbackは表示／追加配信の停止であり、研究データ破壊ではない。

---

## 25. 実装前の残確認

OIについて次を確定する。

1. **A（推奨）: 新規OI paneなし**
2. B: Footprint Chart専用OI paneを追加

Time & Salesについては次をV2既定とする。

- DOM右側へ固定
- 受理約定を100ms batch
- latest-value TICKは使用禁止
- browser保持500件
- 表示20〜40行
- display filter
- large trade黄色outline
- row clickでFootprint同期
- gap／overflow明示

---

## 26. Checkpoint

現在時刻: 2026-07-28 15:09:11 JST
承認範囲:

- V2指示書作成
- Time & Salesを正式設計対象へ追加
- source code変更は未承認／未着手

完了済み:

- PROJECT_MEMORY全文確認
- 3本Footprintモック
- 連続10本Footprintモック
- Footprint × LIVE DOM融合モック
- 現行Footprint履歴不足の確認
- 現行Order Book配信境界の確認
- 現行latest-value TICKがTime & Salesへ不適であることの確認
- Time & Sales V2契約作成

未完了:

- Phase 0B baseline commit／branch承認
- Phase 0C storage sizing
- schema／retention承認
- source code実装
- tests
- live no-loss accounting
- browser実機検証
- PROJECT_MEMORY更新

今回追加したfile:

- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_FUSION_IMPLEMENTATION_INSTRUCTION_V2_20260728.md`

維持する旧文書:

- `ArchitectureRepository/00_Master/FOOTPRINT_CHART_DOM_FUSION_IMPLEMENTATION_INSTRUCTION_20260728.md`

blockerの限定範囲:

- Footprint実装開始はPhase 0B／0CとPhase 1明示GO待ち
- OI pane方針はAで確定済み

次の再開位置:

1. Phase 0A remediationを完了
2. exact baseline commit対象を再提示
3. Phase 0B明示承認後にcommit／branch
4. Phase 0C read-only sizing
