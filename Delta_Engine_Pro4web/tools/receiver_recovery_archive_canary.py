"""Run a real Binance public-data integration canary for receiver recovery."""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.recover_receiver_trades import (  # noqa: E402
    DEFAULT_ARCHIVE_BASE_URL,
    IncidentSpec,
    RecoveryError,
    TradeIdRange,
    _download_file,
    read_binance_trade_archive,
    sha256_file,
    stage_rest_rows,
    verify_archive_checksum,
)


UTC = timezone.utc


def _first_consecutive_ids(archive_path: Path, count: int = 3) -> tuple[int, ...]:
    with zipfile.ZipFile(archive_path) as archive:
        members = [
            item
            for item in archive.infolist()
            if not item.is_dir() and item.filename.lower().endswith(".csv")
        ]
        if len(members) != 1:
            raise RecoveryError("Binance trade archive must contain exactly one CSV")
        ids: list[int] = []
        with archive.open(members[0], "r") as binary:
            text = io.TextIOWrapper(binary, encoding="utf-8-sig", newline="")
            for line_number, fields in enumerate(csv.reader(text), start=1):
                if not fields:
                    continue
                try:
                    trade_id = int(fields[0])
                except ValueError:
                    if line_number == 1:
                        continue
                    raise RecoveryError(
                        f"invalid archive trade ID at CSV line {line_number}"
                    )
                ids.append(trade_id)
                if len(ids) == count:
                    break
    if len(ids) != count or ids != list(range(ids[0], ids[0] + count)):
        raise RecoveryError("archive does not start with consecutive individual trade IDs")
    return tuple(ids)


def run_canary(
    *,
    archive_date: str,
    output_dir: Path,
    archive_base_url: str = DEFAULT_ARCHIVE_BASE_URL,
) -> dict[str, Any]:
    try:
        day = datetime.strptime(archive_date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise RecoveryError("archive date must be YYYY-MM-DD") from exc
    output = output_dir.resolve()
    if output.exists():
        raise RecoveryError(f"canary output already exists: {output}")
    filename = f"BTCUSDT-trades-{day.isoformat()}.zip"
    url = f"{archive_base_url.rstrip('/')}/BTCUSDT/{filename}"

    with tempfile.TemporaryDirectory(prefix="receiver-recovery-real-canary-") as temporary:
        temporary_root = Path(temporary)
        archive_path = temporary_root / filename
        checksum_path = temporary_root / f"{filename}.CHECKSUM"
        _download_file(url, archive_path, timeout_seconds=90.0, max_retries=2)
        _download_file(
            f"{url}.CHECKSUM",
            checksum_path,
            timeout_seconds=30.0,
            max_retries=2,
        )
        archive_sha256 = verify_archive_checksum(archive_path, checksum_path)
        ids = _first_consecutive_ids(archive_path)
        spec = IncidentSpec(
            schema_version=1,
            incident_id=f"real-archive-canary-{day.isoformat()}",
            symbol="BTCUSDT",
            expected_trade_count=len(ids),
            ranges=(TradeIdRange(ids[0], ids[-1]),),
        )
        rows = read_binance_trade_archive(archive_path, spec)
        stage_dir = output / "stage"
        stage_manifest = stage_rest_rows(
            spec=spec,
            raw_rows=rows,
            output_dir=stage_dir,
            source=f"BINANCE_PUBLIC_DATA:{url}#sha256={archive_sha256}",
            accept_event_time_surrogate=True,
        )

    report = {
        "artifact_type": "RECEIVER_RECOVERY_REAL_ARCHIVE_CANARY",
        "status": "PASS",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "archive": {
            "date": day.isoformat(),
            "url": url,
            "sha256": archive_sha256,
        },
        "real_trade_ids": list(ids),
        "trade_count": len(rows),
        "mapping": {
            "prices": [str(row["price"]) for row in rows],
            "quantities": [str(row["qty"]) for row in rows],
            "trade_times_epoch_ms": [int(row["time"]) for row in rows],
            "is_buyer_maker": [bool(row["isBuyerMaker"]) for row in rows],
        },
        "stage": {
            "manifest_sha256": sha256_file(stage_dir / "manifest.json"),
            "raw_sha256": stage_manifest["raw_file"]["sha256"],
            "canonical_sha256": stage_manifest["canonical_file"]["sha256"],
            "trade_count": stage_manifest["trade_count"],
        },
        "production_mutations": 0,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "canary-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archive-base-url", default=DEFAULT_ARCHIVE_BASE_URL)
    args = parser.parse_args()
    report = run_canary(
        archive_date=args.date,
        output_dir=args.output,
        archive_base_url=args.archive_base_url,
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
