# Realtime UI Freshness 恒久対処 第二段
## Stage 2B — Stage 1:event-loopブロッキングcallback特定 調査報告書

**文書ID:** DE05M-RTUIF-HBPRI-STAGE2B-STAGE1-REPORT-001  
**版:** 1.0 (調査完了)  
**作成日:** 2026-08-03  
**実施者:** Codex  
**適用指示書:** DE05M-RTUIF-HBPRI-STAGE2B-STAGE1-INST-004  
**現在判定:** COMPLETE — starvation主因coroutineと内部2モードを実測特定。production無改変・正規image復元済み。

---

## 0. 展開前checkpoint

**記録時点:** 2026-08-03 23:37 +09:00  
**承認範囲:** 可逆overlayによるslow-callback一次観測、候補callback区間計時、wake相関、正規image復元。  
**production source変更:** 0。  
**完了済み:** 現行runtime状態、親image ID、復元基準7件SHAの照合。  
**未完了:** 一次overlay構築・測定、候補確定、候補overlay測定、相関集計、復元。  
**blocker:** なし。  
**次の再開位置:** 正規image内sourceの起動/lifespan/task境界を確認し、一次観測計装をrepository外overlayへ限定実装。

### 0.1 現行runtime

```text
container ID: 9d80072e293c9c6db9a764e96dcc866a5036808cf1e62c8f59be02b684165129
image ID    : sha256:508bb78281aeb797f5e69d90e47a3bcb6c45e5f93e43ebd6273897f87ef6acb6
restart     : 0
OOM         : false
status      : running
health      : RED
sequence gap: 6
reconnect   : 6
pipeline    : GREEN
event lag   : 15,468ms
memory      : 744MB
```

現行runtimeは劣化しているため測定母体にしない。clean recreate後に測定する。

### 0.2 親image・復元基準

親image `sha256:508bb78281aeb797f5e69d90e47a3bcb6c45e5f93e43ebd6273897f87ef6acb6`
は実在しID一致。復元基準7件は指示値と全MATCH。

本Stageではproduction/test/config/timeout/protected/consumer/storage実装を変更しない。

## 1. 一次観測overlay構築checkpoint

**記録時点:** 2026-08-04 00:03 +09:00  
**完了済み:** asyncio slow-callback + loop可用性canary overlay構築、isolated block probe、親/overlay全`/app` SHA比較。  
**未完了:** clean recreate、readiness、600秒soak、一次候補抽出、候補区間計時、相関、復元。  
**blocker:** なし。  
**次の再開位置:** maintenance windowでoverlayをclean recreateし、readiness PASS後に600秒一次soak。

### 1.1 実loopと観測方式

現行processは`uvloop` C実装を使用している(`/proc/1/maps`で
`uvloop/loop.cpython-312-x86_64-linux-gnu.so`を確認)。privateな`_run_once`はPython層に
存在しないため、C loop内部への危険なmonkeypatchは採らない。次の2信号を同時計測する。

- `loop.set_debug(True)`、`slow_callback_duration=0.1`によるuvloop標準slow-callback警告。
- 10ms間隔canaryの実起床間隔・deadline lateness全件。これはselect/poll内部値ではなく、
  callback実行可能性を直接測る安全なloop可用性観測である。

production repositoryは無変更。正規`main.py`のtemporary copyへ次の3 hunkだけを加えた。

1. 観測module import。
2. lifespan開始時のprobe起動。
3. lifespan終了時のprobe停止・flush。

`main.py`の既存改行はCRLF 1043 / LF 96を保持し、新規5行だけCRLFで追加した
(overlay: CRLF 1048 / LF 96)。

### 1.2 overlay実体

```text
evidence root : C:\tmp\rtuif_stage2b_stage1_20260803_234500
parent image  : sha256:508bb78281aeb797f5e69d90e47a3bcb6c45e5f93e43ebd6273897f87ef6acb6
overlay image : sha256:e65d739897efa41a05e96675daf0cf89976c256d5b68a79c535d3d97c76a730a
overlay main  : 33cd050ff7324eb766b216e859333435754932cc2cd9c799d61e434082e74a96
probe module  : 5fec4f2c1584aaa43b5a464f25e79379687d7db199e3a5043b05e892003ed093
```

親/overlayの`/app`全file SHAを比較した。親1237件、overlay 1238件。差分は次の3行だけで、
変更対象は`main.py`と新規観測moduleだけである。

```text
<= adf09b07... /app/webapp/main.py
=> 33cd050f... /app/webapp/main.py
=> 5fec4f2c... /app/webapp/stage2b_loop_probe.py
```

manifest SHA:

```text
parent_app_sha256.txt : d6101d34515a421c6a0f75e80deb83213ac3fea3dc87369119e07a88b35ab340
overlay_app_sha256.txt: aded2747c871394d06b0d550faca13ab23a0075c74d4b4cb36c6b64fec4ea49f
```

### 1.3 isolated probe

production runtimeへ展開する前に、isolated containerで意図的な0.2秒同期blockを1回だけ
発生させた。uvloop slow-callbackは`0.201 seconds`、canaryはinterval
`211.432168ms` / lateness `201.378160ms`を記録した。閾値・時刻結合・background writerが
動作することを確認済み。本番upstreamへの障害注入は行っていない。

## 2. slow-callback一次観測結果

### 2.1 clean recreateとreadiness

一次overlayをclean recreateし、container imageが
`sha256:e65d739897efa41a05e96675daf0cf89976c256d5b68a79c535d3d97c76a730a`、
restart 0 / OOM falseであることを確認した。起動後、CPU約99%かつ`/health`・`/api/health`
20秒timeout、WebSocket opening handshake 15秒timeoutとなった。これは旧劣化containerの継続ではなく、
clean recreateした新containerでstarvationが即時再現した事実である。測定は中止せず、同一の
clean recreate個体で600秒を採取した。

### 2.2 600秒一次観測

```text
measurement elapsed : 605.392 sec
cgroup samples      : 600
CPU mean/p95/max    : 100.087% / 113.863% / 127.243%
cgroup throttle     : nr_throttled delta 0 / throttled_usec delta 0
heartbeat samples   : 305 (全件 pipeline_alive=true / upstream_fresh=true)
browser interval max: 27,546.5353ms
sequence gap        : 0
canary samples      : 3,786
canary lateness max : 17,598.740824ms
lateness >=3000ms   : 28
slow callback count : 665
```

生ログSHA:

```text
primary_loop_observation_full.jsonl : 89856a08ef4d2592f6432e03eb70cfe7e3917382a238c6072dbbe5dd75c5f9bd
stage2b_primary_cgroup.jsonl         : e5ea4b25f2f62aa6b829691e7e68645498a777edd36444ce75e7c12e3594ebab
stage2b_primary_observer...jsonl     : 0aeff57fad88c530184ddab02316457722bf0a8e75fb79719cb3f1e124f38eca
primary_container.log               : da404de2d2c1c30092d5d94b55551cdb0c694666be2d9bc67e64f619db1ee215
stage2b_primary_orchestrator.json    : 36425ba0afe91875a68a490c3e8018b675b3d01634bf9637bf61edacb8555aeb
primary_analysis_v2.json             : f17c7753f95eadc0d8e46f82e015e37650af57a2444c18004ab278c09ed96e0b
```

### 2.3 callback別一次分布

canonical 600秒内の最大占有は`LivePipeline.run_async`で、
`n=643 / mean=712.664ms / p95=2423ms / max=17299ms`。起動後readiness区間では同taskの
36.832秒blockも別途記録した。taskは`/app/src/pipeline.py:1980`で次のqueue取得を待つ直前に観測された。
したがって、1件のraw event受領後から次の`norm_q.get()`へ戻るまでの同期pipeline処理が主候補である。

canonical 600秒の3秒以上canary spikeは28件。最大spikeは17,598.741msで、その直前に
`LivePipeline.run_async took 17.299 seconds`が存在する。28件すべてで直前の最占有coroutineは
`LivePipeline.run_async`だった。
一次観測だけではraw event 1件の重処理かqueue backlogの連続処理かを分離できないため、
候補overlayでqueue待ち、raw event、trade handle、depth path、storage tick、連続ready burstを分離する。

## 3. 候補区間計時overlay checkpoint

**完了済み:** 候補overlay構築、構文検証、isolated writer検証、親/overlay全`/app` SHA比較、600秒測定、復元。  
**未完了:** なし。本Stageでは是正実装を行わない。  
**blocker:** なし。

```text
candidate image : sha256:54b8299e6709393cacb653616fcd08197b703a917bbb5b4ca86ab073c2bc5a94
candidate main  : d6cba80cfd1d3ab061027140bc384e5faa1696bb872a5357234ab1946cb2dcbd
candidate pipe  : 4eec664547132baf1bfc8bb361e0d4addf0d6d79ca46c5a42eef585051cd60d0
candidate probe : 56b7378cfbf1c9836e310e01e5fb8fbf9b8ab20192ccbaea47a97f937a9a32d8
manifest SHA    : 3fe72e2470a934628d1f2ab8cd42f903f204fa4ba2882d26bbf1183a4dcab819
```

親1237件、candidate 1239件の全`/app` manifest差分は、`main.py`、`pipeline.py`、
新規観測module 2件だけ。`pipeline.py`の既存改行CRLF 1314/LF 850を保持し、追加行だけ
周辺改行へ合わせた。計時はpayload・判定・queue順序を変更せず、各境界の前後timestampを
background writerへ渡すだけである。

## 4. 候補callback区間計時結果

### 4.1 canonical測定境界

candidate containerをclean recreateし、600秒のorchestrator境界だけをcanonical集計した。
生ログは回収待ち時間も含むため、`stage2b_candidate_orchestrator.json`の
`started_wall_ns`から`ended_wall_ns`までに限定した`candidate_analysis_v2.json`を正とする。
境界外を含む旧`candidate_analysis.json`は参考資料であり承認根拠に用いない。

```text
measurement elapsed : 601.261 sec
candidate records   : 295,179
cgroup samples      : 600
CPU mean/p95/max    : 88.488% / 110.323% / 134.767%
cgroup throttle     : nr_throttled delta 0 / throttled_usec delta 0
heartbeat samples   : 469 (全件 pipeline_alive=true / upstream_fresh=true)
browser interval max: 7,751.6407ms
canary samples      : 14,446
canary lateness max : 5,456.517861ms
lateness >=3000ms   : 10
```

### 4.2 候補分布

| 候補 | n | mean ms | p95 ms | max ms |
|---|---:|---:|---:|---:|
| `pipeline.ready_queue_burst` | 5,378 | 70.998 | 194.383 | 5,413.526 |
| `pipeline.raw_event` | 30,753 | 11.225 | 47.037 | 3,407.268 |
| `pipeline.path` | 30,753 | 11.184 | 46.909 | 3,407.232 |
| `pipeline.normalize_and_handle` | 24,859 | 3.873 | 8.906 | 3,407.130 |
| `pipeline.handle_trade` | 24,804 | 3.538 | 7.908 | 3,406.431 |
| `pipeline.notify_hook.observe_raw_trade` | 24,858 | 0.067 | 0.118 | 11.795 |
| `pipeline.storage_tick` | 30,753 | 0.002394 | 0.0038 | 3.070 |
| `pipeline.classify_raw` | 30,753 | 0.006 | 0.011 | 1.289 |

raw event種別:

| 種別 | n | mean ms | p95 ms | max ms |
|---|---:|---:|---:|---:|
| depth | 5,894 | 41.740 | 80.740 | 3,234.482 |
| trade | 24,859 | 3.990 | 9.180 | 3,407.268 |

queue取得時に既にqueue非空だった割合は`82.535%`。連続ready burstは
`n=5,378 / event数 mean=5.728 / p95=19 / max=418`である。

### 4.3 wake spike相関表

candidate canonical 600秒で発生した10件を全件示す。全件の直前最占有coroutineは
`LivePipeline.run_async`である。

| canary seq | wake ms | burst ms | burst events | raw events | raw sum ms | max raw ms | max kind |
|---:|---:|---:|---:|---:|---:|---:|---|
| 700 | 4,938.051 | 4,779.968 | 354 | 372 | 739.696 | 33.688 | depth |
| 6611 | 3,539.404 | 1,787.869 | 150 | 389 | 2,907.460 | 191.507 | depth |
| 9703 | 4,143.035 | 3,505.675 | 2 | 3 | 3,612.984 | 3,407.268 | trade |
| 10868 | 3,460.103 | 3,379.991 | 10 | 11 | 88.339 | 50.253 | depth |
| 10870 | 3,409.388 | 3,169.917 | 309 | 310 | 2,843.455 | 209.026 | depth |
| 11916 | 5,456.518 | 5,413.526 | 240 | 241 | 1,252.499 | 45.589 | depth |
| 13960 | 3,007.300 | 200.479 | 5 | 5 | 196.183 | 145.131 | depth |
| 14613 | 4,860.716 | 3,910.961 | 5 | 78 | 4,328.555 | 3,234.482 | depth |
| 14616 | 3,468.953 | 2,940.555 | 165 | 176 | 3,297.209 | 99.912 | depth |
| 14666 | 3,036.894 | 2,804.531 | 292 | 300 | 2,751.453 | 137.539 | depth |

相関表は、次の2モードが共存することを示す。

1. 多数eventの連続処理: 240〜354件等のready backlogを同coroutineが処理し続け、
   2.8〜5.4秒占有する。
2. 単一eventの重処理: trade `handle`最大3.406秒、depth path最大3.234秒。

`LivePipeline.run_async`を単一主因coroutineと特定するが、内部原因は
「backlog時の公平性喪失」と「稀な単一event重処理」の複数である。

## 5. storage / 他callbackの判定

- `BackgroundStorageWriter`はsource上でmarket loopからI/Oを分離している
  (`src/pipeline.py:1487-1495`)。
- loop上の`storage.tick()`はmax 3.070ms。3秒級starvationへ寄与しない。
- candidate container logの`E4001` / `E4003` / `storage` / `parquet`は各0件。
  parquet直列化のloop同期blockは本測定で検出されなかった。
- 一次観測の他callbackは、Tape max 429ms、BookProjection max 262ms、
  Connector max 272ms等で、17.299秒の`LivePipeline.run_async`より一桁以上小さい。
- protected / consumer fileは変更しておらず、Heatmap/Tape/Flow/3段chartのpayload・計算・意味は不変。

## 6. Stage 2B設計判断材料(事実のみ)

### 6.1 処理特性

- 主因はevent-loop上の同期`LivePipeline.run_async` coroutine。
- depth pathとtrade handleはPython同期処理であり、観測区間中のcgroup throttleは0。
  外部quota待ちではなくprocess内CPU占有である。
- storage同期I/Oは主因でない。
- queue ready率82.535%、burst最大418 event。event数またはwall-time budgetで処理を区切り、
  loopへ明示的に制御を返すchunk化は構造上可能である。
- この公平性chunk化はADR-003の単一loop・単一book ownerを維持したまま設計できる見込みがある。
- ただし単一trade/depth event自体が3秒を超えた実測がある。event間yieldだけではこの2件を
  3000ms未満にできない。depth path / trade handle内部の分割可能性、計算量上限、
  executor退避の要否はStage 2設計で別途判断が必要である。

本Stageではchunk化、executor、throttle、timeout変更を一切実装していない。

## 7. 復元証明

測定後、対象serviceを正規Stage 2A imageへclean recreateした。

```text
container ID : fda5f7d4a4552b1d7e3a2a9af221404674735a9944cc5a255dab8d6994439ce9
image ID     : sha256:508bb78281aeb797f5e69d90e47a3bcb6c45e5f93e43ebd6273897f87ef6acb6
restart      : 0
OOM          : false
status       : running
instrumentation env/file/tmp evidence: absent
/health      : {"status":"ok"}
/api/health  : GREEN
```

container内・host repositoryの7件SHAは次と全MATCH。

```text
push_broker.py      : 953180e969679111fb502f0405cb4d2a691caf707d5b7594c2476a6ec8548a02
main.py             : adf09b07612ef0817a20779706990f946b50cb17c7879657918e40dd3372d20b
orderbook_heatmap.js: 2da8849d8e77ce82066f02e95c996dde75a952f2a900fc02018e4ea74467388b
time_sales.js       : f59fec3f3478cc5a9b977c74978c3d8eb7c66e27a479a0b40fcf6d5f18f8d4c2
footprint_canvas.js : 987c5da72a7375495eb44bd9910a1b79b076226b2f0206cc8e3d3de2f08c01be
index.html          : 3a025cd2ef7425e922a962fa80a438b0d31f5e77b9a16732aacfc4f3577c513c
market_freshness.js : 65c94cf5f90f37b381b1877c9ed1c4f0e93d92540ff90238dbc5c44af3483a48
```

production source / test / config / timeout変更は0。git add / commit / pushは0。

## 8. 証拠index

root: `C:\tmp\rtuif_stage2b_stage1_20260803_234500`

| file | bytes | SHA-256 |
|---|---:|---|
| `primary_loop_observation_full.jsonl` | 1,757,294 | `89856a08ef4d2592f6432e03eb70cfe7e3917382a238c6072dbbe5dd75c5f9bd` |
| `stage2b_primary_cgroup.jsonl` | 260,962 | `e5ea4b25f2f62aa6b829691e7e68645498a777edd36444ce75e7c12e3594ebab` |
| `stage2b_primary_observer_segment_000.jsonl` | 141,383 | `0aeff57fad88c530184ddab02316457722bf0a8e75fb79719cb3f1e124f38eca` |
| `stage2b_primary_orchestrator.json` | 1,088 | `36425ba0afe91875a68a490c3e8018b675b3d01634bf9637bf61edacb8555aeb` |
| `primary_analysis_v2.json` | 21,997 | `f17c7753f95eadc0d8e46f82e015e37650af57a2444c18004ab278c09ed96e0b` |
| `candidate_timings_full.jsonl` | 121,666,857 | `69a158077b21a010fd144f3de962eb84d60ec97e012c2d2124d628afb8b614bb` |
| `candidate_loop_observation_full.jsonl` | 3,250,953 | `0a836b1344c3d5cf426de2c9807fdb6844d4fd0c8e9ff820fd6c91216fcf7886` |
| `stage2b_candidate_cgroup.jsonl` | 260,516 | `340878e10af47b8bf8664c3ffce0550d77591e2cca3bf06f1f8a60b32f4d31d5` |
| `stage2b_candidate_observer_segment_001.jsonl` | 190,648 | `4d91787f5cf34aa70e580c274c571d423f7ee969cf577a388f5fce1c8531a6d1` |
| `stage2b_candidate_orchestrator.json` | 1,644 | `d1d633ba77def7bba241b410e0590f798c2de3ef0760be2ec68cd341fbf67310` |
| `candidate_container.log` | 10,507 | `b79b6cbcef719e92942845629fee9d008e0346c463b54d02058ff111b9705d32` |
| `candidate_analysis_v2.json` | 10,935 | `0dd20e4a2fe06c39b28d2f265575d1d9db4685575375a91e7963b781413283b8` |
| `candidate_app_sha256.txt` | 236,194 | `3fe72e2470a934628d1f2ab8cd42f903f204fa4ba2882d26bbf1183a4dcab819` |

overlay image / context / raw logはClaude独立検証完了まで保持する。

## 9. 結論

Stage 2B Stage 1のDoDを満たした。starvation主因は
`LivePipeline.run_async`であり、共有broadcast lock、PushBroker priority queue、storage障害、
container throttleは原因でない。内部ではready backlogの長時間連続処理と、稀な単一
depth/trade eventの3秒超同期処理が共存する。

Stage 2B是正の設計・実装は未着手。次段は本実物と生ログをClaudeが独立検証した後、
ユーザーの明示GOを待つ。
