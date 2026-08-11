# DeltaEngine リアルタイム表示鮮度修正 checkpoint

## 2026-08-02 13:34:55 +09:00 — 変更前

- 承認範囲: Binance USD-M のリアルタイム表示が古値を現在値として残す不具合を修正し、回帰試験と実配信照合を行う。既存の Flow Price Response と3段チャートの意味・構造は変更しない。
- 完了済み:
  - `ArchitectureRepository/00_Master/PROJECT_MEMORY.md` 全文確認済み。
  - 現行表示とBinance公式履歴を照合し、12:41:53の画面が12:35:05の価格を保持していた事実を確認。
  - 修正前tracked worktreeを、worktree/indexを変えないGit snapshot `cebcf854e7a900cd260d300fc8ed651afd79bdaa` (`stash@{0}`) に保存。
  - snapshot作成前後でworktreeが不変であることを確認。
- 未完了:
  - 既存UI差分とテスト構造の精査。
  - 最新TICK再同期、STALEフェイルクローズ、鮮度監視の実装。
  - 切断・再接続・古TICK・正常復帰・既存UI回帰試験。
  - 実Binance対Delta配信の最終照合。
- 変更file:
  - 本checkpointのみ。
- 予定対象file:
  - `Delta_Engine_Pro4web/webapp/push_broker.py`
  - `Delta_Engine_Pro4web/webapp/static/index.html`
  - 専用のwebapp test file（既存dirty testへの不要な混入を避ける）
- 検証結果:
  - Git snapshot作成成功。
  - `WORKTREE_UNCHANGED=YES`。
- blocker: なし。
- 次の再開位置: 現在の`index.html`差分を保持したまま、接続状態・価格描画・テストfixtureを読み取り、最小パッチを設計する。

## 2026-08-02 13:42:51 +09:00 — 設計確定

- 承認範囲: 変更なし。
- 完了済み:
  - `index.html`の既存未コミット差分はDOM→Time & Sales診断部分だけで、鮮度修正対象行と非重複であることを確認。
  - 表示停止を許した4条件を確定: client-side tick watchdogなし、disconnect時の価格無効化なし、reconnect時のlatest TICK cacheなし、server healthがbrowser deliveryを監視しない。
  - 修正設計を以下に限定。
    1. TICKへ`published_time`と`source_age_ms`をadditiveに付与し、latest TICKをreconnect cacheする。
    2. 独立したclient freshness guardで古いcached/backlogged TICKと無通信をfail closedにする。
    3. STALE/SYNCING/RECONNECTING中は価格を無効化し、live UI全体へ判断禁止bannerを表示する。
    4. fresh TICK受理後だけ自動復帰する。
  - Flow Price Response、3段チャートの計算、Hook、Strategy thresholdは変更対象外とした。
- 未完了:
  - 実装、専用試験、全webapp回帰、実配信照合。
- 変更file:
  - 本checkpointのみ。
- 検証結果:
  - 既存diffと対象行の非重複を確認。
  - payload v1はadditive fieldを許容する仕様であることを確認。
- blocker: なし。
- 次の再開位置: `market_freshness.js`、PushBroker latest TICK cache、`index.html` fail-closed projection、専用testsを実装する。

## 2026-08-02 14:06:52 +09:00 — 限定実装完了

- 承認範囲: 変更なし。実行環境への反映はまだ行っていない。
- 完了済み:
  - TICK payloadへ`published_time`と`source_age_ms`をadditiveに追加。
  - PushBrokerにlatest TICK 1件のreconnect cacheを追加し、cache送信とclient登録をbroadcastに対して順序保証。
  - 独立JS `MarketFreshnessGuard`を追加。古い／metadata不正TICK、2秒間のTICK無更新、接続後5秒のfresh TICK欠落をfail closed化。
  - STALE／SYNCING／RECONNECTING時は現在価格を消去し、live DOM・Tape・Heatmapの入力を止め、判断禁止bannerを表示。fresh TICKだけを復帰条件とした。
  - CANDLE／BAR_UPDATEから現在価格を補完する経路をfresh時だけに限定。
  - WebSocket仕様のTICK節へ鮮度fieldとfail-closed契約を追記。
  - Flow Price Response、3段チャート計算、Hook、Strategy thresholdは未変更。
- 変更file:
  - `Delta_Engine_Pro4web/webapp/push_broker.py`
  - `Delta_Engine_Pro4web/webapp/static/index.html`（既存DOM→Time & Sales診断差分を保持）
  - `Delta_Engine_Pro4web/webapp/static/market_freshness.js`（新規）
  - `Delta_Engine_Pro4web/tests/webapp/test_market_freshness_ui.py`（新規）
  - `ArchitectureRepository/30_Modules/WebApp/Specifications/WebSocketPayload_Spec_v1.md`（既存v1.5差分を保持し、TICK節だけ追記）
  - 本checkpoint。
- 検証結果:
  - 専用test: 5 passed。
  - 専用＋既存吸収表示test: 8 passed。
  - 関連既存test初回: 80 passed / 1 static contract failed。鮮度gateを関数入口へ移し既存contractを保持して解消済み。
  - `market_freshness.js`と`index.html` inline scriptのNode構文検査成功。
  - `push_broker.py`のPython compile成功。
  - 対象fileの`git diff --check`成功。
- 未完了:
  - 関連test一式の再実行。
  - `tests/webapp`全回帰。
  - 実行環境への反映とBinance公式価格との実配信照合。
- blocker: なし。
- 次の再開位置: 関連test一式を再実行後、`tests/webapp`全体を実行する。全通過時だけcontainerを再build/restartして実配信を照合する。

## 2026-08-02 14:15:17 +09:00 — WebApp回帰完了

- 承認範囲: 変更なし。実行環境への反映はまだ行っていない。
- 完了済み:
  - 鮮度・WebSocket・DOM・Tape・Heatmap・Footprint関連test一式を再実行。
  - `tests/webapp`全177件を実行。
- 検証結果:
  - 関連test: 86 passed。
  - WebApp全体: 176 passed / 1 failed。
  - 唯一のfailureは`test_dom_tape_fusion_ui.py::test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation`が`body.phase5-fusion #right>#left`を要求する既存static contract不一致。
  - 現行・HEAD・修正前snapshot `cebcf854...`はいずれも`body.phase5-fusion #main>#left`であり、要求文字列は修正前から存在しない。今回差分由来ではないことを確認。
  - 当該レイアウトとtestは今回の承認範囲外のため変更せず、既知baseline failureとして分離。
- 変更file: 前checkpointから変更なし（本checkpoint追記のみ）。
- 未完了:
  - WebApp以外を含む全体回帰。
  - 実行環境への反映とBinance公式価格との実配信照合。
- blocker: 既知baseline failure 1件は価格鮮度修正をblockしない。実配信照合には影響しない。
- 次の再開位置: 既知baseline 1件を除外した全体回帰を実行し、価格鮮度関連の新規failureがないことを確認する。

## 2026-08-02 14:20:00 +09:00 — 実行環境反映前

- 承認範囲: userの`GO`に基づき、test合格後に対象WebApp containerだけを再build/restartし実配信照合する。
- 完了済み:
  - 既知baseline 1件だけを除外したリポジトリ全体回帰を実行。
  - `804 passed, 1 skipped, 1 deselected`、exit code 0を確認。
  - 現在の稼働対象は`delta_engine_pro4web-deltaengine_clone-1`、公開portは`18080 -> 8080`であることを確認。
- 変更file: 前checkpointから変更なし（本checkpoint追記のみ）。
- 検証結果:
  - 新規／今回起因failureなし。
  - 実行環境は現時点で`Up 10 hours`、まだ再起動していない。
- 未完了:
  - compose定義と対象serviceの特定。
  - 対象containerの再build/restart。
  - browser配信TICK metadata、STALE防止、Binance公式価格との同時照合。
  - 最終diff、Git状態、復旧手順の確定。
- blocker: なし。
- 次の再開位置: compose fileとserviceを特定し、対象serviceだけをbuild/recreateする。起動health確認後にWebSocket TICKをBinance USD-M公式streamと同時採取する。

## 2026-08-02 14:26:43 +09:00 — 実配信検証完了

- 承認範囲: 完了。対象`deltaengine_clone`以外のservice／dataは変更していない。
- 完了済み:
  - `docker compose up -d --build deltaengine_clone`で対象serviceだけを再build/recreate。
  - 静的鮮度guardのHTTP配信、server起動、health、WebSocket TICK metadataを確認。
  - Delta WebSocketとBinance USD-M公式`btcusdt@trade`を8秒同時採取し、trade ID単位で照合。
  - 新規WebSocket接続時のlatest TICK即時同期を確認。
- 実配信検証結果:
  - 同時採取: Delta TICK 24件、Binance trade 34件、同一trade ID 23件。
  - 同一trade IDの価格不一致: 0件。
  - Delta transport age: min 1.6ms / avg 3.2ms / max 9.8ms。
  - `source_age_ms`: min 0 / avg 0 / max 0（host/exchange wall-clock差は非負clamp契約）。
  - reconnect時first TICK: 接続開始から71.6ms、`published_time` age 25.7ms。
  - 最終health: GREEN、pipeline exception 0、event lag 0ms、Tape dropped/pending/send failure 0、anomalies 0。
  - container: `delta_engine_pro4web-deltaengine_clone-1` running。
- 最終変更file:
  - `Delta_Engine_Pro4web/webapp/push_broker.py`
  - `Delta_Engine_Pro4web/webapp/static/index.html`（修正前からの既存差分も保持）
  - `Delta_Engine_Pro4web/webapp/static/market_freshness.js`（新規）
  - `Delta_Engine_Pro4web/tests/webapp/test_market_freshness_ui.py`（新規）
  - `ArchitectureRepository/30_Modules/WebApp/Specifications/WebSocketPayload_Spec_v1.md`（修正前からの既存差分も保持）
  - 本checkpoint。
- Git状態:
  - stagingは空。commitは作成していない。
  - 修正前tracked snapshotは`cebcf854e7a900cd260d300fc8ed651afd79bdaa`（`stash@{0}`）。
  - rollback時は`git reset`／checkoutを使わず、snapshot対比の今回対象hunkだけを逆適用し、新規2実装/test fileを除去後、対象serviceだけを再buildする。
- blocker:
  - 今回起因blockerなし。
  - 修正前からの既知baseline: DOM/Tape layout static contract 1件。価格鮮度とは非関連で未変更。
- 次の再開位置: なし。価格鮮度修正は実装・全体回帰・実配信照合まで完了。

## 2026-08-03 07:45:38 +09:00 — LIVE自己切断バグ是正開始

- 承認範囲: ユーザー明示指示「しゅうせいしろ。ほかにえいきょうあたえるなよ」に基づき、リアルタイム鮮度監視が`TICK_TIMEOUT`時に共有WebSocketを自ら切断する不具合と、PushBrokerの無期限送信待ちを限定是正する。
- 変更禁止範囲:
  - Order Book Heatmapの描画・履歴・操作・意味
  - Flow Price Response、3段チャート、Footprint、LIVE DOM、Time & Salesの計算・表示仕様
  - Hook、Strategy、取引判断ロジック
  - Binance Spot参照値の分析経路への接続
- 完了済み:
  - `TICK_TIMEOUT`から`MarketFreshnessGuard._fail()`、`onReconnect`、`ws.close()`へ至る自己切断経路をsourceで確認。
  - 直近30分のruntime logでWebSocket `connection open` 58回を確認。
  - `/api/health`が5秒timeoutする状態を確認。
  - `PushBroker.register()`と`_broadcast()`がglobal lock保持中にtimeoutなしで`send_text()`をawaitする配信停止リスクを確認。
  - 現行専用testが実WebSocketの切断・再接続・backoff loopとslow client隔離を検証していないことを確認。
- 変更予定file:
  - `Delta_Engine_Pro4web/webapp/static/market_freshness.js`
  - `Delta_Engine_Pro4web/webapp/static/index.html`
  - `Delta_Engine_Pro4web/webapp/push_broker.py`
  - `Delta_Engine_Pro4web/tests/webapp/test_market_freshness_ui.py`
  - 必要な既存WebSocket仕様の鮮度節
  - 本checkpoint
- 未完了:
  - TICK鮮度判定とtransport再接続の分離。
  - slow/dead clientを他clientから隔離するbounded send。
  - 専用・関連回帰、runtime反映、同一WebSocket上での`STALE -> LIVE`復帰確認。
- blocker: なし。repositoryの多数の別件dirty/untracked fileには触れない。
- 次の再開位置: 鮮度guardからtransport操作を除去し、専用回帰testを先に更新する。

## 2026-08-03 07:50:32 +09:00 — 限定実装・関連回帰完了

- 承認範囲・変更禁止範囲: 07:45:38記録から変更なし。
- 完了済み:
  - `MarketFreshnessGuard`から`onReconnect`とtransport操作状態を除去。`TICK_TIMEOUT`は同一socketを維持した`STALE`化だけに限定。
  - fresh TICK受理による同一socket上の`STALE -> LIVE`復帰を専用test化。
  - `source_age_ms=null/empty/boolean`を0へ誤変換せずmetadata不正としてfail closed化。
  - `PushBroker`のclient集合lockとbroadcast直列化lockを分離。
  - network sendをclient集合lock外へ移動し、cache handoff／broadcastを0.5秒の総時間上限でbounded化。
  - slow/dead clientだけを除外し、healthy client配信を継続するtestを追加。
  - reconnect cache順序をfreshness確立に必要なTICK先頭へ変更。
  - WebSocket payload仕様の鮮度判定／transport分離契約を更新。
- 変更file:
  - `Delta_Engine_Pro4web/webapp/static/market_freshness.js`
  - `Delta_Engine_Pro4web/webapp/static/index.html`
  - `Delta_Engine_Pro4web/webapp/push_broker.py`
  - `Delta_Engine_Pro4web/tests/webapp/test_market_freshness_ui.py`
  - `ArchitectureRepository/30_Modules/WebApp/Specifications/WebSocketPayload_Spec_v1.md`
  - 本checkpoint
- 検証結果:
  - 専用test: **7 passed**。
  - 鮮度／Spot／PushBroker／BOOK／Tape／吸収表示関連: **76 passed**。
  - `market_freshness.js` Node構文: PASS。
  - 対象diff check: PASS（既存LF→CRLF warningのみ）。
- 未完了:
  - WebApp全体回帰。
  - runtime build/recreateと実browserでの同一socket復帰確認。
- blocker: なし。
- 次の再開位置: `tests/webapp`全体を実行し、既知baseline以外の新規failureがないことを確認する。

## 2026-08-03 07:51:30 +09:00 — WebApp全回帰完了

- 承認範囲・変更file: 07:50:32記録から変更なし。
- 検証結果:
  - WebApp全体: **190 passed / 1 failed**。
  - 唯一のfailureは既知baseline
    `test_dom_tape_fusion_ui.py::test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation`。
  - failure内容は旧selector `body.phase5-fusion #right>#left`要求と現行`#main>#left`の不一致で、今回対象hunkと非重複。今回起因failureは0。
- 未完了:
  - 既知baseline 1件を除外したrepository全体回帰。
  - runtime build/recreateと実配信確認。
- blockerの限定範囲: 既知baseline 1件は③の修正をblockしない。対象外のため変更しない。
- 次の再開位置: repository全体回帰を長時間実行する。終了後に対象diffとruntime反映前状態を再確認する。

## 2026-08-03 07:56:00 +09:00 — Repository全回帰完了

- 承認範囲・変更file: 07:50:32記録から変更なし。
- 検証結果:
  - 既知baseline 1件だけを除外したrepository全体: **818 passed / 1 skipped / 1 deselected**、exit code 0。
  - 新規／今回起因failure: 0。
  - Heatmap、Flow Price Response、3段チャート、Footprint、DOM、Tape、Spotを含む既存testへの影響なし。
- 未完了:
  - 対象diff最終監査とruntime反映前source確認。
  - 対象serviceだけのbuild/recreate。
  - 実browserでWebSocket identity、`STALE -> LIVE`同一socket復帰、再接続storm消滅、healthを確認。
- blocker: なし。
- 次の再開位置: 変更対象fileと禁止範囲をdiff監査し、合格時だけ`deltaengine_clone`へ反映する。

## 2026-08-03 07:57:23 +09:00 — Runtime反映直前

- 承認範囲: 対象`deltaengine_clone`だけのbuild/recreateと実配信検証。ほかのservice／dataは変更しない。
- 完了済み:
  - 対象diff check: PASS（既存LF→CRLF warningのみ）。
  - `index.html`全inline JavaScript Node構文: PASS。
  - 旧`onReconnect`／`reconnectRequested`自己切断signatureがsourceから消えていることを確認。
  - 残存`ws.close()`は実transport `onerror` handlerだけであることを確認。
  - 禁止範囲の`orderbook_heatmap.js`と`src`はclean。`footprint_canvas.js`のmodified状態は本件開始前からのPOC復旧差分であり、本件では未編集。
- 未完了:
  - 対象service build/recreate。
  - health、WebSocket接続回数、host/container source一致、実browser復帰確認。
- blocker: なし。
- 次の再開位置: `docker compose up -d --build deltaengine_clone`を実行し、起動完了後にsource hashとhealthを確認する。

## 2026-08-03 08:00:03 +09:00 — Runtime反映・起動検証完了

- 承認範囲: 07:57:23記録から変更なし。
- 完了済み:
  - `docker compose up -d --build deltaengine_clone`成功。対象containerだけをrecreate。
  - container running、restart count 0。
  - host/containerの`market_freshness.js`、`index.html`、`push_broker.py` SHA-256一致。
- 検証結果:
  - `/api/health`: **GREEN**。
  - `ws_reconnect=0`、pipeline exception 0、event lag 0ms。
  - Tape dropped=0、pending=0、send failures=0、balanced=True。
  - sequence gap 0、anomalies 0。
  - 起動logにERROR／Traceback／Exceptionなし。
- 未完了:
  - 実WebSocket短時間採取によるTICK間隔・metadata・接続維持確認。
  - 再接続stormが再発しないことのsoak確認。
  - 最終checkpoint・Git差分確認。
- blocker: なし。
- 次の再開位置: 読み取り用WebSocket client 1接続でTICKを採取し、その後のlog／healthを確認する。

## 2026-08-03 08:04:26 +09:00 — 実配信確認・browser reload待ち

- 承認範囲: 変更なし。ユーザー画面のreload／切替は未実施。
- 完了済み:
  - 読み取り専用WebSocket client 1接続で15.02秒採取。
  - 243 messages、34 TICKを同一socketで受信し正常終了。
  - trade ID `7947840145 -> 7947840258`、最大TICK間隔1572.7ms、最大transport age 725.3ms。
  - 単発`/api/health`: GREEN、reconnect 0、pipeline exception 0、Tape send failure 0。
  - container running、restart count 0、直近log ERROR 0。
- 監視補足:
  - 60秒monitor用PowerShellが結果回収で予定時間を超えたため、monitor processだけを停止。serviceは停止／変更していない。
  - 直後の単発healthは2秒で正常応答。
  - 直近2分logは`connection open=5`、`connection closed=0`。対象service再起動前から開いているbrowser tabは旧inline JavaScriptをメモリ保持し、WebSocket reconnectだけでは新`index.html`を再読込しない。
- 未完了:
  - ユーザー操作による既存dashboard pageの1回reload。
  - reload後、同一browser tabで`TICK_TIMEOUT`がsocket closeを発生させず、fresh TICKでLIVE復帰することの最終観察。
- blockerの限定範囲:
  - source、test、container反映、server実配信は完了。
  - 現在開いているユーザー画面への新client code適用だけがreload待ち。画面を勝手に切り替えない指示に従い自動操作しない。
- 次の再開位置: ユーザーがdashboardを1回reload後、画面を操作せずlogとhealthだけを確認する。

## 2026-08-03 08:14:19 +09:00 — TICK単独timeout誤判定の再是正

- 発生事実: ユーザー実画面でreload後もTIMEOUTが連発。
- runtime確認:
  - `/api/health` GREEN。
  - upstream reconnect 0、pipeline exception 0、直近1分browser WebSocket open/close 0、log error 0。
- 原因確定:
  - transport／serverは正常だが、client guardが「受理TICKが2秒ない」だけで`TICK_TIMEOUT`へ落としていた。
  - 約定が発生しない正常区間またはbrowser event-loop遅延を配信断と誤判定する設計であり、前回是正は自己切断除去だけで不十分だった。
- 承認範囲: 鮮度guardとBOOK market-activity wiring、専用test、仕様、本checkpointだけを限定修正。ほかの表示・計算・分析は禁止。
- 設計訂正:
  - fresh SYNCED BOOKを価格鮮度guardへ入力する案は、価格鮮度とHeatmap／BOOKの意味を再結合する場当たり対応になるため採用しない。
  - TICK、upstream connector、server-to-browser delivery、Heatmap BOOK freshnessを独立stateとして扱う必要がある。
- 未完了:
  - 独立レビュー用の現状整理・対処法文書作成。
  - レビュー承認前の第二source修正は実施しない。
- blocker: 技術blockerではなく設計承認gate。ユーザー指示によりCodex単独判断での実装続行を禁止。
- 次の再開位置: `REALTIME_UI_FRESHNESS_TIMEOUT_CURRENT_STATE_AND_REMEDIATION_REVIEW_20260803.md`を独立レビューへ渡し、承認された境界だけを実装する。

## 2026-08-03 — 独立レビュー資料作成

- ユーザー明示指示: 「現状の整理と対処法を文章にしてファイルしろ。お前だけの判断はだめ」。
- source／runtime変更: なし。
- 作成file: `ArchitectureRepository/00_Master/REALTIME_UI_FRESHNESS_TIMEOUT_CURRENT_STATE_AND_REMEDIATION_REVIEW_20260803.md`。
- 現在status: 第二修正 **HOLD / NO-GO**。独立レビューとユーザーGO待ち。

## 2026-08-03 — 恒久対処実装指示書作成GO

- ユーザー明示GO: 独立レビュー推奨を固定した恒久対処実装指示書の作成。
- 作成file: `ArchitectureRepository/00_Master/REALTIME_UI_FRESHNESS_HEARTBEAT_PERMANENT_FIX_IMPLEMENTATION_INSTRUCTION_V1_20260803.md`。
- 実施範囲: 指示書作成と本checkpoint更新のみ。
- source／runtime／test変更、container再起動、Git stage／commit: **未実施・未承認**。
- 次のgate: 指示書実物の独立レビューと、恒久対処実装への別途明示GO。

## 2026-08-03 — Claude独立レビューpackage作成

- ユーザー明示指示: レビュー一式をファイル化する。
- package: `ArchitectureRepository/00_Master/REALTIME_UI_FRESHNESS_CLAUDE_REVIEW_PACKAGE_20260803.zip`。
- 収録範囲: 正本文書、実装指示書、checkpoint、現物対象source、protected source、関連test、package manifest。
- source／runtime／container／Git stage／commit: 変更しない。
- gate: Claude独立レビュー結果待ち。恒久対処source実装はNO-GOを維持。

## 2026-08-03 — エラー証拠追加package V2作成

- Claude追加要求: エラー全文、発生場所、traceback、失敗test名、関係source現物。
- 追加document: `REALTIME_UI_FRESHNESS_ERROR_EVIDENCE_20260803.md`。
- 追加evidence: ユーザー提供の`OFFバグ`実スクリーンショット。
- package: `REALTIME_UI_FRESHNESS_CLAUDE_REVIEW_PACKAGE_V2_20260803.zip`。
- source／runtime／container変更: なし。

## 2026-08-03 12:33:27 +09:00 — 恒久対処V1.1 source実装開始前

- ユーザー明示GO: 独立確認済みの恒久対処実装指示書V1.1に従うsource実装。
- 承認範囲: 指示書§3の許可file、既存checkpoint、実装完了時の報告書1点だけ。runtime反映は別GO。
- 必読確認: `PROJECT_MEMORY.md`、V1.1指示書、現状整理正本、本checkpoint、`WebSocketPayload_Spec_v1.md`。
- branch: `feature/footprint-dom-tape`
- HEAD: `7552bc3487a3539dca9c7830e92de7cca8884c4f`
- source precondition: 指示書§2.2の7 file SHA-256が全件一致。実装開始可。
- protected precondition: 指示書§4の3 file SHA-256が全件一致。
- 改行baseline補足:
  - V1.1 §2.4の「main.py以外はLF」という説明と現物には差がある。
  - 指定SHAと一致する現物実測では`config.py`、`config.yaml`、`push_broker.py`、`index.html`にも既存CRLFがある。
  - hash preconditionは一致しているため、現物の下記CRLF／LF比率を開始正本とし、各編集hunk周辺の既存改行を保持する。全file正規化は禁止。
- 許可production／config file開始値:

| file | SHA-256 | bytes | CRLF | LF-only | total newline |
|---|---|---:|---:|---:|---:|
| `src/acquisition/connector.py` | `458c902f622de0791f1c25fd3c23e87c36062dcf1a893bfaf2a6ea0fe068b78f` | 7,013 | 0 | 181 | 181 |
| `src/config.py` | `1e8207e7853170be0d848e77a076973a42ef98246287bced0f3af0f532f3f7f5` | 18,057 | 2 | 484 | 486 |
| `config/config.yaml` | `7f1203055bd85add19fc8cb8eb9e50842e6ca0d76c7723c6a328115f2691823b` | 3,617 | 120 | 38 | 158 |
| `webapp/main.py` | `57f40d3efdadff6ec21509e10f976fa733a1603284adb14e0f98639a270b1d9a` | 42,539 | 954 | 96 | 1,050 |
| `webapp/push_broker.py` | `d072c256cb722f61a699eb0dec1993ce0d50543d9e39d58c6dc567451729262c` | 28,434 | 3 | 658 | 661 |
| `webapp/static/market_freshness.js` | `254ab8d289b8c056f603e5f3c52166cb95df1118e99251548a49ed053df5f93d` | 4,298 | 0 | 122 | 122 |
| `webapp/static/index.html` | `d61471dce0058a156647775370709561d085da0c4fb20f56b477d963adc4b79c` | 193,445 | 2,486 | 189 | 2,675 |

- protected file開始値:

| file | SHA-256 | review hash一致 |
|---|---|---|
| `webapp/static/orderbook_heatmap.js` | `2da8849d8e77ce82066f02e95c996dde75a952f2a900fc02018e4ea74467388b` | YES |
| `webapp/static/time_sales.js` | `f59fec3f3478cc5a9b977c74978c3d8eb7c66e27a479a0b40fcf6d5f18f8d4c2` | YES |
| `webapp/static/footprint_canvas.js` | `987c5da72a7375495eb44bd9910a1b79b076226b2f0206cc8e3d3de2f08c01be` | YES |

- `src/orderflow/hooks/**`／`src/strategy_engine/**`開始時全file SHA-256（62 files、`.pyc`を含む現物全file。test時はbytecode書込を抑止する）:

```text
src/orderflow/hooks/__init__.py c527712c3ea62d51138bc00d837f3793d387d747828dc98fc437ed682d0e4c78
src/orderflow/hooks/__pycache__/__init__.cpython-313.pyc eaf7910cb841f8eca4799ecd7daec6745e1bb0e55988e44438211dc2163f6c19
src/orderflow/hooks/__pycache__/adapters.cpython-313.pyc 203a2a402c2016e480945e990fee63f811acb242503a0f56981bbabb0072a3a7
src/orderflow/hooks/__pycache__/config.cpython-313.pyc be3dac560574d238be3fd3f82eba89b40a232bee242095f7811224fc64903799
src/orderflow/hooks/__pycache__/detector_utils.cpython-313.pyc 3912dce33e7b8a3003ec96040a05c0170202a4d8e0d19dba6b3c62e71f5bdeb9
src/orderflow/hooks/__pycache__/dom_features.cpython-313.pyc 4e6e849b3e8957f9410ae1d01891558e977963e49d61638a9bb3b7a0ffe6d5bf
src/orderflow/hooks/__pycache__/dom_iceberg.cpython-313.pyc 86d3ed255118f380a3a1ab9cecff8ba0623105b25c995f22ca04f26325a8da65
src/orderflow/hooks/__pycache__/dom_liquidity.cpython-313.pyc 226e7c4a7a5371b3dbef742536123253a6505056585ad6ced4a01426aa1105be
src/orderflow/hooks/__pycache__/dom_quote_motion.cpython-313.pyc ccec249ff0e7e953f6f5809567aa0c3d83b823b6b2a632c1ff934e4226421ac6
src/orderflow/hooks/__pycache__/dom_wall.cpython-313.pyc 5d027b5fe300ce310e16471a5b5fbd4edb77b2b3a2d02c7041b434e81b58a80a
src/orderflow/hooks/__pycache__/flow_transition.cpython-313.pyc 5e3332b9d8b89440bc62b5a6b4407d9b839c53d16be06b3291682f9a4811043b
src/orderflow/hooks/__pycache__/interaction.cpython-313.pyc 42682e37cd920af2c4e877a18bfd023aa53e2bd5c0e1f6e8085c06629301c1f3
src/orderflow/hooks/__pycache__/liquidation.cpython-313.pyc c4f07c6792734dce7c5a946e0785a75e97ccf7b3faa5bc4c080b56bb405f48eb
src/orderflow/hooks/__pycache__/live.cpython-313.pyc 13c3e0be001dfaa46b136494ace6ee6f4f118e9f1734cc56c834fa1e23c19257
src/orderflow/hooks/__pycache__/models.cpython-313.pyc 762f70edcd17b0bd8d7699f811108c228a32ea056d2e92eb9d366dae3686b3a2
src/orderflow/hooks/__pycache__/open_interest.cpython-313.pyc 80adda4acb53c2ff3303de0abf139aa4b2dec9d2055c0119a43c669549509225
src/orderflow/hooks/__pycache__/price_structure.cpython-313.pyc 48eeb4b4f25fbcf5a1ca6078696ad690f554e62f2ce444c463ba32faf89262bf
src/orderflow/hooks/__pycache__/quality.cpython-313.pyc 2952c0f6813106af0b6ce98680e7c3badeaad56db9e4fc526ce1e7a140ce1af8
src/orderflow/hooks/__pycache__/registry.cpython-313.pyc 4d92dff4f9357dff4520d8e3bdc46aa95ee8a186b6d131969c74cd78e706375c
src/orderflow/hooks/__pycache__/runtime.cpython-313.pyc cd13c0774a1786e4ce7e1e9f74d54cc140fb588fce49a5d4357e553a6a9a5330
src/orderflow/hooks/adapters.py 127f74865b142b2164beaa3844fc53b429115d660c8ef5a5b5df2785a9fae5e6
src/orderflow/hooks/config.py b8cbff073564b1a39f826fb4f5be13f8ea68ef260117efe242718b8be13fa7c4
src/orderflow/hooks/detector_utils.py b33007c2a6c0a127f065e73e5f714e5c672d6a65ee47a7de9792dcaedf205ed0
src/orderflow/hooks/dom_features.py 54f95a6c249038d08adb920f381e04d2323205e11144b01ddb4565d5bcff5dc6
src/orderflow/hooks/dom_iceberg.py 270d3eb9fb40a978ca2dd096d806303c0605550de54a963f0a4194d583ee57ae
src/orderflow/hooks/dom_liquidity.py 7e361b3e4eb1728d3ba200b22cf7af1e41fe53dfa041c37e7f63dbf3437524dc
src/orderflow/hooks/dom_quote_motion.py 91656e9e83f747652c3935340bccb28238fbf27e057fd39db9c66cdefe808459
src/orderflow/hooks/dom_wall.py 24597a792f3698e84a7eb77fb3bd51baf39ec2e7f66b1b8a716d35dd79c400f5
src/orderflow/hooks/flow_transition.py 7824fdd02ba0676a048047754581afddc0145d102bf0c1af6ed3104df03debe2
src/orderflow/hooks/interaction.py 4c957ea4ea64fec0de0f778337a602b814e134d2cfa185a13a7b8497cf8b6ffa
src/orderflow/hooks/liquidation.py 8484ebfa35538ee9fd5d1966ba189a7f89d5942f4e80527b31e9cc1409745182
src/orderflow/hooks/live.py 0a25aef6f55dfc7534adb4f7eff9b6dd4c2870c83749609c16e844ee1df8b45e
src/orderflow/hooks/models.py 954330871810f7380e7cf70d0b8dd3771ea0a8f9bfd9af309fde235ebd90e95f
src/orderflow/hooks/open_interest.py a00ed3113a78734d1168f9d9c0cb14083dcac738fd1a44a56d43e5d9723ee9dc
src/orderflow/hooks/price_structure.py 1a96dbb0a6aac3b878bfaf3886d51df297c3f5b42846402de54100c79d07b1dc
src/orderflow/hooks/quality.py 27ab02a2880c4f44f6184225739c5c5ecbc64f2998144684134778ff2510b4e8
src/orderflow/hooks/registry.py 39fcba0d99fbd7ab8a0b6f377bc8048e202118abaf452084cdb84b04a1875593
src/orderflow/hooks/runtime.py 04432da90e1516e613db8623a84e9d8c6f1e8677fd7a7e14908b39cc22873f57
src/strategy_engine/__init__.py 16f50eac7f8b8be9ee5fbda88a6a66f9996366c14663abb6bc4a49f52a29fa92
src/strategy_engine/__pycache__/__init__.cpython-313.pyc 3994f716b78f6045c8cdf7d147063e3c9e59252cc4d0bd9fc991b39e2b0bc6db
src/strategy_engine/__pycache__/engine.cpython-313.pyc 5ad49f63500c4f133c80e5b2bf3d3ad58a81094258558c0cd99eb8c061bd2334
src/strategy_engine/__pycache__/events.cpython-313.pyc 9c0aaaa90030265aec9aa0dc6434bbfc2f460612103a94762eaa5ac6d2e8eeed
src/strategy_engine/__pycache__/predicate_eval.cpython-313.pyc 12c486c060fa46a8076b5fc11425fb7a9a3452878c64fa4c32ae889185804d57
src/strategy_engine/__pycache__/predicate_spec.cpython-313.pyc 7a7bebba9fe1f6209332ffc0c53541f1212be59d3b3c9a71825514cb6368118f
src/strategy_engine/__pycache__/real_predicate_eval.cpython-313.pyc 1af39d01ded45c08bdc4836b0df09babc75a045c32c0e3e848eec4c03b3fddd4
src/strategy_engine/__pycache__/variant_runtime.cpython-313.pyc 45bb4881fda7f286a4948b6063bdb5730aedefa58cfa3f0ba6c7286077dbed20
src/strategy_engine/engine.py ca6514757a64cf8848cf1e65501bd9a3427c3124cd8101a82e096541bad0153d
src/strategy_engine/events.py 778bf39fc5fa346b9f14fa57d2fbe9a66492d013dce4d4908bcbe0c2c0ec4ecb
src/strategy_engine/ingestion/__init__.py 7e0c29381ca25bd026a0b09c1d76bc9faff55d0917ad596d78c2291798291ddf
src/strategy_engine/ingestion/__pycache__/__init__.cpython-313.pyc 96670c2b9647d5ebd455ef9dd829a7b80e150238d2c1f8bdb71d5e24d1309d53
src/strategy_engine/ingestion/__pycache__/condition_adapter.cpython-313.pyc 2485b6aba039fadd988b20d0e37a18d9ff10afaa39829c49886992535d3ef594
src/strategy_engine/ingestion/__pycache__/market_state.cpython-313.pyc 8ad23fa68899bbd190b16b27be263be78509b0e7f58c3dc5cbbd70cd511cd694
src/strategy_engine/ingestion/__pycache__/session_vwap.cpython-313.pyc 8075d1a4da382271f11918d4634df8d62880f1bc14c49204962d13af87f0fb89
src/strategy_engine/ingestion/__pycache__/snapshot_producer.cpython-313.pyc cc44a11fbc8f60a38b3240bf0c64c592702180ba02ea4ca481bcee5e50484fbc
src/strategy_engine/ingestion/condition_adapter.py f58b06bae25f4fb461f905497bb5d38354171fe4dbf2ef5ddaf06c8f8370323a
src/strategy_engine/ingestion/market_state.py d4beaa78195616cc7bff957380a98d98061d5e50e8185a99784114f1dd7b8422
src/strategy_engine/ingestion/session_vwap.py 38f377f8159e21f1587c8a59c8be4537be1daa12fba2900699827e06d9e85882
src/strategy_engine/ingestion/snapshot_producer.py 894edbc04e5504fec395ab282daba3b0babb46862bf46a61d42d62707723c481
src/strategy_engine/predicate_eval.py 912f823118ba6e86d58f76d53dab50c97175d87caff422f3df7dc168e339d92b
src/strategy_engine/predicate_spec.py 13552904a85091dad95af7b9d91d7711ce26e602f78d86b88931178bc1aa251d
src/strategy_engine/real_predicate_eval.py 050922da7ad3516d77609d2530d9f701b37d01dd2b93fa97574df45a617452e8
src/strategy_engine/variant_runtime.py 2764f871cfc18216eb2e1743ec1d02de9b9dd4d0cd12ff3ad9eba377a2901dd9
```

- 開始時`git status --short`（本件開始前dirtyを含む）:

```text
 M ArchitectureRepository/00_Master/ORDER_BOOK_HEATMAP_IMPLEMENTATION_INSTRUCTION_V1_20260729.md
 M ArchitectureRepository/00_Master/ORDER_BOOK_HEATMAP_PHASE_H0_CHECKPOINT_20260729.md
 M ArchitectureRepository/00_Master/PROJECT_MEMORY.md
 M ArchitectureRepository/30_Modules/WebApp/Specifications/WebSocketPayload_Spec_v1.md
 M Delta_Engine_Pro4web/docker-compose.yml
 M Delta_Engine_Pro4web/tests/webapp/test_dom_tape_fusion_ui.py
 M Delta_Engine_Pro4web/tests/webapp/test_footprint_chart_ui.py
 M Delta_Engine_Pro4web/webapp/main.py
 M Delta_Engine_Pro4web/webapp/push_broker.py
 M Delta_Engine_Pro4web/webapp/static/footprint_canvas.js
 M Delta_Engine_Pro4web/webapp/static/index.html
?? ArchitectureRepository/00_Master/ABSORPTION_REALTIME_DISPLAY_FIX_CHECKPOINT_20260731.md
?? "ArchitectureRepository/00_Master/AI\343\202\263\343\203\241\343\203\263\343\203\210/"
?? ArchitectureRepository/00_Master/BINANCE_SPOT_REFERENCE_PRICE_CHECKPOINT_20260802.md
?? ArchitectureRepository/00_Master/CHECK_Stage2_Visual_Confirmation_v1.0.md
?? ArchitectureRepository/00_Master/DRIVE_CORE_BACKUP_CHECKPOINT_20260802.md
?? ArchitectureRepository/00_Master/DRIVE_CORE_BACKUP_RESTORE_20260802.md
?? ArchitectureRepository/00_Master/FOOTPRINT_POC_RESTORATION_CHECKPOINT_20260801.md
?? ArchitectureRepository/00_Master/HEATMAP/
?? ArchitectureRepository/00_Master/HEATMAP_Instruction_v1.5.md
?? ArchitectureRepository/00_Master/HOOK_STAGE2C4_CHECKPOINT_20260731.md
?? ArchitectureRepository/00_Master/Handoff_Heatmap_Phase2-3_Stage2_Task2_to_Task3_20260801.md
?? "ArchitectureRepository/00_Master/Heatmap_Handover_20260730 (1).md"
?? ArchitectureRepository/00_Master/Heatmap_Handover_20260730.md
?? ArchitectureRepository/00_Master/INSTR_Commit1_HeatmapCore_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Commit2_Preflight_PushBroker_v1.0.md
?? "ArchitectureRepository/00_Master/INSTR_Commit2_PushBroker_BookIdentity_v1.0 (1).md"
?? ArchitectureRepository/00_Master/INSTR_Commit2_PushBroker_BookIdentity_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Commit2_PushBroker_BookIdentity_v1.1.md
?? ArchitectureRepository/00_Master/INSTR_Commit3_AbsorptionRealtime_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Commit3_Preflight_AbsorptionTest_Wiring_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Commit3_Preflight_Pipeline_TimeSales_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Commit4_PersistentWriter_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Commit5_TimeSales_and_ComposeCleanup_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Commit6_FrameSource_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Stage2_Roadmap_and_Task1_Investigation_v1.0.md
?? "ArchitectureRepository/00_Master/INSTR_Stage2_Task1_DesignFinalization_Investigation_v1.0 (1).md"
?? ArchitectureRepository/00_Master/INSTR_Stage2_Task1_DesignFinalization_Investigation_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Stage2_Task1_FinalDesignMaterial_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Stage2_Task1_FrameSource_Implementation_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Stage2_Task2_AnchorMaterial_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Stage2_Task2_Implementation_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Stage2_Task2_Recovery_and_Completion_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Stage2_Task2_SupplyPath_Investigation_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Stage2_Task3_Commit_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Stage2_Task3_FrameBudget_Stage1_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Stage2_Task3_FrameBudget_Stage2_v1.0.md
?? ArchitectureRepository/00_Master/Instruction_Phase2-2_Renderer_v1.md
?? ArchitectureRepository/00_Master/PHEMEX_INTEGRATION_DETAILED_SPEC_20260802.md
?? ArchitectureRepository/00_Master/PHEMEX_PHASE0_BOUNDARY_LOCK_PREFLIGHT_INSTRUCTION_V1_20260803.md
?? ArchitectureRepository/00_Master/PHEMEX_SPEC_V1.3_REVISION_COMPLETION_REPORT_20260803.md
?? ArchitectureRepository/00_Master/REALTIME_UI_FRESHNESS_CLAUDE_REVIEW_PACKAGE_MANIFEST_20260803.md
?? ArchitectureRepository/00_Master/REALTIME_UI_FRESHNESS_ERROR_EVIDENCE_20260803.md
?? ArchitectureRepository/00_Master/REALTIME_UI_FRESHNESS_FIX_CHECKPOINT_20260802.md
?? ArchitectureRepository/00_Master/REALTIME_UI_FRESHNESS_HEARTBEAT_PERMANENT_FIX_IMPLEMENTATION_INSTRUCTION_V1_20260803.md
?? ArchitectureRepository/00_Master/REALTIME_UI_FRESHNESS_INSTRUCTION_V1_1_AMENDMENT_COMPLETION_REPORT_20260803.md
?? ArchitectureRepository/00_Master/REALTIME_UI_FRESHNESS_TIMEOUT_CURRENT_STATE_AND_REMEDIATION_REVIEW_20260803.md
?? ArchitectureRepository/00_Master/SCHEDULED_TASK_RESUME_FIX_CHECKPOINT_20260731.md
?? ArchitectureRepository/00_Master/VWAP_CHART_RELATED_MODULE_INVENTORY_20260729.md
?? ArchitectureRepository/00_Master/VWAP_INVESTIGATION_20260729/
?? "ArchitectureRepository/00_Master/\343\203\210\343\203\252\343\202\254\343\203\274\344\275\234\346\210\220\346\214\207\347\244\272\346\233\270\347\276\244/"
?? "ArchitectureRepository/00_Master/\345\256\237\351\201\213\347\224\250/"
?? "ArchitectureRepository/00_Master/\346\214\207\347\244\272\346\233\270_STAGE2C2_Hook\350\274\203\346\255\243_\345\210\206\345\270\203\351\233\206\350\250\210_v1.md"
?? Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/
?? Delta_Engine_Pro4web/tests/webapp/test_market_freshness_ui.py
?? Delta_Engine_Pro4web/tests/webapp/test_spot_reference_price.py
?? Delta_Engine_Pro4web/webapp/spot_price_stream.py
?? Delta_Engine_Pro4web/webapp/static/market_freshness.js
?? pytest-vwap-ui-elevated/
?? vwap-audit.duckdb
?? vwap_first100.jsonl
?? vwap_restore_ws_capture.jsonl
?? vwap_ws_capture.jsonl
```

- 完了済み: precondition／protected hash／改行baseline／dirty worktree固定。
- 未完了: connector/config、server heartbeat、browser state machine、Heatmap／Tape分離、test、runtime反映前gate。
- 変更file: 本checkpointのみ。
- test結果: 未実行。
- blocker: なし。改行説明の差は実測baselineを正として吸収し、既存改行を変更しない。
- 次の再開位置: 現物sourceとtest anchorを読み、connector/configのadditive変更と専用testから実装する。

## 2026-08-03 12:45:05 +09:00 — Connector／config完了

- 承認範囲: V1.1から変更なし。runtime未変更。
- 完了済み:
  - `ExchangeConnector`へUTC受信監査時刻、read-only monotonic受信値、`message_age_ms()`をadditive追加。
  - raw frame取得直後、`messages_out`／`out_queue.put()`より前に観測値を更新。
  - `webapp.market_heartbeat_interval_ms=1000`、`market_heartbeat_timeout_ms=3000`をschema／production YAMLへ追加。
  - timeoutがinterval×3未満ならstartup validationでfail fast。
- 変更file／現在SHA-256:
  - `src/acquisition/connector.py`: `bdbcf9d9e88b4803109fbe121480657c8c43c454177219d0f900c26f857cd588`
  - `src/config.py`: `e55a13351f4ed2501838b04bd1c7049ae0103c11e3ce1779d1aeea878a0663be`
  - `config/config.yaml`: `3cfe453ccb9dc248de443f69ddeeab06c7ac74fab3b8c33c1083649c8e7af6c2`
  - `tests/acquisition/test_acquisition.py`: `e95682644e19b133448e4796c136d7b091ebf6b93d206c4f65a422f77bfc3809`
  - `tests/webapp/test_api.py`: `969e74a69509d02b8f712595aa75b57d946fd7626e0e81dfed6e1f0955a4b959`
- 改行検証:
  - `connector.py`: CRLF 0、LF 208（開始181＋意図した27行）。
  - `config.py`: CRLF 2不変、LF 501（開始484＋意図した17行）。
  - `config.yaml`: CRLF 120不変、LF 40（開始38＋意図した2行）。
  - 既存行のCRLF↔LF変換なし。
- test結果: connector全体＋config専用 **14 passed**。
- protected hash: この段階では未変更対象。終了時に全件再測定する。
- 未完了: PushBroker heartbeat、main lifecycle／HELLO、browser state machine、Heatmap／Tape分離、全回帰。
- blocker: なし。
- 次の再開位置: PushBrokerへnon-cache `MARKET_HEARTBEAT`を追加し、mainのlive限定task／payload生成／HELLOを接続する。

## 2026-08-03 13:12:50 +09:00 — main.py改行自己汚染検出・限定修復

- 発生: server heartbeat hunk適用直後、`main.py`がCRLF 944／LF 193となり、開始値から既存CRLF 10行がLF化し、新規87行もLFになったことを即時検出。
- 規律対応: それ以上の実装hunkを停止。V2 review package内の開始時`main.py`と現物をread-only全文比較し、既存CRLF→LF 10行と新規87行を特定。
- 修復: 内容を変更せず、今回の4 semantic hunkだけの97改行をCRLFへ限定復元。広域normalize、dos2unix／unix2dosは未使用。
- 修復後: CRLF 1,041（開始954＋意図した新規87）、LF 96（開始96不変）、総newline 1,137。
- 修復後SHA-256: `7fadb2e281a996e97c2fd496803dec6627b14043e1b9ed9c3eec837d0ce95dc1`
- content invariant: CRLFをLFへ正規化した文字列比較で修復前後完全一致。
- 変更file: `webapp/main.py`の改行だけ、本checkpoint。
- test結果: 修復前Python構文PASS。修復後はserver専用testと併せて再実行する。
- protected hash: 未変更。
- blocker: 解消。V1.1の意図した改行増減条件へ復帰。
- 次の再開位置: PushBroker／main heartbeat専用testを追加し、payload、sequence、fresh AND条件、cache不存在、live/replay lifecycleを検証する。

## 2026-08-03 13:15:53 +09:00 — Server MARKET_HEARTBEAT完了

- 承認範囲: V1.1から変更なし。runtime未変更。
- 完了済み:
  - `PushBroker.send_market_heartbeat()`をadditive追加。通常`_broadcast()`経路、process-local sequence 1開始・1増分。
  - heartbeat cache／`_latest_heartbeat_message`は作成しない。
  - mainへ即時初回送信＋1000ms間隔のlive限定taskを追加し、既存shutdown tasksへ包含。
  - payload fresh条件を`SUBSCRIBED`、monotonic age 0〜3000ms、pipeline task aliveのANDに固定。
  - HELLOへ`market_mode`、interval 1000、timeout 3000をadditive追加。
  - replayではlive heartbeat taskを起動せず、HELLOを`market_mode=replay`とする。
- 変更file／現在SHA-256:
  - `webapp/main.py`: `7fadb2e281a996e97c2fd496803dec6627b14043e1b9ed9c3eec837d0ce95dc1`
  - `webapp/push_broker.py`: `4c0409b73f14661ef3a33f9f3f870385e0b3311da1deb65e03b8b937efe43fd8`
  - `tests/webapp/test_push_broker.py`: `5eb9160076cd9c27866a02bbf324c524fcb36945869a0a88b34b772896824503`
  - `tests/webapp/test_api.py`: `e351cc3c8ea5d146f336b0c25074110effaafc9e7130049dfe9fce80d2b6cb15`
- 改行検証:
  - `main.py`: CRLF 1,041（開始954＋意図した87）、LF 96不変。
  - `push_broker.py`: CRLF 3不変、LF 669（開始658＋意図した11）。
- test結果:
  - server heartbeat専用 **5 passed**。
  - replay isolation専用 **1 passed**。
  - connector/config段階を含む累計専用実行はすべてPASS。
- protected hash: 未変更対象。終了時に全件再測定。
- 未完了: browser state machine、Heatmap／Tape transport分離、仕様更新、関連／全体test。
- blocker: なし。
- 次の再開位置: `market_freshness.js`をlive heartbeat guardとSpot event guardへ分離し、HELLO／MARKET_HEARTBEAT／TICK state遷移を`index.html`へ接続する。

## 2026-08-03 13:22:58 +09:00 — Browser heartbeat state machine完了

- 承認範囲: V1.1から変更なし。runtime未変更。
- 完了済み:
  - USD-Mを`MarketHeartbeatGuard`、Spotを独立`SpotEventFreshnessGuard`へ分離。既存Spot aliasは互換維持。
  - USD-M guardはHELLOの1000／3000だけを使用し、browser sourceへtimeout値を重複hard-codeしない。
  - heartbeat受信間隔は`performance.now()`相当monotonic clockだけで判定。payload絶対時刻とbrowser wall clockを比較しない。
  - TICK absence timer／`TICK_TIMEOUT`／`TICK_SYNC_TIMEOUT`を撤去。
  - live heartbeat、upstream fresh、pipeline alive、mode、sequenceを検証。
  - `STALE -> fresh heartbeat -> SYNCING -> fresh TICK -> LIVE`を固定。
  - replayは`REPLAY` stateでlive heartbeat timeoutをdisableし、mode mismatch heartbeatをreject。
  - TICKの既存published/source metadata fail-closedは維持。
- 変更file／現在SHA-256:
  - `webapp/static/market_freshness.js`: `65c94cf5f90f37b381b1877c9ed1c4f0e93d92540ff90238dbc5c44af3483a48`
  - `webapp/static/index.html`: `3a025cd2ef7425e922a962fa80a438b0d31f5e77b9a16732aacfc4f3577c513c`
  - `tests/webapp/test_market_freshness_ui.py`: `270c1a4891fa1a64be63b5ca387feb1376d2849cdb94a450b39f532f4596e5ef`
- 改行検証:
  - `market_freshness.js`: CRLF 0、LF 341（開始122＋意図した219）。
  - `index.html`: CRLF 2,492（開始2,486＋意図した6）、LF 199（開始189＋意図した10）。
  - index適用直後に既存CRLF 7行のLF化を検出し、開始実物とのread-only diffで特定。既存7行＋CRLF領域新規6行だけを内容不変でCRLFへ限定修復済み。
- test結果: browser heartbeat＋Spot **21 passed**、Node module syntax PASS。
- 未完了: server/browser統合関連回帰、仕様更新、全体test。
- blocker: なし。
- 次の再開位置: Heatmap／Tape transport分離のsource境界とprotected hashを固定する。

## 2026-08-03 13:22:58 +09:00 — Heatmap／Tape transport分離完了

- 完了済み:
  - `TAPE_UI.setConnected()`／`HEATMAP_UI.setConnected()`は`setRealtimeTransportConnected()`内だけに集約。
  - WebSocket `onopen`でtrue、`onclose`／`onerror`でfalse。価格freshnessからの呼出し0。
  - `renderMarketFreshness()`からHeatmap／Tape connected操作、BOOK `NO_CONNECTION`置換、main全体のstale class／ARIA無効化を撤去。
  - `onBookUpdate()`の`S.marketFresh`入口returnを撤去し、STALE中もHeatmapへBOOKを渡す。
  - `onTapeUpdate()`はdecision freshnessではなくactual browser transport openだけをgateとする。
  - DOM／Heatmapの現在価格projectionは引き続き`S.marketFresh ? S.price : null`でfail closed。
- protected hash開始値との一致:
  - `orderbook_heatmap.js`: `2da8849d8e77ce82066f02e95c996dde75a952f2a900fc02018e4ea74467388b` — MATCH。
  - `time_sales.js`: `f59fec3f3478cc5a9b977c74978c3d8eb7c66e27a479a0b40fcf6d5f18f8d4c2` — MATCH。
  - `footprint_canvas.js`: `987c5da72a7375495eb44bd9910a1b79b076226b2f0206cc8e3d3de2f08c01be` — MATCH。
- source確認: connected呼出しはtransport同期関数の2件だけ。`TICK_TIMEOUT`はguard／indexとも0件。
- test結果: 専用structural assertionを含む前段21件PASS。
- 変更禁止file: 3 protected sourceとも未編集。
- 未完了: WebSocket仕様更新、関連test、WebApp／repository全回帰、最終tree hash。
- blocker: なし。
- 次の再開位置: WebSocket正本へMARKET_HEARTBEAT／HELLO／state separation契約をadditive追記し、関連testを実行する。

## 2026-08-03 13:32:31 +09:00 — 仕様更新・関連／WebApp回帰完了

- 承認範囲: V1.1から変更なし。runtime未変更。
- 完了済み:
  - `WebSocketPayload_Spec_v1.md`をv1.6 additiveへ更新。
  - HELLO、MARKET_HEARTBEAT payload、1000／3000、non-cache、monotonic browser判定、replay isolation、Heatmap／Tape分離を正本化。
  - TICK absence timeout契約を仕様から撤去し、個別TICK metadata fail-closedとheartbeat後fresh TICK復帰を明記。
- 仕様／test SHA-256:
  - `WebSocketPayload_Spec_v1.md`: `7d3f1a07c6085d8f68fbb526be33439068b5dc0ec64a041fb0759e2e4f0726a5`
  - `tests/webapp/test_push_broker.py`: `06e097978315d3abeb24f8ff8cfc3b55843fa1335d969e194663d2f3e856a4b0`
  - `tests/webapp/test_market_freshness_ui.py`: `d36ef8de8afde862492dd060669b64c3bc8f0045ca57f59634706b37c4ec8921`
- 仕様改行: CRLF 0不変、LF 608（開始559＋意図した49）。
- test結果:
  - 補強test（slow client後BOOK、wall clock±5分）: **2 passed**。
  - config／acquisition／freshness／PushBroker／API／Heatmap／Tape／DOM／Spot関連: **144 passed, 1 deselected**。deselectは開始前固定baseline 1件だけ。
  - WebApp全体: **198 passed, 1 failed**。
  - 唯一のfailureは開始前と同じ`test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation`の旧`#right>#left`要求。現物は開始前から`#main>#left`で今回hunkと非重複。新規failure 0。
- protected hash: browser分離checkpoint記載の3 file全件開始値一致。
- 未完了: repository全体回帰、最終diff/EOL/protected tree gate、runtime反映承認要求。
- blockerの限定範囲: 既知baseline failure 1件だけ。今回実装をblockしないが、全結果で明示分離する。
- 次の再開位置: 同一baseline test 1件だけを明示deselectし、repository全体回帰を実行する。

## 2026-08-03 13:46:01 +09:00 — repository全体回帰完了／protected tree開始値転記訂正

- 承認範囲: V1.1 source実装GOのまま。runtime／browser／container未変更。
- repository全体回帰: 開始前固定baseline 1件だけをdeselectし、**829 passed, 1 skipped, 1 deselected**（2026-08-03 13:42:22 +09:00終了、177.93秒）。新規failure 0。
- protected tree終了比較で`src/strategy_engine/ingestion/__pycache__/market_state.cpython-313.pyc`の開始記録と現物に1文字差を検出し、追加hunkを止めて原因を独立検証した。
- 開始記録の`...b16d27...`は転記ミス。正しいSHA-256は`8ad23fa68899bbd190b16b27be263be78509b0e7f58c3dc5cbbd70cd511cd694`。上記開始値列挙の該当1文字も`d`から`b`へ訂正した。
- 根拠:
  - 現物`.pyc`: 5,369 bytes、LastWriteTime `2026-07-28 02:10:50.6620912`。
  - source `market_state.py`: SHA-256 `d4beaa78195616cc7bff957380a98d98061d5e50e8185a99784114f1dd7b8422`、3,298 bytes、mtime `1785167567`で開始値と一致。
  - `.pyc`headerのsource mtime／sizeは上記sourceと一致。現物の`co_filename` (`src/strategy_engine/ingestion/market_state.py`)と同一条件でメモリ上再構築した`.pyc`は現物とbyte-for-byte一致し、SHA-256も上記正値。
- 判定: protected source／treeの実変更ではない。残り61 fileも開始値と一致。転記訂正後に62 file全件の最終gateを再実行する。
- 未完了: 最終diff／EOL／index allowlist／heartbeat cache不存在gate。
- blocker: なし。
- 次の再開位置: runtimeに触れず最終gateを全件再実行する。

## 2026-08-03 13:52:23 +09:00 — source実装最終gate PASS／runtime反映GO待ち

- 承認範囲: V1.1 source実装GO。source／test／仕様／checkpointのみ変更。browser操作、画面切替、container build／recreate、runtime反映は実施していない。
- source実装: 完了。connector受信観測値、config 1000／3000ms契約、non-cache `MARKET_HEARTBEAT`、live-only lifecycle、browser monotonic state machine、replay分離、Heatmap／Tape transport分離を実装済み。
- test最終結果:
  - connector／config専用: **14 passed**。
  - server heartbeat専用: **5 passed**。
  - replay isolation専用: **1 passed**。
  - browser heartbeat／Spot: **21 passed**。
  - 関連回帰: **144 passed, 1 deselected**。
  - WebApp全体: **198 passed, 1 failed**。failure 1件は開始前と同じ既知`#right>#left`要求で、今回hunkと非重複。新規failure 0。
  - repository全体（既知1件だけdeselect）: **829 passed, 1 skipped, 1 deselected**。新規failure 0。
- 終了時production／config SHA-256／bytes:

| file | SHA-256 | bytes |
|---|---|---:|
| `src/acquisition/connector.py` | `bdbcf9d9e88b4803109fbe121480657c8c43c454177219d0f900c26f857cd588` | 8,142 |
| `src/config.py` | `e55a13351f4ed2501838b04bd1c7049ae0103c11e3ce1779d1aeea878a0663be` | 18,778 |
| `config/config.yaml` | `3cfe453ccb9dc248de443f69ddeeab06c7ac74fab3b8c33c1083649c8e7af6c2` | 3,690 |
| `webapp/push_broker.py` | `4c0409b73f14661ef3a33f9f3f870385e0b3311da1deb65e03b8b937efe43fd8` | 28,984 |
| `webapp/main.py` | `7fadb2e281a996e97c2fd496803dec6627b14043e1b9ed9c3eec837d0ce95dc1` | 45,644 |
| `webapp/static/market_freshness.js` | `65c94cf5f90f37b381b1877c9ed1c4f0e93d92540ff90238dbc5c44af3483a48` | 12,611 |
| `webapp/static/index.html` | `3a025cd2ef7425e922a962fa80a438b0d31f5e77b9a16732aacfc4f3577c513c` | 193,917 |

- 改行終了値（開始値 → 終了値）:
  - `connector.py`: CRLF 0／LF 181 → CRLF 0／LF 208（意図したLF +27）。
  - `config.py`: CRLF 2／LF 484 → CRLF 2／LF 501（意図したLF +17）。
  - `config.yaml`: CRLF 120／LF 38 → CRLF 120／LF 40（意図したLF +2）。
  - `main.py`: CRLF 954／LF 96 → CRLF 1,041／LF 96（意図したCRLF +87）。
  - `push_broker.py`: CRLF 3／LF 658 → CRLF 3／LF 669（意図したLF +11）。
  - `market_freshness.js`: CRLF 0／LF 122 → CRLF 0／LF 341（意図したLF +219）。
  - `index.html`: CRLF 2,486／LF 189 → CRLF 2,492／LF 199（意図したCRLF +6／LF +10）。
  - V2開始現物とnormalized text diffを取得済み。既存行のCRLF↔LF変換0。
- protected終了gate:
  - `orderbook_heatmap.js` `2da8849d8e77ce82066f02e95c996dde75a952f2a900fc02018e4ea74467388b` — MATCH。
  - `time_sales.js` `f59fec3f3478cc5a9b977c74978c3d8eb7c66e27a479a0b40fcf6d5f18f8d4c2` — MATCH。
  - `footprint_canvas.js` `987c5da72a7375495eb44bd9910a1b79b076226b2f0206cc8e3d3de2f08c01be` — MATCH。
  - `src/orderflow/hooks/**`／`src/strategy_engine/**`: 開始値訂正後の**62 files全件MATCH**。
- その他gate:
  - `git diff --check`: PASS。
  - 開始前dirty以外の新規tracked diff: 許可file以外0。開始前dirty／untrackedは保存。
  - `index.html`: V2開始現物との全差分が§11 allowlistのsemantic anchorだけ。CSS／Flow Price Response／3段chart／Heatmap renderer／Footprint／Spot計算／Hook／Strategy差分0。
  - heartbeat cache signature: source 0件。`TICK_TIMEOUT`: guard／index 0件。
  - `TAPE_UI.setConnected`／`HEATMAP_UI.setConnected`: actual transport同期関数内の2呼出しだけ。
  - `onBookUpdate()`: `S.marketFresh` gate 0、`HEATMAP_UI.ingestBook()`有り。
  - JS構文: `market_freshness.js`／`index.html` inlineともPASS。Python AST構文: 対象source／test 8 files PASS。
- 未完了: §14で別承認とされる`deltaengine_clone`だけのbuild／recreate、§15 runtime検証、実装完了報告書。
- blockerの限定範囲: 技術blockerなし。runtime反映はユーザーの別GO待ちのため停止。
- 変更file: §3許可範囲のproduction／config 7、test 4、WebSocket仕様1、本checkpoint 1。完了報告書はまだ作成しない。
- 次の再開位置: ユーザーのruntime反映GO受領後、対象`deltaengine_clone`だけをbuild／recreateし、他service／data／browser画面を変更せず§15を検証する。

## 2026-08-03 13:55:30 +09:00 — runtime反映GO受領／build開始前checkpoint

- 明示承認: ユーザーからruntime反映`GO`を受領。
- 承認範囲: Docker Compose service `deltaengine_clone`だけのbuild／recreateと§15 runtime検証。
- 対象container: `delta_engine_pro4web-deltaengine_clone-1`。開始前状態`Up 6 hours`、port `127.0.0.1:15555->5555/tcp`／`0.0.0.0:18080->8080/tcp`。
- Compose定義service: `deltaengine_clone` 1件だけ。`--no-deps`で他serviceを操作しない。
- source反映前gate: 2026-08-03 13:52:23 +09:00 checkpointの全件PASSを維持。
- 禁止維持: production upstreamの故意停止、data／volume変更、他service操作、browser操作／画面切替、Git stage／commit／pushを行わない。
- 完了済み: source実装／test／pre-runtime gate。
- 未完了: 対象service build／recreate、host/container SHA、health／SUBSCRIBED／heartbeat／consumer非影響／soak検証、完了報告書。
- 変更file: 本checkpointへの承認記録だけ。
- blocker: なし。
- 次の再開位置: `deltaengine_clone`だけをbuild後、`--no-deps --force-recreate`で反映する。

## 2026-08-03 14:06:35 +09:00 — 対象image build完了

- 承認範囲: runtime反映GO。`deltaengine_clone`だけ。
- 完了済み: `docker compose ... build deltaengine_clone` exit 0（103.4秒）。
- 生成image: `delta_engine_pro4web-deltaengine_clone:latest`。
- image ID／manifest list: `sha256:9c4674c5b56638ae7f8ca629091558dd654e4b2c3572c46fbccf3a5525d88f10`。size 238,019,537 bytes。
- build結果: dependency installはcache hit、source `COPY . .`とimage exportは成功。
- 他service／data／browser操作: 0。このcheckpoint時点で旧containerは未切替。
- 未完了: 対象container recreate／health／runtime検証／soak／完了報告書。
- blocker: なし。
- 次の再開位置: `--no-deps --force-recreate deltaengine_clone`を実行し、新container ID／開始statusを固定する。

## 2026-08-03 14:11:36 +09:00 — runtime反映／初期検証PASS／soak開始前checkpoint

- 承認範囲: runtime反映GO。対象`deltaengine_clone`だけ。
- recreate: `docker compose ... up -d --no-deps --force-recreate deltaengine_clone` exit 0。他service／data操作0。
- 新container: `delta_engine_pro4web-deltaengine_clone-1`、ID `e2aab8bca1e53ef4f7a831aba4e8b23fe28a7a6e710cc67986af1e7666fa2854`。image `sha256:9c4674c5b56638ae7f8ca629091558dd654e4b2c3572c46fbccf3a5525d88f10`。running／restart 0。
- host/container SHA-256: production／config 7 files全件byte一致。値は2026-08-03 13:52:23 +09:00 checkpointの終了値と同一。
- health:
  - `/health`: HTTP 200 `{"status":"ok"}`。
  - `/api/health`: HTTP 200／state `GREEN`。book gap 0、WS reconnect 0、pipeline exception 0、latency 0ms。Tape dropped 0／pending 0／send_failures 0／balanced true。
- live WebSocket 20秒採取:
  - HELLO: `market_mode=live`、interval 1000ms、timeout 3000ms。
  - heartbeat 20件、sequence 85→104で全件連続。interval min 983.98ms／mean 1008.67ms／max 1038.96ms。
  - 全heartbeatが`upstream_state=SUBSCRIBED`／`upstream_fresh=true`／`pipeline_alive=true`。upstream age 0〜84ms。socket close 0。
  - 同socket受信: TICK 88、BOOK 165（全`SYNCED`）、TAPE 75、FLOW 17、FLOW_RESPONSE 20、BAR_UPDATE 47。
- isolated deterministic browser guard（稼働containerと7 source SHA一致の`market_freshness.js`）:
  - 5秒TICK無し／fresh heartbeat継続でLIVE維持。
  - 3001ms heartbeat無しでSTALE／`HEARTBEAT_TIMEOUT`、socket close call 0。
  - stale後のTICK先行は`WAITING_FOR_FRESH_HEARTBEAT`でreject。fresh heartbeat後はSYNCING、続くfresh TICKで同一guard／同一socketのLIVE復帰。socket open 1回のまま。
- browser画面／ユーザーの視認中画面: 操作／切替／障害注入0。
- 完了済み: §15-1〜7、9／10の初期証拠。§15-11／12も20秒区間PASS。§15-13はprotected hash／同socket message継続で初期PASS。
- 未完了: 長時間soak後のhealth／heartbeat／BOOK／Tape／Flow再検証、最終hash／checkpoint／完了報告書。
- blocker: なし。
- 次の再開位置: ユーザ画面とproduction upstreamを操作せず、isolated WebSocket clientで長時間soakを開始する。

## 2026-08-03 14:20:26 +09:00 — 3分runtime soak NO-GO（heartbeat 3000ms契約超過）

- 承認範囲: runtime反映後検証のみ。source／configの追加変更は行っていない。
- soak: isolated WebSocket client 1本を同一socketで180.039秒継続。受信例外なし、socket closeなし。
- PASS証拠:
  - heartbeat sequence 288→453／166件、gap 0。`SUBSCRIBED`／`upstream_fresh=true`／`pipeline_alive=true`以外0件。
  - HEALTH 35件全てGREEN。BOOK 1,218件全てSYNCED。TICK 625、Tape 571、FLOW_RESPONSE 178、BAR_UPDATE 369。
  - container restart 0／OOM false。book gap 0／pipeline exception 0／Tape dropped 0／pending 0／send failure 0。
- FAIL証拠:
  - heartbeat受信間隔: min 998.85ms／mean 1083.67ms／p95 1330.19ms／**max 4747.54ms**。§5／HELLOの3000ms timeoutを1747.54ms超過。
  - TICK最大gap 3.958秒（≥3秒 1回）。この区間でheartbeatが及ばなければbrowserは正常にSTALE判定するため、「TICK無しでheartbeat freshならLIVE維持」のruntime gateを満たさない。
- 原因切り分け:
  - heartbeat payload `published_time` 3連続のserver生成間隔に2.764秒を観測。client表示だけの遅延ではなく、heartbeat task生成／配信自体が1秒から遅延。
  - container CPU（soak client終了後）: 62.03〜101.83%。常時高負荷。
  - `STATS clients=1`。診断client 1本だけで、複数client倍増だけが原因ではない。
  - `_market_heartbeat_loop` は`broker.send_market_heartbeat()`完了後に1秒sleepし、heartbeatはTICK／BOOK／Tape等と同じ`_broadcast_lock`／bounded sendを通る。ロック待ち／event-loop遅延が1秒に加算される。
- 判定: §15-4／8／14はNO-GO。実装完了は宣言しない。
- 安全規律: 3000ms→5000／10000msの設定変更、PushBroker優先度変更、pipeline負荷変更、rollbackをCodex判断で行わない。稼働画面への障害注入も0。
- 変更file: 本checkpointへのruntime証拠追記だけ。稼働containerは恒久対処imageのままrunning。
- blockerの限定範囲: heartbeat interval／timeout契約とshared PushBroker遅延の設計判断。それ以外のhealth／BOOK／Tape／Flow継続証拠はPASS。
- 次の再開位置: heartbeat payloadのserver `published_time`とclient monotonic受信間隔を同時計測し、server scheduling遅延とtransport遅延を定量分離する。

## 2026-08-03 14:24:58 +09:00 — heartbeat遅延源確定／runtime NO-GO維持

- 追加同時計測: isolated WebSocket client 1本、120.048秒。例外0、sequence 757→836／80件、sequence gap 0。
- server `published_time`間隔: min 1000.54ms／mean 1404.47ms／p95 2779.62ms／**max 12011.18ms**。3000ms超過2回。
- client monotonic受信間隔: min 999.94ms／mean 1265.53ms／p95 2078.34ms／**max 6859.85ms**。3000ms超過2回。
- 代表区間:
  - sequence 757→758: server生成間隔12011.18ms、client受信間隔1036.31ms。sequence 757がshared broadcast待ち後に遅延到着し、その約1秒後に758が到着したと整合。
  - sequence 795→796: server間隔1390.56ms、client間隔6859.85ms。続く796→797はserver間隔6751.78ms、client間隔1115.49ms。配信lock待ちと次回loop生成遅延が前後区間へ分離して現れている。
- 根本原因:
  - `_market_heartbeat_loop` は`published_at`を作成後、`send_market_heartbeat()`がshared `_broadcast_lock`を取得／配信完了するまでawaitし、その後に1000ms sleepする。
  - そのためTICK／BOOK／Tape／Flow等の高頻度broadcastとCPU飽和下でheartbeatが優先されず、生成・到着の両方が3000msを超える。
  - heartbeatは意図どおり同一PushBroker経路だが、その契約にpriority／deadline guaranteeがないため、interval 1000ms／timeout 3000ms契約と現行配信構造が両立していない。
- 影響: browser guardは仕様どおり3秒でSTALE／`HEARTBEAT_TIMEOUT`に入る。後続fresh heartbeat／TICKで同一socket復帰するが、LIVEが一時OFFになる現象は残る。
- 2026-08-03 14:24:58 +09:00現在runtime:
  - container running／restart 0／OOM false／image `sha256:9c4674c5b56638ae7f8ca629091558dd654e4b2c3572c46fbccf3a5525d88f10`。
  - `/api/health` state GREEN。book gap 0／WS reconnect 0／pipeline exception 0／Tape dropped/pending/send failure 0。`anomalies_today=1`。
  - CPU 106.20%／memory 375.9MiB／OOMなし。
- 判定: 恒久対処のruntime検証は**NO-GO**。§15-4／8／14不適合。§16未充足のため完了報告書は作成しない。
- 現状維持: 証拠を壊さないため、設定値変更／priority実装／pipeline変更／rollbackは行っていない。恒久対処imageのcontainerは稼働継続中。
- 変更file: 本checkpointの証拠追記だけ。source／config／test／runtime dataの追加変更0。
- blockerの限定範囲: 新たな設計確定が必要。候補は「shared PushBrokerでheartbeatだけをdeadline-aware priority配信し、通常messageの相対順序／bounded send／Heatmap／Tape契約を保持」または「実測jitterに基づくtimeout契約の再承認」。Codex単独判断では選定しない。
- 次の再開位置: 本checkpoint実物の独立レビューと、priority配信／timeout再設計／rollbackのどれを行うかのユーザー明示承認。
