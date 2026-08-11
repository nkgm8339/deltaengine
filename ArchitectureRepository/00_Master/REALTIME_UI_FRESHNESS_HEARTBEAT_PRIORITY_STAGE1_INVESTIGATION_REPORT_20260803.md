# Realtime UI Freshness 恒久対処 第二段
## heartbeat priority配信 — Stage 1 調査報告書

**文書ID:** DE05M-RTUIF-HBPRI-STAGE1-REPORT-001  
**版:** 1.0  
**開始日:** 2026-08-03  
**実施者:** Codex  
**状態:** Stage 1 NO-GO（内部3計測点の直接計装許可不足／Stage 2 source実装NO-GO）

---

## 1. 2026-08-03 14:44:20 +09:00 — Stage 1開始checkpoint

- ユーザー承認: ClaudeがStage 1前提受領物の実物SHA照合を完了した旨と、Stage 1測定開始指示を受領。
- 承認範囲: Stage 1の読取専用runtime測定、source調査、設計文、Stage 2 gate固定。
- 禁止: source／test／config／runtime code／imageの変更、priority実装、timeout変更、rollback、production upstream障害注入、Git stage／commit／push／branch操作。
- repository: branch `feature/footprint-dom-tape`、HEAD `7552bc3487a3539dca9c7830e92de7cca8884c4f`。開始前dirty／untrackedは保存する。
- runtime: container `delta_engine_pro4web-deltaengine_clone-1`、ID `e2aab8bca1e53ef4f7a831aba4e8b23fe28a7a6e710cc67986af1e7666fa2854`、image `sha256:9c4674c5b56638ae7f8ca629091558dd654e4b2c3572c46fbccf3a5525d88f10`、running／restart 0／OOM false。
- Stage 1前提source／protected SHA-256（Codex再測値、Claude照合完了の連絡受領）:

| role | file | SHA-256 | bytes |
|---|---|---|---:|
| latest source | `webapp/main.py` | `7fadb2e281a996e97c2fd496803dec6627b14043e1b9ed9c3eec837d0ce95dc1` | 45,644 |
| latest source | `webapp/push_broker.py` | `4c0409b73f14661ef3a33f9f3f870385e0b3311da1deb65e03b8b937efe43fd8` | 28,984 |
| latest source | `webapp/static/market_freshness.js` | `65c94cf5f90f37b381b1877c9ed1c4f0e93d92540ff90238dbc5c44af3483a48` | 12,611 |
| latest source | `webapp/static/index.html` | `3a025cd2ef7425e922a962fa80a438b0d31f5e77b9a16732aacfc4f3577c513c` | 193,917 |
| protected | `webapp/static/orderbook_heatmap.js` | `2da8849d8e77ce82066f02e95c996dde75a952f2a900fc02018e4ea74467388b` | 66,280 |
| protected | `webapp/static/time_sales.js` | `f59fec3f3478cc5a9b977c74978c3d8eb7c66e27a479a0b40fcf6d5f18f8d4c2` | 18,597 |
| protected | `webapp/static/footprint_canvas.js` | `987c5da72a7375495eb44bd9910a1b79b076226b2f0206cc8e3d3de2f08c01be` | 64,289 |

- 前提package: `UPLOAD_THIS_REALTIME_UI_FRESHNESS_HBPRI_STAGE1_PRECONDITION_20260803.zip`、SHA-256 `484c04095e69cb50b56ecff8c156af5afba37b98699b85daa5f8e352797cb62c`、108,394 bytes。
- 既存NO-GO checkpoint: SHA-256 `d7b5e99b21b074f8a8964ea80727ae6e656eef7e553dedca860b8b17623624dd`、64,969 bytes／821行／CR 0。本Stageでは変更しない。
- 外部instrumentation現物確認: 稼働containerに`py-spy`／`strace`／`perf`／`gdb`は存在しない。Python 3.12.13、uvicorn PID 1／22 threads。
- 完了済み: Stage 1開始条件の受領、7実物SHA再測、runtime同一性確認。
- 未完了: 現行source構造行根拠、4測定、CPU寄与分離、設計文、Stage 2 gate、終了hash。
- 変更file: 本Stage 1調査報告書1点だけ。
- blocker: なし。稼働processへのcode injectionを行わず、外部観測と現行sourceの時系列契約から4値を分離できるかをまず確定する。
- 次の再開位置: `PushBroker`／`_market_heartbeat_loop`／WebSocket registerの現行行番号と呼出し経路を固定する。

---

## 2. 現行配信構造のsource根拠

### 2.1 per-client writer不存在／共有lock直列化

- 観測元: `Delta_Engine_Pro4web/webapp/push_broker.py`。
- `PushBroker` classは142行から開始。実体は`_clients: set` (157行)、client集合用`_lock` (158行)、broker全体用`_broadcast_lock` (159行)を持つ。
- source全体検索でclient別`Queue`／`PriorityQueue`／writer taskの定義は0件。現行にper-client writerは存在しない。
- `_broadcast()` (218〜238行) はmessageをJSON化後、共有`_broadcast_lock`を取得 (220行)し、`_lock`下でclient snapshotを作成 (221〜222行)、各clientへの`send_one()`を`asyncio.gather` (233行)で完了するまでbroadcast lockを保持する。
- `_send_text()` (212〜216行) は各`ws.send_text()`へ`asyncio.wait_for(..., timeout=client_send_timeout_sec)`を適用。定数`CLIENT_SEND_TIMEOUT_SEC=0.5` (19行)が既定bounded send契約。
- 判定: 現行は「broker単位の共有broadcast lockでbroadcast間を直列化し、そのlock内でclient送信を同時gather」する方式。client単位のqueue／writer方式ではない。

### 2.2 heartbeat呼出し経路

- 観測元: `webapp/main.py`と`webapp/push_broker.py`。
- `main.py:_market_heartbeat_loop()` (153行以降) はloop冒頭で`published_at` (162行)とpayload (163〜167行)を作成し、`await broker.send_market_heartbeat(...)` (168行)完了後に1000ms相当の`asyncio.sleep()` (169行)を行う。
- `push_broker.py:send_market_heartbeat()` (656〜664行) はsequenceを増分 (658〜660行)、`published_time`を格納 (661行)し、通常と同じ`await self._broadcast(...)` (662〜664行)を呼ぶ。
- したがってheartbeatは`_broadcast_lock` (220行)、client snapshot (221〜222行)、各clientの0.5秒bounded `_send_text()` (212〜216／228行)、全client `gather()` (233行)を経由する。
- `main.py` lifespanでheartbeat taskを作成 (468行付近)し、`app.state.tasks`へ登録 (723〜724／740行)、shutdownで全task cancel／await (745〜749行)する。

### 2.3 reconnect cacheとheartbeat非cache契約

- WebSocket endpointはHELLO送信後に`broker.register(ws)` (main.py:776〜795行)を呼び、disconnect時に`broker.unregister(ws)` (799〜802行)を呼ぶ。
- `register()` (push_broker.py:174〜202行) は共有`_broadcast_lock`を取得 (177行)し、TICK／SPOT／HFM／BOOK／ABSORPTIONの5 latest cacheだけをsnapshot (179〜185行)、0.5秒の総deadline内で直列送信 (187〜198行)してからclientを登録 (201〜202行)する。
- `__init__()`のcache fieldは163〜167行の5件。`_latest_heartbeat_message`／`latest_heartbeat`はsource全体で0件。heartbeatはregister cacheへ入らない。
- 干渉範囲: heartbeatはcache payloadと混合しないが、register中のcache handoffも同じ`_broadcast_lock`を保持するため、最大0.5秒契約の範囲でheartbeat lock取得と競合し得る。

### 2.4 source構造の結論

heartbeatはnon-cacheかつ通常PushBroker経路である。一方でpriority／deadline-aware arbitrationはなく、TICK／BOOK／Tape／Flow／BAR／HEALTH／STATS／register cache handoffと同じbroker-wide lockの取得順に従う。これがStage 0 runtimeで観測したheartbeat滞留を許容するsource構造である。

---

## 3. 2026-08-03 14:47 +09:00 — 4測定開始前checkpoint

- 旧image現物: Docker内に`stage2c4-20260730` (`sha256:99769af0...`)以前のimageは残存するが、最新でも7月30日版。v1.1実装直前の8月3日同一source／同一Heatmap／Tape／pipeline条件のimageは残存しない。
- 制約: 旧image起動はStage 1の`runtime/image変更禁止`と「稼働container維持」に反するうえ、同条件ではない。そのため旧imageとの直接CPU A/B比較には使用しない。
- 稼働process内に外部attach用`py-spy`／`strace`／`perf`／`gdb`はない。現行sourceにevent-loop wake／`_broadcast_lock` wait／`send_text` duration metricの公開点はない。
- 変更禁止を保持して取得可能な観測:
  - Docker statsのCPU／memory／PIDs時系列。
  - heartbeat payload `published_time`とclient同一host wall／monotonic受信時刻。
  - WebSocket protocol ping/pong RTT（server event-loop／transport応答遅延のproxy）。
  - server生成間隔、client受信間隔、published→receive age。
- 分離可能範囲:
  - `published→receive age` = lock取得待ち + `send_text` await + local transport／client dispatchの複合値。
  - WebSocket ping RTTでserver event-loop／transport応答の概算上限を並行測定する。
  - `server interval - 1000ms - 直前published→receive age`で残差を算出し、sleep wake遅延の外部推定値とする。ただしreceive ageには実送信／transportが含まれるため直接計装値ではない。
- 未解決の観測限界: source／runtime code injectionを禁止したままでは、`_broadcast_lock` acquire前後と`ws.send_text()`前後の個別timestampは外部から直接取得できない。外部推定の結果後もDoDが直接値を必須とする場合、Claude／ユーザーに「一時的なreversible runtime-only instrumentation」の変更許可が必要。
- 次の再開位置: 180秒同時計測でCPU／memory／heartbeat／pingを1時系列として取得する。

### 3.1 同時計測A（180.856秒）— CPU stream欠落のため部分証拠

- 方法: hostのisolated WebSocket client 1本でheartbeat payload／全messageを受信し、1秒ごとにprotocol ping/pong RTTを計測。同時にDocker stats streamをsubprocessで取得する設計だった。
- 計測完了: 180.856秒、WebSocket受信例外0、heartbeat sequence 1800→1817／18件／gap 0／fresh条件全件true。
- heartbeat server生成間隔: n=17／min 1089.815ms／mean 8360.878ms／p95 42021.245ms／max **77732.247ms**。3000ms以上4件。
- browser相当monotonic受信間隔: n=17／min 1026.948ms／mean 8349.158ms／p95 44349.443ms／max **80381.090ms**。3000ms以上3件。
- `published_time`→receive wall age: n=18／min 2.041ms／mean 8033.932ms／p95 36444.753ms／max **76639.210ms**。3000ms以上4件。
- protocol ping RTT: n=178／min 1.603ms／mean 694.089ms／p95 3033.460ms／max 3668.609ms。
- 外部推定wake residual (`server interval - 1000 - 直前age`): n=17／min 22.533ms／mean 569.208ms／p95 3231.333ms／max 5189.144ms。
- 代表: seq 1801→1802はserver interval 77732.25ms、直前heartbeat age 76639.21ms、wake residual 93.04ms。この区間は生成間隔のほぼ全てが直前heartbeatのpublished後滞留と整合し、sleep wake遅延主体ではない。
- 代表: seq 1816→1817はserver interval 7359.00ms、直前age 1169.86ms、wake residual 5189.14ms。この区間はsleep wake／event-loop scheduling寄与が大きい。
- 生series canonical JSON SHA-256: `eff3506c8b06e7e4bf96225e056c603bcd4739e5977911783f1a36a0ffffece2`（CPU 0／heartbeat 18／ping 178 samples）。
- 測定失敗点: Docker stats subprocessからsampleが1件も取得できず、CPU／memoryはnull。原因は連続streamのWindows subprocess取得不適合。この区間を§4.2 CPU baselineの根拠に使わない。
- 次の再開位置: 稼働container内からcgroup `cpu.stat`／`memory.current`／`pids.current`を読む1秒samplerと、host WebSocket計測を並列180秒で再実行する。

---

## 4. single-writer + client単位priority queue設計（Stage 1固定案、未実装）

### 4.1 データ構造と所有権

- brokerは`set[WebSocket]`直接管理を、clientごとのchannel record管理へ変更する。channelは少なくとも`ws`、bounded `asyncio.PriorityQueue`、writer task、closing flag、enqueue／send／overflow counterを持つ。
- queue itemは`(priority, order, text, message_type)`相当の不変recordとする。heartbeatはpriority 0、通常messageはpriority 1。`order`はbroker内monotonic counterで、同priority内のFIFO tie-breakerに使う。
- 同一`ws`の`send_text()`を呼ぶのはそのchannelのwriter task 1本だけ。broadcast／register／unregister／heartbeat producerは`send_text()`を直接呼ばない。例外はwriter生成前のHELLO 1件だけで、HELLO完了後にregisterする現行endpoint順序を維持する。
- client集合／channel mapの所有権は既存`_lock`。通常messageの順序付けと全channelへのenqueueは「network awaitを含まない」短時間のenqueue critical sectionで直列化する。既存`_broadcast_lock`をnetwork I/O lockとしては廃止し、必要ならnormal-order enqueue lockに責務を限定する。

### 4.2 enqueueと順序契約

- 通常message: JSON化後、normal-order critical sectionでorderを1回採番し、その時点のactive channel全件へ`put_nowait()`する。TICK／BOOK／Tape／Flow／BAR等のmessage typeによらずnormal priorityとし、通常message同士のbroker enqueue順を全clientで維持する。
- heartbeat: JSON化後、active channel snapshotへheartbeat priorityで`put_nowait()`する。normal-order lockとnetwork I/O完了を待たない。writerが現在送信中の1件はpreemptせず、その完了後の「次の1件」としてheartbeatを最優先にする。
- heartbeatは通常messageの間へ割り込める。heartbeatと通常messageの相対順序は契約対象外。heartbeat割込み前後の通常message同士はorder順を保つ。
- heartbeat cacheは作成しない。queueはactive connection向けの一時的delivery bufferであり、reconnect後にheartbeat itemを引き継がない。

### 4.3 writerとbounded send

- writerはqueueから1件ずつ取り出し、既存と同じ`asyncio.wait_for(ws.send_text(text), timeout=0.5)`を適用する。同一socketへの同時sendは構造上0。
- timeout／WebSocket errorではそのchannelだけをclosingにし、channel mapから除外してsocketをcloseする。他clientのwriter／queueはawaitもcancelもしない。
- queueは有界とする。queue full時に通常messageまたはheartbeatを無記録dropせず、当該clientをslow／overflow clientとして隔離する。これにより継続中connectionの通常message FIFOとheartbeat sequence gap 0を「dropで見かけ上維持」することを避ける。
- queue上限値はStage 2指示書でconfig／根拠を固定する。最低条件は「正常clientの実測p99 enqueue速度×0.5秒send budget／burstでoverflowしない」と「無制限memory growthを許さない」の両立。magic numberは不可。

### 4.4 register／unregister／shutdown lifecycle

- register: HELLO送信完了後、normal-order enqueue critical section内でchannelを作成する。latest cache 5件を現行固定順でnormal queueへenqueueし、その後channelをactive mapへ公開する。このcritical section後に通常live messageがenqueueされるため、cache→liveの相対順を維持する。cache送信もwriterだけが行い、registerが`send_text()`を直接awaitしない。
- unregister: active mapからchannelを原子的に除外し、closingを1回だけ設定。外部disconnect経路はwriter taskをcancelしawaitする。writer内error経路は自分自身をawaitせず、brokerの後処理でmap除外／socket closeを行う。二重close／二重awaitはclosing flagで防ぐ。
- shutdown: まずproducer task群（pipeline／heartbeat／BOOK／Tape等）をcancel／awaitし、新規enqueueを停止。次に`broker.close()`がactive channel snapshotを除外し、全writer taskをcancel、`gather(..., return_exceptions=True)`でawait、socket close、queue reference解放を行う。終了後writer task 0をtestで証明する。

### 4.5 deadline-aware heartbeat loop

- `send_market_heartbeat()`はnetwork送信完了をawaitせず、各active channelへのpriority enqueue完了までをawait範囲とする。
- heartbeat loopは「送信完了後に1000ms sleep」の累積drift方式をやめ、event-loop monotonic clockで次回deadlineを持つ。各loopでdeadlineまでsleepし、起床後に生成／enqueueし、次deadlineをinterval単位で前進させる。
- event loopが複数interval分遅延した場合、過去heartbeatをburst送信しない。現在より未来の最初deadlineまで進め、生成するheartbeatは現在1件だけ。sequenceは実際にenqueueしたheartbeatだけ1増分。
- Stage 2でwake lateness、priority enqueue duration、queue wait、writer send durationのadditive metricを公開し、現行の観測不能を解消する。これらはpayloadの価格／BOOK／Tape／Flow意味を変えない。

### 4.6 非影響境界

- message payload、message type、TICK／BOOK／Tape／Flow／BARの生成・計算・個別sequenceを変更しない。変更はPushBroker内のdelivery schedulingとlifespan shutdown連携に限定する。
- `orderbook_heatmap.js`／`time_sales.js`／`footprint_canvas.js`／Flow Price Response／3段チャート／Hook／Strategyは変更しない。
- Heatmap adaptive stale／gap／sequenceとTape store／gap／row順は現行payloadと通常message FIFOに対する既存testで固定する。

---

## 5. Stage 2検証gate固定案

1. **server interval:** 連続runtime soakの`MARKET_HEARTBEAT.payload.published_time`間隔maxが**3000ms未満**。1件でも3000ms以上ならFAIL。
2. **browser receive interval:** 同一soakのbrowser `performance.now()`相当monotonic受信間隔maxが**3000ms未満**。1件でも3000ms以上ならFAIL。
3. **heartbeat integrity:** 同一connection内sequence gap 0／duplicate 0／mode mismatch 0。全heartbeatが期待するupstream／pipeline契約に従う。heartbeat cache 0。
4. **normal FIFO:** fake client writerと複数並行producerで、brokerがenqueueしたTICK／BOOK／Tape／Flow／BARの通常orderと各client実send orderが一致。heartbeatを間に割り込ませた上で、heartbeatを除いた通常message列が全件同順。
5. **single writer:** 同一fake WebSocketの`send_text()`同時実行数max=1。複数client間のwriterは独立実行可。
6. **bounded send／slow isolation:** 0.5秒不変。slow client 1本をtimeoutまたはqueue overflowさせてもhealthy clientのheartbeat／TICK／BOOK継続、normal FIFO、sequenceに影響0。slow clientだけが隔離される。
7. **register cache:** HELLO→latest cache固定順→live normal message順を同一writerで証明。cache handoff中のheartbeatは次送信1件へ優先されてよいが、heartbeatはreconnect cacheに残らない。
8. **lifecycle:** registerごとにwriter 1、unregister／send timeout／overflow／app shutdown後に該当writer task 0。cancel／await漏れ、pending task warning、二重close 0。
9. **protected／consumer:** protected 3 fileの開始／終了SHA-256一致。Heatmap adaptive stale／gap／sequence、Tape順序／drop／pending／send failure、Flow Price Response／3段チャート既存testの新規failure 0。
10. **runtime health:** health GREEN／BOOK gap 0／WS reconnect storm 0／pipeline exception 0／Tape dropped 0／pending 0／send failure 0／container restart 0／OOM false。
11. **resource regression:** Stage 1の同条件baselineと比較し、CPU mean/p95は各+5 percentage points以内、CPU maxは+10 points以内、memory mean/p95/maxは各+10%以内。超過した場合は統計的／機能的根拠なしにPASSにしない。
12. **soak下限:** 単一browser相当clientで**600秒以上**。Stage 0の180秒で不具合を検出したためそれ未満は不可。専用test clientに加え、ユーザー画面を切り替えないisolated headless browserでguard stateがLIVE維持・STALE遇遇0を確認する。
13. **failure reporting:** maxだけでなくmin／mean／p95／max、3000ms超過全区間、近傍CPU／queue depth／wake lateness／queue wait／send durationをStage 2 checkpointへ記録する。

---

## 6. 同時計測B開始失敗とruntime応答遅延

- 方法: container内cgroup 1秒CPU samplerとhost WebSocket samplerを同時180秒で開始。source／image変更なし。
- 失敗: WebSocket opening handshakeが5秒でtimeoutし、同時計測は開始条件を満たさなかった。CPU samplerは別processとして開始済みだったため自然終了まで継続し、終了後にprocess残存0を確認。並列orchestration側がWebSocket例外で打ち切られたためsampler stdoutは回収できず、CPU baseline根拠には使わない。
- sampler稼働中: uvicorn PID 1 CPU 92.7%、sampler CPU 1.7%。samplerはread-only cgroup取得だけで、主CPU消費はuvicorn。
- sampler終了後もhost `/health` は15秒timeout。ただしcontainer logには該当GETが後刻HTTP 200として処理された記録があり、request喪失ではなくevent-loop処理遅延。
- sampler終了後container: running／restart 0／OOM false。uvicorn PID 1 CPU 92.3%／memory 17.3%。cgroup `memory.current=656,695,296` bytes、`pids.current=24`、FD 18、TCP ESTABLISHED 2。CPU cgroup throttling 0。
- 同時期log: `oi_polling_loop` 10秒timeout複数、upstream Binance keepalive ping timeout (`1011`)、その後のorder book gap 1件を記録。Stage 1はupstreamへ障害注入していない。現行runtimeのevent-loop／CPU遅延がupstream keepalive／book continuityにも表面化した時系列として扱う。
- 判定: heartbeatだけのshared lock待ちに加え、event loop全体の応答遅延も独立寄与。priority queueはbroker lock滞留を解くが、CPU-bound event-loop starvationを単独では解かない。Stage 2 gateは両方を必須とする。
- 次の再開位置: WebSocketを追加せず、cgroup CPU／memory／PIDsのみを180秒単独測定する。

### 6.1 CPU baseline C（diagnostic WebSocketなし／180.002秒）

- 計測方法: 稼働container内の別processがread-onlyでcgroup v2 `cpu.stat.usage_usec`／`memory.current`／`pids.current`を1秒ごとに読取。前後sampleの`usage_usec`差をmonotonic実経過時間で除し、CPU%=1 logical CPUを100%として算出。WebSocket clientは追加していない。
- CPU: n=180／min **97.911%**／mean **102.358%**／p95 **111.849%**／max **119.700%**。100%以上105 samples。
- memory: n=180／min 648.125MiB／mean 660.016MiB／p95 675.106MiB／max 677.617MiB。
- PIDs: n=180／min/mean/p95/maxすべて23。process leakによる増加なし。
- CPU top: 119.700% (t=24s)、118.445% (t=1s)、117.341% (t=90s)、116.464% (t=52s)、114.132% (t=124s)。特定の単発spikeではなく、180秒区間で継続的に1 core相当を飽和。
- raw 180-sample canonical JSON SHA-256: `b6f9f617262cda93fed1974bc0f0071cd0f74d54825b74e24a4081334ba1de0a`。
- 結論: checkpointのCPU 106%は短期の偶発値ではない。diagnostic WebSocketなしでもmean 102.358%であり、現行runtimeが定常的に1 core以上を消費することを実測した。
- 限界: v1.1実装直前の同条件imageがなく、旧image起動も禁止されているため、「実装前CPU実測値との直接差」は取得不能。次にheartbeat task単体のpure CPU寄与を同sourceのisolated microbenchmarkで上限推定する。

### 6.2 heartbeat task単体CPU寄与の推定

- 計測方法: 稼働runtimeと同一host sourceの`_build_market_heartbeat_payload()`と`PushBroker.send_market_heartbeat()`をisolated Python processで反復。`PYTHONDONTWRITEBYTECODE=1`。source／runtime変更なし。fake fast WebSocketは`send_text()`で文字列bytes数を計数し直ちにreturn。値はprocess CPU time／call数で算出。
- payload生成のみ: 500,000 calls／CPU 1.96875s／**3.9375µs/call**／wall 4.0254µs/call。
- broker経路／client 0: 50,000 calls／CPU 1.078125s／**21.5625µs/call**／wall 21.9298µs/call。
- broker経路／fast client 1: 20,000 calls／CPU 2.03125s／**101.5625µs/call**／wall 105.3138µs/call／`send_text` 20,000 calls。
- 1Hzでのcontainer CPU寄与推定: fast client 1で`101.5625µs / 1s = 0.01016% of one core`。network await時間はwall latencyを増やすが、CPU実行時間を同比率で増やさない。余裕を見てもheartbeat task追加でmean 102.358%を有意に説明することはできない。
- browser state machineはbrowser process内で実行され、container CPU baselineへの直接寄与0。Heatmap／Tape分離はserverの既存message生成レートを増やす変更ではない。
- 結論: 「v1.1 heartbeat追加がCPU 106%を新規に作った」という仮説は実測上支持されない。CPU飽和は既存pipeline／WebApp workloadが主体。heartbeatはその高負荷下でshared broker lock／event-loop starvationの影響を受ける側である。ただし、同条件の実装前image実測がないため「実装前後差の直接証明」ではなく、単体寄与の実測上限による切り分けである。

---

## 7. 4測定の最終整理

| 測定 | 値 | 方法／観測点 | 証拠区分 |
|---|---|---|---|
| CPU baseline | min 97.911%／mean 102.358%／p95 111.849%／max 119.700% | container cgroup `cpu.stat.usage_usec`を1秒間隔で180回 | **直接実測** |
| event-loop wake遅延 | residual min 22.533ms／mean 569.208ms／p95 3231.333ms／max 5189.144ms | `server interval - 1000ms - 直前 published→receive age` | **外部推定**。sleep終了点の直接timestampではない |
| heartbeat lock待ち | lock + bounded send + transport複合age: min 2.041ms／mean 8033.932ms／p95 36444.753ms／max 76639.210ms | `published_time`生成からclient wall受信まで | **複合直接実測／個別内訳は未計装** |
| 実`send_text()`時間 | 現行契約上限0.5秒。protocol ping RTT min 1.603ms／mean 694.089ms／p95 3033.460ms／max 3668.609ms | source `push_broker.py:212-216`／WebSocket ping-pong proxy | **上限契約／proxy**。`send_text()`前後の直接timestampではない |

### 7.1 寄与度の結論

- shared broker滞留が主体の区間: seq 1801→1802はserver interval 77732.25msに対し、直前 published→receive age 76639.21ms、wake residual 93.04ms。この区間は待ち／配信複合が約98.6%を説明する。
- event-loop starvationが大きい区間: seq 1816→1817はwake residual 5189.14ms。protocol pingもp95 3033.46ms／max 3668.61msで、broker heartbeat以外のevent-loop応答自体が3000msを超える。
- CPU baselineはdiagnostic WebSocketなしでmean 102.358%。heartbeat taskのisolated CPU寄与は1 client／1Hzで約0.01016% of one core。高CPUはheartbeat追加が主因ではない。
- 総合結論: **shared lock／delivery滞留とCPU-bound event-loop starvationの両方が寄与**。client単位priority queueは前者を解く必要条件だが、後者が残ればserver／browser max 3000ms gateを単独で保証しない。

### 7.2 直接分離を阻む境界矛盾

Stage 1はsource／runtime／image変更を全禁止する一方、現行sourceが保持／公開していない次のtimestampの直接実測をDoDとする。

1. `_market_heartbeat_loop` sleep終了時刻。
2. heartbeatの`_broadcast_lock` acquire要求／完了時刻。
3. 各client `ws.send_text()`開始／完了時刻。

稼働processにattach profiler／tracerは存在せず、既存API／log／metricにも上記3点はない。外部からは複合値までしか観測できず、個別値の直接実測には一時的なreversible instrumentationが必要。したがって、本報告は推定値を直接値としてPASS扱いしない。

---

## 8. 終了時非変更証拠とruntime状態

### 8.1 source／protected SHA-256

開始値と終了値は7 files全件一致。

| role | file | 終了SHA-256 | 判定 |
|---|---|---|---|
| latest source | `webapp/main.py` | `7fadb2e281a996e97c2fd496803dec6627b14043e1b9ed9c3eec837d0ce95dc1` | MATCH |
| latest source | `webapp/push_broker.py` | `4c0409b73f14661ef3a33f9f3f870385e0b3311da1deb65e03b8b937efe43fd8` | MATCH |
| latest source | `webapp/static/market_freshness.js` | `65c94cf5f90f37b381b1877c9ed1c4f0e93d92540ff90238dbc5c44af3483a48` | MATCH |
| latest source | `webapp/static/index.html` | `3a025cd2ef7425e922a962fa80a438b0d31f5e77b9a16732aacfc4f3577c513c` | MATCH |
| protected | `webapp/static/orderbook_heatmap.js` | `2da8849d8e77ce82066f02e95c996dde75a952f2a900fc02018e4ea74467388b` | MATCH |
| protected | `webapp/static/time_sales.js` | `f59fec3f3478cc5a9b977c74978c3d8eb7c66e27a479a0b40fcf6d5f18f8d4c2` | MATCH |
| protected | `webapp/static/footprint_canvas.js` | `987c5da72a7375495eb44bd9910a1b79b076226b2f0206cc8e3d3de2f08c01be` | MATCH |

### 8.2 2026-08-03 17:37:00 +09:00 runtime状態

- container: running／restart 0／OOM false／image `sha256:9c4674c5b56638ae7f8ca629091558dd654e4b2c3572c46fbccf3a5525d88f10`。
- `/api/health`: 30秒timeout。現時点でhealth GREENと判定できない。
- point-in-time Docker stats: CPU 99.14%／memory 738MiB / 3.708GiB／PIDs 22。
- Stage 1中のsource／config／test／image／container recreate／restart／rollback／upstream障害注入: 0。
- 稼働containerは指示どおり現状維持した。ただしHTTP／WebSocket応答遅延、upstream keepalive timeout／book gapが実測されており、runtimeの継続稼働安全性は別途の明示判断が必要。

---

## 9. Stage 1 DoD判定

| DoD | 判定 | 根拠 |
|---|---|---|
| §3 source SHA照合 | PASS | Claude照合完了連絡／Codex開始終了全件MATCH |
| §4.1 source構造 | PASS | 本報告§2、file:line付き |
| §4.2 4測定 | **NO-GO** | CPUは直接実測。wake／lock／sendは複合／推定までで、禁止境界下で内部timestampを直接取得不能 |
| §4.3 CPU負荷源 | 条件付きPASS | 旧同条件imageなし。現行baselineとheartbeat単体CPU上限で「実装が主因ではない」を定量切り分け |
| §4.4 設計文 | PASS | 本報告§4、実装codeなし |
| §4.5 Stage 2 gate | PASS | 本報告§5 |
| 1文書集約 | PASS | 本Stage 1報告書1点。調査script／CSV／manifest新規作成0 |

**Stage 1総合判定: NO-GO。** source構造、CPU baseline／寄与切り分け、priority queue設計、Stage 2 gateは確定した。一方、§4.2のうちevent-loop wake／lock wait／actual send durationの直接分離は、現行の変更禁止境界と観測点不存在のため未達。Stage 2実装GOの前にClaude独立レビューと、「一時的なreversible instrumentationを許可するStage 1追記」または「外部推定で§4.2を充足とする明示判定」が必要。

