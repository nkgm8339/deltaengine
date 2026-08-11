# Realtime UI Freshness TIMEOUT不具合
## 現状整理・恒久対処法 独立レビュー資料

- 作成日: 2026-08-03 JST
- 対象repository: `DeltaEngine05M`
- branch: `feature/footprint-dom-tape`
- source基準HEAD: `7552bc3487a3539dca9c7830e92de7cca8884c4f`
- status: **HOLD / NO-GO（第二修正未実施）**
- 目的: Codex単独判断で追加修正せず、現状・原因・影響境界・対処候補・検証gateを第三者が独立レビューできる形で固定する。

---

## 1. 結論

現在のTIMEOUT連発は、browserの鮮度guardが`TICK`をheartbeatとして誤用していることが直接原因である。

`TICK`は約定が発生した場合だけ届くeventであり、transportやupstream connectionのheartbeatではない。ところが現行guardは、最後に受理したTICKから2秒経過しただけで`TICK_TIMEOUT`へ遷移する。そのため、server・Binance connector・browser WebSocketが正常でも、正常な無約定区間またはbrowser event-loop遅延を通信断として誤判定する。

また、現行`index.html`では価格鮮度stateがHeatmap、LIVE DOM、Time & Salesへ結合されている。このため価格の誤TIMEOUTがHeatmapの接続状態やBOOK入力まで停止させ得る。

単純なtimeout延長、BOOK updateによるtimer延命、再接続回数増加は恒久対処にならない。TICK、upstream connection、server-to-browser delivery、Heatmap BOOK freshnessを別stateとして扱う必要がある。

---

## 2. ユーザー観測事象

1. 画面上部に次のbannerが表示された。
   - `MARKET DATA STALE — LIVE DECISION DATA DISABLED · TICK_TIMEOUT`
2. 初回実装ではLIVEがOFFになった後、WebSocket再接続が反復した。
3. 第一是正で自己切断を除去した後も、page reload後に`TICK_TIMEOUT`が連発した。
4. 同時刻のserverはGREENであり、upstream reconnect、pipeline exception、log errorは0だった。

---

## 3. 実測証拠

### 3.1 第一是正前

- browser側guard:
  - `staleAfterMs=2000`
  - `check()`が2秒無TICKで`TICK_TIMEOUT`
  - `_fail()`が`onReconnect()`を実行
  - `index.html`の`onReconnect`が共有WebSocketを`close()`
- runtime log:
  - 30分間にWebSocket `connection open` 58回
- `/api/health`:
  - 5秒timeoutを観測
- `PushBroker`:
  - client集合global lock保持中にtimeoutなしで`send_text()`をawait

### 3.2 第一是正・runtime反映後

- source／container SHA-256一致を確認した対象:
  - `webapp/static/market_freshness.js`
  - `webapp/static/index.html`
  - `webapp/push_broker.py`
- `/api/health`: GREEN
- pipeline exception: 0
- upstream reconnect: 0
- Tape dropped／pending／send failure: 0
- container restart count: 0
- 読み取り専用WebSocket 15.02秒採取:
  - 243 messages
  - 34 TICK
  - 最大TICK間隔 1572.7ms
  - 最大transport age 725.3ms
  - 同一socketで正常終了

### 3.3 TIMEOUT再発時

- `/api/health`: GREEN
- upstream reconnect: 0
- pipeline exception: 0
- 直近1分browser WebSocket open／close: 0／0
- log ERROR／Traceback／Exception: 0
- それにもかかわらずbrowserは`TICK_TIMEOUT`を反復表示

この組合せにより、再発時のTIMEOUTはserver／transport断ではなく、clientのTICK単独timeout誤判定と判断できる。

---

## 4. 現在適用済みの第一是正

以下はsourceと対象containerへ適用済みだが、Git commitは未作成である。

### 4.1 自己切断除去

- `MarketFreshnessGuard`から`onReconnect`実行を除去
- `TICK_TIMEOUT`でWebSocketを閉じない
- WebSocket reconnectは実際の`onclose`／`onerror`時だけ

### 4.2 PushBroker slow-client隔離

- client集合lockとbroadcast直列化lockを分離
- client集合lock中にnetwork sendをawaitしない
- cache handoffとbroadcast sendに0.5秒上限
- slow／dead clientだけを配信集合から除外
- 1 clientの停止で全client配信を無期限停止させない
- reconnect cacheはTICKを先頭に送る

### 4.3 metadata validation

- `source_age_ms=null/empty/boolean`を数値0として受理しない
- 不正metadataはfail closed

### 4.4 第一是正の検証

- 専用test: 7 passed
- 関連test: 76 passed
- WebApp全体: 190 passed / 既知baseline 1 failed
- repository全体: 818 passed / 1 skipped / 既知baseline 1 deselected
- 今回起因failure: 0

### 4.5 第一是正に残った欠陥

自己切断は止まったが、`lastAcceptedAt`がTICK受理時だけ更新され、2秒無TICKで`STALE`へ落ちる設計は残った。このため「再接続storm」は抑止されても、「LIVE OFF／TIMEOUT連発」は解消していない。

---

## 5. 現在の誤結合

### 5.1 TICKとtransport livenessの誤結合

現行guardは次を同一視している。

- 約定が発生しなかった
- browserがTICKを受信できなかった
- server broker配信が停止した
- Binance upstream connectionが切断した

これらは別事象であり、TICK受信間隔だけでは区別できない。

### 5.2 価格鮮度とHeatmapの誤結合

現行`index.html`には次の結合がある。

- `renderMarketFreshness()`が`HEATMAP_UI.setConnected(fresh, ...)`を呼ぶ
- `S.marketFresh=false`の場合、`onBookUpdate()`が入口でreturnする
- stale遷移時に`S.liveBook`を`NO_CONNECTION`へ置換する

したがって、価格TICKの誤TIMEOUTが正常なBOOK streamとHeatmapへ波及する。

### 5.3 価格鮮度とTime & Salesの誤結合

`renderMarketFreshness()`が`TAPE_UI.setConnected(fresh)`を呼ぶ。無約定はTapeの接続断ではないため、TICK timeoutをTape transport stateへ流用してはならない。

---

## 6. 分離すべき4つのstate

| state | 正本 | 用途 | 他stateの代用可否 |
|---|---|---|---|
| Browser transport | browser WebSocket `open/close/error` | serverとの接続状態 | TICKで代用不可 |
| Binance upstream | `ExchangeConnector.state`、最終raw frame受信時刻 | Binance接続とsource受信の生存性 | BOOK/TICK単独で代用不可 |
| Decision price | fresh TICKのprice／metadata | USD-M現在価格と判断可否 | Heatmap接続へ流用不可 |
| Heatmap BOOK | `BOOK_UPDATE.sync_state`、book sequence、Heatmap既存adaptive stale | Heatmap描画・gap・stale | 価格TICKへ流用不可 |

---

## 7. 採用してはならない対処

### 7.1 2秒を5秒／10秒へ延長

判定根拠がTICKのままであり、閾値を超えれば同じ誤判定が再発する。原因を時間的に先送りするだけなので不採用。

### 7.2 BOOK updateでTICK timerを延命

価格鮮度とBOOK／Heatmapを再結合する。BOOK停止、BOOK fail-closed、Heatmap仕様変更が価格LIVEへ波及するため不採用。

### 7.3 TICK timeoutでWebSocket再接続

第一不具合の自己切断stormを再導入するため禁止。

### 7.4 CANDLE／BAR_UPDATEで価格をLIVE復帰

約定eventとbar close／in-progress barの意味を混在させるため禁止。

### 7.5 server healthがGREENなら無条件LIVE

health sampling間隔と評価目的が異なり、browser delivery停止を即時検出できないため不採用。

---

## 8. 恒久対処候補（独立レビュー対象）

### 8.1 ExchangeConnector観測値のadditive追加

既存`ExchangeConnector`は次を保持している。

- `state`
- `reconnect_count`
- `messages_out`
- `errors`

raw frame受信ごとに次のread-only観測値をadditiveに更新する候補とする。

- `last_message_received_at`（UTC wall clock）
- 必要なら`last_message_received_monotonic`

分析、正規化、queue順序、BOOK処理は変更しない。

### 8.2 専用`MARKET_HEARTBEAT`

serverは既存PushBroker経路から、例として1秒間隔で専用heartbeatを送る。

候補payload:

```json
{
  "heartbeat_sequence": 123,
  "published_time": "2026-08-03T00:00:00.000000+00:00",
  "upstream_state": "SUBSCRIBED",
  "upstream_last_message_time": "2026-08-02T23:59:59.950000+00:00",
  "upstream_age_ms": 50,
  "pipeline_alive": true
}
```

要件:

- browserまでの実配信と同じPushBroker経路を通す
- reconnect cacheへ混在させるかは独立判断する
- heartbeat欠落時もWebSocketをclient側から強制closeしない
- heartbeat interval／timeoutは設定値または仕様確定値とし、場当たりなmagic numberにしない
- replay modeでlive heartbeatを混入させない、または明示的にreplay stateを送る

### 8.3 Browser freshness state

候補state遷移:

```text
WebSocket open
  -> SYNCING
fresh MARKET_HEARTBEAT + fresh TICK
  -> LIVE
heartbeat missing / upstream not SUBSCRIBED / pipeline dead
  -> STALE（socketは維持）
fresh heartbeat復帰
  -> SYNCING（古い価格を即再表示しない）
fresh TICK受理
  -> LIVE
actual WebSocket close/error
  -> RECONNECTING
```

重要事項:

- TICK absenceだけではSTALEにしない
- individual TICKの`published_time`／`source_age_ms` validationは維持
- stale中は価格判断をfail closedにする
- staleからの価格復帰にはfresh TICKを要求する

### 8.4 Heatmap／Tapeのtransport分離

- `HEATMAP_UI.setConnected()`はbrowser WebSocketの実`open/close`だけで操作する
- `TAPE_UI.setConnected()`もbrowser WebSocketの実`open/close`だけで操作する
- `renderMarketFreshness()`からHeatmap／Tapeのconnected操作を除去する
- `BOOK_UPDATE`は価格freshnessに関係なくHeatmapへ渡す
- Heatmapは既存の`BOOK_UPDATE.sync_state`、sequence、adaptive staleを正本として維持する
- LIVE DOMなど価格判断を必要とするconsumerだけをdecision freshness gateの後段に置く

Heatmap renderer、BookStore、履歴、色、操作、adaptive stale計算そのものは変更禁止とする。

---

## 9. 影響境界

| component | 許可候補 | 禁止 |
|---|---|---|
| `src/acquisition/connector.py` | read-only liveness観測値の追加 | 接続・再接続・queue処理変更 |
| `webapp/push_broker.py` | heartbeat payload配信 | TICK／BOOK／Tape payload意味変更 |
| `webapp/main.py` | heartbeat lifecycle wiring | pipeline／analysis callback変更 |
| `market_freshness.js` | heartbeat基準state machine | TICK回数基準timeout |
| `index.html` | consumer routing分離 | chart計算・layout・表示意味変更 |
| Heatmap source | **変更なし** | renderer／BookStore／adaptive stale変更 |
| Flow Price Response | **変更なし** | 計算・表示・意味変更 |
| 3段チャート | **変更なし** | 計算・表示・意味変更 |
| Hook／Strategy | **変更なし** | threshold／state／判断変更 |
| Spot reference | 原則変更なし | USD-M判断経路への混入 |

---

## 10. 必須検証gate

独立レビューで設計承認後も、以下を全件PASSするまでruntime反映不可とする。

### 10.1 State machine

1. 10秒以上TICKがなくてもheartbeatがfreshならLIVEを維持する
2. heartbeatがtimeoutしたらSTALEになるが`ws.close()`を呼ばない
3. upstream stateが`SUBSCRIBED`以外ならSTALE
4. pipeline deadならSTALE
5. stale後、fresh heartbeatだけでは価格を再表示しない
6. fresh heartbeat後のfresh TICKで同一socket上のLIVEへ復帰
7. 古い／不正TICK metadataは引き続きreject

### 10.2 Heatmap非影響

1. price stateがSTALEでも`BOOK_UPDATE`はHeatmapへ渡る
2. price state変更で`HEATMAP_UI.setConnected()`を呼ばない
3. WebSocket close時だけHeatmap connected=false
4. Heatmapの既存adaptive stale、gap、sequence testが差分ゼロでPASS
5. Heatmap renderer source hashが変更前後で一致

### 10.3 Tape／DOM

1. 無約定区間だけでTapeをRECONNECTINGにしない
2. actual WebSocket close時はTapeをRECONNECTINGにする
3. price decision stale中のDOM判断表示はfail closed
4. Tape store、gap、accepted trade順序を変更しない

### 10.4 Server delivery

1. slow clientがheartbeat／TICK／BOOKを他clientへ波及停止させない
2. heartbeat task停止時に他taskをcancelしない
3. service shutdownでheartbeat taskを確実にcancel／awaitする
4. replay／testでlive stateを混入させない

### 10.5 全体

- 専用test
- acquisition connector既存test
- PushBroker／WebSocket lifecycle test
- Heatmap／DOM／Tape／Spot関連test
- WebApp全体
- repository全体
- 実browser長時間soak
- health、WebSocket open/close回数、TICK／heartbeat ageの実測

---

## 11. Rollback選択肢

### 11.1 第一是正を維持して恒久対処を待つ

- 長所: 自己切断stormとPushBroker無期限send待ちは抑止される
- 短所: TICK単独timeoutによるLIVE OFFは残る

### 11.2 鮮度機能全体を変更前へ限定rollback

- 変更前tracked snapshot:
  - `cebcf854e7a900cd260d300fc8ed651afd79bdaa`
- 注意:
  - snapshot後にBinance Spot表示と別件修正が追加されている
  - repositoryは多数の別件dirty／untracked fileを含む
  - `git reset`／checkoutで一括復元してはならない
  - 対象hunkだけを逆適用し、Spot・POC・DOM/Tape・debug overlay除去を保持する必要がある
- 長所: TIMEOUT連発は鮮度機能導入前へ戻る
- 短所: 古い価格をLIVE表示し続けた元不具合が再発する

### 11.3 TICK absence判定だけを暫定無効化

- 長所: TIMEOUT連発を止め、metadata不正・actual disconnect fail-closedは維持可能
- 短所: server-to-browser silent stallを検出する正本heartbeatが完成するまで検知空白が生じる
- 扱い: 緊急暫定策。採否は独立レビューとユーザー明示GOが必要。

---

## 12. 独立レビューで確定すべき事項

1. 恒久対処として専用`MARKET_HEARTBEAT`を採用するか
2. heartbeat interval／timeoutの仕様値と根拠
3. upstream fresh判定に使う観測値
4. replay modeのheartbeat契約
5. stale復帰時にfresh TICKを必須とするか
6. Heatmap／Tape connected stateをWebSocket transportへ完全分離するか
7. 第一是正のPushBroker bounded sendを維持するか
8. 恒久対処までの間、現状維持・限定rollback・TICK absence暫定無効化のどれを選ぶか

---

## 13. 変更許可gate

本資料作成時点では第二source修正を**NO-GO**とする。

次の条件が揃うまでCodexはsource／runtimeを変更しない。

1. 本資料を第三者が独立レビュー
2. 採用案、変更file、禁止範囲、heartbeat仕様、検証gateを確定
3. ユーザーが確定案へ明示GO

Codexの自己申告、unit test PASS、runtime GREENだけを承認根拠にしてはならない。実物diff、対象source hash、全test結果、実browser挙動を独立照合する。

---

## 14. 現在の停止位置

- 第一是正: source／containerへ適用済み、未commit
- TIMEOUT連発: 未解消
- BOOKでtimer延命する案: source未適用、採用禁止
- 専用heartbeat案: 設計候補のみ、source未適用
- Heatmap／Flow Price Response／3段チャート: 第二修正では未変更
- 次のaction: 本資料の独立レビューとユーザー判断
