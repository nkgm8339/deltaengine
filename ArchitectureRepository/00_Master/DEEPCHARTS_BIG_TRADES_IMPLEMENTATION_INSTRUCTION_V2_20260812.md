# DeltaEngine05M Big Trades Effort／Result・Reaction Zone 実装指示書 V2

- 作成日: 2026-08-12
- 対象repository: `C:\Users\user\Desktop\DeltaEngine05M\Delta_Engine_Pro4web`
- logic正本: `ArchitectureRepository/00_Master/DEEPCHARTS_BIG_TRADES_EFFORT_RESULT_REACTION_ZONE_LOGIC_V2_20260812.md`
- 旧指示書: V1／V1.1。削除・上書きせず訂正前記録として保持する
- 文書状態: 実装前指示書
- 現在の承認範囲: 本V2文書の作成と検証まで
- source実装、config変更、runtime、UI、deployment: 本文書だけでは未承認

## 0. 決定要約

V2の目的はBig Trades markerを出すことではない。大きなexecuted effortを選別し、そのexecution price rangeをReaction Zoneとして後続時間へ延長し、価格がそのareaからどちらへ離れ、戻り、再び攻撃され、wickだけで終わり、またはcloseで抜けたかを履歴化することである。

```text
NormalizedTrade
  → same-side 40ms aggregation
  → Manual／Automatic Size Filter
  → BigTradeEvent＋全fill
  → exact execution-range Reaction Zone
  → later accepted tradesによるABOVE／INSIDE／BELOWと再訪
  → later BigTradeEventのsame-area link
  → 1m candleのwick／body／close observation
  → 1s～600s result snapshots
  → storage／WebSocket／history／Live＝Replay
  → userがeffortとresultを同じ画面で判断
```

V2は次の四つをすべて実装対象にする。

1. 大口数量のManual Min／Max。
2. symbol・activity・volatility連動Automatic Size Filter。
3. Big Trade一件ごとのmarker、全fill、履歴。
4. Big Trade実行価格から延長するReaction Zoneと後続result履歴。

一件のmarkerを人、機関、parent orderと呼ばない。systemがabsorption、勝者、entryを自動確定しない。Fabio本人が見ている観測事実を同じtime／price上へ揃える。

## 1. V1.1を完成扱いしない理由

V1.1はSize Filter、marker、historyまでを詳細化した一方、Big Trade後のprice result、同一areaでの反復、break後のretest、push消失を実装対象にしなかった。

Fabio本人の公開判断は次で一組である。

```text
effort
  + price result
  + same-area repetition
  + opposite effort
  + follow-through or failure
```

したがってV1.1のtestが全て通っても、Fabio型判断を可能にする目的は未達である。V2 acceptanceはReaction Zoneとresult reconstructionなしではPASSにしない。

## 2. 実装目的

実装後、userは一つのselected Big Tradeについて次を連続して確認できること。

1. どれだけの約定量が入ったか。
2. 何件のfillへ分割されていたか。
3. どのprice rangeで約定したか。
4. どのthresholdを通過したか。
5. cluster完了後、priceがzoneの上・中・下のどこへ移ったか。
6. 最初に上へ抜けたか、下へ抜けたか。
7. zoneへ何回戻ったか。
8. 同じareaで後続Big Tradeが何回、どちら側に、合計いくつ出たか。
9. candleがzone外でcloseしたか、wickだけ出して戻ったか。
10. 1、5、15、30、60、180、300、600秒時点のprice result。
11. source gapにより判断不能な区間があるか。
12. CVD、Delta、Volume、Flow Response等の既存contextを同じcandle IDで参照できるか。
13. 自分がそのareaをどう判断したかを、system factと分けて記録できるか。
14. restartとReplay後も同じevent、zone、interaction、snapshotを復元できるか。

## 3. 承認境界

### 3.1 本指示書作成で承認されない操作

- Python／JavaScript source変更。
- `config.yaml`変更。
- database migration実行。
- Docker build、restart、deployment。
- backfill。
- calibration生成・activation。
- production feature flag変更。
- 既存3段chartまたはFlow Price Response変更。
- Hook、Strategy、MT5、注文接続。

### 3.2 実装工程

工程は§59～§66へ分ける。userが「工程Nを進めて」と明示した工程だけを行う。番号を知らなければならない運用にはせず、各工程名と内容を日本語で提示する。

### 3.3 現在の停止位置

V2文書完成後に停止する。source実装を推定して開始しない。

## 4. 正本優先順位

1. userの最新の明示指示。
2. `PROJECT_MEMORY.md`。
3. 本V2実装指示書。
4. V2 logic正本。
5. Fabio具体証拠台帳と公式動画監査。
6. 現行module仕様書。
7. 現行source。
8. V1.1指示書。

矛盾が目的または見え方を変える場合、実装者が選ばず該当工程を止め、原文、影響、選択肢をuserへ示す。

## 5. 用語

- `trade`: DataNormalizerがacceptした一件の約定済み取引。
- `aggressor side`: 成行側。BUYまたはSELL。
- `ExecutionCluster`: 同方向かつ直前fillから40ms以内のtrade列。
- `BigTradeEvent`: Size Filterを通過したExecutionCluster。
- `effort`: eventのaggregate quantity、全fill、同areaの反復executed activity。
- `result`: event完了後のaccepted trade price pathと確定1分足の実際の動き。
- `Reaction Zone`: eventの実約定low～highを時間方向へ保持する観測area。
- `interaction`: zoneに対する離脱、接触、再入、cross、gap、session close。
- `linked event`: 同じareaまたは1 tick隣接で発生した別のBigTradeEvent。
- `system observation`: source dataから決定論的に得た事実。
- `user assessment`: userが事実を読んで付けた評価。system factと別。
- `calibration`: Automatic thresholdのimmutable計算結果。
- `activation`: settings／calibrationが次cluster first tradeからeffectiveになった記録。

## 6. Fabio一次証拠への対応

| Fabioの観測 | V2に必要な機能 |
|---|---|
| 72・61・60・62のeffortが上へ進めない | event quantities、same-area link、zone後のprice path |
| 反対sellersだけが下方result | opposite event link、first exit、max below、candle close |
| 105、再試行、101が同じareaを抜けない | persistent zone、reentry、linked event ordinal、wick／close |
| CVDだけでは不足 | independent CVD contextとBig Trade／resultの同時参照 |
| Big Tradesのpush消失でexit | horizon result推移、追加effort消失、opposite interaction |
| breakout後のretest | price breakでzoneを削除しない、return／reentry継続 |
| levelをprotectする追加aggression | same-area linked eventsとprice result |

これはFabioの非公開formulaを自動化したという主張ではない。本人が公開画面で照合した事実の再現contractである。

## 7. 絶対に変更しない範囲

userの別の明示指示がない限り、次を変更しない。

### 7.1 完成済み中心機能

- `src/orderflow/flow_price_response.py`。
- Flow Price Response 6窓、分類、outcome。
- 3段chartのPRICE／CVD+Delta／VOLUME構成。
- 3段chartのgeometry、zoom、pan、選択、8パターン。
- CVD、Delta、Volume、OIの意味。

### 7.2 既存indicator

- `LargeTradeDetector`。
- Footprint、Heatmap、DOM、Tape。
- Absorption、Imbalance、Sweep、Exhaustion、Unfinished Auction。
- Time & Salesの個別quantity／notional filter。
- DOM Trade Pulse。

### 7.3 発注系

- Hook routing。
- Strategy Engine。
- SignalEngine。
- MT5 bridge。
- execution flag。
- order send。

Big Trade event、zone、assessmentを発注系へ渡さない。

### 7.4 data

- 既存tableのdrop／rename／truncate。
- 既存Parquetの書換え。
- raw recordingの削除。
- 現行historyの再分類上書き。

## 8. 現行repositoryの接続事実

- `NormalizedTrade`はevent time、trade ID、symbol、Decimal price／quantity、BUY／SELLを持つ。
- DataNormalizerは非正値、duplicate、late eventを処理する。
- Live／Replayは共通`handle(normalized)`を通る。
- Tapeは全accepted tradeのUI projectionであり、Big Trades sourceではない。
- `LargeTradeDetector`は既存FLOW EVENTS用の個別trade固定thresholdであり、再利用しない。
- BackgroundStorageWriterはmarket event loop外でDuckDB／Parquetを扱う。
- 中央panelは`FOOTPRINT | HEATMAP`切替である。
- 右Time & Sales、下段indicator、さらに下の3段chartは保護対象である。

## 9. target architecture

```text
DataNormalizer
  │ NormalizedTrade
  ├─ existing storage／Flow／CVD／Footprint／Tape／detectors
  │
  └─ BigTradesRuntimeV2
       ├─ SameMillisecondTradeOrderBuffer
       ├─ ExecutionClusterAggregator
       ├─ BigTradesFilter
       ├─ CalibrationBook／ActivationLedger
       ├─ BigTradeEventFactory
       ├─ ReactionZoneFactory
       ├─ ReactionZoneBoundaryIndex
       ├─ SourcePricePathIndex
       ├─ ReactionZoneObserver
       ├─ HorizonScheduler
       ├─ ZoneCandleObserver
       ├─ SameAreaEventLinker
       └─ storage-ack publication coordinator
              ├─ BackgroundStorageWriter
              ├─ recent event／zone ring
              └─ BigTradesBatcherV2
                       ↓
                 PushBroker
                       ↓
          BIG_TRADES_UPDATE／STATUS
                       ↓
          big_trades.js dedicated Canvas
```

## 10. V2 input mode

完全対応:

```text
AGGREGATE_TRADES
```

予約のみ:

```text
VOLUME
ORDER
ICEBERG
```

予約modeはruntimeで`UnsupportedInputMode`、UIで`SOURCE UNAVAILABLE`かつdisabled。trade IDをorder IDと呼ばず、DOM wallをICEBERGへ名前変更しない。

## 11. logic version

```text
logic_version = BTLOGIC-2.0
event_schema_version = 2
zone_schema_version = 1
```

次を変えるとlogic versionを上げる。

```text
aggregation_window_ms
Automatic history／rank／volatility constants
session template
1m boundary contract
zone bounds contract
zone match tolerance
zone observation lifetime
result horizons
snapshot staleness contract
relation／touch／cross definitions
```

## 12. config contract

```yaml
big_trades:
  enabled: false
  input_mode: AGGREGATE_TRADES
  filter_mode: MANUAL
  manual_min_quantity: "5.000"
  manual_max_quantity: "0"
  automatic_intensity: MEDIUM
  side_filter: BOTH
  marker_price_mode: LAST_PRICE
  calibration_schedule: MANUAL
  calibration_activation_policy: SCHEDULED_SESSION_BOUNDARY
  replay_calibration_mode: HISTORICAL_ACTIVATION
  quantity_step: "0.001"
  reaction_zones_enabled: true
  reaction_zone_match_tolerance_ticks: 1
  reaction_observation_mode: UTC_SESSION
  result_horizons_seconds: [1, 5, 15, 30, 60, 180, 300, 600]
  result_snapshot_max_staleness_ms: 1000
  active_zone_capacity: 5000
  recent_event_capacity: 5000
  recent_interaction_capacity: 20000
  history_api_max_limit: 5000
  batch_interval_ms: 100
  batch_max_records: 200
  batch_pending_capacity: 10000
  max_fills_per_cluster: 10000
```

Manual数量値は例でありproduction値ではない。production symbol metadataとuser意向を工程0で確認する。

### 12.1 enum

```text
filter_mode = MANUAL | AUTOMATIC
automatic_intensity = LOW | MEDIUM | STRONG
side_filter = BOTH | BUY | SELL
marker_price_mode = START_PRICE | LAST_PRICE | VWAP_PRICE
calibration_schedule = MANUAL | WEEKLY | MONTHLY
calibration_activation_policy = SCHEDULED_SESSION_BOUNDARY | MANUAL_ONLY
replay_calibration_mode = HISTORICAL_ACTIVATION | FIXED_RESEARCH
reaction_observation_mode = UTC_SESSION
```

### 12.2 validation

- Decimal stringはfinite、quantityは0以上、stepは0より大きい。
- Maxが0でなければMax >= Min。
- tolerance ticks、capacity、batch、horizon、stalenessはbooleanを除く正integer。
- horizonsは昇順、重複なし、最大600。
- V2で`UTC_SESSION`以外を受理しない。
- unknown keyはstartup error。
- invalid設定へsilent fallbackしない。
- source実装後も工程7まで`enabled: false`。

## 13. user変更可能設定

```text
filter_mode
manual_min_quantity
manual_max_quantity
automatic_intensity
side_filter
marker_price_mode
```

zoneの判定logic、tolerance、horizon、session lifetime、quantity stepは通常UIから変更できない。side filterは表示だけで、zone観測と保存を停止しない。

## 14. settings／activation

### 14.1 immutable snapshot

cluster開始時にeffective settingsとcalibrationをsnapshotする。cluster途中の変更は次clusterまで適用しない。

origin eventが作ったzoneは、origin settings ID、calibration ID、logic version、zone contractをsession closeまで保持する。後の設定変更で既存zoneを再計算しない。

### 14.2 versioned artifacts

```text
data_05M/settings/big_trades/versions/<settings_id>.json
data_05M/settings/big_trades/pending/<key>.json
data_05M/settings/big_trades/active/<key>.json
data_05M/settings/big_trades/activations/<activation_id>.json
```

version、pending、activation artifactはtemporary write、flush、fsync、read-back、hash検証、`os.replace`を使う。activation artifact final renameを唯一のdurable commit pointとする。

active pointerは再構築可能cacheであり正本ではない。

### 14.3 effective boundary

settings／calibration requestは`PENDING`。現在open clusterを強制分割しない。自然に次clusterが始まる最初のaccepted tradeをeffective keyにする。

```text
effective_session_id
effective_from_event_time
effective_from_trade_id
```

### 14.4 Replay selection

Replayはcommitted activation artifactを次で昇順にし、cluster first key以下の最後のrowを選ぶ。

```text
(effective_from_event_time, effective_from_trade_id, activation_id)
```

created time、file mtime、現在pointerから過去versionを推定しない。欠損／collisionはBig Trades Replayだけfail closed。

## 15. same-millisecond ordering

同じevent-time millisecondのtradeを一bucketへ保持し、次millisecond到着時にtrade ID整数昇順でaggregatorへreleaseする。

stream end、disconnect、session transitionはsort後flush。release済みmillisecondより古いtradeは拒否。wall-clock timerを使わない。

## 16. ExecutionClusterAggregator

joinは次のAND。

```text
same symbol
same venue
same side
current.event_time_ms - cluster.last_time_ms <= 40
same UTC session
same 1m candle_id
```

price一致は要求しない。0→35→70msは一cluster。side変更、41ms gap、session、candle、disconnect、stream endでcloseする。

final values:

```text
quantity = Σq
notional = Σ(pq)
vwap = notional / quantity
low = min(price)
high = max(price)
duration = last_ms - first_ms
levels = distinct price count
```

max fills超過はsilent splitせずinvalid clusterにし、current tradeから新clusterを開始する。

## 17. Manual filter

```text
aggregate_quantity < Min → reject
Max > 0 and aggregate_quantity > Max → reject
otherwise → accept
```

境界同値はaccept。Max 0は上限なし。side filterは数量判定後の表示filter。

## 18. Automatic calibration

### 18.1 population

`as_of`以前の直近20完了UTC sessionへliveと同じaggregatorを適用する。進行中session、future data、gap session、restart truncated sessionを除外する。

各sessionのquantity降順:

```text
LOW=20位
MEDIUM=9位
STRONG=2位
```

各順位を有効session間のDecimal medianで統合。有効session10未満の強度が一つでもあればcalibration全体をinvalidにする。

### 18.2 volatility

保存済み1m candleからNTRを計算し、session median、20-session baseline、5-session recentを作る。

```text
factor = clamp(sqrt(recent / baseline), 0.75, 1.50)
```

valid candle coverage 95%未満のsessionはvolatility無効。必要件数不足はfactor 1.00とstatusを保存する。

### 18.3 final threshold

base × factorをquantity stepへ`ROUND_CEILING`し、Low < Medium < Strongを最低1 step差で保証する。Automatic Max 0。

### 18.4 schedule

WEEKLY／MONTHLYは次session最初のaccepted tradeでsource-confirmed boundaryを検出する。完了session summary最大20件からcalibrationを作り、raw tradesをlive loopで再走査しない。

validation成功かつpolicy `SCHEDULED_SESSION_BOUNDARY`なら同じ新session first clusterから自動activate。通常user操作0回。失敗時は旧calibration維持、failure表示、silent retry／fallbackなし。

`MANUAL_ONLY`ではcandidateをpendingに留める。手動生成artifactはpolicyに関係なく明示activation requestまでactiveにしない。

## 19. BigTradeEvent model

immutable field:

```text
event_id, schema_version, logic_version
symbol, venue, side, input_mode
first／last trade ID and time
first／last／low／high／VWAP price
aggregate quantity／notional
fill count, price-level count, duration
close reason
filter mode, intensity, threshold, Max
side filter, marker mode
settings ID, calibration ID, activation ID
session ID, candle ID
content hash
```

DecimalはJSON string。event IDは`bt2_`＋canonical key SHA-256。order ID、person IDではない。

## 20. Reaction Zone model

accepted event一件につきexactly one origin zoneを作る。

```text
zone_id = btz2_<sha256>
origin_event_id
zone_low = event.low_price
zone_high = event.high_price
zone_anchor = event.vwap
zone_visual_start = event.first_time
zone_source_start = event.last_time
origin_side = event.side
session_id = event.session_id
logic_version
settings_id
calibration_id
lifecycle = ACTIVE
```

ATR、percentage、candle high／lowでboundsを拡張しない。single-price zoneを許可する。画面の最低pixel高をauthoritative boundsへ戻さない。

price突破ではzoneを閉じない。次session最初のaccepted tradeで旧sessionをsource-confirmした時だけ`SESSION_CLOSED`にする。

## 21. Reaction Zone indexing

trade一件ごとに全active zoneをloopするO(N)実装を禁止する。

### 21.1 boundary index

`ReactionZoneBoundaryIndex`はzone low／highを価格順へ保持する。

- previous priceからcurrent price間でcrossした境界だけを`bisect`またはinterval treeで取得。
- relation変化が起きたzoneだけinteractionを作る。
- point queryでcurrent priceを含むzoneだけinside quantityを加算。
- new BigTrade range queryで近接zoneだけlink候補にする。

目標complexity:

```text
normal trade: O(log N + K)
K = touched／crossed／contained zones
```

### 21.2 source price path index

accepted trade priceをsource key順へappendし、time-range min／maxとlast-at-or-before queryを提供する。

```text
append O(log M)以下
range min/max O(log M)
last-at-or-before O(log M)
```

horizon snapshotとselected visible zoneのexcursionはこのindexから求め、全zoneのmaxをtradeごとに更新しない。

session close後にold source pathを解放できるのは、全zone snapshotとsession final stateがdurableになった後だけ。

## 22. trade relation／interaction

```text
price < low → BELOW
low <= price <= high → INSIDE
price > high → ABOVE
```

origin event key以下を後続resultへ数えない。

append-only interaction:

```text
ZONE_CREATED
FIRST_EXIT_UP／DOWN
TOUCH_FROM_ABOVE／BELOW
REENTER_FROM_ABOVE／BELOW
CROSS_UP／DOWN
RELATION_ABOVE／INSIDE／BELOW
SOURCE_GAP_STARTED／ENDED
ZONE_SESSION_CLOSED
```

outside→inside transition一回につきtouch一回。同じINSIDE滞在中の全tradeをtouchにしない。ABOVE→BELOWの直接jumpは架空のinside timeを作らずCROSS_DOWNをcurrent trade keyで記録する。

first exitはimmutable。後の反対方向移動で書き換えない。

## 23. repeated event linking

後続event rangeとactive zone rangeのinterval gapをDecimalで計算し、同symbol、venue、session、後続source keyかつgap <= 1 tickならlinkする。

各linkはzone ID、origin event ID、linked event ID、side、quantity、range、time、gap ticks、ordinalを持つ。

複数eventを一つへmergeしない。linkは同一人物またはparent orderを意味しない。

zone summary:

```text
linked BUY／SELL event count
linked BUY／SELL aggregate quantity
same-origin-side count／quantity
opposite-side count／quantity
```

## 24. inside-zone activity

accepted trade priceがzone bounds内にある場合、そのzoneへBUY／SELL別quantityとtrade countを加える。

同一tradeが重複zoneへ属しても各zoneの独立観測として許可する。zone間で合計して市場全体の独立scoreにしない。

## 25. result horizons

fixed horizon:

```text
1, 5, 15, 30, 60, 180, 300, 600 seconds
```

first trade with time > targetを受けたとき、target以下の最後のaccepted tradeをsnapshotにする。source age >1000ms、gap intersection、session boundaryなら補間せずmissing。

各snapshot:

```text
price and relation
return from last price／VWAP in bps
origin-side signed return
range max above／below ticks and bps
touch／cross counts
linked Big Trade counts and quantities
inside BUY／SELL quantities
validity and source age
```

## 26. candle observations

既存CVD確定1分足をBig Tradesへ渡し、UTC boundary parityを確認してからactive zonesとの関係を保存する。

```text
CLOSE ABOVE
CLOSE BELOW
UPPER WICK RETURN
LOWER WICK RETURN
CLOSED INSIDE
```

計算:

```text
close above = close > zone_high
close below = close < zone_low
upper wick return = high > zone_high and close <= zone_high
lower wick return = low < zone_low and close >= zone_low
```

`ABSORPTION CONFIRMED`または`REJECTION CONFIRMED`へ自動変換しない。

## 27. system observationとuser assessment

### 27.1 system observation

画面とAPIで許可するsystem status:

```text
AWAITING RESULT
FIRST EXIT UP
FIRST EXIT DOWN
PRICE ABOVE ZONE
PRICE INSIDE ZONE
PRICE BELOW ZONE
RETURNED TO ZONE
REPEATED BIG EFFORT
SOURCE GAP — RESULT INCOMPLETE
SESSION OBSERVATION CLOSED
```

これらはsource factの短縮表示であり、BUY／SELL推奨ではない。

### 27.2 user assessment

userはselected zoneへ次を任意記録できる。

```text
UNASSESSED
EFFORT_REWARDED
EFFORT_NOT_REWARDED
OPPOSING_ABSORPTION_OBSERVED
REPEATED_DEFENSE_OBSERVED
BREAK_ACCEPTED_OBSERVED
BATTLE_UNRESOLVED
CONTROL_UP_OBSERVED
CONTROL_DOWN_OBSERVED
```

assessmentはappend-only。訂正は`supersedes_assessment_id`を持つ新row。systemはassessmentをmarket fact、signal、orderへ変換しない。

## 28. existing context read-only link

selected zone detailは、同じcandle IDまたはsource-time rangeの既存値をread-only表示できる。

```text
1m OHLC
CVD open／close／change
Delta
Volume
Flow Price Response 6窓
Absorption state／event
Imbalance
Footprint selected price levels
VWAP
```

context contract:

1. 元moduleの値を再計算しない。
2. Big Trades scoreへ加算しない。
3. missingを0で補完しない。
4. source timestampとsource IDを表示する。
5. Big Trades ERRORで元moduleを停止しない。
6. contextが欠けてもevent／zone factを書き換えない。

3段chartのgeometry、計算、selection contractを勝手に変更しない。時刻同期が必要な場合はadditiveなselection coordinatorを使い、工程5のUI mockでuser承認を得る。

## 29. source-confirmed session transition

session完了は次session最初のaccepted tradeだけで確定する。wall clock、timer、shutdown、browser時刻を使わない。

処理順:

1. current new-session tradeをBig Tradesへまだ入れない。
2. CVDがcurrent tradeで閉じた旧session最後の1分足をzone candle observerへ渡す。
3. old same-millisecond bucketをsortしてflushする。
4. old open clusterを`SESSION_CHANGED`でfinalizeする。
5. そのclusterがacceptedならevent、fills、zone、prior-zone linksをatomic保存する。
6. old active zonesのdue horizonをvalid source dataでfinalizeする。
7. old zonesへ`ZONE_SESSION_CLOSED`をappendし、final stateをdurable保存する。
8. old session statsをauthoritative artifactへ保存しread-backする。
9. eligible WEEKLY／MONTHLY calibrationを生成・検証する。
10. policyとrequest優先順位に従いactivation artifactをcommitする。
11. current tradeをnew effective snapshotで処理する。

7または8が失敗した場合、scheduled calibrationを作成・activateしない。旧calibrationを維持し、Big Tradesを`DEGRADED_STORAGE`にする。

stream end／shutdownはbufferとclusterをflushするが、current sessionとactive zonesを完了扱いにしない。

## 30. BigTradesRuntimeV2

新規`src/orderflow/big_trades/runtime.py`へLive／Replay共通runtimeを置く。

責務:

1. settings、calibration、activationを検証。
2. same-millisecond ordering。
3. cluster aggregation／filter。
4. event／fills／zone／links構築。
5. source price path index更新。
6. zone boundary interaction更新。
7. inside-zone activity更新。
8. horizon snapshot finalization。
9. closed candle observation。
10. session transition。
11. storage batch submissionとcommit ack管理。
12. committed recordだけrecent ring／WebSocketへ公開。
13. counters、status、errors。

### 30.1 per-trade authoritative order

```text
accepted NormalizedTrade
  → finalize due horizon snapshots using previous source price
  → append current trade to SourcePricePathIndex
  → update existing zone interactions／inside activity
  → process current trade through cluster aggregator
  → handle finalized prior cluster
  → create event／zone／links if accepted
```

current tradeがprior clusterをcloseさせる場合、current trade自身はprior eventのpost-resultに含めてよいのは、prior event keyより後であり、zone作成が確定した後である。実装は同じcurrent tradeを二重にprice pathへappendせず、prior zoneとの関係を一回だけ記録する。

### 30.2 finalized cluster order

```text
validate cluster
  → resolve start snapshot threshold
  → quantity filter
  → side display flag
  → deterministic event
  → deterministic origin zone
  → link to prior active zones
  → submit atomic storage batch
  → wait for background writer commit ack
  → add event／zone／links to recent stores
  → publish ordered records
```

commit ack前にmarkerまたはzoneをbrowserへ出さない。

### 30.3 exception isolation

- invalid input: Big Trades reject、existing pipeline継続。
- queue full: uncommitted record非公開、DEGRADED。
- invariant／ID collision: Big Trades ERROR、existing pipeline継続。
- programmer error: stack trace、same trade retryなし、existing pipeline継続。

## 31. pipeline接続

Live／Replay双方の`handle(normalized)`でCVD処理直後へ接続する。既存moduleの相対順序を変えない。

```text
existing trade storage
existing Native／Flow Price Response
cvd_result = cvd.process(normalized)

if cvd_result.closed_candle:
    big_trades.observe_closed_candle(cvd_result.closed_candle)

if live reconnect_count changed:
    big_trades.flush(STREAM_DISCONNECTED)

big_trades.process(normalized)

existing Footprint／Flow detector／bar processing
```

closed candleをcurrent tradeより先に渡すのは、session境界の旧session最終candleをzone observationsへ含めるためである。

finalize時はnormalizer flush後、storage close前に`big_trades.flush(STREAM_ENDED)`を呼ぶ。current sessionを完了扱いにしない。

## 32. authoritative storage schema

新規`src/database/big_trades_schema.py`をDuckDB DDL、Arrow schema、Decimal conversionの単一正本にする。

### 32.1 `big_trade_events`

```sql
CREATE TABLE IF NOT EXISTS big_trade_events (
  event_id VARCHAR PRIMARY KEY,
  schema_version INTEGER NOT NULL,
  logic_version VARCHAR NOT NULL,
  symbol VARCHAR NOT NULL,
  venue VARCHAR NOT NULL,
  side VARCHAR NOT NULL,
  input_mode VARCHAR NOT NULL,
  first_trade_id BIGINT NOT NULL,
  last_trade_id BIGINT NOT NULL,
  first_time TIMESTAMP NOT NULL,
  last_time TIMESTAMP NOT NULL,
  marker_time TIMESTAMP NOT NULL,
  first_price DECIMAL(20,8) NOT NULL,
  last_price DECIMAL(20,8) NOT NULL,
  marker_price DECIMAL(20,8) NOT NULL,
  low_price DECIMAL(20,8) NOT NULL,
  high_price DECIMAL(20,8) NOT NULL,
  vwap DECIMAL(38,16) NOT NULL,
  aggregate_quantity DECIMAL(38,16) NOT NULL,
  aggregate_notional DECIMAL(38,8) NOT NULL,
  fill_count INTEGER NOT NULL,
  price_level_count INTEGER NOT NULL,
  duration_ms BIGINT NOT NULL,
  close_reason VARCHAR NOT NULL,
  filter_mode VARCHAR NOT NULL,
  intensity VARCHAR,
  threshold_used DECIMAL(38,16) NOT NULL,
  max_threshold_used DECIMAL(38,16) NOT NULL,
  side_filter VARCHAR NOT NULL,
  marker_price_mode VARCHAR NOT NULL,
  settings_id VARCHAR NOT NULL,
  calibration_id VARCHAR,
  activation_id VARCHAR NOT NULL,
  session_id VARCHAR NOT NULL,
  candle_id TIMESTAMP NOT NULL,
  content_hash VARCHAR NOT NULL
);
```

### 32.2 `big_trade_event_fills`

```sql
CREATE TABLE IF NOT EXISTS big_trade_event_fills (
  event_id VARCHAR NOT NULL,
  fill_ordinal INTEGER NOT NULL,
  trade_id BIGINT NOT NULL,
  event_time TIMESTAMP NOT NULL,
  price DECIMAL(20,8) NOT NULL,
  quantity DECIMAL(20,8) NOT NULL,
  side VARCHAR NOT NULL,
  PRIMARY KEY(event_id, fill_ordinal)
);
```

### 32.3 `big_trade_reaction_zones`

```sql
CREATE TABLE IF NOT EXISTS big_trade_reaction_zones (
  zone_id VARCHAR PRIMARY KEY,
  zone_schema_version INTEGER NOT NULL,
  logic_version VARCHAR NOT NULL,
  origin_event_id VARCHAR UNIQUE NOT NULL,
  symbol VARCHAR NOT NULL,
  venue VARCHAR NOT NULL,
  origin_side VARCHAR NOT NULL,
  zone_low DECIMAL(20,8) NOT NULL,
  zone_high DECIMAL(20,8) NOT NULL,
  zone_anchor DECIMAL(38,16) NOT NULL,
  zone_visual_start TIMESTAMP NOT NULL,
  zone_source_start TIMESTAMP NOT NULL,
  session_id VARCHAR NOT NULL,
  settings_id VARCHAR NOT NULL,
  calibration_id VARCHAR,
  activation_id VARCHAR NOT NULL,
  content_hash VARCHAR NOT NULL
);
```

base zone rowはimmutable。current relationやclose statusを上書き列として持たず、interaction／checkpointから導出する。

### 32.4 `big_trade_zone_interactions`

```sql
CREATE TABLE IF NOT EXISTS big_trade_zone_interactions (
  interaction_id VARCHAR PRIMARY KEY,
  zone_id VARCHAR NOT NULL,
  interaction_type VARCHAR NOT NULL,
  source_event_time TIMESTAMP NOT NULL,
  source_trade_id BIGINT,
  source_candle_id TIMESTAMP,
  price DECIMAL(20,8),
  previous_relation VARCHAR,
  current_relation VARCHAR,
  direction VARCHAR,
  ordinal BIGINT NOT NULL,
  gap_epoch_id VARCHAR,
  content_hash VARCHAR NOT NULL
);
```

### 32.5 `big_trade_zone_event_links`

```sql
CREATE TABLE IF NOT EXISTS big_trade_zone_event_links (
  link_id VARCHAR PRIMARY KEY,
  zone_id VARCHAR NOT NULL,
  origin_event_id VARCHAR NOT NULL,
  linked_event_id VARCHAR NOT NULL,
  linked_side VARCHAR NOT NULL,
  linked_quantity DECIMAL(38,16) NOT NULL,
  linked_low DECIMAL(20,8) NOT NULL,
  linked_high DECIMAL(20,8) NOT NULL,
  linked_time TIMESTAMP NOT NULL,
  interval_gap_ticks DECIMAL(38,16) NOT NULL,
  same_as_origin_side BOOLEAN NOT NULL,
  ordinal_for_zone BIGINT NOT NULL,
  content_hash VARCHAR NOT NULL,
  UNIQUE(zone_id, linked_event_id)
);
```

### 32.6 `big_trade_result_snapshots`

```sql
CREATE TABLE IF NOT EXISTS big_trade_result_snapshots (
  snapshot_id VARCHAR PRIMARY KEY,
  zone_id VARCHAR NOT NULL,
  horizon_seconds INTEGER NOT NULL,
  target_time TIMESTAMP NOT NULL,
  snapshot_trade_id BIGINT,
  snapshot_trade_time TIMESTAMP,
  source_age_ms BIGINT,
  snapshot_price DECIMAL(20,8),
  relation VARCHAR,
  return_last_bps DECIMAL(38,16),
  return_vwap_bps DECIMAL(38,16),
  origin_side_signed_return_bps DECIMAL(38,16),
  max_above_ticks DECIMAL(38,16),
  max_below_ticks DECIMAL(38,16),
  touch_count BIGINT NOT NULL,
  cross_count BIGINT NOT NULL,
  linked_event_count BIGINT NOT NULL,
  inside_buy_quantity DECIMAL(38,16) NOT NULL,
  inside_sell_quantity DECIMAL(38,16) NOT NULL,
  validity VARCHAR NOT NULL,
  content_hash VARCHAR NOT NULL,
  UNIQUE(zone_id, horizon_seconds)
);
```

### 32.7 `big_trade_zone_candle_observations`

```sql
CREATE TABLE IF NOT EXISTS big_trade_zone_candle_observations (
  candle_observation_id VARCHAR PRIMARY KEY,
  zone_id VARCHAR NOT NULL,
  candle_id TIMESTAMP NOT NULL,
  open_price DECIMAL(20,8) NOT NULL,
  high_price DECIMAL(20,8) NOT NULL,
  low_price DECIMAL(20,8) NOT NULL,
  close_price DECIMAL(20,8) NOT NULL,
  open_relation VARCHAR NOT NULL,
  close_relation VARCHAR NOT NULL,
  high_above_ticks DECIMAL(38,16) NOT NULL,
  low_below_ticks DECIMAL(38,16) NOT NULL,
  body_overlaps_zone BOOLEAN NOT NULL,
  wick_overlaps_zone BOOLEAN NOT NULL,
  closed_above BOOLEAN NOT NULL,
  closed_below BOOLEAN NOT NULL,
  upper_wick_return BOOLEAN NOT NULL,
  lower_wick_return BOOLEAN NOT NULL,
  content_hash VARCHAR NOT NULL,
  UNIQUE(zone_id, candle_id)
);
```

### 32.8 `big_trade_zone_state_checkpoints`

runtime restart recovery用のderived checkpoint。authoritative interactions／snapshotsを書き換えない。

```sql
CREATE TABLE IF NOT EXISTS big_trade_zone_state_checkpoints (
  checkpoint_id VARCHAR PRIMARY KEY,
  zone_id VARCHAR NOT NULL,
  source_bucket_time TIMESTAMP NOT NULL,
  current_relation VARCHAR NOT NULL,
  first_exit_direction VARCHAR,
  first_exit_time TIMESTAMP,
  touch_count BIGINT NOT NULL,
  cross_count BIGINT NOT NULL,
  inside_buy_quantity DECIMAL(38,16) NOT NULL,
  inside_sell_quantity DECIMAL(38,16) NOT NULL,
  linked_event_count BIGINT NOT NULL,
  gap_epoch_id VARCHAR,
  content_hash VARCHAR NOT NULL,
  UNIQUE(zone_id, source_bucket_time)
);
```

source-time 1秒bucketごとに、その秒でstateが変化したzoneだけcheckpointする。checkpoint欠損時はinteractionから再構築し、不足区間をgapとして残す。

### 32.9 `big_trade_user_assessments`

```sql
CREATE TABLE IF NOT EXISTS big_trade_user_assessments (
  assessment_id VARCHAR PRIMARY KEY,
  zone_id VARCHAR NOT NULL,
  assessment VARCHAR NOT NULL,
  assessed_at_utc TIMESTAMP NOT NULL,
  assessed_against_source_time TIMESTAMP NOT NULL,
  user_note VARCHAR,
  supersedes_assessment_id VARCHAR,
  content_hash VARCHAR NOT NULL
);
```

### 32.10 calibration／settings／activation／session

V1.1の`big_trade_session_stats`、`big_trade_calibrations`、`big_trade_settings_history`、`big_trade_activation_history`をBTLOGIC-2.0として実装する。activation effective source key、atomic artifact、schedule dedup、Replay selectionを維持する。

## 33. Parquet layout

```text
data_05M/parquet/big_trade_events/
data_05M/parquet/big_trade_event_fills/
data_05M/parquet/big_trade_reaction_zones/
data_05M/parquet/big_trade_zone_interactions/
data_05M/parquet/big_trade_zone_event_links/
data_05M/parquet/big_trade_result_snapshots/
data_05M/parquet/big_trade_zone_candle_observations/
data_05M/parquet/big_trade_zone_state_checkpoints/
data_05M/parquet/big_trade_user_assessments/
data_05M/parquet/big_trade_session_stats/
data_05M/parquet/big_trade_calibrations/
data_05M/parquet/big_trade_settings_history/
data_05M/parquet/big_trade_activation_history/
```

既存trades／candles／Footprint ParquetへBig Trades列を追加しない。

## 34. storage atomicity／publication

### 34.1 origin batch

一つのaccepted clusterについて次を一つの`BigTradeOriginStorageBatch`にする。

```text
event row
all fill rows
origin zone row
ZONE_CREATED interaction
prior-zone event links
```

DuckDB一transactionでcommitする。いずれか一つだけをcommitしない。

### 34.2 commit acknowledgement

BackgroundStorageWriterはbatch ID付きcommit ackをruntimeへ返す。runtimeはmarket loopを同期blockせずpending publicationへ保持し、commit success callback後だけrecent ringとWebSocketへ出す。

queue admissionだけをdurable successと呼ばない。

### 34.3 Parquet

関連fileをtemporaryへ書きread-backした後、commit manifestを作る。DuckDB commit済み／Parquet pendingはstatusへ明示しretryする。history APIのauthoritative live readはDuckDB＋committed recent ringとする。

### 34.4 updates

interaction、snapshot、candle observation、assessmentもcommit ack後にpublishする。same ID／same contentはidempotent、different contentはcollision。

## 35. BackgroundStorageWriter additions

explicit kind:

```text
big_trade_origin_batch
big_trade_zone_interactions
big_trade_zone_links
big_trade_result_snapshots
big_trade_zone_candles
big_trade_zone_checkpoints
big_trade_user_assessments
big_trade_session_stats
big_trade_calibration
big_trade_settings
big_trade_activation
```

counter:

```text
origin_batches_committed／failed
events_written
fills_written
zones_written
interactions_written
links_written
snapshots_written
candle_observations_written
zone_checkpoints_written
assessments_written
duplicates
collisions
commit_ack_latency_ms
parquet_pending／failures
```

既存writer kind、queue ordering、trade／candle／Footprint意味を変えない。

## 36. BigTradesBatcherV2／WebSocket

### 36.1 unified ordered stream

event、zone、interaction、snapshot、candle observationの因果順を維持するため、一つのBig Trades stream IDと連続sequenceを共有する。

```text
type = BIG_TRADES_UPDATE
payload.records[].kind =
  EVENT_CREATED
  ZONE_CREATED
  ZONE_INTERACTION
  ZONE_EVENT_LINK
  RESULT_SNAPSHOT
  CANDLE_OBSERVATION
  USER_ASSESSMENT
```

recordsはstorage commit ack順ではなくauthoritative source key＋record precedenceで整列する。同一origin batchでは`EVENT_CREATED → ZONE_CREATED → ZONE_EVENT_LINK`。

### 36.2 batch contract

- thread safe、publishはawaitしない。
- UUID stream ID、sequence 1開始。
- 100msまたは200 records。
- pending max 10000。
- overflowはdrop oldestをcounterへ明示。
- dropped sequenceをbrowserへ隠さない。
- history recovery可能。

### 36.3 payload Decimal

price、quantity、bps、ticksはJSON string。count、sequence、millisecondsはinteger。booleanをintegerとして受理しない。

### 36.4 status

```text
BIG_TRADES_STATUS
```

status enum:

```text
DISABLED
STARTING
MANUAL_READY
AUTOMATIC_READY
INSUFFICIENT_HISTORY
CALIBRATION_UNAVAILABLE
CALIBRATION_ACTIVATION_FAILED
DEGRADED_STORAGE
DEGRADED_POINTER_CACHE
DEGRADED_SOURCE_GAP
ERROR
```

PushBrokerは最新statusをcacheしreconnect clientへ先に送る。

## 37. REST API

### 37.1 event／zone history

```text
GET /api/history/big-trades/events
GET /api/history/big-trades/zones
GET /api/history/big-trades/zones/{zone_id}
```

queryはlimit 1..5000、exclusive before source time＋ID、side、lifecycle、assessment。oldest-firstで返す。

zone detail response:

```text
origin event
fills summary
zone bounds／lifecycle
current／final relation
first exit
excursions
interaction counts
linked event summary
horizon snapshots
candle observations
gap segments
latest user assessment
lineage IDs
```

### 37.2 lazy details

```text
GET /api/history/big-trades/events/{event_id}/fills
GET /api/history/big-trades/zones/{zone_id}/interactions
GET /api/history/big-trades/zones/{zone_id}/linked-events
GET /api/history/big-trades/zones/{zone_id}/snapshots
GET /api/history/big-trades/zones/{zone_id}/candles
GET /api/history/big-trades/zones/{zone_id}/assessments
```

一覧取得で全fill／interactionを巨大JOINしない。

### 37.3 assessment write

```text
POST /api/big-trades/zones/{zone_id}/assessments
```

closed enum、note最大長、timezone-aware assessed-against source time、supersedes存在をtransactional validationする。update／delete endpointを作らない。

### 37.4 settings／calibration／activation

```text
GET／PUT /api/big-trades/settings
GET /api/big-trades/calibrations
GET /api/big-trades/calibrations/{id}
POST /api/big-trades/calibrations/{id}/activate
GET /api/big-trades/activations
GET /api/big-trades/activations/{id}
```

PUT／POSTはPENDINGを返し、HTTP response時刻でactive扱いしない。

### 37.5 errors

validation 4xx、collision／storage 5xx。HTTP 200に`ok:false`を隠さない。error code、reason、affected subsystemを返す。

## 38. BIG TRADES UI

### 38.1 central three-mode

```text
[ FOOTPRINT ] [ HEATMAP ] [ BIG TRADES ]
```

Footprint／Heatmapを削除、置換、縮小しない。中央panel外寸、右Time & Sales、下段indicator、3段chart geometryを変えない。

### 38.2 controls

headerへ常設:

```text
MODE       MANUAL | AUTO
INPUT      AGGREGATE TRADES
SIDE       BOTH | BUY | SELL
MIN        Decimal
MAX        Decimal, 0=OFF
INTENSITY  LOW | MEDIUM | STRONG
MARK AT    START | LAST | VWAP
ZONES      ON | OFF
STATE      ACTIVE | ALL
CAL        calibration short ID
APPLY
```

Manual／Autoでcontrolを出し入れせず、unused側をdisabledにして位置固定。ZONES OFFは描画だけを止め、観測／保存を止めない。

### 38.3 canvas layers

```text
background
grid
candles
closed historical zones
active reaction zones
zone gap segments
zone range connectors
BUY／SELL markers
quantity labels
linked-event ordinal badges
selection
crosshair
tooltip
```

### 38.4 zone drawing

- authoritative zone low～highをhorizontal bandとしてevent first timeからsession closeまたはlatest source timeまで延長。
- single-price zoneはminimum visual pixel高だけ与える。
- origin BUYはgreen outline、origin SELLはred／magenta outline。
- band fillはneutral low-opacity。support／resistanceを色で断定しない。
- gap segmentはhatched／dashed。
- price breakでzoneを消さない。
- overlapping zonesはorigin markerとordinalを保持し、破壊的mergeしない。

### 38.5 selected detail

一つの固定detail領域を次の順で表示する。

```text
EFFORT
  side, aggregate qty, fills, duration, execution range, VWAP, threshold

RESULT
  current relation, first exit, max above／below, 1s..600s snapshots

REPEATED AREA ACTIVITY
  linked BUY／SELL events and quantities, touches, reentries, crosses,
  inside-zone BUY／SELL executed quantities

CANDLE RESULT
  close above／below, upper／lower wick return, last candle ID

CONTEXT
  CVD, Delta, Volume, Flow Response, Absorption, Imbalance availability

ASSESSMENT
  latest user assessment, history, note

LINEAGE
  event, zone, settings, calibration, activation, logic version
```

effortとresultを別tabに分断しない。

### 38.6 interaction

- hover tooltip。
- clickでzone pin。
- Escapeで解除。
- left／rightでvisible origin event移動。
- wheel zoom、drag pan、LIVE LOCK。
- linked badge clickで後続event detail。
- active modeだけkeyboard／pointer handlerを受ける。

### 38.7 no-data／failure

項目を消さず値を`—`。gap、stale、calibration unavailable、storage degradedを常設statusへ表示する。old calibration維持時は旧CALを表示したままcandidate failureを併記する。

## 39. frontend modules

新規`webapp/static/big_trades.js`へ次を分離する。

```text
BigTradeRecordValidator
BigTradeEventStore
ReactionZoneStore
ReactionZoneProjection
BigTradesContinuity
BigTradesCanvas
BigTradesSettingsController
BigTradesAssessmentController
BigTradesContextLink
```

EventStore／ZoneStore:

- ID dedup、content collision拒否。
- source key deterministic sort。
- history＋live merge。
- event 5000、interaction 20000のbounded store。
- side／zone visibilityはdisplay filter。
- stream restartで全消去せずhistory refill。

browserはTAPE_UPDATEを40ms集約せず、zone resultを再判定しない。

## 40. history hydration／continuity

初回BIG TRADES選択時に直近500 zonesとorigin eventsを取得する。古い方向へpanした時だけexclusive cursorで追加取得する。

WebSocket stream ID変更、sequence gap、dropped countを検出したら`GAP RECOVERING`。history APIでmissing source rangeを回復し、ID／content hash照合後だけwarning解除。回復不能なら表示を残す。

same timestampはID tie breakerで欠落なくpageする。

## 41. restart／reconnect／gap

### 41.1 server restart

- new stream UUID、sequence 1。
- committed activationからsettings／calibration復元。
- current UTC sessionのzones、interactions、last checkpointsを復元。
- open clusterは復元しない。
- exact continuation不能区間はgap epochを作る。
- active pointer cacheはcommitted artifactから再構築。

### 41.2 upstream reconnect

- accepted trade処理前にopen clusterをdisconnect flush。
- active zonesを削除しない。
- gap start／endを記録。
- gap横断snapshotをinvalid。

### 41.3 browser reconnect

- cached status。
- latest zones／events／interactions hydrate。
- live records merge。
- continuity確認までwarning維持。

## 42. fail-closed matrix

| 状況 | Big Trades V2 | 既存pipeline |
|---|---|---|
| invalid trade | reject／counter | 継続 |
| Automatic calibrationなし | event／zone emit 0 | 継続 |
| activation ledger不整合 | Big Trades ERROR | 継続 |
| event／fills／zone atomic commit失敗 | 全て非公開 | 継続 |
| interaction commit失敗 | zone DEGRADED、未保存update非公開 | 継続 |
| invalid tick size | zone observer ERROR | 継続 |
| candle boundary mismatch | Big Trades ERROR | 継続 |
| source gap | gap横断result invalid、hatched表示 | 継続 |
| zone capacity超過 | new zone非公開、ERROR／counter、silent eviction禁止 | 継続 |
| ID content collision | Big Trades ERROR | 継続 |
| WebSocket drop | gap表示＋history recovery | 継続 |
| browser invalid payload | record拒否＋gap表示 | server継続 |
| assessment保存失敗 | success表示しない | market observation継続 |
| context missing | `—` | event／zone継続 |

Manualへsilent fallbackしない。old factを書き換えない。

## 43. health／stats

`/api/stats.big_trades`へadditive追加。

```text
status, logic version
settings／calibration／activation IDs
active／pending threshold
trades observed
clusters started／finalized／accepted／rejected
origin batches submitted／committed／failed
events／zones written and published
active／closed zone count
boundary index size
price path index size
zone interactions／links／snapshots／candle observations
touch／reentry／cross counts
valid／missing horizon snapshots
source gap epochs
assessment count
batch accepted／sent／dropped／pending／balanced
storage ack p50／p95／p99
last trade／event／zone update time
last source-confirmed session
last error
```

Big Trades単独でoverall healthをREDへ変えるかはintegration工程で既存policyを確認する。既定は独立subsystem status。

## 44. logging

logger:

```text
orderflow.big_trades
orderflow.big_trades.reaction_zones
webapp.big_trades
```

INFO:

- activation、calibration、session transition。
- origin batch commit。
- zone session close。
- source gap start／end。

WARN:

- insufficient history。
- missing result snapshot。
- invalid session exclusion。
- WebSocket recovery。
- pointer cache rebuild。

ERROR:

- invariant、collision、storage、artifact hash。
- candle boundary mismatch。
- activation history missing／invalid。
- zone capacity／index corruption。

trade一件ごとのrelation不変をINFOへ流さない。

## 45. performance／boundedness

server target:

```text
Big Trades total per-trade p95 <= 0.15ms
Big Trades total per-trade p99 <= 0.40ms
cluster finalize p99 <= 1.50ms excluding async storage ack
boundary query p99 <= 0.25ms
horizon snapshot finalize p99 <= 1.00ms
daily transition p99 <= 500ms
```

memory:

```text
open cluster 1/symbol
fills max 10000/cluster
active zones max 5000
recent events max 5000
recent interactions max 20000
WebSocket pending max 10000
browser visible markers max 2000
browser visible zones max 2000
session summary max 20
```

O(N active zones) per tradeは禁止。benchmarkでactive zone 10、100、1000、5000を測る。

browser target:

```text
Canvas draw p95 <= 8ms at 1280×900
mode switch <= 100ms
5000 event＋20000 interaction merge <= 150ms
horizontal overflow 0
console error 0
3段chart geometry delta 0px
```

Big Trades OFF／ONでTICK／BAR source age、storage queue、Tape accounting、Book gap、browser drop、CPU、RSSを比較する。

## 46. new source files

```text
Delta_Engine_Pro4web/src/orderflow/big_trades/__init__.py
Delta_Engine_Pro4web/src/orderflow/big_trades/constants.py
Delta_Engine_Pro4web/src/orderflow/big_trades/models.py
Delta_Engine_Pro4web/src/orderflow/big_trades/ids.py
Delta_Engine_Pro4web/src/orderflow/big_trades/time_buckets.py
Delta_Engine_Pro4web/src/orderflow/big_trades/ordering.py
Delta_Engine_Pro4web/src/orderflow/big_trades/aggregation.py
Delta_Engine_Pro4web/src/orderflow/big_trades/filtering.py
Delta_Engine_Pro4web/src/orderflow/big_trades/calibration.py
Delta_Engine_Pro4web/src/orderflow/big_trades/artifacts.py
Delta_Engine_Pro4web/src/orderflow/big_trades/settings.py
Delta_Engine_Pro4web/src/orderflow/big_trades/activation.py
Delta_Engine_Pro4web/src/orderflow/big_trades/price_path.py
Delta_Engine_Pro4web/src/orderflow/big_trades/zone_index.py
Delta_Engine_Pro4web/src/orderflow/big_trades/reaction_zones.py
Delta_Engine_Pro4web/src/orderflow/big_trades/horizons.py
Delta_Engine_Pro4web/src/orderflow/big_trades/candle_observer.py
Delta_Engine_Pro4web/src/orderflow/big_trades/runtime.py
Delta_Engine_Pro4web/src/database/big_trades_schema.py
Delta_Engine_Pro4web/webapp/big_trades.py
Delta_Engine_Pro4web/webapp/static/big_trades.js
Delta_Engine_Pro4web/tools/calibrate_big_trades.py
Delta_Engine_Pro4web/tools/backfill_big_trades.py
```

## 47. modified source files

予定:

```text
Delta_Engine_Pro4web/src/config.py
Delta_Engine_Pro4web/config/config.yaml
Delta_Engine_Pro4web/src/pipeline.py
Delta_Engine_Pro4web/src/database/storage.py
Delta_Engine_Pro4web/webapp/main.py
Delta_Engine_Pro4web/webapp/push_broker.py
Delta_Engine_Pro4web/webapp/history.py
Delta_Engine_Pro4web/webapp/static/index.html
```

変更しない予定:

```text
src/orderflow/flow_price_response.py
src/orderflow/flow_detector.py
src/orderflow/cvd.py
src/orderflow/footprint.py
src/orderflow/absorption.py
src/orderflow/imbalance.py
webapp/static/time_sales.js
webapp/static/footprint_canvas.js
webapp/static/orderbook_heatmap.js
```

実装前に現行diffとhunkを再監査する。user変更へbroad formattingをかけない。

## 48. document updates

実装工程でadditive更新:

```text
ArchitectureRepository/30_Modules/WebApp/Specifications/WebSocketPayload_Spec_v1.md
ArchitectureRepository/40_Reference/YAMLReference_v3.4.md
ArchitectureRepository/40_Reference/DuckDBDDL_v3.1.md
ArchitectureRepository/40_Reference/ParquetSchema_v3.1.md
ArchitectureRepository/DOCUMENT_INDEX.md
ArchitectureRepository/00_Master/PROJECT_MEMORY.md
```

`PROJECT_MEMORY.md`は全実装・検証完了後だけ完成記録を追加する。

## 49. test files

```text
tests/orderflow/test_big_trades_ordering.py
tests/orderflow/test_big_trades_aggregation.py
tests/orderflow/test_big_trades_filtering.py
tests/orderflow/test_big_trades_calibration.py
tests/orderflow/test_big_trades_artifacts.py
tests/orderflow/test_big_trades_activation.py
tests/orderflow/test_big_trades_price_path.py
tests/orderflow/test_big_trades_zone_index.py
tests/orderflow/test_big_trades_reaction_zones.py
tests/orderflow/test_big_trades_horizons.py
tests/orderflow/test_big_trades_candle_observer.py
tests/orderflow/test_big_trades_runtime.py
tests/database/test_big_trades_storage.py
tests/webapp/test_big_trades_batcher.py
tests/webapp/test_big_trades_api.py
tests/webapp/test_big_trades_ui.py
tests/test_pipeline_big_trades.py
tests/tools/test_calibrate_big_trades.py
tests/tools/test_backfill_big_trades.py
```

## 50. mandatory test contract — core／calibration

### Input、ordering、aggregation

1. `BT2-C001` Decimal price／quantity受理。
2. `BT2-C002` price 0／negative拒否。
3. `BT2-C003` quantity 0／negative拒否。
4. `BT2-C004` NaN／Infinity拒否。
5. `BT2-C005` unknown side拒否。
6. `BT2-C006` symbol／venue mismatch拒否。
7. `BT2-C007` timezone-naive拒否。
8. `BT2-C008` duplicate trade IDがBig Tradesへ来ない。
9. `BT2-C009` same-ms arrival逆順をtrade ID昇順release。
10. `BT2-C010` next-msまでbucket保持。
11. `BT2-C011` stream endでsort後flush。
12. `BT2-C012` disconnectでsort後flush。
13. `BT2-C013` released-msより古いtrade拒否。
14. `BT2-C014` same side 0ms join。
15. `BT2-C015` same side 40ms join。
16. `BT2-C016` 41ms split。
17. `BT2-C017` 0→35→70ms one cluster。
18. `BT2-C018` side変更split。
19. `BT2-C019` price違いjoin。
20. `BT2-C020` session境界split。
21. `BT2-C021` 1m candle境界split。
22. `BT2-C022` disconnect前後非結合。
23. `BT2-C023` max fills超過silent splitなし。
24. `BT2-C024` aggregate quantity正確。
25. `BT2-C025` aggregate notional／VWAP正確。
26. `BT2-C026` low／high／distinct levels正確。
27. `BT2-C027` fill ordinal正確。
28. `BT2-C028` UTC minute floor境界直前／境界上。
29. `BT2-C029` offset timestampをUTC同一bucketへ正規化。
30. `BT2-C030` CVD candle boundary parity。

### Manual／settings／IDs

31. `BT2-C031` q < Min reject。
32. `BT2-C032` q = Min accept。
33. `BT2-C033` Max 0 unlimited。
34. `BT2-C034` q = Max accept。
35. `BT2-C035` q > Max reject。
36. `BT2-C036` side filterはquantity判定後。
37. `BT2-C037` cluster途中settings変更は旧snapshot。
38. `BT2-C038` 次clusterは新snapshot。
39. `BT2-C039` invalid settings全体不適用。
40. `BT2-C040` settings ID deterministic。
41. `BT2-C041` event ID deterministic。
42. `BT2-C042` same event ID same content idempotent。
43. `BT2-C043` same event ID different content collision。
44. `BT2-C044` marker START／LAST／VWAP price／time。
45. `BT2-C045` DecimalをJSON string化。

### Automatic／session／activation

46. `BT2-C046` session quantity descending rank。
47. `BT2-C047` Low 20位。
48. `BT2-C048` Medium 9位。
49. `BT2-C049` Strong 2位。
50. `BT2-C050` odd Decimal median。
51. `BT2-C051` even Decimal median。
52. `BT2-C052` valid sessions 9でinsufficient。
53. `BT2-C053` exactly 10でvalid。
54. `BT2-C054` current session除外。
55. `BT2-C055` future data除外。
56. `BT2-C056` gap／restart session除外。
57. `BT2-C057` TR三候補max。
58. `BT2-C058` previous session close使用。
59. `BT2-C059` NTR／session median。
60. `BT2-C060` 95% candle coverage境界。
61. `BT2-C061` 20-session baseline。
62. `BT2-C062` 5-session recent。
63. `BT2-C063` Decimal sqrt factor。
64. `BT2-C064` factor 0.75 clamp。
65. `BT2-C065` factor 1.50 clamp。
66. `BT2-C066` invalid baseline fallback 1.00＋status。
67. `BT2-C067` quantity step ceiling。
68. `BT2-C068` Low < Medium < Strong補正。
69. `BT2-C069` calibration ID deterministic／immutable。
70. `BT2-C070` artifact wrong symbol／logic／step拒否。
71. `BT2-C071` next-session first accepted tradeだけがcompletion trigger。
72. `BT2-C072` wall clock midnightで未完了。
73. `BT2-C073` shutdownで未完了。
74. `BT2-C074` old-session final CVD candleを先に観測。
75. `BT2-C075` session transition authoritative order。
76. `BT2-C076` session stats failureでschedule停止。
77. `BT2-C077` weekly／monthly boundary dedup。
78. `BT2-C078` scheduled validation success auto activate。
79. `BT2-C079` scheduled failureでold calibration維持。
80. `BT2-C080` MANUAL_ONLY pending維持。
81. `BT2-C081` manual artifact自動activateなし。
82. `BT2-C082` same-boundary user calibration優先。
83. `BT2-C083` activation row一件だけ。
84. `BT2-C084` initial PRODUCTION_INITIAL before first marker。
85. `BT2-C085` Replay effective key selection。
86. `BT2-C086` created_at変更でReplay不変。
87. `BT2-C087` activation history missing／invalid fail closed。
88. `BT2-C088` FIXED_RESEARCH production write 0。

## 51. mandatory test contract — Reaction Zone／Result

### Zone creation／bounds

89. `BT2-Z089` accepted event exactly one zone。
90. `BT2-Z090` rejected cluster zone 0。
91. `BT2-Z091` zone low == event low。
92. `BT2-Z092` zone high == event high。
93. `BT2-Z093` anchor == raw VWAP。
94. `BT2-Z094` source start == event last time。
95. `BT2-Z095` visual start == event first time。
96. `BT2-Z096` single-price zone valid。
97. `BT2-Z097` visual paddingがauthoritative boundsへ逆流しない。
98. `BT2-Z098` zone ID deterministic。
99. `BT2-Z099` same eventへsecond zone作成なし。
100. `BT2-Z100` zone origin side保存、support／resistance自動化なし。

### Relation／interaction

101. `BT2-Z101` price < lowはBELOW。
102. `BT2-Z102` price == lowはINSIDE。
103. `BT2-Z103` low < price < highはINSIDE。
104. `BT2-Z104` price == highはINSIDE。
105. `BT2-Z105` price > highはABOVE。
106. `BT2-Z106` origin fillsをpost-resultへ数えない。
107. `BT2-Z107` first outside upはFIRST_EXIT_UP。
108. `BT2-Z108` first outside downはFIRST_EXIT_DOWN。
109. `BT2-Z109` first exit immutable。
110. `BT2-Z110` ABOVE→INSIDE touch／reentry一回。
111. `BT2-Z111` BELOW→INSIDE touch／reentry一回。
112. `BT2-Z112` INSIDE連続tradeでtouch増加なし。
113. `BT2-Z113` BELOW→ABOVE direct CROSS_UP、架空insideなし。
114. `BT2-Z114` ABOVE→BELOW direct CROSS_DOWN、架空insideなし。
115. `BT2-Z115` price breakでzone deletionなし。
116. `BT2-Z116` break後retest記録。
117. `BT2-Z117` session close後new tradeをold zoneへ入れない。
118. `BT2-Z118` wall clockでzone closeなし。

### Index／activity／link

119. `BT2-Z119` boundary index queryがbrute-force結果と一致。
120. `BT2-Z120` point queryはcontaining zonesだけ。
121. `BT2-Z121` crossed boundary zonesだけrelation update。
122. `BT2-Z122` active zone 5000でsilent evictionなし。
123. `BT2-Z123` inside BUY quantity／count正確。
124. `BT2-Z124` inside SELL quantity／count正確。
125. `BT2-Z125` overlapping zonesへ同tradeを各一回。
126. `BT2-Z126` exact overlap later event link。
127. `BT2-Z127` 1 tick adjacent link。
128. `BT2-Z128` >1 tick gap no link。
129. `BT2-Z129` different symbol／venue／session no link。
130. `BT2-Z130` link ordinal source order。
131. `BT2-Z131` linked event remains independent origin event／zone。
132. `BT2-Z132` link payloadにidentity／parent orderなし。
133. `BT2-Z133` BUY／SELL linked quantity summary正確。

### Horizon／excursion

134. `BT2-Z134` horizons exactly 1／5／15／30／60／180／300／600。
135. `BT2-Z135` target以下last trade選択。
136. `BT2-Z136` target後trade価格をsnapshotへ使わない。
137. `BT2-Z137` source age exactly 1000ms valid。
138. `BT2-Z138` source age 1001ms missing stale。
139. `BT2-Z139` gap intersectでmissing gap。
140. `BT2-Z140` same-session requirement。
141. `BT2-Z141` return from last／VWAP Decimal正確。
142. `BT2-Z142` BUY signed return。
143. `BT2-Z143` SELL signed return。
144. `BT2-Z144` range min／max query exact。
145. `BT2-Z145` max above／below ticks正確。
146. `BT2-Z146` touch／cross count horizon cutoff。
147. `BT2-Z147` linked event horizon cutoff。
148. `BT2-Z148` inside quantities horizon cutoff。
149. `BT2-Z149` same input Live／Replay snapshot同値。
150. `BT2-Z150` Replay speedでsnapshot不変。

### Candle／gap／restart

151. `BT2-Z151` close > highはCLOSE ABOVE。
152. `BT2-Z152` close < lowはCLOSE BELOW。
153. `BT2-Z153` high > high and close insideはUPPER WICK RETURN。
154. `BT2-Z154` low < low and close insideはLOWER WICK RETURN。
155. `BT2-Z155` exact-boundary closeはINSIDE。
156. `BT2-Z156` wick returnをabsorption confirmedへ変換しない。
157. `BT2-Z157` candle boundary mismatchでBig TradesだけERROR。
158. `BT2-Z158` disconnect gap start／end interaction。
159. `BT2-Z159` gap後segmentを連続pathと偽装しない。
160. `BT2-Z160` restart recovery checkpoint＋interactions一致。
161. `BT2-Z161` incomplete restart segmentはACTIVE_WITH_GAP。
162. `BT2-Z162` stream endでcurrent zone session closeなし。

### User assessment／context

163. `BT2-Z163` valid assessment append。
164. `BT2-Z164` invalid enum拒否。
165. `BT2-Z165` supersedeはold row保持。
166. `BT2-Z166` assessment保存失敗をsuccess表示しない。
167. `BT2-Z167` assessmentでsystem observation不変。
168. `BT2-Z168` assessmentからorder path 0。
169. `BT2-Z169` context source ID／time保持。
170. `BT2-Z170` missing contextは`—`、0補完なし。
171. `BT2-Z171` existing indicator値不変。

## 52. mandatory test contract — storage／pipeline

### Storage

172. `BT2-S172` event＋fills＋zone＋created interaction atomic commit。
173. `BT2-S173` one component failureでbatch全rollback。
174. `BT2-S174` parent duplicateでfill／zone duplicate 0。
175. `BT2-S175` content mismatch collision。
176. `BT2-S176` commit ack前publication 0。
177. `BT2-S177` commit ack後record precedence正確。
178. `BT2-S178` queue full silent dropなし。
179. `BT2-S179` event／zone Parquet read-back。
180. `BT2-S180` interaction／link Parquet read-back。
181. `BT2-S181` snapshot／candle Parquet read-back。
182. `BT2-S182` assessment Parquet read-back。
183. `BT2-S183` partial temporary file非正本。
184. `BT2-S184` manifest片側欠損検出。
185. `BT2-S185` Decimal precision round trip。
186. `BT2-S186` UTC round trip。
187. `BT2-S187` interaction source ordering。
188. `BT2-S188` zone checkpoint idempotent。
189. `BT2-S189` checkpoint不一致collision。
190. `BT2-S190` activation artifact／pointer一致。

### Pipeline／Live／Replay

191. `BT2-P191` disabled時existing output byte-equivalent。
192. `BT2-P192` enabled時CVD不変。
193. `BT2-P193` enabled時Footprint不変。
194. `BT2-P194` enabled時Flow Price Response不変。
195. `BT2-P195` enabled時LargeTradeDetector不変。
196. `BT2-P196` accepted tradeをBig Tradesへ一回だけ。
197. `BT2-P197` CVD closed candle then current trade順。
198. `BT2-P198` reconnect first tradeがold clusterへjoinしない。
199. `BT2-P199` reconnectでもactive zones削除なし。
200. `BT2-P200` runtime ERRORでもmarket pipeline継続。
201. `BT2-P201` Live／Replay event IDs同値。
202. `BT2-P202` Live／Replay zone IDs同値。
203. `BT2-P203` Live／Replay interactions同値。
204. `BT2-P204` Live／Replay links同値。
205. `BT2-P205` Live／Replay snapshots同値。
206. `BT2-P206` historical activationによるzone lineage一致。
207. `BT2-P207` FIXED_RESEARCH production zone rows 0。
208. `BT2-P208` shutdown storage flush後open session維持。
209. `BT2-P209` source-confirmed session order trace一致。
210. `BT2-P210` old session final zone close後new event生成。

## 53. mandatory test contract — WebSocket／API／UI

### WebSocket／API

211. `BT2-W211` unified stream envelope。
212. `BT2-W212` record kind validation。
213. `BT2-W213` Decimal string／integer strict型。
214. `BT2-W214` contiguous sequence。
215. `BT2-W215` stream restart検出。
216. `BT2-W216` drop count伝達。
217. `BT2-W217` status cache reconnect送信。
218. `BT2-W218` event before zone precedence。
219. `BT2-W219` invalid payload browser拒否。
220. `BT2-W220` zones oldest-first history。
221. `BT2-W221` exclusive time＋ID cursor。
222. `BT2-W222` DB＋recent merge dedup。
223. `BT2-W223` zone detail全lineage。
224. `BT2-W224` fills ordinal pagination。
225. `BT2-W225` interactions source order。
226. `BT2-W226` linked events ordinal。
227. `BT2-W227` snapshots horizon order。
228. `BT2-W228` candles candle-ID order。
229. `BT2-W229` assessment append／supersede。
230. `BT2-W230` assessment update／delete endpoint不存在。
231. `BT2-W231` settings PUT atomic／PENDING。
232. `BT2-W232` manual calibration activation PENDING。
233. `BT2-W233` activation history immutable API。
234. `BT2-W234` 4xx／5xx error semantics。
235. `BT2-W235` history limit／ID validation。

### UI

236. `BT2-U236` 3-mode switch。
237. `BT2-U237` Footprint mode DOM／geometry不変。
238. `BT2-U238` Heatmap mode DOM／geometry不変。
239. `BT2-U239` Big Trades canvasだけactive。
240. `BT2-U240` controls常設、Manual／Auto disabled状態。
241. `BT2-U241` marker aggregate quantity label。
242. `BT2-U242` BUY／SELLは色＋文字で識別。
243. `BT2-U243` exact execution-range horizontal zone。
244. `BT2-U244` single-price minimum pixel only display。
245. `BT2-U245` break後zone継続。
246. `BT2-U246` closed zone source-endで停止。
247. `BT2-U247` gap segment hatch。
248. `BT2-U248` overlapping zones non-destructive。
249. `BT2-U249` linked ordinal badge。
250. `BT2-U250` selected EFFORT detail。
251. `BT2-U251` selected RESULT detail。
252. `BT2-U252` selected REPEATED detail。
253. `BT2-U253` selected CANDLE RESULT detail。
254. `BT2-U254` selected CONTEXT missing handling。
255. `BT2-U255` selected ASSESSMENT append history。
256. `BT2-U256` 1s..600s snapshot表示。
257. `BT2-U257` current ABOVE／INSIDE／BELOW表示。
258. `BT2-U258` first exit immutable表示。
259. `BT2-U259` touch／reentry／cross count。
260. `BT2-U260` side filterでdata deletionなし。
261. `BT2-U261` ZONES OFFでobserver継続。
262. `BT2-U262` history＋live dedup。
263. `BT2-U263` sequence gap warning／recovery。
264. `BT2-U264` no-data項目`—`維持。
265. `BT2-U265` click／Escape／arrow navigation。
266. `BT2-U266` wheel zoom／drag pan／LIVE LOCK。
267. `BT2-U267` inactive mode handler停止。
268. `BT2-U268` 5000 event／20000 interaction capacity。
269. `BT2-U269` horizontal overflow 0。
270. `BT2-U270` browser console error 0。
271. `BT2-U271` Time & Sales filter意味不変。
272. `BT2-U272` DOM Trade Pulse不変。
273. `BT2-U273` 3段chart geometry delta 0px。
274. `BT2-U274` Flow Response cards不変。
275. `BT2-U275` system factsとuser assessment視覚分離。

## 54. mandatory performance／operational tests

276. `BT2-O276` active zones 10 per-trade benchmark。
277. `BT2-O277` active zones 100 benchmark。
278. `BT2-O278` active zones 1000 benchmark。
279. `BT2-O279` active zones 5000 benchmark。
280. `BT2-O280` O(N) scan guard fixture。
281. `BT2-O281` boundary index vs brute force randomized equality。
282. `BT2-O282` price path range-query randomized equality。
283. `BT2-O283` 6000 trade no-loss accounting。
284. `BT2-O284` 25000 trade overflow accounting。
285. `BT2-O285` 5000 event＋20000 interaction browser merge。
286. `BT2-O286` 2000 marker＋zone Canvas p95。
287. `BT2-O287` Big Trades OFF／ON TICK age比較。
288. `BT2-O288` BAR_UPDATE age比較。
289. `BT2-O289` storage queue high-watermark。
290. `BT2-O290` Tape accounting no regression。
291. `BT2-O291` Book gap／sync no regression。
292. `BT2-O292` CPU／RSS boundedness。
293. `BT2-O293` 120秒以上live soak。
294. `BT2-O294` restart recovery soak。
295. `BT2-O295` scheduled session transition performance。
296. `BT2-O296` full repository regression。

V2最低test contractは`BT2-C001`から`BT2-O296`の296項目である。複数assertionを一test functionへ詰めて件数だけ減らし、未検証contractを隠さない。

## 55. fixed evidence vectors

logic正本§30の全vectorをgolden fixture化する。さらにFabio concrete scenarioを抽象化した次を追加する。

### 55.1 repeated failed area attacks

```text
origin SELL event: zone 100..101, qty 105
price: 100 → 102 → 100
later SELL event: range 100..101, qty 101
price: 100 → 103
```

expected system facts:

```text
two independent SELL events
one linked event on origin zone
two upward departures recorded
reentry count preserved
no automatic "absorption confirmed"
```

userが`OPPOSING_ABSORPTION_OBSERVED`を付けた場合だけassessment layerへ表示する。

### 55.2 effort with same-direction result

```text
SELL zone 100..101
later price 99, 98
later SELL event 98..99
```

expected:

```text
FIRST EXIT DOWN
max below ticks exact
later eventはprice rangeがzoneから離れていればsame-area linkしない
directional resultはraw factsとして表示
```

### 55.3 effort loses push

```text
SELL origin zone
30s snapshot BELOW
60s snapshot BELOW but less distance
180s snapshot INSIDE
later BUY linked event at zone
```

systemはpush lossやexitを自動命令しない。snapshot推移、return、opposite effortを表示する。

## 56. baseline regression

各工程で最低限、normalization、CVD、Footprint、Flow Price Response、Flow detector、Absorption、Imbalance、pipeline、live pipeline、Tape、PushBroker、Footprint UI、DOM/Tape fusion、DOM pulse、Heatmap、API、configを実行する。

最終工程はrepository全体pytest。

開始前から存在するfailureはtest名、command、error、開始時source hashを固定し、新規failureと分離する。現在確認済みbaselineは`846 passed, 1 failed, 1 skipped`で、既存failureはHeatmap layout selectorと旧test不一致である。実装開始時に再実行して同一性を確認する。

## 57. backfill

### 57.1 dry-run first

過去event／zoneを生成する前にsource DB identity、期間、trade count、cluster／event／zone／interaction／snapshot予測件数、disk見積、logic／settings／calibration／activation modeをreportする。

### 57.2 no production mutation

production writerが使用中のDBへ初回backfillを混在させない。read-only snapshotと隔離outputを使用する。

### 57.3 historical activation

production相当backfillはactivation historyに従う。activation以前の時刻へ現在thresholdを適用しない。比較研究は`FIXED_RESEARCH` namespaceへ隔離する。

### 57.4 idempotency

same source＋versionsでevent、zone、interaction、snapshot IDsが同一、duplicate追加0。

backfill完了とlive enableを同一操作にしない。

## 58. security／data integrity

- settings／assessment note inputの長さ、enum、Decimal、timezoneをserver validation。
- pathをrequestから組み立てない。
- artifact pathはID regexとfixed directory。
- SQLはparameter binding。
- user noteをHTMLとして描画しない。
- APIからconfig YAML、activation history、system factsを編集・削除しない。
- content hash mismatchをmtimeで解決しない。
- existing DB backupなしのmigration禁止。

## 59. 工程0：baseline／design lock

工程0ではsource codeを変更しない。次を完了してreportし、次工程へ進む前にuserの明示承認を得る。

1. `PROJECT_MEMORY.md`、本指示書、logic正本を全文再読する。
2. branch、HEAD、tag、staged／unstaged／untrackedを記録する。
3. 対象sourceとprotected sourceのSHA-256を記録する。
4. repository全体pytestを実行し、pass／fail／skipと既存failureを記録する。
5. Big Trades OFFで既存3段chartの位置、寸法、mode、描画、操作、healthを記録する。
6. browser screenshot、bounding box、Console、Network、WebSocket baselineを保存する。
7. production instrumentごとのquantity step、既存setting、初期Manual Min／Max候補をreportする。候補は自動採用しない。
8. Reaction Zoneを含むBig Trades modeのstatic mockを提示する。既存3段chartへ埋め込まない。
9. restore tag `pre-big-trades-20260811`のobject IDと現在HEADの一致を確認する。一致しなければ新たな変更前tag方針をuserへ提示する。
10. V1／V1.1で不足していたReaction Zone／result observationと、V2で追加する範囲を対照表にする。

工程0の完了条件は、source変更0、baseline evidence保存、未決定値一覧、user承認である。

## 60. 工程1：pure core

工程1ではI/Oを含まないpure coreだけを実装する。

- 正規化後trade ordering。
- 40ms same-side chain aggregation。
- Manual／Automatic Size Filter判定。
- deterministic ID生成。
- BigTrade event／fill構築。
- Reaction Zone生成。
- `ABOVE／INSIDE／BELOW` relation。
- zone boundary index。
- source price path range query。
- first exit、touch、reentry、cross、max excursion。
- event-zone link。
- horizon snapshot。
- 1-minute candle observation。

固定vectorとrandomized oracleでcoreの一致を確認する。storage、pipeline、API、WebSocket、UIへ接続しない。feature flagはfalseのまま。工程完了時にtest結果とcheckpointを提示し、承認まで停止する。

## 61. 工程2：config／calibration／artifact

工程2ではstrict config、user settings、calibration、session stats、activation historyを実装する。

1. unknown key、非法Decimal、非法timezone、非法enumを起動前に拒否する。
2. Manual設定versionを保存し、effective timeをsource時刻で固定する。
3. completed sessionをsource-confirmed transitionで確定する。
4. calibration artifactをimmutable＋content hash付きで生成する。
5. activation historyをappend-onlyで保存する。
6. Replayの`RECORDED_ACTIVATION`と研究用`FIXED_RESEARCH`を分離する。
7. weekly／monthly生成はactivateを意味しない。
8. fail-closed理由をstatusへ露出する。

runtime featureはまだfalse。production dataへのbackfill、UI接続、自動activateを行わない。testとartifact例を提示し、承認まで停止する。

## 62. 工程3：storage／Live／Replay

工程3では隔離したtemporary DBからmigrationを開始し、storageとruntimeを接続する。

- §32の全table、index、foreign key相当整合性、schema versionを実装する。
- event＋fills＋zone＋created interaction＋linksを一transactionで保存する。
- commit acknowledgement後だけpublishする。
- state checkpoint、restart recovery、source gap invalidationを実装する。
- LiveとReplayへ同一coreを接続する。
- source-confirmed session transitionでzoneをfinalizeする。
- snapshot／candle observationの遅延到着とidempotent upsertを実装する。
- storage queue overflowをsilent dropにせずfail-closedへ接続する。

production DBを直接migrationしない。feature flagはfalse。Live／Replay同一fixture、restart、gap、atomicityを検証し、承認まで停止する。

## 63. 工程4：WebSocket／API

工程4ではbackend surfaceだけを追加する。

- unified Big Trades batch stream。
- snapshot hydration endpoint。
- event、zone、interaction、snapshot、candle observation、calibration、settings history、health endpoint。
- append-only user assessment作成／訂正endpoint。
- pagination、cursor、version、source identityを実装する。
- REST snapshotからWebSocket継続時の重複／欠落防止を実装する。
- commit未完了dataを返さない。

既存message typeと既存endpoint responseを変更しない。UI接続前にprotocol testを完了し、承認まで停止する。

## 64. 工程5：UI

工程5は、工程0で承認済みのstatic mockに従って実装する。未承認のlayout解釈を追加しない。

1. Big Tradesを既存modeと独立した第3modeとして追加する。
2. event marker、Reaction Zone、status、historyを同一Big Trades viewへ表示する。
3. selected zone panelでorigin event、subsequent interactions、linked events、horizon snapshots、candle observations、read-only contextを時系列表示する。
4. system factsとuser assessmentを視覚的・data的に分離する。
5. exact execution rangeとvisual minimum heightを分離する。
6. zoom、pan、resize、DPR、hydration、reconnectでmarker／zone位置を維持する。
7. DOM／Tape／CVD／Footprint／Flow Price Response／Heatmapの既存meaningとgeometryを変更しない。

protected UIのbefore／after bounding box差分、screenshot、Console、Network、WebSocket、Canvas performanceを提示し、承認まで停止する。

## 65. 工程6：integration／performance／soak

工程6では次をまとめて検証する。

- `BT2-C001`から`BT2-O296`の全contract。
- feature OFF時の完全非介入。
- feature ON時のevent／zone／interaction／snapshot／history一貫性。
- 6000 trade、25000 trade、5000 event＋20000 interaction。
- active zone 10／100／1000／5000の性能とO(N) scan guard。
- Big Trades OFF／ONでTICK age、BAR_UPDATE age、Tape accounting、Book syncの比較。
- 120秒以上live soakとrestart recovery soak。
- repository全体pytest。
- backfill dry-runのみ。production mutationなし。

既存baselineからの新規failure、欠落、geometry変化、silent drop、unbounded memoryが1件でもあれば工程未完了とする。feature flagはfalseのまま。結果を提示し、承認まで停止する。

## 66. 工程7：operational activation

工程7はuserの明示したproduction activation承認後だけ実行する。

1. branch、HEAD、restore tag、dirty stateを再確認する。
2. production DBとconfigのbackupを作成し、restore手順を実測する。
3. migration対象pathとbackup pathを絶対pathで記録する。
4. 最終Manual Min／Maxまたはactive calibration versionをuser指定値へ固定する。
5. activation modeとeffective source timeを記録する。
6. featureを有効化する。
7. health、input age、queue、DB commit、WebSocket continuity、Canvasを確認する。
8. 最低30分のlive soakを行う。
9. 少なくとも3件についてraw trades→cluster→event→zone→interaction→snapshot→UIを照合する。
10. 既存3段chart、Flow Price Response、Tape、Book、Heatmapの非回帰を確認する。

異常時は§67のrollbackを即時実行する。activation完了は、単にUIへmarkerが見えた時点ではない。

## 67. rollback

### 67.1 最短rollback

1. `big_trades.enabled=false`へ戻す。
2. Big Trades runtimeの新規受付を停止する。
3. background writerの未完了transactionをcommitまたは明示rollbackし、状態を記録する。
4. Big Trades UI entryを非表示にする。
5. serviceを通常手順でrestartする。
6. 既存3段chart、Flow Price Response、Tape、Book、Heatmap、healthを確認する。

### 67.2 data

rollback時にBig Trades table、artifact、historyを削除しない。読取対象から外し、原因解析と再開に残す。schema downgradeが必要な場合だけ、backupから別pathへrestoreして照合後に切り替える。

### 67.3 code rollback

変更前基準はtag `pre-big-trades-20260811`である。ただし無関係なuser変更を失う操作は禁止する。`git reset --hard`、`git clean`、workspace全体の上書きを使用しない。Big Trades commitだけを特定し、通常は`git revert <commit>`で戻す。dirty worktreeでは先に差分を記録し、user承認なしにrevertしない。

### 67.4 userが使う指示文

最短停止は次の明示指示で開始する。

```text
Big Trades V2を無効化して、既存機能だけ動く状態へ戻せ。データは削除するな。
```

codeまで戻す場合は次を使用する。

```text
Big Trades V2のcommitだけをrevertしろ。既存変更と保存データは消すな。
```

## 68. checkpoint contract

最初の変更前、各工程完了後、長時間処理の前後、承認要求前、未完了終了前にcheckpointを更新する。最低記録項目は次である。

- JST現在時刻。
- current branch／HEAD／restore tag。
- userが承認した工程と禁止範囲。
- 完了済み作業。
- 未完了作業。
- changed filesと各hash。
- 実行command、pass／fail／skip、performance値。
- source DB identity、logic／settings／calibration／activation version。
- blockerと、そのblockerが止める直接依存工程だけ。
- 次の一操作と再開位置。

checkpointを最後にまとめて作らない。途中状態を逐次保存する。

## 69. 禁止shortcut

次の実装はacceptしない。

1. individual raw tradeをclusterせずSize Filterへ直接入れる。
2. different sideを同一clusterへ混ぜる。
3. equal source timeをarrival順だけで決める。
4. `float`でquantity／price／notional thresholdを判定する。
5. unknown quantityを0扱いする。
6. Manual MinだけでMaxを省略する。
7. Automaticでsample不足時に適当なdefault thresholdへfallbackする。
8. calibration生成とactivateを同一操作にする。
9. Replay過去時刻へ現在active calibrationを適用する。
10. execution rangeではなく任意のcandle high／lowをzoneにする。
11. single-price eventへhit-test用の偽price幅を与える。
12. horizontal lineを描くだけでReaction Zone実装完了とする。
13. price breakでzoneを削除し、その後のretest履歴を失う。
14. active zone全件をtradeごとにlinear scanする。
15. browserでcluster、filter、zone、resultを再計算する。
16. event markerとzone historyを別sourceから無保証で結合する。
17. DB commit前、またはqueue admissionだけでWebSocket publishする。
18. gapを跨いだsnapshotをVALIDにする。
19. stale tradeをtarget horizonの価格に採用する。
20. eventを同一価格帯という理由でmergeする。
21. linked eventを同一participantと表示する。
22. systemが`ABSORPTION CONFIRMED`、buyer win、seller win、entry、exitを自動確定する。
23. user assessmentをsystem fact tableへ保存する。
24. read-only contextをBig Trades event判定へ逆流させる。
25. session終端をwall clockだけで確定する。
26. silent drop、silent fallback、silent correctionを行う。
27. V1／V1.1のSize Filter完成をもってV2全体完成と報告する。
28. protected 3段chartまたはFlow Price ResponseをBig Trades都合で変更する。
29. performance未計測でfeatureを有効化する。
30. checkpoint、test evidence、rollback確認なしに次工程へ進む。

## 70. logic正本とのtraceability

| logic正本 | 本指示書 | 実装対象 |
|---|---|---|
| §0–§7 | §0–§8 | 目的、境界、用語、保護範囲 |
| §8–§12 | §10–§18 | input、ordering、cluster、Manual／Automatic |
| §13–§16 | §19、§32–§37 | event、fill、ID、storage、delivery |
| §17–§22 | §20–§24 | Reaction Zone、relation、interaction、linked event |
| §23–§25 | §25–§26 | horizon snapshot、candle result |
| §26–§27 | §27–§28 | system fact／assessment分離、context |
| §28–§29 | §29–§30、§41–§42 | session、runtime、gap、fail-closed |
| §30 | §55 | fixed evidence vectors |
| §31–§35 | §31–§45 | pipeline、schema、API、UI、performance |
| §36 | §17–§18、§51 | Manual／Automatic equivalence |
| §37 | §21、§44–§45、§54 | performance／observability |
| §38 | §71–§75 | invariants、acceptance、開始条件 |

この表に対応しないlogic変更を実装者判断で追加しない。logic正本と本指示書に矛盾がある場合、進行せず矛盾箇所をuserへ提示する。

## 71. final invariants

1. 一つのaccepted BigTrade eventに一つのevent markerと一つのorigin Reaction Zoneが対応する。
2. eventの事実、zoneの事実、後続価格の事実を後から上書きしない。
3. Reaction Zoneはexecution price rangeであり、予測support／resistanceではない。
4. price break後も同一session内のzone履歴を保持する。
5. effortはevent quantity、resultは後続price pathとして別々に保存する。
6. repeated effortは独立eventのままzoneへlinkする。
7. Fabio式の判断材料を表示するが、Fabioの非公開判断を自動再現したと主張しない。
8. system factとhuman assessmentを混同しない。
9. LiveとReplayは同じsource data、version、logicで同一結果になる。
10. gap、stale、sample不足、artifact不一致はVALIDに見せない。
11. browserはauthoritative calculationを行わない。
12. existing Flow Price Responseと3段chartのmeaning、geometry、runtime pathを変えない。

## 72. acceptance criteria

V2は次の全条件を満たした場合だけacceptする。

### 72.1 四機能

- userがManual Min／Maxを設定し、境界値どおりにeventを選別できる。
- instrument／session／quantity-step／distributionに連動したAutomatic Size Filterを、versioned calibrationとして再現できる。
- accepted event一件ごとのmarker、fill、履歴、raw traceを検索・Replayできる。
- accepted eventのexecution rangeからReaction Zoneを生成し、first exit、touch、reentry、cross、max excursion、horizon、candle close／wick return、later event linkを時系列に追える。

### 72.2 Fabio式判断に必要な表示

selected zone一画面で、最低限次を同時に確認できる。

- どちら側の、どれだけ大きい約定だったか。
- どの価格帯で成立したか。
- その直後と各horizonで価格がどちらへ、何tick動いたか。
- 価格帯を抜けたか、戻ったか、再接触したか。
- 同じ価格帯へ後続の大口約定が来たか。
- 1-minute candleが外でcloseしたか、wickだけ外へ出て戻ったか。
- CVD／Delta／Footprint／Flow Price Responseの同時刻context。
- どの項目がsystem factで、どの項目がuser assessmentか。

この一覧の一部しかない場合、「Fabioと同様の判断材料を使える状態」と報告しない。

### 72.3 determinism／integrity

- 296 test contractsがpassする。
- same input＋same versionsでID、event、zone、interaction、snapshotがbyte-equivalentである。
- DB transactionとWebSocket publish順序に矛盾がない。
- restart、reconnect、Replay、backfillでduplicateと欠落がない。
- active zone 5000でperformance budgetを満たす。
- source gapとstale horizonが明示INVALIDになる。

### 72.4 non-regression

- Big Trades OFFで既存動作とbaselineが一致する。
- Big Trades ONでも既存3段chartのgeometryとmeaningが一致する。
- repository全体testに新規failureがない。
- TICK／BAR_UPDATE age、Tape／Book accounting、CPU／RSSがbudget内である。

### 72.5 operational safety

- restore tag、backup、rollback手順が実測済みである。
- production threshold、calibration、activation modeをuserが明示承認している。
- 30分以上のlive soakと3件以上のend-to-end照合が完了している。
- 未解決blocker、未記録shortcut、未承認仕様判断が0である。

## 73. completion evidence

完了報告には最低限次を添付する。

1. branch、HEAD、commit一覧、restore tag。
2. changed files一覧と要約。
3. logic／settings／calibration／activation versions。
4. 全296件（`BT2-C001`～`BT2-O296`）のcontract結果。
5. repository全体pytest結果。
6. performance表とsoak結果。
7. Big Trades OFF／ONのhealth比較。
8. protected chartのbefore／after screenshotとbounding box差分。
9. 3件以上のraw trades→cluster→event→zone→interaction→snapshot→UI trace。
10. ManualとAutomaticで同一accepted eventを得るequivalence trace。
11. break後retest、reentry、opposite eventを含むzone history trace。
12. gap／stale／fail-closed表示例。
13. rollback実測結果。
14. 残存制約。0件なら0件と明記する。

「test済み」「動作確認済み」だけの要約で代用しない。

## 74. implementation開始前の明示確認事項

本書完成はsource実装開始の承認ではない。実装者は次をuserへ一つずつ明示し、回答を記録する。

1. 開始してよい工程番号。
2. production instrument別Manual Min／Max初期値。
3. Automatic calibrationの初期window、percentile、schedule。
4. calibration activationをV1運用どおり手動限定にするか、別途auto activation仕様を作るか。
5. Big Trades static UI mockの承認。
6. user assessment機能を初回releaseへ含めるか。
7. production activationとbackfillは別承認であることの確認。

未回答値を実装者が推測して埋めない。回答不要のpure core工程だけが明示承認された場合、その範囲だけ進める。

## 75. stop instruction

この指示書を書き終えた時点では、source code変更、dependency追加、DB migration、backfill、service restart、UI変更、feature enableを行わない。

次に進めるのは、userが工程番号または具体的作業を明示した後だけである。
