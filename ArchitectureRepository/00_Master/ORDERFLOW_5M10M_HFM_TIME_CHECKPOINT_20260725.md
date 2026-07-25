# HFM time-alignment checkpoint

時刻: 2026-07-25 13:55 JST  
承認範囲: HFM quote parserと同一local-clock outcome evaluator  
未承認: Binance Episodeへの実データ結合、戦略評価、Live接続、発注

## 完了

- `src/orderflow/hfm_episode_outcome.py`を新規追加
- HFM CSVのBid／Ask、source time、local received time、sequenceを読み取る純粋parserを追加
- 同一local clockのsignal timeに対する最新quoteをentryへ使用
- BUYはAsk entry→Bid exit、SELLはBid entry→Ask exitで計算
- spreadを別途二重控除しない
- entry stale、outcome missing、quote gap、時刻逆行を明示
- `tests/orderflow/test_hfm_episode_outcome.py`を追加

## 検証

- HFM evaluator tests: **3 passed**
- `data/latency/quotes.csv`のHFM行: 20,918件
- 同ファイルのHFM local received範囲: 2026-07-22 16:23:36～16:56:23 UTC
- `quotes_hfm_bridge_after_network_20260723.csv`のHFM行: 627件
- 同ファイルのHFM local received範囲: 2026-07-22 23:12:14～23:14:14 UTC
- HFM source time - local received timeの中央値:
  - `quotes.csv`: 10,801.798秒
  - `quotes_hfm_bridge_after_network_20260723.csv`: 10,799.970秒

## 結合禁止の理由

05M RAW／Episodeの現在主期間は2026-07-24～2026-07-25であり、保存済みHFM quoteの
期間と重ならない。さらにHFM source timeはlocal received timeと約3時間ずれている。

したがって、次をしてはならない。

- Binance event timeをHFM local received timeと仮定する
- source timeへ固定3時間補正してentry時刻を作る
- 日付の異なるHFM履歴を05M Episodeへ結合する
- quote不在を直前値、0、Binance価格で補間する

## 次の必要条件

Episodeのcheckpoint時に、少なくとも次を同一local clockで保存する。

- Binance event／observation time
- Binance local received time
- HFM local received time
- HFM source time
- Bid／Ask
- sequence

この保存境界が連続してから、初めてHFM Gate 3へ進む。

