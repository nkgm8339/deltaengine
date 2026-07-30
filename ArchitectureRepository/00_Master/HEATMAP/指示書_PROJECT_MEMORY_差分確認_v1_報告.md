# [停止] 指示書_PROJECT_MEMORY_差分確認_v1

## 該当箇所引用

### セクション: Order Book Heatmap GO-H0 baseline audit（2026-07-29）

> - primary baseline commit 57 file
> GO-H0監査後、ユーザーの`baseline commit GO`を受領した。57 fileをexact pathでstageし、
> manifest差分0、artifact／別topic文書混入0を確認してrestore pointを作成した。
> - commit後WebApp: **122 passed**
> - commit後repository全体: **664 passed, 1 skipped**
> - commit後実Edge: baseline geometry完全一致、gap各12px、overflow 0、Tape 14px／28px、error 0
> GO-H0は完了。GO-H1以降のsource実装、runtime再起動、deploymentは未承認。

### セクション: Order Book Heatmap GO-H1 Book continuity contract（2026-07-29）

> ユーザーの`GO-H1実装のみを許可する`承認に基づき、additive Book continuity
> contractをsource実装した。
> - targeted **45 passed**
> - WebApp **125 passed**
> - repository **667 passed, 1 skipped**
> - failure／error 0
> current runtimeは旧imageのまま。GO-H1はsource PASSで完了し、
> 再build／再起動／deployment／GO-H2以降は未承認。
> 完了報告／checkpoint:

### セクション: Order Book Heatmap V1 operational activation (GO-H6, 2026-07-29)

> GO-H6を完了し、Order Book Heatmap V1をoperational activationした。
> - H1 continuity backend imageをbuild／再配備し、runtime `/ws/delta` の`orderbook.seq_id`,`orderbook.prev_seq_id`,`orderbook.reset`を確認。
> - image `delta_engine_pro4web-web:heatmap-h1-20260729`、container `delta-engine-pro4web`をruntime baselineとする。
> - static bind-mounted UI flag `ORDER_BOOK_HEATMAP_V1_ENABLED=true`。
> - final health GREEN。15分LIVE観測は`/health`,`/api/status`,`/api/replay/status`,`/api/market-data-status`,`/api/storage/status`全件GREEN。
> - recent production logsの`ERROR|Exception|Traceback|Address already in use`は0件。
> - rollback fallbackは旧image、flag off、source baselineの3系統をrehearsal PASS後に削除。
> - 完成済みFlow Price Response、3段チャート、Tape、PDF、既存REST／WS schemaは変更していない。

### セクション: Persistent depth history sizing (2026-07-29)

> GO-H6後、ユーザー承認の30分LIVE sizingのみを実施した。persistent writer／保存先／schemaは変更していない。
> - 観測時間: 1,806.13s、orderbook frame 19,612、平均10.86 frame/s、27.68 KiB/s
> - JSON transport estimate: 48.65 MiB / 30min、2.28 GiB/day、68.41 GiB/30d、interval compressed 7.30 MiB / 30min相当
> - 平均levels: asks 5.54、bids 8.33、full top-of-book pairは1,223 frame
> - WebSocket errors 0、sequence gaps 0、resets 1。reset frameは空、次のnon-resetでbook復帰。

### セクション: Persistent depth history GO-PD1 isolated prototype（2026-07-29）

> GO-PD0 onlyの続行承認により、production未接続のisolated raw segment prototypeを追加した。`Decimal -> str -> JSON -> str -> Decimal`のexact round-trip、append-only NDJSON、closed segment sidecar manifest（sha256/bytes/count/seq range/reason）、size rotation、shutdown closeを実装し、isolated test 2 passed。syntheticのみで、REST/WebSocket/container/live path/record_path wiringは変更していない。

### セクション: Persistent depth history GO-PD2 isolated recovery prototype（2026-07-29）

> ユーザー承認により、production未接続のPD2 recovery prototypeを追加した。live segment durability（flush + fsync）、incomplete JSON tail切り捨て、valid-record-only replay、gap/reset boundary metadata、best bid/askのexact reconstructionを実装・検証し、isolated suite 4 tests passed。source commit、production wire、build/deploy/live確認、PD3以降は未実施。

### セクション: Persistent depth history GO-PD3 isolated sizing／safety（2026-07-29）

> ユーザー承認により、synthetic fixture onlyのisolated PD3 sizing／safety検証を実施した。10分simulated stream（120,000 event）でraw 17,547,265 byte、estimated 41.84 GiB/30d、writer＋flush p95 0.064075ms、full segment fsync p95 4.0474ms、isolated suite 7 tests passed。容量cap超過時はfail loudlyして不完全recordをappendしない。latency guardはp95 5ms超でstop。production wiring、container、live、PD4+は未実施。

### セクション: Persistent depth history GO-PD4 compatibility deployment（2026-07-29）

> ユーザー承認により、compose runtimeへadditive wiringを追加した。`ORDERBOOK_HISTORY_ENABLED=false`を既定とし、output directory bind mountを追加、isolated writer failureはmarket data pathを止めず`status.error`へ報告する。backendをbuild/deployし、final health GREEN、flag false、既存REST／WS schema不変、rollback rehearsal PASSを確認した。targeted 12 passed、WebApp 130 passed、repository 679 passed／1 skipped。既存Bookmap/CVD/PDF/Flow Price Response/3段チャートは変更していない。

### セクション: Persistent depth history GO-PD5 preflight NO-GO（2026-07-29）

> ユーザー承認によりruntime preflight、production-input 10分shadow sizing、30日projected storage、before-activation rollback rehearsalを実施した。backend runtime／bind mount／live seq continuityはGREEN、30日projected storageは2.73 GiB（cap 90 GiB以内）、rollback rehearsalもPASS。しかしcontainer内environmentが`ORDERBOOK_HISTORY_ENABLED`と`ORDERBOOK_HISTORY_OUTPUT_DIR`を未設定のため、activation GO条件を満たさずNO-GOとした。flag falseを維持し、既存Bookmap V1／CVD／PDF／Flow Price Response／3段チャートは稼働維持。コード、compose、container、record_path、writer wiringは変更していない。

### セクション: Persistent depth history PD5 implementation activation（2026-07-29）

> ユーザー承認済み指示書に基づき、production integrationを実装した。isolated raw segment writerを`WebAppProcessManager._market_data_consumer()`のbook更新直後へwiringし、`futuresBookTicker`をdecode前除外、real `@depth5@100ms` eventのみをraw NDJSONへ記録する。初回buildのbridge整合不良を修正し、backend再配備後は`ORDERBOOK_HISTORY_ENABLED=true`、`status.enabled=true`、`status.error=null`、`.ndjson`／`.manifest.json`生成を確認した。
> - 関連回帰48 passed
> - final health GREEN
> - closed manifest `raw_orderbook_20260729T165502-20260729T165503_f1b3bb4e.manifest.json` は`record_count=72`、`byte_size=7641`、`closed_reason=restart`、SHA-256一致
> - recent 10分 `ERROR|Exception|Traceback|Address already in use|Persistent orderbook history writer failed` = 0
> - 初回失敗はhidden smoke testによるport 8000競合と旧解釈の`futuresBookTicker`混入。修正版のみをPASS扱いとし、旧artifactはrollback archiveへ隔離。

### セクション: 2026-07-29 Persistent Depth History PD6

> persistent depth history PD6を実施。production writer有効状態で約30分のLIVE soakを完了し、`continuity check PASS (validated=1,805)`、final health 5/5 GREEN、WebSocket／writer error 0、`.ndjson=27`／`.manifest.json=26`を確認した。30日projected storageはrun内raw bytes extrapolationで`5.837 GiB`、closed-manifest rateで`5.83 GiB`、90 GiB capに対し安全。recent backend logsは`ERROR|Exception|Traceback|Address already in use|Persistent orderbook history writer failed|No space left on device=0`。本番コード、compose、既存UI、既存REST／WS schemaは変更していない。

## 状態

引用報告をファイルへ保存済み。次の指示待ちで停止。
