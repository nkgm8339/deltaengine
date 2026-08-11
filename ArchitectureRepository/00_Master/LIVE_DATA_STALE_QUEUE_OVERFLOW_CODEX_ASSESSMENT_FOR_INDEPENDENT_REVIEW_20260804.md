# DeltaEngine05M — LIVE市場データSTALE／内部キューoverflowに関するCodex見解書

- 文書目的: ユーザーが別の専門家・AI・実装者へ提示し、Codexの判断を独立に吟味してもらうため
- 作成日時: 2026-08-04 23:24 JST以降
- 対象repository: `C:\Users\user\Desktop\DeltaEngine05M`
- 文書の性格: Codex自身の見解。承認済み仕様、実装指示、修復完了報告ではない
- 今回の変更: 本文書1件のみ
- 今回未実施: 製品source変更、config変更、test変更、image build、container restart、deployment、Git操作

## 0. 結論

2026-08-04 22:48 JSTに画面へ出た
`MARKET DATA STALE — LIVE DECISION DATA DISABLED · TICK_SOURCE_STALE`は、
誤表示でも、単にブラウザ表示だけが遅れた事象でもない。

確認済みの直接原因は、DeltaEngine内部の共通`receiver_out` queueが上限10,000件へ到達し、
`drop_oldest_log`規則により受信済みraw eventを破棄したことである。
同時にmain consumerの処理がsource timeへ追いつかず、数十秒から100秒超の遅延が発生した。
ブラウザのfreshness guardは、その古いTICKを拒否して正しくfail closedした。

同日に実装されたLIVE DOM修復は、次の限定不具合を修正している。

1. `DepthSyncCoordinator`の二重owner
2. `pu` chain不連続後の破損buffer再利用
3. `SYNC_FAILED`後に再armされず永久停止する問題

今回のruntimeではBook gap後にLIVE DOMが`SYNCED`へ復帰しているため、この限定修復は機能している。
一方、その修復は、共通queueの処理能力不足、raw event破棄、main consumerのthroughput不足を
対象にしていなかった。したがって「LIVE DOM永久停止修復」と
「市場データ全体が高負荷でも遅延・欠損しないこと」を同一の完成条件として扱ってはならない。

Codexの現時点の判定は次のとおりである。

```text
LIVE DOM terminal固定の修復          : 限定的に有効
高負荷時の内部queue overflow         : 未修正、再現中
raw eventのend-to-end no-loss        : 不成立
市場データのsource-time freshness    : 不成立
現runtimeを売買判断へ使用            : NO-GO
恒久修正の実装                       : 未承認・未実装
無バグの事前保証                     : 不可能
隔離・検証gate後の再設計可能性       : あり。ただし第三者レビューが必要
```

## 1. ユーザーへ明示すべきだったCodexの3つの誤り

### 1.1 誤り1 — `NO-GO`を完成に近い状態として扱った

`RTUIF_STAGE2B1_RUNTIME_SOAK_RERUN_REPORT_20260804.md`の最終判定は、冒頭から明確に
`NO-GO`である。遅延効果gateはPASSしたが、BOOK_UPDATE 3,143件中1件が`STALE`で、
strict非破壊gateを満たしていなかった。

それにもかかわらず、後続説明でStage 2B-1を「freshness問題を直した基盤」に近い意味で扱い、
`NO-GO`であることをユーザー判断の中心へ置かなかった。これは判断上の誤りである。

さらに、LIVE DOM修復後の対象回帰は74件＋65件が合格したが、repository全体pytestは
実行harnessの125秒制限で完走していなかった。runtime反映後の最初の確認も約2分である。
全体回帰未完走と短時間観測を残したまま、ユーザーが「完全に直った」と受け取れる説明をしたことも、
この誤りに含まれる。

### 1.2 誤り2 — 修復対象の範囲を明確に分けなかった

2026-08-04 20:26 JST以降の修復は、depth同期のowner、buffer、rearmを対象にした。
`LIVE_DOM_COMPLETE_REPAIR_ANALYSIS_REPORT_20260804.md`自身も、32 event／50msのchunk化維持、
timeout不変、他の完成済み機能不変を修復境界としている。

この修復後の`book_synced=true`を、市場データ経路全体が恒久的にfreshでno-lossになった証拠のように
受け取れる説明をしたことが誤りである。Bookの同期整合性と、event source timeの鮮度は別条件である。

### 1.3 誤り3 — 赤帯確認直後、証拠取得前に上流要因へ寄せて説明した

画像の赤帯がLIVE DOMの`RESYNCING`とは別の`TICK_SOURCE_STALE`である点は正しかった。
しかし、health、WebSocket payload、queue overflow logを確認する前に、Binance上流の瞬断・遅延を
主候補として説明した。後続の直接証拠は、主要因がDeltaEngine内部のqueue滞留と破棄であることを示した。

原因を確定する前に、以前観測された上流DNS／timeout事象へ説明を寄せたことが誤りである。

## 2. 今回確認した事実

### 2.1 runtime identity

2026-08-04 23:24:51 JSTのread-only確認:

```text
container image : sha256:a1cd6406b3c95150803e653507af241b3b72b6e02b996419f60294cdadaa70d0
started at      : 2026-08-04T11:57:33.06639803Z
restart count   : 0
OOM killed      : false
```

### 2.2 health／stats

同時刻の`/api/health`と`/api/stats`:

```text
health state               : RED
event lag                  : 147,520ms
book_synced                : true
book_projection_state      : SYNCED
book_gaps_detected         : 18
book_resyncs               : 18
tape_dropped_trades        : 0
tape_accounting_balanced   : true
```

この組合せは矛盾ではない。

- `book_synced=true`は、現在適用したSnapshot／DIFFのupdate ID chainが成立していることを示す。
- `event lag=147,520ms`は、その処理対象eventが実時間から約148秒遅れていることを示す。
- したがって「構造上SYNCEDだが、source timeとして古い板／約定」は成立する。

### 2.3 `receiver_out` overflow

container logの確認結果:

```text
first:
2026-08-04T13:00:32.179866064Z
E9002 queue 'receiver_out' overflow: dropped oldest (count=1)

last sampled:
2026-08-04T14:19:41.292890535Z
E9002 queue 'receiver_out' overflow: dropped oldest (count=2810)
```

JSTでは、最初の確認済みoverflowは22:00:32、最後のsampleは23:19:41である。
23:24:51までにlog上2,810件のraw eventが`receiver_out`で破棄された。

一方、connector直後の`ws_out`について、同じcontainer起動期間のoverflow logは0件だった。
したがって今回確認した破棄位置は、WebSocket受信そのものより後、DataReceiverからmain consumerへ
渡す境界である。

### 2.4 Book gapとの時間的対応

同じcontainer起動期間のBook gap logは18件だった。

```text
first:
2026-08-04T12:07:10.610421302Z
E3004 order book gap detected ...

last sampled:
2026-08-04T14:19:41.398377508Z
E3004 order book gap detected ...
```

23:19:41 JSTの最後のgapは、同時刻の`receiver_out` overflow直後に発生している。
また22:49:42 JSTおよび22:52:33 JSTにも、大量overflowとBook gapが同時刻帯に記録された。

共通queueはtrade、depth、liquidationを混在保持しているため、oldest dropにdepthが含まれれば
update ID gapになる。今回の時間的一致と実装構造は、内部overflowがBook gapを発生させたという
因果を強く支持する。ただし、各drop eventのtypeを保存した専用counterがないため、
2,810件すべての内訳までは未確認である。

### 2.5 local WebSocketで確認したTICKの古さ

22:53 JST台にlocal `/ws`を12秒観測した。

```text
TICK received          : 68
first source_age_ms    : 42,020
last source_age_ms     : 44,811
BOOK_UPDATE received   : 32
last BOOK event_time   : 2026-08-04T13:53:04.087Z
last projection_time   : 2026-08-04T13:53:48.702Z
reported book age_ms   : 184
```

TICKは届いていたが、届いたTICK自体が42〜45秒古かった。
またBOOKの`age_ms=184`は小さく見えるが、`event_time`と`projection_time`の差は約44.6秒だった。
これは、backlog内の古いdepthを「いま適用した」ためmonotonic ageが小さくなることを示す。
`age_ms`だけではsource-time freshnessを保証できない。

### 2.6 Binance側との切り分け

22:54 JST台にBinance Futures公式RESTのserver timeと最新tradeを直接取得した。

```text
local UTC             : 2026-08-04T13:54:03.7148007Z
Binance server UTC    : 2026-08-04T13:54:07.154Z
latest trade UTC      : 2026-08-04T13:54:07.530Z
local - server        : -3,439ms
local - latest trade  : -3,815ms
```

PC clockはBinanceより約3.4秒遅れていたが、Binance公式最新tradeはほぼ現在時刻だった。
DeltaEngine内TICKの42〜45秒遅延、後続healthの147秒遅延をBinance側source delayだけでは説明できない。

### 2.7 CPU

22:54 JST前後の`docker stats --no-stream`ではcontainer CPUが約101.56%だった。
単一Python／uvicorn processが主負荷であり、少なくともそのsampleでは1 CPU core相当を飽和させていた。
これはarrival rateがservice rateを上回る説明と整合するが、どのcallbackが何%を占有したかは
profiler未実施のため未確認である。

## 3. 実装から確認できる故障経路

現在の主要経路は次である。

```text
Binance combined WebSocket
  -> ws_out queue                  max 10,000 / drop_oldest_log
  -> DataReceiver
       -> raw recorder.write()
       -> receiver_out queue       max 10,000 / drop_oldest_log
  -> LivePipeline main consumer 1本
       -> liquidation normalize
       -> depth sync / book apply
       -> raw Hook observation
       -> trade normalize
       -> CVD / Flow / Footprint / detectors / callbacks
       -> storage.tick()
```

設定は`config/config.yaml`の次である。

```yaml
queue:
  default_depth: 10000
  overflow_policy: drop_oldest_log
  pipeline_chunk_max_events: 32
  pipeline_chunk_max_wall_ms: 50
```

Stage 2B-1の32 event／50ms chunk化は、ready backlogを長時間処理してevent loop上の他taskを
starvationさせる問題へ対処する。これは公平性改善であり、1秒当たりの総処理能力を増やす契約ではない。

今回のように持続的にarrival rateがservice rateを上回る場合、50msごとにyieldしてもqueueは増え続ける。
10,000件へ達するとoldest raw eventが破棄される。したがってStage 2B-1の存在と今回のoverflowは両立する。

## 4. データ完全性への影響

`DataReceiver`はraw recorderへ書いた後、`receiver_out.put()`を行う。
このため、raw recorderが正常に動いていたeventはoffline再構築へ使える可能性がある。
ただし、raw recorderの対象stream、durable commit、同期間の欠落有無は別監査が必要であり、
本書ではraw完全保存を断定しない。

`receiver_out`でdropされたeventは、少なくともlive main consumerへ到達していない。
したがって次のlive派生値の完全性は保証できない。

- CVD
- Delta
- Footprint
- Flow Price Response入力
- Absorption／Imbalance等のtrade依存検出
- accepted trade以降をsourceとするTape accounting
- depth chainとLIVE DOM／Heatmap
- downstream DuckDB／Parquetの該当live processed data

特に`Tape dropped=0 / balanced=true`は、Tape batcherが受理した後のaccountingである。
`receiver_out`で先にdropされたraw eventはTapeのaccepted分母へ入らない。
したがって現在のTape GREENをend-to-end no-lossの証拠にしてはならない。

## 5. 監視の不足

現行`/api/stats`はBook、Tape、storage等を表示するが、少なくとも今回のresponseには次がなかった。

- `ws_out` current size／high watermark／overflow count
- `receiver_out` current size／high watermark／overflow count
- event kind別drop count
- connector messages outとmain consumer processedの差
- event kind別source lag
- Book `event_time -> projection_time` lag

そのため、raw eventが2,810件破棄されても、`pipeline exception=0`、`Tape GREEN`、
`book_synced=true`が同時に成立した。最上段のTICK freshness guardがREDにしたことで利用停止できたが、
healthの原因表示はqueue data lossを直接示していない。

## 6. 「永久修正できるか」に対するCodexの見解

### 6.1 修正可能な範囲

今回と同じ内部原因について、次を設計目標にすることは技術的に可能である。

- trade burstがdepth処理を詰まらせない
- depth burstがtrade処理を詰まらせない
- authoritative raw eventを`drop_oldest`で黙ってlive計算から失わない
- source lagをboundedに保つ
- gap／disconnect時に古い状態を表示しない
- 復旧後にrestartなしで再arm／再同期する
- raw ingressからstorage／analysisまでend-to-end accountingする

### 6.2 保証できない範囲

次は事前に絶対保証できない。

- 新規実装に未知bugが1件もないこと
- 無限の受信量でも遅延しないこと
- Binance、DNS、回線、OS、diskが永久に停止しないこと
- 一度もgapやreconnectが起きないこと

したがって「バグを絶対に出さない」という条件へ、Codexが真実としてYESと答えることはできない。
保証できるのは、未検証candidateをproductionへ入れず、既知failureを決定論的に再現し、
定量gateを通らない限り切り替えず、異常時にfail closed／rollbackする工程である。

## 7. 恒久対処として第三者に検討してほしい構造

以下は提案であり、承認済み実装仕様ではない。

### 7.1 先に測定すべき項目

architectureを決める前に、overflow期間のraw記録を使い次を測定する必要がある。

1. stream別arrival rateの平均、p95、p99、最大1秒／5秒burst
2. trade／depth／liquidation別service time
3. `handle_trade()`内module別時間
4. Hook raw observer、Footprint、Flow、WebSocket callback、storage enqueueの個別時間
5. `ws_out`／`receiver_out`の時系列qsizeとdrop type
6. per-drop warning logがoverloadを増幅した量
7. 1 CPU core制約、GIL、Docker CPU limitの実状態

per-drop warningがlog stormとして負荷を増幅する可能性はあるが、現時点では仮説であり、
主原因と断定しない。

### 7.2 分離候補

独立レビューで比較すべき少なくとも二案:

#### 案A — stream別live lane

```text
Trade connection -> Trade専用ordered queue -> Trade consumer
Depth connection -> Depth専用ordered queue -> Depth sync/book consumer
Liquidation      -> 専用queue             -> Liquidation consumer
```

利点:

- trade burstとdepth gapを分離できる
- stream別capacity／lag／dropを監視できる
- ownerと順序契約を明確にできる

注意:

- cross-streamの完全な全順序は存在しないため、source timeとreceived timeの結合契約が必要
- moduleが共有mutable stateを直接変更しないowner設計が必要
- trade分析自体がservice rate不足なら、Trade lane単独でもoverflowする

#### 案B — durable ingress journalを正本とするfan-out

```text
Ingress -> durable append / sequence accounting
             -> Depth consumer
             -> Trade analytics consumer
             -> UI latest projection
```

利点:

- live consumerが遅れてもraw正本を失わず再開可能
- end-to-end offsetで欠落を検出できる
- live derived stateをrebuildしやすい

注意:

- disk latency、writer durability、backpressure、recovery offsetの設計が必要
- live判断へ必要なlatency budgetを別に満たす必要がある
- journalが新しい単一障害点にならない検証が必要

Codexの現時点の暫定見解は、案Aだけでなく、少なくともauthoritative ingress accountingまたは
durable replay可能境界を併用すべきである。ただし、profiling前に採用案を確定してはならない。

## 8. 実装を許可する前に必要なgate案

外部reviewerが修正案を採用する場合も、production変更前に最低限次を要求すべきである。

### 8.1 再現gate

- 2026-08-04 overflow期間のraw rate／順序を再現
- 現行baselineが同じ条件でoverflow／lagすることを確認
- 故障を再現できないtestで修復効果を主張しない

### 8.2 accounting gate

event kindごとに次を一致させる。

```text
connector accepted
= raw durably recorded
= consumer accepted + explicitly rejected
= analysis accounted
= storage accounted
```

invalid payload等のrejectは件数と理由を独立計上し、dropと混ぜない。

### 8.3 load gate

- 観測済み最大burst以上の事前固定負荷
- 短時間burstと持続高負荷を分離
- queue drop 0
- duplicate 0
- per-stream order violation 0
- internal原因Book gap 0
- source lagを事前固定上限内に維持
- CPU／memory／diskへ安全余裕を残す

「最大の何倍」「何分／何時間」は、raw測定後に外部reviewerが固定すべきであり、
Codexが証拠なしに数字を決めるべきではない。

### 8.4 failure gate

- Binance disconnect
- DNS failure
- REST snapshot timeout
- queue near-capacity
- consumer exception
- disk slowdown／writer停止
- process restart
- browser reconnect

各故障で、古いデータをLIVE表示せず、状態を明示し、復旧後は同runtimeで再開できることを確認する。

### 8.5 regression gate

完成済みの次を変更しないか、結果差0を証明する。

- Flow Price Response
- 3段チャート
- CVD／Delta
- Footprint／POC／VA／Imbalance
- LIVE DOM／Heatmap
- Time & Sales
- OI
- Hook／Strategy／executionの既存権限境界

### 8.6 activation gate

- isolated candidateで全gate完了
- shadow運転中はproduction decisionへ接続しない
- 外部reviewerとユーザーが証拠を確認
- rollback対象と復元時間を実測
- 明示承認後のみ切替
- 短時間GREENを完成証拠にしない

## 9. 現在のデータと運用に関する暫定勧告

第三者判断が出るまでのCodex見解:

1. `MARKET DATA STALE`中は売買判断へ使用しない。
2. `book_synced=true`だけを正常判定にしない。
3. 2026-08-04 22:00:32 JST以降のlive derived dataは、完全性監査前に研究正本へ混ぜない。
4. 再起動はqueueを空にする一時復旧であり、恒久修正と呼ばない。
5. queue size増加やfreshness timeout延長だけで問題を隠さない。
6. raw recorderから欠落期間を再構築可能か、別途read-only監査する。
7. CVD等の累積状態がdrop後に正しくreseedされたか確認するまで、正確性を断定しない。

## 10. 外部reviewerへ確認してほしい質問

1. `receiver_out` overflowを今回の主要因とする因果判断は十分か。
2. trade／depthのconnectionとconsumerを分離すべきか。
3. durable ingress journalをlive正本にすべきか。
4. 1 consumer内でmodule別batch化／別process化する場合、順序とstate ownershipをどう固定するか。
5. CVD、Flow、Footprintを全trade no-lossで処理する現実的capacityはいくらか。
6. queue overflow時にsession全体をinvalid化し、どの境界からreseedすべきか。
7. Bookの`age_ms`へsource-time lag gateを追加すべきか。
8. Tape accountingの分母をconnector／receiverまで拡張すべきか。
9. per-drop logをrate-limitしつつ、silent lossを防ぐ監査方式は何か。
10. production activationに必要なpeak倍率、継続時間、soak期間は何か。
11. 現在のdirty worktreeと未完了full regressionを前提に、正常baselineをどう確立するか。
12. 修正前に現在のruntimeを停止すべきか、観測専用fail-closedで維持すべきか。

## 11. 参照した主要証拠

- `ArchitectureRepository/00_Master/PROJECT_MEMORY.md`
- `ArchitectureRepository/00_Master/RTUIF_STAGE2B1_RUNTIME_SOAK_RERUN_REPORT_20260804.md`
- `ArchitectureRepository/00_Master/RTUIF_STAGE2B1_BACKLOG_CHUNKING_INSTRUCTION_V1_20260804.md`
- `ArchitectureRepository/00_Master/LIVE_DOM_COMPLETE_REPAIR_ANALYSIS_REPORT_20260804.md`
- `ArchitectureRepository/00_Master/LIVE_DOM_COMPLETE_REPAIR_ANALYSIS_CHECKPOINT_20260804.md`
- `ArchitectureRepository/00_Master/LIVE_DOM_RESYNC_INCIDENT_CHECKPOINT_20260804.md`
- `Delta_Engine_Pro4web/config/config.yaml`
- `Delta_Engine_Pro4web/src/acquisition/event_queue.py`
- `Delta_Engine_Pro4web/src/acquisition/receiver.py`
- `Delta_Engine_Pro4web/src/pipeline.py`
- `Delta_Engine_Pro4web/src/monitor/health.py`
- `Delta_Engine_Pro4web/webapp/book_projection.py`
- `Delta_Engine_Pro4web/webapp/push_broker.py`
- `Delta_Engine_Pro4web/webapp/static/market_freshness.js`
- `C:\Users\user\Pictures\2026-08-04 22 48 50.png`
- 2026-08-04 22:50〜23:24 JSTのread-only `/api/health`、`/api/stats`、local `/ws`、
  `docker logs --timestamps`、`docker stats --no-stream`、Binance Futures公式REST確認

## 12. 最終自己評価

Codexは、限定修復の技術的成功とシステム全体の恒久正常化を明確に分けず、
`NO-GO`証拠をユーザー判断の中心へ置かず、初動説明を証拠取得前に上流要因へ寄せた。
ユーザーがCodex単独の判断を信用せず、第三者レビューを要求するのは、今回の経緯から合理的である。

本書は修正許可を求めるものではない。第三者が原因、影響、提案、gateを独立に検証し、
誤りがあれば訂正するための材料である。
