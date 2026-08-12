"""Bounded order-book selection benchmark for an isolated CI runner."""

from __future__ import annotations

import cProfile
import json
import platform
import random
import statistics
import timeit
from decimal import Decimal
from pathlib import Path

from src.orderflow.orderbook import OrderBookSnapshot


LEVEL_COUNT = 1_000
LIMIT = 50
LOOPS = 500
REPEATS = 7
ROOT = Path(__file__).resolve().parents[1]


def _books(*, shuffled: bool) -> tuple[dict[Decimal, Decimal], dict[Decimal, Decimal]]:
    bid_rows = [
        (Decimal("100000") - Decimal(index) / Decimal("10"), Decimal(index + 1))
        for index in range(LEVEL_COUNT)
    ]
    ask_rows = [
        (Decimal("100000.1") + Decimal(index) / Decimal("10"), Decimal(index + 1))
        for index in range(LEVEL_COUNT)
    ]
    if shuffled:
        rng = random.Random(20260812)
        rng.shuffle(bid_rows)
        rng.shuffle(ask_rows)
    return dict(bid_rows), dict(ask_rows)


def _legacy_select(
    bids: dict[Decimal, Decimal], asks: dict[Decimal, Decimal]
) -> tuple[tuple[tuple[Decimal, Decimal], ...], tuple[tuple[Decimal, Decimal], ...]]:
    return (
        tuple(sorted(bids.items(), key=lambda row: row[0], reverse=True)[:LIMIT]),
        tuple(sorted(asks.items(), key=lambda row: row[0])[:LIMIT]),
    )


def _bounded_select(
    bids: dict[Decimal, Decimal], asks: dict[Decimal, Decimal]
) -> tuple[tuple[tuple[Decimal, Decimal], ...], tuple[tuple[Decimal, Decimal], ...]]:
    snapshot = OrderBookSnapshot("BTCUSDT", 1, bids, asks)
    return snapshot.best_bids(LIMIT), snapshot.best_asks(LIMIT)


def _legacy_with_copy(
    bids: dict[Decimal, Decimal], asks: dict[Decimal, Decimal]
) -> tuple[tuple[tuple[Decimal, Decimal], ...], tuple[tuple[Decimal, Decimal], ...]]:
    return _legacy_select(dict(bids), dict(asks))


def _bounded_with_copy(
    bids: dict[Decimal, Decimal], asks: dict[Decimal, Decimal]
) -> tuple[tuple[tuple[Decimal, Decimal], ...], tuple[tuple[Decimal, Decimal], ...]]:
    return _bounded_select(dict(bids), dict(asks))


def _copy_only(bids: dict[Decimal, Decimal], asks: dict[Decimal, Decimal]) -> None:
    dict(bids), dict(asks)


def _median_seconds(callback: object) -> float:
    samples = timeit.repeat(callback, number=LOOPS, repeat=REPEATS)
    return statistics.median(samples) / LOOPS


def _profile(
    path: Path,
    callback: object,
    *,
    iterations: int = 2_000,
) -> None:
    profiler = cProfile.Profile()
    profiler.enable()
    for _ in range(iterations):
        callback()
    profiler.disable()
    profiler.dump_stats(path)


def main() -> None:
    results: dict[str, object] = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "levels_per_side": LEVEL_COUNT,
        "limit": LIMIT,
        "loops_per_repeat": LOOPS,
        "repeats": REPEATS,
        "scenarios": {},
    }

    for scenario, shuffled in (("ordered", False), ("shuffled", True)):
        bids, asks = _books(shuffled=shuffled)
        legacy_expected = _legacy_select(bids, asks)
        assert _bounded_select(bids, asks) == legacy_expected
        assert _legacy_with_copy(bids, asks) == legacy_expected
        assert _bounded_with_copy(bids, asks) == legacy_expected

        legacy_select = _median_seconds(lambda: _legacy_select(bids, asks))
        bounded_select = _median_seconds(lambda: _bounded_select(bids, asks))
        legacy_copy = _median_seconds(lambda: _legacy_with_copy(bids, asks))
        bounded_copy = _median_seconds(lambda: _bounded_with_copy(bids, asks))
        copy_only = _median_seconds(lambda: _copy_only(bids, asks))
        results["scenarios"][scenario] = {
            "legacy_select_seconds": legacy_select,
            "bounded_select_seconds": bounded_select,
            "selection_ratio_new_over_old": bounded_select / legacy_select,
            "legacy_with_copy_seconds": legacy_copy,
            "bounded_with_copy_seconds": bounded_copy,
            "with_copy_ratio_new_over_old": bounded_copy / legacy_copy,
            "copy_only_seconds": copy_only,
            "copy_share_of_bounded_with_copy": copy_only / bounded_copy,
            "outputs_identical": True,
        }

        if scenario == "shuffled":
            _profile(
                ROOT / "cpu_orderbook_legacy.prof",
                lambda: _legacy_with_copy(bids, asks),
            )
            _profile(
                ROOT / "cpu_orderbook_bounded.prof",
                lambda: _bounded_with_copy(bids, asks),
            )

    output = ROOT / "cpu_orderbook_benchmark.json"
    output.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")

    import pstats

    with (ROOT / "cpu_orderbook_profile.txt").open("w", encoding="utf-8") as stream:
        for label in ("legacy", "bounded"):
            stream.write(f"=== {label} shuffled with dictionary copy ===\n")
            stats = pstats.Stats(
                str(ROOT / f"cpu_orderbook_{label}.prof"), stream=stream
            )
            stats.strip_dirs().sort_stats("cumulative").print_stats(15)

    print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
