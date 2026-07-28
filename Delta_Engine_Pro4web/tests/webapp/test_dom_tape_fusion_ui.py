"""Phase 5 fused LIVE DOM and virtualized Time & Sales frontend contracts."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).parents[2]
HTML_PATH = ROOT / "webapp" / "static" / "index.html"
CANVAS_PATH = ROOT / "webapp" / "static" / "footprint_canvas.js"
TAPE_PATH = ROOT / "webapp" / "static" / "time_sales.js"


def test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")

    assert '<script src="/static/time_sales.js"></script>' in html
    assert "const PHASE5_FUSION_ENABLED = true;" in html
    assert 'id="fpdomstatus"' in html
    assert 'id="tape" class="panel"' in html
    assert 'id="tapeviewport" tabindex="0" role="grid"' in html
    assert 'id="tapedetail" role="status" aria-live="polite"' in html
    assert 'id="tapefilterstate"' in html
    assert 'id="tapegap"' in html
    assert 'id="tapecount"' in html
    assert 'body.phase5-fusion #right>#left{display:none!important}' in html
    assert "if(flowTop&&appgrid){appgrid.appendChild(flowTop)" in html
    assert "mainCol.insertBefore(flowTop,centerCol)" not in html
    assert "if(flowTop&&absPanel){flowTop.appendChild(absPanel)" in html
    assert "if(flowTop&&imbPanel){flowTop.appendChild(imbPanel)" in html
    assert "body.phase5-fusion #main{grid-template-columns:minmax(0,1fr) 232px!important" in html
    assert "body.phase5-fusion #flowtop{grid-column:1 / -1;grid-row:4" in html
    assert "grid-template-rows:198px 178px" in html
    assert "body.phase5-fusion #flowtop>#alerthist{grid-column:3;display:flex!important" in html


def test_alert_toasts_stay_out_of_the_trading_screen_center() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")

    assert "#toasts{position:fixed;top:auto;right:14px;bottom:14px;left:auto;transform:none" in html
    assert "width:min(340px,calc(100vw - 28px));pointer-events:none" in html
    assert "#toasts{position:fixed;top:56px;left:50%" not in html


def test_book_and_tape_messages_are_wired_without_using_latest_tick_as_tape() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")

    assert 'case "BOOK_UPDATE": if(PHASE5_FUSION_ENABLED)onBookUpdate(p); break;' in html
    assert 'case "TAPE_UPDATE": if(PHASE5_FUSION_ENABLED)onTapeUpdate(m,p); break;' in html
    assert "TAPE_UI.ingestBatch(p,m.symbol||S.symbol);" in html
    assert "loadTimeSalesHistory()" in html
    assert "api/history/time-sales" in html
    assert "TAPE_UI.mergeHistory(rows,S.symbol)" in html
    tick_body = html.split("function onTick(m,p){", 1)[1].split("function onBookUpdate", 1)[0]
    assert "TAPE_UI" not in tick_body


def test_canvas_uses_one_geometry_for_footprint_and_live_dom_dirty_layer() -> None:
    source = CANVAS_PATH.read_text(encoding="utf-8")

    assert "function prepareBook" in source
    assert 'dirtyLayer === "liveDom"' in source
    assert 'layer === "liveDom"' in source
    assert "const domX = axisWidth + plotWidth" in source
    assert "this.frame.book.byIndex.get(row.index)" in source
    assert 'return { area: "dom"' in source
    assert "PASSIVE BID" in source
    assert "book.bestBidIndex" in source
    assert "book.bidWall" in source
    assert "this.onSelection(this.selectionPayload(hit))" in source
    assert "selectTrade(trade)" in source


def test_time_sales_keeps_500_data_items_but_reuses_only_20_to_40_rows() -> None:
    source = TAPE_PATH.read_text(encoding="utf-8")

    assert "const DEFAULT_CAPACITY = 500" in source
    assert "const DEFAULT_POOL_SIZE = 32" in source
    assert "this.rowHeight = Math.max(28" in source
    html = HTML_PATH.read_text(encoding="utf-8")
    assert "rowHeight:28" in html
    assert "height:28px;padding:0 5px" in html
    assert 'font:800 14px "Cascadia Mono"' in html
    assert "this.poolSize = clamp" in source
    assert "this.store.filtered(this.filters).slice().reverse()" in source
    assert "this.rowsElement.appendChild(row)" in source
    assert "this.pool[poolIndex]" in source
    assert "this.store.trades.length" in source
    assert "this.filters.largeOnly" in source
    assert 'row.className = `tape-row' in source


def test_phase5_does_not_change_completed_three_stage_chart_geometry() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")

    assert 'const MC={W:1200,H:500' in html
    assert '<text x="28" y="335"' in html
    assert '<text x="28" y="454"' in html
    assert '#bottom.market-chart-panel{height:594px;min-height:594px;flex:0 0 594px' in html


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_passive_depth_bucket_best_wall_and_fail_closed_are_deterministic() -> None:
    script = r"""
const f=require(process.argv[1]);
const synced=f.prepareBook({sync_state:'SYNCED',bids:[{price:'100.0',qty:'2'},{price:'99.9',qty:'5'}],
  asks:[{price:'100.1',qty:'3'},{price:'100.2',qty:'7'}],best_bid:'100.0',best_ask:'100.1',spread:'0.1',age_ms:40,last_update_id:9},.1,2);
const stale=f.prepareBook({sync_state:'STALE',bids:[{price:'100',qty:'99'}],asks:[{price:'101',qty:'88'}]},.1,2);
process.stdout.write(JSON.stringify({state:synced.state,levels:synced.levels,bestBid:synced.bestBidIndex,
  bestAsk:synced.bestAskIndex,bidWall:synced.bidWall,askWall:synced.askWall,spread:synced.spread,
  staleState:stale.state,staleLevels:stale.levels,tf:f.timeframeMilliseconds('5m')}));
"""
    result = subprocess.run(
        [shutil.which("node"), "-e", script, str(CANVAS_PATH)],
        check=True,
        capture_output=True,
        encoding="utf-8",
    )
    payload = json.loads(result.stdout)
    assert payload == {
        "state": "SYNCED",
        "levels": [
            {"index": 1002, "price": 100.2, "bid": 0, "ask": 7},
            {"index": 1000, "price": 100, "bid": 2, "ask": 3},
            {"index": 998, "price": 99.8, "bid": 5, "ask": 0},
        ],
        "bestBid": 1000,
        "bestAsk": 1000,
        "bidWall": 998,
        "askWall": 1002,
        "spread": 0.1,
        "staleState": "STALE",
        "staleLevels": [],
        "tf": 300000,
    }


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_tape_history_live_dedup_sequence_gap_restart_and_filters() -> None:
    script = r"""
const t=require(process.argv[1]);
const store=new t.TapeStore({capacity:500});
store.mergeHistory([
  {trade_id:1,symbol:'BTCUSDT',event_time:'2026-07-28T08:00:00.001Z',price:'100',quantity:'1',notional:'100',side:'BUY'},
  {trade_id:2,symbol:'BTCUSDT',event_time:'2026-07-28T08:00:00.002Z',price:'101',quantity:'2',notional:'202',side:'SELL'}
],'BTCUSDT');
const first=store.ingestBatch({stream_id:'stream-a',first_sequence:10,last_sequence:11,accepted_count:2,dropped_count:0,trades:[
  {sequence:10,trade_id:2,event_time:'2026-07-28T08:00:00.002Z',price:'101',quantity:'2',notional:'202',side:'SELL'},
  {sequence:11,trade_id:3,event_time:'2026-07-28T08:00:00.003Z',price:'102',quantity:'3',notional:'306',side:'BUY'}
]},'BTCUSDT');
const gap=store.ingestBatch({stream_id:'stream-a',first_sequence:13,last_sequence:13,accepted_count:1,dropped_count:1,trades:[
  {sequence:13,trade_id:4,event_time:'2026-07-28T08:00:00.004Z',price:'103',quantity:'4',notional:'412',side:'SELL'}
]},'BTCUSDT');
const restart=store.ingestBatch({stream_id:'stream-b',first_sequence:50,last_sequence:50,accepted_count:1,dropped_count:0,trades:[
  {sequence:50,trade_id:5,event_time:'2026-07-28T08:00:00.005Z',price:'104',quantity:'5',notional:'520',side:'BUY'}
]},'BTCUSDT');
const filtered=store.filtered({side:'BUY',minimumQuantity:3,minimumNotional:300,largeOnly:true,largeThreshold:500});
process.stdout.write(JSON.stringify({first,gap,restart,count:store.trades.length,keys:store.trades.map(x=>x.tradeId),
  expected:store.expectedSequence,storeGap:store.gap,restarts:store.restartCount,dropped:store.droppedCount,
  filtered:filtered.map(x=>x.tradeId),clock:t.jstClock('2026-07-28T08:00:00.001Z','millisecond')}));
"""
    result = subprocess.run(
        [shutil.which("node"), "-e", script, str(TAPE_PATH)],
        check=True,
        capture_output=True,
        encoding="utf-8",
    )
    payload = json.loads(result.stdout)
    assert payload["first"] == {"added": 1, "restart": False, "gap": False, "reasons": []}
    assert payload["gap"]["gap"] is True
    assert "EXPECTED 12 GOT 13" in payload["gap"]["reasons"]
    assert "DROPPED 1" in payload["gap"]["reasons"]
    assert payload["restart"] == {"added": 1, "restart": True, "gap": False, "reasons": []}
    assert payload["count"] == 5
    assert payload["keys"] == ["1", "2", "3", "4", "5"]
    assert payload["expected"] == 51
    assert payload["storeGap"] is False
    assert payload["restarts"] == 1
    assert payload["dropped"] == 1
    assert payload["filtered"] == ["5"]
    assert payload["clock"] == "17:00:00.001"
