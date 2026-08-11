"""Generate machine-readable Big Trades V2 phase-6 performance evidence."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.performance.test_big_trades_phase6 import (  # noqa: E402
    _bar_age_run,
    _canvas_benchmark,
    _daily_transition_benchmark,
    _isolated_active_zone_benchmark,
    _isolated_compute_benchmark,
    _mode_switch_benchmark,
    _percentile,
    _tick_age_run,
)


def _browser_merges(iterations: int = 5) -> list[dict[str, object]]:
    command = [
        "node",
        str(ROOT / "tests" / "performance" / "big_trades_browser_benchmark.js"),
        str(ROOT / "webapp" / "static" / "big_trades.js"),
    ]
    results = []
    for _ in range(iterations):
        completed = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        results.append(json.loads(completed.stdout))
    return results


def run() -> dict[str, object]:
    active_zones = {
        str(count): _isolated_active_zone_benchmark(count)
        for count in (10, 100, 1_000, 5_000)
    }
    cluster = _isolated_compute_benchmark("cluster")
    horizon = _isolated_compute_benchmark("horizon")
    browser_runs = _browser_merges()
    browser_values = [float(item["elapsed_ms"]) for item in browser_runs]
    canvas = _canvas_benchmark()
    mode_switch = _mode_switch_benchmark()
    with tempfile.TemporaryDirectory(prefix="bt2-phase6-transition-") as temporary:
        daily_transition = _daily_transition_benchmark(Path(temporary))
    tick_off = asyncio.run(_tick_age_run(False))
    tick_on = asyncio.run(_tick_age_run(True))
    bar_off = asyncio.run(_bar_age_run(False))
    bar_on = asyncio.run(_bar_age_run(True))
    tick_delta = _percentile(tick_on, 0.95) - _percentile(tick_off, 0.95)
    bar_delta = _percentile(bar_on, 0.95) - _percentile(bar_off, 0.95)

    checks = {
        "active_zone_total_p95": all(
            metrics["total_p95_ms"] <= 0.15 for metrics in active_zones.values()
        ),
        "active_zone_total_p99": all(
            metrics["total_p99_ms"] <= 0.40 for metrics in active_zones.values()
        ),
        "boundary_query_p99": all(
            metrics["boundary_p99_ms"] <= 0.25 for metrics in active_zones.values()
        ),
        "cluster_finalize_p99": cluster["p99_ms"] <= 1.50,
        "horizon_finalize_p99": horizon["p99_ms"] <= 1.00,
        "daily_transition_p99": float(daily_transition["p99_ms"]) <= 500,
        "browser_merge": max(browser_values) <= 150,
        "canvas_draw_p95": float(canvas["renderP95Ms"]) <= 8,
        "mode_switch_p99": mode_switch["p99_ms"] <= 100,
        "tick_age_delta_p95": tick_delta <= 1,
        "bar_age_delta_p95": bar_delta <= 1,
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "measurement_scope": "isolated synthetic fixtures; production mutation 0",
        "budgets": {
            "total_per_trade_p95_ms": 0.15,
            "total_per_trade_p99_ms": 0.40,
            "cluster_finalize_p99_ms": 1.50,
            "boundary_query_p99_ms": 0.25,
            "horizon_finalize_p99_ms": 1.00,
            "daily_transition_p99_ms": 500,
            "browser_merge_ms": 150,
            "canvas_draw_p95_ms": 8,
            "mode_switch_ms": 100,
            "tick_bar_age_delta_p95_ms": 1,
        },
        "checks": checks,
        "active_zones": active_zones,
        "cluster_finalize": cluster,
        "horizon_finalize": horizon,
        "daily_transition": daily_transition,
        "browser_merge": {
            "runs": browser_runs,
            "p95_ms": _percentile(browser_values, 0.95),
            "max_ms": max(browser_values),
        },
        "canvas": canvas,
        "mode_switch": mode_switch,
        "off_on_age": {
            "tick_off_p95_ms": _percentile(tick_off, 0.95),
            "tick_on_p95_ms": _percentile(tick_on, 0.95),
            "tick_delta_p95_ms": tick_delta,
            "bar_off_p95_ms": _percentile(bar_off, 0.95),
            "bar_on_p95_ms": _percentile(bar_on, 0.95),
            "bar_delta_p95_ms": bar_delta,
        },
        "production_mutations": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
