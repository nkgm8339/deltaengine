# Stage 1 §4.2 境界矛盾 — Codex回答書

**文書ID:** DE05M-RTUIF-HBPRI-STAGE1-QUERY-RESPONSE-001  
**版:** 1.0  
**作成日:** 2026-08-03  
**回答者:** Codex  
**対象問い合わせ:** DE05M-RTUIF-HBPRI-STAGE1-QUERY-001  
**状態:** 回答のみ。計装／実装／runtime操作NO-GO

---

## 0. 結論

- Q1は**(a) 一時的・可逆・runtime限定instrumentation**が妥当。
- repositoryのdirty sourceを直接編集せず、確定image `sha256:9c4674c5...d88f10`を親とするtemporary overlay imageで`main.py`／`push_broker.py`のheartbeat経路だけを計装する。
- 現在の劣化containerは計測母体にしない。まず読取専用証拠を固定し、明示承認後にclean lifecycleからbaseline／計装測定する。
- client単位priority queueとevent-loop starvation対処は別Stageに分ける。ただし最終的な3000ms gateは両方の共通release gateとし、どちらかを「本件外」として無視しない。

---

## Q1. §4.2の充足方式

### 回答: (a)

一時的・可逆・runtime限定instrumentationを明示承認し、event-loop wake／heartbeat lock wait／actual `send_text()` durationの個別timestampを直接実測する方式を選ぶ。

### 根拠

1. 現行sourceには必要な観測点がない。
   - `webapp/main.py:153-169` は`published_at`生成、heartbeat送出await、`asyncio.sleep()`を持つが、sleep要求／起床のmonotonic timestampを保持しない。
   - `webapp/push_broker.py:218-238` は`_broadcast_lock`を取るが、acquire要求／完了時刻を保持しない。
   - `webapp/push_broker.py:212-216`は`ws.send_text()`を0.5秒でbounded awaitするが、前後timestampを保持しない。
2. 外部推定は原因の複数性を確定したが、個別値の代替にならない。
   - Stage 1実測の`published_time→receive age` max 76,639.210msは「lock wait + send await + transport/client dispatch」の複合値。
   - wake residual推定はmin 22.533ms／mean 569.208ms／p95 3231.333ms／max 5189.144msだが、sleep終了点の直接値ではない。
   - ping RTTはmin 1.603ms／mean 694.089ms／p95 3033.460ms／max 3668.609msだが、actual `send_text()`所要時間ではない。
3. (b)を採用すると、priority queue後も3000ms超過した際に「queue待ちが残ったのか、event loopが起きなかったのか、send/backpressureか」を判別できない。これはStage 2の設計／rollback判定を再び推測に戻す。
4. (c)として外部attach profiler／tracerの使用も考えられるが、稼働containerに`py-spy`／`strace`／`perf`／`gdb`は存在しない。さらにstack samplingだけでasync lock待ち開始／完了と個々のsend durationを正確に再構成できない。

したがって、計装点を最小範囲へ直接置く(a)が最も誤差が小さく、検証可能である。

---

## Q2. (a)を採る場合の計装範囲と可逆性

### Q2-1. 計装file／箇所

計装は次の2 fileのheartbeat経路に限定できる。計装のためにconsumer／payload意味／pipeline計算を変更する必要はない。

1. `webapp/main.py:153-169` (`_market_heartbeat_loop`)
   - loop開始時刻。
   - heartbeat `published_at`生成時刻。
   - `send_market_heartbeat()` await開始／完了。
   - `asyncio.sleep()`開始時刻、設計wake deadline、実起床時刻、wake lateness。
2. `webapp/push_broker.py:218-238, 656-664`
   - `MARKET_HEARTBEAT`に限定した`_broadcast_lock` acquire要求／完了時刻、lock wait duration。
   - client snapshot完了時刻／client数。
   - 各heartbeat `send_one()`の`_send_text()`開始／完了／timeout／exception／actual duration。
   - `asyncio.gather()`完了時刻／heartbeat broadcast total duration。

timestampはserver wall clockではなく、同一processの`time.perf_counter_ns()`またはevent-loop monotonic clockで取る。sequenceでmain／broker／client受信を結合する。計測値は1 heartbeatあたり1 structured recordへ集約し、timestamp取得の間にlog I/Oを挿入しない。

### Q2-2. 変更禁止領域の担保

- temporary overlayで上計2 file以外をCOPY／編集しない。
- 開始前／計装image内／復元後に次のSHA-256を照合する。
  - `orderbook_heatmap.js`: `2da8849d8e77ce82066f02e95c996dde75a952f2a900fc02018e4ea74467388b`
  - `time_sales.js`: `f59fec3f3478cc5a9b977c74978c3d8eb7c66e27a479a0b40fcf6d5f18f8d4c2`
  - `footprint_canvas.js`: `987c5da72a7375495eb44bd9910a1b79b076226b2f0206cc8e3d3de2f08c01be`
- `index.html`／`market_freshness.js`／Heatmap／Tape／Flow Price Response／3段chart／Hook／Strategy／config／testは計装overlayに含めない。
- Docker image diffで2 file以外のcontainer layer差分0を確認する。host source 7件のSHAはStage 1開始値と一致し続ける。

### Q2-3. 有効化方式

- 環境変数例: `RTUIF_HBPRI_STAGE1_INSTRUMENTATION=1`。未設定／`0`を既定OFFとする。
- OFF時はstructured record生成／保持／出力を行わない。ただし測定はtemporary imageのON状態でのみ行う。
- 1Hz heartbeatだけを記録し、TICK／BOOK／Tapeごとのlogを増やさない。client識別子はconnection内連番とし、IP／payload／取引dataを出力しない。
- instrumentation overheadを別counterで測り、heartbeat当たり追加CPU／wall costを報告する。

### Q2-4. repositoryを汚染しないtemporary overlay image

1. 親imageを`sha256:9c4674c5b56638ae7f8ca629091558dd654e4b2c3572c46fbccf3a5525d88f10`でpinする。tagだけに依存しない。
2. `C:\tmp`配下の専用temporary build contextへ、SHA確認済み`main.py`／`push_broker.py`のcopyだけを置き、instrumentation hunkを適用する。
3. overlay Dockerfileは親imageを`FROM`し、上計2 fileだけを`/app/webapp/`へCOPYする。temporary imageは専用tag／image IDで固定する。
4. 実行前に`docker inspect`／image ID／container config／mount／port／env／source hashを固定し、明示承認後に対象serviceだけをinstrumented imageへrecreateする。
5. repository内sourceは編集しないため、dirty worktreeの反射・復元・checkoutは不要。`git add/commit/push/branch`も実行しない。

### Q2-5. 測定後の完全復元

1. 計装log／container inspect／image ID／開始終了hashを報告書へ固定する。
2. 対象serviceだけを保存済み親image ID `sha256:9c4674c5...d88f10`へrecreateする。temporary tagの付け替えではなくimage IDを照合する。
3. 復元container内で次を照合する。
   - `main.py`: `7fadb2e281a996e97c2fd496803dec6627b14043e1b9ed9c3eec837d0ce95dc1`
   - `push_broker.py`: `4c0409b73f14661ef3a33f9f3f870385e0b3311da1deb65e03b8b937efe43fd8`
   - その他source／protected 5件もStage 1開始値とMATCH。
4. instrumentation envがcontainerにないこと、restart 0／health／SUBSCRIBED／BOOK syncを確認する。
5. temporary image／build context／logをClaude検証が終わる前に削除しない。検証後の削除は対象を明示した別承認で行う。

repository sourceを直接編集する方式も理論上は可能だが、開始前dirtyがあり、改行混在も既知である。復元ミスの危険を避けるためtemporary overlay方式を推奨する。

---

## Q3. 計測環境（劣化中containerの扱い）

### Q3-1. 現行containerをそのまま計測母体にしない

劣化中の現行containerで追加計装を開始することは非推奨。理由は次のとおり。

- diagnostic WebSocketなしCPU baselineがmin 97.911%／mean 102.358%／p95 111.849%／max 119.700%。
- WebSocket opening handshakeが5秒timeout、`/health` 15秒timeout、その後`/api/health` 30秒timeout。
- upstream keepalive ping timeout (`1011`)、OI 10秒timeout複数、order book gapを観測。
- 2026-08-03 17:37 +09:00時点でCPU 99.14%／memory 738MiB。containerはrunning／restart 0／OOM falseだが、health応答が成立しない。

この状態から計測すると、起動後に蓄積したbacklog／connection degradation／memory growthと定常負荷を分けられない。計装hunkの追加overheadも評価できない。

### Q3-2. 推奨計測環境

1. 劣化containerの読取専用証拠を先に固定する。
2. ユーザー明示承認のmaintenance windowで、親image `9c4674c5...`から対象serviceだけをclean recreateする。
3. まず未計装の親imageでhealth GREEN／SUBSCRIBED／BOOK SYNCEDを満たすclean baseline区間を取る。CPU／memory／heartbeat外部intervalは少なくと600秒。
4. 同じcontainer config／mount／port／client数でtemporary instrumented imageへ切り替え、起動後の同一warm-upを経て600秒以上計測する。
5. 計測後は親image IDへ完全復元する。

別containerを同時にlive upstreamへ接続する方式は、upstream接続／DB／volume writerが二重化する危険があるため採用しない。Replayは安全だが現行liveのCPU／broadcast contentionと同条件ではなく、本測定の代替にならない。

### Q3-3. 証拠保全

劣化container自体を無期限に稼働保全する必要はない。応答遅延中の稼働継続は利用者への影響を拡大する。recreate前に次を読取専用で固定すれば、原因証拠は保てる。

- `docker inspect`全文、container／image ID、start time、restart／OOM、mount／env／port。
- `docker logs --since <start>`とそのhash。
- `docker stats`／cgroup CPU／memory／PIDs／thread CPU／FD／TCP state。
- `/health`／`/api/health`の応答またはtimeoutと実経過。
- host／container source SHA、`docker diff`、protected hash。
- heartbeat raw測定のサンプル数／min／mean／p95／max／outlier／canonical series hash。

container writable layer自体のforensic snapshotが必要と別途判定された場合だけ、`docker commit/export`を対象と復元用途を明示した別承認で行う。現時点で自動実行はしない。

---

## Q4. event-loop starvationへの対処要否

### Q4-1. priority queueだけで3000ms gateを満たさない可能性

**ある。しかも現在の証拠では無視できない。**

- client単位priority queueはheartbeatをbroker-wide network await／通常message backlogから分離する。
- しかしheartbeat taskが実行可能にならないevent-loop starvation中は、priority enqueue自体を実行できない。
- Stage 1でwake residual max 5189.144ms、ping RTT p95 3033.460ms／max 3668.609ms、HTTP health 30秒timeoutを観測。shared lockを除いてもevent-loop応答が3000msを超える実証がある。

### Q4-2. Stage分割

starvationの根本対処はpriority queue Stage 2に同梱せず、別Stageへ分ける。理由は次のとおり。

- priority queueの主な変更境界は`push_broker.py`／`main.py`のdelivery scheduling／lifecycle。
- CPU starvationの負荷源はpipeline normalization／book projection／storage／hook／WebApp render payload生成等を跨ぐ可能性があり、protected機能／完成済みconsumerへの影響境界が異なる。
- 両方を1回の変更に混ぜると、CPU改善とdelivery分離のどちらが効いたかを再び分離できなくなる。

推奨する分割は次のとおり。

- **Stage 1A:** 本回追記でtemporary instrumentationを直接測定し、lock／send／wakeの内訳を確定。
- **Stage 2A:** client単位single-writer + priority queueを`PushBroker`境界で実装。CPU workloadを変更しない。専用testとinternal timingでdelivery滞留解消を単独証明。
- **Stage 2B:** event-loop／CPU starvation負荷源の別調査・是正。Stage 1Aの直接wake測定が3000ms gateを単独超過する場合は必須。
- **Final runtime gate:** Stage 2A／2Bの必要な成果を反映後、server／browser max 3000ms未満を600秒以上で証明。このgateまで「恒久対処完了」としない。

Stage 1Aの直接測定でwake maxが3000ms未満であり、超過のほぼ全てがlock/sendに属すると確定した場合は、Stage 2Bを後続の一般performance課題として分離できる。ただし現在の外部証拠はその条件を支持していない。

### Q4-3. 責務範囲

- priority deliveryの設計／single-writer／bounded send／heartbeat queueは**Realtime UI Freshness / WebApp PushBrokerの責務**。
- CPU 100%飽和の個別負荷源とその最適化は、調査対象によってpipeline／storage／Hook／WebApp各moduleの責務となり、**priority queue実装自体のcode範囲外**。
- 一方、「LIVE decision配信が3000ms以内に生存確認できる」というSLOは**Realtime WebApp全体のrelease責務**。したがってCPU starvationを別module責務として完了判定から除外することはできない。

---

## 5. 最終推奨

1. Q1(a)を承認し、temporary overlay imageに限定したStage 1A instrumentation追記指示書を作る。
2. 劣化containerの読取専用証拠を固定後、別承認でclean baseline→instrumented measurement→親image復元を行う。
3. 直接wake遅延が3000msを超える場合はStage 2B starvation対処を必須とし、priority queueだけで恒久完了としない。
4. 本回の問い合わせ回答でsource／test／config／runtime／image／Git操作は行わない。

