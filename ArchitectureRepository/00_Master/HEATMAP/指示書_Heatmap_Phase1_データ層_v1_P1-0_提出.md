# [完了] 指示書_Heatmap_Phase1_データ層_v1 (P1-0)

作成日: 2026-07-29  
対象: P1-0 設計前提の提出のみ  
提出後の状態: 次の指示待ちで停止

## 実施境界

- ソース実装・機能変更: なし
- テスト実行: なし
- ライブ接続: なし
- commit / push: なし
- 指定7ファイルの内容: 2026-07-29時点のworktree現物
- `main.py`、`push_broker.py`、`docker-compose.yml`の既存未コミット差分は変更・破棄していない

## P1-0-a 提出対象一覧

| # | ファイル | 行数 | SHA-256 | 取得時状態 |
|---:|---|---:|---|---|
| 1 | `Delta_Engine_Pro4web/webapp/persistent_depth_writer.py` | 85 | `451669F63D108DB42A5E84490B36A3A063809FD6C3BE383F522507065B61FFCF` | clean |
| 2 | `Delta_Engine_Pro4web/webapp/main.py` | 950 | `812539DF73886404D804868A83DC75B84985817CFFFF6720AF654BAD5DC536BE` | M（既存差分） |
| 3 | `Delta_Engine_Pro4web/webapp/push_broker.py` | 564 | `71654F78872A8D659D698264E65AEC3B638EB1FCF58D1E31F94976693367F7D1` | M（既存差分） |
| 4 | `Delta_Engine_Pro4web/tools/persistent_depth_prototype.py` | 140 | `26453DBA592E1C2B6006C3F1D605850BA04D2D1575AC40079537457F6252594D` | clean |
| 5 | `Delta_Engine_Pro4web/tools/persistent_depth_recovery.py` | 60 | `0C699413537FC05F77A7084CD589BFDF33FF7F17341DDF9A1548A96D990C134A` | clean |
| 6 | `Delta_Engine_Pro4web/tests/webapp/test_persistent_depth_writer.py` | 29 | `939C19A0FC3727A83C17BA8158B5A8CB4354AC5B96FCEDD5E4C365F093AB921E` | clean |
| 7 | `Delta_Engine_Pro4web/docker-compose.yml` | 29 | `3A43209878CF5B138A0E290075552F2F42A1D6384948991C85E80778D4E523D8` | M（既存差分） |

## P1-0-b sandbox編集可否

- 判定: **不可**
- 試験対象: `Delta_Engine_Pro4web/webapp/persistent_depth_writer.py`
- 選定理由: git追跡済みソースであり、試験前がclean。既存Mファイルを破壊しないため。
- 試験前SHA-256: `451669F63D108DB42A5E84490B36A3A063809FD6C3BE383F522507065B61FFCF`
- 試験方法: `apply_patch`で末尾へ空行1行を追加する操作
- 結果: sandbox準備段階で拒否され、ファイル内容の変更は発生しなかった
- `git checkout`: 実行不要（編集自体が適用されなかったため）
- 試験後SHA-256: `451669F63D108DB42A5E84490B36A3A063809FD6C3BE383F522507065B61FFCF`
- 試験後`git status --porcelain -- Delta_Engine_Pro4web/webapp/persistent_depth_writer.py`: 空

### エラーメッセージ全文

```text
apply_patch verification failed: Failed to read file to update C:\Users\user\desktop\deltaengine05M\Delta_Engine_Pro4web\webapp\persistent_depth_writer.py: failed to prepare fs sandbox: failed to prepare windows sandbox wrapper: windows unelevated restricted-token sandbox cannot enforce split writable root sets directly; refusing to run unsandboxed
```

### 回避策候補（未実行）

1. writable rootをworkspace 1件だけにしたsandbox profileで`apply_patch`を再実行する。
2. 既存追跡ファイルの変更時だけ、ユーザー承認付きのescalated実行を使用する。
3. 変更パッチを新規ファイルとして提出し、人間または編集可能な環境で適用する。

## P1-0-c 既存prototypeのR1〜R5適合自己評価

判定語は「適合／不適合／要修正」の3種。現状のままPhase 1正本へ継承可能な項目はない。

| 対象 | 要件 | 判定 | ファイル:行番号の根拠 |
|---|---|---|---|
| `webapp/persistent_depth_writer.py` | R1 | **不適合** | `persistent_depth_writer.py:43-51`は`book_stream_id`と`book_sequence`を持つ任意payloadをJSON化するだけ。実際の入力は`push_broker.py:295-296`のUI用`BOOK_UPDATE` payloadであり、`book_projection.py:215-216`でbid/askを`depth_levels`件へ切り詰める。`config/config.yaml:85`は50段。REST snapshot＋生`@depth`全量ではない。 |
| 同上 | R2 | **不適合** | `persistent_depth_writer.py:43-50`にevent type、`lastUpdateId`、`U`、`u`、`pu`、gap、resetの検証・記録契約がない。stream切替とframe数だけでrotateする。 |
| 同上 | R3 | **要修正** | ファイル内に`float()`はないが、`persistent_depth_writer.py:43-51`は任意dictを受け、float混入を拒否しない。現行UI投影の価格・数量は`push_broker.py:278-285`で`d2s`によりstr化されるが、生イベント記録用の型契約は存在しない。 |
| 同上 | R4 | **不適合** | `persistent_depth_writer.py:52-54`が毎frame同期`write + flush + fsync`。`push_broker.py:295-296`からasync event-loop上で直接呼ぶ。closeも`main.py:568-570`で`asyncio.to_thread`を使い、スレッド禁止条件にも抵触する。メモリバッファ・周期flushなし。 |
| 同上 | R5 | **不適合** | writer内部にerror statusがなく、`append()`例外は呼出元へ伝播する。`book_projection.py:279-286`はgeneric send failureとして捕捉するだけでwriter専用statusへ報告しない。`persistent_depth_writer.py:52-58`はwrite/fsync後にhash・countを更新するため、中途障害時の再試行・重複・partial rowを管理する契約もない。 |
| `tools/persistent_depth_prototype.py` | R1 | **不適合** | `persistent_depth_prototype.py:42-48`はUI frame形式を検証し、`60-91`はframe列を圧縮する。`85-87`の`DIFF`も生`@depth`差分ではなくfull frameを包んだ独自record。REST snapshot＋生差分全量ではない。 |
| 同上 | R2 | **不適合** | `persistent_depth_prototype.py:42-48,84-87,109-121`は独自`book_sequence/base_sequence`だけを扱い、Binance `lastUpdateId/U/u/pu`の同期、gap時snapshot再取得、reset記録がない。 |
| 同上 | R3 | **要修正** | `persistent_depth_prototype.py:38-39`は任意dictを`json.dumps`し、`42-48`も価格・数量のstr型やfloat禁止を検証しない。 |
| 同上 | R4 | **要修正** | `persistent_depth_prototype.py:60-91`は全frameをlist化し、同期圧縮するisolated prototype。production用のasyncメモリバッファ、周期flush、segment-close限定fsync契約がない。 |
| 同上 | R5 | **要修正** | validation失敗は例外で明示されるが、`persistent_depth_prototype.py:60-91`はmarket dataパスからの障害隔離・status報告を持たない。ファイルappend writerでもないため、partial append防止契約としては未完成。 |
| `tools/persistent_depth_recovery.py` | R1 | **不適合** | `persistent_depth_recovery.py:18-32`はcaller supplied frame listを1 segmentにするだけで、REST snapshot＋生`@depth`event種別や全量性を検証しない。 |
| 同上 | R2 | **不適合** | `persistent_depth_recovery.py:31,36-47`は独自`book_sequence`の先頭末尾しか検証せず、`lastUpdateId/U/u/pu`、gap、snapshot再取得、reset recordを扱わない。 |
| 同上 | R3 | **要修正** | `persistent_depth_recovery.py:14-15`は任意dictをJSON化し、float混入や価格・数量str契約を検証しない。 |
| 同上 | R4 | **要修正** | `persistent_depth_recovery.py:22-30`はsegment全体をメモリ構築し、同期write後にclose時1回のflush/fsyncを行う。毎frame fsyncではない点は利用可能だが、周期flush・asyncio協調・単一loop上のblocking回避がない。 |
| 同上 | R5 | **要修正** | `persistent_depth_recovery.py:24-30`のtemp→replaceと`39-47`のchecksum/count検証は利用候補。一方`32`のmanifestはatomic write/fsyncでなく、例外のmarket path隔離とstatus報告もない。 |

### 現行受信経路に関する横断所見

- raw記録の土台は存在する。`pipeline.py:1144-1157,1178-1189`の`record_path`指定時、`DataReceiver`がvalidation後の生WS eventを到着順で記録し、`pipeline.py:191-222`が取得したREST snapshotも同じrecorderへ書く。
- ただしWebApp起動は`main.py:359-360`で`raw_recorder=hook_capture`だけを渡し、`record_path`を指定していない。現行persistent writerはこのraw経路ではなくUI projection経路へ接続されている。
- R2の重要な不適合がある。`orderbook.py:142-151`のdocstringは公式整合条件を記述する一方、実処理`orderbook.py:233-242`はinitial syncで最初のnon-stale diffを`U <= lastUpdateId+1 <= u`確認なしに受理する。コメントにも`lenient`と明記されている。
- 通常同期後のgap検知は`orderbook.py:245-268`でstateを空にし、`pipeline.py:191-238`のsupervisorがsnapshotを再取得する。しかし永続データへ独立したreset recordを残す契約はない。
- R7設定矛盾も現存する。`docker-compose.yml:24-27`はコメントが「remains disabled」なのに値は`PERSISTENT_DEPTH_HISTORY_ENABLED=true`。一方`tests/tools/test_persistent_depth_pd4_deployment.py:6`は`false`を期待する。
- Replay側は`pipeline.py:646-664`でdepthをbookへ適用するが、WebAppは`main.py:347-358`でreplay時の`book_projection_task`を無効化する。Phase 1実装ではLive/Replay双方の記録入口を明示的に揃える必要がある。

## P1-0-a 指定ファイル現物全文
### `Delta_Engine_Pro4web/webapp/persistent_depth_writer.py`

````python
"""Production-gated append-only depth segment writer.

Enabled only by PERSISTENT_DEPTH_HISTORY_ENABLED=true.  It is deliberately
separate from the existing DuckDB/Parquet storage writer.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


class PersistentDepthWriter:
    def __init__(self, root: str | Path, symbol: str, max_frames: int = 1000) -> None:
        self.root = Path(root) / f"symbol={symbol}"
        self.root.mkdir(parents=True, exist_ok=True)
        self.symbol = symbol
        self.max_frames = max(1, int(max_frames))
        self._stream_id: str | None = None
        self._part: Path | None = None
        self._handle = None
        self._hasher = hashlib.sha256()
        self._count = 0
        self._first: int | None = None
        self._last: int | None = None

    @property
    def frames_written(self) -> int:
        return self._count

    def _open(self, stream_id: str, sequence: int) -> None:
        self._stream_id = stream_id
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        self._part = self.root / f"stream={stream_id}.start={sequence}.{stamp}.jsonl.part"
        self._handle = self._part.open("wb")
        self._hasher = hashlib.sha256()
        self._count = 0
        self._first = None
        self._last = None

    def append(self, payload: dict) -> None:
        stream_id = str(payload.get("book_stream_id") or "")
        sequence = payload.get("book_sequence")
        if not stream_id or not isinstance(sequence, int) or sequence < 1:
            raise ValueError("invalid persistent depth payload")
        if self._handle is None or self._stream_id != stream_id or self._count >= self.max_frames:
            self.close()
            self._open(stream_id, sequence)
        row = (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        self._handle.write(row)
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self._hasher.update(row)
        self._count += 1
        self._first = sequence if self._first is None else self._first
        self._last = sequence

    def close(self) -> None:
        if self._handle is None or self._part is None:
            return
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self._handle.close()
        final = self._part.with_suffix("")
        os.replace(self._part, final)
        manifest = {
            "symbol": self.symbol,
            "stream_id": self._stream_id,
            "first_sequence": self._first,
            "last_sequence": self._last,
            "record_count": self._count,
            "sha256": self._hasher.hexdigest(),
            "schema_revision": "DEPTH_HISTORY_V1",
        }
        final.with_suffix(final.suffix + ".manifest.json").write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
        self._handle = None
        self._part = None

    def __enter__(self) -> "PersistentDepthWriter":
        return self

    def __exit__(self, *_args) -> None:
        self.close()
````

### `Delta_Engine_Pro4web/webapp/main.py`

````python
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
from webapp.persistent_depth_writer import PersistentDepthWriter
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


def _build_broker(config, persistent_writer=None) -> PushBroker:
    w = config.webapp
    return PushBroker(
        symbol=config.market.symbol,
        depth_levels=w.depth_levels,
        live_dom_depth_levels=w.live_dom_depth_levels,
        persistent_writer=persistent_writer,
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
    persistent_enabled = os.getenv("PERSISTENT_DEPTH_HISTORY_ENABLED", "false").lower() == "true"
    persistent_writer = PersistentDepthWriter(os.getenv("PERSISTENT_DEPTH_HISTORY_ROOT", "data_05M/depth_history"), config.market.symbol) if persistent_enabled else None
    broker = _build_broker(config, persistent_writer)
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
        if persistent_writer is not None:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(persistent_writer.close)


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





````

### `Delta_Engine_Pro4web/webapp/push_broker.py`

````python
"""PushBroker: pipeline hooks → WebSocket clients. Payload組立の唯一の場所。

WebSocketPayload仕様_v1 に完全準拠。数値は全て str(Decimal)。float() 禁止。
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Awaitable, Callable, Optional
from uuid import uuid4

from webapp.book_projection import BookProjection, FAIL_CLOSED_STATES, SYNCED
from webapp.tape import TapeBatch

PAYLOAD_VERSION = 1


def d2s(v: Optional[Decimal]) -> Optional[str]:
    """Decimal → str（None透過）。floatは受け付けない。"""
    if v is None:
        return None
    if not isinstance(v, (Decimal, int)):
        raise TypeError(f"d2s expects Decimal/int/None, got {type(v)}")
    return str(v)


def _vwap_status(value: Optional[Decimal], status: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if status not in {"EXACT", "PARTIAL"}:
        raise ValueError("vwap_status must be EXACT or PARTIAL when vwap is present")
    return status


def envelope(msg_type: str, time_: datetime, symbol: str, payload: dict) -> dict:
    return {
        "v": PAYLOAD_VERSION,
        "type": msg_type,
        "time": time_.astimezone(timezone.utc).isoformat(),
        "symbol": symbol,
        "payload": payload,
    }


def compute_value_area(levels: list[dict]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """POC/VAH/VAL（WebSocketPayload仕様_v1 §4.3）。levelsは価格降順、各要素 Decimal。"""
    if not levels:
        return None, None, None
    totals = [(lv["price"], lv["bid"] + lv["ask"]) for lv in levels]
    poc_i = 0
    for i, (_, tot) in enumerate(totals):
        if tot > totals[poc_i][1]:
            poc_i = i
    grand = sum(t for _, t in totals)
    target = grand * Decimal("0.7")
    lo = hi = poc_i
    acc = totals[poc_i][1]
    while acc < target and (hi > 0 or lo < len(totals) - 1):
        up = totals[hi - 1][1] if hi > 0 else Decimal("-1")
        dn = totals[lo + 1][1] if lo < len(totals) - 1 else Decimal("-1")
        if up >= dn:
            hi -= 1
            acc += up
        else:
            lo += 1
            acc += dn
    return str(totals[poc_i][0]), str(totals[hi][0]), str(totals[lo][0])



class IntervalGate:
    """単調時刻ベースの間引きゲート (BAR_UPDATE スロットリング)。

    ready(now) は前回 True からの経過が interval_sec 以上のときだけ True。
    純粋ロジック (時刻は呼び出し側が渡す) — テスト可能。
    """

    def __init__(self, interval_sec: float) -> None:
        if interval_sec <= 0:
            raise ValueError("interval_sec must be > 0")
        self.interval_sec = float(interval_sec)
        self._last = None  # monotonic clock value (loop.time())

    def ready(self, now) -> bool:
        if self._last is None or (now - self._last) >= self.interval_sec:
            self._last = now
            return True
        return False


class LatestValuePump:
    """Send only the newest market value at a bounded cadence.

    The analytics path still consumes every trade. This pump is only for the
    browser projection, where replaying thousands of stale ticks creates visual
    latency without adding information. Publish is intentionally synchronous
    and must be called from the event-loop thread.
    """

    def __init__(
        self,
        send: Callable[[Any], Awaitable[None]],
        interval_sec: float,
    ) -> None:
        if interval_sec <= 0:
            raise ValueError("interval_sec must be > 0")
        self._send = send
        self.interval_sec = float(interval_sec)
        self._wake = asyncio.Event()
        self._latest: Any = None
        self._version = 0
        self.published = 0
        self.sent = 0

    def publish(self, value: Any) -> None:
        self._latest = value
        self._version += 1
        self.published += 1
        self._wake.set()

    @property
    def coalesced(self) -> int:
        return max(0, self.published - self.sent)

    async def run(self) -> None:
        while True:
            await self._wake.wait()
            self._wake.clear()
            value = self._latest
            version = self._version
            await self._send(value)
            self.sent += 1
            if self._version != version:
                self._wake.set()
            await asyncio.sleep(self.interval_sec)


class PushBroker:
    """WebSocketクライアント管理とPayload配信。asyncio単一ループ（ADR-003）。"""

    def __init__(
        self,
        symbol: str,
        depth_levels: int = 15,
        live_dom_depth_levels: int = 50,
        persistent_writer=None,
    ) -> None:
        self.symbol = symbol
        self.persistent_writer = persistent_writer
        self.depth_levels = depth_levels
        self.live_dom_depth_levels = live_dom_depth_levels
        self._clients: set[Any] = set()
        self._lock = asyncio.Lock()
        self._latest_hfm_message: dict | None = None
        self._latest_book_message: dict | None = None
        self.book_stream_id = str(uuid4())
        self.book_updates_broadcast = 0
        self.tape_batches_broadcast = 0
        self.tape_trades_broadcast = 0

    async def register(self, ws: Any) -> None:
        async with self._lock:
            self._clients.add(ws)
            latest_hfm = self._latest_hfm_message
            latest_book = self._latest_book_message
        for latest in (latest_hfm, latest_book):
            if latest is None:
                continue
            try:
                await ws.send_text(json.dumps(latest, separators=(",", ":")))
            except Exception:
                await self.unregister(ws)
                break

    async def unregister(self, ws: Any) -> None:
        async with self._lock:
            self._clients.discard(ws)

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def _broadcast(self, msg: dict) -> None:
        text = json.dumps(msg, separators=(",", ":"))
        async with self._lock:
            dead = []
            for ws in self._clients:
                try:
                    await ws.send_text(text)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._clients.discard(ws)

    async def on_trade(self, trade) -> None:
        await self._broadcast(envelope("TICK", trade.event_time, self.symbol, {
            "trade_id": int(trade.trade_id),
            "price": d2s(trade.price),
            "quantity": d2s(trade.quantity),
            "side": trade.side,
            "tick_delta": d2s(getattr(trade, "tick_delta", None)),
            "tick_cvd": d2s(getattr(trade, "tick_cvd", None)),
        }))

    async def on_tape_update(self, batch: TapeBatch) -> None:
        """Broadcast one ordered, bounded Time & Sales batch without caching it."""
        if batch.accepted_count != len(batch.trades) or not batch.trades:
            raise ValueError("TAPE_UPDATE accepted_count must match non-empty trades")
        if batch.dropped_count < 0:
            raise ValueError("TAPE_UPDATE dropped_count must be >= 0")
        sequences = tuple(trade.sequence for trade in batch.trades)
        if sequences != tuple(range(batch.first_sequence, batch.last_sequence + 1)):
            raise ValueError("TAPE_UPDATE batch sequences must be contiguous")
        message = envelope(
            "TAPE_UPDATE",
            batch.batch_time,
            self.symbol,
            {
                "batch_time": batch.batch_time.astimezone(timezone.utc).isoformat(),
                "stream_id": batch.stream_id,
                "first_sequence": batch.first_sequence,
                "last_sequence": batch.last_sequence,
                "accepted_count": batch.accepted_count,
                "dropped_count": batch.dropped_count,
                "trades": [
                    {
                        "sequence": trade.sequence,
                        "trade_id": trade.trade_id,
                        "event_time": trade.event_time.astimezone(
                            timezone.utc
                        ).isoformat(),
                        "price": d2s(trade.price),
                        "quantity": d2s(trade.quantity),
                        "notional": d2s(trade.notional),
                        "side": trade.side,
                    }
                    for trade in batch.trades
                ],
            },
        )
        await self._broadcast(message)
        self.tape_batches_broadcast += 1
        self.tape_trades_broadcast += batch.accepted_count

    async def on_book_update(self, projection: BookProjection) -> None:
        """Broadcast one bounded LIVE DOM projection and cache it for reconnect."""
        if projection.sync_state != SYNCED and projection.sync_state not in FAIL_CLOSED_STATES:
            raise ValueError(f"unknown book sync_state: {projection.sync_state}")
        synced = projection.sync_state == SYNCED
        if synced and (
            projection.best_bid is None
            or projection.best_ask is None
            or projection.spread is None
        ):
            raise ValueError("SYNCED BOOK_UPDATE requires best bid, best ask, and spread")
        book_sequence = self.book_updates_broadcast + 1
        bids = projection.bids if synced else ()
        asks = projection.asks if synced else ()
        message = envelope(
            "BOOK_UPDATE",
            projection.projection_time,
            self.symbol,
            {
                "book_stream_id": self.book_stream_id,
                "book_sequence": book_sequence,
                "event_time": (
                    projection.event_time.astimezone(timezone.utc).isoformat()
                    if projection.event_time is not None else None
                ),
                "projection_time": projection.projection_time.astimezone(
                    timezone.utc
                ).isoformat(),
                "last_update_id": projection.last_update_id,
                "sync_state": projection.sync_state,
                "bids": [
                    {"price": d2s(price), "qty": d2s(quantity)}
                    for price, quantity in bids
                ],
                "asks": [
                    {"price": d2s(price), "qty": d2s(quantity)}
                    for price, quantity in asks
                ],
                "depth_levels": projection.depth_levels,
                "best_bid": d2s(projection.best_bid) if synced else None,
                "best_ask": d2s(projection.best_ask) if synced else None,
                "spread": d2s(projection.spread) if synced else None,
                "age_ms": projection.age_ms,
            },
        )
        self._latest_book_message = message
        self.book_updates_broadcast = book_sequence
        if self.persistent_writer is not None:
            self.persistent_writer.append(message["payload"])
        await self._broadcast(message)

    async def on_candle(
        self,
        candle,
        footprint_levels,
        orderbook_snapshot,
        session_vwap: Optional[Decimal] = None,
        vwap_status: Optional[str] = None,
    ) -> None:
        levels = [
            {"price": lv["price"], "bid": lv["bid"], "ask": lv["ask"]}
            for lv in footprint_levels
        ]
        poc, vah, val = compute_value_area(levels)
        book = {"last_update_id": None, "bids": [], "asks": [], "depth_levels": self.depth_levels}
        if orderbook_snapshot is not None:
            bids = sorted(orderbook_snapshot.bids.items(), key=lambda x: x[0], reverse=True)
            asks = sorted(orderbook_snapshot.asks.items(), key=lambda x: x[0])
            book = {
                "last_update_id": orderbook_snapshot.last_update_id,
                "bids": [{"price": str(p), "qty": str(q)} for p, q in bids[: self.depth_levels]],
                "asks": [{"price": str(p), "qty": str(q)} for p, q in asks[: self.depth_levels]],
                "depth_levels": self.depth_levels,
            }
        quality = _vwap_status(session_vwap, vwap_status)
        await self._broadcast(envelope("CANDLE", candle.bar_time, self.symbol, {
            "bar_time": candle.bar_time.astimezone(timezone.utc).isoformat(),
            "timeframe": candle.timeframe,
            "open": d2s(candle.open), "high": d2s(candle.high),
            "low": d2s(candle.low), "close": d2s(candle.close),
            "volume": d2s(candle.volume), "delta": d2s(candle.delta), "cvd": d2s(candle.cvd),
            "vwap": d2s(session_vwap),
            "vwap_status": quality,
            "footprint": {
                "levels": [{"price": str(l["price"]), "bid": str(l["bid"]), "ask": str(l["ask"])} for l in levels],
                "poc_price": poc, "vah_price": vah, "val_price": val,
            },
            "orderbook": book,
        }))

    async def on_analysis(self, analysis_result, signal_result, module_scores, absorption_result, divergence=None, imbalance_result=None, imbalance_detector=None, flow_events=None) -> None:
        now = analysis_result.analysis_time
        await self._broadcast(envelope("ANALYSIS", now, self.symbol, {
            "divergence": None if divergence is None else {
                "direction": divergence.direction.value,
                "kind": divergence.kind.value,
                "pivot_time": divergence.pivot_time.astimezone(timezone.utc).isoformat(),
                "previous_pivot_time": divergence.previous_pivot_time.astimezone(timezone.utc).isoformat(),
                "pivot_price": d2s(divergence.pivot_price),
                "previous_pivot_price": d2s(divergence.previous_pivot_price),
                "pivot_cvd": d2s(divergence.pivot_cvd),
                "previous_pivot_cvd": d2s(divergence.previous_pivot_cvd),
                "price_change": d2s(divergence.price_change),
                "cvd_change": d2s(divergence.cvd_change),
                "bars_between": divergence.bars_between,
            },
            "imbalance": None if imbalance_result is None else {
                "walls": [
                    {
                        "side": si.direction,
                        "count": si.count,
                        "price_start": d2s(si.start_price),
                        "price_end": d2s(si.end_price),
                    }
                    for si in imbalance_result.stacked_imbalances
                ],
                "ratio_threshold": d2s(imbalance_detector.ratio_threshold) if imbalance_detector is not None else None,
                "stack_count": imbalance_detector.stack_count if imbalance_detector is not None else None,
                "ratio_cap": d2s(imbalance_detector.ratio_cap) if imbalance_detector is not None else None,
                "min_volume": d2s(imbalance_detector.last_effective_min_volume) if imbalance_detector is not None else None,
            },
            "absorption": None if absorption_result is None else {
                "classification": absorption_result.classification,
                "strength": d2s(absorption_result.strength),
                "price_low": d2s(absorption_result.price_low),
                "price_high": d2s(absorption_result.price_high),
            },
            "flow_events": None if not flow_events else [
                {"event_time": fe.event_time.astimezone(timezone.utc).isoformat(),
                 "category": fe.kind.upper(), "kind": fe.kind, "side": fe.side,
                 "strength": d2s(fe.strength), "price": d2s(fe.price),
                 "detector": fe.kind,
                 "detail": fe.detail if isinstance(fe.detail, dict) else {}}
                for fe in flow_events
            ],
        }))

    async def on_flow_event(self, ev) -> None:
        category = str(getattr(ev, "category", getattr(ev, "kind", "UNKNOWN"))).upper()
        detector = str(getattr(ev, "detector", getattr(ev, "kind", category)))
        detail = getattr(ev, "detail", {})
        await self._broadcast(envelope("FLOW", ev.event_time, self.symbol, {
            "event_time": ev.event_time.astimezone(timezone.utc).isoformat(),
            "category": category, "side": ev.side,
            "strength": d2s(ev.strength), "price": d2s(getattr(ev, "price", None)),
            "detector": detector, "detail": detail,
        }))

    async def on_flow_response(self, snapshots) -> None:
        """Broadcast observational order-flow/price-response windows."""
        snapshots = tuple(snapshots)
        if not snapshots:
            return
        now = max(s.event_time for s in snapshots)
        await self._broadcast(envelope("FLOW_RESPONSE", now, self.symbol, {
            "windows": [
                {
                    "window_sec": s.window_sec,
                    "state": s.state.value,
                    "pressure_side": s.pressure_side,
                    "buy_volume": d2s(s.buy_volume),
                    "sell_volume": d2s(s.sell_volume),
                    "total_volume": d2s(s.total_volume),
                    "delta": d2s(s.delta),
                    "pressure_ratio": d2s(s.pressure_ratio),
                    "persistence": d2s(s.persistence),
                    "first_price": d2s(s.first_price),
                    "last_price": d2s(s.last_price),
                    "price_change": d2s(s.price_change),
                    "price_change_bps": d2s(s.price_change_bps),
                    "relative_volume": d2s(s.relative_volume),
                    "trade_count": s.trade_count,
                }
                for s in snapshots
            ],
            "note": "observed state; not a trade signal or probability",
        }))

    async def on_liquidation(self, liq) -> None:
        await self._broadcast(envelope("LIQUIDATION", liq.event_time, self.symbol, {
            "side": liq.side, "price": d2s(liq.price), "quantity": d2s(liq.quantity),
        }))

    async def on_oi(
        self,
        event_time: datetime,
        open_interest: Decimal,
        prev: Optional[Decimal],
        *,
        received_time: Optional[datetime] = None,
        source: str = "BINANCE_USDM",
        poll_interval_sec: int = 10,
    ) -> None:
        change = open_interest - prev if prev is not None else None
        change_pct = (
            (change / prev) * Decimal("100")
            if change is not None and prev is not None and prev > 0 else None
        )
        await self._broadcast(envelope("OI", event_time, self.symbol, {
            "open_interest": d2s(open_interest), "prev": d2s(prev),
            "change": d2s(change), "change_pct": d2s(change_pct),
            "source_time": event_time.astimezone(timezone.utc).isoformat(),
            "received_time": (
                received_time or datetime.now(timezone.utc)
            ).astimezone(timezone.utc).isoformat(),
            "source": source,
            "poll_interval_sec": poll_interval_sec,
        }))

    async def on_hfm_quote(self, quote) -> None:
        """Broadcast the directly observed HFM Bid/Ask and USD spread."""
        message = envelope(
            "HFM_QUOTE",
            quote.received_time,
            self.symbol,
            {
                "hfm_symbol": quote.symbol,
                "source_time": (
                    quote.source_time.astimezone(timezone.utc).isoformat()
                    if quote.source_time is not None else None
                ),
                "received_time": quote.received_time.astimezone(timezone.utc).isoformat(),
                "sequence": quote.sequence,
                "bid": d2s(quote.bid),
                "ask": d2s(quote.ask),
                "spread_usd": d2s(quote.spread),
            },
        )
        self._latest_hfm_message = message
        await self._broadcast(message)

    async def on_combined_context(self, event) -> None:
        """Broadcast a closed native 5m/10m four-axis observation."""
        entry = event.hfm_entry
        await self._broadcast(envelope(
            "COMBINED_CONTEXT",
            event.event_time,
            self.symbol,
            {
                "event_time": event.event_time.astimezone(timezone.utc).isoformat(),
                "bar_time": event.bar_time.astimezone(timezone.utc).isoformat(),
                "timeframe": event.timeframe,
                "pattern_no": event.context.pattern.number,
                "pattern_name": event.context.pattern.name,
                "price_direction": event.context.pattern.price_direction,
                "cvd_direction": event.context.pattern.cvd_direction,
                "delta_direction": event.context.pattern.delta_direction,
                "oi_direction": event.context.oi_direction.value,
                "oi_open": d2s(event.oi_open),
                "oi_close": d2s(event.oi_close),
                "oi_change": d2s(event.oi_change),
                "oi_change_pct": d2s(event.oi_change_pct),
                "oi_sample_count": event.oi_sample_count,
                "context_code": event.context.code,
                "context_title": event.context.title,
                "context_summary_ja": event.context.summary_ja,
                "hfm_entry_status": event.hfm_entry_status,
                "hfm_symbol": entry.symbol if entry is not None else None,
                "hfm_entry_spread": d2s(entry.spread) if entry is not None else None,
            },
        ))


    async def on_bar_update(
        self,
        candle,
        footprint_levels,
        *,
        source_trade_id: Optional[int] = None,
        source_event_time: Optional[datetime] = None,
        session_vwap: Optional[Decimal] = None,
        vwap_status: Optional[str] = None,
    ) -> None:
        """進行中バーのスナップショット配信 (BAR_UPDATE)。

        CANDLE と同形の footprint 構造 (levels 価格降順) + in_progress=true。
        orderbook は含めない (板は CANDLE 配信に同梱済み・軽量化のため)。
        """
        levels = [
            {"price": lv["price"], "bid": lv["bid"], "ask": lv["ask"]}
            for lv in footprint_levels
        ]
        poc, vah, val = compute_value_area(levels)
        quality = _vwap_status(session_vwap, vwap_status)
        await self._broadcast(envelope("BAR_UPDATE", candle.bar_time, self.symbol, {
            "bar_time": candle.bar_time.astimezone(timezone.utc).isoformat(),
            "timeframe": candle.timeframe,
            "in_progress": True,
            "source_trade_id": source_trade_id,
            "source_event_time": (
                source_event_time.astimezone(timezone.utc).isoformat()
                if source_event_time is not None else None
            ),
            "open": d2s(candle.open), "high": d2s(candle.high),
            "low": d2s(candle.low), "close": d2s(candle.close),
            "volume": d2s(candle.volume), "delta": d2s(candle.delta), "cvd": d2s(candle.cvd),
            "vwap": d2s(session_vwap),
            "vwap_status": quality,
            "footprint": {
                "levels": [{"price": str(l["price"]), "bid": str(l["bid"]), "ask": str(l["ask"])} for l in levels],
                "poc_price": poc, "vah_price": vah, "val_price": val,
            },
        }))

    async def send_health(self, event_time: datetime, payload: dict) -> None:
        """SelfMonitor v1 の HEALTH メッセージ (payload は直列化可能な dict)。"""
        await self._broadcast(envelope("HEALTH", event_time, self.symbol, payload))

    async def send_stats(self, event_time: datetime, stats: dict) -> None:
        await self._broadcast(envelope("STATS", event_time, self.symbol,
                                       {k: str(v) for k, v in stats.items()}))






````

### `Delta_Engine_Pro4web/tools/persistent_depth_prototype.py`

````python
"""Isolated PD1 format prototype.

This module only encodes caller-supplied fixtures.  It never opens project data,
DuckDB, Parquet, or runtime paths.  zstandard is optional; when unavailable the
prototype uses a clearly labelled deflate fallback for repeatable local tests.
"""
from __future__ import annotations

import hashlib
import json
import struct
import time
import zlib
from dataclasses import dataclass
from typing import Iterable


MAGIC = b"DEPD1\0"


def _compress(data: bytes, level: int = 3) -> tuple[bytes, str]:
    try:
        import zstandard as zstd  # type: ignore
    except ImportError:
        return zlib.compress(data, max(1, min(9, level))), "DEFLATE_FALLBACK"
    return zstd.ZstdCompressor(level=level).compress(data), "ZSTD"


def _decompress(data: bytes, codec: str) -> bytes:
    if codec == "ZSTD":
        import zstandard as zstd  # type: ignore
        return zstd.ZstdDecompressor().decompress(data)
    if codec == "DEFLATE_FALLBACK":
        return zlib.decompress(data)
    raise ValueError(f"unsupported codec: {codec}")


def _canonical(frame: dict) -> bytes:
    return (json.dumps(frame, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _validate(frame: dict) -> None:
    if not isinstance(frame, dict) or not frame.get("book_stream_id"):
        raise ValueError("missing book stream")
    if not isinstance(frame.get("book_sequence"), int) or frame["book_sequence"] < 1:
        raise ValueError("invalid book sequence")
    if frame.get("sync_state") == "SYNCED" and (not frame.get("bids") or not frame.get("asks")):
        raise ValueError("synced frame has no levels")


@dataclass(frozen=True)
class Encoded:
    name: str
    codec: str
    payload: bytes
    source_count: int
    checksum: str


def encode_jsonl(frames: Iterable[dict], level: int = 3) -> Encoded:
    rows = list(frames)
    for frame in rows:
        _validate(frame)
    raw = b"".join(_canonical(frame) for frame in rows)
    payload, codec = _compress(raw, level)
    return Encoded("JSONL_ZSTD", codec, payload, len(rows), hashlib.sha256(raw).hexdigest())


def encode_binary(frames: Iterable[dict], level: int = 3) -> Encoded:
    rows = list(frames)
    for frame in rows:
        _validate(frame)
    raw = MAGIC + b"".join(struct.pack(">I", len(blob)) + blob for blob in (_canonical(f) for f in rows))
    payload, codec = _compress(raw, level)
    return Encoded("BINARY_ZSTD", codec, payload, len(rows), hashlib.sha256(raw).hexdigest())


def encode_keyframe_diff(frames: Iterable[dict], keyframe_every: int = 5, level: int = 3) -> Encoded:
    rows = list(frames)
    records: list[dict] = []
    previous = None
    for index, frame in enumerate(rows):
        _validate(frame)
        if previous is None or index % max(1, keyframe_every) == 0:
            records.append({"kind": "KEYFRAME", "frame": frame})
        else:
            records.append({"kind": "DIFF", "frame": frame, "base_sequence": previous["book_sequence"]})
        previous = frame
    raw = b"".join(_canonical(record) for record in records)
    payload, codec = _compress(raw, level)
    return Encoded(f"KEYFRAME_DIFF_{keyframe_every}", codec, payload, len(rows), hashlib.sha256(raw).hexdigest())


def decode(encoded: Encoded) -> list[dict]:
    raw = _decompress(encoded.payload, encoded.codec)
    if encoded.name == "JSONL_ZSTD":
        rows = [json.loads(line) for line in raw.splitlines() if line]
    elif encoded.name == "BINARY_ZSTD":
        if not raw.startswith(MAGIC):
            raise ValueError("binary magic mismatch")
        cursor, rows = len(MAGIC), []
        while cursor < len(raw):
            size = struct.unpack(">I", raw[cursor : cursor + 4])[0]
            cursor += 4
            rows.append(json.loads(raw[cursor : cursor + size]))
            cursor += size
        if cursor != len(raw):
            raise ValueError("binary tail mismatch")
    elif encoded.name.startswith("KEYFRAME_DIFF_"):
        records = [json.loads(line) for line in raw.splitlines() if line]
        rows, previous = [], None
        for record in records:
            if record["kind"] == "KEYFRAME":
                previous = record["frame"]
            elif record["kind"] == "DIFF":
                if previous is None or record["base_sequence"] != previous["book_sequence"]:
                    raise ValueError("diff base mismatch")
                previous = record["frame"]
            else:
                raise ValueError("unknown record kind")
            rows.append(previous)
    else:
        raise ValueError(f"unsupported format: {encoded.name}")
    if len(rows) != encoded.source_count:
        raise ValueError("record count mismatch")
    return rows


def benchmark(frames: list[dict]) -> list[dict]:
    candidates = [lambda: encode_jsonl(frames), lambda: encode_binary(frames), lambda: encode_keyframe_diff(frames)]
    results = []
    for factory in candidates:
        started = time.perf_counter()
        encoded = factory()
        encode_ms = (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        decoded = decode(encoded)
        decode_ms = (time.perf_counter() - started) * 1000
        results.append({"candidate": encoded.name, "codec": encoded.codec, "source_count": encoded.source_count, "bytes": len(encoded.payload), "encode_ms": encode_ms, "decode_ms": decode_ms, "round_trip": decoded == frames})
    return results
````

### `Delta_Engine_Pro4web/tools/persistent_depth_recovery.py`

````python
"""PD2 isolated segment durability and replay contract prototype."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path


MAGIC = b"DEPD-SEGMENT-V1\n"


def _row(frame: dict) -> bytes:
    return (json.dumps(frame, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def write_segment(directory: str | os.PathLike[str], frames: list[dict], stream_id: str) -> dict:
    """Write a self-contained segment to an isolated directory atomically."""
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    body = MAGIC + b"".join(_row(frame) for frame in frames)
    checksum = hashlib.sha256(body).hexdigest()
    final = target / f"segment-{stream_id}.jsonl"
    temp = target / f".{final.name}.tmp"
    with temp.open("wb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, final)
    manifest = {"segment": final.name, "stream_id": stream_id, "first_sequence": frames[0]["book_sequence"] if frames else None, "last_sequence": frames[-1]["book_sequence"] if frames else None, "record_count": len(frames), "byte_count": len(body), "sha256": checksum, "schema_revision": "PD1-PROTOTYPE"}
    (target / f"{final.name}.manifest.json").write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def read_segment(directory: str | os.PathLike[str], manifest: dict) -> list[dict]:
    path = Path(directory) / manifest["segment"]
    body = path.read_bytes()
    if hashlib.sha256(body).hexdigest() != manifest["sha256"]:
        raise ValueError("SEGMENT CHECKSUM MISMATCH")
    if not body.startswith(MAGIC):
        raise ValueError("SEGMENT MAGIC MISMATCH")
    rows = [json.loads(line) for line in body[len(MAGIC) :].splitlines() if line]
    if len(rows) != manifest["record_count"]:
        raise ValueError("SEGMENT RECORD COUNT MISMATCH")
    if rows and (rows[0]["book_sequence"] != manifest["first_sequence"] or rows[-1]["book_sequence"] != manifest["last_sequence"]):
        raise ValueError("SEGMENT SEQUENCE MANIFEST MISMATCH")
    return rows


def replay_segment(directory: str | os.PathLike[str], manifest: dict, live_frames=None) -> list[dict]:
    """Replay only durable segment rows; live_frames is intentionally ignored."""
    del live_frames
    return read_segment(directory, manifest)


def isolated_directory() -> tempfile.TemporaryDirectory:
    return tempfile.TemporaryDirectory(prefix="delta-pd2-")


````

### `Delta_Engine_Pro4web/tests/webapp/test_persistent_depth_writer.py`

````python
from pathlib import Path

from webapp.persistent_depth_writer import PersistentDepthWriter


def payload(sequence, stream="s"):
    return {"book_stream_id": stream, "book_sequence": sequence, "sync_state": "SYNCED", "bids": [{"price": "100", "qty": "1"}], "asks": [{"price": "101", "qty": "2"}]}


def test_writer_rotates_segments_and_writes_manifest(tmp_path):
    writer = PersistentDepthWriter(tmp_path, "BTCUSDT", max_frames=2)
    for sequence in range(1, 5):
        writer.append(payload(sequence))
    writer.close()
    finals = sorted((tmp_path / "symbol=BTCUSDT").glob("*.jsonl"))
    manifests = sorted((tmp_path / "symbol=BTCUSDT").glob("*.manifest.json"))
    assert len(finals) == 2
    assert len(manifests) == 2
    assert not list((tmp_path / "symbol=BTCUSDT").glob("*.part"))


def test_writer_separates_streams(tmp_path):
    writer = PersistentDepthWriter(tmp_path, "BTCUSDT", max_frames=10)
    writer.append(payload(1, "a"))
    writer.append(payload(1, "b"))
    writer.close()
    names = [path.name for path in (tmp_path / "symbol=BTCUSDT").glob("*.jsonl")]
    assert any("stream=a" in name for name in names)
    assert any("stream=b" in name for name in names)
````

### `Delta_Engine_Pro4web/docker-compose.yml`

````yaml
version: "3.9"
services:
  deltaengine_clone:
    build: .
    ports:
      - "18080:8080"
      # MT5 Adapter (SIGNAL/HEARTBEAT)。ホストの loopback のみに公開（LAN 非公開）。
      # MT5 は同一 Windows ホスト上の 127.0.0.1:15555 へ接続する。
      - "127.0.0.1:15555:5555"
    volumes:
      - ./data_05M:/app/data_05M
      - ./config:/app/config
      - ./webapp/static:/app/webapp/static
      - type: bind
        source: ${APPDATA}/MetaQuotes/Terminal/Common/Files/DeltaEngine_HFM_quotes_utf8.jsonl
        target: /app/data_05M/hfm/DeltaEngine_HFM_quotes_utf8.jsonl
        read_only: true
      # バージョン単一情報源(webapp/version.py が /app/CHANGELOG.md を読む)
      - ../ArchitectureRepository/00_Master/CHANGELOG.md:/app/CHANGELOG.md:ro
    environment:
      - PYTHONUNBUFFERED=1
      - HFM_QUOTE_FILE=/app/data_05M/hfm/DeltaEngine_HFM_quotes_utf8.jsonl
      - HOOK_OBSERVER_CONFIG=/app/config/hook_observer.yaml
      # PD4 compatibility boundary: persistent writer remains disabled.
      - PERSISTENT_DEPTH_HISTORY_ENABLED=true
      - PERSISTENT_DEPTH_HISTORY_ROOT=/app/data_05M/depth_history
    restart: unless-stopped


````

## P1-0-a 現在のorderbook受信箇所（行番号付き）

以下は`@depth`購読からREST snapshot、raw記録、正規化、book適用、50段投影、persistent writer呼出しまでの現行経路。

### `Delta_Engine_Pro4web/config/config.yaml:15`

````text
   15: websocket:
   16:   url: "wss://fstream.binance.com/ws"
   17:   reconnect: true
   18:   reconnect_delay_sec: 5
   19:   reconnect_max_retries: 0
   20:   heartbeat_sec: 30
   21:   connect_timeout_sec: 10
   22:   subscribe_streams:
   23:     - "btcusdt@trade"
   24:     - "btcusdt@depth@100ms"
   25:     - "btcusdt@forceOrder"
````

### `Delta_Engine_Pro4web/src/acquisition/binance_ws.py:65`

````text
   65: def is_agg_trade_or_depth(message: Any) -> bool:
   66:     """True for trade events (aggTrade or trade), depthUpdate, or forceOrder — passes all feeds.
   67: 
   68:     B-1 addition: use this predicate when the pipeline should process both
   69:     trade (CVD/Footprint/Imbalance path) and depthUpdate (Order Book /
   70:     Absorption path). Subscription-ack frames and other control messages are
   71:     rejected here so they are counted by DataReceiver as filtered, not silently lost.
   72: 
   73:     Accepts both "aggTrade" (@aggTrade stream) and "trade" (@trade stream) so the
   74:     pipeline works with either Binance Futures trade stream variant.
   75:     Also accepts "forceOrder" (@forceOrder stream, 清算注文ストリーム) for liquidation tracking.
   76:     """
   77:     if not isinstance(message, dict):
   78:         return False
   79:     return message.get("e") in ("aggTrade", "trade", "depthUpdate", "forceOrder")
````

### `Delta_Engine_Pro4web/src/acquisition/binance_ws.py:132`

````text
  132: def make_binance_connect(
  133:     *,
  134:     ping_interval: Optional[float] = None,
  135:     ping_timeout: Optional[float] = 20,
  136:     subscribe_id: int = 1,
  137:     ws_connect: Optional[WsConnect] = None,
  138: ) -> Callable[[str, list[str]], Awaitable[AsyncIterator[dict]]]:
  139:     """Build a ConnectFn for the ExchangeConnector.
  140: 
  141:     The returned coroutine opens the connection, sends the Binance SUBSCRIBE
  142:     control frame for ``streams``, and returns a ``BinanceStream``. Any failure
  143:     to connect or subscribe is raised as ``ConnectionError``.
  144: 
  145:     ``ping_interval`` maps to the WebSocket_v3.2 heartbeat; ``ws_connect`` is
  146:     injectable so the adapter is unit-testable without a network (defaults to
  147:     ``websockets.connect``).
  148:     """
  149:     connector: WsConnect = ws_connect or websockets.connect
  150: 
  151:     async def connect(url: str, streams: list[str]) -> AsyncIterator[dict]:
  152:         try:
  153:             ws = await connector(url, ping_interval=ping_interval, ping_timeout=ping_timeout)
  154:         except (OSError, InvalidURI, InvalidHandshake, WebSocketException) as exc:
  155:             raise ConnectionError(f"binance connect failed: {exc}") from exc
  156: 
  157:         subscribe = {"method": "SUBSCRIBE", "params": list(streams), "id": subscribe_id}
  158:         try:
  159:             await ws.send(json.dumps(subscribe))
  160:         except (WebSocketException, OSError) as exc:
  161:             await _safe_close(ws)
  162:             raise ConnectionError(f"binance subscribe failed: {exc}") from exc
  163: 
  164:         logger.info("binance subscribed streams=%s url=%s", streams, url)
  165:         return BinanceStream(ws)
  166: 
  167:     return connect
````

### `Delta_Engine_Pro4web/src/acquisition/receiver.py:29`

````text
   29: class JsonlRecorder:
   30:     """Append-only JSON Lines recorder with deterministic serialization.
   31: 
   32:     One JSON object per line, keys sorted, compact separators — so a recorded
   33:     stream replays byte-identically (deterministic replay, M6).
   34:     """
   35: 
   36:     def __init__(self, path: str | Path) -> None:
   37:         self.path = Path(path)
   38:         self.path.parent.mkdir(parents=True, exist_ok=True)
   39:         self._handle = self.path.open("w", encoding="utf-8")
   40:         self.written = 0
   41: 
   42:     def write(self, obj: dict) -> None:
   43:         self._handle.write(json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n")
   44:         self.written += 1
   45: 
   46:     def close(self) -> None:
   47:         self._handle.close()
````

### `Delta_Engine_Pro4web/src/acquisition/receiver.py:61`

````text
   61: class DataReceiver:
   62:     """Validate → (record) → forward raw events, preserving arrival order."""
   63: 
   64:     def __init__(
   65:         self,
   66:         source: BoundedEventQueue,
   67:         destination: BoundedEventQueue,
   68:         *,
   69:         recorder: Optional[JsonlRecorder] = None,
   70:         validate: Callable[[Any], bool] = default_validate,
   71:         sequence_key: Optional[Callable[[dict], Any]] = None,
   72:     ) -> None:
   73:         self._source = source
   74:         self._destination = destination
   75:         self._recorder = recorder
   76:         self._validate = validate
   77:         self._sequence_key = sequence_key
   78:         self._last_seq: Any = None
   79:         # counters
   80:         self.forwarded = 0
   81:         self.invalid = 0
   82:         self.out_of_order = 0
   83: 
   84:     async def run(self) -> None:
   85:         """Consume until the STOP sentinel; forward valid events in order."""
   86:         while True:
   87:             message = await self._source.get()
   88:             if message is STOP:
   89:                 break
   90:             if not self._validate(message):
   91:                 self.invalid += 1
   92:                 logger.warning("%s invalid payload discarded: %r", ERROR_INVALID_MARKET_DATA, message)
   93:                 continue
   94:             if self._sequence_key is not None:
   95:                 key = self._sequence_key(message)
   96:                 if self._last_seq is not None and key < self._last_seq:
   97:                     self.out_of_order += 1  # informational; reordering is the Normalizer's job
   98:                 self._last_seq = key
   99:             if self._recorder is not None:
  100:                 self._recorder.write(message)
  101:             await self._destination.put(message)
  102:             self.forwarded += 1
````

### `Delta_Engine_Pro4web/src/acquisition/binance_rest.py:49`

````text
   49: async def fetch_depth_snapshot(
   50:     symbol: str,
   51:     limit: int = 1000,
   52:     base_url: str = _DEFAULT_BASE_URL,
   53: ) -> dict:
   54:     """GET /fapi/v1/depth?symbol={symbol}&limit={limit} -> raw dict.
   55: 
   56:     Raises ConnectionError on HTTP error or timeout.
   57:     Numbers are returned as-is (strings) — the caller performs Decimal conversion.
   58:     """
   59:     url = f"{base_url}{_DEPTH_PATH}"
   60:     params = {"symbol": symbol, "limit": limit}
   61:     timeout = aiohttp.ClientTimeout(total=_TIMEOUT_SEC)
   62:     try:
   63:         async with aiohttp.ClientSession(timeout=timeout) as session:
   64:             async with session.get(url, params=params) as response:
   65:                 if response.status != 200:
   66:                     text = await response.text()
   67:                     raise ConnectionError(
   68:                         f"depth snapshot HTTP {response.status}: {text[:200]}"
   69:                     )
   70:                 data = await response.json()
   71:                 logger.info(
   72:                     "depth snapshot fetched symbol=%s lastUpdateId=%s",
   73:                     symbol, data.get("lastUpdateId"),
   74:                 )
   75:                 return data
   76:     except aiohttp.ClientError as exc:
   77:         raise ConnectionError(f"depth snapshot request failed: {exc}") from exc
   78:     except asyncio.TimeoutError as exc:
   79:         raise ConnectionError(f"depth snapshot timeout after {_TIMEOUT_SEC}s") from exc
   80: 
   81: 
   82: async def fetch_open_interest(
   83:     symbol: str,
   84:     base_url: str = _DEFAULT_BASE_URL,
   85: ) -> dict:
   86:     """GET /fapi/v1/openInterest?symbol={symbol} -> raw dict.
   87: 
   88:     Raises ConnectionError on HTTP error or timeout.
   89:     Numbers are returned as API strings — the caller performs Decimal conversion.
````

### `Delta_Engine_Pro4web/src/acquisition/binance_rest.py:124`

````text
  124: def rest_to_depth_event(raw_rest: dict, symbol: str) -> dict:
  125:     """Convert a REST /fapi/v1/depth response to normalizer depthSnapshot format.
  126: 
  127:     Binance Futures REST response shape:
  128:         {"lastUpdateId": int, "E": epoch_ms, "T": epoch_ms,
  129:          "bids": [[price, qty], ...], "asks": [[price, qty], ...]}
  130: 
  131:     binance.yaml order_book_mapping expects:
  132:         e="depthSnapshot", s=symbol, E=event_time_ms, u=lastUpdateId,
  133:         b=bids, a=asks.
  134:     """
  135:     # Binance Futures REST depth payloads provide lastUpdateId/bids/asks but
  136:     # no event timestamp. Supply the local receipt time for the normalizer's
  137:     # canonical event_time; it is metadata only and never drives book ordering.
  138:     event_time_ms = raw_rest.get("E", raw_rest.get("T", time.time_ns() // 1_000_000))
  139:     return {
  140:         "e": "depthSnapshot",
  141:         "s": symbol,
  142:         "E": event_time_ms,
  143:         "u": raw_rest["lastUpdateId"],
  144:         "b": raw_rest["bids"],
  145:         "a": raw_rest["asks"],
  146:     }
````

### `Delta_Engine_Pro4web/src/normalization/normalizer.py:386`

````text
  386:     def process_depth(self, raw: dict[str, Any]) -> Optional[OrderBookUpdate]:
  387:         """Normalize one raw depth event; return canonical update or None.
  388: 
  389:         Returns None and increments depth_filtered when the profile has no
  390:         order_book_mapping (decision 5 — backward compatible). Returns None
  391:         and increments depth_rejected on normalization failure.
  392:         """
  393:         if self.profile.order_book_mapping is None:
  394:             self.depth_filtered += 1
  395:             return None
  396:         try:
  397:             update = normalize_raw_depth(raw, self.profile)
  398:         except NormalizationError as exc:
  399:             self.depth_rejected += 1
  400:             logger.warning("%s depth normalization rejected: %s", exc.code, exc.reason)
  401:             return None
  402:         self.depth_processed += 1
  403:         return update
  404: 
  405:     def classify_raw(self, raw: dict[str, Any]) -> str:
  406:         """Return "trade" | "depth" | "liquidation" based on the active exchange profile.
  407: 
  408:         "liquidation" when the raw event's "e" field is "forceOrder" (@forceOrder stream).
  409:         "depth" when the profile has order_book_mapping AND the raw event's
  410:         event_type_field matches a known depth event type. Otherwise "trade"
  411:         (consumers treat unknown / unmappable events as trade for backward compat).
  412:         """
  413:         if raw.get("e") == "forceOrder":
  414:             return "liquidation"
  415:         ob = self.profile.order_book_mapping
  416:         if ob is not None:
  417:             etype = raw.get(ob["event_type_field"])
  418:             if etype in (ob["event_type_snapshot"], ob["event_type_diff"]):
  419:                 return "depth"
  420:         return "trade"
````

### `Delta_Engine_Pro4web/src/normalization/normalizer.py:473`

````text
  473: def normalize_raw_depth(
  474:     raw: dict[str, Any],
  475:     profile: ExchangeProfile,
  476: ) -> OrderBookUpdate:
  477:     """Map one raw depth event to a canonical Order Book Update Record.
  478: 
  479:     Raises NormalizationError on unmappable input. The caller (process_depth)
  480:     guards against a None order_book_mapping before calling here.
  481:     """
  482:     ob = profile.order_book_mapping
  483:     if ob is None:
  484:         raise NormalizationError("no order_book_mapping in profile")
  485: 
  486:     # Determine update_type from event type discriminator.
  487:     raw_etype = raw.get(ob["event_type_field"])
  488:     if raw_etype == ob["event_type_snapshot"]:
  489:         update_type = "SNAPSHOT"
  490:     elif raw_etype == ob["event_type_diff"]:
  491:         update_type = "DIFF"
  492:     else:
  493:         raise NormalizationError(
  494:             f"unknown depth event type {raw_etype!r} "
  495:             f"(expected {ob['event_type_snapshot']!r} or {ob['event_type_diff']!r})"
  496:         )
  497: 
  498:     # symbol
  499:     sym_key = ob["symbol_field"]
  500:     if sym_key not in raw:
  501:         raise NormalizationError(f"missing depth symbol field {sym_key!r}")
  502:     symbol = str(raw[sym_key])
  503: 
  504:     # event_time
  505:     et_key = ob["event_time_field"]
  506:     if et_key not in raw:
  507:         raise NormalizationError(f"missing depth event_time field {et_key!r}")
  508:     try:
  509:         event_time = _convert_timestamp(raw[et_key], profile.timestamp_format)
  510:     except (NormalizationError, Exception) as exc:
  511:         raise NormalizationError(f"invalid depth event_time: {exc}") from exc
  512: 
  513:     # final_update_id (required for both SNAPSHOT and DIFF)
  514:     fuid_key = ob["final_update_id_field"]
  515:     if fuid_key not in raw:
  516:         raise NormalizationError(f"missing final_update_id field {fuid_key!r}")
  517:     try:
  518:         final_update_id = int(raw[fuid_key])
  519:     except (TypeError, ValueError) as exc:
  520:         raise NormalizationError(f"invalid final_update_id: {exc}") from exc
  521: 
  522:     # first_update_id (required for DIFF, optional for SNAPSHOT)
  523:     first_key = ob["first_update_id_field"]
  524:     first_update_id: Optional[int] = None
  525:     if update_type == "DIFF":
  526:         if first_key not in raw:
  527:             raise NormalizationError(
  528:                 f"DIFF missing first_update_id field {first_key!r}"
  529:             )
  530:         try:
  531:             first_update_id = int(raw[first_key])
  532:         except (TypeError, ValueError) as exc:
  533:             raise NormalizationError(f"invalid first_update_id: {exc}") from exc
  534:     elif first_key in raw and raw[first_key] is not None:
  535:         try:
  536:             first_update_id = int(raw[first_key])
  537:         except (TypeError, ValueError):
  538:             pass  # optional for SNAPSHOT — ignore invalid
  539: 
  540:     # bids and asks
  541:     pi = ob["level_price_index"]
  542:     qi = ob["level_quantity_index"]
  543:     bids = _parse_levels(raw, ob["bids_field"], pi, qi, "bids")
  544:     asks = _parse_levels(raw, ob["asks_field"], pi, qi, "asks")
  545: 
  546:     # previous_final_update_id (pu, Binance Futures @depth — optional field)
  547:     pu_key = ob.get("previous_final_update_id_field")
  548:     previous_final_update_id: Optional[int] = None
  549:     if pu_key and pu_key in raw:
  550:         try:
  551:             previous_final_update_id = int(raw[pu_key])
  552:         except (TypeError, ValueError):
  553:             pass
  554: 
  555:     return OrderBookUpdate(
  556:         event_time=event_time,
  557:         symbol=symbol,
  558:         update_type=update_type,
  559:         first_update_id=first_update_id,
  560:         final_update_id=final_update_id,
  561:         bids=bids,
  562:         asks=asks,
  563:         previous_final_update_id=previous_final_update_id,
  564:     )
  565: 
  566: 
  567: def _parse_levels(
  568:     raw: dict[str, Any],
  569:     field: str,
  570:     price_idx: int,
  571:     qty_idx: int,
  572:     side_name: str,
  573: ) -> tuple[BookLevel, ...]:
  574:     if field not in raw:
  575:         raise NormalizationError(f"missing {side_name} field {field!r}")
  576:     raw_levels = raw[field]
  577:     if not isinstance(raw_levels, list):
  578:         raise NormalizationError(f"{side_name} field {field!r} must be a list")
  579:     levels: list[BookLevel] = []
  580:     for i, item in enumerate(raw_levels):
  581:         try:
  582:             price = Decimal(str(item[price_idx]))
  583:             qty = Decimal(str(item[qty_idx]))
  584:         except (IndexError, TypeError, ValueError) as exc:
  585:             raise NormalizationError(
  586:                 f"{side_name}[{i}] cannot be parsed as BookLevel: {exc}"
  587:             ) from exc
  588:         levels.append(BookLevel(price=price, quantity=qty))
  589:     return tuple(levels)
````

### `Delta_Engine_Pro4web/src/orderflow/orderbook.py:97`

````text
   97: class OrderBookStateManager:
   98:     """Maintains live Order Book state by applying OrderBookUpdate records.
   99: 
  100:     SNAPSHOT establishes or re-establishes state. DIFF updates are applied
  101:     as set-to-value (quantity > 0 overwrites, quantity = 0 removes level).
  102:     Gap detection rejects out-of-sequence DIFFs and resets state.
  103:     """
  104: 
  105:     def __init__(
  106:         self,
  107:         symbol: str,
  108:         *,
  109:         clock: Callable[[], float] = time.monotonic,
  110:     ) -> None:
  111:         self.symbol = symbol
  112:         self._clock = clock
  113:         self._bids: dict[Decimal, Decimal] = {}
  114:         self._asks: dict[Decimal, Decimal] = {}
  115:         self._last_update_id: Optional[int] = None
  116:         self._last_event_time: Optional[datetime] = None
  117:         self._last_applied_monotonic: Optional[float] = None
  118:         self._initialized: bool = False
  119:         self._sync_id: Optional[int] = None   # set during initial Binance sync phase
  120:         # counters (no silent loss)
  121:         self.snapshots_applied: int = 0
  122:         self.diffs_applied: int = 0
  123:         self.diffs_rejected_before_snapshot: int = 0
  124:         self.diffs_stale: int = 0
  125:         self.gaps_detected: int = 0
  126: 
  127:     # -- public interface -------------------------------------------------------
  128: 
  129:     def apply(self, update: OrderBookUpdate) -> ApplyResult:
  130:         """Apply one OrderBookUpdate; return ApplyResult describing what happened."""
  131:         if update.symbol != self.symbol:
  132:             raise ValueError(
  133:                 f"symbol mismatch: manager is {self.symbol!r}, update is {update.symbol!r}"
  134:             )
  135: 
  136:         if update.update_type == "SNAPSHOT":
  137:             return self._apply_snapshot(update)
  138:         if update.update_type == "DIFF":
  139:             return self._apply_diff(update)
  140:         raise ValueError(f"unknown update_type: {update.update_type!r}")
  141: 
  142:     def apply_initial_sync(self, snapshot_update_id: int) -> None:
  143:         """Enter initial sync mode after applying a REST snapshot.
  144: 
  145:         Enables Binance-spec buffer alignment: buffered diffs with
  146:         final_update_id <= snapshot_update_id are counted as stale; the first
  147:         diff where first_update_id <= snapshot_update_id+1 <= final_update_id
  148:         exits sync mode and applies normally. Call immediately after
  149:         apply(SNAPSHOT update).
  150:         """
  151:         self._sync_id = snapshot_update_id
  152: 
  153: 
  154:     @property
  155:     def is_initialized(self) -> bool:
  156:         """True when Snapshot state exists, including initial alignment wait."""
  157:         return self._initialized
  158: 
  159:     @property
  160:     def is_synchronized(self) -> bool:
  161:         """True only after initial/resync Snapshot alignment has completed."""
  162:         return self._initialized and self._sync_id is None
  163: 
  164:     @property
  165:     def last_event_time(self) -> Optional[datetime]:
  166:         """Source time of the latest accepted state transition or detected gap."""
  167:         return self._last_event_time
  168: 
  169:     def age_ms(self, now_monotonic: Optional[float] = None) -> Optional[int]:
  170:         """Monotonic age of the latest applied Snapshot/DIFF."""
  171:         if self._last_applied_monotonic is None:
  172:             return None
  173:         now = self._clock() if now_monotonic is None else now_monotonic
  174:         return max(0, int((now - self._last_applied_monotonic) * 1000))
  175: 
  176:     def snapshot(self) -> Optional[OrderBookSnapshot]:
  177:         """Return immutable snapshot of current state, or None if not initialized."""
  178:         if not self._initialized:
  179:             return None
  180:         return OrderBookSnapshot(
  181:             symbol=self.symbol,
  182:             last_update_id=self._last_update_id,  # type: ignore[arg-type]
  183:             bids=dict(self._bids),
  184:             asks=dict(self._asks),
  185:             event_time=self._last_event_time,
  186:         )
  187: 
  188:     def bid_quantity_at(self, price: Decimal) -> Decimal:
  189:         return self._bids.get(_to_decimal(price), _ZERO)
  190: 
  191:     def ask_quantity_at(self, price: Decimal) -> Decimal:
  192:         return self._asks.get(_to_decimal(price), _ZERO)
  193: 
  194:     # -- private helpers --------------------------------------------------------
  195: 
  196:     def _apply_snapshot(self, update: OrderBookUpdate) -> ApplyResult:
  197:         reinitialized = self._initialized
  198:         self._bids = {}
  199:         self._asks = {}
  200:         for level in update.bids:
  201:             if level.quantity > _ZERO:
  202:                 self._bids[level.price] = level.quantity
  203:         for level in update.asks:
  204:             if level.quantity > _ZERO:
  205:                 self._asks[level.price] = level.quantity
  206:         self._last_update_id = update.final_update_id
  207:         self._sync_id = None
  208:         self._mark_applied(update)
  209:         self._initialized = True
  210:         self.snapshots_applied += 1
  211:         return ApplyResult(applied=True, reinitialized=reinitialized, gap_detected=False)
  212: 
  213:     def _apply_diff(self, update: OrderBookUpdate) -> ApplyResult:
  214:         # Reject if not yet initialized.
  215:         if not self._initialized:
  216:             self.diffs_rejected_before_snapshot += 1
  217:             logger.warning(
  218:                 "%s order book diff before snapshot: symbol=%s final_id=%s",
  219:                 ERROR_OUT_OF_ORDER, self.symbol, update.final_update_id,
  220:             )
  221:             return ApplyResult(applied=False, reinitialized=False, gap_detected=False)
  222: 
  223:         # Stale: already applied.
  224:         if update.final_update_id <= self._last_update_id:  # type: ignore[operator]
  225:             self.diffs_stale += 1
  226:             logger.warning(
  227:                 "%s order book stale diff: symbol=%s final_id=%s <= last_id=%s",
  228:                 ERROR_OUT_OF_ORDER, self.symbol,
  229:                 update.final_update_id, self._last_update_id,
  230:             )
  231:             return ApplyResult(applied=False, reinitialized=False, gap_detected=False)
  232: 
  233:         # Initial sync mode: accept first non-stale diff (lenient — Binance Futures
  234:         # batches can start at first_update_id > snap_id+1 due to connection timing).
  235:         if self._sync_id is not None:
  236:             self._sync_id = None
  237:             self._apply_levels(self._bids, update.bids)
  238:             self._apply_levels(self._asks, update.asks)
  239:             self._last_update_id = update.final_update_id
  240:             self._mark_applied(update)
  241:             self.diffs_applied += 1
  242:             return ApplyResult(applied=True, reinitialized=False, gap_detected=False)
  243: 
  244:         # Gap: sequence discontinuity.
  245:         # Prefer pu-based check (Binance Futures @depth: pu == prev_u guarantees
  246:         # continuity; U may jump legitimately between batches).
  247:         gap = False
  248:         if update.previous_final_update_id is not None:
  249:             gap = update.previous_final_update_id != self._last_update_id  # type: ignore[operator]
  250:         elif update.first_update_id is not None:
  251:             expected = self._last_update_id + 1  # type: ignore[operator]
  252:             gap = update.first_update_id != expected
  253:         if gap:
  254:             prev_id = self._last_update_id
  255:             self._bids = {}
  256:             self._asks = {}
  257:             self._last_update_id = None
  258:             self._sync_id = None
  259:             self._last_event_time = update.event_time
  260:             self._last_applied_monotonic = None
  261:             self._initialized = False
  262:             self.gaps_detected += 1
  263:             logger.warning(
  264:                 "%s order book gap detected: symbol=%s last_id=%s pu=%s first_id=%s",
  265:                 ERROR_OUT_OF_ORDER, self.symbol,
  266:                 prev_id, update.previous_final_update_id, update.first_update_id,
  267:             )
  268:             return ApplyResult(applied=False, reinitialized=False, gap_detected=True)
  269: 
  270:         # Apply set-to-value semantics.
  271:         self._apply_levels(self._bids, update.bids)
  272:         self._apply_levels(self._asks, update.asks)
  273:         self._last_update_id = update.final_update_id
  274:         self._mark_applied(update)
  275:         self.diffs_applied += 1
  276:         return ApplyResult(applied=True, reinitialized=False, gap_detected=False)
````

### `Delta_Engine_Pro4web/src/pipeline.py:98`

````text
   98: class _RecorderFanout:
   99:     """Preserve the legacy recorder while isolating an optional observation tap."""
  100: 
  101:     def __init__(self, legacy: Any | None, observation: Any | None) -> None:
  102:         self._legacy = legacy
  103:         self._observation = observation
  104: 
  105:     @property
  106:     def written(self) -> int:
  107:         return int(getattr(self._legacy, "written", 0))
  108: 
  109:     def write(self, obj: dict[str, Any]) -> None:
  110:         if self._legacy is not None:
  111:             self._legacy.write(obj)
  112:         if self._observation is not None:
  113:             try:
  114:                 self._observation.write(obj)
  115:             except Exception:
  116:                 logger.exception(
  117:                     "independent Hook observation tap failed; market pipeline continues"
  118:                 )
  119: 
  120:     def write_snapshot(self, obj: dict[str, Any], *, reason: str) -> None:
  121:         """Keep legacy bytes stable while adding acquisition reason to research raw."""
  122:         if self._legacy is not None:
  123:             self._legacy.write(obj)
  124:         if self._observation is not None:
  125:             observation_row = dict(obj)
  126:             observation_row["_capture_reason"] = reason
  127:             try:
  128:                 self._observation.write(observation_row)
  129:             except Exception:
  130:                 logger.exception(
  131:                     "independent Hook snapshot tap failed; market pipeline continues"
  132:                 )
  133: 
  134:     def close(self) -> None:
  135:         if self._legacy is not None:
  136:             self._legacy.close()
  137:         if self._observation is not None:
  138:             try:
  139:                 self._observation.close()
  140:             except Exception:
````

### `Delta_Engine_Pro4web/src/pipeline.py:191`

````text
  191: async def _book_resync_supervisor(
  192:     *,
  193:     symbol: str,
  194:     book_state: OrderBookStateManager,
  195:     normalizer: Any,
  196:     fetch_snapshot: Callable,
  197:     counters: BookResyncCounters,
  198:     recorder: Optional[Any] = None,
  199:     sleep: Callable[[int], Awaitable[None]] = asyncio.sleep,
  200: ) -> None:
  201:     """Keep the live order book initialized with retry and gap recovery."""
  202:     consecutive_failures = 0
  203:     synced_once = False
  204:     while True:
  205:         if book_state.is_initialized:
  206:             consecutive_failures = 0
  207:             await sleep(_BOOK_HEALTH_POLL_SEC)
  208:             continue
  209:         try:
  210:             raw_snap = await fetch_snapshot(symbol)
  211:             depth_evt = rest_to_depth_event(raw_snap, symbol)
  212:             update = normalizer.process_depth(depth_evt)
  213:             if update is None:
  214:                 raise ValueError("depth snapshot normalization returned None")
  215:             if recorder is not None:
  216:                 reason = "BOOK_RESYNC" if synced_once else "INITIAL_BOOK_SYNC"
  217:                 if hasattr(recorder, "write_snapshot"):
  218:                     recorder.write_snapshot(depth_evt, reason=reason)
  219:                 else:
  220:                     recorder.write(depth_evt)
  221:             book_state.apply(update)
  222:             book_state.apply_initial_sync(update.final_update_id)
  223:             if synced_once:
  224:                 counters.resyncs += 1
  225:                 logger.info("order book resynced: snap_id=%s resyncs=%s", update.final_update_id, counters.resyncs)
  226:             else:
  227:                 logger.info("initial snapshot applied: snap_id=%s (sync waiting for first diff with U<=%s)", update.final_update_id, update.final_update_id + 1)
  228:             synced_once = True
  229:             consecutive_failures = 0
  230:             await sleep(_BOOK_HEALTH_POLL_SEC)
  231:         except asyncio.CancelledError:
  232:             raise
  233:         except Exception as exc:
  234:             counters.fetch_failures += 1
  235:             delay = _BOOK_RESYNC_BACKOFF_SEC[min(consecutive_failures, len(_BOOK_RESYNC_BACKOFF_SEC) - 1)]
  236:             consecutive_failures += 1
  237:             logger.warning("depth snapshot fetch failed (attempt=%s, retry_in=%ss): %s", consecutive_failures, delay, exc)
  238:             await sleep(delay)
````

### `Delta_Engine_Pro4web/src/pipeline.py:1139`

````text
 1139:     async def run_async(
 1140:         self,
 1141:         *,
 1142:         duration_sec: Optional[float] = None,
 1143:         max_trades: Optional[int] = None,
 1144:         record_path: str | Path | None = None,
 1145:         raw_recorder: Any | None = None,
 1146:         connect: Optional[ConnectFn] = None,
 1147:         event_filter: Callable[[Any], bool] = is_agg_trade_or_depth,
 1148:         treat_stream_end_as_disconnect: bool = True,
 1149:         poll_interval: float = 0.5,
 1150:         fetch_snapshot: Optional[Callable] = fetch_depth_snapshot,
 1151:     ) -> LiveStats:
 1152:         """Run the live CVD+Absorption path until a stop condition; return a LiveStats.
 1153: 
 1154:         ``connect`` defaults to the real Binance transport; inject a fake
 1155:         ConnectFn (e.g. over ListTransport) for tests. ``record_path`` captures
 1156:         the forwarded stream and every applied REST depth snapshot as JSON
 1157:         Lines, so recorded depth diffs can be reconstructed exactly.
 1158:         ``raw_recorder`` is an independent optional append-only observation tap;
 1159:         when omitted, the pre-Stage-2A path is unchanged.
 1160:         """
 1161:         connect = connect or make_binance_connect(ping_interval=self.heartbeat_sec)
 1162: 
 1163:         out_q = BoundedEventQueue(self.queue_depth, self.overflow_policy, name="ws_out")
 1164:         norm_q = BoundedEventQueue(self.queue_depth, self.overflow_policy, name="receiver_out")
 1165: 
 1166:         connector = ExchangeConnector(
 1167:             url=self.ws_url,
 1168:             subscribe_streams=self.subscribe_streams,
 1169:             out_queue=out_q,
 1170:             connect=connect,
 1171:             reconnect=self.reconnect,
 1172:             reconnect_delay_sec=self.reconnect_delay_sec,
 1173:             reconnect_max_retries=self.reconnect_max_retries,
 1174:             connect_timeout_sec=self.connect_timeout_sec,
 1175:             heartbeat_sec=self.heartbeat_sec,
 1176:             treat_stream_end_as_disconnect=treat_stream_end_as_disconnect,
 1177:         )
 1178:         legacy_recorder = JsonlRecorder(record_path) if record_path else None
 1179:         recorder = (
 1180:             _RecorderFanout(legacy_recorder, raw_recorder)
 1181:             if legacy_recorder is not None or raw_recorder is not None
 1182:             else None
 1183:         )
 1184:         receiver = DataReceiver(
 1185:             out_q,
 1186:             norm_q,
 1187:             recorder=recorder,
 1188:             validate=lambda m: default_validate(m) and event_filter(m),
 1189:         )
 1190:         normalizer = DataNormalizer(self.profile, self.dedup_window, self.reorder_tolerance_ms)
````

### `Delta_Engine_Pro4web/src/pipeline.py:1481`

````text
 1481:         loop = asyncio.get_event_loop()
 1482:         connector_task = asyncio.create_task(connector.run())
 1483:         receiver_task = asyncio.create_task(receiver.run())
 1484: 
 1485:         # Order book sync is owned by the resync supervisor (ADR-010): it performs
 1486:         # the initial REST snapshot with retry, and re-syncs automatically after
 1487:         # gap-detection resets. fetch_snapshot=None disables it (tests).
 1488:         self.book_resync_counters = BookResyncCounters()
 1489:         book_supervisor_task: Optional[asyncio.Task] = None
 1490:         if fetch_snapshot is not None:
 1491:             book_supervisor_task = asyncio.create_task(_book_resync_supervisor(
 1492:                 symbol=self.symbol,
 1493:                 book_state=book_state,
 1494:                 normalizer=normalizer,
 1495:                 fetch_snapshot=fetch_snapshot,
 1496:                 counters=self.book_resync_counters,
 1497:                 recorder=recorder,
 1498:             ))
 1499:         deadline = (loop.time() + duration_sec) if duration_sec is not None else None
 1500:         trades_in = 0
 1501: 
 1502:         try:
 1503:             while True:
 1504:                 now = loop.time()
 1505:                 if deadline is not None and now >= deadline:
 1506:                     break
 1507:                 # Natural end: the connector stopped (finite/injected source) and
 1508:                 # everything it produced has been drained.
 1509:                 if connector_task.done() and out_q.empty() and norm_q.empty():
 1510:                     break
 1511:                 timeout = poll_interval
 1512:                 if deadline is not None:
 1513:                     timeout = min(poll_interval, max(0.0, deadline - now))
 1514:                 try:
 1515:                     raw = await asyncio.wait_for(norm_q.get(), timeout=timeout)
 1516:                 except asyncio.TimeoutError:
 1517:                     storage.tick()  # time-based flush while idle
 1518:                     continue
 1519:                 if raw is STOP:
 1520:                     break
 1521:                 kind = normalizer.classify_raw(raw)
 1522:                 if kind == "liquidation":
 1523:                     try:
 1524:                         liq_evt = normalize_raw_liquidation(raw, self.profile)
 1525:                         liquidation_buffer.append(liq_evt)
 1526:                         if liq_evt.side == "SELL":
 1527:                             long_liq_notional += liq_evt.price * liq_evt.quantity
 1528:                         else:
 1529:                             short_liq_notional += liq_evt.price * liq_evt.quantity
 1530:                         liquidations_received += 1
 1531:                         if self.on_liquidation is not None:
 1532:                             self.on_liquidation(liq_evt)
 1533:                     except NormalizationError as exc:
 1534:                         logger.warning("liquidation normalization failed: %s", exc)
 1535:                 elif kind == "depth":
 1536:                     update = normalizer.process_depth(raw)
 1537:                     if update is not None:
 1538:                         apply_result = book_state.apply(update)
 1539:                         book_snapshot = book_state.snapshot()
 1540:                         producer.observe_book_update(
 1541:                             update,
 1542:                             apply_result,
 1543:                             book_snapshot,
 1544:                             approved_tick_size=self.tick_size,
 1545:                         )
````

### `Delta_Engine_Pro4web/src/pipeline.py:1553`

````text
 1553:         finally:
 1554:             connector.stop()
 1555:             if book_supervisor_task is not None:
 1556:                 book_supervisor_task.cancel()
 1557:                 with contextlib.suppress(asyncio.CancelledError):
 1558:                     await book_supervisor_task
 1559:             # Unblock the receiver and let it forward anything still queued.
 1560:             await out_q.put(STOP)
 1561:             with contextlib.suppress(Exception):
 1562:                 await asyncio.wait_for(receiver_task, timeout=5)
 1563:             # Drain any events the receiver forwarded after the consumer stopped.
 1564:             while not norm_q.empty():
 1565:                 pending = norm_q.get_nowait()
 1566:                 if pending is STOP:
 1567:                     continue
 1568:                 kind = normalizer.classify_raw(pending)
 1569:                 if kind == "liquidation":
 1570:                     try:
 1571:                         liq_evt = normalize_raw_liquidation(pending, self.profile)
 1572:                         liquidation_buffer.append(liq_evt)
 1573:                         if liq_evt.side == "SELL":
 1574:                             long_liq_notional += liq_evt.price * liq_evt.quantity
 1575:                         else:
 1576:                             short_liq_notional += liq_evt.price * liq_evt.quantity
 1577:                         liquidations_received += 1
 1578:                         if self.on_liquidation is not None:
 1579:                             self.on_liquidation(liq_evt)
 1580:                     except NormalizationError as exc:
 1581:                         logger.warning("liquidation normalization failed: %s", exc)
 1582:                 elif kind == "depth":
 1583:                     update = normalizer.process_depth(pending)
 1584:                     if update is not None:
 1585:                         apply_result = book_state.apply(update)
 1586:                         book_snapshot = book_state.snapshot()
 1587:                         producer.observe_book_update(
 1588:                             update,
 1589:                             apply_result,
 1590:                             book_snapshot,
 1591:                             approved_tick_size=self.tick_size,
 1592:                         )
````

### `Delta_Engine_Pro4web/webapp/book_projection.py:85`

````text
   85: def build_book_projection(
   86:     book_state: Any,
   87:     *,
   88:     depth_levels: int = 50,
   89:     stale_after_ms: int = 2000,
   90:     now_monotonic: float | None = None,
   91:     projection_time: datetime | None = None,
   92: ) -> BookProjection:
   93:     """Read the current state without mutating or queueing analysis updates."""
   94:     if depth_levels < 1:
   95:         raise ValueError("depth_levels must be >= 1")
   96:     if stale_after_ms < 1:
   97:         raise ValueError("stale_after_ms must be >= 1")
   98:     projected_at = projection_time or _utc_now()
   99:     if projected_at.tzinfo is None:
  100:         raise ValueError("projection_time must be timezone-aware")
  101:     projected_at = projected_at.astimezone(timezone.utc)
  102: 
  103:     if book_state is None:
  104:         return _closed_projection(
  105:             projection_time=projected_at,
  106:             event_time=None,
  107:             last_update_id=None,
  108:             sync_state="NO_SNAPSHOT",
  109:             depth_levels=depth_levels,
  110:             age_ms=None,
  111:         )
  112: 
  113:     snapshot = book_state.snapshot()
  114:     event_time = getattr(book_state, "last_event_time", None)
  115:     if isinstance(event_time, datetime) and event_time.tzinfo is not None:
  116:         event_time = event_time.astimezone(timezone.utc)
  117:     elif event_time is not None:
  118:         event_time = None
  119:     age_ms = book_state.age_ms(now_monotonic)
  120: 
  121:     if snapshot is None:
  122:         state = "RESYNCING" if getattr(book_state, "gaps_detected", 0) else "NO_SNAPSHOT"
  123:         return _closed_projection(
  124:             projection_time=projected_at,
  125:             event_time=event_time,
  126:             last_update_id=None,
  127:             sync_state=state,
  128:             depth_levels=depth_levels,
  129:             age_ms=age_ms,
  130:         )
  131: 
  132:     if not getattr(book_state, "is_synchronized", False):
  133:         state = "RESYNCING" if getattr(book_state, "gaps_detected", 0) else "NO_SNAPSHOT"
  134:         return _closed_projection(
  135:             projection_time=projected_at,
  136:             event_time=event_time,
  137:             last_update_id=snapshot.last_update_id,
  138:             sync_state=state,
  139:             depth_levels=depth_levels,
  140:             age_ms=age_ms,
  141:         )
  142: 
  143:     if age_ms is None or age_ms > stale_after_ms:
  144:         return _closed_projection(
  145:             projection_time=projected_at,
  146:             event_time=event_time,
  147:             last_update_id=snapshot.last_update_id,
  148:             sync_state="STALE",
  149:             depth_levels=depth_levels,
  150:             age_ms=age_ms,
  151:         )
  152: 
  153:     if event_time is None:
  154:         return _closed_projection(
  155:             projection_time=projected_at,
  156:             event_time=None,
  157:             last_update_id=snapshot.last_update_id,
  158:             sync_state="INVALID",
  159:             depth_levels=depth_levels,
  160:             age_ms=age_ms,
  161:         )
  162: 
  163:     raw_bids = tuple(snapshot.bids.items())
  164:     raw_asks = tuple(snapshot.asks.items())
  165:     if any(
  166:         not price.is_finite()
  167:         or not quantity.is_finite()
  168:         or price <= 0
  169:         or quantity <= 0
  170:         for price, quantity in raw_bids + raw_asks
  171:     ):
  172:         return _closed_projection(
  173:             projection_time=projected_at,
  174:             event_time=event_time,
  175:             last_update_id=snapshot.last_update_id,
  176:             sync_state="INVALID",
  177:             depth_levels=depth_levels,
  178:             age_ms=age_ms,
  179:         )
  180:     if not raw_bids or not raw_asks:
  181:         return _closed_projection(
  182:             projection_time=projected_at,
  183:             event_time=event_time,
  184:             last_update_id=snapshot.last_update_id,
  185:             sync_state="EMPTY",
  186:             depth_levels=depth_levels,
  187:             age_ms=age_ms,
  188:         )
  189: 
  190:     bids = tuple(sorted(raw_bids, key=lambda level: level[0], reverse=True))
  191:     asks = tuple(sorted(raw_asks, key=lambda level: level[0]))
  192:     best_bid = bids[0][0]
  193:     best_ask = asks[0][0]
  194:     if best_bid == best_ask:
  195:         state = "LOCKED"
  196:     elif best_bid > best_ask:
  197:         state = "CROSSED"
  198:     else:
  199:         state = SYNCED
  200:     if state != SYNCED:
  201:         return _closed_projection(
  202:             projection_time=projected_at,
  203:             event_time=event_time,
  204:             last_update_id=snapshot.last_update_id,
  205:             sync_state=state,
  206:             depth_levels=depth_levels,
  207:             age_ms=age_ms,
  208:         )
  209: 
  210:     return BookProjection(
  211:         projection_time=projected_at,
  212:         event_time=event_time,
  213:         last_update_id=snapshot.last_update_id,
  214:         sync_state=SYNCED,
  215:         bids=bids[:depth_levels],
  216:         asks=asks[:depth_levels],
  217:         depth_levels=depth_levels,
  218:         best_bid=best_bid,
  219:         best_ask=best_ask,
  220:         spread=best_ask - best_bid,
  221:         age_ms=age_ms,
  222:     )
````

### `Delta_Engine_Pro4web/webapp/book_projection.py:225`

````text
  225: class LatestBookProjectionPump:
  226:     """Sample the book at a bounded cadence and send only changed projections."""
  227: 
  228:     def __init__(
  229:         self,
  230:         get_book_state: Callable[[], Any],
  231:         send: Callable[[BookProjection], Awaitable[None]],
  232:         *,
  233:         depth_levels: int = 50,
  234:         interval_sec: float = 0.1,
  235:         stale_after_ms: int = 2000,
  236:         monotonic: Callable[[], float] = time.monotonic,
  237:         utcnow: Callable[[], datetime] = _utc_now,
  238:         sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
  239:     ) -> None:
  240:         if interval_sec <= 0:
  241:             raise ValueError("interval_sec must be > 0")
  242:         self._get_book_state = get_book_state
  243:         self._send = send
  244:         self.depth_levels = depth_levels
  245:         self.interval_sec = float(interval_sec)
  246:         self.stale_after_ms = stale_after_ms
  247:         self._monotonic = monotonic
  248:         self._utcnow = utcnow
  249:         self._sleep = sleep
  250:         self._last_fingerprint: tuple | None = None
  251:         self.latest_projection: BookProjection | None = None
  252:         self.samples = 0
  253:         self.sent = 0
  254:         self.synced_sent = 0
  255:         self.fail_closed_sent = 0
  256:         self.unchanged_suppressed = 0
  257:         self.send_failures = 0
  258: 
  259:     @property
  260:     def current_state(self) -> str:
  261:         return (
  262:             self.latest_projection.sync_state
  263:             if self.latest_projection is not None
  264:             else "NO_SNAPSHOT"
  265:         )
  266: 
  267:     async def project_once(self) -> bool:
  268:         projection = build_book_projection(
  269:             self._get_book_state(),
  270:             depth_levels=self.depth_levels,
  271:             stale_after_ms=self.stale_after_ms,
  272:             now_monotonic=self._monotonic(),
  273:             projection_time=self._utcnow(),
  274:         )
  275:         self.samples += 1
  276:         if projection.fingerprint == self._last_fingerprint:
  277:             self.unchanged_suppressed += 1
  278:             return False
  279:         try:
  280:             await self._send(projection)
  281:         except asyncio.CancelledError:
  282:             raise
  283:         except Exception:  # keep LIVE market analysis isolated from UI delivery
  284:             self.send_failures += 1
  285:             logger.exception("BOOK_UPDATE projection send failed")
  286:             return False
  287:         self._last_fingerprint = projection.fingerprint
  288:         self.latest_projection = projection
  289:         self.sent += 1
  290:         if projection.sync_state == SYNCED:
  291:             self.synced_sent += 1
  292:         else:
  293:             self.fail_closed_sent += 1
  294:         return True
  295: 
  296:     async def run(self) -> None:
  297:         while True:
  298:             await self.project_once()
  299:             await self._sleep(self.interval_sec)
````

### `Delta_Engine_Pro4web/webapp/main.py:114`

````text
  114: @contextlib.asynccontextmanager
  115: async def lifespan(app: FastAPI):
  116:     app.state.version = resolve_version()
  117:     config = load_config(_CONFIG_PATH)
  118:     profile = load_profile(_profile_path(config))
  119:     persistent_enabled = os.getenv("PERSISTENT_DEPTH_HISTORY_ENABLED", "false").lower() == "true"
  120:     persistent_writer = PersistentDepthWriter(os.getenv("PERSISTENT_DEPTH_HISTORY_ROOT", "data_05M/depth_history"), config.market.symbol) if persistent_enabled else None
  121:     broker = _build_broker(config, persistent_writer)
````

### `Delta_Engine_Pro4web/webapp/main.py:203`

````text
  203:     market_push_pump = LatestValuePump(
  204:         push_latest_market,
  205:         config.webapp.tick_push_interval_ms / 1000.0,
  206:     )
  207:     tape_batcher = TapeBatcher(
  208:         broker.on_tape_update,
  209:         symbol=config.market.symbol,
  210:         interval_sec=config.webapp.tape_batch_interval_ms / 1000.0,
  211:         max_trades_per_message=config.webapp.tape_max_trades_per_message,
  212:         pending_capacity=config.webapp.tape_pending_capacity,
  213:         batch_time_mode="event" if config.replay.enabled else "wall",
  214:     )
  215:     book_projection_pump = LatestBookProjectionPump(
  216:         lambda: getattr(pipeline, "book_manager", None),
  217:         broker.on_book_update,
  218:         depth_levels=config.webapp.live_dom_depth_levels,
  219:         interval_sec=config.webapp.book_update_interval_ms / 1000.0,
  220:         stale_after_ms=config.webapp.book_stale_after_ms,
  221:     )
````

### `Delta_Engine_Pro4web/webapp/main.py:347`

````text
  347:     if config.replay.enabled:
  348:         market_push_task = None
  349:         book_projection_task = None
  350:         loop = asyncio.get_event_loop()
  351:         # run_in_executor returns a Future, not a coroutine. asyncio.create_task()
  352:         # rejects Futures (TypeError at lifespan startup) — ensure_future accepts both.
  353:         pipeline_task = asyncio.ensure_future(
  354:             loop.run_in_executor(None, pipeline.run, config.replay.data_path)
  355:         )
  356:     else:
  357:         market_push_task = asyncio.create_task(market_push_pump.run())
  358:         book_projection_task = asyncio.create_task(book_projection_pump.run())
  359:         pipeline_task = asyncio.create_task(
  360:             pipeline.run_async(raw_recorder=hook_capture)
  361:         )
````

### `Delta_Engine_Pro4web/webapp/main.py:557`

````text
  557:     try:
  558:         yield
  559:     finally:
  560:         for t in app.state.tasks:
  561:             t.cancel()
  562:         for t in app.state.tasks:
  563:             with contextlib.suppress(asyncio.CancelledError, Exception):
  564:                 await t
  565:         if hook_capture is not None:
  566:             with contextlib.suppress(Exception):
  567:                 await asyncio.to_thread(hook_capture.close)
  568:         if persistent_writer is not None:
  569:             with contextlib.suppress(Exception):
  570:                 await asyncio.to_thread(persistent_writer.close)
````

### `Delta_Engine_Pro4web/webapp/push_broker.py:141`

````text
  141: class PushBroker:
  142:     """WebSocketクライアント管理とPayload配信。asyncio単一ループ（ADR-003）。"""
  143: 
  144:     def __init__(
  145:         self,
  146:         symbol: str,
  147:         depth_levels: int = 15,
  148:         live_dom_depth_levels: int = 50,
  149:         persistent_writer=None,
  150:     ) -> None:
  151:         self.symbol = symbol
  152:         self.persistent_writer = persistent_writer
  153:         self.depth_levels = depth_levels
  154:         self.live_dom_depth_levels = live_dom_depth_levels
  155:         self._clients: set[Any] = set()
  156:         self._lock = asyncio.Lock()
  157:         self._latest_hfm_message: dict | None = None
  158:         self._latest_book_message: dict | None = None
  159:         self.book_stream_id = str(uuid4())
  160:         self.book_updates_broadcast = 0
````

### `Delta_Engine_Pro4web/webapp/push_broker.py:248`

````text
  248:     async def on_book_update(self, projection: BookProjection) -> None:
  249:         """Broadcast one bounded LIVE DOM projection and cache it for reconnect."""
  250:         if projection.sync_state != SYNCED and projection.sync_state not in FAIL_CLOSED_STATES:
  251:             raise ValueError(f"unknown book sync_state: {projection.sync_state}")
  252:         synced = projection.sync_state == SYNCED
  253:         if synced and (
  254:             projection.best_bid is None
  255:             or projection.best_ask is None
  256:             or projection.spread is None
  257:         ):
  258:             raise ValueError("SYNCED BOOK_UPDATE requires best bid, best ask, and spread")
  259:         book_sequence = self.book_updates_broadcast + 1
  260:         bids = projection.bids if synced else ()
  261:         asks = projection.asks if synced else ()
  262:         message = envelope(
  263:             "BOOK_UPDATE",
  264:             projection.projection_time,
  265:             self.symbol,
  266:             {
  267:                 "book_stream_id": self.book_stream_id,
  268:                 "book_sequence": book_sequence,
  269:                 "event_time": (
  270:                     projection.event_time.astimezone(timezone.utc).isoformat()
  271:                     if projection.event_time is not None else None
  272:                 ),
  273:                 "projection_time": projection.projection_time.astimezone(
  274:                     timezone.utc
  275:                 ).isoformat(),
  276:                 "last_update_id": projection.last_update_id,
  277:                 "sync_state": projection.sync_state,
  278:                 "bids": [
  279:                     {"price": d2s(price), "qty": d2s(quantity)}
  280:                     for price, quantity in bids
  281:                 ],
  282:                 "asks": [
  283:                     {"price": d2s(price), "qty": d2s(quantity)}
  284:                     for price, quantity in asks
  285:                 ],
  286:                 "depth_levels": projection.depth_levels,
  287:                 "best_bid": d2s(projection.best_bid) if synced else None,
  288:                 "best_ask": d2s(projection.best_ask) if synced else None,
  289:                 "spread": d2s(projection.spread) if synced else None,
  290:                 "age_ms": projection.age_ms,
  291:             },
  292:         )
  293:         self._latest_book_message = message
  294:         self.book_updates_broadcast = book_sequence
  295:         if self.persistent_writer is not None:
  296:             self.persistent_writer.append(message["payload"])
  297:         await self._broadcast(message)
````

## 逸脱事項

- P1-0-bで指定された「空行追加→`git checkout`復元」は、sandboxが編集適用前に拒否したため、空行追加もcheckoutも発生していない。判定は「不可」とし、エラー全文と無変更証拠を記録した。
- 対象ファイル確認用PowerShellと行番号検索用`rg`で、それぞれ構文誤りが1回発生した。いずれもread-onlyコマンドであり、同一失敗の再実行、タイムアウト、ファイル変更はない。

以上。P1-1は未着手。次の指示待ちで停止。