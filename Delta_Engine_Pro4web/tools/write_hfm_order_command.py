"""Validate and atomically publish one MT5 test-order command."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def build_command(payload: dict[str, object]) -> str:
    command_id = str(payload.get("command_id", "")).strip()
    side = str(payload.get("side", "")).strip().upper()
    stop_loss = float(payload.get("stop_loss", 0))
    take_profit = float(payload.get("take_profit", 0))
    if not command_id:
        raise ValueError("command_id is required")
    if side not in {"BUY", "SELL"}:
        raise ValueError("side must be BUY or SELL")
    if stop_loss <= 0:
        raise ValueError("stop_loss must be positive")
    if take_profit < 0:
        raise ValueError("take_profit must be zero or positive")
    return f"{command_id}|{side}|{stop_loss:.8f}|{take_profit:.8f}\n"


def publish(path: Path, payload: dict[str, object]) -> None:
    command = build_command(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(command, encoding="utf-8", newline="")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--command-file", type=Path, required=True)
    parser.add_argument("--payload", type=Path, required=True)
    args = parser.parse_args()
    publish(args.command_file, json.loads(args.payload.read_text(encoding="utf-8")))
    print(args.command_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
