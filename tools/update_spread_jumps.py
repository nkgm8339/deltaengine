"""Build trustworthy spread-jump exports from a synced board recording.

The source must contain a depthSnapshot followed by Binance depthUpdate
messages. Diff rows are not complete books, so this tool replays them through
the live pipeline's OrderBookStateManager before calculating best bid, best
ask, and spread.

The command fails closed and leaves existing exports untouched when exact
top-of-book reconstruction is impossible.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Sequence
from zoneinfo import ZoneInfo

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.normalization.normalizer import (  # noqa: E402
    ExchangeProfile,
    NormalizationError,
    normalize_raw_depth,
)
from src.orderflow.orderbook import OrderBookStateManager  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = PROJECT_ROOT / "data" / "recordings" / "btcusdt_board_synced.jsonl"
DEFAULT_JSONL = PROJECT_ROOT / "data" / "recordings" / "spread_jumps.jsonl"
DEFAULT_CSV = PROJECT_ROOT / "data" / "recordings" / "spread_jumps.csv"
DEFAULT_PROFILE = PROJECT_ROOT / "config" / "profiles" / "binance.yaml"

_ZERO = Decimal("0")
_JST = ZoneInfo("Asia/Tokyo")


class BoardStreamError(ValueError):
    """The recording cannot support exact top-of-book reconstruction."""


@dataclass(frozen=True)
class BoardObservation:
    event_time: datetime
    update_type: str
    best_bid: Decimal
    best_ask: Decimal
    spread: Decimal
    ma_window: int
    spread_ma: Decimal
    spread_jump: Decimal
    bids_top: tuple[tuple[Decimal, Decimal], ...]
    asks_top: tuple[tuple[Decimal, Decimal], ...]


@dataclass(frozen=True)
class BoardFrame:
    rows: tuple[BoardObservation, ...]
    depth_rows: int
    snapshots: int
    diffs_applied: int
    diffs_skipped_unsynced: int
    stale_diffs: int
    gaps: int


def _load_profile(path: Path) -> ExchangeProfile:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise BoardStreamError(f"cannot load exchange profile {path}: {exc}") from exc
    return ExchangeProfile.from_dict(raw)


def _mean(values: Sequence[Decimal]) -> Decimal:
    return sum(values, _ZERO) / Decimal(len(values))


def _with_rolling_metrics(
    raw_rows: Iterable[tuple[datetime, str, Decimal, Decimal,
                             tuple[tuple[Decimal, Decimal], ...],
                             tuple[tuple[Decimal, Decimal], ...]]],
    *,
    window: int,
) -> tuple[BoardObservation, ...]:
    spreads: list[Decimal] = []
    rows: list[BoardObservation] = []
    for event_time, update_type, best_bid, best_ask, bids_top, asks_top in raw_rows:
        spread = best_ask - best_bid
        spreads.append(spread)
        spread_ma = _mean(spreads[-window:])
        rows.append(BoardObservation(
            event_time=event_time,
            update_type=update_type,
            best_bid=best_bid,
            best_ask=best_ask,
            spread=spread,
            ma_window=window,
            spread_ma=spread_ma,
            spread_jump=spread - spread_ma,
            bids_top=bids_top,
            asks_top=asks_top,
        ))
    return tuple(rows)


def load_board_frame(
    source: Path,
    *,
    top_n: int = 5,
    window: int = 5,
    profile_path: Path = DEFAULT_PROFILE,
) -> BoardFrame:
    """Reconstruct synchronized board states from a mixed raw JSONL stream."""
    if top_n < 1:
        raise BoardStreamError("top_n must be >= 1")
    if window < 1:
        raise BoardStreamError("window must be >= 1")
    if not source.is_file():
        raise BoardStreamError(f"source file not found: {source}")

    profile = _load_profile(profile_path)
    manager: OrderBookStateManager | None = None
    raw_rows: list[
        tuple[datetime, str, Decimal, Decimal,
              tuple[tuple[Decimal, Decimal], ...],
              tuple[tuple[Decimal, Decimal], ...]]
    ] = []
    depth_rows = 0
    snapshots = 0
    diffs_applied = 0
    diffs_skipped_unsynced = 0
    stale_diffs = 0
    gaps = 0

    try:
        handle = source.open("r", encoding="utf-8")
    except OSError as exc:
        raise BoardStreamError(f"cannot open source {source}: {exc}") from exc

    with handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise BoardStreamError(
                    f"invalid JSON at {source}:{line_number}: {exc.msg}"
                ) from exc
            if not isinstance(raw, dict):
                raise BoardStreamError(
                    f"JSON value at {source}:{line_number} must be an object"
                )

            event_type = raw.get("e")
            if event_type not in {"depthSnapshot", "depthUpdate"}:
                continue
            depth_rows += 1
            try:
                update = normalize_raw_depth(raw, profile)
            except NormalizationError as exc:
                raise BoardStreamError(
                    f"invalid depth row at {source}:{line_number}: {exc.reason}"
                ) from exc

            if manager is None:
                manager = OrderBookStateManager(update.symbol)
            if update.symbol != manager.symbol:
                raise BoardStreamError(
                    f"mixed symbols at {source}:{line_number}: "
                    f"expected {manager.symbol}, got {update.symbol}"
                )

            if update.update_type == "SNAPSHOT":
                result = manager.apply(update)
                if not result.applied:
                    raise BoardStreamError(
                        f"snapshot was rejected at {source}:{line_number}"
                    )
                manager.apply_initial_sync(update.final_update_id)
                snapshots += 1
            else:
                if not manager.is_initialized:
                    diffs_skipped_unsynced += 1
                    continue
                result = manager.apply(update)
                if result.gap_detected:
                    gaps += 1
                    continue
                if not result.applied:
                    stale_diffs += 1
                    continue
                diffs_applied += 1

            snapshot = manager.snapshot()
            if snapshot is None:
                continue
            if not snapshot.bids or not snapshot.asks:
                raise BoardStreamError(
                    f"empty synchronized book at {source}:{line_number}"
                )
            bids_top = tuple(sorted(
                snapshot.bids.items(), key=lambda level: level[0], reverse=True,
            )[:top_n])
            asks_top = tuple(sorted(
                snapshot.asks.items(), key=lambda level: level[0],
            )[:top_n])
            best_bid = bids_top[0][0]
            best_ask = asks_top[0][0]
            if best_bid >= best_ask:
                raise BoardStreamError(
                    f"crossed/locked synchronized book at {source}:{line_number}: "
                    f"best_bid={best_bid} best_ask={best_ask}"
                )
            raw_rows.append((
                update.event_time,
                update.update_type,
                best_bid,
                best_ask,
                bids_top,
                asks_top,
            ))

    if depth_rows == 0:
        raise BoardStreamError(f"no depth rows found in {source}")
    if snapshots == 0:
        raise BoardStreamError(
            f"{source} contains {depth_rows} depth rows but no depthSnapshot; "
            "depthUpdate rows are incremental diffs and cannot establish exact "
            "best bid/ask. Do not use zero-quantity-filtered recordings either, "
            "because quantity=0 is the delete-level instruction."
        )
    if not raw_rows:
        raise BoardStreamError(f"no synchronized board states reconstructed from {source}")

    return BoardFrame(
        rows=_with_rolling_metrics(raw_rows, window=window),
        depth_rows=depth_rows,
        snapshots=snapshots,
        diffs_applied=diffs_applied,
        diffs_skipped_unsynced=diffs_skipped_unsynced,
        stale_diffs=stale_diffs,
        gaps=gaps,
    )


def select_jumps(
    frame: BoardFrame,
    threshold_z: Decimal | str = Decimal("2.0"),
) -> tuple[tuple[BoardObservation, ...], Decimal]:
    try:
        z = Decimal(str(threshold_z))
    except InvalidOperation as exc:
        raise BoardStreamError(f"invalid threshold_z: {threshold_z}") from exc
    if z < _ZERO:
        raise BoardStreamError("threshold_z must be >= 0")

    eligible = tuple(row for row in frame.rows if row.update_type == "DIFF")
    if not eligible:
        raise BoardStreamError("no synchronized depthUpdate rows available for review")
    values = tuple(row.spread_jump for row in eligible)
    mean = _mean(values)
    variance = _mean(tuple((value - mean) ** 2 for value in values))
    threshold = mean + z * variance.sqrt()
    jumps = tuple(row for row in eligible if row.spread_jump > threshold)
    return jumps, threshold


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _levels_json(levels: tuple[tuple[Decimal, Decimal], ...]) -> list[list[str]]:
    return [[_decimal_text(price), _decimal_text(quantity)] for price, quantity in levels]


def _payload(row: BoardObservation) -> dict[str, object]:
    return {
        "event_time": row.event_time.astimezone(_JST).isoformat(),
        "best_bid": _decimal_text(row.best_bid),
        "best_ask": _decimal_text(row.best_ask),
        "spread": _decimal_text(row.spread),
        "ma_window": row.ma_window,
        "spread_ma": _decimal_text(row.spread_ma),
        "spread_jump": _decimal_text(row.spread_jump),
        "bids_top5": _levels_json(row.bids_top),
        "asks_top5": _levels_json(row.asks_top),
    }


def write_jsonl(jumps: Sequence[BoardObservation], output: Path) -> None:
    temporary = output.with_suffix(output.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in jumps:
            handle.write(json.dumps(_payload(row), ensure_ascii=False) + "\n")
    temporary.replace(output)


def write_csv(jumps: Sequence[BoardObservation], output: Path) -> None:
    temporary = output.with_suffix(output.suffix + ".tmp")
    fieldnames = [
        "event_time", "best_bid", "best_ask", "spread", "ma_window",
        "spread_ma", "spread_jump", "bids_top5", "asks_top5",
    ]
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in jumps:
            payload = _payload(row)
            payload["bids_top5"] = json.dumps(payload["bids_top5"], ensure_ascii=False)
            payload["asks_top5"] = json.dumps(payload["asks_top5"], ensure_ascii=False)
            writer.writerow(payload)
    temporary.replace(output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reconstruct a synced order book and update spread-jump exports",
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--window", type=int, default=5, help="moving-average window size")
    parser.add_argument("--threshold-z", default="2.0", help="threshold = mean + z * std")
    parser.add_argument("--top-n", type=int, default=5, help="board levels to export per side")
    args = parser.parse_args(argv)

    try:
        frame = load_board_frame(
            args.source,
            top_n=args.top_n,
            window=args.window,
        )
        jumps, threshold = select_jumps(frame, threshold_z=args.threshold_z)
    except (BoardStreamError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("Existing spread-jump exports were left untouched.", file=sys.stderr)
        return 2

    args.jsonl.parent.mkdir(parents=True, exist_ok=True)
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(jumps, args.jsonl)
    write_csv(jumps, args.csv)

    now = datetime.now(timezone.utc).isoformat()
    print(f"generated_at={now}")
    print(f"source={args.source}")
    print(
        f"depth_rows={frame.depth_rows} snapshots={frame.snapshots} "
        f"diffs_applied={frame.diffs_applied} "
        f"diffs_skipped_unsynced={frame.diffs_skipped_unsynced} "
        f"stale_diffs={frame.stale_diffs} gaps={frame.gaps}"
    )
    print(f"states={len(frame.rows)} jumps={len(jumps)} threshold={threshold}")
    print(f"jsonl={args.jsonl}")
    print(f"csv={args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
