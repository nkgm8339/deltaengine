# DeepCharts Big Trades Size Filter 再構成ロジック v1.0

- 作成日: 2026-08-11
- 文書種別: ロジック仕様書
- 対象: Fabioが旧称 `Deep Trades View` と呼んでいた大口約定表示機能
- 現在のDeepCharts上の名称: `Big Trades`
- 実装状態: 未実装。本書はロジックの確立だけを行う

## 0. この文書が定義するもの

本書は、約定データを受け取ってから、短時間に分割された約定を集約し、手動または自動のSize Filterを適用し、表示対象となる大口約定markerを出力するまでの全処理を、一つの決定論的ロジックとして定義する。

対象範囲は次のとおり。

1. 入力約定の正規化
2. 重複排除と時系列整列
3. 同方向の分割約定の集約
4. 集約数量の計算
5. 手動Min／Max Filter
6. 銘柄別Automatic Size Filterの較正
7. ボラティリティ補正
8. Low／Medium／Strongの閾値生成
9. runtimeでの通過判定
10. markerの価格位置、数量、履歴情報の出力
11. 欠損、重複、遅延、session境界等の例外処理
12. 再現性を固定する擬似コードとテストベクトル

次はSize Filterの処理に含めない。

- 大口約定後に価格が上昇・下落したかの判断
- absorption、follow-through、entry、exitの判断
- 発注者名、機関名、口座、parent orderの特定
- DOM上の未約定注文の判定
- Flow Price Responseおよび3段チャートの変更

Size Filterの仕事は、約定済みデータから「表示する規模」を選別するところまでとする。

## 1. 名称の固定

Fabioの過去動画で使われた `Deep Trades View` は、DeepCharts v15.6で `Big Trades` に改名された。旧機能の役割は、約定数量をfilterし、大きなexecuted tradesをbubble／markerで表示することである。

同じv15.6で新しく追加された現在の `Deep Trades` はMBOデータを使用する別機能であり、本書のSize Filter再構成対象ではない。

したがって、本書中の対象名は次で統一する。

```text
Fabio動画上の旧名: Deep Trades View
DeepCharts現行名:   Big Trades
本書の対象:         Big TradesのSize Filter
```

## 2. 根拠の区分

ロジック内の各要素は、次の三種類に分ける。

### 2.1 公式に確認できる仕様

- `Min Filter`は、Big Tradeとして扱う最小数量である。
- `Max Filter`は最大数量であり、`0`は上限無効である。
- `Aggregate Trades`は、短時間に成立した複数約定を一つの取引として集約する。
- markerを集約開始価格または最終約定価格へ置く価格modeがある。
- Automatic Big Trades Analysisは、選択銘柄の過去データを走査する。
- Automaticは銘柄のprice behaviorとvolatilityを使用する。
- Automaticの強度は`Low`、`Medium`、`Strong`である。
- `Low`はmoderateな大口まで広く残し、`Strong`は最大級に限定する。
- 自動分析結果は保存され、weekly／monthlyで再計算できる。

### 2.2 公開再現実装から固定する値

DeepCharts／VolumetricaのTrade Aggregationを再現した公開実装では、次が使用されている。

```text
aggregation_window_ms = 40
```

同実装は、同方向の連続約定を、直前約定から40ms以内である限り同一clusterへ加算し、side変更、40ms超過、chart candle境界でclusterを閉じる。

本書は、非公開のDeepCharts内部値を断定せず、再現可能な基準値として40msを採用する。

### 2.3 本書で決定論化する推論値

DeepChartsのAutomatic Size Filterの内部数式と正確な順位値は公開されていない。このため、公式の挙動と旧Market Statisticsの件数分布例を、次の固定値へ変換する。

```text
履歴期間:             直近20完了session
直近volatility期間:   直近5完了session
Lowの目標表示数:      20件/session
Mediumの目標表示数:   9件/session
Strongの目標表示数:   2件/session
volatility係数下限:   0.75
volatility係数上限:   1.50
```

`9件/session`と`2件/session`は、旧Market Statisticsの公式例で、300 contractsが平均9回／日、450 contractsが平均2回／日だったことに対応する。`20件/session`はLowをMediumより広く残すための固定目標値とする。

## 3. 全体処理

```text
取引所の約定データ
        ↓
入力検証・正規化
        ↓
trade_id重複排除
        ↓
event time順へ整列
        ↓
同方向・短時間の約定をcluster化
        ↓
clusterの合計数量、VWAP、価格範囲を確定
        ↓
手動閾値 または 自動閾値を選択
        ↓
Min以上か判定
        ↓
Maxが有効ならMax以下か判定
        ↓
通過clusterだけmarker／履歴として出力
```

## 4. 入力

### 4.1 約定ごとの必須項目

```text
symbol          銘柄
trade_id        取引所が付与した約定ID
event_time_ms   取引所約定時刻。UTC epoch milliseconds
price           約定価格
quantity        約定数量
side            aggressor side。BUY または SELL
```

### 4.2 銘柄ごとの必須metadata

```text
quantity_step   数量の最小刻み
price_tick      価格の最小刻み
session_id      取引sessionを一意に識別する値
timezone        session境界の判定に使うtimezone
```

### 4.3 使用する数値型

価格、数量、VWAP、閾値、true range、volatility係数はDecimalで扱う。件数、順位、millisecondsだけ整数とする。

## 5. 入力検証と正規化

各tradeを次の順番で処理する。

1. `symbol`が空なら破棄する。
2. `event_time_ms`が整数でなければ破棄する。
3. `price <= 0`なら破棄する。
4. `quantity <= 0`なら破棄する。
5. `side`を`BUY`または`SELL`へ正規化する。
6. aggressor sideを確定できないtradeはSize Filterへ入れない。
7. 数量を`quantity_step`へ丸め直さない。取引所から受信した数量を保持する。
8. `trade_id`が既処理集合に存在する場合は重複として破棄する。

同一時刻のtradeは、次の順序で決定論的に並べる。

```text
第1key: event_time_ms 昇順
第2key: trade_id 数値化できる場合は数値昇順
第3key: trade_id文字列 昇順
```

## 6. 約定集約ロジック

### 6.1 clusterの意味

`execution_cluster`は、短時間に連続した同方向約定を表示上の一件へまとめたものである。parent order、同一人物、同一機関を意味しない。

### 6.2 cluster開始

処理対象銘柄にopen clusterがない場合、現在tradeで新しいclusterを開始する。

cluster開始時に次を保存する。

```text
symbol
side
first_trade_id
first_time_ms
last_time_ms
first_price
last_price
low_price
high_price
total_quantity
weighted_notional
fill_count
session_id
candle_id
```

初期値は次のとおり。

```text
first_time_ms     = trade.event_time_ms
last_time_ms      = trade.event_time_ms
first_price       = trade.price
last_price        = trade.price
low_price         = trade.price
high_price        = trade.price
total_quantity    = trade.quantity
weighted_notional = trade.price × trade.quantity
fill_count        = 1
```

### 6.3 cluster継続条件

次をすべて満たす場合だけ、現在tradeをopen clusterへ加算する。

```text
trade.symbol == cluster.symbol
trade.side == cluster.side
trade.event_time_ms - cluster.last_time_ms <= 40
trade.session_id == cluster.session_id
trade.candle_id == cluster.candle_id
```

時間差はcluster開始時刻からではなく、直前約定時刻から測る。

例:

```text
trade A: 00ms
trade B: 35ms  → Aとの差35msなので同一cluster
trade C: 70ms  → Bとの差35msなので同一cluster
```

この場合、AからCまでは70msあるが、各連続間隔が40ms以内なので同一clusterとなる。

### 6.4 価格条件

同一価格だけに限定しない。短時間の同方向market executionが複数price levelを食う場合も一つのclusterへ含める。

価格の動きは次の項目へ保存する。

```text
first_price
last_price
low_price
high_price
price_level_count
```

### 6.5 cluster加算

継続条件を満たすtradeは次のように加算する。

```text
total_quantity    += trade.quantity
weighted_notional += trade.price × trade.quantity
fill_count        += 1
last_time_ms       = trade.event_time_ms
last_price         = trade.price
low_price          = min(low_price, trade.price)
high_price         = max(high_price, trade.price)
price_set.add(trade.price)
```

### 6.6 cluster終了条件

次のいずれか一つでopen clusterを閉じる。

1. BUYからSELL、またはSELLからBUYへsideが変わった。
2. 直前約定からの時間差が40msを超えた。
3. sessionが変わった。
4. chart candleが変わった。
5. stream終了、切断、銘柄解除が発生した。

clusterを閉じた後、終了原因となった現在tradeは、新しいclusterの最初のtradeとして処理する。stream終了の場合だけ新clusterは作らない。

### 6.7 cluster確定値

cluster終了時に次を計算する。

```text
vwap = weighted_notional / total_quantity
duration_ms = last_time_ms - first_time_ms
price_level_count = count(distinct price)
```

Size Filterに入力する数量は、個々のfill数量ではなく次である。

```text
filter_quantity = total_quantity
```

## 7. Size Filterの入力mode

Big Tradesの入力種類は別々に扱い、同じ閾値cacheを共有しない。

```text
VOLUME
ORDER
ICEBERG
AGGREGATE_TRADES
```

本書で完全に定義する主対象は`AGGREGATE_TRADES`である。

- `AGGREGATE_TRADES`: 第6章で生成したclusterの`total_quantity`を使う。
- `VOLUME`: providerが渡すvolume単位を使う。
- `ORDER`: order-level情報がproviderから得られる場合、そのorder quantityを使う。
- `ICEBERG`: refill検出器が確定した累積executed quantityを使う。

input modeが違えば数量分布も変わるため、自動閾値keyへ必ずinput modeを含める。

## 8. 手動Size Filter

### 8.1 設定

```text
manual_min_quantity
manual_max_quantity
```

### 8.2 判定式

```text
if filter_quantity < manual_min_quantity:
    REJECT

if manual_max_quantity > 0
   and filter_quantity > manual_max_quantity:
    REJECT

otherwise:
    ACCEPT
```

境界値は通過させる。

```text
filter_quantity == manual_min_quantity → ACCEPT
filter_quantity == manual_max_quantity → ACCEPT
```

`manual_max_quantity = 0`は上限なしを意味する。

## 9. Automatic Size Filterの較正単位

自動閾値は次のkeyごとに独立して計算・保存する。

```text
symbol
venue
input_mode
session_template
quantity_unit
intensity
calibration_version
```

次を混ぜない。

- BTCとETH
- futuresとspot
- contractsとbase asset quantity
- 通常sessionと短縮session
- Aggregate TradesとIceberg
- 異なる取引所

## 10. Automatic Size Filter用の履歴生成

### 10.1 対象期間

直近20完了sessionを使用する。進行中sessionは較正母集団へ入れない。

### 10.2 履歴への同一処理適用

履歴tradeにもliveと同じ第5章、第6章の処理を適用する。liveとbackfillで別の集約ロジックを使わない。

各sessionについて、確定clusterの`total_quantity`一覧を作る。

```text
quantities_by_session[session_id] = [q1, q2, q3, ...]
```

無効trade、重複trade、未確定clusterは較正対象へ入れない。

## 11. 基礎閾値の計算

### 11.1 強度ごとの目標件数

```text
LOW:    20件/session
MEDIUM: 9件/session
STRONG: 2件/session
```

### 11.2 sessionごとの順位閾値

各sessionのcluster数量を降順に並べる。

```text
Q_s[1] >= Q_s[2] >= Q_s[3] ...
```

各強度のsession閾値を次で求める。

```text
low_session_threshold    = Q_s[20]
medium_session_threshold = Q_s[9]
strong_session_threshold = Q_s[2]
```

同じ数量が複数ある場合、同値はすべて同じ閾値として扱う。そのため実際の表示件数が目標件数を超えることは許可する。

### 11.3 20sessionの統合

強度ごとに、session閾値の中央値を基礎閾値とする。

```text
base_low    = median(valid low_session_thresholds)
base_medium = median(valid medium_session_thresholds)
base_strong = median(valid strong_session_thresholds)
```

中央値は、極端に多い日または極端に少ない一日だけで閾値が決まることを防ぐ。

### 11.4 session内件数不足

あるsessionのcluster件数が必要順位に届かない場合、そのsessionを当該強度の中央値計算から外す。

```text
LOW:    20件未満なら、そのsessionをLOW計算から除外
MEDIUM: 9件未満なら、そのsessionをMEDIUM計算から除外
STRONG: 2件未満なら、そのsessionをSTRONG計算から除外
```

各強度で有効sessionが10未満の場合、新しい自動閾値を確定しない。その場合は次の順で処理する。

1. 同じkeyの前回確定済み自動閾値があれば、それを維持する。
2. 前回値がなければAutomaticを`INSUFFICIENT_HISTORY`とする。
3. `INSUFFICIENT_HISTORY`時に任意の閾値を自動生成しない。

## 12. ボラティリティ計算

### 12.1 1分足True Range

各1分足について次を計算する。

```text
TR_i = max(
    high_i - low_i,
    abs(high_i - previous_close_i),
    abs(low_i - previous_close_i)
)
```

価格水準が違う銘柄を正規化するため、closeで割る。

```text
NTR_i = TR_i / close_i
```

`close_i <= 0`のbarは除外する。

### 12.2 session volatility

各sessionの1分NTRの中央値を、そのsessionのvolatilityとする。

```text
session_volatility_s = median(NTR values in session s)
```

### 12.3 基準と直近の比較

```text
baseline_volatility = median(last 20 completed session volatilities)
recent_volatility   = median(last 5 completed session volatilities)
```

### 12.4 補正係数

```text
raw_factor = sqrt(recent_volatility / baseline_volatility)
volatility_factor = clamp(raw_factor, 0.75, 1.50)
```

square rootを使い、volatilityが2倍になっただけで数量閾値まで2倍になる過補正を避ける。

次の場合は`volatility_factor = 1.00`とする。

- baselineが0
- baselineまたはrecentが欠損
- 有効な1分足が不足

## 13. 最終自動閾値

### 13.1 補正と丸め

```text
raw_low    = base_low    × volatility_factor
raw_medium = base_medium × volatility_factor
raw_strong = base_strong × volatility_factor
```

各値を`quantity_step`単位で上方向へ丸める。

```text
round_up(value, step) = ceil(value / step) × step
```

```text
auto_low    = round_up(raw_low, quantity_step)
auto_medium = round_up(raw_medium, quantity_step)
auto_strong = round_up(raw_strong, quantity_step)
```

### 13.2 閾値順序の保証

丸め後に同値または逆転した場合、次で修正する。

```text
auto_medium = max(auto_medium, auto_low + quantity_step)
auto_strong = max(auto_strong, auto_medium + quantity_step)
```

最終的に必ず次を満たす。

```text
auto_low < auto_medium < auto_strong
```

### 13.3 自動Max

Automatic Size Filterは最小閾値を決める。自動上限は設けない。

```text
automatic_max_quantity = 0
```

## 14. 自動閾値の更新と保存

自動較正は次のいずれかで実行する。

1. userが明示的にBig Trades Analysisを実行したとき。
2. weekly scheduleの完了時。
3. monthly scheduleの完了時。

進行中sessionの途中で閾値を連続変動させない。較正完了後に一つのversionとして保存し、次の切替点から使用する。

保存項目:

```text
calibration_version
created_at_utc
symbol
venue
input_mode
session_template
history_start_session
history_end_session
valid_session_count_low
valid_session_count_medium
valid_session_count_strong
base_low
base_medium
base_strong
baseline_volatility
recent_volatility
volatility_factor
auto_low
auto_medium
auto_strong
quantity_step
aggregation_window_ms
```

同一versionの値は後から書き換えない。再較正は新versionを作る。

## 15. runtime閾値選択

### 15.1 手動mode

```text
active_min = manual_min_quantity
active_max = manual_max_quantity
threshold_source = MANUAL
```

### 15.2 Automatic mode

```text
if intensity == LOW:
    active_min = auto_low
if intensity == MEDIUM:
    active_min = auto_medium
if intensity == STRONG:
    active_min = auto_strong

active_max = 0
threshold_source = AUTOMATIC
```

### 15.3 modeの優先順位

ManualとAutomaticを同時合成しない。画面で選択された一方だけを使用する。

Automaticが`INSUFFICIENT_HISTORY`で前回値もない場合、勝手にManualへ切り替えない。marker出力を止め、状態を返す。

## 16. runtime通過判定

確定clusterごとに次を実行する。

```text
q = cluster.total_quantity

if q < active_min:
    result = REJECT_BELOW_MIN
else if active_max > 0 and q > active_max:
    result = REJECT_ABOVE_MAX
else:
    result = ACCEPT
```

side表示filterが設定されている場合、Size Filter通過後に適用する。

```text
BUY_ONLY  and cluster.side != BUY  → HIDE_BY_SIDE
SELL_ONLY and cluster.side != SELL → HIDE_BY_SIDE
BOTH                              → 継続
```

sideは規模を決める値ではない。BUY／SELLのどちらを表示するかだけを決める。

## 17. markerの価格位置

価格modeは次の三つを定義する。

```text
START_PRICE → cluster.first_price
LAST_PRICE  → cluster.last_price
VWAP_PRICE  → cluster.vwapをprice_tickへ丸めた値
```

公式機能との対応を優先する既定値は`LAST_PRICE`とする。開始位置を見たい場合は`START_PRICE`へ切り替える。

## 18. markerの出力

Size Filterを通過したclusterだけ、次を出力する。

```json
{
  "event_type": "BIG_TRADE",
  "symbol": "...",
  "side": "BUY|SELL",
  "marker_time_ms": 0,
  "marker_price": "...",
  "aggregate_quantity": "...",
  "fill_count": 0,
  "first_trade_id": "...",
  "first_time_ms": 0,
  "last_time_ms": 0,
  "duration_ms": 0,
  "first_price": "...",
  "last_price": "...",
  "low_price": "...",
  "high_price": "...",
  "vwap": "...",
  "price_level_count": 0,
  "filter_mode": "MANUAL|AUTOMATIC",
  "intensity": "LOW|MEDIUM|STRONG|null",
  "threshold_used": "...",
  "max_threshold_used": "...",
  "input_mode": "AGGREGATE_TRADES",
  "aggregation_window_ms": 40,
  "calibration_version": "..."
}
```

marker labelへ表示する数量は`aggregate_quantity`である。個々の最後のfill数量ではない。

`marker_time_ms`は価格modeに合わせる。

```text
START_PRICE → first_time_ms
LAST_PRICE  → last_time_ms
VWAP_PRICE  → last_time_ms
```

## 19. marker sizeの視覚変換

閾値を超えた数量差をbubble sizeへ反映する場合、面積が数量に対して過大にならないよう平方根を使用する。

```text
ratio = aggregate_quantity / threshold_used
visual_scale = clamp(sqrt(ratio), 1.00, 3.00)
```

これは表示上の大きさだけを決める。ACCEPT／REJECT判定には使用しない。

## 20. 履歴

ACCEPTしたmarkerは、chart表示と同じpayloadを履歴へ保存する。

履歴から次を再現できなければならない。

- どのraw tradesがclusterを構成したか
- 合計数量がいくつだったか
- どのthreshold versionを通過したか
- ManualかAutomaticか
- Low／Medium／Strongのどれだったか
- markerが開始価格、最終価格、VWAPのどこに置かれたか

raw trade ID一覧が大きい場合も、最初と最後だけでなく全構成IDを別配列または別履歴tableへ保存する。

## 21. 例外処理

### 21.1 重複trade

同じ`symbol + trade_id`は一度だけ加算する。再接続後に再送されてもcluster数量へ二重加算しない。

### 21.2 out-of-order trade

確定済みclusterより古いtradeが後着した場合、live表示済みmarkerを黙って変更しない。

```text
late trade → LATE_TRADE履歴へ保存
live cluster → 不変
replay再計算 → event_time順で完全再構成
```

### 21.3 stream切断

切断時点のopen clusterを確定して判定する。再接続後のtradeを切断前clusterへ接続しない。

### 21.4 session境界

前sessionと次sessionのtradeを同じclusterへ入れない。前session末尾clusterを先に確定する。

### 21.5 candle境界

公開再現実装との一致を取るため、chart candleを跨いでclusterを継続しない。同じraw trade列でもchart timeframeを変えると境界付近のclusterが変わり得るため、`candle_timeframe`を履歴へ保存する。

### 21.6 metadata欠損

`quantity_step`がない場合は自動閾値を確定しない。任意の小数桁を数量stepとして代用しない。

### 21.7 閾値変更

open clusterの途中で設定が変わった場合、そのclusterは開始時点のthreshold versionで最後まで判定する。次clusterから新設定を使う。

## 22. 完全擬似コード

```text
CONSTANT AGGREGATION_WINDOW_MS = 40
CONSTANT HISTORY_SESSIONS = 20
CONSTANT RECENT_VOL_SESSIONS = 5
CONSTANT MIN_VALID_SESSIONS = 10
CONSTANT TARGET_LOW = 20
CONSTANT TARGET_MEDIUM = 9
CONSTANT TARGET_STRONG = 2
CONSTANT VOL_FACTOR_MIN = 0.75
CONSTANT VOL_FACTOR_MAX = 1.50

function on_trade(raw_trade):
    trade = normalize_and_validate(raw_trade)
    if trade is INVALID:
        record_invalid(raw_trade)
        return

    if seen(symbol=trade.symbol, trade_id=trade.trade_id):
        return

    mark_seen(trade.symbol, trade.trade_id)

    cluster = open_cluster[trade.symbol]

    if cluster is NONE:
        open_cluster[trade.symbol] = start_cluster(trade, active_settings_snapshot())
        return

    can_join = (
        trade.side == cluster.side
        and trade.event_time_ms - cluster.last_time_ms <= AGGREGATION_WINDOW_MS
        and trade.session_id == cluster.session_id
        and trade.candle_id == cluster.candle_id
    )

    if can_join:
        add_trade(cluster, trade)
        return

    finalize_and_filter(cluster)
    open_cluster[trade.symbol] = start_cluster(trade, active_settings_snapshot())


function finalize_and_filter(cluster):
    cluster.vwap = cluster.weighted_notional / cluster.total_quantity
    cluster.duration_ms = cluster.last_time_ms - cluster.first_time_ms
    cluster.price_level_count = count(cluster.distinct_prices)

    settings = cluster.settings_snapshot

    if settings.mode == MANUAL:
        min_q = settings.manual_min
        max_q = settings.manual_max
        intensity = NONE
        calibration_version = NONE
    else:
        calibration = load_calibration(settings.calibration_key)
        if calibration is NONE:
            record_status(INSUFFICIENT_HISTORY, cluster)
            return
        min_q = calibration.threshold(settings.intensity)
        max_q = 0
        intensity = settings.intensity
        calibration_version = calibration.version

    if cluster.total_quantity < min_q:
        record_rejection(REJECT_BELOW_MIN, cluster, min_q, max_q)
        return

    if max_q > 0 and cluster.total_quantity > max_q:
        record_rejection(REJECT_ABOVE_MAX, cluster, min_q, max_q)
        return

    if not side_filter_accepts(cluster.side, settings.side_filter):
        record_rejection(HIDE_BY_SIDE, cluster, min_q, max_q)
        return

    marker = build_marker(
        cluster,
        settings.price_mode,
        min_q,
        max_q,
        intensity,
        calibration_version
    )
    emit(marker)
    save_history(marker, cluster.trade_ids)


function calibrate(calibration_key, completed_sessions, one_minute_bars):
    sessions = last_n(completed_sessions, HISTORY_SESSIONS)

    for session in sessions:
        trades = load_trades(calibration_key, session)
        clusters = aggregate_with_live_logic(trades)
        quantities[session] = sort_desc([c.total_quantity for c in clusters])

        if count(quantities[session]) >= TARGET_LOW:
            low_values.append(quantities[session][TARGET_LOW - 1])

        if count(quantities[session]) >= TARGET_MEDIUM:
            medium_values.append(quantities[session][TARGET_MEDIUM - 1])

        if count(quantities[session]) >= TARGET_STRONG:
            strong_values.append(quantities[session][TARGET_STRONG - 1])

    if count(low_values) < MIN_VALID_SESSIONS
       or count(medium_values) < MIN_VALID_SESSIONS
       or count(strong_values) < MIN_VALID_SESSIONS:
        return KEEP_PREVIOUS_OR_INSUFFICIENT_HISTORY

    base_low = median(low_values)
    base_medium = median(medium_values)
    base_strong = median(strong_values)

    session_vols = calculate_session_ntr_medians(one_minute_bars, sessions)
    baseline_vol = median(last_n(session_vols, HISTORY_SESSIONS))
    recent_vol = median(last_n(session_vols, RECENT_VOL_SESSIONS))

    if baseline_vol <= 0 or recent_vol is MISSING:
        vol_factor = 1.00
    else:
        vol_factor = clamp(
            sqrt(recent_vol / baseline_vol),
            VOL_FACTOR_MIN,
            VOL_FACTOR_MAX
        )

    low = round_up(base_low * vol_factor, quantity_step)
    medium = round_up(base_medium * vol_factor, quantity_step)
    strong = round_up(base_strong * vol_factor, quantity_step)

    medium = max(medium, low + quantity_step)
    strong = max(strong, medium + quantity_step)

    calibration = immutable_calibration(
        low=low,
        medium=medium,
        strong=strong,
        volatility_factor=vol_factor,
        aggregation_window_ms=AGGREGATION_WINDOW_MS,
        history_sessions=sessions
    )

    save_new_version(calibration)
    return calibration
```

## 23. テストベクトル

### 23.1 同方向40ms以内

入力:

```text
BUY  t=0ms   price=100  qty=18
BUY  t=25ms  price=101  qty=17
BUY  t=60ms  price=102  qty=20
SELL t=70ms  price=101  qty=5
```

結果:

```text
BUY cluster:
  total_quantity = 55
  fill_count = 3
  duration_ms = 60
  first_price = 100
  last_price = 102
  low_price = 100
  high_price = 102
  price_level_count = 3

SELL tradeは別clusterを開始する。
```

`t=60ms`は開始tradeから60ms後だが、直前tradeから35msなのでBUY clusterへ入る。

### 23.2 40ms超過

入力:

```text
BUY t=0ms   qty=30
BUY t=41ms  qty=30
```

結果:

```text
cluster 1 quantity = 30
cluster 2 quantity = 30
```

合計60として扱わない。

### 23.3 手動Min／Max

```text
cluster quantity = 55
Min = 50
Max = 0
結果 = ACCEPT
```

```text
cluster quantity = 55
Min = 20
Max = 50
結果 = REJECT_ABOVE_MAX
```

```text
cluster quantity = 50
Min = 50
Max = 50
結果 = ACCEPT
```

### 23.4 side変更

```text
BUY  t=0ms  qty=20
SELL t=10ms qty=20
```

時間差が40ms以内でも、二つのclusterに分ける。

### 23.5 重複

```text
trade_id=1001 BUY qty=25
trade_id=1001 BUY qty=25 再送
```

結果:

```text
total_quantity = 25
```

50にはしない。

### 23.6 自動閾値の順序

丸め前:

```text
raw_low = 40.01
raw_medium = 40.02
raw_strong = 40.03
quantity_step = 1
```

通常丸め後は全て41になるため、順序保証を適用する。

```text
auto_low = 41
auto_medium = 42
auto_strong = 43
```

## 24. 不変条件

同じ入力trade列、同じmetadata、同じchart timeframe、同じ設定versionを与えた場合、liveとreplayで次が完全一致しなければならない。

- cluster境界
- cluster合計数量
- VWAP
- ACCEPT／REJECT
- marker時刻
- marker価格
- 使用閾値
- calibration version
- 履歴payload

次も常に成立しなければならない。

```text
total_quantity > 0
fill_count >= 1
first_time_ms <= last_time_ms
low_price <= high_price
manual_max == 0 or manual_min <= manual_max
auto_low < auto_medium < auto_strong
volatility_factor >= 0.75
volatility_factor <= 1.50
```

## 25. Fabioの使用事実との対応

Fabioは旧Deep Trades Viewについて、executed ordersをfilterし、big market participantsだけを見るための表示だと説明している。

画面に残った具体例には次がある。

```text
72 contracts
61 contracts
60 contracts
62 contracts
105 contracts
101 contracts
```

これらの数字は、Size Filter通過後に表示された具体的な約定数量である。全銘柄共通の固定閾値ではない。

Fabioはvolumeが多い日は、より大きいfilterが必要だとも説明している。本書では、この銘柄・市場状態による閾値変動を、session別数量分布とvolatility factorで決定論化した。

## 26. 公開事実と再構成値の最終境界

### 公開事実

- Min／Max Filterがある。
- Maxの0は無効である。
- 複数tradeをAggregate Tradesとしてまとめる。
- 自動分析は過去chartを走査する。
- 銘柄のprice behaviorとvolatilityを使用する。
- Low／Medium／Strongを選べる。
- 自動結果を保存し、weekly／monthlyで更新できる。

### 公開再現実装から採用した値

- 連続約定の集約窓: 40ms
- 同方向、直前fillとの時間差、candle境界によるcluster確定

### 本書が再現用に固定した推論値

- 20完了session
- 直近5session volatility
- 20／9／2件 per session
- 1分Normalized True Rangeのsession中央値
- `sqrt(recent / baseline)`による補正
- 0.75～1.50のclamp
- 各session順位値を20session間でmedian統合

この区分により、DeepCharts非公開コードの値と、本書の再現ロジックの値を混同しない。

## 27. 参照資料

- DeepCharts v15.6 release note — 旧Deep Trades ViewのBig Tradesへの改名、新Deep Tradesの追加  
  https://www.deepcharts.com/changelog/v15.6
- DeepCharts Big Trades manual — Min／Max、Automatic、Low／Medium／Strong、volatility  
  https://www.deepcharts.com/helpcenter/article/big-trades
- DeepCharts input types — Volume／Order／Iceberg／Aggregate Trades  
  https://www.deepcharts.com/helpcenter/article/different-types-of-input
- Volumetrica Big Trades — Aggregate Trades、Min／Maxの旧公式説明  
  https://help.volumetricatrading.com/en/support/solutions/articles/204000013600-big-trades
- Volumetrica Market Statistics — 過去分布、300 contracts平均9回／日、450 contracts平均2回／日の例  
  https://help.volumetricatrading.com/en/support/solutions/articles/204000011921-market-statistics
- DeepCharts developer update — 自動分析、intensity、開始／最終価格mode  
  https://www.youtube.com/watch?v=_RaMVm82tHE
- Fabio — executed ordersをfilterしてbig market participantsだけを見る説明と72／61／60／62、105／101の例  
  https://www.youtube.com/watch?v=Pz8f0wWW12M&t=2251s
- Fabio — volumeが多い日はより大きいfilterが必要という説明  
  https://www.youtube.com/watch?v=jasv3L-d8ZE&t=73s
- 公開再現実装 Kairos — Big Tradesの40ms aggregation  
  https://gitlab.com/kreotic/kairos

## 28. 本書の完了状態

本書で、Big Trades Size Filterの入力からmarker出力までの再構成ロジックを固定した。

コード実装、設定変更、既存機能変更は行っていない。
