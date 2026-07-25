from datetime import datetime, timedelta, timezone

import pytest

from src.orderflow.orderflow_episode import EpisodeStage, FlowObservation, OrderFlowEpisodeBuilder

UTC = timezone.utc


def observation(at, state, side="BUY", price=100.0):
    return FlowObservation(at, "BTCUSDT", 60, state, side, 0.4, 0.7, 1.2, 0.0, price)


def test_episode_tracks_stall_persistence_and_breakthrough():
    start = datetime(2026, 7, 25, tzinfo=UTC)
    builder = OrderFlowEpisodeBuilder("BTCUSDT", 60, max_gap_sec=120)
    assert builder.process(observation(start, "BUY_EFFECTIVE")) == ()
    assert builder.process(observation(start + timedelta(seconds=30), "BUY_STALLED")) == ()
    assert builder.process(observation(start + timedelta(seconds=60), "BUY_STALLED")) == ()
    emitted = builder.process(observation(start + timedelta(seconds=90), "BUY_EFFECTIVE", price=101.0))
    assert len(emitted) == 1
    assert emitted[0].stage is EpisodeStage.AGGRESSOR_BREAKTHROUGH
    assert emitted[0].resolved is True
    assert [point.stage for point in emitted[0].checkpoints] == [
        EpisodeStage.AGGRESSION, EpisodeStage.NON_RESPONSE,
        EpisodeStage.SUSTAINED_CONFLICT, EpisodeStage.AGGRESSOR_BREAKTHROUGH,
    ]


def test_trapped_resolves_and_opposite_side_starts_next_episode():
    start = datetime(2026, 7, 25, tzinfo=UTC)
    builder = OrderFlowEpisodeBuilder("BTCUSDT", 60)
    builder.process(observation(start, "BUY_EFFECTIVE"))
    emitted = builder.process(observation(start + timedelta(seconds=30), "BUY_TRAPPED", price=99.0))
    assert emitted[0].stage is EpisodeStage.DEFENDER_REVERSAL
    assert emitted[0].resolved is True
    assert builder.process(observation(start + timedelta(seconds=60), "SELL_EFFECTIVE", side="SELL")) == ()


def test_gap_invalidates_episode_and_starts_new_one():
    start = datetime(2026, 7, 25, tzinfo=UTC)
    builder = OrderFlowEpisodeBuilder("BTCUSDT", 60, max_gap_sec=30)
    builder.process(observation(start, "BUY_EFFECTIVE"))
    emitted = builder.process(observation(start + timedelta(seconds=31), "BUY_STALLED"))
    assert len(emitted) == 1
    assert emitted[0].stage is EpisodeStage.INVALIDATED
    assert builder.finalize()[0].stage is EpisodeStage.UNRESOLVED


def test_out_of_order_observation_is_rejected():
    start = datetime(2026, 7, 25, tzinfo=UTC)
    builder = OrderFlowEpisodeBuilder("BTCUSDT", 60)
    builder.process(observation(start, "BUY_EFFECTIVE"))
    with pytest.raises(ValueError, match="chronological"):
        builder.process(observation(start - timedelta(seconds=1), "BUY_STALLED"))


def test_max_episode_duration_invalidates_and_restarts_causally():
    start = datetime(2026, 7, 25, tzinfo=UTC)
    builder = OrderFlowEpisodeBuilder(
        "BTCUSDT", 60, max_gap_sec=120, max_episode_sec=60
    )
    builder.process(observation(start, "BUY_EFFECTIVE"))
    builder.process(observation(start + timedelta(seconds=60), "BUY_STALLED"))
    emitted = builder.process(observation(start + timedelta(seconds=61), "BUY_STALLED"))
    assert len(emitted) == 1
    assert emitted[0].stage is EpisodeStage.INVALIDATED
    assert emitted[0].end_time == start + timedelta(seconds=60)
    restarted = builder.finalize()[0]
    assert restarted.start_time == start + timedelta(seconds=61)
    assert restarted.stage is EpisodeStage.UNRESOLVED
