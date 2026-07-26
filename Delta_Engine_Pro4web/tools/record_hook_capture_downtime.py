"""Append a verified Hook capture downtime interval without rewriting metadata."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.observation.capture_coverage import CaptureCoverageLedger


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-dir", type=Path, required=True)
    parser.add_argument("--stream", choices=("full", "liquidation"), required=True)
    parser.add_argument("--started-at", type=_time, required=True)
    parser.add_argument("--ended-at", type=_time, required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()

    meta = json.loads(
        (args.campaign_dir / "campaign_meta.json").read_text(encoding="utf-8")
    )
    ledger = CaptureCoverageLedger(
        args.campaign_dir,
        original_deadlines={
            "full": datetime.fromisoformat(meta["full_capture_until"]),
            "liquidation": datetime.fromisoformat(meta["liquidation_capture_until"]),
        },
        extension_caps={
            "full": timedelta(hours=72),
            "liquidation": timedelta(days=7),
        },
    )
    appended = ledger.record_extension(
        args.stream,
        started_at=args.started_at,
        ended_at=args.ended_at,
        reason=args.reason,
        evidence={"source": "operator_verified_checkpoint"},
    )
    print(
        json.dumps(
            {
                "appended": appended,
                "stream": args.stream,
                **ledger.stats()[args.stream],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
