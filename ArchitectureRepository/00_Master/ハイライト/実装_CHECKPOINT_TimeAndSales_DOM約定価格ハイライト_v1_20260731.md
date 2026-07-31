# Time & Sales → LIVE DOM 約定価格ハイライト 実装checkpoint

最終更新: 2026-07-31 10:16:47 JST  
状態: **HL-0〜HL-3完了／source実装・実ライブ検証PASS／コミット済み**

## 現在の承認範囲

- ユーザーの2026-07-31「おねがいします」を、直前に提示した
  `指示書_TimeAndSales_DOM約定価格ハイライト_v1_20260731.md`に基づく
  HL-0〜HL-3のsource実装、試験、実ブラウザ検証、完了文書作成の承認として受領した。
- HL-4のcontainer restart、image build、production deploymentは別承認とする。
- commitはユーザー確認済み。pushは未実施。
- backend、storage、WebSocket schema、Hook、Strategy、executionは変更しない。

## Baseline

- branch: `feature/footprint-dom-tape`
- HEAD: `ad4b47d59b4805048c1c6f5f2929480ef396ddc5`
- `PROJECT_MEMORY.md`: 全1192行確認済み
- 実装指示書: 全804行、Markdown fence 24件balanced、必須契約語欠落0
- target folderは本件で新規作成した
  `ArchitectureRepository/00_Master/ハイライト`

## 既存未コミット変更

本件開始前から次がdirtyである。

- `Delta_Engine_Pro4web/webapp/static/index.html`
  - 105行追加／10行削除
  - Order Book HeatmapのUI、配線、presentation gateを含む
  - `TAPE_UPDATE`受理約定をHeatmapへ渡す`onAcceptedTrades`配線を含む
- `Delta_Engine_Pro4web/webapp/static/time_sales.js`
  - 6行追加
  - `onAcceptedTrades` callbackとlive accepted trade抽出を含む

上記は既存ユーザー作業として保全する。
本件は`time_sales.js`を原則変更せず、既存callbackを正式な分岐点として利用する。

## 完了済み

- 必読`PROJECT_MEMORY.md`を全文確認した。
- Footprint／LIVE DOM／Time & SalesのV2、V2.1、Phase 5／6、可読性checkpoint、
  WebSocket payload正本を確認した。
- 現行`time_sales.js`、`footprint_canvas.js`、`index.html`、関連testを確認した。
- BUYはpassive ASK、SELLはpassive BIDを対象とする意味を確認した。
- DOMとFootprintが同じCanvas `frame.rows`／tick／multiplierを使用することを確認した。
- history hydrateが`onAcceptedTrades`を通らないことを確認した。
- worktreeの関連dirty差分を確認し、既存Heatmap変更との統合点を特定した。
- HL-1:
  - `DomTradePulseStore`をCanvas module内のpure classとして追加した。
  - BUY→ASK、SELL→BIDのside mappingを追加した。
  - exact priceをnative tick indexへ正規化し、現display multiplierへ投影する。
  - 400ms、70% hold＋30% fade、最大256 active entryとした。
  - 同一exact price／same sideはcoalesceし、最新tradeから400msへ延長する。
  - `domTradePulse` overlay dirty layerとyellow fill／borderを追加した。
  - 数量levelの現存有無から独立して、current `frame.rows`へpulseを描画する。
  - pulse schedulerをCanvasあたり最大一個のRAFへ限定した。
  - fail-closed、book stream、Tape stream、symbol、feature、Canvas destroyのclear APIを追加した。
- HL-2:
  - `index.html`へ`onAcceptedTapeTrades()` named coordinatorを追加した。
  - 既存`TimeSalesView.onAcceptedTrades`を正式な分岐点として使用した。
  - DOM PulseとHeatmapを独立consumerとして個別try境界へ分けた。
  - Heatmapの既存`TAPE_UI.store.streamId` source契約を維持した。
  - `TICK`、history hydrate、Flow経路へpulseを追加していない。
  - `time_sales.js`は本件では変更していない。
  - feature flagは`DOM_TRADE_PULSE_ENABLED = true`、durationは400msとした。
- 新規test `test_dom_trade_pulse_ui.py`を追加した。
  - pure state／side／bucket／expiry／coalesce／capacity
  - ASK／BID半セルCanvas座標
  - level非存在時のoverlay
  - named accepted-trade routing
  - stream／book／fail-closed／feature lifecycle
- HL-3:
  - WebApp全体回帰とrepository全体回帰を実行した。
  - 6,000 trade burst、Pulse Store capacity、overlay p95を測定した。
  - deterministic実EdgeでBUY／SELL、level削除、expiryを確認した。
  - 実runtime `/ws`へ独立Edge harnessを接続し、実BUY／SELL tradeを照合した。
  - 証拠PNG 3件を保存し、active／expired画像が異なるSHA-256であることを確認した。
  - 実装報告を作成し、`PROJECT_MEMORY.md`へ確認済み事実を追記した。

## 未完了

- root `FileResponse`安定化目的のcontainer restart
- image build
- ユーザー側browserでの最終目視
- commit／push

## 本件の予定変更file

- `Delta_Engine_Pro4web/webapp/static/footprint_canvas.js`
- `Delta_Engine_Pro4web/webapp/static/index.html`
- `Delta_Engine_Pro4web/tests/webapp/test_dom_trade_pulse_ui.py`
- 本checkpoint
- 実装完了報告
- HL-3完了時の`PROJECT_MEMORY.md`

原則変更しない:

- `Delta_Engine_Pro4web/webapp/static/time_sales.js`
- backend／storage／payload正本

## 検証結果

- JavaScript syntax:
  - `footprint_canvas.js`: PASS
  - `time_sales.js`: PASS
  - `orderbook_heatmap.js`: PASS
  - `index.html` inline script compile: PASS（1 script）
- DOM Trade Pulse新規test: **5 passed**
- HL-2対象回帰:
  - **27 passed, 1 baseline failure**
  - 新規failure 0
  - 一度Heatmapのsource marker testが失敗したが、coordinator内で既存の
    `TAPE_UI.store.streamId`を直接渡す契約へ戻し、再試験でPASSした。
- 関連baseline:
  - **25 passed, 1 failed**
  - failureは本件開始前から存在するHeatmap layout変更と旧assertの不一致:
    `test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation`
  - 旧testは`body.phase5-fusion #right>#left`を要求するが、
    現sourceは既存Heatmap差分で`body.phase5-fusion #main>#left`となっている。
  - 本件の回帰判定では、このbaseline failureを新規failureとして数えない。
- source変更前fingerprint:
  - `index.html`: 2,493行／181,129 bytes／
    `C18754A7A64E492C34C319757A64DD41002B41EEAE31DFD2243751B21005F4BB`
  - `footprint_canvas.js`: 1,039行／50,310 bytes／
    `D4E15757A41EC6B8E4D882EB5D20289EEEFEDC0D869594F0F6DA9194BF3CECB6`
  - `time_sales.js`: 435行／18,597 bytes／
    `F59FEC3F3478CC5A9B977C74978C3D8EB7C66E27A479A0B40FCF6D5F18F8D4C2`
  - `test_dom_tape_fusion_ui.py`: 185行／8,891 bytes／
    `C77E9FB55DD6A48C36A0229C44EF9F04193DF4CE2ABA7FA8D977DC4CA7C7E85A`
- Historical same-renderer実Edge baseline:
  - Canvas warm render p95: 2.0ms
  - Tape render p95: 2.2ms
  - 出典: Phase 5 completion report
- full regression:
  - **770 passed, 1 baseline failure, 1 skipped**
  - 新規failure 0
- performance:
  - 6,000 trades
  - ingest 5.994ms
  - pulses started 40／coalesced 5,960
  - active 40／capacity 256／eviction 0
  - overlay draw p95 0.138ms／max 1.348ms
- deterministic実Edge:
  - Canvas 768×467
  - BUY→ASK x 692、SELL→BID x 619、DOM center x 691
  - level削除後もactive
  - SELL expiry初回確認406.4ms
  - Canvas p95 0.5ms
  - gap／drop／overflow／browser error 0
- 実WebSocket:
  - LIVE SELL `7941933073`／64687.20 → BID x 619
  - LIVE BUY `7941935464`／64678.30 → ASK x 692
  - Book `SYNCED`
  - Tape gap／drop 0
- 証拠画像:
  - BUY Ask level removed:
    `62ADABDBD21F95B019022AF68F72C8D47536E7613C00ABD624D2BBCAC3E70506`
  - SELL Bid:
    `DC9701FB196851C872057E6DB2E0A52BDDDB6F0FAFA3947FC352250888965E31`
  - expired:
    `4D6EEE8DC2CE09198F87FD8D02719502D17AC55B7D19789938E4BD40B8A5B6D2`

## blockerの限定範囲

- 現時点でblockerなし。
- `index.html`は既存Heatmap作業と同じfileだが、差分を確認済みであり、
  accepted trade coordinatorへ統合して既存routeを保持できる。
- `git diff --check`は、開始前の`index.html`既存Heatmap差分に含まれていた
  EOF空行だけを報告する。本件で追加したPulse source／testにwhitespace errorはない。
- runtime containerはUpで、`/api/health`はHTTP 200へ自動復旧した。
  ただしroot `FileResponse`は断続的にtimeoutし、logへ
  `OSError: [Errno 9] Bad file descriptor`が一度記録された。
- direct `/ws`とPulseの実ライブ経路はPASSしているため、blockerは
  root page responseの安定運用確認だけに限定される。
- container restartは承認範囲外のため実行していない。

## 次の再開位置

1. ユーザーが画面を再読込し、実際の見え方を確認する。
2. root pageがtimeoutする場合は、container restartの明示承認を得る。
3. 承認後にrestart前後health、root HTTP、WebSocket、Pulseを再確認する。
4. pushが必要な場合は、ユーザーの明示承認を得る。

## Commit

- `feat/webapp: highlight DOM cells for accepted tape trades`（current HEADで確定）
- 本コミットの対象は本件実装・テスト・指示書・報告書・checkpoint・PROJECT_MEMORYと、共有integration file `index.html`。
- Heatmap関連の他ファイル、生成物、backend変更は未ステージ・未コミットのまま保全した。
