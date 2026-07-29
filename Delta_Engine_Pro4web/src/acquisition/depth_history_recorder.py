"""ADR-011準拠 raw depth history recorder.

取得層の raw_recorder タップに接続し、検証済み生WSイベント(@depth差分の
U/u/pu を含む)と適用REST snapshotを到着順のまま append-only JSONL セグメント
として記録する。UI投影・切り詰め・加工は行わない(全量記録の原則)。

設計制約:
- 単一ループasyncio上から同期呼び出しされる前提。スレッド不使用(ADR-003)。
- write() はOSバッファ書き込みのみ。flushは1秒周期。fsyncはセグメント
  クローズ時のみ(R4)。
- クラッシュ時、確定前セグメント(.part)の末尾行は不完全になり得る。
  manifestは確定済みセグメントにのみ存在し、読み出し側は manifest のない
  .part を「末尾不完全許容」で扱う契約とする。
- 価格・数量はBinanceが文字列で送信するため、素通し再直列化でfloatは
  混入しない(R3)。本モジュールは値の型変換を一切行わない。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_FLUSH_INTERVAL_SEC = 1.0
_DEFAULT_MAX_BYTES = 64 * 1024 * 1024
_SCHEMA_REVISION = "RAW_DEPTH_HISTORY_V1"


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")


class DepthHistoryRecorder:
    """Append-only rotating JSONL segment recorder."""

    def __init__(
        self,
        root: str | Path,
        symbol: str,
        max_bytes: int = _DEFAULT_MAX_BYTES,
        flush_interval_sec: float = _FLUSH_INTERVAL_SEC,
        clock=time.monotonic,
    ) -> None:
        self.root = Path(root) / f"symbol={symbol}"
        self.root.mkdir(parents=True, exist_ok=True)
        self.symbol = symbol
        self.max_bytes = max(1, int(max_bytes))
        self.flush_interval_sec = float(flush_interval_sec)
        self._clock = clock
        self._handle = None
        self._part: Path | None = None
        self._hasher = hashlib.sha256()
        self._count = 0
        self._bytes = 0
        self._last_flush = self._clock()
        self._started_at: str | None = None
        self.segments_closed = 0

    @property
    def records_written(self) -> int:
        return self._count

    def _open(self) -> None:
        self._started_at = _utc_stamp()
        self._part = self.root / f"raw_depth.{self._started_at}.jsonl.part"
        self._handle = self._part.open("ab")
        self._hasher = hashlib.sha256()
        self._count = 0
        self._bytes = 0
        self._last_flush = self._clock()

    def write(self, obj: dict) -> None:
        line = (
            json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
        if self._handle is None:
            self._open()
        self._handle.write(line)
        self._hasher.update(line)
        self._count += 1
        self._bytes += len(line)
        now = self._clock()
        if now - self._last_flush >= self.flush_interval_sec:
            self._handle.flush()
            self._last_flush = now
        if self._bytes >= self.max_bytes:
            self._close_segment("rotate")

    def close(self) -> None:
        self._close_segment("close")

    def _close_segment(self, reason: str) -> None:
        if self._handle is None or self._part is None:
            return
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self._handle.close()
        final = self._part.with_suffix("")  # drop ".part"
        os.replace(self._part, final)
        manifest = {
            "schema_revision": _SCHEMA_REVISION,
            "symbol": self.symbol,
            "record_count": self._count,
            "byte_size": self._bytes,
            "sha256": self._hasher.hexdigest(),
            "closed_reason": reason,
            "started_at": self._started_at,
            "closed_at": _utc_stamp(),
        }
        final.with_suffix(final.suffix + ".manifest.json").write_text(
            json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
        )
        self.segments_closed += 1
        self._handle = None
        self._part = None


class SafeRecorder:
    """R5: 記録器障害をmarket dataパスから隔離するラッパー。

    例外発生時は以後の書き込みを停止(fail loudly, no partial append再試行)し、
    エラーを保持してERRORログを出す。呼出元へは決して例外を伝播させない。
    """

    def __init__(self, inner) -> None:
        self._inner = inner
        self.error: str | None = None
        self.disabled = False

    def write(self, obj: dict) -> None:
        if self.disabled:
            return
        try:
            self._inner.write(obj)
        except Exception as exc:  # noqa: BLE001 — 隔離が目的
            self.disabled = True
            self.error = f"{type(exc).__name__}: {exc}"
            logger.error("depth history recorder failed; recording disabled: %s", self.error)
            try:
                self._inner.close()
            except Exception:  # noqa: BLE001
                pass

    def close(self) -> None:
        try:
            self._inner.close()
        except Exception as exc:  # noqa: BLE001
            if self.error is None:
                self.error = f"{type(exc).__name__}: {exc}"
            logger.error("depth history recorder close failed: %s", self.error)


class RecorderTee:
    """複数タップへ同一イベントを配る(hook_captureとの併用用)。closeは行わない。

    各タップのライフサイクル(close)は所有者(main.py lifespan)が管理する。
    """

    def __init__(self, taps) -> None:
        self._taps = [t for t in taps if t is not None]

    def write(self, obj: dict) -> None:
        for tap in self._taps:
            tap.write(obj)
