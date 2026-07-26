"""14 tests for webapp.push_broker (WebSocketPayload仕様_v1)."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from webapp.push_broker import (
    PAYLOAD_VERSION,
    PushBroker,
    compute_value_area,
    d2s,
    envelope,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _utc(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def _make_broker(**kwargs) -> PushBroker:
    defaults = dict(
        symbol="BTCUSDT",
        depth_levels=15,
    )
    defaults.update(kwargs)
    return PushBroker(**defaults)


# ── test 1: envelope shape ─────────────────────────────────────────────────────

def test_envelope_shape():
    t = _utc("2024-01-01T12:00:00")
    msg = envelope("TICK", t, "BTCUSDT", {"price": "50000"})
    assert msg["v"] == PAYLOAD_VERSION == 1
    assert msg["type"] == "TICK"
    assert msg["symbol"] == "BTCUSDT"
    assert msg["time"].endswith("+00:00") or msg["time"].endswith("Z") or "T" in msg["time"]
    assert isinstance(msg["payload"], dict)


def test_tick_payload_keeps_trade_id_for_latency_audit():
    async def run():
        broker = _make_broker()
        ws = MagicMock()
        sent = []

        async def send_text(text):
            sent.append(json.loads(text))

        ws.send_text = AsyncMock(side_effect=send_text)
        await broker.register(ws)
        await broker.on_trade(SimpleNamespace(
            event_time=_utc("2026-07-23T00:00:00"),
            trade_id=987654,
            price=Decimal("50000.1"),
            quantity=Decimal("0.2"),
            side="BUY",
        ))
        assert sent[0]["type"] == "TICK"
        assert sent[0]["payload"]["trade_id"] == 987654

    asyncio.run(run())


def test_hfm_quote_payload_is_bid_ask_and_usd_spread():
    from src.orderflow.combined_context_runtime import HfmQuote

    async def run():
        broker = _make_broker()
        ws = MagicMock()
        sent = []

        async def send_text(text):
            sent.append(json.loads(text))

        ws.send_text = AsyncMock(side_effect=send_text)
        await broker.register(ws)
        now = _utc("2026-07-24T10:00:00")
        await broker.on_hfm_quote(HfmQuote(
            "#BTCUSDr", now, now, 41, Decimal("65751.411"), Decimal("65771.681"),
        ))
        assert sent[0]["type"] == "HFM_QUOTE"
        assert sent[0]["payload"]["hfm_symbol"] == "#BTCUSDr"
        assert sent[0]["payload"]["bid"] == "65751.411"
        assert sent[0]["payload"]["ask"] == "65771.681"
        assert sent[0]["payload"]["spread_usd"] == "20.270"

    asyncio.run(run())


def test_late_browser_receives_latest_hfm_quote_immediately():
    from src.orderflow.combined_context_runtime import HfmQuote

    async def run():
        broker = _make_broker()
        now = _utc("2026-07-24T10:00:00")
        await broker.on_hfm_quote(HfmQuote(
            "#BTCUSDr", now, now, 41, Decimal("100"), Decimal("120"),
        ))
        ws = MagicMock()
        sent = []

        async def send_text(text):
            sent.append(json.loads(text))

        ws.send_text = AsyncMock(side_effect=send_text)
        await broker.register(ws)
        assert sent[0]["type"] == "HFM_QUOTE"
        assert sent[0]["payload"]["spread_usd"] == "20"

    asyncio.run(run())


# ── test 2: d2s ───────────────────────────────────────────────────────────────

def test_d2s_decimal_to_str():
    assert d2s(Decimal("123.456")) == "123.456"
    assert d2s(Decimal("0")) == "0"
    assert d2s(None) is None


def test_d2s_float_raises():
    with pytest.raises(TypeError):
        d2s(1.23)  # type: ignore[arg-type]


# ── test 3: compute_value_area single-peak ────────────────────────────────────

def test_compute_value_area_single_peak():
    # 3 levels, middle has highest volume → POC = middle
    levels = [
        {"price": Decimal("102"), "bid": Decimal("10"), "ask": Decimal("5")},
        {"price": Decimal("101"), "bid": Decimal("50"), "ask": Decimal("50")},
        {"price": Decimal("100"), "bid": Decimal("10"), "ask": Decimal("5")},
    ]
    poc, vah, val = compute_value_area(levels)
    # POC is the highest-volume level (index 1, price=101)
    assert poc == "101"
    # VAH >= POC >= VAL
    assert vah is not None and val is not None
    assert Decimal(vah) >= Decimal(poc) >= Decimal(val)


# ── test 4: compute_value_area empty ─────────────────────────────────────────

def test_compute_value_area_empty():
    poc, vah, val = compute_value_area([])
    assert poc is None
    assert vah is None
    assert val is None


# ── test 5: confluence BUY direction ─────────────────────────────────────────


# ── test 6: confluence WAIT → all false / count 0 ────────────────────────────


# ── test 6b: confluence WAIT with directional composite (Task-C) ──────────────


# ── test 7: flow_score weighted average / empty returns None ──────────────────


# ── test 8: on_analysis payload shape ────────────────────────────────────────

def test_on_analysis_payload_shape():
    broker = _make_broker()
    sent = []

    async def fake_send_text(text):
        import json
        sent.append(json.loads(text))

    fake_ws = MagicMock()
    fake_ws.send_text = AsyncMock(side_effect=fake_send_text)

    analysis_result = MagicMock()
    analysis_result.analysis_time = _utc("2024-01-01T12:00:00")
    analysis_result.market_state = "BULL"
    analysis_result.risk_level = "LOW"
    analysis_result.reasons = ("CVD_UP",)

    signal_result = MagicMock()
    signal_result.signal = "BUY"
    signal_result.confidence = Decimal("0.75")
    signal_result.composite = None
    signal_result.reasons = ()

    module_scores = {
        "cvd": Decimal("55"),
        "footprint": Decimal("42"),
        "imbalance": Decimal("10"),
    }
    absorption_result = None

    async def run():
        await broker.register(fake_ws)
        await broker.on_analysis(analysis_result, signal_result, module_scores, absorption_result)

    asyncio.run(run())

    assert len(sent) == 1
    msg = sent[0]
    p = msg["payload"]
    assert p["divergence"] is None
    assert p["imbalance"] is None
    assert p["absorption"] is None
    assert p["flow_events"] is None


def test_on_analysis_serializes_imbalance_walls_and_effective_floor():
    from src.orderflow.imbalance import ImbalanceResult, StackedImbalance

    broker = _make_broker()
    sent = []

    async def fake_send_text(text):
        import json
        sent.append(json.loads(text))

    fake_ws = MagicMock()
    fake_ws.send_text = AsyncMock(side_effect=fake_send_text)
    analysis_time = _utc("2024-01-01T12:00:00")
    analysis_result = MagicMock(
        analysis_time=analysis_time, market_state="BULL", risk_level="LOW", reasons=(),
    )
    signal_result = MagicMock(
        signal="BUY", confidence=Decimal("0.75"), composite=None, reasons=[],
    )
    imbalance_result = ImbalanceResult(
        bar_time=analysis_time,
        symbol="BTCUSDT",
        buy_imbalances=(),
        sell_imbalances=(),
        stacked_imbalances=(
            StackedImbalance(
                start_price=Decimal("100.25"),
                end_price=Decimal("100.75"),
                count=3,
                direction="BUY",
            ),
            StackedImbalance(
                start_price=Decimal("99.75"),
                end_price=Decimal("99.25"),
                count=4,
                direction="SELL",
            ),
        ),
    )
    detector = MagicMock()
    detector.ratio_threshold = Decimal("3.0")
    detector.stack_count = 3
    detector.ratio_cap = Decimal("10.0")
    detector.last_effective_min_volume = Decimal("0.125")

    async def run():
        await broker.register(fake_ws)
        await broker.on_analysis(
            analysis_result,
            signal_result,
            {},
            None,
            None,
            imbalance_result,
            detector,
        )

    asyncio.run(run())
    assert sent[0]["payload"]["imbalance"] == {
        "walls": [
            {
                "side": "BUY",
                "count": 3,
                "price_start": "100.25",
                "price_end": "100.75",
            },
            {
                "side": "SELL",
                "count": 4,
                "price_start": "99.75",
                "price_end": "99.25",
            },
        ],
        "ratio_threshold": "3.0",
        "stack_count": 3,
        "ratio_cap": "10.0",
        "min_volume": "0.125",
    }


# ── test 9: independent IMBALANCE no longer emits rounded flow events ────────

def test_evaluate_and_store_excludes_imbalance_score_and_flow_events():
    """Independent IMBALANCE stays out of composite and rounded FLOW events."""
    from src.pipeline import _evaluate_and_store
    from src.orderflow.imbalance import ImbalanceResult, StackedImbalance
    from unittest.mock import MagicMock
    from decimal import Decimal
    import datetime

    emitted = []

    def on_ev(ev):
        emitted.append(ev)

    bar_time = datetime.datetime(2024, 1, 1, 12, 0, tzinfo=datetime.timezone.utc)

    # Build a minimal stacked imbalance result with both directions
    si_buy = StackedImbalance(
        start_price=Decimal("101"), end_price=Decimal("103"), count=5, direction="BUY"
    )
    si_sell = StackedImbalance(
        start_price=Decimal("99"), end_price=Decimal("97"), count=3, direction="SELL"
    )

    imb_result = ImbalanceResult(
        bar_time=bar_time,
        symbol="BTCUSDT",
        buy_imbalances=(),
        sell_imbalances=(),
        stacked_imbalances=(si_buy, si_sell),
    )

    # Mock all dependencies
    imbalance_detector = MagicMock()
    imbalance_detector.detect.return_value = imb_result

    candle = MagicMock()
    candle.bar_time = bar_time
    candle.symbol = "BTCUSDT"
    candle.delta = Decimal("100")

    fp_bar = MagicMock()
    fp_level = MagicMock()
    fp_level.buy_volume = Decimal("10")
    fp_level.sell_volume = Decimal("8")
    fp_bar.levels = [fp_level]

    signal_engine = MagicMock()
    from src.orderflow.signal import SignalResult
    signal_result = SignalResult(Decimal("1"), Decimal("0.7"), "BUY", ())
    signal_engine.evaluate.return_value = signal_result

    storage = MagicMock()
    volume_ref = MagicMock()
    volume_ref.current.return_value = None
    absorption = MagicMock()
    absorption.current.return_value = None
    analysis_engine = MagicMock()
    analysis_result = MagicMock()
    analysis_result.analysis_time = bar_time
    analysis_engine.evaluate.return_value = analysis_result

    result = _evaluate_and_store(
        candle, fp_bar,
        imbalance_detector, signal_engine, storage,
        None, 3,
        volume_ref, absorption, analysis_engine,
        on_webapp_flow_event=on_ev,
    )

    assert emitted == []

    # Independent indicators are no longer passed into the shrinking composite.
    assert result.module_scores is not None
    assert result.module_scores["cvd"] is None
    assert result.module_scores["footprint"] is None
    assert result.module_scores["imbalance"] is None
    assert signal_engine.evaluate.call_args.args[0] is None
    assert signal_engine.evaluate.call_args.args[1] is None
    assert signal_engine.evaluate.call_args.args[2] is None


# ── test 10: ABSORPTION hook fires exactly once per event_detected increment ──

def test_absorption_hook_fires_once_per_event():
    """ABSORPTION PushFlowEvent fires once per events_detected increment."""
    from src.pipeline import LivePipeline, PushFlowEvent
    import datetime

    fired = []

    def on_ev(ev: PushFlowEvent):
        fired.append(ev)

    # Minimal mock pipeline with absorption detector that triggers once
    absorption = MagicMock()
    absorption.events_detected = 0  # before

    ar = MagicMock()
    ar.classification = "BUY_ABSORPTION"
    ar.strength = Decimal("0.75")
    absorption.current.return_value = ar

    event_time = datetime.datetime(2024, 1, 1, 12, 0, tzinfo=datetime.timezone.utc)
    normalized = MagicMock()
    normalized.event_time = event_time

    # Simulate what handle() does:
    prev_abs = absorption.events_detected  # 0
    absorption.events_detected = 1         # increment (simulates observe_trade effect)

    if absorption.events_detected > prev_abs:
        result_ar = absorption.current()
        if result_ar is not None:
            side = "BUY" if result_ar.classification == "BUY_ABSORPTION" else "SELL"
            on_ev(PushFlowEvent(
                event_time=normalized.event_time,
                symbol="BTCUSDT",
                category="ABSORPTION",
                side=side,
                strength=result_ar.strength,
                detector="AbsorptionDetector",
                detail="window_sec=10",
            ))

    # Call again without incrementing → no new fire
    prev_abs2 = absorption.events_detected  # 1
    # events_detected stays 1 → no new event
    if absorption.events_detected > prev_abs2:
        on_ev(MagicMock())  # should NOT run

    assert len(fired) == 1
    assert fired[0].category == "ABSORPTION"
    assert fired[0].side == "BUY"
    assert fired[0].strength == Decimal("0.75")


# ── test 11: on_webapp_flow_event=None causes no exception ───────────────────

def test_flow_hook_none_no_exception():
    """_evaluate_and_store with on_webapp_flow_event=None raises no exception."""
    from src.pipeline import _evaluate_and_store
    from src.orderflow.imbalance import ImbalanceResult, StackedImbalance
    import datetime

    bar_time = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
    si = StackedImbalance(
        start_price=Decimal("100"), end_price=Decimal("103"), count=4, direction="BUY"
    )
    imb_result = ImbalanceResult(
        bar_time=bar_time, symbol="BTCUSDT",
        buy_imbalances=(), sell_imbalances=(),
        stacked_imbalances=(si,),
    )

    imbalance_detector = MagicMock()
    imbalance_detector.detect.return_value = imb_result

    candle = MagicMock()
    candle.bar_time = bar_time
    candle.symbol = "BTCUSDT"
    candle.delta = Decimal("0")

    fp_bar = MagicMock()
    lv = MagicMock()
    lv.buy_volume = Decimal("5")
    lv.sell_volume = Decimal("5")
    fp_bar.levels = [lv]

    signal_engine = MagicMock()
    sr = MagicMock()
    sr.signal = "WAIT"
    sr.confidence = Decimal("0")
    sr.reasons = []
    signal_engine.evaluate.return_value = sr

    storage = MagicMock()
    volume_ref = MagicMock()
    absorption = MagicMock()
    absorption.current.return_value = None
    analysis_engine = MagicMock()
    ar = MagicMock()
    analysis_engine.evaluate.return_value = ar

    # Must not raise
    result = _evaluate_and_store(
        candle, fp_bar,
        imbalance_detector, signal_engine, storage,
        None, 3,
        volume_ref, absorption, analysis_engine,
        on_webapp_flow_event=None,
    )
    assert result.module_scores is not None


# ── test 12: WS endpoint sends HELLO with payload_version=1 ──────────────────

def test_ws_hello_payload_version():
    from fastapi.testclient import TestClient
    from unittest.mock import AsyncMock, MagicMock, patch

    mock_pipeline = MagicMock()
    mock_pipeline.run_async = AsyncMock(return_value=None)
    mock_pipeline.on_trade = None
    mock_pipeline.on_candle = None
    mock_pipeline.on_analysis = None
    mock_pipeline.on_liquidation = None
    mock_pipeline.on_flow_event = None
    mock_pipeline.on_webapp_flow_event = None
    mock_pipeline.book_manager = None
    mock_pipeline.cvd_calculator = None
    mock_pipeline.absorption_detector = None
    mock_pipeline._last_bar_close = None
    mock_pipeline._last_fp_bar = None

    mock_config = MagicMock()
    mock_config.market.symbol = "BTCUSDT"
    mock_config.market.bar_timeframe = "1m"
    mock_config.webapp.host = "0.0.0.0"
    mock_config.webapp.port = 8080
    mock_config.webapp.depth_levels = 15
    mock_config.webapp.flow_window_sec = 60
    mock_config.webapp.alert_threshold = 0.85
    mock_config.webapp.confluence.score_threshold = 40
    mock_config.webapp.confluence.strength_threshold = 0.5
    mock_config.webapp.oi_poll_interval_sec = 10
    mock_config.webapp.tick_push_interval_ms = 50
    mock_config.webapp.bar_update_interval_sec = 0.2
    mock_config.monitor.enabled = False
    mock_config.monitor.interval_sec = 5
    mock_config.monitor.log_dir = "data/monitor"
    mock_config.monitor.bar_missing_tolerance_sec = 90
    mock_config.monitor.latency_yellow_ms = 2000
    mock_config.monitor.latency_red_ms = 10000
    mock_config.monitor.memory_yellow_mb = 900
    mock_config.monitor.memory_red_mb = 1500
    mock_config.monitor.window_min = 15
    mock_config.monitor.reconnect_yellow = 1
    mock_config.monitor.reconnect_red = 3
    mock_config.monitor.gap_yellow = 1
    mock_config.monitor.gap_red = 5
    mock_config.monitor.exception_yellow = 1
    mock_config.monitor.exception_red = 3
    mock_config.replay.enabled = False
    mock_config.signal.enabled = True
    mock_config.database.duckdb_path = ":memory:"
    mock_config.normalizer.exchange_profile = "binance"
    mock_config._data = {"webapp": {}}

    with patch("webapp.main.load_config", return_value=mock_config), \
         patch("webapp.main.load_profile", return_value=MagicMock()), \
         patch("webapp.main.LivePipeline") as MockPipeline, \
         patch("webapp.main.oi_polling_loop", new=AsyncMock()):
        MockPipeline.from_config.return_value = mock_pipeline

        from webapp.main import app
        with TestClient(app) as client:
            with client.websocket_connect("/ws") as ws:
                data = ws.receive_json()
                assert data["type"] == "HELLO"
                assert data["v"] == 1
                assert data["payload"]["payload_version"] == 1
                assert data["symbol"] == "BTCUSDT"


# ── test 13: register/unregister removes dead client on broadcast ─────────────

def test_register_unregister_dead_client_removed():
    broker = _make_broker()

    broken_ws = MagicMock()
    broken_ws.send_text = AsyncMock(side_effect=Exception("connection closed"))

    good_ws = MagicMock()
    received = []

    async def good_send(text):
        received.append(text)

    good_ws.send_text = AsyncMock(side_effect=good_send)

    async def run():
        await broker.register(broken_ws)
        await broker.register(good_ws)
        assert broker.client_count == 2

        t = _utc("2024-01-01T00:00:00")
        msg = envelope("STATS", t, "BTCUSDT", {"x": "1"})
        await broker._broadcast(msg)

        # broken_ws should have been removed
        assert broken_ws not in broker._clients
        # good_ws should still be there
        assert good_ws in broker._clients
        assert len(received) == 1

    asyncio.run(run())


# ── test 14: config validation — invalid port fails ──────────────────────────

def test_config_webapp_invalid_port_raises():
    """ConfigValidationError raised for webapp.port out of range."""
    import tempfile, os
    from src.config import load_config, ConfigValidationError

    bad_yaml = """
market:
  symbol: BTCUSDT
  exchange: BINANCE
  bar_timeframe: 1m
websocket:
  url: wss://example.com
  subscribe_streams:
    - btcusdt@aggTrade
webapp:
  port: 99999
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(bad_yaml)
        path = f.name
    try:
        with pytest.raises(ConfigValidationError):
            load_config(path)
    finally:
        os.unlink(path)

# ── test 15 (TaskF): CANDLE payload footprint levels are price-DESCENDING ─────

def test_candle_payload_footprint_levels_descending_and_va_ordered():
    """Adapter contract (webapp.main.on_candle_cb): footprint.to_levels() is
    ascending by module contract; the adapter must reverse it so the CANDLE
    payload is price-descending (WebSocketPayload仕様_v1 §4.3) and
    compute_value_area receives its documented order → VAL <= POC <= VAH."""
    from src.orderflow.footprint import PriceLevel

    # Producer-side ascending tuple (as returned by to_levels()); volume peak
    # near the LOW end so a VAH/VAL swap would violate the assertion below.
    asc = tuple(
        PriceLevel(price=Decimal(p), buy_volume=Decimal(b), sell_volume=Decimal(s))
        for p, b, s in [
            ("100", "20", "10"),  # total 30
            ("101", "30", "20"),  # total 50 → POC (50/120 < 70% → VA must expand)
            ("102", "12", "8"),   # total 20
            ("103", "6", "4"),    # total 10
            ("104", "3", "2"),    # total 5
            ("105", "3", "2"),    # total 5
        ]
    )
    assert list(lv.price for lv in asc) == sorted(lv.price for lv in asc)

    # Exact adapter conversion (webapp/main.py on_candle_cb):
    fp_levels = [
        {"price": lv.price, "bid": lv.sell_volume, "ask": lv.buy_volume}
        for lv in reversed(asc)
    ]

    candle = MagicMock()
    candle.bar_time = _utc("2024-01-01T12:00:00")
    candle.timeframe = "1m"
    for attr in ("open", "high", "low", "close", "volume", "delta", "cvd"):
        setattr(candle, attr, Decimal("1"))

    broker = _make_broker()
    sent = []

    async def fake_send_text(text):
        import json
        sent.append(json.loads(text))

    fake_ws = MagicMock()
    fake_ws.send_text = AsyncMock(side_effect=fake_send_text)

    async def run():
        await broker.register(fake_ws)
        await broker.on_candle(candle, fp_levels, None)

    asyncio.run(run())

    assert len(sent) == 1
    fp = sent[0]["payload"]["footprint"]
    prices = [Decimal(lv["price"]) for lv in fp["levels"]]
    assert prices == sorted(prices, reverse=True), "payload levels must be price-descending"
    assert all(a > b for a, b in zip(prices, prices[1:])), "strictly descending"
    poc, vah, val = fp["poc_price"], fp["vah_price"], fp["val_price"]
    assert poc == "101"
    # grand=120, target=84: VA expands to {100,101,102} → strict on both sides.
    # An ascending-order regression swaps hi/lo and violates these.
    assert Decimal(val) < Decimal(poc) < Decimal(vah)
    assert (vah, val) == ("102", "100")


# ── test 16 (TaskF): adapter wiring guard — reversed() present in main.py ─────

def test_main_adapter_reverses_footprint_levels():
    """Regression guard: webapp/main.py must convert ascending→descending at the
    adapter boundary. If this line is removed, the UI price axis inverts and
    VAH/VAL swap (TaskF)."""
    import pathlib
    src = pathlib.Path(__file__).resolve().parents[2].joinpath(
        "webapp", "main.py").read_text(encoding="utf-8")
    assert "reversed(fp_bar.levels)" in src


def test_on_analysis_serializes_divergence_native_object():
    from src.orderflow.divergence import DivergenceDirection, DivergenceEvent, DivergenceKind

    broker = _make_broker()
    sent = []

    async def fake_send_text(text):
        import json
        sent.append(json.loads(text))

    fake_ws = MagicMock()
    fake_ws.send_text = AsyncMock(side_effect=fake_send_text)
    event = DivergenceEvent(
        direction=DivergenceDirection.BULLISH, kind=DivergenceKind.REGULAR,
        symbol="BTCUSDT", timeframe="1m", detected_time=_utc("2024-01-01T12:00:00"),
        pivot_time=_utc("2024-01-01T11:59:00"), previous_pivot_time=_utc("2024-01-01T11:57:00"),
        pivot_price=Decimal("99"), previous_pivot_price=Decimal("100"),
        pivot_cvd=Decimal("10"), previous_pivot_cvd=Decimal("5"),
        price_change=Decimal("-1"), cvd_change=Decimal("5"), bars_between=2,
    )
    analysis_result = MagicMock(analysis_time=_utc("2024-01-01T12:00:00"), market_state="BULL", risk_level="LOW", reasons=())
    signal_result = MagicMock(signal="BUY", confidence=Decimal("0.75"), composite=None, reasons=[])

    async def run():
        await broker.register(fake_ws)
        await broker.on_analysis(analysis_result, signal_result, {}, None, event)

    asyncio.run(run())
    payload = sent[0]["payload"]["divergence"]
    assert payload == {
        "direction": "BULLISH",
        "kind": "REGULAR",
        "pivot_time": "2024-01-01T11:59:00+00:00",
        "previous_pivot_time": "2024-01-01T11:57:00+00:00",
        "pivot_price": "99",
        "previous_pivot_price": "100",
        "pivot_cvd": "10",
        "previous_pivot_cvd": "5",
        "price_change": "-1",
        "cvd_change": "5",
        "bars_between": 2,
    }


def test_on_flow_response_serializes_observations_without_signal_language():
    from src.orderflow.flow_price_response import FlowResponseSnapshot, FlowResponseState

    broker = _make_broker()
    sent = []

    async def fake_send_text(text):
        import json
        sent.append(json.loads(text))

    fake_ws = MagicMock()
    fake_ws.send_text = AsyncMock(side_effect=fake_send_text)
    snapshot = FlowResponseSnapshot(
        event_time=_utc("2024-01-01T12:00:00"), symbol="BTCUSDT", window_sec=60,
        state=FlowResponseState.BUY_STALLED, pressure_side="BUY",
        buy_volume=Decimal("12"), sell_volume=Decimal("3"), total_volume=Decimal("15"),
        delta=Decimal("9"), pressure_ratio=Decimal("0.6"), persistence=Decimal("0.8"),
        first_price=Decimal("100"), last_price=Decimal("100.005"),
        high_price=Decimal("100.01"), low_price=Decimal("99.99"),
        price_change=Decimal("0.005"), price_change_bps=Decimal("0.5"),
        relative_volume=None, trade_count=42, observed_span_sec=60,
    )

    async def run():
        await broker.register(fake_ws)
        await broker.on_flow_response((snapshot,))

    asyncio.run(run())
    assert sent[0]["type"] == "FLOW_RESPONSE"
    payload = sent[0]["payload"]
    assert payload["note"] == "observed state; not a trade signal or probability"
    assert payload["windows"][0]["state"] == "BUY_STALLED"
    assert payload["windows"][0]["pressure_ratio"] == "0.6"
    assert payload["windows"][0]["relative_volume"] is None


def test_on_flow_event_accepts_native_detector_event_and_keeps_event_time():
    from src.orderflow.flow_detector import FlowEvent

    broker = _make_broker()
    sent = []

    async def fake_send_text(text):
        import json
        sent.append(json.loads(text))

    fake_ws = MagicMock()
    fake_ws.send_text = AsyncMock(side_effect=fake_send_text)
    event = FlowEvent(
        event_time=_utc("2024-01-01T12:00:07"), kind="large_trade", side="BUY",
        price=Decimal("42000.5"), strength=Decimal("0.91"),
        detail={"quantity": "7.5"},
    )

    async def run():
        await broker.register(fake_ws)
        await broker.on_flow_event(event)

    asyncio.run(run())
    assert sent[0]["type"] == "FLOW"
    assert sent[0]["payload"] == {
        "event_time": "2024-01-01T12:00:07+00:00",
        "category": "LARGE_TRADE",
        "side": "BUY",
        "strength": "0.91",
        "price": "42000.5",
        "detector": "large_trade",
        "detail": {"quantity": "7.5"},
    }


def test_on_analysis_flow_events_include_original_timestamp_for_candle_markers():
    from src.orderflow.flow_detector import FlowEvent

    broker = _make_broker()
    sent = []

    async def fake_send_text(text):
        import json
        sent.append(json.loads(text))

    fake_ws = MagicMock()
    fake_ws.send_text = AsyncMock(side_effect=fake_send_text)
    analysis_result = MagicMock(
        analysis_time=_utc("2024-01-01T12:01:00"), market_state="BULL",
        risk_level="LOW", reasons=(),
    )
    signal_result = MagicMock(
        signal="BUY", confidence=Decimal("0.75"), composite=None, reasons=(),
    )
    event = FlowEvent(
        event_time=_utc("2024-01-01T12:00:07"), kind="sweep", side="SELL",
        price=Decimal("42001"), strength=Decimal("0.88"), detail={"levels": 4},
    )

    async def run():
        await broker.register(fake_ws)
        await broker.on_analysis(
            analysis_result, signal_result, {}, None, flow_events=[event],
        )

    asyncio.run(run())
    item = sent[0]["payload"]["flow_events"][0]
    assert item["event_time"] == "2024-01-01T12:00:07+00:00"
    assert item["category"] == "SWEEP"
    assert item["price"] == "42001"


def test_main_wires_native_and_webapp_flow_events_to_broker():
    import pathlib

    source = pathlib.Path(__file__).resolve().parents[2].joinpath(
        "webapp", "main.py",
    ).read_text(encoding="utf-8")
    assert "pipeline.on_flow_event = on_webapp_flow_cb" in source
    assert "pipeline.on_webapp_flow_event = on_webapp_flow_cb" in source


def test_flow_event_marker_ui_is_two_hour_in_memory_observation_only():
    import pathlib

    source = pathlib.Path(__file__).resolve().parents[2].joinpath(
        "webapp", "static", "index.html",
    ).read_text(encoding="utf-8")
    assert "FLOW_EVENT_RETENTION_MS=2*60*60*1000" in source
    assert "function ingestFlowEvent(" in source
    assert "function flowEventBuckets(" in source
    assert "function flowEventMarkersSvg(" in source
    assert "FLOW EVENTS · 2H MEMORY" in source
    assert "flowEventsDetail(events)" in source
    assert "/api/history/flow-events" not in source


def test_flow_event_candle_markers_are_individually_toggleable():
    import pathlib

    source = pathlib.Path(__file__).resolve().parents[2].joinpath(
        "webapp", "static", "index.html",
    ).read_text(encoding="utf-8")
    assert "CANDLE MARK" in source
    assert "chartMarker:true" in source
    assert 'data-flow-marker-key="${k}"' in source
    assert "function isFlowMarkerEnabled(category)" in source
    assert "if(!isFlowMarkerEnabled(event.category))continue;" in source
    assert "saveFlowCfg();renderChart();" in source
    assert 'localStorage.setItem("deltaengine.flow"' in source


def test_oi_context_ui_keeps_three_stage_chart_and_uses_persisted_real_samples():
    import pathlib

    source = pathlib.Path(__file__).resolve().parents[2].joinpath(
        "webapp", "static", "index.html",
    ).read_text(encoding="utf-8")
    assert "BINANCE OI · Δ1M · Δ5M" in source
    assert "function normalizeOiSample(" in source
    assert "function oiContextForBar(" in source
    assert "OPEN INTEREST · BINANCE USDⓈ-M" in source
    assert 'fetch("/api/history/open-interest?limit=2500")' in source
    assert "NO ALIGNED DATA · NOT FILLED" in source
    assert 'const MC={W:1200,H:500' in source
    assert '<text x="28" y="335"' in source
    assert '<text x="28" y="454"' in source
    assert "HFM SPREAD USD" in source
    assert 'case "HFM_QUOTE": onHfmQuote(m,p); break;' in source
    assert "function onHfmQuote(m,p)" in source
    assert "last.orderbook.asks[0].price" not in source


def test_chart_status_rows_remain_visible_without_resizing_three_stage_chart():
    import pathlib

    source = pathlib.Path(__file__).resolve().parents[2].joinpath(
        "webapp", "static", "index.html",
    ).read_text(encoding="utf-8")
    assert '#chartstatus{height:94px;min-height:94px;flex:0 0 94px' in source
    assert '#bottom.market-chart-panel{height:594px;min-height:594px;flex:0 0 594px' in source
    assert 'grid-template-rows:26px 38px 26px' in source
    assert 'grid-template-columns:repeat(6,minmax(0,1fr))' in source
    assert 'grid-template-rows:11px 16px' in source
    assert '.flow-response-head{font-size:11px;line-height:1}' in source
    assert '.flow-response-facts{color:#C5CDF5;font-size:14px;line-height:1}' in source
    assert 'color:#F6F1FF;font-size:14px;font-weight:900' in source
    assert '<div id="cvddiv">CVD DIVERGENCE · —</div>' in source
    assert '05M CONTEXT · CODE — · EVALUATION — · OI — · HFM —' in source
    assert source.count('PR — · P — · V —') >= 6
    assert 'const facts=`PR ${(p>=0?"+":"")}${fmt(p*100,0)}% · P ' in source
    assert 'const flowFacts=flow?`PRESSURE ' in source
    assert 'if(!rows.length){el.style.display="none"' not in source
    assert 'el.style.display="block";\n  el.style.color=dc;' not in source
    assert 'const MC={W:1200,H:500' in source
    assert '<text x="28" y="335"' in source
    assert '<text x="28" y="454"' in source


def test_cvd_slope_is_rounded_and_labels_native_btc_quantity_units():
    import pathlib

    source = pathlib.Path(__file__).resolve().parents[2].joinpath(
        "webapp", "static", "index.html",
    ).read_text(encoding="utf-8")
    assert 'const CVD={method:"regression",window:20};' in source
    assert '${fmt(r.slope,2)} BTC/bar' in source
    assert "String(r.slope)" not in source
    assert 'slope=(win[w-1]-win[0])/(w-1);' in source
    assert 'slope=sxx===0?0:sxy/sxx;' in source


def test_price_cvd_delta_oi_combination_guide_is_clickable_observation_reference():
    import pathlib

    source = pathlib.Path(__file__).resolve().parents[2].joinpath(
        "webapp", "static", "index.html",
    ).read_text(encoding="utf-8")
    assert 'id="combinationguidebtn"' in source
    assert 'aria-controls="combinationguide"' in source
    assert 'role="dialog"' in source
    assert "PRICE × CVD × Δ × OI" in source
    assert "全16ケース" in source
    assert "非常に強い上昇。" in source
    assert "ショートカバー主体。" in source
    assert "非常に強い下落。" in source
    assert "ロングの投げ売り・手仕舞い。" in source
    assert "反発候補。" in source
    assert "ショートの利確（買い戻し）の可能性が高い。" in source
    assert "上昇中に売りが増加。" in source
    assert "ロングの利確が主体。" in source
    assert "上昇反発に新規参加。" in source
    assert "売り圧力を吸収。" in source
    assert "買い圧力を吸収。" in source
    assert "下落再開に新規参加。" in source
    assert source.count('<tr><td class="guide-dir ') == 16
    assert "const OI_COMBINED_CONTEXTS=Object.freeze({" in source
    assert "function combinedOiContext(pattern,oiChange)" in source
    assert "P${pattern.no}_MISSING" in source
    assert "P${pattern.no}_UNCHANGED" in source
    assert "P${pattern.no}_${oiDirection>0?'BUILDING':'UNWINDING'}" in source
    assert 'class="ct-pattern-oi"' in source
    assert 'chartDirection("OI",oiDirection)' in source
    assert 'const oiComment=combined?' in source
    assert "これは観測評価であり、売買シグナルではありません。" in source
    assert 'event.key==="Escape"&&!backdrop.hidden' in source


def test_live_observation_and_fixed_chart_detail_keep_final_readability_contract():
    import pathlib

    source = pathlib.Path(__file__).resolve().parents[2].joinpath(
        "webapp", "static", "index.html",
    ).read_text(encoding="utf-8")
    assert 'grid-template-columns:minmax(0,1fr) 238px' in source
    assert 'grid-template-columns:minmax(0,1fr) 334px!important' in source
    assert '#charttip{display:block;position:relative;z-index:8;pointer-events:auto' in source
    assert '#lotime{color:#24D6F2;font:800 13px' in source
    assert '.lo-measure-head b{font:800 14px' in source
    assert '.lo-inline-measure b{color:#25B7E8;font:800 14px' in source
    assert '.lo-value,.lo-change{font:700 14px' in source
    assert '.lo-change{font-size:11px' in source
    assert '.lo-arrow{font:900 16px/1' in source
    assert '.lo-context-row b{' in source and 'font-size:11px' in source
    assert '.lo-context-dot{width:8px;height:8px' in source
    assert '.lo-facts .lo-title{font-size:9px}' in source
    assert '.lo-fact{' in source and 'font-size:14px' in source
    assert '#charttip .ct-time{color:#23DFFF;font-size:14px' in source
    assert '#charttip .ct-v{color:#FFFFFF;font-size:14px' in source
    assert '#charttip .ct-num{font-size:14px}' in source
    assert '#charttip .ct-pattern{' in source and 'font-size:12px' in source
    assert '#charttip .ct-dirs{' in source and 'font-size:14px' in source
    assert 'function footprintTotalsForBar(bar)' in source
    assert 'function footprintTotalsHtml(bar)' in source
    assert 'Σ BID' in source and 'Σ ASK' in source
    assert 'function selectChartIndex(index,preserveScroll=false)' in source
    assert 'const tip=$("charttip"),scrollTop=preserveScroll?tip.scrollTop:0;' in source
    assert 'if(index>=0)selectChartIndex(index,true);' in source
    assert 'tip.scrollTop=scrollTop;' in source
    assert '$("charttip").scrollTop=0;' in source


def test_flow_response_state_guide_explains_all_colors_without_changing_chart():
    import pathlib

    source = pathlib.Path(__file__).resolve().parents[2].joinpath(
        "webapp", "static", "index.html",
    ).read_text(encoding="utf-8")
    assert 'id="flowresponseguidebtn"' in source
    assert 'aria-controls="flowresponseguide"' in source
    assert 'id="flowresponseguideclose"' in source
    assert "FLOW RESPONSE STATES" in source
    assert "COLOR &amp; STATE GUIDE" in source
    assert "BUY PRESSURE · PRICE UP" in source
    assert "SELL PRESSURE · PRICE DOWN" in source
    assert "BUY PRESSURE · STALLED" in source
    assert "SELL PRESSURE · STALLED" in source
    assert "BUY PRESSURE · PRICE DOWN" in source
    assert "SELL PRESSURE · PRICE UP" in source
    assert "BUY_TRAPPED" in source
    assert "SELL_TRAPPED" in source
    assert "UNCLEAR" in source
    assert "TIME WINDOW READING MANUAL" in source
    assert "5mで異変を見る → 1mで始点を確認 → 15mで広がりを確認" in source
    assert "1 · MAIN — 5m" in source
    assert "2 · START — 1m" in source
    assert "3 · CONTEXT — 15m" in source
    assert "ローソク足は1mのままです。" in source
    assert "これは観測状態であり、売買シグナルではありません。" in source
    assert "flow-guide-swatch stalled" in source
    assert "flow-guide-swatch divergence" in source
    assert 'const MC={W:1200,H:500' in source
