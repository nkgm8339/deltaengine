# 5M/10M 構造検証 checkpoint

実行日: 2026-07-25  
対象: `data_05M/parquet/flow_response_events/**/*.parquet`  
条件: UTCセッション区分、既存イベントの `window_sec` 60秒・300秒

## 観測結果

既存イベントには 30/60/180/300/900/1800 秒の窓が存在した。固定プロトコルの600秒イベントは現時点で存在しないため、600秒については未評価とした。

60秒窓では、`BUY_EFFECTIVE` の平均価格変化は +3.70bps、`BUY_STALLED` は +0.35bps、`BUY_TRAPPED` は -1.96bps。売り側は符号が逆で、`SELL_EFFECTIVE` -3.86bps、`SELL_STALLED` -0.23bps、`SELL_TRAPPED` +1.63bpsだった。

300秒窓では、`BUY_EFFECTIVE` +7.72bps、`BUY_STALLED` +0.24bps、`BUY_TRAPPED` -1.95bps。売り側は `SELL_EFFECTIVE` -5.82bps、`SELL_STALLED` -0.22bps、`SELL_TRAPPED` +1.87bpsだった。

この並びは、攻撃が価格を進める状態、停滞状態、罠・反転状態が分離して観測されていることを示す。ただし、これは既存イベントの記述統計であり、HFMスプレッド控除後の期待値、独立約定成績、将来期間での再現性を証明しない。

## セッション別の注意

セッション別集計は可能だが、EUROPE_NY_OVERLAP、NEW_YORK、LATEの一部状態は件数が少ない。現時点ではセッション優劣を結論づけず、HFM手動実測の各記録に同じ `session_id` を付与して再検証する。

## 判定

- 1M由来の「有効攻撃 → 停滞 → 罠・反転」という構造は、60秒・300秒イベント上でも観測できる。
- 300秒で構造が消える証拠はないが、5M/10Mで実戦可能とする証拠にはまだ不足している。
- 次工程は固定プロトコルのままHFM手動実測を開始し、スプレッド・遅延・見送りを含む記録を蓄積する。
