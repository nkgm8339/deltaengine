import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "webapp" / "static" / "orderbook_heatmap.js"


def run_node(script):
    result = subprocess.run(["node", "-e", script], cwd=ROOT, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def test_heatmap_core_contracts():
    script = f"""
const h=require("./webapp/static/orderbook_heatmap.js");
const id='123e4567-e89b-12d3-a456-426614174000';
const base={{book_stream_id:id,event_time:'2026-07-29T00:00:00Z',projection_time:'2026-07-29T00:00:00Z',last_update_id:1,depth_levels:2,sync_state:'SYNCED',bids:[{{price:'100',qty:'2'}},{{price:'99',qty:'1'}}],asks:[{{price:'101',qty:'3'}},{{price:'102',qty:'1'}}],best_bid:'100',best_ask:'101',spread:'1'}};
const invalid=h.validateBookPayload({{...base,best_ask:'100'}});
const s=new h.HeatmapBookStore({{maxAgeMs:1000,maxFrames:2}});
const a=s.ingest({{...base,book_sequence:1}},Date.parse(base.event_time));
const gap=s.ingest({{...base,book_sequence:3}},Date.parse(base.event_time)+100);
const b=h.bucketBookFrame(base,1,1);
const scale=h.computeHeatScale(b);
const bubbles=h.aggregateTradeBubbles([{{stream_id:'stream-a',trade_id:'1',sequence:1,event_time:base.event_time,price:'100',quantity:'2',notional:'200',side:'BUY'}},{{stream_id:'stream-a',trade_id:'2',sequence:2,event_time:base.event_time,price:'100',quantity:'1',notional:'100',side:'BUY'}}],1,1,0);
console.log(JSON.stringify({{invalid:invalid.valid,accepted:a.accepted,gap:s.gap.reason,frames:s.frames.length,bucket:b.length,q95:scale.q95,bubbleCount:bubbles[0].count}}));
"""
    result = run_node(script)
    assert result == {"invalid": False, "accepted": True, "gap": "BOOK DELIVERY GAP", "frames": 2, "bucket": 4, "q95": 3, "bubbleCount": 2}





def test_heatmap_max_load_is_bounded_and_reconnect_safe():
    script = r'''
const h=require("./webapp/static/orderbook_heatmap.js");
const id="123e4567-e89b-12d3-a456-426614174000";
const start=Date.now(); const book=new h.HeatmapBookStore({maxFrames:9000,maxAgeMs:900000});
for(let i=1;i<=9000;i++){const t=start+i*50; book.ingest({book_stream_id:id,book_sequence:i,event_time:new Date(t).toISOString(),projection_time:new Date(t).toISOString(),last_update_id:i,depth_levels:2,sync_state:"SYNCED",bids:[{price:"100",qty:"1"},{price:"99",qty:"2"}],asks:[{price:"101",qty:"3"},{price:"102",qty:"4"}],best_bid:"100",best_ask:"101",spread:"1"},t);}
const trades=new h.HeatmapTradeStore({capacity:100000,maxAgeMs:900000}); const rows=[];
for(let i=1;i<=100000;i++) rows.push({stream_id:"stream-a",trade_id:String(i),sequence:i,event_time:new Date(start+i*5).toISOString(),price:"100",quantity:"1",notional:"100",side:i%2?"BUY":"SELL"});
const result=trades.ingest(rows,start+500000); const framesBeforeRestart=book.frames.length; const restart=book.ingest({...({book_stream_id:"223e4567-e89b-12d3-a456-426614174000",book_sequence:1,event_time:new Date(start+500100).toISOString(),projection_time:new Date(start+500100).toISOString(),last_update_id:1,depth_levels:1,sync_state:"SYNCED",bids:[{price:"100",qty:"1"}],asks:[{price:"101",qty:"1"}],best_bid:"100",best_ask:"101",spread:"1"})},start+500100);
console.log(JSON.stringify({frames:framesBeforeRestart,trades:trades.trades.length,added:result.added,retention:trades.retentionLimited,restart:restart.accepted,restarts:book.restartCount}));
'''
    result = run_node(script)
    assert result == {"frames": 9000, "trades": 100000, "added": 100000, "retention": False, "restart": True, "restarts": 1}


def test_heatmap_duration_weighting_gap_and_side_separation():
    script = r'''
const h=require("./webapp/static/orderbook_heatmap.js");
const columns=h.buildTimeColumns([],0,10,1);
const intervals=[
  {start:0,end:4,cells:[{side:"BID",index:100,quantity:10,level_count:1},{side:"ASK",index:101,quantity:30,level_count:1}]},
  {start:4,end:10,cells:[{side:"BID",index:100,quantity:20,level_count:1},{side:"ASK",index:101,quantity:40,level_count:1}]},
];
const cells=h.durationWeightedCells(intervals,columns,[{start:2,end:4,reason:"GAP"}])[0];
const values=Object.fromEntries(cells.map(cell=>[cell.side,cell.quantity]));
console.log(JSON.stringify({bid:values.BID,ask:values.ASK,count:cells.length}));
'''
    result = run_node(script)
    assert result == {"bid": 17.5, "ask": 37.5, "count": 2}


def test_heatmap_book_gap_keeps_history_and_recovers_without_carry_forward():
    script = r'''
const h=require("./webapp/static/orderbook_heatmap.js");
const id="123e4567-e89b-12d3-a456-426614174000";
const frame=(seq,time)=>({book_stream_id:id,book_sequence:seq,event_time:new Date(time).toISOString(),projection_time:new Date(time).toISOString(),last_update_id:seq,depth_levels:1,sync_state:"SYNCED",bids:[{price:"100",qty:"2"}],asks:[{price:"101",qty:"3"}],best_bid:"100",best_ask:"101",spread:"1"});
const store=new h.HeatmapBookStore({maxAgeMs:60000,maxFrames:10});
store.ingest(frame(1,1000),1000);
store.ingest({book_stream_id:id,book_sequence:2,event_time:new Date(2000).toISOString(),projection_time:new Date(2000).toISOString(),last_update_id:2,depth_levels:1,sync_state:"STALE",bids:[],asks:[],best_bid:null,best_ask:null,spread:null},2000);
const during={frames:store.frames.length,active:store.activeGap.reason};
store.ingest(frame(3,3000),3000);
console.log(JSON.stringify({during,frames:store.frames.length,active:store.activeGap,gap:store.gaps[0]}));
'''
    result = run_node(script)
    assert result["during"] == {"frames": 1, "active": "BOOK STALE"}
    assert result["frames"] == 2
    assert result["active"] is None
    assert result["gap"]["start"] == 2000
    assert result["gap"]["end"] == 3000


def test_heatmap_accepts_authoritative_normalized_time_sales_shape():
    script = r'''
const h=require("./webapp/static/orderbook_heatmap.js");
const store=new h.HeatmapTradeStore({maxAgeMs:60000,capacity:10});
const result=store.ingest([{tradeId:"77",sequence:9,eventTime:1000,price:"100.5",quantity:"2",notional:"201",side:"BUY"}],1000,{streamId:"tape-stream"});
const trade=store.trades[0];
console.log(JSON.stringify({added:result.added,streamId:trade.streamId,tradeId:trade.tradeId,eventTime:trade.eventTime}));
'''
    result = run_node(script)
    assert result == {"added": 1, "streamId": "tape-stream", "tradeId": "77", "eventTime": 1000}

