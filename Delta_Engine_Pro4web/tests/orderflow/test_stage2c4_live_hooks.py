from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.orderflow.cvd import Candle
from src.orderflow.hooks.config import ThresholdBook
from src.orderflow.hooks.live import (
    STAGE2C4_CALIBRATED_HOOK_IDS,
    LiveHookObserver,
    load_live_hook_config,
)
from src.orderflow.hooks.models import CalibrationStatus, HookThreshold
from src.orderflow.orderbook import (
    ApplyResult,
    BookLevel,
    OrderBookSnapshot,
    OrderBookUpdate,
)


D = Decimal
T0 = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)


class MemorySink:
    def __init__(self) -> None:
        self.events = []
        self.closed = False

    def add_event(self, event) -> bool:
        self.events.append(event)
        return True

    def stats(self) -> dict:
        return {"accepted": len(self.events), "written": len(self.events)}

    def close(self) -> None:
        self.closed = True


def _live_config_text(*, enabled: str = "true", mode: str = "OBSERVE") -> str:
    hook_ids = "\n".join(
        f"  - {hook_id}" for hook_id in sorted(STAGE2C4_CALIBRATED_HOOK_IDS)
    )
    return (
        "schema_version: 1\n"
        f"event_firing_enabled: {enabled}\n"
        f"mode: {mode}\n"
        "execution_enabled: false\n"
        "calibrated_hook_ids:\n"
        f"{hook_ids}\n"
    )


def test_live_hook_config_is_observe_only_and_exactly_allowlisted(
    tmp_path: Path,
) -> None:
    path = tmp_path / "hook_live.yaml"
    path.write_text(_live_config_text(), encoding="utf-8")
    config = load_live_hook_config(path)
    assert config.event_firing_enabled is True
    assert config.mode == "OBSERVE"
    assert config.execution_enabled is False
    assert config.calibrated_hook_ids == STAGE2C4_CALIBRATED_HOOK_IDS

    path.write_text(_live_config_text(mode="EXECUTE"), encoding="utf-8")
    with pytest.raises(ValueError, match="mode must be OBSERVE"):
        load_live_hook_config(path)

    path.write_text(_live_config_text(enabled='"true"'), encoding="utf-8")
    with pytest.raises(ValueError, match="must be boolean"):
        load_live_hook_config(path)


def _threshold(hook_id: str, metric: str, value: str) -> HookThreshold:
    return HookThreshold(
        hook_id=hook_id,
        metric_name=metric,
        operator="ge",
        quantile=D("0.90"),
        value=D(value),
        status=CalibrationStatus.CALIBRATED,
        input_manifest_sha256="a" * 64,
        sample_count=1_000,
        valid_days=3,
    )


def _observer(thresholds: dict[str, HookThreshold]) -> tuple[LiveHookObserver, MemorySink]:
    sink = MemorySink()
    observer = LiveHookObserver(
        symbol="BTCUSDT",
        profile=SimpleNamespace(),
        thresholds=ThresholdBook(thresholds, config_hash="b" * 64),
        sink=sink,
    )
    return observer, sink


def test_live_observer_emits_calibrated_price_hook_and_suppresses_others() -> None:
    observer, sink = _observer({
        "G10": _threshold("G10", "distance_to_round_number_bps", "0"),
    })
    candle = Candle(
        bar_time=T0,
        symbol="BTCUSDT",
        timeframe="1m",
        open=D("100"),
        high=D("101"),
        low=D("99"),
        close=D("100"),
        volume=D("10"),
        delta=D("1"),
        cvd=D("1"),
    )

    emitted = observer.observe_candle(
        candle,
        received_time=T0 + timedelta(minutes=1),
    )

    assert [event.hook_id for event in emitted] == ["G10"]
    assert [event.hook_id for event in sink.events] == ["G10"]
    assert observer.runtime.thresholds.suppressed_uncalibrated >= 3
    assert observer.stats()["events_by_hook"] == {"G10": 1}


def test_live_observer_requires_aligned_dom_diff_before_calibrated_fire() -> None:
    observer, sink = _observer({
        "A01": _threshold("A01", "level_quantity_over_side_median", "1"),
    })
    applied = ApplyResult(applied=True, reinitialized=False, gap_detected=False)
    snapshot_update = OrderBookUpdate(
        event_time=T0,
        symbol="BTCUSDT",
        update_type="SNAPSHOT",
        first_update_id=None,
        final_update_id=100,
        bids=(BookLevel(D("100"), D("1")),),
        asks=(BookLevel(D("101"), D("1")),),
    )
    snapshot = OrderBookSnapshot(
        symbol="BTCUSDT",
        last_update_id=100,
        bids={D("100"): D("1")},
        asks={D("101"): D("1")},
        event_time=T0,
    )
    assert observer.observe_depth(
        snapshot_update,
        applied,
        snapshot,
        received_time=T0,
    ) == ()

    diff_time = T0 + timedelta(milliseconds=100)
    diff_update = OrderBookUpdate(
        event_time=diff_time,
        symbol="BTCUSDT",
        update_type="DIFF",
        first_update_id=101,
        final_update_id=101,
        previous_final_update_id=100,
        bids=(BookLevel(D("100"), D("10")), BookLevel(D("99"), D("1"))),
        asks=(BookLevel(D("101"), D("2")), BookLevel(D("102"), D("1"))),
    )
    after = OrderBookSnapshot(
        symbol="BTCUSDT",
        last_update_id=101,
        bids={D("100"): D("10"), D("99"): D("1")},
        asks={D("101"): D("2"), D("102"): D("1")},
        event_time=diff_time,
    )
    emitted = observer.observe_depth(
        diff_update,
        applied,
        after,
        received_time=diff_time,
    )

    assert [event.hook_id for event in emitted] == ["A01"]
    assert [event.hook_id for event in sink.events] == ["A01"]
    assert observer.quality.is_valid is True
