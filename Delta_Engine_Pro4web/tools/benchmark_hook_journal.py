"""Reproducible enqueue-latency and compression benchmark for Stage 2A."""

from __future__ import annotations

import argparse
import gzip
import json
import statistics
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.observation.raw_journal import CaptureCampaign
from src.orderflow.hooks.config import (
    CaptureSettings,
    HookObserverConfig,
    HookStorageSettings,
    JournalSettings,
)


def _payload(index: int) -> dict:
    if index % 200 == 0:
        return {
            "e": "forceOrder",
            "E": 1_774_700_000_000 + index,
            "o": {
                "s": "BTCUSDT",
                "S": "SELL" if index % 400 == 0 else "BUY",
                "p": str(118_000 + index % 37),
                "q": f"{1 + (index % 100) / 100:.2f}",
                "T": 1_774_700_000_000 + index,
            },
        }
    if index % 20 == 0:
        return {
            "e": "aggTrade",
            "E": 1_774_700_000_000 + index,
            "s": "BTCUSDT",
            "a": index,
            "p": str(118_000 + index % 37),
            "q": f"{1 + (index % 100) / 100:.2f}",
            "T": 1_774_700_000_000 + index,
            "m": bool(index % 40),
        }
    return {
        "e": "depthUpdate",
        "E": 1_774_700_000_000 + index,
        "s": "BTCUSDT",
        "U": 10_000_000 + index,
        "u": 10_000_000 + index,
        "pu": 9_999_999 + index,
        "b": [[str(117_999 - index % 11), f"{(index % 97) / 10:.1f}"]],
        "a": [[str(118_001 + index % 13), f"{(index % 89) / 10:.1f}"]],
    }


def _percentile(values: list[int], quantile: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, int((len(ordered) - 1) * quantile))
    return ordered[index] / 1000


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--events", type=int, default=20_000)
    args = parser.parse_args()
    if args.events < 1:
        raise SystemExit("--events must be positive")

    config = HookObserverConfig(
        enabled=True,
        capture=CaptureSettings(
            campaign_id=args.campaign_id,
            root=args.root,
            full_capture_days=3,
            liquidation_capture_days=14,
        ),
        journal=JournalSettings(
            queue_depth=max(20_000, args.events),
            compression="xz",
            compression_level=6,
            flush_interval_sec=1,
            min_free_bytes=1,
        ),
        storage=HookStorageSettings(
            enabled=False,
            root=args.root / "unused-hook-storage",
            queue_depth=1,
            batch_size=1,
            flush_interval_sec=1,
        ),
        thresholds_path=Path("config/hook_thresholds.yaml"),
        playbooks_path=Path("config/playbooks.yaml"),
        config_hash="d" * 64,
    )
    campaign = CaptureCampaign.open(config)
    elapsed_ns: list[int] = []
    started = time.perf_counter()
    for index in range(args.events):
        before = time.perf_counter_ns()
        campaign.write(_payload(index))
        elapsed_ns.append(time.perf_counter_ns() - before)
    enqueue_seconds = time.perf_counter() - started
    campaign.close()

    compressed_bytes = 0
    uncompressed_bytes = 0
    for path in campaign.campaign_dir.glob("**/raw-*.jsonl.*"):
        compressed_bytes += path.stat().st_size
        opener = gzip.open if path.suffix == ".gz" else __import__("lzma").open
        with opener(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                uncompressed_bytes += len(chunk)

    stats = campaign.stats()
    output = {
        "events_submitted": args.events,
        "enqueue_seconds": enqueue_seconds,
        "enqueue_events_per_sec": args.events / enqueue_seconds,
        "enqueue_us_mean": statistics.fmean(elapsed_ns) / 1000,
        "enqueue_us_p50": _percentile(elapsed_ns, 0.50),
        "enqueue_us_p95": _percentile(elapsed_ns, 0.95),
        "enqueue_us_p99": _percentile(elapsed_ns, 0.99),
        "enqueue_us_max": max(elapsed_ns) / 1000,
        "compressed_bytes": compressed_bytes,
        "uncompressed_bytes": uncompressed_bytes,
        "compression_ratio": (
            compressed_bytes / uncompressed_bytes if uncompressed_bytes else None
        ),
        "campaign": stats,
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
