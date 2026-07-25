"""Tests for FastAPI endpoints (pipeline mocked)."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


def _make_mock_config():
    cfg = MagicMock()
    cfg.market.symbol = "BTCUSDT"
    cfg.market.bar_timeframe = "1m"
    cfg.webapp.host = "0.0.0.0"
    cfg.webapp.port = 8080
    cfg.webapp.depth_levels = 15
    cfg.webapp.flow_window_sec = 60
    cfg.webapp.alert_threshold = 0.85
    cfg.webapp.confluence.score_threshold = 40
    cfg.webapp.confluence.strength_threshold = 0.5
    cfg.webapp.oi_poll_interval_sec = 10
    cfg.webapp.tick_push_interval_ms = 50
    cfg.webapp.bar_update_interval_sec = 0.2
    cfg.monitor.enabled = False
    cfg.monitor.interval_sec = 5
    cfg.monitor.log_dir = "data/monitor"
    cfg.monitor.bar_missing_tolerance_sec = 90
    cfg.monitor.latency_yellow_ms = 2000
    cfg.monitor.latency_red_ms = 10000
    cfg.monitor.memory_yellow_mb = 900
    cfg.monitor.memory_red_mb = 1500
    cfg.monitor.window_min = 15
    cfg.monitor.reconnect_yellow = 1
    cfg.monitor.reconnect_red = 3
    cfg.monitor.gap_yellow = 1
    cfg.monitor.gap_red = 5
    cfg.monitor.exception_yellow = 1
    cfg.monitor.exception_red = 3
    cfg.replay.enabled = False
    cfg.signal.enabled = False
    cfg.database.duckdb_path = ":memory:"
    cfg.normalizer.exchange_profile = "binance"
    cfg._data = {"webapp": {"host": "0.0.0.0", "port": 8080}}
    return cfg


def _make_mock_pipeline():
    p = MagicMock()
    p.run_async = AsyncMock(return_value=None)
    p.on_trade = None
    p.on_candle = None
    p.on_analysis = None
    p.on_liquidation = None
    p.on_flow_event = None
    p.on_webapp_flow_event = None
    p.book_manager = None
    p.volume_ref_tracker = None
    p.cvd_calculator = None
    p.absorption_detector = None
    p._last_bar_close = None
    p._last_fp_bar = None
    p.storage_writer = None
    return p


def test_health_ok():
    mock_pipeline = _make_mock_pipeline()
    mock_config = _make_mock_config()

    with patch("webapp.main.load_config", return_value=mock_config), \
         patch("webapp.main.load_profile", return_value=MagicMock()), \
         patch("webapp.main.LivePipeline") as MockPipeline, \
         patch("webapp.main.oi_polling_loop", new=AsyncMock()):
        MockPipeline.from_config.return_value = mock_pipeline

        from webapp.main import app
        with TestClient(app) as client:
            resp = client.get("/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


def test_stats_ok():
    mock_pipeline = _make_mock_pipeline()
    mock_config = _make_mock_config()

    with patch("webapp.main.load_config", return_value=mock_config), \
         patch("webapp.main.load_profile", return_value=MagicMock()), \
         patch("webapp.main.LivePipeline") as MockPipeline, \
         patch("webapp.main.oi_polling_loop", new=AsyncMock()):
        MockPipeline.from_config.return_value = mock_pipeline

        from webapp.main import app
        with TestClient(app) as client:
            resp = client.get("/api/stats")

    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)


def test_config_ok():
    mock_pipeline = _make_mock_pipeline()
    mock_config = _make_mock_config()

    with patch("webapp.main.load_config", return_value=mock_config), \
         patch("webapp.main.load_profile", return_value=MagicMock()), \
         patch("webapp.main.LivePipeline") as MockPipeline, \
         patch("webapp.main.oi_polling_loop", new=AsyncMock()):
        MockPipeline.from_config.return_value = mock_pipeline

        from webapp.main import app
        with TestClient(app) as client:
            resp = client.get("/api/config")

    assert resp.status_code == 200
    data = resp.json()
    assert "webapp" in data


def test_candle_history_returns_oldest_first():
    mock_pipeline = _make_mock_pipeline()
    mock_config = _make_mock_config()
    newest_first = [
        {"bar_time": "2026-07-21 00:01:00", "timeframe": "1m", "open": "101", "high": "102", "low": "100", "close": "101", "volume": "2", "delta": "1", "cvd": "3"},
        {"bar_time": "2026-07-21 00:00:00", "timeframe": "1m", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1", "delta": "1", "cvd": "2"},
    ]

    with patch("webapp.main.load_config", return_value=mock_config), \
         patch("webapp.main.load_profile", return_value=MagicMock()), \
         patch("webapp.main.LivePipeline") as MockPipeline, \
         patch("webapp.main.query_candles", return_value=newest_first) as history_query, \
         patch("webapp.main.oi_polling_loop", new=AsyncMock()):
        MockPipeline.from_config.return_value = mock_pipeline
        from webapp.main import app
        with TestClient(app) as client:
            response = client.get("/api/history/candles?limit=999")

    assert response.status_code == 200
    candles = response.json()["candles"]
    assert candles[0]["bar_time"] == "2026-07-21 00:00:00"
    assert candles[1]["bar_time"] == "2026-07-21 00:01:00"
    history_query.assert_called_once_with(":memory:", "BTCUSDT", 300, "1m")


def test_flow_response_history_returns_oldest_first():
    mock_pipeline = _make_mock_pipeline()
    mock_config = _make_mock_config()
    newest_first = [
        {"event_time": "2026-07-21T00:01:00+00:00", "window_sec": "30", "state": "BUY_TRAPPED"},
        {"event_time": "2026-07-21T00:00:00+00:00", "window_sec": "30", "state": "BUY_STALLED"},
    ]

    with patch("webapp.main.load_config", return_value=mock_config), \
         patch("webapp.main.load_profile", return_value=MagicMock()), \
         patch("webapp.main.LivePipeline") as MockPipeline, \
         patch("webapp.main.query_flow_response_events", return_value=newest_first) as history_query, \
         patch("webapp.main.oi_polling_loop", new=AsyncMock()):
        MockPipeline.from_config.return_value = mock_pipeline
        from webapp.main import app
        with TestClient(app) as client:
            response = client.get("/api/history/flow-response?limit=99999")

    assert response.status_code == 200
    events = response.json()["events"]
    assert events[0]["state"] == "BUY_STALLED"
    assert events[1]["state"] == "BUY_TRAPPED"
    history_query.assert_called_once_with(":memory:", "BTCUSDT", 10000)


def test_open_interest_history_returns_oldest_first():
    mock_pipeline = _make_mock_pipeline()
    mock_config = _make_mock_config()
    newest_first = [
        {"source_time": "2026-07-22T00:00:20+00:00", "open_interest": "102"},
        {"source_time": "2026-07-22T00:00:10+00:00", "open_interest": "101"},
    ]

    with patch("webapp.main.load_config", return_value=mock_config), \
         patch("webapp.main.load_profile", return_value=MagicMock()), \
         patch("webapp.main.LivePipeline") as MockPipeline, \
         patch("webapp.main.query_open_interest_samples", return_value=newest_first) as history_query, \
         patch("webapp.main.oi_polling_loop", new=AsyncMock()):
        MockPipeline.from_config.return_value = mock_pipeline
        from webapp.main import app
        with TestClient(app) as client:
            response = client.get("/api/history/open-interest?limit=99999")

    assert response.status_code == 200
    samples = response.json()["samples"]
    assert [row["open_interest"] for row in samples] == ["101", "102"]
    assert history_query.call_count == 2  # startup preload + REST response
    history_query.assert_called_with(":memory:", "BTCUSDT", 5000)


def test_replay_does_not_start_live_oi_poller():
    mock_pipeline = _make_mock_pipeline()
    mock_pipeline.run = MagicMock(return_value=None)
    mock_config = _make_mock_config()
    mock_config.replay.enabled = True
    mock_config.replay.data_path = "recording.jsonl"
    oi_poller = AsyncMock()

    with patch("webapp.main.load_config", return_value=mock_config), \
         patch("webapp.main.load_profile", return_value=MagicMock()), \
         patch("webapp.main.ReplayPipeline") as MockPipeline, \
         patch("webapp.main.oi_polling_loop", new=oi_poller):
        MockPipeline.from_config.return_value = mock_pipeline
        from webapp.main import app
        with TestClient(app) as client:
            response = client.get("/api/history/open-interest")

    assert response.status_code == 200
    assert response.json() == {"samples": []}
    oi_poller.assert_not_called()


def test_combined_context_history_returns_oldest_first_and_filters_5m():
    mock_pipeline = _make_mock_pipeline()
    mock_config = _make_mock_config()
    newest_first = [
        {"event_time": "2026-07-24T00:10:00+00:00", "context_code": "P8_BUILDING"},
        {"event_time": "2026-07-24T00:05:00+00:00", "context_code": "P1_BUILDING"},
    ]

    with patch("webapp.main.load_config", return_value=mock_config), \
         patch("webapp.main.load_profile", return_value=MagicMock()), \
         patch("webapp.main.LivePipeline") as MockPipeline, \
         patch("webapp.main.query_open_interest_samples", return_value=[]), \
         patch("webapp.main.query_combined_context_events", return_value=newest_first) as query, \
         patch("webapp.main.oi_polling_loop", new=AsyncMock()), \
         patch("webapp.main.hfm_quote_tail_loop", new=AsyncMock()):
        MockPipeline.from_config.return_value = mock_pipeline
        from webapp.main import app
        with TestClient(app) as client:
            response = client.get("/api/history/combined-context?timeframe=5m&limit=99999")

    assert response.status_code == 200
    assert [row["context_code"] for row in response.json()["events"]] == [
        "P1_BUILDING", "P8_BUILDING",
    ]
    query.assert_called_once_with(":memory:", "BTCUSDT", "5m", 5000)


def test_hfm_context_outcome_history_returns_spread_inclusive_records():
    mock_pipeline = _make_mock_pipeline()
    mock_config = _make_mock_config()
    newest_first = [{
        "event_time": "2026-07-24T00:05:00+00:00",
        "horizon_sec": "180",
        "long_net_usd": "3.00000000",
        "short_net_usd": "-7.00000000",
    }]

    with patch("webapp.main.load_config", return_value=mock_config), \
         patch("webapp.main.load_profile", return_value=MagicMock()), \
         patch("webapp.main.LivePipeline") as MockPipeline, \
         patch("webapp.main.query_open_interest_samples", return_value=[]), \
         patch("webapp.main.query_hfm_context_outcomes", return_value=newest_first) as query, \
         patch("webapp.main.oi_polling_loop", new=AsyncMock()), \
         patch("webapp.main.hfm_quote_tail_loop", new=AsyncMock()):
        MockPipeline.from_config.return_value = mock_pipeline
        from webapp.main import app
        with TestClient(app) as client:
            response = client.get("/api/history/hfm-context-outcomes?timeframe=5m&limit=99999")

    assert response.status_code == 200
    assert response.json()["outcomes"][0]["long_net_usd"] == "3.00000000"
    query.assert_called_once_with(":memory:", "BTCUSDT", "5m", 10000)


def test_api_health_unknown_before_first_sample():
    """monitor 無効 (health loop 未稼働) では UNKNOWN を返す。"""
    mock_pipeline = _make_mock_pipeline()
    mock_config = _make_mock_config()

    with patch("webapp.main.load_config", return_value=mock_config), \
         patch("webapp.main.load_profile", return_value=MagicMock()), \
         patch("webapp.main.LivePipeline") as MockPipeline, \
         patch("webapp.main.oi_polling_loop", new=AsyncMock()):
        MockPipeline.from_config.return_value = mock_pipeline

        from webapp.main import app
        with TestClient(app) as client:
            resp = client.get("/api/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["state"] == "UNKNOWN"
    assert data["anomalies_today"] == 0


def test_api_health_returns_latest_report():
    """health loop が格納した最新レポートをそのまま返す。"""
    mock_pipeline = _make_mock_pipeline()
    mock_config = _make_mock_config()

    with patch("webapp.main.load_config", return_value=mock_config), \
         patch("webapp.main.load_profile", return_value=MagicMock()), \
         patch("webapp.main.LivePipeline") as MockPipeline, \
         patch("webapp.main.oi_polling_loop", new=AsyncMock()):
        MockPipeline.from_config.return_value = mock_pipeline

        from webapp.main import app
        with TestClient(app) as client:
            report = {"state": "YELLOW",
                      "checks": {"latency": {"level": "YELLOW", "value": "2500",
                                             "detail": "event lag 2500ms"}},
                      "anomalies_today": 1}
            app.state.health_report = report
            resp = client.get("/api/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["state"] == "YELLOW"
    assert data["checks"]["latency"]["value"] == "2500"


def test_replay_startup_uses_ensure_future_wiring_guard():
    """回帰ガード: replay 起動は run_in_executor の Future を ensure_future で包む。

    asyncio.create_task(Future) は TypeError で lifespan 起動が失敗する
    (v3.6.3 以前に存在した実バグ)。ソース配線を直接検証する。
    """
    import inspect
    import webapp.main as m

    src = inspect.getsource(m)
    assert "asyncio.ensure_future(" in src
    assert "asyncio.create_task(\n            loop.run_in_executor" not in src


def test_stats_includes_book_resync_counters():
    from datetime import datetime, timezone
    from decimal import Decimal
    from src.orderflow.orderbook import BookLevel, OrderBookStateManager, OrderBookUpdate
    from src.pipeline import BookResyncCounters

    mock_pipeline = _make_mock_pipeline()
    book = OrderBookStateManager("BTCUSDT")
    book.apply(OrderBookUpdate(
        event_time=datetime(2026, 1, 1, tzinfo=timezone.utc), symbol="BTCUSDT",
        update_type="SNAPSHOT", first_update_id=None, final_update_id=100,
        bids=(BookLevel(Decimal("50000"), Decimal("1")),),
        asks=(BookLevel(Decimal("50001"), Decimal("1")),),
    ))
    mock_pipeline.book_manager = book
    mock_pipeline.book_resync_counters = BookResyncCounters(resyncs=2, fetch_failures=3)
    mock_config = _make_mock_config()

    with patch("webapp.main.load_config", return_value=mock_config), \
         patch("webapp.main.load_profile", return_value=MagicMock()), \
         patch("webapp.main.LivePipeline") as MockPipeline, \
         patch("webapp.main.oi_polling_loop", new=AsyncMock()):
        MockPipeline.from_config.return_value = mock_pipeline
        from webapp.main import app
        with TestClient(app) as client:
            data = client.get("/api/stats").json()

    assert data["book_synced"] is True
    assert data["book_resyncs"] == 2
    assert data["book_snapshot_fetch_failures"] == 3
