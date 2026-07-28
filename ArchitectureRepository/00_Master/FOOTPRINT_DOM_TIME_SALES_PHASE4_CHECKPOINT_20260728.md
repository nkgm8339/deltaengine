# Footprint × LIVE DOM × Time & Sales Phase 4 checkpoint

最終更新: 2026-07-28 21:09 JST  
状態: **Phase 4完了**

## 承認

Phase 3完了報告後のユーザー「GO」を、V2.1 GO-9として受領した。

承認範囲:

- Canvas Footprint Chart
- 共通価格軸
- 初期10本、最大拡大3本、最大縮小20本
- cursor anchor wheel zoom
- drag history／lazy Footprint history
- LIVE LOCK
- 表示専用PRICE STEP（AUTO／1／2／5／10／20 ticks）
- BID × ASK、candle／wick、POC、Value Area、Imbalance／Stacked Imbalance
- DPR 1／1.25／1.5／2
- requestAnimationFrame集約、data model／render state分離
- 同一geometryによるhit testing
- HTML selected detail／tooltip／keyboard selection
- Phase 4専用・統合・全回帰・browser検証
- Phase 4完了文書

承認範囲外:

- Phase 5 LIVE DOM／Time & Sales frontend融合
- old Order Book panel presentation removal
- Time & Sales filter／virtualized rows／large marker／selection sync
- completed Flow Price Response／3段チャートの計算・構造・操作変更
- Footprint raw aggregation／Imbalance／Absorption detector変更
- Strategy／Hook／Condition／Order Trigger／execution変更
- production process／data操作
- git commit／push

## 開始状態

```text
branch: feature/footprint-dom-tape
HEAD: 92ee4eff823ba31e84f7fc0af197d39b877ec236
Phase 3 full regression: 644 passed, 1 skipped
```

Phase 1〜3差分および既存dirty／untracked source／artifactを保持し、
reset、checkout、削除、stage、commitしない。

## 必須確認

- `PROJECT_MEMORY.md` 1000行を全文再確認
- 2026-07-21の再誕、Flow Price Response、3段チャート固定原則を再確認
- V2 §2〜§10、§18、§22.1／22.5／22.6、§23 Phase 4を再確認
- V2.1 §6 Frontend描画方式、Canvas試験条件を再確認
- Phase 3完了報告と次のGO-9境界を再確認

## 現行境界監査

- 現行Footprint UIは1本の価格帯をDOM rowとして再構築する実装である。
- 現行`S.bars`はCANDLE履歴最大300本とlive CANDLE／BAR_UPDATEを保持する。
- `/api/history/candles?limit=300`はFootprint levelsを返さない。
- `/api/history/footprints`は確定Footprintをoldest-first、最大100本、exclusive
  `before` cursor付きで返す。
- BAR_UPDATEには形成中Footprint levelsとOHLC／VWAPがある。
- persisted Footprint historyにはOHLCがないため、同時刻のCANDLE historyとjoinし、
  不明なOHLCをFootprint levelsから推測しない。
- 現行Footprint panelは最終UI overrideで高さ344px、幅はmain中央列に制約される。
- 完成済み3段チャートは別panel／別rendererであり、Footprint置換から分離できる。
- `webapp/static/index.html`はGO-9開始時点でtracked差分なし。

## 確定実装方針

- 既存1-bar DOM row rendererだけをCanvas multi-bar rendererへ置換する。
- 3段チャートrenderer、Flow Price Response、8パターン、OI、既存選択操作は変更しない。
- Canvas cell、text、candle、POC／VA／Imbalanceを単一geometry modelから描く。
- raw levelsは変更せず、表示時だけDecimal tick bucketへ合算する。
- AUTO stepはviewportを概ね20〜40行に収める方向で1／2／5系列から選ぶ。
- 表示bucket後にPOC／VAを再計算し、`DISPLAY STEP`を常設表示する。
- initial hydrateは最新40 Footprint、過去drag端でexclusive cursorをlazy loadする。
- Live CANDLE／BAR_UPDATEと履歴は`bar_time`でdedupし、確定履歴を形成中値で上書きしない。
- Canvas backing storeだけDPR倍し、layout／hit testingはCSS pixelで統一する。
- market updateはdirty flagを立て、描画はrequestAnimationFrameへ集約する。
- selected cellのexact price bucket、BID、ASK、bar timeはHTMLへ常設出力する。
- render duration ringからp95を算出し、statusへ表示する。

## 完了済み

- 必須文書確認
- 現行Footprint DOM renderer／history API／live payload／layout境界監査
- Phase 4開始checkpoint作成
- standalone `footprint_canvas.js` data model／renderer
- display-only 1／2／5／10／20／AUTO tick bucket
- bucket後POC／VA／diagonal Imbalance／Stacked Imbalance
- common price axis／20〜40 virtual price rows
- BID × ASK heat cells／candle body／wick／current price／VWAP
- initial 10、3／10／20 controls、wheel anchor、drag、LIVE LOCK
- DPR backing store／requestAnimationFrame dirty render／render p95
- geometry-shared pointer hit test／keyboard selection／HTML exact detail
- latest40 history hydrate／exclusive cursor lazy load
- live CANDLE／BAR_UPDATE＋persisted history `bar_time` dedup
- Phase 4 contract test作成
- 3本詳細へDelta／Volume／CVD Δ／OI Δ／EVENTSを表示
- VAH／VAL境界、selected bar／cell共通geometry outline
- selected detail／tooltipへbucket範囲と非省略BID／ASK
- OffscreenCanvas static base＋reference／selection部分再描画
- 実Edge DPR／操作／performance／lazy history検証
- Phase 4 WebApp対象回帰67件
- V2／V2.1 GO-9 completion record
- Phase 4完了報告

## 未完了

- Phase 4内はなし
- Phase 5 LIVE DOM／Time & Sales frontend融合はGO-10未承認

## 変更file

- 本checkpoint
- `Delta_Engine_Pro4web/webapp/static/footprint_canvas.js`（新規）
- `Delta_Engine_Pro4web/webapp/static/index.html`
- `Delta_Engine_Pro4web/tests/webapp/test_footprint_chart_ui.py`（新規）
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_FUSION_IMPLEMENTATION_INSTRUCTION_V2_20260728.md`
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_FUSION_PREIMPLEMENTATION_AMENDMENT_V2_1_20260728.md`
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_PHASE4_COMPLETION_REPORT_20260728.md`（新規）

## 検証結果

- GO-9開始前の`webapp/static/index.html` tracked差分なし
- `node --check webapp/static/footprint_canvas.js`: pass
- inline JavaScript compile: pass
- Phase 4＋既存WebApp targeted: **67 passed in 3.05s**
- 実Edge: 3／10／20 bars、wheel 19、drag offset 3、LIVE LOCK復帰を確認
- 実Edge: DPR 1／1.25／1.5／2でCanvas backing store比一致
- 実Edge: pointer／keyboard hit testとHTML exact detailを確認
- 実Edge: LIVE足 `cvd_change=130`、`oi_change=5`、`events_count=1`を確認
- 実Edge: 最新40 hydrate→exclusive `before`→過去40 lazy load、80本一意を確認
- 実Edge: cold初期render p95 53.7〜72.3ms
- 実Edge: warm full Canvas render p95 **7.3ms**、max 12.4ms
- 実Edge: current-price partial render p95 **0.4ms**、frame再構築なし
- 実Edge: Canvas内cell DOM node 0、browser page error 0
- 診断用screenshotは視覚確認後、対象path検証のうえ削除
- 全回帰初回: **648 passed, 1 skipped, 1 failed**。失敗は製品実装ではなく、新規Nodeテストの
  UTF-8出力（bucket範囲のen dash）をWindows既定cp932でdecodeしたtest harness 1件に限定。
- Node subprocessへ`encoding="utf-8"`を明示し、Phase 4対象: **5 passed in 0.27s**
- 全回帰最終: **649 passed, 1 skipped in 34.41s**
- 完了文書前のV2.1照合でFootprint足時刻のUTC切り出しを検出。JST足label、
  JST＋UTC ISO＋exchange `bar_time` selected detailへ修正し、再検証中。
- timezone修正後`node --check`: pass、Phase 4対象: **5 passed in 0.63s**
- timezone修正後の全回帰最終: **649 passed, 1 skipped in 30.80s**
- production runtime／data変更なし
- Phase 4専用pytest temp directory残存なし
- `git diff --check`: pass
- blockerなし

## 次の再開位置

1. GO-10の明示承認があればPhase 5開始checkpointを作成
2. LIVE DOMとFootprintを同一価格geometryへ融合
3. Time & Sales virtualized list／filter／selection syncを実装
