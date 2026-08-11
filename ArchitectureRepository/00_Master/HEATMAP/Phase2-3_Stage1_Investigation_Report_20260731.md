# Phase 2-3 Stage 1 調査報告

Version: 1.0  
作成日: 2026-07-31  
対象: DeltaEngine05M / Heatmap Phase 2-3

## 0. 行番号とリポジトリ状態の記法

- `H:` = `git show HEAD:<path>`で取得したHEAD版の行番号
- `W:` = 現在の作業ツリーの行番号
- 未追跡ファイルはHEADに存在しないため、`W:`のみ

調査時のHEAD:

```text
869dc83c9556d74d32853ddcd061ce66bf01fa13
```

HEADの`src/heatmap/`に存在するファイル:

```text
Delta_Engine_Pro4web/src/heatmap/__init__.py
Delta_Engine_Pro4web/src/heatmap/reconstruct.py
```

`binner.py`、`render_static.py`、`transform.py`およびTask 4計測物は未追跡の作業ツリーファイルである。`git status --porcelain`は空ではない。最終生出力は本報告末尾に掲載する。

## I1. RenderReport.total_ms

`RenderReport`は次を保持する。

```text
output_path, width, height, price_bins, time_cols, gap_columns,
bytes_written, aggregation_ms, transform_ms, render_ms, total_ms
```

根拠: `W:Delta_Engine_Pro4web/src/heatmap/render_static.py:37-51`

計測境界:

- `total_start_ns`は描画関数内の検証後、出力パス生成直後に開始する。`W:Delta_Engine_Pro4web/src/heatmap/render_static.py:73-81`
- `transform_ms`は全セルの`grid_cell_raster_bounds`生成だけを計測する。`W:Delta_Engine_Pro4web/src/heatmap/render_static.py:83-97`
- `transform_ms`終了後、幅・高さの最大値算出と空ラスタ検証が行われる。`W:Delta_Engine_Pro4web/src/heatmap/render_static.py:99-102`
- `render_ms`は色スケール構築、pixel buffer生成、セル塗装、PNG encode、親ディレクトリ生成、`write_bytes`までを含む。`W:Delta_Engine_Pro4web/src/heatmap/render_static.py:104-143`
- `total_ms`は`total_start_ns`からPNG書き込み後までの実測値である。`W:Delta_Engine_Pro4web/src/heatmap/render_static.py:140-144`
- `aggregation_ms`は`bin_samples`済みグリッドを受け取るため明示的に0である。`W:Delta_Engine_Pro4web/src/heatmap/render_static.py:65-70,145-156`

したがって`total_ms`はtransform+renderの単純和ではなく、PNG I/Oを含む関数内総時間である。transformとrenderの間で個別タイマーに含まれない処理は幅・高さ算出と検証である。タイマー呼び出し・report構築前までの境界オーバーヘッドも`total_ms`側にだけ含まれる。`W:Delta_Engine_Pro4web/src/heatmap/render_static.py:81-156`

Task 4 `last_report`の差:

- Full: `20320.174 - 3127.441 - 17148.5707 - 0 = 44.1623 ms`
  - 根拠値: `W:ArchitectureRepository/00_Master/HEATMAP/tools_p22/render_check_metrics.json:73-83`
- Downsampled: `5957.0337 - 882.7213 - 5065.8872 - 0 = 8.4252 ms`
  - 根拠値: `W:ArchitectureRepository/00_Master/HEATMAP/tools_p22/render_check_metrics.json:24-34`

この差をさらに分解するタイマーは存在しない。ソース上の未分離区間は`render_static.py:99-103`と各タイマー境界である。

## I2. `src/heatmap/`公開資産

### `__init__.py`

1 byteの空ファイルで公開定義なし。`H/W:Delta_Engine_Pro4web/src/heatmap/__init__.py:1`

### `binner.py` — 未追跡

- `HeatmapGrid`
  - fields: `price_bin`, `price_bins`, `sample_times_ms`, `bid_quantities`, `ask_quantities`, `gap_columns`
  - `W:Delta_Engine_Pro4web/src/heatmap/binner.py:19-33`
  - `price_count -> int`: `W:Delta_Engine_Pro4web/src/heatmap/binner.py:49-51`
  - `time_count -> int`: `W:Delta_Engine_Pro4web/src/heatmap/binner.py:53-55`
- `bin_samples(samples: Iterable[tuple[int, OrderBookSnapshot]], price_bin: Decimal, max_time_cols: int) -> HeatmapGrid`
  - `W:Delta_Engine_Pro4web/src/heatmap/binner.py:58-62`

### `reconstruct.py`

- `SegmentIntegrityError(RuntimeError)`: `H/W:Delta_Engine_Pro4web/src/heatmap/reconstruct.py:35-36`
- `SegmentInfo(path: Path, manifest: dict, started_at: str)`: `H/W:Delta_Engine_Pro4web/src/heatmap/reconstruct.py:39-45`
- `DepthHistoryReader`
  - `__init__(directory: Path)`: `H/W:Delta_Engine_Pro4web/src/heatmap/reconstruct.py:51-53`
  - `segments() -> list[SegmentInfo]`: `H/W:Delta_Engine_Pro4web/src/heatmap/reconstruct.py:55-95`
  - `iter_records() -> Iterator[dict]`: `H/W:Delta_Engine_Pro4web/src/heatmap/reconstruct.py:97-113`
- `ReconstructionEvent(kind: str, event_time_ms: int, last_update_id: int | None, epoch: int)`
  - `H/W:Delta_Engine_Pro4web/src/heatmap/reconstruct.py:153-160`
- `DepthReconstructor`
  - `__init__(*, symbol="BTCUSDT", max_buffered_diffs=10000, max_attempts=1)`: `H/W:Delta_Engine_Pro4web/src/heatmap/reconstruct.py:163-178`
  - `run(records: Iterable[dict]) -> Iterator[ReconstructionEvent]`: `H/W:Delta_Engine_Pro4web/src/heatmap/reconstruct.py:180-201`
  - `snapshot() -> OrderBookSnapshot | None`: `H/W:Delta_Engine_Pro4web/src/heatmap/reconstruct.py:203-206`
  - `sample_states(records, *, interval_ms: int) -> Iterator[tuple[int, OrderBookSnapshot]]`: `H/W:Delta_Engine_Pro4web/src/heatmap/reconstruct.py:208-243`
  - `counters -> dict[str, int]`: `H/W:Delta_Engine_Pro4web/src/heatmap/reconstruct.py:245-256`

### `transform.py` — 未追跡

- `PixelViewport(left, top, width, height: Decimal)`: `W:Delta_Engine_Pro4web/src/heatmap/transform.py:22-29`
  - `right -> Decimal`: `W:Delta_Engine_Pro4web/src/heatmap/transform.py:43-45`
  - `bottom -> Decimal`: `W:Delta_Engine_Pro4web/src/heatmap/transform.py:47-49`
- `GridIndex(price_index: int, time_index: int)`: `W:Delta_Engine_Pro4web/src/heatmap/transform.py:52-57`
- `PixelPoint(x: Decimal, y: Decimal)`: `W:Delta_Engine_Pro4web/src/heatmap/transform.py:60-65`
- `PixelRect(left, top, right, bottom: Decimal)`: `W:Delta_Engine_Pro4web/src/heatmap/transform.py:68-75`
- `RasterRect(left, top, right, bottom: int)`: `W:Delta_Engine_Pro4web/src/heatmap/transform.py:78-85`
- `grid_to_pixel(...) -> PixelPoint`: `W:Delta_Engine_Pro4web/src/heatmap/transform.py:88-108`
- `pixel_to_grid(...) -> GridIndex`: `W:Delta_Engine_Pro4web/src/heatmap/transform.py:111-150`
- `grid_cell_bounds(...) -> PixelRect`: `W:Delta_Engine_Pro4web/src/heatmap/transform.py:153-186`
- `grid_cell_raster_bounds(...) -> RasterRect`: `W:Delta_Engine_Pro4web/src/heatmap/transform.py:189-211`

### `render_static.py` — 未追跡

- `RenderReport(...)`: `W:Delta_Engine_Pro4web/src/heatmap/render_static.py:37-51`
- `render_heatmap(grid: HeatmapGrid, viewport: PixelViewport, out_path: Path | str) -> RenderReport`
  - `W:Delta_Engine_Pro4web/src/heatmap/render_static.py:60-64`

## I3. recording駆動入力経路

時系列順序:

1. ファイル候補を名前順に列挙し、manifestと整合検査する。`H/W:Delta_Engine_Pro4web/src/heatmap/reconstruct.py:63-93`
2. 最終的なsegment順はmanifestの`started_at`昇順である。`H/W:Delta_Engine_Pro4web/src/heatmap/reconstruct.py:95`
3. 各segmentをその順で開き、JSONLを行順にyieldする。`H/W:Delta_Engine_Pro4web/src/heatmap/reconstruct.py:97-113`
4. `DepthReconstructor.run`は入力順に処理し、tradeをskip、`depthUpdate`と`depthSnapshot`を各経路へ渡す。`H/W:Delta_Engine_Pro4web/src/heatmap/reconstruct.py:180-201`
5. event timeは各recordの`E`から取得する。`H/W:Delta_Engine_Pro4web/src/heatmap/reconstruct.py:489-491`
6. `sample_states`は`DIFF_APPLIED`のみをサンプル源にし、`interval_ms`単位の固定event-time間隔でyieldする。`H/W:Delta_Engine_Pro4web/src/heatmap/reconstruct.py:208-225,227-243`
7. gapまたはsync failureで次回サンプル起点をリセットする。`H/W:Delta_Engine_Pro4web/src/heatmap/reconstruct.py:220-223`
8. 1つのDIFF時刻が複数の未出力intervalを跨いだ場合、同一の最新snapshotを複数時刻へyieldする。`H/W:Delta_Engine_Pro4web/src/heatmap/reconstruct.py:237-243`

Task 4は次の経路である。

- `reader.iter_records()` → `reconstructor.sample_states(..., interval_ms)`:
  `W:ArchitectureRepository/00_Master/HEATMAP/tools_p22/render_check.py:212-221`
- `bin_samples(..., max_time_cols=len(samples))`:
  `W:ArchitectureRepository/00_Master/HEATMAP/tools_p22/render_check.py:225-229`
- CLI既定`interval_ms=1000`:
  `W:ArchitectureRepository/00_Master/HEATMAP/tools_p22/render_check.py:323`

`bin_samples`:

- 入力をtuple化し、sample timeがstrict ascendingであることを検査する。`W:Delta_Engine_Pro4web/src/heatmap/binner.py:85-88,139-153`
- 出力行列は価格行×時間列である。`W:Delta_Engine_Pro4web/src/heatmap/binner.py:19-33,119-135`
- gapは隣接時刻差の最小値をnominal intervalとし、それより大きい差をgapにする。`W:Delta_Engine_Pro4web/src/heatmap/binner.py:167-177`
- 時間列削減時は各連続segmentを独立して整数規則で選択する。`W:Delta_Engine_Pro4web/src/heatmap/binner.py:65-74,156-164,180-206`

1フレーム分を返す公開APIは該当なし。`HeatmapGrid`は全時間軸と全行列、およびcount propertyだけを公開する。`W:Delta_Engine_Pro4web/src/heatmap/binner.py:28-55`。公開関数は全グリッドを生成する`bin_samples`のみである。`W:Delta_Engine_Pro4web/src/heatmap/binner.py:58-62`

## I4. Canvas配置とデータ送出

### サーバ経路

- `LatestBookProjectionPump`は`OrderBookStateManager`のcurrent stateを既定100ms間隔で投影する。`H:Delta_Engine_Pro4web/webapp/main.py:227-233`、`H:Delta_Engine_Pro4web/webapp/book_projection.py:225-249,296-299`
- 同一fingerprintの投影は送信しない。`H:Delta_Engine_Pro4web/webapp/book_projection.py:267-294`
- 同期済み投影はbid/askを各`depth_levels`件に制限する。`H:Delta_Engine_Pro4web/webapp/book_projection.py:190-221`
- `PushBroker`はpayloadをJSON化し、登録WebSocketへ`send_text`する。`H:Delta_Engine_Pro4web/webapp/push_broker.py:160-192`
- `/ws`は接続後にHELLOを送り、brokerへ登録する。`H:Delta_Engine_Pro4web/webapp/main.py:602-625`

### 現行データ形状

`BookProjection`は次を持つ。

```text
projection_time, event_time, last_update_id, sync_state,
bids, asks, depth_levels, best_bid, best_ask, spread, age_ms
```

根拠: `H:Delta_Engine_Pro4web/webapp/book_projection.py:31-45`

作業ツリーの`BOOK_UPDATE`には加えて`book_stream_id`と`book_sequence`がある。`W:Delta_Engine_Pro4web/webapp/push_broker.py:250-299`

ブラウザ側はこのfull snapshot形状を検査し、bid/askをtyped arrayへ変換する。`H/W:Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:49-107,110-128`

既存送出形状は、サーバ計算済みグリッド、RGB値、セル差分ではなく、各時点のbounded bid/ask snapshotである。ブラウザがsnapshot列からintervalと時間×価格ラスタを生成する。`H/W:Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:475-510,563-573,793-843`

### HEADと作業ツリーの差

HEADのブラウザvalidatorは`book_stream_id`と`book_sequence`を必須にしている。`H:Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:49-60`

一方、HEADの`PushBroker.on_book_update` payloadには両フィールドがない。`H:Delta_Engine_Pro4web/webapp/push_broker.py:244-288`

現在の未commit作業ツリーでは両フィールドが追加されている。`W:Delta_Engine_Pro4web/webapp/push_broker.py:261-270`

### 保護ファイル接点

`index.html`には既に次が存在する。

- モード切替ボタン、Canvas、status/detail: `H:Delta_Engine_Pro4web/webapp/static/index.html:754-781`
- `orderbook_heatmap.js`読込: `H:Delta_Engine_Pro4web/webapp/static/index.html:957-959`
- WebSocket受信から`ingestBook`: `H:Delta_Engine_Pro4web/webapp/static/index.html:1004-1011,1061,1079-1082`
- Canvas/store生成とモード切替: `H:Delta_Engine_Pro4web/webapp/static/index.html:2323-2372`

ただしpresentation gateは`false`で、false時はCanvasとボタンを隠してreturnする。`H:Delta_Engine_Pro4web/webapp/static/index.html:969,2329-2333`。現行中央画面で表示を有効にする接点は最低でもこのgateである。

`main.py`にはlive `BOOK_UPDATE`経路がある。`H:Delta_Engine_Pro4web/webapp/main.py:227-233,602-625`。HEADのwebapp全体にはrecording/heatmap専用のHTTPまたはWebSocket routeは該当なし。raw depth historyは記録用としてlifespanへ接続されている。`H:Delta_Engine_Pro4web/webapp/main.py:122-130,371,582-584`

## I5. 16msフレーム計測

Task 4はfull 20回、downsampled 20回である。`W:ArchitectureRepository/00_Master/HEATMAP/tools_p22/render_check_metrics.json:39,88`。計測ループは毎回PNGを再生成する。`W:ArchitectureRepository/00_Master/HEATMAP/tools_p22/render_check.py:150-170,237-247,286-309`

既存Canvas計測:

- `renderTimes`と`ingestTimes`を保持する。`H/W:Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:621-622`
- ingest計測はstoreへの取込だけである。`H/W:Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:648-667`
- 描画は`requestAnimationFrame`で予約され、同時pendingを1件に集約する。`H/W:Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:699-704`
- `render()`の計測開始はresize後である。`H/W:Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:722-726`
- `baseDirty`時だけ時間列構築、interval生成、ラスタ生成を含む。`H/W:Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:727-731,793-844`
- 可視Canvasへの`drawImage`とinteraction描画後に終了時刻を取る。`H/W:Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:733-740`
- 最新240件を保持し、nearest-rank p95を算出する。`H/W:Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:25-30,698,740`
- statusとmetricsへ`renderP95`を公開する。`H/W:Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:1022-1023,1192-1202`

既存の`renderTimes`は、`baseDirty=true`時のtransform/raster/drawと、`baseDirty=false`時の再合成描画が同じ系列に入る。`H/W:Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:727-740`

また、次は含まない。

- ingest開始からrAF callback開始まで: `H/W:Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:648-704`
- resize時間: `H/W:Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:722-726`
- `drawImage`後にブラウザcompositorが画面提示を完了した時刻: 終了点は同じcallback内の`performance.now()`である。`H/W:Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:733-740`

per-frame render p95の仕組みは存在するが、入力→transform→描画→画面提示までを一括する計測は該当なし。既存の計測境界候補はrAF callback開始`704-726`とCanvas描画直後`736-740`である。

## I6. カラーマッピング

静的renderer:

- 定数:
  - `_ONE = Decimal("1")`
  - `_MIN_INTENSITY = Decimal("32")`
  - `_INTENSITY_SPAN = Decimal("223")`
  - `_BACKGROUND = (0,0,0)`
  - `W:Delta_Engine_Pro4web/src/heatmap/render_static.py:29-34`
- bid/askは別々のscaleを作る。`W:Delta_Engine_Pro4web/src/heatmap/render_static.py:104-114`
- 正値quantityを`(1+quantity).ln()`へ変換する。`W:Delta_Engine_Pro4web/src/heatmap/render_static.py:172-175`
- p1/p99をlower/upperにする。`W:Delta_Engine_Pro4web/src/heatmap/render_static.py:178-181`
- quantileはDecimal補間である。`W:Delta_Engine_Pro4web/src/heatmap/render_static.py:184-199`
- 値をp1-p99へclipし、32〜255へ変換する。`W:Delta_Engine_Pro4web/src/heatmap/render_static.py:202-211`
- gap列は塗らず、初期値0のpixel bufferを維持する。`W:Delta_Engine_Pro4web/src/heatmap/render_static.py:115,117-120`
- askは赤channel、bidは青channel、greenは0である。数量同士は加算しない。`W:Delta_Engine_Pro4web/src/heatmap/render_static.py:214-239`

Canvasで同じ確定値を参照する対象は、上記定数と`_build_scale`、`_quantile`、`_intensity`、`_paint_cell`である。`W:Delta_Engine_Pro4web/src/heatmap/render_static.py:29-34,172-239`

現在のCanvas実装値:

- 多色`HEAT_STOPS`を使用する。`H/W:Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:16-19`
- bid/askを合わせた値から単一Q95 scaleを作り、`Math.log1p(quantity)/Math.log1p(q95)`を使う。`H/W:Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:513-527,798-800`
- bid/ask双方に同じ多色paletteを使い、上下半分へ空間分離する。`H/W:Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:633,828-839`
- gapは黒ではなく灰色overlayである。`H/W:Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:902-910`

## I7. ADR整合に関係する論点

### ADR-003

ADR本文はsingle-process asyncio event loopを採用する。`ArchitectureRepository/00_Master/ADR/ADR-003_Concurrency_Model_v3.0.md:20-29`

同ADRはスレッドを全面禁止する記述ではなく、blocking/CPU-heavy処理を`loop.run_in_executor`へoffloadする規則である。`ArchitectureRepository/00_Master/ADR/ADR-003_Concurrency_Model_v3.0.md:26-30,51-55`

現行接点:

- live pipelineはsingle asyncio event loopとして定義される。`H:Delta_Engine_Pro4web/src/pipeline.py:920-924`
- `PushBroker`はasyncio lockの下でclientへ順番にawait送信する。`H:Delta_Engine_Pro4web/webapp/push_broker.py:140-192`
- 静的rendererは同期Python loop、zlib、ファイルI/Oを同一呼出し内で実行する。`W:Delta_Engine_Pro4web/src/heatmap/render_static.py:83-144`
- Canvas描画はブラウザ側`requestAnimationFrame`で実行される。`H/W:Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:699-740`
- raw recorder自身は「単一loopから同期呼出し、スレッド不使用」と明記する。`H:Delta_Engine_Pro4web/src/acquisition/depth_history_recorder.py:7-10`

論点は、Python側でframe用CPU処理を行う場合のevent-loop占有境界、executor利用時の共有状態境界、ブラウザ側rAFとの責任分離である。根拠となる規則はADR-003の`26-29`である。

### ADR-011

ADR-011:

- 取得データを関連性判断で間引かず全量記録する。`ArchitectureRepository/00_Master/ADR/ADR-011_No_Decimation_Recording_v3.0.md:12-14`
- 表示層と蓄積層を分離し、表示用の間引き蓄積を作らない。`ArchitectureRepository/00_Master/ADR/ADR-011_No_Decimation_Recording_v3.0.md:15`
- 生メッセージを優先し、加工物は再計算可能な派生とする。`ArchitectureRepository/00_Master/ADR/ADR-011_No_Decimation_Recording_v3.0.md:16-17`

現行接点:

- `DataReceiver`はvalidate成功後にrecorderへ書き、その後forwardする。`H:Delta_Engine_Pro4web/src/acquisition/receiver.py:86-105`
- pipelineは`default_validate && event_filter`をrecord前のvalidateとして設定する。`H:Delta_Engine_Pro4web/src/pipeline.py:1372-1378`
- `DepthHistoryRecorder`は検証済み生WSイベントとREST snapshotを記録し、UI投影・切り詰めを行わない。`H:Delta_Engine_Pro4web/src/acquisition/depth_history_recorder.py:1-15`
- `LatestBookProjectionPump`は表示用にtop Nへ制限し、同一状態を送出抑制する。`H:Delta_Engine_Pro4web/webapp/book_projection.py:210-221,267-294`
- browser storeは900秒・9000 frameでpruneする。`H/W:Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:150-155,242-251`
- `bin_samples`には表示用時間列削減が存在する。`W:Delta_Engine_Pro4web/src/heatmap/binner.py:65-74,156-164`

論点は、bounded projection・時間列削減・browser retentionが蓄積層へ逆流しない境界と、record前validate/event filterの対象範囲である。

### Replay/Live applyコア

仕様記述ではrecorded raw eventがlive WebSocketを置換し、下流処理を同一としている。`H:Delta_Engine_Pro4web/src/pipeline.py:1-10`

実装:

- Replayは`OrderBookStateManager`を生成する。`H:Delta_Engine_Pro4web/src/pipeline.py:494-530`
- Replay depthは`DataNormalizer.process_depth`後に`book_state.apply`する。`H:Delta_Engine_Pro4web/src/pipeline.py:672-688`
- Liveも同じ`OrderBookStateManager`を生成する。`H:Delta_Engine_Pro4web/src/pipeline.py:1438-1447`
- verified snapshot→initial sync→verified diffを同じmanagerへ適用する。`H:Delta_Engine_Pro4web/src/pipeline.py:1687-1712`
- 通常live depthも`book_state.apply`する。`H:Delta_Engine_Pro4web/src/pipeline.py:1825-1894`
- 共通apply本体は`OrderBookStateManager.apply`である。`H:Delta_Engine_Pro4web/src/orderflow/orderbook.py:97-140`
- offline `DepthReconstructor`も同じmanagerを生成し、同じ`apply`と`apply_initial_sync`を使用する。`H/W:Delta_Engine_Pro4web/src/heatmap/reconstruct.py:258-263,293-320,370-409`
- offline側は`DataNormalizer`ではなく、raw recordから`OrderBookUpdate`を組み立てる独自境界を持つ。`H/W:Delta_Engine_Pro4web/src/heatmap/reconstruct.py:411-457`

論点は、recording frame生成を追加した場合にもstate mutationを`OrderBookStateManager.apply`経由に保つ境界と、offline独自normalization境界である。

## I8. 保護4ファイル接触棚卸し

| 保護ファイル | 区分 | 実物根拠 |
|---|---:|---|
| `webapp/static/index.html` | ○ | Canvas、ボタン、script、setupは既存だが、gateが`false`でfalse時に表示要素を隠してreturnする。`H:index.html:754-781,959,969,2323-2333` |
| `webapp/main.py` | △ | live用pumpと`/ws`は既存。`H:main.py:227-233,602-625`。recording/heatmap専用routeは該当なし。raw recorderは記録用途。`H:main.py:122-130,371,582-584` |
| `docker-compose.yml` | × | `data_05M`と`webapp/static`全体が既にbind mountされている。`H:docker-compose.yml:10-16`。raw history rootも既存環境変数にある。`H:docker-compose.yml:24-30` |
| `tests/webapp/test_book_update.py` | △ | 既存テストが`BOOK_UPDATE` payloadとreconnect cacheを固定する。`H:test_book_update.py:275-311`。wire shapeを維持する場合と変更する場合で接点が分岐する。 |

4ファイルとも現在の作業ツリーでは`M`である。最終`git status --porcelain`を末尾に掲載する。

## 参照21ファイルの識別値

```text
FILE ArchitectureRepository/00_Master/ADR/ADR-003_Concurrency_Model_v3.0.md
HEAD sha256=2556967937602A9572ADEC687BD1D3FA4A73946EFB5F63DA30E2114A6D307BBF bytes=2189 LF=66 CR=0
WT   sha256=2556967937602A9572ADEC687BD1D3FA4A73946EFB5F63DA30E2114A6D307BBF bytes=2189 LF=66 CR=0

FILE ArchitectureRepository/00_Master/ADR/ADR-011_No_Decimation_Recording_v3.0.md
HEAD sha256=F2509EA289A644B0EEA1884E34329F26E6784B638C21A8E6A6A1C9BA8C7C0175 bytes=3809 LF=28 CR=0
WT   sha256=833ACD61263F64B9964BF66F05BFE3FE66B7610C755BD550A5A55BA215562FCB bytes=3810 LF=28 CR=1

FILE ArchitectureRepository/00_Master/HEATMAP/tools_p22/render_check.py
HEAD N/A
WT   sha256=103F489CDADDA89DAD898489074E16684E4E1BD59C6A849C1C046AAAE06B2796 bytes=11159 LF=373 CR=0

FILE ArchitectureRepository/00_Master/HEATMAP/tools_p22/render_check_metrics.json
HEAD N/A
WT   sha256=1ECA9FCC2A8C16765595CC341E7611F389038F91C4A1876762C84E3D878500B4 bytes=3520 LF=120 CR=0

FILE Delta_Engine_Pro4web/docker-compose.yml
HEAD sha256=DF117FFF755B5B352E49697AD2C5156415F89D047EADB5257D6E046AED4FF76E bytes=1448 LF=31 CR=0
WT   sha256=6DCF2FAE7CE4DB114C8E686DAE62A7F9C6DB18B79C53040148B80F5E339F24B0 bytes=1449 LF=32 CR=0

FILE Delta_Engine_Pro4web/src/acquisition/depth_history_recorder.py
HEAD sha256=5BB3C42F110720E6A64DB0F63E0CAC91460EE9BB98377761BED2EAC2F408BE7A bytes=12886 LF=348 CR=0
WT   sha256=5BB3C42F110720E6A64DB0F63E0CAC91460EE9BB98377761BED2EAC2F408BE7A bytes=12886 LF=348 CR=0

FILE Delta_Engine_Pro4web/src/acquisition/receiver.py
HEAD sha256=B28B01D618E3718D4D71D6B56CE8FBF52D658A397AF11E0B5977939DA9EE84B9 bytes=3739 LF=106 CR=0
WT   sha256=B28B01D618E3718D4D71D6B56CE8FBF52D658A397AF11E0B5977939DA9EE84B9 bytes=3739 LF=106 CR=0

FILE Delta_Engine_Pro4web/src/acquisition/replay.py
HEAD sha256=E069634F1AC572E6DDB5570D447D8C7FD4DCE346DF011AF32679D9DA7208EBE2 bytes=2304 LF=73 CR=0
WT   sha256=E069634F1AC572E6DDB5570D447D8C7FD4DCE346DF011AF32679D9DA7208EBE2 bytes=2304 LF=73 CR=0

FILE Delta_Engine_Pro4web/src/heatmap/__init__.py
HEAD sha256=01BA4719C80B6FE911B091A7C05124B64EEECE964E09C058EF8F9805DACA546B bytes=1 LF=1 CR=0
WT   sha256=01BA4719C80B6FE911B091A7C05124B64EEECE964E09C058EF8F9805DACA546B bytes=1 LF=1 CR=0

FILE Delta_Engine_Pro4web/src/heatmap/binner.py
HEAD N/A
WT   sha256=15F41C721F41B680F7946714C4614C585E6D40F3783C0D8585030A4F8266F4C7 bytes=9299 LF=255 CR=0

FILE Delta_Engine_Pro4web/src/heatmap/reconstruct.py
HEAD sha256=84639422635CC01678CFB1E622FA561DF0B51D733A3262DA4A2B3A25C16BEB0C bytes=20394 LF=573 CR=0
WT   sha256=84639422635CC01678CFB1E622FA561DF0B51D733A3262DA4A2B3A25C16BEB0C bytes=20394 LF=573 CR=0

FILE Delta_Engine_Pro4web/src/heatmap/render_static.py
HEAD N/A
WT   sha256=AB9E040BCBAFD4E2D55A3B30AEEF728486E9A55366E35829BFB3F2234608A3AD bytes=8470 LF=264 CR=0

FILE Delta_Engine_Pro4web/src/heatmap/transform.py
HEAD N/A
WT   sha256=0A076B1274F907241D3A68D3267AA0E2065C91D5EC7BC30C9CB5EFC76B113C39 bytes=6766 LF=240 CR=0

FILE Delta_Engine_Pro4web/src/orderflow/orderbook.py
HEAD sha256=291D46612AEBE09CD4B7A60E46F30CB9E8602FDD53817A3D01170F669D424C05 bytes=11295 LF=290 CR=0
WT   sha256=291D46612AEBE09CD4B7A60E46F30CB9E8602FDD53817A3D01170F669D424C05 bytes=11295 LF=290 CR=0

FILE Delta_Engine_Pro4web/src/pipeline.py
HEAD sha256=F77F4998A86D4359FA60550D3389670D5A7631F6B35EF94804804EB4578A4BD4 bytes=98188 LF=2138 CR=0
WT   sha256=9313A7C07D80DC773E36C9D16F22268D3AAF7F1650D563E607085CDE8D8B3DAC bytes=100403 LF=2164 CR=1314

FILE Delta_Engine_Pro4web/tests/webapp/test_book_update.py
HEAD sha256=4E4969D34F31CB871C60A429487E07882C7F615399220C0B6C523174CB5DB5BF bytes=11038 LF=341 CR=0
WT   sha256=62DC21D34CC9C78C338676227E12EFB6795302B13BBE7EA589454CB6B108F5A4 bytes=15072 LF=458 CR=0

FILE Delta_Engine_Pro4web/webapp/book_projection.py
HEAD sha256=591BBB8A43946FCDE43CD04B42026BD03DA1BE55135CA08491D295DB8E755D99 bytes=9154 LF=299 CR=0
WT   sha256=591BBB8A43946FCDE43CD04B42026BD03DA1BE55135CA08491D295DB8E755D99 bytes=9154 LF=299 CR=0

FILE Delta_Engine_Pro4web/webapp/main.py
HEAD sha256=72DAC7191E076150EFA5E6D08E188BE14DE8AE31DE29B23CBE5A3EBD4D0B231B bytes=37678 LF=960 CR=0
WT   sha256=E4D9A6AEC7F1A515141BAFD7D880848A9FF7C7E3D16B5D695B6A8DB9BE3016A4 bytes=39478 LF=975 CR=950

FILE Delta_Engine_Pro4web/webapp/push_broker.py
HEAD sha256=D1F3D32E1706186DB375300AFF94C4B2A1D93313516642312FE6DFE17F5916AE bytes=23450 LF=549 CR=0
WT   sha256=D74F0F13B092055E7FA93D604A09E27278401B87D84444D1CB83B4C03AAF19BD bytes=25453 LF=593 CR=6

FILE Delta_Engine_Pro4web/webapp/static/index.html
HEAD sha256=A647D5D4405881082CBC07BF38C5D537E33032E7F0591115386BCC2A9A5B154C bytes=182084 LF=2515 CR=0
WT   sha256=5474C889B80550664EE3E3FB23ABC7252949471D8BF09E7D648DDA354024CEB5 bytes=183658 LF=2562 CR=12

FILE Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js
HEAD sha256=9F362BAF58FF79ED24A10133B98ED1FCBB61D14D150BC93CBB70968319E1A807 bytes=62708 LF=1226 CR=0
WT   sha256=9F362BAF58FF79ED24A10133B98ED1FCBB61D14D150BC93CBB70968319E1A807 bytes=62708 LF=1226 CR=0
```

## 最終HEAD・staging・status生出力

`git -C <root> rev-parse HEAD`

```text
869dc83c9556d74d32853ddcd061ce66bf01fa13
```

`git -C <root> diff --cached --name-only`

```text
```

`git -C <root> status --porcelain`

```text
 M ArchitectureRepository/00_Master/ORDER_BOOK_HEATMAP_IMPLEMENTATION_INSTRUCTION_V1_20260729.md
 M ArchitectureRepository/00_Master/ORDER_BOOK_HEATMAP_PHASE_H0_CHECKPOINT_20260729.md
 M ArchitectureRepository/00_Master/PROJECT_MEMORY.md
 M ArchitectureRepository/30_Modules/WebApp/Specifications/WebSocketPayload_Spec_v1.md
 M Delta_Engine_Pro4web/docker-compose.yml
 M Delta_Engine_Pro4web/src/pipeline.py
 M Delta_Engine_Pro4web/tests/webapp/test_book_update.py
 M Delta_Engine_Pro4web/webapp/main.py
 M Delta_Engine_Pro4web/webapp/push_broker.py
 M Delta_Engine_Pro4web/webapp/static/index.html
 M Delta_Engine_Pro4web/webapp/static/time_sales.js
?? ArchitectureRepository/00_Master/ABSORPTION_REALTIME_DISPLAY_FIX_CHECKPOINT_20260731.md
?? "ArchitectureRepository/00_Master/AI\343\202\263\343\203\241\343\203\263\343\203\210/"
?? ArchitectureRepository/00_Master/HEATMAP/Approval_P22_Task1_Go_Task2.md
?? ArchitectureRepository/00_Master/HEATMAP/Approval_P22_Task2_Go_Task3.md
?? ArchitectureRepository/00_Master/HEATMAP/Approval_P22_Task3_Go_Task4.md
?? ArchitectureRepository/00_Master/HEATMAP/Approval_P22_Task3_PreReport_Reply_v1.md
?? ArchitectureRepository/00_Master/HEATMAP/Instruction_P22_Task1_ReSubmit_v1.md
?? ArchitectureRepository/00_Master/HEATMAP/Instruction_P22_Task2_Submit_v1.md
?? ArchitectureRepository/00_Master/HEATMAP/Instruction_P22_Task3_Submit_v1.md
?? ArchitectureRepository/00_Master/HEATMAP/Instruction_P22_Task4_Fix_v1.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Stage1_Investigation_Report_20260731.md
?? ArchitectureRepository/00_Master/HEATMAP/Roadmap_Heatmap_Render_to_Dynamic_v1.md
?? ArchitectureRepository/00_Master/HEATMAP/p21_evidence/
?? ArchitectureRepository/00_Master/HEATMAP/tools_p22/
?? ArchitectureRepository/00_Master/HEATMAP/worktree_backup_pre_p21_20260730.patch
?? ArchitectureRepository/00_Master/HEATMAP/worktree_status_pre_p21_20260730.txt
?? ArchitectureRepository/00_Master/HEATMAP_Instruction_v1.5.md
?? ArchitectureRepository/00_Master/HOOK_STAGE2C4_CHECKPOINT_20260731.md
?? "ArchitectureRepository/00_Master/Heatmap_Handover_20260730 (1).md"
?? ArchitectureRepository/00_Master/Heatmap_Handover_20260730.md
?? ArchitectureRepository/00_Master/Instruction_Phase2-2_Renderer_v1.md
?? ArchitectureRepository/00_Master/SCHEDULED_TASK_RESUME_FIX_CHECKPOINT_20260731.md
?? ArchitectureRepository/00_Master/VWAP_CHART_RELATED_MODULE_INVENTORY_20260729.md
?? ArchitectureRepository/00_Master/VWAP_INVESTIGATION_20260729/
?? "ArchitectureRepository/00_Master/\343\203\210\343\203\252\343\202\254\343\203\274\344\275\234\346\210\220\346\214\207\347\244\272\346\233\270\347\276\244/DeltaEngine_\347\265\214\347\267\257\345\240\261\345\221\212_\347\254\2541\346\234\237-\347\254\2544\346\234\237_20260727.md"
?? "ArchitectureRepository/00_Master/\343\203\210\343\203\252\343\202\254\343\203\274\344\275\234\346\210\220\346\214\207\347\244\272\346\233\270\347\276\244/HOOK_AND_LEGACY_STRATEGY_INVENTORY_20260727.md"
?? "ArchitectureRepository/00_Master/\343\203\210\343\203\252\343\202\254\343\203\274\344\275\234\346\210\220\346\214\207\347\244\272\346\233\270\347\276\244/HOOK_AND_STRATEGY_CONTENT_GUIDE_20260727.md"
?? "ArchitectureRepository/00_Master/\343\203\210\343\203\252\343\202\254\343\203\274\344\275\234\346\210\220\346\214\207\347\244\272\346\233\270\347\276\244/HOOK_STAGE2C1_CONTAINER_RESTART_20260730.md"
?? "ArchitectureRepository/00_Master/\343\203\210\343\203\252\343\202\254\343\203\274\344\275\234\346\210\220\346\214\207\347\244\272\346\233\270\347\276\244/HOOK_STAGE2C1_GATE_DATA_20260729.md"
?? "ArchitectureRepository/00_Master/\345\256\237\351\201\213\347\224\250/"
?? "ArchitectureRepository/00_Master/\346\214\207\347\244\272\346\233\270_STAGE2C2_Hook\350\274\203\346\255\243_\345\210\206\345\270\203\351\233\206\350\250\210_v1.md"
?? Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/
?? Delta_Engine_Pro4web/src/heatmap/binner.py
?? Delta_Engine_Pro4web/src/heatmap/render_static.py
?? Delta_Engine_Pro4web/src/heatmap/transform.py
?? Delta_Engine_Pro4web/tests/heatmap/test_binner.py
?? Delta_Engine_Pro4web/tests/heatmap/test_render_static.py
?? Delta_Engine_Pro4web/tests/heatmap/test_transform.py
?? Delta_Engine_Pro4web/tests/webapp/test_absorption_realtime_display.py
?? pytest-vwap-ui-elevated/
?? vwap-audit.duckdb
?? vwap_first100.jsonl
?? vwap_restore_ws_capture.jsonl
?? vwap_ws_capture.jsonl
```

## 作業範囲

本Stage 1調査で新規生成したファイルは本調査報告のみである。`src/heatmap/`、保護4ファイル、git履歴、stagingへの変更操作は行っていない。
