"""PD2 isolated segment durability and replay contract prototype."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path


MAGIC = b"DEPD-SEGMENT-V1\n"


def _row(frame: dict) -> bytes:
    return (json.dumps(frame, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def write_segment(directory: str | os.PathLike[str], frames: list[dict], stream_id: str) -> dict:
    """Write a self-contained segment to an isolated directory atomically."""
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    body = MAGIC + b"".join(_row(frame) for frame in frames)
    checksum = hashlib.sha256(body).hexdigest()
    final = target / f"segment-{stream_id}.jsonl"
    temp = target / f".{final.name}.tmp"
    with temp.open("wb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, final)
    manifest = {"segment": final.name, "stream_id": stream_id, "first_sequence": frames[0]["book_sequence"] if frames else None, "last_sequence": frames[-1]["book_sequence"] if frames else None, "record_count": len(frames), "byte_count": len(body), "sha256": checksum, "schema_revision": "PD1-PROTOTYPE"}
    (target / f"{final.name}.manifest.json").write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def read_segment(directory: str | os.PathLike[str], manifest: dict) -> list[dict]:
    path = Path(directory) / manifest["segment"]
    body = path.read_bytes()
    if hashlib.sha256(body).hexdigest() != manifest["sha256"]:
        raise ValueError("SEGMENT CHECKSUM MISMATCH")
    if not body.startswith(MAGIC):
        raise ValueError("SEGMENT MAGIC MISMATCH")
    rows = [json.loads(line) for line in body[len(MAGIC) :].splitlines() if line]
    if len(rows) != manifest["record_count"]:
        raise ValueError("SEGMENT RECORD COUNT MISMATCH")
    if rows and (rows[0]["book_sequence"] != manifest["first_sequence"] or rows[-1]["book_sequence"] != manifest["last_sequence"]):
        raise ValueError("SEGMENT SEQUENCE MANIFEST MISMATCH")
    return rows


def replay_segment(directory: str | os.PathLike[str], manifest: dict, live_frames=None) -> list[dict]:
    """Replay only durable segment rows; live_frames is intentionally ignored."""
    del live_frames
    return read_segment(directory, manifest)


def isolated_directory() -> tempfile.TemporaryDirectory:
    return tempfile.TemporaryDirectory(prefix="delta-pd2-")


