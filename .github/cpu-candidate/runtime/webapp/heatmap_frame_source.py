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
