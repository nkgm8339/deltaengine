from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "webapp" / "static" / "index.html"
HEATMAP = ROOT / "webapp" / "static" / "orderbook_heatmap.js"


def test_heatmap_is_fail_closed_until_operational_activation():
    source = INDEX.read_text(encoding="utf-8")
    assert "const ORDER_BOOK_HEATMAP_ENABLED = false;" in source
    assert "if(!ORDER_BOOK_HEATMAP_ENABLED)" in source
    assert "heatmapButton.hidden=true" in source
    assert "window.HEATMAP_UI=api" in source


def test_heatmap_canvas_really_replaces_footprint_in_same_stage():
    source = INDEX.read_text(encoding="utf-8")
    assert '#fpcanvas[hidden],#heatmapcanvas[hidden]' in source
    assert "#fpstage>#fpcanvas,#fpstage>#heatmapcanvas{position:absolute;inset:0" in source
    assert "fpCanvas.hidden=heat;heatCanvas.hidden=!heat" in source
    assert 'id="heatmaptooltip"' in source
    assert 'id="heatmapdetail"' in source
    assert 'id="heatmapstatus"' in source


def test_heatmap_controls_and_accessibility_contract_exist():
    source = INDEX.read_text(encoding="utf-8")
    for marker in [
        'id="hm1m"', 'id="hm5m"', 'id="hm15m"', 'id="hmstep"',
        'id="hmintensityminus"', 'id="hmintensityplus"', 'id="hmbubbles"',
        'id="hmlock"', 'id="hmminnotional"', 'id="hmbidask"', 'id="hmlast"',
        'tabindex="0"', 'role="tooltip"',
    ]:
        assert marker in source
    assert "Bookmap-style time by price" in source
    assert "SESSION ONLY" in source


def test_heatmap_uses_canvas_renderer_not_rudimentary_inline_strips():
    source = INDEX.read_text(encoding="utf-8")
    module = HEATMAP.read_text(encoding="utf-8")
    assert "new HEATMAP_BOOK_ID.OrderBookHeatmapCanvas" in source
    assert "class OrderBookHeatmapCanvas" in module
    assert "durationWeightedCells(intervals, columns, gaps)" in module
    assert "drawBookGaps" in module
    assert "drawTapeMarkers" in module
    assert "drawAxes" in module
    assert "drawLegend" in module
    assert "aggregateTradeBubbles" in module
    assert 'bucketBookFrame(f,1,1)' not in source
    assert 'side==="bids"?' not in source


def test_time_sales_linkage_preserves_normalizer_and_passes_stream_context():
    source = INDEX.read_text(encoding="utf-8")
    tape = (INDEX.parent / "time_sales.js").read_text(encoding="utf-8")
    assert "this.onAcceptedTrades(accepted, result)" in tape
    assert "ingestTrades(trades,{streamId:TAPE_UI.store.streamId,result})" in source
    assert "recordTapeContinuity(result,TAPE_UI.store.streamId)" in source
    assert "focusTrade(trade)" in source


def test_primary_heatmap_axis_and_tooltip_font_contract():
    source = INDEX.read_text(encoding="utf-8")
    module = HEATMAP.read_text(encoding="utf-8")
    assert '#heatmaptooltip{position:absolute' in source
    assert 'font:800 14px' in source
    assert 'context.font = `800 14px ${FONT}`' in module
