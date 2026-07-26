"""Snapshot closed Binance Futures 1-minute klines for offline replay.

The endpoint is public market data.  This tool has no authentication and no
order endpoint.  It writes both a Parquet snapshot and an audit metadata file.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pyarrow as pa
import pyarrow.parquet as pq
import requests


UTC = timezone.utc
INTERVAL_MS = 60_000
DEFAULT_URL = "https://fapi.binance.com/fapi/v1/klines"


@dataclass(frozen=True)
class BinanceKline:
    open_time: datetime
    close_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_count: int


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("time must be timezone-aware")
    return parsed.astimezone(UTC)


def _request_payload(
    request_get: Callable[..., object],
    url: str,
    params: dict[str, object],
    *,
    attempts: int = 3,
) -> list[list[object]]:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = request_get(
                url,
                params=params,
                timeout=20,
                headers={"User-Agent": "DeltaEngine-research-snapshot/1.0"},
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                raise ValueError("Binance kline response is not a list")
            return payload
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(0.5 * (attempt + 1))
    assert last_error is not None
    raise RuntimeError(f"Binance kline request failed: {last_error}") from last_error


def fetch_closed_klines(
    *,
    symbol: str,
    start: datetime,
    end: datetime,
    url: str = DEFAULT_URL,
    request_get: Callable[..., object] = requests.get,
) -> tuple[tuple[BinanceKline, ...], dict[str, object]]:
    if start.tzinfo is None or end.tzinfo is None or end <= start:
        raise ValueError("start/end must be ordered timezone-aware values")
    start_ms = int(start.astimezone(UTC).timestamp() * 1000)
    end_ms = int(end.astimezone(UTC).timestamp() * 1000)
    first_open_ms = start_ms - start_ms % INTERVAL_MS
    cursor = first_open_ms
    raw_rows: list[list[object]] = []
    request_count = 0
    while cursor <= end_ms:
        params = {
            "symbol": symbol,
            "interval": "1m",
            "startTime": cursor,
            "endTime": end_ms,
            "limit": 1500,
        }
        payload = _request_payload(request_get, url, params)
        request_count += 1
        if not payload:
            break
        raw_rows.extend(payload)
        last_open_ms = int(payload[-1][0])
        next_cursor = last_open_ms + INTERVAL_MS
        if next_cursor <= cursor:
            raise RuntimeError("Binance pagination made no progress")
        cursor = next_cursor
        if len(payload) < 1500:
            break

    by_open_ms: dict[int, BinanceKline] = {}
    invalid_count = 0
    duplicate_count = 0
    for row in raw_rows:
        try:
            if len(row) < 9:
                raise ValueError("short kline row")
            open_ms = int(row[0])
            close_ms = int(row[6])
            values = [float(row[index]) for index in (1, 2, 3, 4, 5)]
            if open_ms < first_open_ms or close_ms > end_ms:
                continue
            open_price, high, low, close, volume = values
            if (
                min(values) < 0
                or open_price <= 0
                or close <= 0
                or high < max(open_price, low, close)
                or low > min(open_price, high, close)
            ):
                raise ValueError("invalid OHLC")
            parsed = BinanceKline(
                open_time=datetime.fromtimestamp(open_ms / 1000, tz=UTC),
                close_time=datetime.fromtimestamp(close_ms / 1000, tz=UTC),
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=volume,
                trade_count=int(row[8]),
            )
        except (TypeError, ValueError, IndexError):
            invalid_count += 1
            continue
        if open_ms in by_open_ms:
            duplicate_count += 1
        by_open_ms[open_ms] = parsed

    ordered_ms = sorted(by_open_ms)
    klines = tuple(by_open_ms[value] for value in ordered_ms)
    if not klines:
        raise RuntimeError("no closed Binance klines were returned")
    gap_count = sum(
        right - left != INTERVAL_MS
        for left, right in zip(ordered_ms, ordered_ms[1:])
    )
    max_gap_sec = max(
        (right - left) / 1000
        for left, right in zip(ordered_ms, ordered_ms[1:])
    ) if len(ordered_ms) > 1 else 0.0
    last_expected_open_ms = ((end_ms - (INTERVAL_MS - 1)) // INTERVAL_MS) * INTERVAL_MS
    expected_count = max(
        0,
        (last_expected_open_ms - first_open_ms) // INTERVAL_MS + 1,
    )
    metadata: dict[str, object] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source": "BINANCE_FUTURES_PUBLIC_REST",
        "source_url": url,
        "symbol": symbol,
        "interval": "1m",
        "requested_start": start.astimezone(UTC).isoformat(),
        "requested_end": end.astimezone(UTC).isoformat(),
        "first_open_time": klines[0].open_time.isoformat(),
        "last_close_time": klines[-1].close_time.isoformat(),
        "request_count": request_count,
        "response_row_count": len(raw_rows),
        "closed_row_count": len(klines),
        "expected_closed_row_count": expected_count,
        "missing_minute_count": max(0, expected_count - len(klines)),
        "duplicate_count": duplicate_count,
        "invalid_count": invalid_count,
        "gap_count": gap_count,
        "max_gap_sec": max_gap_sec,
        "authenticated": False,
        "orders_sent": False,
    }
    return klines, metadata


def _table(klines: tuple[BinanceKline, ...]) -> pa.Table:
    return pa.Table.from_pylist(
        [
            {
                "open_time": value.open_time,
                "close_time": value.close_time,
                "open": value.open,
                "high": value.high,
                "low": value.low,
                "close": value.close,
                "volume": value.volume,
                "trade_count": value.trade_count,
            }
            for value in klines
        ],
        schema=pa.schema(
            [
                ("open_time", pa.timestamp("ms", tz="UTC")),
                ("close_time", pa.timestamp("ms", tz="UTC")),
                ("open", pa.float64()),
                ("high", pa.float64()),
                ("low", pa.float64()),
                ("close", pa.float64()),
                ("volume", pa.float64()),
                ("trade_count", pa.int64()),
            ]
        ),
    )


def _args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data_05M/research/binance_futures_1m_20260725.parquet"),
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=Path("data_05M/research/binance_futures_1m_20260725.metadata.json"),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    klines, metadata = fetch_closed_klines(
        symbol=args.symbol,
        start=_parse_time(args.start),
        end=_parse_time(args.end),
        url=args.url,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.metadata.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(_table(klines), args.output, compression="zstd")
    args.metadata.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "rows": len(klines),
                "missing_minutes": metadata["missing_minute_count"],
                "gaps": metadata["gap_count"],
                "orders_sent": False,
                "output": str(args.output),
                "metadata": str(args.metadata),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
