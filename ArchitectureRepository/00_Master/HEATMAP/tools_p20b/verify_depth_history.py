"""Read-only verifier for Phase 2-0-b raw depth-history evidence."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RecordRef:
    segment: str
    line: int
    ordinal: int
    event: str | None
    first_update_id: int | None
    final_update_id: int | None
    previous_final_update_id: int | None
    capture_reason: str | None

    @property
    def location(self) -> str:
        return f"{self.segment}:{self.line}"


def contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, dict):
        return any(contains_float(item) for item in value.values())
    if isinstance(value, list):
        return any(contains_float(item) for item in value)
    return False


def optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    return None


def load_records(data_dir: Path) -> tuple[
    list[Path],
    list[RecordRef],
    dict[str, int],
    list[str],
    list[str],
]:
    segments = sorted(data_dir.glob("*.jsonl"))
    records: list[RecordRef] = []
    line_counts: dict[str, int] = {}
    float_lines: list[str] = []
    json_errors: list[str] = []

    ordinal = 0
    for segment in segments:
        count = 0
        with segment.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                count = line_number
                ordinal += 1
                try:
                    payload = json.loads(raw_line)
                except json.JSONDecodeError as exc:
                    json_errors.append(
                        f"{segment.name}:{line_number}: "
                        f"{exc.msg} (column {exc.colno})"
                    )
                    continue

                if contains_float(payload):
                    float_lines.append(f"{segment.name}:{line_number}")

                records.append(
                    RecordRef(
                        segment=segment.name,
                        line=line_number,
                        ordinal=ordinal,
                        event=payload.get("e"),
                        first_update_id=optional_int(payload.get("U")),
                        final_update_id=optional_int(
                            payload.get("u", payload.get("lastUpdateId"))
                        ),
                        previous_final_update_id=optional_int(payload.get("pu")),
                        capture_reason=payload.get("_capture_reason"),
                    )
                )
        line_counts[segment.name] = count

    return segments, records, line_counts, float_lines, json_errors


def bool_text(value: bool) -> str:
    return "PASS" if value else "FAIL"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "data_dir",
        type=Path,
        help="symbol directory containing raw_depth.*.jsonl segments",
    )
    args = parser.parse_args()
    data_dir = args.data_dir.resolve()

    if not data_dir.is_dir():
        parser.error(f"data directory does not exist: {data_dir}")

    segments, records, line_counts, float_lines, json_errors = load_records(
        data_dir
    )
    updates = [record for record in records if record.event == "depthUpdate"]
    snapshots = [
        record for record in records if record.event == "depthSnapshot"
    ]

    mismatches: list[tuple[RecordRef, RecordRef, bool]] = []
    for previous, current in zip(updates, updates[1:]):
        snapshot_between = any(
            previous.ordinal < snapshot.ordinal < current.ordinal
            for snapshot in snapshots
        )
        if current.previous_final_update_id != previous.final_update_id:
            mismatches.append((previous, current, snapshot_between))

    print("PHASE_2_0_B_DEPTH_HISTORY_VERIFICATION")
    print(f"DATA_DIR: {data_dir}")
    print(f"SEGMENT_COUNT: {len(segments)}")
    for segment in segments:
        print(
            f"SEGMENT: {segment.name} "
            f"bytes={segment.stat().st_size} "
            f"lines={line_counts[segment.name]}"
        )
    print(f"JSON_ERROR_COUNT: {len(json_errors)}")
    for error in json_errors:
        print(f"JSON_ERROR: {error}")

    print(f"DEPTH_UPDATE_COUNT: {len(updates)}")
    print(f"DEPTH_UPDATE_ADJACENT_PAIR_COUNT: {max(0, len(updates) - 1)}")
    print(f"DEPTH_UPDATE_CHAIN_MISMATCH_COUNT: {len(mismatches)}")
    for previous, current, snapshot_between in mismatches:
        print(
            "DEPTH_UPDATE_CHAIN_MISMATCH: "
            f"previous={previous.location} "
            f"previous_u={previous.final_update_id} "
            f"next={current.location} "
            f"next_pu={current.previous_final_update_id} "
            f"snapshot_between={str(snapshot_between).lower()}"
        )

    print(f"SNAPSHOT_COUNT: {len(snapshots)}")
    for snapshot in snapshots:
        following_update = next(
            (
                update
                for update in updates
                if update.ordinal > snapshot.ordinal
            ),
            None,
        )
        if following_update is None or snapshot.final_update_id is None:
            print(
                "SNAPSHOT_CONNECTION: "
                f"snapshot={snapshot.location} "
                f"snapshot_u={snapshot.final_update_id} "
                f"capture_reason={snapshot.capture_reason!r} "
                "next_depth_update=NONE result=FAIL"
            )
            continue
        target = snapshot.final_update_id + 1
        connected = (
            following_update.first_update_id is not None
            and following_update.final_update_id is not None
            and following_update.first_update_id
            <= target
            <= following_update.final_update_id
        )
        print(
            "SNAPSHOT_CONNECTION: "
            f"snapshot={snapshot.location} "
            f"snapshot_u={snapshot.final_update_id} "
            f"capture_reason={snapshot.capture_reason!r} "
            f"next_depth_update={following_update.location} "
            f"next_U={following_update.first_update_id} "
            f"next_u={following_update.final_update_id} "
            f"target={target} result={bool_text(connected)}"
        )

    print(f"SEGMENT_BOUNDARY_COUNT: {max(0, len(segments) - 1)}")
    for previous_segment, next_segment in zip(segments, segments[1:]):
        previous_update = next(
            (
                update
                for update in reversed(updates)
                if update.segment == previous_segment.name
            ),
            None,
        )
        next_update = next(
            (
                update
                for update in updates
                if update.segment == next_segment.name
            ),
            None,
        )
        intervening_snapshot = any(
            snapshot.segment == next_segment.name
            and (
                next_update is None
                or snapshot.ordinal < next_update.ordinal
            )
            for snapshot in snapshots
        )
        if previous_update is None or next_update is None:
            print(
                "SEGMENT_BOUNDARY: "
                f"previous_segment={previous_segment.name} "
                f"next_segment={next_segment.name} "
                "result=NOT_EVALUABLE"
            )
            continue
        connected = (
            next_update.previous_final_update_id
            == previous_update.final_update_id
        )
        print(
            "SEGMENT_BOUNDARY: "
            f"previous_segment={previous_segment.name} "
            f"next_segment={next_segment.name} "
            f"previous_depth_update={previous_update.location} "
            f"previous_u={previous_update.final_update_id} "
            f"next_depth_update={next_update.location} "
            f"next_pu={next_update.previous_final_update_id} "
            f"snapshot_before_next_update={str(intervening_snapshot).lower()} "
            f"result={bool_text(connected)}"
        )

    print(f"FLOAT_NUMBER_LINE_COUNT: {len(float_lines)}")
    for location in float_lines:
        print(f"FLOAT_NUMBER_LINE: {location}")
    print("RESULT: COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
