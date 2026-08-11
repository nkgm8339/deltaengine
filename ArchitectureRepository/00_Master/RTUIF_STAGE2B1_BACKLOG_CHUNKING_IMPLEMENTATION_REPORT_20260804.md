# Realtime UI Freshness 恒久対処 第二段
## Stage 2B-1 — backlog公平性chunk化 実装・検証報告書

**文書ID:** DE05M-RTUIF-HBPRI-STAGE2B1-REPORT-001  
**版:** 1.0 (実装・検証・復元完了 / NO-GO)  
**作成日:** 2026-08-04  
**実施者:** Codex  
**適用指示書:** DE05M-RTUIF-HBPRI-STAGE2B1-INST-001  
**現在判定:** **NO-GO** — backlog chunk化は作動したがrelease/non-destructive gate不達。正規Stage 2B-1 image復元済み。

---

## 0. 着手前基準

- 対象repository: `C:\Users\user\Desktop\DeltaEngine05M`
- 指示書SHA-256: `7fe490ba5188fc2608f311d0cc4a0382f7bfdfbc2efd6b551c2de0ab482422a2` (MATCH)
- 正規Stage 2A `src/pipeline.py`: `9313a7c07d80dc773e36c9d16f22268d3aaf7f1650d563e607085cde8d8b3dac` (MATCH)
- 開始時実物退避: `C:\tmp\rtuif_stage2b1_20260804_033018\pipeline_stage2a_preimplementation.py`
- protected 5件、`webapp/main.py`、`webapp/push_broker.py`は提示開始SHAと全MATCH。
- Stage 2B Stage 1 evidence `C:\tmp\rtuif_stage2b_stage1_20260803_234500`は無変更・保持。

## 1. Stage 1調査承認後の実装

承認範囲内で次を実装した。

- `src/pipeline.py`: ready backlogをevent数32件または連続50msの早い方でevent境界yield。
- `src/config.py`: strict schemaへ2項目を追加し、正の整数のみ許可。
- `config/config.yaml`: shipped default 32 / 50を追加。
- `tests/test_config.py`: shipped/default/非正値・bool拒否を追加。
- `tests/test_live_pipeline.py`: event budget、wall-time budget、順序保持、book同期を検証。

変更していないもの: shutdown後同期drain、book構築・順序・ownership、単一event内部、storage、PushBroker、protected/consumer、timeout 1000/3000ms。

## 2. 専用test checkpoint

**記録時点:** 2026-08-04 03:47:16 +09:00  
**承認範囲:** Stage 2B-1 source/config/test実装と検証。  
**完了済み:** source/config/test実装、専用/config/book整合gate。  
**未完了:** EOL復元、重点回帰、WebApp/repository全体test、hash gate、正規image build、temporary overlay 600秒soak、復元、最終提出。  
**変更file:** `src/pipeline.py`, `src/config.py`, `config/config.yaml`, `tests/test_config.py`, `tests/test_live_pipeline.py`, 本報告書。  
**blockerの限定範囲:** 解消済み。`src/pipeline.py`の既存14行がpatch hunk内でCRLFからLFへ変化したため、開始時実物に基づきEOLだけを復元した。  
**次の再開位置:** WebApp全体test、repository全体test、protected/hash gate。

専用gate最終結果:

```text
37 passed in 6.45s
```

初回は35 passed / 2 failed。failureはテストfixtureが3 eventだけでready backlogを作らず、direct constructorのreorder既定500msによりaccepted観測がshutdownまで遅延したことが原因。shipped liveと同じ`reorder_tolerance_ms=0`、65 event backlogへ修正した。assert契約の削除・緩和は行っていない。

## 3. 改行checkpoint

開始時 `src/pipeline.py`: CRLF 1,314 / LF-only 850。  
実装直後: CRLF 1,300 / LF-only 913。総改行増分49に加えて既存14行のCRLF→LFを検出。  
旧2,164行は内容・順序が開始時実物と全一致、新規は8 block / 49行だけであることを確認した。旧行のEOLを開始実物どおり復元し、新規行は各blockの局所EOLへ合わせた。正規化内容SHAは復元前後で不変。

復元後:

```text
src/pipeline.py  SHA-256 7591fef6cdeed2b1515add62bb4e9eda8ce8df904360cd5304df8a13c9893bae
                 CRLF 1,336 / LF-only 877
config/config.yaml SHA-256 3411cb14b55d228b3c856fe34572857f596f793cd675134535d15b89e7fa9fc0
                   CRLF 122 / LF-only 40
git diff --check: PASS
```

## 4. 重点回帰checkpoint

**記録時点:** 2026-08-04 03:47以降 +09:00  
**完了済み:** config、全live pipeline、snapshot wiring、session VWAP live、WebApp Phase6 integration。  
**未完了:** WebApp全体、repository全体、protected/hash、runtime/soak/復元。  
**blocker:** なし。  
**次の再開位置:** WebApp全体test。

```text
60 passed in 14.51s
```

追加の`LivePipeline.from_config`実物受け渡しassert後:

```text
tests/test_config.py + tests/test_live_pipeline.py: 56 passed in 12.40s
WebApp全体: 1 failed, 201 passed in 15.34s
repository全体最終: 1 failed, 841 passed, 1 skipped in 223.00s
```

唯一のfailureは既知baselineと同じ
`tests/webapp/test_dom_tape_fusion_ui.py::test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation`。
旧selectorを要求する既知不整合で、protected `index.html`は開始SHAと一致する。新規fail 0。

## 5. source/hash gate・runtime build前checkpoint

**完了済み:** 実装・専用/重点/WebApp/repository全体test、EOL、`git diff --check`、protected/Stage 2A成果SHA。  
**未完了:** 正規Stage 2B-1 image build、clean readiness、temporary overlay、600秒soak、分析、正規image復元、最終package。  
**blocker:** なし。  
**次の再開位置:** 現行Stage 2A runtimeを変更せずStage 2B-1正規imageをbuildし、image内source SHAを照合する。

最終source/test SHA:

```text
src/pipeline.py             7591fef6cdeed2b1515add62bb4e9eda8ce8df904360cd5304df8a13c9893bae
src/config.py               df5b727850fa2be15f2ec85dfba0dba1f3b59feeaa485ff5cadd7fc187225a0d
config/config.yaml          3411cb14b55d228b3c856fe34572857f596f793cd675134535d15b89e7fa9fc0
tests/test_config.py        3264d19a495e2325faa213ec1983654bf21dd062dcac747f5a4345459b2a471b
tests/test_live_pipeline.py bb9552c5c8970667ad8d393c83ad7c623a2fcef6f9e3bb9c99e77ff7655c0348
```

開始時正規preimageは
`C:\tmp\rtuif_stage2b1_20260804_033018\pipeline_stage2a_preimplementation.py`
に保持し、SHA `9313a7c07d80dc773e36c9d16f22268d3aaf7f1650d563e607085cde8d8b3dac`。

Stage 2A成果2件とprotected 5件は開始値と全MATCH:

```text
webapp/push_broker.py               953180e969679111fb502f0405cb4d2a691caf707d5b7594c2476a6ec8548a02
webapp/main.py                      adf09b07612ef0817a20779706990f946b50cb17c7879657918e40dd3372d20b
webapp/static/orderbook_heatmap.js  2da8849d8e77ce82066f02e95c996dde75a952f2a900fc02018e4ea74467388b
webapp/static/time_sales.js         f59fec3f3478cc5a9b977c74978c3d8eb7c66e27a479a0b40fcf6d5f18f8d4c2
webapp/static/footprint_canvas.js   987c5da72a7375495eb44bd9910a1b79b076226b2f0206cc8e3d3de2f08c01be
webapp/static/index.html            3a025cd2ef7425e922a962fa80a438b0d31f5e77b9a16732aacfc4f3577c513c
webapp/static/market_freshness.js   65c94cf5f90f37b381b1877c9ed1c4f0e93d92540ff90238dbc5c44af3483a48
```

timeout shipped値は`market_heartbeat_interval_ms=1000` / `market_heartbeat_timeout_ms=3000`のまま。

## 6. image / temporary overlay build checkpoint

**証拠root:** `C:\tmp\rtuif_stage2b1_runtime_20260804_044000`  
**完了済み:** Stage 2B-1正規image build・pin、image内source/protected SHA、config wiring、overlay rebase/build、全`/app` manifest比較、isolated probe。  
**未完了:** 正規image clean readiness、overlay runtime 600秒soak、分析、正規image復元。  
**blocker:** なし。  
**次の再開位置:** predeploy runtime状態を固定後、正規Stage 2B-1 imageへclean recreateしてreadiness gate。

```text
正規Stage 2B-1 image:
sha256:a9c39d4f2e8bdbaf69e20ee7ace13cae5a84616a40f34b25641f615f9aa8de8c

temporary overlay image:
sha256:1d77ffbff68e8d9f8264218a3245139e089fd200063fa218f68209feb3fb74c9
```

正規image内`pipeline.py` / `config.py` / `main.py` / `push_broker.py` / protected 5件はhost最終SHAと一致。configは既存設計どおりruntime bind mountであり、read-only bindしたisolated probeで`config_wiring=32/50`を確認した。

overlayは正規image IDを`FROM`でpin。親1,605 file、overlay 1,607 fileの全`/app` manifest差分は次だけ。

```text
modified: /app/src/pipeline.py
modified: /app/webapp/main.py
added   : /app/src/stage2b_candidate_probe.py
added   : /app/webapp/stage2b_loop_probe.py
```

overlay `pipeline.py`は正規Stage 2B-1実物の旧2,213行と全一致し、temporary計装105行のみ追加。production repository sourceは不変。計装はenv既定OFF、isolated計装ON専用test 3 passed、default-OFF import probe PASS。

## 7. 正規Stage 2B-1 runtime readiness checkpoint

正規Stage 2B-1 imageへclean recreateした。起動直後readiness attemptはWebSocket HTTP handshake前に接続し、初期接続をretryしないhost observer制約で早期終了した。containerはrestart 0 / OOM falseのままstartup完了し、別証拠名のretryはexit 0。

```text
image ID      : sha256:a9c39d4f2e8bdbaf69e20ee7ace13cae5a84616a40f34b25641f615f9aa8de8c
restart / OOM : 0 / false
/health       : ok
/api/health   : GREEN
book          : SYNCED
heartbeat     : upstream SUBSCRIBED / upstream_fresh=true / pipeline_alive=true
sequence gap  : 0
tape          : dropped=0 pending=0 send_failures=0 balanced=true
instrumentation env/file: absent
```

container内source・Stage 2A成果・protected 5件はhost最終SHAと全MATCH。

**完了済み:** 正規image clean recreate/readiness/hash/non-destructive gate。  
**未完了:** temporary overlay clean recreate/readiness、600秒soak、分析、正規image復元。  
**blocker:** なし。  
**次の再開位置:** overlay imageへclean recreateし、readiness PASS後に長時間処理前checkpointを固定して600秒soak。

## 8. temporary overlay readiness / 600秒soak前checkpoint

overlay imageへclean recreateした。正規image時と同じstartup直後observer制約による初回handshake失敗後、startup完了を直接確認し、retryはexit 0。

```text
container ID  : aa67ebf7dec9ca8f31099ae00dfd89327c2bde6c9e38fbe0c378c94dc18bc78e
image ID      : sha256:1d77ffbff68e8d9f8264218a3245139e089fd200063fa218f68209feb3fb74c9
restart / OOM : 0 / false
/health       : ok
/api/health   : GREEN
book          : SYNCED
heartbeat     : SUBSCRIBED / fresh=true / alive=true
sequence gap  : 0
instrumentation files: active
```

host observerはheartbeatに加え、BOOK/TAPE/FLOW/BAR等のtypeと順序fieldを記録するtemporary copyへ拡張した。production/overlay imageは変更せず、observer SHA-256は`c9ea52c42d4da025a7f40304a1c13bb932cc99f7ab7fcbb8b9e6e4474424bab8`、構文PASS。

**長時間処理前記録:** overlay readiness PASS後、600秒canonical測定開始前。  
**完了済み:** overlay build/manifest/isolated probe/clean readiness。  
**未完了:** 600秒observer+cgroup+loop/raw timing、分析、post-soak非破壊gate、正規image復元。  
**blocker:** なし。  
**次の再開位置:** `stage2b1` labelで600秒supervisorを完走し、container内計装logを回収する。

## 9. 600秒soak実測

### 9.1 canonical境界

```text
requested       : 600.0 sec
elapsed         : 600.6856045 sec
observer segment: 1 / exit 0 / 4,657,306 bytes
cgroup samples  : 600 / sampler exit 0
```

graceful stopで計装writerをcloseした完全logを回収し、orchestratorの`started_wall_ns`～`ended_wall_ns`だけを最終集計した。startup/readiness/stop区間は除外。

### 9.2 効果と残存超過

```text
heartbeat                    : 494 / healthy 494 / sequence gap 0
server publish interval max  : 9,081.750ms
browser receive interval max : 9,128.901ms
canary lateness max          : 8,192.738ms
canary >=3000ms              : 10
```

server/browserとも3,000ms未満を満たさず、release gateはFAIL。

ready burst:

| metric | Stage 2B Stage 1 | Stage 2B-1 |
|---|---:|---:|
| event count p95 / max | 19 / 418 | 25 / 32 |
| wall duration p95 / max | 194.383 / 5,413.526ms | 111.668 / 4,947.458ms |

`fairness_yield`は4,832回。event数max 32で二重budgetのevent側上限は直接確認できた。wall p95は短縮したが、maxは単一eventを分割できないため残存した。

raw event:

| kind | n | p95 | max |
|---|---:|---:|---:|
| depth | 6,091 | 97.433ms | 4,923.216ms |
| trade | 35,172 | 9.494ms | 4,133.376ms |

`pipeline.handle_trade` max 4,132.466ms、`storage.tick()` max 1.287ms。storageは引き続き主因でない。

3000ms超10件の直接相関分類:

```text
single event >=3000ms            : 5
other task / queue resume delay  : 5
backlog burst >32 events         : 0
```

単一event型はdepth 3.861～4.923秒、trade 4.133秒等。残りには`hfm_quote_tail_loop`の6.051秒slow callbackや、ready queue get中に他taskへ制御が移った区間が含まれる。したがって旧型の150～354 event連続backlog占有は解消したが、単一eventおよびpipeline外taskを含むloop starvationが残る。

### 9.3 非破壊gate

通常message継続実測:

```text
BAR_UPDATE    1,509
BOOK_UPDATE   1,927
FLOW            578
FLOW_RESPONSE   605
TICK          2,545
TAPE_UPDATE   1,863
```

Tapeは1,863 batch / 34,965 trade、batch内・batch間sequence error 0、dropped sum 0。post-soak APIも`dropped=0 pending=0 send_failures=0 balanced=True`。

Book WebSocket sequence errorは0だが、状態内訳は`SYNCED=1,910 / STALE=16 / RESYNCING=1`。post-soak APIは`book gaps in window: 1`でYELLOW。指示書のbook gap 0 / 全SYNCED条件を満たさないため非破壊gateはFAIL。pipeline exception 0、WS reconnect 0。

### 9.4 soak判定

**NO-GO / runtime反映不可。**

- backlog公平性chunk化自体はmax 32 eventsで作動し、旧大backlog連続占有型は0件。
- server/browser 3,000ms未満は未達。
- 単一event型5件に加え、他task/queue再開遅延5件が残る。
- book gap 1 / STALE・RESYNCING発生により非破壊gate不達。

指示に従いbudget調整、Stage 2B-2実装、別task変更へは進まない。Claude独立検証と次の明示指示を待つ。

## 10. 正規Stage 2B-1 image復元証明

overlayをgraceful stopして計装writerをflush後、pin済み正規Stage 2B-1 imageへclean recreateした。

```text
container ID  : 7dd38166a586a57664b8777ddd534b7fd108a32bd8e219f3d48939627c9aaf3c
image ID      : sha256:a9c39d4f2e8bdbaf69e20ee7ace13cae5a84616a40f34b25641f615f9aa8de8c
restart / OOM : 0 / false
status        : running
instrumentation env / module files: absent
/health       : ok
/api/health   : GREEN
book          : SYNCED / gap 0
heartbeat     : SUBSCRIBED / fresh=true / alive=true
```

復元container内SHA:

```text
src/pipeline.py                     7591fef6cdeed2b1515add62bb4e9eda8ce8df904360cd5304df8a13c9893bae
src/config.py                       df5b727850fa2be15f2ec85dfba0dba1f3b59feeaa485ff5cadd7fc187225a0d
webapp/main.py                      adf09b07612ef0817a20779706990f946b50cb17c7879657918e40dd3372d20b
webapp/push_broker.py               953180e969679111fb502f0405cb4d2a691caf707d5b7594c2476a6ec8548a02
webapp/static/orderbook_heatmap.js  2da8849d8e77ce82066f02e95c996dde75a952f2a900fc02018e4ea74467388b
webapp/static/time_sales.js         f59fec3f3478cc5a9b977c74978c3d8eb7c66e27a479a0b40fcf6d5f18f8d4c2
webapp/static/footprint_canvas.js   987c5da72a7375495eb44bd9910a1b79b076226b2f0206cc8e3d3de2f08c01be
webapp/static/index.html            3a025cd2ef7425e922a962fa80a438b0d31f5e77b9a16732aacfc4f3577c513c
webapp/static/market_freshness.js   65c94cf5f90f37b381b1877c9ed1c4f0e93d92540ff90238dbc5c44af3483a48
```

host production source/test/config/protectedはsoak前最終SHAから変更0。git add / commit / push / branch操作0。

### 10.1 復元後の継続状態

復元readiness時点では`/api/health GREEN`、event lag 0ms、book gap 0だった。その後の最終監査では、同一container / 同一正規image / restart 0 / OOM false / 計装不在のまま次へ変化した。

```text
/api/health : RED
event lag   : 77,807ms
book gap    : 0
reconnect   : 0
pipeline exception: 0
Tape        : dropped=0 send_failures=0 balanced=true
```

正規imageへの復元条件とSHAは維持されているが、runtime freshnessは時間経過後に再劣化した。再起動やbudget調整で状態を隠さず、この実状態を最終提出へ記録する。

## 11. 最終checkpoint

**記録時点:** 600秒soak・closed-log解析・正規image復元後。  
**承認範囲:** DE05M-RTUIF-HBPRI-STAGE2B1-INST-001、2026-08-04実装GO票。  
**完了済み:** 実装、config、専用/波及/全体test、EOL、protected/hash、正規/overlay image、600秒soak、直接相関、非破壊gate、正規image復元、証拠集約。  
**未完了:** release、budget再調整、Stage 2B-2、pipeline外slow task対処。いずれも本GO範囲外。  
**変更file:** `src/pipeline.py`, `src/config.py`, `config/config.yaml`, `tests/test_config.py`, `tests/test_live_pipeline.py`, 本報告書。  
**限定blocker:** server/browser 3,000ms未満不達、book gap 1 / STALE・RESYNCING、単一eventと他task/queue再開遅延。  
**次の再開位置:** Claudeが`stage2b1_gate_analysis.json`と生ログを独立検証し、Stage 2B-2だけでなくpipeline外slow task・book gapを含む次指示範囲をユーザーへ提示する地点。  
**証拠root:** `C:\tmp\rtuif_stage2b1_runtime_20260804_044000`（削除禁止、別承認まで保持）。

本Stageの対象実装・検証・復元作業は完了したがDoD全PASSではないため、COMPLETE/releaseとは判定しない。
