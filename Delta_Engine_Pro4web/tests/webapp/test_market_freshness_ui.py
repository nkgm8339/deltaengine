from __future__ import annotations

import asyncio
import json
import subprocess
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from webapp.push_broker import PushBroker


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "webapp" / "static" / "market_freshness.js"
INDEX = ROOT / "webapp" / "static" / "index.html"


def run_node(script: str) -> dict:
    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_live_guard_keeps_live_without_ticks_while_heartbeats_continue():
    result = run_node(
        r'''
const {MarketHeartbeatGuard}=require("./webapp/static/market_freshness.js");
let mono=0,wall=Date.parse("2026-08-03T00:00:00.000Z");
const guard=new MarketHeartbeatGuard({
  now:()=>mono,wallNow:()=>wall,maxTransportAgeMs:2000,maxSourceAgeMs:5000,
});
guard.socketOpen();
guard.configureHello({mode:"live",intervalMs:1000,timeoutMs:3000});
guard.acceptHeartbeat({mode:"live",sequence:1,upstreamFresh:true,pipelineAlive:true});
const tick=guard.acceptTick({publishedTime:new Date(wall-100).toISOString(),sourceAgeMs:25});
for(let sequence=2;sequence<=12;sequence+=1){mono+=1000;guard.acceptHeartbeat({mode:"live",sequence,upstreamFresh:true,pipelineAlive:true});guard.check();}
console.log(JSON.stringify({tick:tick.accepted,total:tick.snapshot.totalAgeMs,state:guard.snapshot().state,reason:guard.snapshot().reason,lastTickAt:guard.snapshot().lastAcceptedAt,lastHeartbeatSequence:guard.snapshot().lastHeartbeatSequence}));
'''
    )
    assert result == {
        "tick": True,
        "total": 125,
        "state": "LIVE",
        "reason": "FRESH_HEARTBEAT",
        "lastTickAt": 1785715200000,
        "lastHeartbeatSequence": 12,
    }


def test_live_guard_tolerates_heartbeat_drop_uses_monotonic_and_never_closes_transport():
    result = run_node(
        r'''
const {MarketHeartbeatGuard}=require("./webapp/static/market_freshness.js");
let mono=0,wall=Date.parse("2026-08-03T00:00:00.000Z"),transportCloses=0;
const guard=new MarketHeartbeatGuard({now:()=>mono,wallNow:()=>wall,onReconnect:()=>{transportCloses+=1;}});
guard.socketOpen();guard.configureHello({mode:"live",intervalMs:1000,timeoutMs:3000});
guard.acceptHeartbeat({mode:"live",sequence:1,upstreamFresh:true,pipelineAlive:true});
guard.acceptTick({publishedTime:new Date(wall).toISOString(),sourceAgeMs:0});
mono+=2000;guard.check();const afterDrop=guard.snapshot().state;
wall+=300000;guard.acceptHeartbeat({mode:"live",sequence:2,upstreamFresh:true,pipelineAlive:true});const afterWallSkew=guard.snapshot().state;
wall-=600000;mono+=500;guard.acceptHeartbeat({mode:"live",sequence:3,upstreamFresh:true,pipelineAlive:true});const afterNegativeWallSkew=guard.snapshot().state;
mono+=3001;guard.check();
console.log(JSON.stringify({afterDrop,afterWallSkew,afterNegativeWallSkew,state:guard.snapshot().state,reason:guard.snapshot().reason,transportCloses}));
'''
    )
    assert result == {
        "afterDrop": "LIVE",
        "afterWallSkew": "LIVE",
        "afterNegativeWallSkew": "LIVE",
        "state": "STALE",
        "reason": "HEARTBEAT_TIMEOUT",
        "transportCloses": 0,
    }


def test_live_guard_fails_closed_for_upstream_or_pipeline_and_recovers_in_order():
    result = run_node(
        r'''
const {MarketHeartbeatGuard}=require("./webapp/static/market_freshness.js");
let mono=0,wall=Date.parse("2026-08-03T00:00:00.000Z");
const make=()=>{const g=new MarketHeartbeatGuard({now:()=>mono,wallNow:()=>wall});g.socketOpen();g.configureHello({mode:"live",intervalMs:1000,timeoutMs:3000});return g;};
const upstream=make();upstream.acceptHeartbeat({mode:"live",sequence:1,upstreamFresh:false,pipelineAlive:true});
const pipeline=make();pipeline.acceptHeartbeat({mode:"live",sequence:1,upstreamFresh:true,pipelineAlive:false});
const recovery=make();recovery.acceptHeartbeat({mode:"live",sequence:1,upstreamFresh:true,pipelineAlive:true});recovery.acceptTick({publishedTime:new Date(wall).toISOString(),sourceAgeMs:0});
mono+=3001;recovery.check();const tickBeforeHeartbeat=recovery.acceptTick({publishedTime:new Date(wall).toISOString(),sourceAgeMs:0});
const heartbeat=recovery.acceptHeartbeat({mode:"live",sequence:2,upstreamFresh:true,pipelineAlive:true});const syncing=recovery.snapshot().state;
const tick=recovery.acceptTick({publishedTime:new Date(wall).toISOString(),sourceAgeMs:0});
console.log(JSON.stringify({upstream:upstream.snapshot().reason,pipeline:pipeline.snapshot().reason,tickBeforeHeartbeat:tickBeforeHeartbeat.reason,heartbeat:heartbeat.accepted,syncing,tick:tick.accepted,state:recovery.snapshot().state}));
'''
    )
    assert result == {
        "upstream": "UPSTREAM_NOT_FRESH",
        "pipeline": "PIPELINE_NOT_ALIVE",
        "tickBeforeHeartbeat": "WAITING_FOR_FRESH_HEARTBEAT",
        "heartbeat": True,
        "syncing": "SYNCING",
        "tick": True,
        "state": "LIVE",
    }


def test_live_guard_rejects_mode_mismatch_and_disables_timeout_in_replay():
    result = run_node(
        r'''
const {MarketHeartbeatGuard}=require("./webapp/static/market_freshness.js");
let mono=0;
const replay=new MarketHeartbeatGuard({now:()=>mono});replay.socketOpen();replay.configureHello({mode:"replay",intervalMs:1000,timeoutMs:3000});
const rejected=replay.acceptHeartbeat({mode:"live",sequence:1,upstreamFresh:true,pipelineAlive:true});mono+=10000;replay.check();
const live=new MarketHeartbeatGuard({now:()=>mono});live.socketOpen();live.configureHello({mode:"live",intervalMs:1000,timeoutMs:3000});
const mismatch=live.acceptHeartbeat({mode:"replay",sequence:1,upstreamFresh:true,pipelineAlive:true});
console.log(JSON.stringify({replayState:replay.snapshot().state,rejected:rejected.reason,liveState:live.snapshot().state,mismatch:mismatch.reason}));
'''
    )
    assert result == {
        "replayState": "REPLAY",
        "rejected": "HEARTBEAT_MODE_MISMATCH",
        "liveState": "SYNCING",
        "mismatch": "HEARTBEAT_MODE_MISMATCH",
    }


def test_tick_metadata_remains_fail_closed_but_spot_uses_independent_event_guard():
    result = run_node(
        r'''
const {MarketHeartbeatGuard,MarketFreshnessGuard}=require("./webapp/static/market_freshness.js");
let mono=0,wall=Date.parse("2026-08-03T00:00:00.000Z");
const live=new MarketHeartbeatGuard({now:()=>mono,wallNow:()=>wall,maxTransportAgeMs:2000});live.socketOpen();live.configureHello({mode:"live",intervalMs:1000,timeoutMs:3000});live.acceptHeartbeat({mode:"live",sequence:1,upstreamFresh:true,pipelineAlive:true});
const cached=live.acceptTick({publishedTime:new Date(wall-60000).toISOString(),sourceAgeMs:10});live.acceptHeartbeat({mode:"live",sequence:2,upstreamFresh:true,pipelineAlive:true});const nullAge=live.acceptTick({publishedTime:new Date(wall).toISOString(),sourceAgeMs:null});
let spotNow=wall;const spot=new MarketFreshnessGuard({now:()=>spotNow,staleAfterMs:5000});spot.socketOpen();const spotAccepted=spot.acceptTick({publishedTime:new Date(spotNow).toISOString(),sourceAgeMs:0});spotNow+=5001;spot.check();
console.log(JSON.stringify({cached:cached.reason,nullAge:nullAge.reason,liveState:live.snapshot().state,spotAccepted:spotAccepted.accepted,spotState:spot.snapshot().state,spotReason:spot.snapshot().reason}));
'''
    )
    assert result == {
        "cached": "TICK_TRANSPORT_STALE",
        "nullAge": "TICK_FRESHNESS_METADATA_INVALID",
        "liveState": "STALE",
        "spotAccepted": True,
        "spotState": "STALE",
        "spotReason": "EVENT_TIMEOUT",
    }


def test_tick_payload_has_freshness_metadata_and_late_browser_gets_latest_tick():
    async def run():
        broker = PushBroker("BTCUSDT")
        event_time = datetime.now(timezone.utc) - timedelta(milliseconds=100)
        first = SimpleNamespace(
            event_time=event_time,
            trade_id=1001,
            price=Decimal("63450.0"),
            quantity=Decimal("0.01"),
            side="BUY",
        )
        second = SimpleNamespace(
            event_time=event_time + timedelta(milliseconds=10),
            trade_id=1002,
            price=Decimal("63450.1"),
            quantity=Decimal("0.02"),
            side="SELL",
        )
        await broker.on_trade(first)
        await broker.on_trade(second)

        received = []
        ws = MagicMock()
        ws.send_text = AsyncMock(side_effect=lambda text: received.append(json.loads(text)))
        await broker.register(ws)

        assert broker.client_count == 1
        assert len(received) == 1
        message = received[0]
        assert message["type"] == "TICK"
        assert message["payload"]["trade_id"] == 1002
        assert message["payload"]["price"] == "63450.1"
        assert datetime.fromisoformat(message["payload"]["published_time"]).tzinfo is not None
        assert isinstance(message["payload"]["source_age_ms"], int)
        assert message["payload"]["source_age_ms"] >= 0

    asyncio.run(run())


def test_failed_cached_tick_send_does_not_register_client():
    async def run():
        broker = PushBroker("BTCUSDT")
        await broker.on_trade(SimpleNamespace(
            event_time=datetime.now(timezone.utc),
            trade_id=1,
            price=Decimal("1"),
            quantity=Decimal("1"),
            side="BUY",
        ))
        ws = MagicMock()
        ws.send_text = AsyncMock(side_effect=RuntimeError("closed"))
        await broker.register(ws)
        assert broker.client_count == 0

    asyncio.run(run())


def test_slow_client_is_timed_out_without_blocking_healthy_client():
    async def run():
        broker = PushBroker("BTCUSDT", client_send_timeout_sec=0.02)
        never = asyncio.Event()

        slow_ws = MagicMock()

        async def blocked_send(_text):
            await never.wait()

        slow_ws.send_text = AsyncMock(side_effect=blocked_send)
        healthy_messages = []
        healthy_ws = MagicMock()
        healthy_ws.send_text = AsyncMock(side_effect=healthy_messages.append)

        await broker.register(slow_ws)
        await broker.register(healthy_ws)
        await asyncio.wait_for(
            broker.on_trade(SimpleNamespace(
                event_time=datetime.now(timezone.utc),
                trade_id=2001,
                price=Decimal("63450.0"),
                quantity=Decimal("0.01"),
                side="BUY",
            )),
            timeout=0.2,
        )
        await broker.wait_until_idle()

        assert len(healthy_messages) == 1
        assert json.loads(healthy_messages[0])["type"] == "TICK"
        assert slow_ws not in broker._clients
        assert healthy_ws in broker._clients

    asyncio.run(run())


def test_hanging_cached_send_does_not_hold_broker_locks():
    async def run():
        broker = PushBroker("BTCUSDT", client_send_timeout_sec=0.02)
        await broker.on_trade(SimpleNamespace(
            event_time=datetime.now(timezone.utc),
            trade_id=3001,
            price=Decimal("63450.0"),
            quantity=Decimal("0.01"),
            side="BUY",
        ))

        never = asyncio.Event()
        slow_ws = MagicMock()

        async def blocked_send(_text):
            await never.wait()

        slow_ws.send_text = AsyncMock(side_effect=blocked_send)
        await asyncio.wait_for(broker.register(slow_ws), timeout=0.2)
        assert slow_ws not in broker._clients

        healthy_messages = []
        healthy_ws = MagicMock()
        healthy_ws.send_text = AsyncMock(side_effect=healthy_messages.append)
        await asyncio.wait_for(broker.register(healthy_ws), timeout=0.2)
        assert healthy_ws in broker._clients
        assert json.loads(healthy_messages[0])["type"] == "TICK"

    asyncio.run(run())


def test_html_uses_freshness_guard_for_every_live_price_projection():
    html = INDEX.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")
    assert '<script src="/static/market_freshness.js"></script>' in html
    assert 'id="freshnessbanner"' in html
    assert "setInterval(()=>{MARKET_FRESHNESS.check();SPOT_FRESHNESS.check();},250)" in html
    assert "new MARKET_FRESHNESS_ID.MarketHeartbeatGuard" in html
    assert "MARKET_FRESHNESS.configureHello({" in html
    assert 'case "MARKET_HEARTBEAT": onMarketHeartbeat(p); break;' in html
    assert "staleAfterMs:2000" not in html
    assert "TICK_TIMEOUT" not in module
    assert "if(S.marketFresh&&S.price==null" in html
    assert "currentPrice:S.marketFresh?S.price:null" in html
    assert "getLastPrice:()=>S.marketFresh?S.price:null" in html
    assert "if(!S.marketFresh)return;" in html
    assert "if(!S.marketFresh||!TAPE_UI)return;" not in html
    assert "if(!S.wsTransportOpen||!TAPE_UI)return;" in html
    assert "const currentPrice=S.marketFresh?S.price:null;" in html
    assert "S.price??(bar?bar.c:null)" not in html
    assert "onReconnect:" not in html
    render = html.split("function renderMarketFreshness(snapshot){", 1)[1].split("function renderSpotFreshness", 1)[0]
    assert "TAPE_UI.setConnected" not in render
    assert "HEATMAP_UI.setConnected" not in render
    book = html.split("function onBookUpdate(p){", 1)[1].split("function onTapeUpdate", 1)[0]
    assert "S.marketFresh" not in book
    assert "ws.onopen=()=>{setRealtimeTransportConnected(true)" in html
    assert "ws.onclose=()=>{setRealtimeTransportConnected(false)" in html
