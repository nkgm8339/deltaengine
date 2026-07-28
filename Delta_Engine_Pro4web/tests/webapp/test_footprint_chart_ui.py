"""Phase 4 Canvas Footprint Chart contract tests."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).parents[2]
HTML_PATH = ROOT / "webapp" / "static" / "index.html"
JS_PATH = ROOT / "webapp" / "static" / "footprint_canvas.js"


def test_canvas_footprint_panel_has_fixed_controls_and_accessible_detail() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")

    assert '<script src="/static/footprint_canvas.js"></script>' in html
    assert 'id="fpcanvas"' in html
    assert 'id="fpstage"' in html
    assert 'id="fpselection" role="status" aria-live="polite"' in html
    assert 'id="fpstatus"' in html
    assert 'id="fpstep"' in html
    assert 'value="AUTO"' in html
    for count in (3, 10, 20):
        assert f'id="fp{count}"' in html
    assert "LIVE LOCK" in html
    assert '<span class="fp-control-label">JST</span>' in html
    assert 'id="fpbody"' not in html


def test_canvas_footprint_connects_live_history_and_lazy_cursor_without_dom_cells() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")
    source = JS_PATH.read_text(encoding="utf-8")

    assert "rememberFootprintBar(p);" in html
    assert 'renderFootprint("liveFootprint")' in html
    assert "async function loadFootprintHistory(before=null)" in html
    assert "api/history/footprints" in html
    assert 'query.set("before",cursor)' in html
    assert "onNeedHistory:()=>loadFootprintHistory(FP.cursor)" in html
    assert "new DeltaFootprint.CanvasChart" in html
    assert "requestAnimationFrame" in source
    assert "OffscreenCanvas" in source
    assert 'layer === "reference" || layer === "selection"' in source
    assert "new ResizeObserver" in source
    assert "setTransform(dpr" in source
    assert "getBoundingClientRect" in source
    assert "addEventListener(\"wheel\"" in source
    assert "addEventListener(\"keydown\"" in source
    assert "document.createElement" not in source
    assert ".innerHTML" not in source


def test_canvas_layers_preserve_footprint_meanings_and_completed_chart_geometry() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")
    source = JS_PATH.read_text(encoding="utf-8")

    assert 'const BUY = "#19C979"' in source
    assert 'const SELL = "#FF4058"' in source
    assert 'const POC = "#F4C542"' in source
    assert "bucketLevels" in source
    assert "valueArea" in source
    assert "imbalanceFlags" in source
    assert "drawCandle" in source
    assert "drawReferences" in source
    assert "drawSelection" in source
    assert "CVD Δ" in source
    assert "OI Δ" in source
    assert "EVENTS" in source
    assert "bar.va.vah" in source and "bar.va.val" in source
    assert "bucketLabel(hit.row, this.frame)" in source
    assert "exactValue(hit.level.bid)" in source
    assert "EXCHANGE BAR_TIME" in source
    assert "JST_OFFSET_MS" in source
    assert "const AXIS_FONT_PX = 12" in source
    assert "const CELL_FONT_PX = 14" in source
    assert "const STANDARD_CELL_FONT_PX = 12" in source
    assert "autoMultiplier(minPrice, maxPrice, tick, 20)" in source
    assert "const maxTextWidth = Math.max(8, half - 5)" in source
    assert "y + g.rowHeight / 2, maxTextWidth" in source
    assert "20–40 PRICE ROWS" in html
    # Phase 4 must not resize or replace the completed three-stage chart.
    assert 'const MC={W:1200,H:500' in html
    assert '<text x="28" y="335"' in html
    assert '<text x="28" y="454"' in html
    assert '#bottom.market-chart-panel{height:594px;min-height:594px;flex:0 0 594px' in html


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_display_bucket_value_area_and_auto_step_are_deterministic() -> None:
    script = r"""
const f=require(process.argv[1]);
const rows=f.bucketLevels([
  {price:'100.0',bid:'2',ask:'3'},
  {price:'100.1',bid:'4',ask:'5'},
  {price:'100.2',bid:'1',ask:'1'}
],0.1,2);
const va=f.valueArea(rows,70);
process.stdout.write(JSON.stringify({rows,auto:f.autoMultiplier(100,110,0.1,30),poc:va.poc,
  label:f.bucketLabel({price:100},{step:.2,tick:.1,multiplier:2}),exact:f.exactValue(.3),
  jst:f.jstClock(Date.parse('2026-07-28T08:40:00Z'),'millisecond')}));
"""
    result = subprocess.run(
        [shutil.which("node"), "-e", script, str(JS_PATH)],
        check=True,
        capture_output=True,
        encoding="utf-8",
    )
    payload = json.loads(result.stdout)
    assert payload["rows"] == [
        {"index": 1002, "price": 100.2, "bid": 1, "ask": 1},
        {"index": 1000, "price": 100, "bid": 6, "ask": 8},
    ]
    assert payload["auto"] == 5
    assert payload["poc"] == 1000
    assert payload["label"] == "100.0–100.1"
    assert payload["exact"] == "0.3"
    assert payload["jst"] == "17:40:00.000"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_bucketed_diagonal_imbalance_uses_display_step_adjacency() -> None:
    script = r"""
const f=require(process.argv[1]);
const rows=[
  {index:1002,price:100.2,bid:1,ask:10},
  {index:1000,price:100.0,bid:1,ask:1}
];
const flags=f.imbalanceFlags(rows,3,0,3);
process.stdout.write(JSON.stringify({buy:flags.get(1002).buy,sell:flags.get(1000).sell}));
"""
    result = subprocess.run(
        [shutil.which("node"), "-e", script, str(JS_PATH)],
        check=True,
        capture_output=True,
        encoding="utf-8",
    )
    assert json.loads(result.stdout) == {"buy": True, "sell": False}
