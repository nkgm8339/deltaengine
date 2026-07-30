# [完了] Phase 2-0-d-2 manifest_録画検証

- 完了時刻: 2026-07-30 04:43:18 +09:00
- 承認範囲: manifest V2、`DEPTH_HISTORY_MAX_BYTES`配線、fixtureテスト、承認済み300秒検証録画、実データverify
- 完了: 実装、80件の対象テスト、float静的検査、300.276712秒の手動録画、34セグメント/33境界の実データverify、manifest突き合わせ、環境復帰確認
- 未完了: なし
- blocker: なし
- ライブ接続: 承認済み手動確認タスクとして1回実施。常時記録は有効化していない

## 1. 変更・新規ファイル

### 変更

1. `Delta_Engine_Pro4web/src/acquisition/depth_history_recorder.py`
2. `Delta_Engine_Pro4web/src/pipeline.py`
3. `Delta_Engine_Pro4web/tests/acquisition/test_depth_history_recorder.py`
4. `Delta_Engine_Pro4web/tests/test_live_pipeline.py`

### 新規

1. `ArchitectureRepository/00_Master/HEATMAP/Phase_2-0-d-2_manifest_録画検証報告.md`（本checkpoint）

### 変更していないもの

- `src/acquisition/depth_sync.py`
- `src/orderflow/orderbook.py`
- Replay pipeline
- `webapp/main.py`
- `docker-compose.yml`
- `webapp/static/index.html`
- `tests/webapp/test_book_update.py`

## 2. manifest V2 実装

### 2.1 schema

- V1/V2 loader: `src/acquisition/depth_history_recorder.py:85`
- recorder: 同:103
- coordinator action受け口: 同:173
- manifest生成: 同:242
- `schema_version`: 同:251
- `sync_events` / `sync_failures`: 同:260-261

V2 manifestは既存フィールドを維持し、次を追加する。

```json
{
  "schema_version": 2,
  "schema_revision": "RAW_DEPTH_HISTORY_V2",
  "sync_events": [],
  "sync_failures": []
}
```

verified actionは次の形に変換する。

```json
{
  "epoch": 1,
  "reason": "INITIAL_BOOK_SYNC",
  "snapshot_u": 99,
  "bridge_U": 100,
  "bridge_u": 105,
  "sync_verified": true,
  "attempts": 1
}
```

`SYNC_FAILED`は`sync_events`へ入れず、次の形で`sync_failures`へ入れる。

```json
{
  "epoch": 1,
  "reason": "INITIAL_BOOK_SYNC",
  "failure_reason": "...",
  "attempts": 1
}
```

reasonは承認どおり、epoch 1を`INITIAL_BOOK_SYNC`、epoch 2以降を
`BOOK_RESYNC`として構築する。`depth_sync.py`の返却契約は変更していない。

ID、epoch、attemptsはboolを除く整数として検証する。verified entryの
`sync_verified`はtrueだけであり、false entryは作らない。

### 2.2 V1後方互換

`load_depth_history_manifest()`は`schema_version`欠落をV1として読み、
in-memory結果へ`schema_version: 1`を補う。V1の既存フィールドは変更しない。
対応版は1と2だけを受け付ける。

### 2.3 rotationとmetadata帰属

閾値到達後、現在レコードを含むセグメントを「rotation due」とし、物理closeを
次レコード直前まで遅延する。JSONLのレコード境界は旧実装と同じである。
session終了時にrotation dueなら`closed_reason="rotate"`で確定する。

これにより、snapshot/bridge検証直後の`DepthSyncAction`を、閾値到達済みでも
open中のセグメントmanifestへ格納できる。metadataはepoch/resultごとに
session内で重複排除する。

### 2.4 forwarding

- `SafeRecorder.record_sync_action()`: `depth_history_recorder.py:300`
- `RecorderTee.record_sync_action()`: 同:341
- `_RecorderFanout.record_sync_action()`: `src/pipeline.py:140`
- Live action処理: `src/pipeline.py:1601`

pipelineでは:

1. verified action: strict batchの板apply成功後にだけrecorderへ通知。
2. `SYNC_FAILED`: 失敗確定時にrecorderへ通知。
3. verified batch apply自体が失敗: coordinatorのfailed actionを記録。
4. snapshot候補処理例外: failed actionを同じ経路へ渡す。

snapshot fetch taskやcoordinatorへ板state/manifest所有を追加していない。

## 3. `DEPTH_HISTORY_MAX_BYTES` 配線

- 優先順位処理: `depth_history_recorder.py:60`
- environment文字列parser: 同:74
- constructor適用: 同:109-116

優先順位:

```text
明示constructor整数
  > DEPTH_HISTORY_MAX_BYTES
  > 64 * 1024 * 1024
```

- 明示値はboolを除く正整数だけ。
- environment値はstrip後の10進正整数文字列だけ。
- `0`、負値、`1.5`、空文字、boolを拒否する。
- `float()`は使用しない。
- WebAppは従来どおりmax_bytes未指定でconstructorを呼ぶため、保護対象
  `webapp/main.py`を変更せず環境変数が有効になる。
- `docker-compose.yml`の恒久設定は変更していない。

## 4. 追加・更新テスト

### 指示書 §5 対応

| 検証項目 | テスト |
|---|---|
| 1. V2 sync_events | `test_manifest_v2_contains_verified_sync_event_from_coordinator` |
| 複数epoch | `test_manifest_v2_records_initial_and_book_resync_epochs` |
| 2. V1後方互換 | `test_manifest_v1_without_schema_version_loads_backward_compatibly` |
| 3. verified/failure分離 | `test_sync_failed_enters_failures_not_verified_events` |
| 4. 正整数max_bytes rotation | `test_explicit_max_bytes_overrides_environment_and_rotates`、`test_environment_max_bytes_is_used_when_constructor_is_unspecified` |
| default維持 | `test_unset_max_bytes_keeps_64_mib_default` |
| 5. invalid拒否 | `test_explicit_max_bytes_rejects_non_positive_or_float`、`test_environment_max_bytes_parser_rejects_invalid_values` |
| 6. float不在 | `test_manifest_v2_contains_no_float_values` |

### 承認済み追加検証

| 検証 | テスト |
|---|---|
| rotation時metadata欠落なし | `test_rotation_keeps_sync_metadata_on_threshold_segment` |
| SafeRecorder forwarding | `test_safe_recorder_forwards_sync_action` |
| RecorderTee forwarding | `test_tee_forwards_sync_action_only_to_capable_taps` |
| pipeline verified転送 | `test_live_depth_fetch_starts_after_raw_buffer_and_applies_verified_batch`更新 |
| pipeline failed転送 | `test_live_depth_attempt_limit_is_fail_closed_while_trade_path_continues`更新 |

## 5. テスト結果

### compile

```text
python -m py_compile src/acquisition/depth_history_recorder.py src/pipeline.py tests/acquisition/test_depth_history_recorder.py tests/test_live_pipeline.py
```

結果: exit 0。

### recorder最終

```text
python -m pytest -q -p no:cacheprovider tests/acquisition/test_depth_history_recorder.py
...........................                                              [100%]
27 passed in 0.32s
```

### d-1同期系・acquisition周辺を含む対象回帰

```text
python -m pytest -q -p no:cacheprovider tests/acquisition/test_depth_history_recorder.py tests/acquisition/test_depth_sync.py tests/test_book_resync.py tests/test_live_pipeline.py tests/acquisition/test_acquisition.py tests/acquisition/test_binance_rest.py
........................................................................ [ 90%]
........                                                                 [100%]
80 passed in 5.55s
```

途中結果:

- recorder初回: 24 passed
- Live strict対象: 2 passed, 16 deselected
- recorder追加後: 25 passed
- 対象回帰途中: 78 passed
- recorder最終: 27 passed
- 対象回帰最終: 80 passed

失敗コマンド: なし。

全体pytestの既知Phase 5 UI failureは、本指示書で同一失敗を再発させないため再実行していない。

## 6. float混入チェック

変更追加行に対しbuiltin `float(`を検査した。

```text
NO_ADDED_FLOAT_CALLS
```

fixture manifestの全leafを再帰走査し、float型0件を確認した。

## 7. 保護差分確認

checkpoint時点の既存差分:

```text
docker-compose.yml                 +1 / -0
tests/webapp/test_book_update.py +117 / -0
webapp/main.py                    +13 / -2
webapp/static/index.html         +105 / -10
```

本作業の`apply_patch`対象には一度も含めていない。
`depth_sync.py`、`orderbook.py`、Replayも変更していない。

## 8. 実行コマンドと結果

1. `rg`でDepthHistoryRecorder、DEPTH_HISTORY、manifest、max_bytes、pipeline経路を検索 — 成功。
2. recorder、recorder tests、webapp生成箇所、pipeline d-1経路を`Get-Content` — 成功。
3. Phase 2-0-c報告、`verify_depth_history.py`、`depth_sync.py`をread-only確認 — 成功。
4. compose、start.ps1、config、live_capture/live_verifyをread-only確認 — 成功。
5. 対象/保護ファイルの`git status`、`git diff --numstat` — 成功。
6. 承認後の全編集 — `apply_patch`直接適用が全件成功。patch fallback不要。
7. `python -m py_compile ...` — 成功。
8. recorder pytest各段階 — 24、25、27 passed。
9. Live strict `-k live_depth` — 2 passed, 16 deselected。
10. 対象回帰各段階 — 78、80 passed。
11. `git diff --check` — exit 0。LF→CRLF warningのみ。
12. added `float()`静的検査 — 0件。
13. 行番号・最終status・保護差分再監査 — 成功。
14. 録画承認後の報告書§9・start.ps1・Web lifespan・LivePipeline run/cleanup・verify CLI再確認 — 成功。
    最初の`rg`に渡したWindows wildcard path 1件だけが`os error 123`となったが、同一コマンドは再試行せず、
    `rg --files`を使う別コマンドで対象fileを確認した。
15. timestamp付き検証専用directory生成 — 成功。既存記録は変更していない。
16. process限定環境による300秒ライブ録画 — exit 0、300.276712秒、28084行、34セグメント。
17. 録画用環境変数解除とcompose `DEPTH_HISTORY_ENABLED=false`確認 — 成功。
18. `verify_depth_history.py` — exit 0、snapshot 1/1 PASS、境界33/33 PASS、chain mismatch 0、float 0。
19. PowerShell manifest集約 — `bridge_U` / `bridge_u`のcase衝突で失敗。再試行せずPythonへ切替。
20. Python manifest集約初版 — manifestに`segment`フィールドがないため`KeyError: 'segment'`で失敗。
    同一コマンドは再試行せず、対応するJSONL filenameを使う別コマンドへ切替。
21. Python集約修正版 — 成功。34 manifest、28084 record、sync event 1、sync failure 0。
22. 同期突き合わせ初版 — snapshot IDを`lastUpdateId`固定で探した補助コマンドの仮定誤りにより
    location未検出。生行を確認後、verifierと同じ`u` fallback規則を使う別コマンドで全項目PASS。
23. manifest全件SHA-256・byte・行数・float監査 — 全件PASS。
24. 報告書内verifier転記行数、fresh processの環境、compose、保護差分、`git diff --check`最終監査 — 成功。

## 9. 検証録画（承認後に追記）

### 9.0 長時間処理開始前checkpoint

- checkpoint時刻: 2026-07-30 04:30:59 +09:00
- 録画承認: 2026-07-30付「Phase 2-0-d-2 検証録画の承認」を受領済み。
- 承認範囲: process限定の300秒ライブ録画、専用データ領域への出力、録画後のread-only検証。
- 完了済み: manifest V2、V1 loader、max_bytes配線、forwarding、fixtureテスト、静的監査、録画起動経路確認。
- 未完了: 300秒録画、環境復帰確認、実データverify、manifest実測突き合わせ。
- 変更file: 実装4fileと本報告書。録画データは下記の新規専用directoryにのみ生成する。
- fixture検証結果: 80 passed、added `float()` 0件。
- blocker: なし。
- 次の再開位置: `LivePipeline.run(duration_sec=300, raw_recorder=...)`を起動し、終了後に環境変数を解除する。

検証専用パス:

- root: `Delta_Engine_Pro4web/data_05M/phase2_0_d2_validation/20260730T043059/`
- raw depth: 同 `depth_history_raw/`
- Parquet: 同 `parquet/`
- DuckDB: 同 `duckdb/orderflow_validation.duckdb`

予定条件:

- `DEPTH_HISTORY_ENABLED=true`（録画process限定）
- `DEPTH_HISTORY_MAX_BYTES=524288`
- 時間: 300秒
- 保存先: 既存記録と分離したtimestamp付き新規directory
- Parquet/DuckDB: 検証専用directory
- pytestからは呼ばない

録画後:

1. process限定環境変数を解除。
2. composeの`DEPTH_HISTORY_ENABLED=false`が不変であることを確認。
3. `verify_depth_history.py`を実行。
4. 出力全文、manifest V2現物、実測照合を本節へ追記。

FAIL停止条件:

- SNAPSHOT_CONNECTIONにFAILが1件でもある。
- SEGMENT_BOUNDARYにFAILが1件でもある。
- DEPTH_UPDATE_CHAIN_MISMATCH_COUNTが0以外。
- FLOAT_NUMBER_LINE_COUNTが0以外。

BOOK_RESYNCが0件であることはFAILにしない。

### 9.1 実施条件と録画結果

- 実施方式: pytestではなく、`LivePipeline.run(duration_sec=300, raw_recorder=...)`を手動実行。
- process限定環境:
  - `DEPTH_HISTORY_ENABLED=true`
  - `DEPTH_HISTORY_MAX_BYTES=524288`
  - `DEPTH_HISTORY_ROOT=C:\Users\user\Desktop\DeltaEngine05M\Delta_Engine_Pro4web\data_05M\phase2_0_d2_validation\20260730T043059\depth_history_raw`
- Parquet: `C:\Users\user\Desktop\DeltaEngine05M\Delta_Engine_Pro4web\data_05M\phase2_0_d2_validation\20260730T043059\parquet`
- DuckDB: `C:\Users\user\Desktop\DeltaEngine05M\Delta_Engine_Pro4web\data_05M\phase2_0_d2_validation\20260730T043059\duckdb\orderflow_validation.duckdb`
- raw recorder開始: `20260729T193154.046959Z`
- raw recorder終了: `20260729T193654.323671Z`
- manifest時刻による実時間: 300.276712秒
- max bytes: 524288
- セグメント数: 34
- rotation境界数: 33
- 総行数: 28084
- JSONL総byte数: 17532117

録画コマンドの要点:

```powershell
$env:DEPTH_HISTORY_ENABLED='true'
$env:DEPTH_HISTORY_MAX_BYTES='524288'
$env:DEPTH_HISTORY_ROOT='<validation-root>\depth_history_raw'
$env:P20D2_PARQUET_ROOT='<validation-root>\parquet'
$env:P20D2_DUCKDB_PATH='<validation-root>\duckdb\orderflow_validation.duckdb'

# proxy環境変数を録画process内だけ解除
# config/profileを読込み、専用Parquet/DuckDBを指定してLivePipelineを構築
# SafeRecorder(DepthHistoryRecorder(DEPTH_HISTORY_ROOT, symbol))をraw_recorderへ渡す
python -c "<inline Python: pipeline.run(duration_sec=300, raw_recorder=raw_recorder)>"

# finallyで上記録画用環境変数をすべて解除
```

録画結果:

```text
P20D2_CAPTURE_START duration_sec=300 max_bytes=524288
P20D2_DEPTH_ROOT=C:\Users\user\Desktop\DeltaEngine05M\Delta_Engine_Pro4web\data_05M\phase2_0_d2_validation\20260730T043059\depth_history_raw
P20D2_PARQUET_ROOT=C:\Users\user\Desktop\DeltaEngine05M\Delta_Engine_Pro4web\data_05M\phase2_0_d2_validation\20260730T043059\parquet
P20D2_DUCKDB_PATH=C:\Users\user\Desktop\DeltaEngine05M\Delta_Engine_Pro4web\data_05M\phase2_0_d2_validation\20260730T043059\duckdb\orderflow_validation.duckdb
P20D2_CAPTURE_COMPLETE
raw_out=28084
forwarded=28083
filtered=1
normalized=25117
reconnects=0
recorded=0
book_snapshots_applied=1
book_diffs_applied=2938
book_diffs_rejected_before_snapshot=0
book_gaps_detected=0
depth_processed=2939
depth_rejected=0
trades_stored=25117
candles_stored=6
P20D2_ENV_CLEARED enabled= max_bytes= root=
```

`recorded=0`はlegacy `record_path` recorderの統計であり、独立したraw recorderの失敗を意味しない。
raw recorderの現物は28084行・34セグメント生成されている。
録画中に購読ack 1件の`E2003`と、depth以外のnormalizationで`E3001` warningが27件出た。
depth側は`depth_rejected=0`、検証対象のraw記録・同期・境界には欠落を生じていない。

### 9.2 環境復帰

録画コマンドの`finally`と、終了後の独立したPowerShell processの両方で確認した。

```text
{"DEPTH_HISTORY_ENABLED":null,"DEPTH_HISTORY_MAX_BYTES":null,"DEPTH_HISTORY_ROOT":null}
docker-compose.yml:29:      - DEPTH_HISTORY_ENABLED=false
```

常時記録の恒久有効化は行っていない。composeも変更していない。

### 9.3 `verify_depth_history.py` 出力全文

実行コマンド:

```powershell
python ArchitectureRepository\00_Master\HEATMAP\tools_p20b\verify_depth_history.py `
  Delta_Engine_Pro4web\data_05M\phase2_0_d2_validation\20260730T043059\depth_history_raw\symbol=BTCUSDT
```

出力全文:

```text
PHASE_2_0_B_DEPTH_HISTORY_VERIFICATION
DATA_DIR: C:\Users\user\Desktop\DeltaEngine05M\Delta_Engine_Pro4web\data_05M\phase2_0_d2_validation\20260730T043059\depth_history_raw\symbol=BTCUSDT
SEGMENT_COUNT: 34
SEGMENT: raw_depth.20260729T193154.046959Z.jsonl bytes=527899 lines=813
SEGMENT: raw_depth.20260729T193201.309417Z.jsonl bytes=535833 lines=1019
SEGMENT: raw_depth.20260729T193207.936510Z.jsonl bytes=525583 lines=711
SEGMENT: raw_depth.20260729T193215.790120Z.jsonl bytes=531770 lines=760
SEGMENT: raw_depth.20260729T193226.297145Z.jsonl bytes=524355 lines=707
SEGMENT: raw_depth.20260729T193235.259351Z.jsonl bytes=525172 lines=794
SEGMENT: raw_depth.20260729T193243.737595Z.jsonl bytes=524330 lines=794
SEGMENT: raw_depth.20260729T193255.493715Z.jsonl bytes=525048 lines=885
SEGMENT: raw_depth.20260729T193303.935062Z.jsonl bytes=537066 lines=940
SEGMENT: raw_depth.20260729T193313.208341Z.jsonl bytes=527482 lines=1029
SEGMENT: raw_depth.20260729T193319.564627Z.jsonl bytes=534873 lines=811
SEGMENT: raw_depth.20260729T193327.357648Z.jsonl bytes=532621 lines=1268
SEGMENT: raw_depth.20260729T193330.818457Z.jsonl bytes=525313 lines=753
SEGMENT: raw_depth.20260729T193341.396258Z.jsonl bytes=524369 lines=869
SEGMENT: raw_depth.20260729T193351.301390Z.jsonl bytes=530161 lines=888
SEGMENT: raw_depth.20260729T193359.580460Z.jsonl bytes=524398 lines=1124
SEGMENT: raw_depth.20260729T193405.999303Z.jsonl bytes=545355 lines=979
SEGMENT: raw_depth.20260729T193410.656550Z.jsonl bytes=526874 lines=916
SEGMENT: raw_depth.20260729T193417.604225Z.jsonl bytes=524382 lines=1160
SEGMENT: raw_depth.20260729T193424.030018Z.jsonl bytes=527085 lines=837
SEGMENT: raw_depth.20260729T193431.811899Z.jsonl bytes=525329 lines=823
SEGMENT: raw_depth.20260729T193440.224873Z.jsonl bytes=524567 lines=685
SEGMENT: raw_depth.20260729T193451.435394Z.jsonl bytes=525215 lines=813
SEGMENT: raw_depth.20260729T193501.543033Z.jsonl bytes=527858 lines=702
SEGMENT: raw_depth.20260729T193512.150766Z.jsonl bytes=524774 lines=670
SEGMENT: raw_depth.20260729T193522.699724Z.jsonl bytes=536309 lines=727
SEGMENT: raw_depth.20260729T193534.949801Z.jsonl bytes=524857 lines=700
SEGMENT: raw_depth.20260729T193549.278358Z.jsonl bytes=526328 lines=750
SEGMENT: raw_depth.20260729T193602.913092Z.jsonl bytes=544913 lines=758
SEGMENT: raw_depth.20260729T193615.710341Z.jsonl bytes=529825 lines=843
SEGMENT: raw_depth.20260729T193623.912893Z.jsonl bytes=526325 lines=850
SEGMENT: raw_depth.20260729T193630.783699Z.jsonl bytes=526978 lines=777
SEGMENT: raw_depth.20260729T193639.671392Z.jsonl bytes=526097 lines=770
SEGMENT: raw_depth.20260729T193652.336710Z.jsonl bytes=82773 lines=159
JSON_ERROR_COUNT: 0
DEPTH_UPDATE_COUNT: 2939
DEPTH_UPDATE_ADJACENT_PAIR_COUNT: 2938
DEPTH_UPDATE_CHAIN_MISMATCH_COUNT: 0
SNAPSHOT_COUNT: 1
SNAPSHOT_CONNECTION: snapshot=raw_depth.20260729T193154.046959Z.jsonl:2 snapshot_u=11165393552876 capture_reason='INITIAL_BOOK_SYNC' next_depth_update=raw_depth.20260729T193154.046959Z.jsonl:3 next_U=11165393550921 next_u=11165393566438 target=11165393552877 result=PASS
SEGMENT_BOUNDARY_COUNT: 33
SEGMENT_BOUNDARY: previous_segment=raw_depth.20260729T193154.046959Z.jsonl next_segment=raw_depth.20260729T193201.309417Z.jsonl previous_depth_update=raw_depth.20260729T193154.046959Z.jsonl:813 previous_u=11165394691547 next_depth_update=raw_depth.20260729T193201.309417Z.jsonl:64 next_pu=11165394691547 snapshot_before_next_update=false result=PASS
SEGMENT_BOUNDARY: previous_segment=raw_depth.20260729T193201.309417Z.jsonl next_segment=raw_depth.20260729T193207.936510Z.jsonl previous_depth_update=raw_depth.20260729T193201.309417Z.jsonl:1019 previous_u=11165395982872 next_depth_update=raw_depth.20260729T193207.936510Z.jsonl:1 next_pu=11165395982872 snapshot_before_next_update=false result=PASS
SEGMENT_BOUNDARY: previous_segment=raw_depth.20260729T193207.936510Z.jsonl next_segment=raw_depth.20260729T193215.790120Z.jsonl previous_depth_update=raw_depth.20260729T193207.936510Z.jsonl:711 previous_u=11165397443056 next_depth_update=raw_depth.20260729T193215.790120Z.jsonl:1 next_pu=11165397443056 snapshot_before_next_update=false result=PASS
SEGMENT_BOUNDARY: previous_segment=raw_depth.20260729T193215.790120Z.jsonl next_segment=raw_depth.20260729T193226.297145Z.jsonl previous_depth_update=raw_depth.20260729T193215.790120Z.jsonl:760 previous_u=11165399047943 next_depth_update=raw_depth.20260729T193226.297145Z.jsonl:1 next_pu=11165399047943 snapshot_before_next_update=false result=PASS
SEGMENT_BOUNDARY: previous_segment=raw_depth.20260729T193226.297145Z.jsonl next_segment=raw_depth.20260729T193235.259351Z.jsonl previous_depth_update=raw_depth.20260729T193226.297145Z.jsonl:635 previous_u=11165400375981 next_depth_update=raw_depth.20260729T193235.259351Z.jsonl:27 next_pu=11165400375981 snapshot_before_next_update=false result=PASS
SEGMENT_BOUNDARY: previous_segment=raw_depth.20260729T193235.259351Z.jsonl next_segment=raw_depth.20260729T193243.737595Z.jsonl previous_depth_update=raw_depth.20260729T193235.259351Z.jsonl:794 previous_u=11165401506766 next_depth_update=raw_depth.20260729T193243.737595Z.jsonl:1 next_pu=11165401506766 snapshot_before_next_update=false result=PASS
SEGMENT_BOUNDARY: previous_segment=raw_depth.20260729T193243.737595Z.jsonl next_segment=raw_depth.20260729T193255.493715Z.jsonl previous_depth_update=raw_depth.20260729T193243.737595Z.jsonl:789 previous_u=11165402857809 next_depth_update=raw_depth.20260729T193255.493715Z.jsonl:10 next_pu=11165402857809 snapshot_before_next_update=false result=PASS
SEGMENT_BOUNDARY: previous_segment=raw_depth.20260729T193255.493715Z.jsonl next_segment=raw_depth.20260729T193303.935062Z.jsonl previous_depth_update=raw_depth.20260729T193255.493715Z.jsonl:885 previous_u=11165404132166 next_depth_update=raw_depth.20260729T193303.935062Z.jsonl:1 next_pu=11165404132166 snapshot_before_next_update=false result=PASS
SEGMENT_BOUNDARY: previous_segment=raw_depth.20260729T193303.935062Z.jsonl next_segment=raw_depth.20260729T193313.208341Z.jsonl previous_depth_update=raw_depth.20260729T193303.935062Z.jsonl:940 previous_u=11165405863026 next_depth_update=raw_depth.20260729T193313.208341Z.jsonl:1 next_pu=11165405863026 snapshot_before_next_update=false result=PASS
SEGMENT_BOUNDARY: previous_segment=raw_depth.20260729T193313.208341Z.jsonl next_segment=raw_depth.20260729T193319.564627Z.jsonl previous_depth_update=raw_depth.20260729T193313.208341Z.jsonl:1029 previous_u=11165407071671 next_depth_update=raw_depth.20260729T193319.564627Z.jsonl:1 next_pu=11165407071671 snapshot_before_next_update=false result=PASS
SEGMENT_BOUNDARY: previous_segment=raw_depth.20260729T193319.564627Z.jsonl next_segment=raw_depth.20260729T193327.357648Z.jsonl previous_depth_update=raw_depth.20260729T193319.564627Z.jsonl:811 previous_u=11165408815132 next_depth_update=raw_depth.20260729T193327.357648Z.jsonl:7 next_pu=11165408815132 snapshot_before_next_update=false result=PASS
SEGMENT_BOUNDARY: previous_segment=raw_depth.20260729T193327.357648Z.jsonl next_segment=raw_depth.20260729T193330.818457Z.jsonl previous_depth_update=raw_depth.20260729T193327.357648Z.jsonl:1268 previous_u=11165409688274 next_depth_update=raw_depth.20260729T193330.818457Z.jsonl:42 next_pu=11165409688274 snapshot_before_next_update=false result=PASS
SEGMENT_BOUNDARY: previous_segment=raw_depth.20260729T193330.818457Z.jsonl next_segment=raw_depth.20260729T193341.396258Z.jsonl previous_depth_update=raw_depth.20260729T193330.818457Z.jsonl:753 previous_u=11165411132399 next_depth_update=raw_depth.20260729T193341.396258Z.jsonl:32 next_pu=11165411132399 snapshot_before_next_update=false result=PASS
SEGMENT_BOUNDARY: previous_segment=raw_depth.20260729T193341.396258Z.jsonl next_segment=raw_depth.20260729T193351.301390Z.jsonl previous_depth_update=raw_depth.20260729T193341.396258Z.jsonl:753 previous_u=11165412398675 next_depth_update=raw_depth.20260729T193351.301390Z.jsonl:18 next_pu=11165412398675 snapshot_before_next_update=false result=PASS
SEGMENT_BOUNDARY: previous_segment=raw_depth.20260729T193351.301390Z.jsonl next_segment=raw_depth.20260729T193359.580460Z.jsonl previous_depth_update=raw_depth.20260729T193351.301390Z.jsonl:888 previous_u=11165413415601 next_depth_update=raw_depth.20260729T193359.580460Z.jsonl:6 next_pu=11165413415601 snapshot_before_next_update=false result=PASS
SEGMENT_BOUNDARY: previous_segment=raw_depth.20260729T193359.580460Z.jsonl next_segment=raw_depth.20260729T193405.999303Z.jsonl previous_depth_update=raw_depth.20260729T193359.580460Z.jsonl:1009 previous_u=11165415017450 next_depth_update=raw_depth.20260729T193405.999303Z.jsonl:31 next_pu=11165415017450 snapshot_before_next_update=false result=PASS
SEGMENT_BOUNDARY: previous_segment=raw_depth.20260729T193405.999303Z.jsonl next_segment=raw_depth.20260729T193410.656550Z.jsonl previous_depth_update=raw_depth.20260729T193405.999303Z.jsonl:979 previous_u=11165416276089 next_depth_update=raw_depth.20260729T193410.656550Z.jsonl:11 next_pu=11165416276089 snapshot_before_next_update=false result=PASS
SEGMENT_BOUNDARY: previous_segment=raw_depth.20260729T193410.656550Z.jsonl next_segment=raw_depth.20260729T193417.604225Z.jsonl previous_depth_update=raw_depth.20260729T193410.656550Z.jsonl:916 previous_u=11165417625599 next_depth_update=raw_depth.20260729T193417.604225Z.jsonl:3 next_pu=11165417625599 snapshot_before_next_update=false result=PASS
SEGMENT_BOUNDARY: previous_segment=raw_depth.20260729T193417.604225Z.jsonl next_segment=raw_depth.20260729T193424.030018Z.jsonl previous_depth_update=raw_depth.20260729T193417.604225Z.jsonl:1157 previous_u=11165418818621 next_depth_update=raw_depth.20260729T193424.030018Z.jsonl:12 next_pu=11165418818621 snapshot_before_next_update=false result=PASS
SEGMENT_BOUNDARY: previous_segment=raw_depth.20260729T193424.030018Z.jsonl next_segment=raw_depth.20260729T193431.811899Z.jsonl previous_depth_update=raw_depth.20260729T193424.030018Z.jsonl:837 previous_u=11165420201078 next_depth_update=raw_depth.20260729T193431.811899Z.jsonl:81 next_pu=11165420201078 snapshot_before_next_update=false result=PASS
SEGMENT_BOUNDARY: previous_segment=raw_depth.20260729T193431.811899Z.jsonl next_segment=raw_depth.20260729T193440.224873Z.jsonl previous_depth_update=raw_depth.20260729T193431.811899Z.jsonl:823 previous_u=11165421529548 next_depth_update=raw_depth.20260729T193440.224873Z.jsonl:1 next_pu=11165421529548 snapshot_before_next_update=false result=PASS
SEGMENT_BOUNDARY: previous_segment=raw_depth.20260729T193440.224873Z.jsonl next_segment=raw_depth.20260729T193451.435394Z.jsonl previous_depth_update=raw_depth.20260729T193440.224873Z.jsonl:685 previous_u=11165422863577 next_depth_update=raw_depth.20260729T193451.435394Z.jsonl:1 next_pu=11165422863577 snapshot_before_next_update=false result=PASS
SEGMENT_BOUNDARY: previous_segment=raw_depth.20260729T193451.435394Z.jsonl next_segment=raw_depth.20260729T193501.543033Z.jsonl previous_depth_update=raw_depth.20260729T193451.435394Z.jsonl:813 previous_u=11165424254683 next_depth_update=raw_depth.20260729T193501.543033Z.jsonl:1 next_pu=11165424254683 snapshot_before_next_update=false result=PASS
SEGMENT_BOUNDARY: previous_segment=raw_depth.20260729T193501.543033Z.jsonl next_segment=raw_depth.20260729T193512.150766Z.jsonl previous_depth_update=raw_depth.20260729T193501.543033Z.jsonl:702 previous_u=11165426133363 next_depth_update=raw_depth.20260729T193512.150766Z.jsonl:1 next_pu=11165426133363 snapshot_before_next_update=false result=PASS
SEGMENT_BOUNDARY: previous_segment=raw_depth.20260729T193512.150766Z.jsonl next_segment=raw_depth.20260729T193522.699724Z.jsonl previous_depth_update=raw_depth.20260729T193512.150766Z.jsonl:670 previous_u=11165427959104 next_depth_update=raw_depth.20260729T193522.699724Z.jsonl:5 next_pu=11165427959104 snapshot_before_next_update=false result=PASS
SEGMENT_BOUNDARY: previous_segment=raw_depth.20260729T193522.699724Z.jsonl next_segment=raw_depth.20260729T193534.949801Z.jsonl previous_depth_update=raw_depth.20260729T193522.699724Z.jsonl:727 previous_u=11165429638399 next_depth_update=raw_depth.20260729T193534.949801Z.jsonl:13 next_pu=11165429638399 snapshot_before_next_update=false result=PASS
SEGMENT_BOUNDARY: previous_segment=raw_depth.20260729T193534.949801Z.jsonl next_segment=raw_depth.20260729T193549.278358Z.jsonl previous_depth_update=raw_depth.20260729T193534.949801Z.jsonl:700 previous_u=11165431324990 next_depth_update=raw_depth.20260729T193549.278358Z.jsonl:1 next_pu=11165431324990 snapshot_before_next_update=false result=PASS
SEGMENT_BOUNDARY: previous_segment=raw_depth.20260729T193549.278358Z.jsonl next_segment=raw_depth.20260729T193602.913092Z.jsonl previous_depth_update=raw_depth.20260729T193549.278358Z.jsonl:750 previous_u=11165433314623 next_depth_update=raw_depth.20260729T193602.913092Z.jsonl:1 next_pu=11165433314623 snapshot_before_next_update=false result=PASS
SEGMENT_BOUNDARY: previous_segment=raw_depth.20260729T193602.913092Z.jsonl next_segment=raw_depth.20260729T193615.710341Z.jsonl previous_depth_update=raw_depth.20260729T193602.913092Z.jsonl:758 previous_u=11165435463604 next_depth_update=raw_depth.20260729T193615.710341Z.jsonl:70 next_pu=11165435463604 snapshot_before_next_update=false result=PASS
SEGMENT_BOUNDARY: previous_segment=raw_depth.20260729T193615.710341Z.jsonl next_segment=raw_depth.20260729T193623.912893Z.jsonl previous_depth_update=raw_depth.20260729T193615.710341Z.jsonl:843 previous_u=11165436889130 next_depth_update=raw_depth.20260729T193623.912893Z.jsonl:2 next_pu=11165436889130 snapshot_before_next_update=false result=PASS
SEGMENT_BOUNDARY: previous_segment=raw_depth.20260729T193623.912893Z.jsonl next_segment=raw_depth.20260729T193630.783699Z.jsonl previous_depth_update=raw_depth.20260729T193623.912893Z.jsonl:850 previous_u=11165438160044 next_depth_update=raw_depth.20260729T193630.783699Z.jsonl:1 next_pu=11165438160044 snapshot_before_next_update=false result=PASS
SEGMENT_BOUNDARY: previous_segment=raw_depth.20260729T193630.783699Z.jsonl next_segment=raw_depth.20260729T193639.671392Z.jsonl previous_depth_update=raw_depth.20260729T193630.783699Z.jsonl:777 previous_u=11165439450329 next_depth_update=raw_depth.20260729T193639.671392Z.jsonl:1 next_pu=11165439450329 snapshot_before_next_update=false result=PASS
SEGMENT_BOUNDARY: previous_segment=raw_depth.20260729T193639.671392Z.jsonl next_segment=raw_depth.20260729T193652.336710Z.jsonl previous_depth_update=raw_depth.20260729T193639.671392Z.jsonl:770 previous_u=11165440960777 next_depth_update=raw_depth.20260729T193652.336710Z.jsonl:8 next_pu=11165440960777 snapshot_before_next_update=false result=PASS
FLOAT_NUMBER_LINE_COUNT: 0
RESULT: COMPLETE
```

判定:

- SNAPSHOT_CONNECTION: 1/1 PASS
- SEGMENT_BOUNDARY: 33/33 PASS
- DEPTH_UPDATE_CHAIN_MISMATCH_COUNT: 0
- FLOAT_NUMBER_LINE_COUNT: 0
- JSON_ERROR_COUNT: 0

### 9.4 manifest V2現物

全34 manifestが`schema_version: 2`。同期metadataを持つのは最初のsegment manifestだけで、
残り33 manifestの`sync_events` / `sync_failures`は空配列だった。

`sync_events`:

```json
[
  {
    "attempts": 1,
    "bridge_U": 11165393550921,
    "bridge_u": 11165393566438,
    "epoch": 1,
    "reason": "INITIAL_BOOK_SYNC",
    "snapshot_u": 11165393552876,
    "sync_verified": true
  }
]
```

`sync_failures`:

```json
[]
```

BOOK_RESYNCは0件。短時間録画でgapが発生しなかったためであり、承認済み基準により正常。

同期metadataを含むmanifest全文:

```json
{"byte_size": 527899, "closed_at": "20260729T193201.281442Z", "closed_reason": "rotate", "record_count": 813, "schema_revision": "RAW_DEPTH_HISTORY_V2", "schema_version": 2, "sha256": "58048404f36a7fcb4a2487cb87d8c9a9f95386d624c3d4bccb1c21b227747dd6", "started_at": "20260729T193154.046959Z", "symbol": "BTCUSDT", "sync_events": [{"attempts": 1, "bridge_U": 11165393550921, "bridge_u": 11165393566438, "epoch": 1, "reason": "INITIAL_BOOK_SYNC", "snapshot_u": 11165393552876, "sync_verified": true}], "sync_failures": []}
```

### 9.5 manifestと実測の突き合わせ

| epoch / reason | 項目 | manifest | verify実測 | 結果 |
|---|---|---:|---:|---|
| 1 / INITIAL_BOOK_SYNC | snapshot_u | 11165393552876 | 11165393552876 (`raw_depth.20260729T193154.046959Z.jsonl:2`) | PASS |
| 1 / INITIAL_BOOK_SYNC | bridge_U | 11165393550921 | 11165393550921 (`raw_depth.20260729T193154.046959Z.jsonl:3`) | PASS |
| 1 / INITIAL_BOOK_SYNC | bridge_u | 11165393566438 | 11165393566438 (`raw_depth.20260729T193154.046959Z.jsonl:3`) | PASS |
| 1 / INITIAL_BOOK_SYNC | sync_verified | true | strict bridge条件PASS | PASS |

機械照合出力:

```text
SYNC_EVENT_MATCH: {"manifest_segment": "raw_depth.20260729T193154.046959Z.jsonl", "epoch": 1, "reason": "INITIAL_BOOK_SYNC", "manifest_snapshot_u": 11165393552876, "manifest_bridge_U": 11165393550921, "manifest_bridge_u": 11165393566438, "manifest_sync_verified": true, "verify_snapshot_location": "raw_depth.20260729T193154.046959Z.jsonl:2", "verify_snapshot_u": 11165393552876, "verify_bridge_location": "raw_depth.20260729T193154.046959Z.jsonl:3", "verify_bridge_U": 11165393550921, "verify_bridge_u": 11165393566438, "result": "PASS"}
ALL_SYNC_EVENT_MATCH: PASS
```

### 9.6 manifest全件監査

```text
CAPTURE_STARTED_AT_UTC: 20260729T193154.046959Z
CAPTURE_CLOSED_AT_UTC: 20260729T193654.323671Z
CAPTURE_ELAPSED_SECONDS: 300.276712
SEGMENT_COUNT: 34
TOTAL_RECORD_COUNT: 28084
TOTAL_JSONL_BYTES: 17532117
MANIFEST_SCHEMA_V2_COUNT: 34
MANIFEST_BYTE_MISMATCH_COUNT: 0
MANIFEST_LINE_MISMATCH_COUNT: 0
MANIFEST_SHA256_MISMATCH_COUNT: 0
MANIFEST_FLOAT_VALUE_COUNT: 0
MANIFEST_AUDIT_RESULT: PASS
```

### 9.7 検証中の失敗コマンドと切り分け

1. 最初のread-only検索で`rg`へ渡した`Delta_Engine_Pro4web/*.py`は、
   PowerShell/Windows上のpath指定として`os error 123`になった。他の検索結果は取得済みで、
   同一コマンドは再試行せず、`rg --files`を使う別コマンドで必要fileを確認した。
2. PowerShell `ConvertFrom-Json`によるmanifest集約は、JSONキー`bridge_U`と`bridge_u`を
   case-insensitiveな同一キーとして扱うPowerShell側仕様により失敗した。同一コマンドは再試行せず、
   Python標準`json`による別コマンドへ切り替えた。manifest JSON自体は有効。
3. Python集約初版はmanifestに存在しない`segment`フィールドを参照し`KeyError: 'segment'`で失敗した。
   同一コマンドは再試行せず、対応するJSONL filenameをmanifestの所属segmentとして扱う別コマンドに切り替えた。
4. 最初のPython補助照合はsnapshot IDを`lastUpdateId`固定で検索し、
   現物snapshotが使用する`u`を見なかったため`verify_snapshot_location: null`となった。
   生データ2行目で`e="depthSnapshot", u=11165393552876`を確認し、
   verifier本体と同じ`payload.get("u", payload.get("lastUpdateId"))`規則の別コマンドで照合した結果、
   全項目PASSになった。製品データやmanifestの不一致ではなく、補助コマンドのフィールド仮定誤りである。

## 10. checkpoint / 次の再開位置

- checkpoint時刻: 2026-07-30 04:40:04 +09:00
- 承認範囲: manifest V2、max_bytes配線、fixtureテスト、承認済み300秒録画、read-only実データ検証。
- 完了済み: 実装、80件の対象回帰、300秒録画、34セグメント/33境界verify、manifest実測突き合わせ、環境復帰。
- 未完了: なし。
- 変更file: 承認済み実装4file、本報告書。検証専用データdirectoryを新規生成。
- 検証結果: snapshot 1/1 PASS、境界33/33 PASS、chain mismatch 0、JSON float 0、manifest float 0、SHA/byte/行数不一致0。
- blocker: なし。
- 次の再開位置: Phase 2-0-d-2完了。Phase 2-1指示を待つ。

## 11. 報告書保存先

`ArchitectureRepository/00_Master/HEATMAP/Phase_2-0-d-2_manifest_録画検証報告.md`
