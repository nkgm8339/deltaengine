# Footprint × LIVE DOM × Time & Sales Phase 3 完了報告

完了時刻: 2026-07-28 20:13 JST  
対象branch: `feature/footprint-dom-tape`  
開始HEAD: `92ee4eff823ba31e84f7fc0af197d39b877ec236`  
承認: V2.1 GO-8

## 1. 結論

Phase 3「Time & Sales backend／TAPE_UPDATE」を実装し、全回帰試験まで完了した。

Tape sourceはlatest-value `TICK`ではなく、DataNormalizerが正常受理した各約定である。
Live／Replayの双方で受理順を保ち、100ms単位のbounded batchとして配信する。
欠落を隠さず、sequence gap、`dropped_count`、accounting、healthで観測できる。

完成済みのFlow Price Responseと3段チャート、既存フロントページは変更していない。
Canvas Footprint ChartはPhase 4、Time & Sales／LIVE DOMの画面表示はPhase 5である。

## 2. 実装済み契約

### 2.1 Authoritative accepted-trade tap

- DataNormalizer正常受理直後の約定だけをTapeへpublish
- duplicate／invalid tradeはTapeへ流入せずsequenceも消費しない
- `TICK`、Flow、CVDからTapeを再構成しない
- observer例外はanalysis／storage経路から隔離
- ReplayPipelineでも同一契約のaccepted tradeを通知

### 2.2 Bounded Tape batcher

- cadence: 100ms
- 1 message最大: 250 trades
- pending capacity: 10,000 trades
- overflow: drop oldest
- `publish()`は同期・thread-safeで、WebSocket送信をawaitしない
- accepted／sent／pending／in-flight／droppedを計測
- `accepted = sent + pending + in_flight + dropped`を維持
- send failure時のin-flightはdroppedへ移し、次の正常batchで明示

### 2.3 Stream／sequence／reconnect

- `stream_id`: process／replay session単位のUUID
- `sequence`: stream内で1から単調増加
- batch内sequenceは連続し、first／lastと一致
- overflow／send failureで割当済みsequenceを詰め直さない
- 同一processへの再接続ではstreamを継続
- 新しいstreamではclientがgap判定状態をreset
- Tape batchはPushBrokerの再接続cacheへ保存しない

### 2.4 WebSocket payload v1.3

additive message type `TAPE_UPDATE`を追加し、envelopeの`"v": 1`は維持した。

主なfield:

- `batch_time`
- `stream_id`
- `first_sequence`／`last_sequence`
- `accepted_count`／`dropped_count`
- `trades[].sequence`
- `trades[].trade_id`
- `trades[].event_time`
- `trades[].price`／`quantity`／`notional`
- `trades[].side`

price／quantity／notionalはDecimal文字列、event timeはUTCである。

### 2.5 Time & Sales history

`GET /api/history/time-sales`を追加した。

- `limit`: 1〜500
- optional `symbol`
- `before`＋`before_trade_id`複合exclusive cursor
- 同一event timeの複数tradeを欠落させない
- responseはoldest-first
- exact Decimal notional
- liveとのdedup keyは`(symbol, trade_id)`

### 2.6 Lifecycle／observability

- Live／Replayの双方でTape taskを起動
- Replayはreplay accepted tradeだけを流し、live tapeを混在させない
- STATS／`/api/stats`へTape accountingを公開
- overflow、send failure、accounting不一致をhealthへ反映

## 3. 変更file

- `Delta_Engine_Pro4web/webapp/tape.py`（新規）
- `Delta_Engine_Pro4web/webapp/push_broker.py`
- `Delta_Engine_Pro4web/webapp/main.py`
- `Delta_Engine_Pro4web/webapp/history.py`
- `Delta_Engine_Pro4web/src/pipeline.py`
- `Delta_Engine_Pro4web/src/config.py`
- `Delta_Engine_Pro4web/config/config.yaml`
- `Delta_Engine_Pro4web/tests/webapp/test_tape_update.py`（新規）
- `Delta_Engine_Pro4web/tests/webapp/test_api.py`
- `Delta_Engine_Pro4web/tests/webapp/test_push_broker.py`
- `Delta_Engine_Pro4web/tests/test_live_pipeline.py`
- `Delta_Engine_Pro4web/tests/test_pipeline.py`
- `Delta_Engine_Pro4web/tests/test_config.py`
- `ArchitectureRepository/30_Modules/WebApp/Specifications/WebSocketPayload_Spec_v1.md`
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_FUSION_IMPLEMENTATION_INSTRUCTION_V2_20260728.md`
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_FUSION_PREIMPLEMENTATION_AMENDMENT_V2_1_20260728.md`
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_PHASE3_CHECKPOINT_20260728.md`
- 本報告

既存dirty／untrackedのsource、実データ、監査・設計成果物は
reset、checkout、削除、stageしていない。

## 4. 検証

- `py_compile`: PASS
- Phase 3 targeted regression: **113 passed in 19.45s**
- final full pytest: **644 passed, 1 skipped in 34.50s**
- `git diff --check`: PASS
- accepted trade order／duplicate／invalid exclusion: PASS
- 250件chunk／10,000件overflow／drop oldest: PASS
- slow sender中のnon-blocking publish: PASS
- send failure gap／`dropped_count`: PASS
- accounting invariant: PASS
- new stream UUID／sequence reset: PASS
- reconnect Tape batch非cache: PASS
- Live／Replay observer例外隔離: PASS
- history 500件／exact notional／複合cursor: PASS

全テスト用に作成したPhase 3専用一時ディレクトリは、workspace内の対象pathを
検証してから削除した。source、DB、監査成果物は削除していない。

## 5. 運用上の注意

- backendは`TAPE_UPDATE`を配信できるが、既存フロントページは未知typeとして無視する。
- したがって、本Phase完了だけではTime & Salesは画面に表示されない。
- UIのJST `HH:mm:ss.SSS`、virtualized list、filter、large trade強調、
  Footprint選択同期はPhase 5で実装する。
- production processは起動しておらず、production dataは変更していない。
- commit／pushは行っていない。

## 6. 次の承認境界

次はGO-9、Phase 4「Canvas Footprint Chart」である。

GO-9まで未着手:

- Footprint Canvas renderer
- 複数足表示と拡大時約3本の詳細表示
- POC／imbalance／absorption等のFootprint色付け
- viewport／partial redraw／hit testing

Phase 5のTime & Sales／LIVE DOM frontend統合は、さらに別の明示GOを必要とする。
