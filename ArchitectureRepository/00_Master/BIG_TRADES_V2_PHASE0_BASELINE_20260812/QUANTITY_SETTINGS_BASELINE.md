# Big Trades V2 Phase 0 Quantity／Settings Baseline

取得日: 2026-08-12

## Production identity

現行`config/config.yaml`の事実:

```text
exchange = BINANCE
symbol = BTCUSDT
bar timeframe = 1m
price tick size = 0.1
live trade stream = btcusdt@trade
replay = disabled
```

## Binance BTCUSDT metadata

取得元:

```text
GET https://fapi.binance.com/fapi/v1/exchangeInfo?symbol=BTCUSDT
```

取得結果:

| field | value |
|---|---:|
| status | `TRADING` |
| quantity precision | 3 |
| `LOT_SIZE.minQty` | `0.001` BTC |
| `LOT_SIZE.stepSize` | `0.001` BTC |
| `LOT_SIZE.maxQty` | `1000` BTC |
| `MARKET_LOT_SIZE.minQty` | `0.001` BTC |
| `MARKET_LOT_SIZE.stepSize` | `0.001` BTC |
| `MARKET_LOT_SIZE.maxQty` | `120` BTC |
| `PRICE_FILTER.tickSize` | `0.10` USDT |

V2の`quantity_step`は`0.001` BTCで固定できる。

`MARKET_LOT_SIZE.maxQty=120`は単一orderのexchange filterである。V2 clusterは複数executionの合計なので、cluster用Manual Maxへ120を流用しない。

## Existing application filters

### Existing Flow Event Large Trade

```text
flow_detector.large_trade_min_qty = 5.0 BTC
```

これは既存`LargeTradeDetector`がindividual trade一件へ適用する固定Minである。

V2の40ms same-side cluster quantityとは対象が異なる。既存値`5.0`をV2へ入れた場合、同じ検出結果になるとは限らない。

### Existing Time & Sales UI

初期表示値:

```text
MIN QTY = 0
MIN NOTIONAL = 0
LARGE >= 10000 USDT
LARGE ONLY = OFF
```

これはTape表示filterであり、V2 Big Trade eventを生成する設定ではない。

### Existing Big Trades settings

現行config、DB、UIにBig Trades V2専用の次の設定は存在しない。

- `big_trades.enabled`
- `filter_mode`
- `manual_min_quantity`
- `manual_max_quantity`
- `automatic_intensity`
- Big Trades calibration artifact

## Read-only quantity sample

production DuckDBは稼働中writerが保持しているため開いていない。production DB、WAL、Parquetを変更せず、完了済みParquet 1,800 fileからraw trade行だけをread-only集計した。

sample:

```text
first file = part-014881.parquet
last file = part-016680.parquet
first event = 2026-08-11 22:29:08.810 JST
last event = 2026-08-12 01:23:21.406 JST
elapsed = 2.903499 hours
raw trades = 523,986
```

raw individual trade quantity:

| statistic | BTC |
|---|---:|
| minimum | 0.001 |
| p50 | 0.002 |
| p90 | 0.100 |
| p95 | 0.275 |
| p99 | 0.913 |
| p99.5 | 1.300 |
| p99.9 | 2.500 |
| maximum | 64.335 |

## V2 40ms cluster sample

sampleへ次のV2 cluster条件を適用した。

```text
same symbol
same side
previous fillから40ms以内
same UTC minute
```

cluster result:

| statistic | value |
|---|---:|
| cluster count | 72,657 |
| minimum | 0.001 BTC |
| p50 | 0.024 BTC |
| p90 | 0.666 BTC |
| p95 | 1.575 BTC |
| p99 | 6.297 BTC |
| p99.5 | 10.149 BTC |
| p99.9 | 26.486 BTC |
| maximum | 205.471 BTC |
| maximum fills per cluster | 937 |

同sampleの数量上位:

```text
2位 = 173.227 BTC
9位 = 75.086 BTC
20位 = 57.349 BTC
```

これは2.9時間sampleの順位であり、20完了UTC sessionを使うAutomatic calibration値ではない。

## Manual Min scenario

Manual Maxは全scenarioで`0`、すなわち上限なしとする。次は設定候補であり、未承認・未採用である。

| Manual Min | sample accepted clusters | clusters/hour |
|---:|---:|---:|
| 1 BTC | 5,536 | 1,906.665 |
| 2 BTC | 2,954 | 1,017.393 |
| 5 BTC | 1,041 | 358.533 |
| 8 BTC | 525 | 180.816 |
| 10 BTC | 393 | 135.354 |
| 20 BTC | 121 | 41.674 |
| 50 BTC | 26 | 8.955 |

## Candidate set

### Existing detector continuity candidate

```text
Manual Min = 5.000 BTC
Manual Max = 0
```

既存Flow Event thresholdと数値を合わせる候補。ただし既存はindividual trade、V2は40ms clusterなので検出件数は一致しない。sampleでは約358.5 cluster/hour。

### Reduced-density candidate

```text
Manual Min = 20.000 BTC
Manual Max = 0
```

sampleでは約41.7 cluster/hour。

### Sparse candidate

```text
Manual Min = 50.000 BTC
Manual Max = 0
```

sampleでは約9.0 cluster/hour。

## Phase 0 decision state

- quantity step: `0.001 BTC`で確定可能。
- Manual Max: `0`、上限なしを候補とする。
- Manual Min: 5／20／50 BTCを候補として提示する。
- production Manual Min: user未選択。
- Automatic threshold: 未生成。
- feature enable: falseのまま。
- production config変更: 0件。
