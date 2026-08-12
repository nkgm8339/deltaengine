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
