# DeltaEngine05M Phemex 統合詳細仕様書

**文書ID:** DE05M-PHEMEX-MD-001  
**版:** 1.3-draft  
**作成日:** 2026-08-02  
**対象リポジトリ:** DeltaEngine05M の Phemex 版  
**対象市場:** Phemex USDⓈ-M Perpetual / `BTCUSDT`  
**文書状態:** レビュー待ち・実装未承認  

---

## 改訂履歴

| 版 | 日付 | 内容 |
|---|---|---|
| 1.0-draft | 2026-08-02 | 初版 |
| 1.1-draft | 2026-08-02 | trade identity、板配信間隔、REST rate limit、replay照合、清算依存Hookを具体化 |
| 1.2-draft | 2026-08-03 | Repository Boundary、完成図、Phase停止規則、Definition of Done、変更禁止理由を追加 |
| 1.3-draft | 2026-08-03 | MIXED_EXCHANGE_CONFIG検査条件の限定、Phase 0へのdefault test棚卸し追加、fixture path一本化、snapshot待機buffer暫定値の数値化 |

---

## 0. Repository Boundary — 実装変更許可契約

### 0.1 この章の優先順位

本章は、本書の実装時にCodexその他の実装エージェントが変更できる範囲を固定する。

本章と後続章が衝突する場合、ユーザーの最新の明示指示がない限り本章を優先する。
後続章に要件が書かれていることだけを理由に、変更禁止pathを変更してはならない。

本章に列挙されていないpathは、既定で変更禁止とする。必要性が判明した場合は、理由、対象file、
最小差分、回帰範囲をcheckpointへ記録し、ユーザーの明示承認を得るまで該当変更を行わない。

### 0.2 完成図

#### Before — 現行Binance入力

```text
Binance USDⓈ-M WS/REST
        |
        v
Binance Transport / U-u-pu Sync / forceOrder
        |
        v
Canonical Trade / Book / OI
        |
        v
DeltaEngine Pipeline
        |
        +--> CVD / Footprint / DOM / Tape
        +--> Flow Price Response
        +--> 8 Patterns / Combined Context
        +--> 3段チャート
```

#### After — Phemex入力

```text
Phemex USDT Perpetual WS/REST
        |
        v
src/exchange/phemex/
  Transport / Trade Adapter / Book Adapter / REST / Identity
        |
        v
Canonical Trade / Book / OI
        |
        v
DeltaEngine Pipeline                 ← ここから下の意味を変えない
        |
        +--> CVD / Footprint / DOM / Tape
        +--> Flow Price Response
        +--> 8 Patterns / Combined Context
        +--> 3段チャート
```

変更の本質は、`Binance固有入力境界`を`Phemex固有入力境界`へ差し替えることである。
分析結果をPhemexらしく作り変えることではない。

### 0.3 変更可能path — 新規隔離領域

Phemex固有実装は、原則として次の新規namespaceへ閉じ込める。

```text
Delta_Engine_Pro4web/src/exchange/__init__.py
Delta_Engine_Pro4web/src/exchange/phemex/**
Delta_Engine_Pro4web/tests/exchange/__init__.py
Delta_Engine_Pro4web/tests/exchange/phemex/**
Delta_Engine_Pro4web/config/profiles/phemex.yaml
```

`src/exchange/phemex/`に置く論理責務は以下に限定する。

- public WebSocket transport
- heartbeat、subscribe、reconnect
- public REST client
- Phemex JSON schema validation
- trade batch展開
- source trade identityとsequence epoch
- Phemex snapshot/incremental板adapter
- Phemex OI/product metadata adapter
- Phemex raw/replay adapter
- Phemex固有health metrics

分析、パターン、チャート、売買戦略をこのnamespaceへ複製してはならない。

### 0.4 変更可能path — 既存bridgeの限定例外

次の既存fileは、Phemex境界を既存runtimeへ接続する最小差分に限って変更可能とする。

#### 設定・runtime選択

```text
Delta_Engine_Pro4web/config/config.yaml
Delta_Engine_Pro4web/src/config.py
Delta_Engine_Pro4web/src/pipeline.py
Delta_Engine_Pro4web/docker-compose.yml
```

許可される変更:

- active exchangeをPhemexへ切り替える
- Phemex transport/adapterを注入する
- Phemex専用data rootを選択する
- Binance Spot referenceを無効化する
- Phemex接続状態とavailabilityを伝播する

禁止される変更:

- candle、CVD、Footprint、Flow Price Responseの計算分岐を追加する
- Phemex専用の8パターンを追加する
- 既存window、timeframe、確定条件を変更する
- pipeline全体の無関係な整理、rename、formattingを同時実施する

#### canonical modelの最小拡張

```text
Delta_Engine_Pro4web/src/normalization/normalizer.py
Delta_Engine_Pro4web/src/normalization/__init__.py
```

許可される変更:

- `source_trade_key`、`source_sequence_epoch`、`source_timestamp_ns`等のprovenanceを加算的に追加する
- Phemex nanosecondsを受けるための加算的な型・時刻対応
- 既存Binance profileの挙動を変えないdefault値

禁止される変更:

- Binance side mappingの変更
- 既存trade/depth/liquidation分類の意味変更
- 数量、価格、sideのcanonical意味変更
- Phemex raw JSONをBinance raw JSONへ偽装する処理

#### acquisition共通部

```text
Delta_Engine_Pro4web/src/acquisition/receiver.py
Delta_Engine_Pro4web/src/acquisition/event_queue.py
Delta_Engine_Pro4web/src/acquisition/replay.py
Delta_Engine_Pro4web/src/acquisition/depth_history_recorder.py
```

変更は、Phemexのraw frame保存、exchange adapter注入、fail-closed backpressure、replay入力に
必要な最小差分だけを許可する。Binance transport本体は変更しない。

#### storage・journal

```text
Delta_Engine_Pro4web/src/database/schema.py
Delta_Engine_Pro4web/src/database/storage.py
Delta_Engine_Pro4web/src/observation/raw_journal.py
Delta_Engine_Pro4web/src/observation/capture_coverage.py
```

許可される変更:

- Phemex専用DB manifest
- source trade keyとsequence state
- public REST raw record
- exchange provenance
- 新しいPhemex data root

既存Binance rowのreinterpret、旧DBのin-place migration、旧journalの書換えを禁止する。

#### Phemex source表示・OI

```text
Delta_Engine_Pro4web/webapp/main.py
Delta_Engine_Pro4web/webapp/oi_poller.py
Delta_Engine_Pro4web/webapp/market_poller.py
Delta_Engine_Pro4web/webapp/spot_price_stream.py
Delta_Engine_Pro4web/webapp/push_broker.py
Delta_Engine_Pro4web/webapp/static/index.html
```

許可される変更:

- Phemex source label
- Phemex OI field mapping
- Binance Spot referenceの停止
- connection state
- liquidation `UNAVAILABLE`
- 8パターンのliquidation文脈が推定である旨の説明

`index.html`では文言、source status、availability bindingだけを変更可能とする。チャート構造、DOM構造、
CSS layout、描画algorithm、3段チャートの意味は変更禁止である。

### 0.5 変更可能test

新規Phemex testは次に限定して追加する。

```text
Delta_Engine_Pro4web/tests/exchange/phemex/**
```

bridge変更の接続確認として、次の既存test fileへPhemex test caseを**追加**することは可能である。

```text
Delta_Engine_Pro4web/tests/test_config.py
Delta_Engine_Pro4web/tests/test_live_pipeline.py
Delta_Engine_Pro4web/tests/test_book_resync.py
Delta_Engine_Pro4web/tests/observation/test_observation.py
Delta_Engine_Pro4web/tests/database/test_storage.py
Delta_Engine_Pro4web/tests/database/test_open_interest_storage.py
Delta_Engine_Pro4web/tests/webapp/test_api.py
Delta_Engine_Pro4web/tests/webapp/test_market_poller.py
Delta_Engine_Pro4web/tests/webapp/test_oi_context.py
Delta_Engine_Pro4web/tests/webapp/test_push_broker.py
Delta_Engine_Pro4web/tests/webapp/test_spot_reference_price.py
```

既存test case、既存fixture、既存assertionの削除・緩和・renameは禁止する。既存testが失敗した場合、
testを新挙動へ合わせて書換える前に、production差分が既存契約を破っていないか確認する。

Phemex fixtureは`tests/exchange/phemex/fixtures/**`へ一本化する。`tests/fixtures/phemex/**`は
使用しない。将来、交換所横断の共通fixtureが必要になった場合も、まずPhemex配下へ配置し、
共通化は別途ユーザー承認を得てから行う。

例外として、配布defaultをassertする既存test(例: `tests/test_config.py`の配布config stream
assertion)は、Phase 0の棚卸しでユーザー承認を得た場合に限り、新しい配布default(Phemex)へ
書換えることができる。この場合、旧Binance契約は明示的なBinance fixtureを入力とする別のtest case
として保存し、testの削除・緩和のみで通過させてはならない。

### 0.6 変更禁止path — 完成済み分析中核

次のpathはhard protectedとし、本Phemex統合では変更しない。

```text
Delta_Engine_Pro4web/src/orderflow/**
Delta_Engine_Pro4web/src/heatmap/**
Delta_Engine_Pro4web/src/strategy_contract/**
Delta_Engine_Pro4web/src/strategy_engine/**
Delta_Engine_Pro4web/src/signal/**
Delta_Engine_Pro4web/src/ai/**
Delta_Engine_Pro4web/src/execution/**
Delta_Engine_Pro4web/src/mt5/**
Delta_Engine_Pro4web/src/latency_observer/**
Delta_Engine_Pro4web/webapp/book_projection.py
Delta_Engine_Pro4web/webapp/tape.py
Delta_Engine_Pro4web/webapp/static/footprint_canvas.js
Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js
Delta_Engine_Pro4web/webapp/static/time_sales.js
```

特に次の完成済みfileは、理由を問わず本作業内で変更しない。

```text
Delta_Engine_Pro4web/src/orderflow/flow_price_response.py
Delta_Engine_Pro4web/src/orderflow/combined_context.py
Delta_Engine_Pro4web/src/orderflow/combined_context_runtime.py
Delta_Engine_Pro4web/src/orderflow/cvd.py
Delta_Engine_Pro4web/src/orderflow/footprint.py
Delta_Engine_Pro4web/src/orderflow/flow_detector.py
Delta_Engine_Pro4web/src/orderflow/orderbook.py
Delta_Engine_Pro4web/src/orderflow/absorption.py
Delta_Engine_Pro4web/src/orderflow/imbalance.py
Delta_Engine_Pro4web/src/orderflow/multi_timeframe.py
```

Phemex adapterは、これらが現在受け取っているcanonical contractへ合わせる。
protected側をPhemex raw形式へ合わせてはならない。

### 0.7 変更禁止path — 回帰test・Binance証拠

次は実行対象だが変更禁止である。

```text
Delta_Engine_Pro4web/tests/orderflow/**
Delta_Engine_Pro4web/tests/heatmap/**
Delta_Engine_Pro4web/tests/acquisition/test_binance_ws.py
Delta_Engine_Pro4web/tests/acquisition/test_binance_rest.py
Delta_Engine_Pro4web/tests/normalization/test_normalizer_liquidation.py
Delta_Engine_Pro4web/tests/tools/test_measure_binance_to_ui.py
Delta_Engine_Pro4web/tests/tools/test_observe_hfm_binance.py
Delta_Engine_Pro4web/tests/tools/test_snapshot_binance_futures_klines.py
```

また次のproduction/referenceも変更・削除しない。Phemex active runtimeから呼ばれない状態で保全する。

```text
Delta_Engine_Pro4web/src/acquisition/binance_ws.py
Delta_Engine_Pro4web/src/acquisition/binance_rest.py
Delta_Engine_Pro4web/config/profiles/binance.yaml
Delta_Engine_Pro4web/tests/heatmap/fixtures/real_validation/**
```

Binance forkはユーザーが別途保全するが、現リポジトリ内のBinance testとfixtureも、差分検知と
比較証拠として本統合中は読取専用にする。active runtimeからBinance APIへ通信しないことと、
Binance実装fileを削除することは別問題である。

### 0.8 変更禁止path — データ・履歴・認証

```text
Delta_Engine_Pro4web/data_05M/**
既存Binance DuckDB / Parquet / raw journal / capture manifest
既存Hook較正成果物
既存レポート
.git/**
```

次も禁止する。

- Phemex API key/secretの作成、登録、読込
- testnet/productionへの注文送信
- MT5/HFM実行経路の変更
- Binance履歴のPhemex履歴への変換
- 既存data rootの移動、削除、上書き
- git commit、push、branch削除（個別の明示承認がない限り）

### 0.9 変更禁止の理由

hard protected領域を変更しない理由は以下である。

1. Flow Price Response、3段チャート、8パターン、CVD、Footprintは完成済みである。
2. PhemexとBinanceの差分はtransport、frame adapter、provenance、storage isolationで吸収可能である。
3. 分析中核を同時変更すると、交換所差分と分析差分を切り分けられなくなる。
4. 分析中核まで変更すると回帰対象が入力境界から全戦略・全表示へ広がり、事故範囲が実質的に
   桁違いになる。
5. 既存のBinance test、fixture、較正値は、Phemex版が旧挙動を壊していないことを確認する比較基準である。
6. UI構造を同時変更すると、データ誤りと描画誤りを分離できない。
7. Phemex公開清算feedがないことは、完成済み8パターンを変更する理由にならない。

保護領域のtest失敗は、保護領域を修正する許可ではない。最初にadapterまたはbridgeの契約違反として扱う。

### 0.10 作業開始前checkpoint

実装開始の明示指示を受けた後、最初のproduction変更より前に次を作成・更新する。

```text
ArchitectureRepository/00_Master/PHEMEX_IMPLEMENTATION_CHECKPOINT.md
```

checkpoint必須項目:

- 現在時刻とtimezone
- ユーザーが承認したPhase
- 当該Phaseの変更可能path
- 開始時`git status --porcelain`全文
- 開始前から存在する変更とuntracked file
- hard protected fileのSHA-256 manifest
- 完了済み作業
- 未完了作業
- エージェントが変更したfile
- 実行した検証と結果
- blockerと影響範囲
- 次の再開位置

既存のdirty worktreeをエージェント変更と混同しない。Phase完了時は開始時snapshotとの差分だけを
agent-owned deltaとして報告する。

### 0.11 Phase共通停止規則

- 実装は1 Phaseずつ行う。
- Phase内の安全な作業は、直接blockerがない限り完了まで継続する。
- PhaseのDefinition of Doneを満たしたらcheckpointを更新する。
- checkpoint更新後、次Phaseへ自動進行せず停止する。
- 次Phaseはユーザーの明示的な`GO`を受けてから開始する。
- PhaseのDoDを満たせない場合、未完了を成功扱いせず、再開位置を記録して停止する。
- protected pathが必要になった場合、他の許可済み作業を完了した上で、その変更だけをblockerにする。
- Phaseを跨いだついで変更、rename、cleanup、format-allを禁止する。

### 0.12 Definition of Done — 共通条件

各Phaseは、個別条件に加えて次をすべて満たすまでDoneではない。

1. Phase allowlist外のagent-owned差分が0件。
2. hard protected fileのSHA-256が開始前と一致。
3. 新規・変更Python fileが`python -m compileall`を通過。
4. Phase固有pytestが全件PASS。
5. `git diff --check`相当のwhitespace/error確認がPASS。
6. raw journal、DB、既存data rootを意図せず変更していない。
7. Phemex production/testnetへの注文要求が0件。
8. Binance APIへの新規通信が0件。
9. checkpointにcommand、終了code、PASS/FAIL件数を記録。
10. 未検証項目を`PASS`と表記しない。

#### 品質toolの扱い

2026-08-03時点で、repositoryにはruff/mypy設定fileがなく、`requirements.txt`にもruff/mypy宣言がない。
したがって現時点のDoDでは次のように記録する。

```text
pytest: REQUIRED
compileall: REQUIRED
git diff boundary audit: REQUIRED
ruff: NOT_CONFIGURED
mypy: NOT_CONFIGURED
```

ruff/mypyを未実行のまま`PASS`と書いてはならない。導入は依存関係と全既存fileへ影響するため、
別の明示承認を必要とする。将来正式設定された場合、その時点以降のPhase DoDへ追加する。

### 0.13 Phase 0 — Boundary Lock / Preflight

変更対象はcheckpoint文書だけとし、production codeへ触れない。

Done:

- 本章のallowlist/protected listが実在pathと整合する
- 開始時worktree snapshotを保存する
- protected SHA-256 manifestを保存する
- Python/pytest実行環境を確認する
- public market dataのみでAPI key不要であることを確認する
- Phase 1で作成するfile名をcheckpointへ固定する
- active exchange/normalizerのdefaultをassertする既存testを全件棚卸しする
  (既知の該当例: `tests/test_config.py:99`が配布config.yamlの`btcusdt@trade`、
  `btcusdt@depth@100ms`、`btcusdt@forceOrder`を厳密にassertする。
  `src/config.py:241`のschema defaultが`BINANCE`、normalizer defaultが`binance`である)
- 棚卸し結果を「明示的Binance契約test」と「配布default test」へ分類する
- 変更対象となるtestとassertionの一覧をcheckpointへ記録し、ユーザー承認を得る
- 配布default assertionをPhemexへ変更する承認を得た場合、旧Binance契約を明示的な
  Binance fixtureを入力とする別test caseとして保存する方針をcheckpointへ記録する
- testの削除・緩和のみで既存testを通過させる計画がないことを確認する
- production code差分0件

**Gate:** checkpointを提示して停止。Phase 1へ自動進行しない。

### 0.14 Phase 1 — Phemex Transport

責務:

- WebSocket接続
- `trade_p.subscribe`
- `orderbook_p.subscribe`
- 5秒heartbeat
- 15秒pong timeout
- reconnect/backoff
- ack/error/control message処理

変更可能:

```text
src/exchange/__init__.py
src/exchange/phemex/transport.py
src/exchange/phemex/protocol.py
src/exchange/phemex/errors.py
tests/exchange/__init__.py
tests/exchange/phemex/test_transport.py
tests/exchange/phemex/fixtures/control/**
```

禁止:

- trade正規化
- 板構築
- DB保存
- pipeline接続
- UI変更

Done:

```text
python -m pytest tests/exchange/phemex/test_transport.py -q
python -m compileall -q src/exchange/phemex
```

- subscribe payload、heartbeat、timeout、再接続testがPASS
- network I/Oをmockしたtestで未処理task 0件
- Phase 1 allowlist外差分0件

**Gate:** Phase 1 checkpointを更新して停止。

### 0.15 Phase 2 — Trade Adapter / Identity

責務:

- `trades_p` schema validation
- snapshot/incremental分離
- batch展開
- taker side mapping
- nanoseconds保持
- source trade key
- sequence epochと互換trade ID

変更可能:

```text
src/exchange/phemex/trade_adapter.py
src/exchange/phemex/identity.py
src/exchange/phemex/models.py
src/normalization/normalizer.py（加算的provenanceのみ）
src/normalization/__init__.py（exportのみ）
tests/exchange/phemex/test_trade_adapter.py
tests/exchange/phemex/test_identity.py
tests/exchange/phemex/fixtures/trade/**
```

Done:

```text
python -m pytest tests/exchange/phemex/test_trade_adapter.py tests/exchange/phemex/test_identity.py -q
python -m pytest tests/normalization/test_normalizer.py -q
python -m compileall -q src/exchange/phemex src/normalization
```

- 1,000件snapshotをraw保持し分析へ出さない
- reconnect/replayでsource trade keyが安定
- reset/reuse曖昧時にfail closed
- 既存Binance normalizer testを変更せずPASS
- Phase 2 allowlist外差分0件

**Gate:** Phase 2 checkpointを更新して停止。

### 0.16 Phase 3 — Order Book Adapter

責務:

- initial/periodic snapshot
- incremental level set/delete
- non-contiguous sequence
- waiting snapshot buffer
- queue drop/sync lossのfail closed
- full-depth約120ms既定

変更可能:

```text
src/exchange/phemex/book_adapter.py
src/exchange/phemex/book_state.py
tests/exchange/phemex/test_book_adapter.py
tests/exchange/phemex/fixtures/book/**
```

`src/orderflow/orderbook.py`は変更せず、そのcanonical contractへadapterを合わせる。

Done:

```text
python -m pytest tests/exchange/phemex/test_book_adapter.py -q
python -m pytest tests/orderflow/test_orderbook.py tests/test_book_resync.py -q
python -m compileall -q src/exchange/phemex
```

- snapshot、incremental、quantity 0削除、periodic resetがPASS
- sequenceを`+1`前提にしない
- 50段以上を保持できるfixtureでPASS
- protected orderbook code/test差分0件

**Gate:** Phase 3 checkpointを更新して停止。

### 0.17 Phase 4 — Public REST / OI / Storage Isolation

責務:

- product metadata
- OI/mark/funding poll
- REST rate-limit budget
- Phemex専用data root
- source trade keyとsequence state
- WebSocket/REST raw journal
- DB manifest

変更可能:

```text
src/exchange/phemex/rest.py
src/exchange/phemex/rest_budget.py
src/exchange/phemex/storage_state.py
src/database/schema.py
src/database/storage.py
src/observation/raw_journal.py
src/observation/capture_coverage.py
tests/exchange/phemex/test_rest.py
tests/exchange/phemex/test_storage_state.py
tests/exchange/phemex/fixtures/rest/**
tests/database/test_storage.py（Phemex case追加のみ）
tests/database/test_open_interest_storage.py（Phemex case追加のみ）
tests/observation/test_observation.py（Phemex case追加のみ）
```

Done:

```text
python -m pytest tests/exchange/phemex/test_rest.py tests/exchange/phemex/test_storage_state.py -q
python -m pytest tests/database/test_storage.py tests/database/test_open_interest_storage.py tests/observation/test_observation.py -q
python -m compileall -q src/exchange/phemex src/database src/observation
```

- `data_05M`へのread/write 0件
- Phemex manifest mismatchが起動失敗
- sequence stateとtrade batchが同一transaction
- 429/retry-after/local budget testがPASS
- public REST raw recordがreplay可能な形で保存される

**Gate:** Phase 4 checkpointを更新して停止。

### 0.18 Phase 5 — Replay Determinism

責務:

- liveと同一adapterによるreplay
- session開始epoch/high-water seed
- REST raw response replay
- canonical rolling hash
- final state hash
- first mismatch diff

変更可能:

```text
src/exchange/phemex/replay.py
src/exchange/phemex/digest.py
src/acquisition/replay.py（adapter注入のみ）
src/pipeline.py（replay adapter選択のみ）
tests/exchange/phemex/test_replay.py
tests/exchange/phemex/test_digest.py
tests/exchange/phemex/fixtures/replay/**
```

Done:

```text
python -m pytest tests/exchange/phemex/test_replay.py tests/exchange/phemex/test_digest.py -q
python -m pytest tests/test_pipeline.py tests/heatmap/test_reconstruct.py -q
python -m compileall -q src/exchange/phemex src/acquisition
```

- live/replay count、rolling hash、final book hash一致
- replay中の外部network接続0件
- mismatch時に最初のordinalとfield diffを出力
- protected heatmap/analysis差分0件

**Gate:** Phase 5 checkpointを更新して停止。

### 0.19 Phase 6 — Runtime Wiring / OI / Source Presentation

責務:

- active runtimeをPhemexへ切替
- Phemex config/profile/data root
- OI poller
- Binance Spot reference停止
- venue/availability表示
- `C09`、`E01–E06`の`UNAVAILABLE_INPUT`伝播

変更可能pathは§0.4の設定・runtime、Phemex source表示・OIに列挙したfile、および§0.5の
bridge test追加先だけとする。

Done:

```text
python -m pytest tests/test_config.py tests/test_live_pipeline.py tests/test_book_resync.py -q
python -m pytest tests/webapp/test_api.py tests/webapp/test_market_poller.py tests/webapp/test_oi_context.py tests/webapp/test_push_broker.py tests/webapp/test_spot_reference_price.py -q
python -m compileall -q src webapp
```

- active Phemex processからBinance endpoint通信0件
- UI active sourceにBinance表記0件
- liquidationを0ではなく`UNAVAILABLE`表示
- 8パターンの計算・構造に差分0件
- `index.html`の変更がsource/status/説明文だけ
- Phase 6 allowlist外差分0件

**Gate:** Phase 6 checkpointを更新して停止。

### 0.20 Phase 7 — Protected Regression

Phase 7では新機能追加を行わない。不具合が見つかった場合は、原因となる前Phaseへ戻し、
そのPhase allowlist内だけで修正する。

Done:

```text
python -m pytest tests/orderflow tests/heatmap -q
python -m pytest tests -q
python -m compileall -q src webapp
```

- 全test PASS
- Flow Price Response test差分0件
- combined context/8 patterns test差分0件
- Footprint/CVD/orderbook test差分0件
- hard protected SHA-256完全一致
- agent-owned allowlist外差分0件
- Git staging/commit/push 0件

**Gate:** 完全な回帰結果とdiff inventoryを提示して停止。

### 0.21 Phase 8 — Public Data Evidence / 72-hour Capture

Phase 8はpublic market dataの検証であり、注文APIを使用しない。長時間処理開始前にcheckpointを更新する。

検証対象:

- sequence monotonicity/reset/reuse
- batch件数分布と最大値
- full-depth約120ms負荷
- queue drop/sync loss
- raw journal容量
- OI更新特性
- live/replay digest一致

Done:

- 72時間のraw WebSocket/REST captureが完了
- capture中のqueue drop 0件
- raw journal欠損0件
- 未処理例外0件
- 各closed sessionのlive/replay digestが一致
- sequence、batch、負荷、容量の実測reportを保存
- Phemex thresholdをBinance値でCALIBRATED扱いしていない

72時間capture完了はthreshold較正の承認ではない。較正とproduction注文は別の明示指示を必要とする。

**Gate:** 実測reportを提示して停止。自動的に較正・注文実装へ進まない。

### 0.22 最終完了条件

Phemex市場データ統合の実装完了は、Phase 0からPhase 8のcheckpointとDoDがすべて成立し、
ユーザーが最終結果を承認した時点とする。

次は完了に含まれない。

- Phemex実注文
- Phemex API key/secret
- Phemex Spot参照
- liquidation推測feed
- Phemex threshold較正
- protected分析機能の改修

---

## 1. 文書の目的

本書は、現在 Binance USDⓈ-M を市場データ入力元としている DeltaEngine05M を、
Phemex USDⓈ-M Perpetual の `BTCUSDT` 入力へ置き換えるための詳細仕様を定義する。

本書の中心は市場データ入力であり、Phemexへの実注文発注は対象外とする。
注文執行に必要となる境界条件は将来拡張として記録するが、本仕様の受入条件には含めない。

ユーザーが別forkとして保存するBinance版は保全対象である。本リポジトリ側では、実行時の
Binance依存をPhemexへ置き換える。単純な文字列置換ではなく、交換所固有処理を入力境界に
閉じ込め、完成済みの分析ロジックを維持する。

---

## 2. 最優先の設計原則

### 2.1 完成済み機能を変更しない

以下の意味、計算方法、表示構造を変更してはならない。

- Flow Price Response
- 3段チャート
- 8パターン判定
- CVD
- Footprint
- DOM
- Tape
- OI表示
- 既存の確定足、進行足、window集計の境界

交換所固有の差異は、取得、検証、正規化、保存元情報の範囲で吸収する。

### 2.2 Phemex版とBinance版を混在させない

Phemex版の実行プロセスからBinance APIへ接続してはならない。
Phemex版のDB、Parquet、raw journal、閾値、較正結果にBinance由来データを混入させてはならない。

### 2.3 推測値を作らない

Phemex公開APIから取得できない値を、別データから推測して既存項目へ投入してはならない。
特に市場全体の清算約定を、通常約定、大口約定、OI低下、価格急変から合成してはならない。

### 2.4 異常時はfail closedとする

板同期、データ欠損、形式不正、時刻異常、保存失敗を検出した場合、古い値を正常値として
流し続けてはならない。該当機能を `STALE` または `UNAVAILABLE` とし、再同期完了まで分析入力を
停止する。

---

## 3. スコープ

### 3.1 対象

- Phemex公開WebSocketへの接続
- `BTCUSDT` の公開約定購読
- `BTCUSDT` の公開板購読
- Phemex公開RESTからの商品仕様取得
- Phemex公開RESTからのOI・mark price・funding関連値の取得
- Phemexメッセージから既存canonical modelへの正規化
- raw journalとreplayのPhemex対応
- Phemex専用ストレージへの保存
- Phemexソースとしてのwarm start
- UI、状態表示、データソース表記のPhemex化
- Hookと閾値のPhemex用隔離
- 既存分析機能の回帰確認

### 3.2 対象外

- Phemexへの実注文発注
- APIキー、API Secretの登録
- Phemex口座、残高、ポジションの取得
- Binanceとの同時購読
- Binanceをfallback接続先として残すこと
- Binance/Phemex間の裁定分析
- Phemex Spotを使った参照価格
- 清算データの推測生成
- Flow Price Response、3段チャート、8パターンの再設計
- 過去のBinanceデータをPhemexデータへ変換すること

---

## 4. 外部仕様の基準

実装時点の正式な基準はPhemex公式API Referenceとする。

- API Reference: <https://phemex-docs.github.io/>
- 公開REST: `https://api.phemex.com`
- 公開WebSocket: `wss://ws.phemex.com`
- Testnet REST: `https://testnet-api.phemex.com`
- Testnet WebSocket: `wss://testnet-api.phemex.com/ws`

2026-08-02確認時点の公開WebSocket制約は以下である。

- 1クライアント最大5接続
- 1接続最大20購読
- 1接続最大20 request/second
- 公開WebSocketはIP単位で200 connection/5 minutes
- heartbeat間隔は30秒未満
- 推奨heartbeat間隔は5秒
- 3 heartbeat期間応答がなければ能動的に再接続

外部仕様が本書と異なる場合は、差異を記録してユーザー承認を得るまで挙動を変更しない。

---

## 5. 対象商品と商品メタデータ

### 5.1 固定識別子

| 項目 | 値 |
|---|---|
| exchange | `PHEMEX` |
| market type | `USDT_PERPETUAL` |
| symbol | `BTCUSDT` |
| base asset | `BTC` |
| quote asset | `USDT` |
| settle currency | `USDT` |
| canonical timeframe | `05M` |

### 5.2 起動時検証

公開REST `GET /public/products` の `perpProductsV2` から `BTCUSDT` を検索し、少なくとも
以下を検証する。

- 商品が存在する
- 商品状態が取引可能である
- settlement currencyが`USDT`である
- price tickが正の値である
- quantity stepが正の値である
- price precisionとquantity precisionが解釈可能である

確認済み参考値は以下だが、実行時はAPI応答を正とする。

| 項目 | 2026-08-02確認値 |
|---|---:|
| tick size | `0.1` |
| quantity step | `0.001` |
| quantity precision | `3` |

設定値とAPI値が不一致の場合は起動を継続せず、`PRODUCT_SPEC_MISMATCH` とする。
自動的なtick size変更によって既存集計を継続してはならない。

---

## 6. 全体コンポーネント境界

```text
Phemex Public WS/REST
        |
        v
Phemex Transport
  - connect / subscribe / heartbeat / reconnect
        |
        +------> Raw Journal（受信フレームを無加工保存）
        |
        v
Phemex Frame Adapter
  - schema validation
  - batch expansion
  - snapshot/incremental state
  - sequence metadata
        |
        v
Canonical Normalizer
  - NormalizedTrade
  - OrderBookUpdate
  - OI sample
        |
        v
既存DeltaEngine Pipeline
  - CVD / Footprint / Flow Price Response
  - 8 patterns / 3段チャート / DOM / Tape / OI
```

`Phemex Transport` と `Phemex Frame Adapter` より下流では、Phemex固有のJSONキーを
直接参照してはならない。

---

## 7. WebSocket接続仕様

### 7.1 接続先

```text
wss://ws.phemex.com
```

追加URI、query string、APIキーを使用しない。

### 7.2 購読要求

約定購読:

```json
{
  "id": 1001,
  "method": "trade_p.subscribe",
  "params": ["BTCUSDT"]
}
```

板購読:

```json
{
  "id": 1002,
  "method": "orderbook_p.subscribe",
  "params": ["BTCUSDT", true, 0]
}
```

板の第2引数は約120ms集約配信を指定する `true`、depthは全板を指定する `0` とする。
Phemex公式仕様では`false`が約20ms、`true`が約120msである。現行DeltaEngineのBinance板入力が
100msであり、交換所置換時に時間解像度を無断変更しないため、約120msを既定値とする。
既存DOMが50段を要求するため、30段購読を既定値にしてはならない。

約20ms配信は性能比較用の明示設定としてのみ許可する。20msをproduction既定値へ変更するには、
本書の性能・no-loss受入条件を20ms条件で満たした実測記録とユーザー承認を必要とする。

### 7.3 購読確認

各要求について、同一`id`を持つ応答を照合する。

正常条件:

```json
{
  "error": null,
  "id": 1001,
  "result": {"status": "success"}
}
```

`error`がnullでない、`status`が`success`でない、または規定時間内に応答がない場合は
購読未成立とし、市場データを`LIVE`扱いしない。

### 7.4 heartbeat

5秒ごとに次を送信する。

```json
{
  "id": 0,
  "method": "server.ping",
  "params": []
}
```

次の応答をpongとして認識する。

```json
{
  "error": null,
  "id": 0,
  "result": "pong"
}
```

15秒以上pongを受信できない場合、接続を`STALE`にして再接続する。
通常の市場データ受信だけをpongの代用にしてはならない。

### 7.5 再接続

再接続待機は指数backoffとjitterを使用し、基準値を以下とする。

- 初回: 1秒
- 最大: 30秒
- 正常受信が60秒継続したらbackoffを初期化
- 同時に存在する市場データ接続は1本
- 古い接続のtask、timer、subscription stateを確実に破棄

再接続後は、以前の板状態を継続利用してはならない。新しいsnapshotを受信して適用するまで
板、DOM、heatmapのlive更新を`STALE`とする。

---

## 8. 約定メッセージ仕様

### 8.1 受信形式

```json
{
  "sequence": 77702250,
  "symbol": "BTCUSDT",
  "trades_p": [
    [1666856076819029800, "Sell", "20700.3", "0.649"]
  ],
  "type": "incremental"
}
```

`trades_p`の1行は次の順序とする。

| index | 意味 | canonical型 |
|---:|---|---|
| 0 | 約定時刻（nanoseconds） | integer |
| 1 | taker side | enum |
| 2 | price | Decimal |
| 3 | quantity | Decimal |

### 8.2 検証条件

以下を満たさない行はcanonical tradeへ流さない。

- `symbol == BTCUSDT`
- `sequence`が非負整数
- `type`が`snapshot`または`incremental`
- 行の要素数が4
- timestampが正の整数
- sideが`Buy`または`Sell`
- priceが有限かつ0より大きいDecimal
- quantityが有限かつ0より大きいDecimal
- priceが商品tick sizeに整合する
- quantityが商品quantity stepに整合する

不正行はraw frameと理由をquarantine記録し、黙って補正しない。

### 8.3 side変換

Phemexのsideはtaker sideとして扱う。

| Phemex | canonical aggressor side | CVD符号 |
|---|---|---:|
| `Buy` | `BUY` | 正 |
| `Sell` | `SELL` | 負 |

Binanceの`m`フラグ変換をPhemexメッセージへ適用してはならない。

### 8.4 batch展開

1フレーム内の`trades_p`を配列順に0からindex付与し、1行につき1件の
`NormalizedTrade`へ展開する。配列順を価格、時刻、sideで並べ替えてはならない。

元フレームは展開前にraw journalへ1回だけ保存する。展開後イベントには、元フレームを
追跡できる`session_id`、`frame_ordinal`、`sequence`、`batch_index`を付与する。

### 8.5 snapshotの扱い

接続直後に配信される`type=snapshot`の約定履歴はraw journalへ保存するが、live分析、DBの
通常約定、Tape、CVD、Footprintへ投入しない。

理由は、snapshotが過去約定を含み、再接続のたびに重複するためである。
2026-08-02の実受信確認では1フレームに1,000件のsnapshot約定が含まれたため、公式例の
件数を固定上限として実装してはならない。

snapshotを受信した件数は`trade_snapshot_rows_ignored_total`へ記録する。

### 8.6 trade identity

Phemex公開`trades_p`には個別trade IDがない。また、公式仕様は`sequence`をlatest message sequenceと
説明しているが、取引所の全稼働期間を通じた一意性、永続的な単調増加、resetや再利用がないことを
保証していない。そのため`(sequence << 12) | batch_index`を永続主キーとしてはならない。

#### 8.6.1 正本となる複合キー

1約定の正本identityを次の複合キーとする。

```text
source_trade_key = (
    exchange,
    market_type,
    symbol,
    sequence_epoch,
    sequence,
    batch_index
)
```

文字列表現は次とする。

```text
PHEMEX:USDT_PERPETUAL:BTCUSDT:<sequence_epoch>:<sequence>:<batch_index>
```

`source_trade_key`をDBの一意性、dedup、replay照合の正本とする。

#### 8.6.2 session IDの扱い

`session_id`は受信経路とraw frameの追跡専用とし、論理約定identityへ含めない。
session IDをidentityへ含めると、再接続またはreplayのたびに同じ約定が別IDになり、重複排除が
できなくなるためである。

#### 8.6.3 sequence epoch

`sequence_epoch`はPhemex sequenceのresetまたは再利用を隔離する、Phemex・market type・symbol単位の
永続整数である。初期値を0とし、DBのsource sequence stateへ次をatomic保存する。

- current sequence epoch
- last accepted incremental sequence
- last accepted incremental source timestamp ns
- last accepted source trade key
- 更新時application commitとnormalizer profile version

trade snapshotのsequenceは履歴値であり、high-water markまたはepoch判定に使用しない。

#### 8.6.4 runtime単調性検証

新しいincremental frameを受信した場合、次の順で判定する。

1. `sequence > persisted_high_water`なら現在epochの候補として処理する。
2. 現在epochに同じsource trade keyが存在し、全約定内容も一致する場合は再送として無視する。
3. 同じsource trade keyでtimestamp、side、price、quantityのいずれかが異なる場合は
   `TRADE_ID_COLLISION`として停止する。
4. `sequence <= persisted_high_water`かつsource timestampが最終受理時刻以前なら、重複または
   過去再送候補としてbufferし、既存記録との一致を確認する。
5. `sequence <= persisted_high_water`である一方、source timestampが最終受理時刻より新しい場合は
   reset候補とし、直ちに受理しない。

reset候補は最大3 incremental frame、最長30秒を隔離bufferへ保持する。3 frameのsequenceが候補epoch内で
厳密増加し、timestampが非減少かつ旧epochの最終時刻より新しい場合にreset確認とし、
`sequence_epoch`を1増加させてbufferを受信順に受理する。

規定時間内に確認できない、同一sequenceで異なるframeが来る、sequenceとtimestampが矛盾する場合は
`TRADE_SEQUENCE_AMBIGUOUS`としてfail closedにする。session開始だけを理由にepochを増加させてはならない。

#### 8.6.5 既存整数trade IDとの互換

既存pipeline互換の整数`trade_id`が必要な場合、source trade keyのUTF-8 bytesから決定的な
63-bit BLAKE2b digestを生成し、正のsigned 64-bit整数として渡す。

```text
compat_trade_id = blake2b_64(source_trade_key_utf8) & 0x7FFF_FFFF_FFFF_FFFF
```

digest結果が0の場合は互換値1へ写像し、source trade keyによる衝突照合を通常どおり実施する。
整数IDは互換値であり、永続一意性の正本ではない。DBにはsource trade keyの全構成要素も保存し、
同じ整数IDに異なるsource trade keyが対応した場合は`TRADE_ID_COLLISION`として停止する。
乱数、Python processごとに変化する`hash()`、session依存値を使用してはならない。

#### 8.6.6 batch制約

- `0 <= batch_index < 4096`
- 同じraw frameをreplayした場合に同じsource trade keyになる
- 4,096件を超えるbatchは自動的にindex幅を変えず、`TRADE_BATCH_LIMIT_EXCEEDED`として隔離する
- snapshotのbatch indexはraw追跡に残すがlive trade identityとしてDB投入しない

### 8.7 時刻

Phemex timestampはUnix epoch nanosecondsとして解釈する。

- `source_timestamp_ns`: 元の整数を無損失保存
- `event_time`: UTCへ変換
- `received_time`: アプリケーション受信時刻UTC
- `ingested_time`: 永続化処理時刻UTC

既存datetimeの精度がmicrosecondsの場合でも、`source_timestamp_ns`を捨ててはならない。
同一microsecond内の順序は`sequence_epoch`、`sequence`、`batch_index`で決定する。

---

## 9. 板メッセージ仕様

### 9.1 受信形式

```json
{
  "sequence": 77702250,
  "symbol": "BTCUSDT",
  "type": "incremental",
  "timestamp": 1666856076819029800,
  "orderbook_p": {
    "bids": [["20699.9", "1.250"]],
    "asks": [["20700.0", "0"]]
  }
}
```

quantity `0`は、その価格レベルの削除を意味する。

### 9.2 canonical変換

| Phemex | canonical |
|---|---|
| `type=snapshot` | `OrderBookUpdateType.SNAPSHOT` |
| `type=incremental` | `OrderBookUpdateType.DIFF` |
| `sequence` | `final_update_id` |
| adapterが保持する直前の板sequence | `previous_final_update_id` |
| `bids` | bid updates |
| `asks` | ask updates |

Phemex sequenceはチャネルごとの連番ではないため、`current == previous + 1`を要求してはならない。
tradeとbookに同じsequenceが現れる場合があるため、直前値は板チャネル単位で保持する。

### 9.3 初期同期

- 接続開始時の板状態は`WAITING_SNAPSHOT`
- snapshot以前にincrementalを受信した場合はbounded bufferへ保存
- 最初の有効snapshotをatomicに適用
- snapshotより古いbuffer要素を破棄
- snapshotより後に受信したbuffer要素を受信順に適用
- 適用完了後に`LIVE`へ遷移

buffer上限はメッセージ数とbyte数の両方で設定する。上限超過時は全bufferを破棄して
再接続し、部分板を構築してはならない。

暫定初期値を次とする。Phase 8の実測後に見直す。

```text
pre_snapshot_max_messages: 128
pre_snapshot_max_bytes: 16777216
snapshot_wait_timeout_sec: 10
overflow_action: FAIL_CLOSED_RECONNECT
```

根拠: 約120ms配信では128 messageは約15秒分に相当する。Phemexは購読成功後にsnapshotを
配信するため、10秒以内にsnapshotが到着しない場合はbuffer拡張ではなく再接続する。
既存Binanceの`max_buffered_diffs=100000`はREST snapshot取得中のBinance同期用の値であり、
Phemexのpre-snapshot bufferへ流用してはならない。

### 9.4 定期snapshot

Phemexからlive中にsnapshotが配信された場合、異常とは扱わない。現在の板をsnapshot内容で
atomic置換し、そのsnapshot sequenceを新しい基準値にする。

### 9.5 欠損検知

数値の非連続だけでは欠損と判断しない。以下を欠損または同期喪失とする。

- 内部queueが1件以上dropした
- frameのJSON/schema検証に失敗した
- incremental適用に失敗した
- adapterが付けた`previous_final_update_id`とbook managerの最終値が一致しない
- WebSocketが切断した
- snapshot適用前にbuffer上限を超えた
- price/quantityが不正

同期喪失時はbookを`STALE`にし、再接続後のsnapshotまで復帰させない。

### 9.6 DOM出力

内部では全板を保持し、UIへはbest bid/best askから各50段を投影する。
50段未満しか存在しない場合は存在する段だけを返し、0数量の架空レベルを生成しない。

spreadが負、best bidがbest ask以上、price levelがtick size不整合の場合は板を正常扱いしない。

---

## 10. OI・mark price・funding仕様

### 10.1 取得元

```text
GET https://api.phemex.com/md/v3/ticker/24hr?symbol=BTCUSDT
```

最低限使用する項目:

| Phemex field | DeltaEngine用途 |
|---|---|
| `symbol` | 商品照合 |
| `openInterestRv` | OI値 |
| `markRp` | mark price |
| `fundingRateRr` | funding rate |
| `predFundingRateRr` | predicted funding rate（存在時） |
| `timestamp` | source time nanoseconds |

### 10.2 polling

- 標準間隔: 10秒
- 同時リクエスト: 1
- timeout: 5秒
- OI要求上限: 6 requests/minute
- Phemex公開REST全体のlocal上限: 30 weighted requests/minute
- HTTP 429ではrate limitを尊重してbackoff
- HTTP 5xx、timeout、parse errorでは直前値を新しい値として再保存しない
- 3回連続失敗でOIを`STALE`
- 正常応答1回で復帰可能

Phemex公式の一般REST制限は、IP単位で5,000 requests/5 minutes、`Others`グループで
100 requests/minuteである。10秒pollingは6 requests/minuteであり、この一般上限内に収まる。
ただし、商品情報取得その他のPhemex REST要求とbudgetを共有し、endpoint固有weightを0または1と
決め打ちしてはならない。

応答headerから次をcase-insensitiveに読み取り、ログとmetricsへ保存する。

- `x-ratelimit-remaining-<groupName>`
- `x-ratelimit-capacity-<groupName>`
- `x-ratelimit-retry-after-<groupName>`
- Others groupでsuffixが省略された同等header

`retry-after`がある場合はその値を優先する。headerが存在しない公開endpointでも、local token bucketを
無効化してはならない。仕様変更で公式上限またはendpoint weightが不明になった場合は、10秒間隔を
短縮せず`REST_RATE_LIMIT_UNKNOWN`を記録する。

### 10.3 保存

```text
source = PHEMEX_USDT_PERP
symbol = BTCUSDT
source_time = timestamp(nsからUTCへ変換)
open_interest = Decimal(openInterestRv)
received_time = local UTC receive time
```

Binance OIと単位や分布が同一であると仮定しない。過去Binance OIとの連結、差分計算、
同一系列表示を禁止する。

---

## 11. 清算データ仕様

Phemex公開市場データには、Binance USDⓈ-M `@forceOrder`と同等の市場全体清算ストリームを
確認できない。そのためPhemex版では次を必須とする。

- liquidation source stateを`UNAVAILABLE`とする
- 数値`0`を「清算なし」の意味で生成しない
- 通常約定を清算約定として分類しない
- OI低下を清算数量へ変換しない
- 清算依存Hookをfail closedとする
- UIには`Phemex public feed unavailable`相当を表示する
- replayでも架空の清算イベントを生成しない

将来、Phemexが正式な公開清算feedを提供した場合は、別仕様の承認を必要とする。

### 11.1 現行コードの直接依存Hook一覧

2026-08-02の現行コード棚卸しで、Binance `forceOrder`由来の`LiquidationEvent`へ直接依存するHookは
次の7件と確認した。

| Hook ID | registry name | 直接入力 | Phemex版状態 | 動作 |
|---|---|---|---|---|
| `C09` | `liquidation_absorbed` | liquidation、吸収side、応答価格 | `DISABLED_UNAVAILABLE` | candidateを生成しない |
| `E01` | `large_long_liquidation` | forced SELLのprice・quantity | `DISABLED_UNAVAILABLE` | candidateを生成しない |
| `E02` | `large_short_liquidation` | forced BUYのprice・quantity | `DISABLED_UNAVAILABLE` | candidateを生成しない |
| `E03` | `long_liquidation_cascade` | forced SELLのwindow集計 | `DISABLED_UNAVAILABLE` | candidateを生成しない |
| `E04` | `short_liquidation_cascade` | forced BUYのwindow集計 | `DISABLED_UNAVAILABLE` | candidateを生成しない |
| `E05` | `liquidation_no_price_response` | liquidation後の価格応答 | `DISABLED_UNAVAILABLE` | candidateを生成しない |
| `E06` | `liquidation_exhaustion` | liquidation間quiet gap | `DISABLED_UNAVAILABLE` | candidateを生成しない |

根拠となる現行実装は以下である。

- `src/orderflow/hooks/liquidation.py`: `E01`から`E06`
- `src/orderflow/hooks/interaction.py`: `C09`
- `src/orderflow/hooks/registry.py`: Hook IDと名称
- `tools/calibrate_hooks.py`: `C09`、`E01`から`E06`をliquidation必須として較正対象外にしている

これら7件は`UNCALIBRATED`ではなく、入力feed自体が存在しない`UNAVAILABLE_INPUT`として扱う。
thresholdを仮設定してenableにしてはならない。

### 11.2 清算feedに関係する非Hook経路

次の経路もPhemex版で明示的に`UNAVAILABLE`へ切り替える。

- acquisitionの`forceOrder`購読とevent filter
- normalizerの`LiquidationEvent`生成
- live pipelineのliquidation buffer、counter、callback
- raw journalのliquidation専用captureとcoverage
- WebSocket pushの`LIQUIDATION` envelope
- UIの`LIQUIDATION` series
- liquidation capture downtime、benchmark、live verify関連tool

Phemex版でこれらを削除するか停止状態として残すかは実装上選択できるが、active runtimeが
「購読済み」「正常」「0件」と誤表示してはならない。

### 11.3 8パターン内の名称との区別

既存combined contextにある`LONG-LIQUIDATION LEG`および`LONG LIQUIDATION`は、公開清算feedを
直接入力とするHookではない。価格・CVD・deltaの8パターンとOIの`UNWINDING`を組み合わせた
文脈名称であるため、Phemex OIが正常なら既存ロジックを維持する。

ただしUI説明には「OIとフローから推定したポジション解消文脈であり、公開清算feedによる確認ではない」
ことを表示し、E系liquidation Hookの観測結果と混同させない。

---

## 12. raw journal仕様

### 12.1 保存単位

WebSocketから受信したJSONフレームを、batch展開やキー変換より前に1フレーム1レコードで保存する。

必須metadata:

| field | 内容 |
|---|---|
| `exchange` | `PHEMEX` |
| `market_type` | `USDT_PERPETUAL` |
| `symbol` | `BTCUSDT` |
| `channel` | `trade_p`, `orderbook_p`, `control`, `unknown` |
| `message_type` | `snapshot`, `incremental`, `ack`, `pong`, `error`, `unknown` |
| `session_id` | 接続ごとのUUID |
| `frame_ordinal` | session内の受信連番 |
| `sequence` | 存在時のPhemex sequence |
| `source_timestamp_ns` | 存在時のPhemex時刻 |
| `received_at_utc` | 受信時刻 |
| `payload` | 元JSON |

raw journalのsession manifestには、replay開始状態として次を記録する。

- `sequence_epoch_at_open`
- `incremental_high_water_at_open`
- `last_source_timestamp_ns_at_open`
- source sequence state rowのhash
- 起動時product metadata応答のraw record IDとSHA-256

replayは空DBへこの開始状態をseedしてからframeを処理する。replay実行時の既存DB stateやsession IDを
使ってepochを再採番してはならない。

### 12.1.1 公開REST raw record

OIを含むlive/replay同値性のため、分析入力に使用した公開REST応答もraw journalへ保存する。

対象:

- `GET /public/products`
- `GET /md/v3/ticker/24hr?symbol=BTCUSDT`
- 将来、分析入力として追加承認された公開REST endpoint

必須metadata:

- request methodとpath
- secretを含まないquery parameters
- HTTP status
- rate-limit response headers
- received_at_utc
- response bodyの元bytesまたは無加工text
- response body SHA-256
- poll ordinal

replay時は外部RESTへ再接続せず、この保存済み応答をpoll ordinal順に使用する。

### 12.2 保存原則

- 元JSONの数値をfloatへ変換してから保存しない
- `trades_p`配列を分割して元frameを失わない
- snapshotも保存する
- control messageも保存する
- parse不能frameもraw bytesまたは元textとエラー理由をquarantineへ保存する
- API keyやsecretは存在しない前提だが、将来追加されてもjournalへ保存しない

### 12.3 replay同値性

同じraw journalをreplayした場合、次がlive処理と一致しなければならない。

- 発生するcanonical trade件数
- source trade keyと互換trade ID
- event time
- side、price、quantity
- snapshot約定の除外件数
- book snapshot/diff順序
- 最終order book
- candle、CVD、Footprint、Flow Price Responseの結果

liveだけでbatch展開し、replayでは展開しない実装を禁止する。

### 12.4 replay検証artifact

live処理はraw journalのsessionをcloseする際、比較用の`live_digest_manifest.json`を生成する。
replayは空の一時Phemex DBへ同じclosed journalを投入し、`replay_digest_manifest.json`を生成する。

#### 12.4.1 canonical serialization

hash入力は次の規則で決定的にserializeする。

- UTF-8
- object keyを辞書順
- 不要な空白なし
- Decimalは指数表記を避けた正規化文字列
- enumはcanonical value
- source timeはnanoseconds整数
- array順序は保持
- nullとfield欠落を区別

次の非決定値は計算結果の同値hashから除外し、別の観測hashへ分離する。

- `session_id`
- `received_time`
- `ingested_time`
- process ID
- connection ID
- ping RTT、network latency
- ローカル一時path

分析計算が非決定値へ依存していることが判明した場合、単に除外して合格させず、
`NON_DETERMINISTIC_ANALYTICS_INPUT`として不合格にする。

#### 12.4.2 rolling hash

streamごとに次のrolling SHA-256を計算する。

```text
H0 = SHA256(document_id || schema_version || normalizer_profile_version)
Hn = SHA256(H(n-1) || 0x0A || canonical_record_bytes)
```

対象stream:

- canonical trades
- canonical book updates
- 5分足
- CVD/delta
- Footprint
- Flow Price Response
- 8-pattern/combined context
- DOM projection
- OI samples
- Hook candidates（enable対象のみ）

#### 12.4.3 state hash

stream hashに加え、次の最終状態を安定順序でhash化する。

- bidをprice降順、askをprice昇順にした最終全板
- DB各tableを正規主キー順に並べたrow集合
- 最終確定5分足
- Phemex storage manifestのsemantic field

state hashでは`created_at`、`updated_at`、一時path、process/session識別子を除外し、exchange、schema、
商品仕様、normalizer version、threshold hash、sequence state等のsemantic fieldだけを比較する。

#### 12.4.4 比較結果

検証toolは最低限次を出力する。

- streamごとのlive/replay件数
- streamごとのlive/replay hash
- first/last source trade key
- first/last book sequence
- snapshot trade除外件数
- 最初に不一致となったstreamとordinal
- field-level JSON diffへのpath
- final result `MATCH`または`MISMATCH`

不一致時は終了コードを非0とする。hashだけを出して原因箇所を失ってはならない。

---

## 13. queue・backpressure・no-loss仕様

### 13.1 原則

市場データ欠損を無表示で継続してはならない。queue overflow時にoldestをdropして正常継続する
挙動は禁止する。

### 13.2 必須動作

- raw frame受信数を計測
- journal投入数を計測
- canonical展開数を計測
- downstream投入数を計測
- queue depthとhigh-water markを計測
- drop発生時は該当ストリームを`STALE`
- book drop時はsnapshot再同期
- trade drop時はlive分析を停止し、接続sessionを更新して再開
- drop区間を通常の連続データとして5分足へ混ぜない

raw journal自体の保存に失敗した場合、no-loss保証が失われるためプロセスhealthを`DEGRADED`ではなく
`FAILED`とする。

---

## 14. canonical trade仕様

Phemex adapterから既存pipelineへ渡す1約定の論理項目を以下とする。

| field | 値 |
|---|---|
| `exchange` | `PHEMEX` |
| `market_type` | `USDT_PERPETUAL` |
| `symbol` | `BTCUSDT` |
| `source_trade_key` | §8.6の複合キー文字列表現 |
| `trade_id` | source trade keyから得る決定的63-bit互換ID |
| `event_time` | source nanosecondsからUTC変換 |
| `price` | Decimal |
| `quantity` | Decimal |
| `aggressor_side` | `BUY` / `SELL` |
| `is_liquidation` | unknownではなく、項目を使用しない／source unavailable |
| `source_sequence_epoch` | 永続sequence epoch |
| `source_sequence` | Phemex sequence |
| `source_batch_index` | 配列index |
| `source_timestamp_ns` | 元timestamp |
| `received_time` | UTC |

price、quantity、notional計算の途中でbinary floatを使用してはならない。

---

## 15. ストレージ分離仕様

### 15.1 物理分離

Phemex版の既定rootを次のようにする。

```text
data_phemex_05M/
  duckdb/
    orderflow_phemex_05M.duckdb
  parquet/
  raw/
  quarantine/
  hooks/
  monitor/
```

既存の`data_05M`をPhemex版の書込先またはwarm start元に使用してはならない。

### 15.2 warm start

- Phemex専用DuckDBだけを照会する
- `symbol=BTCUSDT`だけで旧Binance DBを探索しない
- database manifestの`exchange=PHEMEX`を検証する
- manifestがない旧DBを自動的にPhemex DBとして採用しない
- mismatch時は空状態で継続せず、明示的に起動失敗とする

### 15.3 manifest

最低限以下を記録する。

- schema version
- exchange
- market type
- symbol
- tick size
- quantity step
- created_at
- application commit
- normalizer profile version
- threshold config hash
- current sequence epoch

### 15.4 source sequence state

tradeのsequence epochとhigh-water markは、file manifestではなくPhemex DB内の専用state rowを正本とする。

複合主キー:

```text
(exchange, market_type, symbol, channel)
```

必須field:

- `sequence_epoch`
- `last_incremental_sequence`
- `last_source_timestamp_ns`
- `last_source_trade_key`
- `updated_at_utc`
- `normalizer_profile_version`

trade batchの永続化とsource sequence stateの更新を同一transactionでcommitする。どちらか一方だけを
commitしてはならない。clean shutdown時のmanifestにはstateのcopyを記録するが、再開時の正本は
DB transaction stateとする。

---

## 16. 閾値・Hook・較正仕様

Binanceの72時間journalで作成されたthresholdをPhemexで`CALIBRATED`として使用してはならない。

Phemex版でvenue依存として隔離する対象:

- large trade minimum quantity
- sweep quantity、window、levels
- imbalance minimum volume
- absorption volume referenceとmultiplier
- DOM wall判定
- iceberg/refill判定
- wall consumption比率
- trade notional閾値
- execution-cost observation閾値
- Hook threshold全般

初期状態:

```text
exchange: PHEMEX
calibration_status: UNCALIBRATED
execution_enabled: false
```

清算直接依存Hookは例外として、次の状態を使用する。

```text
hook_ids: [C09, E01, E02, E03, E04, E05, E06]
input_status: UNAVAILABLE_INPUT
calibration_status: NOT_APPLICABLE_WITHOUT_INPUT
execution_enabled: false
```

未較正Hookは判定値を推測せず、fail closedとする。
閾値の再較正は別途明示承認を必要とする。

保存フィールド名に`binance_bid`、`binance_ask`、`binance_mid`がある場合、Phemexデータをその名で
保存してはならない。新規Phemex保存領域では`venue_bid`、`venue_ask`、`venue_mid`等の中立名、
または明示的な`phemex_*`名を使用する。

---

## 17. 設定仕様

Phemex版の論理設定値を以下とする。実際のYAML構造は既存schemaとの整合を保つが、意味は
この表を満たさなければならない。

| 項目 | 値 |
|---|---|
| exchange | `PHEMEX` |
| market type | `USDT_PERPETUAL` |
| symbol | `BTCUSDT` |
| WS URL | `wss://ws.phemex.com` |
| trade method | `trade_p.subscribe` |
| book method | `orderbook_p.subscribe` |
| book interval option | `true`（約120ms、production既定） |
| book depth | `0`（full depth） |
| pre-snapshot buffer上限(message) | `128`（暫定、Phase 8で見直し） |
| pre-snapshot buffer上限(byte) | `16777216`（暫定、Phase 8で見直し） |
| snapshot待機timeout | 10秒（超過時は再接続） |
| heartbeat | 5秒 |
| heartbeat failure | 15秒 |
| OI poll | 10秒 |
| normalizer profile | `phemex` |
| data root | `data_phemex_05M` |
| spot reference | disabled |
| liquidation source | unavailable |
| execution | disabled |

`MIXED_EXCHANGE_CONFIG`検査の適用条件を次に限定する。

- 本検査は、resolved active configのexchangeが`PHEMEX`である場合のみ実施する
- 検査対象はresolved active config(有効化されたprofile、環境変数、CLI上書きの解決結果)
  だけとする
- 未選択の`config/profiles/binance.yaml`、Binance test、Binance fixture、過去のBinance
  manifestを走査対象にしない
- リポジトリ全体の文字列検索によって本検査を実装してはならない
- replayでは、raw journal manifestの`exchange`と選択されたreplay adapterの整合を照合する
- Binance raw journalのreplayに対して、Phemex live設定のfail-fastを適用してはならない

上記条件の下で、resolved active configにBinance URL、Binance stream名、
`BINANCE_SPOT_REFERENCE_ENABLED=true`が検出された場合、警告だけで継続せず
`MIXED_EXCHANGE_CONFIG`として失敗させる。

---

## 18. UI表示仕様

### 18.1 表記

| 現在の意味 | Phemex版表示 |
|---|---|
| venue header | `PHEMEX · USDT PERP · 05M` |
| instrument | `PHEMEX BTC/USDT PERP` |
| OI | `PHEMEX OI` |
| OI detail | `OPEN INTEREST · PHEMEX USDT PERPETUAL` |
| liquidation | `UNAVAILABLE · NO PUBLIC PHEMEX FEED` |

Phemex版のactive画面、tooltip、API response default、ログsourceに`BINANCE`を残してはならない。
過去レポートやユーザーが保存したBinance履歴の文言は改変しない。

### 18.2 接続状態

表示可能な状態を以下とする。

- `CONNECTING`
- `SUBSCRIBING`
- `WAITING_SNAPSHOT`
- `LIVE`
- `STALE`
- `RECONNECTING`
- `FAILED`

WebSocket接続済みだけで`LIVE`にしてはならない。約定購読成功、板購読成功、板snapshot適用、
pipeline受入可能の全条件が成立して初めて`LIVE`とする。

### 18.3 Spot参照

Binance Spot参照は無効化する。Phemex Spotによる代替は本仕様の対象外である。
参照価格が無効な場合に、perpetual価格をSpot価格欄へ偽装表示してはならない。

---

## 19. ログ・メトリクス仕様

最低限、以下を計測可能にする。

### 19.1 WebSocket

- connection attempts
- successful connections
- disconnects
- reconnects
- subscribe success/failure
- ping sent
- pong received
- ping RTT
- last message age
- session ID

### 19.2 約定

- raw trade frames
- snapshot frames
- incremental frames
- rows received
- snapshot rows ignored
- canonical trades emitted
- validation failures
- duplicate IDs
- ID collisions
- current sequence epoch
- persisted incremental high-water sequence
- sequence reset candidates
- confirmed sequence resets
- ambiguous sequence events
- source timestamp lag

### 19.3 板

- raw book frames
- snapshots applied
- incrementals applied
- queue depth
- queue drops
- sync losses
- current source sequence
- top bid/ask
- spread
- last valid update age

### 19.4 REST

- product metadata fetch success/failure
- ticker/OI fetch success/failure
- HTTP status別件数
- rate-limit responses
- rate-limit remaining/capacity/retry-after
- local REST token budget remaining
- response latency
- OI source age

ログにはAPI secretを記録しない。公開市場データ版ではAPI secret自体を読み込まない。

---

## 20. エラーコード

| code | 条件 | 動作 |
|---|---|---|
| `PRODUCT_NOT_FOUND` | BTCUSDTが商品一覧にない | 起動失敗 |
| `PRODUCT_NOT_TRADABLE` | 商品が取引可能でない | 起動失敗 |
| `PRODUCT_SPEC_MISMATCH` | tick/stepが設定と不一致 | 起動失敗 |
| `MIXED_EXCHANGE_CONFIG` | active PHEMEXのresolved configにBinance設定が残る | 起動失敗 |
| `WS_CONNECT_FAILED` | 接続失敗 | backoff再接続 |
| `WS_SUBSCRIBE_FAILED` | 購読失敗 | 接続破棄・再接続 |
| `WS_HEARTBEAT_TIMEOUT` | 15秒pongなし | `STALE`・再接続 |
| `TRADE_SCHEMA_INVALID` | 約定形式不正 | quarantine・health低下 |
| `TRADE_ID_COLLISION` | 同一source keyまたは互換IDで内容不一致 | 処理停止 |
| `TRADE_BATCH_LIMIT_EXCEEDED` | 1frameが4,096約定を超える | quarantine・処理停止 |
| `TRADE_SEQUENCE_AMBIGUOUS` | sequence reset/再送を判定不能 | fail closed |
| `BOOK_SCHEMA_INVALID` | 板形式不正 | `STALE`・再同期 |
| `BOOK_SYNC_LOST` | 板欠損またはqueue drop | `STALE`・再同期 |
| `RAW_JOURNAL_FAILED` | raw保存失敗 | health `FAILED` |
| `OI_STALE` | OI 3回連続失敗 | OI表示`STALE` |
| `REST_RATE_LIMIT_UNKNOWN` | 公式上限・weightを確認不能 | polling短縮禁止・警告 |
| `REST_RATE_LIMITED` | HTTP 429 | retry-afterまで停止 |
| `REPLAY_MISMATCH` | live/replay digest不一致 | 受入失敗 |
| `NON_DETERMINISTIC_ANALYTICS_INPUT` | 分析結果がwall-clock等へ依存 | 受入失敗 |
| `STORAGE_EXCHANGE_MISMATCH` | DB manifest不一致 | 起動失敗 |

---

## 21. セキュリティ仕様

- 公開市場データ処理ではPhemex API key/secretを要求しない
- 環境変数にkeyが存在しても公開WS購読へ送信しない
- raw journal、ログ、UI、例外へsecretを出力しない
- TLS証明書検証を無効化しない
- WebSocket URLを任意外部hostへ書き換えた設定をproductionで許可しない
- JSONサイズ、batch件数、板level件数に安全上限を設ける
- Decimal変換前に文字列長を制限する
- 異常に未来または過去のtimestampをquarantineする

---

## 22. 性能要件

production既定は全板・約120ms購読とする。約20ms購読は比較試験条件であり、初期production要件ではない。

- network受信taskでDB書込や重い集計を同期実行しない
- raw journal、正規化、pipelineはbounded queueで分離する
- queue high-water markを可視化する
- 初回および定期snapshotでは全板を1回構築する
- incrementalでは変更されたprice levelだけを検証・Decimal変換する
- bid/askごとに`price -> quantity`の直接参照構造を維持する
- 50段DOM投影のために全板全件を毎回sortし直さない
- top 50の境界を増分更新し、変更が境界外ならDOM用構造を再構築しない
- raw payload保存用文字列と計算用Decimalを分離し、全板を重複変換しない
- Decimal精度をfloat化によって犠牲にしない
- 通常負荷でqueue dropを0件とする
- reconnect stormを発生させない
- UI更新頻度は既存意味を維持し、source frameごとにDOM全体を再描画しない

約20msを有効化する場合は、同一時間帯、同一symbol、同一hardwareで約120msと比較し、最低限次を
実測記録する。

- raw bytes/secondとframes/second
- frameあたりlevel更新数
- JSON parse時間p50/p95/p99
- normalization時間p50/p95/p99
- queue depth p50/p95/max
- CPU使用率とsingle-core peak
- RSS memoryと増加傾向
- journal bytes/hour
- DOM projection時間
- queue drop、sync loss、reconnect件数

20ms採用条件は、queue drop 0、sync loss 0、継続的memory増加なし、p99処理遅延がqueueを累積させない
ことである。約120msが既存100ms Binance入力の置換要件を満たす限り、20msを性能上の理由なく選ばない。

---

## 23. テスト仕様

### 23.1 約定unit test

- Buyがcanonical BUYになる
- Sellがcanonical SELLになる
- price/quantityがDecimalで保持される
- nanosecondsが正しくUTCへ変換される
- 元nanosecondsが無損失保存される
- 1フレーム複数行が配列順に展開される
- snapshot行がlive分析へ出ない
- incremental行が出る
- 同じframeのreplayでsource trade keyと互換trade IDが一致する
- `batch_index=4095`は有効、4096はfail closed
- 不正side、不正price、不正quantityを拒否する
- 同一source trade key・同一内容は重複排除される
- 同一source trade key・異内容はcollisionになる
- 同一互換trade ID・異source trade keyはcollisionになる
- session IDが変わっても同じ約定のsource trade keyは変わらない
- snapshot sequenceがhigh-water markへ影響しない
- incremental sequenceが増加する間はepochが変わらない
- 古いsequence・古いtimestampの再送でepochが変わらない
- 新しいtimestampを伴うsequence reset候補を即時受理しない
- 3 frameでresetを確認した場合だけepochが1増える
- reset判定不能時は`TRADE_SEQUENCE_AMBIGUOUS`になる

### 23.2 板unit test

- snapshotで板が置換される
- incrementalでlevelが更新される
- quantity 0でlevelが削除される
- 非連続sequence数値を正常適用できる
- 直前book sequence不一致を検出する
- trade sequenceがbook sequence stateへ影響しない
- periodic snapshotでatomic resetされる
- snapshot以前のincremental bufferが正しく処理される
- buffer overflowで部分板を生成しない
- crossed bookを正常扱いしない
- tick不整合を拒否する

### 23.3 WebSocket test

- production既定で`["BTCUSDT", true, 0]`を送信する
- 比較試験設定でのみ`["BTCUSDT", false, 0]`を送信できる
- ack IDを照合する
- 5秒heartbeatを送信する
- pong timeoutで再接続する
- 再接続で新session IDになる
- 再接続後はsnapshotまでbookがSTALEになる
- 旧connection taskが残らない
- subscription errorをLIVE扱いしない

### 23.4 raw/replay test

- raw frameが展開前の形で保存される
- 1,000件snapshot frameを保存できる
- product metadataとOI REST応答が無加工で保存される
- replay時に外部RESTへ接続しない
- session manifestの開始epoch/high-waterからidentityを再現する
- liveとreplayのcanonical出力が一致する
- liveとreplayの最終bookが一致する
- live/replay digest manifestを生成する
- 非決定fieldを除外したcanonical rolling hashが一致する
- table/state hashが一致する
- 不一致時に最初のordinalとfield-level diffを出す
- 不一致時に終了コードが非0になる
- 分析がreceived timeへ依存した場合に不合格になる
- control messageが分析イベントにならない
- malformed frameがquarantineされる

### 23.5 storage test

- Phemex専用pathへだけ書き込む
- 既存`data_05M`を読み書きしない
- manifest exchange mismatchで起動失敗する
- warm startがPhemex DBだけを使用する
- Binanceと同じsymbolでもデータが混ざらない
- source sequence stateとtrade batchが同一transactionでcommitされる
- transaction失敗後の再開でepoch/high-waterが先行しない

### 23.6 REST rate-limit test

- 10秒OI pollingが6 requests/minuteを超えない
- product metadataとOIが共通local budgetを消費する
- remaining/capacity/retry-after headerをcase-insensitiveに解釈する
- HTTP 429でretry-afterまで要求を停止する
- headerがない場合もlocal token bucketが動作する
- endpoint weight不明時にpollingを短縮しない

### 23.7 liquidation availability test

- `C09`、`E01`から`E06`が`UNAVAILABLE_INPUT`になる
- 清算eventがなくても数値0の観測としてcandidateを生成しない
- その他Hookを一括停止しない
- UI liquidation seriesが0ではなく`UNAVAILABLE`になる
- 8パターンの`LONG LIQUIDATION`文脈名はOI正常時に維持される
- 上記文脈名を公開清算feed確認済みと表示しない

### 23.8 regression test

- 5分足境界が変更されない
- CVD計算式が変更されない
- Footprint bucket意味が変更されない
- Flow Price Responseの入力・出力意味が変更されない
- 3段チャート構造が変更されない
- 8パターンのロジックが変更されない
- DOM 50段表示を維持する
- Tapeの時系列順が維持される
- Phemex未較正Hookがfail closedになる

### 23.9 performance comparison test

- 同一条件で全板約120msと約20msをcaptureする
- §22の負荷metricsを同じ形式で出力する
- 約120ms条件で50段DOMと全既存分析要件を満たす
- 20ms条件でdrop、sync loss、memory増加があればproduction採用不可とする

---

## 24. 受入条件

以下をすべて満たした場合のみ、Phemex市場データ統合を完了扱いにできる。

### 24.1 接続・入力

- `wss://ws.phemex.com`へ接続できる
- tradeとorderbookの購読ackを確認できる
- production既定の板購読が全板・約120msである
- heartbeatが5秒間隔で機能する
- reconnect後に重複したsnapshot約定を分析へ入れない
- 全板snapshotから50段DOMを生成できる
- OIをPhemex RESTから取得できる
- 分析に使用したproduct metadataとOI REST応答をraw保存できる

### 24.2 正確性

- Buy/SellのCVD符号がPhemex taker sideと一致する
- raw frame、canonical event、DB rowを相互追跡できる
- nanosecondsを失わない
- source trade keyがsessionを跨いで決定的である
- sequence reset/reuseがepochで隔離され、曖昧時はfail closedになる
- replay digest、件数、最終state hashがliveと一致する
- replay中のPhemex外部REST接続が0件
- replay不一致時に最初の差分箇所を特定できる
- queue dropまたは板同期喪失が無表示で継続されない
- 清算データを捏造しない

### 24.3 分離

- Phemex実行中にBinance APIへの通信が0件
- Phemex DB/Parquet/rawにBinanceデータが0件
- Binanceの旧data rootを読み書きしない
- Phemex UIのactive表示にBinance表記がない
- Binance較正thresholdがPhemexでCALIBRATED扱いされない
- `C09`、`E01`から`E06`が`UNAVAILABLE_INPUT`である

### 24.4 既存機能保全

- Flow Price Response回帰試験が通る
- 3段チャート回帰試験が通る
- 8パターン回帰試験が通る
- 8パターンのOI文脈名と公開清算feedの有無を混同しない
- Footprint、DOM、Tape、OIの既存意味が維持される
- 完成済みロジックに交換所都合の分岐が混入していない

### 24.5 運用安定性

- 規定の連続稼働試験でqueue drop 0件
- raw journal保存失敗 0件
- 未処理例外 0件
- reconnect後の古い板表示 0件
- memory使用量が継続的に増加しない
- OIがlocal REST budgetを超過しない
- HTTP 429後にretry-afterを無視した再要求が0件

---

## 25. 変更対象の論理一覧

実装承認後に変更対象となる領域を示す。これは実施承認を意味しない。

### 25.1 新規exchange edge

- Phemex WebSocket transport
- Phemex REST client
- Phemex normalizer/profile
- Phemex raw frame adapter
- Phemex fixtureとunit test

### 25.2 交換所選択・pipeline接続

- runtime config
- live pipelineのtransport選択
- snapshot/diff同期方式
- replay時のbatch展開

### 25.3 補助feed

- OI poller
- market ticker poller
- Binance Spot referenceの無効化

### 25.4 永続化

- Phemex専用data root
- DB manifest
- raw journal metadata
- trade source identity
- depth replay/history

### 25.5 表示

- venue label
- instrument label
- OI source label
- liquidation unavailable表示
- connection state

### 25.6 Hook・観測

- thresholdのPhemex隔離
- calibration stateの初期化
- venue-neutral field name
- Phemex用latency/health metrics

---

## 26. 禁止事項

- リポジトリ全体の`Binance`を機械的に`Phemex`へ一括置換すること
- Phemex messageをBinance messageへ偽装して長期保存すること
- Phemex sequenceを`U/u/pu`と同一意味で扱うこと
- sequenceが1増えないことだけでgap判定すること
- trade snapshotを通常live約定として毎回投入すること
- individual trade IDを乱数で生成すること
- ns timestampを保存せずmicrosecondsだけ残すこと
- Binance DBをPhemex warm startへ使用すること
- Binance thresholdをPhemexで較正済みと表示すること
- 清算値を推測で埋めること
- 50段DOMを無断で30段へ縮小すること
- stale bookをLIVE表示すること
- public market data処理へAPI secretを持ち込むこと
- 完成済みのFlow Price Response、3段チャート、8パターンを同時に改変すること

---

## 27. 将来のPhemex注文執行境界

本章は将来要件の境界記録であり、今回の実装対象ではない。

Phemexを注文送信先にする場合は、少なくとも以下を別仕様として定義する必要がある。

- `x-phemex-access-token`
- `x-phemex-request-expiry`
- `x-phemex-request-signature`
- HMAC SHA256署名文字列
- testnetとproductionの完全分離
- client order IDとidempotency
- new/cancel/replace/query
- authenticated account/order/position WebSocket
- fillsとREST responseの照合
- unknown execution resultのreconciliation
- position modeと`posSide`
- `reduceOnly`
- `closeOnTrigger`
- price tickとquantity step検証
- rate limit
- API secret保管
- emergency stop
- execution enableの明示的二重gate

市場データ入力の完成を、注文執行可能と解釈してはならない。

---

## 28. 未確定事項

以下は実装開始前にユーザー判断または実測確認が必要な項目である。

- Phemex full-depth約120msの長時間負荷に対するqueue容量(§9.3暫定値の妥当性をPhase 8実測で見直す)
- 約20msを将来採用する場合の性能改善効果と追加保存コスト
- raw journalの日次保存量とretention
- Phemex用threshold較正期間
- liquidation非対応表示をHook画面のどこまで露出するか
- 過去BinanceレポートをPhemex版配布物へ含めるか
- 将来Phemex Spot参照を追加するか
- 将来Phemex注文執行を追加するか

未確定事項を推測で実装してはならない。

---

## 29. 仕様確認記録

2026-08-02の読み取り調査で確認した事項:

- Phemex公開WebSocketは`wss://ws.phemex.com`
- USDT perpetual trade購読は`trade_p.subscribe`
- USDT perpetual板購読は`orderbook_p.subscribe`
- depth `0`はfull depth
- 板購読の第2引数`false`は約20ms、`true`は約120ms
- 板snapshotは約60秒間隔でself-verification用に配信される
- tradeはbatch形式
- trade timestampはnanoseconds
- trade sideはtaker side
- tradeには個別trade IDが含まれない
- tradeはsnapshotとincrementalを持つ
- 実受信snapshotで1,000 tradesを確認
- 板はsnapshotとincrementalを持つ
- quantity 0はlevel削除
- sequenceはチャネル内の単純連番ではない
- 公式仕様にはsequenceの永久一意性、resetなし、再利用なしの保証がない
- heartbeatは30秒未満、公式推奨5秒
- `GET /public/products`でBTCUSDT商品仕様を取得可能
- `GET /md/v3/ticker/24hr`で`openInterestRv`を取得可能
- 一般REST制限はIP 5,000 requests/5 minutes、Others 100 requests/minute
- 公開市場全体清算feedは確認できない
- 現行の清算直接依存Hookは`C09`、`E01`から`E06`
- 8パターン中のliquidation名称はforceOrder直接依存ではなくOI文脈名

---

## 30. 承認状態

本書作成時点で承認されているのは、調査と仕様書作成のみである。

次の操作は未承認である。

- ソースコード変更
- 設定変更
- DB schema変更
- Binance接続の停止・削除
- Phemex接続の実装
- testnetまたはproductionへの注文送信
- API key/secretの設定
- threshold較正

実装は、ユーザーから明示的な開始指示を受けるまで行わない。
