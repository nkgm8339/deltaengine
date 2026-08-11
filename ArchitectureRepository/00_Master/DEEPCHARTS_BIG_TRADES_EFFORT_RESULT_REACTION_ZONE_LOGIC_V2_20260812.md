# DeltaEngine Big Trades Effort／Result・Reaction Zone ロジック V2

- 作成日: 2026-08-12
- 文書種別: 決定論的logic正本
- 対象: Big Trades Size Filter、Big Trade marker、Reaction Zone、後続price result、反復effort
- 旧正本: `DEEPCHARTS_BIG_TRADES_SIZE_FILTER_RECONSTRUCTION_LOGIC_V1_20260811.md`
- 実装状態: 未実装
- source実装承認: 本書だけでは与えない

## 0. 一文で定義する目的

本logicは、約定済み取引から大きなexecuted effortを選別し、その実行価格帯を時間方向へ保持し、後続価格の移動、再訪、反復攻撃、wick、close、追加Big Tradeを同じzoneへ結び付け、userが`effort`と`result`を分断せず判断できる観測記録を作る。

Size Filter通過を完成条件にしない。

```text
大きなexecuted effortを抽出する
  → そのexecution rangeをReaction Zoneとして固定する
  → 後続price pathをsource timeで追う
  → 同じ価格帯の追加effortと反対effortを結び付ける
  → effortとresultを同じ画面、履歴、Replayで再現する
```

## 1. V1からの訂正

V1はSize Filterの仕事をmarker出力までに限定し、Big Trade後のprice resultを対象外にした。この限定ではFabio本人が公開動画で繰り返す`law of effort and result`の後半を実行できない。

V2は次の4項目を一つの機能として扱う。

1. Manual Min／Max Size Filter。
2. symbol・activity・volatility連動Automatic Size Filter。
3. accepted Big Tradeごとのmarker、全fill、履歴。
4. Big Trade execution priceから延長するReaction Zoneと後続result履歴。

V1／V1.1を削除または同一versionで上書きしない。V2が実装正本として優先し、旧版は訂正経緯として残す。

## 2. Fabio一次証拠から固定する判断対象

Fabio本人の公開動画から確定している中心は次である。

- volume／contractsは`effort`。
- price movementは`result`。
- 大きな攻撃が同方向へpriceを動かせば、攻撃側はresultを得た。
- 大きな攻撃がpriceを動かせなければ、反対側がそのeffortを受け止めた可能性を読む。
- 同じhorizontal areaへの攻撃と失敗が反復することを重視する。
- Big Trades、CVD、Delta、Footprint、price confirmationを別々の確認項目として読む。
- marker一件の発注者名、機関名、parent orderを特定していない。

直接対応する公式例:

- `72・61・60・62 contracts`: 大きなeffortが上へ継続せず、反対側だけが下方resultを得た。
- `105・101 contracts`: 別時刻の攻撃が同じ下側areaを抜けず、複数回失敗した。
- CVD下方pressure: Big Tradesとprice follow-throughが出るまでentryしなかった。
- Big Tradesがpriceを下へpushしなくなった場面: exit判断へ使った。
- repeated seller attack: breakout後の同一levelで繰り返し吸収され、level protectionを確認した。

この事実はReaction Zone、反復effort link、price path、candle resultをV2の必須出力にする根拠である。

## 3. 公開事実とDeltaEngine再構成の分離

### 3.1 Fabio本人の公開事実

- size filterで大きなexecuted ordersを残す。
- volumeが多い日はfilterを大きくする。
- 大きなexecuted effortをprice resultと照合する。
- 同じareaでの反復攻撃と失敗をまとめて読む。
- priceがBig Trade方向へpushし続けるか、pushしなくなるかを管理へ使う。

### 3.2 DeepCharts公式仕様として確認済み

- Manual Min／Max。
- Max 0は上限なし。
- Aggregate Trades。
- Automatic Low／Medium／Strong。
- symbolのprice behaviorとvolatilityを使う自動分析。
- marker price mode。

### 3.3 V2が再現可能にするため固定する値

次はFabioまたはDeepChartsの非公開formulaではない。DeltaEngine V2の決定論的再構成値である。

```text
aggregation_window_ms = 40
history_sessions = 20
recent_volatility_sessions = 5
target_low = 20 events/session
target_medium = 9 events/session
target_strong = 2 events/session
volatility_factor_min = 0.75
volatility_factor_max = 1.50
reaction_zone_match_tolerance_ticks = 1
reaction_observation_session = CRYPTO_UTC_DAY
result_horizons_seconds = [1, 5, 15, 30, 60, 180, 300, 600]
result_snapshot_max_staleness_ms = 1000
```

これらを変更するとlogic versionを上げる。

## 4. V2が自動判定しないもの

V2は次を自動的な確定事実として出さない。

- 発注者名、機関名、口座、同一人物。
- 複数eventが同一parent orderであること。
- `institutional order confirmed`。
- `absorption confirmed`。
- `buyers won`、`sellers won`という最終裁定。
- entry、exit、stop、target。
- 勝率、確率、confidence。
- Hook、Strategy、MT5へのOrder Trigger。

systemは観測事実を出す。最終的なFabio型判断はuserが行う。userが付けた評価は`USER ASSESSMENT`としてsystem observationと分離して保存する。

## 5. 全体処理

```text
NormalizedTrade
  → same-millisecond deterministic ordering
  → same-side 40ms ExecutionCluster
  → aggregate quantity
  → Manual or Automatic Size Filter
  → BigTradeEvent + all fills
  → ReactionZone created from exact execution range
  → every later accepted trade updates zone relation and excursions
  → every closed 1m candle adds wick/body/close observation
  → later BigTradeEvent near the zone creates repeated-effort link
  → fixed source-time horizon snapshots
  → source-confirmed session end closes active observation
  → storage, WebSocket, history, Replay
```

## 6. Authoritative input

### 6.1 Big Trade検出input

`DataNormalizer`がacceptしreleaseした`NormalizedTrade`だけを使う。

必須field:

```text
event_time_utc
trade_id
symbol
venue
price: Decimal
quantity: Decimal
side: BUY | SELL
```

raw WebSocket、browser `TAPE_UPDATE`、arrival wall clockから再計算しない。

### 6.2 price result input

後続price pathのauthoritative sourceも、同じaccepted `NormalizedTrade.price`と`event_time_utc`である。

```text
accepted trade price = path observation
closed 1m candle = wick/body/close observation and visual context
browser receive time = authoritative判定へ不使用
Replay speed = authoritative判定へ不使用
```

### 6.3 candle

既存CVDが確定した1分足をread-onlyで受け取る。Big Tradesはtrade event timeから自前のUTC minute IDを算出し、既存candle boundaryと一致することだけを検証する。

不一致時は`CANDLE_BOUNDARY_MISMATCH`としてBig Tradesだけをfail closedにする。

## 7. 数値と時刻

- price、quantity、notional、VWAP、threshold、excursion、bpsはPython `Decimal`。
- time orderingはtimezone-aware UTC source timeとtrade ID。
- millisecondはUTC epoch microsecondsを1000でinteger floorする。
- sessionはUTC 00:00から次のUTC 00:00直前。
- 1分IDはUTC epoch microsecondsを60秒でinteger floorする。
- UIはpixel計算だけNumberを使用し、server判定を再計算しない。

## 8. deterministic ordering

同一`event_time_ms`のtradeは一bucketへ保持し、次millisecond到着時にtrade ID整数昇順でreleaseする。

stream end、disconnect、session transitionではbucketをsortしてflushする。release済みmillisecondより古いtradeは`LATE_AFTER_RELEASE`として拒否する。

## 9. ExecutionCluster

### 9.1 join条件

次をすべて満たす場合だけcurrent tradeをopen clusterへ加算する。

```text
same symbol
same venue
same aggressor side
current.event_time_ms - cluster.last_time_ms <= 40
same UTC session
same 1m candle_id
```

priceが異なってもjoinする。40msはcluster先頭からではなく直前fillから測る。

```text
0ms → 35ms → 70ms = one cluster
```

### 9.2 close条件

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

### 9.3 finalized values

```text
aggregate_quantity = Σ quantity
aggregate_notional = Σ(price × quantity)
vwap = aggregate_notional / aggregate_quantity
duration_ms = last_time_ms - first_time_ms
low_price = min(fill prices)
high_price = max(fill prices)
price_level_count = count(distinct fill prices)
```

## 10. Size Filter

### 10.1 Manual

```text
q < Min                         → REJECT_BELOW_MIN
Max > 0 and q > Max            → REJECT_ABOVE_MAX
otherwise                      → ACCEPT
```

Min／Maxと同値はACCEPT。Max 0は上限なし。side filterはquantity判定後の表示filterであり、規模判定へ混ぜない。

### 10.2 Automatic

key:

```text
symbol
venue
input_mode
session_template
quantity_unit
logic_version
```

`as_of`より前の直近20完了sessionへ同じ40ms aggregatorを適用し、各sessionのcluster quantityを降順にする。

```text
LOW    = session内20位
MEDIUM = session内9位
STRONG = session内2位
```

各順位値を有効session間でDecimal medianする。有効sessionが一強度でも10未満ならcalibration全体を`INSUFFICIENT_HISTORY`とする。

volatility:

```text
TR = max(high-low, abs(high-prev_close), abs(low-prev_close))
NTR = TR / close
session_volatility = median(valid 1m NTR)
baseline = median(last 20 valid completed sessions)
recent = median(last 5 valid completed sessions)
factor = clamp(sqrt(recent / baseline), 0.75, 1.50)
```

必要件数不足またはbaseline 0はfactor 1.00とし、`VOLATILITY_FALLBACK_1`を保存する。quantity rankingの10-session gateは維持する。

```text
auto_low = ceil(base_low × factor to quantity_step)
auto_medium = ceil(base_medium × factor to quantity_step)
auto_strong = ceil(base_strong × factor to quantity_step)
auto_medium = max(auto_medium, auto_low + step)
auto_strong = max(auto_strong, auto_medium + step)
```

```text
auto_low < auto_medium < auto_strong
```

Automatic Maxは0。

## 11. BigTradeEvent

Size Filter通過clusterごとにimmutable eventを一件作る。

必須field:

```text
event_id
logic_version
symbol
venue
side
first_time
last_time
first_trade_id
last_trade_id
first_price
last_price
low_price
high_price
vwap
aggregate_quantity
aggregate_notional
fill_count
price_level_count
duration_ms
threshold_used
max_threshold_used
filter_mode
intensity
settings_id
calibration_id
session_id
candle_id
```

event IDはcanonical contentからSHA-256で作る。発注者またはorder IDを意味しない。

## 12. Reaction Zone生成

### 12.1 一件一zone

accepted BigTradeEvent一件につき、一件のauthoritative Reaction Zoneを作る。

```text
zone_id = "btz2_" + sha256("BTZ2|" + logic_version + "|" + event_id)
```

複数eventを一つへ破壊的にmergeしない。各eventと全fillの追跡可能性を維持する。

### 12.2 price bounds

```text
zone_low = event.low_price
zone_high = event.high_price
zone_anchor = event.vwap
```

zoneのauthoritative幅は実際に約定したprice rangeだけである。ATR、任意percentage、candle高安、VWAP周辺幅で勝手に拡張しない。

single-price eventは`zone_low == zone_high`を許可する。画面上の最低pixel高は描画だけに使い、hit test、touch、exit判定へ逆流させない。

### 12.3 time bounds

```text
zone_source_start = event.last_time
zone_visual_start = event.first_time
```

price resultはclusterが完成した`last_time`より後だけを対象にする。cluster自身のfillを後続resultへ数えない。

authoritative observationは同じUTC sessionの終了まで継続する。session完了は次session最初のaccepted tradeでsource-confirmする。

```text
zone_source_end = old session end
zone_close_trigger = NEXT_SESSION_FIRST_ACCEPTED_TRADE
```

wall clock、browser timer、shutdownだけでzoneを完了扱いにしない。

### 12.4 zone origin side

origin sideはBigTradeEventのaggressor sideをそのまま保存する。zoneをsupportまたはresistanceと自動命名しない。

```text
origin_side = BUY | SELL
```

BUY zoneが将来supportになる、SELL zoneがresistanceになると固定しない。後続resultを見てuserが判断する。

## 13. price relation

各後続accepted tradeについて、zoneとの位置関係を計算する。

```text
price < zone_low               → BELOW
zone_low <= price <= zone_high → INSIDE
price > zone_high              → ABOVE
```

境界同値はINSIDE。

zone作成時のlast fillは初期referenceであり、interaction countへ入れない。`event.last_time`より後、または同一時刻で`trade_id > event.last_trade_id`のtradeだけを後続観測へ使う。

## 14. path interaction

relationの遷移をappend-only interactionとして記録する。

### 14.1 closed enum

```text
ZONE_CREATED
FIRST_EXIT_UP
FIRST_EXIT_DOWN
TOUCH_FROM_ABOVE
TOUCH_FROM_BELOW
REENTER_FROM_ABOVE
REENTER_FROM_BELOW
CROSS_UP
CROSS_DOWN
RELATION_ABOVE
RELATION_INSIDE
RELATION_BELOW
SOURCE_GAP_STARTED
SOURCE_GAP_ENDED
ZONE_SESSION_CLOSED
```

### 14.2 first exit

zone作成後、最初にINSIDE以外となったaccepted tradeをfirst exitとする。

```text
ABOVE → FIRST_EXIT_UP
BELOW → FIRST_EXIT_DOWN
```

保存値:

```text
exit_time
exit_trade_id
exit_price
exit_direction
time_to_exit_ms
distance_from_nearest_boundary_ticks
```

### 14.3 touch／reentry

- 直前relationがABOVEでcurrentがINSIDEなら`TOUCH_FROM_ABOVE`。
- 直前relationがBELOWでcurrentがINSIDEなら`TOUCH_FROM_BELOW`。
- 一度zone外へ出た後の最初のINSIDEを対応する`REENTER_*`としても記録する。
- 同じINSIDE滞在中のtrade一件ごとにtouch countを増やさない。

### 14.4 cross

accepted trade列が`BELOW → ABOVE`または`ABOVE → BELOW`へ直接遷移した場合、時刻を補間せず`CROSS_UP`または`CROSS_DOWN`をcurrent trade keyで記録する。

架空のzone内tradeまたは架空のcross timestampを生成しない。

## 15. excursion

zone作成後のaccepted tradeから次を継続更新する。

```text
max_price_seen
min_price_seen
max_above_ticks = max(0, (max_price_seen - zone_high) / tick_size)
max_below_ticks = max(0, (zone_low - min_price_seen) / tick_size)
max_above_bps = max(0, (max_price_seen / zone_anchor - 1) × 10000)
max_below_bps = max(0, (1 - min_price_seen / zone_anchor) × 10000)
```

origin sideに対する算術表示:

```text
BUY  directional_excursion = max_above
BUY  opposite_excursion    = max_below
SELL directional_excursion = max_below
SELL opposite_excursion    = max_above
```

これはresult量の表示であり、勝者または売買signalではない。

## 16. inside-zone executed activity

zone内で成立した後続accepted tradeをside別に累積する。

```text
inside_buy_quantity
inside_sell_quantity
inside_buy_trade_count
inside_sell_trade_count
inside_total_quantity
```

同一tradeが複数zoneへ入る場合、各zoneの独立観測へ一回ずつ属してよい。複数zoneの数量を市場全体の独立票として合算しない。

## 17. repeated Big Trade link

後続BigTradeEventと既存active zoneのprice interval distanceを計算する。

```text
interval_gap = max(
  0,
  max(zone_low, event.low_price) - min(zone_high, event.high_price)
)
```

```text
interval_gap <= tick_size × reaction_zone_match_tolerance_ticks
```

を満たし、同symbol、同venue、同session、後続eventである場合、`ZONE_BIG_TRADE_LINK`を作る。

必須field:

```text
zone_id
origin_event_id
linked_event_id
linked_side
linked_quantity
linked_low
linked_high
linked_time
interval_gap_ticks
same_as_origin_side: boolean
ordinal_for_zone
```

linkは同一主体または同一parent orderを意味しない。同じhorizontal areaで別の大きなexecuted effortが起きたという事実だけを表す。

zone summaryへ次を持つ。

```text
linked_big_trade_count
linked_buy_quantity
linked_sell_quantity
same_side_effort_count
opposite_side_effort_count
```

これにより`105 → 再試行 → 101`のような別時刻の反復を一つのzoneから追える。

## 18. fixed result horizons

origin eventごとに次のsource-time horizonを作る。

```text
1s, 5s, 15s, 30s, 60s, 180s, 300s, 600s
```

target:

```text
target_time = event.last_time + horizon_seconds
```

first accepted trade with `event_time > target_time`を受け取った時点で、target以下の最後のaccepted tradeをsnapshot priceとする。

```text
snapshot_price = last accepted price where time <= target_time
snapshot_source_age_ms = target_time - snapshot_trade_time
```

有効条件:

```text
snapshot exists
snapshot_source_age_ms <= 1000
no source gap intersects (event.last_time, target_time]
same session
```

無効ならpriceを補間せず`MISSING_STALE`または`MISSING_SOURCE_GAP`とする。

snapshot field:

```text
horizon_seconds
target_time
snapshot_trade_id
snapshot_trade_time
snapshot_source_age_ms
snapshot_price
relation = ABOVE | INSIDE | BELOW
return_from_last_price_bps
return_from_vwap_bps
origin_side_signed_return_bps
max_above_ticks_to_horizon
max_below_ticks_to_horizon
touch_count_to_horizon
cross_count_to_horizon
linked_big_trade_count_to_horizon
inside_buy_quantity_to_horizon
inside_sell_quantity_to_horizon
validity
```

`origin_side_signed_return_bps`はBUYを+1、SELLを-1として算術的に符号をそろえた値であり、勝率またはsignalではない。

## 19. 1分candle result

zone開始後に確定した各1分足について、zoneとの関係を保存する。

```text
candle_open_relation
candle_close_relation
candle_high_above_ticks
candle_low_below_ticks
body_low
body_high
body_overlaps_zone
wick_overlaps_zone
closed_above_zone
closed_below_zone
returned_inside_after_upper_excursion
returned_inside_after_lower_excursion
```

決定規則:

```text
closed_above_zone = close > zone_high
closed_below_zone = close < zone_low
upper_wick_return = high > zone_high and close <= zone_high
lower_wick_return = low < zone_low and close >= zone_low
```

UI表示名:

```text
CLOSE ABOVE
CLOSE BELOW
UPPER WICK RETURN
LOWER WICK RETURN
CLOSED INSIDE
```

`REJECTION CONFIRMED`または`ABSORPTION CONFIRMED`へ自動変換しない。Fabioの「wickだけ」「candle result」を人間が確認できる事実として出す。

## 20. system observation summary

systemが表示してよいsummaryは事実の組合せに限定する。

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

次の変換は禁止する。

```text
FIRST EXIT UP → BUYERS WON
FIRST EXIT DOWN → SELLERS WON
NO EXIT → ABSORPTION CONFIRMED
REPEATED BIG EFFORT → SAME WHALE
```

## 21. user assessment

Fabio型の最終読解を記録できるよう、userがzoneへ評価を付けられる。ただしsystem observationと別table／別fieldにする。

closed enum:

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

保存:

```text
assessment_id
zone_id
assessment
assessed_at_utc
assessed_against_source_time
user_note
supersedes_assessment_id nullable
```

assessmentはappend-only。訂正時は旧rowを削除せずsupersedeする。systemはassessmentから注文を出さない。

## 22. locationとcontext

Reaction Zone自体はlocation filterを大口認定条件へ混ぜない。

次はread-only contextとして表示できる。

- zone作成時の1分candle OHLC。
- 既存CVD、Delta、Volume。
- 既存Flow Price Response状態。
- 既存Absorption、Imbalance event。
- 既存Footprint price-level data。
- 既存VWAP、previous high／low等。

各contextはsource ID、source time、元の値を保持する。Big Tradesのscoreへ加算しない。既存indicatorの計算、threshold、保存を変更しない。

V2必須なのは、Big Trades chart選択時に同一candle ID／time／priceを確認できるread-only linkである。全contextを一つの自動判定へ統合することではない。

## 23. zone lifecycle

closed enum:

```text
ACTIVE
ACTIVE_WITH_GAP
SESSION_CLOSED
ERROR
```

priceが一度zoneを突破してもzoneを削除またはterminalにしない。Fabioはbreak後のretest、level protection、control changeも見るため、同一session中はrelationと再訪を記録し続ける。

source-confirmed next session first tradeで旧session zoneを`SESSION_CLOSED`にする。履歴からは消さない。

表示上のON／OFF、side filter、minimum visual sizeはデータ収録を停止しない。

## 24. disconnect、gap、restart

### 24.1 disconnect

- open execution clusterを`STREAM_DISCONNECTED`でflushする。
- active zone自体は削除しない。
- gap開始source keyを記録する。
- reconnect後、gap終了を記録する。
- gapを跨ぐhorizon snapshotは`MISSING_SOURCE_GAP`。
- gap後の観測は別segmentとして継続し、gap前後を連続price pathと表示しない。

### 24.2 restart

- open clusterは復元しない。
- session未完了のactive zone、interaction、last relation、excursion、horizon progressをauthoritative artifact／DBから復元する。
- raw trade再走査なしで完全復元できないzoneは`ACTIVE_WITH_GAP`とする。
- restart前後を連続と偽装しない。

### 24.3 WebSocket gap

serverのauthoritative observationは継続する。browserはstream sequence gapを表示し、history APIからevent、zone、interaction、snapshotを回復する。回復完了までwarningを消さない。

## 25. persistence model

最低限、次をappend-onlyまたはimmutableで保存する。

```text
big_trade_events
big_trade_event_fills
big_trade_reaction_zones
big_trade_zone_interactions
big_trade_zone_event_links
big_trade_result_snapshots
big_trade_zone_candle_observations
big_trade_user_assessments
big_trade_session_stats
big_trade_calibrations
big_trade_settings_history
big_trade_activation_history
```

event、fills、zone creationは一つのatomic storage batchにする。eventだけ保存してzoneがない状態、zoneだけ保存してorigin eventがない状態をcommitしない。

zone update、interaction、snapshotはdeterministic IDとcontent hashを持つ。同一ID・同一contentはidempotent、同一ID・異なるcontentはcollisionでBig Tradesだけをfail closedにする。

## 26. Live／Replay

LiveとReplayは同じordering、aggregator、filter、zone observer、candle observer、horizon finalizerを使う。

```text
same accepted trades
+ same candles
+ same settings activation history
+ same calibration artifacts
→ same events
→ same zones
→ same interactions
→ same links
→ same snapshots
```

Replay speed、sleep、実行wall clockで結果を変えない。

historical Replayはcluster first source key以下の最後のcommitted activationを使用する。calibration created time、file timestamp、現在のactive pointerから過去versionを推定しない。

user assessmentは市場事実のReplay出力へ混ぜない。必要なら別layerとして同じsource timeへoverlayする。

## 27. settings snapshot

open clusterは開始時settingsをimmutable snapshotする。Reaction Zoneはorigin eventのsettings、calibration、zone logic versionを最後まで保持する。

後からSize Filter、side display、marker priceを変えても、既存zoneのbounds、origin event、過去interactionを書き換えない。

zone表示setting変更は表示だけに適用する。authoritative observation contractを途中変更しない。

## 28. deterministic IDs

```text
event_id       = hash(cluster identity)
zone_id        = hash(logic version + event_id)
interaction_id = hash(zone_id + interaction type + source event time + trade/candle ID)
link_id        = hash(zone_id + linked_event_id)
snapshot_id    = hash(zone_id + horizon_seconds)
candle_obs_id  = hash(zone_id + candle_id)
assessment_id  = hash(zone_id + assessed_at + assessment + supersedes)
```

IDへwall clock、file path、browser session IDを入れない。`assessed_at_utc`だけはuser actionの監査時刻であり、市場Replayの決定論的結果へ含めない。

## 29. core pseudocode

```text
for normalized_trade in accepted_source_order:
    release same-millisecond bucket by trade_id

    for active_zone in symbol_session_zones:
        if trade is strictly after zone origin event:
            update_gap_safe_relation(active_zone, trade)
            update_excursions(active_zone, trade)
            update_inside_executed_activity(active_zone, trade)
            finalize_due_horizons_using_last_trade_at_or_before_target(active_zone)

    closed_clusters = aggregator.process(normalized_trade)

    for cluster in closed_clusters:
        event = apply_size_filter(cluster, cluster.settings_snapshot)
        if event is not accepted:
            continue

        zone = create_zone(
            low=event.low_price,
            high=event.high_price,
            anchor=event.vwap,
            source_start=event.last_time,
        )

        links = link_event_to_prior_active_zones(event, tolerance_ticks=1)

        atomic_store(event, all_fills, zone, links)
        add_zone_to_active_observer(zone)
        publish_after_durable_enqueue(event, zone, links)
```

closed candle:

```text
verify UTC minute boundary parity
for active_zone overlapping candle time:
    observation = compare_candle_ohlc_to_zone(candle, zone)
    durable_store(observation)
    publish(observation)
```

session transition:

```text
observe old-session final closed candle
flush ordering bucket
finalize old-session open cluster
finalize due snapshots that have valid source observations
close old-session zones with source-confirmed boundary
store session stats
run eligible scheduled calibration
commit eligible activation
process new-session first trade
```

## 30. fixed vectors

### 30.1 Size Filterとzone生成

```text
BUY  t=0ms  p=100 q=18
BUY  t=25ms p=101 q=17
BUY  t=60ms p=102 q=20
SELL t=70ms p=101 q=5
Manual Min=50 Max=0
```

expected:

```text
BUY aggregate_quantity=55
fill_count=3
duration=60ms
zone_low=100
zone_high=102
zone_source_start=60ms
SELL is separate cluster
```

### 30.2 first exit and return

origin zone:

```text
zone=[100,102], origin_side=BUY, origin_last_time=60ms
```

later trades:

```text
70ms  p=102 → INSIDE
80ms  p=103 → FIRST_EXIT_UP
90ms  p=104 → ABOVE
120ms p=102 → TOUCH_FROM_ABOVE + REENTER_FROM_ABOVE
150ms p=99  → FIRST downward relation after reentry; BELOW
```

first exit remainsUP。後の下落で履歴を書き換えない。

### 30.3 repeated effort link

```text
origin zone=[100,102]
later SELL BigTrade range=[99,100]
tick_size=1
tolerance=1 tick
```

interval gap=0なのでlink。別eventのまま保持し、same parentとは表示しない。

```text
later BUY BigTrade range=[104,105]
```

interval gap=2 ticksなのでlinkしない。

### 30.4 wick versus close

zone `[100,102]`。

```text
candle O=101 H=105 L=100 C=101
```

expected:

```text
UPPER WICK RETURN = true
CLOSE ABOVE = false
```

```text
candle O=101 H=105 L=100 C=104
```

expected:

```text
CLOSE ABOVE = true
UPPER WICK RETURN = false
```

### 30.5 gap crossing horizon

```text
event last_time=10:00:00
horizon=30s
source gap=10:00:20..10:00:40
```

expected:

```text
30s snapshot validity=MISSING_SOURCE_GAP
price interpolation=none
zone status=ACTIVE_WITH_GAP
```

### 30.6 source-confirmed session close

old-session zoneはwall clockがUTC 00:00を越えただけではACTIVEを維持する。新sessionの最初のaccepted trade到着時に、そのtradeを旧zoneへ入れず、旧zoneを`SESSION_CLOSED`にしてから新session処理を開始する。

## 31. invariants

```text
every accepted event has all fills and exactly one origin zone
zone_low == event.low_price
zone_high == event.high_price
zone_source_start == event.last_time
zone_low <= zone_anchor <= zone_high
origin event fills are never counted as post-event result
all zone interactions are strictly after origin event key
touch count increments only on outside-to-inside transition
first exit is immutable
price break never deletes a zone
linked event remains an independent event
zone link never asserts common identity
gap-crossing snapshot is never marked valid
wall clock never finalizes a zone or session
same input and versions produce same facts and IDs
user assessment never changes system observations
Big Trades ERROR never stops existing market pipeline
```

## 32. required UI facts

BIG TRADES chartで最低限、次を同時に確認できること。

```text
marker aggregate quantity
marker side
execution range zone
horizontal extension through later candles
current relation ABOVE / INSIDE / BELOW
first exit direction and time
max above / below excursion
fixed-horizon result values
touch / reentry / cross count
same-zone linked Big Trade count and quantities by side
inside-zone executed BUY / SELL quantities
1m candle close / wick facts
source gap status
settings and calibration IDs
optional user assessment
```

markerとzoneを別画面へ分断しない。同じselected zone detailでeffortとresultを読む。

## 33. required history

再起動後とReplayで次を復元できること。

- origin BigTradeEventと全fills。
- exact zone bounds。
- relation transition全件。
- first exit。
- touch、reentry、cross。
- repeated Big Trade links。
- horizon snapshots。
- candle observations。
- source gap segments。
- session close。
- settings／calibration／activation lineage。
- user assessment history。

## 34. fail-closed

- Size Filter calibration欠損: Automatic event／zone生成停止。
- event storage失敗: zoneを作成・broadcastしない。
- zone atomic storage失敗: eventだけをbroadcastしない。
- invalid tick size: zone relation処理停止。
- candle boundary mismatch: Big TradesだけERROR。
- activation history不整合: historical Big Trades Replay停止。
- source gap: gapを跨ぐresult無効、zoneはgap表示付きで継続。
- WebSocket gap: browserは履歴回復までwarning。
- user assessment保存失敗: assessmentを画面上で成功表示しない。market observationは継続。

Manualへsilent fallbackしない。既存Flow Price Response、CVD、Footprint、Heatmap、Tapeを巻き添え停止しない。

## 35. acceptance criteria

V2完成を名乗るには、次をすべて満たす。

1. V1のManual／Automatic／aggregation／history契約を満たす。
2. accepted event全件にexact execution-range zoneが一件ある。
3. zoneが後続candleへ水平延長表示される。
4. accepted tradeからABOVE／INSIDE／BELOWがsource-timeで再現される。
5. first exit、touch、reentry、crossがfixed vectorどおり。
6. price突破後もzoneが消えず、retestを記録する。
7. 同価格帯の後続Big Tradeが独立eventのままzoneへlinkされる。
8. same identity／parent orderを表示しない。
9. 1m candleのwick returnとclose outsideを区別する。
10. 1s～600s result snapshotがlook-aheadなしで保存される。
11. gapを跨ぐsnapshotを補間しない。
12. Live／Replayのevent、zone、interaction、snapshotが同値。
13. event／fills／zoneがatomicに保存される。
14. 再起動後にzoneとresult historyを復元できる。
15. selected zoneでeffortとresultを同時に読める。
16. user assessmentとsystem factが分離される。
17. Flow Price Responseと3段chartの計算、構造、geometryが不変。
18. Strategy、Hook、MT5、注文接続0。

## 36. Fabio事例へのtraceability

| Fabioの具体事実 | V2出力 |
|---|---|
| 72・61・60・62のeffort | linked Big Trade events、aggregate quantities |
| 上へ継続しなかった | zone relation、max above、horizon snapshots、candle close |
| 反対sellersだけ下方result | SELL linked events、first exit down、max below |
| 105、再攻撃、101 | one origin zone＋later event links＋ordinal |
| 同じlevelを抜けない | repeated touch／reentry、close relation、wick return |
| CVDだけでは不十分 | read-only CVD contextと独立Big Trade／price result |
| Big Tradesがpushしなくなった | directional excursion推移、horizon result、new effort消失を人間が確認 |
| breakout後のretest | zoneをbreakで消さず、return／reentryを記録 |
| control change | opposite linked effortとprice pathを同じzoneで確認 |

この表はFabioの非公開判断式を自動化したという意味ではない。本人が画面で照合した事実を、DeltaEngineで欠落なく並べる対応表である。

## 37. 参照正本

- `FABIO_CONCRETE_LARGE_PARTICIPANT_EVIDENCE_20260810.md`
- `FABIO_LARGE_PARTICIPANT_OBSERVATION_RESEARCH_20260810.md`
- `FABIO_70_VIDEO_LARGE_PARTICIPANT_AUDIT_20260810.md`
- `FABIO_LARGE_PARTICIPANT_QUESTION1_SELECTION_20260811.md`
- `DEEPCHARTS_BIG_TRADES_SIZE_FILTER_RECONSTRUCTION_LOGIC_V1_20260811.md`
- `PROJECT_MEMORY.md`

## 38. 完了状態

本書はV2 logic正本であり、source実装ではない。

実装指示書は本書の全sectionをstorage、runtime、API、WebSocket、UI、test、rollbackへ一対一で落とす。Reaction Zoneを表示線だけで代用し、interaction、result、history、Replayを省略してはならない。
