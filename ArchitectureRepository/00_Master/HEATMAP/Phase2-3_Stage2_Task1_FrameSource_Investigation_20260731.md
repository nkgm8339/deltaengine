# Phase 2-3 Stage 2 Task 1 frame_source 調査報告

- 調査日: 2026-07-31
- 調査対象HEAD: `bf9512635d7a6f4d67a14d67d128fc528f6b6707`
- 範囲: J1〜J5の読み取り調査
- 実装・ソース変更・保護ファイル変更・git履歴変更・staging変更: なし

## J1. `sample_states` 戻り値の実体

### `tuple[int, OrderBookSnapshot]` の `int`

- `DepthReconstructor.sample_states(records, *, interval_ms)` の戻り型は `Iterator[tuple[int, OrderBookSnapshot]]` で、docstringは固定event-time intervalの同期済みstate copyを返すと記載する。`interval_ms` は正の整数として検証される。`Delta_Engine_Pro4web/src/heatmap/reconstruct.py:208-216`
- reconstruction eventの `event_time_ms` は入力recordのイベント名 `e` とフィールド `E` から、非負整数として取得される。`Delta_Engine_Pro4web/src/heatmap/reconstruct.py:483-491`
- 同じ値は `divmod(event_time_ms, 1000)` で秒とミリ秒へ分離され、UTC `datetime` に変換される。このため戻りtupleの `int` は入力record `E` に由来するUTC Unix epoch millisecondである。`Delta_Engine_Pro4web/src/heatmap/reconstruct.py:489-497`
- sampling対象は `DIFF_APPLIED` eventだけである。`GAP_DETECTED` または `SYNC_FAILED` では次のsample時刻がresetされ、それ以外のeventは除外される。`Delta_Engine_Pro4web/src/heatmap/reconstruct.py:220-225`
- 最初のsample時刻は最初に対象となった `DIFF_APPLIED.event_time_ms`。その後は `interval_ms` ずつ加算される。gap後に新しいevent時刻が直前sample時刻以下なら、直前sample時刻＋intervalへ補正される。`Delta_Engine_Pro4web/src/heatmap/reconstruct.py:227-243`
- 1つの `DIFF_APPLIED` が複数の未出力sample境界を越えている場合、`while next_sample_time <= event.event_time_ms` により、同じcurrent snapshotが複数の固定sample時刻に対してyieldされる。`Delta_Engine_Pro4web/src/heatmap/reconstruct.py:237-243`
- `DIFF_APPLIED.event_time_ms` 自体は、適用したdiff recordの `E` から生成される。`Delta_Engine_Pro4web/src/heatmap/reconstruct.py:396-409`

### `OrderBookSnapshot` の構造

- `OrderBookSnapshot` は `@dataclass(frozen=True)`。`symbol: str`、`last_update_id: int`、`bids: dict[Decimal, Decimal]`、`asks: dict[Decimal, Decimal]`、optional `event_time: datetime` を持つ。bid/ask dictは価格→数量で、数量は正値のみと定義される。`Delta_Engine_Pro4web/src/orderflow/orderbook.py:69-77`
- price lookupは、該当価格が無い場合にDecimal zeroを返す。`Delta_Engine_Pro4web/src/orderflow/orderbook.py:79-83`
- `OrderBookStateManager.snapshot()` は未初期化時に `None`、初期化済み時にbid/ask dictを `dict(...)` でcopyした `OrderBookSnapshot` を返す。snapshotの `event_time` は最新accepted state transitionのsource timeである。`Delta_Engine_Pro4web/src/orderflow/orderbook.py:165-185`
- reconstruction recordからbook updateを構築する際、bid/askはrecordの `b` / `a` から生成され、snapshot内の `event_time` へrecord `E` のUTC変換値が渡る。`Delta_Engine_Pro4web/src/heatmap/reconstruct.py:411-425`

## J2. `HeatmapGrid` の時間列構造

- モジュールはmatrix orientationを「price row by time column」、bid/askを別layer、公開axisをascendingと定義する。`Delta_Engine_Pro4web/src/heatmap/binner.py:1-5`
- `HeatmapGrid` は `price_bins`、`sample_times_ms`、`bid_quantities`、`ask_quantities`、`gap_columns` をtupleで保持する。`Delta_Engine_Pro4web/src/heatmap/binner.py:19-33`
- `sample_times_ms` と `gap_columns` の長さはtime count、bid/ask outer tupleの長さはprice count、各bid/ask inner rowの長さはtime countでなければならない。`Delta_Engine_Pro4web/src/heatmap/binner.py:35-47`
- `price_count` は `len(price_bins)`、`time_count` は `len(sample_times_ms)` である。`Delta_Engine_Pro4web/src/heatmap/binner.py:49-55`
- `bin_samples` は選択sampleごとにbid/askの1 column dictを作り、`bid_columns` / `ask_columns` へ時間順にappendする。`Delta_Engine_Pro4web/src/heatmap/binner.py:91-117`
- 最終matrixはprice axisをouter loop、時間順column群をinner loopとして構築される。したがってcellは `bid_quantities[price_index][time_index]` / `ask_quantities[price_index][time_index]` である。`Delta_Engine_Pro4web/src/heatmap/binner.py:119-127`
- 同じtime indexの時刻とgap flagは `sample_times_ms[time_index]` と `gap_columns[time_index]` にある。return時にselected time、price-by-time bid/ask rows、selected gap flagsが同じgridへ格納される。`Delta_Engine_Pro4web/src/heatmap/binner.py:129-136`
- 1時間列を構成する既存index関係は、1個の `time_index` に対する `sample_times_ms[time_index]`、`gap_columns[time_index]`、全 `price_index` の `bid_quantities[price_index][time_index]` と `ask_quantities[price_index][time_index]` である。matrix shapeの検証箇所は `Delta_Engine_Pro4web/src/heatmap/binner.py:35-47`、matrix生成箇所は `Delta_Engine_Pro4web/src/heatmap/binner.py:119-135`。
- `gap_columns[index]` は対応time columnの直前にdiscontinuityがあることを示し、rendererはmissing intervalをbridgeせず、そのcolumnをblankにできる。`Delta_Engine_Pro4web/src/heatmap/binner.py:20-25`
- source gapは隣接sample時刻deltaの最小値をnominal intervalとし、それより大きいdeltaで `True` になる。`Delta_Engine_Pro4web/src/heatmap/binner.py:167-177`
- gap位置でcontinuous segmentへ分け、各segmentを独立にtime thinningする。`Delta_Engine_Pro4web/src/heatmap/binner.py:180-206`
- `src/heatmap` と `tests/heatmap` の `frame_source|FrameSource|iter_frames|frame_column` 全文検索結果は0件である。既存のnamed frame_source APIは該当なし。

## J3. 既存Canvas描画APIの入力形状

### `ingestBook` が受けるpayload

- `validateBookPayload(raw)` はraw objectをpayloadとして受ける。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:49-52`
- 必須識別・時刻・状態項目は `book_stream_id`、`book_sequence`、`last_update_id`、`depth_levels`、`event_time`、`projection_time`、`sync_state`。stream IDはUUID、sequenceは1以上のsafe integer、update IDは非負safe integer、depthは1以上のsafe integer、時刻はnumberまたはparse可能な値として検証される。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:53-62`
- bid/askは `payload.bids` / `payload.asks` のarray。SYNCED時は各levelが正の `price` / `qty` を持ち、bidは価格降順、askは価格昇順である必要がある。best bid/askとspreadも検証される。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:63-85`
- 非SYNCED時はbid/ask、best bid/ask、spreadが空でなければfail-closed errorになる。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:65-69`
- validated payloadは、識別子、時刻、update/depth、sync state、`bids: [{price, qty}, ...]`、`asks: [{price, qty}, ...]`、best bid/ask、spread、ageを保持する。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:87-107`

### Canvas内部の1 book frame

- `compactFrame` は1 payloadを1 frameへ変換し、bid/ask価格を `Float64Array`、数量を `Float32Array` として保持する。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:110-128`
- `HeatmapBookStore` はframe arrayを持ち、既定で最大age 900,000ms、最大9,000 framesを保持する。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:150-167`
- store ingestはstream restart、duplicate sequence、delivery gapを処理し、非SYNCED payloadはgapを開始してframeを追加しない。SYNCED payloadだけをcompact frameへ変換して `frames.push(frame)` する。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:193-237`
- ageとframe上限によるpruneはframeの `eventTime` を基準に行う。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:242-251`
- `visibleFrames(start, end)` はwindow内frameに加え、start直前の最新frameがあれば先頭へ付ける。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:253-257`
- Canvas API `ingestBook(payload, nowMs)` はpayloadをbook storeへ渡し、tickを観測し、ingest timingを記録し、baseをdirtyにしてdrawを要求する。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:648-662`
- したがって既存Canvas APIの1回入力は「1時刻のfull book payload（bid level配列＋ask level配列＋識別・時刻・状態）」である。`HeatmapGrid` の「全price binに対するbid/ask quantity vector＋gap flag」を直接受けるAPIではない。payload構造は `Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:92-105`、compact frame構造は `Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:110-128`。

## J4. 動的スクロールの設計論点となる既存事実

### 1フレームと時間列

- Python gridではtime axisがascendingで、1つの `time_index` が1時間列を表す。`Delta_Engine_Pro4web/src/heatmap/binner.py:1-5,35-47`
- `bin_samples` のtime thinningは、両端を残し `i * (sample_count - 1) // (max_time_cols - 1)` で選択する。1列指定時は最新sampleを残す。`Delta_Engine_Pro4web/src/heatmap/binner.py:63-74,156-164`
- static transformはtime indexを左から右へ進め、1 cellの左右境界をviewport width÷time countで計算する。`Delta_Engine_Pro4web/src/heatmap/transform.py:153-186`
- static rendererは全price index×全time indexに対してraster boundsを構築する。`Delta_Engine_Pro4web/src/heatmap/render_static.py:83-97`
- Canvas storeでは1 accepted SYNCED book payloadが1 stored frameになる。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:227-237`
- Canvas rasterの出力時間列数はstored frame数ではなく、`buildTimeColumns(..., width)` の `floor(width)` 個である。各columnはvisible time durationを等分する。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:406-413`
- 各stored frameは次frame時刻までのintervalへ変換され、そのintervalが重なるpixel time columnsへduration-weightedで配賦される。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:475-510,563-573`

### 可視windowと保持幅

- Canvasの既定visible windowは300,000ms。`setViewMs` は10,000〜900,000msへclampする。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:606-607,673-674`
- store既定保持範囲は900,000ms／9,000 frames。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:150-156`
- live window終端はlatest eventまたはcurrent timeから `timeOffsetMs` を引いた値、開始は終端−`viewMs`。この範囲でvisible framesを取得する。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:760-770`

### 再描画範囲

- `ingestBook` はaccepted/invalidを問わずbaseをdirtyにし、full drawを要求する。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:648-662`
- `requestDraw` はpending中の重複requestをまとめ、1回の `requestAnimationFrame` callbackで `render()` を呼ぶ。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:698-705`
- `render()` はbase dirty時に `buildBase` を呼び、base canvas全体をmain canvasへdrawする。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:722-740`
- `buildBase` はvisible範囲全体のtime columns、intervals、duration-weighted rasterを再構築する。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:793-801`
- raster paintはraster width×rowsを走査し、raster canvas全体のImageDataを更新してplot全体へdrawする。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:810-844`
- 上記範囲には、右端の新規1列だけをshift/paintするpartial redraw処理は存在しない。既存経路はdirty時のvisible raster全体再構築である。根拠箇所は `Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:698-705,722-740,793-844`。

### gap

- Python gridの `gap_columns[index]` は対応time column直前のdiscontinuityを表す。`Delta_Engine_Pro4web/src/heatmap/binner.py:20-25`
- static rendererはRGB pixel bufferをzeroで初期化し、gap columnではpaintをskipするため、そのcolumnはbackground `(0,0,0)` のままになる。`Delta_Engine_Pro4web/src/heatmap/render_static.py:34,115-120`
- 非gap cellではask intensityをred channel、bid intensityをblue channelへ別々にpaintする。`Delta_Engine_Pro4web/src/heatmap/render_static.py:214-239`
- 現行Canvasはgap区間をduration aggregation対象から除外する。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:416-432,475-500`
- 現行Canvasはgap区間の上に半透明fillと斜線、幅が72pxを超える場合はreason textを描く。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:902-924`

## J5. per-frame計測点の候補となる既存境界

### frame source側の境界事実

- recording→sampleの既存yield境界は `sample_states` の `yield next_sample_time, snapshot`。その直後に次sample時刻をinterval分進める。`Delta_Engine_Pro4web/src/heatmap/reconstruct.py:237-243`
- gridから1列を参照する境界は、`sample_times_ms[time_index]`、`gap_columns[time_index]`、全price rowの `bid_quantities[price_index][time_index]` / `ask_quantities[price_index][time_index]` である。shape根拠は `Delta_Engine_Pro4web/src/heatmap/binner.py:35-47`、matrix生成根拠は `Delta_Engine_Pro4web/src/heatmap/binner.py:119-135`。
- named frame_source APIの全文検索hitは0件であり、frame_source自身の既存開始・終了計測行は該当なし。

### Canvas側の既存計測境界

- `ingestBook` はstore ingest直前にclockを取り、store ingestとtick観測の後にelapsedを `ingestTimes` へ保存する。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:648-660`
- draw要求は `requestAnimationFrame` callbackから `render()` を呼ぶ境界にある。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:698-705`
- `render()` の既存timingはresize後に開始し、dirty時の `buildBase`、base canvas転送、interaction描画までを測り、`renderTimes` へ最大240件保存する。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:722-740`
- transform/aggregationに近い既存区間は、visible columns・intervals・raster・heat scaleを作る `buildBase` 内にあり、`timing.aggregate` は `buildBase` 開始からscale生成後までを記録する。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:744-801`
- raster paint区間はImageData作成・pixel走査・`putImageData`・`drawImage` の後で `timing.raster` として記録される。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:810-844`
- overlay後に `timing.overlay` と `timing.total` が記録され、`lastBuildTiming` に保存される。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:845-879`
- `renderTimes` のp95はstatusへ表示され、metrics APIはingest p95、render p95、render max、last build timingを返す。`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:1009-1024,1192-1202`
- 現HEADには上記CPU timingが存在する。`requestAnimationFrame` callbackは `render()` 呼出直後に終了し、その後のsecond RAF、`PerformanceObserver`、presentation完了timestampは同ファイル全文検索に該当しない。callbackの実体は `Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:698-705`。
- frame_sourceの1列生成開始からCanvas ingest、transform、draw、browser presentationまでを同一sample IDで結ぶ既存記録は該当なし。既存記録はingest (`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:648-660`)、render CPU (`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:722-740`)、build内訳 (`Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js:744-879`) に分かれている。

### `RenderReport` の計測パターン

- static `RenderReport` はaggregation、transform、render、totalをDecimal millisecondsで別fieldに持つ。`Delta_Engine_Pro4web/src/heatmap/render_static.py:37-51`
- static rendererはtotal startを最初に取り、transformの開始・終了をgrid cell raster bounds全件の前後で計測する。`Delta_Engine_Pro4web/src/heatmap/render_static.py:80-97`
- render timingはcolor scale preparation前に開始し、pixel paint、PNG encode、directory作成、file write後に終了する。totalもfile write後に終了する。`Delta_Engine_Pro4web/src/heatmap/render_static.py:104-144`
- reportへ各測定値を格納してlogへ出す。`Delta_Engine_Pro4web/src/heatmap/render_static.py:145-169`

## 参照ファイル識別値（HEAD時点）

全6ファイルは `git diff --quiet HEAD -- <path>` がexit 0で、作業ツリーbytesがHEADと一致する。

| ファイル | SHA-256 | bytes | LF | CR |
|---|---:|---:|---:|---:|
| `Delta_Engine_Pro4web/src/orderflow/orderbook.py` | `291D46612AEBE09CD4B7A60E46F30CB9E8602FDD53817A3D01170F669D424C05` | 11,295 | 290 | 0 |
| `Delta_Engine_Pro4web/src/heatmap/reconstruct.py` | `84639422635CC01678CFB1E622FA561DF0B51D733A3262DA4A2B3A25C16BEB0C` | 20,394 | 573 | 0 |
| `Delta_Engine_Pro4web/src/heatmap/binner.py` | `15F41C721F41B680F7946714C4614C585E6D40F3783C0D8585030A4F8266F4C7` | 9,299 | 255 | 0 |
| `Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js` | `9F362BAF58FF79ED24A10133B98ED1FCBB61D14D150BC93CBB70968319E1A807` | 62,708 | 1,226 | 0 |
| `Delta_Engine_Pro4web/src/heatmap/render_static.py` | `AB9E040BCBAFD4E2D55A3B30AEEF728486E9A55366E35829BFB3F2234608A3AD` | 8,470 | 264 | 0 |
| `Delta_Engine_Pro4web/src/heatmap/transform.py` | `0A076B1274F907241D3A68D3267AA0E2065C91D5EC7BC30C9CB5EFC76B113C39` | 6,766 | 240 | 0 |

## git証跡（報告ファイル作成前）

### `git rev-parse HEAD`

```text
bf9512635d7a6f4d67a14d67d128fc528f6b6707
```

### `git status --porcelain -- Delta_Engine_Pro4web/`

```text
?? Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/
```

tracked coreの `M` 追加は0件。上記1行は既存の未追跡data directory。

### `git diff --cached --name-only`

```text
CACHED_PATH_COUNT=0
```

## 未実施範囲

- frame_source実装
- `src/heatmap` の変更
- 保護4ファイルの変更
- Canvas gate変更
- test追加・実行
- git add / commit
- Phase 2-3 Task 2以降
