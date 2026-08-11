# Big Trades V2 Implementation CHECKPOINT

## Current checkpoint

- 更新時刻: 2026-08-12 02:38:10 JST
- current phase: 工程2 config／calibration／artifact実装・検証完了、commit直前
- user承認: 2026-08-12「GO」
- 承認範囲: V2実装指示書§60～§66、工程1～7
- branch: `feature/big-trades-v1`
- 工程1開始HEAD: `9fd7d6ffbb0eee3be50a7dd89c7e1670233042cb`
- 工程1完了commit: `23128fc`
- restore tag: `pre-big-trades-20260811`
- restore tag object: `8e81cb389d459afa68bb5a85bbe4e593d7bfe19b`
- feature flag: `big_trades.enabled: false`、既存runtimeへの接続なし

## 承認範囲

- 工程1～7の実装と各工程の契約内検証は承認済み。
- 工程1ではI/Oなしのpure coreだけを実装した。
- storage、pipeline、API、WebSocket、UI、production DB、稼働containerは変更していない。
- production Manual Min／Maxと初期modeは未決定のまま。工程1～6の実装blockerではない。

## 完了済み

### 工程0

- `AGENTS.md`、`PROJECT_MEMORY.md`、V2 logic正本、V2実装指示書を確認済み。
- source hash、repository pytest、runtime、browser、WebSocket、quantity分布、static UI mockをbaseline化した。
- 工程0成果物をcommit `9fd7d6f`として固定した。
- restore tag `pre-big-trades-20260811`は実装前commit `8e81cb3`を保持している。

### 工程1 pure core

- UTC source-time millisecond orderingとsame-ms trade ID順releaseを実装した。
- 40ms same-side chain aggregationと全close reasonを実装した。
- Manual Min／Maxとcalibration済みAutomatic Size Filter判定を実装した。
- Decimal canonical JSON、content hash、event／zone／interaction／link／snapshot／candle IDを実装した。
- Big Trade eventとauthoritative execution rangeからReaction Zoneを生成した。
- `ABOVE／INSIDE／BELOW`、first exit、touch、reentry、direct cross、inside activity、max excursionを実装した。
- event-zone interval gap linkを実装した。event同士はmergeしない。
- centered interval treeとboundary indexを実装し、active zone 5,000件をsilent evictionなしで保持した。
- accepted source price pathへlast-at-or-beforeとAVL subtree aggregateによるrange min／max queryを実装した。
- source gapを補間せず、fixed horizon 1／5／15／30／60／180／300／600秒を実装した。
- horizonの最大上振れ／下振れはsource price path indexからtarget時刻までを計算する。
- 1分candleのclose above／below、upper／lower wick return、boundary parityを実装した。
- calibration純粋計算として20完了session、20／9／2位、Decimal median、NTR factor、0.75～1.50 clamp、quantity step ceiling、strict threshold orderを実装した。
- 仕様外の`VENUE_CHANGED` enumを除去した。
- ordering層へ無期限duplicate-ID setを持たせず、重複排除の既存authoritative責務を侵食しない構造にした。
- 工程2の再監査で、settings変更によるcluster強制分割を除去し、max-fills invalid clusterのevent生成を禁止した。

### 工程2 config／calibration／artifact

- `big_trades` strict config 25項目を`src/config.py`と`config/config.yaml`へ追加した。
- unknown key、unsupported input mode、非法enum、非法Decimal、Max < Min、非法horizon、boolean整数をstartup errorにした。
- feature flagはfalse、Manual Min `5.000`はinactive defaultでありproduction選択ではない。
- canonical settings ID、immutable settings version、append-only request history、pending pointer、superseded request保存を実装した。
- source-confirmed session trackerとsession stats builderを実装した。wall clock／shutdownはsession completionにしない。
- restart／source gap sessionを完了artifactとして保存可能にしつつAutomatic母集団から除外した。
- 1分candle coverage 95%境界を1368／1440で固定し、不足時はvolatilityだけをfallbackした。
- calibrationはcurrent／future sessionを除外し、直近20 valid session、20／9／2位、20-session baseline、5-session recentを使用する。
- 20 volatility session未満またはbaseline 0は`VOLATILITY_FALLBACK_1`とした。
- calibration IDはauthoritative入力だけから決定し、`created_at_utc`をidentity／Replay境界から除外した。
- settings、session stats、calibration、schedule run、activationをtemporary write、flush、fsync、read-back、hash確認、`os.replace`で保存するrepositoryを実装した。
- activation artifactのfinal renameをdurable commit pointとし、active pointerを再構築可能cacheにした。
- activation boundary collision、artifact schema／hash／symbol／venue／logic／step不一致をfail closedにした。
- WEEKLY ISO週境界とMONTHLY UTC年月境界をsource sessionから検出し、boundary＋source manifestでrunをdeduplicateした。
- scheduled成功時auto activate、`MANUAL_ONLY` pending、validation／storage失敗時の旧activation維持、terminal failureの自動retry禁止を実装した。
- 同一境界ではuser calibrationをscheduled candidateより優先し、combined settings／activation一件へ解決した。
- historical Replayはcommitted activationのeffective source keyだけでversionを選択する。
- `FIXED_RESEARCH`は`research/big_trades/<run_id>`へ隔離し、production activationを作らない。
- YAML referenceと実コード由来の4種類のcanonical artifact例を追加した。

## 未完了

- 工程3: isolated migration、storage、runtime、Live／Replay、restart／gap recovery。
- 工程4: WebSocket／API。
- 工程5: 承認済みstatic mockに従うUI。
- 工程6: integration／performance／soak。
- 工程7: production activation。
- production Manual Min／Maxと初期modeの確定。
- repository全体pytestは工程6で再実行する。工程0の全体baselineは取得済みで、工程2ではBig Trades、config、orderflow全体を実行した。

## changed files

### Source

- `Delta_Engine_Pro4web/src/orderflow/big_trades/__init__.py`
- `Delta_Engine_Pro4web/src/orderflow/big_trades/constants.py`
- `Delta_Engine_Pro4web/src/orderflow/big_trades/time_buckets.py`
- `Delta_Engine_Pro4web/src/orderflow/big_trades/ids.py`
- `Delta_Engine_Pro4web/src/orderflow/big_trades/models.py`
- `Delta_Engine_Pro4web/src/orderflow/big_trades/ordering.py`
- `Delta_Engine_Pro4web/src/orderflow/big_trades/aggregation.py`
- `Delta_Engine_Pro4web/src/orderflow/big_trades/filtering.py`
- `Delta_Engine_Pro4web/src/orderflow/big_trades/calibration.py`
- `Delta_Engine_Pro4web/src/orderflow/big_trades/zone_index.py`
- `Delta_Engine_Pro4web/src/orderflow/big_trades/price_path.py`
- `Delta_Engine_Pro4web/src/orderflow/big_trades/reaction_zones.py`
- `Delta_Engine_Pro4web/src/orderflow/big_trades/horizons.py`
- `Delta_Engine_Pro4web/src/orderflow/big_trades/candle_observer.py`

### Tests

- `Delta_Engine_Pro4web/tests/orderflow/_big_trades_helpers.py`
- `Delta_Engine_Pro4web/tests/orderflow/test_big_trades_ordering.py`
- `Delta_Engine_Pro4web/tests/orderflow/test_big_trades_aggregation.py`
- `Delta_Engine_Pro4web/tests/orderflow/test_big_trades_filtering.py`
- `Delta_Engine_Pro4web/tests/orderflow/test_big_trades_calibration.py`
- `Delta_Engine_Pro4web/tests/orderflow/test_big_trades_ids.py`
- `Delta_Engine_Pro4web/tests/orderflow/test_big_trades_zone_index.py`
- `Delta_Engine_Pro4web/tests/orderflow/test_big_trades_price_path.py`
- `Delta_Engine_Pro4web/tests/orderflow/test_big_trades_reaction_zones.py`
- `Delta_Engine_Pro4web/tests/orderflow/test_big_trades_horizons.py`
- `Delta_Engine_Pro4web/tests/orderflow/test_big_trades_candle_observer.py`

### Checkpoint

- `ArchitectureRepository/00_Master/BIG_TRADES_V2_IMPLEMENTATION_CHECKPOINT_20260812.md`

### 工程2追加／変更

- `Delta_Engine_Pro4web/src/config.py`
- `Delta_Engine_Pro4web/config/config.yaml`
- `Delta_Engine_Pro4web/src/orderflow/big_trades/settings.py`
- `Delta_Engine_Pro4web/src/orderflow/big_trades/activation.py`
- `Delta_Engine_Pro4web/src/orderflow/big_trades/artifacts.py`
- `Delta_Engine_Pro4web/src/orderflow/big_trades/__init__.py`
- `Delta_Engine_Pro4web/src/orderflow/big_trades/aggregation.py`
- `Delta_Engine_Pro4web/src/orderflow/big_trades/calibration.py`
- `Delta_Engine_Pro4web/tests/test_config_big_trades.py`
- `Delta_Engine_Pro4web/tests/orderflow/test_big_trades_activation.py`
- `Delta_Engine_Pro4web/tests/orderflow/test_big_trades_artifacts.py`
- `Delta_Engine_Pro4web/tests/orderflow/test_big_trades_aggregation.py`
- `Delta_Engine_Pro4web/tests/orderflow/test_big_trades_calibration.py`
- `ArchitectureRepository/40_Reference/YAMLReference_v3.4.md`
- `ArchitectureRepository/00_Master/BIG_TRADES_V2_PHASE2_ARTIFACT_EXAMPLES_20260812.md`

## 検証結果

- `python -m pytest tests/orderflow -k big_trades -q`: `67 passed, 195 deselected in 4.48s`。
- `python -m pytest tests/orderflow -q`: `262 passed in 5.88s`。
- 工程2途中target: `148 passed, 229 deselected in 13.30s`。
- 工程2最終`python -m pytest tests/orderflow tests/test_config.py tests/test_config_big_trades.py -q`: `379 passed in 15.82s`。
- randomized oracle: zone boundary index 400 zone × 300 query、source price range 1,000 trade × 300 query、全一致。
- active zone 5,000件保持／明示remove: PASS。
- `python -m compileall -q src/orderflow/big_trades tests/orderflow`: PASS。
- 工程2終了時`python -m compileall -q Delta_Engine_Pro4web/src/orderflow/big_trades Delta_Engine_Pro4web/src/config.py`: PASS。
- `ruff`: 環境にmodule未導入のため未実行。試験失敗ではない。
- protected source SHA-256: 9／9 baseline一致。
- production storage write: 0件。testはpytest temporary directoryだけへartifactを書いた。
- production DB migration: 0件。
- pipeline／API／WebSocket／UI接続: 0件。
- 稼働container restart: 0件。

## blocker

- 工程1: なし、完了。
- 工程2: なし、完了。
- 工程3: なし、isolated temporary DBから開始可能。
- 工程7 activation: production Manual Min／Maxと初期modeの確定が必要。
- 開始前runtimeのmemory RED、syncing、Tape gapはpure coreのblockerではない。工程6／7でbaselineとの差分判定対象とする。

## 次の再開位置

1. 工程2 source、tests、reference、artifact例、checkpointを独立commitへ固定する。
2. V2 instruction §62に従い、新規`src/database/big_trades_schema.py`とisolated temporary DuckDB migrationから工程3を開始する。
3. origin batch atomicity、commit acknowledgement、restart checkpoint、source gap、Live／Replay共通runtimeを実装する。
4. feature flagはfalseのまま維持し、production DBをmigrationしない。
