from datetime import datetime, timedelta, timezone

import pytest

from src.orderflow.episode_dataset import EpisodeOutcomeEvaluator, PriceObservation
from src.orderflow.orderflow_episode import EpisodeStage, FlowObservation, OrderFlowEpisodeBuilder

UTC = timezone.utc


def obs(at, state, price):
    return FlowObservation(at, "BTCUSDT", 60, state, "BUY", 0.4, 0.7, 1.0, 0.0, price)


def make_episode():
    start = datetime(2026, 7, 25, tzinfo=UTC)
    builder = OrderFlowEpisodeBuilder("BTCUSDT", 60)
    builder.process(obs(start, "BUY_EFFECTIVE", 100.0))
    builder.process(obs(start + timedelta(seconds=30), "BUY_STALLED", 100.0))
    builder.process(obs(start + timedelta(seconds=60), "BUY_STALLED", 100.0))
    emitted = builder.process(obs(start + timedelta(seconds=90), "BUY_EFFECTIVE", 101.0))
    assert emitted
    return emitted[0], start


def test_labels_are_causal_and_capture_path_extremes():
    episode, start = make_episode()
    prices = [
        PriceObservation(start + timedelta(seconds=value), price)
        for value, price in ((0, 100.0), (60, 99.5), (120, 100.5), (240, 100.2), (300, 101.0), (480, 100.4), (600, 100.25))
    ]
    labels = EpisodeOutcomeEvaluator((300, 600), max_data_gap_sec=180).evaluate((episode,), prices)
    ok = [label for label in labels if label.status == "OK" and label.checkpoint_index == 0]
    assert len(ok) == 2
    assert ok[0].forward_return_bps == pytest.approx(100.0)
    assert ok[0].max_down_bps == pytest.approx(-50.0)
    assert ok[0].pressure_signed_return_bps == pytest.approx(100.0)
    assert ok[0].episode_terminal_stage is EpisodeStage.AGGRESSOR_BREAKTHROUGH


def test_missing_horizon_and_data_gap_are_not_filled():
    episode, start = make_episode()
    prices = [
        PriceObservation(start, 100.0),
        PriceObservation(start + timedelta(seconds=10), 100.1),
        PriceObservation(start + timedelta(seconds=300), 101.0),
    ]
    labels = EpisodeOutcomeEvaluator((300, 600), max_data_gap_sec=30).evaluate((episode,), prices)
    statuses = {label.horizon_sec: label.status for label in labels if label.checkpoint_index == 0}
    assert statuses[300] == "DATA_GAP"
    assert statuses[600] == "MISSING_OUTCOME"


def test_prices_must_be_chronological_and_positive():
    evaluator = EpisodeOutcomeEvaluator((300,))
    with pytest.raises(ValueError, match="chronological"):
        evaluator._ordered_prices([
            PriceObservation(datetime(2026, 7, 25, 0, 1, tzinfo=UTC), 100.0),
            PriceObservation(datetime(2026, 7, 25, tzinfo=UTC), 100.0),
        ])
    with pytest.raises(ValueError, match="positive"):
        evaluator._ordered_prices([PriceObservation(datetime(2026, 7, 25, tzinfo=UTC), 0.0)])
