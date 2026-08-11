# Stage2 Task2 v3.3 Seventh Commit Verification Package

実施日: 2026-08-01  
基準HEAD: `2fea7efebbe64b86b3a62bf1645ffcf3d3946dd4`  
commit: 未実施、staging: 空

## 1-1 新規ファイル全文と計測

### `Delta_Engine_Pro4web/webapp/heatmap_replay_task.py`

```python
"""Recording-driven book supply for the browser heatmap (depth-history replay)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from src.heatmap.reconstruct import DepthHistoryReader
from webapp.book_projection import BookProjection
from webapp.heatmap_frame_source import iter_book_projections

logger = logging.getLogger(__name__)


def ensure_replay_source(recording_dir: Path) -> None:
    """Fail fast when the recording root is missing or has no completed segments."""
    reader = DepthHistoryReader(recording_dir)
    segments = reader.segments()
    if not segments:
        raise RuntimeError(
            f"heatmap replay source has no completed segments: {recording_dir}"
        )


async def heatmap_replay_loop(
    send: Callable[[BookProjection], Awaitable[None]],
    *,
    recording_dir: Path,
    interval_ms: int,
    sample_interval_ms: int,
    depth_levels: int = 50,
    symbol: str = "BTCUSDT",
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Replay one depth-history recording as BOOK_UPDATE projections, once."""
    if interval_ms <= 0:
        raise ValueError("interval_ms must be > 0")
    delay_sec = interval_ms / 1000
    sent = 0
    for projection in iter_book_projections(
        recording_dir,
        interval_ms=sample_interval_ms,
        depth_levels=depth_levels,
        symbol=symbol,
    ):
        try:
            await send(projection)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("heatmap replay BOOK_UPDATE send failed")
        sent += 1
        await sleep(delay_sec)
    if sent == 0:
        raise RuntimeError(
            f"heatmap replay produced zero projections from {recording_dir}"
        )
```

計測: SHA-256 `BB53DEBCBC4CB857ACC95A2BAAADB50FA8660F91D5B37A98A17CA9237D1FAE37`; byte `1853`; LF `59`; CR `0`。

### `Delta_Engine_Pro4web/tests/webapp/test_heatmap_replay_task.py`

```python
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from webapp import heatmap_replay_task as replay


MAIN = Path(__file__).resolve().parents[2] / "webapp" / "main.py"


def test_replay_sends_each_projection_and_sleeps_after_each(monkeypatch) -> None:
    projections = [SimpleNamespace(index=1), SimpleNamespace(index=2)]
    sleeps: list[float] = []
    sent: list[object] = []

    monkeypatch.setattr(replay, "iter_book_projections", lambda *args, **kwargs: iter(projections))

    async def run() -> None:
        async def send(projection) -> None:
            sent.append(projection)

        async def sleep(delay: float) -> None:
            sleeps.append(delay)

        await replay.heatmap_replay_loop(
            send,
            recording_dir=Path("recording"),
            interval_ms=125,
            sample_interval_ms=1000,
            sleep=sleep,
        )

    asyncio.run(run())
    assert sent == projections
    assert sleeps == [0.125, 0.125]


def test_replay_isolates_send_exception_and_continues(monkeypatch) -> None:
    projections = [SimpleNamespace(index=1), SimpleNamespace(index=2)]
    sent: list[object] = []
    sleeps: list[float] = []
    monkeypatch.setattr(replay, "iter_book_projections", lambda *args, **kwargs: iter(projections))

    async def run() -> None:
        async def send(projection) -> None:
            sent.append(projection)
            if projection.index == 1:
                raise RuntimeError("send failed")

        async def sleep(delay: float) -> None:
            sleeps.append(delay)

        await replay.heatmap_replay_loop(
            send,
            recording_dir=Path("recording"),
            interval_ms=100,
            sample_interval_ms=1000,
            sleep=sleep,
        )

    asyncio.run(run())
    assert sent == projections
    assert sleeps == [0.1, 0.1]


def test_replay_reraises_cancelled_error(monkeypatch) -> None:
    monkeypatch.setattr(
        replay,
        "iter_book_projections",
        lambda *args, **kwargs: iter([SimpleNamespace(index=1)]),
    )

    async def run() -> None:
        async def send(projection) -> None:
            raise asyncio.CancelledError

        async def sleep(delay: float) -> None:
            raise AssertionError("sleep must not run after cancellation")

        with pytest.raises(asyncio.CancelledError):
            await replay.heatmap_replay_loop(
                send,
                recording_dir=Path("recording"),
                interval_ms=100,
                sample_interval_ms=1000,
                sleep=sleep,
            )

    asyncio.run(run())


def test_replay_rejects_non_positive_interval() -> None:
    async def run() -> None:
        with pytest.raises(ValueError, match="interval_ms must be > 0"):
            await replay.heatmap_replay_loop(
                lambda projection: None,
                recording_dir=Path("recording"),
                interval_ms=0,
                sample_interval_ms=1000,
            )

    asyncio.run(run())


def test_replay_passes_source_arguments(monkeypatch) -> None:
    calls: list[tuple[tuple, dict]] = []
    projection = SimpleNamespace(index=1)

    def source(*args, **kwargs):
        calls.append((args, kwargs))
        return iter([projection])

    monkeypatch.setattr(replay, "iter_book_projections", source)

    async def run() -> None:
        async def send(value) -> None:
            assert value is projection

        async def sleep(delay: float) -> None:
            pass

        recording_dir = Path("recording")
        await replay.heatmap_replay_loop(
            send,
            recording_dir=recording_dir,
            interval_ms=100,
            sample_interval_ms=250,
            depth_levels=7,
            symbol="ETHUSDT",
            sleep=sleep,
        )

    asyncio.run(run())
    assert calls == [
        (
            (Path("recording"),),
            {
                "interval_ms": 250,
                "depth_levels": 7,
                "symbol": "ETHUSDT",
            },
        )
    ]


def test_replay_raises_when_no_projection(monkeypatch) -> None:
    monkeypatch.setattr(replay, "iter_book_projections", lambda *args, **kwargs: iter(()))

    async def run() -> None:
        with pytest.raises(RuntimeError, match="produced zero projections"):
            await replay.heatmap_replay_loop(
                lambda projection: None,
                recording_dir=Path("empty"),
                interval_ms=100,
                sample_interval_ms=1000,
            )

    asyncio.run(run())


def test_ensure_replay_source_uses_completed_segments(monkeypatch, tmp_path) -> None:
    class Reader:
        def __init__(self, recording_dir) -> None:
            assert recording_dir == tmp_path

        def segments(self):
            return [object()]

    monkeypatch.setattr(replay, "DepthHistoryReader", Reader)
    replay.ensure_replay_source(tmp_path)


def test_ensure_replay_source_rejects_empty_segments(monkeypatch, tmp_path) -> None:
    class Reader:
        def __init__(self, recording_dir) -> None:
            pass

        def segments(self):
            return []

    monkeypatch.setattr(replay, "DepthHistoryReader", Reader)
    with pytest.raises(RuntimeError, match="no completed segments"):
        replay.ensure_replay_source(tmp_path)


def test_live_supply_is_exclusive_for_both_heatmap_flag_values() -> None:
    source = MAIN.read_text(encoding="utf-8")
    assert "if heatmap_replay_enabled" in source
    assert "else asyncio.create_task(book_projection_pump.run())" in source
    assert "if config.replay.enabled and not heatmap_replay_enabled" not in source


def test_pipeline_replay_is_documented_as_non_heatmap_mode() -> None:
    source = MAIN.read_text(encoding="utf-8")
    assert 'if config.replay.enabled:' in source
    assert "book_projection_task = None" in source
```

計測: SHA-256 `FDE3A6A0BE9A9881A52218DE3FE6188A68AD7C1762D32494E100A549DC1130E4`; byte `5914`; LF `198`; CR `0`。

## 1-2 保護ファイル基準差分

### main.py

```diff
diff --git a/Delta_Engine_Pro4web/webapp/main.py b/Delta_Engine_Pro4web/webapp/main.py
index e3ef1c1..2e4ca22 100644
--- a/Delta_Engine_Pro4web/webapp/main.py
+++ b/Delta_Engine_Pro4web/webapp/main.py
@@ -53,6 +53,7 @@ from webapp.book_projection import (
 from webapp.tape import TapeBatcher
 from webapp.oi_poller import oi_polling_loop
 from webapp.hfm_quote_tailer import hfm_quote_tail_loop
+from webapp.heatmap_replay_task import ensure_replay_source, heatmap_replay_loop
 from webapp.history import (
@@ -134,6 +135,6 @@ async def lifespan(app: FastAPI):
         if depth_history_enabled
         else None
     )
+    heatmap_replay_enabled = os.getenv("HEATMAP_REPLAY_ENABLED", "false").lower() == "true"
+    heatmap_replay_dir = Path(os.getenv("DEPTH_HISTORY_ROOT", "data_05M/depth_history_raw")) / f"symbol={config.market.symbol}"
+    heatmap_replay_interval_ms = int(os.getenv("HEATMAP_REPLAY_INTERVAL_MS", "100"))
+    heatmap_replay_sample_interval_ms = int(os.getenv("HEATMAP_REPLAY_SAMPLE_INTERVAL_MS", "1000"))
+    if heatmap_replay_enabled:
+        ensure_replay_source(heatmap_replay_dir)
     broker = _build_broker(config, persistent_writer)
@@ -379,7 +386,11 @@ async def lifespan(app: FastAPI):
         )
     else:
         market_push_task = asyncio.create_task(market_push_pump.run())
-        book_projection_task = asyncio.create_task(book_projection_pump.run())
+        book_projection_task = (
+            None
+            if heatmap_replay_enabled
+            else asyncio.create_task(book_projection_pump.run())
+        )
@@ -387,6 +398,36 @@ async def lifespan(app: FastAPI):
         )
     tape_task = asyncio.create_task(tape_batcher.run())
+
+    app.state.heatmap_replay_failed = False
+    heatmap_replay_task = (
+        asyncio.create_task(
+            heatmap_replay_loop(
+                broker.on_book_update,
+                recording_dir=heatmap_replay_dir,
+                interval_ms=heatmap_replay_interval_ms,
+                sample_interval_ms=heatmap_replay_sample_interval_ms,
+                depth_levels=config.webapp.live_dom_depth_levels,
+                symbol=config.market.symbol,
+            )
+        )
+        if heatmap_replay_enabled
+        else None
+    )
+
+    def _mark_replay_failure(completed) -> None:
+        if completed.cancelled():
+            return
+        error = completed.exception()
+        if error is not None:
+            logger.error(
+                "heatmap replay task failed",
+                exc_info=(type(error), error, error.__traceback__),
+            )
+            app.state.heatmap_replay_failed = True
+
+    if heatmap_replay_task is not None:
+        heatmap_replay_task.add_done_callback(_mark_replay_failure)
@@ -560,6 +601,13 @@ async def lifespan(app: FastAPI):
                 }
                 if tape_problem and health_payload["state"] == "GREEN":
                     health_payload["state"] = "YELLOW"
+                if getattr(app.state, "heatmap_replay_failed", False):
+                    health_payload["state"] = "RED"
+                    health_payload["checks"]["heatmap_replay"] = {
+                        "level": "RED",
+                        "value": "1",
+                        "detail": "heatmap replay task failed",
+                    }
                 app.state.health_report = health_payload
@@ -571,6 +619,8 @@ async def lifespan(app: FastAPI):
         tasks.append(market_push_task)
     if book_projection_task is not None:
         tasks.append(book_projection_task)
+    if heatmap_replay_task is not None:
+        tasks.append(heatmap_replay_task)
     tasks.append(tape_task)
```

### index.html

```diff
diff --git a/Delta_Engine_Pro4web/webapp/static/index.html b/Delta_Engine_Pro4web/webapp/static/index.html
index ebb25b0..2c31dd7 100644
--- a/Delta_Engine_Pro4web/webapp/static/index.html
+++ b/Delta_Engine_Pro4web/webapp/static/index.html
@@ -966,7 +966,7 @@ const UI_PAYLOAD_VERSION = 1;
 // Phase 5 presentation rollback boundary. Backend collection/storage stays active.
 const PHASE5_FUSION_ENABLED = true;
 // GO-H3 presentation gate. Keep false until GO-H6 operational activation.
-const ORDER_BOOK_HEATMAP_ENABLED = false;
+const ORDER_BOOK_HEATMAP_ENABLED = true;
```

### UI test

```diff
diff --git a/Delta_Engine_Pro4web/tests/webapp/test_orderbook_heatmap_ui.py b/Delta_Engine_Pro4web/tests/webapp/test_orderbook_heatmap_ui.py
index cc7a7bc..37a9129 100644
--- a/Delta_Engine_Pro4web/tests/webapp/test_orderbook_heatmap_ui.py
+++ b/Delta_Engine_Pro4web/tests/webapp/test_orderbook_heatmap_ui.py
@@ -6,9 +6,9 @@ INDEX = ROOT / "webapp" / "static" / "index.html"
 HEATMAP = ROOT / "webapp" / "static" / "orderbook_heatmap.js"
 
 
-def test_heatmap_is_fail_closed_until_operational_activation():
+def test_heatmap_gate_is_enabled_for_operation():
     source = INDEX.read_text(encoding="utf-8")
-    assert "const ORDER_BOOK_HEATMAP_ENABLED = false;" in source
+    assert "const ORDER_BOOK_HEATMAP_ENABLED = true;" in source
```

## 1-3 float禁止・衛生

指定の`Select-String ... float\(` 2件およびmain.py diffへの同検索はすべて出力なし（0件）。`git diff --check`も出力なし（空）。

## 1-4 staging/status

`git diff --cached --name-only` の出力は空。

`git status --porcelain -- Delta_Engine_Pro4web/`:

```text
 M Delta_Engine_Pro4web/tests/webapp/test_orderbook_heatmap_ui.py
 M Delta_Engine_Pro4web/webapp/main.py
 M Delta_Engine_Pro4web/webapp/static/index.html
?? Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/
?? Delta_Engine_Pro4web/tests/webapp/test_heatmap_replay_task.py
?? Delta_Engine_Pro4web/webapp/heatmap_replay_task.py
```

## 1-5 pytest全文

対象テスト（`test_heatmap_replay_task.py` / `test_orderbook_heatmap_ui.py` / `test_api.py`）:

```text
33 passed in 3.29s
```

指定全体pytest全文:

```text
........................................................................ [  9%]
........................................................................ [ 18%]
........................................................................ [ 27%]
........................................................................ [ 36%]
........................................................................ [ 45%]
......s................................................................. [ 63%]
........................................................................ [ 72%]
........................................................................ [ 81%]
............................F........................................... [ 90%]
........................................................................ [100%]
================================== FAILURES ===================================
_ test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation _

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
>       assert 'body.phase5-fusion #right>#left{display:none!important}' in html
E       assert 'body.phase5-fusion #right>#left{display:none!important}' in '<!DOCTYPE html>...'

tests\\webapp\\test_dom_tape_fusion_ui.py:30: AssertionError
=========================== short test summary info ============================
FAILED tests/webapp/test_dom_tape_fusion_ui.py::test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation
1 failed, 790 passed, 1 skipped in 132.75s (0:02:12)
```

新規failureはなく、failureは既知の1件のみ。

## 1-6 保護境界

指定コマンド:

```powershell
git diff 2fea7efebbe64b86b3a62bf1645ffcf3d3946dd4 -- Delta_Engine_Pro4web/webapp/heatmap_frame_source.py Delta_Engine_Pro4web/tests/webapp/test_heatmap_frame_source.py Delta_Engine_Pro4web/src/heatmap/reconstruct.py Delta_Engine_Pro4web/docker-compose.yml Delta_Engine_Pro4web/tests/webapp/test_book_update.py
```

出力は空。

## 1-7 fail-fast撤去とD1-D7残存

`Select-String -Path Delta_Engine_Pro4web\\webapp\\main.py -Pattern 'config.replay.enabled and not heatmap_replay_enabled'` は出力なし（0件）。

実物diff・全文で確認できる残存要素:

- D1: `main.py` importに`ensure_replay_source, heatmap_replay_loop`
- D2: `HEATMAP_REPLAY_ENABLED`、`DEPTH_HISTORY_ROOT`、interval/sample intervalの4行と有効時precheck
- D3: live分岐の`None if heatmap_replay_enabled else asyncio.create_task(book_projection_pump.run())`
- D4: `heatmap_replay_task`生成と`heatmap_replay_loop(...)`
- D5: `tasks.append(heatmap_replay_task)`
- D6: `index.html`の`ORDER_BOOK_HEATMAP_ENABLED = true`
- D7a-1: `app.state.heatmap_replay_failed = False`がreplay task生成前
- D7a-2: `_mark_replay_failure`、cancel判定、exception取得、logger、flag設定、done callback登録
- D7b: health payloadへのREDと`checks["heatmap_replay"]`インラインdict
- 0 projection: `heatmap_replay_task.py`の`if sent == 0: raise RuntimeError(...)`

## 1-8 本番live供給網羅テスト

実物に存在する関数とassert:

```text
tests/webapp/test_heatmap_replay_task.py:181
def test_live_supply_is_exclusive_for_both_heatmap_flag_values():
tests/webapp/test_heatmap_replay_task.py:184
assert "if heatmap_replay_enabled" in source
tests/webapp/test_heatmap_replay_task.py:185
assert "else asyncio.create_task(book_projection_pump.run())" in source
tests/webapp/test_heatmap_replay_task.py:186
assert "if config.replay.enabled and not heatmap_replay_enabled" not in source
```

このテストは本番live排他のソース構造（flag=falseでlive pump、flag=trueでlive pumpなし）とfail-fast撤去をassertする。

pipeline replayをHeatmap非供給モードとして固定するテストも存在する:

```text
tests/webapp/test_heatmap_replay_task.py:189
def test_pipeline_replay_is_documented_as_non_heatmap_mode():
tests/webapp/test_heatmap_replay_task.py:191
assert 'if config.replay.enabled:' in source
tests/webapp/test_heatmap_replay_task.py:192
assert "book_projection_task = None" in source
```

なお、実際のlifespanをflag=false/trueの両方で起動してtaskオブジェクト数をassertするテストは実物にない。上記はmain.pyソース構造テストである。

