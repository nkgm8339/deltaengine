# Footprint × LIVE DOM × Time & Sales Phase 3 checkpoint

最終更新: 2026-07-28 20:13 JST  
状態: **完了**

## 承認

Phase 2完了報告後のユーザー「GO」を、V2.1 GO-8として受領した。

承認範囲:

- authoritative accepted-trade tap
- thread-safe bounded tape batcher
- 100ms batch cadence
- 1 message最大250 trades
- pending capacity 10,000
- process／replay session scoped UUID `stream_id`
- stream内1始まり単調増加`sequence`
- `TAPE_UPDATE`
- overflow／send failure／pending accounting
- `GET /api/history/time-sales`
- live／replay lifecycle・stats
- WebSocket payload正本更新
- Phase 3専用・統合・全回帰試験
- Phase 3完了文書

承認範囲外:

- Phase 4 Canvas Footprint Chart
- Phase 5 Time & Sales／DOM frontend描画
- browser filter／virtualized rows／large marker／selection sync
- existing Order Book panelのpresentation removal
- completed Flow Price Response／3段チャートの変更
- Strategy／detector／Hook／storage acceptance経路の間引き
- production process／data操作
- git commit／push

## 開始状態

```text
branch: feature/footprint-dom-tape
HEAD: 92ee4eff823ba31e84f7fc0af197d39b877ec236
```

Phase 1／2差分および既存dirty／untracked source／artifactを保持し、
reset、checkout、削除、stage、commitしない。

## 必須確認

- `PROJECT_MEMORY.md` 1000行を全文再確認
- 2026-07-21の再誕、Flow Price Response、3段チャート固定原則を再確認
- V2 §12〜§16、§18、§22.3〜22.4、§23 Phase 3を再確認
- V2.1 §7 Tape sequence、§8 Timezone、§12 Tape試験条件を再確認
- Phase 2完了報告と次のGO-8境界を再確認

## 現行境界監査

- Live `on_trade` callbackはDataNormalizerの正規化、重複、非正値、side、
  out-of-order rejection通過後の受理約定だけに呼ばれる。
- 現行`TICK`は50ms latest-value投影であり、Tape sourceには使用できない。
- 現行ReplayPipelineは受理約定ごとの`on_trade` callbackを発火しない。
- Replay WebAppはworker threadでpipelineを実行する。
- 既存PushBrokerは`TAPE_UPDATE`を持たず、Tape batch cacheも持たない。
- `trades` tableにはUTC event time、trade ID、symbol、price、quantity、sideがある。
- 現行`query_trades`はtrade ID、notional、before cursorを返さない。

## 確定実装方針

- tapの`publish()`は同期・thread-safe・boundedとし、analysis loopでawaitしない。
- accepted tradeへlock内でsequenceを割り当て、acceptance orderを保持する。
- overflow policyはdrop oldest＋明示counterとする。新しいTapeを優先し、
  欠落sequenceと`dropped_count`で連続を偽装しない。
- batcherは100msごとにpendingを最大250件ずつ順番に全drainする。
- `accepted = sent + pending + inflight + dropped`を観測可能にする。
- send例外で失われたinflight tradeはdroppedへ移し、次batchで明示する。
- `stream_id`はbatcher生成時UUID。connectionではresetせず、server lifespan／
  replay sessionごとに新規生成する。
- reconnect時に過去Tape batchをcache再送しない。history APIと次のsequenceで
  clientがdedup／gap判定する。
- ReplayPipelineも受理約定callbackを発火し、replay専用streamだけへpublishする。
- history APIは最大500件、oldest-first、timezone付きUTC、notional exact、
  optional symbol、exclusive before cursorとする。
- `received_time`はcanonical tradeに存在しないため、payloadの`batch_time`を
  server send境界として使用する。

## 完了済み

- 必須文書確認
- accepted trade／normalizer／PushBroker／history／replay境界監査
- Phase 3開始checkpoint作成
- Live／Replay共通の例外隔離accepted-trade observer
- thread-safe bounded `TapeBatcher`
- 100ms／250件chunk／capacity 10,000／drop-oldest accounting
- UUID stream_id／stream内sequence／send failure gap accounting
- PushBroker `TAPE_UPDATE` serializer／reconnect非cache
- live／replay lifecycle／STATS／HEALTH／`/api/stats`
- `GET /api/history/time-sales`
- 最大500件／oldest-first／exact notional／UTC／symbol
- 同一event_timeを欠落させないevent_time＋trade_id複合cursor
- Phase 3対象回帰113件
- WebSocket payload正本v1.3 `TAPE_UPDATE`契約
- full regression 644 passed, 1 skipped
- V2／V2.1 GO-8 completion record
- Phase 3完了報告

## 未完了

- Phase 3承認範囲内の未完了なし
- Phase 4／5は未承認のため未着手

## 変更file

- `Delta_Engine_Pro4web/WebApp/tape.py`（新規）
- `Delta_Engine_Pro4web/WebApp/push_broker.py`
- `Delta_Engine_Pro4web/WebApp/main.py`
- `Delta_Engine_Pro4web/WebApp/history.py`
- `Delta_Engine_Pro4web/src/pipeline.py`
- `Delta_Engine_Pro4web/src/config.py`
- `Delta_Engine_Pro4web/config/config.yaml`
- `Delta_Engine_Pro4web/tests/webapp/test_tape_update.py`（新規）
- `Delta_Engine_Pro4web/tests/webapp/test_api.py`
- `Delta_Engine_Pro4web/tests/webapp/test_push_broker.py`
- `Delta_Engine_Pro4web/tests/test_live_pipeline.py`
- `Delta_Engine_Pro4web/tests/test_pipeline.py`
- `Delta_Engine_Pro4web/tests/test_config.py`
- `ArchitectureRepository/30_Modules/WebApp/Specifications/WebSocketPayload_Spec_v1.md`
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_FUSION_IMPLEMENTATION_INSTRUCTION_V2_20260728.md`
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_FUSION_PREIMPLEMENTATION_AMENDMENT_V2_1_20260728.md`
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_PHASE3_COMPLETION_REPORT_20260728.md`（新規）
- 本checkpoint

## 検証結果

- `py_compile`: pass
- Phase 3 targeted regression: **113 passed**
- accepted／sent／pending／inflight／dropped accounting balanceを確認
- overflow／send failureでsequence gapとdropped_countが明示されることを確認
- slow sender中もaccepted-trade publishがblockしないことを確認
- Live／Replayのduplicate／invalid trade非流入とobserver例外隔離を確認
- history 500件／notional／複合cursorを確認
- WebSocket payload正本v1.3契約更新を確認
- full regression: **644 passed, 1 skipped in 34.50s**
- `git diff --check`: pass
- production runtime／data変更なし
- Phase 3 pytest専用一時ディレクトリは対象path検証後に削除
- blockerなし

## 次の再開位置

1. ユーザーの明示GO-9を待つ
2. GO-9受領後、Phase 4 Canvas Footprint Chartを開始する
3. Phase 5 frontend統合は別の明示GOまで開始しない
