# Footprint × LIVE DOM × Time & Sales Phase 0C Storage Sizing Report

作成日: 2026-07-28

対象: DeltaEngine05M / BTCUSDT / 1m / tick size 0.1

基準設計: `FOOTPRINT_DOM_TIME_SALES_FUSION_PREIMPLEMENTATION_AMENDMENT_V2_1_20260728.md`

実行branch: `feature/footprint-dom-tape`

実行時HEAD: `92ee4eff823ba31e84f7fc0af197d39b877ec236`

## 1. 結論

Phase 0Cの判定は **PASS WITH LIMITATION** とする。

推奨案:

1. Footprint価格レベルは **A. normalized row table** を採用する。
2. `footprint_levels`本体には、初期段階で4列ART／unique indexを作らない。
3. 小さいbar manifestを別tableに持ち、bar単位のtransactionで論理一意性と
   再処理時の冪等性を保証する。
4. Hot DuckDBは直近30日を目標値とする。
5. Archive ParquetはUTC日次、ZSTD、期間制限なしを推奨する。
6. Phase 1ではautomatic purgeを有効化しない。
7. raw trades、candles、Flow、Hook journalのretentionは変更しない。
8. BackgroundStorageWriterへは価格レベルを1行ずつ積まず、
   confirmed `FootprintBar`を1 commandとして積み、worker側でnormalized rowsへ展開する。

normalized方式を推奨する主な理由:

- latest 40 barsの実測がnested方式より約2倍速い。
- latest／previous 40のJSON相当payloadもnested方式より小さい。
- normalized ZSTD Parquetはnested Parquetより小さい。
- price level検索、history API成形、再計算、検証が単純。
- 4列indexを外せば、nestedとのDuckDB容量差は小さい。
- nested方式のincremental writeは今回の比較で大幅に遅かった。

4列unique indexを初期採用しない主な理由:

- sample DuckDBが7.88 MBから40.64 MBへ増え、約5.16倍になった。
- latest／previous 40のrange query planではindexが使われなかった。
- warm query latencyは改善しなかった。
- 1,000 levelsのwrite medianは7.78 msから10.96 msへ増えた。
- 論理一意性は、bar manifestの小さいprimary key、入力bar内のprice重複検証、
  single writer transactionで維持できる。

## 2. 承認範囲と非変更事項

ユーザーのPhase 0C「GO」に基づき、read-only source inventoryと隔離benchmarkを行った。

productionに対して行っていないこと:

- production DuckDB／Parquetへの書込み
- schema変更
- raw／derived data削除
- archive／purge job有効化
- retention日数の本決定
- Phase 1 source実装
- completed Flow Price Response変更
- completed 3段チャート変更
- git commit／push
- BAT／Docker／600秒retention差分の変更

## 3. Sourceと測定方法

### 3.1 Production設定

```text
symbol: BTCUSDT
timeframe: 1m
tick_size: 0.1
timezone: UTC
database.batch_size: 1000
database.flush_interval_sec: 5
queue.default_depth: 10000
```

production DuckDBは稼働中processがfile lockを保持しており、別processからの
read-only openは失敗した。このため、稼働processを停止せず、production Parquetを
read-only sourceとして固定snapshotを隔離作成した。

固定snapshot:

```text
trades: 4,212,954
distinct trade_id: 4,212,954
first event UTC: 2026-07-23 18:23:42.595
last event UTC:  2026-07-28 08:17:33.939
invalid price/quantity: 0
invalid side: 0
```

source Parquetはmaterialization時点で40,398 files、約142.99 MBだった。
非常に小さいfileが多数あるため、Footprint archiveでは同じfile増加パターンを
繰り返さないことを設計条件とする。

### 3.2 Footprint集計

bar key:

```text
(date_trunc('minute', event_time), symbol, '1m')
```

level key:

```text
(bar_time, symbol, timeframe, raw normalized price)
```

volume:

```text
aggressive buy  = side BUY
aggressive sell = side SELL
```

display用price bucketは使用していない。すべてraw normalized priceで測定した。

### 3.3 比較したstorage shape

A. normalized:

```text
1 price level = 1 row
```

B. nested:

```text
1 bar = 1 row
levels = ordered LIST<STRUCT>
```

benchmark用normalized tableには比較と整合性確認のため、
`total_volume`、`delta`、`trade_count`も保存した。Phase 1最低schemaは
`buy_volume`／`sell_volume`中心でよいため、本報告の容量値は保守的な上限寄りである。

## 4. Sample品質

### 4.1 Coverage

```text
wall-clock span: 約109.9時間
active 1-minute bars: 3,634
active time換算: 約60.57時間
wall-clock minute coverage: 55.10%
完全な1時間区間: 48
最長連続区間: 502分
```

24時間を超えるactive barsと低／高volatilityの双方を含むが、
連続24時間のclean captureは存在しなかった。このため判定を
PASSではなくPASS WITH LIMITATIONとする。

この制約はPhase 1 source実装を妨げるものではないが、
automatic purgeを検討する前に、Phase 1 live instrumentationで
少なくとも連続7日を再観測する。

### 4.2 低／高volatility

完全な1時間区間の代表値:

| regime | UTC hour | trades | hour range | levels/bar median | p95 | max |
|---|---:|---:|---:|---:|---:|---:|
| low | 2026-07-26 11:00 | 17,433 | 37.2 | 7 | 72.15 | 100 |
| high | 2026-07-27 16:00 | 145,422 | 462.7 | 308 | 723.05 | 1,341 |

volatilityによってlevel数が大きく変わる。平均値だけでqueue、payload、
storageを決めてはならない。

## 5. Price levels分布

| metric | value |
|---|---:|
| bars | 3,634 |
| level rows | 599,563 |
| minimum levels/bar | 2 |
| median | 124 |
| p95 | 467 |
| p99 | 758.02 |
| maximum | 2,592 |
| average | 164.99 |

trade分布:

| metric | trades/bar |
|---|---:|
| minimum | 5 |
| median | 828 |
| p95 | 3,279.75 |
| p99 | 6,116.71 |
| maximum | 17,072 |

価格range:

| metric | USD/bar |
|---|---:|
| average | 20.24 |
| p95 | 55.90 |
| maximum | 300.80 |

1,440 active bars/dayへ正規化したlevel row推計:

```text
1日:      237,581 rows
30日:   7,127,441 rows
365日: 86,717,202 rows
```

V2.1の50〜200 levels/bar概算に対し、median 124とaverage 164.99は範囲内だが、
p95 467、p99 758、maximum 2,592という太い裾が確認された。

## 6. Storage容量

### 6.1 実測file

| shape | sample bytes | unit bytes | 1日推計 | 30日推計 | 365日推計 |
|---|---:|---:|---:|---:|---:|
| normalized DuckDB / no index | 7,876,608 | 13.14 / level | 3.12 MB | 93.63 MB | 1.139 GB |
| normalized DuckDB / 4-col unique | 40,644,608 | 67.79 / level | 16.11 MB | 483.17 MB | 5.879 GB |
| nested DuckDB / bar key | 7,090,176 | 1,951.07 / bar | 2.81 MB | 84.29 MB | 1.025 GB |
| normalized ZSTD Parquet | 4,067,060 | 6.78 / level | 1.61 MB | 48.35 MB | 588.24 MB |
| nested ZSTD Parquet | 4,773,286 | 1,313.51 / bar | 1.89 MB | 56.74 MB | 690.38 MB |

単位はdecimal MB／GB。対象はBTCUSDT 1m、1 symbolである。
symbolまたは別timeframeを増やす場合は、概ね保存対象level数に比例する。

### 6.2 容量判断

- normalized no-indexとnestedのHot DuckDB差は30日で約9.35 MBに留まる。
- normalized Parquetはnested Parquetより約14.8%小さい。
- 4列unique indexの容量増加が最大の要因で、table shape差より大きい。
- 30日Hot DuckDBは十分小さい。
- automatic purgeを急いで導入する容量上の理由はない。
- UTC hour partitionでは1 fileあたりが小さすぎる。UTC date partitionを採用する。

## 7. Query latency

各warm値は50回のfetch完了までを測定した。

### 7.1 latest／previous 40 full levels

| shape | query | logical levels | median | p95 | JSON相当bytes |
|---|---|---:|---:|---:|---:|
| normalized no index | latest 40 | 4,975 | 16.38 ms | 21.26 ms | 387,674 |
| normalized no index | previous 40 | 5,660 | 18.64 ms | 31.47 ms | 442,026 |
| normalized 4-col unique | latest 40 | 4,975 | 16.40 ms | 24.34 ms | 387,674 |
| normalized 4-col unique | previous 40 | 5,660 | 19.24 ms | 25.97 ms | 442,026 |
| nested bar key | latest 40 | 4,975 | 31.11 ms | 42.13 ms | 531,676 |
| nested bar key | previous 40 | 5,660 | 32.18 ms | 41.18 ms | 605,218 |

4列unique indexはこれらrange queryのplanで使われず、
no-indexのappend order／zone mapに対して有意な改善を示さなかった。

exact one-level lookupのmedian:

```text
no index: 1.462 ms
indexed:  1.204 ms
```

差は小さく、今回のEXPLAINではexact lookupにもindex scan表示はなかった。
unique constraint自体はduplicate keyを正しく拒否し、row count不変を確認した。

### 7.2 Latest 300 bar summaries

| shape | returned bars | median | p95 | JSON相当bytes |
|---|---:|---:|---:|---:|
| normalized no index / GROUP BY | 300 | 5.91 ms | 7.62 ms | 30,633 |
| normalized 4-col unique / GROUP BY | 300 | 5.94 ms | 8.20 ms | 30,633 |
| nested top-level summary | 300 | 1.91 ms | 2.74 ms | 30,633 |

nestedはbar summaryに強い。一方、UIの主要求である40本のfull levelsはnormalizedが速い。
必要なら既存candle dataまたは小さいbar manifestから300本summaryを返せるため、
この利点だけでlevels本体をnestedにする必要はない。

## 8. Write batch latency

隔離DuckDBへ全sampleをincremental insertした。

| shape | batch | batches | median | p95 | p99 | throughput |
|---|---:|---:|---:|---:|---:|---:|
| normalized no index | 1,000 levels | 600 | 7.78 ms | 16.79 ms | 82.84 ms | 82,764 levels/s |
| normalized 4-col unique | 1,000 levels | 600 | 10.96 ms | 16.56 ms | 23.99 ms | 78,469 levels/s |
| nested bar key | 10 bars | 364 | 116.41 ms | 402.56 ms | 691.29 ms | 64.5 bars/s |

nested 10 barsは平均約1,650 logical levelsに相当するため、
normalized 1,000 rowsと完全な同量比較ではない。ただし、bar close単位の
incremental workloadではnested list／structのwrite amplificationが大きかった。

この測定はDuckDB engineへのlocal `INSERT SELECT`であり、
network、history API、production Python object生成を含まない。
Phase 1ではPyArrow変換、Parquet archive、queue待ちを分けたtimerを追加する。

## 9. Background queue

2026-07-28 Phase 0C観測時のproduction read-only API:

```text
trades_processed: 1,041,106
storage_queue_pending: 0
storage_queue_high_watermark: 798
configured capacity: 10,000
```

Footprint未実装のため、Footprint追加後の実測high watermarkではない。

保守的に1 barの全levelを個別commandとして積むと、sample maximumは2,592 commandである。
現行high watermark 798との単純合算3,390はcapacityの33.9%だが、
同時burstを保証する計算ではない。

Phase 1推奨:

- queue commandは1 confirmed `FootprintBar` = 1 item。
- worker thread内でnormalized rowsへ展開する。
- queue depth 10,000を初期維持する。
- `footprint_bars_enqueued`
- `footprint_bars_written`
- `footprint_levels_written`
- `footprint_duplicates_skipped`
- `footprint_write_failures`
- `storage_queue_pending`
- `storage_queue_high_watermark`
- Footprint flush median／p95／p99
- 70% warning、90% criticalを観測条件とする。
- overflowまたはwrite失敗をsilent lossにしない。

## 10. Archive verification

normalized ZSTD Parquet:

```text
source logical rows: 599,563
archive rows:        599,563
logical keys:        599,563
source trades represented: 4,212,954
symbol: BTCUSDT
timeframe: 1m
min bar_time: 2026-07-23 18:23:00 UTC
max bar_time: 2026-07-28 08:17:00 UTC
min price: 63,050.8
max price: 65,700.2
summed aggressive sell: 100,580.762
summed aggressive buy:  103,689.808
file bytes: 4,067,060
SHA-256: 842277ebc13e67003effb7c0f03c00825b6befdd1900335ac55ca8d9a0ebc0b3
read-back: PASS
```

nested比較artifact:

```text
bars: 3,634
levels: 599,563
source trades represented: 4,212,954
file bytes: 4,773,286
SHA-256: e7ae356ef1daa2ea8e9fd0361fb5d26e719125ad6052a1a7b339ede2b9170fec
read-back: PASS
```

floating sumの末尾にはDOUBLE集計順序による微小差がある。
production schemaは既存規約に合わせて`DECIMAL(20,8)`を使い、
archive verificationもDecimalで一致判定する。

## 11. Phase 1 schema提案

### 11.1 `footprint_bar_manifest`

小さいbar単位table:

| column | type | purpose |
|---|---|---|
| bar_time | TIMESTAMP | UTC bar start |
| symbol | VARCHAR | instrument |
| timeframe | VARCHAR | `1m` |
| level_count | INTEGER | validation／summary |
| buy_volume | DECIMAL(20,8) | bar total |
| sell_volume | DECIMAL(20,8) | bar total |
| content_hash | VARCHAR | deterministic bar content check |

physical primary key:

```text
(bar_time, symbol, timeframe)
```

### 11.2 `footprint_levels`

normalized level table:

| column | type | purpose |
|---|---|---|
| bar_time | TIMESTAMP | UTC bar start |
| symbol | VARCHAR | instrument |
| timeframe | VARCHAR | bar timeframe |
| price | DECIMAL(20,8) | raw normalized price |
| buy_volume | DECIMAL(20,8) | aggressive buy |
| sell_volume | DECIMAL(20,8) | aggressive sell |

logical unique key:

```text
(bar_time, symbol, timeframe, price)
```

初期physical index:

```text
none
```

`delta`は`buy_volume - sell_volume`、`total_volume`は両者の和で再計算できるため、
最低schemaでは重複保存しない。

### 11.3 Atomic idempotency

confirmed bar受領時:

1. UTC、symbol、timeframe、price、volumeを検証する。
2. bar内priceの重複を拒否する。
3. transactionを開始する。
4. manifestを`ON CONFLICT DO NOTHING`でinsertする。
5. manifestが新規の場合だけ全level rowsをinsertする。
6. 全件成功時だけcommitする。
7. manifest conflictはbar全体のduplicateとしてcount／logし、二重加算しない。
8. 部分失敗はrollbackし、manifestだけ、levelsだけの状態を作らない。

これにより4列ARTを持たずに論理一意性を維持する。

## 12. Retention／Archive提案

GO-5承認済み:

| data | proposal |
|---|---|
| Hot DuckDB Footprint | 直近30日 |
| Archive Parquet | 期間制限なし |
| Partition | symbol/timeframe/UTC year/month/day |
| Compression | ZSTD |
| Archive unit | sealed UTC day |
| Raw trades | 現行方針を変更しない |
| Automatic purge | Phase 1ではOFF |

sealed UTC dayを推奨する理由:

- normalized Parquetの推計は約1.61 MB/dayで、hour partitionには小さすぎる。
- source側では40,398 small filesが既に存在し、scan overheadが観測された。
- Hot DuckDBが当日durabilityと履歴queryを担当できる。
- 翌UTC日に前日分を1 archive unitへまとめ、検証後にarchive completeとできる。

将来Hot rowsを外す場合の必須gate:

1. source／archive row count一致
2. logical key count一致
3. symbol／timeframe一致
4. min／max bar_time一致
5. min／max price一致
6. summed buy／sell volume一致
7. file SHA-256記録
8. fresh process read-back PASS
9. archive manifest durable commit
10. ユーザーによるpurge明示承認

不一致時はHot rowsを維持する。

## 13. Phase 1 acceptance追加案

- latest 40 full levels warm p95 < 50 ms
- previous 40 full levels warm p95 < 50 ms
- 300 bar summary warm p95 < 20 ms
- confirmed bar duplicate replayでrow count不変
- partial transaction failureでmanifest／levels双方rollback
- maximum 2,592-level fixtureを保存／reload可能
- p99 759-level fixtureを連続投入してqueue overflow 0
- queue pending 0へ回復
- UTC日次archive verification PASS
- production schemaはDecimalでvolume identity一致
- restart後に40 bars hydrate
- raw data、completed Flow Price Response、3段チャートへ回帰なし

## 14. 限定blocker

1. production DuckDB固有metadataは稼働process lockにより直接確認できなかった。
   storage shape判断は固定Parquet snapshotと隔離DuckDBで完了している。
2. 連続24時間captureはなく、最長502分だった。
   ただし60.57 active hours、48 complete hours、低／高volatilityを含む。
3. Footprint追加後のqueue high watermarkはPhase 1実装前のため未計測。
   現行baseline 798／10,000を取得済みで、Phase 1 counter追加案を定義した。

blockerはいずれもPhase 1 storage実装そのものではなく、
automatic purge有効化と長期capacity確定に限定する。

## 15. GO-5承認結果と次の境界

2026-07-28、ユーザーの「GO」により次をGO-5として承認済みとする。

1. normalized levels + bar manifest
2. 4列level ARTを初期作成しない
3. Hot DuckDB 30日
4. UTC日次ZSTD Parquetを無期限保持
5. Phase 1 automatic purge OFF

GO-5はschema／retention decisionの承認であり、source変更を含まない。

次はGO-6としてPhase 1 source implementationを別途承認する。
