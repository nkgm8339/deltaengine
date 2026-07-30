"""Manual offline verification CLI for the Phase 2-1 reconstructor.

No exchange API or WebSocket is used.  The command reads finalized local
depth-history segments, verifies every manifest, reconstructs the book, and
streams interval samples without retaining full state history.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
APPLICATION_ROOT = REPOSITORY_ROOT / "Delta_Engine_Pro4web"
if str(APPLICATION_ROOT) not in sys.path:
    sys.path.insert(0, str(APPLICATION_ROOT))

from src.heatmap.reconstruct import (  # noqa: E402
    DepthHistoryReader,
    DepthReconstructor,
    SegmentIntegrityError,
)


EVENT_KINDS = (
    "SYNC_STARTED",
    "SNAPSHOT_APPLIED",
    "DIFF_APPLIED",
    "GAP_DETECTED",
    "RESYNC_STARTED",
    "SYNC_FAILED",
)


def _positive_int(raw_value: str) -> int:
    if not raw_value.isdecimal():
        raise argparse.ArgumentTypeError("value must be a positive integer")
    value = int(raw_value, 10)
    if value <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return value


def run_check(recording_directory: Path, interval_ms: int) -> tuple[int, dict[str, Any]]:
    started_ns = time.perf_counter_ns()
    directory = Path(recording_directory).resolve()
    result: dict[str, Any] = {
        "recording_directory": str(directory),
        "sample_interval_ms": interval_ms,
        "segment_count": 0,
        "skipped_segment_count": 0,
        "skipped_segments": [],
        "integrity": "NOT_CHECKED",
        "events": {kind: 0 for kind in EVENT_KINDS},
        "counters": {},
        "sample_count": 0,
        "first_sample_time_ms": None,
        "last_sample_time_ms": None,
        "final_last_update_id": None,
        "elapsed_ms": 0,
        "status": "FAIL",
    }

    try:
        reader = DepthHistoryReader(directory)
        segments = reader.segments()
        result["segment_count"] = len(segments)
        result["skipped_segment_count"] = len(reader.skipped_segments)
        result["skipped_segments"] = [
            str(path) for path in reader.skipped_segments
        ]
        result["integrity"] = "PASS"

        reconstructor = DepthReconstructor()
        event_counts: Counter[str] = Counter()
        for event in reconstructor.run(reader.iter_records()):
            event_counts[event.kind] += 1
        result["events"] = {
            kind: event_counts.get(kind, 0) for kind in EVENT_KINDS
        }
        result["counters"] = reconstructor.counters
        final_snapshot = reconstructor.snapshot()
        result["final_last_update_id"] = (
            final_snapshot.last_update_id
            if final_snapshot is not None
            else None
        )

        sample_reader = DepthHistoryReader(directory)
        sampler = DepthReconstructor()
        sample_count = 0
        first_sample_time: int | None = None
        last_sample_time: int | None = None
        for sample_time, _ in sampler.sample_states(
            sample_reader.iter_records(),
            interval_ms=interval_ms,
        ):
            if first_sample_time is None:
                first_sample_time = sample_time
            last_sample_time = sample_time
            sample_count += 1
        result["sample_count"] = sample_count
        result["first_sample_time_ms"] = first_sample_time
        result["last_sample_time_ms"] = last_sample_time

        has_sync_failure = result["events"]["SYNC_FAILED"] != 0
        has_gap = result["events"]["GAP_DETECTED"] != 0
        result["status"] = (
            "PASS"
            if result["integrity"] == "PASS"
            and not has_sync_failure
            and not has_gap
            else "FAIL"
        )
        exit_code = 0 if result["status"] == "PASS" else 3
    except SegmentIntegrityError as exc:
        result["integrity"] = "FAIL"
        result["error_type"] = type(exc).__name__
        result["error"] = str(exc)
        exit_code = 2
    except Exception as exc:  # noqa: BLE001 - manual CLI must report the boundary
        result["error_type"] = type(exc).__name__
        result["error"] = str(exc)
        exit_code = 1

    result["elapsed_ms"] = (time.perf_counter_ns() - started_ns) // 1_000_000
    return exit_code, result


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify and reconstruct finalized local depth-history segments."
        )
    )
    parser.add_argument("recording_dir", type=Path)
    parser.add_argument(
        "--interval-ms",
        type=_positive_int,
        default=1000,
    )
    args = parser.parse_args()

    exit_code, result = run_check(args.recording_dir, args.interval_ms)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
