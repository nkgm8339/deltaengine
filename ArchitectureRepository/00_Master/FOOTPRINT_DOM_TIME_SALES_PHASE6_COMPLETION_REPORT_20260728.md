# Footprint × LIVE DOM × Time & Sales Phase 6 完了報告

完了時刻: 2026-07-28 22:29 JST  
対象branch: `feature/footprint-dom-tape`  
開始HEAD: `92ee4eff823ba31e84f7fc0af197d39b877ec236`  
承認: V2.1 GO-11

## 1. 結論

Phase 6「restart／reconnect／replay／live no-loss統合検証」を完了した。

source implementationと隔離統合環境の判定は **PASS** である。
Phase 1〜5の機能を一つの経路として接続し、replay市場時刻、再起動履歴、再接続欠番、
stream restart、LIVE no-loss、bounded overflow、実Edge layoutまで確認した。

一方、現稼働runtimeへのdeployment／operational activationは **NO-GO** とする。
稼働中コンテナは旧版で、storage I/O errorによりpipelineが停止し、disk余力も不足している。
これはPhase 6実装testの失敗ではなく、既存運用環境の独立したblockerである。

## 2. Phase 6で判明・修正した契約違反

### 2.1 Replay speed

`replay.speed`はconfigと正本に存在したがruntime未接続だった。

修正後:

- `0`: wall waitなしで可能な限り高速
- 正値: source event time差を倍率でwall timeへ対応
- Normalizerが確定したaccepted trade順でpace
- negative値は拒否
- LivePipelineの時刻・batch方式は変更しない

### 2.2 Replay WebApp callback

ReplayPipelineは従来`on_accepted_trade`だけを呼び、chart向けcallbackを出していなかった。

修正後:

- accepted trade
- trade observation callback
- confirmed／final replay candle
- analysis
- Flow Price Response

をsource-time順に発行する。replay worker threadからFastAPI event loopへは
`run_coroutine_threadsafe`でmarshalし、live loop内では通常taskとして送る。

### 2.3 Replay Tape time／isolation

- Replay Tapeの`batch_time`とWebSocket envelope timeをbatch末尾tradeのevent timeへ変更
- Live Tapeは従来どおりserver wall send time
- replay中はlive shadow Flow Response fileへ書き込まない
- replay中はlive OI poller／LIVE DOM projectorを起動しない既存境界を維持

## 3. 統合検証

### 3.1 Restart hydration

二つの隔離LivePipeline sessionを同じtemporary DuckDB／Parquetへ順番に接続した。

- sessionごとに異なるUUID `stream_id`
- 各streamのsequenceは1から再開
- 各session accepted 122、sent 122、drop 0、balance true
- restart後のTime & Sales history: 244件一意、oldest-first
- restart後のFootprint history: confirmed 4 bars一意
- production DB／Parquetは不使用

### 3.2 Reconnect

- 同一server streamではsequence継続
- disconnect中batchをreconnect cacheへ入れない
- reconnect時は最新BOOK_UPDATE 1件だけ再送
- history hydrateは`(symbol, trade_id)`でdedup
- expected 43に対するfirst 45をsame-stream gap 1件として表示
- new streamではold expectedとgap表示をresetし、restart countを1件表示

### 3.3 Replay

- accepted trade順とsource event time順一致
- 2倍速fixtureの60秒market差を30秒wall delayとしてfake clockで確認
- final replay candle／analysis callbackを確認
- FastAPI実lifespan上でworker threadからCANDLE／TAPE_UPDATEを受信
- TAPE message time／batch time／trade event timeが同じreplay market time
- 現在LIVE trade／OI／DOM／shadow writeの混入なし

### 3.4 Live no-loss／overflow

隔離LivePipelineへ6,000件を投入:

- normalized: 6,000
- stored: 6,000
- Tape accepted: 6,000
- Tape sent: 6,000
- dropped: 0
- batches: 24
- max batch: 250
- pending high watermark: 6,000
- latest history: 500、trade ID 5,501〜6,000
- `accepted = sent + pending + in_flight + dropped`: true
- elapsed: 1.882秒

bounded queueへ25,000件を投入:

- accepted: 25,000
- sent: 10,000
- dropped: 15,000
- first sent sequence: 15,001
- first batch `dropped_count`: 15,000
- accounting balanced: true
- 黙った欠落なし

## 4. 実Edge

環境: 1536 × 1200、DPR 1.25、local ephemeral HTTP／mock exchange stream。

- same-stream reconnect gap: 1
- new-stream restart: 1、final gap false
- final expected sequence: 1,022
- history received: 132、live received: 1,024、kept: 500
- Tape row: 15px、viewport 23行、pool 32、visible node 32
- warm 100回×5-trade batch render p95: **1.4ms**
- cold／reconnect／250-trade burstを含む観測p95: 46.5ms
- LIVE DOM: SYNCED後STALEでquantity level 0
- 旧Order Book presentation: hidden
- 3段チャート寸法: 前後不変
- horizontal overflow: なし
- browser page error: 0

初回Edgeは診断scriptが旧selector `#marketChart`を参照して描画前に停止した。
現行`#chart`へ修正して同じ操作を再実行し、上記最終結果を得た。製品runtime failureではない。

## 5. Automated regression

- Replay／Tape／restart／reconnect新規統合: **5 tests追加**
- 既存関連修正前: **68 passed**
- 既存関連修正後: **68 passed**
- Phase 1〜6対象: **186 passed in 20.07s**
- final full pytest: **661 passed, 1 skipped in 33.27s**
- Python compile: PASS
- Node syntax: PASS
- `git diff --check`: PASS（改行形式warningのみ）

## 6. 変更file

- `Delta_Engine_Pro4web/src/pipeline.py`
- `Delta_Engine_Pro4web/webapp/main.py`
- `Delta_Engine_Pro4web/webapp/tape.py`
- `Delta_Engine_Pro4web/tests/test_pipeline.py`
- `Delta_Engine_Pro4web/tests/webapp/test_tape_update.py`
- `Delta_Engine_Pro4web/tests/webapp/test_api.py`
- `Delta_Engine_Pro4web/tests/webapp/test_phase6_integration.py`（新規）
- `ArchitectureRepository/00_Master/PROJECT_MEMORY.md`
- V2／V2.1正本
- Phase 6 checkpoint
- 本報告

既存dirty／untrackedのsource、実データ、監査・設計成果物は
reset、checkout、stage、削除していない。Phase 6専用一時script、画像、pytest領域だけを
正確なpath確認後に削除した。

## 7. Rollback判定

- Phase 5 presentationは`PHASE5_FUSION_ENABLED`境界で停止可能
- old Order Book source／detector／rendererは維持
- Tape表示停止でtrade storageを削除しない
- DOM表示停止でbook analysisを停止しない
- Footprint levelsは既存trade／candle tableから分離
- rollbackでraw／archive／research dataを削除しない
- 現在は新Python image未配備なので、現runtimeに対するdeployment rollback操作は不要

## 8. 現runtime read-only監査

2026-07-28 22:27 JST:

- container: `delta_engine_pro4web-deltaengine_clone-1`
- image作成: 約14時間前
- version: `v3.6.21`
- health: **RED**
- pipeline: `StorageError`でdead
- detail: Parquet write `[Errno 5] Input/output error`
- bar flow／latency: RED
- Cドライブ空き: 768,671,744 bytes（約0.72 GiB）
- `ws_out` drop-oldest counter: read-only log確認時351,364
- Phase 1〜6 Tape／Book stats key: 旧imageのため未提供

process停止／再起動、data削除、Docker build／deployは行っていない。

## 9. 最終運用判定と次の承認境界

| 対象 | 判定 |
|---|---|
| Phase 1〜6 source implementation | PASS |
| isolated restart／reconnect／replay | PASS |
| live no-loss／overflow accounting | PASS |
| browser layout／interaction | PASS |
| full regression | PASS |
| existing runtime activation | **NO-GO** |

次の工程はPhase 7ではなく、独立した運用remediationである。

別承認が必要:

1. disk使用量のread-only inventory
2. 保持／移動／削除対象のユーザー判断
3. dead old container停止／storage I/O復旧
4. Phase 1〜6を含むnew image build
5. production restart／post-deploy health・Tape accounting確認

disk dataを無断削除せず、旧dead containerを無断再起動しない。

## 10. Post-completion operational activation（2026-07-28）

上記NO-GOは22:27 JST時点の履歴として保持する。その後、別承認のoperational remediationを実施した。

- 旧XMTradingの再取得可能なmarket-history cacheだけを限定削除し、C空きを回復
- Phase 1〜6を含むimage
  `sha256:81b5ae72cb4ff2847a914e71863c4870ba2a1383bc6f47983c00d203f7ab5e01`をbuild／配備
- image内Phase 1〜6対象 **116 passed, 4 skipped**
- storage pending 0、Footprint write failure 0
- Tape 151,002 accepted＝151,002 sent、pending／in-flight／dropped 0、balanced true
- Book SYNCED、send failure 0
- Hook drop／disk reject／writer error 0
- production browserでFootprint／LIVE DOM／Tape／3段チャートを確認、console／page error 0
- Binance reconnect／gapの15分window満了後、23:34:23 JSTに全health check GREEN
- 23:37 JSTに新しいBinance ping timeout／book gapが発生しoverall YELLOWだが、
  pipeline／bar／latency／Tape／storage／Bookは正常。upstream degradationとして分離
- deploy後logにStorageError／Traceback／Parquet I/O error再発なし

更新後の判定:

| 対象 | 判定 |
|---|---|
| Phase 1〜6 source implementation | PASS |
| isolated integration／regression | PASS |
| production operational activation | **PASS（upstream feed degradation ACTIVE）** |

完成済みFlow Price Response、3段チャート、8パターン、OI、Strategy／注文authorityは変更していない。
詳細は`FOOTPRINT_DOM_TIME_SALES_OPERATIONAL_REMEDIATION_REPORT_20260728.md`を正とする。
