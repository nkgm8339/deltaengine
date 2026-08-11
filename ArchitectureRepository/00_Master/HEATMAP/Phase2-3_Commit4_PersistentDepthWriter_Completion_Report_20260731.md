# Phase 2-3 第四コミット Persistent depth writer 完了報告

- 実施日: 2026-07-31
- 実施前HEAD: `052d6e3ba347f576db51496ae48b3e4ea0fd3398`
- 実施後HEAD: `f58f584ee363117356ff37062fdd087e58a21166`
- 結果: 完了
- commit対象: `Delta_Engine_Pro4web/webapp/main.py` の1パスのみ
- 対象外: `Delta_Engine_Pro4web/docker-compose.yml`、`Delta_Engine_Pro4web/webapp/static/time_sales.js`、その他の作業ツリー変更

## S1. main.py 差分追加行の float( 走査

実行対象:

```powershell
git -C <root> diff HEAD -- Delta_Engine_Pro4web/webapp/main.py | grep -nE "^\+" | grep "float("
```

生出力:

```text
DIFF_ADDED_FLOAT_HIT_COUNT=0
```

補助走査の生出力:

```text
MAIN_DIFF_ABSORPTION_HIT_COUNT=0
+from webapp.persistent_depth_writer import PersistentDepthWriter
+def _build_broker(config, persistent_writer=None) -> PushBroker:
+        persistent_writer=persistent_writer,
+    persistent_enabled = os.getenv("PERSISTENT_DEPTH_HISTORY_ENABLED", "false").lower() == "true"
+    persistent_writer = PersistentDepthWriter(os.getenv("PERSISTENT_DEPTH_HISTORY_ROOT", "data_05M/depth_history"), config.market.symbol) if persistent_enabled else None
+    broker = _build_broker(config, persistent_writer)
+        if persistent_writer is not None:
+                await asyncio.to_thread(persistent_writer.close)
MAIN_DIFF_PERSISTENT_HIT_COUNT=8
```

## S3. commit前staging検証

### git diff --cached --name-only

```text
Delta_Engine_Pro4web/webapp/main.py
CACHED_PATH_COUNT=1
```

### staged main.py on_absorption_state grep

```text
MAIN_STAGED_ABSORPTION_HIT_COUNT=0
```

### staged main.py persistent grep

```text
+from webapp.persistent_depth_writer import PersistentDepthWriter
+def _build_broker(config, persistent_writer=None) -> PushBroker:
+        persistent_writer=persistent_writer,
+    persistent_enabled = os.getenv("PERSISTENT_DEPTH_HISTORY_ENABLED", "false").lower() == "true"
+    persistent_writer = PersistentDepthWriter(os.getenv("PERSISTENT_DEPTH_HISTORY_ROOT", "data_05M/depth_history"), config.market.symbol) if persistent_enabled else None
+    broker = _build_broker(config, persistent_writer)
+        if persistent_writer is not None:
+                await asyncio.to_thread(persistent_writer.close)
MAIN_STAGED_PERSISTENT_HIT_COUNT=8
S3_VALID=True
```

## S4. commit

固定commitメッセージ:

```text
feat(webapp): add optional persistent depth history writer

Env-gated (PERSISTENT_DEPTH_HISTORY_ENABLED, default false) writer wired
through PushBroker and closed on lifespan shutdown. No-op unless enabled;
follows ADR-011 full-capture principle.
```

commit生出力:

```text
[feature/footprint-dom-tape f58f584] feat(webapp): add optional persistent depth history writer
 1 file changed, 9 insertions(+), 2 deletions(-)
```

## S5. commit後証跡

### git show --stat HEAD

```text
commit f58f584ee363117356ff37062fdd087e58a21166
Author: unknown <ksckk0126@gmailcom>
Date:   Fri Jul 31 21:20:38 2026 +0900

    feat(webapp): add optional persistent depth history writer
    
    Env-gated (PERSISTENT_DEPTH_HISTORY_ENABLED, default false) writer wired
    through PushBroker and closed on lifespan shutdown. No-op unless enabled;
    follows ADR-011 full-capture principle.

 Delta_Engine_Pro4web/webapp/main.py | 11 +++++++++--
 1 file changed, 9 insertions(+), 2 deletions(-)
```

### git rev-parse HEAD

```text
f58f584ee363117356ff37062fdd087e58a21166
```

### git status --porcelain

```text
 M ArchitectureRepository/00_Master/ORDER_BOOK_HEATMAP_IMPLEMENTATION_INSTRUCTION_V1_20260729.md
 M ArchitectureRepository/00_Master/ORDER_BOOK_HEATMAP_PHASE_H0_CHECKPOINT_20260729.md
 M ArchitectureRepository/00_Master/PROJECT_MEMORY.md
 M ArchitectureRepository/30_Modules/WebApp/Specifications/WebSocketPayload_Spec_v1.md
 M Delta_Engine_Pro4web/docker-compose.yml
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
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Commit3_AbsorptionRealtime_Completion_Report_20260731.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Commit3_Preflight_Pipeline_TimeSales_Materials_20260731.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Commit3_TimeSales_Ownership_Materials_20260731.md
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
?? ArchitectureRepository/00_Master/INSTR_Commit3_AbsorptionRealtime_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Commit3_Preflight_AbsorptionTest_Wiring_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Commit3_Preflight_Pipeline_TimeSales_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Commit4_PersistentWriter_v1.0.md
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
?? pytest-vwap-ui-elevated/
?? vwap-audit.duckdb
?? vwap_first100.jsonl
?? vwap_restore_ws_capture.jsonl
?? vwap_ws_capture.jsonl
```

### git diff --cached --name-only

```text
CACHED_PATH_COUNT=0
```

対象ソースの最終status:

```text
 M Delta_Engine_Pro4web/docker-compose.yml
 M Delta_Engine_Pro4web/webapp/static/time_sales.js
```

`Delta_Engine_Pro4web/webapp/main.py` はstatusから消えている。

## S6. pytest

実行コマンド:

```powershell
cd Delta_Engine_Pro4web
python -m pytest -q -p no:cacheprovider
```

FAILED行とサマリの生出力:

```text
FAILED tests/webapp/test_dom_tape_fusion_ui.py::test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation
1 failed, 773 passed, 1 skipped in 115.60s (0:01:55)
```

failureは既知の `tests/webapp/test_dom_tape_fusion_ui.py::test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation` 1件。新規failは0件。

## main.py commit後SHA-256

```text
E4D9A6AEC7F1A515141BAFD7D880848A9FF7C7E3D16B5D695B6A8DB9BE3016A4  Delta_Engine_Pro4web/webapp/main.py
```

## 次のアクション案（未実行）

統括による第四コミットの検算後、`time_sales.js` のDOM Trade Pulse片翼是正（第五コミット）および `docker-compose.yml` 空行の扱いに関する指示を待つ。これらには着手していない。
