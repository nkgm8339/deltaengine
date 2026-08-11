"""Big Trades V2 phase-6 performance and operational contracts.

Each test name carries exactly one BT2-O contract ID.  The 120-second live
soak is executed by ``tools/big_trades_phase6_soak.py``; O293 verifies the
committed machine-readable result so the full repository suite stays
repeatable while the duration evidence remains auditable.
"""

from __future__ import annotations

import asyncio
import gc
import json
import logging
import random
import subprocess
import sys
from math import ceil
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from threading import Event
from time import perf_counter_ns
from types import SimpleNamespace

import psutil

from src.database.big_trades_storage import (
    BigTradesBackgroundStorageWriter,
    BigTradesDuckDbStore,
)
from src.orderflow.big_trades.aggregation import create_big_trade_event
from src.orderflow.big_trades.activation import (
    ActivationArtifact,
    ActivationReason,
    CalibrationActivationPolicy,
)
from src.orderflow.big_trades.artifacts import BigTradesArtifactRepository
from src.orderflow.big_trades.constants import (
    AutomaticIntensity,
    FilterMode,
    MarkerPriceMode,
    SideFilter,
)
from src.orderflow.big_trades.models import BigTradeFill
from src.orderflow.big_trades.filtering import decide_cluster
from src.orderflow.big_trades.horizons import ResultHorizonTracker
from src.orderflow.big_trades.price_path import SourcePricePathIndex
from src.orderflow.big_trades.reaction_zones import ReactionZoneObserver
from src.orderflow.big_trades.runtime import (
    BigTradesRuntimeV2,
    FixedActivationSettingsResolver,
    RuntimeMode,
    RuntimeRecord,
)
from src.orderflow.big_trades.settings import SettingsVersion
from src.orderflow.big_trades.zone_index import ReactionZoneBoundaryIndex
from src.orderflow.orderbook import BookLevel, OrderBookStateManager, OrderBookUpdate
from tests.orderflow._big_trades_helpers import event_zone, settings as helper_settings
from webapp.big_trades_protocol import BigTradesBatcherV2
from webapp.push_broker import PushBroker
from webapp.tape import TapeBatcher


UTC = timezone.utc
BASE = datetime(2026, 8, 12, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = ROOT.parent
SOAK_EVIDENCE = (
    REPOSITORY_ROOT
    / "ArchitectureRepository"
    / "00_Master"
    / "BIG_TRADES_V2_PHASE6_EVIDENCE_20260812"
    / "live_soak_120s.json"
)
PERFORMANCE_EVIDENCE = SOAK_EVIDENCE.with_name("performance_report.json")
TRACE_EVIDENCE = SOAK_EVIDENCE.with_name("lineage_traces.json")


class _NullStorageWriter:
    """No-I/O writer for rejected-cluster hot-path measurements."""

    def statistics(self) -> dict[str, object]:
        return {
            "queue_pending": 0,
            "queue_high_watermark": 0,
            "queue_full": 0,
        }


def _settings_activation(minimum: str = "999999999"):
    effective = BASE - timedelta(days=1)
    settings = SettingsVersion.create(
        symbol="BTCUSDT",
        venue="BINANCE",
        filter_mode=FilterMode.MANUAL,
        manual_min_quantity=minimum,
        manual_max_quantity="0",
        automatic_intensity=AutomaticIntensity.MEDIUM,
        side_filter=SideFilter.BOTH,
        marker_price_mode=MarkerPriceMode.LAST_PRICE,
    )
    activation = ActivationArtifact.create(
        symbol="BTCUSDT",
        venue="BINANCE",
        effective_from_event_time=effective,
        effective_from_trade_id=0,
        settings_id=settings.settings_id,
        calibration_id=None,
        activation_reason=ActivationReason.USER_SETTINGS,
        activation_policy=CalibrationActivationPolicy.MANUAL_ONLY,
        requested_at_utc=effective,
    )
    return settings, activation


def _runtime(*, minimum: str = "999999999", writer=None, horizons=()):
    settings, activation = _settings_activation(minimum)
    return BigTradesRuntimeV2(
        enabled=True,
        mode=RuntimeMode.LIVE,
        symbol="BTCUSDT",
        venue="BINANCE",
        tick_size=Decimal("0.1"),
        settings_resolver=FixedActivationSettingsResolver(settings, activation),
        storage_writer=writer or _NullStorageWriter(),
        horizons_seconds=tuple(horizons),
    )


def _trade(
    trade_id: int,
    milliseconds: int,
    *,
    price: str = "1",
    quantity: str = "1",
    side: str = "BUY",
    base: datetime = BASE,
) -> BigTradeFill:
    event_time = base + timedelta(milliseconds=milliseconds)
    return BigTradeFill(
        event_time=event_time,
        trade_time=event_time,
        trade_id=trade_id,
        symbol="BTCUSDT",
        venue="BINANCE",
        price=Decimal(price),
        quantity=Decimal(quantity),
        side=side,
    )


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, ceil(len(ordered) * percentile) - 1))]


def _zone(identifier: int, low: int, high: int):
    _, template, _ = event_zone()
    return replace(
        template,
        zone_id=f"zone-{identifier}",
        zone_low=Decimal(low),
        zone_high=Decimal(high),
    )


def _cluster_finalize_benchmark(iterations: int = 5_000) -> dict[str, float]:
    event, _, origin_fills = event_zone(minimum="1")
    configured = helper_settings(minimum="1")
    from src.orderflow.big_trades.models import ExecutionCluster

    cluster = ExecutionCluster(
        origin_fills,
        configured,
        event.close_reason,
    )
    for _ in range(500):
        create_big_trade_event(cluster, decide_cluster(cluster))
    batch_size = 50
    times: list[float] = []
    gc_enabled = gc.isenabled()
    gc.disable()
    try:
        for _ in range(0, iterations, batch_size):
            started = perf_counter_ns()
            for _ in range(batch_size):
                decision = decide_cluster(cluster)
                create_big_trade_event(cluster, decision)
            times.append((perf_counter_ns() - started) / 1_000_000 / batch_size)
    finally:
        if gc_enabled:
            gc.enable()
    return {
        "iterations": iterations,
        "batch_size": batch_size,
        "p95_ms": _percentile(times, 0.95),
        "p99_ms": _percentile(times, 0.99),
        "max_ms": max(times),
    }


def _horizon_finalize_benchmark(iterations: int = 5_000) -> dict[str, float]:
    event, zone, origin_fills = event_zone()
    observer = ReactionZoneObserver(zone, tick_size=Decimal("1"))
    path = SourcePricePathIndex(symbol=event.symbol, venue=event.venue)
    for trade in origin_fills:
        path.append(trade)
    target = event.last_time + timedelta(seconds=1)
    target_trade = BigTradeFill(
        event_time=target,
        trade_time=target,
        trade_id=100,
        symbol=event.symbol,
        venue=event.venue,
        price=Decimal("103"),
        quantity=Decimal("1"),
        side="BUY",
    )
    path.append(target_trade)
    observer.observe_trade(target_trade)
    tracker = ResultHorizonTracker(
        event,
        zone,
        observer,
        path,
        horizons_seconds=(1,),
    )
    for _ in range(500):
        tracker._build(1, target)
    batch_size = 50
    times: list[float] = []
    gc_enabled = gc.isenabled()
    gc.disable()
    try:
        for _ in range(0, iterations, batch_size):
            started = perf_counter_ns()
            for _ in range(batch_size):
                tracker._build(1, target)
            times.append((perf_counter_ns() - started) / 1_000_000 / batch_size)
    finally:
        if gc_enabled:
            gc.enable()
    return {
        "iterations": iterations,
        "batch_size": batch_size,
        "p95_ms": _percentile(times, 0.95),
        "p99_ms": _percentile(times, 0.99),
        "max_ms": max(times),
    }


def _isolated_compute_benchmark(name: str, runs: int = 3) -> dict[str, object]:
    if name not in {"cluster", "horizon"}:
        raise ValueError("unknown compute benchmark")
    function = (
        "_cluster_finalize_benchmark"
        if name == "cluster"
        else "_horizon_finalize_benchmark"
    )
    program = (
        "import json; "
        f"from tests.performance.test_big_trades_phase6 import {function}; "
        f"print(json.dumps({function}()))"
    )
    trials = []
    for _ in range(runs):
        completed = subprocess.run(
            [sys.executable, "-c", program],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        trials.append(json.loads(completed.stdout))
    return {
        "iterations_per_trial": trials[0]["iterations"],
        "batch_size": trials[0]["batch_size"],
        "trial_count": runs,
        "p95_ms": median(item["p95_ms"] for item in trials),
        "p99_ms": median(item["p99_ms"] for item in trials),
        "max_ms": max(item["max_ms"] for item in trials),
        "trials": trials,
    }


def test_big_trades_cluster_finalize_p99_under_1_5ms() -> None:
    metrics = _isolated_compute_benchmark("cluster")
    assert metrics["p99_ms"] <= 1.50, metrics


def test_big_trades_horizon_finalize_p99_under_1ms() -> None:
    metrics = _isolated_compute_benchmark("horizon")
    assert metrics["p99_ms"] <= 1.00, metrics


def test_big_trades_phase6_machine_performance_evidence_is_complete() -> None:
    result = json.loads(PERFORMANCE_EVIDENCE.read_text(encoding="utf-8"))
    assert result["status"] == "PASS"
    assert result["production_mutations"] == 0
    assert result["checks"] and all(result["checks"].values())


def test_big_trades_phase6_lineage_evidence_has_three_validated_ui_traces() -> None:
    result = json.loads(TRACE_EVIDENCE.read_text(encoding="utf-8"))
    assert result["status"] == "PASS"
    assert result["production_mutations"] == 0
    assert len(result["traces"]) == 3
    assert all(trace["ui_projection"]["validated"] for trace in result["traces"])
    assert result["manual_automatic_equivalence"]["status"] == "PASS"


def _active_zone_benchmark(zone_count: int) -> dict[str, float]:
    runtime = _runtime()
    for identifier in range(zone_count):
        runtime.zone_index.add(
            _zone(identifier, 10_000 + identifier * 3, 10_001 + identifier * 3)
        )
    for index in range(500):
        runtime.process(_trade(index + 1, index, price=str(1 + index % 2)))
    total_times: list[float] = []
    boundary_times: list[float] = []
    gc.collect()
    measured = [
        _trade(index + 1, index, price=str(1 + index % 2))
        for index in range(500, 20_500)
    ]
    batch_size = 500
    gc_enabled = gc.isenabled()
    gc.disable()
    try:
        for start in range(0, len(measured), batch_size):
            started = perf_counter_ns()
            for trade in measured[start : start + batch_size]:
                runtime.process(trade)
            total_times.append(
                (perf_counter_ns() - started) / 1_000_000 / batch_size
            )
        for _ in range(40):
            started = perf_counter_ns()
            for _ in range(500):
                runtime.zone_index.candidates(Decimal("1"), Decimal("2"))
            boundary_times.append((perf_counter_ns() - started) / 1_000_000 / 500)
    finally:
        if gc_enabled:
            gc.enable()
    stats = runtime.statistics()
    assert stats["active_zone_count"] == zone_count
    assert stats["errors"] == 0
    return {
        "total_p95_ms": _percentile(total_times, 0.95),
        "total_p99_ms": _percentile(total_times, 0.99),
        "boundary_p99_ms": _percentile(boundary_times, 0.99),
    }


def _assert_server_budget(metrics: dict[str, float]) -> None:
    assert metrics["total_p95_ms"] <= 0.15, metrics
    assert metrics["total_p99_ms"] <= 0.40, metrics
    assert metrics["boundary_p99_ms"] <= 0.25, metrics


def _isolated_active_zone_benchmark(
    zone_count: int, runs: int = 3
) -> dict[str, object]:
    program = (
        "import json; "
        "from tests.performance.test_big_trades_phase6 import _active_zone_benchmark; "
        f"print(json.dumps(_active_zone_benchmark({zone_count})))"
    )
    trials = []
    for _ in range(runs):
        completed = subprocess.run(
            [sys.executable, "-c", program],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        trials.append(json.loads(completed.stdout))
    return {
        "trial_count": runs,
        "total_p95_ms": median(item["total_p95_ms"] for item in trials),
        "total_p99_ms": median(item["total_p99_ms"] for item in trials),
        "boundary_p99_ms": median(item["boundary_p99_ms"] for item in trials),
        "trials": trials,
    }


def test_bt2_o276_active_zones_10_per_trade_benchmark() -> None:
    _assert_server_budget(_isolated_active_zone_benchmark(10))


def test_bt2_o277_active_zones_100_per_trade_benchmark() -> None:
    _assert_server_budget(_isolated_active_zone_benchmark(100))


def test_bt2_o278_active_zones_1000_per_trade_benchmark() -> None:
    _assert_server_budget(_isolated_active_zone_benchmark(1_000))


def test_bt2_o279_active_zones_5000_per_trade_benchmark() -> None:
    _assert_server_budget(_isolated_active_zone_benchmark(5_000))


def test_bt2_o280_query_hot_path_does_not_scan_zone_dictionary() -> None:
    class _NoScanDict(dict):
        def __iter__(self):
            raise AssertionError("zone dictionary iteration on query hot path")

        def values(self):
            raise AssertionError("zone dictionary values scan on query hot path")

        def items(self):
            raise AssertionError("zone dictionary items scan on query hot path")

    index = ReactionZoneBoundaryIndex(
        _zone(identifier, identifier * 3, identifier * 3 + 1)
        for identifier in range(5_000)
    )
    index.candidates(Decimal("100"), Decimal("101"))
    index._zones = _NoScanDict(index._zones)  # structural guard after index build
    assert index.candidates(Decimal("100"), Decimal("101"))
    assert index.overlapping_or_adjacent(
        Decimal("100"), Decimal("101"), Decimal("1")
    )


def test_bt2_o281_boundary_index_matches_randomized_brute_force() -> None:
    randomizer = random.Random(20260812)
    zones = []
    for identifier in range(500):
        low = randomizer.randint(1, 5_000)
        zones.append(_zone(identifier, low, low + randomizer.randint(0, 50)))
    index = ReactionZoneBoundaryIndex(zones)
    for _ in range(500):
        previous = Decimal(randomizer.randint(1, 5_100))
        current = Decimal(randomizer.randint(1, 5_100))
        lower, upper = sorted((previous, current))
        expected = tuple(
            sorted(
                zone.zone_id
                for zone in zones
                if zone.zone_low <= previous <= zone.zone_high
                or zone.zone_low <= current <= zone.zone_high
                or lower < zone.zone_low <= upper
                or lower < zone.zone_high <= upper
            )
        )
        assert index.candidates(previous, current) == expected


def test_bt2_o282_price_path_range_query_matches_randomized_oracle() -> None:
    randomizer = random.Random(20260812)
    path = SourcePricePathIndex(symbol="BTCUSDT", venue="BINANCE")
    prices: list[Decimal] = []
    trades: list[BigTradeFill] = []
    for index in range(2_000):
        price = Decimal(randomizer.randint(1, 1_000_000)) / Decimal("100")
        trade = _trade(index + 1, index, price=str(price))
        prices.append(price)
        trades.append(trade)
        path.append(trade)
    for _ in range(500):
        start = randomizer.randint(0, len(trades) - 1)
        end = randomizer.randint(start, len(trades) - 1)
        assert path.range_min_max_by_source_key(
            trades[start].source_key, trades[end].source_key
        ) == (min(prices[start : end + 1]), max(prices[start : end + 1]))


def test_bt2_o283_6000_trade_runtime_accounting_has_no_loss() -> None:
    runtime = _runtime()
    for index in range(6_000):
        runtime.process(
            _trade(
                index + 1,
                index * 50,
                side="BUY" if index % 2 == 0 else "SELL",
            )
        )
    runtime.flush()
    stats = runtime.statistics()
    assert stats["trades_observed"] == 6_000
    assert stats["clusters_finalized"] == 6_000
    assert stats["clusters_rejected"] == 6_000
    assert stats["clusters_accepted"] == 0
    assert stats["invalid_trades"] == 0
    assert stats["errors"] == 0


def _record(index: int) -> RuntimeRecord:
    digest = f"{index + 1:064x}"[-64:]
    event_id = f"bt2_{digest}"
    return RuntimeRecord(
        kind="EVENT_CREATED",
        source_event_time=BASE + timedelta(microseconds=index),
        source_trade_id=index + 1,
        record_id=event_id,
        content_hash=digest,
        payload={"event_id": event_id, "content_hash": digest},
    )


def test_bt2_o284_25000_trade_and_stream_overflow_is_fully_accounted() -> None:
    async def ignore(_value) -> None:
        return None

    tape = TapeBatcher(ignore, symbol="BTCUSDT", pending_capacity=10_000)
    stream = BigTradesBatcherV2(ignore, symbol="BTCUSDT", pending_capacity=10_000)
    tape_logger = logging.getLogger("webapp.tape")
    stream_logger = logging.getLogger("webapp.big_trades")
    previous_levels = tape_logger.level, stream_logger.level
    tape_logger.setLevel(logging.CRITICAL)
    stream_logger.setLevel(logging.CRITICAL)
    try:
        for index in range(25_000):
            tape.publish(_trade(index + 1, index))
            stream.publish((_record(index),))
    finally:
        tape_logger.setLevel(previous_levels[0])
        stream_logger.setLevel(previous_levels[1])
    tape_stats = tape.stats_snapshot()
    stream_stats = stream.stats_snapshot()
    assert tape_stats["accepted_trades"] == 25_000
    assert tape_stats["dropped_trades"] == 15_000
    assert tape_stats["pending"] == 10_000
    assert tape_stats["accounting_balanced"] is True
    assert stream_stats["accepted_records"] == 25_000
    assert stream_stats["dropped_records"] == 15_000
    assert stream_stats["pending"] == 10_000
    assert stream_stats["accounting_balanced"] is True


def test_bt2_o285_browser_merges_5000_events_20000_interactions_under_budget() -> None:
    command = [
        "node",
        str(Path(__file__).with_name("big_trades_browser_benchmark.js")),
        str(ROOT / "webapp" / "static" / "big_trades.js"),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=True, timeout=30)
    result = json.loads(completed.stdout)
    assert result["events"]["events"] == 5_000
    assert result["zones"]["interactions"] == 20_000
    assert result["elapsed_ms"] <= 150, result


def _mode_switch_benchmark() -> dict[str, float]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.set_content(
            "<canvas id='chart' tabindex='0' style='width:1100px;height:760px'></canvas>"
            "<div id='tip' hidden></div>"
        )
        page.add_script_tag(path=str(ROOT / "webapp" / "static" / "big_trades.js"))
        result = page.evaluate(
            """
            () => {
              const api = window.DeltaBigTradesV2;
              const chart = new api.BigTradesCanvas({
                canvas:document.getElementById('chart'),
                tooltip:document.getElementById('tip'),
                eventStore:new api.BigTradeEventStore(5000),
                zoneStore:new api.ReactionZoneStore(5000, 20000),
                candlesProvider:() => []
              });
              const samples = [];
              for (let index = 0; index < 100; index += 1) {
                const started = performance.now();
                chart.setActive(true);
                chart.setActive(false);
                samples.push(performance.now() - started);
              }
              samples.sort((a,b) => a-b);
              return {
                iterations:samples.length,
                p95_ms:samples[Math.ceil(samples.length * 0.95) - 1],
                p99_ms:samples[Math.ceil(samples.length * 0.99) - 1],
                max_ms:samples[samples.length - 1]
              };
            }
            """
        )
        browser.close()
    return result


def test_big_trades_mode_switch_under_100ms() -> None:
    metrics = _mode_switch_benchmark()
    assert metrics["p99_ms"] <= 100, metrics


def _canvas_benchmark() -> dict[str, object]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.set_content(
            "<canvas id='chart' tabindex='0' style='width:1100px;height:760px'></canvas>"
            "<div id='tip' hidden></div>"
        )
        page.add_script_tag(path=str(ROOT / "webapp" / "static" / "big_trades.js"))
        result = page.evaluate(
            """
            () => {
              const api = window.DeltaBigTradesV2;
              const events = new api.BigTradeEventStore(5000);
              const zones = new api.ReactionZoneStore(5000, 20000);
              const base = Date.parse('2026-08-12T00:00:00Z');
              const hex = value => Number(value).toString(16).padStart(64, '0').slice(-64);
              for (let index = 0; index < 2000; index += 1) {
                const eventId = `bt2_${hex(index + 1)}`;
                const zoneId = `btz2_${hex(index + 1)}`;
                const hash = hex(index + 100000);
                const at = new Date(base + index * 400).toISOString();
                const price = (100 + (index % 100) / 10).toFixed(1);
                events.ingest({ event_id:eventId, last_time:at, marker_time:at,
                  marker_price:price, aggregate_quantity:'10', fill_count:1,
                  side:index % 2 ? 'SELL' : 'BUY', content_hash:hash });
                zones.ingestZone({ zone_id:zoneId, origin_event_id:eventId,
                  zone_source_start:at, zone_source_end:null, zone_low:price,
                  zone_high:price, zone_anchor:price,
                  origin_side:index % 2 ? 'SELL' : 'BUY', lifecycle:'ACTIVE',
                  current_relation:'INSIDE', gap_segments:[], content_hash:hash });
              }
              const chart = new api.BigTradesCanvas({
                canvas:document.getElementById('chart'),
                tooltip:document.getElementById('tip'), eventStore:events,
                zoneStore:zones, candlesProvider:() => []
              });
              chart.active = true;
              for (let index = 0; index < 5; index += 1) chart.draw();
              chart.drawTimes = [];
              for (let index = 0; index < 40; index += 1) chart.draw();
              return { ...chart.stats(), zones:chart.hitZones.length };
            }
            """
        )
        browser.close()
    return result


def test_bt2_o286_canvas_2000_markers_and_zones_p95_under_budget() -> None:
    result = _canvas_benchmark()
    assert result["zones"] == 2_000
    assert result["renderP95Ms"] <= 8, result


async def _tick_age_run(enabled: bool) -> list[int]:
    runtime = _runtime() if enabled else None
    broker = PushBroker("BTCUSDT")
    messages: list[dict] = []

    async def capture(message: dict) -> None:
        messages.append(message)

    broker._broadcast = capture
    for index in range(500):
        now = datetime.now(UTC)
        trade = BigTradeFill(
            event_time=now,
            trade_time=now,
            trade_id=index + 1,
            symbol="BTCUSDT",
            venue="BINANCE",
            price=Decimal("100"),
            quantity=Decimal("1"),
            side="BUY",
        )
        if runtime is not None:
            runtime.process(trade)
        await broker.on_trade(trade)
    if runtime is not None:
        assert runtime.statistics()["errors"] == 0
    return [message["payload"]["source_age_ms"] for message in messages]


def test_bt2_o287_big_trades_off_on_tick_source_age_comparison() -> None:
    off = asyncio.run(_tick_age_run(False))
    on = asyncio.run(_tick_age_run(True))
    assert len(off) == len(on) == 500
    assert _percentile(on, 0.95) - _percentile(off, 0.95) <= 1


async def _bar_age_run(enabled: bool) -> list[float]:
    runtime = _runtime() if enabled else None
    broker = PushBroker("BTCUSDT")
    ages: list[float] = []

    async def capture(message: dict) -> None:
        source = datetime.fromisoformat(message["payload"]["source_event_time"])
        ages.append((datetime.now(UTC) - source).total_seconds() * 1000)

    broker._broadcast = capture
    for index in range(200):
        now = datetime.now(UTC)
        trade = BigTradeFill(
            event_time=now,
            trade_time=now,
            trade_id=index + 1,
            symbol="BTCUSDT",
            venue="BINANCE",
            price=Decimal("100"),
            quantity=Decimal("1"),
            side="BUY",
        )
        if runtime is not None:
            runtime.process(trade)
        candle = SimpleNamespace(
            bar_time=now.replace(second=0, microsecond=0),
            symbol="BTCUSDT",
            timeframe="1m",
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=Decimal("1"),
            delta=Decimal("0"),
            cvd=Decimal("0"),
        )
        await broker.on_bar_update(
            candle, [], source_trade_id=index + 1, source_event_time=now
        )
    if runtime is not None:
        assert runtime.statistics()["errors"] == 0
    return ages


def test_bt2_o288_big_trades_off_on_bar_update_source_age_comparison() -> None:
    off = asyncio.run(_bar_age_run(False))
    on = asyncio.run(_bar_age_run(True))
    assert len(off) == len(on) == 200
    assert _percentile(on, 0.95) - _percentile(off, 0.95) <= 1


def test_bt2_o289_storage_queue_high_watermark_and_overflow_are_visible(
    tmp_path: Path,
) -> None:
    entered = Event()
    release = Event()

    def block(stage: str, table_name: str) -> None:
        if stage == "before_commit" and table_name == "big_trade_origin_batch":
            entered.set()
            assert release.wait(10)

    store = BigTradesDuckDbStore(tmp_path / "queue.duckdb", fault_injector=block)
    writer = BigTradesBackgroundStorageWriter(store, queue_maxsize=4)
    runtime = _runtime(minimum="10", writer=writer, horizons=(1,))
    try:
        runtime.process(_trade(1, 0, price="100", quantity="6", side="BUY"))
        runtime.process(_trade(2, 10, price="100", quantity="6", side="BUY"))
        runtime.process(_trade(3, 100, price="101", quantity="1", side="SELL"))
        runtime.process(_trade(4, 200, price="101", quantity="1", side="SELL"))
        assert entered.wait(5)
        trade_id = 5
        for cycle in range(1, 10):
            for offset, quantity, side in ((0, "6", "BUY"), (10, "6", "BUY"), (100, "1", "SELL")):
                runtime.process(
                    _trade(
                        trade_id,
                        cycle * 1_000 + offset,
                        price=str(100 + cycle * 10),
                        quantity=quantity,
                        side=side,
                    )
                )
                trade_id += 1
        stats = writer.statistics()
        assert stats["queue_high_watermark"] == 4
        assert stats["queue_pending"] <= 4
        assert stats["queue_full"] >= 1
    finally:
        release.set()
        writer.close()


def _drain_tape(batcher: TapeBatcher) -> list[object]:
    async def drain() -> list[object]:
        while batcher.pending:
            assert await batcher.flush_once()
        return sent

    sent: list[object] = []
    batcher._send = lambda batch: _append_async(sent, batch)
    return asyncio.run(drain())


async def _append_async(target: list[object], value: object) -> None:
    target.append(value)


def test_bt2_o290_tape_accounting_is_identical_with_big_trades_fanout() -> None:
    async def ignore(_value) -> None:
        return None

    stream_id = "123e4567-e89b-12d3-a456-426614174000"
    off = TapeBatcher(
        ignore,
        symbol="BTCUSDT",
        stream_id=stream_id,
        batch_time_mode="event",
        max_trades_per_message=200,
    )
    on = TapeBatcher(
        ignore,
        symbol="BTCUSDT",
        stream_id=stream_id,
        batch_time_mode="event",
        max_trades_per_message=200,
    )
    runtime = _runtime()
    for index in range(1_000):
        trade = _trade(index + 1, index, price="100")
        off.publish(trade)
        runtime.process(trade)
        on.publish(trade)
    off_batches = _drain_tape(off)
    on_batches = _drain_tape(on)
    assert off_batches == on_batches
    assert off.stats_snapshot() == on.stats_snapshot()
    assert on.stats_snapshot()["accounting_balanced"] is True


def _book_updates() -> tuple[OrderBookUpdate, ...]:
    levels_bid = (BookLevel(Decimal("99"), Decimal("1")),)
    levels_ask = (BookLevel(Decimal("101"), Decimal("1")),)
    return (
        OrderBookUpdate(BASE, "BTCUSDT", "SNAPSHOT", None, 100, levels_bid, levels_ask),
        OrderBookUpdate(BASE, "BTCUSDT", "DIFF", 101, 105, levels_bid, ()),
        OrderBookUpdate(BASE, "BTCUSDT", "DIFF", 200, 205, (), ()),
        OrderBookUpdate(BASE, "BTCUSDT", "SNAPSHOT", None, 300, levels_bid, levels_ask),
    )


def test_bt2_o291_book_gap_and_sync_are_identical_with_big_trades_fanout() -> None:
    baseline = OrderBookStateManager("BTCUSDT")
    enabled = OrderBookStateManager("BTCUSDT")
    runtime = _runtime()
    for index, update in enumerate(_book_updates()):
        baseline.apply(update)
        runtime.process(_trade(index + 1, index, price="100"))
        enabled.apply(update)
    assert baseline.snapshot() == enabled.snapshot()
    assert baseline.gaps_detected == enabled.gaps_detected == 1
    assert baseline.snapshots_applied == enabled.snapshots_applied == 2
    assert baseline.diffs_applied == enabled.diffs_applied == 1
    assert baseline.is_synchronized == enabled.is_synchronized is True


def test_bt2_o292_cpu_and_rss_remain_bounded_for_25000_trades() -> None:
    process = psutil.Process()
    runtime = _runtime()
    before_rss = process.memory_info().rss
    before_cpu = sum(process.cpu_times()[:2])
    started = perf_counter_ns()
    for index in range(25_000):
        runtime.process(_trade(index + 1, index, price=str(1 + index % 2)))
    runtime.flush()
    elapsed = (perf_counter_ns() - started) / 1_000_000_000
    after_cpu = sum(process.cpu_times()[:2])
    after_rss = process.memory_info().rss
    stats = runtime.statistics()
    assert stats["trades_observed"] == 25_000
    assert stats["price_path_index_size"] == 25_000
    assert stats["active_zone_count"] <= 5_000
    assert stats["recent_records"] <= 20_000
    assert after_rss - before_rss < 64 * 1024 * 1024
    assert after_cpu - before_cpu <= elapsed * 1.25


def test_bt2_o293_live_soak_is_at_least_120_seconds_and_clean() -> None:
    assert SOAK_EVIDENCE.is_file(), f"missing soak evidence: {SOAK_EVIDENCE}"
    result = json.loads(SOAK_EVIDENCE.read_text(encoding="utf-8"))
    assert result["contract_id"] == "BT2-O293"
    assert result["duration_seconds"] >= 120
    assert result["status"] == "PASS"
    assert result["runtime"]["errors"] == 0
    assert result["runtime"]["storage"]["queue_full"] == 0
    assert result["runtime"]["pending_origins"] == 0
    assert result["runtime"]["pending_updates"] == 0
    assert result["rss_growth_bytes"] < 64 * 1024 * 1024


def _settle(writer: BigTradesBackgroundStorageWriter, runtime: BigTradesRuntimeV2) -> None:
    for _ in range(10):
        writer.join()
        runtime.drain_commit_acks()
        runtime.take_publications()
        stats = runtime.statistics()
        if stats["pending_origins"] == 0 and stats["pending_updates"] == 0:
            return
    raise AssertionError("runtime did not settle")


def test_bt2_o294_restart_recovery_soak_preserves_identity_and_continuity(
    tmp_path: Path,
) -> None:
    settings, activation = _settings_activation("10")
    resolver = FixedActivationSettingsResolver(settings, activation)
    store = BigTradesDuckDbStore(tmp_path / "restart.duckdb")
    writer = BigTradesBackgroundStorageWriter(store)
    runtime = BigTradesRuntimeV2(
        enabled=True,
        mode=RuntimeMode.LIVE,
        symbol="BTCUSDT",
        venue="BINANCE",
        tick_size=Decimal("0.1"),
        settings_resolver=resolver,
        storage_writer=writer,
        artifact_repository=BigTradesArtifactRepository(tmp_path / "artifacts"),
        horizons_seconds=(1,),
    )
    trades: list[BigTradeFill] = []
    try:
        for cycle in range(10):
            offset = cycle * 1_000
            price = str(100 + cycle * 10)
            cycle_trades = [
                _trade(cycle * 3 + 1, offset, price=price, quantity="6", side="BUY"),
                _trade(cycle * 3 + 2, offset + 10, price=price, quantity="6", side="BUY"),
                _trade(cycle * 3 + 3, offset + 100, price=price, quantity="1", side="SELL"),
            ]
            trades.extend(cycle_trades)
            for trade in cycle_trades:
                runtime.process(trade)
        runtime.flush()
        _settle(writer, runtime)
        before = {
            "events": store.count("big_trade_events"),
            "zones": store.count("big_trade_reaction_zones"),
        }
    finally:
        writer.close()

    restarted_store = BigTradesDuckDbStore(tmp_path / "restart.duckdb")
    restarted_writer = BigTradesBackgroundStorageWriter(restarted_store)
    restarted = BigTradesRuntimeV2(
        enabled=True,
        mode=RuntimeMode.LIVE,
        symbol="BTCUSDT",
        venue="BINANCE",
        tick_size=Decimal("0.1"),
        settings_resolver=resolver,
        storage_writer=restarted_writer,
        artifact_repository=BigTradesArtifactRepository(tmp_path / "artifacts"),
        horizons_seconds=(1,),
    )
    try:
        restarted.recover_current_session(
            session_id=BASE.date().isoformat(), source_trades=trades
        )
        _settle(restarted_writer, restarted)
        assert restarted_store.count("big_trade_events") == before["events"]
        assert restarted_store.count("big_trade_reaction_zones") == before["zones"]
        assert restarted.statistics()["restart_recoveries"] == 1
        assert restarted.statistics()["errors"] == 0
        assert restarted.statistics()["source_gap_epochs"] == 1
    finally:
        restarted_writer.close()


def _daily_transition_benchmark(root: Path) -> dict[str, object]:
    settings, activation = _settings_activation("10")
    store = BigTradesDuckDbStore(root / "sessions.duckdb")
    writer = BigTradesBackgroundStorageWriter(store)
    runtime = BigTradesRuntimeV2(
        enabled=True,
        mode=RuntimeMode.LIVE,
        symbol="BTCUSDT",
        venue="BINANCE",
        tick_size=Decimal("0.1"),
        settings_resolver=FixedActivationSettingsResolver(settings, activation),
        storage_writer=writer,
        artifact_repository=BigTradesArtifactRepository(root / "artifacts"),
        horizons_seconds=(1,),
    )
    transition_ms: list[float] = []
    trade_id = 1
    try:
        for day in range(12):
            session = BASE + timedelta(days=day)
            for offset, quantity, side in ((0, "6", "BUY"), (10, "6", "BUY"), (100, "1", "SELL")):
                runtime.process(
                    _trade(
                        trade_id,
                        offset,
                        price=str(100 + day * 10),
                        quantity=quantity,
                        side=side,
                        base=session,
                    )
                )
                trade_id += 1
            _settle(writer, runtime)
            if day < 11:
                next_session = BASE + timedelta(days=day + 1)
                started = perf_counter_ns()
                runtime.process(
                    _trade(
                        trade_id,
                        0,
                        price=str(110 + day * 10),
                        quantity="6",
                        side="BUY",
                        base=next_session,
                    )
                )
                writer.join()
                runtime.drain_commit_acks()
                transition_ms.append((perf_counter_ns() - started) / 1_000_000)
                trade_id += 1
        statistics = runtime.statistics()
        return {
            "transitions": len(transition_ms),
            "p95_ms": _percentile(transition_ms, 0.95),
            "p99_ms": _percentile(transition_ms, 0.99),
            "max_ms": max(transition_ms),
            "errors": statistics["errors"],
            "sessions_source_confirmed": statistics["sessions_source_confirmed"],
        }
    finally:
        writer.close()


def test_bt2_o295_scheduled_session_transition_p99_under_500ms(tmp_path: Path) -> None:
    metrics = _daily_transition_benchmark(tmp_path)
    assert metrics["p99_ms"] <= 500, metrics
    assert metrics["errors"] == 0
    assert metrics["sessions_source_confirmed"] == 11
