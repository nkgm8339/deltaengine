"""Big Trades V2 browser contract tests (BT2-U236 through BT2-U275)."""

from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[2]
INDEX = ROOT / "webapp" / "static" / "index.html"
MODULE = ROOT / "webapp" / "static" / "big_trades.js"


def html() -> str:
    return INDEX.read_text(encoding="utf-8")


def module() -> str:
    return MODULE.read_text(encoding="utf-8")


def run_node(body: str) -> str:
    script = f'''require("./webapp/static/big_trades.js");
const bt = global.DeltaBigTradesV2;
{body}
'''
    completed = subprocess.run(
        [shutil.which("node"), "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def test_bt2_u236_three_mode_switch() -> None:
    source = html()
    positions = [source.index(f'id="{item}"') for item in ("modeFootprint", "modeHeatmap", "modeBigTrades")]
    assert positions == sorted(positions)
    assert 'bigButton.onclick=()=>setMode("BIG_TRADES")' in source


def test_bt2_u237_footprint_mode_dom_and_geometry_preserved() -> None:
    source = html()
    assert 'id="fpcanvas"' in source
    assert 'id="fpcontrols"' in source
    assert 'footprintButton.classList.toggle("on",!heat&&!big)' in source
    assert 'body.big-trades-mode #center>.panel:first-child' in source


def test_bt2_u238_heatmap_mode_dom_and_geometry_preserved() -> None:
    source = html()
    assert 'id="heatmapcanvas"' in source
    assert 'id="heatmapcontrols"' in source
    assert 'heatmapButton.classList.toggle("on",heat)' in source
    assert 'if(chart)chart.setVisible(heat)' in source


def test_bt2_u239_only_big_trades_canvas_is_active_in_big_mode() -> None:
    source = html()
    assert 'fpStage.hidden=big;fpCanvas.hidden=heat;heatCanvas.hidden=!heat;if(big)fpCanvas.hidden=true;btWorkspace.hidden=!big' in source
    assert "#fpstage[hidden]{display:none!important}" in source
    assert 'if(BIG_TRADES_UI)BIG_TRADES_UI.setActive(big)' in source


def test_bt2_u240_controls_are_fixed_and_manual_auto_disable_unused_side() -> None:
    source = html()
    for identifier in ("btmode", "btside", "btmin", "btmax", "btintensity", "btmark", "btzones", "btstate", "btcal", "btapply"):
        assert f'id="{identifier}"' in source
    js = module()
    assert "this.elements.min.disabled = !manual" in js
    assert "this.elements.intensity.disabled = manual" in js


def test_bt2_u241_marker_has_aggregate_quantity_label() -> None:
    js = module()
    assert "eventRow.aggregate_quantity" in js
    assert "ctx.fillText(`${zone.origin_side}" in js


def test_bt2_u242_buy_sell_use_text_and_color() -> None:
    js = module()
    assert 'zone.origin_side === "BUY" ? "#19C979" : "#FF4058"' in js
    assert "zone.origin_side" in js


def test_bt2_u243_zone_uses_exact_execution_range() -> None:
    js = module()
    assert "exactLow = num(zone.zone_low), exactHigh = num(zone.zone_high)" in js
    assert "exactLow, exactHigh, exactHeight, visualHeight" in js


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_bt2_u244_single_price_minimum_height_is_visual_only() -> None:
    output = run_node('''
const p = new bt.ReactionZoneProjection({minZonePixels:3});
const box = p.zoneRect({zone_low:"100",zone_high:"100",zone_source_start:"2026-08-12T00:00:00Z"},{sourceEnd:null},{x:x=>x/1000,y:y=>200-y},Date.parse("2026-08-12T00:01:00Z"));
if(box.exactLow!==100||box.exactHigh!==100||box.exactHeight!==0||box.visualHeight!==3) throw new Error(JSON.stringify(box));
console.log("ok");
''')
    assert output == "ok"


def test_bt2_u245_break_does_not_delete_zone() -> None:
    js = module()
    assert "CROSS_UP" not in js[js.index("ingestInteraction(row)"):js.index("ingestLink(row)")]
    assert "this.zones.delete" in js and "pruneZones" in js


def test_bt2_u246_closed_zone_stops_at_source_end() -> None:
    js = module()
    assert 'row.interaction_type === "ZONE_SESSION_CLOSED"' in js
    assert "state.sourceEnd ? Date.parse(state.sourceEnd) : latestTime" in js


def test_bt2_u247_gap_segment_is_hatched() -> None:
    js = module()
    assert "state.gaps.forEach" in js
    assert "ctx.clip()" in js
    assert 'ctx.strokeStyle = "#F4C542"' in js


def test_bt2_u248_overlapping_zones_are_not_destructively_merged() -> None:
    js = module()
    assert "this.zones = new Map()" in js
    assert "this.insert(this.zones, row.zone_id, row)" in js
    assert "mergeZones" not in js


def test_bt2_u249_linked_event_ordinal_badge() -> None:
    js = module()
    assert "link.ordinal_for_zone" in js
    assert "this.hitBadges.push" in js


def test_bt2_u250_selected_effort_detail() -> None:
    js = module()
    for label in ("EFFORT", "AGGREGATE QTY", "FILLS", "DURATION", "EXECUTION RANGE", "VWAP", "THRESHOLD"):
        assert f'"{label}"' in js


def test_bt2_u251_selected_result_detail() -> None:
    js = module()
    for label in ("RESULT", "CURRENT", "FIRST EXIT", "MAX ABOVE", "MAX BELOW"):
        assert f'"{label}"' in js


def test_bt2_u252_selected_repeated_area_detail() -> None:
    js = module()
    for label in ("REPEATED AREA ACTIVITY", "LINKED BUY / SELL", "TOUCHES", "REENTRIES", "CROSSES", "INSIDE BUY / SELL", "TIMELINE"):
        assert f'"{label}"' in js


def test_bt2_u253_selected_candle_result_detail() -> None:
    js = module()
    for label in ("CANDLE RESULT", "UPPER WICK RETURN", "LOWER WICK RETURN", "LAST CANDLE ID"):
        assert f'"{label}"' in js


def test_bt2_u254_context_keeps_missing_values_visible() -> None:
    js = module()
    for label in ("CONTEXT", "CVD", "DELTA", "VOLUME", "FLOW RESPONSE", "ABSORPTION", "IMBALANCE"):
        assert f'"{label}"' in js
    assert 'const no = "—"' in js


def test_bt2_u255_assessment_is_append_only_with_visible_history() -> None:
    source, js = html(), module()
    assert 'id="btassessmenthistory"' in source
    assert 'method: "POST"' in js
    assert "getSupersedesId" in js
    assert "user_assessment_history" in js


def test_bt2_u256_snapshots_cover_one_to_six_hundred_seconds() -> None:
    js = module()
    assert '"1s..600s"' in js
    assert "snapshots.map" in js


def test_bt2_u257_current_relation_is_server_fact() -> None:
    js = module()
    assert "row.current_relation" in js
    assert "state.relation || zone?.current_relation" in js


def test_bt2_u258_first_exit_is_displayed_from_history_detail() -> None:
    js = module()
    assert "detail?.first_exit" in js
    assert "firstExit.direction || firstExit.interaction_type" in js


def test_bt2_u259_touch_reentry_cross_counts_sum_both_directions() -> None:
    js = module()
    assert '(counts.TOUCH_FROM_ABOVE || 0) + (counts.TOUCH_FROM_BELOW || 0)' in js
    assert '(counts.REENTER_FROM_ABOVE || 0) + (counts.REENTER_FROM_BELOW || 0)' in js
    assert '(counts.CROSS_UP || 0) + (counts.CROSS_DOWN || 0)' in js


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_bt2_u260_side_filter_does_not_delete_data() -> None:
    output = run_node('''
const s=new bt.ReactionZoneStore();
const mk=(side,digit)=>({zone_id:"btz2_"+digit.repeat(64),content_hash:digit.repeat(64),zone_source_start:"2026-08-12T00:00:00Z",origin_side:side,zone_low:"100",zone_high:"101"});
s.ingestZone(mk("BUY","1"));s.ingestZone(mk("SELL","2"));
if(s.visible({side:"BUY",state:"ALL"}).length!==1||s.zones.size!==2)throw new Error("filter deleted data");
console.log("ok");
''')
    assert output == "ok"


def test_bt2_u261_zones_off_changes_drawing_only() -> None:
    js = module()
    assert "setFilters({ side, state, zonesOn })" in js
    assert "this.zonesOn = zonesOn; this.draw(true)" in js
    assert "if (this.zonesOn)" in js
    assert 'this.elements.zones.value === "ON"' in js


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_bt2_u262_history_live_dedup_and_collision_rejection() -> None:
    output = run_node('''
const s=new bt.BigTradeEventStore(5),id="bt2_"+"1".repeat(64),base={event_id:id,content_hash:"a".repeat(64),last_time:"2026-08-12T00:00:00Z",aggregate_quantity:"1"};
if(s.merge([base,{...base}])!==1||s.events.size!==1)throw new Error("bulk dedup failed");
let rejected=false;try{s.merge([{...base,content_hash:"b".repeat(64)}])}catch(_){rejected=true}
if(!rejected||s.collisions!==1)throw new Error("collision accepted");console.log("ok");
''')
    assert output == "ok"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_big_trades_bulk_interaction_merge_preserves_runtime_state_and_collision_rules() -> None:
    output = run_node('''
const s=new bt.ReactionZoneStore(5,5),z="btz2_"+"1".repeat(64),base={zone_id:z,source_event_time:"2026-08-12T00:00:00Z",ordinal:1,current_relation:"ABOVE"};
const rows=[
  {...base,interaction_id:"bti2_"+"2".repeat(64),interaction_type:"SOURCE_GAP_STARTED",gap_epoch_id:"gap-1",content_hash:"2".repeat(64)},
  {...base,interaction_id:"bti2_"+"3".repeat(64),interaction_type:"SOURCE_GAP_ENDED",gap_epoch_id:"gap-1",source_event_time:"2026-08-12T00:00:01Z",ordinal:2,current_relation:"INSIDE",content_hash:"3".repeat(64)},
  {...base,interaction_id:"bti2_"+"4".repeat(64),interaction_type:"ZONE_SESSION_CLOSED",source_event_time:"2026-08-12T00:00:02Z",ordinal:3,current_relation:"BELOW",content_hash:"4".repeat(64)},
];
if(s.mergeInteractions(rows)!==3||s.mergeInteractions(rows)!==0||s.interactions.size!==3)throw new Error("bulk dedup failed");
const state=s.state(z),gap=state.gaps[0];
if(state.lifecycle!=="SESSION_CLOSED"||state.relation!=="BELOW"||state.sourceEnd!==rows[2].source_event_time||!gap.end_time)throw new Error("state projection changed");
let rejected=false;try{s.mergeInteractions([{...rows[0],content_hash:"f".repeat(64)}])}catch(_){rejected=true}
if(!rejected||s.collisions!==1)throw new Error("collision accepted");console.log("ok");
''')
    assert output == "ok"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_bt2_u263_sequence_gap_and_restart_enter_recovery() -> None:
    output = run_node('''
const gaps=[],c=new bt.BigTradesContinuity(x=>gaps.push(x));
c.accept({stream_id:"a",first_sequence:1,last_sequence:2,dropped_count:0});
c.accept({stream_id:"a",first_sequence:4,last_sequence:4,dropped_count:0});
c.accept({stream_id:"b",first_sequence:1,last_sequence:1,dropped_count:2});
if(!c.recovering||c.gapCount!==2||c.dropped!==2||gaps.length!==2)throw new Error("continuity failed");
if(!c.recovered({stream_id:"b",last_admitted_sequence:7,dropped_count:2})||c.lastSequence!==7||c.recovering)throw new Error("recovery marker failed");console.log("ok");
''')
    assert output == "ok"


def test_bt2_u264_no_data_fields_remain_dash() -> None:
    source, js = html(), module()
    assert source.count("—") >= 20
    assert 'return value === null || value === undefined || value === "" ? "—"' in js


def test_bt2_u265_click_escape_and_arrow_navigation() -> None:
    js = module()
    assert 'event.key === "Escape"' in js
    assert 'event.key === "ArrowLeft" || event.key === "ArrowRight"' in js
    assert "click(event)" in js and "select(zoneId)" in js


def test_bt2_u266_wheel_drag_and_live_lock() -> None:
    js = module()
    assert "pointerdown" in js
    assert "wheel(event)" in js
    assert "lockLive()" in js
    assert 'event.key.toLowerCase() === "l"' in js


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_bt2_u267_inactive_mode_detaches_handlers() -> None:
    output = run_node('''
const calls={add:0,remove:0},canvas={addEventListener(){calls.add++},removeEventListener(){calls.remove++},focus(){},getBoundingClientRect(){return {width:100,height:100}},getContext(){return {}}},tooltip={hidden:true};
const chart=new bt.BigTradesCanvas({canvas,tooltip,eventStore:{},zoneStore:{}});chart.draw=()=>{};chart.setActive(true);chart.setActive(false);
if(calls.add!==8||calls.remove!==8||chart._handlers!==null)throw new Error(JSON.stringify(calls));console.log("ok");
''')
    assert output == "ok"


def test_bt2_u268_bounded_store_capacities_are_wired() -> None:
    js = module()
    assert "new BigTradeEventStore(5000)" in js
    assert "new ReactionZoneStore(5000, 20000)" in js
    assert "while (this.events.size > this.capacity)" in js
    assert "while (this.interactions.size > this.interactionCapacity)" in js


def test_bt2_u269_big_trades_has_no_horizontal_overflow() -> None:
    source = html()
    assert "#btworkspace{display:grid" in source
    assert "min-width:0;min-height:0;overflow:hidden" in source
    assert "#btdetail{min-width:0" in source


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_bt2_u270_browser_javascript_compiles() -> None:
    subprocess.run([shutil.which("node"), "--check", str(MODULE)], check=True)
    check_inline = r'''const fs=require("fs"),source=fs.readFileSync(process.argv[1],"utf8");
const inline=source.slice(source.indexOf("<script>")+8,source.lastIndexOf("</script>"));new Function(inline);'''
    completed = subprocess.run(
        [shutil.which("node"), "-e", check_inline, str(INDEX)],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_bt2_u271_time_sales_filter_meaning_is_untouched() -> None:
    source = html()
    for identifier in ("tapeside", "tapeminqty", "tapeminnotional", "tapelarge", "tapelargeonly"):
        assert f'id="{identifier}"' in source
    assert "TAPE_UI.setFilters({side:" in source


def test_bt2_u272_dom_trade_pulse_path_is_untouched() -> None:
    source = html()
    assert "DOM_TRADE_PULSE_ENABLED" in source
    assert "FP.chart.ingestDomTradePulses" in source
    assert "onAcceptedTrades:onAcceptedTapeTrades" in source


def test_bt2_u273_three_stage_chart_geometry_is_not_overridden() -> None:
    source = html()
    assert '#bottom.market-chart-panel{\n  grid-column:1;grid-row:2;' in source
    bt_css = source[source.index('<style id="big-trades-v2-ui">'):source.index('</style>', source.index('<style id="big-trades-v2-ui">'))]
    assert "#bottom" not in bt_css and "#chartwrap" not in bt_css and "#chartstatus" not in bt_css


def test_bt2_u274_flow_response_cards_are_not_replaced() -> None:
    source = html()
    assert 'id="flowresponse"' in source
    assert source.count('class="flow-response-slot"') == 8
    assert "function renderLiveObservation()" in source


def test_bt2_u275_system_facts_and_user_assessment_are_separate() -> None:
    source, js = html(), module()
    assert ".bt-system-facts{border-color:#275071" in source
    assert ".bt-user-assessment{border-color:#594780" in source
    assert '"bt-detail-section bt-system-facts"' in js
    assert '"bt-detail-section bt-user-assessment"' in js


def test_big_trades_frontend_exports_all_required_modules() -> None:
    js = module()
    for name in (
        "BigTradeRecordValidator", "BigTradeEventStore", "ReactionZoneStore",
        "ReactionZoneProjection", "BigTradesContinuity", "BigTradesCanvas",
        "BigTradesSettingsController", "BigTradesAssessmentController",
        "BigTradesContextLink",
    ):
        assert f"class {name}" in js


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_browser_validator_rejects_unknown_fields_and_numeric_decimal() -> None:
    output = run_node('''
const id="bt2_"+"1".repeat(64),hash="a".repeat(64),base={v:1,type:"BIG_TRADES_UPDATE",time:"2026-08-12T00:00:00Z",symbol:"BTCUSDT",payload:{batch_time:"2026-08-12T00:00:00Z",stream_id:"123e4567-e89b-42d3-a456-426614174000",first_sequence:1,last_sequence:1,accepted_count:1,dropped_count:0,records:[{kind:"EVENT_CREATED",sequence:1,source_event_time:"2026-08-12T00:00:00Z",source_trade_id:1,record_id:id,content_hash:hash,data:{event_id:id,content_hash:hash,aggregate_quantity:"1"}}]}};
bt.BigTradeRecordValidator.validateUpdate(base);let rejected=0;
try{bt.BigTradeRecordValidator.validateUpdate({...base,extra:true})}catch(_){rejected++}
try{bt.BigTradeRecordValidator.validateUpdate({...base,payload:{...base.payload,records:[{...base.payload.records[0],data:{...base.payload.records[0].data,aggregate_quantity:1}}]}})}catch(_){rejected++}
if(rejected!==2)throw new Error("invalid payload accepted");console.log("ok");
''')
    assert output == "ok"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_browser_validator_accepts_enum_price_mode_and_numeric_price_path_size() -> None:
    output = run_node('''
const id="bt2_"+"1".repeat(64),hash="a".repeat(64);
bt.BigTradeRecordValidator.validateHistoryRow({event_id:id,content_hash:hash,last_time:"2026-08-12T00:00:00Z",marker_price_mode:"LAST_PRICE"},"event_id","last_time");
bt.BigTradeRecordValidator.validateStatus({v:1,type:"BIG_TRADES_STATUS",time:"2026-08-12T00:00:00Z",symbol:"BTCUSDT",payload:{status:"MANUAL_READY",reason:null,counters:{price_path_index_size:25000}}});
console.log("ok");
''')
    assert output == "ok"
