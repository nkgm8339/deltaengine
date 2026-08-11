# Phase 2-3 Stage 2 Task 2 供給経路＋gate 実装報告

- 指示書: Phase 2-3 Stage 2 Task 2 供給経路+gate 実装 Version 1.0
- 実施日: 2026-08-01
- 実施時HEAD: `2fea7efebbe64b86b3a62bf1645ffcf3d3946dd4`
- git add / commit: 未実施
- 実装後状態: 全pytestでgate旧前提の新規failure 1件を検出したため、指示どおり追加修正・commitを停止

## 1. 実施対象

新規:

1. `Delta_Engine_Pro4web/webapp/heatmap_replay_task.py`
2. `Delta_Engine_Pro4web/tests/webapp/test_heatmap_replay_task.py`

保護ファイル承認アンカー差分:

1. `Delta_Engine_Pro4web/webapp/main.py` D1-D5
2. `Delta_Engine_Pro4web/webapp/static/index.html` D6

既存の他チャネルには触れていない。

## 2. webapp/heatmap_replay_task.py 全文

```python
"""Recording-driven book supply for the browser heatmap (depth-history replay)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from webapp.book_projection import BookProjection
from webapp.heatmap_frame_source import iter_book_projections

logger = logging.getLogger(__name__)


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
        await sleep(delay_sec)
```

## 3. tests/webapp/test_heatmap_replay_task.py 全文

```python
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from webapp import heatmap_replay_task


def test_sends_every_projection_then_sleeps_at_configured_interval(
    monkeypatch,
) -> None:
    projections = [
        SimpleNamespace(last_update_id=1),
        SimpleNamespace(last_update_id=2),
        SimpleNamespace(last_update_id=3),
    ]
    sent = []
    delays = []

    def fake_iter_book_projections(*_args, **_kwargs):
        return iter(projections)

    async def fake_send(projection) -> None:
        sent.append(projection)

    async def fake_sleep(delay) -> None:
        delays.append(delay)

    monkeypatch.setattr(
        heatmap_replay_task,
        "iter_book_projections",
        fake_iter_book_projections,
    )

    asyncio.run(
        heatmap_replay_task.heatmap_replay_loop(
            fake_send,
            recording_dir=Path("recording"),
            interval_ms=250,
            sample_interval_ms=1000,
            sleep=fake_sleep,
        )
    )

    assert sent == projections
    assert delays == [0.25, 0.25, 0.25]


def test_send_exception_is_isolated_and_remaining_projections_continue(
    monkeypatch,
) -> None:
    projections = [
        SimpleNamespace(last_update_id=1),
        SimpleNamespace(last_update_id=2),
        SimpleNamespace(last_update_id=3),
    ]
    attempted = []
    sent = []
    delays = []

    def fake_iter_book_projections(*_args, **_kwargs):
        return iter(projections)

    async def fake_send(projection) -> None:
        attempted.append(projection)
        if projection is projections[1]:
            raise RuntimeError("isolated send failure")
        sent.append(projection)

    async def fake_sleep(delay) -> None:
        delays.append(delay)

    monkeypatch.setattr(
        heatmap_replay_task,
        "iter_book_projections",
        fake_iter_book_projections,
    )

    asyncio.run(
        heatmap_replay_task.heatmap_replay_loop(
            fake_send,
            recording_dir=Path("recording"),
            interval_ms=100,
            sample_interval_ms=1000,
            sleep=fake_sleep,
        )
    )

    assert attempted == projections
    assert sent == [projections[0], projections[2]]
    assert delays == [0.1, 0.1, 0.1]


def test_non_positive_interval_ms_raises_value_error() -> None:
    async def fake_send(_projection) -> None:
        raise AssertionError("send must not be called")

    for interval_ms in (0, -1):
        with pytest.raises(ValueError, match="interval_ms must be > 0"):
            asyncio.run(
                heatmap_replay_task.heatmap_replay_loop(
                    fake_send,
                    recording_dir=Path("recording"),
                    interval_ms=interval_ms,
                    sample_interval_ms=1000,
                )
            )


def test_iter_book_projections_receives_all_source_arguments(monkeypatch) -> None:
    recording_dir = Path("depth-history")
    calls = []

    def fake_iter_book_projections(
        supplied_recording_dir,
        *,
        interval_ms,
        depth_levels,
        symbol,
    ):
        calls.append(
            {
                "recording_dir": supplied_recording_dir,
                "interval_ms": interval_ms,
                "depth_levels": depth_levels,
                "symbol": symbol,
            }
        )
        return iter(())

    async def fake_send(_projection) -> None:
        raise AssertionError("send must not be called")

    async def fake_sleep(_delay) -> None:
        raise AssertionError("sleep must not be called")

    monkeypatch.setattr(
        heatmap_replay_task,
        "iter_book_projections",
        fake_iter_book_projections,
    )

    asyncio.run(
        heatmap_replay_task.heatmap_replay_loop(
            fake_send,
            recording_dir=recording_dir,
            interval_ms=125,
            sample_interval_ms=750,
            depth_levels=17,
            symbol="ETHUSDT",
            sleep=fake_sleep,
        )
    )

    assert calls == [
        {
            "recording_dir": recording_dir,
            "interval_ms": 750,
            "depth_levels": 17,
            "symbol": "ETHUSDT",
        }
    ]
```

## 4. 新規ファイルSHA-256・byte・LF・CR

| ファイル | SHA-256 | byte | LF | CR |
|---|---|---:|---:|---:|
| `Delta_Engine_Pro4web/webapp/heatmap_replay_task.py` | `4ED34226A17F081BCAAB3B0302FF5FED49FE691E7CABB5737C907B4CCCA188B3` | 1,273 | 42 | 0 |
| `Delta_Engine_Pro4web/tests/webapp/test_heatmap_replay_task.py` | `2CD4933EFDF82A6A7F992C222BDBEA80112492E10ECF3AAD988CA730EEB3AF01` | 4,219 | 163 | 0 |

## 5. main.py git diff全文

```diff
diff --git a/Delta_Engine_Pro4web/webapp/main.py b/Delta_Engine_Pro4web/webapp/main.py
index e3ef1c1..fab3e7d 100644
--- a/Delta_Engine_Pro4web/webapp/main.py
+++ b/Delta_Engine_Pro4web/webapp/main.py
@@ -53,6 +53,7 @@ from webapp.book_projection import (
 from webapp.tape import TapeBatcher
 from webapp.oi_poller import oi_polling_loop
 from webapp.hfm_quote_tailer import hfm_quote_tail_loop
+from webapp.heatmap_replay_task import heatmap_replay_loop
 from webapp.history import (
     query_combined_context_events,
     query_candles,
@@ -134,6 +135,10 @@ async def lifespan(app: FastAPI):
         if depth_history_enabled
         else None
     )
+    heatmap_replay_enabled = os.getenv("HEATMAP_REPLAY_ENABLED", "false").lower() == "true"
+    heatmap_replay_dir = Path(os.getenv("DEPTH_HISTORY_ROOT", "data_05M/depth_history_raw")) / f"symbol={config.market.symbol}"
+    heatmap_replay_interval_ms = int(os.getenv("HEATMAP_REPLAY_INTERVAL_MS", "100"))
+    heatmap_replay_sample_interval_ms = int(os.getenv("HEATMAP_REPLAY_SAMPLE_INTERVAL_MS", "1000"))
     broker = _build_broker(config, persistent_writer)
     context_observer = CombinedContextObserver(config.market.symbol)
     shadow_recorder = ShadowSignalRecorder(Path("data_05M/manual/flow_response_shadow.jsonl"))
@@ -379,7 +384,11 @@ async def lifespan(app: FastAPI):
         )
     else:
         market_push_task = asyncio.create_task(market_push_pump.run())
-        book_projection_task = asyncio.create_task(book_projection_pump.run())
+        book_projection_task = (
+            None
+            if heatmap_replay_enabled
+            else asyncio.create_task(book_projection_pump.run())
+        )
         _raw_taps = [t for t in (hook_capture, depth_history_recorder) if t is not None]
         _raw_tap = _raw_taps[0] if len(_raw_taps) == 1 else (RecorderTee(_raw_taps) if _raw_taps else None)
         pipeline_task = asyncio.create_task(
@@ -387,6 +396,21 @@ async def lifespan(app: FastAPI):
         )
     tape_task = asyncio.create_task(tape_batcher.run())
 
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
     pending_oi_samples: list[dict] = []
 
     def store_oi_sample(sample: dict) -> None:
@@ -571,6 +595,8 @@ async def lifespan(app: FastAPI):
         tasks.append(market_push_task)
     if book_projection_task is not None:
         tasks.append(book_projection_task)
+    if heatmap_replay_task is not None:
+        tasks.append(heatmap_replay_task)
     tasks.append(tape_task)
     if oi_task is not None:
         tasks.append(oi_task)
```

差分はD1-D5の5 hunkのみ。`git diff --numstat`は`27 1`。

## 6. index.html git diff全文

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
 // Accepted Time & Sales trade -> passive LIVE DOM half-cell pulse.
 const DOM_TRADE_PULSE_ENABLED = true;
 const DOM_TRADE_PULSE_DURATION_MS = 400;
```

差分はD6の1行のみ。`git diff --numstat`は`1 1`。

## 7. float走査

対象:

```text
webapp/heatmap_replay_task.py
tests/webapp/test_heatmap_replay_task.py
```

結果:

```text
FLOAT_HIT_COUNT=0
```

`git diff --check`はPASS。保護ファイルについてLF→CRLFの将来変換warningのみ。

## 8. 新規テスト

実行コマンド:

```powershell
python -m pytest -q tests/webapp/test_heatmap_replay_task.py
```

結果:

```text
....                                                                     [100%]
4 passed in 0.13s
```

## 9. 全pytest

実行コマンド:

```powershell
python -m pytest -q -p no:cacheprovider
```

FAILED行とサマリ:

```text
FAILED tests/webapp/test_dom_tape_fusion_ui.py::test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation
FAILED tests/webapp/test_orderbook_heatmap_ui.py::test_heatmap_is_fail_closed_until_operational_activation
2 failed, 783 passed, 1 skipped in 138.35s (0:02:18)
```

既知failure:

```text
tests/webapp/test_dom_tape_fusion_ui.py:30
assert 'body.phase5-fusion #right>#left{display:none!important}' in html
```

新規failure:

```text
tests/webapp/test_orderbook_heatmap_ui.py:11
assert "const ORDER_BOOK_HEATMAP_ENABLED = false;" in source
```

承認済みD6で`ORDER_BOOK_HEATMAP_ENABLED = true`へ変更したため、falseを要求する上記assertがfailureとなった。指示に従い、当該testを変更せず追加修正・commitを停止した。

## 10. Git証跡

### git rev-parse HEAD

```text
2fea7efebbe64b86b3a62bf1645ffcf3d3946dd4
```

### git status --porcelain -- Delta_Engine_Pro4web/

```text
 M Delta_Engine_Pro4web/webapp/main.py
 M Delta_Engine_Pro4web/webapp/static/index.html
?? Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/
?? Delta_Engine_Pro4web/tests/webapp/test_heatmap_replay_task.py
?? Delta_Engine_Pro4web/webapp/heatmap_replay_task.py
```

### git diff --cached --name-only

```text
```

stagingは空。

## 11. 停止境界

- 新規test 4件はPASS。
- 全pytestで既知failure 1件とgate旧前提の新規failure 1件を確認。
- 新規failure検出後、source/testの追加変更を行っていない。
- git add / commitは行っていない。
- 統括による新規failureの扱いに関する次指示を待つ。
