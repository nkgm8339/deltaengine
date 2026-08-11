# Realtime UI Freshness 恒久対処 第二段
## Stage 1A — temporary instrumentation 直接測定 報告書

**文書ID:** DE05M-RTUIF-HBPRI-STAGE1A-REPORT-001  
**版:** 1.0  
**作成日:** 2026-08-03  
**実施者:** Codex  
**対象指示書:** DE05M-RTUIF-HBPRI-STAGE1A-INST-001  
**状態:** COMPLETE — Stage 1A測定完了／親image復元PASS

---

## 0. Checkpoint — 2026-08-03 18:30 +09:00

### 承認範囲

- 劣化containerの読取専用証拠固定。
- `C:\tmp`のtemporary overlay build contextとimage内だけで、`main.py`／
  `push_broker.py`のheartbeat経路を計装。
- repository内source／test／config、protected領域、Heatmap／Tape／Flow Price Response／
  3段chart／Hook／Strategyは変更禁止。
- runtime recreate／instrumented image切替は、指示書指定のmaintenance承認境界。
- Git操作は禁止。

### 完了済み

1. 現行containerを特定。
   - name: `delta_engine_pro4web-deltaengine_clone-1`
   - container ID: `e2aab8bca1e53ef4f7a831aba4e8b23fe28a7a6e710cc67986af1e7666fa2854`
   - image ID: `sha256:9c4674c5b56638ae7f8ca629091558dd654e4b2c3572c46fbccf3a5525d88f10`
   - started: `2026-08-03T05:07:25.298497138Z`
   - restart count: 0
   - OOMKilled: false
2. §1.1の読取専用証拠を`C:\tmp\rtuif_stage1a_20260803_182344`へ固定。
3. host／container source 7件のSHA-256がStage 1開始値と全件一致。
4. 証拠固定時点の一時点stats:
   - CPU: 31.76%
   - memory: 689.2 MiB / 3.708 GiB
   - PIDs: 21 (`pids.current`は23)
   - cgroup `oom_kill`: 0
   - PID 1 FD数: 18
5. endpoint再確認:
   - `/health`: HTTP 200、192.056ms。
   - `/api/health`: HTTP 200、436.239ms、state YELLOW。
   - 以前記録された30秒timeout後に応答性が回復しているため、過去の劣化証拠を
     上書きせず時点差として扱う。

### 証拠file

| file | SHA-256 |
|---|---|
| `container_inspect.json` | `8c39fc6be6a80e4b37940888172e4c7119c3546a4e950e20fae297cba18e755c` |
| `parent_image_inspect.json` | `848edda7b7ea0815c573b939097269523e9cb616e144fd5125f1013ad6a00a95` |
| `docker_logs_stdout.log` | `c03a335bfd17bac26c106a0677523fe728186fb72d2a29b36e8654eaa0c0d7f6` |
| `docker_logs_stderr.log` | `bf832d8eab4629860eee3b2ecb27d06770ca532c3cc685b7d1ff25787e49bf5d` |
| `docker_stats.txt` | `5aded7f6811e055029ef209fe10ca688efc89394593d4eecaf7201021ddf25ac` |
| `container_readonly_metrics.txt` | `f1afb8557b0f72975dd17086b436f2076b72bd562175c35b995759b043b3e104` |
| `docker_diff.txt` | `3cbd695396b6cb47c191809ea32e9ee0b61356d5d603c48dc90d65d445d7fd2d` |
| `host_source_hashes.json` | `ce2b6da8875aacf97f3fe80a7ce62cb83a59e7d169dbdc463872ecb7fa8ced3d` |
| `container_source_hashes.txt` | `2e506f534d6cfb618250b642cea7ff8fdaffbce4a1934f948bcbcc7f24b4190a` |
| `endpoint_health.json` | `3a57ee21dedaaddbece39884bdd344aacccad5e85635b077d5a0003307d7d7ed` |

### 変更file

- 本報告書のみ。
- repository内source／test／configの変更なし。
- temporary evidence fileは上記`C:\tmp`配下のみ。

### 未完了

- temporary overlay hunk作成・image build・境界hash照合。
- clean baseline 600秒測定。
- instrumented 600秒測定。
- 親imageへの完全復元と最終hash照合。
- 直接測定統計、canonical series SHA-256、寄与度判定。

### Blockerと再開位置

- 現時点のblockerなし。
- 再開位置: SHA確認済み2 fileだけをtemporary contextへcopyし、heartbeat限定計装を適用する。

---

## 1. Checkpoint — 2026-08-03 18:58 +09:00

### 完了済み

1. `C:\tmp\rtuif_stage1a_20260803_182344\overlay_context`へ、開始SHA一致を確認した
   `main.py`／`push_broker.py`だけをcopyし、heartbeat限定instrumentationを適用。
2. repository非汚染を確認。
   - host `main.py`: `7fadb2e281a996e97c2fd496803dec6627b14043e1b9ed9c3eec837d0ce95dc1`
   - host `push_broker.py`: `4c0409b73f14661ef3a33f9f3f870385e0b3311da1deb65e03b8b937efe43fd8`
3. temporary overlay imageを構築。
   - parent: `sha256:9c4674c5b56638ae7f8ca629091558dd654e4b2c3572c46fbccf3a5525d88f10`
   - child: `sha256:69e4b38e43a3a533abcdb8546a37bc56165f1d970441062144011c2de37c9933`
   - BuildKitは`FROM sha256:<local ID>`をregistry名として扱ったため初回buildはlayer生成前に失敗。
     完全parent IDから専用aliasを作り、alias解決IDをbuild前後に完全照合した。
     build logでも`FROM ...@sha256:9c4674c5...d88f10`への解決を確認。
4. image境界を確認。
   - parent layer数8、child layer数10。
   - childの先頭8 layersはparentと順序込みで完全一致。
   - 追加2 layersはDockerfileの`main.py`／`push_broker.py`各COPYに対応。
   - child内の`index.html`、`market_freshness.js`、protected 3件はparent SHAと一致。
   - child内Python構文検証PASS。
5. network-none使い捨てcontainerでinstrumentation境界probeを実施。
   - ON: heartbeat sequence 1,2,3。各recordに直接wake／lock wait／client send timestampあり。
   - OFF: instrumentation record 0、trace保持0、通常heartbeat送出1件。
   - ON probe log SHA-256: `81da26cbd81d151e7c73a3d0f1c576450b79f08d548e19a158974c1702020c19`
   - OFF probe log SHA-256: `e752eb0b0c67d1e6155026a06995c98088d1bdb5175e5156b48dfc2d92ca20ad`
6. 測定helperをtemporary evidence directoryへ作成し、構文検証PASS。
   host `websockets` versionは15.0.1。
7. 親／計装compose overrideを`docker compose config`で展開し、実行前検証PASS。
   - parent configにinstrumentation envなし。
   - instrumented configだけ`RTUIF_HBPRI_STAGE1_INSTRUMENTATION=1`。
   - 親／子とも完全IDから作った専用aliasを使用。

### 原因分類（ユーザー指定の文書記載）

本件の分類階層は次のとおりである。

`マーケットデータ配信周り`
→ `WebApp／Realtime UI基盤周り`
→ `WebSocket配信・鮮度監視周り`
→ `PushBroker／heartbeat処理`

直接の不具合箇所は下位2層であり、Heatmap／chart描画処理そのものではない。

### 変更file

- repository内: 本報告書のみ。
- temporary context／evidence:
  - `overlay_context/Dockerfile`
  - `overlay_context/webapp/main.py`
  - `overlay_context/webapp/push_broker.py`
  - `instrumentation_probe.py`
  - `stage1a_observer.py`
  - `cgroup_sampler.py`
  - `stage1a_parent.override.yml`
  - `stage1a_instrumented.override.yml`
  - §0および本節に記載した証拠log／inspect／hash file。

### 検証結果

- production service／画面／設定の変更なし。
- production container IDは`e2aab8...`のまま、親image ID`9c4674c5...`で稼働。
- repository内source／test／configの変更なし。
- Git操作なし。

### Blockerの限定範囲

- clean recreateは稼働containerを置換するため、指示書§1.4のmaintenance window明示GOが必要。
- blockerはruntime切替と、それに直接依存するbaseline／instrumented各600秒測定だけ。
- temporary image、context、証拠は削除せず保持中。

### 未完了と再開位置

- clean parent imageでのrecreate、readiness gate、baseline 600秒。
- instrumented image切替、readiness gate、直接測定600秒。
- 親imageへの完全復元、source/protected hash、health／SUBSCRIBED／BOOK確認。
- 統計・canonical series hash・寄与度・Stage 2B要否の確定。
- 再開位置: maintenance GO受領後、親aliasの解決IDを再照合して対象serviceだけを
  `--no-build --force-recreate --no-deps`でclean recreateする。

---

## 2. Checkpoint — 2026-08-03 19:15 +09:00

### maintenance GOとclean baseline

- ユーザーのmaintenance GOを受領。
- 対象serviceだけを親imageでclean recreate。
  - before container: `e2aab8bca1e53ef4f7a831aba4e8b23fe28a7a6e710cc67986af1e7666fa2854`
  - after container: `71325ee2944da80fee7287d098e05f3cc0d453b13fd23108f393ef8a8dd9eb9c`
  - image: `sha256:9c4674c5b56638ae7f8ca629091558dd654e4b2c3572c46fbccf3a5525d88f10`
  - restart count 0、instrumentation envなし。
- readiness初回はtemporary helperが実type`BOOK_UPDATE`を`BOOK`と誤記したため
  `book_synced=false`の偽陰性。180秒間に`BOOK_UPDATE`を1,112件受信しており、product
  不具合ではない。helperだけを修正し再実行。
- readiness再実行はhealth GREEN／SUBSCRIBED／BOOK SYNCED／pipeline aliveの全条件PASS。
- baseline開始前のcontainer内source／protected 7件SHAは期待値と一致。

### clean baseline 600秒結果

- 実測時間: 600.922秒。
- cgroup sample: 600（interval 599）。observer exit 0、sampler exit 0。
- heartbeat: 472件、interval 471、sequence gap 0、fresh契約違反0。
- ping: 600件、receive error 0、ping error 0。

| metric | n | min | mean | p95 | max |
|---|---:|---:|---:|---:|---:|
| CPU raw % | 599 | 54.245 | 85.636 | 107.071 | 121.132 |
| CPU sampler除外 % | 599 | 54.208 | 85.576 | 107.008 | 121.003 |
| memory MiB | 600 | 345.234 | 419.836 | 452.074 | 476.805 |
| server heartbeat interval ms | 471 | 998.699 | 1272.677 | 2352.241 | **11505.162** |
| browser相当receive interval ms | 471 | 998.130 | 1250.998 | 1959.266 | **10239.627** |
| published→receive age ms | 472 | -0.197 | 206.604 | 847.526 | **10211.302** |
| ping RTT ms | 600 | 1.073 | 114.284 | 623.121 | **3428.831** |

- OOM kill 0→0、PIDs 23固定。
- baseline observer SHA-256:
  `9bfa58466aaaabede9499d361b91994af6791584b69c961939a4ef9916f0b764`
- baseline cgroup SHA-256:
  `13c636b1dd5c1d13f3eda6cb5a64985df29fe822958e366cb4baebd969ba2118`
- observer canonical series SHA-256:
  `e4166a4748ddeafa85cb32bb4c3e50e3837288e83afd0159482cace5ae568468`
- cgroup canonical series SHA-256:
  `4f45d93a26e8562f66295b0ab0e931d97085dc0ee2b87c281f68aaf697e40982`

### 判定と再開位置

- baseline証拠はサンプル数・終了record・error 0を満たし有効。
- 未計装parent imageでも3000ms超過を再現。計装imageで内部wake／lock／sendへ分離する。
- 再開位置: child aliasの完全IDを再照合し、対象serviceだけをinstrumented imageへrecreateする。

---

## 3. Instrumented 600秒測定

### 3.1 image／readiness境界

- instrumented container:
  `b3bc8a0232495997dd4af7ea4393f263fec64cce569b79daa1b7a83de937b6ca`
- instrumented image:
  `sha256:69e4b38e43a3a533abcdb8546a37bc56165f1d970441062144011c2de37c9933`
- `RTUIF_HBPRI_STAGE1_INSTRUMENTATION=1`を確認。
- restart count 0。
- readinessはhealth GREEN／SUBSCRIBED／BOOK SYNCED／pipeline aliveの全条件PASS。
- container内の計装対象SHA:
  - `main.py`: `010b982d4944c609a68dfb7eecda01e8c41ef0296cb325c34dda651527b2966c`
  - `push_broker.py`: `c19acd1e9f7564406cdf7b22e4f791c1d0aef48b5682cc5b0848c0fa03682f99`
- `index.html`／`market_freshness.js`／protected 3件はparent SHAと一致。

### 3.2 外部observer／resource結果

- 実測時間: 600.669秒。
- cgroup sample: 600（interval 599）。observer exit 0、sampler exit 0。
- heartbeat: 474件、interval 473、sequence gap 0、fresh契約違反0。
- ping: 600件、receive error 0、ping error 0。

| metric | n | min | mean | p95 | max | 3000ms以上 |
|---|---:|---:|---:|---:|---:|---:|
| CPU raw % | 599 | 30.859 | 78.016 | 107.341 | 125.291 | — |
| CPU sampler除外 % | 599 | 30.802 | 77.930 | 107.246 | 125.232 | — |
| memory MiB | 600 | 278.125 | 365.002 | 420.502 | 448.137 | — |
| server heartbeat interval ms | 473 | 1000.403 | 1266.195 | 2538.017 | **11736.555** | **15** |
| browser相当receive interval ms | 473 | 984.927 | 1266.188 | 2594.774 | **11788.013** | **18** |
| published→receive age ms | 474 | -0.718 | 198.016 | 1123.295 | **10731.395** | **6** |
| ping RTT ms | 600 | 1.071 | 95.412 | 462.845 | **3613.435** | 1以上 |

- OOM kill 0→0、PIDs 23固定。
- instrumented observer SHA-256:
  `ca016a5a1e260d9077938c3c77cf471f7744bab8719ddd57e340dde3c171b82f`
- instrumented cgroup SHA-256:
  `460a90f034c9d026b06de1fd2c6b776aeec198268c343fc5fc40fe2cef4042c1`

### 3.3 内部timestamp直接測定

同区間の外部observer sequence 474件と、container traceをsequenceで結合した。
log全体のtrace 582件から測定区間474件だけを抽出し、malformed traceは0件。
client countは全recordで1、send errorは0。

| metric | n | min ms | mean ms | p95 ms | max ms |
|---|---:|---:|---:|---:|---:|
| event-loop wake lateness | 474 | 0.000 | 56.611 | 204.018 | **1636.700** |
| heartbeat `_broadcast_lock` wait | 474 | 0.004 | 183.191 | 1117.584 | **10302.241** |
| actual `_send_text()` duration | 474 | 0.055 | 0.162 | 0.323 | **5.947** |
| `asyncio.gather` duration | 474 | 0.110 | 25.549 | 79.136 | **2026.442** |
| gather scheduling residual | 473 | 0.054 | 25.405 | 79.587 | **2026.224** |
| heartbeat broadcast total | 474 | 0.248 | 208.828 | 1230.097 | **10734.707** |
| `send_market_heartbeat()` await | 474 | 0.261 | 208.861 | 1230.197 | **10734.729** |

`gather scheduling residual`は、1 client条件で`gather duration - actual send duration`として
算出した。実socket send自体ではなく、send task完了前後にparent coroutineが再度実行権を得る
までのevent-loop scheduling時間を表す。

直接series SHA-256:

- wake lateness: `270e7b9aa5172342e9ece1fa9f638c23a0f1d158844df872cd6cfcab9731505f`
- lock wait: `61c99e059619025670afbca283149d89877f95c7ce591b654c027c1fc0ea109c`
- actual send: `e77b75b54a699b5260fc5a69601dd6bb90ea11856e5b443deba1d5dda927ef68`
- direct trace combined:
  `6a1490acf78e2eab99e2085fd33e4a7e1a6c4459460569b54009568e343c2011`

---

## 4. 3000ms超過の直接寄与度

instrumented区間のserver interval 473件中、3000ms以上は15件。各区間を
「直前heartbeatのawait成分 + 当該heartbeat起床成分」にsequence結合した。

15件の`interval - 1000ms`合計は63,426.174ms。

| component | 合計 ms | 超過時間に対する割合 |
|---|---:|---:|
| shared `_broadcast_lock` wait | 54,599.420 | **86.083%** |
| gather scheduling residual | 5,841.501 | **9.210%** |
| event-loop wake lateness | 2,985.141 | **4.706%** |
| actual `_send_text()` | 1.918 | **0.003%** |
| awaitその他 | 1.374 | 0.002% |
| instrumentation emit | 3.279 | 0.005% |
| timestamp丸め等の残差 | -6.460 | -0.010% |

最大区間はsequence 362→363の11,736.555ms。

- lock wait: 10,302.241ms
- gather scheduling: 432.278ms
- actual send: 0.146ms
- wake lateness: 1.614ms
- instrumentation emit: 0.142ms

3000ms以上の単独成分件数:

- lock wait: 6件
- wake lateness: 0件
- actual send: 0件
- gather scheduling residual: 0件

寄与度row canonical SHA-256:
`33ee94fd29747421b5e9c7cbb848b9567fd66d4339efcb3cb47848e6adb092db`

### 結論

3000ms超過の主因はactual WebSocket sendではなく、heartbeatが通常messageと共有する
`_broadcast_lock`の取得待ちである。CPU／event-loop schedulingも副因として実測されたが、
超過時間の86.083%は共有lock待ちで説明される。Stage 2Aのclient単位single-writer +
priority queueは、直接測定で確定した第一原因に対応する。

---

## 5. Instrumentation overhead

baselineとinstrumentedは各600秒、専用observer 1 client、同じcgroup sampler条件。

| resource | baseline | instrumented | 差 |
|---|---:|---:|---:|
| CPU mean % | 85.636 | 78.016 | -7.620 percentage points |
| CPU p95 % | 107.071 | 107.341 | +0.270 percentage points |
| CPU max % | 121.132 | 125.291 | +4.159 percentage points |
| memory mean MiB | 419.836 | 365.002 | -54.835 (-13.061%) |
| memory p95 MiB | 452.074 | 420.502 | -31.572 (-6.984%) |
| memory max MiB | 476.805 | 448.137 | -28.668 (-6.013%) |

比較区間の市場負荷は完全同一ではないため、CPU／memory低下を計装効果とは解釈しない。
ただし指示書のresource非悪化gate（CPU mean/p95 +5pp以内、max +10pp以内、memory +10%以内）
は全項目PASS。

1 heartbeat当たりのrecord serialization／stdout emit直接overhead:

- process CPU: n 474／min 0.063ms／mean 0.269ms／p95 0.746ms／max 7.055ms
- wall: n 474／min 0.065ms／mean 0.256ms／p95 0.746ms／max 7.052ms

計装overheadは3000ms超過の説明変数ではない。

---

## 6. Stage 2B要否判定

本Stageの明示判定条件「wake遅延単独が3000msを超えるか」は、max 1636.700ms／
3000ms以上0件で**未成立**。したがって、Stage 1Aの直接wake gateだけを根拠として
Stage 2BをStage 2Aより前に必須化する証拠は得られなかった。

一方で次は残る。

- gather scheduling residual max 2026.224ms。
- ping RTT max 3613.435ms。
- instrumented CPU p95 107.341%／max 125.291%。

よってstarvationを「不存在」または「解決済み」とは判定しない。確定順序は次である。

1. 直接主因86.083%を除去するStage 2Aを実装。
2. Stage 2A後もserver／browser max 3000ms未満の共通release gateを必須とする。
3. Stage 2A後にwakeまたはpriority enqueue schedulingが3000ms以上を示す、あるいは
   最終3000ms gateを満たさない場合、Stage 2Bをrelease前必須とする。

現時点の判定は、**Stage 2A先行、Stage 2Bは条件付き保留**である。

---

## 7. 親image完全復元

- restored container:
  `81ce462b103f4d184de4470d1d9f19da9d89320cd4f7e47e96fc45c756c4da26`
- restored image:
  `sha256:9c4674c5b56638ae7f8ca629091558dd654e4b2c3572c46fbccf3a5525d88f10`
- instrumentation env: 0件。
- restart count: 0。
- OOMKilled: false。
- readiness: health GREEN／SUBSCRIBED／BOOK SYNCED／pipeline alive、全条件PASS。
- host／restored containerのsource／protected 7件SHAはStage 1開始値と全件一致。

| file | restored SHA-256 |
|---|---|
| `webapp/main.py` | `7fadb2e281a996e97c2fd496803dec6627b14043e1b9ed9c3eec837d0ce95dc1` |
| `webapp/push_broker.py` | `4c0409b73f14661ef3a33f9f3f870385e0b3311da1deb65e03b8b937efe43fd8` |
| `webapp/static/market_freshness.js` | `65c94cf5f90f37b381b1877c9ed1c4f0e93d92540ff90238dbc5c44af3483a48` |
| `webapp/static/index.html` | `3a025cd2ef7425e922a962fa80a438b0d31f5e77b9a16732aacfc4f3577c513c` |
| `webapp/static/orderbook_heatmap.js` | `2da8849d8e77ce82066f02e95c996dde75a952f2a900fc02018e4ea74467388b` |
| `webapp/static/time_sales.js` | `f59fec3f3478cc5a9b977c74978c3d8eb7c66e27a479a0b40fcf6d5f18f8d4c2` |
| `webapp/static/footprint_canvas.js` | `987c5da72a7375495eb44bd9910a1b79b076226b2f0206cc8e3d3de2f08c01be` |

repository内source／test／configへの編集なし。Git操作なし。

---

## 8. 証拠一式

証拠directory:
`C:\tmp\rtuif_stage1a_20260803_182344`

- evidence file数: 61（inventory自身を除く）。
- `evidence_inventory.json` SHA-256:
  `1f2fd039a5e5a731871654ef06ce0024fd7007e55ebbb063496e5adc4582de12`
- baseline analysis v2 SHA-256:
  `213d51a9c1e93002eeabeedd596b78df385da83ffe398d8216b19e546d9b1771`
- instrumented analysis v3 SHA-256:
  `7a4e490bfa9a918ac912dc5f54aab8fff4f2186f9693e9d70287c75bbdccff4a`
- instrumented measurement stdout SHA-256:
  `289d1347bc5bb76963d3534717fe36ac2b131b6703e7329a8f5dd902a61f88d4`

temporary parent／instrumented image alias、overlay context、raw log、analysis fileは
Claudeの独立検証完了まで削除しない。

---

## 9. DoD判定

1. 劣化container読取専用証拠: PASS。
2. 2 file以外のimage差分0／protected不変: PASS。
3. clean baseline 600秒: PASS。
4. instrumented 600秒＋overhead: PASS。
5. wake／lock／actual sendの直接値とseries hash: PASS。
6. 3000ms超過寄与度とStage 2B要否: PASS。
7. 親image ID完全復元、7件SHA、runtime readiness: PASS。
8. 単一Stage 1A報告書への集約: PASS。

**Stage 1A総合判定: COMPLETE。Claude独立検証待ち。**
