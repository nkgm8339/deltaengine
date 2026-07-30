# 指示書_Heatmap_Phase1_実装_P1-1_v1
**作成日: 2026-07-29 / 発行: Claude(統括) / 対象: Claude Code**
**前提: P1-0提出物(SHA-256付き現物)を統括が検証済み。ベースラインはコミット`1ebdc7b`+既存Mファイル9件。**

---

## 1. 設計決定(統括確定。変更禁止)

| ID | 決定 | 根拠(P1-0提出物) |
|---|---|---|
| D1 | 記録は取得層の`raw_recorder`タップに接続する。UI投影経路(`PersistentDepthWriter`←`push_broker`)は使わない | pipeline.py:1144-1189で検証済み生WSイベント+適用REST snapshotが到着順で流れる。receiver.py:99-100 |
| D2 | `webapp/persistent_depth_writer.py`は流用しない(P1-0-c全項目不適合/要修正)。撤去は後続タスクとし、本指示書では休眠のまま触らない | P1-0-c評価表 |
| D3 | 既存`JsonlRecorder`も流用しない(`open("w")`切り詰め、rotation/manifest/fsyncなし) | receiver.py:36-47 |
| D4 | 新規記録器は「バッファ書き込み+1秒周期flush、fsyncはセグメントクローズ時のみ、サイズローテーション+manifest」。すべて単一ループ上、スレッド不使用 | R4、ADR-003 |
| D5 | 記録器障害はSafeラッパーで隔離し、以後の書き込みを停止してエラー保持。market dataパスへ例外を伝播させない | R5 |
| D6 | 生イベントは素通し記録(価格・数量はBinanceが文字列で送るため、json再直列化でfloatは混入しない)。加工・投影・切り詰め禁止 | R1、R3 |
| D7 | REST snapshotレコードが記録ストリーム中のreset/sync境界マーカーを兼ねる(gap時はsupervisorがsnapshot再取得→同タップへ流れる)。orderbook.py:233-242のlenient sync問題は読み出し側課題としてPhase 1記録層から分離 | pipeline.py:1155-1157、R2 |
| D8 | 有効化フラグは`DEPTH_HISTORY_ENABLED`(既定false)。ライブでの実記録開始は後続の手動確認タスク(P1-2)とし、本指示書ではテストのみ | R7、R8 |

---

## 2. Task 1: 新規ファイル作成(sandbox制約の影響なし)

### 2-1. `Delta_Engine_Pro4web/src/acquisition/depth_history_recorder.py`(新規・全文)

```python
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
```

### 2-2. `Delta_Engine_Pro4web/tests/acquisition/test_depth_history_recorder.py`(新規・全文)

```python
"""depth_history_recorder のfixture駆動テスト。ライブ接続禁止(R8)。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.acquisition.depth_history_recorder import (
    DepthHistoryRecorder,
    RecorderTee,
    SafeRecorder,
)

DEPTH_EVENT = {
    "e": "depthUpdate", "E": 1722200000000, "T": 1722200000001, "s": "BTCUSDT",
    "U": 100, "u": 105, "pu": 99,
    "b": [["50000.10", "1.234"]], "a": [["50000.20", "0.500"]],
}
SNAPSHOT_EVENT = {
    "lastUpdateId": 99,
    "bids": [["50000.00", "2.000"]], "asks": [["50000.30", "1.000"]],
}


def _read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_passthrough_preserves_strings(tmp_path):
    rec = DepthHistoryRecorder(tmp_path, "BTCUSDT")
    rec.write(DEPTH_EVENT)
    rec.write(SNAPSHOT_EVENT)
    rec.close()
    finals = sorted((tmp_path / "symbol=BTCUSDT").glob("*.jsonl"))
    assert len(finals) == 1
    rows = _read_jsonl(finals[0])
    assert rows[0]["b"] == [["50000.10", "1.234"]]  # 文字列のまま(R3)
    assert rows[0]["pu"] == 99                      # 生フィールド保持(R1/R2)
    assert rows[1]["lastUpdateId"] == 99            # snapshot素通し(D7)
    assert not any(
        isinstance(v, float) for row in rows for v in _flatten(row)
    )


def _flatten(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _flatten(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _flatten(v)
    else:
        yield obj


def test_manifest_matches_content(tmp_path):
    rec = DepthHistoryRecorder(tmp_path, "BTCUSDT")
    rec.write(DEPTH_EVENT)
    rec.close()
    root = tmp_path / "symbol=BTCUSDT"
    final = next(root.glob("*.jsonl"))
    manifest = json.loads(final.with_suffix(final.suffix + ".manifest.json").read_text())
    assert manifest["record_count"] == 1
    assert manifest["closed_reason"] == "close"
    assert manifest["schema_revision"] == "RAW_DEPTH_HISTORY_V1"
    assert manifest["sha256"] == hashlib.sha256(final.read_bytes()).hexdigest()
    assert manifest["byte_size"] == final.stat().st_size


def test_rotation_by_size(tmp_path):
    rec = DepthHistoryRecorder(tmp_path, "BTCUSDT", max_bytes=10)
    rec.write(DEPTH_EVENT)   # 1件でmax_bytes超過→rotate
    rec.write(DEPTH_EVENT)
    rec.close()
    root = tmp_path / "symbol=BTCUSDT"
    finals = sorted(root.glob("*.jsonl"))
    assert len(finals) == 2
    reasons = sorted(
        json.loads(f.with_suffix(f.suffix + ".manifest.json").read_text())["closed_reason"]
        for f in finals
    )
    assert reasons == ["close", "rotate"]
    assert not list(root.glob("*.part"))


def test_flush_is_periodic_not_per_write(tmp_path):
    t = {"now": 0.0}
    rec = DepthHistoryRecorder(tmp_path, "BTCUSDT", clock=lambda: t["now"])
    flushes = {"n": 0}
    rec.write(DEPTH_EVENT)  # open
    orig_flush = rec._handle.flush
    rec._handle.flush = lambda: (flushes.__setitem__("n", flushes["n"] + 1), orig_flush())[1]
    rec.write(DEPTH_EVENT)          # t=0: 周期未達→flushなし
    assert flushes["n"] == 0
    t["now"] = 1.5
    rec.write(DEPTH_EVENT)          # 周期到達→flush 1回
    assert flushes["n"] == 1


def test_safe_recorder_isolates_failure(tmp_path):
    class Boom:
        def write(self, obj):
            raise OSError("disk gone")

        def close(self):
            pass

    safe = SafeRecorder(Boom())
    safe.write(DEPTH_EVENT)   # 例外は伝播しない(R5)
    assert safe.disabled is True
    assert "disk gone" in safe.error
    safe.write(DEPTH_EVENT)   # 以後は静かにno-op
    safe.close()


def test_tee_writes_to_all_taps(tmp_path):
    seen = []

    class Tap:
        def __init__(self, name):
            self.name = name

        def write(self, obj):
            seen.append(self.name)

    RecorderTee([Tap("a"), None, Tap("b")]).write(DEPTH_EVENT)
    assert seen == ["a", "b"]
```

`tests/acquisition/` に `__init__.py` が必要な構成であれば空ファイルを新規作成する(既存テストツリーの慣例に合わせる)。

---

## 3. Task 2: 既存ファイル編集(アンカー付きbefore/after)

**sandbox制約**: 既存ファイル編集が現在も拒否される場合、この3編集を1つのgit適用可能パッチ `ArchitectureRepository/00_Master/HEATMAP/P1-1_wiring.patch`(新規ファイル)として出力し、手動適用手順を添えて停止・報告する。編集可能なら直接適用する。

### 3-1. `webapp/main.py` — import追加

既存の `PersistentDepthWriter` をimportしている行を特定し(行番号を報告に記載)、その直後に追加:

```python
from src.acquisition.depth_history_recorder import (
    DepthHistoryRecorder,
    RecorderTee,
    SafeRecorder,
)
```

importパスは既存mainのimport規約(相対/絶対)に合わせ、変えた場合は報告する。

### 3-2. `webapp/main.py` — recorder生成(lifespan内)

before(アンカー、main.py:119-121):
```python
    persistent_enabled = os.getenv("PERSISTENT_DEPTH_HISTORY_ENABLED", "false").lower() == "true"
    persistent_writer = PersistentDepthWriter(os.getenv("PERSISTENT_DEPTH_HISTORY_ROOT", "data_05M/depth_history"), config.market.symbol) if persistent_enabled else None
```

after:
```python
    persistent_enabled = os.getenv("PERSISTENT_DEPTH_HISTORY_ENABLED", "false").lower() == "true"
    persistent_writer = PersistentDepthWriter(os.getenv("PERSISTENT_DEPTH_HISTORY_ROOT", "data_05M/depth_history"), config.market.symbol) if persistent_enabled else None
    depth_history_enabled = os.getenv("DEPTH_HISTORY_ENABLED", "false").lower() == "true"
    depth_history_recorder = (
        SafeRecorder(
            DepthHistoryRecorder(
                os.getenv("DEPTH_HISTORY_ROOT", "data_05M/depth_history_raw"),
                config.market.symbol,
            )
        )
        if depth_history_enabled
        else None
    )
```

### 3-3. `webapp/main.py` — rawタップ接続

before(アンカー、main.py:359-361):
```python
        pipeline_task = asyncio.create_task(
            pipeline.run_async(raw_recorder=hook_capture)
        )
```

after:
```python
        _raw_taps = [t for t in (hook_capture, depth_history_recorder) if t is not None]
        _raw_tap = _raw_taps[0] if len(_raw_taps) == 1 else (RecorderTee(_raw_taps) if _raw_taps else None)
        pipeline_task = asyncio.create_task(
            pipeline.run_async(raw_recorder=_raw_tap)
        )
```

### 3-4. `webapp/main.py` — shutdownでclose

before(アンカー、main.py:568-570):
```python
        if persistent_writer is not None:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(persistent_writer.close)
```

after:
```python
        if persistent_writer is not None:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(persistent_writer.close)
        if depth_history_recorder is not None:
            with contextlib.suppress(Exception):
                depth_history_recorder.close()
```

(closeは直接呼び出し。to_thread禁止(ADR-003)。shutdown時の1回のfsyncは許容)

### 3-5. `docker-compose.yml` — R7矛盾解消+新フラグ

対象3行(PD4コメント行〜ROOT行)は**行末にCR(\r)が混入している**(P1-0提出物で確認済み)。編集時はCR除去を含めてLFに正規化する。

before(アンカー):
```yaml
      # PD4 compatibility boundary: persistent writer remains disabled.
      - PERSISTENT_DEPTH_HISTORY_ENABLED=true
      - PERSISTENT_DEPTH_HISTORY_ROOT=/app/data_05M/depth_history
```

after:
```yaml
      # 旧persistent writer(UI投影系)は無効。コメントと値の矛盾を解消(R7)。
      - PERSISTENT_DEPTH_HISTORY_ENABLED=false
      - PERSISTENT_DEPTH_HISTORY_ROOT=/app/data_05M/depth_history
      # ADR-011 raw depth history(取得層タップ)。有効化はP1-2で判断。
      - DEPTH_HISTORY_ENABLED=false
      - DEPTH_HISTORY_ROOT=/app/data_05M/depth_history_raw
```

---

## 4. Task 3: テスト実行

```
python -m pytest -q -p no:cacheprovider tests/acquisition/test_depth_history_recorder.py
python -m pytest -q -p no:cacheprovider
```

- 新規テストが全pass、既存スイートに新規failが出ないこと(実行前後のpass/fail数を報告)
- 統制ルール適用: 同一失敗2回で停止・報告。ライブ接続禁止

Task 2がパッチ出力(手動適用待ち)になった場合、全体スイートは新規テスト単体のみ実行し、配線後の全体実行は適用後に行う。

---

## 5. 受入基準

1. 新規テスト全pass、既存スイートに退行なし
2. `DEPTH_HISTORY_ENABLED`未設定時、動作が現行と完全に同一(recorder生成なし、raw_recorder=hook_captureのまま)
3. writerの毎フレームfsyncが新経路に存在しない(コード上明示)
4. コミットは1つ: `feat(depth-history): ADR-011 raw depth recorder (P1-1)` (パッチ待ちの場合は新規ファイルのみでコミットし、その旨報告)

## 6. 報告フォーマット

```
[完了/失敗/停止] 指示書_Heatmap_Phase1_実装_P1-1_v1
- 作成ファイル一覧
- 既存編集: 直接適用/パッチ出力 のどちらか。importアンカー行番号
- テスト結果: 新規 x passed / 全体 before→after
- コミットハッシュ
## 逸脱事項
```

## 7. 禁止事項

- ライブ接続、`DEPTH_HISTORY_ENABLED=true`での起動(P1-2で統括が判断)
- `PersistentDepthWriter`本体・呼出箇所の撤去(後続タスク)
- 指定外のファイル変更、push、Phase 2着手
