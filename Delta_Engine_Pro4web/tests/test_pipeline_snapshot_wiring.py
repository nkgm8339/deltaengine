from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from src.config import load_config
from src.normalization.normalizer import ExchangeProfile
from src.pipeline import LivePipeline, ReplayPipeline, load_profile
from src.strategy_engine.ingestion.market_state import MarketStateSnapshot
from src.acquisition.replay import ListTransport


PROJECT_ROOT = Path(__file__).resolve().parents[1]
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
            "side_rule": "m == true → SELL, m == false → BUY",
        },
        "timestamp_format": "epoch_ms",
    }
)


def _trade(trade_id: int, event_ms: int, *, sell: bool = False) -> dict:
    return {
        "e": "aggTrade",
        "E": event_ms,
        "T": event_ms,
        "a": trade_id,
        "s": "BTCUSDT",
        "p": "100",
        "q": "2",
        "m": sell,
    }


class _Connect:
    def __init__(self, messages: list[dict]) -> None:
        self.messages = messages

    async def __call__(self, url: str, streams: list[str]) -> ListTransport:
        return ListTransport(self.messages)


def test_replay_pipeline_publishes_market_snapshot(tmp_path: Path) -> None:
    raw = [
        {
            "e": "depthSnapshot",
            "E": 1767225600000,
            "s": "BTCUSDT",
            "u": 1,
            "b": [["99.9", "2"]],
            "a": [["100.1", "3"]],
        },
        _trade(1, 1767225601000),
        _trade(2, 1767225661000, sell=True),
    ]
    data = tmp_path / "replay.jsonl"
    data.write_text("\n".join(json.dumps(row) for row in raw) + "\n", encoding="utf-8")
    config = load_config(PROJECT_ROOT / "config" / "config.yaml")
    profile = load_profile(PROJECT_ROOT / "config" / "profiles" / "binance.yaml")
    pipeline = ReplayPipeline.from_config(
        config, profile, tmp_path / "parquet", tmp_path / "replay.duckdb"
    )

    pipeline.run(data)

    assert isinstance(pipeline._last_market_state, MarketStateSnapshot)
    assert pipeline.tick_size == Decimal("0.1")
    assert [sample.value for sample in pipeline._last_market_state.price_samples] == [
        Decimal("100"),
        Decimal("100"),
    ]


def test_live_pipeline_publishes_market_snapshot_and_producer(tmp_path: Path) -> None:
    messages = [_trade(1, 1767225601000), _trade(2, 1767225661000, sell=True)]
    pipeline = LivePipeline(
        symbol="BTCUSDT",
        timeframe="1m",
        profile=PROFILE,
        ws_url="wss://test/ws",
        subscribe_streams=["btcusdt@aggTrade"],
        parquet_path=tmp_path / "parquet",
        duckdb_path=tmp_path / "live.duckdb",
        batch_size=10,
        flush_interval_sec=1,
        reconnect=False,
    )

    pipeline.run(
        connect=_Connect(messages),
        poll_interval=0.02,
        fetch_snapshot=None,
    )

    assert isinstance(pipeline._last_market_state, MarketStateSnapshot)
    assert pipeline.tick_size == Decimal("0.1")
    assert pipeline._snapshot_producer is not None
    assert [sample.value for sample in pipeline._last_market_state.price_samples] == [
        Decimal("100"),
        Decimal("100"),
    ]
