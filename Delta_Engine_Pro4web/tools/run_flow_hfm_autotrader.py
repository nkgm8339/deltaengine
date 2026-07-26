"""Run the independent Flow Response -> HFM MT5 execution sidecar."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from contextlib import suppress
from decimal import Decimal
from pathlib import Path

import websockets
from aiohttp import web

from src.execution.flow_hfm_executor import (
    FlowExecutionController,
    JsonlAuditLog,
    Mt5MarketOrderGateway,
)


LOG = logging.getLogger("flow_hfm_autotrader")


DASHBOARD_HTML = r"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DeltaEngine Flow → HFM</title>
<style>
:root{color-scheme:dark;--bg:#071018;--panel:#0d1b27;--line:#20384a;--text:#e8f1f7;--muted:#8fa8b8;--buy:#29d391;--sell:#ff6178;--warn:#ffcc66}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 ui-monospace,SFMono-Regular,Consolas,monospace}
main{max-width:1480px;margin:auto;padding:18px}.top{display:flex;justify-content:space-between;gap:16px;align-items:center;margin-bottom:14px}
h1{font-size:20px;margin:0}.badge{border:1px solid var(--line);border-radius:999px;padding:6px 10px}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px;min-height:100px}
.label{color:var(--muted);font-size:11px;text-transform:uppercase}.value{font-size:19px;margin-top:7px;overflow-wrap:anywhere}
.buy{color:var(--buy)}.sell{color:var(--sell)}.warn{color:var(--warn)}.muted{color:var(--muted)}
table{width:100%;border-collapse:collapse;margin-top:14px;background:var(--panel);font-size:12px}th,td{border-bottom:1px solid var(--line);padding:8px;text-align:left;vertical-align:top}th{color:var(--muted);position:sticky;top:0;background:var(--panel)}
.path{display:flex;gap:6px;align-items:center;margin:14px 0}.node{flex:1;border:1px solid var(--line);background:var(--panel);padding:10px;border-radius:8px;text-align:center}.arrow{color:var(--muted)}
@media(max-width:900px){.grid{grid-template-columns:1fr 1fr}.path{display:grid;grid-template-columns:1fr}.arrow{display:none}}
</style>
</head>
<body><main>
<div class="top"><h1>DeltaEngine — Flow → HFM 自動発注</h1><div id="updated" class="badge">接続中…</div></div>
<div class="path"><div class="node">Flow Response</div><div class="arrow">→</div><div class="node">初回状態遷移</div><div class="arrow">→</div><div class="node">BUY / SELL intent</div><div class="arrow">→</div><div class="node">MT5 check / send</div><div class="arrow">→</div><div class="node">ticket / fill</div></div>
<section class="grid">
  <div class="card"><div class="label">稼働モード</div><div id="mode" class="value">-</div><div id="window" class="muted"></div></div>
  <div class="card"><div class="label">Flow WebSocket</div><div id="upstream" class="value">-</div><div id="upstream-detail" class="muted"></div></div>
  <div class="card"><div class="label">現在のFlow</div><div id="flow" class="value">-</div><div id="flow-detail" class="muted"></div></div>
  <div class="card"><div class="label">直近のMT5結果</div><div id="result" class="value">-</div><div id="ticket" class="muted"></div></div>
</section>
<table><thead><tr><th>時刻</th><th>段階</th><th>状態</th><th>方向</th><th>HFM価格</th><th>結果</th><th>ticket / retcode</th></tr></thead><tbody id="history"></tbody></table>
</main>
<script>
const esc=v=>String(v??"-").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
const cls=v=>String(v).includes("BUY")?"buy":String(v).includes("SELL")?"sell":String(v).includes("REJECT")?"warn":"";
async function refresh(){
 try{
  const r=await fetch("/api/status",{cache:"no-store"}),d=await r.json();
  updated.textContent="更新 "+new Date(d.generated_at).toLocaleTimeString();
  mode.textContent=d.mode.toUpperCase(); mode.className="value "+(d.mode==="live"?"warn":"");
  window.textContent=`対象 window: ${d.window_sec}秒`;
  upstream.textContent=d.upstream?.status??"-"; upstream.className="value "+(d.upstream?.status==="CONNECTED"?"buy":"warn");
  document.getElementById("upstream-detail").textContent=d.upstream?.detail??"";
  flow.textContent=d.latest_flow?.state??"受信待ち"; flow.className="value "+cls(d.latest_flow?.state);
  document.getElementById("flow-detail").textContent=d.latest_flow?`signal ${d.latest_flow.last_price??"-"} / lag ${d.latest_flow.lag_ms??"-"} ms`:"";
  const x=d.latest_execution,algo=d.mt5?.terminal?.trade_allowed;
  result.textContent=x?`${x.stage}: ${x.status}`:`MT5 ${d.mt5?.status??"-"} / ALGO ${algo?"ON":"OFF"}`;
  result.className="value "+(x?cls(x.status):(algo?"buy":"warn"));
  ticket.textContent=x?`order ${x.order_ticket??"-"} / deal ${x.deal_ticket??"-"} / fill ${x.fill_price??"-"}`:`${d.mt5?.account?.server??"-"} / ${d.mt5?.symbol?.name??"-"} / 0.01 lot`;
  history.innerHTML=(d.history??[]).map(x=>`<tr><td>${esc(new Date(x.recorded_at).toLocaleTimeString())}</td><td>${esc(x.stage)}</td><td class="${cls(x.flow_state)}">${esc(x.flow_state)}</td><td class="${cls(x.side??x.mapped_side)}">${esc(x.side??x.mapped_side)}</td><td>${esc(x.fill_price??x.request_price??x.signal_price)}</td><td class="${cls(x.status)}">${esc(x.status)}</td><td>${esc(x.order_ticket??"-")} / ${esc(x.retcode??x.check?.retcode??"-")}</td></tr>`).join("");
 }catch(e){updated.textContent="dashboard error: "+e}
}
setInterval(refresh,500);refresh();
</script></body></html>"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", default="ws://127.0.0.1:18080/ws")
    parser.add_argument("--window-sec", type=int, default=30)
    parser.add_argument(
        "--mode",
        choices=("observe", "check"),
        default="check",
        help="Flow-only LIVE mode is retired and intentionally unavailable",
    )
    parser.add_argument("--symbol", default="#BTCUSDr")
    parser.add_argument("--volume", type=Decimal, default=Decimal("0.01"))
    parser.add_argument(
        "--terminal-path",
        default=r"C:\Program Files\HFM Metatrader 5\terminal64.exe",
    )
    parser.add_argument("--deviation-points", type=int, default=5000)
    parser.add_argument("--magic", type=int, default=520260726)
    parser.add_argument(
        "--audit",
        type=Path,
        default=Path("data_05M/execution/flow_hfm_execution.jsonl"),
    )
    parser.add_argument("--dashboard-host", default="127.0.0.1")
    parser.add_argument("--dashboard-port", type=int, default=18081)
    parser.add_argument("--log-level", default="INFO")
    return parser


async def upstream_loop(controller: FlowExecutionController, url: str) -> None:
    while True:
        try:
            controller.set_upstream("CONNECTING", url)
            async with websockets.connect(
                url,
                ping_interval=20,
                ping_timeout=20,
                open_timeout=10,
                max_size=2**22,
            ) as websocket:
                controller.set_upstream("CONNECTED", url)
                await websocket.send("FLOW_HFM_EXECUTOR_READY")
                async for raw in websocket:
                    try:
                        envelope = json.loads(raw)
                    except json.JSONDecodeError as exc:
                        controller.set_upstream("MESSAGE_ERROR", str(exc))
                        continue
                    records = await asyncio.to_thread(controller.handle_envelope, envelope)
                    for record in records:
                        LOG.info(
                            "%s | %s | flow=%s | side=%s | status=%s | ticket=%s | fill=%s",
                            record.get("recorded_at"),
                            record.get("stage"),
                            record.get("flow_state"),
                            record.get("side") or record.get("mapped_side"),
                            record.get("status"),
                            record.get("order_ticket"),
                            record.get("fill_price"),
                        )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            controller.set_upstream("DISCONNECTED", f"{type(exc).__name__}: {exc}")
            LOG.warning("upstream disconnected: %s", exc)
            await asyncio.sleep(2)


def make_app(controller: FlowExecutionController) -> web.Application:
    app = web.Application()

    async def index(_request: web.Request) -> web.Response:
        return web.Response(text=DASHBOARD_HTML, content_type="text/html")

    async def status(_request: web.Request) -> web.Response:
        return web.json_response(controller.snapshot())

    app.router.add_get("/", index)
    app.router.add_get("/api/status", status)
    return app


async def run(args: argparse.Namespace) -> None:
    gateway = Mt5MarketOrderGateway(
        terminal_path=args.terminal_path,
        symbol=args.symbol,
        volume=args.volume,
        deviation_points=args.deviation_points,
        magic=args.magic,
    )
    controller = FlowExecutionController(
        window_sec=args.window_sec,
        mode=args.mode,
        gateway=gateway,
        audit=JsonlAuditLog(args.audit),
    )
    mt5_status = await asyncio.to_thread(controller.inspect_mt5)
    LOG.info(
        "MT5 inspect: status=%s terminal_trade_allowed=%s account_trade_allowed=%s",
        mt5_status.get("status"),
        (mt5_status.get("terminal") or {}).get("trade_allowed"),
        (mt5_status.get("account") or {}).get("trade_allowed"),
    )

    app = make_app(controller)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, args.dashboard_host, args.dashboard_port)
    await site.start()
    LOG.info(
        "dashboard http://%s:%s | upstream=%s | mode=%s | window=%ss | %s %s",
        args.dashboard_host,
        args.dashboard_port,
        args.upstream,
        args.mode,
        args.window_sec,
        args.symbol,
        args.volume,
    )

    upstream_task = asyncio.create_task(upstream_loop(controller, args.upstream))
    try:
        await asyncio.Future()
    finally:
        upstream_task.cancel()
        with suppress(asyncio.CancelledError):
            await upstream_task
        await runner.cleanup()


def main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
