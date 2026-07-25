"""Validate one manual execution JSON object and append it to a JSONL ledger."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.orderflow.manual_execution_ledger import append_record, decode_record


def append_json_text(ledger: Path, text: str) -> str:
    payload = json.loads(text)
    record = decode_record(json.dumps(payload, ensure_ascii=False))
    append_record(ledger, record)
    return record.record_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--record", type=Path, help="JSON record file; omit to read stdin")
    args = parser.parse_args(argv)
    text = args.record.read_text(encoding="utf-8") if args.record else sys.stdin.read()
    try:
        record_id = append_json_text(args.ledger, text)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps({"appended": True, "record_id": record_id}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
