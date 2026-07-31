import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from tests.webapp.test_api import _make_mock_config, _make_mock_pipeline

from webapp import heatmap_replay_task as replay


MAIN = Path(__file__).resolve().parents[2] / "webapp" / "main.py"


def test_replay_sends_each_projection_and_sleeps_after_each(monkeypatch) -> None:
    projections = [SimpleNamespace(index=1), SimpleNamespace(index=2)]
    sleeps: list[float] = []
    sent: list[object] = []

    monkeypatch.setattr(replay, "iter_book_projections", lambda *args, **kwargs: iter(projections))

    async def run() -> None:
        async def send(projection) -> None:
            sent.append(projection)

        async def sleep(delay: float) -> None:
            sleeps.append(delay)

        await replay.heatmap_replay_loop(
            send,
            recording_dir=Path("recording"),
            interval_ms=125,
            sample_interval_ms=1000,
            sleep=sleep,
        )

    asyncio.run(run())
    assert sent == projections
    assert sleeps == [0.125, 0.125]


def test_replay_isolates_send_exception_and_continues(monkeypatch) -> None:
    projections = [SimpleNamespace(index=1), SimpleNamespace(index=2)]
    sent: list[object] = []
    sleeps: list[float] = []
    monkeypatch.setattr(replay, "iter_book_projections", lambda *args, **kwargs: iter(projections))

    async def run() -> None:
        async def send(projection) -> None:
            sent.append(projection)
            if projection.index == 1:
                raise RuntimeError("send failed")

        async def sleep(delay: float) -> None:
            sleeps.append(delay)

        await replay.heatmap_replay_loop(
            send,
            recording_dir=Path("recording"),
            interval_ms=100,
            sample_interval_ms=1000,
            sleep=sleep,
        )

    asyncio.run(run())
    assert sent == projections
    assert sleeps == [0.1, 0.1]


def test_replay_reraises_cancelled_error(monkeypatch) -> None:
    monkeypatch.setattr(
        replay,
        "iter_book_projections",
        lambda *args, **kwargs: iter([SimpleNamespace(index=1)]),
    )

    async def run() -> None:
        async def send(projection) -> None:
            raise asyncio.CancelledError

        async def sleep(delay: float) -> None:
            raise AssertionError("sleep must not run after cancellation")

        with pytest.raises(asyncio.CancelledError):
            await replay.heatmap_replay_loop(
                send,
                recording_dir=Path("recording"),
                interval_ms=100,
                sample_interval_ms=1000,
                sleep=sleep,
            )

    asyncio.run(run())


def test_replay_rejects_non_positive_interval() -> None:
    async def run() -> None:
        with pytest.raises(ValueError, match="interval_ms must be > 0"):
            await replay.heatmap_replay_loop(
                lambda projection: None,
                recording_dir=Path("recording"),
                interval_ms=0,
                sample_interval_ms=1000,
            )

    asyncio.run(run())


def test_replay_passes_source_arguments(monkeypatch) -> None:
    calls: list[tuple[tuple, dict]] = []
    projection = SimpleNamespace(index=1)

    def source(*args, **kwargs):
        calls.append((args, kwargs))
        return iter([projection])

    monkeypatch.setattr(replay, "iter_book_projections", source)

    async def run() -> None:
        async def send(value) -> None:
            assert value is projection

        async def sleep(delay: float) -> None:
            pass

        recording_dir = Path("recording")
        await replay.heatmap_replay_loop(
            send,
            recording_dir=recording_dir,
            interval_ms=100,
            sample_interval_ms=250,
            depth_levels=7,
            symbol="ETHUSDT",
            sleep=sleep,
        )

    asyncio.run(run())
    assert calls == [
        (
            (Path("recording"),),
            {
                "interval_ms": 250,
                "depth_levels": 7,
                "symbol": "ETHUSDT",
            },
        )
    ]


def test_replay_raises_when_no_projection(monkeypatch) -> None:
    monkeypatch.setattr(replay, "iter_book_projections", lambda *args, **kwargs: iter(()))

    async def run() -> None:
        with pytest.raises(RuntimeError, match="produced zero projections"):
            await replay.heatmap_replay_loop(
                lambda projection: None,
                recording_dir=Path("empty"),
                interval_ms=100,
                sample_interval_ms=1000,
            )

    asyncio.run(run())


def test_ensure_replay_source_uses_completed_segments(monkeypatch, tmp_path) -> None:
    class Reader:
        def __init__(self, recording_dir) -> None:
            assert recording_dir == tmp_path

        def segments(self):
            return [object()]

    monkeypatch.setattr(replay, "DepthHistoryReader", Reader)
    replay.ensure_replay_source(tmp_path)


def test_ensure_replay_source_rejects_empty_segments(monkeypatch, tmp_path) -> None:
    class Reader:
        def __init__(self, recording_dir) -> None:
            pass

        def segments(self):
            return []

    monkeypatch.setattr(replay, "DepthHistoryReader", Reader)
    with pytest.raises(RuntimeError, match="no completed segments"):
        replay.ensure_replay_source(tmp_path)


def test_live_supply_is_exclusive_for_both_heatmap_flag_values() -> None:
    source = MAIN.read_text(encoding="utf-8")
    assert "if heatmap_replay_enabled" in source
    assert "else asyncio.create_task(book_projection_pump.run())" in source
    assert "if config.replay.enabled and not heatmap_replay_enabled" not in source


def test_pipeline_replay_is_documented_as_non_heatmap_mode() -> None:
    source = MAIN.read_text(encoding="utf-8")
    assert 'if config.replay.enabled:' in source
    assert "book_projection_task = None" in source


def test_live_runtime_uses_live_pump_when_replay_flag_is_false(monkeypatch) -> None:
    mock_config = _make_mock_config()
    mock_config.replay.enabled = False
    mock_pipeline = _make_mock_pipeline()
    book_run = AsyncMock()
    replay_run = AsyncMock()
    monkeypatch.delenv("HEATMAP_REPLAY_ENABLED", raising=False)

    with patch("webapp.main.load_config", return_value=mock_config), \
         patch("webapp.main.load_profile", return_value=MagicMock()), \
         patch("webapp.main.LivePipeline") as MockPipeline, \
         patch("webapp.main.LatestBookProjectionPump.run", new=book_run), \
         patch("webapp.main.heatmap_replay_loop", new=replay_run), \
         patch("webapp.main.oi_polling_loop", new=AsyncMock()), \
         patch("webapp.main.hfm_quote_tail_loop", new=AsyncMock()):
        MockPipeline.from_config.return_value = mock_pipeline
        from webapp.main import app

        with TestClient(app) as client:
            assert client.get("/health").status_code == 200

    book_run.assert_awaited()
    replay_run.assert_not_awaited()


def test_live_runtime_uses_replay_task_when_replay_flag_is_true(monkeypatch) -> None:
    mock_config = _make_mock_config()
    mock_config.replay.enabled = False
    mock_pipeline = _make_mock_pipeline()
    book_run = AsyncMock()
    replay_run = AsyncMock()
    monkeypatch.setenv("HEATMAP_REPLAY_ENABLED", "true")

    with patch("webapp.main.load_config", return_value=mock_config), \
         patch("webapp.main.load_profile", return_value=MagicMock()), \
         patch("webapp.main.LivePipeline") as MockPipeline, \
         patch("webapp.main.ensure_replay_source", new=MagicMock()), \
         patch("webapp.main.LatestBookProjectionPump.run", new=book_run), \
         patch("webapp.main.heatmap_replay_loop", new=replay_run), \
         patch("webapp.main.oi_polling_loop", new=AsyncMock()), \
         patch("webapp.main.hfm_quote_tail_loop", new=AsyncMock()):
        MockPipeline.from_config.return_value = mock_pipeline
        from webapp.main import app

        with TestClient(app) as client:
            assert client.get("/health").status_code == 200

    replay_run.assert_awaited()
    book_run.assert_not_awaited()
