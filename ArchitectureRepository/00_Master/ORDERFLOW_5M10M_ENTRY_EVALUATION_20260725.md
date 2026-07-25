# 5M/10M Episode Entry Spec v1 オフライン評価

生成時刻: 2026-07-25 07:15:14.969410+00:00
判定: **EXPLORATORY_INSUFFICIENT_DATA**

## 評価境界

- 既存1M Flow Price Responseと3段チャートは変更していない
- LIVE／MT5注文は生成していない
- 60秒観測と300秒観測を、300秒／600秒outcomeから分離した
- proxy costは過去実測spread 20 USDと1.5倍stress 30 USDを一回だけ控除した
- HFM同一時計quote bytes: 0

## 現在の運用判定

- Entry Spec v1: **NO_GO_FOR_HFM_ENTRY_V1**
- 30 USD proxy: **NO_POSITIVE_MEDIAN_AT_30_USD**
- 意味: 現在の結果からMT5／LIVE発注へ進まない。理論全体の統計的棄却ではない。

## データ

- Flow observations: 2275
- RAW trades: 776768
- RAW期間: 2026-07-23 18:23:42.595000+00:00 ～ 2026-07-25 06:50:28.248000+00:00
- entry cutoff: 2026-07-25 06:40:00+00:00
- outcome price cutoff: 2026-07-25 06:50:30+00:00
- 観測日数: 1.5186
- RAW files rejected: 0
- non-trade schema files ignored: 995
- duplicate trade IDs excluded: 0
- nonpositive prices excluded: 0

## 非重複候補の全体結果

| cost USD | obs | entry | horizon | OK | median gross bps | median net bps | invalidation-or-horizon net | median MFE | median MAE | favorable first | adverse first |
|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 20 | 60 | ATTACK_V1 | 300 | 58 | 0.266 | -2.856 | -2.856 | 2.651 | -2.931 | 0.397 | 0.414 |
| 20 | 60 | ATTACK_V1 | 600 | 57 | 0.031 | -3.039 | -3.039 | 4.696 | -4.585 | 0.474 | 0.491 |
| 20 | 60 | PERSIST_PRESSURE_V1 | 300 | 28 | 0.187 | -2.935 | -3.135 | 2.373 | -2.353 | 0.321 | 0.357 |
| 20 | 60 | PERSIST_PRESSURE_V1 | 600 | 26 | -0.776 | -3.871 | -3.135 | 3.570 | -3.443 | 0.462 | 0.346 |
| 20 | 60 | RESOLUTION_CONFIRMED_V1 | 300 | 18 | -0.990 | -4.109 | -5.077 | 2.182 | -2.548 | 0.333 | 0.278 |
| 20 | 60 | RESOLUTION_CONFIRMED_V1 | 600 | 18 | -0.749 | -3.847 | -5.290 | 2.946 | -6.077 | 0.389 | 0.333 |
| 20 | 300 | ATTACK_V1 | 300 | 52 | 0.582 | -2.521 | -2.521 | 2.493 | -2.696 | 0.423 | 0.346 |
| 20 | 300 | ATTACK_V1 | 600 | 50 | 0.031 | -3.094 | -3.094 | 3.535 | -3.964 | 0.460 | 0.400 |
| 20 | 300 | PERSIST_PRESSURE_V1 | 300 | 3 | 1.606 | -1.513 | -3.100 | 5.341 | -0.421 | 1.000 | 0.000 |
| 20 | 300 | PERSIST_PRESSURE_V1 | 600 | 3 | 2.655 | -0.414 | -3.100 | 6.262 | -0.421 | 1.000 | 0.000 |
| 20 | 300 | RESOLUTION_CONFIRMED_V1 | 300 | 2 | -0.716 | -3.810 | -3.777 | 3.897 | -1.983 | 1.000 | 0.000 |
| 20 | 300 | RESOLUTION_CONFIRMED_V1 | 600 | 2 | 2.289 | -0.805 | -3.777 | 4.358 | -1.983 | 1.000 | 0.000 |
| 30 | 60 | ATTACK_V1 | 300 | 58 | 0.266 | -4.417 | -4.417 | 2.651 | -2.931 | 0.328 | 0.276 |
| 30 | 60 | ATTACK_V1 | 600 | 57 | 0.031 | -4.574 | -4.574 | 4.696 | -4.585 | 0.456 | 0.404 |
| 30 | 60 | PERSIST_PRESSURE_V1 | 300 | 28 | 0.187 | -4.497 | -4.694 | 2.373 | -2.353 | 0.286 | 0.179 |
| 30 | 60 | PERSIST_PRESSURE_V1 | 600 | 26 | -0.776 | -5.418 | -4.694 | 3.570 | -3.443 | 0.346 | 0.308 |
| 30 | 60 | RESOLUTION_CONFIRMED_V1 | 300 | 18 | -0.990 | -5.668 | -6.623 | 2.182 | -2.548 | 0.222 | 0.278 |
| 30 | 60 | RESOLUTION_CONFIRMED_V1 | 600 | 18 | -0.749 | -5.397 | -6.834 | 2.946 | -6.077 | 0.278 | 0.444 |
| 30 | 300 | ATTACK_V1 | 300 | 52 | 0.582 | -4.072 | -4.072 | 2.493 | -2.696 | 0.288 | 0.231 |
| 30 | 300 | ATTACK_V1 | 600 | 50 | 0.031 | -4.656 | -4.656 | 3.535 | -3.964 | 0.320 | 0.380 |
| 30 | 300 | PERSIST_PRESSURE_V1 | 300 | 3 | 1.606 | -3.072 | -4.635 | 5.341 | -0.421 | 0.667 | 0.000 |
| 30 | 300 | PERSIST_PRESSURE_V1 | 600 | 3 | 2.655 | -1.949 | -4.635 | 6.262 | -0.421 | 0.667 | 0.000 |
| 30 | 300 | RESOLUTION_CONFIRMED_V1 | 300 | 2 | -0.716 | -5.357 | -5.324 | 3.897 | -1.983 | 0.000 | 0.000 |
| 30 | 300 | RESOLUTION_CONFIRMED_V1 | 600 | 2 | 2.289 | -2.352 | -5.324 | 4.358 | -1.983 | 0.500 | 0.000 |

## 主候補の解放種別・売買方向別stress結果

30 USD costの主候補を、突破と反転、BUYとSELLへ分離する。

| obs | horizon | resolution | side | OK | median gross bps | median net bps | invalidation-or-horizon net | favorable first | adverse first | invalidation first |
|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| 60 | 300 | AGGRESSOR_BREAKTHROUGH | BUY | 7 | -0.491 | -5.098 | -5.098 | 0.143 | 0.571 | 0.571 |
| 60 | 300 | AGGRESSOR_BREAKTHROUGH | SELL | 7 | -1.887 | -6.566 | -6.863 | 0.286 | 0.143 | 0.429 |
| 60 | 300 | DEFENDER_REVERSAL | BUY | 2 | -0.990 | -5.668 | -6.541 | 0.000 | 0.000 | 1.000 |
| 60 | 300 | DEFENDER_REVERSAL | SELL | 2 | 2.596 | -2.022 | -5.532 | 0.500 | 0.000 | 0.500 |
| 60 | 600 | AGGRESSOR_BREAKTHROUGH | BUY | 7 | -6.960 | -11.631 | -6.812 | 0.286 | 0.714 | 0.714 |
| 60 | 600 | AGGRESSOR_BREAKTHROUGH | SELL | 7 | -1.344 | -6.032 | -6.863 | 0.286 | 0.286 | 0.429 |
| 60 | 600 | DEFENDER_REVERSAL | BUY | 2 | 1.029 | -3.649 | -6.541 | 0.000 | 0.000 | 1.000 |
| 60 | 600 | DEFENDER_REVERSAL | SELL | 2 | -4.142 | -8.759 | -6.323 | 0.500 | 0.500 | 1.000 |
| 300 | 300 | AGGRESSOR_BREAKTHROUGH | BUY | 1 | -2.149 | -6.752 | -5.954 | 0.000 | 0.000 | 1.000 |
| 300 | 300 | AGGRESSOR_BREAKTHROUGH | SELL | 1 | 0.717 | -3.961 | -4.694 | 0.000 | 0.000 | 1.000 |
| 300 | 300 | DEFENDER_REVERSAL | BUY | 0 | — | — | — | — | — | — |
| 300 | 300 | DEFENDER_REVERSAL | SELL | 0 | — | — | — | — | — | — |
| 300 | 600 | AGGRESSOR_BREAKTHROUGH | BUY | 1 | 1.335 | -3.269 | -5.954 | 1.000 | 0.000 | 1.000 |
| 300 | 600 | AGGRESSOR_BREAKTHROUGH | SELL | 1 | 3.244 | -1.435 | -4.694 | 0.000 | 0.000 | 1.000 |
| 300 | 600 | DEFENDER_REVERSAL | BUY | 0 | — | — | — | — | — | — |
| 300 | 600 | DEFENDER_REVERSAL | SELL | 0 | — | — | — | — | — | — |

## 主候補のセッション別stress結果

30 USD cost、`RESOLUTION_CONFIRMED_V1`だけを固定UTCセッションで表示する。

| obs | horizon | session | OK | median net bps | favorable first | adverse first | invalidation first |
|---:|---:|---|---:|---:|---:|---:|---:|
| 60 | 300 | ASIA | 4 | -6.123 | 0.000 | 0.250 | 0.500 |
| 60 | 300 | EUROPE_NY_OVERLAP | 0 | — | — | — | — |
| 60 | 300 | LATE | 5 | -4.006 | 0.000 | 0.400 | 0.800 |
| 60 | 300 | NEW_YORK | 9 | -6.435 | 0.444 | 0.222 | 0.444 |
| 60 | 600 | ASIA | 4 | -5.240 | 0.000 | 0.250 | 0.500 |
| 60 | 600 | EUROPE_NY_OVERLAP | 0 | — | — | — | — |
| 60 | 600 | LATE | 5 | -3.945 | 0.200 | 0.600 | 0.800 |
| 60 | 600 | NEW_YORK | 9 | -11.631 | 0.444 | 0.444 | 0.667 |
| 300 | 300 | ASIA | 0 | — | — | — | — |
| 300 | 300 | LATE | 2 | -5.357 | 0.000 | 0.000 | 1.000 |
| 300 | 300 | NEW_YORK | 0 | — | — | — | — |
| 300 | 600 | ASIA | 0 | — | — | — | — |
| 300 | 600 | LATE | 2 | -2.352 | 0.500 | 0.000 | 1.000 |
| 300 | 600 | NEW_YORK | 0 | — | — | — | — |

## 判定制約

- 30日未満かつpurge後200 Episode未満なので、優位性を宣言しない
- 同日データで仕様確認した探索集計であり、untouched testではない
- 20／30 USD控除はBinance価格上のproxyであり、HFM伝達性を証明しない
- HFM同一時計Bid／Askが無いためGate 3／4は未評価
- 各ローリング更新を独立取引として数えず、600秒重複purgeを主表に使用した

詳細なstatus件数、raw／purged候補数、paired比較、全行outcomeはJSON成果物に保存した。
