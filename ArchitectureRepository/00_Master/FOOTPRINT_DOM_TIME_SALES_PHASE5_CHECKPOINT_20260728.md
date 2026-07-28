# Footprint × LIVE DOM × Time & Sales Phase 5 checkpoint

最終更新: 2026-07-28 21:54 JST  
状態: **完了**

## 承認

Phase 4完了報告後のユーザー「GO」を、V2.1 GO-10として受領した。

承認範囲:

- Footprint Canvasと同一価格軸／同一geometryの固定LIVE DOM
- WebSocket `BOOK_UPDATE` frontend接続
- passive Bid／Ask depth、Best Bid／Ask、Spread、visible wall candidate
- stale／unsynced fail-closed表示
- 右端固定Time & Sales
- WebSocket `TAPE_UPDATE` frontend接続
- recent 500 trades browser ring、20〜40 row virtualized HTML list
- ALL／BUY／SELL、minimum quantity、minimum notional、large-only filter
- large trade黄色outlineとthreshold常設
- stream scoped sequence、gap／overflow／restart／reconnect表示
- `GET /api/history/time-sales` hydrateと`(symbol, trade_id)` dedup
- Tape／Footprint／LIVE DOM selection sync
- 旧Order Book panel presentation removal（source／detectorは維持）
- Phase 5対象・browser・全回帰試験
- Phase 5完了文書

承認範囲外:

- Phase 6 restart／reconnect／replay／live no-loss総合運転
- BOOK_UPDATE／TAPE_UPDATE backend契約変更
- Footprint raw aggregation／detector／storage変更
- completed Flow Price Response／3段チャート／8パターン／OIの計算・構造・操作変更
- Strategy／Hook／Condition／Pattern／Order Trigger／execution変更
- production process／data操作
- git commit／push

## 着手前に確認した基準

- `PROJECT_MEMORY.md`全1000行を再読した。
- 2026-07-21再誕の目的と、完成済みFlow Price Response／3段チャートの保護を確認した。
- V2 §2〜§9、§11〜§20、§22.2〜§22.6、§23 Phase 5、§24を確認した。
- V2.1 §6〜§8、§12のCanvas／Tape sequence／timezone契約を確認した。
- Phase 4 checkpoint／completion reportの完了境界を確認した。

## 開始時点

- branch: `feature/footprint-dom-tape`
- HEAD: `92ee4eff823ba31e84f7fc0af197d39b877ec236`
- Phase 1〜4の変更は未コミットでworktreeに存在する。
- 既存dirty／untracked変更をreset、checkout、stage、削除しない。
- Phase 4最終全回帰: **649 passed, 1 skipped**

## Frontend／payload監査結果

- frontend WebSocket switchは`BOOK_UPDATE`／`TAPE_UPDATE`を未処理で、現在はunknown typeとして無視する。
- Phase 2 `BOOK_UPDATE`は`sync_state`、top50 bid／ask、Best Bid／Ask、Spread、ageを配信済み。
- fail-closed stateではbackendがbid／askを空配列にして古い数量を送らない。
- Phase 3 `TAPE_UPDATE`はstream UUID、連続sequence、accepted／dropped、exact trade値を配信済み。
- Tape batchはreconnect cacheへ保存されないため、frontend側history hydrateとgap表示が必要。
- `/api/history/time-sales`は最大500件、oldest-first、exact notional、複合cursorを実装済み。
- Phase 4 CanvasはFootprint barsだけを描き、LIVE DOM用geometry／hit areaをまだ持たない。
- Phase 4 CanvasはrAF dirty layerとOffscreenCanvas baseを持つため、DOM overlay layerを追加可能。
- 現行layoutはruntimeでFlow／Absorption／Imbalance／Alertsを左列へ移し、旧Order Bookを右列へ移す。
- 右固定列をTime & Salesへ置換し、旧Order Book sourceを残してpresentationだけ外せる。
- Flow Price Response／3段チャートは別renderer／固定geometryであり、Phase 5から分離できる。

## 確定実装方針

- `footprint_canvas.js`へDOM固定幅、passive depth bucket、Best／wall／spread、DOM hit testingを追加する。
- Canvas price rowsとDOM rowsは同一`frame.rows`／`buildGeometry()`を使用する。
- BOOK_UPDATEは`liveDom` dirty layerとし、通常更新でstatic Footprint baseを再構築しない。
- DOM fail-closed時は数量を描かず、HTML固定statusをwarningへする。
- Time & Salesは専用JS controllerへ分離し、500件data ringと最大32個の再利用DOM rowを持つ。
- filterはbrowser表示だけへ適用し、受信／dedup／ring／gap accountingへ影響させない。
- new streamはexpected sequenceをresetしてfalse gapを防ぎ、restart境界とhistory hydrateを行う。
- same streamのsequence不一致、`dropped_count`、batch不整合はpersistent `TAPE GAP`へする。
- Tape clickでexact bar／display bucketを選択し、未読込barはFootprint historyを追加取得する。
- Footprint cell clickは同価格DOM rowと保持中Tape rowsだけをhighlightする。
- LIVE DOM clickは同display bucketをFootprintへhighlightし、Tape filterは変更しない。
- 時刻はFootprintと同じ固定JST formatterを共有し、detailでUTC ISO／exchange timeも確認可能にする。
- 3段チャートrenderer／geometry tokenへ変更を加えない。

## 完了済み

- PROJECT_MEMORY全1000行確認
- V2／V2.1 Phase 5契約確認
- branch／HEAD／dirty worktree確認
- Canvas／layout／WebSocket switch監査
- BOOK_UPDATE／TAPE_UPDATE／history API payload監査
- Phase 5開始checkpoint作成
- Canvas共通価格geometryへ固定LIVE DOM列を追加
- passive depthのdisplay bucket、Best Bid／Ask、Spread、wall candidate
- fail-closed quantity非表示と固定HTML DOM status
- `liveDom` dirty layer（static Footprint base再利用）
- Footprint／DOM／Tape共通selectionとkeyboard hit testing
- 500件TapeStore、stream sequence／gap／drop／restart state
- 32行再利用DOM poolのTime & Sales controller
- ALL／BUY／SELL、min quantity／notional、large-only filter
- large trade黄色outline、JST／UTC／exchange exact detail
- `BOOK_UPDATE`／`TAPE_UPDATE` frontend wiring
- Time & Sales history hydrate／dedup／reconnect hydrate
- Tape click→Footprint lazy history selection
- 旧Order Book presentation rollback flag／非表示、右列Tape固定
- Phase 5 contract test作成
- Phase 4／5対象12件合格
- 実Edge最終検証合格
- 全回帰656 passed、1 skipped
- V2／V2.1 GO-10 completion record更新
- Phase 5完了報告作成
- 診断画像／script／pytest専用一時領域の削除

## 未完了

- Phase 5内はなし
- Phase 6 restart／reconnect／replay／live no-loss総合運転はGO-11未承認のため未着手

## 変更file

- 本checkpoint
- `Delta_Engine_Pro4web/webapp/static/footprint_canvas.js`
- `Delta_Engine_Pro4web/webapp/static/time_sales.js`（新規）
- `Delta_Engine_Pro4web/webapp/static/index.html`
- `Delta_Engine_Pro4web/tests/webapp/test_dom_tape_fusion_ui.py`（新規）
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_FUSION_IMPLEMENTATION_INSTRUCTION_V2_20260728.md`
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_FUSION_PREIMPLEMENTATION_AMENDMENT_V2_1_20260728.md`
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_PHASE5_COMPLETION_REPORT_20260728.md`（新規）

## 検証結果

- source変更前監査のみ
- `node --check footprint_canvas.js`: pass
- `node --check time_sales.js`: pass
- inline JavaScript compile: pass
- Phase 4／5＋BOOK／TAPE／WebApp対象初回: **75 passed, 1 failed**。失敗は製品実装でなく、
  `onTick` test抽出終端が新規handler位置より後ろだったtest harness範囲1件に限定。
- test harness修正後のPhase 4／5＋BOOK／TAPE／WebApp対象: **76 passed in 5.91s**
- 実Edge初回操作はscreenshot生成まで完走。最終JSON出力だけが中点文字をWindows既定cp932へ
  encodeできず終了コード1。blockerは診断結果stdoutのUTF-8固定だけに限定し、browser runtimeとは分離。
- UTF-8出力で実Edge結果取得: LIVE DOM／Tape／filter／selection／gap／new stream／500 ring／
  fail-closed／disconnectはpass、page error 0、横overflowなし、Canvas p95 2.0ms、Tape p95 2.2ms。
- 実Tape viewportは19行で契約下限20に1行不足。row heightを15pxへ修正し再検証中。
- 一batchの複数gap理由をsequence gap件数へ重複計上しないようbatch単位countへ修正。
- Edge再検証でcontroller側minimum 18px clampが15px指定を戻していたことを確認。
  minimum clampも15pxへ修正。gap countは1 batchとしてpass、page error 0。
- 最終row-height修正後のPhase 4／5対象: **12 passed in 0.50s**。
- 最終実Edge再検証: row height 15px、viewport **23 rows**、固定pool 32、visible node 32、
  same-stream gap count 1、drop count 1、`TAPE GAP`表示、横overflowなし、page error 0。
- final full pytest: **656 passed, 1 skipped in 32.80s**。
- 診断用Edge script／PNG／JPGは結果取得後に削除した。
- final `node --check`（Footprint／Tape）: pass
- `git diff --check`: pass（改行形式のwarningのみ、whitespace errorなし）
- pytest専用最終basetemp削除済み
- production runtime／data変更なし
- blockerなし

## 次の再開位置

1. GO-11が明示された場合だけPhase 6開始checkpointを作成する
2. restart／reconnect／replay／live no-loss総合運転を実施する
