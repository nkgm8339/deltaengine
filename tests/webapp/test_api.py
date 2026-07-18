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
    cfg.webapp.bar_update_interval_sec = 1
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
    p.on_webapp_flow_event = None
    p.book_manager = None
    p.volume_ref_tracker = None
    p.cvd_calculator = None
    p.absorption_detector = None
    p._last_bar_close = None
    p._last_fp_bar = None
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
