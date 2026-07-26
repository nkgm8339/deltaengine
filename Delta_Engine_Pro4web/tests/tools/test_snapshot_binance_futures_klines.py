from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tools.snapshot_binance_futures_klines import fetch_closed_klines


UTC = timezone.utc
BASE = datetime(2026, 7, 25, tzinfo=UTC)


def raw_row(minute: int, *, close: str = "101.0") -> list[object]:
    open_ms = int((BASE + timedelta(minutes=minute)).timestamp() * 1000)
    return [
        open_ms,
        "100.0",
        "102.0",
        "99.0",
        close,
        "10.0",
        open_ms + 59_999,
        "1000.0",
        20,
        "5.0",
        "500.0",
        "0",
    ]


class Response:
    def __init__(self, payload: list[list[object]]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> list[list[object]]:
        return self.payload


def test_fetch_closed_klines_audits_complete_public_rows() -> None:
    calls: list[dict[str, object]] = []

    def get(url: str, **kwargs: object) -> Response:
        calls.append({"url": url, **kwargs})
        return Response([raw_row(0), raw_row(1), raw_row(2)])

    values, metadata = fetch_closed_klines(
        symbol="BTCUSDT",
        start=BASE,
        end=BASE + timedelta(minutes=3),
        request_get=get,
    )
    assert len(values) == 3
    assert values[-1].close == 101.0
    assert metadata["expected_closed_row_count"] == 3
    assert metadata["missing_minute_count"] == 0
    assert metadata["gap_count"] == 0
    assert metadata["orders_sent"] is False
    assert calls[0]["params"]["interval"] == "1m"


def test_fetch_closed_klines_reports_missing_minute() -> None:
    def get(url: str, **kwargs: object) -> Response:
        return Response([raw_row(0), raw_row(2)])

    values, metadata = fetch_closed_klines(
        symbol="BTCUSDT",
        start=BASE,
        end=BASE + timedelta(minutes=3),
        request_get=get,
    )
    assert len(values) == 2
    assert metadata["missing_minute_count"] == 1
    assert metadata["gap_count"] == 1
    assert metadata["max_gap_sec"] == 120.0
