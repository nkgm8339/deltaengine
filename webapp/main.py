"""DeltaEngine WebApp — FastAPI + WebSocket。

起動: uvicorn webapp.main:app  /  docker-compose up
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.config import load_config
from src.pipeline import LivePipeline, ReplayPipeline, load_profile
from src.monitor.health import HealthMonitor, HealthSnapshot, read_rss_mb
from webapp.push_broker import IntervalGate, PushBroker, PAYLOAD_VERSION
from webapp.oi_poller import oi_polling_loop
from webapp.version import resolve_version

logger = logging.getLogger("webapp.main")

_CONFIG_PATH = "config/config.yaml"
_STATIC_DIR = Path(__file__).parent / "static"



_TF_SEC = {"1s": 1, "1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}


def _timeframe_sec(tf: str) -> int:
    return _TF_SEC.get(tf, 60)


def _profile_path(config) -> str:
    return f"config/profiles/{config.normalizer.exchange_profile}.yaml"


def _config_to_dict(node) -> Any:
    if hasattr(node, "_data"):
        return {k: _config_to_dict(v) for k, v in node._data.items()}
    return node


def _build_broker(config) -> PushBroker:
    w = config.webapp
    return PushBroker(
        symbol=config.market.symbol,
        depth_levels=w.depth_levels,
        flow_window_sec=w.flow_window_sec,
        confluence_score_threshold=Decimal(str(w.confluence.score_threshold)),
        confluence_strength_threshold=Decimal(str(w.confluence.strength_threshold)),
    )


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.version = resolve_version()
    config = load_config(_CONFIG_PATH)
    profile = load_profile(_profile_path(config))
    broker = _build_broker(config)

    if config.replay.enabled:
        pipeline = ReplayPipeline.from_config(
            config, profile,
            parquet_path=config.database.parquet_path,
            duckdb_path=config.database.duckdb_path,
        )
    else:
        pipeline = LivePipeline.from_config(config, profile)

    # ── hooks ────────────────────────────────────────────────────────────────

    bar_update_gate = IntervalGate(config.webapp.bar_update_interval_sec)
    _loop_for_gate = asyncio.get_event_loop()

    def on_trade_cb(trade):
        asyncio.create_task(broker.on_trade(trade))
        # ライブ進行中バー配信 (BAR_UPDATE): interval ごとに形成中バーを配信。
        if bar_update_gate.ready(_loop_for_gate.time()):
            cvd_calc = getattr(pipeline, "cvd_calculator", None)
            fp_calc = getattr(pipeline, "_footprint_calculator", None)
            snap = cvd_calc.current_bar_snapshot() if cvd_calc is not None else None
            if snap is not None:
                fp_levels = []
                if fp_calc is not None:
                    # ascending (module contract) -> DESCENDING (payload §4.3)
                    fp_levels = [
                        {"price": lv.price, "bid": lv.sell_volume, "ask": lv.buy_volume}
                        for lv in reversed(fp_calc.current_tick_snapshot())
                    ]
                asyncio.create_task(broker.on_bar_update(snap, fp_levels))

    def on_candle_cb(candle):
        app.state.last_bar_wall = datetime.now(timezone.utc)
        fp_bar = getattr(pipeline, "_last_fp_bar", None)
        fp_levels = []
        if fp_bar is not None:
            # footprint.to_levels() is ascending by module contract; the WebSocket
            # payload (WebSocketPayload仕様_v1 §4.3) and compute_value_area() require
            # DESCENDING price order. Convert here at the adapter boundary.
            fp_levels = [
                {"price": lv.price, "bid": lv.sell_volume, "ask": lv.buy_volume}
                for lv in reversed(fp_bar.levels)
            ]
        bm = getattr(pipeline, "book_manager", None)
        snap = bm.snapshot() if bm else None
        asyncio.create_task(broker.on_candle(candle, fp_levels, snap))

    def on_analysis_cb(analysis_result):
        bc = getattr(pipeline, "_last_bar_close", None)
        if bc is not None:
            asyncio.create_task(broker.on_analysis(
                analysis_result,
                bc.signal_result,
                bc.module_scores,
                bc.absorption_result,
            ))

    def on_liquidation_cb(liq):
        asyncio.create_task(broker.on_liquidation(liq))

    def on_webapp_flow_cb(ev):
        asyncio.create_task(broker.on_flow_event(ev))

    pipeline.on_trade = on_trade_cb
    pipeline.on_candle = on_candle_cb
    pipeline.on_analysis = on_analysis_cb
    pipeline.on_liquidation = on_liquidation_cb
    pipeline.on_webapp_flow_event = on_webapp_flow_cb

    app.state.broker = broker
    app.state.config = config
    app.state.pipeline = pipeline

    if config.replay.enabled:
        loop = asyncio.get_event_loop()
        # run_in_executor returns a Future, not a coroutine. asyncio.create_task()
        # rejects Futures (TypeError at lifespan startup) — ensure_future accepts both.
        pipeline_task = asyncio.ensure_future(
            loop.run_in_executor(None, pipeline.run, config.replay.data_path)
        )
    else:
        pipeline_task = asyncio.create_task(pipeline.run_async())

    oi_task = asyncio.create_task(
        oi_polling_loop(broker, config.market.symbol, config.webapp.oi_poll_interval_sec)
    )

    async def _stats_loop():
        while True:
            await asyncio.sleep(5)
            try:
                stats: dict = {"ws_upstream": "OPEN", "clients": str(broker.client_count)}
                cvd_calc = getattr(pipeline, "cvd_calculator", None)
                if cvd_calc is not None:
                    stats["tick_per_sec"] = str(getattr(cvd_calc, "processed", 0))
                ab = getattr(pipeline, "absorption_detector", None)
                if ab is not None:
                    stats["dropped"] = "0"
                await broker.send_stats(datetime.now(timezone.utc), stats)
            except Exception:
                pass

    stats_task = asyncio.create_task(_stats_loop())

    # ── SelfMonitor v1 ───────────────────────────────────────────────────────
    m = config.monitor
    app.state.last_bar_wall = None
    app.state.health_report = None
    monitor = HealthMonitor(
        timeframe_sec=_timeframe_sec(config.market.bar_timeframe),
        log_dir=m.log_dir,
        bar_missing_tolerance_sec=m.bar_missing_tolerance_sec,
        latency_yellow_ms=m.latency_yellow_ms,
        latency_red_ms=m.latency_red_ms,
        memory_yellow_mb=m.memory_yellow_mb,
        memory_red_mb=m.memory_red_mb,
        window_min=m.window_min,
        reconnect_yellow=m.reconnect_yellow,
        reconnect_red=m.reconnect_red,
        gap_yellow=m.gap_yellow,
        gap_red=m.gap_red,
        exception_yellow=m.exception_yellow,
        exception_red=m.exception_red,
    )
    app.state.monitor = monitor

    async def _health_loop():
        while True:
            await asyncio.sleep(m.interval_sec)
            try:
                bm = getattr(pipeline, "book_manager", None)
                conn = getattr(pipeline, "_connector", None)
                dead = pipeline_task.done() and pipeline_task.exception() is not None
                snap = HealthSnapshot(
                    sample_time=datetime.now(timezone.utc),
                    gaps_detected=(bm.gaps_detected if bm is not None else 0),
                    reconnects=(conn.reconnect_count if conn is not None else 0),
                    exceptions=(1 if dead else 0),
                    pipeline_alive=not dead,
                    last_bar_wall=app.state.last_bar_wall,
                    last_event_time=getattr(pipeline, "_last_event_time", None),
                    rss_mb=read_rss_mb(),
                )
                report = monitor.evaluate(snap)
                app.state.health_report = report.to_payload()
                await broker.send_health(snap.sample_time, report.to_payload())
            except Exception:
                logger.exception("health loop iteration failed")

    health_task = asyncio.create_task(_health_loop()) if m.enabled else None
    tasks = [pipeline_task, oi_task, stats_task]
    if health_task is not None:
        tasks.append(health_task)
    app.state.tasks = tasks

    try:
        yield
    finally:
        for t in app.state.tasks:
            t.cancel()
        for t in app.state.tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t


app = FastAPI(title="DeltaEngine WebApp", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/")
async def index() -> FileResponse:
    # no-cache: force the browser to revalidate index.html on every load so UI
    # changes take effect without a manual Ctrl+F5. index.html is fully inline
    # (no external JS/CSS assets), so no per-asset cache-busting is required.
    return FileResponse(
        str(_STATIC_DIR / "index.html"),
        headers={"Cache-Control": "no-cache"},
    )


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    broker: PushBroker = ws.app.state.broker
    config = ws.app.state.config
    await ws.send_json({
        "v": PAYLOAD_VERSION, "type": "HELLO",
        "time": datetime.now(timezone.utc).isoformat(),
        "symbol": config.market.symbol,
        "payload": {
            "server": "DeltaEngine WebApp",
            "payload_version": PAYLOAD_VERSION,
            "bar_timeframe": config.market.bar_timeframe,
            "signal_enabled": config.signal.enabled,
        },
    })
    await broker.register(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await broker.unregister(ws)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/health")
async def api_health(request: Request):
    """SelfMonitor v1 の最新レポート。未評価時は UNKNOWN。"""
    report = getattr(request.app.state, "health_report", None)
    if report is None:
        return JSONResponse({"state": "UNKNOWN", "checks": {}, "anomalies_today": 0})
    return JSONResponse(report)


@app.get("/api/version")
async def api_version(request: Request):
    # lifespan で解決済みの値を返す。未経由(テスト等)ではその場で解決。
    version = getattr(request.app.state, "version", None)
    if version is None:
        version = resolve_version()
    return JSONResponse({"version": version})


@app.get("/api/stats")
async def api_stats(request: Request):
    pipeline = getattr(request.app.state, "pipeline", None)
    stats: dict = {}
    if pipeline is None:
        return JSONResponse(stats)
    bm = getattr(pipeline, "book_manager", None)
    if bm is not None:
        stats["book_snapshots_applied"] = bm.snapshots_applied
        stats["book_diffs_applied"] = bm.diffs_applied
        stats["book_gaps_detected"] = bm.gaps_detected
    cvd_calc = getattr(pipeline, "cvd_calculator", None)
    if cvd_calc is not None:
        stats["current_cvd"] = str(cvd_calc.cvd)
        stats["trades_processed"] = cvd_calc.processed
    ab = getattr(pipeline, "absorption_detector", None)
    if ab is not None:
        stats["absorption_events"] = ab.events_detected
    return JSONResponse(stats)


@app.get("/api/config")
async def api_config(request: Request):
    config = getattr(request.app.state, "config", None)
    if config is None:
        return JSONResponse({})
    return JSONResponse(_config_to_dict(config))
