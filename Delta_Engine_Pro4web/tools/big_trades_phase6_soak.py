"""Run the isolated Big Trades V2 live soak and write JSON evidence."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import psutil

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from src.database.big_trades_storage import (
    BigTradesBackgroundStorageWriter,
    BigTradesDuckDbStore,
)
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
from src.orderflow.big_trades.runtime import (
    BigTradesRuntimeV2,
    FixedActivationSettingsResolver,
    RuntimeMode,
)
from src.orderflow.big_trades.settings import SettingsVersion


UTC = timezone.utc
SOURCE_BASE = datetime(2026, 8, 12, tzinfo=UTC)


def _runtime(root: Path):
    settings = SettingsVersion.create(
        symbol="BTCUSDT",
        venue="BINANCE",
        filter_mode=FilterMode.MANUAL,
        manual_min_quantity="10",
        manual_max_quantity="0",
        automatic_intensity=AutomaticIntensity.MEDIUM,
        side_filter=SideFilter.BOTH,
        marker_price_mode=MarkerPriceMode.LAST_PRICE,
    )
    activation = ActivationArtifact.create(
        symbol="BTCUSDT",
        venue="BINANCE",
        effective_from_event_time=SOURCE_BASE,
        effective_from_trade_id=0,
        settings_id=settings.settings_id,
        calibration_id=None,
        activation_reason=ActivationReason.USER_SETTINGS,
        activation_policy=CalibrationActivationPolicy.MANUAL_ONLY,
        requested_at_utc=SOURCE_BASE,
    )
    store = BigTradesDuckDbStore(root / "big-trades-soak.duckdb")
    writer = BigTradesBackgroundStorageWriter(store, queue_maxsize=10_000)
    runtime = BigTradesRuntimeV2(
        enabled=True,
        mode=RuntimeMode.LIVE,
        symbol="BTCUSDT",
        venue="BINANCE",
        tick_size=Decimal("0.1"),
        settings_resolver=FixedActivationSettingsResolver(settings, activation),
        storage_writer=writer,
        artifact_repository=BigTradesArtifactRepository(root / "artifacts"),
        horizons_seconds=(1, 5),
    )
    return settings, activation, store, writer, runtime


def _settle(writer: BigTradesBackgroundStorageWriter, runtime: BigTradesRuntimeV2) -> None:
    for _ in range(20):
        writer.join()
        runtime.drain_commit_acks()
        runtime.take_publications()
        stats = runtime.statistics()
        if stats["pending_origins"] == 0 and stats["pending_updates"] == 0:
            return
    raise RuntimeError("soak runtime did not settle")


def run(duration_seconds: float, rate_per_second: int) -> dict[str, object]:
    if duration_seconds < 120:
        raise ValueError("phase-6 live soak must run for at least 120 seconds")
    if rate_per_second < 1:
        raise ValueError("rate_per_second must be positive")
    process = psutil.Process()
    trade_count = 0
    with tempfile.TemporaryDirectory(prefix="big-trades-v2-phase6-") as temporary:
        root = Path(temporary)
        settings, activation, store, writer, runtime = _runtime(root)
        rss_before = process.memory_info().rss
        cpu_before = sum(process.cpu_times()[:2])
        wall_started = datetime.now(UTC)
        started = time.perf_counter()
        peak_rss = rss_before
        try:
            interval = 1 / rate_per_second
            while True:
                elapsed = time.perf_counter() - started
                if elapsed >= duration_seconds:
                    break
                slot = trade_count % rate_per_second
                cycle = trade_count // rate_per_second
                if slot in (0, 1):
                    side, quantity = "BUY", Decimal("6")
                else:
                    side, quantity = "SELL", Decimal("0.001")
                source_time = SOURCE_BASE + timedelta(
                    microseconds=int(trade_count * 1_000_000 / rate_per_second)
                )
                trade = BigTradeFill(
                    event_time=source_time,
                    trade_time=source_time,
                    trade_id=trade_count + 1,
                    symbol="BTCUSDT",
                    venue="BINANCE",
                    price=Decimal(100 + cycle * 10),
                    quantity=quantity,
                    side=side,
                )
                runtime.process(trade)
                trade_count += 1
                if trade_count % rate_per_second == 0:
                    peak_rss = max(peak_rss, process.memory_info().rss)
                deadline = started + trade_count * interval
                remaining = deadline - time.perf_counter()
                if remaining > 0:
                    time.sleep(remaining)
            runtime.flush()
            _settle(writer, runtime)
            runtime_stats = runtime.statistics()
            table_counts = {
                table: store.count(table)
                for table in (
                    "big_trade_events",
                    "big_trade_event_fills",
                    "big_trade_reaction_zones",
                    "big_trade_zone_interactions",
                    "big_trade_result_snapshots",
                    "big_trade_zone_state_checkpoints",
                )
            }
        finally:
            writer.close()
    ended = time.perf_counter()
    wall_ended = datetime.now(UTC)
    rss_after = process.memory_info().rss
    peak_rss = max(peak_rss, rss_after)
    cpu_after = sum(process.cpu_times()[:2])
    duration = ended - started
    passed = (
        duration >= 120
        and runtime_stats["errors"] == 0
        and runtime_stats["invalid_trades"] == 0
        and runtime_stats["storage"]["queue_full"] == 0
        and runtime_stats["pending_origins"] == 0
        and runtime_stats["pending_updates"] == 0
        and runtime_stats["trades_observed"] == trade_count
        and peak_rss - rss_before < 64 * 1024 * 1024
    )
    return {
        "contract_id": "BT2-O293",
        "status": "PASS" if passed else "FAIL",
        "started_at_utc": wall_started.isoformat(),
        "ended_at_utc": wall_ended.isoformat(),
        "duration_seconds": duration,
        "requested_duration_seconds": duration_seconds,
        "rate_per_second": rate_per_second,
        "trade_count": trade_count,
        "cpu_seconds": cpu_after - cpu_before,
        "rss_before_bytes": rss_before,
        "rss_after_bytes": rss_after,
        "rss_peak_bytes": peak_rss,
        "rss_growth_bytes": peak_rss - rss_before,
        "runtime": runtime_stats,
        "table_counts": table_counts,
        "settings_id": settings.settings_id,
        "activation_id": activation.activation_id,
        "storage": "temporary isolated DuckDB deleted after read-back",
        "production_mutations": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration-seconds", type=float, default=120)
    parser.add_argument("--rate-per-second", type=int, default=100)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.duration_seconds, args.rate_per_second)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
