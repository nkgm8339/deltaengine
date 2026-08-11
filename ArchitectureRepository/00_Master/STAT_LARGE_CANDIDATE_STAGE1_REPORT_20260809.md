# 統計的大口候補判定 — Stage 1 調査レポート

## 調査環境

- commit SHA: `778289d63f744adbe452186845d3709bbbdcfa0b`
- branch: `feature/footprint-dom-tape`
- 調査日時: `2026-08-09 01:56 UTC`開始
- 対象: `Delta_Engine_Pro4web/`
- 変更: コード、テスト、依存、既存設定は変更していない。新規作成は本レポートのみ。

## P. pipeline.py

### P-1: trade正規化

実装は`src/normalization/normalizer.py`にある。`normalize_raw(raw, profile)`（`src/normalization/normalizer.py:233`）がraw dictを受け、`NormalizedTrade`を返す。price/quantityは`Decimal(str(...))`で正規化され、非有限・非正値は拒否される（`src/normalization/normalizer.py:249-268`）。`DataNormalizer.process(raw)`（`src/normalization/normalizer.py:340`）がdedup/reorderを行い、releaseされた`list[NormalizedTrade]`を返す。

根拠:

```python
def normalize_raw(raw: dict[str, Any], profile: ExchangeProfile) -> NormalizedTrade:
    ...
    price = Decimal(str(field("price")))
    quantity = Decimal(str(field("quantity")))
```

### P-2: detector呼び出し

Liveは`LivePipeline.run_async`のconsumer（`src/pipeline.py:1971-2005`）が`normalizer.process(raw)`を呼び、返されたtradeごとにローカル関数`handle(normalized)`（`src/pipeline.py:1585`）を直接呼ぶ。イベントバスではない。Replayは`ReplayPipeline.run`の`handle`（`src/pipeline.py:590`）で同じ順序の処理を直接行う。

根拠:

```python
for normalized in normalizer.process(raw):
    handle(normalized)
trades_in += 1
```

### P-3: 既存detector一覧

Liveのtrade-path登録は`src/pipeline.py:1505-1518`。`LargeTradeDetector`、`SweepDetector`、`ExhaustionDetector`、`UnfinishedAuctionDetector`、`TapeAnalyzer`が生成される。Absorption、Imbalance、CVD、Footprint、FlowPriceResponseも`handle`内で直接処理される（`src/pipeline.py:1593-1678`）。Hookの`LiveHookObserver`は設定が有効な場合に`src/pipeline.py:1249-1325`で生成される。

### P-4: detector後のstorage

Liveは`BackgroundStorageWriter`を`src/pipeline.py:1491-1500`で生成し、tradeを`storage.add_trade(trade_to_row(normalized))`（`src/pipeline.py:1593`）、Flow Responseを`storage.add_flow_response_event(...)`（`src/pipeline.py:1611`）、candle/footprintを`src/pipeline.py:1664-1675`で追加する。実際の非同期書き込み実装は`src/database/storage.py:744`の`BackgroundStorageWriter`。Replayは`StorageWriter`を`src/pipeline.py:563-566`で生成し、同じrow APIを直接呼ぶ。DuckDB/Parquetのパスはstorage writerへ渡される。

### P-5: detector後のpush_broker

Pipeline自身はbrokerをimportせずcallbackを持つ。`on_flow_event`、`on_webapp_flow_event`、`on_flow_response`等のcallback属性は`src/pipeline.py:1008-1106`で受ける。WebApp側で`on_webapp_flow_cb`が`broker.on_flow_event`をscheduleし、各callbackをpipelineへ代入する（`webapp/main.py:404-434`）。`on_flow_event`は`webapp/push_broker.py:691`、Flow Responseは同`703`、TICKは`webapp/main.py:269-300`のpump経由でbrokerへ渡る。

### P-6: asyncio/thread/executor/queue

Liveはsingle asyncio loopだが、connector task、receiver task、任意のbook supervisor taskを作る（`src/pipeline.py:1907-1925`）。`receiver_out`と`ws_out`は`BoundedEventQueue`（`src/pipeline.py:1367-1368`）。snapshot request/resultも`asyncio.Queue`（`src/pipeline.py:1393-1394`）。Replayは`webapp/main.py:454`で`loop.run_in_executor(None, pipeline.run, ...)`を使い、replay worker threadからbroker callbackを`run_coroutine_threadsafe`で戻す（`webapp/main.py:318-355`）。新しい統計detectorは既存main loop内の同期callに限定する必要がある。

### P-7: 最小変更候補

tradeが正規化され既存detectorへ渡る共通点は、Liveの`handle(normalized)`内、`storage.add_trade`直後〜既存detector群の前後（`src/pipeline.py:1593-1648`）である。Replayにも同じ機能を追加するなら`ReplayPipeline.run`の`handle`（`src/pipeline.py:590-624`）にも同じ同期callが必要になる。最小候補は新collectorを生成し、Live/Replay双方の`handle`で`collector.observe(normalized)`を1回呼ぶこと。ただし、P-6の既存Replay executorとstorage/push経路を壊さない設計が必要。

### P-8: pipeline.py内のfloat()

0件ではない。次の3箇所がある。

- `src/pipeline.py:391` `self.replay_speed = float(replay_speed)`
- `src/pipeline.py:463` `float(getattr(replay, "speed", 0.0))`
- `src/pipeline.py:1190` `mt5_heartbeat_interval=float(config.mt5.heartbeat_interval_sec)`

これらはreplay速度・MT5 heartbeatの制御値であり、price/quantity/notional計算ではない。ただし親文書の「pipeline.py内float() 0件」という要求とは不一致なので、統計機能実装とは別に承認を得て扱う必要がある。Stage 1では修正していない。

## F. flow_detector.py / LargeTradeDetector

### F-1: large_trade_min_qty

設定スキーマは`src/config.py:313-315`で`"5.0"`というnon-empty string。Pipelineで`Decimal(config.flow_detector.large_trade_min_qty)`へ変換され、`LivePipeline.__init__`の`flow_large_trade_min_qty`となる（`src/pipeline.py:1012`, `1108`, `1192`）。`LargeTradeDetector`へDecimalとして渡される。

### F-2: 入力シグネチャ・出力

`src/orderflow/flow_detector.py:41-58`の`LargeTradeDetector.__init__(min_qty: Decimal)`と`process(trade: Any) -> Optional[FlowEvent]`。入力tradeのquantity/priceは正規化済みDecimal。閾値以上で`FlowEvent`、未満でNone。

根拠:

```python
def process(self, trade: Any) -> Optional[FlowEvent]:
    qty = trade.quantity
    if qty < self._min_qty:
        return None
```

### F-3: イベント種別

`FlowEvent.kind`は`"large_trade"`（`src/orderflow/flow_detector.py:19-24`, `48-58`）。WebSocket側では`FLOW` envelope内の`category/kind/detector`として運ばれる（`webapp/push_broker.py:691-700`）。独立した`LARGE_TRADE` WebSocket typeではない。

### F-4: push経路

Live `handle`が`_large_trade_det.process(normalized)`を呼び、結果を`_emit_flow`へ渡す（`src/pipeline.py:1643-1650`）。`_emit_flow`は`self.on_flow_event(evt)` callbackを呼ぶ（`src/pipeline.py:1522-1528`）。WebAppの`on_webapp_flow_cb`が`broker.on_flow_event`をscheduleする（`webapp/main.py:404-434`）。

### F-5: float()

`src/orderflow/flow_detector.py`本体に実行される`float()`は0件。モジュールdocstringにもDecimal only/float禁止がある（`src/orderflow/flow_detector.py:1-9`）。

## H. Hook Detector

### H-1: large_trade系フック

`src/orderflow/hooks/registry.py:20-48`にA/B/C等のHook名がcatalogとして定義される。large系はBカテゴリの`large_market_buy`、`large_market_sell`、`large_buy_cluster`、`large_sell_cluster`。閾値は`ThresholdBook`がYAMLから読み、Decimalで`HookThreshold.value/quantile`を保持する（`src/orderflow/hooks/config.py:177-243`）。個別の`hook_detector.py`は不在。

### H-2: hook名・行番号

- `large_market_buy`, `large_market_sell`: `src/orderflow/hooks/registry.py:35-42`
- `large_buy_cluster`, `large_sell_cluster`: `src/orderflow/hooks/registry.py:39-42`

### H-3: HookEvent payload

`HookEvent`は`src/orderflow/hooks/models.py:207-237`。`hook_id`、`detector_version`、`metric_name/value`、threshold、`evidence`等を持ち、専用のdetector名フィールドではなく`hook_id`と`detector_version`で識別する。`to_row`は`src/orderflow/hooks/models.py:295`付近。

### H-4: pipeline段階

Raw tradeはnormalizerの前に`notify_hook("observe_raw_trade", raw, ...)`（`src/pipeline.py:2000-2005`）へ送られる。depthは`process_live_depth`内で`notify_hook("observe_depth", ...)`（`src/pipeline.py:1731-1756`, `1858-1888`）へ送られる。従ってHookは正規化trade detector後ではなく、raw trade/depth処理の別tapとして動く。Hook observer自体は`src/pipeline.py:1325`で生成される。

### H-5: 分布・統計量

Hookにはrolling/state保持がある。例として`src/orderflow/hooks/adapters.py:71`にtrade window deque、`src/orderflow/hooks/dom_iceberg.py:16`に5秒episode window、`src/orderflow/hooks/dom_features.py:106-178`に前回DOM feature cacheがある。ThresholdBookは分布収集器ではなく、事前計算済みthreshold/quantileを読み、candidateへ適用する（`src/orderflow/hooks/config.py:197-243`）。

## B. push_broker.py

### B-1: PriorityQueue

`CLIENT_QUEUE_MAXSIZE = 256`、heartbeat priority `0`、normal priority `1`は`webapp/push_broker.py:20-23`。各clientの`asyncio.PriorityQueue`は`webapp/push_broker.py:148-163`。queue itemは(priority, sequence)で順序付けされる。

### B-2: event種別登録

enumや中央registryはなく、`envelope(msg_type: str, ...)`（`webapp/push_broker.py:43-50`）へ文字列を渡す自由形式。現在の明示種別はTICK、SPOT_PRICE、TAPE_UPDATE、BOOK_UPDATE、CANDLE、ANALYSIS、ABSORPTION_STATE、FLOW、FLOW_RESPONSE、LIQUIDATION、OI、HFM_QUOTE、BAR_UPDATE、MARKET_HEARTBEAT、HEALTH、STATS（各送信箇所: `webapp/push_broker.py:432`, `453`, `480`, `522`, `582`, `599`, `683`, `691`, `704`, `729`, `748`, `761`, `784`, `834`, `861`, `866`, `869`）。

### B-3: 新種別追加箇所

文字列event種別の中央登録は不要。`PushBroker`へ新`on_statistical_large_candidate`メソッドを追加し、payload validation、cache要否、`_broadcast`呼び出し、`webapp/main.py` callback wiring、ブラウザのmessage dispatch、関連テストが変更候補になる。queue priorityは通常priority 1が候補だが、候補イベント数と既存TICK/TAPEへの影響を計測して決める。初期Stage 1では変更なし。

### B-4: 送信失敗・drop

送信は`_client_writer`（`webapp/push_broker.py:336-368`）で`client_send_timeout_sec=0.5`（`webapp/push_broker.py:20`, `175-190`）を使う。例外時はclientをclosingにし、pending queueを`_fail_pending`でfailさせる（`webapp/push_broker.py:317-334`）。queue fullは`_enqueue`（`webapp/push_broker.py:399-418`）でslow clientを切断する。サイレントdropではない。

### B-5: stale閾値

PushBroker自体はstale判定をしない。ブラウザFreshness guardが`webapp/static/market_freshness.js:30-32`でTICKのtransport 2000ms、source 5000ms、future tolerance 5000msを既定値として持つ。Event freshness guardはtransport 3000ms/source 5000ms（同`235-239`, `308-309`）。

### B-6: browser queue制限

Server-side client queueは256件（`webapp/push_broker.py:20-23`, `157-158`）。Tapeのbrowser-side保持上限は設定値`config.webapp.tape_pending_capacity`を`webapp/main.py:301-306`から`TapeBatcher`へ渡し、`webapp/static/time_sales.js:224`のcapacity初期値・`195-202`のfilter処理がある。新候補イベント専用bufferの上限は未定義。

### B-7: push頻度の概算

- TICK: analyticsはtradeごとに処理されるが、browser送信は`LatestValuePump`の`config.webapp.tick_push_interval_ms`（`webapp/main.py:269-303`）で最新値へcoalesce。
- BOOK_UPDATE: `book_update_interval_ms`の`LatestBookProjectionPump`（`webapp/main.py:303-312`）で定期送信。
- TAPE_UPDATE: `tape_batch_interval_ms`と`max_trades_per_message`（`webapp/main.py:301-306`）でbatch送信。
- FLOW/ABSORPTION/FLOW_RESPONSE: detector発火・snapshot生成時のみ。固定pps定数は見つからず、候補cluster両発火時は追加イベント数ぶん増える。

## R. Replay / EventSource

### R-1: 起動経路

設定`config.replay.enabled`がtrueの場合、`webapp/main.py:255-263`で`ReplayPipeline.from_config`を生成し、`webapp/main.py:454`で`loop.run_in_executor(None, pipeline.run, config.replay.data_path)`を開始する。設定スキーマは`src/config.py:305-310`。

### R-2: trade供給元

`ReplayPipeline.run(data_path)`は`src/acquisition/replay.py:37-62`の`ReplaySource.read_all()`からJSON Linesを読み込む（`src/pipeline.py:497-498`）。Parquet/DuckDBではなく、指定されたJSONL raw recordingが直接の供給元。

### R-3: detector経路

Replayは`ReplayPipeline.run`内でDataNormalizerを通し、`handle(normalized)`へ進む（`src/pipeline.py:497`, `590-605`）。Liveの`LivePipeline`とは別クラスだが、normalize→trade detector/flow/storageの処理は同等の順序で、独自のEventSource detector経路ではない。

### R-4: EventSource種別

`ReplaySource`はraw JSON dictをyieldするだけで、イベント種別registryは持たない（`src/acquisition/replay.py:37-72`）。rawの`e`は`DataNormalizer.classify_raw`が分類する。従って`STATISTICAL_LARGE_CANDIDATE`をReplaySourceへ登録する場所は不在。

### R-5: event_time順序

ReplaySourceはファイル順で読み込む（`src/acquisition/replay.py:37-62`）。ReplayPipelineのDataNormalizerは`reorder_tolerance_ms`と内部bufferでrelease順を整える（`src/normalization/normalizer.py:301-340`）。ファイル自体をtimestamp sortする処理は見当たらないため、入力が許容範囲を超えて逆順の場合はrejectされる。完全な事前ソート保証ではない。

### R-6: Replay初期化

`ReplayPipeline.run`開始ごとにnormalizer、FlowPriceResponse、Absorption、Imbalance、CVD、Footprint、StorageWriter等を新規生成する（`src/pipeline.py:499-566`）。分布collectorは未実装で、既存detector状態はrunごとに初期化される。warm-startを行う既存Flow Responseは`warm_start` API（`src/orderflow/flow_price_response.py:215`）があるが、ReplayPipeline.runではraw run用の新規detectorを使うため、統計的大口分布の再利用は未定義。

## T. 既存テスト

### T-1: test_api.py

場所: `tests/webapp/test_api.py`。関数一覧は`tests/webapp/test_api.py:79-641`で、health/heartbeat/stats/config、candle/footprint/tape/Flow Response/OI/history、replay時のOI/book停止、replay callback、book resyncを検証する。新push種別を追加する場合、`test_stats_ok`、`test_replay_*`、broker wiring関連が影響候補。

### T-2: test_push_broker.py

場所: `tests/webapp/test_push_broker.py`。関数一覧は`tests/webapp/test_push_broker.py:39-1250`。envelope、Decimal、queue overflow、TICK/BOOK/CANDLE/ANALYSIS/Flow/Absorption/Flow Response、三段チャートUI payload、broker wiringを検証する。新種別は既存exact payload期待値、queue overflow、main wiringテストに影響する。

### T-3: test_absorption_realtime_display.py

場所: `tests/webapp/test_absorption_realtime_display.py`。3関数（`48`, `92`, `132`）でactive/clear/cache、tick-time bridge、realtime/fallback wiringを検証する。統計的大口イベントをAbsorptionへ混ぜる変更は禁止なので、直接影響はないが、shared broker payload変更時は回帰対象。

### T-4: tests/orderflow一覧と関連

`tests/orderflow/`にはflow detector（`test_flow_detector.py:69-254`）、Flow Price Response（`test_flow_price_response.py:53-202`）、Hook契約/Stage2B（`test_hook_contract.py`, `test_stage2b_*`, `test_stage2c4_live_hooks.py`）、Absorption、CVD、Footprint、VolumeRef、pipeline wiring関連（repository rootの`tests/test_pipeline*.py`）がある。統計collector追加に直接関係する既存回帰は`test_flow_detector.py`、`test_hook_contract.py`、`test_stage2b_*`、`test_live_pipeline.py`、`test_pipeline_snapshot_wiring.py`、`test_pipeline_absorption.py`。

### T-5: 期待値が変わりうるテスト

新moduleをimportするだけなら既存期待値は変わらない見込み。`pipeline.py`へ1行callを追加すると、callback/event count、storage write count、websocket queue/message exact payloadが変わりうる。特に`tests/webapp/test_push_broker.py:761-801`（queue overflow/close）、`1008-1090`（Flow event/main wiring）、`tests/webapp/test_api.py:549-641`（Replay callback/stats）、`tests/test_live_pipeline.py`（live callback）が影響候補。新イベントを既存`FLOW`へ混ぜる場合は、Flow event countとUI marker期待値が変わるため禁止または明示更新が必要。

## L. 流動性関連データ

### L-1: 計算・保持されている指標

- **spread / spread_bps**: `DomFeatures.spread`, `spread_bps`（`src/orderflow/hooks/dom_features.py:68-99`, `152-178`）。Decimal。depth snapshotごとに更新。`DomFeatureCache`のメモリ内previous/currentのみ。
- **bid_total / ask_total / bid_median / ask_median**: 同じ`DomFeatures`（`src/orderflow/hooks/dom_features.py:68-99`, `167-177`）。Decimal。depthごと、メモリ保持。
- **wall ratio / gap bps**: `bid_wall_ratio`, `ask_wall_ratio`, `downside_gap_bps`, `upside_gap_bps`（同`68-99`, `167-178`）。Decimal。depthごと、メモリ保持。Hook candidateのevidence/metricへ渡る。
- **volume reference**: `VolumeRefTracker`（`src/orderflow/volume_ref.py:31-82`）。Decimal deque、既定20 bars（`src/config.py:289-292`）。confirmed footprint barごとに更新、memory only。Absorption/Imbalance共有。
- **session VWAP**: `PriceStructureDetector`の`_vwap_notional`, `_vwap_volume`, `vwap`（`src/orderflow/hooks/price_structure.py:35-42`, `191-205`）。Decimal、bar closeごと、日付変更でreset、memory only。WebApp projectionは`webapp/main.py:172-181`。
- **open interest**: `OpenInterestDetector`のDecimal point deque（`src/orderflow/hooks/open_interest.py:18-67`）とstorage OI rows。定期REST poll、memory + DuckDB/Parquet storage。`webapp/main.py:526-530`が保存。
- **order-book depth / spread**: `OrderBookStateManager`のbid/ask levels（`src/orderflow/orderbook.py:41-90`以降）、WebApp `BookProjection` payload（`webapp/push_broker.py:515-552`）。Decimal、verified depth updateごと、memory。永続raw depthは設定有効時にJSONL recorder（`webapp/main.py:195-204`, `src/acquisition/depth_history_recorder.py:117-141`）。

### L-2: 流動性状態分類

有り。Hook registryに`low_liquidity_context`（`src/orderflow/hooks/registry.py:78-80`）がある。`DomLiquidityDetector`はdepth removed/added fraction、spread expansion/contraction、dominant/opposite depth ratioを検出する（`src/orderflow/hooks/dom_liquidity.py:35-105`）。ただし統計的大口用の共通`HIGH/MEDIUM/LOW`状態enumは不在。HFMの`hfm_spread_normal`はBinance orderbook流動性とは別指標。

### L-3: rolling/streaming統計の再利用候補

有り。

- `VolumeRefTracker`: fixed-bar deque、Decimal moving average（`src/orderflow/volume_ref.py:31-82`）。
- `FlowPriceResponseDetector`: 1秒bucket dequeで30s〜30m rolling window（`src/orderflow/flow_price_response.py:104-155`）。
- `DomFeatureCache`: previous/current streaming state（`src/orderflow/hooks/dom_features.py:106-178`）。
- Hook `adapters.py`: trade deque window（`src/orderflow/hooks/adapters.py:71`）。
- `OpenInterestDetector`: points deque（`src/orderflow/hooks/open_interest.py:18-67`）。

統計的大口分布collectorの再利用候補はdeque/prune・Decimal・deterministic replayの設計。ただし既存VolumeRefはper-level volume用であり、約定notional分布へそのまま流用できない。

### L-4: tickSize

設定`market.tick_size`が必須Decimal string（`src/config.py:238-244`）。`ReplayPipeline.from_config`と`LivePipeline.from_config`で`Decimal(str(config.market.tick_size))`へ変換され、`src/pipeline.py:461`, `1157`の`self.tick_size`へ保持される。exchangeInfoをruntimeで取得してtickSizeを更新する処理は不在。統計collectorはこの設定値を使い、missing/invalid時は判定不能にする必要がある。

## 調査中に発見した問題・懸念

1. P-8の通り、`pipeline.py`にはfloat()が3箇所ある。価格・数量計算ではないが、親文書の「pipeline.py float 0件」とは不一致。
2. `push_broker.py`はdocstringで「float()禁止」としているが、queue timeout/interval制御にはfloat変換がある（`webapp/push_broker.py:84-90`, `187-189`）。Decimal payloadとは別系統だが、指示書の型境界を実装時に分離する必要がある。
3. ReplaySourceはファイル順であり、完全なtimestamp sortを行わない。統計分布の再現性には、既存normalizerのrelease順と未来データ混入テストが必要。
4. Hook catalogにはlarge系・low liquidity系があるが、統計的大口分布を既に収集する共通基盤はない。ThresholdBookのquantileは事前設定値でありlive分布更新器ではない。
5. PushBrokerのclient queueは256件で、queue full時はslow clientを切断する。個別/cluster両イベントを追加する場合、既存TICK/TAPEと同一queueに入るため、Stage 2前に発火頻度・coalesce・優先度を決める必要がある。
6. `STATISTICAL_LARGE_CANDIDATE`の保存schema、Replay event種別、独立UI bufferは現状不在。Stage 1の不在として記録し、実装時に新規設計が必要。

## 調査結果の要約

- 最小の同期call候補はLive/Replay双方の正規化済みtrade `handle`内。ただしLiveとReplayは別クラスなので両方へ同じcollector callが必要。
- 既存Hookはraw trade/depth tapで、統計collectorの入力段階とは異なる。Hookとは独立並行にするのが安全。
- Decimalはnormalizer、Flow detector、VolumeRef、payloadで既に使われている。pipelineの制御値floatは別問題として隔離する。
- 新イベントはpush_brokerの自由文字列envelopeに追加できるが、既存queue 256件、0.5秒送信timeout、Freshness 2000/3000/5000msの影響をStage 2 soakで検証する必要がある。
- 流動性分割に使えるspread、depth total、volume reference、VWAP、OIは既存にあるが、共通分類enumと統計分布collectorは未実装。

## SHA-256 / バイト数

最終ファイルのSHA-256とバイト数は、レポート完成後のhandoffで報告する。
