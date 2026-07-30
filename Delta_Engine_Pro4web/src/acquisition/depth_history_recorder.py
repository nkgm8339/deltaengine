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
from typing import Any

from .depth_sync import (
    BOOK_RESYNC,
    INITIAL_BOOK_SYNC,
    DepthSyncAction,
    DepthSyncState,
)

logger = logging.getLogger(__name__)

_FLUSH_INTERVAL_SEC = 1.0
_DEFAULT_MAX_BYTES = 64 * 1024 * 1024
_MAX_BYTES_ENV = "DEPTH_HISTORY_MAX_BYTES"
_SCHEMA_VERSION = 2
_SCHEMA_REVISION = "RAW_DEPTH_HISTORY_V2"


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _non_negative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def resolve_depth_history_max_bytes(
    explicit_max_bytes: int | None = None,
) -> int:
    """Resolve explicit > environment > 64 MiB without float coercion."""

    if explicit_max_bytes is not None:
        return _positive_int("max_bytes", explicit_max_bytes)

    raw_value = os.environ.get(_MAX_BYTES_ENV)
    if raw_value is None:
        return _DEFAULT_MAX_BYTES
    return parse_depth_history_max_bytes(raw_value)


def parse_depth_history_max_bytes(raw_value: str) -> int:
    """Parse the environment representation as a strict positive integer."""

    if not isinstance(raw_value, str):
        raise ValueError(f"{_MAX_BYTES_ENV} must be a positive integer")
    normalized = raw_value.strip()
    if not normalized.isdecimal():
        raise ValueError(f"{_MAX_BYTES_ENV} must be a positive integer")
    return _positive_int(_MAX_BYTES_ENV, int(normalized, 10))


def load_depth_history_manifest(path: str | Path) -> dict[str, Any]:
    """Load V1 or V2 manifest; missing ``schema_version`` means legacy V1."""

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("depth history manifest must be a JSON object")
    version = raw.get("schema_version", 1)
    if isinstance(version, bool) or not isinstance(version, int):
        raise ValueError("manifest schema_version must be an integer")
    if version not in {1, 2}:
        raise ValueError(
            f"unsupported depth history manifest schema_version: {version}"
        )
    manifest = dict(raw)
    manifest["schema_version"] = version
    return manifest


class DepthHistoryRecorder:
    """Append-only rotating JSONL segment recorder."""

    def __init__(
        self,
        root: str | Path,
        symbol: str,
        max_bytes: int | None = None,
        flush_interval_sec: float = _FLUSH_INTERVAL_SEC,
        clock=time.monotonic,
    ) -> None:
        self.root = Path(root) / f"symbol={symbol}"
        self.root.mkdir(parents=True, exist_ok=True)
        self.symbol = symbol
        self.max_bytes = resolve_depth_history_max_bytes(max_bytes)
        self.flush_interval_sec = float(flush_interval_sec)
        self._clock = clock
        self._handle = None
        self._part: Path | None = None
        self._hasher = hashlib.sha256()
        self._count = 0
        self._bytes = 0
        self._last_flush = self._clock()
        self._started_at: str | None = None
        self._rotation_due = False
        self._sync_events: list[dict[str, Any]] = []
        self._sync_failures: list[dict[str, Any]] = []
        self._pending_sync_events: list[dict[str, Any]] = []
        self._pending_sync_failures: list[dict[str, Any]] = []
        self._sync_result_keys: set[tuple[str, int]] = set()
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
        self._rotation_due = False
        self._sync_events = self._pending_sync_events
        self._sync_failures = self._pending_sync_failures
        self._pending_sync_events = []
        self._pending_sync_failures = []

    def write(self, obj: dict) -> None:
        if self._rotation_due:
            self._close_segment("rotate")
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
            self._rotation_due = True

    def record_sync_action(self, action: DepthSyncAction) -> None:
        """Attach one terminal coordinator result to exactly one segment manifest."""

        if not isinstance(action, DepthSyncAction):
            raise TypeError("action must be a DepthSyncAction")
        epoch = _positive_int("sync epoch", action.epoch)
        attempts = _positive_int("sync attempts", action.attempt)
        reason = INITIAL_BOOK_SYNC if epoch == 1 else BOOK_RESYNC

        if action.is_verified:
            if action.snapshot is None or not action.diffs:
                raise ValueError("verified sync action requires snapshot and bridge diff")
            snapshot_u = _non_negative_int(
                "snapshot_u", action.snapshot.get("u")
            )
            bridge = action.diffs[0]
            bridge_U = _non_negative_int("bridge_U", bridge.get("U"))
            bridge_u = _non_negative_int("bridge_u", bridge.get("u"))
            entry = {
                "epoch": epoch,
                "reason": reason,
                "snapshot_u": snapshot_u,
                "bridge_U": bridge_U,
                "bridge_u": bridge_u,
                "sync_verified": True,
                "attempts": attempts,
            }
            self._record_sync_result("verified", epoch, entry)
            return

        if action.state is DepthSyncState.SYNC_FAILED:
            failure_reason = action.failure_reason
            if not isinstance(failure_reason, str) or not failure_reason.strip():
                raise ValueError("SYNC_FAILED action requires a non-empty failure_reason")
            entry = {
                "epoch": epoch,
                "reason": reason,
                "failure_reason": failure_reason,
                "attempts": attempts,
            }
            self._record_sync_result("failed", epoch, entry)
            return

        raise ValueError("only verified or SYNC_FAILED actions can enter manifest V2")

    def _record_sync_result(
        self, result_type: str, epoch: int, entry: dict[str, Any]
    ) -> None:
        key = (result_type, epoch)
        if key in self._sync_result_keys:
            return
        self._sync_result_keys.add(key)
        if result_type == "verified":
            target = (
                self._sync_events
                if self._handle is not None
                else self._pending_sync_events
            )
        else:
            target = (
                self._sync_failures
                if self._handle is not None
                else self._pending_sync_failures
            )
        target.append(entry)

    def close(self) -> None:
        self._close_segment("rotate" if self._rotation_due else "close")

    def _close_segment(self, reason: str) -> None:
        if self._handle is None or self._part is None:
            return
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self._handle.close()
        final = self._part.with_suffix("")  # drop ".part"
        os.replace(self._part, final)
        manifest = {
            "schema_version": _SCHEMA_VERSION,
            "schema_revision": _SCHEMA_REVISION,
            "symbol": self.symbol,
            "record_count": self._count,
            "byte_size": self._bytes,
            "sha256": self._hasher.hexdigest(),
            "closed_reason": reason,
            "started_at": self._started_at,
            "closed_at": _utc_stamp(),
            "sync_events": [dict(entry) for entry in self._sync_events],
            "sync_failures": [dict(entry) for entry in self._sync_failures],
        }
        final.with_suffix(final.suffix + ".manifest.json").write_text(
            json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
        )
        self.segments_closed += 1
        self._handle = None
        self._part = None
        self._rotation_due = False
        self._sync_events = []
        self._sync_failures = []


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

    def record_sync_action(self, action: DepthSyncAction) -> None:
        if self.disabled:
            return
        try:
            self._inner.record_sync_action(action)
        except Exception as exc:  # noqa: BLE001 — 隔離が目的
            self.disabled = True
            self.error = f"{type(exc).__name__}: {exc}"
            logger.error(
                "depth history recorder sync metadata failed; recording disabled: %s",
                self.error,
            )
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
    """複数タップへ同一イベントを配る(hook_captureとの併用用)。

    close() は呼ばれても安全な no-op とする。各タップの実ライフサイクル(close)は
    所有者(main.py lifespan)が個別変数を保持して管理する。Teeを経由した
    二重closeを避けるため、ここでは何も閉じない。
    """

    def __init__(self, taps) -> None:
        self._taps = [t for t in taps if t is not None]

    def write(self, obj: dict) -> None:
        for tap in self._taps:
            tap.write(obj)

    def record_sync_action(self, action: DepthSyncAction) -> None:
        for tap in self._taps:
            callback = getattr(tap, "record_sync_action", None)
            if callback is not None:
                callback(action)

    def close(self) -> None:  # no-op: 所有者が各タップを個別にcloseする
        return
