from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.orderflow.cvd import Trade
from src.strategy_engine.ingestion.condition_adapter import (
    RELATION_CODES,
    IngestionAdapter,
)
from src.strategy_engine.ingestion.market_state import (
    MarketStateSnapshot,
    TimeSample,
)
from src.strategy_engine.ingestion.session_vwap import SessionVwapSeed
from src.strategy_engine.ingestion.snapshot_producer import SnapshotProducer


BASE = datetime(2026, 7, 27, tzinfo=timezone.utc)
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _ns(value: datetime) -> int:
    delta = value - EPOCH
    return (
        delta.days * 86_400 * 1_000_000_000
        + delta.seconds * 1_000_000_000
        + delta.microseconds * 1_000
    )


def _trade(
    seconds: float,
    price: str,
    quantity: str,
    trade_id: int,
    *,
    day: int = 0,
) -> Trade:
    return Trade(
        trade_id=trade_id,
        event_time=BASE + timedelta(days=day, seconds=seconds),
        symbol="BTCUSDT",
        price=Decimal(price),
        quantity=Decimal(quantity),
        side="BUY",
    )


def test_trade_level_session_vwap_emits_all_g03_materials() -> None:
    producer = SnapshotProducer("BTCUSDT")
    producer.observe_trade(_trade(0.2, "100", "1", 1))
    producer.observe_trade(_trade(2, "110", "3", 2))

    conditions = producer.to_conditions(
        engine_time_ns=2_000_000_000,
        source_time_ns=_ns(BASE + timedelta(seconds=2)),
        tick_size=Decimal("0.5"),
    )

    # (100*1 + 110*3) / 4 = 107.5; current price is 5 ticks above it.
    assert conditions["distance_to_session_vwap"] == Decimal("5")
    assert conditions["relation_to_session_vwap"] == RELATION_CODES["ABOVE"]
    assert conditions["distance_to_session_open_avwap"] == Decimal("5")
    assert (
        conditions["relation_to_session_open_avwap"]
        == RELATION_CODES["ABOVE"]
    )


def test_partial_session_and_future_aggregate_are_omitted() -> None:
    partial = SnapshotProducer("BTCUSDT")
    partial.observe_trade(_trade(3_600, "100", "1", 1))
    partial_conditions = partial.to_conditions(
        engine_time_ns=0,
        source_time_ns=_ns(BASE + timedelta(hours=1)),
        tick_size=Decimal("0.1"),
    )
    assert not any("vwap" in key for key in partial_conditions)

    producer = SnapshotProducer("BTCUSDT")
    producer.observe_trade(_trade(0.2, "100", "1", 1))
    producer.observe_trade(_trade(2, "110", "1", 2))
    before_second_trade = producer.build_market_state(
        engine_time_ns=1_000_000_000,
        source_time_ns=_ns(BASE + timedelta(seconds=1)),
        tick_size=Decimal("0.1"),
    )
    assert before_second_trade.session_vwap is None
    assert before_second_trade.session_open_avwap is None
    assert not any(
        "vwap" in key
        for key in IngestionAdapter().to_conditions(before_second_trade)
    )


def test_partial_session_exposes_display_value_without_strategy_material() -> None:
    producer = SnapshotProducer("BTCUSDT")
    producer.observe_trade(_trade(3_600, "100", "1", 1))
    producer.observe_trade(_trade(3_601, "110", "3", 2))

    state = producer.build_market_state(
        engine_time_ns=0,
        source_time_ns=_ns(BASE + timedelta(seconds=3_601)),
        tick_size=Decimal("0.1"),
    )

    assert state.session_vwap is None
    assert producer._session_vwap.session_complete is False
    assert producer._session_vwap.current_value == Decimal("107.5")


def test_utc_day_reset_discards_prior_session_and_rechecks_coverage() -> None:
    producer = SnapshotProducer("BTCUSDT")
    producer.observe_trade(_trade(0.2, "100", "1", 1))
    producer.observe_trade(_trade(0.2, "200", "2", 2, day=1))

    next_day = producer.build_market_state(
        engine_time_ns=0,
        source_time_ns=_ns(BASE + timedelta(days=1, seconds=0.2)),
        tick_size=Decimal("0.1"),
    )
    assert next_day.session_vwap == Decimal("200")
    assert next_day.session_open_avwap == Decimal("200")

    producer.observe_trade(_trade(43_200, "300", "1", 3, day=2))
    incomplete_day = producer.to_conditions(
        engine_time_ns=0,
        source_time_ns=_ns(BASE + timedelta(days=2, hours=12)),
        tick_size=Decimal("0.1"),
    )
    assert not any("vwap" in key for key in incomplete_day)


def test_seed_continues_exact_aggregate_and_rejects_boundary_duplicate() -> None:
    producer = SnapshotProducer("BTCUSDT")
    seed = SessionVwapSeed(
        symbol="BTCUSDT",
        session_start=BASE,
        first_event_time=BASE + timedelta(seconds=0.2),
        last_event_time=BASE + timedelta(seconds=2),
        notional=Decimal("430"),
        volume=Decimal("4"),
        trade_count=2,
        last_trade_id=2,
    )
    assert producer.seed_session_vwap(seed) == 2
    producer.observe_trade(_trade(2, "999", "1", 2))
    producer.observe_trade(_trade(3, "120", "2", 3))

    state = producer.build_market_state(
        engine_time_ns=0,
        source_time_ns=_ns(BASE + timedelta(seconds=3)),
        tick_size=Decimal("0.1"),
    )
    assert state.session_vwap == Decimal("670") / Decimal("6")
    assert state.session_open_avwap == state.session_vwap


def test_relation_encoding_and_market_state_validation() -> None:
    state = MarketStateSnapshot(
        engine_time_ns=5_000_000_000,
        price_samples=(
            TimeSample(engine_time_ns=5_000_000_000, value=Decimal("99")),
        ),
        tick_size=Decimal("0.5"),
        session_vwap=Decimal("100"),
        session_open_avwap=Decimal("99"),
    )
    conditions = IngestionAdapter().to_conditions(state)
    assert conditions["distance_to_session_vwap"] == Decimal("-2")
    assert conditions["relation_to_session_vwap"] == RELATION_CODES["BELOW"]
    assert conditions["distance_to_session_open_avwap"] == Decimal("0")
    assert conditions["relation_to_session_open_avwap"] == RELATION_CODES["AT"]

    with pytest.raises(ValueError):
        MarketStateSnapshot(engine_time_ns=0, session_vwap=Decimal("0"))
