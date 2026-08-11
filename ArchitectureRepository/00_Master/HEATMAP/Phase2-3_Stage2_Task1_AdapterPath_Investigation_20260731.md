# Phase 2-3 Stage 2 Task 1 設計確定調査（アダプタ経路）

- 指示書: Phase 2-3 Stage 2 Task 1 設計確定調査（アダプタ経路）Version 1.0
- 調査日: 2026-07-31
- 調査種別: 読み取りのみ
- 調査時HEAD: `bf9512635d7a6f4d67a14d67d128fc528f6b6707`

## K1. BookProjection の構造と生成元

### K1-1. `BookProjection` のフィールド

`BookProjection` は frozen dataclass であり、定義は `Delta_Engine_Pro4web/webapp/book_projection.py:31-45` にある。

| フィールド | 型 | 根拠 |
|---|---|---|
| `projection_time` | `datetime` | `Delta_Engine_Pro4web/webapp/book_projection.py:35` |
| `event_time` | `datetime | None` | `Delta_Engine_Pro4web/webapp/book_projection.py:36` |
| `last_update_id` | `int | None` | `Delta_Engine_Pro4web/webapp/book_projection.py:37` |
| `sync_state` | `str` | `Delta_Engine_Pro4web/webapp/book_projection.py:38` |
| `bids` | `tuple[tuple[Decimal, Decimal], ...]` | `Delta_Engine_Pro4web/webapp/book_projection.py:39` |
| `asks` | `tuple[tuple[Decimal, Decimal], ...]` | `Delta_Engine_Pro4web/webapp/book_projection.py:40` |
| `depth_levels` | `int` | `Delta_Engine_Pro4web/webapp/book_projection.py:41` |
| `best_bid` | `Decimal | None` | `Delta_Engine_Pro4web/webapp/book_projection.py:42` |
| `best_ask` | `Decimal | None` | `Delta_Engine_Pro4web/webapp/book_projection.py:43` |
| `spread` | `Decimal | None` | `Delta_Engine_Pro4web/webapp/book_projection.py:44` |
| `age_ms` | `int | None` | `Delta_Engine_Pro4web/webapp/book_projection.py:45` |

`symbol` は `BookProjection` のフィールド列には存在しない（全フィールドは同ファイル `:35-45`）。WebSocket envelope の `symbol` は `PushBroker.symbol`（`Delta_Engine_Pro4web/webapp/push_broker.py:151`）から入る（同ファイル `:264-268`、envelopeの構造は `:38-45`）。

### K1-2. ライブ経路での生成

1. LivePipeline は正規化済みdepthを `book_state.apply(update)` へ渡し、直後に `book_state.snapshot()` を得る（`Delta_Engine_Pro4web/src/pipeline.py:1851-1869`）。同期済み経路でも同じapply/snapshotが実行される（同ファイル `:1897-1907`）。
2. LivePipeline はその `book_state` を `self.book_manager` として公開する（`Delta_Engine_Pro4web/src/pipeline.py:1526-1529`）。
3. webapp は `lambda: getattr(pipeline, "book_manager", None)` を `LatestBookProjectionPump` の取得関数へ、`broker.on_book_update` を送信関数へ渡す（`Delta_Engine_Pro4web/webapp/main.py:231-237`）。
4. live分岐では `book_projection_pump.run()` がasyncio taskとして起動される（`Delta_Engine_Pro4web/webapp/main.py:380-387`）。
5. pumpの `project_once()` は取得したbook stateを `build_book_projection` へ渡す（`Delta_Engine_Pro4web/webapp/book_projection.py:267-274`）。`build_book_projection` は `book_state.snapshot()` を読み出す（同ファイル `:85-93,113-120`）。
6. 生成されたprojectionはpumpのsend callbackへ渡される（`Delta_Engine_Pro4web/webapp/book_projection.py:276-280`）。main側でそのcallbackは `broker.on_book_update` である（`Delta_Engine_Pro4web/webapp/main.py:231-237`）。

## K2. `push_broker.on_book_update` の入力契約

`on_book_update(projection: BookProjection)` の定義は `Delta_Engine_Pro4web/webapp/push_broker.py:250-299` にある。SYNCED時はbest bid/ask/spreadの3値を必須とする（同ファイル `:252-260`）。非SYNCED時はbids/asksを空tupleにする（同ファイル `:261-263`）。

### K2-1. envelope と payload の写像

| 出力位置 | 出力キー | 入力・生成元 | 根拠 |
|---|---|---|---|
| envelope | `v` | `PAYLOAD_VERSION` | `Delta_Engine_Pro4web/webapp/push_broker.py:38-45` |
| envelope | `type` | 固定値 `BOOK_UPDATE` | `Delta_Engine_Pro4web/webapp/push_broker.py:264-266` |
| envelope | `time` | `projection.projection_time` をUTC ISO文字列化 | `Delta_Engine_Pro4web/webapp/push_broker.py:264-266`; 同ファイル `:38-45` |
| envelope | `symbol` | `self.symbol` | `Delta_Engine_Pro4web/webapp/push_broker.py:264-268`; 同ファイル `:38-45` |
| payload | `book_stream_id` | `self.book_stream_id` | `Delta_Engine_Pro4web/webapp/push_broker.py:268-270` |
| payload | `book_sequence` | `self.book_updates_broadcast + 1` | `Delta_Engine_Pro4web/webapp/push_broker.py:261,268-270` |
| payload | `event_time` | `projection.event_time` をUTC ISO文字列化、None透過 | `Delta_Engine_Pro4web/webapp/push_broker.py:271-274` |
| payload | `projection_time` | `projection.projection_time` をUTC ISO文字列化 | `Delta_Engine_Pro4web/webapp/push_broker.py:275-277` |
| payload | `last_update_id` | `projection.last_update_id` | `Delta_Engine_Pro4web/webapp/push_broker.py:278` |
| payload | `sync_state` | `projection.sync_state` | `Delta_Engine_Pro4web/webapp/push_broker.py:279` |
| payload | `bids` | `(price, quantity)` を `{price: d2s(price), qty: d2s(quantity)}` へ変換 | `Delta_Engine_Pro4web/webapp/push_broker.py:280-283` |
| payload | `asks` | `(price, quantity)` を `{price: d2s(price), qty: d2s(quantity)}` へ変換 | `Delta_Engine_Pro4web/webapp/push_broker.py:284-287` |
| payload | `depth_levels` | `projection.depth_levels` | `Delta_Engine_Pro4web/webapp/push_broker.py:288` |
| payload | `best_bid` | SYNCED時 `d2s(projection.best_bid)`、それ以外None | `Delta_Engine_Pro4web/webapp/push_broker.py:289` |
| payload | `best_ask` | SYNCED時 `d2s(projection.best_ask)`、それ以外None | `Delta_Engine_Pro4web/webapp/push_broker.py:290` |
| payload | `spread` | SYNCED時 `d2s(projection.spread)`、それ以外None | `Delta_Engine_Pro4web/webapp/push_broker.py:291` |
| payload | `age_ms` | `projection.age_ms` | `Delta_Engine_Pro4web/webapp/push_broker.py:292` |

`d2s` はDecimal/int/Noneのみを受け、値を文字列化する（`Delta_Engine_Pro4web/webapp/push_broker.py:21-27`）。

### K2-2. stream identity と sequence の生成

- `book_stream_id` は `PushBroker.__init__` で `str(uuid4())` として生成される（`Delta_Engine_Pro4web/webapp/push_broker.py:144-161`）。
- `book_sequence` は送信直前に `book_updates_broadcast + 1` として生成される（同ファイル `:261`）。
- messageをキャッシュした後に `book_updates_broadcast` が当該sequenceへ更新される（同ファイル `:295-296`）。
- `best_bid` / `best_ask` / `spread` は `BookProjection` からpayloadへ移される（同ファイル `:289-291`）。そのprojection側の値は `build_book_projection` が算出する（`Delta_Engine_Pro4web/webapp/book_projection.py:190-220`）。

## K3. `OrderBookSnapshot` から `BookProjection` までの距離

### K3-1. Snapshotが直接保持する値

`OrderBookSnapshot` は `symbol`, `last_update_id`, `bids`, `asks`, `event_time` を持つ（`Delta_Engine_Pro4web/src/orderflow/orderbook.py:69-77`）。bids/asksは `dict[Decimal, Decimal]` の価格→数量である（同ファイル `:75-76`）。`OrderBookStateManager.snapshot()` は内部stateのdict copyとlast event timeからこのsnapshotを作る（同ファイル `:176-186`）。

### K3-2. Snapshotに直接ないBookProjectionフィールドと既存算出箇所

| Snapshotに直接ない値 | 既存コード上の取得・算出事実 | 根拠 |
|---|---|---|
| `projection_time` | 引数があれば使用し、なければ `_utc_now()`。timezone-awareを要求しUTC化 | `Delta_Engine_Pro4web/webapp/book_projection.py:27-28,90-101` |
| `sync_state` | stateなし、snapshotなし、非同期、stale、invalid、empty、locked、crossed、syncedをbook stateの状態・内容から分岐 | `Delta_Engine_Pro4web/webapp/book_projection.py:103-161,163-208` |
| `depth_levels` | `build_book_projection` の引数（既定50）として受け取る | `Delta_Engine_Pro4web/webapp/book_projection.py:85-92` |
| top-Nの `bids` / `asks` | bidsを価格降順、asksを価格昇順にsortし、`[:depth_levels]` で切る | `Delta_Engine_Pro4web/webapp/book_projection.py:190-191,210-217` |
| `best_bid` | 降順sort済みbidsの先頭価格 | `Delta_Engine_Pro4web/webapp/book_projection.py:190-193` |
| `best_ask` | 昇順sort済みasksの先頭価格 | `Delta_Engine_Pro4web/webapp/book_projection.py:190-193` |
| `spread` | `best_ask - best_bid` | `Delta_Engine_Pro4web/webapp/book_projection.py:210-220` |
| `age_ms` | `book_state.age_ms(now_monotonic)` | `Delta_Engine_Pro4web/webapp/book_projection.py:113-120`; `Delta_Engine_Pro4web/src/orderflow/orderbook.py:169-174` |

補足事実:

- `event_time` 自体はSnapshotに存在する（`Delta_Engine_Pro4web/src/orderflow/orderbook.py:77`）。既存 `build_book_projection` はSnapshotの当該fieldを直接読むのではなく、`book_state.last_event_time` を読みtimezoneを検査する（`Delta_Engine_Pro4web/webapp/book_projection.py:113-118`）。manager側propertyは `Delta_Engine_Pro4web/src/orderflow/orderbook.py:164-167` にある。
- `depth_levels` はsnapshot由来の計算値ではなく、webapp config値がpumpへ渡される（`Delta_Engine_Pro4web/webapp/main.py:231-236`）。
- `sync_state` の判定には `book_state.snapshot()`, `gaps_detected`, `is_synchronized`, `age_ms` が使われる（`Delta_Engine_Pro4web/webapp/book_projection.py:113-151`）。
- `OrderBookSnapshot` だけを引数に取る `BookProjection` 生成関数は `webapp/book_projection.py` 内に該当なし。同ファイルの生成関数は `build_book_projection(book_state, ...)` であり、引数に対して `.snapshot()` と `.age_ms()` を呼ぶ（`Delta_Engine_Pro4web/webapp/book_projection.py:85-93,113-120`）。
- `symbol` はSnapshotにある（`Delta_Engine_Pro4web/src/orderflow/orderbook.py:73`）がBookProjectionにはなく（`Delta_Engine_Pro4web/webapp/book_projection.py:35-45`）、payload envelopeではbrokerのsymbolが使われる（`Delta_Engine_Pro4web/webapp/push_broker.py:151,264-268`）。

## K4. 既存Canvas gate=false の理由痕跡

### K4-1. gate と周辺フラグ

- `PHASE5_FUSION_ENABLED = true` の直後に、`GO-H3 presentation gate. Keep false until GO-H6 operational activation.` というコメントがある（`Delta_Engine_Pro4web/webapp/static/index.html:966-969`）。
- `ORDER_BOOK_HEATMAP_ENABLED = false` は `Delta_Engine_Pro4web/webapp/static/index.html:969`。
- その直後のDOM Trade Pulse gateはtrueである（同ファイル `:970-972`）。

### K4-2. gate true側に存在する要素とsetup範囲

- HTMLにはFOOTPRINT/HEATMAP切替button、heatmap controlsがある（`Delta_Engine_Pro4web/webapp/static/index.html:754-771`）。
- `heatmapcanvas`, tooltip, detail, statusがHTMLにある（同ファイル `:776-781`）。
- Canvas実装script `orderbook_heatmap.js` は読み込まれる（同ファイル `:957-960`）。
- setupは必要DOMの存在を検査した後、gate=falseならheatmap button/canvas/controls/detail/statusをhiddenにし、footprint側を表示したままreturnする（同ファイル `:2370-2380`）。
- returnしない経路では `HeatmapBookStore`, `HeatmapTradeStore`, `OrderBookHeatmapCanvas` を生成する（同ファイル `:2381-2386`）。
- 同経路ではbook/trade ingest、continuity、connection、focus、metrics、mode切替を持つAPIが `window.HEATMAP_UI` に設定される（同ファイル `:2387-2397`）。
- mode切替はcanvas/controls/detail/statusのhidden状態とchart visibilityを切り替える（同ファイル `:2398-2406`）。duration、step、intensity、bubble、live lock、gear、best bid/ask line、last price lineのcontrolsがchartへ接続される（同ファイル `:2407-2418`）。
- WebSocket connection状態、BOOK_UPDATE、accepted trade、tape continuityは `window.HEATMAP_UI` が存在する場合にheatmapへ渡る（同ファイル `:1020,1085-1088,1090-1108`）。

### K4-3. TODO/FIXME走査

次の走査は0件だった。

```text
rg -n -i "TODO|FIXME" Delta_Engine_Pro4web/webapp/static/index.html Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js
TODO_FIXME_HIT_COUNT=0
```

したがって、`TODO` / `FIXME` 文字列による未完了事項は両ファイルに該当なし。gate offの理由として記載された文字列は `index.html:968` のGO-H6 operational activation待ちコメントである。

## K5. replay/recording供給の既存フック

### K5-1. 通常ReplayPipelineからwebappへの経路

- `ReplaySource` は1行1JSON objectのファイルをfile orderで読み、async iteratorと同期 `read_all()` を持つ（`Delta_Engine_Pro4web/src/acquisition/replay.py:37-63`）。
- `ReplayPipeline.run(data_path)` は `ReplaySource(data_path).read_all()` で全recordを得る（`Delta_Engine_Pro4web/src/pipeline.py:495-497`）。
- replayのdepth recordはnormalizerを通り、ローカルな `book_state` にapplyされ、snapshotが `SnapshotProducer.observe_book_update` へ渡る（`Delta_Engine_Pro4web/src/pipeline.py:530-538,677-692`）。
- ReplayPipelineのcallback fieldsには `on_accepted_trade`, `on_trade`, `on_candle`, `on_analysis`, `on_absorption_state`, `on_flow_response` がある（`Delta_Engine_Pro4web/src/pipeline.py:424-429`）。
- normalized tradeごとに `on_accepted_trade` が呼ばれ（同ファイル `:587-601`）、candle/analysis callbacksもbar close時に呼ばれる（同ファイル `:647-674`）。
- webappはconfigのreplay分岐で `ReplayPipeline.from_config(...)` を生成する（`Delta_Engine_Pro4web/webapp/main.py:179-186`）。
- webappはaccepted tradeをTapeBatcherへ渡すcallback（同ファイル `:268-270`）、candleをbrokerへ渡すcallback（同ファイル `:274-301`）、analysisをbrokerへ渡すcallback（同ファイル `:303-315`）を定義し、pipeline callbacksへ接続する（同ファイル `:350-359`）。
- replay時は `pipeline.run(config.replay.data_path)` がexecutorで動く（同ファイル `:371-379`）。

### K5-2. Replay時のbook projection状態

- ReplayPipeline内のbook stateは `run()` のローカル変数 `book_state` である（`Delta_Engine_Pro4web/src/pipeline.py:495-530`）。ReplayPipelineの初期化済み属性列 `:390-432` には `book_manager` がない。
- `self.book_manager = book_state` の代入はLivePipeline側にある（`Delta_Engine_Pro4web/src/pipeline.py:1526-1529`）。同ファイル全体の `self.book_manager` 出現はこの1箇所だった。
- mainはbook projection pump自体を `getattr(pipeline, "book_manager", None)` で構築する（`Delta_Engine_Pro4web/webapp/main.py:231-237`）が、replay分岐では `book_projection_task = None` とし、pumpを起動しない（同ファイル `:371-382`）。
- statsもreplay時のbook projection stateを `DISABLED_REPLAY` とする（`Delta_Engine_Pro4web/webapp/main.py:428-443,873-885`）。

### K5-3. `depth_history_raw` のwebapp読込entry

- webappの `DEPTH_HISTORY_ROOT` 使用箇所は、`DepthHistoryRecorder` を生成する書込側である（`Delta_Engine_Pro4web/webapp/main.py:124-135`）。既定pathは `data_05M/depth_history_raw`（同ファイル `:130`）。
- `DepthHistoryReader` はoffline reconstructorとして定義され、recording directoryからmanifest付きsegmentを列挙する（`Delta_Engine_Pro4web/src/heatmap/reconstruct.py:1-5,48-86`）。
- `Delta_Engine_Pro4web/webapp/` に対する `DepthHistoryReader` / `heatmap.reconstruct` 読込参照のgrepは0件。webapp側の `depth_history_raw` 参照は上記writer構築（`Delta_Engine_Pro4web/webapp/main.py:126-135`）のみだった。
- 通常replay entryは単一の `config.replay.data_path` を `ReplayPipeline.run` へ渡す（`Delta_Engine_Pro4web/webapp/main.py:371-379`）もので、readerは1ファイルを読む `ReplaySource` である（`Delta_Engine_Pro4web/src/acquisition/replay.py:37-63`）。manifest付きdirectoryを読む `DepthHistoryReader` をwebappから呼ぶentryは該当なし。
- 別系統の `PersistentDepthWriter` は `data_05M/depth_history` を既定rootとしてBOOK_UPDATE payloadを書き込む（`Delta_Engine_Pro4web/webapp/main.py:124-125`; `Delta_Engine_Pro4web/webapp/persistent_depth_writer.py:15-20,43-58`）。

## 参照ファイル識別値

下表は調査時のファイルbytesに対するSHA-256である。表中の `Delta_Engine_Pro4web/` 10ファイルについて `git diff --name-only HEAD -- <paths>` の出力は空だった。

| ファイル | SHA-256 | byte | LF | CR |
|---|---:|---:|---:|---:|
| `ArchitectureRepository/00_Master/PROJECT_MEMORY.md` | `F14AA1002269E0AF1F43B28AF5E7356C118E19BFF5DF6C45B081530153DDA032` | 81936 | 1274 | 1190 |
| `Delta_Engine_Pro4web/webapp/book_projection.py` | `591BBB8A43946FCDE43CD04B42026BD03DA1BE55135CA08491D295DB8E755D99` | 9154 | 299 | 0 |
| `Delta_Engine_Pro4web/webapp/push_broker.py` | `D74F0F13B092055E7FA93D604A09E27278401B87D84444D1CB83B4C03AAF19BD` | 25453 | 593 | 6 |
| `Delta_Engine_Pro4web/src/orderflow/orderbook.py` | `291D46612AEBE09CD4B7A60E46F30CB9E8602FDD53817A3D01170F669D424C05` | 11295 | 290 | 0 |
| `Delta_Engine_Pro4web/webapp/main.py` | `E4D9A6AEC7F1A515141BAFD7D880848A9FF7C7E3D16B5D695B6A8DB9BE3016A4` | 39478 | 975 | 950 |
| `Delta_Engine_Pro4web/webapp/static/index.html` | `5474C889B80550664EE3E3FB23ABC7252949471D8BF09E7D648DDA354024CEB5` | 183658 | 2562 | 12 |
| `Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js` | `9F362BAF58FF79ED24A10133B98ED1FCBB61D14D150BC93CBB70968319E1A807` | 62708 | 1226 | 0 |
| `Delta_Engine_Pro4web/src/pipeline.py` | `9313A7C07D80DC773E36C9D16F22268D3AAF7F1650D563E607085CDE8D8B3DAC` | 100403 | 2164 | 1314 |
| `Delta_Engine_Pro4web/src/acquisition/replay.py` | `E069634F1AC572E6DDB5570D447D8C7FD4DCE346DF011AF32679D9DA7208EBE2` | 2304 | 73 | 0 |
| `Delta_Engine_Pro4web/src/heatmap/reconstruct.py` | `84639422635CC01678CFB1E622FA561DF0B51D733A3262DA4A2B3A25C16BEB0C` | 20394 | 573 | 0 |
| `Delta_Engine_Pro4web/webapp/persistent_depth_writer.py` | `451669F63D108DB42A5E84490B36A3A063809FD6C3BE383F522507065B61FFCF` | 3163 | 85 | 0 |

## Git証跡

### `git rev-parse HEAD`

```text
bf9512635d7a6f4d67a14d67d128fc528f6b6707
```

### `git status --porcelain -- Delta_Engine_Pro4web/`

```text
?? Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/
```

上記出力にtracked `M` はなく、表示された項目は調査開始時から存在したuntracked directoryである。

### `git diff --cached --name-only`

```text
（出力なし）
```

`CACHED_PATH_COUNT=0`
