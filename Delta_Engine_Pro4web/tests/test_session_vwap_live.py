from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from src.acquisition.replay import ListTransport
from src.normalization.normalizer import ExchangeProfile
from src.pipeline import LivePipeline


BASE = datetime(2026, 7, 27, tzinfo=timezone.utc)
BASE_MS = int(BASE.timestamp() * 1_000)
PROFILE = ExchangeProfile.from_dict(
    {
        "profile_name": "binance",
        "field_mapping": {
            "event_time": "E",
            "trade_time": "T",
            "trade_id": "a",
            "symbol": "s",
            "price": "p",
            "quantity": "q",
            "side_field": "m",
            "side_rule": "m == true -> SELL, m == false -> BUY",
        },
        "timestamp_format": "epoch_ms",
    }
)


def _agg(trade_id: int, offset_ms: int, price: str, quantity: str) -> dict:
    timestamp = BASE_MS + offset_ms
    return {
        "e": "aggTrade",
        "E": timestamp,
        "T": timestamp,
        "s": "BTCUSDT",
        "a": trade_id,
        "p": price,
        "q": quantity,
        "m": False,
    }


class FakeConnect:
    def __init__(self, messages: list[dict]) -> None:
        self.messages = messages

    async def __call__(self, _url: str, _streams: list[str]) -> ListTransport:
        return ListTransport(self.messages)


def _pipeline(tmp_path: Path) -> LivePipeline:
    return LivePipeline(
        symbol="BTCUSDT",
        timeframe="1m",
        profile=PROFILE,
        ws_url="wss://test/ws",
        subscribe_streams=["btcusdt@aggTrade"],
        parquet_path=tmp_path / "parquet",
        duckdb_path=tmp_path / "orderflow.duckdb",
        batch_size=10,
        flush_interval_sec=1,
        reconnect=False,
        flow_response_enabled=False,
        tick_size=Decimal("0.5"),
    )


def test_live_restart_restores_complete_session_vwap(tmp_path: Path) -> None:
    first = _pipeline(tmp_path)
    first.run(
        connect=FakeConnect(
            [
                _agg(1, 200, "100", "1"),
                _agg(2, 60_200, "110", "3"),
            ]
        ),
        poll_interval=0.01,
        fetch_snapshot=None,
    )

    restarted = _pipeline(tmp_path)
    restarted.run(
        connect=FakeConnect([_agg(3, 61_200, "120", "2")]),
        poll_interval=0.01,
        fetch_snapshot=None,
    )

    assert restarted.session_vwap_warm_start_error is None
    assert restarted.session_vwap_warm_start_trades == 2
    assert restarted.session_vwap_warm_start_complete is True
    assert restarted._last_market_state is not None
    assert restarted._last_market_state.session_vwap == Decimal("670") / Decimal("6")
    assert (
        restarted._last_market_state.session_open_avwap
        == restarted._last_market_state.session_vwap
    )
