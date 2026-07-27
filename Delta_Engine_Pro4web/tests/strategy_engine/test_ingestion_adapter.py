"""I1-I6: IngestionAdapter (MarketStateSnapshot -> Tier A condition snapshot).

Verifies the window derivations (CVD, walls, OI), pass-through of pre-aggregated
counters, fail-closed behaviour on missing material, and an end-to-end run through
the Engine using adapter-produced conditions (Tier A routes only).
"""

from __future__ import annotations

from decimal import Decimal

from src.strategy_contract.enforcer import InstancePhase, OrderReadyHandoff
from src.strategy_engine.engine import StrategyEngine
from src.strategy_engine.ingestion.condition_adapter import (
    JOINT_STATE_CODES,
    IngestionAdapter,
)
from src.strategy_engine.ingestion.market_state import (
    NS_PER_SECOND,
    BookLevel,
    MarketStateSnapshot,
    TimeSample,
)

from ._helpers import (
    load_variant,
    make_event,
    real_arm_event,
    real_evaluator,
    terminal_event,
)

S = NS_PER_SECOND
_ADAPTER = IngestionAdapter()


def _ts(seconds: float, value) -> TimeSample:
    return TimeSample(engine_time_ns=int(seconds * S), value=Decimal(str(value)))


# --- I1: CVD window derivation ----------------------------------------------

def test_I1_cvd_change_and_slope():
    snap = MarketStateSnapshot(
        engine_time_ns=5 * S,
        cvd_samples=(_ts(0, 100), _ts(2.5, 95), _ts(5, 90)),
    )
    conditions = _ADAPTER.to_conditions(snap)
    assert conditions["cvd_change_5s"] == Decimal("-10")
    # slope per second across the 5s window: (90-100)/5 = -2
    assert conditions["cvd_slope_5s"] == Decimal("-2")


def test_I1_price_progress_uses_asof_source_time_and_tick_units():
    snap = MarketStateSnapshot(
        engine_time_ns=1 * S,
        price_samples=(_ts(0, 100), _ts(1, "99.6")),
        tick_size=Decimal("0.1"),
    )

    conditions = _ADAPTER.to_conditions(snap)

    assert conditions["upward_progress_ticks_1s"] == Decimal("0")
    assert conditions["downward_progress_ticks_1s"] == Decimal("4")
    assert "upward_progress_ticks_5s" not in conditions
    assert "downward_progress_ticks_5s" not in conditions


# --- I2: wall concentration + distance --------------------------------------

def test_I2_bid_wall_concentration_and_distance():
    snap = MarketStateSnapshot(
        engine_time_ns=0,
        bid_levels=(
            BookLevel(Decimal("100.0"), Decimal("5")),
            BookLevel(Decimal("99.9"), Decimal("50")),  # the wall
            BookLevel(Decimal("99.8"), Decimal("5")),
        ),
        ask_levels=(BookLevel(Decimal("100.1"), Decimal("1")),),
        tick_size=Decimal("0.1"),
    )
    conditions = _ADAPTER.to_conditions(snap)
    assert conditions["bid_wall_concentration_top10"] == Decimal("50") / Decimal("60")
    # distance from best bid (100.0) to the wall (99.9) is one tick
    assert conditions["distance_to_nearest_bid_wall"] == Decimal("1")


def test_I2_wall_tie_uses_nearest_candidate_and_crossed_book_omits_all():
    tied = MarketStateSnapshot(
        engine_time_ns=0,
        bid_levels=(
            BookLevel(Decimal("100.0"), Decimal("1")),
            BookLevel(Decimal("99.9"), Decimal("10")),
            BookLevel(Decimal("99.8"), Decimal("10")),
        ),
        ask_levels=(BookLevel(Decimal("100.1"), Decimal("2")),),
        tick_size=Decimal("0.1"),
    )
    tied_conditions = _ADAPTER.to_conditions(tied)
    assert tied_conditions["distance_to_nearest_bid_wall"] == Decimal("1")

    crossed = MarketStateSnapshot(
        engine_time_ns=0,
        bid_levels=(BookLevel(Decimal("100.1"), Decimal("1")),),
        ask_levels=(BookLevel(Decimal("100.0"), Decimal("1")),),
        tick_size=Decimal("0.1"),
    )
    assert not any("wall" in key for key in _ADAPTER.to_conditions(crossed))


def test_I2_off_grid_wall_distance_is_omitted_without_rounding():
    snap = MarketStateSnapshot(
        engine_time_ns=0,
        bid_levels=(
            BookLevel(Decimal("100.0"), Decimal("1")),
            BookLevel(Decimal("99.95"), Decimal("10")),
        ),
        ask_levels=(BookLevel(Decimal("100.1"), Decimal("1")),),
        tick_size=Decimal("0.1"),
    )
    conditions = _ADAPTER.to_conditions(snap)
    assert "bid_wall_concentration_top10" in conditions
    assert "distance_to_nearest_bid_wall" not in conditions


# --- I3: OI change / pct / joint state --------------------------------------

def test_I3_open_interest_change_pct_and_joint_state():
    snap = MarketStateSnapshot(
        engine_time_ns=300 * S,
        oi_samples=(_ts(0, 1000), _ts(300, 950)),
        price_samples=(_ts(0, 100), _ts(300, 99)),
    )
    conditions = _ADAPTER.to_conditions(snap)
    assert conditions["open_interest_change_5m"] == Decimal("-50")
    assert conditions["open_interest_pct_change_5m"] == Decimal("-5")
    # price down + OI down
    assert conditions["price_oi_joint_state_5m"] == JOINT_STATE_CODES["PRICE_DOWN_OI_DOWN"]


# --- I4: pre-aggregated pass-through -----------------------------------------

def test_I4_pre_aggregated_pass_through():
    snap = MarketStateSnapshot(
        engine_time_ns=0,
        pre_aggregated={
            "buy_no_progress_ratio_1s": Decimal("0.9"),
            "downward_progress_ticks_1s": Decimal("4"),
            "bid_refresh_count_1s": Decimal("2"),
            "bid_pull_ratio_1s": Decimal("0.3"),
        },
    )
    conditions = _ADAPTER.to_conditions(snap)
    assert conditions["buy_no_progress_ratio_1s"] == Decimal("0.9")
    assert conditions["downward_progress_ticks_1s"] == Decimal("4")
    assert conditions["bid_refresh_count_1s"] == Decimal("2")
    assert conditions["bid_pull_ratio_1s"] == Decimal("0.3")


# --- I5: fail-closed on missing / insufficient material ----------------------

def test_I5_empty_snapshot_emits_nothing():
    conditions = _ADAPTER.to_conditions(MarketStateSnapshot(engine_time_ns=0))
    assert conditions == {}


def test_I5_single_cvd_sample_has_no_change_or_slope():
    snap = MarketStateSnapshot(engine_time_ns=5 * S, cvd_samples=(_ts(5, 90),))
    conditions = _ADAPTER.to_conditions(snap)
    assert "cvd_change_5s" not in conditions
    assert "cvd_slope_5s" not in conditions


def test_I5_zero_base_oi_skips_pct_change():
    snap = MarketStateSnapshot(
        engine_time_ns=300 * S,
        oi_samples=(_ts(0, 0), _ts(300, 10)),
    )
    conditions = _ADAPTER.to_conditions(snap)
    assert conditions["open_interest_change_5m"] == Decimal("10")
    assert "open_interest_pct_change_5m" not in conditions  # base 0 -> skipped


# --- I6: end-to-end through the Engine with adapter-produced conditions -------

def _advance_events_from_adapter():
    # E01: CVD fell 6 over 5s -> cvd_change_5s = -6 (<= -5).
    e1 = _ADAPTER.to_conditions(
        MarketStateSnapshot(engine_time_ns=5 * S, cvd_samples=(_ts(0, 0), _ts(5, -6)))
    )
    # E02: no upward progress ratio (pre-aggregated).
    e2 = _ADAPTER.to_conditions(
        MarketStateSnapshot(
            engine_time_ns=0,
            pre_aggregated={"buy_no_progress_ratio_1s": Decimal("0.9")},
        )
    )
    # E03: price breaking down (pre-aggregated).
    e3 = _ADAPTER.to_conditions(
        MarketStateSnapshot(
            engine_time_ns=0,
            pre_aggregated={"downward_progress_ticks_1s": Decimal("4")},
        )
    )
    # E04: fresh OI decrease -> open_interest_change_5m < 0.
    e4 = _ADAPTER.to_conditions(
        MarketStateSnapshot(
            engine_time_ns=300 * S, oi_samples=(_ts(0, 1000), _ts(300, 990))
        )
    )
    snapshots = [e1, e2, e3, e4]
    return [
        make_event(
            f"E0{i}",
            source_event_id=f"adv{i}",
            source_s=float(i),
            engine_ns=i * 1_000_000,
            conditions=snapshots[i - 1],
        )
        for i in range(1, 5)
    ]


def test_I6_engine_full_path_with_adapter_conditions():
    engine = StrategyEngine(
        load_variant(), observation_instance_id="ING-1", evaluator=real_evaluator()
    )
    report = engine.run(
        [real_arm_event(), *_advance_events_from_adapter(), terminal_event()]
    )
    assert all(d.step.accepted for d in report.decisions), [
        (d.edge_id, d.step.reason) for d in report.decisions if not d.step.accepted
    ]
    assert engine.phase is InstancePhase.TERMINAL
    assert len(report.handoffs) == 1
    assert isinstance(report.handoffs[0], OrderReadyHandoff)
    assert report.handoffs[0].direction == "SHORT_READY"
    assert report.order_intents == 0
