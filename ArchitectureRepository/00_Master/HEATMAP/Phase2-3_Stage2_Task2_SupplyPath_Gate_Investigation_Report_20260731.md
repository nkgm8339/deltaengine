# Phase 2-3 Stage 2 Task 2 供給経路＋gate 調査報告

- 指示書: Phase 2-3 Stage 2 Task 2 供給経路+gate 調査 Version 1.0
- 実施日: 2026-07-31
- 調査時HEAD: `2fea7efebbe64b86b3a62bf1645ffcf3d3946dd4`
- 段階: 読み取り調査
- source実装・既存source変更: なし
- stage: なし

## M1. main.pyのbook projection供給の起動／非起動条件

- pipelineは`config.replay.enabled`で排他選択される。trueなら`ReplayPipeline`、falseなら`LivePipeline`。`Delta_Engine_Pro4web/webapp/main.py:179-186`
- `LatestBookProjectionPump`はlifespan内で構築され、取得元は`pipeline.book_manager`、送信先は`broker.on_book_update`。間隔は`book_update_interval_ms / 1000`。`Delta_Engine_Pro4web/webapp/main.py:231-237`
- replay時は`market_push_task=None`、`book_projection_task=None`となり、`pipeline.run(config.replay.data_path)`だけがexecutorで起動する。`Delta_Engine_Pro4web/webapp/main.py:371-379`
- live時だけ`market_push_pump.run()`、`book_projection_pump.run()`、`pipeline.run_async()`がtask化される。`Delta_Engine_Pro4web/webapp/main.py:380-387`
- replay時の5秒statsではbook状態を`DISABLED_REPLAY`とする。`Delta_Engine_Pro4web/webapp/main.py:428-444`
- `/api/stats`でもreplay時は`book_projection_state="DISABLED_REPLAY"`とする。`Delta_Engine_Pro4web/webapp/main.py:873-889`

lifespan内の既存task生成・管理パターン:

- callbackがapp loop内なら`app_loop.create_task()`、別threadなら`asyncio.run_coroutine_threadsafe()`を使う。`Delta_Engine_Pro4web/webapp/main.py:239-266`
- replay pipelineは`run_in_executor()`のFutureを`asyncio.ensure_future()`で管理する。`Delta_Engine_Pro4web/webapp/main.py:371-379`
- live market/book/pipelineと共通Tape taskを生成する。`Delta_Engine_Pro4web/webapp/main.py:380-388`
- OI taskは非replay時のみ。`Delta_Engine_Pro4web/webapp/main.py:406-414`
- HFM tail taskも非replay時のみ。`Delta_Engine_Pro4web/webapp/main.py:416-426`
- stats taskは常時生成される。`Delta_Engine_Pro4web/webapp/main.py:428-491`
- health taskはmonitor有効時のみ。`Delta_Engine_Pro4web/webapp/main.py:515-568`
- taskは`app.state.tasks`へ集約される。`Delta_Engine_Pro4web/webapp/main.py:568-581`
- shutdown時は全taskをcancelし、各taskをawaitする。`Delta_Engine_Pro4web/webapp/main.py:583-590`
- Hook captureとPersistent writerは`asyncio.to_thread(close)`、raw Depth recorderは同期`close()`される。`Delta_Engine_Pro4web/webapp/main.py:591-599`

## M2. config.replay構造とrecording directory指定手段

`config.replay`の定義フィールド:

- `enabled: bool`、default false。`Delta_Engine_Pro4web/src/config.py:303-305`
- `data_path: nullable non-empty string`、default null。`Delta_Engine_Pro4web/src/config.py:303-306`
- `speed: number >= 0`、default 1.0。`Delta_Engine_Pro4web/src/config.py:303-307`
- 現設定値は`enabled: false`、`data_path: null`、`speed: 1.0`。`Delta_Engine_Pro4web/config/config.yaml:104-107`

`data_path`はmarket replay入力として`pipeline.run()`へ渡される。`Delta_Engine_Pro4web/webapp/main.py:371-379`、`Delta_Engine_Pro4web/src/pipeline.py:495-497`

現行`replay` schemaにはdepth recording directory専用フィールドはない。`Delta_Engine_Pro4web/src/config.py:303-307`

既存のdirectory指定:

- `DEPTH_HISTORY_ENABLED`と`DEPTH_HISTORY_ROOT`があり、default rootは`data_05M/depth_history_raw`。`Delta_Engine_Pro4web/webapp/main.py:124-135`
- Compose値は`DEPTH_HISTORY_ENABLED=false`、`DEPTH_HISTORY_ROOT=/app/data_05M/depth_history_raw`。`Delta_Engine_Pro4web/docker-compose.yml:28-30`
- raw recorderは`root/symbol=<symbol>`を作成する。`Delta_Engine_Pro4web/src/acquisition/depth_history_recorder.py:103-115`
- そのdirectoryへ`raw_depth.<timestamp>.jsonl`を作る。`Delta_Engine_Pro4web/src/acquisition/depth_history_recorder.py:139-142`
- close時に`started_at`、byte、record数、SHA、sync情報を持つmanifestを作る。`Delta_Engine_Pro4web/src/acquisition/depth_history_recorder.py:239-265`
- `frame_source`は渡されたdirectoryを`DepthHistoryReader`へ直接渡す。`Delta_Engine_Pro4web/webapp/heatmap_frame_source.py:43-58`
- Readerは指定directory直下のJSONLとmanifestを読む。`Delta_Engine_Pro4web/src/heatmap/reconstruct.py:48-100`

既存raw設定から得られる入力形は`DEPTH_HISTORY_ROOT/symbol=<config.market.symbol>`。`Delta_Engine_Pro4web/src/acquisition/depth_history_recorder.py:103-115`

別系統:

- `PERSISTENT_DEPTH_HISTORY_ENABLED`と`PERSISTENT_DEPTH_HISTORY_ROOT`があり、default rootは`data_05M/depth_history`。`Delta_Engine_Pro4web/webapp/main.py:124-125`
- Compose値はfalse、`/app/data_05M/depth_history`。`Delta_Engine_Pro4web/docker-compose.yml:24-27`
- Persistent writerも`root/symbol=<symbol>`を作るが、内容は`BOOK_UPDATE` payload列。`Delta_Engine_Pro4web/webapp/persistent_depth_writer.py:15-18`、`Delta_Engine_Pro4web/webapp/persistent_depth_writer.py:43-58`
- そのmanifestはstream/sequence/schema revisionを持つ。`Delta_Engine_Pro4web/webapp/persistent_depth_writer.py:60-77`
- `DepthHistoryReader`側はraw recorder由来の`started_at`、byte数、record数、SHAを検証する。`Delta_Engine_Pro4web/src/heatmap/reconstruct.py:74-95`、`Delta_Engine_Pro4web/src/heatmap/reconstruct.py:115-145`

## M3. index.html gate有効化の最小変更範囲

- 現在のgateは`ORDER_BOOK_HEATMAP_ENABLED=false`。`Delta_Engine_Pro4web/webapp/static/index.html:967-971`
- setupはボタン、Canvas、module objectの存在を確認する。`Delta_Engine_Pro4web/webapp/static/index.html:2371-2375`
- gate=falseの場合、Heatmapボタン、Canvas、controls、detail、statusをhiddenにしてFootprintを表示し、returnする。`Delta_Engine_Pro4web/webapp/static/index.html:2376-2380`

gate=true時に通る既存範囲:

- `HeatmapBookStore`と`HeatmapTradeStore`を生成する。`Delta_Engine_Pro4web/webapp/static/index.html:2381-2382`
- `OrderBookHeatmapCanvas`を生成する。`Delta_Engine_Pro4web/webapp/static/index.html:2383-2386`
- ingest、trade、connection、metrics、mode APIを作り、`window.HEATMAP_UI`へ設定する。`Delta_Engine_Pro4web/webapp/static/index.html:2387-2397`
- mode切替でFootprint／HeatmapのCanvasとcontrolsを切り替え、`chart.setVisible()`を呼ぶ。`Delta_Engine_Pro4web/webapp/static/index.html:2398-2406`
- Heatmap表示時間、step、intensity、bubble、live lock等のcontrolsを接続する。`Delta_Engine_Pro4web/webapp/static/index.html:2407-2417`
- 初期modeはFootprint。`Delta_Engine_Pro4web/webapp/static/index.html:2418`

関連する別条件:

- Heatmap JSは読み込み済み。`Delta_Engine_Pro4web/webapp/static/index.html:957-959`
- module objectが存在しなければsetupはreturnする。`Delta_Engine_Pro4web/webapp/static/index.html:982`、`Delta_Engine_Pro4web/webapp/static/index.html:2375`
- `PHASE5_FUSION_ENABLED`は現在true。`Delta_Engine_Pro4web/webapp/static/index.html:967`
- `BOOK_UPDATE`と`TAPE_UPDATE`のhandler呼び出しは`PHASE5_FUSION_ENABLED`で条件付けされる。`Delta_Engine_Pro4web/webapp/static/index.html:1066-1067`
- Tape UI自体も`PHASE5_FUSION_ENABLED`内で生成される。`Delta_Engine_Pro4web/webapp/static/index.html:2427-2439`
- accepted Tape tradeからHeatmap bubbleへ渡す経路は`window.HEATMAP_UI`の存在を条件にする。`Delta_Engine_Pro4web/webapp/static/index.html:1095-1108`
- `ORDER_BOOK_HEATMAP_ENABLED`の参照は定義行とsetup分岐の2箇所。`Delta_Engine_Pro4web/webapp/static/index.html:969`、`Delta_Engine_Pro4web/webapp/static/index.html:2376`

## M4. broker.on_book_updateをasync taskから駆動する接続点

live経路:

1. `LatestBookProjectionPump`へbook manager getterと`broker.on_book_update`を渡す。`Delta_Engine_Pro4web/webapp/main.py:231-237`
2. live分岐で`book_projection_pump.run()`をtask化する。`Delta_Engine_Pro4web/webapp/main.py:380-387`
3. `run()`が`project_once()`を呼ぶ。`Delta_Engine_Pro4web/webapp/book_projection.py:296-299`
4. `project_once()`が`build_book_projection()`を実行する。`Delta_Engine_Pro4web/webapp/book_projection.py:267-274`
5. fingerprintが変化した場合、登録済みsend callbackを`await`する。`Delta_Engine_Pro4web/webapp/book_projection.py:275-280`
6. `PushBroker.on_book_update()`がstream IDとsequenceを付けて`BOOK_UPDATE`を生成する。`Delta_Engine_Pro4web/webapp/push_broker.py:250-294`
7. cache、sequence更新、broadcastを行う。`Delta_Engine_Pro4web/webapp/push_broker.py:295-299`

`iter_book_projections()`は同期generatorであり、`DepthReconstructor.sample_states()`を同期`for`してyieldする。`Delta_Engine_Pro4web/webapp/heatmap_frame_source.py:43-66`

完全同形の「同期generatorをasync task内で直接回し、各要素ごとに`await broker...`」は該当なし。

近い既存パターン:

- `hfm_quote_tail_loop()`はasync loop内で同期`for raw_line in lines`を回し、各quoteを`await _dispatch()`する。`Delta_Engine_Pro4web/webapp/hfm_quote_tailer.py:77-84`、`Delta_Engine_Pro4web/webapp/hfm_quote_tailer.py:115-131`
- `_dispatch()`はcallback戻り値がawaitableならawaitする。`Delta_Engine_Pro4web/webapp/hfm_quote_tailer.py:71-74`
- main側callbackは`await broker.on_hfm_quote()`し、このloopをtask化する。`Delta_Engine_Pro4web/webapp/main.py:416-426`
- `ReplayPipeline.run()`は同期raw列を同期`for`し、executor threadから`run_coroutine_threadsafe()`でbroker callbackをapp loopへ渡す。`Delta_Engine_Pro4web/src/pipeline.py:495-497`、`Delta_Engine_Pro4web/src/pipeline.py:677-697`、`Delta_Engine_Pro4web/webapp/main.py:239-266`、`Delta_Engine_Pro4web/webapp/main.py:371-379`

間隔制御:

- live bookは`webapp.book_update_interval_ms`を秒へ変換する。`Delta_Engine_Pro4web/webapp/main.py:231-237`
- schema defaultは100ms、最小10ms。`Delta_Engine_Pro4web/src/config.py:323-330`
- 現設定値は100ms。`Delta_Engine_Pro4web/config/config.yaml:80-87`
- pumpは各`project_once()`後に`await asyncio.sleep(interval_sec)`する。`Delta_Engine_Pro4web/webapp/book_projection.py:225-249`、`Delta_Engine_Pro4web/webapp/book_projection.py:296-299`
- `frame_source.interval_ms`は再構築stateのsampling間隔として`sample_states()`へ渡され、送信sleepは持たない。`Delta_Engine_Pro4web/webapp/heatmap_frame_source.py:43-59`
- market replayには別に`config.replay.speed`によるsource-time対wall-timeのblocking sleepがある。`Delta_Engine_Pro4web/src/pipeline.py:440-464`、`Delta_Engine_Pro4web/src/pipeline.py:569-585`

## M5. live bookとreplay heatmap bookの共存

WebSocketからHeatmapへのbook経路:

- brokerは`BOOK_UPDATE` envelopeを生成しbroadcastする。`Delta_Engine_Pro4web/webapp/push_broker.py:250-299`
- browserはWebSocket JSONを`handle()`へ渡す。`Delta_Engine_Pro4web/webapp/static/index.html:1004-1011`
- `handle()`の`BOOK_UPDATE`分岐から`onBookUpdate()`へ渡す。`Delta_Engine_Pro4web/webapp/static/index.html:1029-1067`
- `onBookUpdate()`はpayloadを`S.liveBook`へ保存し、`HEATMAP_UI.ingestBook()`へ渡す。`Delta_Engine_Pro4web/webapp/static/index.html:1085-1088`

異なる`book_stream_id`の扱い:

- payload検証でUUID、sequence、時刻、update ID、depth、level順序等を確認する。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:49-107`
- 現stream IDと異なる場合、`restartCount`を増加させ、`BOOK STREAM RESTART` gapを追加し、`expectedSequence`をnullへ戻す。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:203-211`
- その後、新stream IDを保存し、新しいsequence追跡を開始する。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:212-225`
- restart分岐では既存`frames`をclearしていない。新しいsynced frameは既存frame列へappendされる。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:205-237`
- 同一stream内の小さいsequenceはduplicate、大きいsequenceはdelivery gapとして扱う。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:213-225`

共存状態:

- replay／live pipeline生成は同じ`if/else`で排他。`Delta_Engine_Pro4web/webapp/main.py:179-186`
- task起動も同じ`if/else`で排他。replay時はlive book taskが`None`、live時だけlive book taskが起動する。`Delta_Engine_Pro4web/webapp/main.py:371-387`
- 現HEADで`iter_book_projections()`を参照するproductionコードはなく、定義とテスト参照だけ。`Delta_Engine_Pro4web/webapp/heatmap_frame_source.py:43-66`
- 現HEADのreplay分岐ではreplay Heatmap book供給もlive book供給も起動していない。`Delta_Engine_Pro4web/webapp/main.py:371-379`

## M6. WebSocketからCanvasまでの経路

1. pumpがprojectionを作り、send callbackをawaitする。`Delta_Engine_Pro4web/webapp/book_projection.py:267-280`
2. callbackは`broker.on_book_update`。`Delta_Engine_Pro4web/webapp/main.py:231-237`
3. brokerが`BOOK_UPDATE`を生成し、clientへ`send_text()`する。`Delta_Engine_Pro4web/webapp/push_broker.py:250-299`、`Delta_Engine_Pro4web/webapp/push_broker.py:188-198`
4. 再接続時はcached latest bookも登録直後に送られる。`Delta_Engine_Pro4web/webapp/push_broker.py:165-176`
5. browserがJSON parse後に`handle()`へ渡す。`Delta_Engine_Pro4web/webapp/static/index.html:1006-1011`
6. `BOOK_UPDATE`分岐が`onBookUpdate()`を呼ぶ。`Delta_Engine_Pro4web/webapp/static/index.html:1029-1067`
7. `onBookUpdate()`が`HEATMAP_UI.ingestBook()`を呼ぶ。`Delta_Engine_Pro4web/webapp/static/index.html:1085-1088`
8. setup済みAPIが`chart.ingestBook()`へ渡す。`Delta_Engine_Pro4web/webapp/static/index.html:2387-2397`
9. Canvasが`HeatmapBookStore.ingest()`を呼び、描画要求を登録する。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:648-662`
10. storeはpayloadを検証し、synced frameを保持する。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:193-237`
11. `requestDraw()`がRAF経由で`render()`を呼ぶ。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:699-705`
12. `render()`がbaseを構築してCanvasへ転写する。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:722-742`
13. `buildBase()`がframe列からtime columns、interval、rasterを作り描画する。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:744-879`

条件上の事実:

- setupはWebSocket `connect()`より前に同期実行される。`Delta_Engine_Pro4web/webapp/static/index.html:2371-2419`、`Delta_Engine_Pro4web/webapp/static/index.html:2465`
- gate=true、Heatmap module存在、`PHASE5_FUSION_ENABLED=true`の条件では上記各中継先が定義済み。`Delta_Engine_Pro4web/webapp/static/index.html:959-982`、`Delta_Engine_Pro4web/webapp/static/index.html:1066`、`Delta_Engine_Pro4web/webapp/static/index.html:2371-2397`
- 初期modeはFootprintなので、bookはstoreへingestされるがCanvas描画要求はvisible=falseでreturnする。`Delta_Engine_Pro4web/webapp/static/index.html:2418`、`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:699-704`
- HEATMAPボタン選択時に`chart.setVisible(true)`が描画要求を起こす。`Delta_Engine_Pro4web/webapp/static/index.html:2398-2406`、`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:641`

## 保護ファイル接触の見込み一覧

### main.py

- frame source import追加位置となる既存import群。`Delta_Engine_Pro4web/webapp/main.py:33-55`
- recording directory／intervalを解決するlifespan設定領域。`Delta_Engine_Pro4web/webapp/main.py:120-137`
- 既存live pump構築領域。`Delta_Engine_Pro4web/webapp/main.py:231-237`
- replay時に現在`book_projection_task=None`としているtask分岐。`Delta_Engine_Pro4web/webapp/main.py:371-388`
- replay供給開始後も現在`DISABLED_REPLAY`を出すlifespan stats領域。`Delta_Engine_Pro4web/webapp/main.py:428-444`
- task登録とshutdownの既存共通経路。`Delta_Engine_Pro4web/webapp/main.py:568-590`
- `/api/stats`側の`DISABLED_REPLAY`領域。`Delta_Engine_Pro4web/webapp/main.py:873-889`

### index.html

- gate値の変更対象は`ORDER_BOOK_HEATMAP_ENABLED`定義行。`Delta_Engine_Pro4web/webapp/static/index.html:969`
- setup、store、Canvas、API、mode切替の既存実装範囲。`Delta_Engine_Pro4web/webapp/static/index.html:2370-2419`
- BOOK_UPDATE dispatchの既存実装範囲。`Delta_Engine_Pro4web/webapp/static/index.html:1029-1067`
- `onBookUpdate→ingestBook`の既存実装範囲。`Delta_Engine_Pro4web/webapp/static/index.html:1085-1088`

## 参照ファイルのHEAD SHA-256・byte・LF・CR

| HEADファイル:行範囲 | SHA-256 | byte | LF | CR |
|---|---|---:|---:|---:|
| `Delta_Engine_Pro4web/webapp/main.py:1-975` | `FEFA73A2B6E54A1F7710B3606BA946B7E3055FAB3B93B3720BB1C4F9289233EA` | 38,528 | 975 | 0 |
| `Delta_Engine_Pro4web/src/config.py:1-486` | `F08857A76D6446E3C2DB11F35337235B894E0BB374D75F654093F4921DE43A28` | 18,055 | 486 | 0 |
| `Delta_Engine_Pro4web/config/config.yaml:1-158` | `D238C66E2476E409135AD7F1677BE81BC64C47FD7CC7B79304FF772EEB76B960` | 3,497 | 158 | 0 |
| `Delta_Engine_Pro4web/docker-compose.yml:1-31` | `DF117FFF755B5B352E49697AD2C5156415F89D047EADB5257D6E046AED4FF76E` | 1,448 | 31 | 0 |
| `Delta_Engine_Pro4web/webapp/heatmap_frame_source.py:1-66` | `15C8DAC80B0AF5DD0DFB497325CA2B236D7892C5D767CECA9DB15B05633E8B7F` | 2,067 | 66 | 0 |
| `Delta_Engine_Pro4web/webapp/book_projection.py:1-299` | `591BBB8A43946FCDE43CD04B42026BD03DA1BE55135CA08491D295DB8E755D99` | 9,154 | 299 | 0 |
| `Delta_Engine_Pro4web/webapp/push_broker.py:1-593` | `67522B9460DDAA53756A3404B4BC32BCC6E910B63707845A81BA8784AE129C3B` | 25,447 | 593 | 0 |
| `Delta_Engine_Pro4web/webapp/hfm_quote_tailer.py:1-136` | `306ACE4257965C183A068D456095F284565F08E7ED0C640608777DC6148C0568` | 4,698 | 136 | 0 |
| `Delta_Engine_Pro4web/src/pipeline.py:1-2164` | `B47209211031B3DD9B9B27761A4B1645E724268288FECC9F1A1DBF8AE472A235` | 99,089 | 2,164 | 0 |
| `Delta_Engine_Pro4web/src/acquisition/depth_history_recorder.py:1-348` | `5BB3C42F110720E6A64DB0F63E0CAC91460EE9BB98377761BED2EAC2F408BE7A` | 12,886 | 348 | 0 |
| `Delta_Engine_Pro4web/src/heatmap/reconstruct.py:1-573` | `84639422635CC01678CFB1E622FA561DF0B51D733A3262DA4A2B3A25C16BEB0C` | 20,394 | 573 | 0 |
| `Delta_Engine_Pro4web/webapp/persistent_depth_writer.py:1-85` | `451669F63D108DB42A5E84490B36A3A063809FD6C3BE383F522507065B61FFCF` | 3,163 | 85 | 0 |
| `Delta_Engine_Pro4web/webapp/static/index.html:1-2562` | `BFC9F54E32415CEDA6E456FE858F942F1D1D36E7FDA97F808DCDC684CB448964` | 183,646 | 2,562 | 0 |
| `Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:1-1226` | `9F362BAF58FF79ED24A10133B98ED1FCBB61D14D150BC93CBB70968319E1A807` | 62,708 | 1,226 | 0 |

## Git証跡

```text
git rev-parse HEAD
2fea7efebbe64b86b3a62bf1645ffcf3d3946dd4
```

```text
git status --porcelain -- Delta_Engine_Pro4web/
?? Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/
```

```text
git diff --cached --name-only
```

出力なし。参照14ファイルの`git diff --name-only HEAD -- <paths>`も出力なし。

## 調査終了境界

- Task 2 source実装は行っていない。
- `main.py`、`index.html`を含む既存sourceは変更していない。
- 新規作成したのは本調査報告書のみ。
- 本調査報告書はstageしていない。
