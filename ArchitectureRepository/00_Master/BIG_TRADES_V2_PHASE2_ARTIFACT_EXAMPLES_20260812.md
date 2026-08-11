# Big Trades V2 Phase 2 Artifact Examples

生成日: 2026-08-12

この文書のJSONは、工程2の実装クラスから同一入力で実際に生成したcanonical JSON例である。production dataへは書き込んでいない。DecimalはJSON numberではなくstring、時刻はUTC、keyは辞書順である。

## 1. Settings version

```json
{"automatic_intensity":"MEDIUM","calibration_id":"btcal1_fd001000245a6f97c21309341e95b086b3f4345fcf5e9a6f4c0fe9d3d87d3eb8","content_sha256":"87572c4dfd28c64d79e42fc80e44b0f98e2a4739e440a296918fa2b52d8dabe2","filter_mode":"AUTOMATIC","input_mode":"AGGREGATE_TRADES","logic_version":"BTLOGIC-2.0","manual_max_quantity":"0","manual_min_quantity":"5","marker_price_mode":"LAST_PRICE","schema_version":1,"settings_id":"bts1_87572c4dfd28c64d79e42fc80e44b0f98e2a4739e440a296918fa2b52d8dabe2","side_filter":"BOTH","symbol":"BTCUSDT","venue":"BINANCE"}
```

## 2. Calibration

```json
{"aggregation_candle_timeframe":"1m","aggregation_window_ms":40,"auto_low":"11","auto_medium":"22","auto_strong":"29","base_low":"11","base_medium":"22","base_strong":"29","baseline_volatility":null,"calibration_id":"btcal1_fd001000245a6f97c21309341e95b086b3f4345fcf5e9a6f4c0fe9d3d87d3eb8","content_sha256":"fd001000245a6f97c21309341e95b086b3f4345fcf5e9a6f4c0fe9d3d87d3eb8","created_at_utc":"2026-01-21T00:00:00.000000Z","history_end_session":"2026-01-20","history_start_session":"2026-01-01","input_mode":"AGGREGATE_TRADES","logic_version":"BTLOGIC-2.0","quantity_step":"0.001","quantity_unit":"BASE_ASSET","recent_volatility":null,"schema_version":1,"session_template":"CRYPTO_UTC_DAY","source_manifest_sha256":"57df3a8c53bd295775264115a02a3eecb78a316dbae3648c26357a8f9b84a368","symbol":"BTCUSDT","target_events":{"LOW":20,"MEDIUM":9,"STRONG":2},"valid_sessions_low":20,"valid_sessions_medium":20,"valid_sessions_strong":20,"venue":"BINANCE","volatility_factor":"1","volatility_status":"VOLATILITY_FALLBACK_1"}
```

`created_at_utc`は監査情報であり、`calibration_id`、Replay適用境界、active判定には使わない。この例はcandle volatilityが不足しているため、quantity rankingは有効のままfactorだけ`1`へ明示fallbackしている。

## 3. Committed activation

```json
{"activation_id":"bta1_13ded1086d92d7c5025e6250aa00071294d6ccf175887924df375fd5fdfef779","activation_policy":"SCHEDULED_SESSION_BOUNDARY","activation_reason":"SCHEDULED_WEEKLY","calibration_id":"btcal1_fd001000245a6f97c21309341e95b086b3f4345fcf5e9a6f4c0fe9d3d87d3eb8","content_hash":"5679a1221ec95c809700a43cd9d0b5e9788de60a39f8fcbe66173e73afb83358","effective_from_event_time":"2026-01-26T00:00:00.000000Z","effective_from_trade_id":100,"effective_session_id":"2026-01-26","input_mode":"AGGREGATE_TRADES","logic_version":"BTLOGIC-2.0","requested_at_utc":"2026-01-26T00:00:00.000000Z","schema_version":1,"settings_id":"bts1_87572c4dfd28c64d79e42fc80e44b0f98e2a4739e440a296918fa2b52d8dabe2","symbol":"BTCUSDT","venue":"BINANCE"}
```

Replayは`effective_from_event_time`と`effective_from_trade_id`を使用する。`requested_at_utc`、file mtime、active pointerは使用しない。

## 4. Schedule run

```json
{"attempted_at_source_event_time":"2026-01-26T00:00:00.000000Z","candidate_calibration_id":"btcal1_fd001000245a6f97c21309341e95b086b3f4345fcf5e9a6f4c0fe9d3d87d3eb8","content_sha256":"aa28a1a17569cb07cf8c3062eda46a4aa952c340518097e1c8e2669241d350bd","failure_code":null,"result":"ACTIVATED","run_id":"btrun1_467ada08c84623bd9b9776596922fd24ad6ca8f6f5ccc3357bcd6de5674fdea2","schedule_boundary_id":"WEEKLY|2026-W05|BTCUSDT|BINANCE|AGGREGATE_TRADES|BTLOGIC-2.0","schema_version":1,"source_manifest_sha256":"57df3a8c53bd295775264115a02a3eecb78a316dbae3648c26357a8f9b84a368"}
```

`run_id`はschedule boundaryとsource manifestから決まり、同一入力の自動再生成・再activateを防ぐ。`VALIDATION_FAILED`または`STORAGE_FAILED`も同じIDでterminal記録となる。
