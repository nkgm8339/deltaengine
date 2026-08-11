# Realtime UI Freshness 恒久対処 第二段
## Stage 2A — client単位 single-writer + priority queue 実装指示書 V1

**文書ID:** DE05M-RTUIF-HBPRI-STAGE2A-INST-001
**版:** 1.1
**作成日:** 2026-08-03
**作成者:** Claude(統括)
**実施者:** Codex
**決定:** Stage 1A承認済み。3000ms超過の86.083%が共有`_broadcast_lock`待ち。
本Stageでその第一原因を除去する。

---

## 0. 目的と範囲

### 0.1 目的

`PushBroker`の配信を、共有`_broadcast_lock`直下の全client直列gatherから、
client単位のsingle-writer + deadline-aware priority queueへ置き換える。
これによりheartbeatが通常message backlogの背後で待たされる構造を除去し、
Stage 1Aで確定した超過の第一原因(lock wait 86.083%)を消す。

### 0.2 確定設計(ユーザー・Stage 1A確定・変更不可)

- 共有lock外からの並列直接`send_text()`は採らない。
- clientごとに単一writer task。同一socketへの送信は常に直列。
- clientごとにpriority queue。heartbeatを最優先で送出。
- 通常message同士の相対順序のみ維持。heartbeatは任意位置へ割込可。
- bounded send 0.5秒(`CLIENT_SEND_TIMEOUT_SEC=0.5`)維持。
- heartbeat cacheなし。
- timeout 1000ms / 3000ms のまま。
- Heatmap / Tape / Flow Price Response / 3段チャート / Hook / Strategy 変更禁止。

### 0.3 本Stageでやらないこと

- event-loop starvation / CPU飽和の根本対処(Stage 2B、条件付き保留)。
- timeout値の変更。
- consumer(browser)側のstate machineロジック変更(§3.5の最小配線を除く)。

---

## 1. 対象と前提

### 1.1 変更対象file(source 2件 + 波及test)

| file | 開始SHA-256(Stage 1A復元後) |
|---|---|
| `webapp/push_broker.py` | `4c0409b73f14661ef3a33f9f3f870385e0b3311da1deb65e03b8b937efe43fd8` |
| `webapp/main.py` | `7fadb2e281a996e97c2fd496803dec6627b14043e1b9ed9c3eec837d0ce95dc1` |

着手前に両fileの実SHA-256が上記と一致することを確認する。不一致なら停止し報告。
`main.py`はCRLF/LF混在(CRLF 1041 / LF 96)。指示書v1.1 §2.4の改行保持規律を適用する。
編集する行の改行コードを周辺既存行に合わせ、一括変換・normalizeを禁止する。

上記2 sourceに加え、配信意味の変更(enqueue即時・送信非同期化)により正当に
失敗する既存testの更新を許可対象に含める。ただし次を厳守する。

- 更新できるのは、§2.2の波及調査で「実装前に把握済みの想定fail」として列挙し、
  Stage 1調査報告へ記録したtestに限る。事前列挙のないtestを実装中に発見した場合は
  停止して報告し、更新前にStage 1節へ追記する。
- 更新は新挙動への追随に限る。既存assertionの緩和・削除・renameで通してはならない。
  同期完了前提のassertionを非同期配信前提へ書き換える場合も、検証する不変条件
  (最終的に全通常messageが相対順序で届く、heartbeatが届く等)は保持する。
- 配布default assertionや契約testを、値を弱めて通す変更は禁止する。
- test更新も変更境界(§5)とdiff管理の対象とし、更新したtest fileを開始終了で
  一覧化する。source 2件・許可testの外に新規diffがゼロであることを証明する。

### 1.2 protected(変更禁止・開始終了hash一致で証明)

```text
orderbook_heatmap.js : 2da8849d8e77ce82066f02e95c996dde75a952f2a900fc02018e4ea74467388b
time_sales.js        : f59fec3f3478cc5a9b977c74978c3d8eb7c66e27a479a0b40fcf6d5f18f8d4c2
footprint_canvas.js  : 987c5da72a7375495eb44bd9910a1b79b076226b2f0206cc8e3d3de2f08c01be
```

`index.html`(`3a025cd2...`)、`market_freshness.js`(`65c94cf5...`)は原則不変。
本Stageで配線変更が要る場合も§3.5の最小範囲に限定し、diff allowlistで管理する。

---

## 2. Stage 1調査(実装前・Codex実施)

実装前に次を現物で確定し、Stage 2A実装報告のStage 1節へ記録する。
実物未確認で設計を確定するとNO-GO手戻りになる(v3.2教訓)。

### 2.1 配信経路の全数棚卸し

現行`_broadcast`(push_broker.py:218-238)を呼ぶ全メソッドを列挙する。
`on_trade`他すべてのpayload送出経路が`_broadcast`単一集約であることを
source行番号で確認する。heartbeatが`send_market_heartbeat`(656行付近)経由で
`_broadcast`を通ることも確認する。

### 2.2 起動時テストへの波及調査

新しいwriter task lifecycleとqueue導入で失敗し得る既存testを棚卸しする。
特に次を実物で確認する。

- `tests/webapp/test_push_broker.py`(存在すれば)のbroadcast/register/unregister
  前提が、単一gather方式に依存したassertionを持つか。
- `_broadcast`の同期的完了(呼び出し即送信完了)を前提とするtestの有無。
  queue化で「enqueueは即時・実送信は非同期」に変わるため、送信完了を
  同期的にassertするtestは波及する。
- shutdown/lifespan系test(main.py)がtask cancel順序を前提とするか。

波及するtestを「実装前に把握済みの想定fail」として列挙し、書換え方針を
Stage 1節へ記録する。既存assertionの緩和・削除で通す計画がないことを明記する。

### 2.3 shutdown経路の確定

main.py `lifespan`(122行付近)とtask構成(`tasks = [pipeline_task, stats_task]`
638行付近)を確認し、writer task群をどこで生成・cancel・awaitするかを設計する。
既存のtask cancel順序を壊さないことを確認する。

---

## 3. 実装設計

### 3.1 client状態の構造化

現行は`self._clients: set[Any]`でwsのみ保持。これを、client単位の配信状態を
持つ構造へ拡張する。各clientにつき次を持つ。

- ws本体。
- priority queue(高優先=heartbeat / 通常=その他)。
- 単一writer task。
- 通常message用のFIFO順序保持。

実装方式はCodex事前調査で次に確定した。

- `asyncio.PriorityQueue`方式を採用する。
- clientごとにqueueを持ち、queue上限は256件とする。
- heartbeatを高優先、通常message(TICK/BOOK/Tape/Flow/BAR)を低優先とする。
- 同一priority内は投入順(FIFO)。通常message間の相対順序をsequence番号で保つ。
  heartbeat同士が同時滞留した場合も投入順を保つ。
- priority比較でpayload本体を比較対象にしない(dictの大小比較例外を避けるため、
  (priority, sequence)のtupleキー等で順序を決め、payloadは比較に含めない)。

queue上限256件の根拠と、Stage 2A soakでの妥当性確認方法を設計文に記す。
256件が過大/過小と判明した場合はsoak結果に基づき見直す。

### 3.2 writer task(client単位single-writer)

各clientにつき1つのwriter taskを起動する。writerは自clientのqueueから
1件ずつ取り出し、`_send_text`(bounded 0.5秒)で送る。同一socketへの送信は
このwriter 1本のみが行うため、並列send競合は構造的に発生しない。

- queueから取得→`_send_text`→次、を繰り返す。
- `_send_text`がtimeout/例外なら、そのclientをdead判定しwriter終了+unregister。
- 1 clientのwriter停止は他clientのwriter/queueに波及しない
  (第一是正のslow-client隔離原則を維持)。

### 3.3 enqueue(旧`_broadcast`の置換)

旧`_broadcast`の「lock取得 + 全client gather send」を、
「client集合スナップショットを取り、各client queueへenqueue」に置き換える。

- enqueueはnon-blocking(queue上限内なら即時)。ここでnetwork awaitしない。
  これがlock wait除去の核心。enqueueは共有lockを保持したままnetwork I/Oを待たない。
- 通常message(TICK/BOOK/Tape/Flow/BAR)は通常priorityでenqueue。
- heartbeatは高priorityでenqueue(§3.4)。
- client集合の読取スナップショットは短時間の`_lock`保持のみ。network awaitを含めない。

### 3.4 heartbeat priority enqueue

`send_market_heartbeat`(656行付近)の送出を、各client queueへの高priority
enqueueに変更する。heartbeatはcacheしない(確定制約)。heartbeatが通常backlogの
先頭へ割り込むことで、通常message滞留中でもheartbeatが3000ms以内に届く。

### 3.5 queue overflow / bounded 挙動

- 各client queueに上限を設ける。上限値はStage 1で決め設計文に記す
  (暫定の目安を置き、Stage 2A soakで妥当性確認)。
- overflow時挙動: queueが256件上限に達した場合、黙ってmessageを捨てず、
  当該clientのみを切断する(writer終了 + unregister)。他clientへ波及させない。
  これは第一是正のslow-client隔離原則と一致する。「黙ってdrop」は
  consumerが欠落を検知できないため採らない。切断はconsumer側のWebSocket
  close検知→再接続→再同期へ繋がり、欠落した状態のままLIVE表示を続けるより安全。
- heartbeatはoverflow起因でも生存信号として扱うが、そもそもqueue上限に達する前に
  当該clientを切断するため、heartbeatだけを特別に残す分岐は要さない。
- bounded send 0.5秒は各writer内の`_send_text`で維持。

### 3.6 lifecycle(register / unregister / shutdown)

- register: client状態を作りqueueとwriter taskを起動。cache handoff(現行187-200)は
  維持。heartbeat cacheは追加しない。
- unregister: writer taskをcancelしawait、queueを破棄、client集合から除去。
- shutdown(main.py lifespan): 全writer taskを確実にcancel/awaitする経路を追加。
  既存のtask cancel順序を壊さない。

### 3.7 consumer側(index.html / market_freshness.js)

原則不変。browser state machineのheartbeat判定ロジックは変更しない。
サーバ配信順序が変わっても、通常message相対順序とheartbeat到達は保たれるため、
consumer変更は不要なのが望ましい。もし配線変更が不可避な場合のみ、
§1.2のdiff allowlist管理下で最小変更に限定し、Flow/3段チャート/Heatmap/Tapeの
表示・計算・意味に触れないことを証明する。

---

## 4. 検証gate(Stage 2A完了後・全PASSでruntime反映可)

### 4.1 内部timing(実装効果の直接確認)

Stage 1Aの計装(temporary overlay方式、可逆)を再適用し、Stage 2A後の
lock wait / wake / send 内訳を再測定する。次を必須とする。

- heartbeatの共有lock wait寄与が実装前(86.083%)から大幅に消えること。
- server生成間隔の最大が3000ms未満。
- browser受信間隔の最大が3000ms未満。
- 上記を600秒以上のsoakで確認。

計装は必ずtemporary overlay imageで行い、測定後に親image
`sha256:9c4674c5...d88f10`相当(Stage 2A実装後の正規image)へ復元する。
repository source直接編集での計装は禁止。

### 4.2 順序・隔離

- 通常message(TICK/BOOK/Tape/Flow/BAR)の相対順序が保たれる検証。
- slow client 1本がheartbeat/通常messageを他clientへ波及停止させない検証。
- heartbeat task停止時に他clientのwriterをcancelしない検証。
- shutdownで全writer taskがcancel/awaitされる検証。

### 4.3 protected不変・境界

- protected 3件の開始終了SHA一致。
- Heatmap adaptive stale / gap / sequence の既存test差分ゼロ。
- Tape store / gap / accepted trade順序を変更しない検証。
- index.html を変更した場合、diff allowlist内のhunkのみで、それ以外の
  新規diffがゼロ。

### 4.4 test / 全体

- 専用test(新規writer/queue/priority)。
- `tests/webapp/test_push_broker.py`他、§2.2で把握した波及testの正当な更新
  (緩和・削除でなく新挙動への追随)。
- WebApp全体 / repository全体のtest。既知baseline以外の新規failゼロ。
- main.py の CRLF/LF 比率が意図した増減のみ(指示書v1.1 §2.4)。

### 4.5 runtime soak(必須release条件)

- server生成・browser受信ともに最大3000ms未満を600秒以上で証明。
- health GREEN / SUBSCRIBED / BOOK SYNCED / restart 0 / OOM false。
- これを満たさない場合、Stage 2B(starvation対処)をrelease前必須とする。

---

## 5. 変更境界(Stage 2A)

| 対象 | 許可 | 禁止 |
|---|---|---|
| `push_broker.py` | writer/queue/priority実装 | payload意味・TICK/BOOK/Tape内容変更 |
| `main.py` | writer lifecycle wiring、shutdown cancel | pipeline/analysis callback変更 |
| `index.html`/`market_freshness.js` | §3.5の最小配線のみ(必要時) | chart計算・layout・表示意味変更 |
| protected 3件 | なし | いかなる変更も |
| Heatmap/Tape/Flow/3段/Hook/Strategy | なし | いかなる変更も |
| timeout値 | なし | 1000/3000msの変更 |

---

## 6. 実装手順(段階stop)

1. §1.1 開始SHA照合。§2 Stage 1調査(配線棚卸し・test波及・shutdown経路)を
   報告書へ記録しstop。ユーザー/Claude確認後に実装へ。
2. push_broker.py へ client状態・writer・priority queue・enqueue置換を実装。
3. main.py へ writer lifecycle と shutdown cancel を配線。
4. 専用test作成、波及test更新。
5. 全体test。CRLF/LF検証。protected hash検証。
6. temporary overlay で計装soak(§4.1)。max 3000ms未満を確認。
7. 実装後 source 実物一式と全証拠を提出。Claude独立検証。

各段でsource/test以外への波及、protected変更、timeout変更が無いことを確認する。
git add/commit/pushはしない。

---

## 7. 完了条件(DoD)

1. §2 Stage 1調査結果(配線棚卸し・test波及一覧・shutdown設計)。
2. §3設計に沿った実装。
3. §4検証gate全PASS(内部timing・順序隔離・protected・test・soak)。
4. 実装後 push_broker.py / main.py の実SHA-256、CRLF/LF比率。
5. protected 3件の開始終了一致証明。
6. runtime soak max 3000ms未満(server/browser)の直接証拠。
7. 単一Stage 2A報告書へ集約。証拠保持。

Stage 2A報告はClaudeが独立検証する。自己申告・test PASS・runtime GREENだけを
承認根拠にしない。実物diff・source hash・soak実測ログ・計装点を独立照合する。

---

## 8. 実装開始条件

本Stage 2Aの実装開始(手順2以降)は、§2 Stage 1調査の完了と、ユーザーの明示GOによる。
手順1(調査)まではStage 1A承認をもって着手してよい。実装(source変更)は
調査提出後の明示GOを待つ。決定はユーザーが下し、Claudeが文書化する。
