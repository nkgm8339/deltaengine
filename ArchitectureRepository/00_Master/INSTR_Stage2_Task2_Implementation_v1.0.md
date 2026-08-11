# 指示書: Phase 2-3 Stage 2 Task 2 供給経路+gate 実装
Version: 1.0
発行: Claude(統括) → Codex(実装)
対象: DeltaEngine05M / Heatmap Phase 2-3 Stage 2
前提: 起動モデル承認済(bookチャネル排他 + gate有効化)。HEAD 2fea7ef。アンカー材料検証済。
統括の承認: 保護ファイル main.py / index.html への下記アンカー差分を承認する。他の変更は禁止。

---

## 1. 絶対規律
- 新規1ファイル追加 + 新規テスト1ファイル + main.py の指定5アンカー差分 + index.html の1アンカー差分のみ。
- 保護ファイルは指定アンカー以外を一切変更するな。差分はアンカー文字列ベースのbefore/after。行番号ベース不可。
- float()禁止(grep "float(" 0件)。配信間隔秒は `interval_ms / 1000` で計算しfloat()を書かない。
- 既存の他チャネル(market/trade/candle/analysis)に触れるな。

## 2. 新規ファイル webapp/heatmap_replay_task.py(全文をこの仕様で作成)

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

## 3. main.py アンカー差分(5箇所)

### D1. import追加
アンカーbefore:
```
from webapp.hfm_quote_tailer import hfm_quote_tail_loop
```
after:
```
from webapp.hfm_quote_tailer import hfm_quote_tail_loop
from webapp.heatmap_replay_task import heatmap_replay_loop
```

### D2. env解決追加(broker構築の直前)
アンカーbefore:
```
    broker = _build_broker(config, persistent_writer)
```
after:
```
    heatmap_replay_enabled = os.getenv("HEATMAP_REPLAY_ENABLED", "false").lower() == "true"
    heatmap_replay_dir = Path(os.getenv("DEPTH_HISTORY_ROOT", "data_05M/depth_history_raw")) / f"symbol={config.market.symbol}"
    heatmap_replay_interval_ms = int(os.getenv("HEATMAP_REPLAY_INTERVAL_MS", "100"))
    heatmap_replay_sample_interval_ms = int(os.getenv("HEATMAP_REPLAY_SAMPLE_INTERVAL_MS", "1000"))
    broker = _build_broker(config, persistent_writer)
```

### D3. live分岐で book_projection_pump を排他化
アンカーbefore:
```
        market_push_task = asyncio.create_task(market_push_pump.run())
        book_projection_task = asyncio.create_task(book_projection_pump.run())
```
after:
```
        market_push_task = asyncio.create_task(market_push_pump.run())
        book_projection_task = (
            None
            if heatmap_replay_enabled
            else asyncio.create_task(book_projection_pump.run())
        )
```

### D4. heatmap replay task 生成(tape_task の直後)
アンカーbefore:
```
    tape_task = asyncio.create_task(tape_batcher.run())
```
after:
```
    tape_task = asyncio.create_task(tape_batcher.run())

    heatmap_replay_task = (
        asyncio.create_task(
            heatmap_replay_loop(
                broker.on_book_update,
                recording_dir=heatmap_replay_dir,
                interval_ms=heatmap_replay_interval_ms,
                sample_interval_ms=heatmap_replay_sample_interval_ms,
                depth_levels=config.webapp.live_dom_depth_levels,
                symbol=config.market.symbol,
            )
        )
        if heatmap_replay_enabled
        else None
    )
```

### D5. tasks登録(book_projection_task登録の直後)
アンカーbefore:
```
    if book_projection_task is not None:
        tasks.append(book_projection_task)
    tasks.append(tape_task)
```
after:
```
    if book_projection_task is not None:
        tasks.append(book_projection_task)
    if heatmap_replay_task is not None:
        tasks.append(heatmap_replay_task)
    tasks.append(tape_task)
```

## 4. index.html アンカー差分(1箇所)

### D6. gate有効化(GO-H6)
アンカーbefore:
```
const ORDER_BOOK_HEATMAP_ENABLED = false;
```
after:
```
const ORDER_BOOK_HEATMAP_ENABLED = true;
```

## 5. 新規テスト tests/webapp/test_heatmap_replay_task.py
- iter_book_projections を monkeypatch で projection 列(SimpleNamespace等の疑似projection)に差し替え。
- fake send(collector list)、fake sleep(呼び出し回数/引数を記録、no-op)。
- T1: 全projectionがsendされ、各send後にsleep(delay_sec)が呼ばれる。delay_sec==interval_ms/1000。
- T2: send中の1回がExceptionでも継続し、残りが届く(isolate)。
- T3: interval_ms<=0 で ValueError。
- T4: recording_dir/interval/symbol/depth_levels/sample_interval_ms が iter_book_projections へ正しく渡る(monkeypatchで引数検証)。
- float()を使わない。

## 6. 手順
1. 新規2ファイル作成、main.py D1-D5、index.html D6 を適用。
2. float走査: `grep -n "float(" webapp/heatmap_replay_task.py tests/webapp/test_heatmap_replay_task.py` → 0件。
3. 保護ファイル差分の自己確認(提出):
```
git -C <root> diff -- Delta_Engine_Pro4web/webapp/main.py
git -C <root> diff -- Delta_Engine_Pro4web/webapp/static/index.html
```
main.py差分がD1-D5のみ、index.html差分がD6の1行のみであること。余計な変更があれば停止・報告。
4. 新規テスト: `python -m pytest -q tests/webapp/test_heatmap_replay_task.py`。
5. 全pytest: `python -m pytest -q -p no:cacheprovider`。gate=true化でindex.html前提のUIテストに新規failが出ないか確認。既知failure(test_dom_tape_fusion_ui.py)以外の新規failが出たら、そのテスト名と該当assertを報告し停止(commitへ進むな)。
6. git add はまだしない(統括検証後に別コミット指示)。

## 7. 提出物
- webapp/heatmap_replay_task.py と tests/webapp/test_heatmap_replay_task.py の全文
- 両新規ファイルのSHA-256・byte・LF・CR
- main.py と index.html の `git diff`(全文、アンカー範囲のみであることを示す)
- float走査結果(0件)
- 新規テスト結果、全pytestサマリ・FAILED行
- `git status --porcelain -- Delta_Engine_Pro4web/`, `git rev-parse HEAD`(2fea7ef)

## 8. 禁止事項
- 指定アンカー以外の保護ファイル変更、他チャネルへの接触。
- float()の使用。
- git add / commit(検証後に別指示)。
- gate=trueで新規failが出たままの続行。

以上。提出後、統括が新規2ファイルと保護ファイル差分を独立検証(SHA・float・テスト・diff範囲・新規fail有無)し、合格なら第七コミット(Task 2、保護ファイル含む)指示書を発行する。これでStage 2の動的ヒートマップ供給が繋がる。
