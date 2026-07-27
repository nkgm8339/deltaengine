# Book Event History / Time / Reset Contract V0.1

作成日: 2026-07-27 JST  
状態: **お館様のA→D→E順次解決指示に基づくP3-C D契約**

## 1. 目的

同期済みlocal order bookへ実際に適用されたdepth updateから、G07 Book Event Flowの
100ms／1s／5s値をsource-timeで再現可能に生成する。point-in-time wall値をwall崩壊へ
読み替えない。

## 2. Authoritative input

- `OrderBookUpdate`、`ApplyResult`、適用後`OrderBookSnapshot`を一組として使う。
- `ApplyResult.applied == true`のupdateだけをevent-flowへ加える。
- source timestampは`OrderBookUpdate.event_time`のUTC epoch nanoseconds。
- `OrderBookSnapshot.last_update_id`はlineage確認に使い、event時刻の代用にしない。
- Market-by-Price diffから注文者、cancel意図、market consumption identityを断定しない。
  本契約の`cancel_volume`は表示数量の減少量である。

## 3. Update単位の材料

各DIFFについて、update前後の同一price level数量を比較する。

```text
quantity_delta = new_quantity - previous_quantity
add_volume      = sum(max(quantity_delta, 0))
cancel_volume   = sum(max(-quantity_delta, 0))
net_flow        = add_volume - cancel_volume
```

- bid／askを独立集計する。
- `refresh_count`: update前またはupdate後のbest側top3に含まれるpriceで数量が増えたlevel数。
- changed priceはupdate payloadに現れ、実際に数量が変化したlevelだけ。

## 4. Window集計

G07正本どおり100ms／1s／5sを生成する。windowは`(now - window, now]`。

- add／cancel／net／refresh: window内eventの合計。
- pull ratio: `cancel / (add + cancel)`。分母0はomit。
- stack ratio: `add / (add + cancel)`。分母0はomit。
- level turnover: window内で数量が変化したunique price level数を、baselineとcurrentの
  top10 unique level和集合数で割る。分母0はomit。
- depth change: current top10 cumulative depth minus window開始時as-of top10 cumulative depth。
- baseline stateがwindow開始以前に存在し、current stateがwindow内に存在する場合だけ
  そのwindowを出力する。0埋めでwindow完成を偽装しない。

## 5. Reset / resync

次の場合、book event履歴、baseline、最新snapshotを即時破棄する。

- `ApplyResult.gap_detected == true`
- SNAPSHOT適用
- `ApplyResult.reinitialized == true`
- symbol不一致は例外拒否

resync snapshotがProducerへ直接通知されない経路では、resync後最初のapplied DIFFを
新baselineとして扱う。新baselineから各windowが完成するまでG07 keyをomitする。
reconnect前後のeventを同一windowへ混ぜない。

## 6. Retention / future leakage

- 最大5秒のeventと、5秒境界直前のstate 1件を保持する。
- snapshot評価時刻より未来のstate／eventは条件へ含めない。
- source時刻逆転update、stale／未適用updateは集計しない。
- G01のdepth freshness／sync／contiguous quality gateはG07値と独立して維持する。

## 7. 非対象

wall認定語義はEで別途解決する。G16 composite、threshold、runtime有効化、発注権限、
raw data、完成済みFlow Price Response／3段チャート／8パターン／OI／UIは変更しない。
