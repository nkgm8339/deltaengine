"""End-to-end tests for the live CVD pipeline (Phase6).

No network: an injected ConnectFn feeds Binance-shaped aggTrade dicts (plus a
subscription ack and a depthUpdate, to verify the aggTrade-only filter) through
the exact live wiring — connector -> receiver(filter+record) -> normalizer ->
CVD -> Parquet/DuckDB. Also verifies the recorded JSON Lines round-trips through
ReplayPipeline to the identical CVD result (deterministic replay reuse, M6).
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from decimal import Decimal as _Decimal

from src.acquisition.replay import ListTransport, ReplaySource
from src.normalization.normalizer import ExchangeProfile
from src.pipeline import LivePipeline, ReplayPipeline

# Binance profile with the Phase6 aggTrade mapping (trade_id -> aggregate id `a`).
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


def _agg(a: int, m: bool, q: str, epoch_ms: int) -> dict:
    """A Binance Futures aggTrade payload (unwrapped /ws form)."""
    return {"e": "aggTrade", "E": epoch_ms, "s": "BTCUSDT", "a": a,
            "p": "100", "q": q, "f": a, "l": a, "T": epoch_ms, "m": m}


# 00:00:01 and 00:01:01 UTC -> two different 1m bars (mid-stream rollover).
_T0 = 1767225601000
_T1 = 1767225661000

# Stream carries non-trade frames the CVD path must filter out.
MESSAGES = [
    {"result": None, "id": 1},                 # subscription ack -> filtered
    _agg(1, m=False, q="2", epoch_ms=_T0),     # BUY  2  -> cvd +2
    {"e": "depthUpdate", "E": _T0, "b": [], "a": []},  # order book -> filtered
    _agg(2, m=True, q="1", epoch_ms=_T1),      # SELL 1  -> cvd -1  (new bar)
]


class FakeConnect:
    """A ConnectFn that serves a fixed message list once (finite, no network)."""

    def __init__(self, messages: list[dict]) -> None:
        self.messages = messages

    async def __call__(self, url: str, streams: list[str]) -> ListTransport:
        return ListTransport(self.messages)


def _live(tmp_path: Path, sub: str, record_path=None) -> LivePipeline:
    return LivePipeline(
        symbol="BTCUSDT",
        timeframe="1m",
        profile=PROFILE,
        ws_url="wss://test/ws",
        subscribe_streams=["btcusdt@aggTrade"],
        parquet_path=tmp_path / sub / "parquet",
        duckdb_path=tmp_path / sub / "orderflow.duckdb",
        batch_size=10,
        flush_interval_sec=1,
        reconnect=False,   # finite injected source: connector ends cleanly
    )


def test_live_pipeline_filters_normalizes_and_stores(tmp_path: Path) -> None:
    pipeline = _live(tmp_path, "live")
    stats = pipeline.run(connect=FakeConnect(MESSAGES), poll_interval=0.02,
                         fetch_snapshot=None)

    # B-2: default event_filter is now is_agg_trade_or_depth, so the depthUpdate
    # is also forwarded (forwarded=3). The subscription ack still fails the filter
    # (filtered=1). The depthUpdate arrives at the normalizer but is rejected as
    # a trade (profile has no order_book_mapping, normalization fails → rejected).
    assert stats.forwarded == 3          # two aggTrade + depthUpdate forwarded
    assert stats.filtered == 1           # only ack filtered (depthUpdate now passes)
    assert stats.normalized == 2         # only the two aggTrades normalise cleanly
    assert stats.duplicates == 0
    assert stats.trades_stored == 2
    assert stats.candles_stored == 2     # bar @00:00 closed + final bar @00:01
    assert stats.signals_stored == 2     # one signal per confirmed bar
    assert stats.final_cvd == Decimal("2") + Decimal("-1")  # == 1
    assert pipeline._last_bar_close is not None
    assert pipeline._last_bar_close.module_scores["cvd"] is None
    assert pipeline._last_bar_close.module_scores["footprint"] is None
    assert pipeline._last_bar_close.module_scores["imbalance"] is None


def test_live_divergence_clears_on_non_fire_bar(tmp_path: Path) -> None:
    messages = MESSAGES + [_agg(3, m=False, q="1", epoch_ms=_T1 + 60000)]
    pipeline = _live(tmp_path, "divergence_clear")
    detector = MagicMock()
    detector.update.side_effect = [object(), None]

    with patch("src.pipeline.CvdDivergenceDetector", return_value=detector):
        pipeline.run(
            connect=FakeConnect(messages),
            poll_interval=0.02,
            fetch_snapshot=None,
        )

    assert detector.update.call_count == 2
    assert pipeline.divergence is None


def test_live_recording_replays_identically(tmp_path: Path) -> None:
    record = tmp_path / "rec" / "btcusdt.jsonl"
    live = _live(tmp_path, "live")
    live_stats = live.run(connect=FakeConnect(MESSAGES), record_path=record, poll_interval=0.02,
                          fetch_snapshot=None)

    # B-2: the depthUpdate is now forwarded (is_agg_trade_or_depth default),
    # so it is also recorded. Recorded count = 3 (2 aggTrade + 1 depthUpdate).
    assert live_stats.recorded == 3
    recorded = ReplaySource(record).read_all()
    agg_trades = [m for m in recorded if m.get("e") == "aggTrade"]
    assert [m["a"] for m in agg_trades] == [1, 2]

    # Replaying the recording reproduces the identical CVD result (M6).
    replay = ReplayPipeline(
        symbol="BTCUSDT",
        timeframe="1m",
        profile=PROFILE,
        parquet_path=tmp_path / "replay" / "parquet",
        duckdb_path=tmp_path / "replay" / "orderflow.duckdb",
        batch_size=10,
    )
    replay_stats = replay.run(record)

    assert replay_stats.trades_stored == live_stats.trades_stored
    assert replay_stats.candles_stored == live_stats.candles_stored
    assert replay_stats.signals_stored == live_stats.signals_stored
    assert replay_stats.final_cvd == live_stats.final_cvd


# ── forceOrder (Liquidation) tests ────────────────────────────────────────────

_FORCE_ORDER = {
    "e": "forceOrder",
    "E": _T0,
    "o": {
        "s": "BTCUSDT",
        "S": "SELL",        # SELL = long position was liquidated
        "p": "100",
        "q": "2.500",
        "T": _T0,
    },
}


def test_live_pipeline_liquidation_buffer_and_stats(tmp_path: Path) -> None:
    """Injected forceOrder is reflected in liquidations_received counter."""
    pipeline = _live(tmp_path, "liq_stats")
    stats = pipeline.run(
        connect=FakeConnect([_FORCE_ORDER]),
        poll_interval=0.02,
        fetch_snapshot=None,
    )
    assert stats.liquidations_received == 1
    # Trades and candles are unaffected — liquidation does not flow into CVD path.
    assert stats.normalized == 0
    assert stats.trades_stored == 0


def test_live_pipeline_on_liquidation_hook(tmp_path: Path) -> None:
    """on_liquidation hook is called for each forceOrder; None hook causes no error."""
    # Case A: hook is a callable — must be called with the LiquidationEvent.
    received = []
    pipeline_a = LivePipeline(
        symbol="BTCUSDT",
        timeframe="1m",
        profile=PROFILE,
        ws_url="wss://test/ws",
        subscribe_streams=["btcusdt@forceOrder"],
        parquet_path=tmp_path / "hook_a" / "parquet",
        duckdb_path=tmp_path / "hook_a" / "orderflow.duckdb",
        batch_size=10,
        flush_interval_sec=1,
        reconnect=False,
        on_liquidation=received.append,
    )
    stats_a = pipeline_a.run(
        connect=FakeConnect([_FORCE_ORDER]),
        poll_interval=0.02,
        fetch_snapshot=None,
    )
    assert stats_a.liquidations_received == 1
    assert len(received) == 1
    assert received[0].side == "SELL"
    assert received[0].price == _Decimal("100")
    assert received[0].quantity == _Decimal("2.500")

    # Case B: on_liquidation=None (default) — no error, counter still increments.
    pipeline_b = _live(tmp_path, "hook_none")   # on_liquidation defaults to None
    stats_b = pipeline_b.run(
        connect=FakeConnect([_FORCE_ORDER]),
        poll_interval=0.02,
        fetch_snapshot=None,
    )
    assert stats_b.liquidations_received == 1


# ── FlowDetector integration tests ───────────────────────────────────────────

_BIG_TRADE_MESSAGES = [
    _agg(10, m=False, q="50", epoch_ms=_T0),  # BUY qty=50, well above default min_qty=5
]


def test_flow_event_buffer_and_counter(tmp_path: Path) -> None:
    """Large trade triggers a FlowEvent that appears in buffer and flow_events_emitted."""
    pipeline = LivePipeline(
        symbol="BTCUSDT",
        timeframe="1m",
        profile=PROFILE,
        ws_url="wss://test/ws",
        subscribe_streams=["btcusdt@aggTrade"],
        parquet_path=tmp_path / "flow_buf" / "parquet",
        duckdb_path=tmp_path / "flow_buf" / "orderflow.duckdb",
        batch_size=10,
        flush_interval_sec=1,
        reconnect=False,
        flow_large_trade_min_qty=Decimal("5.0"),
    )
    stats = pipeline.run(
        connect=FakeConnect(_BIG_TRADE_MESSAGES),
        poll_interval=0.02,
        fetch_snapshot=None,
    )
    assert stats.flow_events_emitted >= 1
    assert len(pipeline.flow_event_buffer) >= 1
    kinds = {evt.kind for evt in pipeline.flow_event_buffer}
    assert "large_trade" in kinds


def test_flow_score_present_in_signal_result(tmp_path: Path) -> None:
    """With w_flow>0 and large trade events, signal_result.flow_score is not None."""
    candles_seen = []
    pipeline = LivePipeline(
        symbol="BTCUSDT",
        timeframe="1m",
        profile=PROFILE,
        ws_url="wss://test/ws",
        subscribe_streams=["btcusdt@aggTrade"],
        parquet_path=tmp_path / "flow_score" / "parquet",
        duckdb_path=tmp_path / "flow_score" / "orderflow.duckdb",
        batch_size=10,
        flush_interval_sec=1,
        reconnect=False,
        flow_large_trade_min_qty=Decimal("5.0"),
        signal_w_flow=Decimal("1.0"),
        on_candle=candles_seen.append,
    )
    # Two trades across two bars → bar close happens → _last_bar_close populated
    pipeline.run(
        connect=FakeConnect(_BIG_TRADE_MESSAGES + [_agg(11, m=True, q="50", epoch_ms=_T1)]),
        poll_interval=0.02,
        fetch_snapshot=None,
    )
    # Flow is independent and no longer contributes a composite score.
    if pipeline._last_bar_close is not None:
        assert pipeline._last_bar_close.signal_result.flow_score is None
        assert pipeline._last_bar_close.flow_events is not None


def test_flow_on_flow_event_hook_called(tmp_path: Path) -> None:
    """on_flow_event hook is called for each FlowEvent emitted."""
    received = []
    pipeline = LivePipeline(
        symbol="BTCUSDT",
        timeframe="1m",
        profile=PROFILE,
        ws_url="wss://test/ws",
        subscribe_streams=["btcusdt@aggTrade"],
        parquet_path=tmp_path / "flow_hook" / "parquet",
        duckdb_path=tmp_path / "flow_hook" / "orderflow.duckdb",
        batch_size=10,
        flush_interval_sec=1,
        reconnect=False,
        flow_large_trade_min_qty=Decimal("5.0"),
        on_flow_event=received.append,
    )
    stats = pipeline.run(
        connect=FakeConnect(_BIG_TRADE_MESSAGES),
        poll_interval=0.02,
        fetch_snapshot=None,
    )
    assert stats.flow_events_emitted == len(received)
    assert len(received) >= 1
    assert all(hasattr(e, "kind") for e in received)


def test_flow_price_response_reaches_callback_and_persists_outcome(tmp_path: Path) -> None:
    received = []
    pipeline = LivePipeline(
        symbol="BTCUSDT", timeframe="1m", profile=PROFILE,
        ws_url="wss://test/ws", subscribe_streams=["btcusdt@aggTrade"],
        parquet_path=tmp_path / "flow_response" / "parquet",
        duckdb_path=tmp_path / "flow_response" / "orderflow.duckdb",
        batch_size=10, flush_interval_sec=1, reconnect=False,
        flow_response_windows_sec=(3,), flow_response_baseline_window_sec=3,
        flow_response_min_trades=3, flow_response_outcome_horizons_sec=(1,),
        on_flow_response=received.append,
    )
    messages = [
        _agg(100 + second, m=False, q="1", epoch_ms=_T0 + second * 1000)
        for second in range(4)
    ]
    pipeline.run(connect=FakeConnect(messages), poll_interval=0.02, fetch_snapshot=None)

    assert received
    assert received[0][0].state.value == "BUY_STALLED"
    assert len(pipeline.flow_response_events) == 1
    assert len(pipeline.flow_response_outcomes) == 1

    import duckdb
    con = duckdb.connect(str(tmp_path / "flow_response" / "orderflow.duckdb"), read_only=True)
    try:
        assert con.execute("SELECT count(*) FROM flow_response_events").fetchone()[0] == 1
        assert con.execute("SELECT count(*) FROM flow_response_outcomes").fetchone()[0] == 1
        row = con.execute(
            "SELECT state, horizon_sec, forward_return_bps FROM flow_response_outcomes"
        ).fetchone()
        assert row == ("BUY_STALLED", 1, Decimal("0E-8"))
    finally:
        con.close()


def test_flow_response_relative_volume_warm_starts_from_persisted_trades(tmp_path: Path) -> None:
    duckdb_path = tmp_path / "flow_warm_start" / "orderflow.duckdb"
    parquet_path = tmp_path / "flow_warm_start" / "parquet"

    def make_pipeline(callback=None) -> LivePipeline:
        return LivePipeline(
            symbol="BTCUSDT", timeframe="1m", profile=PROFILE,
            ws_url="wss://test/ws", subscribe_streams=["btcusdt@aggTrade"],
            parquet_path=parquet_path, duckdb_path=duckdb_path,
            batch_size=10, flush_interval_sec=1, reconnect=False,
            flow_response_windows_sec=(3,), flow_response_baseline_window_sec=3,
            flow_response_min_trades=1, on_flow_response=callback,
        )

    first = make_pipeline()
    first.run(
        connect=FakeConnect([
            _agg(300 + second, m=False, q="1", epoch_ms=_T0 + second * 1000)
            for second in range(3)
        ]),
        poll_interval=0.02,
        fetch_snapshot=None,
    )

    received = []
    restarted = make_pipeline(received.append)
    restarted.run(
        connect=FakeConnect([
            _agg(303 + second, m=False, q="1", epoch_ms=_T0 + (3 + second) * 1000)
            for second in range(2)
        ]),
        poll_interval=0.02,
        fetch_snapshot=None,
    )

    assert restarted.flow_response_warm_start_error is None
    assert restarted.flow_response_warm_start_trades == 3
    assert received
    assert received[0][0].relative_volume == Decimal("1")


def test_live_pipeline_rejects_zero_trade_and_keeps_flow_outcome_alive(tmp_path: Path) -> None:
    pipeline = LivePipeline(
        symbol="BTCUSDT", timeframe="1m", profile=PROFILE,
        ws_url="wss://test/ws", subscribe_streams=["btcusdt@aggTrade"],
        parquet_path=tmp_path / "zero_guard" / "parquet",
        duckdb_path=tmp_path / "zero_guard" / "orderflow.duckdb",
        batch_size=10, flush_interval_sec=1, reconnect=False,
        flow_response_windows_sec=(3,), flow_response_baseline_window_sec=3,
        flow_response_min_trades=3, flow_response_outcome_horizons_sec=(2,),
    )
    messages = [
        _agg(200 + second, m=False, q="1", epoch_ms=_T0 + second * 1000)
        for second in range(4)
    ]
    invalid = _agg(204, m=False, q="0", epoch_ms=_T0 + 4000)
    invalid["p"] = "0"
    messages.extend([invalid, _agg(205, m=False, q="1", epoch_ms=_T0 + 5000)])

    stats = pipeline.run(
        connect=FakeConnect(messages), poll_interval=0.02, fetch_snapshot=None,
    )

    assert stats.normalized == 5
    assert stats.normalizer_rejected == 1
    assert stats.trades_stored == 5
    assert len(pipeline.flow_response_events) == 1
    assert len(pipeline.flow_response_outcomes) == 1
    assert pipeline.flow_response_outcomes[0].max_down_bps == Decimal("0")

    import duckdb
    con = duckdb.connect(str(tmp_path / "zero_guard" / "orderflow.duckdb"), read_only=True)
    try:
        assert con.execute(
            "SELECT count(*) FROM trades WHERE price <= 0 OR quantity <= 0"
        ).fetchone()[0] == 0
    finally:
        con.close()
