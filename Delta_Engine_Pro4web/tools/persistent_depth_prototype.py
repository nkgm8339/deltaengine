"""Isolated PD1 format prototype.

This module only encodes caller-supplied fixtures.  It never opens project data,
DuckDB, Parquet, or runtime paths.  zstandard is optional; when unavailable the
prototype uses a clearly labelled deflate fallback for repeatable local tests.
"""
from __future__ import annotations

import hashlib
import json
import struct
import time
import zlib
from dataclasses import dataclass
from typing import Iterable


MAGIC = b"DEPD1\0"


def _compress(data: bytes, level: int = 3) -> tuple[bytes, str]:
    try:
        import zstandard as zstd  # type: ignore
    except ImportError:
        return zlib.compress(data, max(1, min(9, level))), "DEFLATE_FALLBACK"
    return zstd.ZstdCompressor(level=level).compress(data), "ZSTD"


def _decompress(data: bytes, codec: str) -> bytes:
    if codec == "ZSTD":
        import zstandard as zstd  # type: ignore
        return zstd.ZstdDecompressor().decompress(data)
    if codec == "DEFLATE_FALLBACK":
        return zlib.decompress(data)
    raise ValueError(f"unsupported codec: {codec}")


def _canonical(frame: dict) -> bytes:
    return (json.dumps(frame, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _validate(frame: dict) -> None:
    if not isinstance(frame, dict) or not frame.get("book_stream_id"):
        raise ValueError("missing book stream")
    if not isinstance(frame.get("book_sequence"), int) or frame["book_sequence"] < 1:
        raise ValueError("invalid book sequence")
    if frame.get("sync_state") == "SYNCED" and (not frame.get("bids") or not frame.get("asks")):
        raise ValueError("synced frame has no levels")


@dataclass(frozen=True)
class Encoded:
    name: str
    codec: str
    payload: bytes
    source_count: int
    checksum: str


def encode_jsonl(frames: Iterable[dict], level: int = 3) -> Encoded:
    rows = list(frames)
    for frame in rows:
        _validate(frame)
    raw = b"".join(_canonical(frame) for frame in rows)
    payload, codec = _compress(raw, level)
    return Encoded("JSONL_ZSTD", codec, payload, len(rows), hashlib.sha256(raw).hexdigest())


def encode_binary(frames: Iterable[dict], level: int = 3) -> Encoded:
    rows = list(frames)
    for frame in rows:
        _validate(frame)
    raw = MAGIC + b"".join(struct.pack(">I", len(blob)) + blob for blob in (_canonical(f) for f in rows))
    payload, codec = _compress(raw, level)
    return Encoded("BINARY_ZSTD", codec, payload, len(rows), hashlib.sha256(raw).hexdigest())


def encode_keyframe_diff(frames: Iterable[dict], keyframe_every: int = 5, level: int = 3) -> Encoded:
    rows = list(frames)
    records: list[dict] = []
    previous = None
    for index, frame in enumerate(rows):
        _validate(frame)
        if previous is None or index % max(1, keyframe_every) == 0:
            records.append({"kind": "KEYFRAME", "frame": frame})
        else:
            records.append({"kind": "DIFF", "frame": frame, "base_sequence": previous["book_sequence"]})
        previous = frame
    raw = b"".join(_canonical(record) for record in records)
    payload, codec = _compress(raw, level)
    return Encoded(f"KEYFRAME_DIFF_{keyframe_every}", codec, payload, len(rows), hashlib.sha256(raw).hexdigest())


def decode(encoded: Encoded) -> list[dict]:
    raw = _decompress(encoded.payload, encoded.codec)
    if encoded.name == "JSONL_ZSTD":
        rows = [json.loads(line) for line in raw.splitlines() if line]
    elif encoded.name == "BINARY_ZSTD":
        if not raw.startswith(MAGIC):
            raise ValueError("binary magic mismatch")
        cursor, rows = len(MAGIC), []
        while cursor < len(raw):
            size = struct.unpack(">I", raw[cursor : cursor + 4])[0]
            cursor += 4
            rows.append(json.loads(raw[cursor : cursor + size]))
            cursor += size
        if cursor != len(raw):
            raise ValueError("binary tail mismatch")
    elif encoded.name.startswith("KEYFRAME_DIFF_"):
        records = [json.loads(line) for line in raw.splitlines() if line]
        rows, previous = [], None
        for record in records:
            if record["kind"] == "KEYFRAME":
                previous = record["frame"]
            elif record["kind"] == "DIFF":
                if previous is None or record["base_sequence"] != previous["book_sequence"]:
                    raise ValueError("diff base mismatch")
                previous = record["frame"]
            else:
                raise ValueError("unknown record kind")
            rows.append(previous)
    else:
        raise ValueError(f"unsupported format: {encoded.name}")
    if len(rows) != encoded.source_count:
        raise ValueError("record count mismatch")
    return rows


def benchmark(frames: list[dict]) -> list[dict]:
    candidates = [lambda: encode_jsonl(frames), lambda: encode_binary(frames), lambda: encode_keyframe_diff(frames)]
    results = []
    for factory in candidates:
        started = time.perf_counter()
        encoded = factory()
        encode_ms = (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        decoded = decode(encoded)
        decode_ms = (time.perf_counter() - started) * 1000
        results.append({"candidate": encoded.name, "codec": encoded.codec, "source_count": encoded.source_count, "bytes": len(encoded.payload), "encode_ms": encode_ms, "decode_ms": decode_ms, "round_trip": decoded == frames})
    return results
