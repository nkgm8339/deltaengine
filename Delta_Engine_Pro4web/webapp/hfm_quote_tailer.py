"""Read the observation-only HFM MT5 Bid/Ask JSONL stream."""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from src.orderflow.combined_context_runtime import HfmQuote

logger = logging.getLogger("webapp.hfm_quote_tailer")


def default_hfm_quote_path() -> Path:
    configured = os.environ.get("HFM_QUOTE_FILE")
    if configured:
        return Path(configured)
    appdata = os.environ.get("APPDATA")
    if appdata:
        return (
            Path(appdata)
            / "MetaQuotes"
            / "Terminal"
            / "Common"
            / "Files"
            / "DeltaEngine_HFM_quotes_utf8.jsonl"
        )
    return Path("/app/data_05M/hfm/DeltaEngine_HFM_quotes_utf8.jsonl")


def parse_hfm_quote(line: str, received_time: datetime) -> HfmQuote:
    message: dict[str, Any] = json.loads(line)
    server_time = message.get("server_time_msc")
    source_time = None
    if server_time not in (None, ""):
        seconds, millis = divmod(int(server_time), 1000)
        source_time = (
            datetime.fromtimestamp(seconds, tz=timezone.utc)
            + timedelta(milliseconds=millis)
        )
    sequence = message.get("sequence")
    return HfmQuote(
        symbol=str(message["symbol"]),
        source_time=source_time,
        received_time=received_time,
        sequence=int(sequence) if sequence not in (None, "") else None,
        bid=Decimal(str(message["bid"])),
        ask=Decimal(str(message["ask"])),
    )


def _last_complete_line(path: Path, block_size: int = 65_536) -> str | None:
    size = path.stat().st_size
    if size <= 0:
        return None
    with path.open("rb") as handle:
        start = max(0, size - block_size)
        handle.seek(start)
        data = handle.read()
    lines = [part for part in data.splitlines() if part.strip()]
    if not lines:
        return None
    return lines[-1].decode("utf-8-sig")


async def _dispatch(callback: Callable[[HfmQuote], object], quote: HfmQuote) -> None:
    result = callback(quote)
    if inspect.isawaitable(result):
        await result


async def hfm_quote_tail_loop(
    callback: Callable[[HfmQuote], object],
    *,
    path: Path | None = None,
    poll_interval_sec: float = 0.05,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> None:
    """Tail new HFM observations and first publish the latest complete quote."""
    source = path or default_hfm_quote_path()
    offset: int | None = None
    pending = b""
    while True:
        try:
            if not source.exists():
                offset = None
                pending = b""
                await asyncio.sleep(poll_interval_sec)
                continue
            size = source.stat().st_size
            if offset is None:
                latest = _last_complete_line(source)
                if latest is not None:
                    initial_time = datetime.fromtimestamp(
                        source.stat().st_mtime, tz=timezone.utc,
                    )
                    try:
                        await _dispatch(callback, parse_hfm_quote(latest, initial_time))
                    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                        logger.warning("latest HFM quote line is invalid")
                offset = size
                await asyncio.sleep(poll_interval_sec)
                continue
            if size < offset:
                offset = 0
                pending = b""
            if size == offset:
                await asyncio.sleep(poll_interval_sec)
                continue
            with source.open("rb") as handle:
                handle.seek(offset)
                chunk = handle.read()
                offset = handle.tell()
            pending += chunk
            lines = pending.split(b"\n")
            pending = lines.pop()
            for raw_line in lines:
                if not raw_line.strip():
                    continue
                received_time = clock()
                try:
                    quote = parse_hfm_quote(raw_line.decode("utf-8-sig"), received_time)
                except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError):
                    logger.warning("invalid HFM quote line skipped")
                    continue
                await _dispatch(callback, quote)
        except asyncio.CancelledError:
            raise
        except OSError as exc:
            logger.warning("HFM quote file retrying after: %s", exc)
            await asyncio.sleep(1)
