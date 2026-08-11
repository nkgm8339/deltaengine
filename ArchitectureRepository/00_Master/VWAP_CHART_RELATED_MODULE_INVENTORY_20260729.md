# VWAPチャート関連モジュール一覧

作成日: 2026-07-29 JST

目的: VWAPチャートの計算元、配信、履歴、描画、仕様、テストの関係を一覧化する。既存の計算・表示コードは変更しない。

## 1. 計算・セッション状態（Strategy Engine）

- `Delta_Engine_Pro4web/src/strategy_engine/ingestion/session_vwap.py`
  - 約定単位のUTCセッションVWAP accumulator。seed、trade観測、`value_at` を提供。
- `Delta_Engine_Pro4web/src/strategy_engine/ingestion/snapshot_producer.py`
  - `SessionVwapAccumulator` を保持し、約定を取り込み、スナップショットへ `session_vwap` / `session_open_avwap` を投影。
- `Delta_Engine_Pro4web/src/strategy_engine/ingestion/market_state.py`
  - 市場状態に保持される `session_vwap` のデータ構造・状態。
- `Delta_Engine_Pro4web/src/pipeline.py`
  - snapshot producer / market state をパイプラインで接続する上流モジュール。
- `Delta_Engine_Pro4web/src/database/session_vwap_warm_start.py`
  - DuckDBからUTCセッションVWAP seedを読み込む読み取り専用warm start。

## 2. WebSocket配信・履歴API

- `Delta_Engine_Pro4web/webapp/main.py`
  - `_chart_session_vwap()` で既存のmarket stateまたはsnapshot producerから値を取得し、CANDLE/BAR_UPDATE配信へ渡す。
- `Delta_Engine_Pro4web/webapp/push_broker.py`
  - `vwap` と `vwap_status`（EXACT/PARTIAL）をpayloadへ付加・検証。
- `Delta_Engine_Pro4web/webapp/history.py`
  - チャート履歴のVWAP列を返す。現状のDB履歴SELECTは `NULL AS vwap, NULL AS vwap_status` を含む。
- `ArchitectureRepository/30_Modules/WebApp/Specifications/WebSocketPayload_Spec_v1.md`
  - CANDLE/BAR_UPDATE payloadのVWAPフィールド仕様。

## 3. チャート描画

- `Delta_Engine_Pro4web/webapp/static/index.html`
  - `rememberVwap()`、bar正規化、履歴補完、価格スケール、VWAP線・ラベル・凡例を実装。
  - 現在の線・ラベル・凡例色は `WARN`。
- `Delta_Engine_Pro4web/webapp/static/footprint_canvas.js`
  - Footprint Canvas側の参照線としてVWAPを描画（現在の色定数は `CYAN`）。

## 4. テスト

- `Delta_Engine_Pro4web/tests/strategy_engine/test_session_vwap.py`
  - accumulatorの計算・seed・セッション境界。
- `Delta_Engine_Pro4web/tests/test_session_vwap_live.py`
  - live trade取り込みとVWAP状態。
- `Delta_Engine_Pro4web/tests/database/test_session_vwap_warm_start.py`
  - warm-start seed loader。
- `Delta_Engine_Pro4web/tests/webapp/test_bar_update.py`
  - CANDLE/BAR_UPDATE payloadとVWAPフィールド。
- `Delta_Engine_Pro4web/tests/webapp/test_history.py`
  - 履歴APIの列・VWAPフィールド。

## 5. 仕様・定義・運用資料

- `ArchitectureRepository/40_Reference/VWAPReference_v3.0.md`
  - VWAP定義・参照仕様。
- `ArchitectureRepository/40_Reference/IndicatorDefinitions_v3.md`
  - 指標定義。
- `ArchitectureRepository/40_Reference/TradingSessionsReference_v3.0.md`
  - セッション境界の参照。
- `ArchitectureRepository/00_Master/トリガー作成指示書群/VWAP_IMPLEMENTATION_CHECKPOINT_20260727.md`
  - VWAP実装チェックポイント。
- `ArchitectureRepository/Reference_Inventory.md`
  - 参照資料の索引。

## 6. 変更履歴上の注意

`849a7a30744e5741c4e89e7a7dc9cd1a7376866d`（2026-07-28）はVWAP配信・描画経路を追加したコミット。計算式そのものの変更は確認できないが、配信経路、履歴列、表示色（WARN）を変更している。色や計算の正当性は本一覧だけでは承認しない。
