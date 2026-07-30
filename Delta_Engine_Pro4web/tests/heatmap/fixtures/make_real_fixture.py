"""Build the Phase 2-1 reduced fixture from the pinned validation recording.

Selection contract across the first two source segments:
- every depthSnapshot record
- every depthUpdate record
- the first five trade records in source order

Selected records retain their original UTF-8 JSONL bytes.  Each generated
manifest carries source provenance and recomputed fixture metrics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


EXPECTED_SOURCE_SEGMENTS = (
    (
        "raw_depth.20260729T193154.046959Z.jsonl",
        "58048404f36a7fcb4a2487cb87d8c9a9f95386d624c3d4bccb1c21b227747dd6",
    ),
    (
        "raw_depth.20260729T193201.309417Z.jsonl",
        "1aaf0643344a30338cfb8e7bced642a83751c52a95008c488b91c93e13741a6d",
    ),
)
EXPECTED_TOTAL_COUNTS = {
    "depthSnapshot": 1,
    "depthUpdate": 136,
    "trade": 5,
}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_source_directory() -> Path:
    return (
        _project_root()
        / "data_05M"
        / "phase2_0_d2_validation"
        / "20260730T043059"
        / "depth_history_raw"
        / "symbol=BTCUSDT"
    )


def default_output_directory() -> Path:
    return Path(__file__).resolve().parent / "real_validation"


def build_real_fixture(
    source_directory: Path,
    output_directory: Path,
) -> list[dict[str, Any]]:
    """Generate both reduced JSONL segments and their manifests."""

    source_directory = Path(source_directory)
    output_directory = Path(output_directory)
    if not source_directory.is_dir():
        raise FileNotFoundError(
            f"validation recording directory not found: {source_directory}"
        )

    actual_first_two = tuple(
        path.name
        for path in sorted(source_directory.glob("*.jsonl"), key=lambda p: p.name)[
            :2
        ]
    )
    expected_names = tuple(name for name, _ in EXPECTED_SOURCE_SEGMENTS)
    if actual_first_two != expected_names:
        raise RuntimeError(
            "validation recording first two segments differ from the pinned "
            f"evidence: expected={expected_names!r} actual={actual_first_two!r}"
        )

    output_directory.mkdir(parents=True, exist_ok=True)
    remaining_trades = EXPECTED_TOTAL_COUNTS["trade"]
    total_counts: Counter[str] = Counter()
    results: list[dict[str, Any]] = []

    for source_name, expected_source_sha in EXPECTED_SOURCE_SEGMENTS:
        source_path = source_directory / source_name
        source_manifest_path = Path(f"{source_path}.manifest.json")
        source_manifest = _load_manifest(source_manifest_path)
        source_bytes, source_records, source_sha = _file_metrics(source_path)
        _verify_source(
            source_path=source_path,
            manifest=source_manifest,
            expected_sha=expected_source_sha,
            actual_bytes=source_bytes,
            actual_records=source_records,
            actual_sha=source_sha,
        )

        selected_lines: list[bytes] = []
        selected_counts: Counter[str] = Counter()
        with source_path.open("rb") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                record = _parse_record(source_path, line_number, raw_line)
                kind = record.get("e")
                selected = kind in {"depthSnapshot", "depthUpdate"}
                if kind == "trade" and remaining_trades > 0:
                    selected = True
                    remaining_trades -= 1
                if selected:
                    selected_lines.append(raw_line)
                    selected_counts[str(kind)] += 1
                    total_counts[str(kind)] += 1

        fixture_data = b"".join(selected_lines)
        fixture_path = output_directory / source_name
        _atomic_write(fixture_path, fixture_data)
        fixture_bytes, fixture_records, fixture_sha = _file_metrics(fixture_path)

        fixture_manifest = dict(source_manifest)
        fixture_manifest.update(
            {
                "record_count": fixture_records,
                "byte_size": fixture_bytes,
                "sha256": fixture_sha,
                "_fixture_provenance": {
                    "source_filename": source_name,
                    "source_sha256": source_sha,
                    "source_byte_size": source_bytes,
                    "source_record_count": source_records,
                    "selected_record_counts": dict(sorted(selected_counts.items())),
                    "selection_contract": (
                        "all depthSnapshot + all depthUpdate across the first "
                        "two pinned segments + first 5 trades in source order"
                    ),
                },
            }
        )
        fixture_manifest_path = Path(f"{fixture_path}.manifest.json")
        manifest_data = (
            json.dumps(
                fixture_manifest,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
        _atomic_write(fixture_manifest_path, manifest_data)

        results.append(
            {
                "path": str(fixture_path),
                "manifest_path": str(fixture_manifest_path),
                "record_count": fixture_records,
                "byte_size": fixture_bytes,
                "sha256": fixture_sha,
                "selected_record_counts": dict(sorted(selected_counts.items())),
                "source_filename": source_name,
                "source_sha256": source_sha,
            }
        )

    if remaining_trades != 0:
        raise RuntimeError(
            f"source recording supplied only "
            f"{EXPECTED_TOTAL_COUNTS['trade'] - remaining_trades} selected trades"
        )
    if dict(total_counts) != EXPECTED_TOTAL_COUNTS:
        raise RuntimeError(
            "reduced fixture totals differ from the evidence contract: "
            f"expected={EXPECTED_TOTAL_COUNTS!r} actual={dict(total_counts)!r}"
        )
    return results


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"source manifest not found: {path}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise RuntimeError(f"source manifest must be a JSON object: {path}")
    return manifest


def _file_metrics(path: Path) -> tuple[int, int, str]:
    hasher = hashlib.sha256()
    byte_size = 0
    record_count = 0
    with path.open("rb") as handle:
        for raw_line in handle:
            hasher.update(raw_line)
            byte_size += len(raw_line)
            record_count += 1
    return byte_size, record_count, hasher.hexdigest()


def _verify_source(
    *,
    source_path: Path,
    manifest: dict[str, Any],
    expected_sha: str,
    actual_bytes: int,
    actual_records: int,
    actual_sha: str,
) -> None:
    expected_values = {
        "byte_size": actual_bytes,
        "record_count": actual_records,
        "sha256": actual_sha,
    }
    for key, actual_value in expected_values.items():
        manifest_value = manifest.get(key)
        if key == "sha256":
            if (
                not isinstance(manifest_value, str)
                or manifest_value.lower() != actual_value
            ):
                raise RuntimeError(
                    f"{source_path}: source manifest sha256 mismatch"
                )
        elif manifest_value != actual_value:
            raise RuntimeError(
                f"{source_path}: source manifest {key} mismatch "
                f"(manifest={manifest_value!r} actual={actual_value!r})"
            )
    if actual_sha != expected_sha:
        raise RuntimeError(
            f"{source_path}: pinned source sha256 mismatch "
            f"(expected={expected_sha} actual={actual_sha})"
        )


def _parse_record(path: Path, line_number: int, raw_line: bytes) -> dict[str, Any]:
    def reject_float(raw_value: str) -> None:
        raise ValueError(f"float literal is forbidden: {raw_value}")

    try:
        record = json.loads(raw_line, parse_float=reject_float)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise RuntimeError(f"{path}:{line_number}: invalid source record") from exc
    if not isinstance(record, dict):
        raise RuntimeError(f"{path}:{line_number}: record must be a JSON object")
    return record


def _atomic_write(path: Path, data: bytes) -> None:
    temporary_path = Path(f"{path}.tmp")
    temporary_path.write_bytes(data)
    temporary_path.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate the pinned Phase 2-1 real-data fixture."
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=default_source_directory(),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output_directory(),
    )
    args = parser.parse_args()

    results = build_real_fixture(args.source_dir, args.output_dir)
    print(json.dumps(results, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
