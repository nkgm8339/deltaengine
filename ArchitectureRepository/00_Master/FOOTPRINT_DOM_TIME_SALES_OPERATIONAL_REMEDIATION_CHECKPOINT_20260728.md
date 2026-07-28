# Footprint × LIVE DOM × Time & Sales operational remediation checkpoint

最終更新: 2026-07-29 00:02 JST  
状態: **修正版production稼働／15分storage・health監視中**

## 承認

Phase 6完了後のユーザー「つづけて」を、直近checkpointの次の安全な工程である
read-only disk／storage inventory開始承認として受領した。

現在の承認範囲:

- 既存storage設計、保持契約、runtime設定のread-only確認
- Cドライブ、workspace、Docker image／container／volume／build cacheのread-only使用量監査
- 現行container health／error／mountのread-only確認
- 保持、移動、削除、再構築候補と必要容量の整理
- 本checkpointとread-only監査報告の更新

現在の承認範囲外:

- file、directory、Docker image／container／volume／cacheの削除、prune、truncate
- 稼働containerの停止、再起動、再作成
- data移動、圧縮、schema／database変更
- Docker image build、deploy、production restart
- LIVE注文、MT5、Strategy／Hook／Condition／Pattern／Order Trigger変更
- 完成済みFlow Price Response／3段チャート／8パターン／OIの変更
- git reset／checkout／stage／commit／push

追加承認:

- 2026-07-28、tool approvalにより、存在しない`D:\MT5XM`に属する旧XMTrading terminalの
  market-history cache `.hc`／`.hcc`だけを永久削除する承認を受領した。
- 承認対象外の現HFM、DeltaEngine data、旧terminalのMQL5／config／ticks／tradesは保持する。
- 2026-07-28、tool approvalにより、旧RED containerを停止せず現在sourceを固有tagへ
  buildする承認を受領した。
- 2026-07-28、tool approvalにより、旧RED containerを停止し、bind-mounted dataを保持したまま
  検証済みPhase 1〜6 imageでproduction recreateする承認を受領した。

## 開始時点

- 時刻: 2026-07-28 22:35:37 JST
- branch: `feature/footprint-dom-tape`
- HEAD: `92ee4eff823ba31e84f7fc0af197d39b877ec236`
- Phase 1〜6変更は未コミットでworktreeに存在する。
- 既存dirty／untracked変更をreset、checkout、stage、削除しない。
- Phase 6 final full pytest: **661 passed, 1 skipped**
- 直近監査のCドライブ空き: 768,671,744 bytes（約0.72 GiB）
- 直近監査のexisting runtime: version `v3.6.21`、health RED、
  Parquet write `[Errno 5] Input/output error`
- Phase 1〜6 source implementation／isolated integration: PASS
- 現runtime activation: NO-GO

## 完了済み

- `ArchitectureRepository/00_Master/PROJECT_MEMORY.md`全1,032行を再読
- Phase 6 checkpoint／completion reportを全文確認
- active goalなしを確認
- branch／HEAD／dirty worktreeを確認
- 本checkpointを変更前境界として作成
- Phase 0C sizing checkpoint／reportとV2／V2.1 storage契約を確認
- Cドライブ、workspace、Docker、user profileをread-only inventory
- existing container state／mount／health／stats／versionをread-only確認
- disk pressureの主因と、現行HFM／DeltaEngine dataから独立した限定cache候補を特定
- 削除直前に対象absolute path、terminal origin、Dドライブ不存在、全file extension、
  90 GB以上のsize boundaryを再検証
- 承認済み旧XMTrading market-history cache 21,260 files／97,337,847,530 bytesを削除
- 削除後のfree spaceと保全対象の存在を再検証
- `phase6-remediation-20260728`固有tagへnew imageをbuild
- host／image間のPhase 1〜6主要13 file SHA-256完全一致を確認
- new image内Phase 1〜6対象regressionを実行
- 旧RED containerをnew imageでrecreate
- 起動直後のpipeline／bar flow／latency／storage／Hook capture回復を確認
- Footprint history APIからproduction保存済みbar／levelsをread-back
- Playwright Chromiumでproduction UIを実ブラウザ検証
- 残存するpre-Footprint imageを内容確認後、fallback rollback tagへ固定
- 15分reconnect health window満了後の23:34 JSTに全health check GREENを確認
- 23:37 JSTの新規Binance reconnect／book gapを、storage／pipelineとは独立したupstream degradationと判定
- deploy後37分のlogにStorageError／Traceback／Parquet I/O再発がないことを確認
- operational remediation report、V2／V2.1、Phase 6 report、PROJECT_MEMORYを確定更新

## 未完了

- 23:47 JSTに再発したOI Parquet `Bad file descriptor`のretry／fail-safe remediation
- 修正版の対象回帰、image build、production restart、post-deploy再監視
- Binance WebSocket品質は外部要因のため通常production監視を継続する。
- git stage／commit／pushは承認範囲外のため実施対象に含めない。

## 変更file

- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_OPERATIONAL_REMEDIATION_CHECKPOINT_20260728.md`
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_OPERATIONAL_REMEDIATION_REPORT_20260728.md`
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_FUSION_IMPLEMENTATION_INSTRUCTION_V2_20260728.md`
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_FUSION_PREIMPLEMENTATION_AMENDMENT_V2_1_20260728.md`
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_PHASE6_COMPLETION_REPORT_20260728.md`
- `ArchitectureRepository/00_Master/PROJECT_MEMORY.md`
- `Delta_Engine_Pro4web/src/database/storage.py`
- `Delta_Engine_Pro4web/tests/database/test_open_interest_storage.py`

## 検証結果

- 監査開始前のCドライブ空き:
  1,042,132,992 bytes（約0.97 GiB）。全体238 GiBに対して100%使用表示。
- workspace合計は約5.1 GiB。主な内訳:
  - `Delta_Engine_Pro4web`: 4,283,471,603 bytes
  - `DeltaEngine_BACKUP_20260719`: 329,580,705 bytes
  - `archive`: 268,112,560 bytes
  - `vwap-audit.duckdb`: 219,688,960 bytes
- `Delta_Engine_Pro4web`の主な内訳:
  - `data_05M`: 2,424,176,976 bytes
  - `data`: 1,538,896,180 bytes
  - Phase 0C隔離benchmark: 190,067,866 bytes
  - `analysis`: 123,528,187 bytes
- project dataには次の大きいfileがあるが、研究／監査証拠として削除していない:
  - `data_05M/manual/flow_response_shadow.jsonl`: 971,112,678 bytes
  - `data/execution_costs/quotes_go1_20260723_094459.csv`: 788,788,542 bytes
  - `data/duckdb/orderflow.duckdb`: 326,119,424 bytes
  - `data_05M/duckdb/orderflow_05M.duckdb`: 255,209,424 bytes
- Docker:
  - `docker_data.vhdx`: 14,224,982,016 bytes
  - build cache: 6.132 GB
  - buildx volume: 655 MB
  - 稼働container writable layer: 2.47 MB
  - 稼働containerの`data_05M`はhost Cドライブへのbind mount
- user profile最大占有は
  `C:\Users\user\AppData\Roaming\MetaQuotes`の101,621,060,417 bytes。
- そのうち97,443,020,128 bytesはterminal hash
  `28A2DF619FD2B717E8C1EF7860232106`。
  `origin.txt`は現在存在しない`D:\MT5XM`を示し、Dドライブ自体が存在しない。
- 限定削除対象は旧terminalの
  `bases\XMTrading-MT5 2\history`だけ:
  - 97,337,847,530 bytes
  - `.hcc` 18,724 files／79,112,427,936 bytes
  - `.hc` 2,536 files／18,225,419,594 bytes
  - 全fileの更新は2026-03-10
  - MT5が再取得可能なmarket-history cache
- 2026-07-28 22:47:39 JSTの削除後検証:
  - 対象path不存在
  - Cドライブ空き98,431,594,496 bytes（約91.67 GiB）
  - 現行HFM terminal hash
    `E3E3B02889D32F38295D39BF94B6AD4A`存在
  - `Terminal\Common\Files\DeltaEngine_HFM_quotes_utf8.jsonl`存在
  - 旧terminalのMQL5とticks存在
- cacheはローカルでは復元不能だが、旧XMTrading terminalを再利用する場合はMT5から再取得できる。
- existing container:
  - running、version `v3.6.21`
  - health RED
  - pipeline dead:
    `StorageError` → Parquet write `[Errno 5] Input/output error`
  - storage queue pending 9
  - Hook full streamはdisk-lowを1件検出後`accepting: false`
  - Hook liquidation streamは`accepting: true`
  - `ws_out` overflow log countは506,002まで増加
  - container root overlayには余裕があり、逼迫箇所はhost C bind mount
- new image:
  - tag: `delta_engine_pro4web-deltaengine_clone:phase6-remediation-20260728`
  - image ID: `sha256:81b5ae72cb4ff2847a914e71863c4870ba2a1383bc6f47983c00d203f7ab5e01`
  - created: 2026-07-28 22:51:58 JST
  - inspect size: 237,465,992 bytes
  - build context: 333.18 kB
  - data／data_05M／config／DuckDB／CSV／Parquetは`.dockerignore`でimageへ未収載
  - old `latest` tagとrunning containerは未変更
  - host／imageの主要13 file SHA-256: 全件一致
  - in-image Phase 1〜6対象: **116 passed, 4 skipped in 39.02s**
- deploy時のrollback境界:
  - current running image `sha256:e002dfd221696e458f10f73a0d528b099e4076f9f483637e9fed56d9ac05032b`
    をrollback tagで保全してからlatestを切り替える
  - new image IDは上記固有tagで保全済み
  - bind-mounted data／config／staticは削除しない
- deploy:
  - container ID:
    `7cee921a82182c3d2fb40ecc170b93b2b26837c1b26e2ec79f8b9fc70ce8e782`
  - image:
    `sha256:81b5ae72cb4ff2847a914e71863c4870ba2a1383bc6f47983c00d203f7ab5e01`
  - started: 2026-07-28 22:57:04 JST
  - restart count: 0
  - bind-mounted DuckDB／Parquet／Hook journal／config／staticを保持
- exact old running config digest `e002dfd...`はlatest切替後にDocker image参照として
  tagできず、旧manifest `6f7048...`も参照消失した。
- fallback rollback:
  - image ID:
    `sha256:2a8c6d243e6caacc2c1ab29de58062616d098db21bf0e6e9c022c03894d61bcb`
  - tag: `delta_engine_pro4web-deltaengine_clone:rollback-pre-footprint-20260728`
  - build時刻は旧running imageと同日同時間帯
  - `webapp/tape.py`、`book_projection.py`、Footprint Canvas、Phase 6 testが存在しない
    pre-Footprint imageであることを確認
- 起動直後22:58 JST:
  - health GREEN
  - pipeline／bar flow／latency GREEN
  - storage pending 0
  - Hook full capture `accepting: true`、disk reject 0
- 22:58 JST production persistence:
  - Footprint bar 1／levels 328 written、failure 0
  - `/api/history/footprints`で同bar 328 levelsをread-back
- 23:06:55 JST継続観測:
  - trades 31,607
  - storage pending 0、high watermark 308
  - Footprint bars 7／levels 3,073 written、failure 0
  - Tape accepted 31,607／sent 31,607／pending 0／dropped 0／balanced true
  - BOOK `SYNCED`、send failure 0
  - Hook full accepted 35,617／durable 35,477／pending 139／drop 0／disk reject 0／writer errorなし
  - Cドライブ空き89,062,014,976 bytes（約82.95 GiB）
- 実browser 1536×1200:
  - HTTP 200、Tape LIVE
  - history 500＋live 105、kept 500、DOM pool 32／32、gap 0
  - LIVE DOM SYNCED、spread 0.1、age 73ms
  - Footprint 10 bars LIVE、Canvas 696×476
  - 3段チャート表示、旧Order Book `display:none`
  - horizontal overflowなし
  - console error 0、page error 0
- 23:06 JSTにBinance stream keepalive ping timeoutが1回発生し、connector reconnect 4、
  book gap 1を検出した。pipeline／bar flow／Tape／storageは継続GREENで復旧済み。
  HealthMonitorの15分window内ではreconnect 4がREDとして残ったが、23:34 JSTにexpireしてGREEN復帰。
- validation中のWindows負荷によりpagefileが24,615,258,112 bytesまで自動拡張し、
  Docker VHDXも15,332,278,272 bytesへ増えた。23:11時点のC空きは89,053,814,784 bytes。
  一時Edge processとpytest temporary directoryは限定cleanup済み。pagefile設定は変更していない。
- host full pytest再実行は既存access-denied directoryのcollectionとWindows basetemp cleanupで
  結果確定不能。既存Phase 6 final **661 passed, 1 skipped**は有効。
- new image内ではPhase 1〜6対象 **116 passed, 4 skipped**。
  image全testはruntime imageに未収載の研究`requests`と外側Strategy正本CSVに依存するため、
  Phase 1〜6以外でcollection 1件／44件が環境境界failureとなった。Strategy runtimeは未有効。
- 23:18 JST、重いvalidation終了境界付近でBinance reconnect 1／book gap 1が再発。
  直後のpipeline／bar／Tape／storageはGREEN、Bookは再同期した。
- 23:20 JST、Binance公式endpoint疎通:
  - host OI 200／662ms
  - container time 200／73ms
  - container OI 5回すべて200／32.0〜233.9ms
  timeoutは直接疎通で再現せず、外部／host負荷中の一過性timeoutとして15分windowを再監視した。
  23:34 JSTの最終確認でreconnect／gap／latencyを含む全check GREEN。
- production container／DeltaEngine dataへの変更なし

## blockerの限定範囲

- disk spaceとdead background worker blockerは解消
- 23:06／23:18のBinance ping timeout／book gapは自動復旧し、23:34 JSTに全check GREEN
- 23:37 JSTに新しいBinance ping timeout／book gapが発生。pipeline／bar／latency／Tape／storage／Bookは正常
- production storage workerは停止中。修正版image build／restartが未完了
- rollbackはexact旧container imageでなく、内容確認済みpre-Footprint fallback image

### 23:47 JST monitoring中の再発

- 23:47:38 JST、OI hourly Parquet temporary writeで
  `[Errno 9] Bad file descriptor`／`error closing file`
- background storage workerはfail closedで停止、health pipeline RED
- Cドライブ空き82.83 GiB。disk-lowではない
- open-file limit 1,048,576、process FD 17。FD exhaustionではない
- target `hour-14.parquet`は4,128 bytes／104 rowsで正常read可能
- failed temporary fileは既存exception cleanupで不存在、target破損なし
- `/app/data_05M`はWindows CへのDocker 9p bind mount
- Tapeはdrop 0／balanced、Hookはaccepting／disk reject 0／writer errorなし
- ただしstorage queueは停止時42 pendingであり、production storage判定はNO-GOへ戻す

### bounded retry remediation

- retry対象はOI hourly Parquetのwrite／atomic replace中に発生するEIO／EBADF／
  `input/output error`／`error closing file`だけ
- retry delayは0.1／0.5／1.0秒、合計4 attempts
- 各attempt前後で限定temporary fileをcleanup
- schema／content errorや4回連続failureは従来どおりE4001→E4003 fail closed
- target破損やsilent lossを許可しない
- 新規test 2件:
  - 1回EBADF後のretry成功／一時file残留なし
  - 4回連続EBADFのbounded failure／E4001維持
- dedicated target: **5 passed**
- database／API関連: **58 passed**
- full regression: **663 passed, 1 skipped in 37.97s**
- remediation image:
  - tag: `delta_engine_pro4web-deltaengine_clone:oi-parquet-retry-20260728`
  - ID: `sha256:da7d17c85b90bc1e0925dd4b30ef8ba094ce846deb50f8ef5b30ee493b6e61de`
  - created: 2026-07-28 23:58:03 JST
  - inspect size: 237,469,367 bytes
  - in-image OI retry: **5 passed in 5.20s**
- 2026-07-29 00:00:40 JST restart前final:
  - pipeline dead、storage pending 42、trades frozen 206,469、Footprint bars 48
  - Tape accepted／sent 206,470、pending／dropped 0、balanced true
  - Hook accepted／durable 233,236、pending／dropped／disk reject 0、writer errorなし
- storage worker停止中の通常Parquet／DuckDB保存gapを隠さない。
  worker memory内pending 42件はcontainer recreateで回収不能。Hook durable captureは継続しているため、
  将来の限定reconstruction可否は別工程で評価する。
- remediation deploy:
  - container ID: `98392cea9c6bb30868a8310ef097402ab166cc8cdc3afb800fa1479d532e3919`
  - image: `sha256:da7d17c85b90bc1e0925dd4b30ef8ba094ce846deb50f8ef5b30ee493b6e61de`
  - started: 2026-07-29 00:01:25 JST
  - restart count: 0
- 00:01:57 JST起動直後:
  - overall／pipeline／bar／latency／Tape／reconnect／gap: 全GREEN
  - storage pending 0、Tape accepted／sent 580、pending／dropped 0、balanced true
  - Book SYNCED、Hook disk reject 0／writer errorなし

## 次の再開位置

1. transient OSErrorに対するbounded retry契約とnegative testを追加
2. 対象回帰後に固有tag imageをbuild
3. production restart前にcheckpointと承認境界を更新
4. storage／Footprint／Tape／Hookと15分healthを再確認

version label更新、exact rollback image整備、Strategy正本CSV mountは別承認工程である。
