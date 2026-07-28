"""DeltaEngine05M WebApp — FastAPI + WebSocket。

起動: uvicorn webapp.main:app  /  docker-compose up
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.config import load_config
from src.database.schema import (
    combined_context_event_to_row,
    hfm_context_outcome_to_row,
)
from src.orderflow.combined_context_runtime import CombinedContextObserver
from src.orderflow.hooks.config import (
    ThresholdBook,
    load_hook_observer_config,
    validate_observe_only_playbooks,
)
from src.observation.raw_journal import CaptureCampaign
from src.orderflow.shadow_signal_recorder import ShadowSignalRecorder
from src.pipeline import LivePipeline, ReplayPipeline, load_profile
from src.monitor.health import HealthMonitor, HealthSnapshot, read_rss_mb
from webapp.push_broker import (
    IntervalGate,
    LatestValuePump,
    PushBroker,
    PAYLOAD_VERSION,
    d2s,
)
from webapp.book_projection import (
    LatestBookProjectionPump,
    SYNCED as BOOK_SYNCED,
    build_book_projection,
)
from webapp.tape import TapeBatcher
from webapp.oi_poller import oi_polling_loop
from webapp.hfm_quote_tailer import hfm_quote_tail_loop
from webapp.history import (
    query_combined_context_events,
    query_candles,
    query_flow_response_events,
    query_footprints,
    query_hfm_context_outcomes,
    query_open_interest_samples,
    query_time_sales,
)
from webapp.version import resolve_version

logger = logging.getLogger("webapp.main")

_CONFIG_PATH = "config/config.yaml"
_HOOK_CONFIG_ENV = "HOOK_OBSERVER_CONFIG"
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
        live_dom_depth_levels=w.live_dom_depth_levels,
    )


def _chart_session_vwap(pipeline: Any) -> tuple[Decimal | None, str | None]:
    """Project Strategy VWAP into an explicitly qualified display value."""

    state = getattr(pipeline, "_last_market_state", None)
    exact = getattr(state, "session_vwap", None)
    if exact is not None:
        return exact, "EXACT"

    producer = getattr(pipeline, "_snapshot_producer", None)
    accumulator = getattr(producer, "_session_vwap", None)
    current = getattr(accumulator, "current_value", None)
    if current is None:
        return None, None
    status = "EXACT" if getattr(accumulator, "session_complete", False) else "PARTIAL"
    return current, status


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.version = resolve_version()
    config = load_config(_CONFIG_PATH)
    profile = load_profile(_profile_path(config))
    broker = _build_broker(config)
    context_observer = CombinedContextObserver(config.market.symbol)
    shadow_recorder = ShadowSignalRecorder(Path("data_05M/manual/flow_response_shadow.jsonl"))
    hook_capture = None
    hook_capture_error = None
    hook_config_path = os.environ.get(_HOOK_CONFIG_ENV, "").strip()
    if hook_config_path and not config.replay.enabled:
        try:
            hook_config = load_hook_observer_config(hook_config_path)
            ThresholdBook.load(hook_config.thresholds_path)
            validate_observe_only_playbooks(hook_config.playbooks_path)
            if hook_config.enabled:
                hook_capture = CaptureCampaign.open(hook_config)
                logger.info(
                    "Hook Stage 2A capture campaign opened: %s",
                    hook_capture.stats(),
                )
        except Exception as exc:
            hook_capture_error = f"{type(exc).__name__}: {exc}"
            logger.exception(
                "Hook Stage 2A capture did not start; market pipeline remains isolated"
            )

    # Restore recent raw OI before live processing starts. This is read-only and
    # allows the first native 5m close after a restart to use real prior samples.
    if not config.replay.enabled:
        try:
            prior_oi = await asyncio.to_thread(
                query_open_interest_samples,
                config.database.duckdb_path,
                config.market.symbol,
                5000,
            )
            for row in reversed(prior_oi):
                context_observer.observe_oi_sample({
                    "source_time": datetime.fromisoformat(row["source_time"]),
                    "symbol": config.market.symbol,
                    "open_interest": Decimal(row["open_interest"]),
                })
        except Exception:
            logger.exception("combined-context OI preload failed")

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

    async def push_latest_market(trade):
        # Browser delivery is a latest-value projection. The analytics and
        # storage paths still consume every normalized trade.
        await broker.on_trade(trade)
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
                session_vwap, vwap_status = _chart_session_vwap(pipeline)
                await broker.on_bar_update(
                    snap,
                    fp_levels,
                    source_trade_id=int(trade.trade_id),
                    source_event_time=trade.event_time,
                    session_vwap=session_vwap,
                    vwap_status=vwap_status,
                )

    market_push_pump = LatestValuePump(
        push_latest_market,
        config.webapp.tick_push_interval_ms / 1000.0,
    )
    tape_batcher = TapeBatcher(
        broker.on_tape_update,
        symbol=config.market.symbol,
        interval_sec=config.webapp.tape_batch_interval_ms / 1000.0,
        max_trades_per_message=config.webapp.tape_max_trades_per_message,
        pending_capacity=config.webapp.tape_pending_capacity,
        batch_time_mode="event" if config.replay.enabled else "wall",
    )
    book_projection_pump = LatestBookProjectionPump(
        lambda: getattr(pipeline, "book_manager", None),
        broker.on_book_update,
        depth_levels=config.webapp.live_dom_depth_levels,
        interval_sec=config.webapp.book_update_interval_ms / 1000.0,
        stale_after_ms=config.webapp.book_stale_after_ms,
    )

    app_loop = asyncio.get_running_loop()

    def schedule_broker(coroutine) -> None:
        """Submit broker work from both the live loop and replay worker thread."""
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop is app_loop:
            app_loop.create_task(coroutine)
            return
        try:
            future = asyncio.run_coroutine_threadsafe(coroutine, app_loop)
        except Exception:
            coroutine.close()
            raise

        def report_failure(completed) -> None:
            if completed.cancelled():
                return
            error = completed.exception()
            if error is not None:
                logger.error(
                    "replay broker callback failed",
                    exc_info=(type(error), error, error.__traceback__),
                )

        future.add_done_callback(report_failure)

    def on_accepted_trade_cb(trade):
        tape_batcher.publish(trade)

    def on_trade_cb(trade):
        market_push_pump.publish(trade)

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
        snap = None
        if bm is not None:
            book_projection = build_book_projection(
                bm,
                depth_levels=config.webapp.live_dom_depth_levels,
                stale_after_ms=config.webapp.book_stale_after_ms,
            )
            if book_projection.sync_state == BOOK_SYNCED:
                snap = bm.snapshot()
        session_vwap, vwap_status = _chart_session_vwap(pipeline)
        schedule_broker(broker.on_candle(
            candle, fp_levels, snap,
            session_vwap=session_vwap,
            vwap_status=vwap_status,
        ))

    def on_analysis_cb(analysis_result):
        bc = getattr(pipeline, "_last_bar_close", None)
        if bc is not None:
            schedule_broker(broker.on_analysis(
                analysis_result,
                bc.signal_result,
                bc.module_scores,
                bc.absorption_result,
                getattr(pipeline, "divergence", None),
                bc.imbalance_result,
                bc.imbalance_detector,
                bc.flow_events,
            ))

    def on_liquidation_cb(liq):
        schedule_broker(broker.on_liquidation(liq))

    def on_webapp_flow_cb(ev):
        schedule_broker(broker.on_flow_event(ev))

    def on_flow_response_cb(snapshots):
        if not config.replay.enabled:
            try:
                shadow_recorder.append(snapshots)
            except OSError:
                logger.exception('shadow flow-response recording failed')
        schedule_broker(broker.on_flow_response(snapshots))

    def on_native_candle_cb(candle):
        event = context_observer.register_candle(
            candle,
            decision_time=datetime.now(timezone.utc),
        )
        if event is None:
            return
        storage = getattr(pipeline, "storage_writer", None)
        if storage is not None:
            storage.add_combined_context_event(combined_context_event_to_row(event))
        schedule_broker(broker.on_combined_context(event))

    pipeline.on_accepted_trade = on_accepted_trade_cb
    pipeline.on_trade = None if config.replay.enabled else on_trade_cb
    pipeline.on_candle = on_candle_cb
    pipeline.on_analysis = on_analysis_cb
    pipeline.on_liquidation = on_liquidation_cb
    pipeline.on_flow_event = on_webapp_flow_cb
    pipeline.on_webapp_flow_event = on_webapp_flow_cb
    pipeline.on_flow_response = on_flow_response_cb
    pipeline.on_native_candle = on_native_candle_cb

    app.state.broker = broker
    app.state.config = config
    app.state.pipeline = pipeline
    app.state.market_push_pump = market_push_pump
    app.state.book_projection_pump = book_projection_pump
    app.state.tape_batcher = tape_batcher
    app.state.context_observer = context_observer
    app.state.hook_capture = hook_capture
    app.state.hook_capture_error = hook_capture_error

    if config.replay.enabled:
        market_push_task = None
        book_projection_task = None
        loop = asyncio.get_event_loop()
        # run_in_executor returns a Future, not a coroutine. asyncio.create_task()
        # rejects Futures (TypeError at lifespan startup) — ensure_future accepts both.
        pipeline_task = asyncio.ensure_future(
            loop.run_in_executor(None, pipeline.run, config.replay.data_path)
        )
    else:
        market_push_task = asyncio.create_task(market_push_pump.run())
        book_projection_task = asyncio.create_task(book_projection_pump.run())
        pipeline_task = asyncio.create_task(
            pipeline.run_async(raw_recorder=hook_capture)
        )
    tape_task = asyncio.create_task(tape_batcher.run())

    pending_oi_samples: list[dict] = []

    def store_oi_sample(sample: dict) -> None:
        context_observer.observe_oi_sample(sample)
        storage = getattr(pipeline, "storage_writer", None)
        if storage is None:
            pending_oi_samples.append(sample)
            if len(pending_oi_samples) > 100:
                pending_oi_samples.pop(0)
            return
        if pending_oi_samples:
            for pending in pending_oi_samples:
                storage.add_open_interest_sample(pending)
            pending_oi_samples.clear()
        storage.add_open_interest_sample(sample)

    # Never mix present-day Binance OI with historical replay candles.
    oi_task = None
    if not config.replay.enabled:
        oi_task = asyncio.create_task(oi_polling_loop(
            broker,
            config.market.symbol,
            config.webapp.oi_poll_interval_sec,
            on_sample=store_oi_sample,
        ))

    async def on_hfm_quote(quote) -> None:
        outcomes = context_observer.observe_hfm_quote(quote)
        storage = getattr(pipeline, "storage_writer", None)
        if storage is not None:
            for outcome in outcomes:
                storage.add_hfm_context_outcome(hfm_context_outcome_to_row(outcome))
        await broker.on_hfm_quote(quote)

    hfm_task = None
    if not config.replay.enabled:
        hfm_task = asyncio.create_task(hfm_quote_tail_loop(on_hfm_quote))

    async def _stats_loop():
        while True:
            await asyncio.sleep(5)
            try:
                stats: dict = {"ws_upstream": "OPEN", "clients": str(broker.client_count)}
                bm = getattr(pipeline, "book_manager", None)
                stats["book"] = (
                    book_projection_pump.current_state
                    if not config.replay.enabled else "DISABLED_REPLAY"
                )
                stats["book_projection_samples"] = str(book_projection_pump.samples)
                stats["book_updates_sent"] = str(book_projection_pump.sent)
                stats["book_fail_closed_sent"] = str(
                    book_projection_pump.fail_closed_sent
                )
                stats["book_projection_send_failures"] = str(
                    book_projection_pump.send_failures
                )
                tape_stats = tape_batcher.stats_snapshot()
                for key, value in tape_stats.items():
                    stats[f"tape_{key}"] = str(value)
                rc = getattr(pipeline, "book_resync_counters", None)
                if rc is not None:
                    stats["book_resyncs"] = str(rc.resyncs)
                cvd_calc = getattr(pipeline, "cvd_calculator", None)
                if cvd_calc is not None:
                    stats["tick_per_sec"] = str(getattr(cvd_calc, "processed", 0))
                stats["ui_ticks_sent"] = str(market_push_pump.sent)
                stats["ui_ticks_coalesced"] = str(market_push_pump.coalesced)
                storage = getattr(pipeline, "storage_writer", None)
                if storage is not None:
                    stats["storage_queue"] = str(getattr(storage, "pending", 0))
                    stats["storage_queue_high"] = str(
                        getattr(storage, "high_watermark", 0)
                    )
                    stats["footprint_bars_written"] = str(
                        getattr(storage, "footprint_bars_written", 0)
                    )
                    stats["footprint_write_failures"] = str(
                        getattr(storage, "footprint_write_failures", 0)
                    )
                latest_hfm = context_observer.latest_hfm
                stats["hfm_quote"] = "LIVE" if latest_hfm is not None else "WAITING"
                stats["hfm_pending_outcomes"] = str(context_observer.pending_outcomes)
                ab = getattr(pipeline, "absorption_detector", None)
                if ab is not None:
                    stats["dropped"] = "0"
                if hook_capture is not None:
                    capture_stats = hook_capture.stats()
                    streams = capture_stats.get("streams", {})
                    for mode, stream in streams.items():
                        stats[f"hook_capture_{mode}"] = (
                            "ACTIVE" if stream.get("accepting") else "STOPPED"
                        )
                        stats[f"hook_capture_{mode}_dropped"] = str(
                            stream.get("dropped_queue_full", 0)
                        )
                elif hook_capture_error is not None:
                    stats["hook_capture"] = "ERROR"
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
                pipeline_error = None
                dead = False
                if pipeline_task.done() and not pipeline_task.cancelled():
                    pipeline_exc = pipeline_task.exception()
                    if pipeline_exc is not None:
                        dead = True
                        error_text = " ".join(str(pipeline_exc).splitlines())
                        pipeline_error = (
                            f"{type(pipeline_exc).__name__}: {error_text}"
                        )[:500]
                snap = HealthSnapshot(
                    sample_time=datetime.now(timezone.utc),
                    gaps_detected=(bm.gaps_detected if bm is not None else 0),
                    reconnects=(conn.reconnect_count if conn is not None else 0),
                    exceptions=(1 if dead else 0),
                    pipeline_alive=not dead,
                    pipeline_error=pipeline_error,
                    last_bar_wall=app.state.last_bar_wall,
                    last_event_time=getattr(pipeline, "_last_event_time", None),
                    rss_mb=read_rss_mb(),
                )
                report = monitor.evaluate(snap)
                health_payload = report.to_payload()
                tape_stats = tape_batcher.stats_snapshot()
                tape_problem = bool(
                    tape_stats["dropped_trades"]
                    or tape_stats["send_failures"]
                    or not tape_stats["accounting_balanced"]
                )
                tape_level = "YELLOW" if tape_problem else "GREEN"
                health_payload["checks"]["tape"] = {
                    "level": tape_level,
                    "value": str(tape_stats["dropped_trades"]),
                    "detail": (
                        "dropped=" + str(tape_stats["dropped_trades"])
                        + " pending=" + str(tape_stats["pending"])
                        + " send_failures=" + str(tape_stats["send_failures"])
                        + " balanced=" + str(tape_stats["accounting_balanced"])
                    ),
                }
                if tape_problem and health_payload["state"] == "GREEN":
                    health_payload["state"] = "YELLOW"
                app.state.health_report = health_payload
                await broker.send_health(snap.sample_time, health_payload)
            except Exception:
                logger.exception("health loop iteration failed")

    health_task = asyncio.create_task(_health_loop()) if m.enabled else None
    tasks = [pipeline_task, stats_task]
    if market_push_task is not None:
        tasks.append(market_push_task)
    if book_projection_task is not None:
        tasks.append(book_projection_task)
    tasks.append(tape_task)
    if oi_task is not None:
        tasks.append(oi_task)
    if hfm_task is not None:
        tasks.append(hfm_task)
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
        if hook_capture is not None:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(hook_capture.close)


app = FastAPI(title="DeltaEngine05M WebApp", lifespan=lifespan)
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
            "server": "DeltaEngine05M WebApp",
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


@app.get("/api/history/candles")
async def api_candle_history(request: Request, limit: int = 300):
    """Return recent candles oldest-first for immediate chart hydration."""
    config = getattr(request.app.state, "config", None)
    if config is None:
        return JSONResponse({"candles": []})
    safe_limit = max(20, min(int(limit), 300))
    try:
        newest_first = await asyncio.to_thread(
            query_candles,
            config.database.duckdb_path,
            config.market.symbol,
            safe_limit,
            config.market.bar_timeframe,
        )
    except Exception:
        logger.exception("candle history query failed")
        newest_first = []
    return JSONResponse({"candles": list(reversed(newest_first))})


@app.get("/api/history/flow-response")
async def api_flow_response_history(request: Request, limit: int = 5000):
    """Return persisted flow-response transitions oldest-first for chart bands."""
    config = getattr(request.app.state, "config", None)
    if config is None:
        return JSONResponse({"events": []})
    safe_limit = max(100, min(int(limit), 10000))
    try:
        newest_first = await asyncio.to_thread(
            query_flow_response_events,
            config.database.duckdb_path,
            config.market.symbol,
            safe_limit,
        )
    except Exception:
        logger.exception("flow-response history query failed")
        newest_first = []
    return JSONResponse({"events": list(reversed(newest_first))})


@app.get("/api/history/footprints")
async def api_footprint_history(
    request: Request,
    limit: int = 40,
    before: str | None = None,
    timeframe: str | None = None,
):
    """Return persisted, closed Footprint bars oldest-first for lazy hydration."""
    config = getattr(request.app.state, "config", None)
    if config is None:
        return JSONResponse({"footprints": [], "next_before": None})
    safe_limit = max(1, min(int(limit), 100))
    selected_timeframe = (
        timeframe
        if timeframe is not None and timeframe in _TF_SEC
        else config.market.bar_timeframe
    )
    try:
        footprints = await asyncio.to_thread(
            query_footprints,
            config.database.duckdb_path,
            config.market.symbol,
            selected_timeframe,
            safe_limit,
            before,
        )
    except Exception:
        logger.exception("footprint history query failed")
        footprints = []
    next_before = footprints[0]["bar_time"] if footprints else None
    return JSONResponse({"footprints": footprints, "next_before": next_before})


@app.get("/api/history/open-interest")
async def api_open_interest_history(request: Request, limit: int = 2500):
    """Return raw official OI observations oldest-first for candle alignment."""
    config = getattr(request.app.state, "config", None)
    if config is None or config.replay.enabled:
        return JSONResponse({"samples": []})
    safe_limit = max(100, min(int(limit), 5000))
    try:
        newest_first = await asyncio.to_thread(
            query_open_interest_samples,
            config.database.duckdb_path,
            config.market.symbol,
            safe_limit,
        )
    except Exception:
        logger.exception("open-interest history query failed")
        newest_first = []
    return JSONResponse({"samples": list(reversed(newest_first))})


@app.get("/api/history/combined-context")
async def api_combined_context_history(
    request: Request,
    timeframe: str = "5m",
    limit: int = 500,
):
    """Return stored native four-axis observations oldest-first."""
    config = getattr(request.app.state, "config", None)
    if config is None:
        return JSONResponse({"events": []})
    selected = timeframe if timeframe in {"5m", "10m"} else "5m"
    safe_limit = max(1, min(int(limit), 5000))
    try:
        newest_first = await asyncio.to_thread(
            query_combined_context_events,
            config.database.duckdb_path,
            config.market.symbol,
            selected,
            safe_limit,
        )
    except Exception:
        logger.exception("combined-context history query failed")
        newest_first = []
    return JSONResponse({"events": list(reversed(newest_first))})


@app.get("/api/history/hfm-context-outcomes")
async def api_hfm_context_outcome_history(
    request: Request,
    timeframe: str = "5m",
    limit: int = 1500,
):
    """Return spread-inclusive HFM outcomes oldest-first."""
    config = getattr(request.app.state, "config", None)
    if config is None:
        return JSONResponse({"outcomes": []})
    selected = timeframe if timeframe in {"5m", "10m"} else "5m"
    safe_limit = max(1, min(int(limit), 10000))
    try:
        newest_first = await asyncio.to_thread(
            query_hfm_context_outcomes,
            config.database.duckdb_path,
            config.market.symbol,
            selected,
            safe_limit,
        )
    except Exception:
        logger.exception("HFM context outcome history query failed")
        newest_first = []
    return JSONResponse({"outcomes": list(reversed(newest_first))})


@app.get("/api/history/time-sales")
async def api_time_sales_history(
    request: Request,
    limit: int = 500,
    before: str | None = None,
    before_trade_id: int | None = None,
    symbol: str | None = None,
):
    """Return accepted Time & Sales trades oldest-first for hydration."""
    config = getattr(request.app.state, "config", None)
    if config is None:
        return JSONResponse({
            "trades": [],
            "next_before": None,
            "next_before_trade_id": None,
        })
    selected_symbol = (symbol or config.market.symbol).strip()
    if not selected_symbol:
        return JSONResponse({
            "trades": [],
            "next_before": None,
            "next_before_trade_id": None,
        })
    safe_limit = max(1, min(int(limit), 500))
    try:
        trades = await asyncio.to_thread(
            query_time_sales,
            config.database.duckdb_path,
            selected_symbol,
            safe_limit,
            before,
            before_trade_id,
        )
    except Exception:
        logger.exception("Time & Sales history query failed")
        trades = []
    next_before = trades[0]["event_time"] if trades else None
    next_before_trade_id = trades[0]["trade_id"] if trades else None
    return JSONResponse({
        "trades": trades,
        "next_before": next_before,
        "next_before_trade_id": next_before_trade_id,
    })


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
        stats["book_synced"] = getattr(bm, "is_synchronized", bm.is_initialized)
        rc = getattr(pipeline, "book_resync_counters", None)
        if rc is not None:
            stats["book_resyncs"] = rc.resyncs
            stats["book_snapshot_fetch_failures"] = rc.fetch_failures
    book_pump = getattr(request.app.state, "book_projection_pump", None)
    if book_pump is not None:
        config = getattr(request.app.state, "config", None)
        replay_enabled = bool(
            getattr(getattr(config, "replay", None), "enabled", False)
        )
        stats["book_projection_state"] = (
            "DISABLED_REPLAY" if replay_enabled else book_pump.current_state
        )
        stats["book_projection_samples"] = book_pump.samples
        stats["book_updates_sent"] = book_pump.sent
        stats["book_synced_updates_sent"] = book_pump.synced_sent
        stats["book_fail_closed_sent"] = book_pump.fail_closed_sent
        stats["book_projection_unchanged_suppressed"] = (
            book_pump.unchanged_suppressed
        )
        stats["book_projection_send_failures"] = book_pump.send_failures
    tape_batcher = getattr(request.app.state, "tape_batcher", None)
    if tape_batcher is not None:
        for key, value in tape_batcher.stats_snapshot().items():
            stats[f"tape_{key}"] = value
    cvd_calc = getattr(pipeline, "cvd_calculator", None)
    if cvd_calc is not None:
        stats["current_cvd"] = str(cvd_calc.cvd)
        stats["trades_processed"] = cvd_calc.processed
    ab = getattr(pipeline, "absorption_detector", None)
    if ab is not None:
        stats["absorption_events"] = ab.events_detected
    storage = getattr(pipeline, "storage_writer", None)
    if storage is not None:
        stats["storage_queue_pending"] = getattr(storage, "pending", 0)
        stats["storage_queue_high_watermark"] = getattr(storage, "high_watermark", 0)
        stats["footprint_bars_written"] = getattr(storage, "footprint_bars_written", 0)
        stats["footprint_levels_written"] = getattr(storage, "footprint_levels_written", 0)
        stats["footprint_duplicates"] = getattr(storage, "footprint_duplicates", 0)
        stats["footprint_write_failures"] = getattr(storage, "footprint_write_failures", 0)
        stats["footprint_flush_median_ms"] = getattr(
            storage, "footprint_flush_median_ms", 0.0
        )
        stats["footprint_flush_p95_ms"] = getattr(
            storage, "footprint_flush_p95_ms", 0.0
        )
    observer = getattr(request.app.state, "context_observer", None)
    if observer is not None:
        latest_hfm = observer.latest_hfm
        stats["hfm_pending_outcomes"] = observer.pending_outcomes
        if latest_hfm is None:
            stats["hfm_quote_status"] = "WAITING"
        else:
            age_ms = max(
                0,
                int(
                    (
                        datetime.now(timezone.utc) - latest_hfm.received_time
                    ).total_seconds() * 1000
                ),
            )
            stats["hfm_quote_status"] = "LIVE" if age_ms <= 3000 else "STALE"
            stats["hfm_symbol"] = latest_hfm.symbol
            stats["hfm_spread_usd"] = str(latest_hfm.spread)
            stats["hfm_quote_age_ms"] = age_ms
    market_push_pump = getattr(request.app.state, "market_push_pump", None)
    if market_push_pump is not None:
        stats["ui_ticks_published"] = market_push_pump.published
        stats["ui_ticks_sent"] = market_push_pump.sent
        stats["ui_ticks_coalesced"] = market_push_pump.coalesced
    hook_capture = getattr(request.app.state, "hook_capture", None)
    hook_capture_error = getattr(request.app.state, "hook_capture_error", None)
    if hook_capture is not None:
        stats["hook_capture"] = hook_capture.stats()
    elif hook_capture_error is not None:
        stats["hook_capture"] = {"status": "ERROR", "error": hook_capture_error}
    else:
        stats["hook_capture"] = {"status": "DISABLED"}
    return JSONResponse(stats)


@app.get("/api/config")
async def api_config(request: Request):
    config = getattr(request.app.state, "config", None)
    if config is None:
        return JSONResponse({})
    return JSONResponse(_config_to_dict(config))


@app.post("/api/absorption/params")
async def set_absorption_params(payload: dict, request: Request):
    pipeline = getattr(request.app.state, "pipeline", None)
    ab = getattr(pipeline, "absorption_detector", None)
    if ab is None:
        return {"ok": False, "reason": "detector_unavailable"}
    pst = payload.get("price_stall_ticks")
    vm = payload.get("volume_multiplier")
    ab.set_params(
        price_stall_ticks=int(pst) if pst is not None else None,
        volume_multiplier=Decimal(str(vm)) if vm is not None else None,
    )
    return {
        "ok": True,
        "price_stall_ticks": ab._price_stall_ticks,
        "volume_multiplier": d2s(ab._volume_multiplier),
    }

