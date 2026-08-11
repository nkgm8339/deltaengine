# 第二コミット着手前 push_broker.py 差分材料

- Version: 1.0
- 採取日: 2026-07-31
- 対象: DeltaEngine05M
- HEAD: `6c5a8b257ff3063d061673588696246be8cd560d`

## T1. `push_broker.py` 全差分生出力

```text
diff --git a/Delta_Engine_Pro4web/webapp/push_broker.py b/Delta_Engine_Pro4web/webapp/push_broker.py
index 2b06939..63ba8b5 100644
--- a/Delta_Engine_Pro4web/webapp/push_broker.py
+++ b/Delta_Engine_Pro4web/webapp/push_broker.py
@@ -7,9 +7,10 @@ from __future__ import annotations
 import asyncio
 import json
 from dataclasses import dataclass, field
-from datetime import datetime, timezone
+from datetime import datetime, timedelta, timezone
 from decimal import Decimal
 from typing import Any, Awaitable, Callable, Optional
+from uuid import uuid4
 
 from webapp.book_projection import BookProjection, FAIL_CLOSED_STATES, SYNCED
 from webapp.tape import TapeBatch
@@ -145,14 +146,18 @@ class PushBroker:
         symbol: str,
         depth_levels: int = 15,
         live_dom_depth_levels: int = 50,
+        persistent_writer=None,
     ) -> None:
         self.symbol = symbol
+        self.persistent_writer = persistent_writer
         self.depth_levels = depth_levels
         self.live_dom_depth_levels = live_dom_depth_levels
         self._clients: set[Any] = set()
         self._lock = asyncio.Lock()
         self._latest_hfm_message: dict | None = None
         self._latest_book_message: dict | None = None
+        self._latest_absorption_message: dict | None = None
+        self.book_stream_id = str(uuid4())
         self.book_updates_broadcast = 0
         self.tape_batches_broadcast = 0
         self.tape_trades_broadcast = 0
@@ -162,7 +167,8 @@ class PushBroker:
             self._clients.add(ws)
             latest_hfm = self._latest_hfm_message
             latest_book = self._latest_book_message
-        for latest in (latest_hfm, latest_book):
+            latest_absorption = self._latest_absorption_message
+        for latest in (latest_hfm, latest_book, latest_absorption):
             if latest is None:
                 continue
             try:
@@ -252,6 +258,7 @@ class PushBroker:
             or projection.spread is None
         ):
             raise ValueError("SYNCED BOOK_UPDATE requires best bid, best ask, and spread")
+        book_sequence = self.book_updates_broadcast + 1
         bids = projection.bids if synced else ()
         asks = projection.asks if synced else ()
         message = envelope(
@@ -259,6 +266,8 @@ class PushBroker:
             projection.projection_time,
             self.symbol,
             {
+                "book_stream_id": self.book_stream_id,
+                "book_sequence": book_sequence,
                 "event_time": (
                     projection.event_time.astimezone(timezone.utc).isoformat()
                     if projection.event_time is not None else None
@@ -284,7 +293,9 @@ class PushBroker:
             },
         )
         self._latest_book_message = message
-        self.book_updates_broadcast += 1
+        self.book_updates_broadcast = book_sequence
+        if self.persistent_writer is not None:
+            self.persistent_writer.append(message["payload"])
         await self._broadcast(message)
 
     async def on_candle(
@@ -373,6 +384,39 @@ class PushBroker:
             ],
         }))
 
+    async def on_absorption_state(
+        self,
+        event_time: datetime,
+        result: Any | None,
+        *,
+        window_sec: int,
+    ) -> None:
+        """Broadcast the tick-time absorption state and cache it for late clients."""
+
+        if window_sec <= 0:
+            raise ValueError("window_sec must be > 0")
+        classification = None if result is None else str(result.classification)
+        if classification not in {None, "BUY_ABSORPTION", "SELL_ABSORPTION"}:
+            raise ValueError(f"unsupported absorption classification: {classification}")
+        message = envelope("ABSORPTION_STATE", event_time, self.symbol, {
+            "active": result is not None,
+            "classification": classification,
+            "strength": None if result is None else d2s(result.strength),
+            "price_low": None if result is None else d2s(result.price_low),
+            "price_high": None if result is None else d2s(result.price_high),
+            "observed_at": event_time.astimezone(timezone.utc).isoformat(),
+            "expires_at": (
+                None
+                if result is None
+                else (event_time + timedelta(seconds=window_sec))
+                .astimezone(timezone.utc)
+                .isoformat()
+            ),
+            "window_sec": window_sec,
+        })
+        self._latest_absorption_message = message
+        await self._broadcast(message)
+
     async def on_flow_event(self, ev) -> None:
         category = str(getattr(ev, "category", getattr(ev, "kind", "UNKNOWN"))).upper()
         detector = str(getattr(ev, "detector", getattr(ev, "kind", category)))
warning: in the working copy of 'Delta_Engine_Pro4web/webapp/push_broker.py', LF will be replaced by CRLF the next time Git touches it
```

## T2. hunk単位の機械分類

| Hunk | hunk見出し | 先頭コンテキスト行 | book識別子 | absorption | その他 |
|---:|---|---|:---:|:---:|---|
| 1 | `@@ -7,9 +7,10 @@ from __future__ import annotations` | ` import asyncio` | × | × | `uuid4` — `Delta_Engine_Pro4web/webapp/push_broker.py:13` |
| 2 | `@@ -145,14 +146,18 @@ class PushBroker:` | `         symbol: str,` | ○ | ○ | — |
| 3 | `@@ -162,7 +167,8 @@ class PushBroker:` | `             self._clients.add(ws)` | × | ○ | — |
| 4 | `@@ -252,6 +258,7 @@ class PushBroker:` | `             or projection.spread is None` | ○ | × | — |
| 5 | `@@ -259,6 +266,8 @@ class PushBroker:` | `             projection.projection_time,` | ○ | × | — |
| 6 | `@@ -284,7 +293,9 @@ class PushBroker:` | `             },` | ○ | × | — |
| 7 | `@@ -373,6 +384,39 @@ class PushBroker:` | `             ],` | × | ○ | — |

機械走査生出力:

```text
HUNK 1
HEADER=@@ -7,9 +7,10 @@ from __future__ import annotations
FIRST_CONTEXT= import asyncio
BOOK=×
ABSORPTION=×
OTHER=uuid4 @ Delta_Engine_Pro4web/webapp/push_broker.py:13
HUNK 2
HEADER=@@ -145,14 +146,18 @@ class PushBroker:
FIRST_CONTEXT=         symbol: str,
BOOK=○
ABSORPTION=○
HUNK 3
HEADER=@@ -162,7 +167,8 @@ class PushBroker:
FIRST_CONTEXT=             self._clients.add(ws)
BOOK=×
ABSORPTION=○
HUNK 4
HEADER=@@ -252,6 +258,7 @@ class PushBroker:
FIRST_CONTEXT=             or projection.spread is None
BOOK=○
ABSORPTION=×
HUNK 5
HEADER=@@ -259,6 +266,8 @@ class PushBroker:
FIRST_CONTEXT=             projection.projection_time,
BOOK=○
ABSORPTION=×
HUNK 6
HEADER=@@ -284,7 +293,9 @@ class PushBroker:
FIRST_CONTEXT=             },
BOOK=○
ABSORPTION=×
HUNK 7
HEADER=@@ -373,6 +384,39 @@ class PushBroker:
FIRST_CONTEXT=             ],
BOOK=×
ABSORPTION=○
```

## T3. `on_absorption_state`のHEAD／作業ツリーgrep

HEAD:

```text
```

作業ツリー:

```text
Delta_Engine_Pro4web/webapp/push_broker.py:387:    async def on_absorption_state(
```

追加を含む差分hunk:

```text
@@ -373,6 +384,39 @@ class PushBroker:
             ],
         }))
 
+    async def on_absorption_state(
```

## T4. book識別子生成・付与箇所

作業ツリー:

```text
Delta_Engine_Pro4web/webapp/push_broker.py:141:class PushBroker:
Delta_Engine_Pro4web/webapp/push_broker.py:144:    def __init__(
Delta_Engine_Pro4web/webapp/push_broker.py:160:        self.book_stream_id = str(uuid4())
Delta_Engine_Pro4web/webapp/push_broker.py:250:    async def on_book_update(self, projection: BookProjection) -> None:
Delta_Engine_Pro4web/webapp/push_broker.py:261:        book_sequence = self.book_updates_broadcast + 1
Delta_Engine_Pro4web/webapp/push_broker.py:269:                "book_stream_id": self.book_stream_id,
Delta_Engine_Pro4web/webapp/push_broker.py:270:                "book_sequence": book_sequence,
Delta_Engine_Pro4web/webapp/push_broker.py:296:        self.book_updates_broadcast = book_sequence
```

HEAD grep:

```text
```

## 末尾git生出力

### `git rev-parse HEAD`

```text
6c5a8b257ff3063d061673588696246be8cd560d
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
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Commit1_HeatmapCore_Completion_Report_20260731.md
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
