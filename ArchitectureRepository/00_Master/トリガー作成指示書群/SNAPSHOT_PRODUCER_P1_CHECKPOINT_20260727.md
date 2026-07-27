# Snapshot Producer P1 Checkpoint

作成日: 2026-07-27 JST
状態: P1完了、P2開始前停止

## 1. 承認範囲

「実在材料による代表1型 最小貫通経路」設計のGOに基づき、Snapshot Producerの材料横流し層だけを実装した。P2 pipeline配線、P3正本更新、P4較正・リプレイは未着手である。

## 2. 完了内容

- `Delta_Engine_Pro4web/src/strategy_engine/ingestion/snapshot_producer.py`を新規追加。
- public detector result objectだけを受け取り、既存`MarketStateSnapshot`へ変換するAPIを追加:
  `observe_cvd`、`observe_flow_response`、`observe_absorption`、`observe_book`、`observe_imbalance`、`build_market_state`、`to_conditions`。
- threshold、clock、既存detector内部ロジックをProducerに実装していない。
- CVDのwindow完全な1s/5s/30s/5m delta・CVD change/slope、1s/5sのside volume/count/average/max/rate/shareをDecimalで生成する。
- FlowResponseの30s/5m deltaをcanonical `trade_delta_30s`／`trade_delta_5m`へ直接供給する。
- 承認済みの横流しとして`BUY_ABSORPTION`→`bid_absorption_like_active=1`、`SELL_ABSORPTION`→`ask_absorption_like_active=1`を供給する。不明・非成立・欠測はomitする。
- public OrderBook snapshotは既存Adapterのbook wall keyへ渡せる`BookLevel`へ変換する。

## 3. 意図的に未実装／omitする材料

- notional、large trade count（price／CalibrationBook thresholdが未供給）。
- G07 book event flow、G09正式式・効率・無進行・反転、G11 profile。
- 1m ImbalanceResultの1s/5s/30s/5m keyへの再window化。
- `flow_price_divergence_active`を含む他のG16 composite、breakout、defense、反証key。
- pipelineからのproducer呼出し、`MarketStateSnapshot`のproduction handoff、configへのtick_size追加。

## 4. テスト・検証

- 新規: `tests/strategy_engine/test_snapshot_producer.py` — **4 passed**。
- 全回帰: `python -m pytest -q tests -p no:cacheprovider --basetemp .pytest_snapshot_p1_20260727_1420` — **578 passed, 1 skipped in 23.66s**。
- source、既存test、pipeline、adapter、正本、runtime、raw data、収録基盤の既存fileは無変更。
- 回帰用basetempは検証後に削除済み。commit/pushなし。

## 5. 停止点と次の再開位置

- blockerはP1ではなく、P2で必要となるLive／Replay両pipelineの観測点配線とengine_time_ns／tick_size handoffである。
- 次の再開位置はP2実装開始。P2着手には、producerの出力key範囲とpipeline変更範囲を確認する。
- P3正本更新とP4較正・実データリプレイには進まない。
