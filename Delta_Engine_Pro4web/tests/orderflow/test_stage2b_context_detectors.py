from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.orderflow.cvd import Candle
from src.orderflow.hooks.config import ThresholdBook
from src.orderflow.hooks.detector_utils import make_candidate
from src.orderflow.hooks.flow_transition import FlowTransitionDetector
from src.orderflow.hooks.interaction import InteractionDetector
from src.orderflow.hooks.liquidation import LiquidationDetector
from src.orderflow.hooks.models import HookSide
from src.orderflow.hooks.open_interest import OpenInterestDetector
from src.orderflow.hooks.price_structure import PriceStructureDetector
from src.orderflow.hooks.runtime import HookRuntime


D = Decimal
T0 = datetime(2026, 7, 26, 8, 0, tzinfo=timezone.utc)


def _liquidation(side: str, when: datetime, price: str = "100", qty: str = "2"):
    return SimpleNamespace(
        event_time=when,
        symbol="BTCUSDT",
        side=side,
        price=D(price),
        quantity=D(qty),
    )


def test_interaction_detector_covers_c03_c09_without_mutating_legacy_absorption():
    detector = InteractionDetector()
    result = []
    result.extend(detector.observe_absorption(
        classification="BUY_ABSORPTION",
        symbol="BTCUSDT",
        anchor_price=D("100"),
        strength=D("0.8"),
        event_time=T0,
        received_time=T0,
        broken=True,
    ))
    result.extend(detector.observe_absorption(
        classification="SELL_ABSORPTION",
        symbol="BTCUSDT",
        anchor_price=D("101"),
        strength=D("0.7"),
        event_time=T0 + timedelta(seconds=1),
        received_time=T0 + timedelta(seconds=1),
        broken=True,
    ))
    result.extend(detector.observe_wall_trade(
        symbol="BTCUSDT",
        wall_side=HookSide.ASK,
        price=D("101"),
        before_quantity=D("10"),
        after_quantity=D("0"),
        aggressive_quantity=D("12"),
        event_time=T0 + timedelta(seconds=2),
        received_time=T0 + timedelta(seconds=2),
    ))
    result.extend(detector.observe_wall_trade(
        symbol="BTCUSDT",
        wall_side=HookSide.BID,
        price=D("100"),
        before_quantity=D("10"),
        after_quantity=D("0"),
        aggressive_quantity=D("12"),
        event_time=T0 + timedelta(seconds=3),
        received_time=T0 + timedelta(seconds=3),
    ))
    result.extend(detector.observe_liquidation_response(
        _liquidation("SELL", T0 + timedelta(seconds=4)),
        response_price=D("100.01"),
        received_time=T0 + timedelta(seconds=5),
        absorption_side=HookSide.BID,
    ))
    assert {"C03", "C04", "C05", "C06", "C07", "C08", "C09"} <= {
        item.hook_id for item in result
    }


def test_liquidation_detector_covers_e01_e06_and_rejects_out_of_order():
    detector = LiquidationDetector(
        cascade_window_ms=1_000,
        response_window_ms=100,
        exhaustion_gap_ms=200,
    )
    result = []
    result.extend(detector.process(
        _liquidation("SELL", T0),
        received_time=T0,
    ))
    result.extend(detector.process(
        _liquidation("BUY", T0 + timedelta(milliseconds=50)),
        received_time=T0 + timedelta(milliseconds=50),
    ))
    result.extend(detector.observe_price(
        symbol="BTCUSDT",
        price=D("100.01"),
        source_time=T0 + timedelta(milliseconds=500),
        received_time=T0 + timedelta(milliseconds=500),
    ))
    assert {"E01", "E02", "E03", "E04", "E05", "E06"} <= {
        item.hook_id for item in result
    }
    assert detector.process(
        _liquidation("SELL", T0 - timedelta(seconds=1)),
        received_time=T0 + timedelta(seconds=1),
    ) == ()
    assert detector.stale_events == 1


@pytest.mark.parametrize(
    ("oi", "price", "expected"),
    [
        ("1100", "101", "F01"),
        ("1100", "99", "F02"),
        ("900", "101", "F03"),
        ("900", "99", "F04"),
    ],
)
def test_open_interest_detector_four_quadrants_and_shock(oi, price, expected):
    detector = OpenInterestDetector(comparison_window_sec=60)
    assert detector.process(
        {"symbol": "BTCUSDT", "source_time": T0, "open_interest": D("1000")},
        price=D("100"),
        received_time=T0,
    ) == ()
    candidates = detector.process(
        {
            "symbol": "BTCUSDT",
            "source_time": T0 + timedelta(seconds=60),
            "open_interest": D(oi),
        },
        price=D(price),
        received_time=T0 + timedelta(seconds=60),
    )
    assert {item.hook_id for item in candidates} == {"F05", expected}


def _candle(index: int, *, high: str, low: str, close: str) -> Candle:
    return Candle(
        bar_time=T0 + timedelta(minutes=index),
        symbol="BTCUSDT",
        timeframe="1m",
        open=D("100"),
        high=D(high),
        low=D(low),
        close=D(close),
        volume=D("10"),
        delta=D("0"),
        cvd=D("0"),
    )


def test_price_structure_closed_bars_cover_g01_g11_and_failed_breaks():
    detector = PriceStructureDetector(
        lookback_bars=10,
        timeframe_sec=60,
        round_increment=D("50"),
        volume_node_bin_size=D("1"),
    )
    result = []
    for index, candle in enumerate(
        (
            _candle(0, high="101", low="99", close="100"),
            _candle(1, high="102", low="98", close="100"),
            _candle(2, high="101", low="99", close="100"),
        )
    ):
        result.extend(detector.process(
            candle,
            received_time=T0 + timedelta(minutes=index, seconds=60),
        ))
    assert {f"G{index:02d}" for index in range(1, 12)} <= {
        item.hook_id for item in result
    }


def _flow(window: int, state: str, when: datetime):
    return SimpleNamespace(
        event_time=when,
        symbol="BTCUSDT",
        window_sec=window,
        state=SimpleNamespace(value=state),
        last_price=D("100"),
    )


def test_flow_transition_detector_covers_d06_d08_and_stale_suppression():
    detector = FlowTransitionDetector(min_aligned_windows=2)
    initial = detector.process(
        (
            _flow(60, "BUY_EFFECTIVE", T0),
            _flow(180, "BUY_EFFECTIVE", T0),
        ),
        received_time=T0,
    )
    assert "D08" in {item.hook_id for item in initial}
    reversed_batch = detector.process(
        (
            _flow(60, "BUY_TRAPPED", T0 + timedelta(seconds=1)),
            _flow(180, "BUY_TRAPPED", T0 + timedelta(seconds=1)),
        ),
        received_time=T0 + timedelta(seconds=1),
    )
    assert {"D06", "D08"} <= {item.hook_id for item in reversed_batch}
    resolved = detector.process(
        (
            _flow(60, "BUY_STALLED", T0 + timedelta(seconds=2)),
            _flow(180, "BUY_STALLED", T0 + timedelta(seconds=2)),
        ),
        received_time=T0 + timedelta(seconds=2),
    )
    assert "D07" in {item.hook_id for item in resolved}
    assert detector.process(
        (_flow(60, "BUY_EFFECTIVE", T0 + timedelta(seconds=1)),),
        received_time=T0 + timedelta(seconds=3),
    ) == ()
    assert detector.stale_snapshots == 1


def test_all_stage2b_hook_ids_remain_fail_closed_while_uncalibrated():
    stage2b_ids = (
        *(f"A{index:02d}" for index in range(1, 25)),
        *(f"C{index:02d}" for index in range(3, 10)),
        *(f"D{index:02d}" for index in range(6, 9)),
        *(f"E{index:02d}" for index in range(1, 7)),
        *(f"F{index:02d}" for index in range(1, 6)),
        *(f"G{index:02d}" for index in range(1, 12)),
    )
    candidates = tuple(
        make_candidate(
            hook_id,
            symbol="BTCUSDT",
            side=HookSide.NEUTRAL,
            source_time=T0,
            received_time=T0,
            metric_name="synthetic_measurement",
            metric_value=1,
        )
        for hook_id in stage2b_ids
    )
    runtime = HookRuntime(ThresholdBook({}, config_hash="a" * 64))
    assert runtime.submit(candidates) == ()
    assert runtime.candidates_seen == len(stage2b_ids) == 56
    assert runtime.events_emitted == 0
    assert runtime.thresholds.suppressed_uncalibrated == 56


def test_future_data_is_rejected_before_candidate_creation():
    detector = OpenInterestDetector(comparison_window_sec=60)
    with pytest.raises(ValueError, match="source_time"):
        detector.process(
            {
                "symbol": "BTCUSDT",
                "source_time": T0 + timedelta(seconds=1),
                "open_interest": D("1000"),
            },
            price=D("100"),
            received_time=T0,
        )
