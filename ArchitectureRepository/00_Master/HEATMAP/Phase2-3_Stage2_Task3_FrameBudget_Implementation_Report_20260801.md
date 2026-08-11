# Phase 2-3 Stage 2 Task 3 — Frame Budget 実装・検証報告

- 実施日: 2026-08-01
- 指示書: `ArchitectureRepository/00_Master/INSTR_Stage2_Task3_FrameBudget_Stage2_v1.0.md`
- ブランチ: `feature/footprint-dom-tape`
- 基準HEAD: `6ae3f1515ddda4927808a0512a1fb79f2fa32133`
- commit: 未実施
- staging: 空

## 1. 結論

Task 3 Stage 2の16ms per-frameバジェット合否表示を実装した。

- `FRAME_BUDGET_MS = 16`を追加した。
- 既存p95が16ms以下なら`[PASS]`、超過なら`[OVER]`を`#heatmapstatus`末尾へ表示する。
- PASS時は`#00cc00`、OVER時は`#ff4444`を`#heatmapstatus.style.color`へ設定する。
- 既存`p95()`算出ロジックと`renderTimes`上限240は変更していない。
- metrics APIは新設していない。
- 新規構造保証テスト5件は全件PASSした。
- 全体回帰は`797 passed, 1 failed, 1 skipped`。failureはStage 1から存在する既知selector不一致1件だけで、新規failureは0件。
- 保護ファイル、Task 1成果物、`src/heatmap/reconstruct.py`の基準HEAD差分は0件。
- コミットは指示どおり未実施。

## 2. 変更ファイル

Task 3による差分は次の2ファイルだけである。

1. `Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js`
2. `Delta_Engine_Pro4web/tests/webapp/test_heatmap_frame_budget.py`（新規）

本報告書はユーザーの2026-08-01の明示依頼により、実装完了後に追加した。

## 3. D1実装内容

### 3.1 `FRAME_BUDGET_MS`定数

変更後:

```javascript
const FRAME_BUDGET_MS = 16;
```

実物では同一IIFEのmodule scopeへ配置した。

指示書は`this.renderTimes = []`の直前を指定していたが、実物の同箇所はconstructor内部である。
そこへblock-scoped `const`を置くと別methodの`updateStatus()`から参照できず、実行時に
`ReferenceError`となる。そのため、機能要件を満たしつつ実行可能な最小位置としてmodule scopeへ置き、
`updateStatus()`の合否判定から直接参照した。

### 3.2 p95表示のbefore／after

Before:

```javascript
const renderP95 = p95(this.renderTimes).toFixed(2);
this.status.textContent = `${bookState} · DEPTH ${frame.bidPrices.length}×${frame.askPrices.length} · SESSION ${jstClock(this.bookStore.sessionStart, "second")} · SESSION ONLY · ${view} · STEP ${step} · Q95 ${geometry.scale.q95.toFixed(3)} · BOOK ${this.bookStore.frames.length}/${this.bookStore.maxFrames} · TAPE ${this.tradeStore.trades.length}/${this.tradeStore.capacity} · RENDER P95 ${renderP95}ms`;
```

After:

```javascript
const renderP95Value = p95(this.renderTimes);
const renderP95 = renderP95Value.toFixed(2);
const frameBudgetPassed = renderP95Value <= FRAME_BUDGET_MS;
const frameBudgetLabel = frameBudgetPassed ? "[PASS]" : "[OVER]";
this.status.textContent = `${bookState} · DEPTH ${frame.bidPrices.length}×${frame.askPrices.length} · SESSION ${jstClock(this.bookStore.sessionStart, "second")} · SESSION ONLY · ${view} · STEP ${step} · Q95 ${geometry.scale.q95.toFixed(3)} · BOOK ${this.bookStore.frames.length}/${this.bookStore.maxFrames} · TAPE ${this.tradeStore.trades.length}/${this.tradeStore.capacity} · RENDER P95 ${renderP95}ms ${frameBudgetLabel}`;
this.status.style.color = frameBudgetPassed ? "#00cc00" : "#ff4444";
```

### 3.3 維持した既存契約

- `const p95 = values => percentile(values, 0.95);`は変更していない。
- `percentile()`本体は変更していない。
- `this.recordTiming(this.renderTimes, elapsed, 240);`は変更していない。
- `#heatmapstatus`のDOM ID・構造は変更していない。
- metrics API、server endpoint、WebSocket payloadは変更していない。

## 4. R1 — `orderbook_heatmap.js`

- Path: `Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js`
- SHA-256: `7DEADC20729C226BEC82301D57B4F330BD59585733C2DF016592707DC730BF2D`
- Bytes: `63,017`
- LF: `1,231`
- CR: `0`
- `node --check webapp/static/orderbook_heatmap.js`: PASS（出力なし、exit 0）
- `float(`走査: 0件

変更後全文の正本は上記pathの実物ファイルである。

## 5. R2 — `test_heatmap_frame_budget.py`全文

- Path: `Delta_Engine_Pro4web/tests/webapp/test_heatmap_frame_budget.py`
- SHA-256: `E7E68471A96EF70EA1366D956C059F9E8DBA35E6AB920397F5ABA996C9B4A8B1`
- Bytes: `2,227`
- LF: `57`
- CR: `0`
- `float(`走査: 0件

```python
"""Tests for 16ms frame-budget instrumentation in orderbook_heatmap.js."""
import pathlib
import pytest

JS_PATH = pathlib.Path(__file__).resolve().parents[2] / "webapp" / "static" / "orderbook_heatmap.js"


@pytest.fixture
def js_source():
    return JS_PATH.read_text(encoding="utf-8")


def test_frame_budget_constant_exists(js_source):
    """FRAME_BUDGET_MS = 16 が宣言されていること。"""
    assert "FRAME_BUDGET_MS" in js_source
    # 値が 16 であること(代入行を検査)
    assert "= 16" in js_source.split("FRAME_BUDGET_MS")[1].split(";")[0]


def test_pass_fail_indicator_exists(js_source):
    """合否インジケータ文字列が存在すること。"""
    assert "[PASS]" in js_source
    assert "[OVER]" in js_source


def test_no_hardcoded_budget_in_indicator(js_source):
    """合否判定で FRAME_BUDGET_MS 定数を参照し、マジックナンバー 16 を
    インラインで使っていないこと。比較演算子の前後に直接 16 が現れないことを検査。"""
    # FRAME_BUDGET_MS の宣言行を除外してから検査
    lines = js_source.splitlines()
    non_decl_lines = [
        ln for ln in lines if "FRAME_BUDGET_MS" not in ln or "const" not in ln
    ]
    indicator_context = [
        ln for ln in non_decl_lines
        if "[PASS]" in ln or "[OVER]" in ln or "FRAME_BUDGET" in ln
    ]
    for ln in indicator_context:
        # 合否判定行で数値リテラル 16 が直接使われていないこと
        # (FRAME_BUDGET_MS 経由であるべき)
        tokens = ln.replace("FRAME_BUDGET_MS", "").split()
        for token in tokens:
            stripped = token.strip("()<=>;,")
            assert stripped != "16", (
                f"マジックナンバー 16 がインラインで使用されている: {ln}"
            )


def test_render_times_buffer_limit(js_source):
    """renderTimes バッファ上限が 240 であること(既存仕様の退行防止)。"""
    assert "240" in js_source


def test_heatmapstatus_color_setting(js_source):
    """合否に応じた色設定が存在すること。"""
    assert "#00cc00" in js_source or "00cc00" in js_source
    assert "#ff4444" in js_source or "ff4444" in js_source
```

## 6. R3 — 対象pytest出力全文

実行command:

```text
python -m pytest tests/webapp/test_heatmap_frame_budget.py -v
```

出力:

```text
============================= test session starts =============================
platform win32 -- Python 3.13.12, pytest-9.1.1, pluggy-1.6.0 -- C:\Users\user\AppData\Local\Programs\Python\Python313\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\user\Desktop\DeltaEngine05M\Delta_Engine_Pro4web
plugins: anyio-4.12.1
collecting ... collected 5 items

tests/webapp/test_heatmap_frame_budget.py::test_frame_budget_constant_exists PASSED [ 20%]
tests/webapp/test_heatmap_frame_budget.py::test_pass_fail_indicator_exists PASSED [ 40%]
tests/webapp/test_heatmap_frame_budget.py::test_no_hardcoded_budget_in_indicator PASSED [ 60%]
tests/webapp/test_heatmap_frame_budget.py::test_render_times_buffer_limit PASSED [ 80%]
tests/webapp/test_heatmap_frame_budget.py::test_heatmapstatus_color_setting PASSED [100%]

============================== 5 passed in 0.12s ==============================
```

## 7. R4 — 全体pytest

実行command:

```text
python -m pytest -q -p no:cacheprovider
```

最終summary:

```text
1 failed, 797 passed, 1 skipped in 134.26s (0:02:14)
```

failure全件:

```text
tests/webapp/test_dom_tape_fusion_ui.py::test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation
```

失敗assert:

```text
assert 'body.phase5-fusion #right>#left{display:none!important}' in html
```

Stage 1 baselineと同一の既知failureであり、本Taskによる新規failureは0件。

## 8. R5 — `git diff --name-only`

実行時の全出力:

```text
ArchitectureRepository/00_Master/ORDER_BOOK_HEATMAP_IMPLEMENTATION_INSTRUCTION_V1_20260729.md
ArchitectureRepository/00_Master/ORDER_BOOK_HEATMAP_PHASE_H0_CHECKPOINT_20260729.md
ArchitectureRepository/00_Master/PROJECT_MEMORY.md
ArchitectureRepository/30_Modules/WebApp/Specifications/WebSocketPayload_Spec_v1.md
Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js
```

先頭4件はTask 3着手前から存在するユーザー所有の既存差分であり、保持した。
新規未追跡テストは`git diff --name-only`には表示されないため、次節のtask-scoped statusで示す。

## 9. R6 — Git status／保護境界

Task-scoped status:

```text
 M Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js
?? Delta_Engine_Pro4web/tests/webapp/test_heatmap_frame_budget.py
```

本報告書追加後の追加status:

```text
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Stage2_Task3_FrameBudget_Implementation_Report_20260801.md
```

staging:

```text
git diff --cached --name-only
```

出力なし。stagingは空。

保護境界確認command:

```text
git diff 6ae3f1515ddda4927808a0512a1fb79f2fa32133 -- webapp/main.py docker-compose.yml tests/webapp/test_book_update.py webapp/static/index.html webapp/heatmap_frame_source.py tests/webapp/test_heatmap_frame_source.py src/heatmap/reconstruct.py
```

出力なし。次の全保護対象に差分なし。

- `webapp/main.py`
- `docker-compose.yml`
- `tests/webapp/test_book_update.py`
- `webapp/static/index.html`
- `webapp/heatmap_frame_source.py`
- `tests/webapp/test_heatmap_frame_source.py`
- `src/heatmap/reconstruct.py`

`git diff --check -- webapp/static/orderbook_heatmap.js tests/webapp/test_heatmap_frame_budget.py`も出力なしでPASS。

## 10. 検証基準判定

| ID | 判定 | 根拠 |
|---|---|---|
| V1 | PASS | `FRAME_BUDGET_MS = 16`あり |
| V2 | PASS | `[PASS]`／`[OVER]`あり |
| V3 | PASS | 合否判定は`FRAME_BUDGET_MS`を参照、inline `16`なし |
| V4 | PASS | `#00cc00`／`#ff4444`あり |
| V5 | PASS | `p95()`本体と上限240に変更なし |
| V6 | PASS | 新規5件全件PASSED |
| V7 | PASS | 797 passed、既知1 failed、1 skipped |
| V8 | PASS | 対象2ファイルの`float(`追加0件 |
| V9 | PASS | Task差分はJSと新規testだけ。本報告書は後続のユーザー明示依頼で追加 |
| V10 | PASS | 保護7ファイルの差分0件 |

## 11. 未実施・次工程

- commitは未実施。
- stagingは空。
- 実ブラウザでの動的フレームp95実測は、本Stage 2の構造保証とは別の次工程。
- 統括検証後、別途commitまたは実測指示を受けて再開する。
