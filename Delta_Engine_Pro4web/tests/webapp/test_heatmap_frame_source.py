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
