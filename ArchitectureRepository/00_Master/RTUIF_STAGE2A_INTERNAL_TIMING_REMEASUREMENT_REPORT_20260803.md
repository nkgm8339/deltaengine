# RTUIF Stage 2A — 内部timing再測定報告書

**文書ID:** DE05M-RTUIF-HBPRI-STAGE2A-REMEASURE-REPORT-001  
**版:** 1.0 (再測定・復元完了)  
**作成日:** 2026-08-03  
**実施者:** Codex  
**適用ディスパッチ:** DE05M-RTUIF-HBPRI-STAGE2A-REMEASURE-003  
**現在判定:** **COMPLETE / Q1・Q2確定** — shared lock寄与は実質消失。健全区間の残余はevent-loop wake starvation主体。正規image復元済み。

---

## 0. 展開前checkpoint

**記録時点:** 2026-08-03 22:20 +09:00  
**承認範囲:** 準備済みoverlayによる計装ON 600秒soak、観測、正規Stage 2A imageへの復元。  
**production source変更:** 0。  
**完了済み:** 現行runtime状態固定、親/overlay image実在・ID一致確認、compose override確認。  
**未完了:** overlay clean recreate、readiness、600秒soak、健全/転落区間分離集計、正規image復元。  
**blocker:** なし。  
**次の再開位置:** overlay imageを計装env ONでclean recreateし、readiness gateを確認。

### 0.1 現行runtime

```text
container ID: 4634608463c21691da9fc3be986676e1af816aac1a49946faa52444b3f66656a
image ID    : sha256:508bb78281aeb797f5e69d90e47a3bcb6c45e5f93e43ebd6273897f87ef6acb6
restart     : 0
OOM         : false
status      : running
health      : RED
pipeline    : RED (E4003 -> E4001)
```

現行containerは劣化済みのため測定母体にしない。ディスパッチ承認範囲内のclean recreateで
置換する。

### 0.2 image ID照合

```text
親/復元先:
sha256:508bb78281aeb797f5e69d90e47a3bcb6c45e5f93e43ebd6273897f87ef6acb6 MATCH

計装overlay:
sha256:dd3c5ec726817c117977fb4dbac68eb7d5ef0a3ecd7e044d3b505b4e427957f5 MATCH
```

overlay overrideは`RTUIF_HBPRI_STAGE1_INSTRUMENTATION=1`を設定する。新規計装codeは
追加しない。repository source、protected、consumer、timeout、storage実装は変更しない。

---

## 1. 計装overlay展開・readiness checkpoint

**記録時点:** 2026-08-03 22:27 +09:00  
**完了済み:** overlay clean recreate、startup完了、readiness条件確認。  
**未完了:** 600秒soak、内部timing/健全区間集計、storage時系列、正規image復元。  
**blocker:** なし。  
**次の再開位置:** 600秒observer+cgroup同時計測。

```text
container ID: 56e1421ce66828a3cebb5176127750aeaba0609f0f7e840b202175df54446aed
image ID    : sha256:dd3c5ec726817c117977fb4dbac68eb7d5ef0a3ecd7e044d3b505b4e427957f5
instrumentation env: RTUIF_HBPRI_STAGE1_INSTRUMENTATION=1
restart     : 0
OOM         : false
status      : running
```

既存readiness scriptのstartup前初回接続はHTTP response前EOF。startup完了後のretryは
health GREENとBOOK SYNCEDを記録したが、同scriptが1 messageごとにhealth APIを同期取得して
高頻度配信に追いつかず、slow-client隔離(code 1013)となった。これはserverのqueue 256
overflow時に当該clientだけを閉じる確定挙動であり、runtime全体はGREENを維持した。

同じ既存observerの高速drain `measure`を12秒実行してreadinessを補完:

```text
heartbeat count : 12
sequence        : 238..249 (gap 0)
upstream_state  : 全件 SUBSCRIBED
upstream_fresh  : 全件 true
pipeline_alive  : 全件 true
receive errors  : 0
ping errors     : 0
health          : GREEN
BOOK_UPDATE     : SYNCED (readiness retry生記録)
restart         : 0
OOM             : false
```

readiness gateは上記の独立記録を合わせてPASSと判定する。計測用fast-drain observerは
slow-client隔離されず、同じWebSocket配信経路を通る。

---

## 2. 計測attempt 1 — observer早期切断と既存orchestrator制約

600秒run開始後、observerは約21.66秒で次を記録してexit 3となった。

```text
heartbeat received : 1 (sequence 327, pipeline_alive/fresh=true)
first ping RTT      : 3,928.693ms
receive error       : ConnectionClosedError code 1013
ping error          : TimeoutError
```

code 1013はStage 2Aの当該client queue overflow/slow-client隔離で使用する唯一のclose code。
runtime全体を閉じたものではない。一方、health APIもその直後12秒timeoutとなり、単なる
observer処理遅延だけでなくruntime event-loop側の飢餓を同時に観測した。

既存`stage1a_run_pair.py`はobserverが早期終了するとsamplerを固定90秒だけ待ち、今回の
runでは`TimeoutExpired`でsamplerをterminateした。このためattempt 1は600秒soakとして
不成立。生observer/cgroup/logは破棄せず保持する。

この制約はproduction/overlay計装点ではなくhost側測定orchestratorに限られる。今回の
「途中転落しても600秒継続」に合わせ、既存observerをsegment単位で再接続し、cgroup
samplerはobserver切断と独立して600秒継続するhost側supervisorを証拠directory内に置く。
repository source・overlay imageは変更しない。

---

## 3. 計測attempt 2 — 600秒完走

### 3.1 clean recreate・readiness

attempt 1のlogを固定後、同一overlay imageをclean recreateした。

```text
container ID: ffbdc20e362d409d21ef04c1a4fbeffdf42026c09027c6dd2073ae7d554bc82f
image ID    : sha256:dd3c5ec726817c117977fb4dbac68eb7d5ef0a3ecd7e044d3b505b4e427957f5
restart     : 0
OOM         : false
```

readiness生記録:

```text
health_ok=true
api_green=true
subscribed=true
book_synced=true
ready=true
heartbeat sequence=10
upstream_state=SUBSCRIBED
upstream_fresh=true
pipeline_alive=true
```

readiness exit 0。直後に600秒測定を開始した。

### 3.2 取得継続性

```text
requested duration : 600.0 sec
orchestrator elapsed: 610.101 sec
cgroup samples     : 600
sampler exit       : 0
observer segments  : 9
```

segment 000は281.499秒後にWebSocket keepalive ping timeout(1011)で終了。segment 001〜006は
接続確立前にexit 1、segment 007は再接続して219.741秒取得後に同じ1011、segment 008は
接続確立前に終了した。各切断・接続不能区間自体を証拠として保持し、cgroupとcontainer内部
traceはobserver状態と独立して600秒継続した。

---

## 4. 健全区間・転落区間の分離

observerが受領したheartbeat 139件をpayload契約で分離した。

| 区分 | 条件 | 件数 |
|---|---|---:|
| 健全 | `SUBSCRIBED && upstream_fresh=true && pipeline_alive=true` | 134 |
| 転落 | 上記を満たさない | 5 |

健全trace 134件はcontainer traceとsequence結合。malformed trace 0、健全trace send error 0。

転落5件はsequence 131〜135、2026-08-03 22:50:00〜22:50:04 +09:00。

```text
upstream_state=RECONNECTING
upstream_fresh=false
pipeline_alive=true
```

すなわち、このattemptではpipeline taskは死亡していない。observer再接続間にはsequence
125→131の欠落が1区間あるため、外部全体seriesの160秒級intervalは連続heartbeat間隔として
扱わない。以下の判定はsequence連続かつ健全な132 intervalだけを正とする。

| 健全・sequence連続 | n | mean | p95 | max |
|---|---:|---:|---:|---:|
| server生成間隔 | 132 | 2,823.425ms | 12,061.502ms | **28,883.246ms** |
| browser受信間隔 | 132 | 3,069.004ms | 12,489.228ms | **46,361.162ms** |
| published→receive age | 132 | — | 3,334.997ms | **32,024.095ms** |

健全server interval 3000ms以上は26件。Stage 2Aの3000ms release gateは再測定でもFAIL。

---

## 5. 内部timing直接測定

### 5.1 健全trace統計

| metric | n | min ms | mean ms | p95 ms | max ms |
|---|---:|---:|---:|---:|---:|
| event-loop wake lateness | 134 | 0.000 | 1,797.037 | 10,842.904 | **27,886.800** |
| client集合lock wait | 134 | 0.0014 | 0.0046 | 0.0090 | **0.0176** |
| queue scheduling wait | 134 | 0.0367 | 70.028 | 294.334 | **1,499.522** |
| actual `send_text()` | 134 | 0.0827 | 0.415 | 0.980 | **10.602** |
| enqueue→delivery完了 | 134 | 0.150 | 791.999 | 3,233.018 | **32,027.659** |
| `send_market_heartbeat()` enqueue await | 134 | 0.0403 | 0.106 | 0.199 | **0.396** |

`shared_broadcast_lock_present=true`は0件。Stage 2A後のlockはclient集合snapshot用の短時間
lockであり、network I/Oを含まない。

### 5.2 3000ms超過26区間の寄与度

Stage 1Aと同じ「直前heartbeat成分 + 当該heartbeat wake成分」の比較軸を用いた。
Stage 2Aではqueue/sendがsleepと非同期に重なるため、wakeとqueueを単純加算すると約1%の
重複が生じ、残差が負になる。この点を明示したうえで内訳を示す。

超過時間(`interval - 1000ms`)合計: 224,423.262ms。

| component | 合計 ms | 超過時間比 |
|---|---:|---:|
| client集合lock wait | 0.100 | **0.000045%** |
| queue scheduling | 2,181.672 | 0.972124% |
| actual send | 17.667 | 0.007872% |
| enqueue awaitその他 | 2.124 | 0.000946% |
| event-loop wake lateness | 224,483.156 | **100.026688%** |
| 非同期重複・timestamp残差 | -2,261.457 | -1.007675% |

3000ms以上の単独成分件数:

```text
wake lateness   : 22
client lock wait: 0
queue scheduling: 0
actual send     : 0
```

最大健全区間はsequence 154→155:

```text
server interval : 28,883.246ms
wake lateness   : 27,886.800ms
client lock wait: 0.002ms
queue scheduling: 74.070ms
actual send     : 0.144ms
```

### 5.3 Q1 / Q2回答

**Q1:** Stage 1Aのshared lock寄与86.083%は、Stage 2A後0%。代わって存在するclient集合
lock寄与は0.000045%、最大0.0176ms。shared lock waitは実測上消失し、Stage 2Aの構造是正は
所期どおり効いている。

**Q2:** 健全区間の残余はevent-loop wake lateness主体。最大28.883秒区間の27.887秒を
wakeが占め、超過26区間の比較軸でも約100%。Stage 2Bはevent-loop starvation / CPU飽和を
標的として設計着手可能である。

---

## 6. CPUとstorage時系列

### 6.1 cgroup

| metric | n | mean | p95 | max |
|---|---:|---:|---:|---:|
| CPU raw | 599 | 98.380% | 115.577% | 131.710% |
| sampler補正後CPU | 599 | 98.299% | 115.495% | 131.639% |
| memory | 600 | 391.979MiB | 476.934MiB | 555.020MiB |

補正後CPU 100%以上は340/599 sample。OOM kill 0→0、PIDs 23固定。

最初の健全outlierはsequence 38→39、22:44:00.570→22:44:04.767 +09:00。

```text
server interval: 4,196.997ms
wake lateness  : 3,196.803ms
```

前後±5秒の補正後CPUはmean 88.368%、p95 118.537%、max 131.386%。wake outlierと
one-core超のCPU sampleが同一窓で共起した。

### 6.2 storage因果

attempt 2のcontainer log全期間:

```text
E4001 count: 0
E4003 count: 0
```

それでも健全区間に26件の3000ms超過、最大28.883秒のserver gap、wake最大27.887秒が
発生した。したがってstorage failureはheartbeat starvationの必要条件ではなく、
Stage 2Bのevent-loop starvation調査をstorage是正の完了待ちにする根拠はない。

一方、前runでstorage failureがpipeline停止を悪化させた事実は維持する。本attemptだけで
両者が常に完全独立とは断定せず、「storage failureなしでもstarvationは再現する」と確定する。

---

## 7. 正規image復元証明

計装log・inspect・終了healthを固定後、正規Stage 2A imageへclean recreateした。

```text
container ID: 9d80072e293c9c6db9a764e96dcc866a5036808cf1e62c8f59be02b684165129
image ID    : sha256:508bb78281aeb797f5e69d90e47a3bcb6c45e5f93e43ebd6273897f87ef6acb6
restart     : 0
OOM         : false
status      : running
health      : GREEN
instrumentation env: absent
```

復元container内SHA-256:

| file | SHA-256 | 判定 |
|---|---|---|
| `push_broker.py` | `953180e969679111fb502f0405cb4d2a691caf707d5b7594c2476a6ec8548a02` | MATCH |
| `main.py` | `adf09b07612ef0817a20779706990f946b50cb17c7879657918e40dd3372d20b` | MATCH |
| `orderbook_heatmap.js` | `2da8849d8e77ce82066f02e95c996dde75a952f2a900fc02018e4ea74467388b` | MATCH |
| `time_sales.js` | `f59fec3f3478cc5a9b977c74978c3d8eb7c66e27a479a0b40fcf6d5f18f8d4c2` | MATCH |
| `footprint_canvas.js` | `987c5da72a7375495eb44bd9910a1b79b076226b2f0206cc8e3d3de2f08c01be` | MATCH |
| `index.html` | `3a025cd2ef7425e922a962fa80a438b0d31f5e77b9a16732aacfc4f3577c513c` | MATCH |
| `market_freshness.js` | `65c94cf5f90f37b381b1877c9ed1c4f0e93d92540ff90238dbc5c44af3483a48` | MATCH |

repository production source、protected、consumer、storage実装、timeout変更0。

### 7.1 復元後の継続状態

復元gateのhealth GREENは2026-08-03 22:55:31 +09:00に直接確認した。その後、解析終了時の
23:19:14 +09:00に再確認するとcontainerは同じ正規imageのままrunning / restart 0 /
OOM false / 計装envなしだが、healthはREDへ変化していた。

```text
sequence_gap=RED: 5
ws_reconnect=RED: 5
pipeline=GREEN
bar_flow=GREEN
latency=YELLOW: 3493ms
memory=GREEN: 673MB
tape=GREEN
```

復元後logの確認範囲ではE4001/E4003は検出されていない。復元条件自体はPASSしたが、
正規imageも時間経過後に再劣化しておりrelease可能状態ではない。追加再起動・設定変更は
行わず、この状態を最終checkpointへ記録する。

---

## 8. 主要証拠SHA-256

証拠directory:

```text
C:\tmp\rtuif_stage2a_remeasure_20260803_222100
```

| file | bytes | SHA-256 |
|---|---:|---|
| `attempt2_readiness.jsonl` | 6,544 | `2fa80fc8419165b88302db879af0f58890a876270f72f2f68feb14f644cbe456` |
| `stage2a_remeasure_attempt2_cgroup.jsonl` | 260,561 | `9779e313c2e7f5f5c91a22869d059da0a170b74302952eb8b8d04e8bf3f803a6` |
| `stage2a_remeasure_attempt2_orchestrator.json` | 5,364 | `63544b965d050f8ba47767f43f165f4b50a5a29f39d1078066fc79f2a59be5c2` |
| `attempt2_container.log` | 235,483 | `ae8c1296d4f9d2604b67eccd44312b20d69c41f9550e17fe83883120a01e8d32` |
| `attempt2_container_inspect.json` | 13,000 | `e97d7044ae3d1ff5c2dc8ba8466aa5d29da23ecb2e3af4d61921d2880bec6149` |
| `attempt2_post_soak_health.json` | 165 | `b90769e80ba59b1709d380d85f581b33f8d42e9c2e7b547d6f8037adaebdd383` |
| `stage2a_remeasure_supervisor.py` | 5,788 | `d710cc37de88bc41b5b694800e4b32016f4da037b43fcd0204ee650040800682` |
| `stage2a_remeasure_analyze.py` | 19,519 | `ed10277c7f4f95baa4ec0d15a08a7d6684e7a710ccec1164b75eb0cfec660e59` |
| `stage2a_remeasure_attempt2_analysis_final.json` | 35,678 | `16493f8e0208aff9e19094b2af144d5f0890893cd4ff9a69a019ad2566dd82e1` |
| `stage2a_remeasure_attempt2_cpu_timeline_v2.json` | 1,258 | `f2f995382dd081f3eca5a26482cb3dede9b41e9a0ec8d48294b2ed8630ba0703` |

observer segment 000 SHA:
`66e0aaadc778a079f0f32fae60c622a87140c5fc4db79c025594473e9db33f70`。
segment 007 SHA:
`d6666b942de528c00fc13d858eff9df0ec2fdefe39a090f078290ba5582c1003`。
他segmentは接続失敗を示すmeasurement_start 1行で、実物を保持する。

健全連続interval寄与度row canonical SHA-256:

```text
083754371e3f3197b21ca6e42e2da35275259811dde8de289ba54452dad6f450
```

---

## 9. 完了checkpoint

**記録時点:** 計装ON 600秒soak、集計、正規image復元後。  
**完了済み:** ディスパッチDoD 1〜6。  
**変更file:** 本報告書のみ。production/test/config変更0。host側測定scriptと全証拠は`C:\tmp`に保持。  
**runtime:** 正規Stage 2A imageへ復元直後health GREENを確認。最終再確認時はhealth RED(sequence gap 5 / reconnect 5)、pipeline GREEN、restart 0、OOM false、計装envなし。  
**Q1:** shared lock寄与消失、Stage 2A構造是正は所期どおり。  
**Q2:** wake starvation主体、Stage 2Bはevent-loop / CPU飽和を標的とする。  
**storage:** 本attemptはE4001/E4003なしでstarvation再現。storage是正はstarvation調査の前提ではない。  
**次のgate:** Claude独立検証後、ユーザー明示GOを受けてStage 2B設計着手。  
