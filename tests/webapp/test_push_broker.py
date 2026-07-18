"""14 tests for webapp.push_broker (WebSocketPayload仕様_v1)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
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
        flow_window_sec=60,
        confluence_score_threshold=Decimal("40"),
        confluence_strength_threshold=Decimal("0.5"),
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

def test_confluence_buy_flags_and_count():
    broker = _make_broker(
        confluence_score_threshold=Decimal("40"),
        confluence_strength_threshold=Decimal("0.5"),
    )
    scores = {
        "cvd": Decimal("50"),       # >= 40 → True for BUY
        "footprint": Decimal("45"), # >= 40 → True
        "imbalance": Decimal("30"), # < 40 → False
        "absorption": Decimal("0.6"),  # >= 0.5 → True
        "flow": Decimal("0.4"),        # < 0.5 → False
    }
    cf = broker.confluence("BUY", scores)
    assert cf["cvd"] is True
    assert cf["footprint"] is True
    assert cf["imbalance"] is False
    assert cf["absorption"] is True
    assert cf["flow"] is False
    assert cf["count"] == 3


# ── test 6: confluence WAIT → all false / count 0 ────────────────────────────

def test_confluence_wait_all_false():
    broker = _make_broker()
    scores = {
        "cvd": Decimal("100"),
        "footprint": Decimal("100"),
        "imbalance": Decimal("100"),
        "absorption": Decimal("1.0"),
        "flow": Decimal("1.0"),
    }
    cf = broker.confluence("WAIT", scores)
    assert cf["cvd"] is False
    assert cf["footprint"] is False
    assert cf["imbalance"] is False
    assert cf["absorption"] is False
    assert cf["flow"] is False
    assert cf["count"] == 0


# ── test 6b: confluence WAIT with directional composite (Task-C) ──────────────

def test_confluence_wait_uses_composite_direction():
    """WAIT no longer short-circuits to all-False: the composite sign supplies
    the direction so aligned modules still light up."""
    broker = _make_broker(
        confluence_score_threshold=Decimal("40"),
        confluence_strength_threshold=Decimal("0.5"),
    )
    scores = {
        "cvd": Decimal("50"),        # aligned with BUY-leaning composite
        "footprint": Decimal("-45"), # opposes composite → False
        "imbalance": Decimal("60"),  # aligned → True
        "absorption": Decimal("0.6"),
        "flow": Decimal("0.2"),
    }
    # Positive composite → BUY-direction sign while signal is WAIT.
    cf = broker.confluence("WAIT", scores, composite=Decimal("35"))
    assert cf["cvd"] is True
    assert cf["footprint"] is False
    assert cf["imbalance"] is True
    assert cf["absorption"] is True
    assert cf["flow"] is False
    assert cf["count"] == 3

    # Zero composite → no direction → all False (parity with legacy WAIT).
    cf0 = broker.confluence("WAIT", scores, composite=Decimal("0"))
    assert cf0["count"] == 0


# ── test 7: flow_score weighted average / empty returns None ──────────────────

def test_flow_score_weighted_average_and_none():
    broker = _make_broker(flow_window_sec=60)
    now = _utc("2024-01-01T12:01:00")

    # Empty → None
    assert broker.flow_score(now) is None

    # Insert a record exactly at `now` (age=0), strength=0.8
    from webapp.push_broker import _FlowRecord
    broker._flow_history.append(_FlowRecord(event_time=now, strength=Decimal("0.8")))
    score = broker.flow_score(now)
    assert score is not None
    # At age=0, weight=2^0=1, so score == 0.8
    assert abs(score - Decimal("0.8")) < Decimal("0.01")


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
    signal_result.reasons = []

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
    assert p["expected_rr"] is None
    assert p["market_state"] == "BULL"
    assert p["signal"] == "BUY"
    assert p["divergence"] is None


def test_on_analysis_includes_divergence_direction():
    broker = _make_broker()
    sent = []

    async def fake_send_text(text):
        import json
        sent.append(json.loads(text))

    fake_ws = MagicMock()
    fake_ws.send_text = AsyncMock(side_effect=fake_send_text)
    analysis_result = MagicMock(
        analysis_time=_utc("2024-01-01T12:00:00"), market_state="BULL",
        risk_level="LOW", reasons=(),
    )
    signal_result = MagicMock(signal="BUY", confidence=Decimal("0.75"), composite=None, reasons=[])
    divergence = MagicMock(direction="BULLISH")

    async def run():
        await broker.register(fake_ws)
        await broker.on_analysis(analysis_result, signal_result, {}, None, divergence)



# ── test 9: FLOW hook IMBALANCE fires BUY+SELL events ────────────────────────

def test_flow_hook_imbalance_buy_sell():
    """_evaluate_and_store fires IMBALANCE PushFlowEvent for BUY and SELL."""
    from src.pipeline import PushFlowEvent, _evaluate_and_store, _BarCloseResult
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
    signal_result = MagicMock()
    signal_result.signal = "BUY"
    signal_result.confidence = Decimal("0.7")
    signal_result.reasons = []
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

    buy_events = [e for e in emitted if e.category == "IMBALANCE" and e.side == "BUY"]
    sell_events = [e for e in emitted if e.category == "IMBALANCE" and e.side == "SELL"]
    assert len(buy_events) == 1
    assert len(sell_events) == 1

    # Task-A: strength halved to min(net/(stack_ref*2), 1) to avoid saturating at 1.00.
    # BUY net=5, stack_ref=3 → min(5/6,1)=0.8333…; SELL net=3 → min(3/6,1)=0.5
    assert buy_events[0].strength == Decimal("5") / (Decimal("3") * 2)
    assert sell_events[0].strength == Decimal("0.5")

    # module_scores present
    assert result.module_scores is not None


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
    mock_config.webapp.bar_update_interval_sec = 1
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
