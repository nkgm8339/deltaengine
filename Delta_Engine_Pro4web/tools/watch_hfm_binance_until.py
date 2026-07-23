"""Watch the observation CSV until a local deadline and finalize reports.

Observation only. This script does not contain or call any trading function.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path


def parse_deadline(value: str) -> datetime:
    hour_text, minute_text = value.split(":", 1)
    now = datetime.now().astimezone()
    deadline = now.replace(
        hour=int(hour_text), minute=int(minute_text), second=0, microsecond=0
    )
    if deadline <= now:
        deadline += timedelta(days=1)
    return deadline


def process_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def stop_process(pid: int | None) -> None:
    if not process_alive(pid):
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    for _ in range(20):
        if not process_alive(pid):
            return
        time.sleep(0.1)


def start_collector(project: Path) -> subprocess.Popen:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(
        [sys.executable, "-m", "tools.observe_hfm_binance"],
        cwd=project,
        creationflags=creationflags,
    )


def read_new_rows(path: Path, offset: int, pending: str) -> tuple[int, str, list[list[str]]]:
    if not path.exists():
        return offset, pending, []
    size = path.stat().st_size
    if size < offset:
        offset, pending = 0, ""
    with path.open("r", encoding="utf-8", newline="") as handle:
        handle.seek(offset)
        chunk = handle.read()
        offset = handle.tell()
    pending += chunk
    lines = pending.split("\n")
    pending = lines.pop()
    rows = [row for row in csv.reader(lines) if len(row) == 6 and row[0] != "source"]
    return offset, pending, rows


def write_log(handle, payload: dict) -> None:
    handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    handle.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--until", default="05:00", help="Local HH:MM deadline")
    parser.add_argument("--duration-sec", type=int, help="Elapsed-time deadline; avoids frozen wall clocks")
    parser.add_argument("--collector-pid", type=int)
    parser.add_argument("--stale-sec", type=int, default=60)
    parser.add_argument("--poll-sec", type=int, default=60)
    args = parser.parse_args()

    project = Path(__file__).resolve().parents[1]
    data_dir = project / "data" / "latency"
    data_dir.mkdir(parents=True, exist_ok=True)
    csv_path = data_dir / "quotes.csv"
    log_path = data_dir / "watchdog.jsonl"
    done_path = data_dir / "finalization.json"
    deadline = parse_deadline(args.until)
    duration_deadline = time.monotonic() + args.duration_sec if args.duration_sec else None
    collector_pid = args.collector_pid
    collector_process: subprocess.Popen | None = None
    offset = csv_path.stat().st_size if csv_path.exists() else 0
    pending = ""
    now_monotonic = time.monotonic()
    last_seen = {"BINANCE": now_monotonic, "HFM": now_monotonic}
    restarts = 0

    with log_path.open("a", encoding="utf-8") as log:
        write_log(log, {"time": datetime.now().astimezone().isoformat(), "event": "START", "deadline": deadline.isoformat(), "collector_pid": collector_pid})
        while (time.monotonic() < duration_deadline) if duration_deadline is not None else (datetime.now().astimezone() < deadline):
            remaining = (
                duration_deadline - time.monotonic()
                if duration_deadline is not None
                else (deadline - datetime.now().astimezone()).total_seconds()
            )
            sleep_for = min(args.poll_sec, max(1.0, remaining))
            time.sleep(sleep_for)
            offset, pending, rows = read_new_rows(csv_path, offset, pending)
            now_monotonic = time.monotonic()
            counts = {"BINANCE": 0, "HFM": 0}
            for row in rows:
                source = row[0].upper()
                if source in last_seen:
                    last_seen[source] = now_monotonic
                    counts[source] += 1
            stale = [source for source, seen in last_seen.items() if now_monotonic - seen > args.stale_sec]
            if stale or not process_alive(collector_pid):
                stop_process(collector_pid)
                collector_process = start_collector(project)
                collector_pid = collector_process.pid
                restarts += 1
                last_seen = {"BINANCE": now_monotonic, "HFM": now_monotonic}
                event = "RESTART"
            else:
                event = "HEALTHY"
            write_log(log, {"time": datetime.now().astimezone().isoformat(), "event": event, "counts": counts, "stale": stale, "collector_pid": collector_pid, "restarts": restarts})

        stop_process(collector_pid)
        report_outputs: dict[str, str] = {}
        for delay_ms, name in ((1000, "report_1s.json"), (3000, "report_3s.json"), (5000, "report_5s.json")):
            output = data_dir / name
            result = subprocess.run(
                [sys.executable, "-m", "tools.report_hfm_binance", str(csv_path), "--output", str(output), "--entry-delay-ms", str(delay_ms)],
                cwd=project,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                write_log(log, {"time": datetime.now().astimezone().isoformat(), "event": "REPORT_ERROR", "delay_ms": delay_ms, "stderr": result.stderr[-1000:]})
                return result.returncode
            report_outputs[str(delay_ms)] = str(output)

        done = {"completed_at": datetime.now().astimezone().isoformat(), "deadline": deadline.isoformat(), "duration_sec": args.duration_sec, "collector_stopped": not process_alive(collector_pid), "restarts": restarts, "reports": report_outputs}
        done_path.write_text(json.dumps(done, ensure_ascii=False, indent=2), encoding="utf-8")
        write_log(log, {"time": datetime.now().astimezone().isoformat(), "event": "COMPLETE", **done})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
