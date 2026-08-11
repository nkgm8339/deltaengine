# Realtime UI Freshness Heartbeat 恒久対処
## 実装指示書 V1.1

- 作成日: 2026-08-03 JST
- 対象repository: `DeltaEngine05M`
- branch: `feature/footprint-dom-tape`
- source基準HEAD: `7552bc3487a3539dca9c7830e92de7cca8884c4f`
- status: **指示書完成・実装NO-GO**
- 実装開始条件: 本指示書の独立レビュー完了とユーザーの別途明示GO

---

## 0. Authorityと目的

本指示書は次の2文書と独立レビュー結果を正本とする。

1. `REALTIME_UI_FRESHNESS_TIMEOUT_CURRENT_STATE_AND_REMEDIATION_REVIEW_20260803.md`
2. `REALTIME_UI_FRESHNESS_FIX_CHECKPOINT_20260802.md`

目的は、TICKをheartbeatとして誤用した`TICK_TIMEOUT`連発と、価格鮮度がHeatmap／Tapeへ波及する誤結合を恒久是正することである。

本変更では次を別stateとして実装する。

- browser transport
- Binance upstream connection
- server-to-browser delivery heartbeat
- USD-M decision price
- Heatmap BOOK freshness
- Spot reference freshness

timeout延長、BOOKによるTICK timer延命、TICK timeoutによる再接続は禁止する。

---

## 1. 独立レビュー確定値

以下を変更してはならない確定値とする。

| 項目 | 確定値 |
|---|---|
| 恒久対処 | 専用`MARKET_HEARTBEAT`を採用 |
| heartbeat interval | 1000ms |
| heartbeat timeout | 3000ms（interval×3） |
| client timer | monotonic受信間隔。browser wall clockとの絶対時刻比較禁止 |
| heartbeat cache | 禁止 |
| upstream fresh | connector state=`SUBSCRIBED`かつserver算出`upstream_age_ms <= 3000`かつpipeline alive |
| replay | `mode`を明示し、live freshness guardをdisable |
| stale復帰 | fresh heartbeat受理後のfresh TICK必須 |
| Heatmap／Tape | decision price freshnessから完全分離 |
| PushBroker bounded send | 第一是正の0.5秒上限を維持 |
| 暫定策 | 挟まない。恒久対処を一括実装 |

---

## 2. 実装開始前precondition

### 2.1 必読

実装担当は最初に次を全文読む。

- `ArchitectureRepository/00_Master/PROJECT_MEMORY.md`
- 本指示書
- §0記載の正本文書2点
- `ArchitectureRepository/30_Modules/WebApp/Specifications/WebSocketPayload_Spec_v1.md`

### 2.2 現物SHA-256 precondition

次のreview-time hashと実装開始時の現物が一致しない場合、実装を開始せずcheckpointへ差異を記録してSTOPする。

| file | SHA-256 |
|---|---|
| `src/acquisition/connector.py` | `458c902f622de0791f1c25fd3c23e87c36062dcf1a893bfaf2a6ea0fe068b78f` |
| `src/config.py` | `1e8207e7853170be0d848e77a076973a42ef98246287bced0f3af0f532f3f7f5` |
| `config/config.yaml` | `7f1203055bd85add19fc8cb8eb9e50842e6ca0d76c7723c6a328115f2691823b` |
| `webapp/main.py` | `57f40d3efdadff6ec21509e10f976fa733a1603284adb14e0f98639a270b1d9a` |
| `webapp/push_broker.py` | `d072c256cb722f61a699eb0dec1993ce0d50543d9e39d58c6dc567451729262c` |
| `webapp/static/market_freshness.js` | `254ab8d289b8c056f603e5f3c52166cb95df1118e99251548a49ed053df5f93d` |
| `webapp/static/index.html` | `d61471dce0058a156647775370709561d085da0c4fb20f56b477d963adc4b79c` |

hash値は小文字・大文字を区別せず比較する。

### 2.3 dirty worktree保護

repositoryには本件開始前から別件のdirty／untracked fileがある。`git reset`、`git checkout`、stash apply、clean、広域formatを禁止する。

開始時に次をcheckpoint本文へ直接記録する。

- 現在時刻
- branch／HEAD
- `git status --short`
- 対象file SHA-256
- protected file SHA-256
- 許可fileと開始前dirty状態

新規の調査script、CSV、manifest fileは作成しない。証拠は既存checkpoint本文へ集約する。

### 2.4 改行コード保持

`webapp/main.py`はCRLFとLFの混在fileである(review時点の実測: CRLF 954行、LF 96行、
全1050行)。他の許可file(`index.html`、`market_freshness.js`、`connector.py`、
`config.py`、`push_broker.py`、`config.yaml`)はLFである。

要件:

- 各許可fileを編集する際、新規行・変更行の改行コードを当該file既存行の改行コードに
  合わせる。`main.py`へ行を挿入・変更する場合はCRLFを用いる。周辺がLFの箇所は
  LFを用いる。
- file全体のCRLF↔LF一括変換、改行正規化、`dos2unix`／`unix2dos`相当の操作を禁止する。
- editor／tool設定による自動改行変換(autocrlf相当)を無効化し、既存の改行を保存する。
- 各許可fileについて、開始時と終了時にCRLF行数・LF行数・総行数を計測し、checkpointへ
  記録する。改行コード比率が本件変更の意図した増減以外で変化した場合はFAILとし、
  それ以上hunkを追加せずSTOPする。
- 意図した増減とは、そのfileへ追加・削除した行数に対応する改行コードの増減のみを指す。
  既存行の改行コードは変更しない。

---

## 3. 変更許可file

次だけを変更してよい。

### Production／config

1. `Delta_Engine_Pro4web/src/acquisition/connector.py`
2. `Delta_Engine_Pro4web/src/config.py`
3. `Delta_Engine_Pro4web/config/config.yaml`
4. `Delta_Engine_Pro4web/webapp/push_broker.py`
5. `Delta_Engine_Pro4web/webapp/main.py`
6. `Delta_Engine_Pro4web/webapp/static/market_freshness.js`
7. `Delta_Engine_Pro4web/webapp/static/index.html`

### Test

8. `Delta_Engine_Pro4web/tests/acquisition/test_acquisition.py`
9. `Delta_Engine_Pro4web/tests/webapp/test_market_freshness_ui.py`
10. `Delta_Engine_Pro4web/tests/webapp/test_push_broker.py`
11. `Delta_Engine_Pro4web/tests/webapp/test_api.py`
12. 既存のHeatmap／Tape／DOM regression testはassertion追加だけ許可。fixture意味・期待表示変更は禁止。

### Documentation／checkpoint

13. `ArchitectureRepository/30_Modules/WebApp/Specifications/WebSocketPayload_Spec_v1.md`
14. `ArchitectureRepository/00_Master/REALTIME_UI_FRESHNESS_FIX_CHECKPOINT_20260802.md`
15. 実装完了報告書1点。実装完了時だけ作成可。

上記以外のfile変更を検出した場合はFAILし、本件hunkをそれ以上追加せずSTOPする。

---

## 4. 変更禁止範囲

次は明示的に変更禁止とする。

- `webapp/static/orderbook_heatmap.js`
- `webapp/static/time_sales.js`
- `webapp/static/footprint_canvas.js`
- Heatmap renderer、BookStore、履歴、色、layout、操作、adaptive stale
- Flow Price Responseの計算、表示、state、window
- 完成済み3段チャートの計算、表示、意味
- `src/orderflow/hooks/**`
- `src/strategy_engine/**`
- Hook threshold、Strategy state、取引判断
- Footprint／POC／VA／Imbalance計算
- Binance SpotをUSD-M判断入力へ混入する変更
- TICK、BOOK、Tape既存payload fieldの意味変更または削除
- database schema／保存data

開始時と終了時に最低でも次のfull-file hash一致を証明する。

| protected file | 開始時review hash |
|---|---|
| `webapp/static/orderbook_heatmap.js` | `2da8849d8e77ce82066f02e95c996dde75a952f2a900fc02018e4ea74467388b` |
| `webapp/static/time_sales.js` | `f59fec3f3478cc5a9b977c74978c3d8eb7c66e27a479a0b40fcf6d5f18f8d4c2` |
| `webapp/static/footprint_canvas.js` | `987c5da72a7375495eb44bd9910a1b79b076226b2f0206cc8e3d3de2f08c01be` |

`src/orderflow/hooks/**`と`src/strategy_engine/**`は全file SHA-256を開始時checkpointへ列挙し、終了時に全件一致を確認する。別manifest fileは禁止する。

`index.html`は許可fileだが、Flow Price Responseと3段チャートを内包する。§9の許可anchor以外にdiff hunkが一つでもあればFAILとする。

---

## 5. Config契約

`webapp`設定へ次をadditiveに追加する。

```yaml
market_heartbeat_interval_ms: 1000
market_heartbeat_timeout_ms: 3000
```

要件:

- 両方とも正整数
- `market_heartbeat_timeout_ms >= market_heartbeat_interval_ms * 3`
- production設定値は1000／3000
- server upstream age閾値は`market_heartbeat_timeout_ms`と同値
- browserへHELLOから配信し、browser sourceへ1000／3000を重複hard-codeしない
- invalid configはstartup時にfail fast
- Spot freshness値は変更しない

---

## 6. ExchangeConnector additive observability

対象anchor:

- `connector.py:45 class ExchangeConnector`
- `connector.py:85 self.messages_out = 0`
- `connector.py:165 async for message in transport`

additiveに次を持たせる。

- `last_message_received_at: datetime | None`
- monotonic基準の最終raw frame受信値
- test注入可能なmonotonic clock
- read-only `message_age_ms()`相当API

raw frameをsocketから取得した直後、`out_queue.put()`より前にwall-clock監査時刻とmonotonic時刻を更新する。

禁止:

- state遷移変更
- reconnect条件・delay・retry変更
- `messages_out`意味変更
- queue順序・drop policy変更
- raw frame内容変更
- normalizer／BOOK処理変更

`upstream_age_ms`はserver内monotonic差分だけで算出する。browser clockを使用しない。

---

## 7. MARKET_HEARTBEAT payload契約

新規additive message type:

```json
{
  "v": 1,
  "type": "MARKET_HEARTBEAT",
  "time": "2026-08-03T00:00:00.000000+00:00",
  "symbol": "BTCUSDT",
  "payload": {
    "mode": "live",
    "heartbeat_sequence": 123,
    "published_time": "2026-08-03T00:00:00.000000+00:00",
    "upstream_state": "SUBSCRIBED",
    "upstream_last_message_time": "2026-08-02T23:59:59.950000+00:00",
    "upstream_age_ms": 50,
    "upstream_fresh": true,
    "pipeline_alive": true
  }
}
```

要件:

- `heartbeat_sequence`はserver process lifecycle内で1開始・1増分
- intervalは1000ms
- `upstream_fresh`はserverで次のAND条件により算出
  - mode=`live`
  - connector state=`SUBSCRIBED`
  - `upstream_age_ms`が非nullかつ0以上3000以下
  - pipeline task alive
- connector未生成／未接続時はstateを現状どおり表し、fresh=false
- heartbeatは既存`PushBroker._broadcast()`を通す
- heartbeatを`register()`のreconnect cacheへ追加しない
- `_latest_heartbeat_message`を作らない
- slow client timeoutは既存0.5秒を使用
- heartbeat送信失敗でpipeline、BOOK、Tape taskをcancelしない
- unknown message typeを無視する既存forward compatibilityを維持

`PushBroker`の変更anchorは`class PushBroker`、`_broadcast()`、`send_health()`／`send_stats()`近傍とする。

---

## 8. main lifecycle／HELLO契約

対象anchor:

- `main.py:122 lifespan`
- `main.py:638 tasks = [pipeline_task, stats_task]`
- `main.py:692 ws_endpoint`
- `main.py:697 HELLO`

### Live mode

- heartbeat taskをlifespanで1個だけ起動
- 最初のheartbeatをtask起動後速やかに送信し、その後1000ms間隔
- taskを`app.state.tasks`へ含める
- shutdown時は既存規律どおりcancelしawaitする
- pipeline task生存、connector state、connector ageからpayloadを生成

### Replay mode

- live `MARKET_HEARTBEAT` taskを起動しない
- HELLOへ`market_mode="replay"`を明示
- browserのlive freshness guardをdisable
- present-day live connector stateをreplayへ混入しない

### HELLO additive field

```json
{
  "market_mode": "live",
  "market_heartbeat_interval_ms": 1000,
  "market_heartbeat_timeout_ms": 3000
}
```

既存HELLO fieldを削除・変更しない。

---

## 9. Browser state machine

対象anchor:

- `market_freshness.js:17` 現行guard
- `index.html:1024` guard生成
- `index.html:1032` connect
- `index.html:1041` renderMarketFreshness
- `index.html:1105` HELLO case
- `index.html:1108` TICK case
- `index.html:1159` onBookUpdate
- `index.html:1165` onTapeUpdate

### 9.1 Guardを責務別に分離

`market_freshness.js`には少なくとも次を別classとして持たせる。

- USD-M live用heartbeat guard
- Spot表示専用event freshness guard

現行Spotの5秒表示鮮度契約をUSD-M heartbeatへ混合しない。

### 9.2 Live heartbeat guard

browser側は`performance.now()`相当のmonotonic clockでheartbeat受信間隔だけを測る。

禁止:

- heartbeat `published_time`と`Date.now()`の差でtimeout判定
- TICK absence timer
- BOOK／Tape／CANDLEをheartbeat代用
- freshness guardから`ws.close()`を呼ぶこと

state遷移:

```text
socket open
  -> SYNCING / WAITING_FOR_LIVE_HEARTBEAT

fresh live heartbeat
  -> SYNCING / WAITING_FOR_FRESH_TICK

fresh TICK
  -> LIVE

heartbeat受信から3000ms超
  -> STALE / HEARTBEAT_TIMEOUT

heartbeat upstream_fresh=false
  -> STALE / UPSTREAM_NOT_FRESH

pipeline_alive=false
  -> STALE / PIPELINE_NOT_ALIVE

STALE後のfresh heartbeat
  -> SYNCING / WAITING_FOR_FRESH_TICK

その後のfresh TICK
  -> LIVE

actual socket close/error
  -> RECONNECTING
```

heartbeat 1回dropではSTALEにならず、3回相当の無受信でSTALEになる。

TICKの既存price、`published_time`、`source_age_ms` validationは維持するが、最後のTICK受信からの経過だけでSTALEへ遷移してはならない。

### 9.3 Replay

HELLO `market_mode=replay`の場合:

- live heartbeat timeoutを起動しない
- live heartbeatを受けた場合はmode mismatchとして破棄
- historical event timeをclient wall clockと比較してSTALEにしない
- UIへlive dataと誤表示しない。stateは明示的にREPLAY相当とする

---

## 10. Heatmap／Tape／DOM分離

### 10.1 Transport接続

`HEATMAP_UI.setConnected()`と`TAPE_UI.setConnected()`は次だけで操作する。

- WebSocket `onopen` -> true
- WebSocket `onclose`／`onerror`によるclose -> false

`renderMarketFreshness()`から両呼出しを完全撤去する。

### 10.2 Heatmap BOOK routing

`onBookUpdate()`は次の順序にする。

1. payloadをHeatmapへ渡す
2. Heatmap自身が既存`sync_state`、sequence、adaptive staleで判定
3. decision priceがSTALEの場合、LIVE DOMなどdecision consumerだけを後段で停止

`S.marketFresh=false`を理由にHeatmapへの`BOOK_UPDATE`を破棄してはならない。

### 10.3 Tape routing

`onTapeUpdate()`はbrowser transportがopenである限り既存Tape storeへ渡す。無約定またはdecision price STALEをTapeのRECONNECTING表示へ流用しない。

Tape store、gap検知、sequence、row、filter、DOM-link表示は変更しない。

### 10.4 Decision consumer

価格判断を必要とする次のconsumerはheartbeat decision freshnessでfail closedを維持する。

- USD-M headline price
- LIVE DOMの判断表示
- price依存の現在値projection
- live decision banner

Heatmap history ingestionとTape transport ingestionはdecision consumerではない。

---

## 11. `index.html` diff allowlist

`index.html`の変更を次のsemantic anchorに限定する。

- WebSocket block
- USD-M guard生成
- WebSocket `onopen/onclose`
- `renderMarketFreshness`
- HELLO／MARKET_HEARTBEAT dispatch
- `onTick`
- `onBookUpdate`
- `onTapeUpdate`
- TAPE／HEATMAP初期化直後のtransport state同期が必要な場合、その1 hunk

次の領域にdiffを出してはならない。

- CSS／layout
- Flow Price Response handler／renderer
- 3段チャートhandler／renderer
- Heatmap controls／geometry／render設定
- Footprint／POC／VA／Imbalance
- DOM price→Tape link
- Spot表示layout／basis計算
- Hook／Strategy表示

行番号は補助情報であり、関数名・message type・field名・現物内容をanchor正本とする。

---

## 12. 必須test

### Connector

1. raw frame受信直後にwall／monotonic観測値を更新
2. queue待ちが発生しても受信時刻が後ろへずれない
3. `message_age_ms()`がmonotonicだけを使用
4. state／reconnect／messages_out既存testが無変更でPASS

### Server heartbeat

5. sequenceが1開始・1増分
6. SUBSCRIBED＋age内＋pipeline aliveだけがfresh=true
7. connectorなし、age超過、pipeline dead、reconnectingでfresh=false
8. heartbeatはregister cacheへ入らない
9. slow clientのheartbeat send timeout後もhealthy clientへTICK／BOOK配信可能
10. heartbeat taskのshutdown cancel／await
11. replayでlive heartbeat taskが起動しない

### Browser state machine

12. heartbeatを1秒ごとに受け、TICKが10秒以上なくてもLIVE維持
13. 3000ms heartbeat無受信でSTALE
14. 1 heartbeat dropではLIVE維持
15. heartbeat timeoutでも`ws.close()`を呼ばない
16. client wall clockを±5分ずらしてもheartbeat判定不変
17. upstream_fresh=falseでSTALE
18. pipeline_alive=falseでSTALE
19. stale後、fresh heartbeatだけでは価格を再表示しない
20. その後のfresh TICKで同一socket上のLIVEへ復帰
21. heartbeat mode mismatchをreject
22. replayでlive heartbeat timeoutを起動しない
23. Spotの既存5秒表示freshness testがPASS

### Heatmap／Tape非影響

24. decision price STALEでもBOOK_UPDATEがHeatmapへ渡る
25. `renderMarketFreshness()`がHeatmap／Tape connectedを操作しない
26. actual socket open/closeだけがHeatmap／Tape connectedを変更
27. Heatmap source SHA-256開始終了一致
28. Heatmap既存全test PASS
29. Tape source SHA-256開始終了一致
30. Tape既存全test PASS
31. DOM decision表示はSTALE中fail closed

### Regression

32. 専用test全PASS
33. acquisition全test
34. PushBroker／WebSocket lifecycle全test
35. Heatmap／DOM／Tape／Spot関連全test
36. WebApp全体
37. repository全体
38. 既知baseline failureは開始前と同一であることを証明。新規failureへ混在させない

testを期待値緩和で通してはならない。既存fixtureの市場意味を変更してはならない。

---

## 13. Checkpoint規律

既存`REALTIME_UI_FRESHNESS_FIX_CHECKPOINT_20260802.md`一つへ証拠を集約する。

最低更新点:

1. 最初のsource変更前
2. connector/config完了後
3. server heartbeat完了後
4. browser state machine完了後
5. Heatmap／Tape分離完了後
6. 関連test後
7. 全体test前後
8. runtime反映承認要求前
9. runtime反映後
10. 最終終了前

各記録に次を含める。

- JST時刻
- 承認範囲
- 完了／未完了
- 変更file
- test結果
- protected hash結果
- blockerの限定範囲
- 次の再開位置

---

## 14. Runtime反映gate

source実装GOとruntime反映GOを同一と解釈してはならない。

次を全件満たした時点で停止し、対象`deltaengine_clone`だけのbuild/recreate承認を求める。

- 専用・関連・WebApp・repository test完了
- diff check PASS
- allowed file以外の新規diff 0
- 各許可fileのCRLF／LF行数が、追加・削除行に対応する意図した増減のみで、
  既存行の改行コードが変化していないことをcheckpointで証明
- protected full-file／tree hash一致
- `index.html` diff allowlist適合
- heartbeat cache不存在
- replay isolation test PASS
- checkpoint更新済み

承認後も他service／dataを変更しない。

---

## 15. Runtime検証

対象service反映後に次を確認する。

1. host/container対象source SHA-256一致
2. health GREEN
3. upstream connector state SUBSCRIBED
4. heartbeat interval分布が仕様範囲
5. heartbeat sequence連続
6. heartbeat transportが同じPushBroker経路
7. WebSocket reconnect storm 0
8. TICKが3秒以上ない観測区間でもheartbeat freshならLIVE維持
9. isolated test clientでheartbeat timeout時にsocket close 0
10. stale後のfresh heartbeat＋fresh TICKで同一socket復帰
11. Heatmap BOOK継続、gap／adaptive stale正常
12. Tape継続、drop／pending／send failure 0
13. Flow Price Responseと3段チャートの表示・計算不変
14. browser長時間soak

production upstreamを故意に停止してはならない。timeout／recoveryはisolated deterministic clientまたはtest harnessで検証し、稼働画面へ障害を注入しない。

---

## 16. 最終GO条件

次が揃うまで完了を宣言してはならない。

- 実物変更file一式
- 開始／終了SHA-256証拠
- 全test実結果
- runtime heartbeat採取結果
- browser state遷移結果
- Heatmap／Tape／Flow Price Response／3段チャート非影響証拠
- 完了報告書
- 第三者による実物diffと内容の独立検証

Codex自己申告だけを承認根拠にしない。

---

## 17. 現在の停止位置

- 第一是正: source／runtimeへ適用済み、未commit
- TICK単独timeout: 未解消
- 恒久対処: 本指示書のみ。source未実装
- Heatmap／Tape分離: 未実装
- runtime: 現在の第一是正版が稼働
- 次のaction: 本指示書の独立レビュー
- 実装開始: 別途ユーザー明示GOが必要
