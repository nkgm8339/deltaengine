# Order Book Heatmap Phase H0 baseline audit

監査時刻: 2026-07-29 05:33 JST  
branch: `feature/footprint-dom-tape`  
HEAD: `92ee4eff823ba31e84f7fc0af197d39b877ec236`  
判定: **AUDIT PASS／baseline commitは明示承認待ち**

## 1. 結論

Heatmap source実装前のcurrent stateをread-only監査した。

- WebApp: **122 passed**
- repository全体: **664 passed, 1 skipped**
- 実Edge: panel overlap 0、horizontal overflow 0、page／console error 0
- Heatmap source／DOM: 未実装、baseline期待値どおり
- dirty entry: 本報告追加後73件
- primary baseline commit候補: **57 file**
- runtime／measurement artifact除外: **13 file**
- 別topic文書: **3 fileを別commit候補として保留**
- access denied directory: broad stage禁止、明示除外

GO-H0のaudit／test／geometry保存はPASSである。
次の操作は57 fileだけをexact pathでstageし、restore point commitを作ることである。
commitはまだ実施していない。

---

## 2. 現在の復元基準

### 2.1 Automated test

| scope | result |
|---|---|
| WebApp | `122 passed in 8.72s` |
| repository | `664 passed, 1 skipped in 34.08s` |
| failure／error | 0 |
| `git diff --check` | error 0、line-ending warningのみ |

### 2.2 実Edge 1280×900／DPR 1

| element | geometry |
|---|---|
| topbar | x10／y10／1260×62 |
| completed three-stage panel | x10／y84／1010×552 |
| three-stage chart Canvas | x15／y239／658×392 |
| main | x10／y648／1010×552 |
| Footprint center | x10／y648／770×552 |
| Footprint Canvas | x11／y683／768×467 |
| Time & Sales | x788／y648／232×552 |
| lower FLOW section | x10／y1212／1260×388 |
| FLOW EVENTS | 1260×198 |
| Absorption | 412×178 |
| Imbalance | 412×178 |
| Alerts | 412×178 |

保護metric:

- three-stage→main gap: 12px
- main→lower indicators gap: 12px
- overlap area: 0
- horizontal overflow: 0
- page scroll height: 1610px
- Tape row: 14px font／28px height
- Footprint normal primary cell: 14px
- toast: right 14px／bottom 14px／transform none
- Heatmap element: absent
- page error: 0
- console error: 0

Heatmap実装後はこの表との差分を測定し、保護対象の変更をfailureとする。

---

## 3. Primary baseline commit候補 — 57 file

### 3.1 Documents／specification — 27

```text
ArchitectureRepository/00_Master/ALERT_TOAST_POSITION_CHECKPOINT_20260729.md
ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_FUSION_IMPLEMENTATION_INSTRUCTION_V2_20260728.md
ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_FUSION_PREIMPLEMENTATION_AMENDMENT_V2_1_20260728.md
ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_LOWER_INDICATOR_LAYOUT_CHECKPOINT_20260729.md
ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_OPERATIONAL_REMEDIATION_CHECKPOINT_20260728.md
ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_OPERATIONAL_REMEDIATION_REPORT_20260728.md
ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_PHASE0C_STORAGE_SIZING_CHECKPOINT_20260728.md
ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_PHASE0C_STORAGE_SIZING_REPORT_20260728.md
ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_PHASE1_CHECKPOINT_20260728.md
ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_PHASE1_COMPLETION_REPORT_20260728.md
ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_PHASE2_CHECKPOINT_20260728.md
ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_PHASE2_COMPLETION_REPORT_20260728.md
ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_PHASE3_CHECKPOINT_20260728.md
ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_PHASE3_COMPLETION_REPORT_20260728.md
ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_PHASE4_CHECKPOINT_20260728.md
ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_PHASE4_COMPLETION_REPORT_20260728.md
ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_PHASE5_CHECKPOINT_20260728.md
ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_PHASE5_COMPLETION_REPORT_20260728.md
ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_PHASE6_CHECKPOINT_20260728.md
ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_PHASE6_COMPLETION_REPORT_20260728.md
ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_READABILITY_CHECKPOINT_20260729.md
ArchitectureRepository/00_Master/ORDER_BOOK_HEATMAP_IMPLEMENTATION_INSTRUCTION_V1_20260729.md
ArchitectureRepository/00_Master/ORDER_BOOK_HEATMAP_INSTRUCTION_CHECKPOINT_20260729.md
ArchitectureRepository/00_Master/ORDER_BOOK_HEATMAP_PHASE_H0_CHECKPOINT_20260729.md
ArchitectureRepository/00_Master/ORDER_BOOK_HEATMAP_PHASE_H0_BASELINE_AUDIT_20260729.md
ArchitectureRepository/00_Master/PROJECT_MEMORY.md
ArchitectureRepository/30_Modules/WebApp/Specifications/WebSocketPayload_Spec_v1.md
```

### 3.2 Source／config／launcher — 17

```text
DeltaEngine05M.bat
Delta_Engine_Pro4web/config/config.yaml
Delta_Engine_Pro4web/docker-compose.yml
Delta_Engine_Pro4web/src/config.py
Delta_Engine_Pro4web/src/database/schema.py
Delta_Engine_Pro4web/src/database/storage.py
Delta_Engine_Pro4web/src/orderflow/orderbook.py
Delta_Engine_Pro4web/src/pipeline.py
Delta_Engine_Pro4web/src/strategy_engine/ingestion/snapshot_producer.py
Delta_Engine_Pro4web/webapp/book_projection.py
Delta_Engine_Pro4web/webapp/history.py
Delta_Engine_Pro4web/webapp/main.py
Delta_Engine_Pro4web/webapp/push_broker.py
Delta_Engine_Pro4web/webapp/static/footprint_canvas.js
Delta_Engine_Pro4web/webapp/static/index.html
Delta_Engine_Pro4web/webapp/static/time_sales.js
Delta_Engine_Pro4web/webapp/tape.py
```

### 3.3 Tests — 13

```text
Delta_Engine_Pro4web/tests/database/test_footprint_storage.py
Delta_Engine_Pro4web/tests/database/test_open_interest_storage.py
Delta_Engine_Pro4web/tests/test_config.py
Delta_Engine_Pro4web/tests/test_live_pipeline.py
Delta_Engine_Pro4web/tests/test_pipeline.py
Delta_Engine_Pro4web/tests/webapp/test_api.py
Delta_Engine_Pro4web/tests/webapp/test_book_update.py
Delta_Engine_Pro4web/tests/webapp/test_dom_tape_fusion_ui.py
Delta_Engine_Pro4web/tests/webapp/test_footprint_chart_ui.py
Delta_Engine_Pro4web/tests/webapp/test_footprint_history.py
Delta_Engine_Pro4web/tests/webapp/test_phase6_integration.py
Delta_Engine_Pro4web/tests/webapp/test_push_broker.py
Delta_Engine_Pro4web/tests/webapp/test_tape_update.py
```

### 3.4 Commit目的

この57 fileは、Heatmap実装前に成立している次のcurrent product stateを一つの復元点へ保存する。

- Session VWAPを含む既存承認済みsource state
- Footprint persistence／history
- LIVE DOM fail-closed projection
- Time & Sales no-silent-loss／history／reconnect
- Canvas Footprint／Tape frontend融合
- 14px可読性修正
- indicator下段配置
- alert toast右下配置
- Phase 1〜6とoperational activation記録
- Heatmap instruction／H0 audit documents

推奨commit message:

```text
snapshot: preserve Footprint DOM Tape baseline before heatmap
```

---

## 4. Baseline commitから除外 — runtime／measurement artifact 13 file

```text
Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/nested_bars.duckdb
Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/nested_zstd.parquet
Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/normalized_index.duckdb
Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/normalized_no_index.duckdb
Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/normalized_zstd.parquet
Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/source_trades.duckdb
Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/write_benchmark_indexed.duckdb
Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/write_benchmark_nested.duckdb
Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/write_benchmark_no_index.duckdb
vwap-audit.duckdb
vwap_first100.jsonl
vwap_restore_ws_capture.jsonl
vwap_ws_capture.jsonl
```

確認済み容量:

- storage sizing directory: 190,067,866 bytes
- `vwap-audit.duckdb`: 219,688,960 bytes
- captureは0〜26,788 bytes

これらは削除しない。untrackedのまま保持し、exact stage listへ入れない。

---

## 5. 別topic文書 — primary baselineへ混ぜない3 file

```text
ArchitectureRepository/00_Master/トリガー作成指示書群/DeltaEngine_経緯報告_第1期-第4期_20260727.md
ArchitectureRepository/00_Master/トリガー作成指示書群/HOOK_AND_LEGACY_STRATEGY_INVENTORY_20260727.md
ArchitectureRepository/00_Master/トリガー作成指示書群/HOOK_AND_STRATEGY_CONTENT_GUIDE_20260727.md
```

内容を失わないよう保持するが、Heatmap／Footprint復元点のprimary commitへ混ぜない。
必要なら別の明示承認でdocument-only commitにする。

---

## 6. Access denied directory

次はgit status時に読取警告が出るため、count外かつstage対象外である。

```text
.pytest_cache/
pytest-vwap-ui/
pytest-vwap-ui-elevated/
Delta_Engine_Pro4web/session_audit_manual_1oa_m84u/
```

`git add -A`、`git add .`、workspace rootのrecursive stageは禁止する。
primary 57 fileをexact pathでのみstageする。

---

## 7. Commit後の期待状態

baseline commit後も次は意図的にworktreeへ残る。

- runtime／measurement artifact 13 file
- 別topic文書3 file
- access denied directory内の未列挙内容（存在する場合）

したがって`git status`が完全cleanでないことはfailureではない。
commit後に次を検証する。

1. staged／committed fileがexact 57件
2. artifact 13件がcommitへ入っていない
3. 別topic文書3件がcommitへ入っていない
4. commit SHAをcheckpointへ保存
5. WebApp 122 testとrepository 664＋1 skipを再確認
6. 実Edge保護geometryに差分がない

---

## 8. 承認待ち

GO-H0の残作業はrestore point commitだけである。

明示承認対象:

- 上記57 fileをexact stage
- commit message `snapshot: preserve Footprint DOM Tape baseline before heatmap`
- artifact／別topic文書を除外

承認後もGO-H1へ自動では進まない。commit／再検証後、GO-H0完了を報告する。
