"""Append-only recorder for observed flow-response snapshots.

This module records observations as SHADOW events. It never creates an order
command and never changes the completed flow-response logic.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


class ShadowSignalRecorder:
    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, snapshots: Iterable[object]) -> int:
        rows: list[dict[str, object]] = []
        for snapshot in snapshots:
            raw = asdict(snapshot) if is_dataclass(snapshot) else vars(snapshot)
            row = {
                "recorded_time": datetime.now(timezone.utc).isoformat(),
                "status": "SHADOW",
                "order_created": False,
                "event": _jsonable(raw),
            }
            rows.append(row)
        if not rows:
            return 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        return len(rows)


def _jsonable(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "value"):
        return _jsonable(getattr(value, "value"))
    return value
