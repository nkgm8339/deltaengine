# Order Book Heatmap GO-H4 checkpoint

更新: 2026-07-29 06:48 JST  
承認: user `GO-H4`

## 完了

- `TimeSalesView`へ additive `onAcceptedTrades(newTrades, batchResult)` callbackを追加。
- callbackはlive ingestで今回新規acceptedされたtradeだけを通知し、history mergeは通知しない。
- Heatmap UIへtrade store ingest、Tape row selection、`TRADE OUTSIDE TAPE RETENTION` fallbackを接続。
- Book H2 storeのdelivery gap／stream restart／fail-closed状態をHeatmap statusへ渡す。
- callback／Heatmap処理はflag OFF時に無効で、既存Tape ingest／renderを妨げない。

## 検証

- Node syntax (time_sales.js／inline index script): PASS
- H2／H3／H4／Footprint／Tape UI contracts: **19 passed**
- 既存Tape history test 1件はpytest temp root permission errorでsetup不能。実装failureではない。

## 未完了

Canvas上の実bubble hit-test、performance／soak、runtime deployment、feature flag enableはGO-H5／H6へ残す。
