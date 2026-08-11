# PHEMEX仕様書 v1.3 修正完了報告書

**文書ID:** DE05M-PHEMEX-REPORT-013  
**版:** 1.0  
**作成日:** 2026-08-03  
**対象:** `PHEMEX_INTEGRATION_DETAILED_SPEC_20260802.md`  
**実施範囲:** 文書修正のみ  

---

## 1. 結果

`PHEMEX_INTEGRATION_DETAILED_SPEC_20260802.md`を`v1.2-draft`から`v1.3-draft`へ改訂した。
修正指示書のEdit 1からEdit 10はすべてanchor不一致なく適用済みである。

production code、test、設定file、DBは変更していない。git add、commit、push、branch操作も
実行していない。

---

## 2. 適用前検証

```text
SHA-256: edb72e001ef31060b5379c6d5d54463584007ea34f74cf6d3c90f2bdd42ffc7b
期待値との一致: YES
bytes: 76,228
LF: 2,245
CR: 0
末尾LF: あり
encoding: UTF-8
```

基準SHA-256と完全一致したため修正を開始した。

---

## 3. Edit適用結果

| Edit | 内容 | 結果 |
|---:|---|---|
| 1 | 版番号を1.3-draftへ更新 | 適用済み |
| 2 | 改訂履歴へ1.3-draftを追加 | 適用済み |
| 3 | fixture pathを一本化 | 適用済み |
| 4 | fixture/default assertion注記を追加 | 適用済み |
| 5 | Phase 0へdefault test棚卸しを追加 | 適用済み |
| 6 | snapshot待機buffer暫定値を追加 | 適用済み |
| 7 | MIXED_EXCHANGE_CONFIG適用条件を限定 | 適用済み |
| 8 | §17設定表へbuffer値を追加 | 適用済み |
| 9 | §20エラー条件をactive PHEMEXへ限定 | 適用済み |
| 10 | §28へPhase 8見直し条件を追加 | 適用済み |

---

## 4. grep検証

```text
1.3-draft: 2件
1.2-draft: 1件
Delta_Engine_Pro4web/tests/fixtures/phemex/**: 0件
tests/fixtures/phemex: 1件
pre_snapshot_max_messages: 1件
resolved active config: 3件
tests/test_config.py:99: 1件
```

すべて修正指示書の期待値と一致した。

Markdown code fenceは98個で、開始・終了の対応は正常である。

---

## 5. 適用後検証

```text
SHA-256: bd965d88d6c649df51f4e34ea1e1968808b91c830a5b4d52d8bbb37939a9a7ba
expected SHA-256との一致: YES
bytes: 79,629
expected bytesとの一致: YES
LF/行数: 2,292
expected linesとの一致: YES
CR: 0
末尾LF: あり
encoding: UTF-8
```

Claudeドライランの期待値と完全一致した。

---

## 6. 変更file

今回内容を変更したfile:

```text
ArchitectureRepository/00_Master/PHEMEX_INTEGRATION_DETAILED_SPEC_20260802.md
```

本完了報告のため追加したfile:

```text
ArchitectureRepository/00_Master/PHEMEX_SPEC_V1.3_REVISION_COMPLETION_REPORT_20260803.md
```

作業ツリーには本作業開始前から多数のmodified/untracked entryが存在する。それらへは触れていない。

---

## 7. git status --porcelain

以下は仕様書改訂直後、完了報告書追加前に取得した全文である。本報告書追加後は、末尾に
`?? ArchitectureRepository/00_Master/PHEMEX_SPEC_V1.3_REVISION_COMPLETION_REPORT_20260803.md`
が追加される。

```text
 M ArchitectureRepository/00_Master/ORDER_BOOK_HEATMAP_IMPLEMENTATION_INSTRUCTION_V1_20260729.md
 M ArchitectureRepository/00_Master/ORDER_BOOK_HEATMAP_PHASE_H0_CHECKPOINT_20260729.md
 M ArchitectureRepository/00_Master/PROJECT_MEMORY.md
 M ArchitectureRepository/30_Modules/WebApp/Specifications/WebSocketPayload_Spec_v1.md
 M Delta_Engine_Pro4web/docker-compose.yml
 M Delta_Engine_Pro4web/tests/webapp/test_footprint_chart_ui.py
 M Delta_Engine_Pro4web/webapp/main.py
 M Delta_Engine_Pro4web/webapp/push_broker.py
 M Delta_Engine_Pro4web/webapp/static/footprint_canvas.js
 M Delta_Engine_Pro4web/webapp/static/index.html
 M Delta_Engine_Pro4web/webapp/static/time_sales.js
?? ArchitectureRepository/00_Master/ABSORPTION_REALTIME_DISPLAY_FIX_CHECKPOINT_20260731.md
?? "ArchitectureRepository/00_Master/AI\343\202\263\343\203\241\343\203\263\343\203\210/"
?? ArchitectureRepository/00_Master/BINANCE_SPOT_REFERENCE_PRICE_CHECKPOINT_20260802.md
?? ArchitectureRepository/00_Master/CHECK_Stage2_Visual_Confirmation_v1.0.md
?? ArchitectureRepository/00_Master/DRIVE_CORE_BACKUP_CHECKPOINT_20260802.md
?? ArchitectureRepository/00_Master/DRIVE_CORE_BACKUP_RESTORE_20260802.md
?? ArchitectureRepository/00_Master/FOOTPRINT_POC_RESTORATION_CHECKPOINT_20260801.md
?? ArchitectureRepository/00_Master/HEATMAP/Approval_P22_Task1_Go_Task2.md
?? ArchitectureRepository/00_Master/HEATMAP/Approval_P22_Task2_Go_Task3.md
?? ArchitectureRepository/00_Master/HEATMAP/Approval_P22_Task3_Go_Task4.md
?? ArchitectureRepository/00_Master/HEATMAP/Approval_P22_Task3_PreReport_Reply_v1.md
?? ArchitectureRepository/00_Master/HEATMAP/INSTR_Stage2_Task2_Commit7_Coherent_v1.1_20260801.md
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
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Commit4_PersistentDepthWriter_Completion_Report_20260731.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Commit5_TimeSales_SourceHygiene_Completion_Report_20260731.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Commit6_FrameSource_Completion_Report_20260731.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Stage1_Investigation_Report_20260731.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Stage2_Preflight_Repository_Hygiene_Materials_20260731.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Stage2_Task1_AdapterPath_Investigation_20260731.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Stage2_Task1_BuildBookProjection_Dependency_Investigation_20260731.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Stage2_Task1_FrameSource_Implementation_Report_20260731.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Stage2_Task1_FrameSource_Investigation_20260731.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Stage2_Task2_Anchor_Materials_20260801.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Stage2_Task2_Commit7_Instruction_Review_20260801.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Stage2_Task2_Live_Supply_Runtime_Test_Report_20260801.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Stage2_Task2_Stage1_Investigation_Report_20260801.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Stage2_Task2_Stage1b_Health_Probe_Investigation_Report_20260801.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Stage2_Task2_Stage1c_FailFast_Impact_Investigation_Report_20260801.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Stage2_Task2_SupplyPath_Gate_Implementation_Report_20260801.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Stage2_Task2_SupplyPath_Gate_Investigation_Report_20260731.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Stage2_Task2_Web_Handoff_Recovery_and_Completion_20260801.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Stage2_Task2_v3.2_Implementation_Stop_Report_20260801.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Stage2_Task2_v3.3_Implementation_Report_20260801.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Stage2_Task2_v3.3_Verification_Package_20260801.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Stage2_Task3_Commit_Report_20260801.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Stage2_Task3_FrameBudget_Implementation_Report_20260801.md
?? ArchitectureRepository/00_Master/HEATMAP/Roadmap_Heatmap_Render_to_Dynamic_v1.md
?? ArchitectureRepository/00_Master/HEATMAP/p21_evidence/
?? ArchitectureRepository/00_Master/HEATMAP/tools_p22/
?? ArchitectureRepository/00_Master/HEATMAP/worktree_backup_pre_p21_20260730.patch
?? ArchitectureRepository/00_Master/HEATMAP/worktree_status_pre_p21_20260730.txt
?? ArchitectureRepository/00_Master/HEATMAP_Instruction_v1.5.md
?? ArchitectureRepository/00_Master/HOOK_STAGE2C4_CHECKPOINT_20260731.md
?? ArchitectureRepository/00_Master/Handoff_Heatmap_Phase2-3_Stage2_Task2_to_Task3_20260801.md
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
?? ArchitectureRepository/00_Master/INSTR_Commit5_TimeSales_and_ComposeCleanup_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Commit6_FrameSource_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Stage2_Roadmap_and_Task1_Investigation_v1.0.md
?? "ArchitectureRepository/00_Master/INSTR_Stage2_Task1_DesignFinalization_Investigation_v1.0 (1).md"
?? ArchitectureRepository/00_Master/INSTR_Stage2_Task1_DesignFinalization_Investigation_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Stage2_Task1_FinalDesignMaterial_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Stage2_Task1_FrameSource_Implementation_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Stage2_Task2_AnchorMaterial_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Stage2_Task2_Implementation_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Stage2_Task2_Recovery_and_Completion_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Stage2_Task2_SupplyPath_Investigation_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Stage2_Task3_Commit_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Stage2_Task3_FrameBudget_Stage1_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Stage2_Task3_FrameBudget_Stage2_v1.0.md
?? ArchitectureRepository/00_Master/Instruction_Phase2-2_Renderer_v1.md
?? ArchitectureRepository/00_Master/PHEMEX_INTEGRATION_DETAILED_SPEC_20260802.md
?? ArchitectureRepository/00_Master/REALTIME_UI_FRESHNESS_FIX_CHECKPOINT_20260802.md
?? ArchitectureRepository/00_Master/SCHEDULED_TASK_RESUME_FIX_CHECKPOINT_20260731.md
?? ArchitectureRepository/00_Master/VWAP_CHART_RELATED_MODULE_INVENTORY_20260729.md
?? ArchitectureRepository/00_Master/VWAP_INVESTIGATION_20260729/
?? "ArchitectureRepository/00_Master/\343\203\210\343\202\252\343\202\254\343\203\274\344\275\234\346\210\220\346\214\207\347\244\272\346\233\270\347\276\244/DeltaEngine_\347\265\214\347\267\257\345\240\261\345\221\212_\347\254\2541\346\234\237-\347\254\2544\346\234\237_20260727.md"
?? "ArchitectureRepository/00_Master/\343\203\210\343\202\252\343\202\254\343\203\274\344\275\234\346\210\220\346\214\207\347\244\272\346\233\270\347\276\244/HOOK_AND_LEGACY_STRATEGY_INVENTORY_20260727.md"
?? "ArchitectureRepository/00_Master/\343\203\210\343\202\252\343\202\254\343\203\274\344\275\234\346\210\220\346\214\207\347\244\272\346\233\270\347\276\244/HOOK_AND_STRATEGY_CONTENT_GUIDE_20260727.md"
?? "ArchitectureRepository/00_Master/\343\203\210\343\202\252\343\202\254\343\203\274\344\275\234\346\210\220\346\214\207\347\244\272\346\233\270\347\276\244/HOOK_STAGE2C1_CONTAINER_RESTART_20260730.md"
?? "ArchitectureRepository/00_Master/\343\203\210\343\202\252\343\202\254\343\203\274\344\275\234\346\210\220\346\214\207\347\244\272\346\233\270\347\276\244/HOOK_STAGE2C1_GATE_DATA_20260729.md"
?? "ArchitectureRepository/00_Master/\345\256\237\351\201\213\347\224\250/"
?? "ArchitectureRepository/00_Master/\346\214\207\347\244\272\346\233\270_STAGE2C2_Hook\350\274\203\346\255\243_\345\210\206\345\270\203\351\233\206\350\250\210_v1.md"
?? Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/
?? Delta_Engine_Pro4web/tests/webapp/test_market_freshness_ui.py
?? Delta_Engine_Pro4web/tests/webapp/test_spot_reference_price.py
?? Delta_Engine_Pro4web/webapp/spot_price_stream.py
?? Delta_Engine_Pro4web/webapp/static/market_freshness.js
?? pytest-vwap-ui-elevated/
?? vwap-audit.duckdb
?? vwap_first100.jsonl
?? vwap_restore_ws_capture.jsonl
?? vwap_ws_capture.jsonl
```

---

## 8. Git操作

```text
git add: 未実行
git commit: 未実行
git push: 未実行
branch操作: 未実行
```
