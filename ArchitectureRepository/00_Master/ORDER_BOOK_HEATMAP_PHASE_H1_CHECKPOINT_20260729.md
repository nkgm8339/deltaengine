# Order Book Heatmap Phase H1 checkpoint

最終更新: 2026-07-29 06:01 JST
状態: **GO-H1実装・全検証完了／source PASS／runtime未配備**

## 承認

- ユーザー発言: `GO-H1`
- 承認範囲:
  - `BOOK_UPDATE`へadditive `book_stream_id`／`book_sequence`を追加
  - 同一broker lifecycle、連続sequence、fail-closed、reconnect cache、restart境界のtest
  - WebSocket payload specification更新
  - targeted／WebApp／repository regression
- 未承認:
  - GO-H2以降のHeatmap store／Canvas／UI
  - runtime再起動、image build、deployment
  - depth history永続化
  - completed Footprint／Tape／3段チャートの変更

## 開始状態

- branch: `feature/footprint-dom-tape`
- HEAD: `1134886430b7c48487cd4a9389a202acfa6ff53e`
- restore point message: `snapshot: preserve Footprint DOM Tape baseline before heatmap`
- GO-H0 post-commit記録として次の2 fileに既存変更あり。保持する。
  - `ArchitectureRepository/00_Master/ORDER_BOOK_HEATMAP_PHASE_H0_CHECKPOINT_20260729.md`
  - `ArchitectureRepository/00_Master/PROJECT_MEMORY.md`
- runtime／measurement artifact 13 fileと別topic文書3 fileはuntrackedのまま保持する。
- baseline: WebApp 122 passed、repository 664 passed／1 skipped、実Edge error 0。

## 完了済み

- GO-H1承認境界を固定した。
- `PushBroker.__init__`、`register`、`on_book_update`を確認した。
- reconnectは`_latest_book_message`を同一JSONとして再送するため、cache messageへsequenceを固定すれば再採番されない。
- existing `book_updates_broadcast`はvalidation通過後の`BOOK_UPDATE`ごとに1増えるため、`book_sequence`のsingle sourceとして利用できる。
- 現payload specは`BOOK_UPDATE v1.2 additive`でcontinuity fieldを持たない。
- 現testはSYNCED payload、reconnect exact equality、fail-closed clearを検証済み。
- 実装方針を固定した。
  - broker lifecycleごとに`str(uuid4())`の`book_stream_id`
  - `book_sequence = book_updates_broadcast + 1`
  - validation failureはsequenceを消費しない
  - SYNCED／fail-closed双方を連番対象とする
  - reconnect cacheは同じstream ID／sequenceを再送する
  - new broker lifecycleはnew UUID、sequence 1
- `PushBroker` lifecycleごとにcanonical UUID `book_stream_id`を生成する実装を追加した。
- `book_sequence = book_updates_broadcast + 1`をpayloadへ追加し、counterと同じsingle sourceへ固定した。
- existing payload field、fail-closed clear、reconnect cache処理は変更していない。
- payload specificationを`BOOK_UPDATE v1.4 additive`へ更新した。
- contract testを追加した。
  - canonical UUID／initial sequence 1
  - SYNCED→STALE→recoveryのsequence 1／2／3
  - fail-closedも連番対象
  - new broker lifecycleで別UUID／sequence 1
  - validation failureはsequenceを消費しない
  - reconnect cacheは同一message
- targeted tests: `45 passed in 3.54s`。
- WebApp全体: `125 passed in 7.90s`。
- repository全体: `667 passed, 1 skipped in 34.53s`。
- test failure／error: 0。
- 検証用pytest temporary directory 3件はabsolute pathを検証して削除済み。
- H1 completion reportを作成した。
- completion document diff check初回は指示書metadata 3行のMarkdown hard-break末尾spaceだけを検出。除去後の再checkはPASS。

## 未完了

- GO-H1承認範囲内はなし。
- GO-H2 Pure Heatmap coreは未承認。

## 変更file

- `ArchitectureRepository/00_Master/ORDER_BOOK_HEATMAP_PHASE_H1_CHECKPOINT_20260729.md`
- `Delta_Engine_Pro4web/webapp/push_broker.py`
- `Delta_Engine_Pro4web/tests/webapp/test_book_update.py`
- `ArchitectureRepository/30_Modules/WebApp/Specifications/WebSocketPayload_Spec_v1.md`
- `ArchitectureRepository/00_Master/ORDER_BOOK_HEATMAP_PHASE_H1_COMPLETION_REPORT_20260729.md`
- `ArchitectureRepository/00_Master/ORDER_BOOK_HEATMAP_IMPLEMENTATION_INSTRUCTION_V1_20260729.md`
- `ArchitectureRepository/00_Master/PROJECT_MEMORY.md`

## 検証／blocker／再開位置

- source diff check: PASS
- instruction section 0〜31連番／source contract 5 marker: PASS
- targeted test: PASS
- WebApp／repository full regression: PASS
- blocker: なし
- runtime: 未再起動／未配備
- 次の再開位置: ユーザーが明示GO-H2を出した場合、pure Heatmap coreのsource変更前checkpointから開始する。
