# 第三コミット着手前 pipeline.py / time_sales.js 差分材料

- Version: 1.0
- 採取日: 2026-07-31
- 対象: DeltaEngine05M
- HEAD: `3be272cbce32464b45f1e952d692cc5ce61703c3`

## T1. pipeline.py 全差分

```text
diff --git a/Delta_Engine_Pro4web/src/pipeline.py b/Delta_Engine_Pro4web/src/pipeline.py
index 6572379..ae2bb36 100644
--- a/Delta_Engine_Pro4web/src/pipeline.py
+++ b/Delta_Engine_Pro4web/src/pipeline.py
@@ -425,6 +425,7 @@ class ReplayPipeline:
         self.on_trade: Optional[Callable] = None
         self.on_candle: Optional[Callable] = None
         self.on_analysis: Optional[Callable] = None
+        self.on_absorption_state: Optional[Callable] = None
         self.on_flow_response: Optional[Callable] = None
         self._last_bar_close = None
         self._last_fp_bar = None
@@ -626,7 +627,11 @@ class ReplayPipeline:
                 closed_higher = higher_timeframes.process(normalized)
                 self.higher_timeframe_candles.update(closed_higher)
             fp_closed = footprint.process_trade(normalized)
-            absorption.observe_trade(normalized)
+            _observe_absorption_state(
+                absorption,
+                normalized,
+                self.on_absorption_state,
+            )
             if cvd_result.closed_candle is not None:
                 detected_divergence = divergence_detector.update(cvd_result.closed_candle)
                 # Spec §3.2: event indicators are silent on non-fire bars.
@@ -781,6 +786,23 @@ def _to_engine_ns(dt: datetime, origin_source_ns: int | None) -> int:
     return _to_source_ns(dt) - origin_source_ns
 
 
+def _observe_absorption_state(
+    absorption: AbsorptionDetector,
+    trade: Any,
+    on_state: Optional[Callable],
+) -> tuple[int, Optional[Any]]:
+    """Update the tick-driven detector and publish only meaningful UI state changes."""
+
+    previous = absorption.current()
+    previous_events = absorption.events_detected
+    absorption.observe_trade(trade)
+    current = absorption.current()
+    detected = absorption.events_detected > previous_events
+    if on_state is not None and (detected or current != previous):
+        on_state(trade.event_time, current)
+    return previous_events, current
+
+
 
 @dataclass(frozen=True)
 class _BarCloseResult:
@@ -977,6 +999,7 @@ class LivePipeline:
         on_accepted_trade: Optional[Callable] = None,
         on_candle: Optional[Callable] = None,
         on_analysis: Optional[Callable] = None,
+        on_absorption_state: Optional[Callable] = None,
         on_liquidation: Optional[Callable] = None,
         on_flow_event: Optional[Callable] = None,
         on_webapp_flow_event: Optional[Callable] = None,
@@ -1057,6 +1080,7 @@ class LivePipeline:
         self.on_accepted_trade = on_accepted_trade
         self.on_candle = on_candle
         self.on_analysis = on_analysis
+        self.on_absorption_state = on_absorption_state
         self.on_liquidation = on_liquidation
         self.on_flow_event = on_flow_event
         self.on_webapp_flow_event = on_webapp_flow_event
@@ -1596,10 +1620,12 @@ class LivePipeline:
                 closed_higher = higher_timeframes.process(normalized)
                 self.higher_timeframe_candles.update(closed_higher)
             fp_closed = footprint.process_trade(normalized)
-            prev_abs = absorption.events_detected
-            absorption.observe_trade(normalized)
+            prev_abs, ar = _observe_absorption_state(
+                absorption,
+                normalized,
+                self.on_absorption_state,
+            )
             if self.on_webapp_flow_event is not None and absorption.events_detected > prev_abs:
-                ar = absorption.current()
                 if ar is not None:
                     side = "BUY" if ar.classification == "BUY_ABSORPTION" else "SELL"
                     self.on_webapp_flow_event(PushFlowEvent(
warning: in the working copy of 'Delta_Engine_Pro4web/src/pipeline.py', LF will be replaced by CRLF the next time Git touches it
```

## T2. pipeline.py hunk分類

| Hunk | hunk見出し | 先頭コンテキスト行 | absorption | on_absorption_state | その他 |
|---:|---|---|:---:|:---:|---|
| 1 | `@@ -425,6 +425,7 @@ class ReplayPipeline:` | `         self.on_trade: Optional[Callable] = None` | ○ | ○ | — |
| 2 | `@@ -626,7 +627,11 @@ class ReplayPipeline:` | `                 closed_higher = higher_timeframes.process(normalized)` | ○ | ○ | — |
| 3 | `@@ -781,6 +786,23 @@ def _to_engine_ns(dt: datetime, origin_source_ns: int \| None) -> int:` | `     return _to_source_ns(dt) - origin_source_ns` | ○ | × | — |
| 4 | `@@ -977,6 +999,7 @@ class LivePipeline:` | `         on_accepted_trade: Optional[Callable] = None,` | ○ | ○ | — |
| 5 | `@@ -1057,6 +1080,7 @@ class LivePipeline:` | `         self.on_accepted_trade = on_accepted_trade` | ○ | ○ | — |
| 6 | `@@ -1596,10 +1620,12 @@ class LivePipeline:` | `                 closed_higher = higher_timeframes.process(normalized)` | ○ | ○ | — |

機械走査生出力:

```text
HUNK 1
HEADER=@@ -425,6 +425,7 @@ class ReplayPipeline:
FIRST_CONTEXT=         self.on_trade: Optional[Callable] = None
ABSORPTION=○
ON_ABSORPTION_STATE=○
HUNK 2
HEADER=@@ -626,7 +627,11 @@ class ReplayPipeline:
FIRST_CONTEXT=                 closed_higher = higher_timeframes.process(normalized)
ABSORPTION=○
ON_ABSORPTION_STATE=○
HUNK 3
HEADER=@@ -781,6 +786,23 @@ def _to_engine_ns(dt: datetime, origin_source_ns: int | None) -> int:
FIRST_CONTEXT=     return _to_source_ns(dt) - origin_source_ns
ABSORPTION=○
ON_ABSORPTION_STATE=×
HUNK 4
HEADER=@@ -977,6 +999,7 @@ class LivePipeline:
FIRST_CONTEXT=         on_accepted_trade: Optional[Callable] = None,
ABSORPTION=○
ON_ABSORPTION_STATE=○
HUNK 5
HEADER=@@ -1057,6 +1080,7 @@ class LivePipeline:
FIRST_CONTEXT=         self.on_accepted_trade = on_accepted_trade
ABSORPTION=○
ON_ABSORPTION_STATE=○
HUNK 6
HEADER=@@ -1596,10 +1620,12 @@ class LivePipeline:
FIRST_CONTEXT=                 closed_higher = higher_timeframes.process(normalized)
ABSORPTION=○
ON_ABSORPTION_STATE=○
```

## T3. absorption受け口の所在

### `on_absorption_state` HEAD grep

```text
```

### `on_absorption_state` 作業ツリーgrep

```text
Delta_Engine_Pro4web/src/pipeline.py:428:        self.on_absorption_state: Optional[Callable] = None
Delta_Engine_Pro4web/src/pipeline.py:633:                self.on_absorption_state,
Delta_Engine_Pro4web/src/pipeline.py:1002:        on_absorption_state: Optional[Callable] = None,
Delta_Engine_Pro4web/src/pipeline.py:1083:        self.on_absorption_state = on_absorption_state
Delta_Engine_Pro4web/src/pipeline.py:1626:                self.on_absorption_state,
```

### callback呼出実体

```text
Delta_Engine_Pro4web/src/pipeline.py:789:def _observe_absorption_state(
Delta_Engine_Pro4web/src/pipeline.py:790:    absorption: AbsorptionDetector,
Delta_Engine_Pro4web/src/pipeline.py:791:    trade: Any,
Delta_Engine_Pro4web/src/pipeline.py:792:    on_state: Optional[Callable],
Delta_Engine_Pro4web/src/pipeline.py:793:) -> tuple[int, Optional[Any]]:
Delta_Engine_Pro4web/src/pipeline.py:794:    """Update the tick-driven detector and publish only meaningful UI state changes."""
Delta_Engine_Pro4web/src/pipeline.py:796:    previous = absorption.current()
Delta_Engine_Pro4web/src/pipeline.py:797:    previous_events = absorption.events_detected
Delta_Engine_Pro4web/src/pipeline.py:798:    absorption.observe_trade(trade)
Delta_Engine_Pro4web/src/pipeline.py:799:    current = absorption.current()
Delta_Engine_Pro4web/src/pipeline.py:800:    detected = absorption.events_detected > previous_events
Delta_Engine_Pro4web/src/pipeline.py:801:    if on_state is not None and (detected or current != previous):
Delta_Engine_Pro4web/src/pipeline.py:802:        on_state(trade.event_time, current)
Delta_Engine_Pro4web/src/pipeline.py:803:    return previous_events, current
```

### `absorption_window_sec` HEAD grep

```text
HEAD:Delta_Engine_Pro4web/src/pipeline.py:359:        absorption_window_sec: int = 10,
HEAD:Delta_Engine_Pro4web/src/pipeline.py:403:        self.absorption_window_sec = absorption_window_sec
HEAD:Delta_Engine_Pro4web/src/pipeline.py:475:            absorption_window_sec=abs_.window_sec,
HEAD:Delta_Engine_Pro4web/src/pipeline.py:532:            window_sec=self.absorption_window_sec,
HEAD:Delta_Engine_Pro4web/src/pipeline.py:963:        absorption_window_sec: int = 10,
HEAD:Delta_Engine_Pro4web/src/pipeline.py:1039:        self.absorption_window_sec = absorption_window_sec
HEAD:Delta_Engine_Pro4web/src/pipeline.py:1134:            absorption_window_sec=abs_.window_sec,
HEAD:Delta_Engine_Pro4web/src/pipeline.py:1442:            window_sec=self.absorption_window_sec,
HEAD:Delta_Engine_Pro4web/src/pipeline.py:1612:                        detail=f"window_sec={self.absorption_window_sec}",
```

### `absorption_window_sec` 作業ツリーgrep

```text
Delta_Engine_Pro4web/src/pipeline.py:359:        absorption_window_sec: int = 10,
Delta_Engine_Pro4web/src/pipeline.py:403:        self.absorption_window_sec = absorption_window_sec
Delta_Engine_Pro4web/src/pipeline.py:476:            absorption_window_sec=abs_.window_sec,
Delta_Engine_Pro4web/src/pipeline.py:533:            window_sec=self.absorption_window_sec,
Delta_Engine_Pro4web/src/pipeline.py:985:        absorption_window_sec: int = 10,
Delta_Engine_Pro4web/src/pipeline.py:1062:        self.absorption_window_sec = absorption_window_sec
Delta_Engine_Pro4web/src/pipeline.py:1158:            absorption_window_sec=abs_.window_sec,
Delta_Engine_Pro4web/src/pipeline.py:1466:            window_sec=self.absorption_window_sec,
Delta_Engine_Pro4web/src/pipeline.py:1638:                        detail=f"window_sec={self.absorption_window_sec}",
```

## T4. pipeline.py差分追加行のfloat走査

```text
DIFF_ADDED_FLOAT_HIT_COUNT=0
```

## T5. time_sales.js 全差分

```text
diff --git a/Delta_Engine_Pro4web/webapp/static/time_sales.js b/Delta_Engine_Pro4web/webapp/static/time_sales.js
index 9afb17c..6f067f7 100644
--- a/Delta_Engine_Pro4web/webapp/static/time_sales.js
+++ b/Delta_Engine_Pro4web/webapp/static/time_sales.js
@@ -218,6 +218,7 @@
       this.filterElement = config.filterElement;
       this.onSelect = config.onSelect || function () {};
       this.onStreamRestart = config.onStreamRestart || function () {};
+      this.onAcceptedTrades = config.onAcceptedTrades || function () {};
       this.store = new TapeStore({ capacity: config.capacity || DEFAULT_CAPACITY });
       this.poolSize = clamp(Math.round(Number(config.poolSize) || DEFAULT_POOL_SIZE), 20, 40);
       this.rowHeight = Math.max(28, Math.round(Number(config.rowHeight) || 28));
@@ -297,7 +298,10 @@
 
     ingestBatch(payload, symbol) {
       const atTop = !this.viewport || this.viewport.scrollTop <= 2;
+      const before = new Set(this.store.keys);
       const result = this.store.ingestBatch(payload, symbol);
+      const accepted = this.store.trades.filter(trade => !before.has(trade.key));
+      if (accepted.length) { try { this.onAcceptedTrades(accepted, result); } catch (_) {} }
       if (result.restart) this.onStreamRestart(this.store.streamId);
       if (atTop && this.viewport) this.viewport.scrollTop = 0;
       this.render();
@@ -427,3 +431,5 @@
     p95,
   };
 });
+
+
warning: in the working copy of 'Delta_Engine_Pro4web/webapp/static/time_sales.js', LF will be replaced by CRLF the next time Git touches it
```

### 差分追加行の文字列走査

```text
ABSORPTION=×
BOOK_IDENTIFIERS=×
TAPE=×
```

### 差分追加行

```text
+      this.onAcceptedTrades = config.onAcceptedTrades || function () {};
+      const before = new Set(this.store.keys);
+      const accepted = this.store.trades.filter(trade => !before.has(trade.key));
+      if (accepted.length) { try { this.onAcceptedTrades(accepted, result); } catch (_) {} }
+
+
```

### 主要シンボル行番号

```text
Delta_Engine_Pro4web/webapp/static/time_sales.js:221:      this.onAcceptedTrades = config.onAcceptedTrades || function () {};
Delta_Engine_Pro4web/webapp/static/time_sales.js:303:      const accepted = this.store.trades.filter(trade => !before.has(trade.key));
Delta_Engine_Pro4web/webapp/static/time_sales.js:304:      if (accepted.length) { try { this.onAcceptedTrades(accepted, result); } catch (_) {} }
```

## 末尾git生出力

### `git rev-parse HEAD`

```text
3be272cbce32464b45f1e952d692cc5ce61703c3
```

### `git status --porcelain`

```text
 M ArchitectureRepository/00_Master/ORDER_BOOK_HEATMAP_IMPLEMENTATION_INSTRUCTION_V1_20260729.md
 M ArchitectureRepository/00_Master/ORDER_BOOK_HEATMAP_PHASE_H0_CHECKPOINT_20260729.md
 M ArchitectureRepository/00_Master/PROJECT_MEMORY.md
 M ArchitectureRepository/30_Modules/WebApp/Specifications/WebSocketPayload_Spec_v1.md
 M Delta_Engine_Pro4web/docker-compose.yml
 M Delta_Engine_Pro4web/src/pipeline.py
 M Delta_Engine_Pro4web/webapp/main.py
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
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Commit1_HeatmapCore_Completion_Report_20260731.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Commit2_BookIdentity_Completion_Report_20260731.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Commit2_Preflight_PushBroker_Diff_Materials_20260731.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Commit2_Stopped_FloatScan_Report_20260731.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Stage1_Investigation_Report_20260731.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Stage2_Preflight_Repository_Hygiene_Materials_20260731.md
?? ArchitectureRepository/00_Master/HEATMAP/Roadmap_Heatmap_Render_to_Dynamic_v1.md
?? ArchitectureRepository/00_Master/HEATMAP/p21_evidence/
?? ArchitectureRepository/00_Master/HEATMAP/tools_p22/
?? ArchitectureRepository/00_Master/HEATMAP/worktree_backup_pre_p21_20260730.patch
?? ArchitectureRepository/00_Master/HEATMAP/worktree_status_pre_p21_20260730.txt
?? ArchitectureRepository/00_Master/HEATMAP_Instruction_v1.5.md
?? ArchitectureRepository/00_Master/HOOK_STAGE2C4_CHECKPOINT_20260731.md
?? "ArchitectureRepository/00_Master/Heatmap_Handover_20260730 (1).md"
?? ArchitectureRepository/00_Master/Heatmap_Handover_20260730.md
?? ArchitectureRepository/00_Master/INSTR_Commit1_HeatmapCore_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Commit2_Preflight_PushBroker_v1.0.md
?? "ArchitectureRepository/00_Master/INSTR_Commit2_PushBroker_BookIdentity_v1.0 (1).md"
?? ArchitectureRepository/00_Master/INSTR_Commit2_PushBroker_BookIdentity_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Commit2_PushBroker_BookIdentity_v1.1.md
?? ArchitectureRepository/00_Master/INSTR_Commit3_Preflight_Pipeline_TimeSales_v1.0.md
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
