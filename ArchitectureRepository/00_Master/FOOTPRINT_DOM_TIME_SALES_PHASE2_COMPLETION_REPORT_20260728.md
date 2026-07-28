# Footprint × LIVE DOM × Time & Sales Phase 2 完了報告

完了時刻: 2026-07-28 19:36 JST  
対象branch: `feature/footprint-dom-tape`  
開始HEAD: `92ee4eff823ba31e84f7fc0af197d39b877ec236`  
承認: V2.1 GO-7

## 1. 結論

Phase 2「LIVE DOM backend／BOOK_UPDATE」を実装し、全回帰試験まで完了した。

Order Bookのanalysis経路は全depth updateを従来どおり受理する。
browser向けには同じstateをread-onlyで100msごとに投影し、最新の有効状態だけを送る。
Snapshot queueやanalysis updateの間引きは導入していない。

完成済みのFlow Price Responseと3段チャートは変更していない。
Time & Sales、Canvas Footprint、LIVE DOM frontend描画、既存Order Book panel removalには
着手していない。

## 2. 実装済み契約

### 2.1 Order Book同期／鮮度

`OrderBookStateManager`へadditiveに次を追加した。

- 最新受理Snapshot／DIFFのsource `event_time`
- 最新受理時点のmonotonic clock
- `age_ms()`
- 初期／再同期のDIFF整列完了を表す`is_synchronized`

初期REST Snapshotだけでは数量を表示しない。最初のnon-stale DIFF適用後に
`SYNCED`へ遷移する。gap時は板数量とupdate IDを破棄し、再同期完了までfail closedとする。

### 2.2 Latest LIVE DOM projection

- sampling cadence: 100ms
- depth: bid／ask各top 50
- bids: bestから価格降順
- asks: bestから価格昇順
- server projection: Best Bid／Best Ask／Spread
- stale threshold: 2000ms
- 同一fingerprintは送信抑制
- browser向け全Snapshot queueなし
- projection／WebSocket送信失敗をmarket analysis経路から隔離

### 2.3 Fail closed

正常表示は`SYNCED`だけとする。

Fail-closed state:

- `NO_SNAPSHOT`
- `RESYNCING`
- `STALE`
- `EMPTY`
- `LOCKED`
- `CROSSED`
- `INVALID`

上記では`bids`／`asks`を空配列、Best Bid／Ask／Spreadをnullにする。
直前の正常数量を残さない。既存の確定足`CANDLE.orderbook`も、投影時に
`SYNCED`でない場合は空の既存15段payloadへ縮退する。

### 2.4 WebSocket／reconnect

`BOOK_UPDATE`をpayload v1.2のadditive typeとして追加した。
envelopeの`"v": 1`は維持する。

主なfield:

- `event_time`
- `projection_time`
- `last_update_id`
- `sync_state`
- `bids`／`asks`
- `depth_levels`
- `best_bid`／`best_ask`／`spread`
- `age_ms`

PushBrokerは最新`BOOK_UPDATE` 1件だけを保持し、再接続clientへ送る。
replay modeではlive projectorを起動しない。

### 2.5 Config／observability

既定値:

- `webapp.live_dom_depth_levels: 50`
- `webapp.book_update_interval_ms: 100`
- `webapp.book_stale_after_ms: 2000`

`/api/stats`へprojection state、sample数、送信数、SYNCED／fail-closed送信数、
同一状態抑制数、送信失敗数を追加した。

## 3. 変更file

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
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_PHASE2_CHECKPOINT_20260728.md`
- 本報告

既存dirty／untrackedのsource、実データ、監査・設計成果物は
reset、checkout、削除、stageしていない。
ディスク枯渇の解消では、workspace直下で監査した再生成可能な
pytest一時ディレクトリだけを削除した。

## 4. 検証

- `py_compile`: PASS
- Phase 2＋既存Order Book／WebApp対象回帰: **112 passed in 3.84s**
- replay stats明確化後targeted: **24 passed in 3.25s**
- final full pytest: **632 passed, 1 skipped in 29.69s**
- `git diff --check`: PASS
- top 50のsort／truncate: PASS
- initial sync→SYNCED→stale→gap→resync→recovery: PASS
- fail-closed quantity clearing: PASS
- reconnect latest cache: PASS
- projection read後のsnapshot／diff適用count不変: PASS
- WebSocket送信失敗の隔離と再試行: PASS
- replay projector非起動: PASS

## 5. 運用上の注意

- backendは`BOOK_UPDATE`を配信できるが、既存フロントページはまだ未知typeとして
  無視する。LIVE DOMの画面表示はPhase 5で接続する。
- したがって、本Phase完了だけでは既存ページ上に新DOMは現れない。
- production processは起動しておらず、production dataは変更していない。
- commit／pushは行っていない。
- pytest一時生成物の整理後、C driveの空きは約667MBである。

## 6. 次の承認境界

次はGO-8、Phase 3「TAPE backend」である。

GO-8まで未着手:

- accepted tradeの100ms batch
- `TAPE_UPDATE`
- process/session scoped `stream_id`／`sequence`
- gap／overflow contract
- reconnect／history hydrate境界

Phase 3でも完成済みのFlow Price Responseと3段チャートは変更対象外とする。
