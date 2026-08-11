# DeltaEngine05M Big Trades Size Filter 実装指示書 V1.1

- 作成日: 2026-08-11
- 対象repository: `C:\Users\user\Desktop\DeltaEngine05M\Delta_Engine_Pro4web`
- logic正本: `ArchitectureRepository/00_Master/DEEPCHARTS_BIG_TRADES_SIZE_FILTER_RECONSTRUCTION_LOGIC_V1_20260811.md`
- 文書状態: 実装前指示書
- 現在の承認範囲: 本指示書の作成まで
- source実装、設定変更、runtime起動、配備: 未承認

## 0. 決定要約

DeltaEngineへ追加する機能は、Fabioの過去動画で`Deep Trades View`と呼ばれ、現在のDeepChartsでは`Big Trades`へ改名された、大口約定のSize Filter相当機能である。

V1で実装する中心処理は次のとおり。

```text
正規化済み個別約定
  → 同方向かつ直前fillから40ms以内の約定を集約
  → clusterのaggregate quantityを計算
  → Manual Min／MaxまたはAutomatic Low／Medium／Strongを適用
  → 通過clusterだけをBig Trade eventとして保存
  → WebSocketと履歴APIへ出力
  → 独立BIG TRADES chartへmarkerと数量を表示
```

V1の完全対応input modeは`AGGREGATE_TRADES`とする。`VOLUME`、`ORDER`、`ICEBERG`という名称だけを見せかけで有効化しない。必要なsource contractが完成するまでUIでは`UNAVAILABLE`とし、選択不能にする。

既存の次の機能とは完全に分離する。

- `LargeTradeDetector`の固定数量Flow Event
- Time & Salesの個別約定filter
- Time & Salesのnotional基準`LARGE ≥`
- Heatmapのaggressive trade bubble
- Flow Price Response
- 3段チャート
- Strategy Engine、Hook、MT5、自動発注

本機能は観測機能であり、売買シグナル、勝率、確率、発注許可を生成しない。

### 0.1 V1.1改訂範囲

V1.0は凍結して保存し、V1.1では次の4点だけを曖昧さのない実装contractへ確定した。Big Tradesの選別logic、Flow Price Response、3段chart、既存indicatorの意味は変更しない。

1. schedule生成calibrationのactivation policyと通常運用コスト。
2. session完了を検出するsource-time triggerと処理順。
3. `candle_id`を算出するcomponentと既存1分足との境界一致検証。
4. Replayが過去時点のactive calibrationを特定するactivation ledgerと選択手順。

V1.0原本:

```text
DEEPCHARTS_BIG_TRADES_IMPLEMENTATION_INSTRUCTION_V1_20260811.md
SHA-256 8C00F57D70566BA04FBCF47108C14A529FAD3C124FA8207211BEECEB4DCA4A73
```

## 1. 実装目的

目的は、通常の小さい約定で画面を埋めず、短時間に分割された同方向約定を合計したうえで、その銘柄と市場状態に対して大きいexecuted activityだけを選別し、数量と価格位置を人間が直接確認できる状態を作ることである。

実装後、userは次を行えること。

1. Manual modeで最小数量と最大数量を指定する。
2. Maxを0にして上限なしにできる。
3. Automatic modeでLow／Medium／Strongを選べる。
4. 使用中の実数量thresholdを画面上で確認できる。
5. BUY、SELL、BOTHを切り替えられる。
6. markerをcluster開始価格、最終価格、VWAPのいずれかへ置ける。
7. marker上のaggregate quantity、fill件数、価格範囲、時間範囲を確認できる。
8. 再起動後も保存済みBig Trade履歴を再読込できる。
9. LiveとReplayへ同じtrade列を与えたとき、同じclusterとmarkerを再生成できる。
10. Automatic較正の履歴期間、基礎値、volatility係数、最終threshold、versionを監査できる。

## 2. 承認境界

### 2.1 本指示書だけでは承認されない操作

この文書を作成したこと自体を、次の承認として扱ってはならない。

- source code変更
- `config/config.yaml`変更
- Docker image build
- container restart
- production deployment
- database migrationの実行
- backfillの実行
- Automatic calibrationの実行
- 既存UIの変更
- Strategy／Hook／注文経路への接続

### 2.2 実装時の承認単位

実装は後述の`GO-BT0`から`GO-BT7`へ分割する。各gateは、そのgate名を含むuserの明示GOを受けてから開始する。

一つのGOを後続全工程の包括承認と解釈しない。

### 2.3 現在の停止位置

本指示書の完成後は停止する。`GO-BT0`を推定して先へ進まない。

## 3. 正本と優先順位

実装判断の優先順位は次のとおり。

1. userの最新の明示指示
2. `ArchitectureRepository/00_Master/PROJECT_MEMORY.md`
3. 本指示書
4. `DEEPCHARTS_BIG_TRADES_SIZE_FILTER_RECONSTRUCTION_LOGIC_V1_20260811.md`
5. 現行module仕様書とWebSocket仕様書
6. 現行source code

本指示書とlogic正本に矛盾が見つかった場合、実装者が勝手に一方を選ばない。矛盾箇所、影響、選択肢をcheckpointへ記録し、該当工程だけを止めてuserへ確認する。

## 4. 名称と意味

### 4.1 製品名の境界

```text
Fabio動画上の旧名: Deep Trades View
DeepCharts現行名:   Big Trades
DeltaEngine表示名:  BIG TRADES
```

現在のDeepChartsに存在するMBO版`Deep Trades`は別機能であり、V1へ混ぜない。

### 4.2 用語

- `trade`: 取引所で成立した一件の正規化済み約定。
- `aggressor side`: 成行側の方向。`BUY`または`SELL`。
- `execution cluster`: 同方向かつ短時間に連続した約定を表示上の一件へ集約したもの。
- `aggregate quantity`: cluster内の全quantity合計。
- `threshold`: marker表示を許可する最小aggregate quantity。
- `Manual`: user指定のMin／Maxで判定するmode。
- `Automatic`: 過去session分布とvolatilityからLow／Medium／Strong thresholdを選ぶmode。
- `marker`: Size Filterを通過したclusterのチャート表示。
- `calibration`: Automatic thresholdを生成する処理と、そのimmutableな結果。

### 4.3 表示禁止の意味

一件のmarkerを次のように表示または記録しない。

- 発注者名
- 機関名
- 同一人物
- parent order確定
- 大口本人
- 買い推奨／売り推奨
- 勝率／確率

表示名は`BIG TRADE`または`AGGREGATED EXECUTION`とする。

## 5. 現行repositoryで確認済みの事実

### 5.1 正規化約定

`src/normalization/normalizer.py`の`NormalizedTrade`は次を持つ。

```text
event_time
trade_time
trade_id
symbol
price: Decimal
quantity: Decimal
side: BUY | SELL
```

`DataNormalizer`は、非正値／非finite拒否、trade ID重複排除、event time整列、out-of-order拒否を行う。

liveの`normalizer.live_reorder_tolerance_ms`は現行0ms、Replayの`reorder_tolerance_ms`は現行500msである。Big Tradesはraw eventを再正規化せず、`DataNormalizer`がacceptしてreleaseした`NormalizedTrade`だけを入力にする。

ただし現行DataNormalizerは、同一`event_time`のtradeをarrival sequence順でreleaseする。logic正本は同時刻をtrade ID順とするため、Big Trades内部だけに同一millisecond用の小さいordering bufferを置く。DataNormalizer本体の既存順序contractは変更しない。

### 5.2 aggressor side

`config/profiles/binance.yaml`はBinance Futures `@trade`のmaker flag `m`を次へ解決する。

```text
m == true  → SELL
m == false → BUY
```

Big Trades側で色や価格位置からsideを再推定しない。

### 5.3 共通処理位置

`src/pipeline.py`にはLive／Replayの両方で、正規化済みtradeを処理する`handle(normalized)`が存在する。

現行live `handle`は概ね次の順である。

```text
on_accepted_trade
trade storage
native coordinator
Flow Price Response
on_trade UI projection
CVD
Footprint
Absorption
Flow detectors
bar close処理
```

Big Trades coreは、この正規化済みtrade経路へ一度だけ接続する。WebSocket用Tape batchから再計算しない。

### 5.4 現行Time & Sales

`webapp/tape.py`の`TapeBatcher`は全accepted tradeを順序付き`TAPE_UPDATE`へ変換する。

`webapp/static/time_sales.js`の現行filterは次である。

```text
個別trade quantityのminimum
個別trade notionalのminimum
個別trade notionalのLARGE threshold
side表示
```

これは40ms execution clusterへ適用するSize Filterではない。今回の実装で現行Time & Salesの意味を変更しない。

### 5.5 現行LargeTradeDetector

`src/orderflow/flow_detector.py`の`LargeTradeDetector`は、個別trade quantityを固定`flow_detector.large_trade_min_qty`と比較し、Flow Eventを生成する。

このdetectorは既存FLOW EVENTS用である。Big Tradesで置換、再利用、閾値上書き、category統合を行わない。

### 5.6 保存

`src/database/storage.py`は、`BackgroundStorageWriter`のbounded FIFOを通じてParquetとDuckDBへ書く。Big Trades履歴も同じbackground writerへ新しい明示kindとして接続し、live event loopでDuckDB／Parquetへ同期書込みしない。

### 5.7 WebSocketと履歴

- `webapp/push_broker.py`は共通`v: 1` envelopeを使う。
- `webapp/main.py`はcallbackをbrokerへ接続する。
- `webapp/history.py`はDuckDB history queryを担当する。
- 現行Tapeはstream UUID、sequence、drop countを持つ。

Big Tradesも独自stream IDとsequenceを持ち、Tape streamのsequenceを流用しない。

### 5.8 中央chart領域

現行中央panelは`FOOTPRINT | HEATMAP`切替である。V1はここへ第三mode`BIG TRADES`を追加する。

既存FootprintとHeatmapを削除、置換、縮小しない。

## 6. 絶対に変更しない範囲

userの別の明示指示がない限り、次を変更しない。

### 6.1 完成済み観測機能

- `src/orderflow/flow_price_response.py`
- Flow Price Responseの6時間窓、状態分類、outcome保存
- 3段チャートのPRICE／CVD+Delta／VOLUME構成
- 3段チャートの高さ、比率、zoom、pan、選択、8パターン
- 既存CVD、Delta、Volume、OIの意味

### 6.2 既存indicator

- `LargeTradeDetector`の既存出力
- Sweep、Exhaustion、Unfinished Auction、Tape Analyzer
- Absorption、Imbalance、Footprintの判定
- DOM／Heatmapのbook contract
- Time & Salesのaccepted trade contract

### 6.3 発注系

- Hook routing
- Strategy Engine
- MT5 bridge
- execution flag
- algorithmic trading設定
- order送信

Big Trade eventをHook、Strategy、SignalEngine、MT5へ渡さない。

### 6.4 data

- 既存DuckDB tableのdrop／rename／truncate
- 既存Parquetの書換え
- raw recordingの削除
- 現行historyの再分類上書き

## 7. 目標architecture

```text
DataNormalizer
  │ NormalizedTrade
  ├─────────────── existing CVD / Footprint / Flow / Tape
  │
  └─ BigTradesRuntime
       ├─ SameMillisecondTradeOrderBuffer
       ├─ ExecutionClusterAggregator
       ├─ BigTradesFilter
       ├─ BigTradesSessionAccumulator
       ├─ BigTradesCalibrationBook
       ├─ BigTrade accepted event
       │    ├─ BackgroundStorageWriter
       │    ├─ in-memory recent ring
       │    └─ callback
       └─ status / counters
                 │
                 v
          BigTradeBatcher
                 │
                 v
          PushBroker BIG_TRADES_UPDATE
                 │
                 v
          big_trades.js / independent Canvas
```

calibrationのpure計算はlive runtimeとoffline toolで同じmoduleを使用する。

```text
stored trades + stored 1m candles
        ↓
tools/calibrate_big_trades.py
        ↓
same aggregator + same calibrator
        ↓
immutable calibration artifact
        ↓
runtime validation / activation
```

## 8. V1 input mode

### 8.1 有効mode

```text
AGGREGATE_TRADES
```

入力はBinance Futures `@trade`からDataNormalizerが生成した個別executed tradeである。

### 8.2 schema上だけ予約するmode

```text
VOLUME
ORDER
ICEBERG
```

予約modeはenumとして定義してよいが、runtime factoryは`UnsupportedInputMode`でfail closedにする。UIではdisabled optionと`SOURCE UNAVAILABLE`を表示する。

### 8.3 見せかけ実装の禁止

- `ORDER`へtrade IDをorder IDとして渡さない。
- `ICEBERG`へ現行DOM wallまたはreload候補をそのまま渡さない。
- `VOLUME`へ一件のtrade quantityを名前だけ変えて渡さない。
- Binance公開tradeに存在しないparent order IDを生成しない。

## 9. 数値と時刻の契約

### 9.1 Decimal

次はPython `Decimal`だけで計算する。

- price
- quantity
- aggregate quantity
- aggregate notional
- VWAP
- threshold
- true range
- normalized true range
- volatility
- volatility factor

判定経路で`float()`、NumPy float、JavaScript Numberをauthoritative計算へ使用しない。

frontendは表示のpixel座標計算にNumberを使用できるが、serverから受け取った数量文字列を判定し直さない。

### 9.2 UTC source time

cluster判定は`NormalizedTrade.event_time`をUTCへ正規化して使用する。wall clock、browser受信時刻、WebSocket受信時刻で40msを測らない。

### 9.3 millisecond

```text
event_time_ms = floor(event_time_utc_epoch_microseconds / 1000)
gap_ms = current.event_time_ms - previous.event_time_ms
```

Binance sourceがmillisecond精度であるため、V1の集約窓はinteger millisecondsで固定する。

### 9.4 session

現行24時間crypto marketのV1 sessionは`UTC 00:00:00.000`から次のUTC 00:00直前までとする。

```text
session_template = CRYPTO_UTC_DAY
session_id = YYYY-MM-DD UTC
```

進行中UTC日はAutomatic較正へ入れない。

### 9.5 candle ID

V1のaggregation candle timeframeはconfigで固定した`1m`とする。

```text
candle_id = floor_utc_bucket(event_time_utc, 60 seconds)
```

`candle_id`は既存candle builderから受け取らない。`BigTradesRuntime`が新規共通pure function `src/orderflow/big_trades/time_buckets.py::floor_utc_bucket()`を呼び、`NormalizedTrade.event_time`から自前で算出する。

`floor_utc_bucket()`はtimezone-aware UTC timestampだけを受理し、UTC epoch microsecondsを60秒単位で整数floorする。local timezoneの`replace(second=0)`、browser時刻、wall clockを使用しない。

既存CVDが確定した1分足の`bar_time`はclusterの`candle_id`供給元ではない。ただし同じsource trade列から得たBig Tradesのminute boundaryとCVDの`bar_time`をruntimeで照合する。対応する境界が一致しない場合は`CANDLE_BOUNDARY_MISMATCH`を記録し、Big Tradesだけをfail closedにする。CVD、Flow Price Response、3段chartを停止または補正しない。

userが画面上でFootprint本数やHeatmap期間を変えてもcluster境界を変えない。

## 10. logic version

次の文字列を全event、calibration、settingsへ保存する。

```text
logic_version = BTLOGIC-1.0
```

次の値を変更する場合はlogic versionを上げ、新旧を同じversionとして保存しない。

```text
aggregation_window_ms = 40
history_sessions = 20
recent_volatility_sessions = 5
minimum_valid_sessions = 10
target_low = 20
target_medium = 9
target_strong = 2
volatility_factor_min = 0.75
volatility_factor_max = 1.50
session_template = CRYPTO_UTC_DAY
aggregation_candle_timeframe = 1m
```

これらのlogic定数を通常UIから変更可能にしない。

## 11. 設定contract

`src/config.py`と`config/config.yaml`へ、独立した`big_trades` sectionを追加する。

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
  recent_event_capacity: 5000
  history_api_max_limit: 5000
  batch_interval_ms: 100
  batch_max_events: 100
  batch_pending_capacity: 5000
  max_fills_per_cluster: 10000
```

YAMLの上記数値は例であり、`manual_min_quantity`と`quantity_step`のproduction値はGO-BT0で現在symbol metadataとuser意向を確認して固定する。

### 11.1 enum

```text
input_mode:
  AGGREGATE_TRADES | VOLUME | ORDER | ICEBERG

filter_mode:
  MANUAL | AUTOMATIC

automatic_intensity:
  LOW | MEDIUM | STRONG

side_filter:
  BOTH | BUY | SELL

marker_price_mode:
  START_PRICE | LAST_PRICE | VWAP_PRICE

calibration_schedule:
  MANUAL | WEEKLY | MONTHLY

calibration_activation_policy:
  SCHEDULED_SESSION_BOUNDARY | MANUAL_ONLY

replay_calibration_mode:
  HISTORICAL_ACTIVATION | FIXED_RESEARCH
```

### 11.2 validation

- `enabled`はboolean。
- `manual_min_quantity`はfinite Decimal stringかつ0以上。
- `manual_max_quantity`はfinite Decimal stringかつ0以上。
- Maxが0でない場合、MaxはMin以上。
- `quantity_step`はfinite Decimal stringかつ0より大きい。
- capacityとbatch値はbooleanを除くintegerかつ1以上。
- unknown keyは現行Config contractどおりstartup error。
- unsupported input modeを選んだ設定はstartup時に明示error。silent fallbackしない。
- `calibration_activation_policy`と`replay_calibration_mode`は上記enum以外を拒否する。
- `FIXED_RESEARCH`はproduction history namespaceへ書き込めない。

### 11.3 feature flag

source実装完了時点でも`enabled: false`を維持する。GO-BT7のproduction activationでuserが明示承認した場合だけtrueへ変更する。

## 12. runtime settings

### 12.1 userが変更できる項目

```text
filter_mode
manual_min_quantity
manual_max_quantity
automatic_intensity
side_filter
marker_price_mode
```

logic定数、quantity step、session templateはUIから変更できない。

### 12.2 settings snapshot

open cluster開始時にeffective settingsをimmutable snapshotとして保持する。

cluster途中でsettingが変更されても、そのclusterは開始時settingsで最後まで判定する。次に開始するclusterから新settingsを使用する。

### 12.3 settings ID

settings内容をkey順canonical JSONへ変換し、SHA-256で次を作る。

```text
settings_id = "bts1_" + lowercase_sha256
```

hash対象:

```text
logic_version
symbol
venue
input_mode
filter_mode
manual_min_quantity
manual_max_quantity
automatic_intensity
side_filter
marker_price_mode
calibration_id or null
```

### 12.4 settings保存

UIから有効なsetting変更を受理したら、append-only settings historyへ「変更要求」として保存する。受理時刻をeffective境界として扱わない。`config.yaml`をHTTP endpointから直接書き換えない。

保存内容:

```text
settings_id
requested_at_utc
previous_settings_id
全設定値
request_source = UI | CONFIG | REPLAY
request_status = PENDING | SUPERSEDED | ACTIVATED | REJECTED
```

設定保存に失敗した場合は変更を適用しない。

settings正本はversioned JSONとpending pointerにする。active pointerはcommitted activation artifactから再構築できるcacheとする。

```text
data_05M/settings/big_trades/versions/<settings_id>.json
data_05M/settings/big_trades/pending/<symbol>_<venue>_<input_mode>.json
data_05M/settings/big_trades/active/<symbol>_<venue>_<input_mode>.json
```

REST PUTの受理順を固定する。

1. request全体を検証する。
2. version JSONをtemporary write、flush、fsync、read-back、hash確認する。
3. append-only settings historyへ`PENDING`を保存する。
4. pending pointerを同じ方式で`os.replace`する。
5. responseへ`settings_id`と`activation_status=PENDING`を返す。

1～4の失敗ではpending requestを成立させず、runtimeのeffective settingsとactive pointer cacheを変更しない。HTTP requestから`config.yaml`を編集しない。

同じsymbol／venueへactivation前のrequestが複数来た場合、最後に完全保存できたrequestだけをpending pointerとする。それ以前の未activation requestは`SUPERSEDED`としてappendし、activation ledgerを作らない。

### 12.5 effective activation boundary

settingsまたはcalibrationを実際に切り替える境界は、受理時のlast tradeではなく「次に開始するclusterの最初のaccepted trade」とする。そのtradeから次を得る。

```text
effective_session_id
effective_from_event_time
effective_from_trade_id
```

Automatic calibrationを切り替えるときは、candidate `calibration_id`を含む新しいimmutable settings versionを先に生成する。filter mode、intensity、side、marker mode、Manual値は直前effective settingsから変えず、`calibration_id`だけをcandidateへ置き換えて§12.3の新settings IDを計算する。calibrationとderived settingsのどちらか一方しか保存できない場合はactivateしない。Manual modeのeffective settingsは`calibration_id = null`とする。

切替順は次で固定する。

1. current tradeが既存open clusterへjoinするかを、現行40ms／side／session／candle ruleで副作用なく判定する。joinする場合は旧snapshotで同clusterへ入れ、activationをpendingのまま残す。setting変更を理由にclusterを強制分割しない。
2. current tradeが自然なsplit条件を満たすかopen clusterがすでにflush済みの場合だけ、旧clusterを旧snapshotで確定し、current tradeを次clusterのfirst tradeとして上記effective keyを固定する。current tradeはまだaggregatorへ入れない。
3. settings／calibration／symbol／venue／input mode／logic versionを再検証する。
4. §26.6のactivation artifactをtemporary fileへ書き、flush、fsync、read-back、hash検証する。
5. `os.replace`でfinal activation artifactへcommitする。このatomic renameだけをactivationのdurable commit pointとする。
6. runtimeのeffective snapshotをcommitted activationへ入れ替える。
7. derived active pointer cacheをcommitted activationへ更新する。
8. first tradeを新snapshotでclusterへ入れる。
9. DuckDB／Parquet mirrorをenqueueする。

4または5に失敗した場合だけ旧runtime snapshotを維持し、first tradeを旧snapshotで処理する。新versionを使用したeventを一件も作らない。5成功後はactivationがcommittedであり、旧versionへ自動rollbackしない。6に失敗した場合はcurrent tradeをBig Tradesへ入れずBig Tradesだけをfail closedにし、restart時にcommitted artifactから回復する。7のcache更新失敗ではcommitted activationとruntime snapshotを維持し、`DEGRADED_POINTER_CACHE`を表示する。9のmirror失敗ではauthoritative artifactを維持してretryし、Replay正本をDBの書込成否で変えない。

## 13. ExecutionClusterAggregator

新規`src/orderflow/big_trades/aggregation.py`へpureなstate machineとして実装する。

### 13.0 SameMillisecondTradeOrderBuffer

aggregatorへ渡す直前に、同じ`event_time_ms`のtradeだけをbufferする。

処理規則:

1. 最初のtradeをそのmillisecond bucketへ保持する。
2. 同じ`event_time_ms`はbucketへ追加する。
3. より新しい`event_time_ms`を受け取った時点で、旧bucketを`trade_id`整数昇順へsortしてaggregatorへ渡す。
4. stream end、disconnect、session flushではbucketをsortしてからaggregatorをflushする。
5. 最後にrelease済みのmillisecondより古いtradeは`LATE_AFTER_RELEASE`として拒否する。

bufferは一つのmillisecond bucketだけを保持する。wall-clock timerは使用しない。

このbufferにより、同じaccepted trade集合ならarrival orderが異なってもBig Tradesのcluster構成を同じにする。

### 13.1 open cluster fields

```text
symbol
side
first_trade_id
last_trade_id
first_time
last_time
first_time_ms
last_time_ms
first_price
last_price
low_price
high_price
total_quantity
weighted_notional
fill_count
distinct_prices
session_id
candle_id
settings_snapshot
trade_fills
```

### 13.2 join条件

現在tradeをopen clusterへ加算する条件は次のANDで固定する。

```text
same symbol
same aggressor side
current.event_time_ms - cluster.last_time_ms <= 40
same session_id
same 1m candle_id
```

同一price条件は入れない。

### 13.3 連鎖窓

40msはcluster最初からではなく直前fillから測る。

```text
0ms → 35ms → 70ms
```

は各gapが35msなので一clusterである。

### 13.4 close原因

enumを固定する。

```text
SIDE_CHANGED
TIME_GAP_EXCEEDED
SESSION_CHANGED
CANDLE_CHANGED
STREAM_ENDED
STREAM_DISCONNECTED
SYMBOL_CHANGED
SETTINGS_FORCED_FLUSH
MAX_FILLS_EXCEEDED
```

setting変更だけではopen clusterを強制closeしない。`SETTINGS_FORCED_FLUSH`はadminまたはshutdown手順で明示flushした場合だけ使用する。

### 13.5 max fills safety

`max_fills_per_cluster`を超えた場合、clusterを二つへsilent splitしない。

1. 現clusterを`MAX_FILLS_EXCEEDED`かつ`INVALID_CLUSTER`として閉じる。
2. markerを出さない。
3. counterとerror logを増やす。
4. 現在tradeから新clusterを開始する。

### 13.6 finalized fields

```text
aggregate_quantity = sum(quantity)
aggregate_notional = sum(price × quantity)
vwap = aggregate_notional / aggregate_quantity
duration_ms = last_time_ms - first_time_ms
price_level_count = count(distinct price)
```

`aggregate_quantity`がSize Filterの入力である。

## 14. Manual filter

新規`src/orderflow/big_trades/filtering.py`へpure functionとして実装する。

```text
if aggregate_quantity < manual_min_quantity:
    REJECT_BELOW_MIN
elif manual_max_quantity > 0
     and aggregate_quantity > manual_max_quantity:
    REJECT_ABOVE_MAX
else:
    ACCEPT
```

Min、Maxと同値はACCEPTする。Max 0は上限なし。

side filterはquantity判定後に適用する。

```text
BUY setting  + SELL cluster → HIDE_BY_SIDE
SELL setting + BUY cluster  → HIDE_BY_SIDE
BOTH                        → sideによる非表示なし
```

side filterを大口規模判定へ混ぜない。

## 15. Automatic calibration母集団

### 15.1 key

次の組合せごとに独立する。

```text
symbol
venue
input_mode
session_template
quantity_unit
logic_version
```

### 15.2 履歴範囲

`as_of`より前の直近20完了UTC sessionを使用する。`as_of`を含む進行中sessionを使わない。

### 15.3 look-ahead禁止

calibrationの`history_end_session`より後のtradeまたはcandleを一件でも使用した場合、artifactを無効とする。

Replayで時刻Tのmarkerを再現する場合、T以前に実際にactiveになったcalibrationだけを使用する。後日作られたthresholdを過去のlive markerへ遡及適用しない。

defaultの`HISTORICAL_ACTIVATION`では、calibration artifactの`created_at_utc`、file timestamp、現在のactive pointerから過去のactive versionを推定しない。§26.6のappend-only activation historyだけを正本とする。

Replay開始前に`data_05M/settings/big_trades/activations/`のauthoritative immutable artifactから対象symbol／venue／input modeのactivation rowを読込み、次の昇順へ整列し、同一effective keyの重複または内容不一致を検証する。DuckDB／Parquetは検索用mirrorであり、それだけを正本にしない。

```text
(effective_from_event_time, effective_from_trade_id, activation_id)
```

各clusterのfirst trade keyを次とする。

```text
cluster_key = (first_event_time_utc, first_trade_id)
```

そのclusterへ適用するrowは、同じsymbol／venue／input mode／logic versionについて次を満たす最後の一件とする。

```text
(row.effective_from_event_time, row.effective_from_trade_id) <= cluster_key
```

選択したrowの`settings_id`と`calibration_id`をimmutable artifactから読込み、content hash、logic version、key、quantity stepを再検証してからclusterを開始する。同じtimestampでは`trade_id`が小さい境界を先とする。cluster途中で次のactivation境界へ達してもopen clusterのsnapshotを変更せず、そのclusterを閉じた後の次clusterから適用する。

必要なactivation row、settings artifact、calibration artifactのいずれかが欠ける場合は`REPLAY_ACTIVATION_HISTORY_MISSING`、不整合なら`REPLAY_ACTIVATION_HISTORY_INVALID`としてBig Trades Replayをfail closedにする。現在のcalibrationまたは任意versionへfallbackしない。

`FIXED_RESEARCH`はuserがReplay requestでsettings IDとcalibration IDを明示した非production比較専用modeとする。このmodeの出力先は`research/big_trades/<run_id>/`へ隔離し、productionの`big_trade_events`、history API、active pointer、activation historyを作成・更新・上書きしない。`FIXED_RESEARCH`の結果をhistorical live再現と表示しない。

## 16. session ranking

各完了sessionへliveと同じaggregatorを適用し、cluster aggregate quantityを降順にする。

```text
Q_s[1] >= Q_s[2] >= ...
```

強度ごとの値:

```text
LOW    = Q_s[20]
MEDIUM = Q_s[9]
STRONG = Q_s[2]
```

必要順位未満のsessionは、その強度の母集団から除外する。

有効sessionが10未満の強度が一つでもある場合、新calibration全体を`INSUFFICIENT_HISTORY`とする。Lowだけ新しく、Strongだけ旧値という混合versionを作らない。

## 17. median contract

値を昇順に並べ、Decimalで次を使う。

```text
奇数n: values[n // 2]
偶数n: (values[n / 2 - 1] + values[n / 2]) / 2
```

各強度のsession threshold中央値:

```text
base_low
base_medium
base_strong
```

標準libraryがfloatを返すmedian関数を使用しない。

## 18. volatility contract

### 18.1 1分足

保存済み`candles` tableの`timeframe = '1m'`を使用する。1分足が存在しないsessionを任意補間しない。

### 18.2 True Range

```text
TR_i = max(
  high_i - low_i,
  abs(high_i - previous_close_i),
  abs(low_i - previous_close_i)
)

NTR_i = TR_i / close_i
```

session最初のbarは、直前session最後の有効closeを`previous_close`に使う。取得できない場合、その最初のbarだけNTR対象から除外する。

### 18.3 session volatility

```text
session_volatility = Decimal median(valid NTR in the session)
```

HLC非正値、非finite、high < low、close <= 0のbarはinvalidとして除外し、件数を記録する。

有効1分barがsession期待本数の95%未満なら、そのsessionのvolatilityを無効とする。24時間crypto sessionの期待本数は1440本である。

### 18.4 baselineとrecent

```text
baseline_volatility = median(last 20 valid completed session volatilities)
recent_volatility   = median(last 5 valid completed session volatilities)
```

20または5の必要件数を満たさない場合、volatility factorは1.00とし、statusへ`VOLATILITY_FALLBACK_1`を保存する。quantity ranking自体の10-session gateは別に維持する。

### 18.5 factor

Decimal context precisionを34へ固定して平方根を計算する。

```text
raw_factor = sqrt(recent_volatility / baseline_volatility)
volatility_factor = clamp(raw_factor, Decimal("0.75"), Decimal("1.50"))
```

baselineが0または無効なら1.00。

## 19. final Automatic threshold

```text
raw_low    = base_low    × volatility_factor
raw_medium = base_medium × volatility_factor
raw_strong = base_strong × volatility_factor
```

quantity stepへ上方向丸めする。

```text
round_up(value, step) = ceil(value / step) × step
```

Python実装はDecimalの`ROUND_CEILING`を使用する。

```text
auto_low    = round_up(raw_low, quantity_step)
auto_medium = round_up(raw_medium, quantity_step)
auto_strong = round_up(raw_strong, quantity_step)

auto_medium = max(auto_medium, auto_low + quantity_step)
auto_strong = max(auto_strong, auto_medium + quantity_step)
```

不変条件:

```text
auto_low < auto_medium < auto_strong
```

Automatic Maxは0、すなわち上限なし。

## 20. calibration IDとartifact

### 20.1 deterministic ID

threshold計算に使った全authoritative fieldをcanonical JSON化し、SHA-256で次を作る。

```text
calibration_id = "btcal1_" + lowercase_sha256
```

hash対象には`created_at`やlocal pathを含めない。同じ入力履歴とlogicから同じIDを生成する。`created_at_utc`はartifact作成の監査情報にすぎず、calibrationがactiveだった時刻またはReplay適用境界の証拠として使用しない。

### 20.2 artifact path

```text
data_05M/calibration/big_trades/
  calibrations/<calibration_id>.json
```

active calibrationを示す唯一の正本は§26.6のcommitted activation artifactとする。`data_05M/settings/big_trades/active/<symbol>_<venue>_<input_mode>.json`は起動高速化用のderived cacheであり、正本ではない。calibration directoryへ別のactive pointerを作らない。

### 20.3 atomic write

1. 同一directoryへtemporary fileを書き込む。
2. flushする。
3. fsyncする。
4. read-backしてschemaとSHA-256を検証する。
5. `os.replace`でfinalへ置換する。

既存final artifactを先に削除しない。active pointer cacheの更新はartifactとderived settingsの検証完了後に§12.5の順で行う。

### 20.4 immutable

同じcalibration IDのfileが存在し、内容hashが一致すればidempotent success。不一致ならcollisionとして停止する。上書きしない。

### 20.5 artifact必須field

```json
{
  "schema_version": 1,
  "logic_version": "BTLOGIC-1.0",
  "calibration_id": "btcal1_...",
  "symbol": "BTCUSDT",
  "venue": "BINANCE",
  "input_mode": "AGGREGATE_TRADES",
  "session_template": "CRYPTO_UTC_DAY",
  "quantity_unit": "BASE_ASSET",
  "quantity_step": "0.001",
  "history_start_session": "...",
  "history_end_session": "...",
  "valid_sessions_low": 0,
  "valid_sessions_medium": 0,
  "valid_sessions_strong": 0,
  "base_low": "...",
  "base_medium": "...",
  "base_strong": "...",
  "baseline_volatility": "...",
  "recent_volatility": "...",
  "volatility_factor": "...",
  "volatility_status": "EXACT|VOLATILITY_FALLBACK_1",
  "auto_low": "...",
  "auto_medium": "...",
  "auto_strong": "...",
  "aggregation_window_ms": 40,
  "aggregation_candle_timeframe": "1m",
  "target_events": {"LOW": 20, "MEDIUM": 9, "STRONG": 2},
  "source_manifest_sha256": "...",
  "content_sha256": "..."
}
```

## 21. calibration実行方法

### 21.1 pure calibrator

`src/orderflow/big_trades/calibration.py`はfile I/O、DuckDB、wall clockを持たないpure計算moduleにする。

### 21.2 offline command

新規`tools/calibrate_big_trades.py`を作る。

```powershell
python -m tools.calibrate_big_trades `
  --config config/config.yaml `
  --as-of 2026-08-11T00:00:00Z `
  --dry-run
```

本実行は`--write-artifact`を明示した場合だけfileを作る。`--activate`は別flagとし、artifact生成とactivation request登録を分離する。`--activate`を指定してもcommand実行時刻でactive pointerを即時変更せず、`USER_CALIBRATION` requestをpending保存し、§12.5の次cluster first tradeでeffectiveにする。

### 21.3 runtime session summaries

session完了はwall clock、timer、process終了、UTC 00:00を過ぎたというOS時刻だけでは確定しない。keyごとに、現在sessionと異なる`session_id`を持つ最初のaccepted `NormalizedTrade`を受け取った時点をsource-confirmed transitionとする。

```text
previous_session_id = runtimeが保持する直前accepted tradeのsession_id
next_session_id = current accepted tradeのsession_id
session_transition = next_session_id != previous_session_id
```

`session_id`が逆行したtradeは通常transitionとして処理せず、既存ordering／late trade contractに従って拒否またはfail closedにする。

session transition時の処理順を固定する。

1. current tradeをBig Trades aggregatorへまだ入れない。
2. CVDがcurrent tradeの処理によって確定した旧session最後の1分足を§28.3の順で先に受け取る。
3. 旧sessionに属するSameMillisecondTradeOrderBufferを全flushする。
4. 旧sessionのopen clusterを`SESSION_CHANGED`で確定する。
5. 旧sessionの全cluster quantityと全受領済み1分足を集計し、session invariantを検証する。
6. `big_trade_session_stats`をdurable storageへ保存し、成功を確認する。
7. current tradeの新sessionがWEEKLY／MONTHLY schedule boundaryなら、保存済み完了sessionだけでcalibrationを生成し、artifactを検証する。
8. §21.5のpolicyが許可する場合、pending settings／calibrationをcurrent tradeのeffective keyへbindingし、activation artifactをcommitしてactive pointer cacheを更新する。
9. current tradeを、新たに確定したeffective snapshotで新session最初のclusterへ入れる。

2で確定candleがない場合は存在しないbarを生成しない。保存済みbar coverageをそのまま記録する。6が失敗した場合、旧sessionを完了済み較正母集団へ入れず、scheduled calibrationを生成・activateしない。旧active versionを維持し、Big Trades storage statusを`DEGRADED_STORAGE`にする。

stream終了またはshutdown時はbufferとclusterをflushできるが、次sessionのaccepted tradeが来ていないcurrent sessionを「完了session」として保存・較正利用しない。最後のtrade後にwall clockが何日進んでも同じである。次sessionのaccepted tradeが来るまでcurrent sessionは`OPEN_UNCONFIRMED`である。

live runtimeはsource-confirmed完了sessionごとに次だけを保存する。

- cluster count
- 上位20 aggregate quantities
- 有効1分bar count
- session NTR median
- invalid trade／bar count
- source開始／終了時刻
- content hash

完了summaryのauthoritative artifact pathを次で固定する。

```text
data_05M/calibration/big_trades/session_stats/
  <logic_version>/<venue>/<symbol>/<input_mode>/<session_id>.json
```

artifactは§26.3の全fieldをcanonical JSONで持ち、§20.3と同じatomic write／read-back／content hash検証を行う。同じkey・同じhashはidempotent、同じkey・異なるhashは`SESSION_STATS_COLLISION`としてscheduled calibrationを停止する。§21.3手順6の「durable保存成功」は、このauthoritative artifactのread-back成功を意味する。DuckDB／Parquetは同じrowのmirrorであり、background writerの遅延を理由に異なるsummaryを計算しない。

weekly／monthly再較正は、この保存済みsession summary artifactから同じpure calibratorを呼ぶ。全20日raw tradesをlive event loop上で毎回再走査しない。

session途中にprocess restartまたはsource gapがあった場合、そのsessionを`RESTART_TRUNCATED`または`SOURCE_GAP`としてAutomatic母集団から除外する。次session trade到着時に欠損区間をwall clockや推定値で補完しない。保存済みraw tradesからのoffline再構築は別の明示GOによるbackfillだけで行う。

### 21.4 schedule

- `MANUAL`: 自動生成しない。
- `WEEKLY`: source-confirmed transitionで`ISO-week(next_session_id) != ISO-week(previous_session_id)`になった最初のcurrent tradeについて、新session clusterへ入れる前に一度だけ作成する。source gapで月曜日のtradeがなく火曜日が最初でも、週境界を越えた一回として扱う。
- `MONTHLY`: source-confirmed transitionで`UTC-year-month(next_session_id) != UTC-year-month(previous_session_id)`になった最初のcurrent tradeについて、新session clusterへ入れる前に一度だけ作成する。月1日のtradeがなくても月境界を越えた一回として扱う。

schedule period IDはWEEKLYならISO week-yearを含む`YYYY-Www`、MONTHLYなら`YYYY-MM`とする。schedule boundary IDは`<schedule>|<schedule_period_id>|<symbol>|<venue>|<input_mode>|<logic_version>`とする。同じboundary IDと同じsource manifestで二重versionを作らない。process restart後も保存済みboundary IDを確認する。

schedule実行結果はcalibration artifact本体へ混ぜず、次のimmutable run artifactへ保存する。これにより、同一入力から同一calibration IDを作る§20.1のidentityを変えない。

```text
data_05M/calibration/big_trades/schedule_runs/
  <sha256(schedule_boundary_id + "|" + source_manifest_sha256)>.json
```

run artifact必須field:

```text
schedule_boundary_id
source_manifest_sha256
attempted_at_source_event_time
candidate_calibration_id or null
result = ACTIVATED | GENERATED_PENDING | VALIDATION_FAILED | STORAGE_FAILED | SUPERSEDED_BY_USER_REQUEST
failure_code or null
content_sha256
```

`attempted_at_source_event_time`はboundaryを検出したcurrent tradeのsource timeであり、wall clockではない。同じboundary IDとsource manifestのrun artifactが存在すれば再生成せず、その保存済みresultへ従う。`VALIDATION_FAILED`または`STORAGE_FAILED`をruntimeが自動retryし続けない。

scheduled activation commit後、run artifact保存前にprocessが停止した場合は、startup時にcommitted activationのreason、effective session、参照calibrationのsource manifestから同じboundary IDを再構築し、欠けた`ACTIVATED` run artifactだけをmaterializeする。新candidateまたは二件目のactivationを作らない。

### 21.5 activation

V1.1で`calibration_schedule`を`WEEKLY`または`MONTHLY`に設定した場合のdefault activation contractは次の組合せとする。初期config例の`MANUAL`を自動で`WEEKLY`へ変更する意味ではない。

```text
calibration_schedule = WEEKLY または MONTHLY
calibration_activation_policy = SCHEDULED_SESSION_BOUNDARY
```

この組合せでは、§21.4のscheduled calibrationが生成され、schema、content hash、logic version、symbol、venue、input mode、quantity step、履歴範囲、最低有効session数の全validationを通過した場合に限り、同じsource-confirmed transitionにある新session最初のclusterから自動activateする。activation historyのreasonは`SCHEDULED_WEEKLY`または`SCHEDULED_MONTHLY`とする。

通常運用でuserが週次または月次versionを手で選ぶ回数は0回である。user作業が必要になるのは、validation失敗、artifact／storage不整合、明示的なrollback、policy変更の場合だけである。

通常運用コストを次で固定する。

| schedule | system処理回数／key | raw trade再走査 | 定常user操作 |
|---|---:|---:|---:|
| `MANUAL` | 0 | 0 | userが生成・activateを要求した時だけ |
| `WEEKLY` | 最大1回／UTC週 | 0。最大20件のsession summaryを読む | 0回／週 |
| `MONTHLY` | 最大1回／UTC月 | 0。最大20件のsession summaryを読む | 0回／月 |

失敗時のuser操作は定常作業ではなく例外対応であり、一件の失敗につきcandidate確認後にretry、rollback、`MANUAL_ONLY`維持のいずれかを明示選択する。runtimeが自動で失敗versionを再activateし続けない。

次の場合は新calibrationをactiveにしない。

- calibration生成またはvalidation失敗。
- session statsのdurable保存失敗。
- activation artifactのvalidationまたはatomic commit失敗。
- active keyとartifact keyの不一致。

失敗時は旧active calibrationをそのまま維持し、statusへ`CALIBRATION_ACTIVATION_FAILED`、失敗reason、旧calibration ID、candidate calibration IDを出す。Manual thresholdへsilent fallbackしない。

activation artifact commit後のactive pointer cache更新失敗はactivation失敗ではない。committed calibrationをeffectiveに保ち、`DEGRADED_POINTER_CACHE`としてcache再構築をretryする。

`calibration_activation_policy = MANUAL_ONLY`ではscheduled artifactを生成してもpendingに留め、userがUI／APIからversionを明示選択するまでactiveにしない。

offline commandまたはAPIで任意時点に手動生成したcalibrationは、policyが`SCHEDULED_SESSION_BOUNDARY`でも自動activateしない。`POST .../activate`による明示要求を受け、§12.5どおり次clusterのfirst tradeでactivateする。activation reasonは`USER_CALIBRATION`とする。

startup時はcommitted activation artifactを読込・検証し、active pointer cacheを照合または再構築する。startup wall clockだけを理由に新versionへ切り替えない。未処理のscheduled boundaryがある場合も、次のsource-confirmed transitionで重複防止keyを確認して処理する。

### 21.6 同一cluster境界のrequest優先順位

一つのeffective source keyへcommitted activationは一件だけ作る。同じ次cluster境界にuser requestとscheduled candidateが重なった場合は次の順で一つのcombined snapshotへ解決する。

1. 最新のvalid pending settingsがあれば、それをbase settingsとする。なければcurrent active settingsをbaseとする。
2. validな`USER_CALIBRATION` pending requestがあれば、そのcalibrationを最優先する。
3. 2がなく、baseがAutomaticでscheduled candidateがvalidation済みかつpolicyが`SCHEDULED_SESSION_BOUNDARY`ならscheduled candidateを使う。
4. 2と3のどちらもなければbaseが参照するcurrent calibrationを維持する。baseがManualなら`calibration_id = null`とする。
5. 最終settings／calibrationからderived settings IDを一つ作り、activation artifactを一件だけcommitする。

pending settingsとpending user calibrationを同時に反映したreasonは`USER_SETTINGS_AND_CALIBRATION`、settingsだけは`USER_SETTINGS`、manual calibrationだけは`USER_CALIBRATION`とする。user calibrationが優先したため未採用となったscheduled artifactは削除せず`SUPERSEDED_BY_USER_REQUEST`として監査可能にし、後から自動activateしない。

Manualへ切替予定のpending settingsが存在する間はcalibration activate POSTを409 `BT_CALIBRATION_MODE_CONFLICT`で拒否する。実装者が二つのrequestを受付順、wall clock、file mtimeで選ばない。

GO-BT7でhistoryが一件もない初回有効化は、user承認済み初期snapshotをpendingに置き、最初のaccepted tradeを最初のcluster keyとして`PRODUCTION_INITIAL` activationをcommitしてからBig Trades処理を始める。初期activation artifactがない状態でmarkerをemitしない。rollback versionの明示activationはreasonを`ROLLBACK`とする。

## 22. BigTradesRuntime

新規`src/orderflow/big_trades/runtime.py`へ、Live／Replay共通runtimeを実装する。

責務:

1. 設定とactive calibrationを検証する。
2. accepted NormalizedTradeをaggregatorへ渡す。
3. 閉じたclusterへfilterを適用する。
4. accepted eventを構築する。
5. session summaryを更新する。
6. event／session summaryをstorageへ渡す。
7. recent accepted event ringへ追加する。
8. callbackを一度だけ呼ぶ。
9. countersとstatusを公開する。
10. CVD確定1分足をsession statsへ取り込む。
11. source-confirmed session transitionを上記順序で確定する。
12. pending settings／calibrationを次clusterのfirst tradeへbindingする。
13. activation historyとeffective snapshotの対応を維持する。

### 22.1 処理順

clusterが閉じたとき、次の順序を固定する。

```text
finalize cluster
  → validate invariants
  → resolve settings snapshot
  → resolve threshold snapshot
  → quantity filter
  → side display filter
  → build deterministic event ID
  → enqueue durable storage
  → add recent ring
  → callback for WebSocket
```

storage enqueueに失敗したeventをWebSocketへ先に流さない。

### 22.2 Automatic unavailable

Automatic modeでactive calibrationがない場合:

```text
status = INSUFFICIENT_HISTORY または CALIBRATION_UNAVAILABLE
marker emit = 0
Manualへのfallback = しない
```

### 22.3 cluster start threshold snapshot

Automatic thresholdもcluster開始時にsnapshotする。cluster途中でactive calibrationが変わっても、そのclusterには旧thresholdを使う。

## 23. event ID

canonical key:

```text
BT1|
logic_version|
venue|
symbol|
input_mode|
side|
first_event_time_utc_ms|
first_trade_id|
last_event_time_utc_ms|
last_trade_id|
aggregation_window_ms|
aggregation_candle_timeframe
```

```text
event_id = "bt1_" + sha256(canonical_key UTF-8).lowercase_hex
```

event IDは発注者、order ID、parent order IDではない。

同じevent IDでpayload内容が一致すればidempotent duplicateとする。内容が異なればcollisionとしてBig Trades featureをfail closedにし、market pipelineの他indicatorを勝手に停止しない。

## 24. Big Trade event model

server internal modelはfrozen dataclassとする。

```text
event_id
logic_version
symbol
venue
side
input_mode
first_trade_id
last_trade_id
first_time
last_time
event_time
marker_time
first_price
last_price
marker_price
low_price
high_price
vwap
aggregate_quantity
aggregate_notional
fill_count
price_level_count
duration_ms
close_reason
filter_mode
intensity nullable
threshold_used
max_threshold_used
side_filter
marker_price_mode
settings_id
calibration_id nullable
aggregation_window_ms
aggregation_candle_timeframe
session_id
```

`event_time`はclusterが確定したsource時刻であり、`last_time`と同値にする。`marker_time`は表示modeにより`first_time`または`last_time`になるため、event確定時刻と混同しない。

DecimalはJSONでstringへ変換する。

## 25. marker位置とsize

### 25.1 price

```text
START_PRICE → first_price
LAST_PRICE  → last_price
VWAP_PRICE  → vwapをprice tickへ表示丸め
```

authoritative raw VWAPは丸めず保存する。marker表示価格だけをprice tickへ丸める。

### 25.2 time

```text
START_PRICE → first_time
LAST_PRICE  → last_time
VWAP_PRICE  → last_time
```

### 25.3 visual size

```text
ratio = aggregate_quantity / threshold_used
visual_scale = clamp(sqrt(ratio), 1.00, 3.00)
```

frontendはserverが渡した`visual_scale`を使用してよいが、ACCEPT／REJECTを再計算しない。

thresholdが0のManual modeではratioを計算できないため`visual_scale = 1.00`とする。

### 25.4 label

markerの常時labelはaggregate quantity。詳細tooltipへfill count、VWAP、時間、範囲を表示する。

## 26. 永続storage schema

新schemaは既存tableへ列追加せず、新規tableとして作る。

### 26.1 `big_trade_events`

```sql
CREATE TABLE IF NOT EXISTS big_trade_events (
    event_id VARCHAR PRIMARY KEY,
    logic_version VARCHAR,
    symbol VARCHAR,
    venue VARCHAR,
    side VARCHAR,
    input_mode VARCHAR,
    first_trade_id BIGINT,
    last_trade_id BIGINT,
    first_time TIMESTAMP,
    last_time TIMESTAMP,
    marker_time TIMESTAMP,
    first_price DECIMAL(20,8),
    last_price DECIMAL(20,8),
    marker_price DECIMAL(20,8),
    low_price DECIMAL(20,8),
    high_price DECIMAL(20,8),
    vwap DECIMAL(38,16),
    aggregate_quantity DECIMAL(38,16),
    aggregate_notional DECIMAL(38,8),
    fill_count INTEGER,
    price_level_count INTEGER,
    duration_ms BIGINT,
    close_reason VARCHAR,
    filter_mode VARCHAR,
    intensity VARCHAR,
    threshold_used DECIMAL(38,16),
    max_threshold_used DECIMAL(38,16),
    side_filter VARCHAR,
    marker_price_mode VARCHAR,
    settings_id VARCHAR,
    calibration_id VARCHAR,
    aggregation_window_ms INTEGER,
    aggregation_candle_timeframe VARCHAR,
    session_id VARCHAR,
    content_hash VARCHAR
);
```

### 26.2 `big_trade_event_fills`

```sql
CREATE TABLE IF NOT EXISTS big_trade_event_fills (
    event_id VARCHAR,
    fill_ordinal INTEGER,
    trade_id BIGINT,
    event_time TIMESTAMP,
    price DECIMAL(20,8),
    quantity DECIMAL(20,8),
    side VARCHAR,
    PRIMARY KEY (event_id, fill_ordinal)
);
```

### 26.3 `big_trade_session_stats`

```sql
CREATE TABLE IF NOT EXISTS big_trade_session_stats (
    logic_version VARCHAR,
    symbol VARCHAR,
    venue VARCHAR,
    input_mode VARCHAR,
    session_id VARCHAR,
    session_start TIMESTAMP,
    session_end TIMESTAMP,
    completion_status VARCHAR,
    completion_trigger VARCHAR,
    confirmed_by_session_id VARCHAR,
    confirmed_by_event_time TIMESTAMP,
    confirmed_by_trade_id BIGINT,
    cluster_count BIGINT,
    rank_2_quantity DECIMAL(38,16),
    rank_9_quantity DECIMAL(38,16),
    rank_20_quantity DECIMAL(38,16),
    top_quantities_json VARCHAR,
    valid_1m_bars INTEGER,
    invalid_1m_bars INTEGER,
    invalid_trades BIGINT,
    source_gap_count BIGINT,
    session_ntr_median DECIMAL(38,24),
    source_first_time TIMESTAMP,
    source_last_time TIMESTAMP,
    content_hash VARCHAR,
    PRIMARY KEY (logic_version, symbol, venue, input_mode, session_id)
);
```

`completion_status`は次のclosed enumとする。

```text
SOURCE_CONFIRMED_COMPLETE
SOURCE_CONFIRMED_EXCLUDED_RESTART_TRUNCATED
SOURCE_CONFIRMED_EXCLUDED_SOURCE_GAP
```

欠損のない完了rowは次を固定する。

```text
completion_status = SOURCE_CONFIRMED_COMPLETE
completion_trigger = NEXT_SESSION_FIRST_ACCEPTED_TRADE
confirmed_by_* = §21.3のcurrent tradeのsession ID／source event time／trade ID
```

`OPEN_UNCONFIRMED`はこのtableへ完了rowとしてinsertしない。

restartまたはsource gapを含むsessionは次session tradeでsource-confirmedになった時点で対応する`EXCLUDED_*` rowを保存できるが、Automatic calibrationのvalid session countへ入れない。

### 26.4 `big_trade_calibrations`

artifact必須fieldを列として保存し、`calibration_id`をPRIMARY KEYとする。artifact JSONとDB rowのcontent hashが一致しなければactivateしない。

### 26.5 `big_trade_settings_history`

settings ID、request時刻、request status、全runtime setting、前versionをappend-onlyで保存する。実際のeffective boundaryはこのtableから推定せず、次のactivation historyを使用する。

### 26.6 `big_trade_activation_history`

実際にruntime snapshotが切り替わったsource境界だけをappend-onlyで保存する。

```sql
CREATE TABLE IF NOT EXISTS big_trade_activation_history (
    activation_id VARCHAR PRIMARY KEY,
    logic_version VARCHAR,
    symbol VARCHAR,
    venue VARCHAR,
    input_mode VARCHAR,
    effective_session_id VARCHAR,
    effective_from_event_time TIMESTAMP,
    effective_from_trade_id BIGINT,
    settings_id VARCHAR,
    calibration_id VARCHAR,
    activation_reason VARCHAR,
    activation_policy VARCHAR,
    requested_at_utc TIMESTAMP,
    content_hash VARCHAR,
    UNIQUE (logic_version, symbol, venue, input_mode, effective_from_event_time, effective_from_trade_id)
);
```

`calibration_id`はManual settingsでnullを許可する。`requested_at_utc`は監査情報であり、effective順序またはReplay選択へ使用しない。

`activation_reason`は次のclosed enumとする。

```text
PRODUCTION_INITIAL
USER_SETTINGS
USER_CALIBRATION
USER_SETTINGS_AND_CALIBRATION
SCHEDULED_WEEKLY
SCHEDULED_MONTHLY
ROLLBACK
```

canonical key:

```text
BTA1|
logic_version|symbol|venue|input_mode|
effective_session_id|
effective_from_event_time_utc_epoch_microseconds|
effective_from_trade_id|
settings_id|calibration_id_or_null|
activation_reason|activation_policy
```

```text
activation_id = "bta1_" + sha256(canonical key UTF-8).lowercase_hex
```

authoritative immutable committed artifact:

```text
data_05M/settings/big_trades/activations/<activation_id>.json
```

artifactはtableの全fieldとschema versionを持ち、§20.3と同じtemporary write、flush、fsync、read-back、hash確認を行い、final pathへの`os.replace`成功をactivation commit pointとする。同じactivation IDと同じcontent hashはidempotent successとする。temporary file、candidate artifact、settings requestだけをcommitted activationとして列挙しない。

同じ`symbol／venue／input_mode／logic_version／effective_from_event_time／effective_from_trade_id`へ異なるsettings IDまたはcalibration IDを割り当ててはならない。不一致を検出した場合は`ACTIVATION_BOUNDARY_COLLISION`としてBig Tradesだけをfail closedにし、どちらかを時刻で推定しない。

derived active pointer cacheは次を必須fieldとする。

```text
activation_id
settings_id
calibration_id or null
effective_session_id
effective_from_event_time
effective_from_trade_id
content_hash
```

cache欠損または不一致時は、committed activation artifactをeffective source key順に検証し、最後の一件からcacheを再構築する。cacheのmtime、内容だけでactivation historyを作らない。committed artifact自体が欠損、不整合、collisionの場合だけfail closedにする。

### 26.7 Arrow／Parquet

新規`src/database/big_trades_schema.py`をauthoritative schemaとし、DuckDB DDL、Arrow schema、row conversionを同居させる。

Parquet dataset:

```text
data_05M/parquet/big_trade_events/
data_05M/parquet/big_trade_event_fills/
data_05M/parquet/big_trade_session_stats/
data_05M/parquet/big_trade_calibrations/
data_05M/parquet/big_trade_settings_history/
data_05M/parquet/big_trade_activation_history/
```

既存root trades ParquetへBig Trades列を追加しない。

### 26.8 event＋fills原子性

一つのaccepted eventと全fillsは一つの`BigTradeStorageBatch`としてbackground writerへ渡す。

DuckDBではtransaction内でparent eventとfillsを挿入する。parentだけ、またはfillsだけをcommitしない。

Parquetはevent fileとfills fileをtemporaryへ書き、双方read-back後にcommit manifestを作る。片方だけのarchiveをhistory正本として扱わない。

## 27. BackgroundStorageWriter変更

`src/database/storage.py`へ次のexplicit kindを追加する。

```text
big_trade_event
big_trade_session_stats
big_trade_calibration
big_trade_settings
big_trade_activation
```

次のcounterを追加する。

```text
big_trade_events_written
big_trade_fills_written
big_trade_duplicates
big_trade_write_failures
big_trade_session_stats_written
big_trade_calibrations_written
big_trade_settings_written
big_trade_activations_written
big_trade_activation_duplicates
big_trade_activation_failures
```

既存kind名、queue ordering、trade/candle/footprint writerの意味を変更しない。

## 28. Pipeline接続

### 28.1 LivePipeline

`LivePipeline.__init__`へBig Trades設定値とcallbackをkeyword-onlyで追加する。

```text
on_big_trade
on_big_trades_status
big_trades_enabled
big_trades settings
```

`from_config`でstrict configから渡す。

### 28.2 ReplayPipeline

Replayも同じ`BigTradesRuntime`を生成し、同じ`process(normalized)`を呼ぶ。

Live専用class、Replay専用簡易ロジックを作らない。

### 28.3 handle位置

Replay／Live双方の既存`handle(normalized)`で、`cvd_result = cvd.process(normalized)`の直後にBig Tradesを接続する。既存のstorage、Native coordinator、Flow Price Response、CVD、Footprint、Flow detector同士の相対順序は変更しない。

```text
storage.add_trade(trade_to_row(normalized))
existing Native／Flow Price Response processing（現行順序のまま）
cvd_result = cvd.process(normalized)

if cvd_result.closed_candle is not None:
    big_trades_runtime.observe_closed_candle(cvd_result.closed_candle)

if Live and connector.reconnect_count changed:
    big_trades_runtime.flush(STREAM_DISCONNECTED)
    update last_big_trades_reconnect_count

big_trades_runtime.process(normalized)
existing CVD result／higher timeframe／Footprint／Flow processing（現行順序のまま）
```

`observe_closed_candle()`を`process(normalized)`より先にする理由は、current tradeが新session最初のtradeである場合に、CVDがそのtradeによって閉じた旧session最後の1分足を旧session summaryへ含めてから§21.3のtransitionを確定するためである。

`observe_closed_candle()`はcandleの`bar_time`を`floor_utc_bucket(candle.bar_time, 60 seconds)`で検証し、runtimeが受領済みtradeから記録した対応minute boundaryと一致させる。不一致時は`CANDLE_BOUNDARY_MISMATCH`でBig Tradesだけをfail closedにする。candle値をcluster IDとして逆流させない。

Replayもこの順序を一行単位で共有する。Replay speed、sleep、実行時wall clockはsession transition、candle boundary、activation selectionへ渡さない。

Big Trades runtimeの例外は次へ分類する。

- invalid feature input: eventをfail closed、counter、既存market pipeline継続。
- storage queue failure: Big TradesをDEGRADED、未保存markerをemitしない。
- invariant violation／ID collision: Big TradesをERROR停止、既存market pipeline継続。
- programmer error: logにstack trace、Big Trades ERROR、同じtradeで再試行しない。

### 28.4 finalize

`normalizer.flush()`後、storage.close()前に必ず次を呼ぶ。

```text
big_trades_runtime.flush(STREAM_ENDED)
```

`STREAM_ENDED`はSameMillisecond bufferとopen clusterを確定するだけである。current sessionを完了扱いにしない。すでに後続sessionのaccepted tradeによってsource-confirmedになったsession summaryが未保存である場合だけ、保存retryを行う。wall clockまたはshutdownを根拠に`finalize_session_if_complete()`を呼ばない。

### 28.5 disconnect

`ExchangeConnector.reconnect_count`をBig Trades用のconnection epochとして使用する。connector本体へ新callbackを追加しない。

pipelineはBig Trades runtime生成時の`reconnect_count`を`last_big_trades_reconnect_count`へ保存する。各accepted tradeについて、CVD closed candleをBig Tradesへ渡した後、current tradeをBig Tradesへ渡す前に現在値を比較する。

```text
if connector.reconnect_count != last_big_trades_reconnect_count:
    big_trades_runtime.flush(STREAM_DISCONNECTED)
    last_big_trades_reconnect_count = connector.reconnect_count

big_trades_runtime.process(normalized)
```

これにより、再接続後の最初のtradeを切断前clusterへ接続しない。再接続中にtradeがない場合は不要な空eventを作らない。40ms超過による自然closeだけへ依存しない。

## 29. BigTradeBatcher

新規`webapp/big_trades.py`へTapeBatcherと分離したbatcherを作る。

### 29.1 contract

- thread safe。
- `publish`はawaitしない。
- BigTrade eventだけを受理する。
- 独自UUID `stream_id`。
- sequenceは1から連続。
- bounded queue。
- 100msごと、最大100 event／message。
- overflowはdrop oldestをcounterへ明示する。
- eventはすでにdurable queueへ入った後なので、clientはhistory APIで回復可能。

### 29.2 accounting

```text
accepted_events
sent_events
dropped_events
pending
inflight
invalid_rejected
send_failures
accounted_events
accounting_balanced
```

TapeBatcherのcounterを流用・混算しない。

## 30. WebSocket contract

新type:

```text
BIG_TRADES_UPDATE
```

envelopeは現行`v: 1`を維持するadditive extensionとする。

```json
{
  "v": 1,
  "type": "BIG_TRADES_UPDATE",
  "time": "...",
  "symbol": "BTCUSDT",
  "payload": {
    "stream_id": "uuid",
    "first_sequence": 1,
    "last_sequence": 1,
    "accepted_count": 1,
    "dropped_count": 0,
    "events": [
      {
        "event_id": "bt1_...",
        "logic_version": "BTLOGIC-1.0",
        "event_time": "...",
        "marker_time": "...",
        "symbol": "BTCUSDT",
        "venue": "BINANCE",
        "side": "BUY",
        "input_mode": "AGGREGATE_TRADES",
        "aggregate_quantity": "55.000",
        "aggregate_notional": "...",
        "fill_count": 3,
        "duration_ms": 60,
        "first_price": "100",
        "last_price": "102",
        "marker_price": "102",
        "low_price": "100",
        "high_price": "102",
        "vwap": "...",
        "price_level_count": 3,
        "filter_mode": "AUTOMATIC",
        "intensity": "MEDIUM",
        "threshold_used": "50",
        "max_threshold_used": "0",
        "side_filter": "BOTH",
        "marker_price_mode": "LAST_PRICE",
        "settings_id": "bts1_...",
        "calibration_id": "btcal1_...",
        "aggregation_window_ms": 40,
        "aggregation_candle_timeframe": "1m",
        "visual_scale": "1.0488"
      }
    ]
  }
}
```

Decimalは文字列、件数／sequence／millisecondsはJSON integer。

### 30.1 status message

新type:

```text
BIG_TRADES_STATUS
```

statusはPushBrokerで最新一件をcacheし、reconnect clientへ送る。

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
ERROR
```

status payloadへeffective settings、threshold、calibration ID、activation ID、activation policy、pending settings／calibration ID、last source-confirmed session ID、last event time、counter、last activation errorを含める。

## 31. REST API

### 31.1 history

```text
GET /api/history/big-trades
```

query:

```text
limit: 1..5000
before: timezone-aware ISO 8601 exclusive cursor
before_event_id: same-time tie breaker
side: BOTH | BUY | SELL
```

returnはoldest-first。

DB flush待ちのlive eventを落とさないため、DuckDB結果とruntime recent ringをevent IDでmergeし、event time＋event ID順に整列する。

### 31.2 fills

```text
GET /api/history/big-trades/{event_id}/fills
```

event ID完全一致だけを受理し、fill ordinal昇順で返す。最大10000件。

### 31.3 effective settings

```text
GET /api/big-trades/settings
PUT /api/big-trades/settings
```

PUTは部分更新を許可せず、全settingを一つのtransactional requestとして検証する。更新成功時に新settings IDと`activation_status=PENDING`を返す。HTTP response時刻をeffective境界と表示しない。

### 31.4 calibrations

```text
GET  /api/big-trades/calibrations
GET  /api/big-trades/calibrations/{calibration_id}
POST /api/big-trades/calibrations/{calibration_id}/activate
```

activate前にschema、logic version、symbol、venue、input mode、quantity step、content SHA-256を再検証する。

POSTはmanual activation requestをpending登録し、`activation_status=PENDING`を返す。実切替は§12.5の次cluster first tradeで行う。scheduled auto activationにこのPOSTを要求しない。

### 31.5 activation history

```text
GET /api/big-trades/activations
GET /api/big-trades/activations/{activation_id}
```

一覧は`effective_from_event_time`、`effective_from_trade_id`、`activation_id`順で返し、source-time rangeとsymbol／venue／input modeで絞り込める。immutable historyの追加・編集・削除endpointは作らない。

### 31.6 error response

```json
{
  "ok": false,
  "error_code": "BT_CONFIG_INVALID",
  "reason": "manual_max_quantity must be 0 or >= manual_min_quantity"
}
```

HTTP 200に`ok:false`を隠さず、validationは4xx、server/storage failureは5xxを使用する。

## 32. UI配置

### 32.1 中央3-mode

現行中央mode switchを次へする。

```text
[ FOOTPRINT ] [ HEATMAP ] [ BIG TRADES ]
```

`BIG TRADES`は第三modeであり、FootprintまたはHeatmapを削除しない。

### 32.2 既存layout不変

- 中央panelの外寸を変えない。
- 右端Time & Salesを移動しない。
- 下段FLOW EVENTS／Absorption／Imbalance／Alertsを移動しない。
- 3段チャートの位置、高さ、比率を変えない。
- Big Tradesの有無でpage要素を増減させない。

### 32.3 BIG TRADES controls

Big Trades modeのheaderへ常設する。

```text
MODE       MANUAL | AUTO
INPUT      AGGREGATE TRADES
SIDE       BOTH | BUY | SELL
MIN        Decimal input（Manual時）
MAX        Decimal input（Manual時、0 = OFF）
INTENSITY  LOW | MEDIUM | STRONG（Auto時）
MARK AT    START | LAST | VWAP
CAL        calibration短縮ID
APPLY      setting確定
```

Manual時もAuto時もcontrol自体を消さない。使用しない側はdisabledにし、位置を維持する。

### 32.4 status行

```text
BIG TRADES · LIVE · AGGREGATE 40MS · AUTO MEDIUM ≥ 50.000 · MAX OFF · CAL btcal1_ab12 · GAP 0
```

dataがない場合も行を残し、値だけ`—`にする。

scheduled activation失敗時は旧CALを表示したまま、`CAL UPDATE FAILED · CANDIDATE <id>`を消さずに表示する。pending manual requestがある場合は`PENDING <id> · NEXT CLUSTER`を表示し、すでにactiveになったように表示しない。

### 32.5 detail行

marker選択時:

```text
BUY · QTY 55.000 · 3 FILLS · 60MS · 100 → 102 · VWAP 101.18 · RANGE 3 LEVELS · THRESHOLD 50.000
```

発注者またはparent orderを示す文言を出さない。

## 33. frontend module

新規`webapp/static/big_trades.js`をUMDまたは現行frontend contractに合わせた独立moduleとして作る。

### 33.1 classes

```text
BigTradeEventStore
BigTradeContinuity
BigTradesCanvas
BigTradesSettingsController
```

### 33.2 EventStore

- event ID dedup。
- event time＋event IDの決定論的sort。
- 最大5000件。
- historyとliveをmerge。
- side filterは表示だけ。server eventを削除しない。
- stream restart時にstoreを全消去せず、history refillする。

### 33.3 continuity

- stream ID変更をrestartとして記録。
- sequence gapを検出。
- dropped_count > 0をgapとして記録。
- gap時はhistory APIを再取得。
- history回復完了まで`GAP RECOVERING`を表示。
- 回復不能時にgap表示を消さない。

### 33.4 Canvas source

Big Trades chartのcandleは既存`CANDLE`、`BAR_UPDATE`、`/api/history/candles`を読み取り専用で利用する。

Big Trades markerは`BIG_TRADES_UPDATE`とBig Trades history APIだけから作る。TAPE_UPDATEをbrowserで40ms集約し直さない。

### 33.5 Canvas layers

```text
background
grid
candles
marker connector/range
BUY markers
SELL markers
quantity labels
selection
crosshair
tooltip
```

### 33.6 marker color

DeltaEngine内での色を固定凡例として明示する。

```text
BUY  = green
SELL = red/magenta
```

色だけに依存せず、marker labelまたはtooltipへ`B`／`S`を表示する。Fabio動画の色設定を再現したとは表示しない。

### 33.7 marker shape

V1はcircle markerを使用する。面積は`visual_scale`へ従う。集約価格範囲が複数levelの場合、low～highを細いvertical rangeで示し、circle自体はmarker priceへ置く。

### 33.8 interaction

- mouse hover: tooltip。
- click: marker pin＋detail固定。
- Escape: pin解除。
- left/right: visible marker移動。
- mouse wheel: time zoom。
- drag: history pan。
- LIVE LOCK: 最新へ戻る。

Footprint／Heatmapのkeyboard handlerと同時発火させない。active modeだけがeventを受ける。

## 34. index.htmlの許可変更境界

`webapp/static/index.html`は既存user変更を含む保護fileである。変更を次へ限定する。

1. mode switchへ`BIG TRADES` buttonを追加。
2. Big Trades専用controls containerを追加。
3. `fpstage`内へ独立`bigtradescanvas`とtooltipを追加。
4. Big Trades専用detail／status行を追加。
5. `big_trades.js` script読込を追加。
6. WebSocket dispatchへ`BIG_TRADES_UPDATE`と`BIG_TRADES_STATUS`をadditive追加。
7. mode switch初期化を3-mode対応へ限定変更。

次のhunkを変更しない。

- bottom 3段chart DOM／CSS／drawing logic
- Flow Response cards
- CVD／Delta／Volume drawing
- Flow Event candle marker
- Footprint calculation
- Heatmap book/trade store
- Time & Sales filter意味
- DOM Trade Pulse

変更前後で該当保護hunkのSHA-256または抽出diffをcheckpointへ保存する。

## 35. history hydration

初回Big Trades mode選択時に直近500 eventを取得する。panで古い方向へ到達したとき、exclusive cursorで追加取得する。

同時刻eventは`before_event_id`で欠落なくpageする。

history responseへ次を含める。

```text
events
next_before
next_before_event_id
has_more
logic_version
```

history queryはlimitを先にevent tableへ適用し、その後fillsを別endpointで遅延取得する。一覧表示のたびに全fillをJOINしない。

## 36. restart／reconnect／gap

### 36.1 server restart

- 新Big Trade stream UUIDを作る。
- sequenceを1へ戻す。
- clientはrestartを検出する。
- history APIで保存済みeventをhydrateする。
- active calibrationとeffective settingsを再読込する。
- derived active pointer cacheのactivation IDとcommitted activation artifactを照合する。cacheだけの欠損または不一致はcommitted artifactから再構築する。committed artifactの欠損または不一致ならBig Tradesをfail closedにし、file timestampからactivationを推定しない。
- open clusterを復元しない。restart前の未確定clusterを次のtradeへ接続しない。

### 36.2 browser reconnect

- cached statusを先に受け取る。
- latest historyを取得する。
- event ID dedup後にlive batchをmergeする。
- sequence gapが解消したことを確認するまでwarningを維持する。

### 36.3 Tape gapとの分離

Big Trades server coreはTape UI batchをsourceにしないため、Tape dropだけでBig Trades eventを無効化しない。Big Trades独自stream gapだけをBig Trades continuityへ使う。

### 36.4 raw trade gap

upstream／normalizerでaccepted trade欠損が検出された場合、該当期間を`SOURCE_GAP`として記録し、そのsession summaryをAutomatic calibrationから除外する。

## 37. fail-closed matrix

| 状況 | Big Trades動作 | 既存market pipeline |
|---|---|---|
| invalid trade | 拒否、counter | 継続 |
| duplicate | DataNormalizerで除外 | 継続 |
| out-of-order late trade | DataNormalizerで除外、Big Tradesへ来ない | 継続 |
| active calibrationなし | Auto marker停止 | 継続 |
| calibration hash不一致 | Auto ERROR | 継続 |
| scheduled calibration validation失敗 | 旧calibration維持、activation failed表示 | 継続 |
| activation history欠損／collision | Big Trades ERROR、推定禁止 | 継続 |
| active pointer cache欠損／不一致 | committed artifactから再構築、DEGRADED表示 | 継続 |
| candle boundary不一致 | `CANDLE_BOUNDARY_MISMATCH`、Big Trades ERROR | 継続 |
| Replay historical activation欠損 | Big Trades Replay停止 | Live／既存Replay処理は継続 |
| quantity step欠損 | 起動時config errorまたはBig Trades disabled | policyどおり |
| cluster invariant違反 | cluster破棄、Big Trades ERROR | 継続 |
| event ID content collision | Big Trades emit停止 | 継続 |
| Big Trade storage enqueue失敗 | 未保存eventをemitしない、DEGRADED | 既存storage状態を報告 |
| Big Trade WebSocket drop | history recovery可能なgap表示 | 継続 |
| browser payload invalid | payload拒否、gap表示 | server継続 |
| Automatic history不足 | `INSUFFICIENT_HISTORY` | 継続 |

エラー時にManualへsilent fallbackしない。

## 38. health／stats

`/api/stats`へ`big_trades` objectをadditive追加する。

```json
{
  "status": "MANUAL_READY",
  "logic_version": "BTLOGIC-1.0",
  "settings_id": "bts1_...",
  "calibration_id": null,
  "activation_id": "bta1_...",
  "calibration_schedule": "MANUAL",
  "calibration_activation_policy": "SCHEDULED_SESSION_BOUNDARY",
  "pending_settings_id": null,
  "pending_calibration_id": null,
  "active_min": "5.000",
  "active_max": "0",
  "trades_observed": 0,
  "clusters_started": 0,
  "clusters_finalized": 0,
  "clusters_accepted": 0,
  "rejected_below_min": 0,
  "rejected_above_max": 0,
  "hidden_by_side": 0,
  "invalid_clusters": 0,
  "events_storage_queued": 0,
  "events_published": 0,
  "batch_dropped": 0,
  "recent_ring_size": 0,
  "last_trade_time": null,
  "last_event_time": null,
  "last_source_confirmed_session_id": null,
  "session_state": "OPEN_UNCONFIRMED",
  "scheduled_calibrations_created": 0,
  "scheduled_calibrations_activated": 0,
  "calibration_activation_failures": 0,
  "candle_boundary_mismatches": 0,
  "last_activation_error": null,
  "last_error": null
}
```

既存overall healthをBig TradesだけでREDへ変えるかは、GO-BT4でHealth policyを確認して決める。V1既定は独立subsystem statusとし、既存pipeline healthの意味を勝手に変更しない。

## 39. logging

logger名:

```text
orderflow.big_trades
webapp.big_trades
```

INFO:

- settings activation
- calibration activation
- session summary completion
- scheduled calibration result
- activation IDとeffective source key
- source-confirmed session transition

WARN:

- insufficient history
- invalid session exclusion
- Big Trade batch drop
- history recovery

ERROR:

- invariant failure
- content collision
- storage failure
- artifact hash mismatch
- activation boundary collision
- Replay activation history missing／invalid
- candle boundary mismatch

trade一件ごとのACCEPT／REJECTを通常INFO logへ流さない。

## 40. performance contract

### 40.1 server hot path

BigTradesRuntimeのtrade一件処理は通常O(1)。distinct price管理を除き、過去全tradeを走査しない。

目標:

```text
process(trade) p95 <= 0.10ms
process(trade) p99 <= 0.25ms
cluster finalize p99 <= 1.00ms
daily source-confirmed transition p99 <= 250ms
```

測定は同じWindows／Docker環境、Decimal、実際のBTCUSDT型データで行う。

daily transition測定にはsession summary artifactのatomic writeを含める。WEEKLY／MONTHLY boundaryでは最大20 summaryのread、pure calibration、candidate／activation artifactのatomic writeを含め、raw trade再走査0件、normalized queue overflow 0件を必須とする。

### 40.2 memory boundedness

```text
open cluster: symbolごと1
fills: max 10000/cluster
recent accepted events: max 5000
WebSocket pending: max 5000
browser events: max 5000
visible markers: max 2000
session top quantities: max 20/session
session summaries: live memory max 20
```

### 40.3 browser

```text
Canvas draw p95 <= 8ms at 1280×900
mode switch <= 100ms
history 5000 event merge <= 100ms
page horizontal overflow = 0
browser console error = 0
```

### 40.4 no regression

Big Trades ON／OFF双方で次を測る。

- TICK source age
- BAR_UPDATE source age
- storage pending／high watermark
- Tape accepted/sent/dropped/accounting
- Book gap／sync
- browser queue drop
- CPU／RSS

既存RTUIF gate:

```text
server/browser最大遅延 < 3000ms
receiver overflow = 0
WebSocket overflow = 0
drop = 0
book gap = 0（feature起因）
```

## 41. new source files

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
Delta_Engine_Pro4web/src/orderflow/big_trades/settings.py
Delta_Engine_Pro4web/src/orderflow/big_trades/runtime.py
Delta_Engine_Pro4web/src/database/big_trades_schema.py
Delta_Engine_Pro4web/webapp/big_trades.py
Delta_Engine_Pro4web/webapp/static/big_trades.js
Delta_Engine_Pro4web/tools/calibrate_big_trades.py
```

## 42. modified source files

予定変更file:

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
Delta_Engine_Pro4web/src/orderflow/flow_price_response.py
Delta_Engine_Pro4web/src/orderflow/flow_detector.py
Delta_Engine_Pro4web/src/orderflow/cvd.py
Delta_Engine_Pro4web/src/orderflow/footprint.py
Delta_Engine_Pro4web/src/orderflow/absorption.py
Delta_Engine_Pro4web/src/orderflow/imbalance.py
Delta_Engine_Pro4web/webapp/static/time_sales.js
Delta_Engine_Pro4web/webapp/static/footprint_canvas.js
Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js
```

実装前に現行diffを再監査し、user変更とhunkが重なる場合は上書きしない。

## 43. document updates

実装工程で次をadditive更新する。

```text
ArchitectureRepository/30_Modules/WebApp/Specifications/WebSocketPayload_Spec_v1.md
ArchitectureRepository/40_Reference/YAMLReference_v3.4.md
ArchitectureRepository/40_Reference/DuckDBDDL_v3.1.md
ArchitectureRepository/40_Reference/ParquetSchema_v3.1.md
ArchitectureRepository/DOCUMENT_INDEX.md
ArchitectureRepository/00_Master/PROJECT_MEMORY.md（実装と検証が完了した後だけ）
```

未完成段階をPROJECT_MEMORYへ完成として書かない。

## 44. test files

新規:

```text
Delta_Engine_Pro4web/tests/orderflow/test_big_trades_aggregation.py
Delta_Engine_Pro4web/tests/orderflow/test_big_trades_time_buckets.py
Delta_Engine_Pro4web/tests/orderflow/test_big_trades_filtering.py
Delta_Engine_Pro4web/tests/orderflow/test_big_trades_calibration.py
Delta_Engine_Pro4web/tests/orderflow/test_big_trades_runtime.py
Delta_Engine_Pro4web/tests/database/test_big_trades_storage.py
Delta_Engine_Pro4web/tests/webapp/test_big_trades_batcher.py
Delta_Engine_Pro4web/tests/webapp/test_big_trades_api.py
Delta_Engine_Pro4web/tests/webapp/test_big_trades_ui.py
Delta_Engine_Pro4web/tests/test_pipeline_big_trades.py
Delta_Engine_Pro4web/tests/tools/test_calibrate_big_trades.py
```

既存試験へ必要最小限のadditive assertionを行う。

## 45. core unit test matrix

最低限、次を一件ずつ独立testにする。

### 45.1 input

1. Decimal price／quantityを受理。
2. price 0拒否。
3. quantity 0拒否。
4. NaN／Infinity拒否。
5. unknown side拒否。
6. symbol mismatch拒否。
7. timezoneなし拒否。
7a. 同一millisecondの逆順arrivalをtrade ID昇順へrelease。
7b. 次millisecond到着までbucketを保持。
7c. stream end／disconnectでbucketを先にflush。
7d. release済みmillisecondより古いtradeを拒否。

### 45.2 aggregation

8. 同方向0msをjoin。
9. 同方向40msをjoin。
10. 同方向41msをsplit。
11. 0→35→70msを一cluster。
12. BUY→SELLをsplit。
13. price違いでもjoin。
14. session境界をsplit。
15. 1m candle境界をsplit。
16. stream endでflush。
17. disconnectでflush。
18. total quantity正確。
19. weighted notional正確。
20. VWAP正確。
21. low／high正確。
22. distinct price count正確。
23. fill ordinal正確。
24. max fills超過でsilent splitしない。
24a. `floor_utc_bucket()`がUTC epoch microsecondsを60秒単位でfloorする。
24b. minute境界上の時刻は同じ境界、境界直前1microsecondは前minuteになる。
24c. timezone-naive timestampを拒否する。
24d. offset付きtimestampをUTCへ正規化して同じcandle IDにする。
24e. Big Trades算出boundaryとCVD `bar_time`が一致する。
24f. boundary不一致で`CANDLE_BOUNDARY_MISMATCH`となり、Big Tradesだけがfail closedになる。

### 45.3 Manual

25. q < Min reject。
26. q = Min accept。
27. Max 0で上限なし。
28. q = Max accept。
29. q > Max reject。
30. side filterはquantity判定と独立。

### 45.4 settings

31. cluster途中変更は旧setting。
32. 次clusterは新setting。
33. invalid settingは全体不適用。
34. settings ID deterministic。
34a. pending setting／calibrationはopen clusterを強制分割しない。
34b. activation effective keyは旧cluster last tradeでなく次cluster first tradeになる。

### 45.5 IDs

35. event ID deterministic。
36. Live／Replay event ID同値。
37. content一致duplicate idempotent。
38. content不一致collision拒否。

## 46. Automatic test matrix

39. session降順rank。
40. Low 20位。
41. Medium 9位。
42. Strong 2位。
43. 同値数量を同threshold。
44. 奇数median。
45. 偶数Decimal median。
46. 10有効session未満でinsufficient。
47. exactly 10で許可。
48. 進行中session除外。
49. as-of後データ除外。
50. TR三候補の最大値。
51. previous close使用。
52. NTR。
53. session median。
54. 95% bar coverage境界。
55. baseline 20 session。
56. recent 5 session。
57. sqrt factor。
58. factor 0.75下限。
59. factor 1.50上限。
60. baseline 0 fallback。
61. missing bars fallback。
62. quantity step ceiling。
63. Low < Medium < Strong補正。
64. Automatic Max 0。
65. calibration ID deterministic。
66. artifact hash検証。
67. artifact immutable。
68. wrong symbol拒否。
69. wrong logic version拒否。
70. wrong quantity step拒否。
70a. 次session最初のaccepted tradeだけが旧session完了triggerになる。
70b. wall clockがUTC 00:00を越えても次session tradeがなければ`OPEN_UNCONFIRMED`のまま。
70c. stream end／shutdownだけではcurrent session statsを完了保存しない。
70d. CVDがcurrent tradeで閉じた旧session最後の1分足をsession statsへ含める。
70e. transition順がbuffer flush→cluster finalize→stats durable save→scheduled calibration→activation→current tradeである。
70f. stats durable save失敗時はscheduled calibrationを作成・activateしない。
70g. WEEKLYはISO週境界を越えた最初のsource transitionで一回だけ生成し、月曜日trade欠損でも次tradeで検出する。
70h. MONTHLYはUTC年月境界を越えた最初のsource transitionで一回だけ生成し、月1日trade欠損でも次tradeで検出する。
70i. restart後も同じschedule boundary IDを二重生成しない。
70j. scheduled artifact validation成功時は新session first clusterから自動activateする。
70k. scheduled artifact validation失敗時は旧calibrationを維持する。
70l. 手動生成artifactは`SCHEDULED_SESSION_BOUNDARY`でも自動activateしない。
70m. `MANUAL_ONLY`はscheduled artifactをpendingに留める。
70n. WEEKLY／MONTHLY正常運用でmanual activation requestが0件である。
70o. 同一境界のuser calibrationがscheduled candidateより優先され、activation rowは一件だけ。
70p. 初回有効化は最初のaccepted tradeへ`PRODUCTION_INITIAL`をcommitしてからmarker処理する。
70q. scheduled activation commit後・run artifact保存前のrestartでrun artifactだけを復元し、candidate／activationを重複生成しない。

## 47. storage test matrix

71. event＋fills atomic insert。
72. parent duplicate no duplicate fills。
73. event content hash mismatch拒否。
74. Parquet event read-back。
75. Parquet fills read-back。
76. partial temporary fileを正本扱いしない。
77. background queue ordering。
78. queue fullをsilent dropしない。
79. close時flush。
80. session stats idempotent。
81. calibration idempotent。
82. settings append-only。
83. Decimal精度保持。
84. UTC round trip。
84a. activation ID deterministic。
84b. activation artifact atomic write／read-back／content hash一致。
84c. 同一activation ID・同一contentはidempotent。
84d. 同一effective key・異なるsettings／calibrationをcollision拒否。
84e. settings request historyだけではeffective境界にならない。
84f. active pointer cacheとcommitted activation artifactの全ID／effective key一致。
84g. cache欠損／不一致をcommitted artifactから再構築する。
84h. activation DuckDB／Parquet mirror read-back一致。

## 48. pipeline／Replay test matrix

85. Big Trades disabled時に既存出力不変。
86. enabled時もCVD結果不変。
87. enabled時もFootprint結果不変。
88. enabled時もFlow Price Response結果不変。
89. enabled時もLargeTradeDetector結果不変。
90. 同一tradeを一度だけBig Tradesへ渡す。
91. Replay speedでcluster境界が変わらない。
92. wall clock差でcluster境界が変わらない。
93. Live／Replay event payload同値。
94. shutdown open cluster保存。
95. reconnect前後を結合しない。
96. Big Trades ERRORでも既存pipeline継続。
97. storage未queue eventをcallbackしない。
97a. CVD closed candleをBig Tradesへ渡した後にcurrent tradeを渡す。
97b. Live／Replayのsession transition処理順が同一。
97c. Replayはactivation rowsをeffective time／trade ID順に選ぶ。
97d. Replay cluster key以下の最後のactivationだけを選ぶ。
97e. 同一timestampのactivation境界をtrade IDで決定する。
97f. artifact `created_at_utc`を変更してもReplay selectionが変わらない。
97g. open cluster途中のactivation境界は次clusterまで適用しない。
97h. activation history欠損で`REPLAY_ACTIVATION_HISTORY_MISSING`、fallback 0件。
97i. activation content不一致で`REPLAY_ACTIVATION_HISTORY_INVALID`。
97j. `FIXED_RESEARCH`出力がresearch namespaceだけに存在する。
97k. `FIXED_RESEARCH`がproduction event／pointer／activation historyを変更しない。

## 49. WebSocket／API test matrix

98. BIG_TRADES_UPDATE envelope。
99. Decimal string。
100. integer field型。
101. batch contiguous sequence。
102. invalid range拒否。
103. drop count伝達。
104. stream restart。
105. status cache reconnect送信。
106. history oldest-first。
107. exclusive cursor。
108. same-time event ID cursor。
109. recent ring＋DB merge dedup。
110. fills ordinal。
111. setting PUT atomic validation。
112. calibration activation validation。
113. unsupported mode拒否。
113a. settings PUT成功は`PENDING`を返し、active IDを即時変更しない。
113b. manual calibration activate POSTは`PENDING`を返す。
113c. scheduled auto activationにPOST requestが不要。
113d. activation history一覧がsource effective key順。
113e. activation historyの変更／削除methodを提供しない。
113f. Manual切替pending中のcalibration activate POSTを409 conflictで拒否する。

## 50. frontend test matrix

114. 3-mode switch。
115. Footprint mode不変。
116. Heatmap mode不変。
117. Big Trades canvasだけ表示。
118. control位置常設。
119. Manual／Auto disabled state。
120. marker quantity label。
121. BUY／SELL形状または文字識別。
122. START／LAST／VWAP位置。
123. history＋live dedup。
124. sequence gap warning。
125. history recovery。
126. stream restart recovery。
127. invalid payload拒否。
128. no data時`—`維持。
129. click detail。
130. keyboard navigation。
131. wheel zoom／drag pan。
132. mode非active handler停止。
133. 5000 event capacity。
134. horizontal overflow 0。
135. existing Time & Sales filter不変。
136. existing DOM pulse不変。
137. existing 3段chart geometry不変。

## 51. fixed test vectors

logic正本の次をgolden fixture化する。

### 51.1 chained 40ms

```text
BUY t=0ms  p=100 q=18
BUY t=25ms p=101 q=17
BUY t=60ms p=102 q=20
SELL t=70ms p=101 q=5
```

expected BUY cluster:

```text
quantity=55
fills=3
duration=60ms
first=100
last=102
low=100
high=102
levels=3
```

### 51.2 41ms split

```text
BUY t=0ms q=30
BUY t=41ms q=30
```

expected: 30と30の二cluster。60へ合算しない。

### 51.3 threshold boundary

```text
q=50 Min=50 Max=50 → ACCEPT
q=55 Min=20 Max=50 → REJECT_ABOVE_MAX
q=55 Min=50 Max=0  → ACCEPT
```

### 51.4 Automatic order correction

```text
raw low=40.01
raw medium=40.02
raw strong=40.03
step=1
```

expected:

```text
low=41
medium=42
strong=43
```

### 51.5 source-confirmed session transition

```text
old trade:     2026-08-09T23:59:59.990Z trade_id=100 BUY q=30
closed candle: bar_time=2026-08-09T23:59:00Z
current trade: 2026-08-10T00:00:00.005Z trade_id=101 BUY q=40
schedule: WEEKLY, policy=SCHEDULED_SESSION_BOUNDARY
candidate: validation PASS
```

expected authoritative order:

```text
observe closed candle 2026-08-09T23:59:00Z
flush old-session ordering buffer
finalize old-session cluster
durably save session_id=2026-08-09 stats
run eligible schedule and validate candidate
write activation at (2026-08-10T00:00:00.005Z, 101)
start new-session cluster with trade_id=101 and new snapshot
```

current tradeがないfixtureでは、wall clockとshutdown時刻に関係なく`2026-08-09`を`OPEN_UNCONFIRMED`のままにし、完了session statsを作らない。

### 51.6 candle boundary ownership

```text
2026-08-11T04:01:00.000000Z → 2026-08-11T04:01:00Z
2026-08-11T04:01:59.999999Z → 2026-08-11T04:01:00Z
2026-08-11T04:02:00.000000Z → 2026-08-11T04:02:00Z
```

三件ともBig Tradesの`floor_utc_bucket()`が算出する。CVD candleは算出元ではなく、同じboundaryであることを確認する比較対象である。

### 51.7 Replay activation selection

```text
A: effective=(2026-08-11T10:00:00Z, trade_id=100), cal=CAL_A
B: effective=(2026-08-11T12:00:00Z, trade_id=200), cal=CAL_B
C: effective=(2026-08-11T12:00:00Z, trade_id=205), cal=CAL_C
```

expected:

```text
cluster first=(11:00:00Z, 150) → CAL_A
cluster first=(12:00:00Z, 202) → CAL_B
cluster first=(12:00:00Z, 205) → CAL_C
```

CAL_A／B／Cの`created_at_utc`を入れ替えてもexpectedは変わらない。

### 51.8 scheduled activation failure

```text
old active = CAL_A
weekly candidate = CAL_B
CAL_B validation = FAIL
new-session first trade = (2026-08-17T00:00:00.010Z, 900)
```

expected:

```text
effective calibration for trade_id=900 = CAL_A
activation row for CAL_B = 0
status = CALIBRATION_ACTIVATION_FAILED
manual fallback = 0
```

## 52. baseline regression

各工程で少なくとも次を実行する。

```text
tests/normalization/
tests/orderflow/test_cvd.py
tests/orderflow/test_footprint.py
tests/orderflow/test_flow_price_response.py
tests/orderflow/test_flow_detector.py
tests/orderflow/test_absorption.py
tests/orderflow/test_imbalance.py
tests/test_pipeline.py
tests/test_live_pipeline.py
tests/webapp/test_tape_update.py
tests/webapp/test_push_broker.py
tests/webapp/test_footprint_chart_ui.py
tests/webapp/test_dom_tape_fusion_ui.py
tests/webapp/test_dom_trade_pulse_ui.py
tests/webapp/test_api.py
tests/test_config.py
```

最終gateではrepository全体pytestを実行する。

開始前から存在するfailureがある場合、開始時にtest名、error、再現commandをbaselineへ固定する。新規failure 0だけで済ませず、本機能との非因果を示す。

## 53. backfill

### 53.1 dry-run first

保存済みtradesから過去Big Trade eventを作る場合、最初にdry-run reportだけを作る。

report:

```text
source DB path
source DB SHA-256またはsnapshot identity
symbol
start/end
trade count
invalid count
cluster count
accepted count by Manual／Low／Medium／Strong
estimated event rows
estimated fill rows
estimated disk bytes
duration
logic version
calibration ID
```

### 53.2 no live DB mutation

初回backfillはproduction runtimeが書込み中のDuckDBへ直接混在させない。read-only snapshotまたは明示的なmaintenance windowを使用する。

### 53.3 idempotency

同じsource、logic、settings、calibrationで再実行してもevent IDが同じで、duplicate追加0になることを確認する。

### 53.4 activation boundary

backfill完了とlive feature ONを同じ操作にしない。

## 54. GO-BT0 — baseline／design lock

実施内容:

1. `PROJECT_MEMORY.md`全文再読。
2. current branch、HEAD、dirty status保存。
3. 本指示書対象fileの現行SHA-256保存。
4. user変更と予定hunkの重複監査。
5. current test baseline。
6. current browser geometry 1280×900保存。
7. current runtime health／latency／Tape／Book stats保存。
8. production quantity stepとmanual初期値の確認。
9. restore手段を記録。

完了条件:

- source変更0。
- baseline reportとcheckpointがある。
- userへ結果を提示。
- GO-BT1待ちで停止。

## 55. GO-BT1 — pure core

実施内容:

- constants、models、IDs、UTC `time_buckets`、aggregator、Manual filter。
- Automatic pure calibrator。
- fixed vectorsとcore unit tests。
- pipeline、storage、UIへ未接続。

完了条件:

- core test全PASS。
- Decimal以外のauthoritative数値計算0。
- deterministic ID確認。
- UTC minute floorとCVD boundary parity fixture確認。
- logic正本の全式と一致。
- GO-BT2待ちで停止。

## 56. GO-BT2 — config／calibration artifacts

実施内容:

- strict config追加。schedule、activation policy、Replay modeを含む。
- settings request model／history／pending contract。
- offline calibration tool。
- calibration artifactとactivation artifactのatomic write／hash／pointer contract。
- dry-run calibration report。

feature flagはfalseのまま。

完了条件:

- invalid config fail closed。
- dry-runはsource不変。
- same input same calibration ID。
- artifact test全PASS。
- settings request時刻がeffective境界へ流用されていない。
- scheduled auto／manual-onlyのpolicy分岐がconfig contractどおり。
- GO-BT3待ちで停止。

## 57. GO-BT3 — storage／Live／Replay

実施内容:

- new storage schema。
- background writer kinds。
- BigTradesRuntime。
- ReplayPipeline／LivePipeline同一接続。
- event＋fills保存。
- source-confirmed session transition、session stats、shutdown／restart境界。
- CVD closed candle→Big Trades current tradeの順序。
- activation history保存とeffective source key binding。
- `HISTORICAL_ACTIVATION` Replay選択と`FIXED_RESEARCH`隔離。

feature flagはfalseのまま。test内だけoverrideする。

完了条件:

- storage atomicity PASS。
- Live／Replay golden equality PASS。
- wall clockによるsession完了0件。
- scheduled activation成功時は新session first clusterから有効、失敗時は旧version維持。
- activation history欠損Replayのfail-closed PASS。
- 既存indicator回帰PASS。
- Big Trades ERROR isolation PASS。
- GO-BT4待ちで停止。

## 58. GO-BT4 — WebSocket／REST

実施内容:

- BigTradeBatcher。
- BIG_TRADES_UPDATE。
- BIG_TRADES_STATUS。
- history、fills、settings、calibration、activation history API。
- recent ring merge。
- stats。

UIは未接続。

完了条件:

- sequence／gap／drop contract PASS。
- history pagination PASS。
- setting transaction PASS。
- settings／manual calibration requestの`PENDING` contract PASS。
- statusがactivation policy、active／pending ID、失敗reasonを区別。
- existing payload回帰PASS。
- GO-BT5待ちで停止。

## 59. GO-BT5 — independent BIG TRADES UI

開始前に、中央3-modeの見え方をuserへ画像または静的mockで提示し、明示承認を得る。

実施内容:

- `big_trades.js`。
- third mode button。
- dedicated canvas／controls／status／detail。
- history hydration。
- marker interaction。
- gap recovery。

完了条件:

- 1280×900実browserで重なり0、overflow 0。
- Footprint／Heatmap／Time & Sales不変。
- 3段chart geometry 1pxも変化なし。
- browser error 0。
- user visual確認。
- GO-BT6待ちで停止。

## 60. GO-BT6 — integration／performance／soak

実施内容:

- source snapshotでend-to-end Replay。
- Big Trades OFF／ON比較。
- Automatic scheduled activation、failure retention、Manual run。
- historical activation Replayとfixed research隔離。
- source-confirmed session transitionとcandle boundary parity。
- 6,000 trade、25,000 trade overflow accounting。
- 120秒以上live soak。
- full regression。
- storage read-back。
- browser performance。

production feature flagはfalseのまま。

完了条件:

- new failure 0。
- server/browser delay gate PASS。
- Tape／Book／storageにfeature起因drop 0。
- Live／Replay equality PASS。
- Replay event全件のsettings／calibration IDがactivation historyから追跡可能。
- WEEKLY／MONTHLY正常系のmanual activation request 0件。
- accepted marker全件がhistory再取得可能。
- GO-BT7待ちで停止。

## 61. GO-BT7 — operational activation

実施内容:

1. pre-deploy backup／image ID／rollback image固定。
2. hostとimageのtarget file hash照合。
3. image内test。
4. user承認済み初期settings、初期calibration、schedule、activation policyを配置。
5. `enabled: true`へ変更。
6. controlled restart。
7. health、source time、storage、WebSocket、browser確認。
8. 30分以上のoperational soak。

完了条件:

- ManualまたはAutomaticのeffective thresholdが画面に明示。
- markerのaggregate quantityがraw fills合計と一致。
- history read-back一致。
- restart後settings／calibration復元。
- active pointer cacheとcommitted activation artifactのeffective key一致、cache再構築PASS。
- scheduled auto activation成功とvalidation失敗時の旧version維持をproduction相当fixtureで確認。
- default scheduled運用に週次／月次manual version選択作業がない。
- existing Flow Price Response／3段chart／Tape／DOM／Footprint正常。
- rollback testedまたは実行手順verified。
- userへcompletion report提出。

## 62. rollback

### 62.1 feature rollback

最初に`big_trades.enabled: false`へ戻す。既存indicatorは継続する。

### 62.2 UI rollback

third mode buttonとBig Trades module読込だけを戻し、Footprint／Heatmapの既存hunkを巻き戻さない。

### 62.3 backend rollback

Big Trades callbackとruntime生成を無効化する。新tableとParquetは削除せず、読み取り対象外にする。

### 62.4 data rollback

新Big Trades table／Parquet／calibration artifactを自動削除しない。data deletionは別の明示承認とbackup確認を要する。

### 62.5 禁止

- `git reset --hard`
- broad checkout
- repository全体のclean
- wildcard recursive delete
- existing DuckDB置換
- user dirty changeの破棄

## 63. checkpoint contract

各gateで次を逐次更新する。

```text
現在時刻
承認されたgate
branch／HEAD
開始時dirty status
完了済み
未完了
変更file
各fileの目的
test commandと結果
performance結果
runtime結果
blockerの限定範囲
rollback位置
次の再開位置
```

最初の変更前、各GO完了後、長時間backfill／soakの前後、user承認要求前、未完了終了前に更新する。

## 64. 禁止shortcut

次を禁止する。

1. 個別tradeへMinをかけただけでAggregate Trades完成とする。
2. browserのTAPE_UPDATEを40ms集約してserver featureの代用にする。
3. existing `LargeTradeDetector`の閾値だけ変えて完成とする。
4. current Time & Sales `LARGE ≥`を名前変更して完成とする。
5. Automaticを固定Min三個で代用する。
6. Low／Medium／Strongのthreshold根拠を保存しない。
7. floatで較正して表示時だけDecimal文字列にする。
8. 進行中sessionまたは未来dataを較正へ混ぜる。
9. insufficient history時に任意値へfallbackする。
10. settings変更でopen clusterの判定を途中変更する。
11. replay speedまたはwall clockでcluster境界を変える。
12. eventを保存前にbroadcastする。
13. WebSocket dropを画面から隠す。
14. markerを大口本人、parent order、institutionと表示する。
15. Big Trade eventを売買signalまたはMT5へ接続する。
16. Flow Price Responseまたは3段chartをBig Trades都合で変更する。
17. userの既存dirty changeを整形、cleanup、置換する。
18. wall clock、shutdown、timerだけでcurrent sessionを完了扱いにする。
19. existing candle builderから渡されたIDをBig Tradesのcluster candle ID正本にする。
20. calibration `created_at_utc`またはfile timestampから過去のactive versionを推定する。
21. activation history欠損時に現在calibrationでhistorical Replayを続行する。

## 65. logic正本とのtraceability

| logic正本 | 本指示書 |
|---|---|
| 入力 | §8、§9 |
| 正規化・重複・整列 | §5.1、§13.0、§28 |
| 40ms cluster | §13 |
| cluster確定値 | §13.6 |
| input mode | §8 |
| Manual Min／Max | §14 |
| Automatic key | §15 |
| 20 session ranking | §15、§16 |
| median | §17 |
| volatility | §18 |
| threshold補正 | §19 |
| calibration version | §20、§21 |
| session完了trigger | §21.3、§28.3、§28.4 |
| scheduled activation policy／運用コスト | §11、§21.4、§21.5 |
| candle ID owner／parity | §9.5、§28.3 |
| activation effective boundary | §12.5、§26.6 |
| Replay calibration特定 | §15.3、§26.6 |
| runtime選択 | §12、§22 |
| marker位置 | §25 |
| marker output | §24、§30 |
| visual scale | §25.3 |
| history | §26、§31、§35 |
| exception | §36、§37 |
| pseudocode | §13、§14、§18、§19、§22 |
| test vectors | §45～§51 |
| invariants | §66 |

logic正本の項目を未対応のまま工程完了にしない。

## 66. 最終invariants

実装と全保存物は次を満たす。

```text
aggregate_quantity > 0
aggregate_notional > 0
fill_count >= 1
fill_count == saved fill row count
first_time <= last_time
duration_ms >= 0
low_price <= first_price <= high_price
low_price <= last_price <= high_price
low_price <= marker_price <= high_price または VWAP tick丸めの許容1 tick内
manual_max == 0 or manual_min <= manual_max
auto_low < auto_medium < auto_strong
0.75 <= volatility_factor <= 1.50
event logic_version == calibration logic_version
event symbol == calibration symbol when Automatic
event input_mode == calibration input_mode when Automatic
session completion requires first accepted trade of a different later session
wall clock and stream end never complete current session
candle_id == floor_utc_bucket(trade.event_time_utc, 60 seconds)
Big Trades minute boundary == corresponding CVD closed candle bar_time
effective runtime snapshot == activation artifact selected by cluster first source key
calibration created_at_utc does not select Replay version
scheduled successful activation begins at new-session first cluster
scheduled failed activation leaves previous calibration active
FIXED_RESEARCH writes production Big Trades history 0 rows
same input + same settings + same calibration → same event IDs and payloads
Big Trades disabled → existing outputs unchanged
```

## 67. V1 acceptance criteria

V1完成を名乗る条件は次の全てである。

- 40ms同方向aggregationがlogic正本どおり。
- price levelを跨ぐclusterが合算される。
- Manual Min／Maxが境界値込みで正しい。
- Max 0が上限なし。
- Automatic Low／Medium／Strongが20／9／2順位で生成される。
- 20完了session、直近5session volatility、0.75～1.50補正が再現可能。
- 完了sessionが次session最初のaccepted source tradeだけで確定し、wall clock／shutdownでは確定しない。
- session statsに旧session最後のCVD確定1分足が処理順どおり含まれる。
- candle IDはBig Trades共通UTC関数が算出し、CVD boundary不一致をfail closedで検出する。
- threshold、settings、calibration versionがmarkerごとに保存される。
- scheduled WEEKLY／MONTHLY calibrationはvalidation成功時に新session first clusterから自動activateし、通常manual activation 0回。
- scheduled activation失敗時は旧calibrationを維持し、失敗を表示する。
- Live／Replay同値。Replay calibrationはactivation historyのeffective source keyから一意に特定される。
- calibration `created_at_utc`はReplay選択へ一切使用されない。
- activation history欠損／不整合Replayはfallbackせずfail closed。
- `FIXED_RESEARCH`はproduction history／pointer／ledgerから隔離される。
- event＋全fillsがhistoryから再読込可能。
- WebSocket sequence gapが検出・回復可能。
- BIG TRADES chartで数量、side、時刻、価格、fill数、thresholdを確認できる。
- 既存Time & Sales、LargeTradeDetector、Heatmap bubbleと意味が混ざっていない。
- Automatic unavailableを画面で明示し、silent fallbackしない。
- full regressionとperformance gateがPASS。
- Flow Price Responseと3段chartの計算・構造・geometryが不変。
- Strategy／Hook／MT5／注文接続0。
- production activationはGO-BT7の明示承認後だけ。

## 68. 完成報告に必須の証拠

completion reportへ次を添付する。

1. 変更file一覧。
2. logic traceability結果。
3. fixed vector実出力。
4. Manual境界test。
5. Automatic較正artifact一式。
6. activation historyとactive pointer cacheの一致／再構築証拠。
7. source-confirmed session transitionの処理順trace。
8. candle boundary parity結果。
9. source manifestとSHA-256。
10. Live／Replay同値比較とReplay activation選択trace。
11. eventとfill history read-back。
12. WebSocket sequence／gap試験。
13. 1280×900 browser screenshot。
14. 3-mode切替screenshot。
15. Big Trade marker tooltip screenshot。
16. 3段chart geometry比較。
17. performance／soak結果。
18. full pytest結果。
19. production image／container ID（GO-BT7時）。
20. rollback手順とrollback image（GO-BT7時）。

テスト件数だけで完成を断定しない。raw tradeからmarker数量まで追跡できる具体例を最低3件提示する。

## 69. 実装開始前の最終確認

確認時点を工程ごとに固定する。

```text
GO-BT0開始前:
  今回のGOはどのgateまでか。

GO-BT2でproduction候補configを固定する前:
  Manual初期Min／Maxはいくつか。

GO-BT5のindex.html変更前:
  中央3-mode UI mockは承認済みか。

GO-BT7のproduction activation前:
  production初期modeはManualかAutomaticか。
  Automaticを使用する場合、初期calibration version、schedule、activation policy、rollback先は何か。
```

`SCHEDULED_SESSION_BOUNDARY`承認後は、正常な週次／月次candidateごとの追加承認を要求しない。validation失敗またはrollback時だけ該当操作を止めてuserへ報告する。

後工程の回答がまだなくても、現在承認済みの独立工程は継続できる。回答のない後工程へは進まず、実装者がproduction値を推定しない。

## 70. 本指示書の停止命令

本指示書作成時点では、実装、test実行、backfill、runtime変更、UI変更、deploymentを行わない。

userが`GO-BT0`または対象gateを明示するまで停止する。
