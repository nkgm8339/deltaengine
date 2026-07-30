# Phase 2-1 板state再構築器 実装報告

## Task 0 checkpoint — 証拠保全完了

- checkpoint時刻: 2026-07-30 08:07:43 +09:00
- 現在HEAD: `e358a0f1696ad3065ce37fce1a75f62b43f46ab8`
- 承認範囲: Task 0（実装前のtracked差分パッチ、untracked一覧、SHA-256取得、checkpoint記録）のみ
- 完了済み:
  - `PROJECT_MEMORY.md`と`CLAUDE.md`の全文確認
  - Step 0出力先の衝突なし確認
  - tracked差分の全量パッチ保全
  - `git status --porcelain`の保全
  - パッチとstatusファイルのSHA-256、byte数、行数の取得
  - パッチ内tracked section数と現在のtracked差分file数の一致確認
- 未完了:
  - Task 1以降のN1〜N7実装
  - fixture生成
  - pytest
  - 34セグメントCLI確認
  - 最終報告、完全ZIP、CompletionLog.md追記
- Task 0変更file:
  - `ArchitectureRepository/00_Master/HEATMAP/worktree_backup_pre_p21_20260730.patch`
  - `ArchitectureRepository/00_Master/HEATMAP/worktree_status_pre_p21_20260730.txt`
  - `ArchitectureRepository/00_Master/HEATMAP/Phase_2-1_板state再構築器実装報告.md`
- 検証結果:
  - patch SHA-256: `E3DE49359AFC63117433DDF9B8183CA2C4B0AE2C6E21ADE08963EF14997C1B70`
  - patch: 108,960 bytes / 2,413 lines / tracked section 16件
  - 現在のtracked差分file: 16件（patch section数と一致）
  - status SHA-256: `E7A3E18130C245392D2B02D074CB3A4A667A3F7658A7CA188D63818D7BD7560A`
  - status: 6,389 bytes / 58 lines
  - status一覧には、コマンド実行時点で既に生成されたpatch自身と、redirect開始時に作成されたstatus自身も含まれる
  - `git add / commit / stash / checkout`実行なし
  - 既存fileの変更なし
- blocker: なし
- 次の再開位置: Task 1の個別承認受領後、N1 `src/heatmap/__init__.py` とN2 `src/heatmap/reconstruct.py`の新規実装から再開する

### 実行コマンドと結果

```powershell
git diff > ArchitectureRepository/00_Master/HEATMAP/worktree_backup_pre_p21_20260730.patch
git status --porcelain > ArchitectureRepository/00_Master/HEATMAP/worktree_status_pre_p21_20260730.txt
```

- 両コマンドともexit code 0。
- `git diff`では既存working copyのLF→CRLF警告が出たが、対象fileへの書込みや変換は発生していない。
- 同一コマンド連続失敗、timeout、ライブ接続は発生していない。

## Task 1 start checkpoint — N1・N2

- checkpoint時刻: 2026-07-30 08:25:32 +09:00
- 承認範囲: N1 `Delta_Engine_Pro4web/src/heatmap/__init__.py` とN2 `Delta_Engine_Pro4web/src/heatmap/reconstruct.py`の新規実装のみ
- 完了済み: Task 0証拠保全
- 未完了: N1・N2実装、Task 1内の非ライブ静的／smoke検証、Task 2以降
- 変更file: Task 0成果物3件のみ
- 検証結果: Task 0承認済み
- blocker: なし
- 固定契約:
  - `DepthSyncCoordinator`がverifiedを返したsnapshot＋diffsだけをbookへ渡す
  - 適用順は`apply(SNAPSHOT)`→`apply_initial_sync(snapshot_u)`→verified diffs到着順
  - `OrderBookStateManager`のlenient分岐はverified bridge diffのみに使用する
  - Decimal変換だけを使用し、float型入力を拒否する
- 次の再開位置: 実録画のレコード形状をread-only確認後、N1・N2を新規作成する

## Task 1 completion checkpoint — N1・N2

- checkpoint時刻: 2026-07-30 08:32:27 +09:00
- 承認範囲: N1・N2の新規実装とTask 1内の非ライブ限定検証
- 完了済み:
  - N1 空package `src/heatmap/__init__.py`
  - N2 `src/heatmap/reconstruct.py`
  - `SegmentInfo`、`SegmentIntegrityError`、`DepthHistoryReader`
  - `ReconstructionEvent`、`DepthReconstructor`
  - manifest V1/V2読込、byte／record／SHA-256照合、manifest欠如segment skip
  - trade skip、float再帰拒否、Decimal価格／数量変換
  - initial sync、gap、resync、terminal failure、sampling、counters
  - verified snapshot＋diffだけをbookへ渡す固定適用手順
- 未完了: Task 2以降のfixture生成、正式pytest、CLI、全体検証、最終提出
- Task 1変更file:
  - `Delta_Engine_Pro4web/src/heatmap/__init__.py`
  - `Delta_Engine_Pro4web/src/heatmap/reconstruct.py`
  - 本報告書のTask 1 checkpoint追記
- file検証:
  - `__init__.py`: 1 byte、SHA-256 `01BA4719C80B6FE911B091A7C05124B64EEECE964E09C058EF8F9805DACA546B`
  - `reconstruct.py`: 20,394 bytes／LF改行数573、SHA-256 `84639422635CC01678CFB1E622FA561DF0B51D733A3262DA4A2B3A25C16BEB0C`
  - `src/heatmap/__pycache__`生成なし
  - tracked既存差分file数はTask 0時点と同じ16件
- 検証結果:
  - AST構文解析／import: PASS
  - 合成verified bridge: `SYNC_STARTED`→`SNAPSHOT_APPLIED`→`DIFF_APPLIED` 2件、PASS
  - 固定順`apply(SNAPSHOT)`→`apply_initial_sync()`→verified diffs: PASS
  - 合成最終stateの全価格・数量Decimal、last_update_id 103: PASS
  - 実録画先頭2segment: `SNAPSHOT_APPLIED=1`、`DIFF_APPLIED=135`、gap 0、sync failure 0、PASS
  - 実録画最終last_update_id: `11165395982872`
  - 合成gap→`RESYNC_STARTED`→後続snapshot再同期: PASS
  - 合成bridge不成立→`SYNC_FAILED`、後続depth discard count: PASS
- 実行上の注意:
  - 最初のread-only schema確認PowerShellは、出力objectの`U`／`u`がcase-insensitive重複keyとなりParserError 1回。
  - 同一コマンドを再実行せず、出力名を`FirstId`／`FinalId`へ変えた別コマンドで成功。
  - pytest失敗、同一コマンド連続失敗、timeout、ライブ接続なし。
- blocker: なし
- 次の再開位置: Task 2の個別承認受領後、N7 fixture生成scriptとN5実データ縮約fixtureを新規作成する

### Task 1行数報告の訂正

- 旧報告の495行はPowerShell `Get-Content | Measure-Object -Line`の結果であり、空行を数えない値だった。
- 実fileは20,394 bytes、SHA-256 `84639422635CC01678CFB1E622FA561DF0B51D733A3262DA4A2B3A25C16BEB0C`で不変。
- byte列中のLF（`0x0A`）を数えた改行数は573。以後はbyte数とSHA-256を正とし、行数表記はLF改行数に統一する。

## Task 2 start checkpoint — N7・N5

- checkpoint時刻: 2026-07-30 19:01:32 +09:00
- 現在HEAD: `0709a09c0b1ea56d2877527dc075d428c43e4f8c`
- 承認範囲:
  - N7 `Delta_Engine_Pro4web/tests/heatmap/fixtures/make_real_fixture.py`
  - N5 `Delta_Engine_Pro4web/tests/heatmap/fixtures/real_validation/`の縮約JSONL 2件＋manifest 2件
- 完了済み: Task 0、Task 1
- 未完了: N7・N5作成、再実行一致確認、Task 3以降
- 変更file: Task 0・Task 1成果物のみ
- 検証結果:
  - N7とN5出力directoryは未作成で衝突なし
  - N2のbyte数／SHA-256はTask 1完了時から不変
  - N2の正しいLF改行数は573
- 固定条件:
  - 元録画の先頭2segmentだけを入力する
  - depthSnapshot全行、depthUpdate全136行、trade先頭5行だけを抽出する
  - 各縮約manifestの`_fixture_provenance`へ元file名と元SHA-256を記録する
  - 縮約後のrecord_count／byte_size／sha256を実値で再計算する
  - JSON価格・数量を型変換せず、元recordを再直列化する
- blocker: なし
- 次の再開位置: 元2segmentとmanifestの対応・SHA-256をread-only確認後、N7を新規実装する

## Task 2 completion checkpoint — N7・N5

- checkpoint時刻: 2026-07-30 19:05:42 +09:00
- 現在HEAD: `0709a09c0b1ea56d2877527dc075d428c43e4f8c`
- 承認範囲: N7生成script、N5縮約fixture、Task 2内の非ライブ生成・独立監査
- 完了済み:
  - pinned source filename／SHA-256／manifest metricsを検証するN7生成script
  - 元JSONL byteを保持した縮約segment 2件
  - 縮約後の実値を記録したmanifest 2件
  - `_fixture_provenance.source_filename`と`source_sha256`の記録
  - 同一入力での再実行一致確認
  - N2 reader／reconstructorを用いた独立監査
- 未完了: Task 3以降の正式pytest、CLI、全体検証、最終提出
- Task 2変更file:
  - `Delta_Engine_Pro4web/tests/heatmap/fixtures/make_real_fixture.py`
  - `Delta_Engine_Pro4web/tests/heatmap/fixtures/real_validation/raw_depth.20260729T193154.046959Z.jsonl`
  - `Delta_Engine_Pro4web/tests/heatmap/fixtures/real_validation/raw_depth.20260729T193154.046959Z.jsonl.manifest.json`
  - `Delta_Engine_Pro4web/tests/heatmap/fixtures/real_validation/raw_depth.20260729T193201.309417Z.jsonl`
  - `Delta_Engine_Pro4web/tests/heatmap/fixtures/real_validation/raw_depth.20260729T193201.309417Z.jsonl.manifest.json`
  - 本報告書のTask 2 checkpoint追記
- file検証（行数はLF改行数）:
  - `make_real_fixture.py`: 9,347 bytes／LF 278／SHA-256 `3EB58620B61F2BA1BED36254C579BD9E62896E63B5C26DA1EA5E52B781AC679B`
  - 1本目JSONL: 428,126 bytes／LF 77／SHA-256 `FC947A962C4216998294713535A665995F186BE16776F7D251438CF8553632F8`
  - 1本目manifest: 906 bytes／LF 1／SHA-256 `442CF60B418093C28642D245C1082E4DECD640F6A62C9968E55FFA3378D46326`
  - 2本目JSONL: 406,713 bytes／LF 65／SHA-256 `2E79BA05A8390283F608B858D5976A94CDD8A44D906F517D2E9366DEC23EC231`
  - 2本目manifest: 725 bytes／LF 1／SHA-256 `9F0CE451817FD19A4CF007D357815DB9F9B0A5F40DEB2880241B39DF701C0ED2`
- provenance:
  - 1本目source: `raw_depth.20260729T193154.046959Z.jsonl`
  - 1本目source SHA-256: `58048404f36a7fcb4a2487cb87d8c9a9f95386d624c3d4bccb1c21b227747dd6`
  - 2本目source: `raw_depth.20260729T193201.309417Z.jsonl`
  - 2本目source SHA-256: `1aaf0643344a30338cfb8e7bced642a83751c52a95008c488b91c93e13741a6d`
- 検証結果:
  - 元source 2件のbyte／record／SHA-256とmanifest一致: PASS
  - 抽出合計: depthSnapshot 1、depthUpdate 136、trade 5: PASS
  - 1本目内訳: depthSnapshot 1、depthUpdate 71、trade 5
  - 2本目内訳: depthUpdate 65
  - 生成script再実行: exit 0、4出力fileのSHA-256差異0
  - 縮約manifest byte_size／record_count／sha256: 全件一致
  - `_fixture_provenance`元file名／元SHA-256: 全件一致
  - JSON内float 0、全板価格・数量string: PASS
  - reader: segment 2、skip 0、integrity PASS
  - reconstruction: SNAPSHOT_APPLIED 1、DIFF_APPLIED 135、gap 0、sync failure 0
  - 最終last_update_id: `11165395982872`
  - `__pycache__`生成なし
  - tracked既存差分file数はTask 0・Task 1時点と同じ16件
- 実行統制:
  - pytest未実行
  - 同一コマンド連続失敗、timeout、ライブ接続なし
- blocker: なし
- 次の再開位置: Task 3の個別承認受領後、N3 `tests/heatmap/__init__.py`とN4 `tests/heatmap/test_reconstruct.py`を新規作成する

## Task 3 start checkpoint — N3・N4

- checkpoint時刻: 2026-07-30 20:29:04 +09:00
- 現在HEAD: `0709a09c0b1ea56d2877527dc075d428c43e4f8c`
- 承認範囲:
  - N3 `Delta_Engine_Pro4web/tests/heatmap/__init__.py`
  - N4 `Delta_Engine_Pro4web/tests/heatmap/test_reconstruct.py`
  - 対象pytestの1回実行
- 完了済み: Task 0〜Task 2
- 未完了: N3・N4作成、対象pytest、Task 4以降
- 変更file: Task 0〜Task 2成果物のみ
- 開始時検証:
  - N3・N4は未作成で衝突なし
  - real fixture 4file存在
  - N2 SHA-256は`84639422635CC01678CFB1E622FA561DF0B51D733A3262DA4A2B3A25C16BEB0C`で不変
  - tracked既存差分fileは17件。Task 2完了時の16件から外部作業により1件増えているため、Task 3対象から除外して保持する
- 合成8ケース:
  1. bridge成立→SYNCED→複数diff適用
  2. bridge不成立→SYNC_FAILED
  3. pu断絶→GAP_DETECTED→後続BOOK_RESYNC snapshotで再同期
  4. pu断絶→後続snapshotなし→末尾まで未適用、counter整合
  5. stale diff→bookがdiffs_staleとして拒否し継続
  6. manifest SHA-256不一致→SegmentIntegrityError
  7. manifest欠如segment→skipped_segments
  8. float混入record→DepthSyncInputError
- 実fixture assert:
  - snapshot_u `11165393552876`
  - bridge `U=11165393550921`／`u=11165393566438`
  - bridge前pre-sync depth 1件は未適用
  - `SNAPSHOT_APPLIED=1`／`DIFF_APPLIED=135`／gap 0／sync failure 0
  - 最終last_update_idは2本目最終depthの`u`と一致
  - state内全価格・数量Decimal、float 0
  - `sample_states(interval_ms=1000)`の時刻は単調増加
- 実行統制:
  - 正式pytestはテスト完成後に1回だけ実行
  - 同一テスト失敗2回連続で停止
- blocker: なし
- 次の再開位置: N3・N4を新規作成し、静的確認後に対象pytestを1回実行する

## Task 3 completion checkpoint — N3・N4

- checkpoint時刻: 2026-07-30 20:32:31 +09:00
- 現在HEAD: `0709a09c0b1ea56d2877527dc075d428c43e4f8c`
- 承認範囲: N3・N4新規作成、AST静的確認、対象pytest 1回
- 完了済み:
  - N3 空package `tests/heatmap/__init__.py`
  - N4正式テスト10件（合成8件＋実fixture 2件）
  - 対象pytest初回実行
- 未完了: Task 4以降のCLI、全体pytest、34segment確認、最終提出
- Task 3変更file:
  - `Delta_Engine_Pro4web/tests/heatmap/__init__.py`
  - `Delta_Engine_Pro4web/tests/heatmap/test_reconstruct.py`
  - 本報告書のTask 3 checkpoint追記
- file検証（行数はLF改行数）:
  - `tests/heatmap/__init__.py`: 1 byte／LF 1／SHA-256 `01BA4719C80B6FE911B091A7C05124B64EEECE964E09C058EF8F9805DACA546B`
  - `tests/heatmap/test_reconstruct.py`: 14,290 bytes／LF 501／SHA-256 `0C2D734F95D6A6A05B0DD438ED8F946DD8964C844939261D6227E21D53C605F7`
  - N2 SHA-256は`84639422635CC01678CFB1E622FA561DF0B51D733A3262DA4A2B3A25C16BEB0C`で不変
  - real fixture 4fileは保持
- 正式テスト内容:
  1. bridge成立→複数diff適用
  2. bridge不成立→max_attempts=1でSYNC_FAILED
  3. pu断絶→gap→後続snapshotでepoch 2再同期
  4. pu断絶→snapshotなし→未初期化のまま末尾
  5. stale diff→book `diffs_stale=1`、後続diff継続
  6. manifest SHA-256不一致→SegmentIntegrityError
  7. manifest欠如`.jsonl`／`.jsonl.part` skip＋V1列挙
  8. float混入record→DepthSyncInputError
  9. 実fixtureのsnapshot／bridge／pre-sync／135diff／最終state／Decimal契約
  10. 実fixture `sample_states(interval_ms=1000)`の厳密単調増加／Decimal契約
- 実fixture assert結果:
  - snapshot_u `11165393552876`: PASS
  - bridge `U=11165393550921`／`u=11165393566438`: PASS
  - bridge前pre-sync depth 1件、適用eventに不在: PASS
  - SNAPSHOT_APPLIED 1／DIFF_APPLIED 135／GAP_DETECTED 0／SYNC_FAILED 0: PASS
  - 最終last_update_idと2本目最終depth `u`一致: PASS
  - 全state price／quantity Decimal、float 0: PASS
  - sample時刻は1,000ms間隔で厳密単調増加: PASS
- 実行コマンド:

  ```powershell
  python -m pytest -q -p no:cacheprovider tests/heatmap/test_reconstruct.py
  ```

- 実行結果: `10 passed in 2.72s`、exit code 0
- 実行統制:
  - 対象pytest実行回数1回
  - pytest失敗0、同一失敗0、timeoutなし、ライブ接続なし
  - `__pycache__`生成0
  - `-p no:cacheprovider`を指定。workspaceに既存`.pytest_cache`は存在するが本実行ではcacheproviderを無効化
  - tracked既存差分fileは開始時と同じ17件
- blocker: なし
- 次の再開位置: Task 4の個別承認受領後、N6 `ArchitectureRepository/00_Master/HEATMAP/tools_p21/reconstruct_check.py`を新規実装する

## Task 4 start checkpoint — N6・全pytest・34segment CLI

- checkpoint時刻: 2026-07-30 20:40:58 +09:00
- 直近確認HEAD: `0709a09c0b1ea56d2877527dc075d428c43e4f8c`
- 承認範囲:
  1. N6 `ArchitectureRepository/00_Master/HEATMAP/tools_p21/reconstruct_check.py`
  2. `python -m pytest -q -p no:cacheprovider`の1回実行
  3. 検証録画34segmentへのN6 CLI 1回実行
- 完了済み: Task 0〜Task 3
- 未完了: N6実装、全pytest、34segment CLI、最終提出
- 開始時検証:
  - N6は未作成で衝突なし
  - 検証録画directory実在
  - JSONL 34件／manifest 34件
  - tracked差分17件の内訳は直前のstatus比較で確認済み。追加1件はPhase 2-1対象外の`config/hook_thresholds.yaml`
- 全pytest判定基準:
  - 既知許容failは`tests/webapp/test_dom_tape_fusion_ui.py` 1件のみ
  - Hook較正14testとPhase 2-1新規10testによりpassed総数増加を見込む
  - 新規fail 0を合格条件とする
- CLI出力契約:
  - segment数／skip数／integrity
  - event種別count／reconstructor counters
  - sample count／interval
  - 最終last_update_id
  - 整数ms所要時間
- 実行統制:
  - 全pytestは1回のみ
  - フル34segment CLIは1回のみ
  - timeout時は再実行せず、①取得待ち ②処理負荷 ③テスト制限時間に分類して報告
  - ライブ接続禁止
- blocker: なし
- 次の再開位置: N6を新規作成し、AST静的確認後に全pytestを1回実行する

## Task 4 completion checkpoint — N6・全pytest・34segment CLI

- checkpoint時刻: 2026-07-30 20:47:02 +09:00
- 承認範囲: N6新規実装、全pytest 1回、34segment CLI 1回
- 完了済み:
  - N6 manual offline verification CLI
  - 全pytest初回実行
  - 検証録画全34segmentのCLI初回実行
- 未完了: 最終報告書確定、完全ZIP、CompletionLog.md追記
- Task 4変更file:
  - `ArchitectureRepository/00_Master/HEATMAP/tools_p21/reconstruct_check.py`
  - 本報告書のTask 4 checkpoint追記
- N6 file検証（行数はLF改行数）:
  - 4,987 bytes／LF 156
  - SHA-256 `84C15DFB96A2D3E41D472568BD6E86EC7A07B09DED38017F1F85477BF18C4CA9`
  - `__pycache__`／temporary file生成0
- 全pytest実行:

  ```powershell
  python -m pytest -q -p no:cacheprovider
  ```

- 全pytest結果:
  - exit code 1
  - `1 failed, 737 passed, 1 skipped in 190.06s (0:03:10)`
  - failは既知の
    `tests/webapp/test_dom_tape_fusion_ui.py::test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation`
    1件のみ
  - 失敗assertは既知selector
    `body.phase5-fusion #right>#left{display:none!important}`
  - 新規fail 0
  - 指定ベースライン727 passedから10件増加し、Phase 2-1新規test 10件と一致
  - Hook較正14件が727 baselineへ既に含まれていたかは集計summaryだけでは分離不能だが、新規failゼロ基準は満たす
  - timeoutなし、再実行なし、ライブ接続なし
- 34segment CLI実行:

  ```powershell
  python ArchitectureRepository/00_Master/HEATMAP/tools_p21/reconstruct_check.py Delta_Engine_Pro4web/data_05M/phase2_0_d2_validation/20260730T043059/depth_history_raw/symbol=BTCUSDT --interval-ms 1000
  ```

- 34segment CLI結果:
  - exit code 0／status PASS
  - segment 34／skip 0／integrity PASS
  - SYNC_STARTED 1
  - SNAPSHOT_APPLIED 1
  - DIFF_APPLIED 2,938
  - GAP_DETECTED 0
  - RESYNC_STARTED 0
  - SYNC_FAILED 0
  - trades_skipped 25,144
  - samples 300／interval 1,000ms
  - first sample `1785353514944`
  - last sample `1785353813944`
  - final last_update_id `11165441170516`
  - CLI elapsed 32,191ms
  - timeoutなし、再実行なし、ライブ接続なし
- timeout分類: timeout非発生のため該当なし
- blocker: なし
- 次の再開位置: 最終Taskの個別承認受領後、報告書最終監査、完全ZIP、CompletionLog.md追記を行う

## Task 5 start checkpoint — 最終提出

- checkpoint時刻: 2026-07-30 20:50:03 +09:00
- 承認範囲:
  1. 本報告書の最終監査・完成
  2. N1〜N7、Task 0証拠、報告書、SHA-256 inventoryを含む完全ZIP
  3. `ArchitectureRepository/00_Master/CompletionLog.md`への承認済み例外追記
- 完了済み: Task 0〜Task 4
- 未完了: 最終inventory、ZIP直前status監査、完全ZIP、CompletionLog追記
- 出力予定:
  - `ArchitectureRepository/00_Master/HEATMAP/Phase_2-1_SHA256_INVENTORY_20260730.txt`
  - `ArchitectureRepository/00_Master/HEATMAP/Phase_2-1_Reconstructor_complete_20260730.zip`
- 開始時検証:
  - inventory／ZIPとも衝突なし
  - 本報告書は19,060 bytes
  - CompletionLog.mdの既存形式と追記位置を確認
- packaging契約:
  - ZIP entryはrepository相対pathを保持する
  - N1〜N7の全file、Task 0 patch／status、本報告書、inventoryだけを明示列挙する
  - unrelated dirty／Hook／VWAP／runtime artifactをZIPへ混入しない
  - inventoryは全payloadのbyte数／LF改行数／SHA-256を記録し、自己参照となるinventory自身のhashは外部監査で報告する
  - ZIP自身のSHA-256は自己参照を避けてCompletionLog／チャットで報告する
- 停止条件:
  - ZIP直前`git status --porcelain`に既知差分・承認済みPhase 2-1差分以外が現れた場合はZIPを作らず停止
- blocker: なし
- 次の再開位置: 明示payloadの存在・hashを監査し、本報告書の最終summaryを確定する

## 最終実装監査

- 監査時刻: 2026-07-30 20:51:12 +09:00
- 実装判定: **PASS**
- 完成範囲:

  | ID | 成果物 |
  |---|---|
  | N1 | `Delta_Engine_Pro4web/src/heatmap/__init__.py` |
  | N2 | `Delta_Engine_Pro4web/src/heatmap/reconstruct.py` |
  | N3 | `Delta_Engine_Pro4web/tests/heatmap/__init__.py` |
  | N4 | `Delta_Engine_Pro4web/tests/heatmap/test_reconstruct.py` |
  | N5 | `Delta_Engine_Pro4web/tests/heatmap/fixtures/real_validation/` JSONL 2件＋manifest 2件 |
  | N6 | `ArchitectureRepository/00_Master/HEATMAP/tools_p21/reconstruct_check.py` |
  | N7 | `Delta_Engine_Pro4web/tests/heatmap/fixtures/make_real_fixture.py` |

- 固定同期契約:
  - `DepthSyncCoordinator`がverifiedを返したsnapshot＋diffsだけをbookへ適用
  - `apply(SNAPSHOT)`→`apply_initial_sync(snapshot_u)`→verified bridge以降のdiff到着順
  - lenient分岐はverified bridge専用
  - gap後はrecorded BOOK_RESYNC snapshotで再検証されるまでstateを出力しない
- Decimal／入力契約:
  - 板価格・数量はdecimal stringからDecimalへのみ変換
  - float混入は即時`DepthSyncInputError`
  - tradeは明示counter付きでskip
  - manifest不一致は`SegmentIntegrityError`
- fixture契約:
  - depthSnapshot 1、depthUpdate 136、trade先頭5
  - 元2segmentのfilename／SHA-256を各`_fixture_provenance`へ記録
  - 生成script再実行前後で全fixture hash一致
- テスト:
  - Phase 2-1対象: **10 passed**
  - 全体: **737 passed, 1 skipped, 1 failed**
  - failは開始前から存在する既知UI selector 1件のみ
  - Phase 2-1新規fail 0
- 34segment manual CLI:
  - integrity PASS／segment 34／skip 0
  - SNAPSHOT_APPLIED 1／DIFF_APPLIED 2,938
  - GAP_DETECTED 0／SYNC_FAILED 0
  - final last_update_id `11165441170516`
- 非変更境界:
  - ライブ接続、描画、ダウンサンプリング、ライブpipeline組込み、約定bubbleを実装していない
  - Flow Price Response、3段チャート、既存orderbook／depth_sync／recorderを変更していない
  - `git add / commit / stash / checkout`未実行
  - 既存file変更は最終提出時のCompletionLog.md追記だけを承認済み例外とする
- 既知worktree境界:
  - Task 0時点tracked差分16件をpatch／statusで保全
  - 後続Hook作業による`Delta_Engine_Pro4web/config/hook_thresholds.yaml`のtracked差分1件を確認
  - 同fileを含むPhase 2-1対象外差分は変更・package対象にしない
- package境界:
  - 本報告書確定後にpayload SHA-256 inventoryを生成する
  - ZIP直前status監査を通過した場合だけ明示payloadをpackageする
  - inventory自身と最終ZIPのSHA-256は自己参照を避け、外部最終監査およびチャットで報告する
- blocker: なし
- 次の再開位置: inventoryを確定し、ZIP直前status監査を行う
