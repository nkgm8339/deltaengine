# [完了] Phase 2-0-d-1 同期stateマシン実装

- 報告時刻: 2026-07-29 22:34:20 +09:00
- 承認範囲: depth 初期同期 state machine、receiver tap、Live pipeline 配線、strict 検証テスト
- 判定: 指示範囲の実装と対象テストは完了。全体回帰は1回実行し、対象外かつ本作業で変更していない Heatmap UI の既存未コミット差分と既存テストの期待値不一致が1件残った。詳細は「全体回帰」を参照。
- ライブ接続: 実施していない。全テストは fixture / fake connector / mock REST 駆動。
- Phase 2-0-d-2: 着手していない。

## 1. 変更・新規ファイル

### 1.1 新規

1. `Delta_Engine_Pro4web/src/acquisition/depth_sync.py`
2. `Delta_Engine_Pro4web/tests/acquisition/test_depth_sync.py`
3. `ArchitectureRepository/00_Master/HEATMAP/Phase_2-0-d-1_同期stateマシン実装報告.md`（本報告）

### 1.2 変更

1. `Delta_Engine_Pro4web/src/acquisition/receiver.py`
2. `Delta_Engine_Pro4web/src/pipeline.py`
3. `Delta_Engine_Pro4web/tests/test_book_resync.py`
4. `Delta_Engine_Pro4web/tests/test_live_pipeline.py`
5. `Delta_Engine_Pro4web/tests/acquisition/test_binance_rest.py`

### 1.3 明示的に変更していないもの

- `Delta_Engine_Pro4web/src/orderflow/orderbook.py`
- `Delta_Engine_Pro4web/src/acquisition/depth_history_recorder.py`
- manifest スキーマ
- `DEPTH_HISTORY_MAX_BYTES` / max_bytes 配線
- `Delta_Engine_Pro4web/docker-compose.yml`
- `Delta_Engine_Pro4web/webapp/main.py`
- `Delta_Engine_Pro4web/tests/webapp/test_book_update.py`
- Replay pipeline

上記3つの既存保護差分（compose / main.py / test_book_update.py）を対象にした `apply_patch`、書込コマンドは実行していない。

## 2. `depth_sync.py` の state 実装

### 2.1 state と返却契約

- `DepthSyncState`: `src/acquisition/depth_sync.py:19`
  - `WAITING_FOR_FIRST_DEPTH`
  - `FETCHING_INITIAL_SNAPSHOT`
  - `VERIFYING_INITIAL_BRIDGE`
  - `SYNCED`
  - `RESYNC_BUFFERING`
  - `FETCHING_RESYNC_SNAPSHOT`
  - `VERIFYING_RESYNC_BRIDGE`
  - `SYNC_FAILED`
- snapshot 候補の `epoch` / `attempt` / `reason`: `SnapshotRequest`（同:37）
- coordinator の返却値: `DepthSyncAction`（同:52）
  - strict 検証済みの場合だけ `snapshot` と bridge 以後の `diffs` を返す。
  - 再取得が必要な場合は次の `SnapshotRequest` を返す。
  - 終端失敗は `SYNC_FAILED` と非空の `failure_reason` を返す。
- coordinator 本体: `DepthSyncCoordinator`（同:78）

coordinator は `OrderBookStateManager` を import せず、板 state を保持・変更しない。

### 2.2 state 遷移を担う関数

| 関数 | 行 | 担当 |
|---|---:|---|
| `notify_first_depth()` | 106 | 最初の有効 depth 実データ barrier。単独利用時の通知口。 |
| `observe_depth()` | 125 | pre-sync raw dict の到着順 buffer、初回 request 発行、候補待機中の再検証、buffer 上限失敗。pipeline では recorder 後・forward 前の receiver tap から呼ぶ。 |
| `observe_snapshot()` | 150 | epoch / attempt / reason の一致を検査し、INITIAL / RESYNC の VERIFYING state に入る。 |
| `observe_fetch_failure()` | 191 | REST 失敗も同じ有限 attempt 予算へ載せる。 |
| `start_resync()` | 222 | gap diff を新 epoch の先頭 buffer とし、`RESYNC_BUFFERING → FETCHING_RESYNC_SNAPSHOT` を開始する。 |
| `fail()` | 247 | 呼出側の正規化・apply 等の異常を明示的な `SYNC_FAILED` にする。 |
| `_verify_candidate()` | 254 | 最初の `U <= snapshot_u + 1 <= u` bridge 探索と、bridge 以後の `pu(後) == u(前)` 全件検証。 |
| `_reject_candidate()` | 297 | target 通過後 bridge 不在、または `pu` 不連続を reject。attempt 未達なら再取得、上限なら失敗。 |
| `_fail()` | 313 | silent retry を行わず終端 `SYNC_FAILED` にする。 |

### 2.3 strict 判定の具体

1. `observe_depth()` は raw dict を shallow copy して専用 list buffer に保持する。bids / asks の価格・数量文字列は変換しない。
2. buffer 最新 `u < snapshot_u + 1` の間は reject せず `VERIFYING_*_BRIDGE` で次の diff を待つ。
3. target を通過したのに bridge がなければ、その候補を reject して attempt を増やす。
4. bridge 以後の全隣接 diff の `pu` chain を検査し、不連続なら verified を返さない。
5. `max_buffered_diffs` と `max_attempts` は bool を含まない正整数のみ。ID は bool を含まない非負整数のみ。
6. buffer 上限、attempt 上限、REST fetch 上限のいずれも明示的な `SYNC_FAILED` と理由を返す。
7. `float()` は使用していない。

## 3. receiver と pipeline の配線

### 3.1 receiver: raw 記録 → buffer tap → forward

- callback 引数: `src/acquisition/receiver.py:72`
- callback 保持: 同:79
- 実行位置: 同:100-104

順序は次のまま固定した。

```text
validate
  → raw recorder.write(message)
  → on_valid_message(message)  # strict pre-sync buffer
  → destination.put(message)   # norm_q forward
```

したがって最初の snapshot request が fetch worker に渡る時点で、最初の有効 diff は raw 記録済みかつ専用 buffer 格納済みである。raw recorder は coordinator buffer と独立し、pre-sync diff を全量・到着順で記録する。

### 3.2 snapshot fetch worker

- result envelope: `src/pipeline.py:199`
- `_book_resync_supervisor()`: 同:205

旧 supervisor から `book_state` と `normalizer` 引数を除去した。新 worker の責務は次だけである。

1. main loop から明示的に渡された `SnapshotRequest` を待つ。
2. REST snapshot 候補を1回取得する。
3. 成功候補を reject 候補も含め raw recorder に記録する。
4. 候補または fetch error を main loop の result queue に返す。

worker は板 apply、bridge 判定、health polling、無限 retry を行わない。fetch error は request attempt に応じた 5 / 10 / 30 秒上限 backoff 後に coordinator へ返し、有限 attempt 予算で処理する。

### 3.3 最初の depth barrier

- 設定: `depth_sync_max_buffered_diffs` / `depth_sync_max_attempts`: `src/pipeline.py:929-930`
- receiver tap: 同:1210
- receiver 配線: 同:1233

`ExchangeConnector.state == SUBSCRIBED` は参照していない。`fetch_snapshot` が有効な場合だけ coordinator と専用 queue を作り、receiver tap が有効 `depthUpdate` を buffer に格納して返した action を main consumer が処理して初回 request を発行する。

### 3.4 板 apply の単一所有者

- verified batch apply: `src/pipeline.py:1528`
- action 処理: 同:1587
- receiver 由来 action drain: 同:1609
- snapshot result drain / coordinator 検証: 同:1620
- Live depth route / gap 開始: 同:1653

板 state を更新するのは `LivePipeline.run_async()` の main consumer 内だけである。

strict PASS 後の順序:

```text
normalize verified snapshot + verified diffs
  → book_state.apply(snapshot)
  → book_state.apply_initial_sync(snapshot_u)
  → verified bridge
  → verified bridge 以後の diffs（到着順）
```

`apply_initial_sync()` の lenient branch には、coordinator が `U <= snapshot_u + 1 <= u` を証明した bridge だけを最初の diff として渡す。以後は事前検証済み `pu` chain と `OrderBookStateManager` 自身の gap 検査を二重に通す。

通常同期後に main consumer が gap を検出した場合、同じ coordinator の `start_resync()` を呼び、新 epoch の BOOK_RESYNC を開始する。snapshot worker は板を変更しない。

prebuffer 済みイベントは main queue で二重 apply しない。main queue の overflow で diff が落ちても coordinator の verified raw batch には残る。イベント object の強参照 identity guard を用い、object ID 再利用と二重処理を避けた。

### 3.5 fail-closed と独立経路

- 同期待機中、失敗後とも板投影だけを行わない。
- trade / CVD / Footprint / Flow Price Response / liquidation の分岐は従来どおり処理する。
- Live 統合テストで attempt 上限後も trade 1件が保存されることを確認した。
- Replay pipeline は変更していない。Live / Replay 二重構造への影響は Live depth 分岐だけ。

## 4. 新規テスト

新規 `tests/acquisition/test_depth_sync.py` は11件。すべて fixture / in-memory queue 駆動でネットワークを使用しない。

| テスト | 行 | 指示書 §5 |
|---|---:|---|
| `test_depth_is_buffered_before_initial_snapshot_request` | 75 | 1 |
| `test_buffer_bridge_establishes_strict_sync` | 90 | 2 |
| `test_snapshot_is_refetched_when_buffer_passes_target_without_bridge` | 106 | 3 |
| `test_attempt_limit_fails_closed_with_explicit_reason` | 121 | 4 |
| `test_fetch_failures_share_the_finite_attempt_budget` | 136 | 4（REST error 分岐追加） |
| `test_pu_discontinuity_after_bridge_is_never_verified` | 148 | 5 |
| `test_candidate_waits_while_latest_buffer_u_is_before_target` | 163 | §4.1-4 の wait 条件 |
| `test_buffer_limit_is_explicit_sync_failure` | 179 | §4.1-2 / fail-closed |
| `test_receiver_records_all_presync_diffs_before_buffer_tap` | 189 | 1、6 |
| `test_book_resync_uses_the_same_strict_bridge_state_machine` | 234 | 7 |
| `test_sync_metadata_has_no_float_and_float_ids_are_rejected` | 256 | 8 |

## 5. 更新した既存テスト: 旧期待 → 新期待

### 5.1 `tests/test_book_resync.py`

| 旧期待 | 新期待 |
|---|---|
| supervisor が内部で無期限に retry し、成功時に板へ snapshot を即適用 | worker は1 request を1回 fetch し、失敗 result を coordinator に返す。有限 retry の所有者は coordinator。 |
| snapshot 成功で worker 自身が板を初期化 | worker は候補を raw 記録して result queue へ返すだけ。板引数自体を持たない。 |
| supervisor 内部の連続失敗回数で backoff | `SnapshotRequest.attempt` に応じて 5 / 10 / 30 秒（30秒 cap）。 |
| supervisor が板 health を polling し、gap 後に再取得・即適用 | main consumer が gap を検出して BOOK_RESYNC request を発行。worker は候補取得・記録のみ。 |
| healthy 中は polling を続け、snapshot fetch を抑止 | request がない限り worker は fetch を開始しない。 |
| health sleep 中の cancel | request queue 待機中の cancel が clean に終了。 |

新テスト名と行:

- `test_fetch_failure_is_reported_for_coordinator_retry`: 40
- `test_successful_snapshot_candidate_is_recorded_before_delivery`: 77
- `test_fetch_backoff_is_bounded_by_request_attempt`: 110
- `test_book_resync_candidate_uses_reason_without_mutating_book`: 144
- `test_worker_does_not_fetch_without_an_explicit_request`: 176
- `test_cancel_terminates_cleanly_while_waiting_for_request`: 205

### 5.2 `tests/acquisition/test_binance_rest.py`

- 旧: snapshot 適用後、stale diff と「最初の非 stale diff」を直接 lenient API に渡す前提。
- 新: `DepthSyncCoordinator` が strict bridge を証明し、返された bridge だけを `apply_initial_sync()` 後の最初の diff として渡す。
- テスト: `test_only_coordinator_verified_bridge_enters_initial_sync_apply`（146行）。

### 5.3 `tests/test_live_pipeline.py`

既存 trade / Flow Price Response テストの期待は変更していない。strict Live 統合テストを追加した。

- `test_live_depth_fetch_starts_after_raw_buffer_and_applies_verified_batch`（579行）
  - raw write / buffer が fetch より先。
  - snapshot 1件、verified diff 2件だけが apply される。
- `test_live_depth_attempt_limit_is_fail_closed_while_trade_path_continues`（619行）
  - bridge 不在で attempt 2回後に板 apply 0件。
  - 独立 trade 経路は継続して1件保存。

## 6. テスト結果

### 6.1 compile

```text
python -m py_compile src/acquisition/depth_sync.py src/acquisition/receiver.py src/pipeline.py
```

結果: 成功（exit 0）。

### 6.2 新規 coordinator

初回:

```text
python -m pytest -q -p no:cacheprovider tests/acquisition/test_depth_sync.py
........                                                                 [100%]
8 passed in 0.08s
```

追加した wait / buffer limit / fetch error budget を含む最終対象範囲:

```text
python -m pytest -q -p no:cacheprovider tests/acquisition/test_depth_sync.py tests/test_book_resync.py tests/test_live_pipeline.py tests/acquisition/test_binance_rest.py
...........................................                              [100%]
43 passed in 5.21s
```

### 6.3 周辺回帰

```text
python -m pytest -q -p no:cacheprovider tests/acquisition/test_acquisition.py tests/orderflow/test_orderbook.py tests/test_pipeline_snapshot_wiring.py tests/test_pipeline_absorption.py
............................                                             [100%]
28 passed in 1.75s
```

### 6.4 途中失敗（隠さず記録）

```text
python -m pytest -q -p no:cacheprovider tests/test_live_pipeline.py -k "live_depth_fetch_starts or live_depth_attempt_limit"
```

初回結果:

```text
2 failed, 16 deselected in 2.81s
AttributeError: 'LivePipeline' object has no attribute 'book_state'
```

原因: 新規テスト側が既存公開属性 `book_manager` を `book_state` と誤記。実装側の失敗ではない。テストの属性名を `book_manager` に修正し、同一コマンドの2回目は次のとおり成功した。

```text
..                                                                       [100%]
2 passed, 16 deselected in 1.46s
```

同一コマンドが2回連続失敗する停止条件には到達していない。

### 6.5 全体回帰（指定どおり1回のみ）

実行:

```text
python -m pytest -q -p no:cacheprovider
```

結果:

```text
1 failed, 707 passed, 1 skipped in 100.92s (0:01:40)
```

失敗:

```text
tests/webapp/test_dom_tape_fusion_ui.py::test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation

expected:
body.phase5-fusion #right>#left{display:none!important}

actual working-tree HTML:
body.phase5-fusion #main>#left{display:none!important}
```

切り分け:

- failure 対象の `webapp/static/index.html` と `tests/webapp/test_dom_tape_fusion_ui.py` は本指示書の変更対象外。
- 本作業の `apply_patch` では両ファイルを変更していない。
- 最終 working tree には `webapp/static/index.html` の別系統 Heatmap UI 未コミット差分（105 insertions / 10 deletions）が存在する。
- failing assertion はその別差分で CSS selector が `#right>#left` から `#main>#left` に変わった一方、既存テスト期待が旧 selector のままであることによる。
- 同一テスト2回連続失敗禁止と「既存未コミット差分を保護」のため再実行・修正は行っていない。
- Phase 2-0-d-1 対象テストは全成功している。

## 7. float 混入チェック

### 7.1 静的検査

変更追加行の `float(` 検査:

```text
NO_ADDED_FLOAT_CONVERSION
```

新規2ファイルを直接、builtin call として再検査:

```text
NO_FLOAT_CALL_IN_NEW_FILES
```

途中の単純文字列検査はテスト helper 名 `_contains_float(` を4件検出したが、builtin `float()` 呼出ではない。負の lookbehind を使った再検査で0件を確認した。

### 7.2 動的検査

`test_sync_metadata_has_no_float_and_float_ids_are_rejected` で以下を確認した。

- `DepthSyncAction` を `asdict()` 化した全 metadata / snapshot / diffs に float なし。
- 価格・数量 `"50000.125"` / `"0.250"` は文字列のまま。
- `u=103.0` は `DepthSyncInputError`。
- `max_buffered_diffs=1.0` は `DepthSyncInputError`。

## 8. 実行コマンドと結果

編集はすべて `apply_patch` を使用し、対象ファイルへの適用は全件成功した。追跡ファイルへの直接 patch が成立したため、`.patch` + `git apply --recount` 分岐は不要だった。

| # | コマンド / 操作 | 結果 |
|---:|---|---|
| 1 | `.NET File.ReadAllText` による `ArchitectureRepository/00_Master/PROJECT_MEMORY.md` 全文読取（同一会話の Phase 2-0-a） | 成功。27,563 byte / 439行。 |
| 2 | `git status --short`（実装対象と指定保護3ファイル） | 実装対象は clean。保護3ファイルの既存差分を確認。 |
| 3 | `git diff --stat`（指定保護3ファイル） | compose +1、test_book_update +117、main.py に既存差分。 |
| 4 | `Get-Content -Raw src/acquisition/receiver.py` | 成功。record → forward 契約を確認。 |
| 5 | `Get-Content` / `rg -n` による `src/pipeline.py`、`normalizer.py`、`orderbook.py`、関連テスト確認 | 成功。旧 supervisor 即適用、main depth apply、lenient branch、テスト契約を特定。 |
| 6 | `rg -n "fetch_snapshot..." tests` と depth fixture 検索 | 成功。影響テストと `fetch_snapshot=None` の test-only 経路を特定。 |
| 7 | `python -m py_compile ...` | 成功。 |
| 8 | `pytest tests/acquisition/test_depth_sync.py` | 8 passed。 |
| 9 | `pytest tests/test_book_resync.py` | 6 passed。 |
| 10 | `pytest tests/test_live_pipeline.py -k ...`（初回） | 2 failed。テスト属性名誤記。 |
| 11 | 同上（修正後） | 2 passed, 16 deselected。 |
| 12 | 対象4テストファイル一括（最初） | 40 passed。 |
| 13 | 対象4テストファイル一括（追加ケース後） | 43 passed。 |
| 14 | receiver / orderbook / snapshot wiring / Replay absorption 周辺 | 28 passed。 |
| 15 | `git diff --check` + `git diff --stat` + 対象 `git status` | exit 0。空白エラーなし。Git の LF→CRLF warning のみ。 |
| 16 | 変更追加行の `float(` 検査 | `NO_ADDED_FLOAT_CONVERSION`。 |
| 17 | 新規ファイルの単純 `float(` 検査 | `_contains_float(` helper 名を4件検出（builtin call ではない）。 |
| 18 | builtin `float()` に限定した再検査 | `NO_FLOAT_CALL_IN_NEW_FILES`。 |
| 19 | `python -m pytest -q -p no:cacheprovider` | 707 passed, 1 skipped, 1 unrelated failure。再試行なし。 |
| 20 | `rg` / `git status` / `git diff` で全体回帰 failure を read-only 切り分け | 別系統 Heatmap UI 差分の selector と旧テスト期待の不一致を確定。 |
| 21 | `rg -n` による最終行番号・テスト名採取 | 成功。 |
| 22 | `git status --short` / `git diff --numstat` 最終監査 | 指示対象差分と多数の既存・別系統差分を確認。本作業対象外は未変更。 |

## 9. 発見した想定外事項

1. 全体回帰時、指定されていた保護3ファイル以外にも Heatmap UI / VWAP 系の tracked・untracked 差分が working tree に存在した。本作業では変更・整理・削除していない。
2. `webapp/static/index.html` の別系統差分と既存 DOM テストの selector 期待が不一致で、全体回帰が1件だけ失敗した。本指示書の変更対象外なので修正していない。
3. Git は変更ファイルについて「次回 Git が触れる際 LF が CRLF に置換される」warning を出した。`git diff --check` は成功し、内容エラーはない。

## 10. checkpoint / 引継ぎ

- 現在時刻: 2026-07-29 22:34:20 +09:00
- 完了済み:
  - strict coordinator
  - receiver raw-after-record buffer tap
  - request-driven snapshot worker
  - main consumer の単一 board apply
  - 初期同期 / gap再同期の同一 state machine
  - finite attempt / buffer 上限 / fail-closed
  - 新規11テスト、既存影響テスト更新
  - 対象43 passed、周辺28 passed、全体回帰1回
  - float 検査
- 未完了:
  - Phase 2-0-d-1 の必須実装なし。
  - 全体回帰の対象外 DOM テスト1件は別差分所有者の判断待ち。
- blocker の限定範囲:
  - `webapp/static/index.html` の別系統未コミット差分と `tests/webapp/test_dom_tape_fusion_ui.py` の旧期待不一致だけ。
  - depth sync 実装・対象テストは block されていない。
- 次の再開位置:
  - 統括が本報告と差分を検証する。
  - Phase 2-0-d-2 は新しい明示指示を受領するまで開始しない。

## 11. 報告書保存先

`ArchitectureRepository/00_Master/HEATMAP/Phase_2-0-d-1_同期stateマシン実装報告.md`
