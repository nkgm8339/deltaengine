===== A1 =====
30:)
31:from src.observation.raw_journal import CaptureCampaign
32:from src.orderflow.shadow_signal_recorder import ShadowSignalRecorder
33:from src.pipeline import LivePipeline, ReplayPipeline, load_profile
34:from src.monitor.health import HealthMonitor, HealthSnapshot, read_rss_mb
35:from webapp.persistent_depth_writer import PersistentDepthWriter
36:from src.acquisition.depth_history_recorder import (
37:    DepthHistoryRecorder,
38:    RecorderTee,
39:    SafeRecorder,
40:)
41:from webapp.push_broker import (
42:    IntervalGate,
43:    LatestValuePump,
44:    PushBroker,
45:    PAYLOAD_VERSION,
46:    d2s,
47:)
48:from webapp.book_projection import (
49:    LatestBookProjectionPump,
50:    SYNCED as BOOK_SYNCED,
51:    build_book_projection,
52:)
53:from webapp.tape import TapeBatcher
54:from webapp.oi_poller import oi_polling_loop
55:from webapp.hfm_quote_tailer import hfm_quote_tail_loop
56:from webapp.history import (
===== A2 =====
118:
119:@contextlib.asynccontextmanager
120:async def lifespan(app: FastAPI):
121:    app.state.version = resolve_version()
122:    config = load_config(_CONFIG_PATH)
123:    profile = load_profile(_profile_path(config))
124:    persistent_enabled = os.getenv("PERSISTENT_DEPTH_HISTORY_ENABLED", "false").lower() == "true"
125:    persistent_writer = PersistentDepthWriter(os.getenv("PERSISTENT_DEPTH_HISTORY_ROOT", "data_05M/depth_history"), config.market.symbol) if persistent_enabled else None
126:    depth_history_enabled = os.getenv("DEPTH_HISTORY_ENABLED", "false").lower() == "true"
127:    depth_history_recorder = (
128:        SafeRecorder(
129:            DepthHistoryRecorder(
130:                os.getenv("DEPTH_HISTORY_ROOT", "data_05M/depth_history_raw"),
131:                config.market.symbol,
132:            )
133:        )
134:        if depth_history_enabled
135:        else None
136:    )
137:    broker = _build_broker(config, persistent_writer)
138:    context_observer = CombinedContextObserver(config.market.symbol)
139:    shadow_recorder = ShadowSignalRecorder(Path("data_05M/manual/flow_response_shadow.jsonl"))
140:    hook_capture = None
===== A3 =====
228:        pending_capacity=config.webapp.tape_pending_capacity,
229:        batch_time_mode="event" if config.replay.enabled else "wall",
230:    )
231:    book_projection_pump = LatestBookProjectionPump(
232:        lambda: getattr(pipeline, "book_manager", None),
233:        broker.on_book_update,
234:        depth_levels=config.webapp.live_dom_depth_levels,
235:        interval_sec=config.webapp.book_update_interval_ms / 1000.0,
236:        stale_after_ms=config.webapp.book_stale_after_ms,
237:    )
238:
239:    app_loop = asyncio.get_running_loop()
240:
===== A4 =====
368:    app.state.hook_capture = hook_capture
369:    app.state.hook_capture_error = hook_capture_error
370:
371:    if config.replay.enabled:
372:        market_push_task = None
373:        book_projection_task = None
374:        loop = asyncio.get_event_loop()
375:        # run_in_executor returns a Future, not a coroutine. asyncio.create_task()
376:        # rejects Futures (TypeError at lifespan startup) — ensure_future accepts both.
377:        pipeline_task = asyncio.ensure_future(
378:            loop.run_in_executor(None, pipeline.run, config.replay.data_path)
379:        )
380:    else:
381:        market_push_task = asyncio.create_task(market_push_pump.run())
382:        book_projection_task = asyncio.create_task(book_projection_pump.run())
383:        _raw_taps = [t for t in (hook_capture, depth_history_recorder) if t is not None]
384:        _raw_tap = _raw_taps[0] if len(_raw_taps) == 1 else (RecorderTee(_raw_taps) if _raw_taps else None)
385:        pipeline_task = asyncio.create_task(
386:            pipeline.run_async(raw_recorder=_raw_tap)
387:        )
388:    tape_task = asyncio.create_task(tape_batcher.run())
389:
390:    pending_oi_samples: list[dict] = []
391:
392:    def store_oi_sample(sample: dict) -> None:
===== A5 =====
566:                logger.exception("health loop iteration failed")
567:
568:    health_task = asyncio.create_task(_health_loop()) if m.enabled else None
569:    tasks = [pipeline_task, stats_task]
570:    if market_push_task is not None:
571:        tasks.append(market_push_task)
572:    if book_projection_task is not None:
573:        tasks.append(book_projection_task)
574:    tasks.append(tape_task)
575:    if oi_task is not None:
576:        tasks.append(oi_task)
577:    if hfm_task is not None:
578:        tasks.append(hfm_task)
579:    if health_task is not None:
580:        tasks.append(health_task)
581:    app.state.tasks = tasks
582:
583:    try:
584:        yield
585:    finally:
586:        for t in app.state.tasks:
587:            t.cancel()
588:        for t in app.state.tasks:
589:            with contextlib.suppress(asyncio.CancelledError, Exception):
590:                await t
591:        if hook_capture is not None:
592:            with contextlib.suppress(Exception):
593:                await asyncio.to_thread(hook_capture.close)
594:        if persistent_writer is not None:
595:            with contextlib.suppress(Exception):
596:                await asyncio.to_thread(persistent_writer.close)
597:        if depth_history_recorder is not None:
598:            with contextlib.suppress(Exception):
599:                depth_history_recorder.close()
600:
===== A6 =====
220:        spread=best_ask - best_bid,
221:        age_ms=age_ms,
222:    )
223:
224:
225:class LatestBookProjectionPump:
226:    """Sample the book at a bounded cadence and send only changed projections."""
227:
228:    def __init__(
229:        self,
230:        get_book_state: Callable[[], Any],
231:        send: Callable[[BookProjection], Awaitable[None]],
232:        *,
233:        depth_levels: int = 50,
234:        interval_sec: float = 0.1,
235:        stale_after_ms: int = 2000,
236:        monotonic: Callable[[], float] = time.monotonic,
237:        utcnow: Callable[[], datetime] = _utc_now,
238:        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
239:    ) -> None:
240:        if interval_sec <= 0:
241:            raise ValueError("interval_sec must be > 0")
242:        self._get_book_state = get_book_state
243:        self._send = send
244:        self.depth_levels = depth_levels
245:        self.interval_sec = float(interval_sec)
246:        self.stale_after_ms = stale_after_ms
247:        self._monotonic = monotonic
248:        self._utcnow = utcnow
249:        self._sleep = sleep
250:        self._last_fingerprint: tuple | None = None
251:        self.latest_projection: BookProjection | None = None
252:        self.samples = 0
253:        self.sent = 0
254:        self.synced_sent = 0
255:        self.fail_closed_sent = 0
256:        self.unchanged_suppressed = 0
257:        self.send_failures = 0
258:
259:    @property
260:    def current_state(self) -> str:
261:        return (
262:            self.latest_projection.sync_state
263:            if self.latest_projection is not None
264:            else "NO_SNAPSHOT"
265:        )
266:
267:    async def project_once(self) -> bool:
268:        projection = build_book_projection(
269:            self._get_book_state(),
270:            depth_levels=self.depth_levels,
271:            stale_after_ms=self.stale_after_ms,
272:            now_monotonic=self._monotonic(),
273:            projection_time=self._utcnow(),
274:        )
275:        self.samples += 1
276:        if projection.fingerprint == self._last_fingerprint:
277:            self.unchanged_suppressed += 1
278:            return False
279:        try:
280:            await self._send(projection)
281:        except asyncio.CancelledError:
282:            raise
283:        except Exception:  # keep LIVE market analysis isolated from UI delivery
284:            self.send_failures += 1
285:            logger.exception("BOOK_UPDATE projection send failed")
286:            return False
287:        self._last_fingerprint = projection.fingerprint
288:        self.latest_projection = projection
289:        self.sent += 1
290:        if projection.sync_state == SYNCED:
291:            self.synced_sent += 1
292:        else:
293:            self.fail_closed_sent += 1
294:        return True
295:
296:    async def run(self) -> None:
297:        while True:
298:            await self.project_once()
299:            await self._sleep(self.interval_sec)
300:
===== A7 =====
60:        return None
61:    with path.open("rb") as handle:
62:        start = max(0, size - block_size)
63:        handle.seek(start)
64:        data = handle.read()
65:    lines = [part for part in data.splitlines() if part.strip()]
66:    if not lines:
67:        return None
68:    return lines[-1].decode("utf-8-sig")
69:
70:
71:async def _dispatch(callback: Callable[[HfmQuote], object], quote: HfmQuote) -> None:
72:    result = callback(quote)
73:    if inspect.isawaitable(result):
74:        await result
75:
76:
77:async def hfm_quote_tail_loop(
78:    callback: Callable[[HfmQuote], object],
79:    *,
80:    path: Path | None = None,
81:    poll_interval_sec: float = 0.05,
82:    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
83:) -> None:
84:    """Tail new HFM observations and first publish the latest complete quote."""
85:    source = path or default_hfm_quote_path()
86:    offset: int | None = None
87:    pending = b""
88:    while True:
89:        try:
90:            if not source.exists():
91:                offset = None
92:                pending = b""
93:                await asyncio.sleep(poll_interval_sec)
94:                continue
95:            size = source.stat().st_size
96:            if offset is None:
97:                latest = _last_complete_line(source)
98:                if latest is not None:
99:                    initial_time = datetime.fromtimestamp(
100:                        source.stat().st_mtime, tz=timezone.utc,
101:                    )
102:                    try:
103:                        await _dispatch(callback, parse_hfm_quote(latest, initial_time))
104:                    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
105:                        logger.warning("latest HFM quote line is invalid")
106:                offset = size
107:                await asyncio.sleep(poll_interval_sec)
108:                continue
109:            if size < offset:
110:                offset = 0
111:                pending = b""
112:            if size == offset:
113:                await asyncio.sleep(poll_interval_sec)
114:                continue
115:            with source.open("rb") as handle:
116:                handle.seek(offset)
117:                chunk = handle.read()
118:                offset = handle.tell()
119:            pending += chunk
120:            lines = pending.split(b"\n")
121:            pending = lines.pop()
122:            for raw_line in lines:
123:                if not raw_line.strip():
124:                    continue
125:                received_time = clock()
126:                try:
127:                    quote = parse_hfm_quote(raw_line.decode("utf-8-sig"), received_time)
128:                except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError):
129:                    logger.warning("invalid HFM quote line skipped")
130:                    continue
131:                await _dispatch(callback, quote)
132:        except asyncio.CancelledError:
133:            raise
134:        except OSError as exc:
135:            logger.warning("HFM quote file retrying after: %s", exc)
136:            await asyncio.sleep(1)
===== A8 =====
250:    async def on_book_update(self, projection: BookProjection) -> None:
251:        """Broadcast one bounded LIVE DOM projection and cache it for reconnect."""
252:        if projection.sync_state != SYNCED and projection.sync_state not in FAIL_CLOSED_STATES:
253:            raise ValueError(f"unknown book sync_state: {projection.sync_state}")
254:        synced = projection.sync_state == SYNCED
255:        if synced and (
256:            projection.best_bid is None
257:            or projection.best_ask is None
258:            or projection.spread is None
259:        ):
260:            raise ValueError("SYNCED BOOK_UPDATE requires best bid, best ask, and spread")
261:        book_sequence = self.book_updates_broadcast + 1
262:        bids = projection.bids if synced else ()
263:        asks = projection.asks if synced else ()
264:        message = envelope(
265:            "BOOK_UPDATE",
266:            projection.projection_time,
267:            self.symbol,
268:            {
269:                "book_stream_id": self.book_stream_id,
270:                "book_sequence": book_sequence,
271:                "event_time": (
272:                    projection.event_time.astimezone(timezone.utc).isoformat()
273:                    if projection.event_time is not None else None
274:                ),
275:                "projection_time": projection.projection_time.astimezone(
276:                    timezone.utc
277:                ).isoformat(),
278:                "last_update_id": projection.last_update_id,
279:                "sync_state": projection.sync_state,
280:                "bids": [
281:                    {"price": d2s(price), "qty": d2s(quantity)}
282:                    for price, quantity in bids
283:                ],
284:                "asks": [
285:                    {"price": d2s(price), "qty": d2s(quantity)}
286:                    for price, quantity in asks
287:                ],
288:                "depth_levels": projection.depth_levels,
289:                "best_bid": d2s(projection.best_bid) if synced else None,
290:                "best_ask": d2s(projection.best_ask) if synced else None,
291:                "spread": d2s(projection.spread) if synced else None,
292:                "age_ms": projection.age_ms,
293:            },
294:        )
295:        self._latest_book_message = message
296:        self.book_updates_broadcast = book_sequence
297:        if self.persistent_writer is not None:
298:            self.persistent_writer.append(message["payload"])
299:        await self._broadcast(message)
300:
===== A9 =====
965:const UI_PAYLOAD_VERSION = 1;
966:// Phase 5 presentation rollback boundary. Backend collection/storage stays active.
967:const PHASE5_FUSION_ENABLED = true;
968:// GO-H3 presentation gate. Keep false until GO-H6 operational activation.
969:const ORDER_BOOK_HEATMAP_ENABLED = false;
970:// Accepted Time & Sales trade -> passive LIVE DOM half-cell pulse.
971:const DOM_TRADE_PULSE_ENABLED = true;
972:const DOM_TRADE_PULSE_DURATION_MS = 400;
===== A10 =====
124:    persistent_enabled = os.getenv("PERSISTENT_DEPTH_HISTORY_ENABLED", "false").lower() == "true"
125:    persistent_writer = PersistentDepthWriter(os.getenv("PERSISTENT_DEPTH_HISTORY_ROOT", "data_05M/depth_history"), config.market.symbol) if persistent_enabled else None
126:    depth_history_enabled = os.getenv("DEPTH_HISTORY_ENABLED", "false").lower() == "true"
130:                os.getenv("DEPTH_HISTORY_ROOT", "data_05M/depth_history_raw"),
===== HEAD SHA256 =====
FEFA73A2B6E54A1F7710B3606BA946B7E3055FAB3B93B3720BB1C4F9289233EA  Delta_Engine_Pro4web/webapp/main.py
591BBB8A43946FCDE43CD04B42026BD03DA1BE55135CA08491D295DB8E755D99  Delta_Engine_Pro4web/webapp/book_projection.py
306ACE4257965C183A068D456095F284565F08E7ED0C640608777DC6148C0568  Delta_Engine_Pro4web/webapp/hfm_quote_tailer.py
67522B9460DDAA53756A3404B4BC32BCC6E910B63707845A81BA8784AE129C3B  Delta_Engine_Pro4web/webapp/push_broker.py
BFC9F54E32415CEDA6E456FE858F942F1D1D36E7FDA97F808DCDC684CB448964  Delta_Engine_Pro4web/webapp/static/index.html
===== git rev-parse HEAD =====
2fea7efebbe64b86b3a62bf1645ffcf3d3946dd4
===== git status --porcelain -- Delta_Engine_Pro4web/ =====
?? Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/
===== git diff --cached --name-only =====
