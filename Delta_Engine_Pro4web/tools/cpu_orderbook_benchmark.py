"""Manager-level order-book benchmark for an isolated CI runner."""

from __future__ import annotations

import cProfile
import importlib.util
import json
import os
import platform
import random
import statistics
import sys
import timeit
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Callable

from src.orderflow import orderbook as candidate


LEVEL_COUNT = 1_000
LIMIT = 50
LOOPS = 500
REPEATS = 7
ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "b4468fadc0052abe01d906146f0e7a0a7f9d9f82"
T0 = datetime(2026, 8, 12, tzinfo=timezone.utc)


def _load_baseline() -> ModuleType:
    path = Path(os.environ["BASELINE_ORDERBOOK_PATH"])
    spec = importlib.util.spec_from_file_location("baseline_orderbook", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load baseline module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _rows(*, shuffled: bool) -> tuple[list[tuple[Decimal, Decimal]], list[tuple[Decimal, Decimal]]]:
    bids = [
        (Decimal("100000") - Decimal(index) / Decimal("10"), Decimal(index + 1))
        for index in range(LEVEL_COUNT)
    ]
    asks = [
        (Decimal("100000.1") + Decimal(index) / Decimal("10"), Decimal(index + 1))
        for index in range(LEVEL_COUNT)
    ]
    if shuffled:
        rng = random.Random(20260812)
        rng.shuffle(bids)
        rng.shuffle(asks)
    return bids, asks


class ManagerRunner:
    def __init__(
        self,
        module: ModuleType,
        *,
        bounded: bool,
        shuffled: bool,
        churn: bool,
    ) -> None:
        self.module = module
        self.bounded = bounded
        self.churn = churn
        self.sequence = 1
        self.toggle = False
        bids, asks = _rows(shuffled=shuffled)
        self.bid_price = Decimal("100000")
        self.ask_price = Decimal("100000.1")
        self.manager = module.OrderBookStateManager("BTCUSDT")
        initial = module.OrderBookUpdate(
            event_time=T0,
            symbol="BTCUSDT",
            update_type="SNAPSHOT",
            first_update_id=None,
            final_update_id=self.sequence,
            bids=tuple(module.BookLevel(price, quantity) for price, quantity in bids),
            asks=tuple(module.BookLevel(price, quantity) for price, quantity in asks),
        )
        result = self.manager.apply(initial)
        if not result.applied:
            raise AssertionError("initial snapshot was rejected")

    def step(self) -> tuple[object, object]:
        self.sequence += 1
        self.toggle = not self.toggle
        if self.churn:
            quantity = Decimal("0") if self.toggle else Decimal("1")
        else:
            quantity = Decimal("2001") if self.toggle else Decimal("2002")
        update = self.module.OrderBookUpdate(
            event_time=T0,
            symbol="BTCUSDT",
            update_type="DIFF",
            first_update_id=self.sequence,
            final_update_id=self.sequence,
            previous_final_update_id=self.sequence - 1,
            bids=(self.module.BookLevel(self.bid_price, quantity),),
            asks=(self.module.BookLevel(self.ask_price, quantity),),
        )
        result = self.manager.apply(update)
        if not result.applied:
            raise AssertionError(f"diff {self.sequence} was rejected")
        snapshot = self.manager.snapshot()
        if snapshot is None:
            raise AssertionError("applied diff produced no snapshot")
        if self.bounded:
            return snapshot.best_bids(LIMIT), snapshot.best_asks(LIMIT)
        return snapshot.ordered_bids[:LIMIT], snapshot.ordered_asks[:LIMIT]


def _median_seconds(callback: Callable[[], object]) -> float:
    samples = timeit.repeat(callback, number=LOOPS, repeat=REPEATS)
    return statistics.median(samples) / LOOPS


def _profile(path: Path, callback: Callable[[], object], iterations: int = 2_000) -> None:
    profiler = cProfile.Profile()
    profiler.enable()
    for _ in range(iterations):
        callback()
    profiler.disable()
    profiler.dump_stats(path)


def main() -> None:
    baseline = _load_baseline()
    results: dict[str, object] = {
        "baseline_commit": BASE_COMMIT,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "levels_per_side": LEVEL_COUNT,
        "limit": LIMIT,
        "loops_per_repeat": LOOPS,
        "repeats": REPEATS,
        "required_ratio_new_over_old": 0.8,
        "scenarios": {},
    }
    all_outputs_identical = True
    all_meet_target = True

    scenarios = (
        ("ordered_quantity_update", False, False),
        ("shuffled_quantity_update", True, False),
        ("ordered_top_churn", False, True),
        ("shuffled_top_churn", True, True),
    )
    for name, shuffled, churn in scenarios:
        legacy_check = ManagerRunner(
            baseline, bounded=False, shuffled=shuffled, churn=churn
        )
        candidate_check = ManagerRunner(
            candidate, bounded=True, shuffled=shuffled, churn=churn
        )
        outputs_identical = all(
            legacy_check.step() == candidate_check.step()
            for _ in range(10)
        )
        all_outputs_identical &= outputs_identical

        legacy_runner = ManagerRunner(
            baseline, bounded=False, shuffled=shuffled, churn=churn
        )
        candidate_runner = ManagerRunner(
            candidate, bounded=True, shuffled=shuffled, churn=churn
        )
        legacy_seconds = _median_seconds(legacy_runner.step)
        candidate_seconds = _median_seconds(candidate_runner.step)
        ratio = candidate_seconds / legacy_seconds
        meets_target = ratio <= 0.8
        all_meet_target &= meets_target
        results["scenarios"][name] = {
            "legacy_seconds_per_accepted_diff": legacy_seconds,
            "candidate_seconds_per_accepted_diff": candidate_seconds,
            "ratio_new_over_old": ratio,
            "improvement_fraction": 1 - ratio,
            "outputs_identical": outputs_identical,
            "meets_20_percent_target": meets_target,
        }

        if name == "ordered_top_churn":
            _profile(ROOT / "cpu_orderbook_legacy.prof", legacy_runner.step)
            _profile(ROOT / "cpu_orderbook_bounded.prof", candidate_runner.step)

    results["all_outputs_identical"] = all_outputs_identical
    results["all_scenarios_meet_20_percent_target"] = all_meet_target
    output = ROOT / "cpu_orderbook_benchmark.json"
    output.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")

    import pstats

    with (ROOT / "cpu_orderbook_profile.txt").open("w", encoding="utf-8") as stream:
        for label in ("legacy", "bounded"):
            stream.write(f"=== {label} ordered top churn ===\n")
            stats = pstats.Stats(
                str(ROOT / f"cpu_orderbook_{label}.prof"), stream=stream
            )
            stats.strip_dirs().sort_stats("cumulative").print_stats(20)

    print(json.dumps(results, indent=2, sort_keys=True))
    if not all_outputs_identical:
        raise SystemExit("benchmark output mismatch")
    if not all_meet_target:
        raise SystemExit("one or more scenarios missed the 20% improvement target")


if __name__ == "__main__":
    main()
