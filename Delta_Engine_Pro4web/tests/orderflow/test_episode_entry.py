from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from src.orderflow.episode_dataset import PriceObservation
from src.orderflow.episode_entry import (
    ATTACK_ENTRY,
    PERSIST_ENTRY,
    RESOLUTION_ENTRY,
    EpisodeEntryPathEvaluator,
    extract_entry_candidates,
    purge_overlapping_candidates,
)
from src.orderflow.orderflow_episode import (
    EpisodeStage,
    FlowObservation,
    OrderFlowEpisodeBuilder,
)

UTC = timezone.utc


def observation(at, state, side="BUY", price=100.0):
    return FlowObservation(
        at, "BTCUSDT", 60, state, side, 0.4, 0.7, 1.2, 0.0, price
    )


def resolved_episode(*, terminal="BUY_EFFECTIVE", terminal_price=100.0):
    start = datetime(2026, 7, 25, tzinfo=UTC)
    builder = OrderFlowEpisodeBuilder("BTCUSDT", 60)
    builder.process(observation(start, "BUY_EFFECTIVE", price=100.0))
    builder.process(
        observation(start + timedelta(seconds=30), "BUY_STALLED", price=99.5)
    )
    builder.process(
        observation(start + timedelta(seconds=60), "BUY_STALLED", price=99.7)
    )
    emitted = builder.process(
        observation(
            start + timedelta(seconds=90), terminal, price=terminal_price
        )
    )
    assert emitted
    return emitted[0], start


def test_extracts_ordered_attack_persist_and_breakthrough_without_single_state_entry():
    episode, _ = resolved_episode()
    candidates = extract_entry_candidates((episode,))
    assert [value.candidate_type for value in candidates] == [
        ATTACK_ENTRY,
        PERSIST_ENTRY,
        RESOLUTION_ENTRY,
    ]
    assert candidates[0].trade_side == "BUY"
    assert candidates[1].entry_stage is EpisodeStage.SUSTAINED_CONFLICT
    assert candidates[2].entry_stage is EpisodeStage.AGGRESSOR_BREAKTHROUGH
    assert candidates[2].trade_side == "BUY"
    assert candidates[2].invalidation_price == pytest.approx(99.5)


def test_defender_reversal_flips_trade_side():
    episode, _ = resolved_episode(terminal="BUY_TRAPPED", terminal_price=99.0)
    resolution = [
        value
        for value in extract_entry_candidates((episode,))
        if value.candidate_type == RESOLUTION_ENTRY
    ][0]
    assert resolution.entry_stage is EpisodeStage.DEFENDER_REVERSAL
    assert resolution.pressure_side == "BUY"
    assert resolution.trade_side == "SELL"
    assert resolution.invalidation_price == pytest.approx(99.7)


def test_attack_candidate_is_not_filtered_by_later_invalidation():
    start = datetime(2026, 7, 25, tzinfo=UTC)
    builder = OrderFlowEpisodeBuilder("BTCUSDT", 60)
    builder.process(observation(start, "BUY_EFFECTIVE"))
    emitted = builder.process(
        observation(start + timedelta(seconds=30), "SELL_EFFECTIVE", side="SELL")
    )
    candidates = extract_entry_candidates(emitted)
    assert [value.candidate_type for value in candidates] == [ATTACK_ENTRY]
    assert candidates[0].episode_terminal_stage is EpisodeStage.INVALIDATED


def test_path_evaluator_reports_cost_hurdle_order_and_price_invalidation():
    episode, start = resolved_episode()
    resolution = [
        value
        for value in extract_entry_candidates((episode,))
        if value.candidate_type == RESOLUTION_ENTRY
    ][0]
    prices = [
        PriceObservation(start + timedelta(seconds=90), 100.0),
        PriceObservation(start + timedelta(seconds=100), 100.25),
        PriceObservation(start + timedelta(seconds=150), 99.4),
        PriceObservation(start + timedelta(seconds=390), 100.1),
    ]
    outcome = EpisodeEntryPathEvaluator(
        (300,), proxy_cost_usd=0.2, max_data_gap_sec=300
    ).evaluate((resolution,), prices)[0]
    assert outcome.status == "OK"
    assert outcome.signed_return_bps == pytest.approx(10.0)
    assert outcome.proxy_cost_bps == pytest.approx(20.0)
    assert outcome.proxy_net_return_bps == pytest.approx(-10.0)
    assert outcome.mfe_bps == pytest.approx(25.0)
    assert outcome.mae_bps == pytest.approx(-60.0)
    assert outcome.hurdle_order == "FAVORABLE_FIRST"
    assert outcome.price_invalidation_time == start + timedelta(seconds=150)
    assert outcome.invalidation_before_favorable is False
    assert outcome.rule_exit_reason == "PRICE_INVALIDATION"
    assert outcome.rule_signed_return_bps == pytest.approx(-60.0)
    assert outcome.rule_proxy_net_return_bps == pytest.approx(-80.0)


def test_path_evaluator_reports_adverse_hurdle_first():
    episode, start = resolved_episode()
    resolution = [
        value
        for value in extract_entry_candidates((episode,))
        if value.candidate_type == RESOLUTION_ENTRY
    ][0]
    prices = [
        PriceObservation(start + timedelta(seconds=90), 100.0),
        PriceObservation(start + timedelta(seconds=100), 99.4),
        PriceObservation(start + timedelta(seconds=120), 100.3),
        PriceObservation(start + timedelta(seconds=390), 100.0),
    ]
    outcome = EpisodeEntryPathEvaluator(
        (300,), proxy_cost_usd=0.2, max_data_gap_sec=300
    ).evaluate((resolution,), prices)[0]
    assert outcome.hurdle_order == "ADVERSE_FIRST"
    assert outcome.invalidation_before_favorable is True


def test_known_invalidation_reference_without_breach_is_false_not_missing():
    episode, start = resolved_episode()
    resolution = [
        value
        for value in extract_entry_candidates((episode,))
        if value.candidate_type == RESOLUTION_ENTRY
    ][0]
    prices = [
        PriceObservation(start + timedelta(seconds=90), 100.0),
        PriceObservation(start + timedelta(seconds=120), 100.3),
        PriceObservation(start + timedelta(seconds=390), 100.1),
    ]
    outcome = EpisodeEntryPathEvaluator(
        (300,), proxy_cost_usd=0.2, max_data_gap_sec=300
    ).evaluate((resolution,), prices)[0]
    assert outcome.price_invalidation_time is None
    assert outcome.invalidation_before_favorable is False
    assert outcome.rule_exit_reason == "FIXED_HORIZON"
    assert outcome.rule_signed_return_bps == pytest.approx(10.0)
    assert outcome.rule_proxy_net_return_bps == pytest.approx(-10.0)


def test_purge_keeps_first_candidate_after_full_horizon():
    episode, start = resolved_episode()
    attack = [
        value
        for value in extract_entry_candidates((episode,))
        if value.candidate_type == ATTACK_ENTRY
    ][0]
    candidates = (
        attack,
        replace(attack, episode_id="overlap", entry_time=start + timedelta(seconds=599)),
        replace(attack, episode_id="boundary", entry_time=start + timedelta(seconds=600)),
    )
    purged = purge_overlapping_candidates(candidates, horizon_sec=600)
    assert [value.episode_id for value in purged] == [
        attack.episode_id,
        "boundary",
    ]
