# Stage 2C-1 コンテナ再起動 / liquidation収録再開報告
実行日時: 2026-07-30 09:30:11 JST
実行者: Codex

## 作業checkpoint（再起動前）

- checkpoint時刻: 2026-07-30 09:30:11 JST
- 承認範囲: 停止中コンテナの再起動、同一campaign `stage2a_20260726_xz`でのliquidation収録再開、read-only事後確認、本報告ファイルの出力
- 完了済み: `PROJECT_MEMORY.md`確認、適用規則確認、復旧スクリプト全文確認、compose／campaign設定確認、再起動前状態採取
- 未完了: コンテナ再起動、health GREEN確認、liquidation新session確認、full stream状態確認、事後状態確認
- 変更file: 本報告ファイルのみ
- 検証結果: `tools/windows/resume_hook_capture.ps1`は既存composeを`--no-build`で起動するスクリプト。`hook_observer.yaml`のcampaignは`stage2a_20260726_xz`
- blockerの限定範囲: なし
- 次の再開位置: `tools/windows/resume_hook_capture.ps1`を最大300秒health待機で実行

## Step 1: 事前状態の記録

実行コマンド:

```powershell
docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"
```

生出力:

```text
NAMES                                      STATUS                    IMAGE
delta_engine_pro4web-deltaengine_clone-1   Exited (0) 13 hours ago   delta_engine_pro4web-deltaengine_clone
deltaengine_clone-deltaengine_clone-1      Exited (127) 5 days ago   deltaengine_clone-deltaengine_clone
buildx_buildkit_default                    Exited (1) 3 days ago     moby/buildkit:buildx-stable-1
```

再起動前liquidation最新session:

```text
session-20260729T113656.349792Z-094697f1
```

再起動前full最新session:

```text
session-20260729T012627.280594Z-31c7f85a
```

## Step 2: コンテナ再起動

使用する既存スクリプト:

```text
Delta_Engine_Pro4web\tools\windows\resume_hook_capture.ps1
```

実行コマンド:

```powershell
powershell -ExecutionPolicy Bypass -File .\Delta_Engine_Pro4web\tools\windows\resume_hook_capture.ps1 -HealthTimeoutSec 300
```

生出力:

```text
DeltaEngine did not reach GREEN with Hook capture within 300 seconds
```

終了コード:

```text
1
```

スクリプト生成log:

```jsonl
{"schema_version":1,"event":"START","recorded_at":"2026-07-30T00:31:07.0186724Z","run_id":"20260730T003106.9206911Z-4bae420c","project_root":"C:\\Users\\user\\Desktop\\DeltaEngine05M\\Delta_Engine_Pro4web","user":"DESKTOP-K1I84LK\\user","compose_override":"C:\\Users\\user\\Desktop\\DeltaEngine05M\\Delta_Engine_Pro4web\\docker-compose.stage2b.yml"}
{"schema_version":1,"event":"DOCKER_READY","recorded_at":"2026-07-30T00:31:09.3175571Z","run_id":"20260730T003106.9206911Z-4bae420c","server_version":"29.6.1"}
{"schema_version":1,"event":"COMPOSE_STARTED","recorded_at":"2026-07-30T00:31:12.8301594Z","run_id":"20260730T003106.9206911Z-4bae420c"}
{"schema_version":1,"event":"FAILED","recorded_at":"2026-07-30T00:36:14.4388740Z","run_id":"20260730T003106.9206911Z-4bae420c","error":"DeltaEngine did not reach GREEN with Hook capture within 300 seconds","error_type":"System.Management.Automation.RuntimeException"}
```

5分待機後の生出力:

```text
2026-07-30 09:40:50 JST
NAMES                                 STATUS                          PORTS
deltaengine_05m-deltaengine_clone-1   Restarting (3) 30 seconds ago
curl: (7) Failed to connect to localhost:18080 after 2251 ms: Could not connect to server
curl: (7) Failed to connect to localhost:8080 after 2256 ms: Could not connect to server
```

`docker logs`の反復エラー（1回分）:

```text
INFO:     Started server process [1]
INFO:     Waiting for application startup.
ERROR:    Traceback (most recent call last):
  File "/usr/local/lib/python3.12/site-packages/starlette/routing.py", line 638, in lifespan
    async with self.lifespan_context(app) as maybe_state:
  File "/usr/local/lib/python3.12/contextlib.py", line 210, in __aenter__
    return await anext(self.gen)
  File "/app/webapp/main.py", line 89, in lifespan
    config = load_config(_CONFIG_PATH)
  File "/app/src/config.py", line 470, in load_config
    return _validate(raw)
  File "/app/src/config.py", line 445, in _validate
    raise ConfigValidationError(problems)
src.config.ConfigValidationError: [E1002] configuration validation failed: unknown key: 'market.tick_size'; unknown key: 'webapp.live_dom_depth_levels'; unknown key: 'webapp.book_update_interval_ms'; unknown key: 'webapp.book_stale_after_ms'; unknown key: 'webapp.tape_batch_interval_ms'; unknown key: 'webapp.tape_max_trades_per_message'; unknown key: 'webapp.tape_pending_capacity'
ERROR:    Application startup failed. Exiting.
```

image identity生出力:

```text
既存停止コンテナ:
Image=sha256:3d1d1e9fa3d256812b2afcedf304526a3e8d3e627505d306aa9552b8dd1f5551
Created=2026-07-29T11:36:17.888902008Z

復旧スクリプトが起動したコンテナ:
Image=sha256:fbc594ed132d0ced7195364c26c6781c99798df50bd3e4b0c3b041cdb797b4ab
Created=2026-07-26T07:24:35.892544519Z
RestartCount=19
```

## 作業checkpoint（復旧スクリプト5分待機後）

- checkpoint時刻: 2026-07-30 09:41 JST
- 承認範囲: 変更なし
- 完了済み: 復旧スクリプト実行、5分待機、失敗状態・log・image identity採取
- 未完了: 既存停止コンテナの直接compose起動、health GREEN確認、liquidation新session確認、full状態確認、事後確認
- 変更file: 本報告ファイル、復旧スクリプトが生成したappend-only autostart log
- 検証結果: 復旧スクリプトは2026-07-26作成imageを起動し、現在configの追加keyを認識できずrestart loop。既存停止コンテナは2026-07-29作成image
- blockerの限定範囲: 2026-07-26 imageによる起動だけ
- 次の再開位置: 失敗した新規containerのrestart loopを停止し、指示書fallbackの既存project `docker compose up -d`を実行

fallback実行コマンド:

```powershell
docker stop deltaengine_05m-deltaengine_clone-1
```

生出力:

```text
deltaengine_05m-deltaengine_clone-1
```

fallback実行コマンド:

```powershell
cd C:\Users\user\Desktop\DeltaEngine05M\Delta_Engine_Pro4web
docker compose up -d
```

生出力:

```text
time="2026-07-30T09:42:57+09:00" level=warning msg="C:\Users\user\Desktop\DeltaEngine05M\Delta_Engine_Pro4web\docker-compose.yml: the attribute `version` is obsolete, it will be ignored, please remove it to avoid potential confusion"
 Container delta_engine_pro4web-deltaengine_clone-1 Recreate
 Container delta_engine_pro4web-deltaengine_clone-1 Recreated
 Container delta_engine_pro4web-deltaengine_clone-1 Starting
 Container delta_engine_pro4web-deltaengine_clone-1 Started
```

## Step 3: health GREEN確認

composeのhost port生出力:

```text
18080:8080
```

実行コマンド:

```powershell
curl.exe -sS --max-time 15 http://localhost:18080/api/health
```

GREEN確認時のhealth応答全体:

```json
{"state":"GREEN","sample_time":"2026-07-30T00:46:46.815454+00:00","checks":{"sequence_gap":{"level":"GREEN","value":"0","detail":"book gaps in window: 0"},"ws_reconnect":{"level":"GREEN","value":"0","detail":"reconnects in window: 0"},"pipeline":{"level":"GREEN","value":"0","detail":"pipeline exceptions in window: 0"},"bar_flow":{"level":"GREEN","value":"47","detail":"last bar 47s ago"},"latency":{"level":"GREEN","value":"0","detail":"event lag 0ms"},"memory":{"level":"GREEN","value":"267","detail":"rss 267MB"},"tape":{"level":"GREEN","value":"0","detail":"dropped=0 pending=1 send_failures=0 balanced=True"}},"anomalies_today":0}
```

## Step 4: liquidation stream確認

実行コマンド:

```powershell
curl.exe -sS --max-time 15 http://localhost:18080/api/stats
```

生出力:

```json
{"book_snapshots_applied":1,"book_diffs_applied":1944,"book_gaps_detected":0,"book_synced":true,"book_resyncs":0,"book_snapshot_fetch_failures":0,"book_projection_state":"SYNCED","book_projection_samples":1725,"book_updates_sent":1709,"book_synced_updates_sent":1707,"book_fail_closed_sent":2,"book_projection_unchanged_suppressed":16,"book_projection_send_failures":0,"tape_stream_id":"542c31bb-4598-4b30-b3e5-8dce85fcf70d","tape_batch_time_mode":"wall","tape_accepted_trades":8834,"tape_sent_trades":8834,"tape_batches_sent":842,"tape_max_batch_size":250,"tape_pending":0,"tape_pending_high_watermark":1129,"tape_inflight_trades":0,"tape_dropped_trades":0,"tape_invalid_rejected":0,"tape_send_failures":0,"tape_accounted_trades":8834,"tape_accounting_balanced":true,"current_cvd":"77.851","trades_processed":8834,"absorption_events":0,"storage_queue_pending":0,"storage_queue_high_watermark":383,"footprint_bars_written":3,"footprint_levels_written":859,"footprint_duplicates":0,"footprint_write_failures":0,"footprint_flush_median_ms":110.34751399995457,"footprint_flush_p95_ms":123.9770629999839,"hfm_pending_outcomes":0,"hfm_quote_status":"STALE","hfm_symbol":"#BTCUSDr","hfm_spread_usd":"18.583","hfm_quote_age_ms":412416818,"ui_ticks_published":8834,"ui_ticks_sent":1117,"ui_ticks_coalesced":7717,"hook_capture":{"campaign_id":"stage2a_20260726_xz","campaign_dir":"data_05M/hook_observer/campaigns/stage2a_20260726_xz","full_capture_until":"2026-07-29T04:19:39.359895+00:00","liquidation_capture_until":"2026-08-09T04:19:39.359895+00:00","full_effective_capture_until":"2026-07-29T18:34:31.945117+00:00","liquidation_effective_capture_until":"2026-08-09T18:25:19.214987+00:00","coverage":{"full":{"original_deadline":"2026-07-29T04:19:39.359895+00:00","extension_seconds":51292.585221999994,"extension_cap_seconds":259200.0,"effective_deadline":"2026-07-29T18:34:31.945117+00:00"},"liquidation":{"original_deadline":"2026-08-09T04:19:39.359895+00:00","extension_seconds":50739.855092,"extension_cap_seconds":604800.0,"effective_deadline":"2026-08-09T18:25:19.214987+00:00"}},"closed":false,"streams":{"liquidation":{"mode":"liquidation","session_id":"session-20260730T004301.314315Z-32f787d3","deadline":"2026-08-09T18:25:19.214987+00:00","accepting":true,"accepted":0,"persisted":0,"durably_committed":0,"pending":0,"high_watermark":0,"dropped_queue_full":0,"rejected_disk_low":0,"rejected_deadline":0,"writer_error":null}}}}
```

新sessionの`COVERAGE_START`生出力:

```jsonl
{"event":"COVERAGE_START","event_id":"9e94708406facafab3a3db80456eb5775e9f91b62e881a69f7e8e0b148cf510d","event_time":"2026-07-30T00:43:00.485132+00:00","ledger_version":1,"session_id":"session-20260730T004301.314315Z-32f787d3","stream":"liquidation"}
```

実行コマンド:

```powershell
Get-Content -LiteralPath 'data_05M/hook_observer/campaigns/stage2a_20260726_xz/coverage_events.jsonl' -Tail 10
```

生出力:

```jsonl
{"accepted":0,"accepting":true,"dropped_queue_full":0,"durably_committed":0,"event":"COVERAGE_HEARTBEAT","event_id":"97ea977e447e6ca5a0352955014a1c52b7643c0ad34edd73dc144012d2e2bace","event_time":"2026-07-30T00:45:41.642261+00:00","ledger_version":1,"persisted":0,"rejected_disk_low":0,"session_id":"session-20260730T004301.314315Z-32f787d3","stream":"liquidation","writer_error":null}
{"accepted":0,"accepting":true,"dropped_queue_full":0,"durably_committed":0,"event":"COVERAGE_HEARTBEAT","event_id":"4773c8d5e22f926cc34d21a28e503c8c3d265b1f5230def513d5d1caea73da01","event_time":"2026-07-30T00:45:51.685923+00:00","ledger_version":1,"persisted":0,"rejected_disk_low":0,"session_id":"session-20260730T004301.314315Z-32f787d3","stream":"liquidation","writer_error":null}
{"accepted":0,"accepting":true,"dropped_queue_full":0,"durably_committed":0,"event":"COVERAGE_HEARTBEAT","event_id":"ddb52009c349b60462d8f10ee67d012e24c14d8e4820f6acf15a0f9c7ee1075b","event_time":"2026-07-30T00:46:01.722179+00:00","ledger_version":1,"persisted":0,"rejected_disk_low":0,"session_id":"session-20260730T004301.314315Z-32f787d3","stream":"liquidation","writer_error":null}
{"accepted":0,"accepting":true,"dropped_queue_full":0,"durably_committed":0,"event":"COVERAGE_HEARTBEAT","event_id":"e51a8be45fbe95c851ad981f57f3a74477fe8fa92ad436163a4bb347b26460a1","event_time":"2026-07-30T00:46:11.729118+00:00","ledger_version":1,"persisted":0,"rejected_disk_low":0,"session_id":"session-20260730T004301.314315Z-32f787d3","stream":"liquidation","writer_error":null}
{"accepted":0,"accepting":true,"dropped_queue_full":0,"durably_committed":0,"event":"COVERAGE_HEARTBEAT","event_id":"3b52f4da0c5b640a3c3274ec52a062a0a83eb5b59b1a02d9a962b5015d4c5b90","event_time":"2026-07-30T00:46:21.761936+00:00","ledger_version":1,"persisted":0,"rejected_disk_low":0,"session_id":"session-20260730T004301.314315Z-32f787d3","stream":"liquidation","writer_error":null}
{"accepted":0,"accepting":true,"dropped_queue_full":0,"durably_committed":0,"event":"COVERAGE_HEARTBEAT","event_id":"0b9a61e441021ce82baf9e38d834605fd6c56a45313e2d9bf1380b9d89343f23","event_time":"2026-07-30T00:46:31.780585+00:00","ledger_version":1,"persisted":0,"rejected_disk_low":0,"session_id":"session-20260730T004301.314315Z-32f787d3","stream":"liquidation","writer_error":null}
{"accepted":0,"accepting":true,"dropped_queue_full":0,"durably_committed":0,"event":"COVERAGE_HEARTBEAT","event_id":"bd57c6c77fafef23e36c2f58568d174eb7266a18bac9a62a790e0a207153558b","event_time":"2026-07-30T00:46:41.792613+00:00","ledger_version":1,"persisted":0,"rejected_disk_low":0,"session_id":"session-20260730T004301.314315Z-32f787d3","stream":"liquidation","writer_error":null}
{"accepted":0,"accepting":true,"dropped_queue_full":0,"durably_committed":0,"event":"COVERAGE_HEARTBEAT","event_id":"79c38959251dd7f3bd4665c4d34e398bba090800b96b2eefc0499167702bbd87","event_time":"2026-07-30T00:46:51.799311+00:00","ledger_version":1,"persisted":0,"rejected_disk_low":0,"session_id":"session-20260730T004301.314315Z-32f787d3","stream":"liquidation","writer_error":null}
{"accepted":0,"accepting":true,"dropped_queue_full":0,"durably_committed":0,"event":"COVERAGE_HEARTBEAT","event_id":"5bc322db32186fc04f0f923ada28d25edf54ff5c73994f19c38fc85f1f6dc55d","event_time":"2026-07-30T00:47:01.811151+00:00","ledger_version":1,"persisted":0,"rejected_disk_low":0,"session_id":"session-20260730T004301.314315Z-32f787d3","stream":"liquidation","writer_error":null}
{"accepted":0,"accepting":true,"dropped_queue_full":0,"durably_committed":0,"event":"COVERAGE_HEARTBEAT","event_id":"73258c99659420577c262986f3e85ff3cad2dd40b723820183aef3a35d92b802","event_time":"2026-07-30T00:47:11.855819+00:00","ledger_version":1,"persisted":0,"rejected_disk_low":0,"session_id":"session-20260730T004301.314315Z-32f787d3","stream":"liquidation","writer_error":null}
```

## Step 5: full stream状態の確認

再起動後のfull stream sessionディレクトリ末尾:

```text
session-20260728T213402.760656Z-3874f516
session-20260728T224805.270012Z-e8d7d36b
session-20260728T230634.507475Z-f2b1651f
session-20260728T235739.617043Z-7eef2c58
session-20260729T012627.280594Z-31c7f85a
```

記録:

```text
新しいfull sessionは開始されなかった。
```

## Step 6: 事後状態の記録

実行コマンド:

```powershell
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

生出力:

```text
NAMES                                      STATUS         PORTS
delta_engine_pro4web-deltaengine_clone-1   Up 3 minutes   127.0.0.1:15555->5555/tcp, 0.0.0.0:18080->8080/tcp, [::]:18080->8080/tcp
```

追加read-only確認:

```powershell
docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"
```

生出力:

```text
NAMES                                      STATUS                     IMAGE
delta_engine_pro4web-deltaengine_clone-1   Up 3 minutes               delta_engine_pro4web-deltaengine_clone
deltaengine_05m-deltaengine_clone-1        Exited (3) 4 minutes ago   deltaengine_05m-deltaengine-clone:stage2b-20260726-r3
deltaengine_clone-deltaengine_clone-1      Exited (127) 5 days ago    deltaengine_clone-deltaengine_clone
buildx_buildkit_default                    Exited (1) 3 days ago      moby/buildkit:buildx-stable-1
```

実行コマンド:

```powershell
(Get-PSDrive C).Free
```

生出力:

```text
93394718720
```

## 作業checkpoint（完了）

- checkpoint時刻: 2026-07-30 09:47 JST
- 承認範囲: 変更なし
- 完了済み: 全Step、既存projectの起動、health GREEN、liquidation新session／accepting確認、full非再開確認、事後状態確認、報告記録
- 未完了: なし
- 変更file: 本報告ファイル、復旧スクリプトが生成したappend-only autostart log
- 検証結果: campaign `stage2a_20260726_xz`、liquidation `accepting:true`、新session `session-20260730T004301.314315Z-32f787d3`、継続heartbeat、full新sessionなし、health GREEN
- blockerの限定範囲: なし。2026-07-26旧imageの失敗containerは削除せずExited(3)で保持
- 次の再開位置: liquidation収録の継続監視
