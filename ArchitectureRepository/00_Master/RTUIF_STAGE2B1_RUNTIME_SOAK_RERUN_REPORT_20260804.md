# Realtime UI Freshness 恒久対処 第二段
## DeltaEngine05M — Stage 2B-1 Runtime Soak 再実測報告書

**文書ID:** DE05M-RTUIF-STAGE2B1-SOAK-RERUN-20260804  
**作成日:** 2026-08-04  
**対象repository:** `C:\Users\user\Desktop\DeltaEngine05M`  
**最終判定:** **NO-GO** — 遅延効果gateはPASSしたが、strict非破壊gateの「全BOOK_UPDATE SYNCED」が1件の一時STALEで不達。

## 0. 結論

Stage 2B-1 backlog chunk化を組み込んだ正規imageを親にtemporary overlay計装を再構築し、
600秒のcanonical runtime soakを完走した。

遅延効果は明確にPASSした。

- canary lateness max: **414.631ms**
- server heartbeat生成間隔 max: **1,356.872ms**
- browser相当WebSocket observer受信間隔 max: **1,450.038ms**
- 3,000ms超: **0件**
- ready burst wall max: **313.454ms**
- ready burst event max: **23件**

したがって、このrunにはbacklog型、単一event型、other task／queue resume型の
3,000ms超は存在しない。3000ms超の分類結果は全分類0件である。

一方、canonical窓のBOOK_UPDATE 3,143件は`SYNCED=3,142 / STALE=1`だった。
Book sequence error 0、API book gap 0で、STALEの次のBOOK_UPDATEはSYNCEDへ戻ったが、
指示書のstrict条件「全SYNCED維持」を満たさない。よってruntime効果だけを理由にreleaseせず、
総合判定をNO-GOとする。Stage 2B-2、budget変更、timeout変更へは進まない。

## 1. 事前状態

- 正規Stage 2B-1 image:
  `sha256:a9c39d4f2e8bdbaf69e20ee7ace13cae5a84616a40f34b25641f615f9aa8de8c`
- 開始container:
  `7dd38166a586a57664b8777ddd534b7fd108a32bd8e219f3d48939627c9aaf3c`
- restart 0 / OOM false / running
- `/health=ok`、`/api/health=GREEN`
- book gap 0、pipeline exception 0、event lag 0ms
- Tape dropped 0 / send failure 0 / balanced true
- container内計装module不在
- hostとcontainerのsource/config/protected 10件SHAは正本値と一致

対象10件の開始・終了SHA:

```text
src/pipeline.py                     7591fef6cdeed2b1515add62bb4e9eda8ce8df904360cd5304df8a13c9893bae
src/config.py                       df5b727850fa2be15f2ec85dfba0dba1f3b59feeaa485ff5cadd7fc187225a0d
config/config.yaml                  3411cb14b55d228b3c856fe34572857f596f793cd675134535d15b89e7fa9fc0
webapp/main.py                      adf09b07612ef0817a20779706990f946b50cb17c7879657918e40dd3372d20b
webapp/push_broker.py               953180e969679111fb502f0405cb4d2a691caf707d5b7594c2476a6ec8548a02
webapp/static/orderbook_heatmap.js  2da8849d8e77ce82066f02e95c996dde75a952f2a900fc02018e4ea74467388b
webapp/static/time_sales.js         f59fec3f3478cc5a9b977c74978c3d8eb7c66e27a479a0b40fcf6d5f18f8d4c2
webapp/static/footprint_canvas.js   987c5da72a7375495eb44bd9910a1b79b076226b2f0206cc8e3d3de2f08c01be
webapp/static/index.html            3a025cd2ef7425e922a962fa80a438b0d31f5e77b9a16732aacfc4f3577c513c
webapp/static/market_freshness.js   65c94cf5f90f37b381b1877c9ed1c4f0e93d92540ff90238dbc5c44af3483a48
```

## 2. temporary overlay

既存証拠を上書きせず、次の新規証拠rootを作成した。

`C:\tmp\rtuif_stage2b1_runtime_rerun_20260804_090000`

正規image tagを`FROM`へ固定してtemporary overlayを再buildした。

- overlay tag: `rtuif-stage2b1-instrumentation:20260804-rerun-090000`
- overlay image ID:
  `sha256:e57276297e3fba9378fbf2b24da61a9ed6911b399128b04febc92249cd900fb2`
- overlay container:
  `0a0f6ed92ed72d6d805e955dc485f0b93ce2015bfc095cb20f55683568d324d6`
- restart 0 / OOM false

親1,605 file、overlay 1,607 fileの`/app`全manifest差分は次の4件だけだった。

```text
modified  src/pipeline.py
modified  webapp/main.py
added     src/stage2b_candidate_probe.py
added     webapp/stage2b_loop_probe.py
```

removedは0。production repository sourceは計装のために編集していない。
overlay readinessは`ready=true / health_ok=true / api_green=true /
subscribed=true / book_synced=true`でPASSした。

## 3. canonical 600秒soak

```text
start JST       2026-08-04T09:12:26.614+09:00
end JST         2026-08-04T09:22:27.178+09:00
requested       600.0 sec
elapsed         600.5639729 sec
observer        1 segment / exit 0 / 5,122,951 bytes
cgroup sampler  exit 0 / 600 samples
```

closed計装log全体には承認待ち中のcanonical外区間も含むため、集計はsupervisorの
`started_wall_ns`から`ended_wall_ns`までに限定した。

## 4. 遅延・backlog実測

| metric | n | p95 | max |
|---|---:|---:|---:|
| canary lateness | 14,053 | 143.957ms | **414.631ms** |
| server heartbeat interval | 557 | 1,193.902ms | **1,356.872ms** |
| browser observer receive interval | 557 | 1,231.800ms | **1,450.038ms** |
| ready burst wall | 7,502 | 99.977ms | **313.454ms** |
| ready burst events | 7,502 | 13 | **23** |
| raw depth event | 5,818 | 94.404ms | **241.314ms** |
| raw trade event | 19,554 | 10.550ms | **313.387ms** |
| `pipeline.handle_trade` | 19,527 | 9.207ms | **312.446ms** |
| `storage.tick()` | 25,372 | 0.004ms | **2.202ms** |

補足:

- fairness yield 3,302回。
- fairness yield終了burstはevents max 23、wall max 313.454ms。
- queue ready比率83.446%、観測max qsize 782でも、一burstの連続処理は23件以内だった。
- cgroup CPUはp95 113.344%、max 126.539%、CPU throttle delta 0。
- 旧150〜354 event連続backlog型はこのrunで0件。

## 5. 3,000ms超の分類

```text
spikes >=3000ms                0
backlog型                      0
単一event型                    0
other task / queue resume型    0
```

最大raw eventは313.387ms、最大canary latenessは414.631msであり、
分類対象となる3,000ms超は発生しなかった。このrunの直接証拠からStage 2B-2の必要性を
確定してはならない。

## 6. 非破壊gate

### PASS項目

- heartbeat 558 / healthy 558
- heartbeat sequence gap 0
- `pipeline_alive=true` / `upstream_fresh=true`
- Book WebSocket sequence error 0
- API book gap 0
- Tape 1,965 batch / 19,527 trade
- Tape dropped sum 0、batch内／batch間sequence error 0
- post-soak API pipeline exception 0、WS reconnect 0
- 通常message継続:
  - BAR_UPDATE 1,533
  - BOOK_UPDATE 3,143
  - FLOW 504
  - FLOW_RESPONSE 584
  - TICK 2,632
  - TAPE_UPDATE 1,965

### FAIL項目

Book sync state:

```text
SYNCED 3142
STALE     1
```

唯一のSTALEはstream `943a2683-f3fc-4801-8574-a5666e075742`、
book sequence 4488、last update ID 11205083945001。直前はSYNCED、次のBOOK_UPDATEも
SYNCEDで、sequence errorおよびAPI gapは0だった。それでも「全SYNCED」の文字どおりの
gateは不達と判定する。

canonical終了430.822秒後に保存されたpost-soak APIはevent lag 5,433msでYELLOWだった。
これはcanonical delay集計へ混ぜていないが、運用状態として隠さず記録する。

## 7. 正規image復元

overlayをgraceful stopし、計装writerをflushしてclosed logを回収した。

初回復元時、`docker compose up`がbase composeの`build:`を実行し、正規pin tagを
host再build image `sha256:d5c78792...`へ一時的に付け替えた。GREENやSHA一致だけで
復元完了とせず、identity不一致として即時訂正した。保存済み正規tag
`rtuif-stage2b1-normal:20260804-044000`が期待IDと一致することを確認し、pin tagを戻し、
`--no-build --pull never`でexact recreateした。誤build imageは削除していない。

最終復元状態:

```text
container ID : 0b997ee8eeaa301b710c38d62d5c345a769537f810b43092d654760471b647df
image ID     : sha256:a9c39d4f2e8bdbaf69e20ee7ace13cae5a84616a40f34b25641f615f9aa8de8c
restart/OOM  : 0 / false
status       : running
readiness    : ready=true / api GREEN / SUBSCRIBED / book SYNCED
instrumentation modules: absent
```

2026-08-04 09:44:46 JSTの最終API:

```text
state GREEN
book gap 0
pipeline exception 0
event lag 0ms
Tape dropped 0 / send failure 0 / balanced true
```

host／containerの上記10件SHAは終了時も全MATCH。

## 8. 証拠

証拠root:

`C:\tmp\rtuif_stage2b1_runtime_rerun_20260804_090000`

主要証拠:

- `evidence/stage2b1_rerun_orchestrator.json`
- `evidence/stage2b1_rerun_observer_segment_000.jsonl`
- `evidence/stage2b1_rerun_cgroup.jsonl`
- `evidence/candidate_timings_closed.jsonl`
- `evidence/loop_observation_closed.jsonl`
- `evidence/candidate_analysis_closed.json`
- `evidence/stage2b1_rerun_gate_analysis.json`
- `evidence/overlay_post_soak_api_health.json`
- `evidence/restore_exact_readiness.jsonl`
- `evidence/restore_exact_container_inspect.json`
- `evidence/restore_exact_container_sha256.txt`
- `evidence/final_api_health.json`
- `evidence/final_host_sha256.txt`

closed log SHA:

```text
c5cc6e717bd5f58b4c87c49223dde6a2e258f870de1d218e88a8a8ac0b5ba37b  candidate_timings_closed.jsonl
8f65cf378261ef4b68b7773ea0e6435bff77767f41c1d01c2944c1877275219c  loop_observation_closed.jsonl
```

## 9. 最終境界

- source本体、protected、timeout値、UI freshnessの変更0。
- `git add` / `commit` / `push` / branch操作0。
- Stage 2B-2、budget再調整、timeout緩和へ進んでいない。
- runtime効果gate: PASS。
- strict非破壊gate: FAIL（BOOK_UPDATE STALE 1件）。
- 総合: **NO-GO**。次の変更はユーザーの新しい明示指示待ち。
