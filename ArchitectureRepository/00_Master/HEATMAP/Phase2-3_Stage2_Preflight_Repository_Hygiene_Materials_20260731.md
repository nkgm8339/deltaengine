# Phase 2-3 Stage 2 着手前 リポジトリ衛生是正（材料収集）

- Version: 1.0
- 採取日: 2026-07-31
- 対象: DeltaEngine05M
- HEAD申告値: `869dc83c9556d74d32853ddcd061ce66bf01fa13`

## T1. 保護4ファイルのHEAD差分全文

### `Delta_Engine_Pro4web/docker-compose.yml`

```text
diff --git a/Delta_Engine_Pro4web/docker-compose.yml b/Delta_Engine_Pro4web/docker-compose.yml
index adf1d58..17bfec8 100644
--- a/Delta_Engine_Pro4web/docker-compose.yml
+++ b/Delta_Engine_Pro4web/docker-compose.yml
@@ -29,3 +29,4 @@ services:
       - DEPTH_HISTORY_ENABLED=false
       - DEPTH_HISTORY_ROOT=/app/data_05M/depth_history_raw
     restart: unless-stopped
+
warning: in the working copy of 'Delta_Engine_Pro4web/docker-compose.yml', LF will be replaced by CRLF the next time Git touches it
```

### `Delta_Engine_Pro4web/tests/webapp/test_book_update.py`

```text
diff --git a/Delta_Engine_Pro4web/tests/webapp/test_book_update.py b/Delta_Engine_Pro4web/tests/webapp/test_book_update.py
index 277c0e6..8881ca7 100644
--- a/Delta_Engine_Pro4web/tests/webapp/test_book_update.py
+++ b/Delta_Engine_Pro4web/tests/webapp/test_book_update.py
@@ -4,9 +4,11 @@ from __future__ import annotations
 
 import asyncio
 import json
+from dataclasses import replace
 from datetime import datetime, timedelta, timezone
 from decimal import Decimal
 from unittest.mock import AsyncMock, MagicMock
+from uuid import UUID
 
 import pytest
 
@@ -298,6 +300,8 @@ def test_book_update_payload_and_reconnect_cache_use_latest_projection() -> None
     message = first_messages[0]
     assert message["type"] == "BOOK_UPDATE"
     payload = message["payload"]
+    assert str(UUID(payload["book_stream_id"])) == payload["book_stream_id"]
+    assert payload["book_sequence"] == 1
     assert payload["event_time"] == "2026-07-28T10:00:00.100000+00:00"
     assert payload["last_update_id"] == 123456
     assert payload["sync_state"] == "SYNCED"
@@ -311,6 +315,119 @@ def test_book_update_payload_and_reconnect_cache_use_latest_projection() -> None
     assert broker.book_updates_broadcast == 1
 
 
+def test_book_sequence_is_contiguous_across_synced_fail_closed_and_recovery() -> None:
+    synced = BookProjection(
+        projection_time=T0 + timedelta(milliseconds=200),
+        event_time=T0 + timedelta(milliseconds=100),
+        last_update_id=100,
+        sync_state="SYNCED",
+        bids=((D("100.0"), D("2.5")),),
+        asks=((D("100.1"), D("3.5")),),
+        depth_levels=50,
+        best_bid=D("100.0"),
+        best_ask=D("100.1"),
+        spread=D("0.1"),
+        age_ms=100,
+    )
+    stale = replace(
+        synced,
+        projection_time=T0 + timedelta(milliseconds=300),
+        event_time=T0 - timedelta(seconds=3),
+        last_update_id=101,
+        sync_state="STALE",
+        age_ms=3000,
+    )
+    recovered = replace(
+        synced,
+        projection_time=T0 + timedelta(milliseconds=400),
+        event_time=T0 + timedelta(milliseconds=350),
+        last_update_id=102,
+        age_ms=50,
+    )
+    broker = PushBroker("BTCUSDT")
+    messages: list[dict] = []
+    ws = MagicMock()
+    ws.send_text = AsyncMock(side_effect=lambda text: messages.append(json.loads(text)))
+
+    async def run() -> None:
+        await broker.register(ws)
+        for projection in (synced, stale, recovered):
+            await broker.on_book_update(projection)
+
+    asyncio.run(run())
+    payloads = [message["payload"] for message in messages]
+    assert [payload["book_sequence"] for payload in payloads] == [1, 2, 3]
+    assert {payload["book_stream_id"] for payload in payloads} == {broker.book_stream_id}
+    assert payloads[1]["sync_state"] == "STALE"
+    assert payloads[1]["bids"] == payloads[1]["asks"] == []
+    assert payloads[2]["sync_state"] == "SYNCED"
+    assert broker.book_updates_broadcast == 3
+
+
+def test_book_stream_changes_per_broker_lifecycle_and_sequence_restarts_at_one() -> None:
+    projection = BookProjection(
+        projection_time=T0,
+        event_time=T0,
+        last_update_id=1,
+        sync_state="SYNCED",
+        bids=((D("100.0"), D("1")),),
+        asks=((D("100.1"), D("1")),),
+        depth_levels=50,
+        best_bid=D("100.0"),
+        best_ask=D("100.1"),
+        spread=D("0.1"),
+        age_ms=0,
+    )
+    brokers = (PushBroker("BTCUSDT"), PushBroker("BTCUSDT"))
+    payloads: list[dict] = []
+
+    async def run() -> None:
+        for broker in brokers:
+            ws = MagicMock()
+            ws.send_text = AsyncMock(
+                side_effect=lambda text: payloads.append(json.loads(text)["payload"])
+            )
+            await broker.register(ws)
+            await broker.on_book_update(projection)
+
+    asyncio.run(run())
+    assert [payload["book_sequence"] for payload in payloads] == [1, 1]
+    assert payloads[0]["book_stream_id"] != payloads[1]["book_stream_id"]
+    assert all(str(UUID(payload["book_stream_id"])) == payload["book_stream_id"] for payload in payloads)
+
+
+def test_invalid_book_projection_does_not_consume_sequence() -> None:
+    valid = BookProjection(
+        projection_time=T0,
+        event_time=T0,
+        last_update_id=1,
+        sync_state="SYNCED",
+        bids=((D("100.0"), D("1")),),
+        asks=((D("100.1"), D("1")),),
+        depth_levels=50,
+        best_bid=D("100.0"),
+        best_ask=D("100.1"),
+        spread=D("0.1"),
+        age_ms=0,
+    )
+    invalid = replace(valid, best_bid=None)
+    broker = PushBroker("BTCUSDT")
+    messages: list[dict] = []
+    ws = MagicMock()
+    ws.send_text = AsyncMock(side_effect=lambda text: messages.append(json.loads(text)))
+
+    async def run() -> None:
+        await broker.register(ws)
+        with pytest.raises(ValueError, match="requires best bid"):
+            await broker.on_book_update(invalid)
+        await broker.on_book_update(valid)
+
+    asyncio.run(run())
+    assert len(messages) == 1
+    assert messages[0]["payload"]["book_sequence"] == 1
+    assert broker.book_updates_broadcast == 1
+
+
 def test_broker_defensively_clears_levels_for_fail_closed_message() -> None:
     stale = BookProjection(
         projection_time=T0,
warning: in the working copy of 'Delta_Engine_Pro4web/tests/webapp/test_book_update.py', LF will be replaced by CRLF the next time Git touches it
```

### `Delta_Engine_Pro4web/webapp/main.py`

```text
diff --git a/Delta_Engine_Pro4web/webapp/main.py b/Delta_Engine_Pro4web/webapp/main.py
index 425beb6..e3ef1c1 100644
--- a/Delta_Engine_Pro4web/webapp/main.py
+++ b/Delta_Engine_Pro4web/webapp/main.py
@@ -32,6 +32,7 @@ from src.observation.raw_journal import CaptureCampaign
 from src.orderflow.shadow_signal_recorder import ShadowSignalRecorder
 from src.pipeline import LivePipeline, ReplayPipeline, load_profile
 from src.monitor.health import HealthMonitor, HealthSnapshot, read_rss_mb
+from webapp.persistent_depth_writer import PersistentDepthWriter
 from src.acquisition.depth_history_recorder import (
     DepthHistoryRecorder,
     RecorderTee,
@@ -88,12 +89,13 @@ def _config_to_dict(node) -> Any:
     return node
 
 
-def _build_broker(config) -> PushBroker:
+def _build_broker(config, persistent_writer=None) -> PushBroker:
     w = config.webapp
     return PushBroker(
         symbol=config.market.symbol,
         depth_levels=w.depth_levels,
         live_dom_depth_levels=w.live_dom_depth_levels,
+        persistent_writer=persistent_writer,
     )
 
 
@@ -119,6 +121,8 @@ async def lifespan(app: FastAPI):
     app.state.version = resolve_version()
     config = load_config(_CONFIG_PATH)
     profile = load_profile(_profile_path(config))
+    persistent_enabled = os.getenv("PERSISTENT_DEPTH_HISTORY_ENABLED", "false").lower() == "true"
+    persistent_writer = PersistentDepthWriter(os.getenv("PERSISTENT_DEPTH_HISTORY_ROOT", "data_05M/depth_history"), config.market.symbol) if persistent_enabled else None
     depth_history_enabled = os.getenv("DEPTH_HISTORY_ENABLED", "false").lower() == "true"
     depth_history_recorder = (
         SafeRecorder(
@@ -130,7 +134,7 @@ async def lifespan(app: FastAPI):
         if depth_history_enabled
         else None
     )
-    broker = _build_broker(config)
+    broker = _build_broker(config, persistent_writer)
     context_observer = CombinedContextObserver(config.market.symbol)
     shadow_recorder = ShadowSignalRecorder(Path("data_05M/manual/flow_response_shadow.jsonl"))
     hook_capture = None
@@ -310,6 +314,13 @@ async def lifespan(app: FastAPI):
                 bc.flow_events,
             ))
 
+    def on_absorption_state_cb(event_time, result):
+        schedule_broker(broker.on_absorption_state(
+            event_time,
+            result,
+            window_sec=pipeline.absorption_window_sec,
+        ))
+
     def on_liquidation_cb(liq):
         schedule_broker(broker.on_liquidation(liq))
 
@@ -340,6 +351,7 @@ async def lifespan(app: FastAPI):
     pipeline.on_trade = None if config.replay.enabled else on_trade_cb
     pipeline.on_candle = on_candle_cb
     pipeline.on_analysis = on_analysis_cb
+    pipeline.on_absorption_state = on_absorption_state_cb
     pipeline.on_liquidation = on_liquidation_cb
     pipeline.on_flow_event = on_webapp_flow_cb
     pipeline.on_webapp_flow_event = on_webapp_flow_cb
@@ -579,6 +591,9 @@ async def lifespan(app: FastAPI):
         if hook_capture is not None:
             with contextlib.suppress(Exception):
                 await asyncio.to_thread(hook_capture.close)
+        if persistent_writer is not None:
+            with contextlib.suppress(Exception):
+                await asyncio.to_thread(persistent_writer.close)
         if depth_history_recorder is not None:
             with contextlib.suppress(Exception):
                 depth_history_recorder.close()
warning: in the working copy of 'Delta_Engine_Pro4web/webapp/main.py', LF will be replaced by CRLF the next time Git touches it
```

### `Delta_Engine_Pro4web/webapp/static/index.html`

```text
diff --git a/Delta_Engine_Pro4web/webapp/static/index.html b/Delta_Engine_Pro4web/webapp/static/index.html
index 8fd8b2f..ebb25b0 100644
--- a/Delta_Engine_Pro4web/webapp/static/index.html
+++ b/Delta_Engine_Pro4web/webapp/static/index.html
@@ -1019,6 +1019,7 @@ function setLive(on){
   if(TAPE_UI)TAPE_UI.setConnected(on);
   if(window.HEATMAP_UI)window.HEATMAP_UI.setConnected(on,S.marketTime||Date.now());
   if(!on&&PHASE5_FUSION_ENABLED){S.liveBook={sync_state:"NO_CONNECTION",bids:[],asks:[]};renderFootprint("liveDom");}
+  if(!on)resetAbsorptionRealtimeState();
 }
 
 function versionWarn(serverV){
@@ -1030,7 +1031,10 @@ function handle(m){
   if(m.v!=null&&m.v!==UI_PAYLOAD_VERSION)versionWarn(m.v);
   const previousSymbol=S.symbol;
   S.symbol=m.symbol||S.symbol;
-  if(previousSymbol!=="—"&&S.symbol!==previousSymbol&&FP.chart)FP.chart.clearDomTradePulses("SYMBOL_CHANGE");
+  if(previousSymbol!=="—"&&S.symbol!==previousSymbol){
+    if(FP.chart)FP.chart.clearDomTradePulses("SYMBOL_CHANGE");
+    resetAbsorptionRealtimeState();
+  }
   const messageTime=Date.parse(m.time);
   if(Number.isFinite(messageTime))S.marketTime=S.marketTime==null?messageTime:Math.max(S.marketTime,messageTime);
   const p=m.payload||{};
@@ -1049,6 +1053,7 @@ function handle(m){
           if(added){renderFlow();renderChart();}
         }
         break;
+      case "ABSORPTION_STATE": onAbsorptionState(m,p); break;
       case "FLOW": onFlow(m,p); break;
       case "FLOW_RESPONSE": onFlowResponse(m,p);break;
       case "LIQUIDATION": pushSeries("LIQUIDATION",Math.abs(N(p.quantity)??0)); break;
@@ -1062,6 +1067,7 @@ function handle(m){
       case "TAPE_UPDATE": if(PHASE5_FUSION_ENABLED)onTapeUpdate(m,p); break;
       default: break; // 未知typeは破棄（前方互換）
     }
+    expireAbsorptionState();
   }catch(_){/* 必須フィールド欠落等はメッセージ単位でスキップ。画面は落とさない */}
 }
 
@@ -1548,8 +1554,47 @@ function renderImbalance(){
   ri.onchange=apply;si.onchange=apply;mi.onchange=apply;
 })();
 
-// ---- Absorption independent indicator: event-only native reading ----
-let ABS=null;
+// ---- Absorption independent indicator: tick-time current state ----
+let ABS=null,ABS_REALTIME_SEEN=false,ABS_EXPIRES_AT=null;
+function resetAbsorptionRealtimeState(){
+  ABS=null;
+  ABS_REALTIME_SEEN=false;
+  ABS_EXPIRES_AT=null;
+  renderAbsorption();
+  renderLiveObservation();
+}
+function expireAbsorptionState(){
+  if(!ABS||!Number.isFinite(ABS_EXPIRES_AT)||!Number.isFinite(S.marketTime)||S.marketTime<ABS_EXPIRES_AT)return false;
+  ABS=null;
+  ABS_EXPIRES_AT=null;
+  renderAbsorption();
+  renderLiveObservation();
+  return true;
+}
+function onAbsorptionState(m,p){
+  ABS_REALTIME_SEEN=true;
+  if(p.active!==true){
+    ABS=null;
+    ABS_EXPIRES_AT=null;
+  }else{
+    const classification=String(p.classification||"");
+    const strength=N(p.strength),priceLow=N(p.price_low),priceHigh=N(p.price_high);
+    const validClassification=classification==="BUY_ABSORPTION"||classification==="SELL_ABSORPTION";
+    if(!validClassification||!Number.isFinite(strength)||strength<0||strength>1||
+       !Number.isFinite(priceLow)||!Number.isFinite(priceHigh)||priceLow>priceHigh){
+      ABS=null;
+      ABS_EXPIRES_AT=null;
+    }else{
+      ABS={classification,strength:p.strength,price_low:p.price_low,price_high:p.price_high};
+      const expiresAt=Date.parse(p.expires_at);
+      ABS_EXPIRES_AT=Number.isFinite(expiresAt)?expiresAt:null;
+    }
+  }
+  if(!expireAbsorptionState()){
+    renderAbsorption();
+    renderLiveObservation();
+  }
+}
 function renderAbsorption(){
   const el=$("absbody"), hint=$("abshint");
   if(!ABS){el.innerHTML='<div class="dash" style="text-align:center">—</div>'; hint.textContent="—"; return;}
@@ -1627,8 +1672,10 @@ function renderAnalysis(){
     }
   }
   renderImbalance();renderFootprint("staticHistory");
-  ABS=a.absorption||null;
-  renderAbsorption();
+  if(!ABS_REALTIME_SEEN){
+    ABS=a.absorption||null;
+    renderAbsorption();
+  }
   renderLiveObservation();
 }// market chart — shared time axis: PRICE / CVD+DELTA / VOLUME
 const MC={W:1200,H:500,L:18,R:1110,price:{top:20,bottom:286},cvd:{top:318,bottom:408},vol:{top:438,bottom:480}};
warning: in the working copy of 'Delta_Engine_Pro4web/webapp/static/index.html', LF will be replaced by CRLF the next time Git touches it
```

## T2. heatmapコアのimportと依存材料

### import文全行

#### `src/heatmap/binner.py`

```text
src/heatmap/binner.py:7:from __future__ import annotations
src/heatmap/binner.py:9:from collections.abc import Iterable, Mapping
src/heatmap/binner.py:10:from dataclasses import dataclass
src/heatmap/binner.py:11:from decimal import Decimal, InvalidOperation, ROUND_FLOOR
src/heatmap/binner.py:13:from src.orderflow.orderbook import OrderBookSnapshot
```

#### `src/heatmap/render_static.py`

```text
src/heatmap/render_static.py:8:from __future__ import annotations
src/heatmap/render_static.py:10:import binascii
src/heatmap/render_static.py:11:import logging
src/heatmap/render_static.py:12:import struct
src/heatmap/render_static.py:13:import time
src/heatmap/render_static.py:14:import zlib
src/heatmap/render_static.py:15:from dataclasses import dataclass
src/heatmap/render_static.py:16:from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
src/heatmap/render_static.py:17:from pathlib import Path
src/heatmap/render_static.py:18:from typing import Iterable
src/heatmap/render_static.py:20:from src.heatmap.binner import HeatmapGrid
src/heatmap/render_static.py:21:from src.heatmap.transform import (
src/heatmap/render_static.py:22:    PixelViewport,
src/heatmap/render_static.py:23:    RasterRect,
src/heatmap/render_static.py:24:    grid_cell_raster_bounds,
src/heatmap/render_static.py:25:)
```

#### `src/heatmap/transform.py`

```text
src/heatmap/transform.py:12:from __future__ import annotations
src/heatmap/transform.py:14:from dataclasses import dataclass
src/heatmap/transform.py:15:from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
```

#### `tests/heatmap/test_binner.py`

```text
tests/heatmap/test_binner.py:1:from __future__ import annotations
tests/heatmap/test_binner.py:3:from decimal import Decimal
tests/heatmap/test_binner.py:5:import pytest
tests/heatmap/test_binner.py:7:from src.heatmap.binner import HeatmapGrid, bin_samples
tests/heatmap/test_binner.py:8:from src.orderflow.orderbook import OrderBookSnapshot
```

#### `tests/heatmap/test_render_static.py`

```text
tests/heatmap/test_render_static.py:1:from __future__ import annotations
tests/heatmap/test_render_static.py:3:import logging
tests/heatmap/test_render_static.py:4:import struct
tests/heatmap/test_render_static.py:5:import zlib
tests/heatmap/test_render_static.py:6:from decimal import Decimal
tests/heatmap/test_render_static.py:7:from pathlib import Path
tests/heatmap/test_render_static.py:9:from src.heatmap.binner import bin_samples
tests/heatmap/test_render_static.py:10:from src.heatmap.render_static import render_heatmap
tests/heatmap/test_render_static.py:11:from src.heatmap.transform import PixelViewport, grid_cell_raster_bounds
tests/heatmap/test_render_static.py:12:from src.orderflow.orderbook import OrderBookSnapshot
```

#### `tests/heatmap/test_transform.py`

```text
tests/heatmap/test_transform.py:1:from __future__ import annotations
tests/heatmap/test_transform.py:3:from decimal import Decimal
tests/heatmap/test_transform.py:5:import pytest
tests/heatmap/test_transform.py:7:from src.heatmap.transform import (
tests/heatmap/test_transform.py:8:    GridIndex,
tests/heatmap/test_transform.py:9:    PixelViewport,
tests/heatmap/test_transform.py:10:    grid_cell_bounds,
tests/heatmap/test_transform.py:11:    grid_cell_raster_bounds,
tests/heatmap/test_transform.py:12:    grid_to_pixel,
tests/heatmap/test_transform.py:13:    pixel_to_grid,
tests/heatmap/test_transform.py:14:)
```

### import対象とM群依存

`○`に該当するimportはなし。

| import対象 | 判定・充足元 |
|---|---|
| `__future__`, `collections.abc`, `dataclasses`, `decimal`, `pathlib`, `typing`, `binascii`, `logging`, `struct`, `time`, `zlib` | × Python標準ライブラリ。各import行は上記一覧 |
| `pytest` | × テスト実行環境。`test_binner.py:5`、`test_transform.py:5` |
| `src.orderflow.orderbook.OrderBookSnapshot` | × HEAD既存。定義は `src/orderflow/orderbook.py:69-83` |
| `src.heatmap.binner` | × M群依存ではない。未追跡6ファイル集合内で充足。HEAD単体には未存在。`render_static.py:20`、`test_binner.py:7`、`test_render_static.py:9` |
| `src.heatmap.transform` | × M群依存ではない。未追跡6ファイル集合内で充足。HEAD単体には未存在。`render_static.py:21-25`、`test_transform.py:7-14`、`test_render_static.py:11` |
| `src.heatmap.render_static` | × M群依存ではない。未追跡6ファイル集合内で充足。HEAD単体には未存在。`test_render_static.py:10` |

HEAD側の依存定義:

```text
src/orderflow/orderbook.py:69:@dataclass(frozen=True)
src/orderflow/orderbook.py:70:class OrderBookSnapshot:
src/orderflow/orderbook.py:71:    """Immutable point-in-time view of Order Book State."""
src/orderflow/orderbook.py:73:    symbol: str
src/orderflow/orderbook.py:74:    last_update_id: int
src/orderflow/orderbook.py:75:    bids: dict[Decimal, Decimal]        # price → quantity (quantity > 0 only)
src/orderflow/orderbook.py:76:    asks: dict[Decimal, Decimal]
src/orderflow/orderbook.py:77:    event_time: Optional[datetime] = None
src/orderflow/orderbook.py:79:    def bid_quantity_at(self, price: Decimal) -> Decimal:
src/orderflow/orderbook.py:82:    def ask_quantity_at(self, price: Decimal) -> Decimal:
```

### テストfixture・helper

```text
tests/heatmap/test_render_static.py:15:def _snapshot(
tests/heatmap/test_render_static.py:30:def _grid_with_gap():
tests/heatmap/test_render_static.py:42:def _read_rgb_png(path: Path) -> tuple[int, int, list[list[tuple[int, int, int]]]]:
tests/heatmap/test_render_static.py:75:def _pixels_in_rect(
tests/heatmap/test_render_static.py:90:def test_render_creates_visible_png_with_report_and_gap_blank(
tests/heatmap/test_render_static.py:91:    tmp_path: Path,
tests/heatmap/test_render_static.py:92:    caplog,
tests/heatmap/test_render_static.py:93:) -> None:
tests/heatmap/test_render_static.py:101:    output = tmp_path / "heatmap.png"
tests/heatmap/test_render_static.py:103:    with caplog.at_level(logging.INFO):
tests/heatmap/test_render_static.py:240:def test_render_rejects_empty_grid(tmp_path: Path) -> None:
tests/heatmap/test_binner.py:11:def _snapshot(
tests/heatmap/test_binner.py:26:def _one_level_snapshot(update_id: int) -> OrderBookSnapshot:
tests/heatmap/test_binner.py:199:@pytest.mark.parametrize(
tests/heatmap/test_transform.py:17:def _viewport() -> PixelViewport:
tests/heatmap/test_transform.py:172:@pytest.mark.parametrize(
```

```text
conftest_match_count=0
```

テスト側のimportは、未追跡3実装、HEADの `OrderBookSnapshot`、標準ライブラリ、pytestおよびpytest組込みfixtureのみ。`pipeline.py`、`push_broker.py`、`main.py`、`index.html`、`time_sales.js`へのimportは該当なし。

## T3. HEAD不整合の最小是正単位材料

### `push_broker.py`の該当行

```text
webapp/push_broker.py:13:from uuid import uuid4
webapp/push_broker.py:160:        self.book_stream_id = str(uuid4())
webapp/push_broker.py:161:        self.book_updates_broadcast = 0
webapp/push_broker.py:261:        book_sequence = self.book_updates_broadcast + 1
webapp/push_broker.py:269:                "book_stream_id": self.book_stream_id,
webapp/push_broker.py:270:                "book_sequence": book_sequence,
webapp/push_broker.py:296:        self.book_updates_broadcast = book_sequence
```

該当未commit差分:

```diff
+from uuid import uuid4
```

```diff
+        self.book_stream_id = str(uuid4())
         self.book_updates_broadcast = 0
```

```diff
+        book_sequence = self.book_updates_broadcast + 1
         bids = projection.bids if synced else ()
         asks = projection.asks if synced else ()
```

```diff
             {
+                "book_stream_id": self.book_stream_id,
+                "book_sequence": book_sequence,
                 "event_time": (
```

```diff
         )
         self._latest_book_message = message
-        self.book_updates_broadcast += 1
+        self.book_updates_broadcast = book_sequence
```

### M群内の直接参照

`tests/webapp/test_book_update.py`:

```text
tests/webapp/test_book_update.py:303:    assert str(UUID(payload["book_stream_id"])) == payload["book_stream_id"]
tests/webapp/test_book_update.py:304:    assert payload["book_sequence"] == 1
tests/webapp/test_book_update.py:318:def test_book_sequence_is_contiguous_across_synced_fail_closed_and_recovery() -> None:
tests/webapp/test_book_update.py:359:    assert [payload["book_sequence"] for payload in payloads] == [1, 2, 3]
tests/webapp/test_book_update.py:360:    assert {payload["book_stream_id"] for payload in payloads} == {broker.book_stream_id}
tests/webapp/test_book_update.py:394:    assert [payload["book_sequence"] for payload in payloads] == [1, 1]
tests/webapp/test_book_update.py:395:    assert payloads[0]["book_stream_id"] != payloads[1]["book_stream_id"]
tests/webapp/test_book_update.py:396:    assert all(str(UUID(payload["book_stream_id"])) == payload["book_stream_id"] for payload in payloads)
tests/webapp/test_book_update.py:427:    assert messages[0]["payload"]["book_sequence"] == 1
```

次のM群ファイルに対する `book_stream_id|book_sequence` の全文検索は該当なし:

```text
src/pipeline.py
webapp/static/time_sales.js
webapp/static/index.html
webapp/main.py
```

`index.html`はBOOK_UPDATE payloadをそのまま既存HEATMAP APIへ渡す:

```text
webapp/static/index.html:1085:function onBookUpdate(p){
webapp/static/index.html:1086:  S.liveBook=p&&typeof p==="object"?p:{sync_state:"INVALID",bids:[],asks:[]};
webapp/static/index.html:1087:  if(window.HEATMAP_UI)window.HEATMAP_UI.ingestBook(S.liveBook);
webapp/static/index.html:1088:  renderFootprint("liveDom");
```

`main.py`は既存pumpへ `broker.on_book_update` を渡す:

```text
webapp/main.py:231:    book_projection_pump = LatestBookProjectionPump(
webapp/main.py:232:        lambda: getattr(pipeline, "book_manager", None),
webapp/main.py:233:        broker.on_book_update,
webapp/main.py:234:        depth_levels=config.webapp.live_dom_depth_levels,
webapp/main.py:235:        interval_sec=config.webapp.book_update_interval_ms / 1000.0,
```

### HEAD側コンシューマ

`orderbook_heatmap.js`はHEADで両フィールドを必須検証する:

```text
HEAD:webapp/static/orderbook_heatmap.js:49:  function validateBookPayload(raw) {
HEAD:webapp/static/orderbook_heatmap.js:50:    const payload = raw || {};
HEAD:webapp/static/orderbook_heatmap.js:51:    const errors = [];
HEAD:webapp/static/orderbook_heatmap.js:52:    const synced = payload.sync_state === "SYNCED";
HEAD:webapp/static/orderbook_heatmap.js:53:    if (!uuid(payload.book_stream_id)) errors.push("INVALID STREAM ID");
HEAD:webapp/static/orderbook_heatmap.js:54:    const sequence = Number(payload.book_sequence);
HEAD:webapp/static/orderbook_heatmap.js:59:    if (!Number.isSafeInteger(sequence) || sequence < 1) errors.push("INVALID BOOK SEQUENCE");
```

HEADでstream再起動・sequence連続性を処理する:

```text
HEAD:webapp/static/orderbook_heatmap.js:203:      const payload = checked.payload;
HEAD:webapp/static/orderbook_heatmap.js:204:      const sequence = payload.book_sequence;
HEAD:webapp/static/orderbook_heatmap.js:205:      if (this.streamId && payload.book_stream_id !== this.streamId) {
HEAD:webapp/static/orderbook_heatmap.js:206:        this.restartCount += 1;
HEAD:webapp/static/orderbook_heatmap.js:207:        this._appendGap("BOOK STREAM RESTART", this.lastEventTime || payload.event_time, payload.event_time, {
HEAD:webapp/static/orderbook_heatmap.js:208:          previous_stream: this.streamId, received_stream: payload.book_stream_id,
HEAD:webapp/static/orderbook_heatmap.js:210:        this.expectedSequence = null;
HEAD:webapp/static/orderbook_heatmap.js:212:      this.streamId = payload.book_stream_id;
HEAD:webapp/static/orderbook_heatmap.js:213:      if (this.expectedSequence !== null) {
HEAD:webapp/static/orderbook_heatmap.js:214:        if (sequence < this.expectedSequence) {
HEAD:webapp/static/orderbook_heatmap.js:215:          this.duplicates += 1;
HEAD:webapp/static/orderbook_heatmap.js:216:          return { accepted: false, duplicate: true, reason: "DUPLICATE BOOK SEQUENCE" };
HEAD:webapp/static/orderbook_heatmap.js:218:        if (sequence > this.expectedSequence) {
HEAD:webapp/static/orderbook_heatmap.js:219:          this.deliveryGapCount += 1;
HEAD:webapp/static/orderbook_heatmap.js:220:          this._appendGap("BOOK DELIVERY GAP", this.lastEventTime || payload.event_time, payload.event_time, {
HEAD:webapp/static/orderbook_heatmap.js:221:            expected: this.expectedSequence, received: sequence,
HEAD:webapp/static/orderbook_heatmap.js:225:      this.expectedSequence = sequence + 1;
```

HEADの `footprint_canvas.js`もstream IDを参照する:

```text
HEAD:webapp/static/footprint_canvas.js:493:    setData(data, layer) {
HEAD:webapp/static/footprint_canvas.js:494:      if (data && Object.prototype.hasOwnProperty.call(data, "book")) {
HEAD:webapp/static/footprint_canvas.js:495:        const nextBook = data.book;
HEAD:webapp/static/footprint_canvas.js:496:        const nextBookStreamId = nextBook && typeof nextBook.book_stream_id === "string"
HEAD:webapp/static/footprint_canvas.js:497:          ? nextBook.book_stream_id : null;
HEAD:webapp/static/footprint_canvas.js:498:        if (this.domTradePulseIdentity.bookStreamId && nextBookStreamId &&
HEAD:webapp/static/footprint_canvas.js:499:            this.domTradePulseIdentity.bookStreamId !== nextBookStreamId) {
HEAD:webapp/static/footprint_canvas.js:500:          this.clearDomTradePulses("BOOK_STREAM_RESTART");
HEAD:webapp/static/footprint_canvas.js:502:        if (nextBookStreamId) this.domTradePulseIdentity.bookStreamId = nextBookStreamId;
```

参照関係:

```text
HEAD main.py:227-233
  -> broker.on_book_update
push_broker.py:261,269-270,296（未commit差分）
  -> BOOK_UPDATEへstream ID/sequenceを付与
HEAD index.html:1079-1082
  -> payloadをHEATMAP_UIへ転送
HEAD orderbook_heatmap.js:49-60,203-225
  -> 両フィールドを検証・連続性処理
HEAD footprint_canvas.js:493-503
  -> book_stream_id変更を再起動として処理
```

M群のうち直接参照があるのは `test_book_update.py:303-304,318-360,394-396,427`。`pipeline.py`、`time_sales.js`、`index.html`、`main.py`には両識別子の直接参照なし。HEAD側の送出接続は `main.py:227-233`、転送接続は `index.html:1079-1082`、必須コンシューマは `orderbook_heatmap.js:49-60,203-225`。

## T4. 全pytest生出力

実行位置:

```text
C:\Users\user\desktop\deltaengine05M\Delta_Engine_Pro4web
```

実行コマンド:

```text
python -m pytest -q -p no:cacheprovider
```

FAILED行:

```text
FAILED tests/webapp/test_dom_tape_fusion_ui.py::test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation
```

サマリ行:

```text
1 failed, 773 passed, 1 skipped in 129.21s (0:02:09)
```

## 末尾git生出力

### `git rev-parse HEAD`

```text
869dc83c9556d74d32853ddcd061ce66bf01fa13
```

### `git status --porcelain`

```text
 M ArchitectureRepository/00_Master/ORDER_BOOK_HEATMAP_IMPLEMENTATION_INSTRUCTION_V1_20260729.md
 M ArchitectureRepository/00_Master/ORDER_BOOK_HEATMAP_PHASE_H0_CHECKPOINT_20260729.md
 M ArchitectureRepository/00_Master/PROJECT_MEMORY.md
 M ArchitectureRepository/30_Modules/WebApp/Specifications/WebSocketPayload_Spec_v1.md
 M Delta_Engine_Pro4web/docker-compose.yml
 M Delta_Engine_Pro4web/src/pipeline.py
 M Delta_Engine_Pro4web/tests/webapp/test_book_update.py
 M Delta_Engine_Pro4web/webapp/main.py
 M Delta_Engine_Pro4web/webapp/push_broker.py
 M Delta_Engine_Pro4web/webapp/static/index.html
 M Delta_Engine_Pro4web/webapp/static/time_sales.js
?? ArchitectureRepository/00_Master/ABSORPTION_REALTIME_DISPLAY_FIX_CHECKPOINT_20260731.md
?? "ArchitectureRepository/00_Master/AI\343\202\263\343\203\241\343\203\263\343\203\210/"
?? ArchitectureRepository/00_Master/HEATMAP/Approval_P22_Task1_Go_Task2.md
?? ArchitectureRepository/00_Master/HEATMAP/Approval_P22_Task2_Go_Task3.md
?? ArchitectureRepository/00_Master/HEATMAP/Approval_P22_Task3_Go_Task4.md
?? ArchitectureRepository/00_Master/HEATMAP/Approval_P22_Task3_PreReport_Reply_v1.md
?? ArchitectureRepository/00_Master/HEATMAP/Instruction_P22_Task1_ReSubmit_v1.md
?? ArchitectureRepository/00_Master/HEATMAP/Instruction_P22_Task2_Submit_v1.md
?? ArchitectureRepository/00_Master/HEATMAP/Instruction_P22_Task3_Submit_v1.md
?? ArchitectureRepository/00_Master/HEATMAP/Instruction_P22_Task4_Fix_v1.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Stage1_Investigation_Report_20260731.md
?? ArchitectureRepository/00_Master/HEATMAP/Roadmap_Heatmap_Render_to_Dynamic_v1.md
?? ArchitectureRepository/00_Master/HEATMAP/p21_evidence/
?? ArchitectureRepository/00_Master/HEATMAP/tools_p22/
?? ArchitectureRepository/00_Master/HEATMAP/worktree_backup_pre_p21_20260730.patch
?? ArchitectureRepository/00_Master/HEATMAP/worktree_status_pre_p21_20260730.txt
?? ArchitectureRepository/00_Master/HEATMAP_Instruction_v1.5.md
?? ArchitectureRepository/00_Master/HOOK_STAGE2C4_CHECKPOINT_20260731.md
?? "ArchitectureRepository/00_Master/Heatmap_Handover_20260730 (1).md"
?? ArchitectureRepository/00_Master/Heatmap_Handover_20260730.md
?? ArchitectureRepository/00_Master/Instruction_Phase2-2_Renderer_v1.md
?? ArchitectureRepository/00_Master/SCHEDULED_TASK_RESUME_FIX_CHECKPOINT_20260731.md
?? ArchitectureRepository/00_Master/VWAP_CHART_RELATED_MODULE_INVENTORY_20260729.md
?? ArchitectureRepository/00_Master/VWAP_INVESTIGATION_20260729/
?? "ArchitectureRepository/00_Master/\343\203\210\343\203\252\343\202\254\343\203\274\344\275\234\346\210\220\346\214\207\347\244\272\346\233\270\347\276\244/DeltaEngine_\347\265\214\347\267\257\345\240\261\345\221\212_\347\254\2541\346\234\237-\347\254\2544\346\234\237_20260727.md"
?? "ArchitectureRepository/00_Master/\343\203\210\343\203\252\343\202\254\343\203\274\344\275\234\346\210\220\346\214\207\347\244\272\346\233\270\347\276\244/HOOK_AND_LEGACY_STRATEGY_INVENTORY_20260727.md"
?? "ArchitectureRepository/00_Master/\343\203\210\343\203\252\343\202\254\343\203\274\344\275\234\346\210\220\346\214\207\347\244\272\346\233\270\347\276\244/HOOK_AND_STRATEGY_CONTENT_GUIDE_20260727.md"
?? "ArchitectureRepository/00_Master/\343\203\210\343\203\252\343\202\254\343\203\274\344\275\234\346\210\220\346\214\207\347\244\272\346\233\270\347\276\244/HOOK_STAGE2C1_CONTAINER_RESTART_20260730.md"
?? "ArchitectureRepository/00_Master/\343\203\210\343\203\252\343\202\254\343\203\274\344\275\234\346\210\220\346\214\207\347\244\272\346\233\270\347\276\244/HOOK_STAGE2C1_GATE_DATA_20260729.md"
?? "ArchitectureRepository/00_Master/\345\256\237\351\201\213\347\224\250/"
?? "ArchitectureRepository/00_Master/\346\214\207\347\244\272\346\233\270_STAGE2C2_Hook\350\274\203\346\255\243_\345\210\206\345\270\203\351\233\206\350\250\210_v1.md"
?? Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/
?? Delta_Engine_Pro4web/src/heatmap/binner.py
?? Delta_Engine_Pro4web/src/heatmap/render_static.py
?? Delta_Engine_Pro4web/src/heatmap/transform.py
?? Delta_Engine_Pro4web/tests/heatmap/test_binner.py
?? Delta_Engine_Pro4web/tests/heatmap/test_render_static.py
?? Delta_Engine_Pro4web/tests/heatmap/test_transform.py
?? Delta_Engine_Pro4web/tests/webapp/test_absorption_realtime_display.py
?? pytest-vwap-ui-elevated/
?? vwap-audit.duckdb
?? vwap_first100.jsonl
?? vwap_restore_ws_capture.jsonl
?? vwap_ws_capture.jsonl
```

### `git diff --cached --name-only`

```text
```
