# Phase 2-3 Stage 2 Task 1 frame_source 実装報告

- 指示書: Phase 2-3 Stage 2 Task 1 frame_source 実装 Version 1.0
- 実施日: 2026-07-31
- 実施時HEAD: `bf9512635d7a6f4d67a14d67d128fc528f6b6707`
- 状態: 完了
- git add / commit: 未実施
- Task 2: 未着手

## 1. 実施内容

次の新規2ソースファイルを追加した。既存trackedファイルは変更していない。

1. `Delta_Engine_Pro4web/webapp/heatmap_frame_source.py`
2. `Delta_Engine_Pro4web/tests/webapp/test_heatmap_frame_source.py`

実装は、`DepthHistoryReader` / `DepthReconstructor.sample_states` が返す `OrderBookSnapshot` を `SnapshotBookStateAdapter` で包み、既存 `build_book_projection` を通して `BookProjection` 列を生成する。stream ID、sequence、WebSocket送信、Canvas gate変更は含めていない。

## 2. 検証結果

### 2.1 float走査

```text
FLOAT_HIT_COUNT=0
```

対象:

```text
webapp/heatmap_frame_source.py
tests/webapp/test_heatmap_frame_source.py
```

### 2.2 新規テスト単体

実行コマンド:

```text
python -m pytest -q tests/webapp/test_heatmap_frame_source.py
```

結果:

```text
.......                                                                  [100%]
7 passed in 1.21s
```

### 2.3 全pytest

実行コマンド:

```text
python -m pytest -q -p no:cacheprovider
```

結果:

```text
1 failed, 780 passed, 1 skipped in 134.39s (0:02:14)
```

FAILED行:

```text
FAILED tests/webapp/test_dom_tape_fusion_ui.py::test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation
```

failureは指示書記載の既知failure 1件で、新規7テストの追加によりpassed数は773から780になった。既知failure以外の新規failureは0件だった。

## 3. 新規ファイル識別値

| ファイル | SHA-256 | byte | LF | CR |
|---|---|---:|---:|---:|
| `Delta_Engine_Pro4web/webapp/heatmap_frame_source.py` | `15C8DAC80B0AF5DD0DFB497325CA2B236D7892C5D767CECA9DB15B05633E8B7F` | 2067 | 66 | 0 |
| `Delta_Engine_Pro4web/tests/webapp/test_heatmap_frame_source.py` | `4BCCD018D0E5D3E48BEEEED575068887E00950D94FE26AF5E49A53D6706F1450` | 5606 | 184 | 0 |

## 4. Git証跡

### 4.1 HEAD

```text
bf9512635d7a6f4d67a14d67d128fc528f6b6707
```

### 4.2 `git status --porcelain -- Delta_Engine_Pro4web/`

```text
?? Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/
?? Delta_Engine_Pro4web/tests/webapp/test_heatmap_frame_source.py
?? Delta_Engine_Pro4web/webapp/heatmap_frame_source.py
```

`phase0c_storage_sizing_20260728/` は本タスク開始時から存在した未追跡ディレクトリ。新規2ファイルは未追跡・未stageである。

### 4.3 tracked差分とstaging

```text
CORE_TRACKED_DIFF_COUNT=0
CACHED_PATH_COUNT=0
```

## 5. `webapp/heatmap_frame_source.py` 全文

```python
"""Recording-backed source of book projections for the browser heatmap."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.heatmap.reconstruct import DepthHistoryReader, DepthReconstructor
from src.orderflow.orderbook import OrderBookSnapshot
from webapp.book_projection import BookProjection, build_book_projection


class SnapshotBookStateAdapter:
    """Expose one reconstructed snapshot through the projection read contract."""

    def __init__(self, snapshot: OrderBookSnapshot) -> None:
        self._snapshot = snapshot
        self.gaps_detected: int = 0

    @property
    def is_synchronized(self) -> bool:
        return True

    @property
    def last_event_time(self) -> datetime | None:
        return self._snapshot.event_time

    def age_ms(self, now_monotonic: float | None = None) -> int:
        return 0

    def snapshot(self) -> OrderBookSnapshot:
        return self._snapshot


def _epoch_ms_to_utc(event_time_ms: int) -> datetime:
    seconds, millis = divmod(event_time_ms, 1000)
    return datetime.fromtimestamp(seconds, tz=timezone.utc) + timedelta(
        milliseconds=millis
    )


def iter_book_projections(
    recording_dir: Path,
    *,
    interval_ms: int,
    depth_levels: int = 50,
    symbol: str = "BTCUSDT",
) -> Iterator[BookProjection]:
    """Yield projections sampled from a validated depth-history recording."""

    if not recording_dir.is_dir():
        raise FileNotFoundError(recording_dir)

    reader = DepthHistoryReader(recording_dir)
    reconstructor = DepthReconstructor(symbol=symbol, max_attempts=1)
    for event_time_ms, snapshot in reconstructor.sample_states(
        reader.iter_records(), interval_ms=interval_ms
    ):
        adapter = SnapshotBookStateAdapter(snapshot)
        projection_time = _epoch_ms_to_utc(event_time_ms)
        yield build_book_projection(
            adapter,
            depth_levels=depth_levels,
            projection_time=projection_time,
        )
```

## 6. `tests/webapp/test_heatmap_frame_source.py` 全文

```python
from datetime import datetime, timezone
from decimal import Decimal

from src.orderflow.orderbook import OrderBookSnapshot
from webapp import heatmap_frame_source as frame_source
from webapp.book_projection import SYNCED, build_book_projection
from webapp.heatmap_frame_source import SnapshotBookStateAdapter


EVENT_TIME = datetime(2026, 7, 31, 0, 0, tzinfo=timezone.utc)


def _snapshot(
    *,
    bids: dict[Decimal, Decimal],
    asks: dict[Decimal, Decimal],
    event_time: datetime | None = EVENT_TIME,
    last_update_id: int = 100,
) -> OrderBookSnapshot:
    return OrderBookSnapshot(
        symbol="BTCUSDT",
        last_update_id=last_update_id,
        bids=bids,
        asks=asks,
        event_time=event_time,
    )


def test_healthy_snapshot_builds_synced_sorted_depth_limited_projection() -> None:
    snapshot = _snapshot(
        bids={
            Decimal("99"): Decimal("2"),
            Decimal("100"): Decimal("1"),
            Decimal("98"): Decimal("3"),
        },
        asks={
            Decimal("102"): Decimal("5"),
            Decimal("101"): Decimal("4"),
            Decimal("103"): Decimal("6"),
        },
    )

    projection = build_book_projection(
        SnapshotBookStateAdapter(snapshot),
        depth_levels=2,
        projection_time=EVENT_TIME,
    )

    assert projection.sync_state == SYNCED
    assert projection.bids == (
        (Decimal("100"), Decimal("1")),
        (Decimal("99"), Decimal("2")),
    )
    assert projection.asks == (
        (Decimal("101"), Decimal("4")),
        (Decimal("102"), Decimal("5")),
    )
    assert projection.best_bid == Decimal("100")
    assert projection.best_ask == Decimal("101")
    assert projection.spread == Decimal("1")
    assert projection.depth_levels == 2


def test_crossed_snapshot_builds_fail_closed_projection() -> None:
    snapshot = _snapshot(
        bids={Decimal("102"): Decimal("1")},
        asks={Decimal("101"): Decimal("1")},
    )

    projection = build_book_projection(
        SnapshotBookStateAdapter(snapshot), projection_time=EVENT_TIME
    )

    assert projection.sync_state == "CROSSED"
    assert projection.bids == ()
    assert projection.asks == ()


def test_locked_snapshot_builds_fail_closed_projection() -> None:
    snapshot = _snapshot(
        bids={Decimal("100"): Decimal("1")},
        asks={Decimal("100"): Decimal("2")},
    )

    projection = build_book_projection(
        SnapshotBookStateAdapter(snapshot), projection_time=EVENT_TIME
    )

    assert projection.sync_state == "LOCKED"


def test_one_sided_snapshot_builds_empty_projection() -> None:
    snapshot = _snapshot(
        bids={Decimal("100"): Decimal("1")},
        asks={},
    )

    projection = build_book_projection(
        SnapshotBookStateAdapter(snapshot), projection_time=EVENT_TIME
    )

    assert projection.sync_state == "EMPTY"


def test_missing_event_time_builds_invalid_projection() -> None:
    snapshot = _snapshot(
        bids={Decimal("100"): Decimal("1")},
        asks={Decimal("101"): Decimal("1")},
        event_time=None,
    )

    projection = build_book_projection(
        SnapshotBookStateAdapter(snapshot), projection_time=EVENT_TIME
    )

    assert projection.sync_state == "INVALID"


def test_snapshot_adapter_exposes_fresh_synchronized_state() -> None:
    snapshot = _snapshot(
        bids={Decimal("100"): Decimal("1")},
        asks={Decimal("101"): Decimal("1")},
    )
    adapter = SnapshotBookStateAdapter(snapshot)

    assert adapter.is_synchronized is True
    assert adapter.age_ms(None) == 0
    assert adapter.snapshot() is snapshot
    assert adapter.last_event_time is snapshot.event_time
    assert adapter.gaps_detected == 0


def test_iter_book_projections_yields_utc_projection_times(
    tmp_path, monkeypatch
) -> None:
    first_snapshot = _snapshot(
        bids={Decimal("100"): Decimal("1")},
        asks={Decimal("101"): Decimal("2")},
        last_update_id=101,
    )
    second_snapshot = _snapshot(
        bids={Decimal("101"): Decimal("3")},
        asks={Decimal("102"): Decimal("4")},
        last_update_id=102,
    )
    records = ({"record": 1},)

    class StubDepthHistoryReader:
        def __init__(self, recording_dir) -> None:
            assert recording_dir == tmp_path

        def iter_records(self):
            return iter(records)

    class StubDepthReconstructor:
        def __init__(self, *, symbol: str, max_attempts: int) -> None:
            assert symbol == "ETHUSDT"
            assert max_attempts == 1

        def sample_states(self, supplied_records, *, interval_ms: int):
            assert tuple(supplied_records) == records
            assert interval_ms == 250
            yield 1_000, first_snapshot
            yield 1_234, second_snapshot

    monkeypatch.setattr(frame_source, "DepthHistoryReader", StubDepthHistoryReader)
    monkeypatch.setattr(frame_source, "DepthReconstructor", StubDepthReconstructor)

    projections = list(
        frame_source.iter_book_projections(
            tmp_path,
            interval_ms=250,
            depth_levels=1,
            symbol="ETHUSDT",
        )
    )

    assert [projection.sync_state for projection in projections] == [SYNCED, SYNCED]
    assert [projection.projection_time for projection in projections] == [
        datetime(1970, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
        datetime(1970, 1, 1, 0, 0, 1, 234000, tzinfo=timezone.utc),
    ]
    assert all(projection.projection_time.tzinfo is timezone.utc for projection in projections)
    assert [projection.depth_levels for projection in projections] == [1, 1]
```

## 7. 次の境界

- 本報告時点で新規2ソースファイルは未追跡・未stage。
- commitは統括の別指示待ち。
- Task 2（供給経路、WebSocket送信、gate有効化、保護ファイル接触）には進んでいない。
