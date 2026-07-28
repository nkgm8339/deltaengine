# Footprint × LIVE DOM × Time & Sales operational remediation report

作成日: 2026-07-28  
対象branch: `feature/footprint-dom-tape`  
状態: **production storage NO-GO／23:47 JST OI Parquet transient I/O remediation中**

## 1. 結論

Phase 1〜6 source implementationは、disk blockerを解消したうえでproductionへ配備した。

- Cドライブ空きは約0.97 GiBから約91.67 GiBへ回復した。
- DeltaEngine raw／research／DuckDB／Parquet／Hook journalは削除していない。
- 現HFM terminalと共通quote fileは削除していない。
- 検証済みnew imageをbuildし、旧RED containerをrecreateした。
- pipeline、bar flow、latency、storage、Footprint persistence、Tape accounting、LIVE DOM、
  Hook captureは復旧した。
- production実browserでFootprint／DOM／Tape／3段チャートを確認した。

23:06 JSTと、重いvalidation終了境界付近の23:18 JSTにBinance stream keepalive ping timeoutが
発生したが、自動再接続後もdata処理を継続した。最後のeventから15分後の23:34:23 JSTに
reconnect／gap／latencyを含む全health checkがGREENへ復帰した。

したがって、Phase 1〜6のproduction operational activationは**PASS**とする。
完成済みFlow Price Responseと3段チャートは変更していない。

ただし23:37:27 JSTにBinance keepalive ping timeout、23:37:33 JSTにbook gapが再発し、
23:37:55 JSTのhealthはreconnect 1／gap 1でYELLOWとなった。pipeline／bar flow／latency／Tapeは
GREEN、storage pending 0、Book SYNCEDであり、配備・永続化障害とは分離した
**upstream feed degradation ACTIVE**として扱う。

## 2. Disk root cause

開始時:

```text
C free: 1,042,132,992 bytes
volume display: 100% used
pipeline: dead
storage error: Parquet write [Errno 5] Input/output error
Hook full capture: accepting false / rejected_disk_low 1
```

稼働containerの`/app/data_05M`はhost Cドライブへのbind mountだった。
container overlayには余裕があり、障害箇所はDocker root filesystemでなくhost storageだった。

user profileをread-only inventoryした結果、最大占有は次だった。

```text
C:\Users\user\AppData\Roaming\MetaQuotes
101,621,060,417 bytes
```

そのうち97,443,020,128 bytesはterminal hash
`28A2DF619FD2B717E8C1EF7860232106`で、`origin.txt`は存在しない`D:\MT5XM`を示していた。
Dドライブ自体も存在せず、最終更新は2026-03-10だった。

## 3. 承認済み限定削除

永久削除したのは次のmarket-history cacheだけである。

```text
C:\Users\user\AppData\Roaming\MetaQuotes\Terminal\
28A2DF619FD2B717E8C1EF7860232106\bases\XMTrading-MT5 2\history
```

削除直前guard:

- resolved absolute path完全一致
- terminal originが`D:\MT5XM`
- Dドライブとorigin pathが不存在
- 全file extensionが`.hc`または`.hcc`
- 合計sizeが90 GB以上

削除結果:

| type | files | bytes |
|---|---:|---:|
| `.hcc` | 18,724 | 79,112,427,936 |
| `.hc` | 2,536 | 18,225,419,594 |
| total | 21,260 | 97,337,847,530 |

保持したもの:

- 現HFM terminal hash `E3E3B02889D32F38295D39BF94B6AD4A`
- `Terminal\Common\Files\DeltaEngine_HFM_quotes_utf8.jsonl`
- 旧terminalのMQL5、config、ticks、trades
- DeltaEngine workspace内の全raw／research／archive data

削除cacheはローカルでは復元不能だが、旧XMTrading terminalを将来再利用する場合はMT5から
market historyを再取得できる。

削除直後:

```text
target exists: false
C free: 98,431,594,496 bytes
```

## 4. New image

compose buildの初回client callは60秒待機上限へ到達したため、旧latestを上書きしない固有tagへ
direct buildした。

```text
tag: delta_engine_pro4web-deltaengine_clone:phase6-remediation-20260728
image ID: sha256:81b5ae72cb4ff2847a914e71863c4870ba2a1383bc6f47983c00d203f7ab5e01
created: 2026-07-28 22:51:58 JST
build context: 333.18 kB
```

`.dockerignore`によりdata、data_05M、config、DuckDB、CSV、Parquetはimageへ収載していない。

deploy前検証:

- host／image間のPhase 1〜6主要13 file SHA-256全件一致
- in-image Phase 1〜6対象: **116 passed, 4 skipped in 39.02s**
- host final full regressionの既存証拠: **661 passed, 1 skipped**

## 5. Production recreate

```text
container ID:
7cee921a82182c3d2fb40ecc170b93b2b26837c1b26e2ec79f8b9fc70ce8e782

image:
sha256:81b5ae72cb4ff2847a914e71863c4870ba2a1383bc6f47983c00d203f7ab5e01

started:
2026-07-28 22:57:04 JST

restart count:
0
```

bind-mounted DuckDB、Parquet、Hook journal、config、staticを保持してrecreateした。

起動直後22:58 JST:

- health GREEN
- pipeline exceptions 0
- bar flow GREEN
- latency GREEN
- storage pending 0
- Hook full capture accepting true／disk reject 0

## 6. Persistence／no-loss

23:06:55 JST:

| check | result |
|---|---:|
| trades processed | 31,607 |
| storage pending | 0 |
| storage high watermark | 308 |
| Footprint bars written | 7 |
| Footprint levels written | 3,073 |
| Footprint write failures | 0 |
| Tape accepted | 31,607 |
| Tape sent | 31,607 |
| Tape pending | 0 |
| Tape dropped | 0 |
| Tape accounting balanced | true |
| Book state | SYNCED |
| Book send failures | 0 |
| Hook full accepted | 35,617 |
| Hook full durable | 35,477 |
| Hook full pending | 139 |
| Hook full dropped | 0 |
| Hook disk reject | 0 |
| Hook writer error | none |

`/api/history/footprints`からproduction保存済みbar 328 levelsをread-backし、
manifestとprice levelsが再起動後history APIへ接続されていることを確認した。

## 7. Production browser

Playwright Chromium、1536 × 1200、DPR 1:

- HTTP 200
- Tape state LIVE
- history 500、live 105、kept 500／500
- virtualized Tape DOM 32／32
- Tape gap 0、drop 0
- LIVE DOM SYNCED、spread 0.1、age 73ms
- Footprint 10 bars LIVE
- Footprint Canvas 696 × 476
- 3段チャート表示
- old Order Book `display:none`
- horizontal overflowなし
- console error 0
- page error 0

Edge headless screenshot経路はbrowser側で終了せず、一時profileのhelper processだけをcommand lineで
特定して停止し、一時profile／logを削除した。通常Edgeとproduction runtimeには影響していない。
同じproduction URLの実browser検証はPlaywright Chromiumで完了した。

この一時Edge process群とvalidation負荷によりWindows pagefileは24,615,258,112 bytesまで
自動拡張した。Docker VHDXは15,332,278,272 bytesとなり、23:11 JSTのC空きは
89,053,814,784 bytesだった。process／temporary directoryはcleanupしたが、pagefile設定や
Windows system fileは変更していない。disk復旧前より十分な余力を維持する。

## 8. Rollback

旧running containerが参照していたconfig digest `e002dfd...`はDocker image tag対象として解決できず、
latest切替後に旧manifest `6f7048...`も参照できなかった。

代わりに、旧running imageと同日同時間帯にbuildされた残存imageを内容確認した。

```text
image ID: sha256:2a8c6d243e6caacc2c1ab29de58062616d098db21bf0e6e9c022c03894d61bcb
tag: delta_engine_pro4web-deltaengine_clone:rollback-pre-footprint-20260728
```

このimageには`webapp/tape.py`、`webapp/book_projection.py`、Footprint Canvas、Phase 6 testがなく、
pre-Footprint imageである。exact旧container imageではないため、その制約を隠さずfallback rollbackとする。

raw／archive／research dataはrollbackでも削除しない。

## 9. 非変更事項

- Flow Price Responseの分類条件
- 3段チャートの計算、構造、操作
- Price／CVD／Delta 8パターン
- OI計算
- Strategy／Hook／Condition／Pattern／Order Triggerのauthority
- LIVE注文、MT5 algorithmic trading
- raw／research data retention
- automatic purge

## 10. 15分window最終確認

23:06 JSTと23:18 JST、Binance streamはkeepalive ping timeoutを記録し、自動再接続した。

- pipeline GREEN
- bar flow GREEN
- Tape GREEN
- storage継続
- Book再同期済み

HealthMonitorは15分window内のreconnect 4をRED、book gap 1をYELLOWとして保持した。
最後のreconnect／gap eventは23:18:45／23:18:50 JSTだった。

23:20 JSTのBinance公式endpoint直接疎通:

- host OI: HTTP 200／662ms
- container time: HTTP 200／73ms
- container OI 5回: 全HTTP 200／32.0〜233.9ms

23:34:23 JST、15分window満了後の最終sample:

| check | result |
|---|---|
| overall／pipeline／bar flow／latency／Tape | GREEN |
| reconnect／book gap | 0／0、GREEN |
| trades processed | 151,002 |
| storage pending | 0 |
| Footprint bars／levels／failures | 35／19,110／0 |
| Book state／send failures | SYNCED／0 |
| Tape accepted／sent／pending／in-flight／dropped | 151,002／151,002／0／0／0 |
| Tape accounting balanced | true |
| Hook accepted／durable／pending | 170,480／170,435／6 |
| Hook drop／disk reject／writer error | 0／0／none |
| Cドライブ空き | 88,926,904,320 bytes（82.82 GiB） |

deploy後37分のcontainer logには新たな`StorageError`、`Traceback`、Parquet
`Input/output error`がない。23:34:23 JST時点までの異常はBinance ping timeout 2件と、それに伴う
book gap 2件だけであり、同sampleではwindowからexpireして全check GREENとなった。

その後23:37:27／23:37:33 JSTに3回目のping timeout／book gapが発生した。
23:37:55 JSTのsampleはoverall YELLOW、reconnect 1、gap 1だが、pipeline／bar flow／latency／Tapeは
GREEN、storage pending 0、Footprint failure 0、Book SYNCED、Tape accepted 164,948／sent 164,945／
pending 3／dropped 0／balanced true、Hook disk reject 0／writer errorなしである。
自動再同期とno-loss accountingは機能しており、限定blockerはBinance WebSocket品質だけである。

## 11. Regression再実行境界

- Phase 6直前host final: **661 passed, 1 skipped**
- deploy image内Phase 1〜6対象: **116 passed, 4 skipped**

operational remediation後のhost全回帰再実行は、既存のaccess-denied監査directoryをpytestが
収集した段階と、Windows sandboxのbasetemp cleanupで結果を確定できなかった。

image全testでは次のruntime packaging境界を確認した。

1. 研究tool用`requests`はruntime requirementsへ未収載のため、当該tool test 1 fileはcollection不能。
2. Strategy contract testは外側`ArchitectureRepository`正本CSVを必要とするが、現composeは
   CHANGELOG以外の外側正本をimage／containerへmountしないため44件がmissing-canonで失敗。
3. 上記を除く結果は611 passed、5 skipped。

これはPhase 1〜6 regression failureではない。Strategy runtimeは未有効であり、今回そのmount／authorityを
拡張していない。将来Strategy runtimeを有効化する前には正本CSVのread-only mount契約が別途必要である。

## 12. 最終判定

| 対象 | 判定 |
|---|---|
| disk／Parquet I/O blocker | RESOLVED |
| Phase 1〜6 image build／production recreate | PASS |
| Footprint persistence／history read-back | PASS |
| Tape no-loss accounting | PASS |
| LIVE DOM／Book resync | PASS |
| Hook durable capture | PASS |
| production browser | PASS |
| 15分post-reconnect health | 23:34 GREEN、23:37 new upstream reconnectでYELLOW |
| production operational activation | **PASS（upstream feed degradation ACTIVE）** |

APIのversion文字列はversion bumpを行っていないため`v3.6.21`のままである。配備identityは
image `sha256:81b5ae72cb4ff2847a914e71863c4870ba2a1383bc6f47983c00d203f7ab5e01`と
container `7cee921a82182c3d2fb40ecc170b93b2b26837c1b26e2ec79f8b9fc70ce8e782`を正とする。

upstream degradationが継続しても、storage／pipeline／Tape accounting／Book resyncが正常である限り
今回のdeploymentをrollbackしない。通常のproduction監視でBinance reconnect、gap、event lagを追跡する。

git stage／commit／pushは行っていない。既存dirty／untracked worktreeを保持した。

## 13. 23:47 JST storage failure再発

15分待機中の23:47:38 JST、OI hourly Parquet temporary writeで
`[Errno 9] Bad file descriptor`／`error closing file`が発生し、background storage workerが
fail closedで停止した。この時点でproduction operational activationのPASSを撤回し、
storage判定を**NO-GO**へ戻す。

- C空き82.83 GiB、disk-lowではない
- container open-file limit 1,048,576、process FD 17、FD exhaustionではない
- OI targetは4,128 bytes／104 rowsとして正常read可能
- failed temporary fileはcleanup済み、既存target破損なし
- `/app/data_05M`はWindows CへのDocker 9p bind mount
- Tape drop 0／balanced、Hook accepting true／disk reject 0／writer errorなし
- storage queue pending 42、pipeline task dead

限定原因はWindows bind mount経路でのtransient file descriptor lossと推定する。
bounded retryを実装・検証し、production再配備後に再判定する。
