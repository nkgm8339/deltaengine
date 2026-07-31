"""Time & Sales accepted trades projected to bounded LIVE DOM pulse overlays."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).parents[2]
CANVAS_PATH = ROOT / "webapp" / "static" / "footprint_canvas.js"
HTML_PATH = ROOT / "webapp" / "static" / "index.html"


def test_dom_trade_pulse_source_is_bounded_and_overlay_only() -> None:
    source = CANVAS_PATH.read_text(encoding="utf-8")

    assert 'const DOM_TRADE_PULSE_COLOR = "#FFD54A"' in source
    assert "const DEFAULT_DOM_TRADE_PULSE_DURATION_MS = 400" in source
    assert "const DEFAULT_DOM_TRADE_PULSE_MAX_ACTIVE = 256" in source
    assert "class DomTradePulseStore" in source
    assert "function passiveSideForAggressor" in source
    assert 'return "ASK"' in source
    assert 'return "BID"' in source
    assert "ingestDomTradePulses(trades, meta)" in source
    assert "scheduleDomTradePulseFrame()" in source
    assert 'layer === "domTradePulse"' in source
    assert "this.drawDomTradePulses(ctx, g, this.frame)" in source
    assert source.index("this.drawBook(ctx, g, this.frame)") < source.index(
        "this.drawDomTradePulses(ctx, g, this.frame)"
    )
    assert source.index("this.drawDomTradePulses(ctx, g, this.frame)") < source.index(
        "this.drawReferences(ctx, g, this.frame)"
    )
    assert "DomTradePulseStore," in source
    assert "passiveSideForAggressor," in source


def test_only_accepted_tape_trades_are_wired_through_named_coordinator() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")

    assert "const DOM_TRADE_PULSE_ENABLED = true;" in html
    assert "const DOM_TRADE_PULSE_DURATION_MS = 400;" in html
    assert "function onAcceptedTapeTrades(trades,result)" in html
    assert "onAcceptedTrades:onAcceptedTapeTrades" in html
    assert "FP.chart.ingestDomTradePulses(trades,{" in html
    assert 'FP.chart.clearDomTradePulses("TAPE_STREAM_RESTART")' in html
    assert 'FP.chart.clearDomTradePulses("SYMBOL_CHANGE")' in html
    assert (
        "window.HEATMAP_UI.ingestTrades("
        "trades,{streamId:TAPE_UI.store.streamId,result})"
    ) in html
    assert "domTradePulseEnabled:DOM_TRADE_PULSE_ENABLED" in html
    assert "domTradePulseDurationMs:DOM_TRADE_PULSE_DURATION_MS" in html

    tick_body = html.split("function onTick(m,p){", 1)[1].split(
        "function onBookUpdate", 1
    )[0]
    assert "ingestDomTradePulses" not in tick_body
    history_body = html.split("async function loadTimeSalesHistory()", 1)[1].split(
        "async function selectTapeTrade", 1
    )[0]
    assert "ingestDomTradePulses" not in history_body


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_pulse_store_side_bucket_expiry_coalesce_fail_closed_and_capacity() -> None:
    script = r"""
const f=require(process.argv[1]);
let now=0;
const store=new f.DomTradePulseStore({durationMs:400,maxActive:4,now:()=>now});
const context={synced:true,tick:.1,multiplier:2,rowIndexes:new Set([1000,1002]),now};
const first=store.ingest([
  {tradeId:'b1',sequence:1,price:'100.1',side:'BUY'},
  {tradeId:'s1',sequence:2,price:'100.1',side:'SELL'}
],context);
const frame={book:{synced:true},tick:.1,multiplier:2,rows:[{index:1002},{index:1000}]};
const cells0=store.activeCells(frame,now).sort((a,b)=>a.passiveSide.localeCompare(b.passiveSide));
now=250;
const coalesced=store.ingest([{tradeId:'b2',sequence:3,price:'100.1',side:'BUY'}],
  {synced:true,tick:.1,multiplier:2,rowIndexes:new Set([1000,1002]),now});
const cells399=store.activeCells(frame,399).sort((a,b)=>a.passiveSide.localeCompare(b.passiveSide));
const cells400=store.activeCells(frame,400);
const cells649=store.activeCells(frame,649);
const cells650=store.activeCells(frame,650);

const rejected=new f.DomTradePulseStore({durationMs:400,maxActive:4,now:()=>now});
const invalid=rejected.ingest([
  {price:'100',side:'WAIT'},
  {price:'0',side:'BUY'},
  {price:'105',side:'SELL'}
],{synced:true,tick:.1,multiplier:1,rowIndexes:new Set([1000]),now});
const unsynced=rejected.ingest([{price:'100',side:'BUY'}],
  {synced:false,tick:.1,multiplier:1,rowIndexes:new Set([1000]),now});

now=1000;
const bounded=new f.DomTradePulseStore({durationMs:400,maxActive:2,now:()=>now});
const cap=bounded.ingest([
  {tradeId:'1',price:'100.0',side:'BUY'},
  {tradeId:'2',price:'100.1',side:'BUY'},
  {tradeId:'3',price:'100.2',side:'BUY'}
],{synced:true,tick:.1,multiplier:1,rowIndexes:new Set([1000,1001,1002]),now});
const beforeClear=bounded.snapshot(now);
const cleared=bounded.clear('TEST_BOUNDARY');
bounded.clear('EMPTY_REPEAT');
const afterClear=bounded.snapshot(now);

process.stdout.write(JSON.stringify({
  mapping:[f.passiveSideForAggressor('BUY'),f.passiveSideForAggressor('sell'),f.passiveSideForAggressor('WAIT')],
  first,coalesced,
  cells0:cells0.map(x=>({side:x.passiveSide,bucket:x.displayBucketIndex,hits:x.hitCount,opacity:x.opacity})),
  cells399:cells399.map(x=>({side:x.passiveSide,hits:x.hitCount,opacity:x.opacity})),
  cells400:cells400.map(x=>x.passiveSide),
  cells649:cells649.map(x=>x.passiveSide),
  cells650:cells650.map(x=>x.passiveSide),
  mainStats:store.snapshot(now),
  invalid,unsynced,rejectedStats:rejected.snapshot(now),
  cap,beforeClear,cleared,afterClear
}));
"""
    result = subprocess.run(
        [shutil.which("node"), "-e", script, str(CANVAS_PATH)],
        check=True,
        capture_output=True,
        encoding="utf-8",
    )
    payload = json.loads(result.stdout)

    assert payload["mapping"] == ["ASK", "BID", None]
    assert payload["first"] == {
        "started": 2,
        "coalesced": 0,
        "skippedUnsynced": 0,
        "skippedInvalid": 0,
        "skippedOffscreen": 0,
    }
    assert payload["coalesced"]["started"] == 0
    assert payload["coalesced"]["coalesced"] == 1
    assert payload["cells0"] == [
        {"side": "ASK", "bucket": 1000, "hits": 1, "opacity": 1},
        {"side": "BID", "bucket": 1000, "hits": 1, "opacity": 1},
    ]
    assert [cell["side"] for cell in payload["cells399"]] == ["ASK", "BID"]
    assert payload["cells399"][0]["hits"] == 2
    assert payload["cells399"][0]["opacity"] == 1
    assert 0 < payload["cells399"][1]["opacity"] < 0.01
    assert payload["cells400"] == ["ASK"]
    assert payload["cells649"] == ["ASK"]
    assert payload["cells650"] == []
    assert payload["mainStats"]["pulsesStarted"] == 2
    assert payload["mainStats"]["pulsesCoalesced"] == 1
    assert payload["mainStats"]["activeEntries"] == 0

    assert payload["invalid"]["skippedInvalid"] == 2
    assert payload["invalid"]["skippedOffscreen"] == 1
    assert payload["unsynced"]["skippedUnsynced"] == 1
    assert payload["rejectedStats"]["activeEntries"] == 0
    assert payload["cap"]["started"] == 3
    assert payload["beforeClear"]["activeEntries"] == 2
    assert payload["beforeClear"]["evictedCapacity"] == 1
    assert payload["cleared"] == 2
    assert payload["afterClear"]["activeEntries"] == 0
    assert payload["afterClear"]["clearedOnBoundary"] == 1
    assert payload["afterClear"]["lastClearReason"] == "EMPTY_REPEAT"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_canvas_draws_ask_and_bid_half_cells_even_without_current_book_level() -> None:
    script = r"""
const f=require(process.argv[1]);
const calls=[];
const ctx={
  globalAlpha:1,fillStyle:'',strokeStyle:'',lineWidth:0,
  save(){calls.push({op:'save'});},restore(){calls.push({op:'restore'});},
  fillRect(x,y,w,h){calls.push({op:'fill',x,y,w,h,alpha:this.globalAlpha,color:this.fillStyle});},
  strokeRect(x,y,w,h){calls.push({op:'stroke',x,y,w,h,alpha:this.globalAlpha,color:this.strokeStyle});}
};
const cells=[
  {passiveSide:'ASK',displayBucketIndex:1000,rowIndex:2,opacity:1,hitCount:1},
  {passiveSide:'BID',displayBucketIndex:1000,rowIndex:2,opacity:.5,hitCount:1}
];
let activeCalls=0;
const chart={
  domTradePulseEnabled:true,
  domTradePulses:{now:()=>10,activeCells(){activeCalls+=1;return cells;}}
};
const geometry={domX:100,domMid:150,domWidth:100,top:30,rowHeight:20};
const syncedFrame={book:{synced:true},rows:[{index:1002},{index:1001},{index:1000}],tick:.1,multiplier:1};
f.CanvasChart.prototype.drawDomTradePulses.call(chart,ctx,geometry,syncedFrame);
const syncedCalls=calls.slice();
calls.length=0;
f.CanvasChart.prototype.drawDomTradePulses.call(chart,ctx,geometry,{book:{synced:false}});
process.stdout.write(JSON.stringify({syncedCalls,unsyncedCalls:calls,activeCalls}));
"""
    result = subprocess.run(
        [shutil.which("node"), "-e", script, str(CANVAS_PATH)],
        check=True,
        capture_output=True,
        encoding="utf-8",
    )
    payload = json.loads(result.stdout)
    fills = [call for call in payload["syncedCalls"] if call["op"] == "fill"]
    strokes = [call for call in payload["syncedCalls"] if call["op"] == "stroke"]

    assert len(fills) == 2
    assert len(strokes) == 2
    assert fills[0] == {
        "op": "fill",
        "x": 151,
        "y": 71,
        "w": 48,
        "h": 18,
        "alpha": 0.5,
        "color": "#FFD54A",
    }
    assert fills[1] == {
        "op": "fill",
        "x": 101,
        "y": 71,
        "w": 48,
        "h": 18,
        "alpha": 0.25,
        "color": "#FFD54A",
    }
    assert payload["unsyncedCalls"] == []
    assert payload["activeCalls"] == 1


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_canvas_lifecycle_clears_on_stream_book_fail_closed_and_feature_boundary() -> None:
    script = r"""
const f=require(process.argv[1]);
let now=0;
const chart=Object.create(f.CanvasChart.prototype);
chart.domTradePulseEnabled=true;
chart.domTradePulses=new f.DomTradePulseStore({durationMs:400,maxActive:256,now:()=>now});
chart.domTradePulseFrameHandle=null;
chart.domTradePulseFrameKind=null;
chart.domTradePulseIdentity={symbol:null,streamId:null,mode:null,bookStreamId:'book-a'};
chart.frame={book:{synced:true},tick:.1,multiplier:1,rows:[{index:1000}]};
chart.data={book:{book_stream_id:'book-a',sync_state:'SYNCED'},currentPrice:100};
chart.lock=true;chart.offset=0;chart.dirty=new Set();chart.drawPending=true;
chart.bookOutsideFrame=()=>false;
const invalidations=[];
let schedules=0;
chart.invalidate=layer=>invalidations.push(layer);
chart.scheduleDomTradePulseFrame=()=>{schedules+=1;};

const first=chart.ingestDomTradePulses([{tradeId:'1',price:'100',side:'BUY'}],
  {symbol:'BTCUSDT',streamId:'tape-a'});
now=100;
const coalesced=chart.ingestDomTradePulses([{tradeId:'2',price:'100',side:'BUY'}],
  {symbol:'BTCUSDT',streamId:'tape-a'});
const beforeRestart=chart.getDomTradePulseStats();
const restarted=chart.ingestDomTradePulses([{tradeId:'3',price:'100',side:'SELL'}],
  {symbol:'BTCUSDT',streamId:'tape-b'});
const afterRestart=chart.getDomTradePulseStats();

chart.setData({book:{book_stream_id:'book-b',sync_state:'SYNCED',bids:[],asks:[]}},'liveDom');
const afterBookRestart=chart.getDomTradePulseStats();
chart.frame={book:{synced:true},tick:.1,multiplier:1,rows:[{index:1000}]};
chart.data.book={book_stream_id:'book-b',sync_state:'SYNCED'};
chart.ingestDomTradePulses([{tradeId:'4',price:'100',side:'BUY'}],
  {symbol:'BTCUSDT',streamId:'tape-b'});
chart.setData({book:{book_stream_id:'book-b',sync_state:'STALE',bids:[],asks:[]}},'liveDom');
const afterStale=chart.getDomTradePulseStats();
chart.frame={book:{synced:true},tick:.1,multiplier:1,rows:[{index:1000}]};
chart.data.book={book_stream_id:'book-b',sync_state:'SYNCED'};
chart.ingestDomTradePulses([{tradeId:'5',price:'100',side:'BUY'}],
  {symbol:'BTCUSDT',streamId:'tape-b'});
chart.setDomTradePulseEnabled(false);
const afterDisabled=chart.getDomTradePulseStats();

process.stdout.write(JSON.stringify({
  first,coalesced,beforeRestart,restarted,afterRestart,afterBookRestart,afterStale,afterDisabled,
  invalidations,schedules
}));
"""
    result = subprocess.run(
        [shutil.which("node"), "-e", script, str(CANVAS_PATH)],
        check=True,
        capture_output=True,
        encoding="utf-8",
    )
    payload = json.loads(result.stdout)

    assert payload["first"]["started"] == 1
    assert payload["coalesced"]["coalesced"] == 1
    assert payload["beforeRestart"]["activeEntries"] == 1
    assert payload["restarted"]["started"] == 1
    assert payload["afterRestart"]["activeEntries"] == 1
    assert payload["afterRestart"]["lastClearReason"] == "STREAMID_CHANGE"
    assert payload["afterBookRestart"]["activeEntries"] == 0
    assert payload["afterBookRestart"]["lastClearReason"] == "BOOK_STREAM_RESTART"
    assert payload["afterStale"]["activeEntries"] == 0
    assert payload["afterStale"]["lastClearReason"] == "BOOK_FAIL_CLOSED"
    assert payload["afterDisabled"]["activeEntries"] == 0
    assert payload["afterDisabled"]["enabled"] is False
    assert payload["afterDisabled"]["lastClearReason"] == "FEATURE_DISABLED"
    assert payload["afterDisabled"]["clearedOnBoundary"] == 4
    assert payload["schedules"] == 5
    assert "domTradePulse" in payload["invalidations"]
