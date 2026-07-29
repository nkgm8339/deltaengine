"""Production-gated append-only depth segment writer.

Enabled only by PERSISTENT_DEPTH_HISTORY_ENABLED=true.  It is deliberately
separate from the existing DuckDB/Parquet storage writer.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


class PersistentDepthWriter:
    def __init__(self, root: str | Path, symbol: str, max_frames: int = 1000) -> None:
        self.root = Path(root) / f"symbol={symbol}"
        self.root.mkdir(parents=True, exist_ok=True)
        self.symbol = symbol
        self.max_frames = max(1, int(max_frames))
        self._stream_id: str | None = None
        self._part: Path | None = None
        self._handle = None
        self._hasher = hashlib.sha256()
        self._count = 0
        self._first: int | None = None
        self._last: int | None = None

    @property
    def frames_written(self) -> int:
        return self._count

    def _open(self, stream_id: str, sequence: int) -> None:
        self._stream_id = stream_id
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        self._part = self.root / f"stream={stream_id}.start={sequence}.{stamp}.jsonl.part"
        self._handle = self._part.open("wb")
        self._hasher = hashlib.sha256()
        self._count = 0
        self._first = None
        self._last = None

    def append(self, payload: dict) -> None:
        stream_id = str(payload.get("book_stream_id") or "")
        sequence = payload.get("book_sequence")
        if not stream_id or not isinstance(sequence, int) or sequence < 1:
            raise ValueError("invalid persistent depth payload")
        if self._handle is None or self._stream_id != stream_id or self._count >= self.max_frames:
            self.close()
            self._open(stream_id, sequence)
        row = (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        self._handle.write(row)
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self._hasher.update(row)
        self._count += 1
        self._first = sequence if self._first is None else self._first
        self._last = sequence

    def close(self) -> None:
        if self._handle is None or self._part is None:
            return
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self._handle.close()
        final = self._part.with_suffix("")
        os.replace(self._part, final)
        manifest = {
            "symbol": self.symbol,
            "stream_id": self._stream_id,
            "first_sequence": self._first,
            "last_sequence": self._last,
            "record_count": self._count,
            "sha256": self._hasher.hexdigest(),
            "schema_revision": "DEPTH_HISTORY_V1",
        }
        final.with_suffix(final.suffix + ".manifest.json").write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
        self._handle = None
        self._part = None

    def __enter__(self) -> "PersistentDepthWriter":
        return self

    def __exit__(self, *_args) -> None:
        self.close()
