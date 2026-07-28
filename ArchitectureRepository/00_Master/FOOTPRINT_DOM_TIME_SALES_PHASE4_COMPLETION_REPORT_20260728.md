# Footprint × LIVE DOM × Time & Sales Phase 4 完了報告

完了時刻: 2026-07-28 21:07 JST  
対象branch: `feature/footprint-dom-tape`  
開始HEAD: `92ee4eff823ba31e84f7fc0af197d39b877ec236`  
承認: V2.1 GO-9

## 1. 結論

Phase 4「Canvas Footprint Chart」を実装し、実Edge検証と全回帰試験まで完了した。

フロントページの旧1本Footprint表示を、共通価格軸を持つ複数足Canvasへ置換した。
通常は10本、拡大時は3本の詳細、縮小時は20本の全体像を表示できる。
表示専用price bucket、POC、Value Area、Imbalance、candle、Session VWAP、
current priceを同じgeometryで描画する。

Phase 5のLIVE DOM／Time & Sales融合は未実施である。
完成済みFlow Price Responseと3段チャートの計算、構造、操作は変更していない。

## 2. 実装済み契約

### 2.1 複数足viewport

- 初期表示: 10 bars
- 固定control: 3／10／20 bars
- wheel zoom: 3〜20 bars、pointer位置をanchorに維持
- horizontal drag: 過去／現在方向へbar単位移動
- LIVE LOCK: forming barへ復帰
- 共通価格軸: viewport内の全Footprint barで一つ
- virtual price rows: 20〜40行、範囲外の上／下level数を表示

### 2.2 Display-only price aggregation

- `PRICE STEP`: AUTO／1／2／5／10／20 ticks
- AUTO: 1／2／5系列からviewportを概ね20〜40行へ収めるstepを選択
- raw `footprint_levels`は変更しない
- Decimal由来tick indexでdisplay bucketへBID／ASKを合算
- POC／VAH／VAL／VAをdisplay bucket後に再計算
- diagonal Imbalance／Stacked Imbalanceもdisplay step隣接関係で再計算
- statusへ実際のdisplay stepを常設表示

### 2.3 表示と色の意味

- aggressive sell／BID: red heat `#FF4058`
- aggressive buy／ASK: green heat `#19C979`
- heat濃度: 各bar内side volumeに比例
- POC: yellow outline `#F4C542`
- Value Area: translucent yellow、VAH／VALはyellow boundary
- sell／buy Imbalance: red／green outline
- Stacked Imbalance: 太いyellow outline
- candle: 上昇green、下降red、wickはwhite
- current price: white line
- Session VWAP: cyan dashed line
- forming bar: cyan frame

色は観測事実を示すだけであり、売買推奨、confidence、予測確率ではない。

### 2.4 足別facts

- 10本以下: Delta、Volume
- 3本詳細: Delta、Volume、CVD Δ、OI Δ、EVENTS
- unknown valueは`—`とし、Footprint levelsからOHLC／OI等を推測しない
- persisted historyとforming barは`bar_time`でdedup
- confirmed historyをforming valueで上書きしない

### 2.5 History／live

- 起動時に`GET /api/history/footprints?limit=40`をhydrate
- 過去端へdragしたときexclusive `before` cursorで次の40本をlazy load
- responseとWebSocket `CANDLE`／`BAR_UPDATE`を`bar_time`で統合
- historyはoldest-firstへ正規化
- duplicate cursor／empty responseで追加要求を停止

### 2.6 Canvas performance

- Footprint cellをDOM node化しない
- CSS pixelとCanvas backing storeを分離
- DPR 1／1.25／1.5／2へ追従
- `requestAnimationFrame`へmarket updateを集約
- data modelとrender stateを分離
- static historyをOffscreenCanvas baseへ保持
- current price／selectionはreference／selection dirty layerだけを再描画
- viewport／size／price range変更時だけfull frameを再構築
- render duration ringのp95をstatusへ表示

### 2.7 Selection／timezone／accessibility

- 描画と同じgeometryでbar／price bucketをhit test
- pointer click、arrow key、Enter、Escapeに対応
- selected price bucket範囲、exact BID、exact ASK、POC／VA／ImbalanceをHTML表示
- Canvasへ`tabindex`、`role=img`、説明用`aria-label`
- selected detailへ`role=status`、`aria-live=polite`
- Footprint bar timeはJST `HH:mm`
- selected detailはJST millisecond、UTC ISO、exchange `bar_time`を併記
- browserの暗黙local timezoneへ依存しない固定JST変換

## 3. 変更file

- `Delta_Engine_Pro4web/webapp/static/footprint_canvas.js`（新規）
- `Delta_Engine_Pro4web/webapp/static/index.html`
- `Delta_Engine_Pro4web/tests/webapp/test_footprint_chart_ui.py`（新規）
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_FUSION_IMPLEMENTATION_INSTRUCTION_V2_20260728.md`
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_FUSION_PREIMPLEMENTATION_AMENDMENT_V2_1_20260728.md`
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_PHASE4_CHECKPOINT_20260728.md`
- 本報告

既存dirty／untrackedのsource、実データ、監査・設計成果物は
reset、checkout、削除、stageしていない。

## 4. 検証

### 4.1 Automated

- `node --check webapp/static/footprint_canvas.js`: PASS
- inline JavaScript compile: PASS
- Phase 4 contract test: **5 passed**
- Phase 4＋既存WebApp targeted: **67 passed in 3.05s**
- final full pytest: **649 passed, 1 skipped in 30.80s**
- display bucket／AUTO step／VA／bucket label: PASS
- display-step diagonal Imbalance: PASS
- JST fixed-offset formatter: PASS
- completed 3-stage chart geometry token: unchanged／PASS

最初の全回帰では、新規Node testのUTF-8出力をWindows既定cp932でdecodeした
test harness 1件だけが失敗した。`encoding="utf-8"`を明示して対象5件、
全649件を再実行し、上記の最終結果を得た。製品runtimeの失敗ではない。

### 4.2 実Edge

- 3／10／20 bars control: PASS
- wheel zoom 19 bars、drag offset 3、LIVE LOCK復帰: PASS
- DPR 1／1.25／1.5／2のbacking store比: PASS
- pointer／keyboard selectionとHTML exact detail: PASS
- forming bar `cvd_change=130`／`oi_change=5`／`events_count=1`: PASS
- latest40 hydrate→exclusive cursor→past40 lazy load: 80 bars一意／PASS
- Canvas price cell DOM node: 0
- browser page error: 0
- warm full render p95: **7.3ms**、max 12.4ms
- current-price partial render p95: **0.4ms**、frame再構築なし
- cold初期render p95: 53.7〜72.3ms

cold初期値には初回Canvas／font／layout準備を含む。定常時のwarm full p95は
16ms未満であり、部分更新も別計測で確認した。

診断用screenshotは視覚確認後、workspace内の対象pathを検証して削除した。
各pytest専用一時ディレクトリも対象path確認後に削除した。

## 5. 運用上の注意

- Phase 4完了時点でFootprint複数足Canvasはフロントページへ表示される。
- backend `BOOK_UPDATE`／`TAPE_UPDATE`は実装済みだが、LIVE DOM／Time & Salesの
  frontend表示はPhase 5まで追加しない。
- old Order Book panelのpresentationはPhase 5まで維持する。
- OIはA案のまま新規paneを追加せず、3本詳細のOI Δで観測する。
- Absorption detector、Imbalance detector、Flow Price Response、3段チャートの
  計算契約は変更していない。
- production processは起動しておらず、production dataは変更していない。
- commit／pushは行っていない。

## 6. 次の承認境界

次はGO-10、Phase 5「LIVE DOM／Time & Sales frontend融合」である。

GO-10まで未着手:

- Footprintと同一価格geometryのfixed LIVE DOM描画
- fixed Time & Sales virtualized HTML list
- display filter／large trade黄色outline
- stream restart／gap／overflow UI
- Time & Sales rowとFootprint bar／price bucketのselection sync
- old Order Book panel presentation removal

Phase 6のrestart／reconnect／replay／live accountingを含む総合検証は、
Phase 5とは別の明示GOを必要とする。
