"""Startup configuration check.

Loads and validates a configuration file. Exits non-zero on any failure so
that misconfiguration prevents startup (implementation instruction: invalid
config must fail startup).

Usage:
    python tools/check_config.py config/config.yaml
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the project root importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import ConfigError, load_config  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python tools/check_config.py <config.yaml>", file=sys.stderr)
        return 2
    try:
        config = load_config(argv[1])
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        "Config OK: "
        f"symbol={config.market.symbol} exchange={config.market.exchange} "
        f"bar_timeframe={config.market.bar_timeframe} "
        f"log_level={config.system.log_level}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
