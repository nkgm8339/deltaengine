# Realtime UI Freshness Claude独立レビューpackage manifest

- 作成日: 2026-08-03 JST
- review status: **実装NO-GO／独立レビュー待ち**
- package file: `REALTIME_UI_FRESHNESS_CLAUDE_REVIEW_PACKAGE_V2_20260803.zip`

## レビュー目的

次の恒久対処実装指示書が、現物sourceと整合し、Heatmap、Tape、Flow Price Response、3段チャート、Hook／Strategyへ意図しない影響を与えないか独立検証する。

- `REALTIME_UI_FRESHNESS_HEARTBEAT_PERMANENT_FIX_IMPLEMENTATION_INSTRUCTION_V1_20260803.md`

## 主要確認事項

1. TICKをheartbeatとして使用しない設計になっているか
2. heartbeat interval 1000ms／timeout 3000msが設定値として一意か
3. browser判定がmonotonic受信間隔でありclock skewを持ち込まないか
4. heartbeatがreconnect cacheへ入らないか
5. upstream freshが`SUBSCRIBED`、age閾値内、pipeline aliveのANDか
6. replayへlive heartbeatが混入しないか
7. stale復帰にfresh heartbeat後のfresh TICKを要求するか
8. Heatmap／Tape connectedがactual browser WebSocket transportへ分離されるか
9. price STALEでもBOOK_UPDATEがHeatmapへ渡るか
10. PushBroker bounded send 0.5秒を維持するか
11. protected source hash規律が十分か
12. test／runtime gateが不具合再現と非影響を証明できるか

## 収録物

### Documents

- `PROJECT_MEMORY.md`
- `REALTIME_UI_FRESHNESS_TIMEOUT_CURRENT_STATE_AND_REMEDIATION_REVIEW_20260803.md`
- `REALTIME_UI_FRESHNESS_HEARTBEAT_PERMANENT_FIX_IMPLEMENTATION_INSTRUCTION_V1_20260803.md`
- `REALTIME_UI_FRESHNESS_FIX_CHECKPOINT_20260802.md`
- `WebSocketPayload_Spec_v1.md`
- `REALTIME_UI_FRESHNESS_ERROR_EVIDENCE_20260803.md`
- 本manifest

### Runtime evidence

- `OFF_bug_20260803_071240.png`

### Target source

- `src/acquisition/connector.py`
- `src/config.py`
- `config/config.yaml`
- `webapp/main.py`
- `webapp/push_broker.py`
- `webapp/static/market_freshness.js`
- `webapp/static/index.html`

### Protected source

- `webapp/static/orderbook_heatmap.js`
- `webapp/static/time_sales.js`
- `webapp/static/footprint_canvas.js`

### Related tests

- `tests/acquisition/test_acquisition.py`
- `tests/webapp/test_market_freshness_ui.py`
- `tests/webapp/test_push_broker.py`
- `tests/webapp/test_api.py`
- `tests/webapp/test_orderbook_heatmap_ui.py`
- `tests/webapp/test_tape_update.py`
- `tests/webapp/test_dom_tape_fusion_ui.py`

## 判定依頼

次のいずれかで明示判定する。

- `GO`: 指示書どおりの恒久対処実装へ進行可能
- `GO WITH CORRECTIONS`: 指示書修正後、source実装前に再提出
- `NO-GO`: 重大な設計／影響境界／検証欠陥あり

Codexの自己申告ではなく、収録された現物source、SHA-256前提値、指示書全文を独立照合する。
