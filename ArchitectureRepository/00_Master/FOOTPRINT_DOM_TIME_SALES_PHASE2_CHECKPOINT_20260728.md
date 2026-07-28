# Footprint × LIVE DOM × Time & Sales Phase 2 checkpoint

最終更新: 2026-07-28 19:36 JST  
状態: **完了**

## 承認

Phase 1完了報告後のユーザー「GO」を、V2.1 GO-7として受領した。

承認範囲:

- 新規WebSocket type `BOOK_UPDATE`
- analysis全depth update経路と独立したlatest Snapshot projection
- 100ms cadence
- top 50 bid／ask levels
- Best Bid／Ask／Spreadのserver projection
- no snapshot／gap／resync／stale／empty／locked／crossedのfail closed
- reconnect clientへのlatest BOOK_UPDATE再送
- projection counter／health projection
- config／WebSocket payload正本更新
- Phase 2専用・統合・全回帰試験
- Phase 2完了文書

承認範囲外:

- Phase 3 Time & Sales backend
- Phase 4 Canvas Footprint Chart
- Phase 5 frontend DOM／Tape融合
- existing Order Book panelのpresentation removal
- completed Flow Price Response／3段チャートの変更
- detector／Hook／storage depth経路への間引き
- production process／data操作
- git commit／push

## 開始状態

```text
branch: feature/footprint-dom-tape
HEAD: 92ee4eff823ba31e84f7fc0af197d39b877ec236
```

Phase 1差分および既存dirty／untracked状態を保持し、reset、checkout、削除、
stage、commitしない。

## 必須確認

- `PROJECT_MEMORY.md` 1000行を全文再確認
- 2026-07-21の再誕、Flow Price Response、3段チャート固定原則を再確認
- V2 §4.3、§8.2、§11、§18、§20、§22.2、§23 Phase 2を再確認
- WebSocketPayload v1.1正本を全文確認

## 現行境界監査

- `OrderBookStateManager`は全depth updateを同期的に適用する。
- initial REST Snapshot後は最初のnon-stale DIFFまでsync待ちとなる。
- gap検出時はbid／ask／last update IDを破棄し、supervisorが再Snapshotする。
- Strategy／detector／Hookは全depth update経路を使用している。
- WebAppは確定足`CANDLE`にだけOrder Book Snapshotを同梱する。
- `BAR_UPDATE`はOrder Bookを含まない。
- 現行PushBrokerに`BOOK_UPDATE`はない。
- current stateのsource event time／monotonic freshnessは
  `OrderBookStateManager`へ保持されていない。

## 確定実装方針

- analysis loopへWebSocket sendを直結しない。
- WebAppの独立taskが同一OrderBookStateManagerを100msごとにread-only投影する。
- updateごとのUI queueは作らず、直近状態だけを送る。
- `OrderBookStateManager`へsource event time、monotonic apply time、
  `is_synchronized`をadditiveに追加する。
- initial Snapshotだけで数量を表示せず、最初のDIFF適用後から`SYNCED`とする。
- stale閾値は2000msとする。BTCUSDT 100ms depth streamの20周期分である。
- LIVE DOM payloadはtop 50 levelsとする。既存CANDLE Order Bookの15段設定は変更しない。
- fail closed payloadはstatusを送るが、bids／asksは空、Best／Spreadはnullとする。
- replay modeではLIVE DOM projectorを起動しない。

## 完了済み

- 必須文書確認
- 現行Order Book／resync／PushBroker／main lifecycle監査
- Phase 2開始checkpoint作成
- `OrderBookStateManager`のsource event time／monotonic freshness／同期状態
- read-only latest-value `BOOK_UPDATE` projection
- 100ms cadence／top 50／Best Bid／Ask／Spread
- no snapshot／gap／resync／stale／empty／locked／crossedのfail closed
- PushBroker serialization／latest reconnect cache
- live lifecycle／replay非起動／stats／config接続
- 確定足`CANDLE.orderbook`も同期状態に対してfail closed
- Phase 2専用・既存対象回帰112件
- WebSocket payload正本v1.2追記
- V2／V2.1 GO-7 completion record
- 全回帰632 passed／1 skipped
- Phase 2完了報告
- 最終監査でreplay時`/api/stats`を`DISABLED_REPLAY`表示へ明確化
- 上記明確化後の対象24件と全回帰632件を再確認
- workspace内の再生成可能なpytest一時生成物を削除し、667MBの空きを回復

## 未完了

- Phase 2承認範囲内はなし
- Phase 3以降は別GO境界

## 変更file

- `Delta_Engine_Pro4web/src/orderflow/orderbook.py`
- `Delta_Engine_Pro4web/WebApp/book_projection.py`（新規）
- `Delta_Engine_Pro4web/WebApp/push_broker.py`
- `Delta_Engine_Pro4web/WebApp/main.py`
- `Delta_Engine_Pro4web/src/config.py`
- `Delta_Engine_Pro4web/config/config.yaml`
- `Delta_Engine_Pro4web/tests/webapp/test_book_update.py`（新規）
- `Delta_Engine_Pro4web/tests/webapp/test_api.py`
- `Delta_Engine_Pro4web/tests/webapp/test_push_broker.py`
- `Delta_Engine_Pro4web/tests/test_config.py`
- `ArchitectureRepository/30_Modules/WebApp/Specifications/WebSocketPayload_Spec_v1.md`
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_FUSION_IMPLEMENTATION_INSTRUCTION_V2_20260728.md`
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_FUSION_PREIMPLEMENTATION_AMENDMENT_V2_1_20260728.md`
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_PHASE2_COMPLETION_REPORT_20260728.md`（新規）
- 本checkpoint

## 検証結果

- `py_compile`: pass
- Phase 2 targeted regression: **112 passed**
- final targeted: **24 passed in 3.25s**
- final full pytest: **632 passed, 1 skipped in 29.69s**
- `git diff --check`: pass
- projectionはOrder Bookのsnapshot／diff適用countを変更しないことを確認
- send failureはanalysis経路へ伝播せず次回再試行することを確認
- replay modeではLIVE DOM projectorを起動しないことを確認
- production runtime／data変更なし
- blockerなし

## 次の再開位置

1. ユーザーのGO-8を待つ
2. GO-8受領時はPhase 3 TAPE backend開始checkpointを作成
3. accepted trade batching／stream_id／sequence／gap／overflowを実装・検証
