# Binance Spot 参照価格表示 checkpoint

## 2026-08-02 15:18:27 +09:00 — 変更前

- 承認範囲: Binance現物`BTC/USDT`の公式価格をDeltaEngine上へ明示表示し、USD-M主価格との差を同一画面で確認できるようにする。
- 判断境界:
  - 現行Order Flow、DOM、Tape、OI、Flow Price Response、3段チャートはUSD-Mを正本として維持する。
  - Spot価格を既存分析入力へ混入させない。表示専用の独立参照値とする。
  - 完成済みFlow Price Responseと3段チャートの計算・意味は変更しない。
- 完了済み:
  - `ArchitectureRepository/00_Master/PROJECT_MEMORY.md`全文確認済み（同一作業連鎖内）。
  - 現物`BTC/USDT`とUSD-M`BTCUSDT Perpetual`の価格差を画像で確認。
  - tracked worktreeを変更しないsnapshot `83d3698d6ae9561dfa045bd6bac5e078c8411fe5`（`stash@{0}`）を作成。
  - snapshot前後で`WorktreeUnchanged=true`を確認。
- 現在のGit:
  - branch: `feature/footprint-dom-tape`
  - HEAD: `7552bc3487a3539dca9c7830e92de7cca8884c4f`
- 変更file: 本checkpointのみ。
- 未完了:
  - Binance公式Spot stream仕様の確認。
  - 既存WebSocket取得・lifecycle・PushBroker配信経路の精査。
  - Spot参照価格の取得、配信、表示、鮮度fail-closed実装。
  - 専用・関連・全体回帰。
  - container反映とBinance公式Spotとのtrade ID／価格照合。
- 検証結果: snapshot作成成功、worktree不変。
- blocker: なし。
- 次の再開位置: 公式Spot WebSocket仕様と既存`main.py`／acquisition／PushBroker lifecycleを読み、分析経路と完全分離した最小設計を確定する。

## 2026-08-02 15:21:10 +09:00 — 設計確定

- 承認範囲: 変更なし。
- 完了済み:
  - Binance公式Spot WebSocket仕様を確認。production endpointは`wss://stream.binance.com:9443`または`:443`、raw streamは`/ws/<streamName>`、`btcusdt@trade`はリアルタイムでtrade ID=`t`、price=`p`。
  - 既存USD-M取得、pipeline callback、PushBroker cache、FastAPI lifespan、UI freshness guardを精査。
  - Spot参照値を以下の完全分離経路に限定:
    1. 新規`spot_price_stream.py`が公式Spot raw trade streamだけを購読。
    2. `SPOT_PRICE` payloadをPushBrokerからbrowserへ配信し最新1件をreconnect cache。
    3. UIは独立freshness guardでSpot欄だけをfail closed。Spot停止時もUSD-M・Order Flowへ影響させない。
    4. headlineのUSD-M価格は維持し、その横へ`BINANCE SPOT BTC/USDT`と`SPOT−PERP`差を追加。
  - replay/testで外部Spot接続を起動しないため、runtime activationは`BINANCE_SPOT_REFERENCE_ENABLED=true`の明示環境変数に限定。
- 予定変更file:
  - `Delta_Engine_Pro4web/webapp/spot_price_stream.py`（新規）
  - `Delta_Engine_Pro4web/webapp/push_broker.py`
  - `Delta_Engine_Pro4web/webapp/main.py`
  - `Delta_Engine_Pro4web/webapp/static/index.html`
  - `Delta_Engine_Pro4web/docker-compose.yml`
  - 専用test file、WebSocket payload仕様、本checkpoint。
- 検証方針:
  - normalize/reconnect/cache/freshness/UI contract専用test。
  - WebSocket・UI関連回帰、全WebApp、全体回帰。
  - 実browser DOMのSpot表示と公式Spot同一trade ID価格を照合。
- blocker: なし。
- 次の再開位置: 新規Spot stream adapterとPushBroker `SPOT_PRICE` cacheから実装する。

## 2026-08-02 15:27:33 +09:00 — 限定実装完了

- 承認範囲: 変更なし。containerへの反映はまだ行っていない。
- 完了済み:
  - Binance Spot raw `btcusdt@trade`を検証・再接続する独立adapterを追加。
  - Spot全約定はadapterで受理するがbrowser配信は50ms latest-value pumpへ集約し、既存PushBroker lockへの過負荷を防止。
  - `SPOT_PRICE` payloadとlatest reconnect cacheを追加。
  - runtime起動を`BINANCE_SPOT_REFERENCE_ENABLED=true`に限定し、replay/test既定では外部接続しない。
  - UI topbarへ`BINANCE SPOT BTC/USDT`と`SPOT-PERP`差を追加。
  - Spot専用freshness guardを追加。5秒無更新／古いmetadataではSpot価格とbasisだけを消す。
  - Spot payload仕様と表示専用・分析非接続契約を追記。
- 変更file:
  - `Delta_Engine_Pro4web/webapp/spot_price_stream.py`（新規）
  - `Delta_Engine_Pro4web/webapp/push_broker.py`
  - `Delta_Engine_Pro4web/webapp/main.py`
  - `Delta_Engine_Pro4web/webapp/static/index.html`
  - `Delta_Engine_Pro4web/docker-compose.yml`
  - `Delta_Engine_Pro4web/tests/webapp/test_spot_reference_price.py`（新規）
  - `Delta_Engine_Pro4web/tests/webapp/test_market_freshness_ui.py`
  - `ArchitectureRepository/30_Modules/WebApp/Specifications/WebSocketPayload_Spec_v1.md`
  - 本checkpoint。
- 検証結果:
  - Python compile成功。
  - index inline JavaScript Node構文検査成功。
  - 専用Spot＋freshness test: 16 passed。
  - 対象fileの`git diff --check`成功。
- 未完了:
  - WebSocket lifecycle／PushBroker／UI関連回帰。
  - WebApp全体・repository全体回帰。
  - container反映と実browser／Binance Spot同一trade ID照合。
- blocker: なし。
- 次の再開位置: 関連testを実行し、task lifecycle・cache順序・既存UI contractの回帰を確認する。

## 2026-08-02 15:32:41 +09:00 — 実行環境反映前

- 承認範囲: test合格後、対象`deltaengine_clone`だけを再build/recreateして実配信照合する。
- 完了済み:
  - Spot専用＋freshness test: 16 passed。
  - WebSocket lifecycle／PushBroker／既存UI関連: 114 passed。
  - WebApp全体: 187 passed / 既知baseline 1 deselected。
  - repository全体: 815 passed / 1 skipped / 既知baseline 1 deselected。
- 検証結果:
  - 今回起因failureなし。
  - stagingは空、commit未作成。
  - 現在containerは旧runtimeのまま`Up 39 minutes`。まだSpot実装を反映していない。
- 未完了:
  - 対象serviceの再build/recreate。
  - `SPOT_PRICE` metadata/cache、実browser DOM、Binance Spot同一trade ID価格、basis表示の照合。
  - 最終health／Git差分／rollback境界確認。
- blocker: なし。
- 次の再開位置: `docker compose up -d --build deltaengine_clone`を実行し、起動後に公式Spot raw streamとbrowser受信・DOMを同時採取する。

## 2026-08-02 15:37:15 +09:00 — 実配信検証完了

- 承認範囲: 完了。対象`deltaengine_clone`以外のservice／dataは変更していない。
- 完了済み:
  - 対象serviceだけを再build/recreate。
  - Delta `SPOT_PRICE`とBinance公式Spot raw `btcusdt@trade`を8秒同時採取。
  - headless Edge実browserでWebSocket frame、JS state、描画DOMを同時照合。
  - 最終health・log・Git状態を確認。
- 実配信検証結果:
  - Delta Spot message 9件、Binance Spot trade 7件、同一trade ID 7件、価格不一致0件。
  - Spot transport age: min 1.8ms / avg 13.4ms / max 77.2ms。
  - 実browser DOM:
    - USD-M `63,449.1`
    - Binance Spot `63,474.72`
    - basis `SPOT-PERP +25.6`
    - USD-M freshness `LIVE`、Spot freshness `LIVE`
    - Spot DOM値と受信`SPOT_PRICE` frame一致。
    - USD-M DOM値と受信`TICK` frame一致。
  - 最終health GREEN、pipeline exception 0、event lag 0ms、Tape dropped/pending/send failure 0、anomalies 0。
  - Spot adapter warning/error 0件。
- 最終test:
  - 専用: 16 passed。
  - 関連: 114 passed。
  - WebApp: 187 passed / 既知baseline 1 deselected。
  - repository: 815 passed / 1 skipped / 既知baseline 1 deselected。
- Git状態:
  - stagingは空、commit未作成。
  - Spot追加前tracked snapshot: `83d3698d6ae9561dfa045bd6bac5e078c8411fe5`（`stash@{0}`）。
  - rollback時はsnapshot対比のSpot対象hunkだけを逆適用する。修正前から存在するuntracked`test_market_freshness_ui.py`は削除せず、Spot timer assertionの1 hunkだけを戻す。
- blocker:
  - 今回起因blockerなし。
  - 修正前からの既知baseline DOM/Tape layout static contract 1件は非関連で未変更。
- 次の再開位置: なし。Binance Spot参照価格の取得・表示・回帰・実配信照合まで完了。
