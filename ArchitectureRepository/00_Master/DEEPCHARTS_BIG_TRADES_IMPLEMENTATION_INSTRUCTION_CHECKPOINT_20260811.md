# DeepCharts Big Trades実装指示書作成 CHECKPOINT

- 更新時刻: 2026-08-11 18:25:08 JST
- 承認範囲: 実装指示書の作成のみ
- branch: `feature/footprint-dom-tape`
- baseline HEAD: `778289d63f744adbe452186845d3709bbbdcfa0b`

## 完了済み

- `PROJECT_MEMORY.md` 1,725行を全文再確認した。
- `DEEPCHARTS_BIG_TRADES_SIZE_FILTER_RECONSTRUCTION_LOGIC_V1_20260811.md`の全ロジックを作成済み正本として確認した。
- Live／Replayの正規化約定経路、Tape batching、WebSocket、履歴API、保存writer、設定schema、現行Time & Sales filterの接続点をread-only監査した。
- `DEEPCHARTS_BIG_TRADES_IMPLEMENTATION_INSTRUCTION_V1_20260811.md`を新規作成した。
- 指示書へ、Manual／Automatic、同方向40ms cluster、同一millisecond trade ID整列、20-session較正、volatility補正、immutable artifact、設定version、原子的event＋fills保存、Live／Replay共通runtime、WebSocket／REST、中央3-mode UI、性能予算、137項目超のtest contract、GO-BT0～BT7、rollback、禁止shortcut、acceptanceを固定した。
- logic正本とのtraceabilityを指示書§65へ記録した。
- 完成済みFlow Price Response、3段チャート、既存Tape／Footprint／Heatmapを変更していない。

## 未完了

- なし。本checkpointの承認範囲である実装指示書作成は完了。
- source実装は承認範囲外であり未着手。

## 変更file

- `ArchitectureRepository/00_Master/DEEPCHARTS_BIG_TRADES_IMPLEMENTATION_INSTRUCTION_CHECKPOINT_20260811.md`（作業記録）
- `ArchitectureRepository/00_Master/DEEPCHARTS_BIG_TRADES_IMPLEMENTATION_INSTRUCTION_V1_20260811.md`（新規実装指示書）

## 検証結果

- repositoryのsource、config、runtime、UIへの変更: 0件。
- 現行worktreeには本作業開始前から多数のuser変更が存在する。指示書ではbroad stage、既存変更の破棄、無関係fileの上書きを禁止する。
- 指示書: 2,602行、73,157 bytes。
- 指示書SHA-256: `8C00F57D70566BA04FBCF47108C14A529FAD3C124FA8207211BEECEB4DCA4A73`
- numbered section: 0～70、欠落0、重複0。
- code fence: 210、開閉balanced。
- 必須contract 21項目: missing 0。
- 指示書が参照する既存source／spec 18 file: missing 0。
- Markdownの意図しない行末空白: 0。

## blocker

- なし。

## 次の再開位置

- 2026-08-11 19:57:36 JST、userの`よし`によりV1.1文書改訂を承認済み。
- V1.0を上書きせず、standalone V1.1へ次の4点を固定する。
  1. scheduled calibrationの自動activationと運用コスト。
  2. source-timeによるsession完了検出と処理順。
  3. Big Trades内部のcandle ID計算責任。
  4. activation ledgerによるReplay calibration再現。
- V1.0改訂前SHA-256は`8C00F57D70566BA04FBCF47108C14A529FAD3C124FA8207211BEECEB4DCA4A73`。
- source実装は承認範囲外。V1.1完成後も`GO-BT0`までsourceへ触れない。

## V1.1改訂中checkpoint — 2026-08-11 20:08:09 JST

- 承認範囲: standalone V1.1実装指示書へreview 4点を反映する文書作業だけ。
- 完了済み:
  - V1.0を変更せずV1.1作業copyを作成した。
  - scheduled calibrationをsource-confirmed session boundaryで自動activateし、正常時の週次／月次manual操作を0回とするpolicyを明文化した。
  - session完了triggerを次session最初のaccepted source tradeへ固定し、CVD closed candle、buffer、cluster、stats、calibration、activation、current tradeの処理順を固定した。
  - candle ID ownerをBig TradesのUTC epoch floor pure functionへ固定し、CVD 1分足とのparity failureをfail-closed化した。
  - Replay calibration選択をappend-only activation historyのeffective source time／trade IDへ固定し、`created_at_utc`推定と欠損fallbackを禁止した。
  - storage schema、API、status、fail-closed matrix、test vector、gate、traceability、invariant、acceptanceへ同じ4決定を反映した。
- 未完了:
  - V1.1全文の構造、cross-reference、矛盾、code fence、SHA-256監査。
  - V1.0 hash不変確認と本checkpointの最終更新。
- 変更file:
  - `ArchitectureRepository/00_Master/DEEPCHARTS_BIG_TRADES_IMPLEMENTATION_INSTRUCTION_V1_1_20260811.md`
  - 本checkpoint。
- 検証結果: まだ最終監査前。source、config、runtime、UI変更は0件。
- blocker: なし。
- 次の再開位置: V1.1全文監査から再開し、文書だけを完成させて停止する。

## V1.1最終checkpoint — 2026-08-11 20:16:34 JST

- 承認範囲: standalone V1.1実装指示書へのreview 4点反映まで。
- 完了済み:
  - `DEEPCHARTS_BIG_TRADES_IMPLEMENTATION_INSTRUCTION_V1_1_20260811.md`を完成した。
  - scheduled WEEKLY／MONTHLY calibrationはvalidation成功時にsource-confirmed新session最初のclusterから自動activateし、定常manual操作0回とした。失敗時は旧version維持とした。
  - session完了triggerを次session最初のaccepted source tradeへ固定し、wall clock／shutdown完了を禁止した。
  - candle ID ownerをBig Trades内部UTC floor関数へ固定し、CVD boundary parityをfail-closed contractにした。
  - Replayはcommitted activation artifactのeffective source time／trade IDだけでversionを選び、`created_at_utc`推定、欠損fallback、productionとfixed researchの混在を禁止した。
  - activation artifactのatomic renameを唯一のcommit pointとし、active pointerは再構築可能cacheへ限定した。
  - 同一境界request優先順位、初回activation、schedule run dedup／crash recoveryまで固定した。
- 未完了:
  - なし。本承認範囲のV1.1文書改訂は完了。
  - source実装、config変更、test実行、runtime／UI／deploymentは未承認・未着手。
- 変更file:
  - `ArchitectureRepository/00_Master/DEEPCHARTS_BIG_TRADES_IMPLEMENTATION_INSTRUCTION_V1_1_20260811.md`
  - 本checkpoint。
- 検証結果:
  - V1.0: 2,602行、73,157 bytes、SHA-256 `8C00F57D70566BA04FBCF47108C14A529FAD3C124FA8207211BEECEB4DCA4A73`。改訂前から不変。
  - V1.1: 3,135行、110,889 bytes、SHA-256 `8548AF1905B7A4AC47FBB2914496C39C539F2D046FD7131A23BAED7F3FCE7528`。
  - numbered section 0～70: 71章、欠落0、重複0。
  - numbered subsection重複: 0。
  - code fence: 262、開閉balanced。
  - test contract §45～§50: 191項目。
  - 意図しない行末空白: 0。
  - stale contract `effective_after`、`auto_activate_calibration`、V1 manual-only activation、旧pipeline接続、calibration側active path: 各0件。
  - repository source、config、runtime、UIへの本作業による変更: 0件。
- blocker: なし。
- 次の再開位置: userが明示的に`GO-BT0`または対象gateを承認するまで停止する。
