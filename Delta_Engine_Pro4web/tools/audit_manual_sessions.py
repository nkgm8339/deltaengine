"""Read-only session audit for the manual HFM execution ledger."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from src.orderflow.manual_execution_ledger import load_records


def session_id(value: datetime) -> str:
    hour = value.astimezone(timezone.utc).hour
    if hour <= 7:
        return "ASIA"
    if hour <= 12:
        return "EUROPE"
    if hour <= 16:
        return "EUROPE_NY_OVERLAP"
    if hour <= 21:
        return "NEW_YORK"
    return "LATE"


def audit(path: Path) -> dict[str, object]:
    records = load_records(path)
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for record in records:
        counts[session_id(record.signal_displayed_time)][record.status.value] += 1
    return {
        "ledger": str(path),
        "record_count": len(records),
        "by_session": {
            key: dict(sorted(value.items()))
            for key, value in sorted(counts.items())
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.ledger), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
