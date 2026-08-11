# Realtime UI Freshness 恒久対処 第二段
## Stage 2A — client単位 single-writer + priority queue 実装報告書

**文書ID:** DE05M-RTUIF-HBPRI-STAGE2A-REPORT-001  
**版:** 0.3 (Stage 2A実装・test完了、runtime release gate NO-GO)  
**作成日:** 2026-08-03  
**実施者:** Codex  
**適用指示書:** DE05M-RTUIF-HBPRI-STAGE2A-INST-001  
**現在判定:** **NO-GO** — source/test実装は完了。600秒soakが3000ms契約を超過したため、正本§6/ディスパッチ§6に従い停止。Stage 2Bはrelease前必須。

---

## 0. Checkpoint

**記録時刻:** 2026-08-03 20:37:17 +09:00  
**承認範囲:** ディスパッチDE05M-RTUIF-HBPRI-STAGE2A-DISPATCH-002により、正本v1.1 §6手順2〜7。  
**完了済み:** 開始SHA照合、改行比率確認、全配信経路棚卸し、test波及調査、shutdown経路調査、実装設計選択。  
**未完了:** source実装、test変更、test実行、image構築、runtime soak。  
**本Stageで作成したfile:** 本報告書1件のみ。  
**source/test/config/runtime変更:** 0 (本checkpoint記録時点)。  
**再開位置:** `webapp/push_broker.py`のclient state / writer / priority queue実装。  

実装着手直前の再照合結果:

- 正本v1.1: `ddc8310b20251a1d72470406f1688137a3a98d3ebfc107498d622d1728747f8f` MATCH。
- Stage 1調査報告snapshot: `484634044157250c7a05ff8a0376696b53a2e31b5a1e92b8350d0c50cfbdc4aa` MATCH。
- `push_broker.py`: `4c0409b73f14661ef3a33f9f3f870385e0b3311da1deb65e03b8b937efe43fd8` MATCH。
- `main.py`: `7fadb2e281a996e97c2fd496803dec6627b14043e1b9ed9c3eec837d0ce95dc1` MATCH。
- GO受領: 2026-08-03、DE05M-RTUIF-HBPRI-STAGE2A-DISPATCH-002。

本件を層で表現すると、Stage 2Aは**WebSocket配信基盤周り**
(server-side delivery / transport scheduling layer)の是正である。
その上位は**Realtime UI鮮度判定・LIVE/STALE状態管理周り**
(browser-side freshness state / presentation control layer)である。
上位の判定logicは本Stageでは変更しない。

---

## 1. 開始時境界照合

### 1.1 実装対象source

| file | 指示値SHA-256 | Codex実測SHA-256 | 判定 |
|---|---|---|---|
| `webapp/push_broker.py` | `4c0409b73f14661ef3a33f9f3f870385e0b3311da1deb65e03b8b937efe43fd8` | `4c0409b73f14661ef3a33f9f3f870385e0b3311da1deb65e03b8b937efe43fd8` | MATCH |
| `webapp/main.py` | `7fadb2e281a996e97c2fd496803dec6627b14043e1b9ed9c3eec837d0ce95dc1` | `7fadb2e281a996e97c2fd496803dec6627b14043e1b9ed9c3eec837d0ce95dc1` | MATCH |

改行実測:

| file | bytes | LF総数 | CRLF | LF-only | CR |
|---|---:|---:|---:|---:|---:|
| `push_broker.py` | 28,984 | 672 | 3 | 669 | 3 |
| `main.py` | 45,644 | 1,137 | 1,041 | 96 | 1,041 |

`main.py`は指示値どおりCRLF/LF混在である。実装GO後も既存行の改行を
一括normalizeせず、編集箇所の周辺改行へ合わせる。

### 1.2 protected / consumer境界

| file | Codex実測SHA-256 | 判定 |
|---|---|---|
| `webapp/static/orderbook_heatmap.js` | `2da8849d8e77ce82066f02e95c996dde75a952f2a900fc02018e4ea74467388b` | MATCH |
| `webapp/static/time_sales.js` | `f59fec3f3478cc5a9b977c74978c3d8eb7c66e27a479a0b40fcf6d5f18f8d4c2` | MATCH |
| `webapp/static/footprint_canvas.js` | `987c5da72a7375495eb44bd9910a1b79b076226b2f0206cc8e3d3de2f08c01be` | MATCH |
| `webapp/static/index.html` | `3a025cd2ef7425e922a962fa80a438b0d31f5e77b9a16732aacfc4f3577c513c` | MATCH |
| `webapp/static/market_freshness.js` | `65c94cf5f90f37b381b1877c9ed1c4f0e93d92540ff90238dbc5c44af3483a48` | MATCH |

本調査中に上記5件を編集していない。consumer側の変更は不要と判断する。

---

## 2. 現行配信構造の全数棚卸し

### 2.1 集約構造

`webapp/push_broker.py`の現行構造は次のとおりである。

- `PushBroker._clients`はwsだけを保持する`set[Any]` (`push_broker.py:157`)。
- client集合lockは`_lock` (`:158`)。
- 全配信直列化lockは`_broadcast_lock` (`:159`)。
- `register()`は`_broadcast_lock`を保持し、最大5件のcacheを直接
  `ws.send_text()`した後にclient集合へ追加する (`:174-202`)。
- `_broadcast()`は`_broadcast_lock`を保持したままclient snapshotを取得し、
  全clientへのbounded sendを`asyncio.gather()`で完了まで待つ (`:218-238`)。
- client単位queueおよびwriter taskは存在しない。

したがって現行は、全clientを一つの共有lockで直列化する方式である。
Stage 1Aで実測したheartbeat遅延の第一原因とsource構造が一致する。

### 2.2 `_broadcast`呼出し全17経路

| # | sender method | payload type | call site | reconnect cache |
|---:|---|---|---|---|
| 1 | `on_trade` | `TICK` | `push_broker.py:240-255` | あり |
| 2 | `on_spot_price` | `SPOT_PRICE` | `:257-277` | あり |
| 3 | `on_tape_update` | `TAPE_UPDATE` | `:279-315` | なし |
| 4 | `on_book_update` | `BOOK_UPDATE` | `:319-368` | あり |
| 5 | `on_candle` | `CANDLE` | `:370-407` | なし |
| 6 | `on_analysis` | `ANALYSIS` | `:409-454` | なし |
| 7 | `on_absorption_state` | `ABSORPTION_STATE` | `:456-487` | あり |
| 8 | `on_flow_event` | `FLOW` | `:489-498` | なし |
| 9 | `on_flow_response` | `FLOW_RESPONSE` | `:500-528` | なし |
| 10 | `on_liquidation` | `LIQUIDATION` | `:530-533` | なし |
| 11 | `on_oi` | `OI` | `:535-559` | なし |
| 12 | `on_hfm_quote` | `HFM_QUOTE` | `:561-581` | あり |
| 13 | `on_combined_context` | `COMBINED_CONTEXT` | `:583-612` | なし |
| 14 | `on_bar_update` | `BAR_UPDATE` | `:615-654` | なし |
| 15 | `send_market_heartbeat` | `MARKET_HEARTBEAT` | `:656-664` | なし |
| 16 | `send_health` | `HEALTH` | `:666-668` | なし |
| 17 | `send_stats` | `STATS` | `:670-672` | なし |

全17経路は`_broadcast()`一箇所へ集約されている。heartbeatも例外ではなく、
`send_market_heartbeat()`から同じ共有`_broadcast_lock`とbounded sendへ入る。

### 2.3 reconnect cacheとheartbeat非干渉

cacheは次の5件だけであり、`register()`内の順序も固定されている
(`push_broker.py:179-185`)。

1. `TICK`
2. `SPOT_PRICE`
3. `HFM_QUOTE`
4. `BOOK_UPDATE`
5. `ABSORPTION_STATE`

`MARKET_HEARTBEAT`を格納するfieldはなく、`send_market_heartbeat()`もcacheへ代入しない。
heartbeat cacheなしという確定契約は現行でも満たされている。

---

## 3. 既存testへの波及調査

### 3.1 変わる同期契約

旧`_broadcast()`は、呼出しの`await`が戻った時点で全sendの成否が確定する。
Stage 2A後は`await _broadcast()`が各client queueへのenqueue完了で戻り、実送信は
client writerが非同期に行う。このため「sender methodをawaitした直後に`sent`を読む」
testは、そのままではraceになる。

testのpayload・順序・dead-client隔離assertionは削除も緩和もしない。
決定的なqueue drain待ちを追加した後、同じ意味をassertする。
固定sleepによるtest通過は採らない。

### 3.2 直接波及する既存test

次の33 testを直接波及対象として確認した。

#### `tests/webapp/test_push_broker.py` (13)

- `test_tick_payload_keeps_trade_id_for_latency_audit`
- `test_market_heartbeat_sequence_is_monotonic_and_never_cached`
- `test_slow_client_heartbeat_timeout_does_not_block_healthy_tick`
- `test_hfm_quote_payload_is_bid_ask_and_usd_spread`
- `test_late_browser_receives_latest_hfm_quote_immediately`
- `test_on_analysis_payload_shape`
- `test_on_analysis_serializes_imbalance_walls_and_effective_floor`
- `test_register_unregister_dead_client_removed`
- `test_candle_payload_footprint_levels_descending_and_va_ordered`
- `test_on_analysis_serializes_divergence_native_object`
- `test_on_flow_response_serializes_observations_without_signal_language`
- `test_on_flow_event_accepts_native_detector_event_and_keeps_event_time`
- `test_on_analysis_flow_events_include_original_timestamp_for_candle_markers`

#### `tests/webapp/test_market_freshness_ui.py` (4)

- `test_tick_payload_has_freshness_metadata_and_late_browser_gets_latest_tick`
- `test_failed_cached_tick_send_does_not_register_client`
- `test_slow_client_is_timed_out_without_blocking_healthy_client`
- `test_hanging_cached_send_does_not_hold_broker_locks`

#### `tests/webapp/test_book_update.py` (5)

- `test_book_update_payload_and_reconnect_cache_use_latest_projection`
- `test_book_sequence_is_contiguous_across_synced_fail_closed_and_recovery`
- `test_book_stream_changes_per_broker_lifecycle_and_sequence_restarts_at_one`
- `test_invalid_book_projection_does_not_consume_sequence`
- `test_broker_defensively_clears_levels_for_fail_closed_message`

#### `tests/webapp/test_bar_update.py` (6)

- `test_bar_update_payload_shape`
- `test_bar_update_empty_levels`
- `test_send_health_payload`
- `test_bar_update_numbers_are_strings`
- `test_bar_update_carries_vwap_value_and_quality`
- `test_candle_carries_exact_vwap_quality`

#### その他 (各1、計5)

- `tests/webapp/test_absorption_realtime_display.py::test_broker_broadcasts_active_and_clear_and_caches_latest_state`
- `tests/webapp/test_phase6_integration.py::test_reconnect_replays_latest_book_not_tape_and_exposes_sequence_gap`
- `tests/webapp/test_tape_update.py::test_push_broker_serializes_tape_and_does_not_replay_batch_on_reconnect`
- `tests/webapp/test_spot_reference_price.py::test_push_broker_caches_latest_spot_reference_for_late_browser`
- `tests/webapp/test_oi_context.py::test_push_broker_oi_payload_has_source_and_real_change`

`tests/webapp/test_broker.py`は`webapp.broker.PushBroker`を対象とする別実装のtestで、
今回の`webapp.push_broker.PushBroker`とは無関係である。文字列名だけで混入させない。

### 3.3 register cache契約の維持方針

cache送信も同一writerを通し、socketへのsingle-writerを破らない。一方で、現行の
「cache handoffが成功してから`register()`が正常完了する」「全cache合計0.5秒上限」
という外部契約は維持する。

実装は、cache itemを通常FIFOの先頭へenqueueし、最後のcache itemのcompletion barrierを
`register()`がlock外で待つ。待機全体に既存0.5秒deadlineを適用する。cache send失敗・
deadline超過時は当該clientだけを除去する。したがってcache専用assertionを
非同期だからという理由で弱める必要はない。

### 3.4 test更新方針

- live broadcast後のassert前に、client queueが空になりsend完了したことを待つ
  決定的APIを使用する。
- 各test終了時にbrokerをcloseし、writer task残留を0にする。
- slow/dead client testは、当該clientの除去とhealthy clientの完了を両方待ってから、
  現在と同じ隔離assertionを行う。
- payload内容、TICK/BOOK/Tape sequence、cache対象/非対象、Flowの意味は変えない。
- 既存assertionの削除、件数の緩和、固定sleepへの置換はしない。

追加する専用回帰test:

1. clientごとの同時`send_text()`最大実行数が必ず1。
2. 通常message A/B/CのFIFOをheartbeat割込後もA/B/Cとして維持。
3. 通常backlog中のheartbeatが次の未送信normalより先に送られる。
4. slow client 1本のtimeout/overflowがhealthy clientへ波及しない。
5. queue overflowでnormalを黙ってdropせず、当該clientだけをfail-closed切断。
6. heartbeatはoverflowで黙ってdropされない。
7. unregisterおよびbroker shutdown後のwriter task残留0。
8. reconnect cacheの5件順序と0.5秒total deadlineを維持。

既存lifespan回帰として、少なくとも次も再実行する。

- `test_push_broker.py::test_ws_hello_payload_version`
- `test_api.py::test_replay_worker_callbacks_reach_websocket_with_market_time`

---

## 4. shutdown経路の現物確認

`webapp/main.py`では全producer/taskを`app.state.tasks`へ集約する (`main.py:720-740`)。
shutdownはまず全taskをcancelし (`:745-746`)、全taskをawaitする (`:747-749`)。
その後にhook capture、persistent writer、depth history recorderを閉じる (`:750-758`)。

client writerは接続ごとに後から生成されるため、固定の`app.state.tasks`へ追加しない。
`PushBroker.close()`が全client writerのcancel/awaitを一元管理する。

GO後の配線位置は、既存producer群のcancel/await完了直後、hook/persistent writerを
閉じる前 (`main.py:749`と`:750`の間)とする。これにより:

- producerからの新規enqueueを止めてからclient writerを閉じる。
- 既存producerのcancel/await順序を変更しない。
- hook/DB/depth recorderの既存close順序を変更しない。
- WebSocket endpoint側の`unregister()`と競合してもidempotentに完了させる。

---

## 5. Stage 2A実装設計の固定案

### 5.1 queue方式

指示書§3.1の**方式1 (`asyncio.PriorityQueue`)**を選択する。

各queue itemは少なくとも次を持つ。

- priority: heartbeat=0、通常message=1。
- order: broker内で単調増加する一意のenqueue sequence。
- serialized text。
- message type / completion情報。

比較keyを`(priority, order)`とするため、同一priority内はFIFOとなる。
heartbeatは通常messageより前へ出られるが、通常message同士のorderは変わらない。
一意orderにより、同順位item比較時にwsやpayload自体が比較される事故も防ぐ。

2本queue方式より、優先度とFIFO規則が1個の比較keyに閉じ、`get()`前後のraceを
作りにくいため採用する。

### 5.2 client状態

`_clients: set[Any]`を、wsからclient stateを引ける構造へ置き換える。
各stateは次を保持する。

- ws本体。
- 上限付き`asyncio.PriorityQueue`。
- writer task 1本。
- closing/closed状態。
- 必要最小限の完了通知。

同一wsへの`_send_text()`はwriterだけが呼ぶ。register cache、heartbeat、全通常messageを
例外なく同じwriterへ通す。

### 5.3 enqueueと順序

- 通常message enqueueは短時間のenqueue直列化lockで順序を確定する。
- そのlock内ではclient snapshotと`put_nowait()`だけを行い、network I/Oを待たない。
- heartbeatは高priorityで各client queueへenqueueする。
- client集合lockはsnapshot/登録/除去だけに使い、network I/Oを含めない。
- overflow clientの退役処理はlock外で行い、他client enqueueを止めない。

旧`_broadcast_lock`のnetwork waitは消える。通常message順序を確定する短時間lockは残すが、
その責務は配信完了待ちではなくenqueue順序の採番だけである。

### 5.4 queue上限とoverflow

clientごとのqueue上限は**256 item**とする。

Stage 1Aの代表180秒区間では、主要normal送出は合計4,110件
(約22.83件/秒)であった。256件は平均約11.2秒分で、通常burstを吸収しつつ
clientごとのmemoryを有限にする暫定値である。Stage 2A soakでdepth high-water markを
必ず計測し、常態的な滞留がないことを確認する。

overflow時はoldest normal dropを採らない。normal FIFOとBOOK/Tape等のsequence意味を
黙って欠落させるためである。代わりに:

- 当該clientをactive集合から除去。
- 当該writerを停止。
- best-effortでsocketをclose。
- 他clientのqueue/writerは継続。

heartbeatもoverflowで黙って捨てない。enqueue不能なclient自体をfail-closedで切断する。

### 5.5 bounded send / failure隔離

各writerはqueueから1件取得し、既存`_send_text()`を使って0.5秒上限で送る。
timeout/例外時はそのclientだけをdead判定して終了する。writerのfinalizerが自stateを
active集合から除去し、自taskをawait/cancelしない構造にする。

`unregister()`はactive集合から先に除去し、lock外でwriterをcancel/awaitしqueueを破棄する。
`close()`はidempotentとし、全stateを一度snapshot/除去した後、全writerをcancel/awaitする。

### 5.6 consumer側

`index.html`と`market_freshness.js`の変更は不要である。
payload、heartbeat sequence、1000/3000ms、browser state machineは現状維持する。

---

## 6. 非影響境界

本設計はpayloadの内容・意味を変えない。特に次は変更しない。

- Heatmap adaptive stale / gap / sequence。
- Tape store / accepted trade / gap / sequence。
- Flow Price Responseの計算・表示・観測意味。
- 完成済み3段チャートの計算・geometry・表示意味。
- Hook / Strategy。
- browser側freshness state machine。
- heartbeat interval 1000ms / timeout 3000ms。

---

## 7. 実装前に解消が必要な指示書内の境界矛盾

指示書§1.1は「変更対象file (2件のみ)」として`push_broker.py`と`main.py`だけを
列挙している。一方、§4.4と§6手順4は、専用test作成と波及testの正当な更新を
必須としている。§5にもtest fileの許可行がない。

このままでは、必要testを更新すると§1.1違反、更新しないと§4.4/§6/DoD違反になる。
source実装前にtest変更allowlistを明示して矛盾を解消する必要がある。

推奨するtest allowlistは次の10件である。実変更は必要なhunkだけに限定する。

1. `tests/webapp/test_push_broker.py`
2. `tests/webapp/test_market_freshness_ui.py`
3. `tests/webapp/test_book_update.py`
4. `tests/webapp/test_bar_update.py`
5. `tests/webapp/test_absorption_realtime_display.py`
6. `tests/webapp/test_phase6_integration.py`
7. `tests/webapp/test_tape_update.py`
8. `tests/webapp/test_spot_reference_price.py`
9. `tests/webapp/test_oi_context.py`
10. `tests/webapp/test_api.py` (lifespan shutdown回帰を追加する場合のみ)

新規専用test fileを増やさず、priority/single-writer専用testは既存
`test_push_broker.py`へ集約できる。

この矛盾はsource設計の不明点ではなく、変更許可境界の問題である。
ユーザー/Claudeによるallowlist確定と明示GOを受領するまで実装しない。

---

## 8. Stage 1調査判定

### 完了

- 開始source 2件SHA: MATCH。
- protected/consumer 5件SHA: MATCH。
- `_broadcast`送出経路: 17/17件を全数確認。
- heartbeat cache: なし。
- per-client writer: 現行なし。
- 同期送信完了前提test: 33件を特定。
- shutdown配線位置: `main.py:749-750`間に固定。
- queue方式: client単位`asyncio.PriorityQueue`。
- queue上限: 256。
- overflow: 当該client fail-closed切断。silent dropなし。
- consumer変更: 不要。

### 旧STOP条件の解消

§7の境界矛盾は正本v1.1
(`ddc8310b20251a1d72470406f1688137a3a98d3ebfc107498d622d1728747f8f`)
で解消された。さらにDE05M-RTUIF-HBPRI-STAGE2A-DISPATCH-002でユーザー明示GOを
受領したため、旧STOP条件は2026-08-03 20:37:17 +09:00に解除された。

---

## 9. Stage 2A source実装

### 9.1 `webapp/push_broker.py`

実装した内容:

- clientごとの`_ClientState`にws、上限256の`asyncio.PriorityQueue`、writer task、
  closing状態、queue high-water markを保持。
- queue itemは`(priority, sequence)`だけを比較keyとし、payload/textは比較対象外。
- 同一socketへの`send_text()`はclient writer 1本だけが実行。
- 通常messageはpriority 1かつ投入sequence順。heartbeatはpriority 0。
- 通常messageのenqueue順は短時間の`_enqueue_lock`で直列化し、network I/Oを
  lock内で待たない。
- heartbeatは共有normal enqueue lockを経由せずclient集合lockだけでpriority enqueue。
- bounded sendは既存`CLIENT_SEND_TIMEOUT_SEC=0.5`を維持。
- queue overflow時はmessageを黙ってdropせず、当該clientだけをactive集合から除去、
  writer cancel/await、best-effort WebSocket close。healthy clientへ波及させない。
- reconnect cache 5件も同一writerへ通す。cache順序と全cache合計0.5秒deadlineを維持。
- `wait_until_idle()`を決定的test同期点として追加。
- `close()`をidempotentな全writer cancel/await経路として追加。
- queue最大滞留のruntime確認用に`client_queue_high_watermark`をadditiveで保持。

実装後SHA-256:

```text
953180e969679111fb502f0405cb4d2a691caf707d5b7594c2476a6ec8548a02
```

実装後実測: 36,036 bytes / LF 860 / CRLF 3 / CR 3。

### 9.2 `webapp/main.py`

既存producer task群のcancel/await完了直後、hook/persistent writer close前に
`await broker.close()`を追加した。content差分はこの2行だけである。

`apply_patch`直後に既存4行のCRLF→LF自己汚染を検出した。変更前copyとのcontent
alignmentにより当該4行をCRLFへ限定復元し、新規2行も周辺どおりCRLFにした。
広域normalizeは行っていない。

開始: CRLF 1,041 / LF-only 96 / LF総数1,137。  
終了: CRLF 1,043 / LF-only 96 / LF総数1,139。  
意図した新規2行分のCRLF増加だけであり、既存行の改行変化は0。

実装後SHA-256:

```text
adf09b07612ef0817a20779706990f946b50cb17c7879657918e40dd3372d20b
```

### 9.3 consumer / protected / timeout

- `index.html`: 開始値`3a025cd2...513c` MATCH、変更0。
- `market_freshness.js`: 開始値`65c94cf5...a48` MATCH、変更0。
- heartbeat interval 1000ms / timeout 3000ms: 不変。
- client send timeout 0.5秒: 不変。
- Heatmap / Tape / Flow Price Response / 3段チャート / Hook / Strategy: 変更0。

---

## 10. test更新と検証結果

### 10.1 更新した許可test file

実変更は事前列挙済みの次の5件だけである。

1. `tests/webapp/test_push_broker.py`
2. `tests/webapp/test_market_freshness_ui.py`
3. `tests/webapp/test_bar_update.py`
4. `tests/webapp/test_absorption_realtime_display.py`
5. `tests/webapp/test_phase6_integration.py`

14件の旧同期完了前提testへ決定的`wait_until_idle()`を追加した。payload、順序、件数、
dead-client隔離のassertionは削除・緩和・renameしていない。

専用回帰testを`test_push_broker.py`へ追加:

- single-writerの同時send最大1。
- heartbeat割込後もnormal A/B/C FIFO維持。
- queue 256 overflow時にslow clientだけを切断し、healthy 258/258件到達。
- `broker.close()`後の全writer task done、二重close安全。

### 10.2 test結果

波及test 10 file初回:

```text
14 failed, 105 passed
```

14 failureは全件事前列挙済みの同期完了前提。test追随後:

```text
122 passed in 11.20s
```

WebApp全体:

```text
1 failed, 201 passed in 13.97s
```

repository全体:

```text
1 failed, 832 passed, 1 skipped in 220.06s
```

唯一のfailure:

```text
tests/webapp/test_dom_tape_fusion_ui.py::
test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation
```

これは旧selector`body.phase5-fusion #right>#left`を要求する既知baselineである。
過去の複数checkpointおよび直前RTUIF checkpointでも同一failureが記録されている。
対象`index.html`のSHAはStage 2A開始値と一致し、本件変更と非重複。新規failureは0。
この既知testと`index.html`は変更していない。

### 10.3 source/test工程checkpoint

**記録時点:** source/test実装とrepository全体test完了後、runtime build前。  
**完了:** 正本§6手順2〜5。  
**未完了:** 正規image build、temporary overlay計装、600秒soak、正規image復元、runtime gate。  
**blocker:** なし。  
**次の再開位置:** Stage 2A正規imageを構築し、clean runtimeでhealth確認後、overlay計装soak。  

---

## 11. Runtime image構築・normal readiness checkpoint

### 11.1 正規Stage 2A image

```text
image ID: sha256:508bb78281aeb797f5e69d90e47a3bcb6c45e5f93e43ebd6273897f87ef6acb6
pin tag : rtuif-stage2a-normal-pin:508bb78281aeb797f5e69d90e47a3bcb6c45e5f93e43ebd6273897f87ef6acb6
```

image内の`main.py` / `push_broker.py`は§9のhost SHAと一致。protected 3件、
`index.html`、`market_freshness.js`も開始SHAと一致した。

### 11.2 temporary overlay image

repository外`C:\tmp\rtuif_stage2a_runtime_20260803_212500`へ、正規imageを親とする
overlay contextを作成した。overlay layerの変更は`/app/webapp/main.py`と
`/app/webapp/push_broker.py`だけである。

```text
overlay image ID: sha256:dd3c5ec726817c117977fb4dbac68eb7d5ef0a3ecd7e044d3b505b4e427957f5
pin tag        : rtuif-stage2a-instrumentation-pin:dd3c5ec726817c117977fb4dbac68eb7d5ef0a3ecd7e044d3b505b4e427957f5
```

計装OFF/ON isolated probeはいずれも1 heartbeat送信、single-writer closeをPASS。
protected/consumer 5件はoverlay内でも正規imageと同一SHA。

### 11.3 正規runtime readiness

正規Stage 2A imageへclean recreateしたcontainer:

```text
container ID: 4634608463c21691da9fc3be986676e1af816aac1a49946faa52444b3f66656a
restart: 0
OOM: false
```

起動直後のreadiness probe 2回は、Uvicornが`Waiting for application startup`中に
WebSocket handshakeを開始したためEOFで失敗。container/image failureではない。
startupは2026-08-03T12:39:48.668329Zに正常完了し、その後のretry2で:

```text
health_ok=true
api_green=true
upstream_state=SUBSCRIBED
book_synced=true
ready=true
```

**長時間処理前checkpoint:** 正規normal 600秒soak開始前。  
**blocker:** なし。  
**次の再開位置:** normal 600秒observer+cgroup測定。完了後overlayへclean切替。  

---

## 12. 正規Stage 2A runtime 600秒soak

### 12.1 測定条件と証拠

正規Stage 2A imageをclean recreateした§11.3のcontainerを、temporary overlay未適用の
状態で600.412秒測定した。observerとcgroup samplerはいずれもexit 0。

主要な保持証拠:

| file | bytes | SHA-256 |
|---|---:|---|
| `stage2a_normal_observer.jsonl` | 208,347 | `70b5548c2efb86d471e9fc23b69ff6e3b38567f50725ecd55d9c77edeb5f21e6` |
| `stage2a_normal_cgroup.jsonl` | 260,534 | `f72db7c8099cc17dca2391635c4bd9a6eb7643f6632bcaea4d41e69a2b8c6905` |
| `stage2a_normal_analysis.json` | 7,543 | `13a4d6b378a0d7e90ca43295d419977fc048572e98be0a813c95c7c4532187fc` |
| `stage2a_normal_orchestrator.json` | 610 | `dbebc8ac4fb6693ac5edb607672a0c8cc3b17c6ec13aa315594c028b31bed712` |

証拠保持directory:

```text
C:\tmp\rtuif_stage2a_runtime_20260803_212500
```

temporary overlay image/context/logはClaude検証完了まで削除しない。

### 12.2 heartbeat release gate

| 指標 | n | p95 | max | 3000ms以上 | 判定 |
|---|---:|---:|---:|---:|---|
| server `published_time`生成間隔 | 537 | 1,051.769ms | **12,627.091ms** | 9 | FAIL |
| browser monotonic受信間隔 | 537 | 1,061.070ms | **12,951.594ms** | 9 | FAIL |
| published-to-receive age | 538 | 30.880ms | 5,144.942ms | 2 | FAIL |

heartbeat受信数538、sequence gapは0。sequence 251〜263付近に複数の超過が集中し、
最大値はsequence 255→256でserver 12,627.091ms / browser 12,951.594msだった。

正本§4.5の必須release条件はserver/browserの両方が600秒以上にわたりmax 3000ms未満。
両方とも不達のため、Stage 2A runtime判定は**NO-GO**である。

### 12.3 CPU / memory / process

| 指標 | mean | p95 | max |
|---|---:|---:|---:|
| container CPU raw | 31.450% | 101.552% | 116.616% |
| sampler補正後CPU | 31.346% | 101.483% | 116.560% |
| memory | 396.870MiB | 457.957MiB | 609.660MiB |

600 samples、OOM kill 0、container restart 0。平均CPUはStage 1A時より低下した一方、
p95は100%を超え、3000ms超過は残存した。共有`_broadcast_lock`待ちの構造除去だけでは
release gateを満たさず、event-loop / storage / queueを含む残存starvationの調査が必要。

---

## 13. soak中に顕在化した別系統storage障害

2026-08-03T12:45:20.168075021Zに次が初出し、その後約10秒間隔で反復した。

```text
StorageError: [E4001] footprint parquet write failed: error closing file
StorageError: [E4003] background storage worker failed: [E4001] ...
```

これによりpipeline taskが停止した。停止時点の`/api/health`は次の状態:

```text
state=RED
pipeline=RED: pipeline task dead (E4003 -> E4001)
bar_flow=RED: no bar close
latency=RED: event lag
restart=0
OOM=false
```

重要な時系列分離:

- 最大heartbeat gapは12:44:40付近。
- storage error初出は12:45:20.168Z。
- したがって、少なくとも最大heartbeat gapはstorage error初出より先に発生している。

よってE4001/E4003は後半のRED/pipeline停止を説明する別release blockerだが、最初の
Stage 2A heartbeat gate不達をstorage errorだけで説明することはできない。
storage実装は本Stageの許可境界外であり、自己判断で修正・rollback・再起動しない。

---

## 14. 段階STOPと最終checkpoint

**記録時点:** Stage 2A正規imageの600秒soak完了、release gate不達検出後。  
**承認範囲:** 正本v1.1 §6手順2〜7、ディスパッチ002。  
**完了済み:** source実装、許可test更新、専用test、全体test、改行検証、protected SHA検証、正規image構築、clean readiness、正規600秒soak。  
**未完了:** Stage 2A後temporary overlayによる内部timing再測定、release。  
**停止理由:** server/browser max 3000ms未満を満たさない。ディスパッチ§6によりStage 2Bをrelease前必須として停止・報告する必要がある。  
**限定blocker:** (1) heartbeat残存starvation、(2) 別系統E4001/E4003 storage障害。  
**変更file:** §9のsource 2件、§10.1の許可test 5件、本報告書。protected/consumer 5件は変更0。  
**runtime:** 正規Stage 2A image `sha256:508bb782...acb6`のcontainerはrunning、restart 0 / OOM falseだがhealth RED。release不可。  
**未展開:** prepared instrumentation overlay `sha256:dd3c5ec...957f5`は作成・isolated probe済みだが、STOP規律に従いruntimeへ展開していない。  
**次の再開位置:** Claude独立検証後、Stage 2Bの調査/対処範囲と、storage障害を別系統として扱うか同時調査へ含めるかをユーザーが承認する地点。  

### 14.1 結論

- Stage 2A source実装自体は、client単位single-writer、heartbeat priority、normal FIFO、
  queue 256、overflow client隔離という確定設計どおり完了した。
- 専用testと既存testはPASSし、既知baseline以外の新規failureは0。
- shared `_broadcast_lock`によるheartbeat後方滞留は構造上除去した。
- しかしruntimeの3000ms契約は不達。Stage 2A単独ではreleaseできない。
- 指示書どおり**NO-GO / Stage 2B必須**として停止する。
