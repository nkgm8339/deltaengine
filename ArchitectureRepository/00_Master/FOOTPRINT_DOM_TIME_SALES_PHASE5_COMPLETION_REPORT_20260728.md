# Footprint × LIVE DOM × Time & Sales Phase 5 完了報告

完了時刻: 2026-07-28 21:52 JST  
対象branch: `feature/footprint-dom-tape`  
開始HEAD: `92ee4eff823ba31e84f7fc0af197d39b877ec236`  
承認: V2.1 GO-10

## 1. 結論

Phase 5「LIVE DOM／Time & Sales frontend融合」を実装し、実Edge検証と全回帰試験まで完了した。

複数足Footprint Canvasの共通価格geometryへLIVE DOMを固定列として統合し、右端の旧Order Book表示を
Time & Salesへ置換した。約定履歴500件、32行の再利用DOM pool、表示filter、large trade強調、
sequence gap／drop／restart／reconnect表示、3領域の選択同期を実装した。

完成済みFlow Price Responseと3段チャートの計算、構造、操作は変更していない。
Phase 6のrestart／reconnect／replay／live no-loss総合運転は未実施である。

## 2. 実装済み契約

### 2.1 LIVE DOM

- FootprintとDOMが同じ`frame.rows`／price step／viewportを使用
- DOM列はCanvas内の固定幅で、Footprint bar本数を変えても価格行が一致
- passive Bidはgreen、passive Askはred
- Best Bid／Best Askはcyan、visible wall candidateはyellow
- server算出Spread、snapshot age、update idを固定statusへ表示
- `SYNCED`以外は数量を描かないfail-closed
- disconnect時は`NO_CONNECTION`へ遷移し、古い数量を消去
- `BOOK_UPDATE`は`liveDom` dirty layerだけを更新し、static Footprint baseを再利用

### 2.2 Time & Sales

- 右端固定panel、新しい約定を上側へ表示
- browser内recent 500 trades ring
- 32個のDOM rowを作成時に一度だけ生成し、scrollで再利用
- 実Edge viewportは15px rowで23行表示
- history／liveを`(symbol, trade_id)`でdedup
- 一覧はJST、detailはJST millisecond／UTC ISO／exchange `event_time`
- price／quantity／notionalのexact値をdetailへ保持
- `TICK`から約定を再構成せず、`TAPE_UPDATE`だけを受理

### 2.3 Filter／large marker

- ALL／BUY／SELL
- minimum quantity
- minimum notional
- large-only
- large thresholdを常設表示
- large tradeはyellow outline
- filterは表示だけへ適用し、受信、dedup、ring、gap accountingを変更しない

### 2.4 Sequence／reconnect

- `stream_id`単位でexpected sequenceを保持
- 同一streamのsequence不一致、`dropped_count`、batch不整合を`TAPE GAP`へ表示
- 一batch内に複数理由があってもgap countは一件
- new streamではexpected sequenceと古いgap表示をresetし、restart境界を表示
- reconnect中は`RECONNECTING`、接続後はhistoryを再hydrate
- historyとliveの重複はdedupし、filter中も欠落計算を継続

### 2.5 Selection sync

- Tape row選択から該当Footprint bar／display price bucketを選択
- 未読込barはexclusive cursorでFootprint historyを追加取得
- Footprint cell選択から同価格DOM rowと保持中Tape tradeをhighlight
- DOM row選択から同display bucketのFootprintをhighlight
- DOM選択でTape filterは変更しない
- pointerとkeyboardの両方で操作可能

### 2.6 旧Order Bookとrollback

- 旧Order Book panelはPhase 5 presentationから非表示
- 旧DOM source／detector／renderer codeは削除していない
- `PHASE5_FUSION_ENABLED`／body classでpresentation rollback境界を維持
- backend `BOOK_UPDATE`／`TAPE_UPDATE`契約は変更していない

## 3. 変更file

- `Delta_Engine_Pro4web/webapp/static/footprint_canvas.js`
- `Delta_Engine_Pro4web/webapp/static/time_sales.js`（新規）
- `Delta_Engine_Pro4web/webapp/static/index.html`
- `Delta_Engine_Pro4web/tests/webapp/test_dom_tape_fusion_ui.py`（新規）
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_FUSION_IMPLEMENTATION_INSTRUCTION_V2_20260728.md`
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_FUSION_PREIMPLEMENTATION_AMENDMENT_V2_1_20260728.md`
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_PHASE5_CHECKPOINT_20260728.md`
- 本報告

既存dirty／untrackedのsource、実データ、監査・設計成果物は
reset、checkout、削除、stageしていない。

## 4. 検証

### 4.1 Automated

- `node --check webapp/static/footprint_canvas.js`: PASS
- `node --check webapp/static/time_sales.js`: PASS
- inline JavaScript compile: PASS
- Phase 4／5 contract: **12 passed in 0.50s**
- Phase 4／5＋BOOK／TAPE／WebApp対象: **76 passed in 5.91s**
- final full pytest: **656 passed, 1 skipped in 32.80s**
- 500 ring／32 row pool／filter／dedup／JST formatter: PASS
- same-stream gap／drop、new-stream restart reset: PASS
- DOM bucket／Best／wall／fail-closed: PASS
- completed 3-stage chart geometry token: unchanged／PASS

初回対象試験の1件失敗は、製品実装ではなく既存function抽出test harnessの範囲が新規handlerまで
含んだことが原因だった。抽出終端を明示して対象76件を再実行し、合格した。

### 4.2 実Edge

- viewport: 1536 × 1200、DPR 1.25
- Canvas CSS: 696 × 476、backing store: 870 × 595
- fixed DOM width: 132px、common price rows: 21
- Tape row height: 15px、viewport: **23 rows**
- Tape pool: 32、visible nodes: 32、ring: 500件で打ち切り
- Tape→Footprint、Footprint→Tape、DOM→Footprint selection: PASS
- filter／large-only／large marker: PASS
- same-stream gap／drop: count 1／1、`TAPE GAP`: PASS
- new stream: gap reset、restart count、expected sequence reset: PASS
- stale／disconnect: DOM quantity 0、`NO_CONNECTION`／`RECONNECTING`: PASS
- horizontal overflow: なし
- browser page error: 0
- warm Canvas render p95: **2.0ms**
- Tape render p95: **2.2ms**

最初の実Edge診断は結果JSONの中点文字をWindows既定cp932へ出力する段階だけで失敗した。
UTF-8出力へ直して同じbrowser操作を再実行し、runtimeが正常であることを確認した。
また、初期19行表示を契約下限20へ合わせるためrow heightを15pxへ修正し、23行を再確認した。

診断用Edge script／PNG／JPGは結果取得後、workspace内の正確な対象pathを確認して削除した。

## 5. 保護境界

- Flow Price Responseの計算、状態、表示契約を変更していない。
- 完成済み3段チャートのrenderer／geometry token／操作を変更していない。
- OIはA案のまま新規paneを追加していない。
- Absorption／Imbalance detectorの計算を変更していない。
- Strategy／Hook／Condition／Pattern／Order Trigger／executionを変更していない。
- production processは起動しておらず、production dataは変更していない。
- commit／pushは行っていない。

## 6. 次の承認境界

次はGO-11、Phase 6「統合検証」である。

GO-11まで未着手:

- process restart時のnew stream切替総合運転
- WebSocket reconnectとhistory hydrate／dedup総合運転
- replay market-timeとTape／Footprint同期
- live accepted／sent／pending／in-flight／dropped no-loss accounting
- 長時間BOOK sampling／Tape batch／browser描画の統合観測
- Phase 6最終rollback／運用判定

Phase 6は別の明示GOを必要とする。
