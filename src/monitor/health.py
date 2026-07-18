"""SelfMonitor v1 — HealthMonitor (自己監視).

DE が自分の異常を検知する。監視対象 6 種 (承認済み仕様):

    1. SEQUENCE_GAP        — order book の update_id ギャップ増加
    2. BAR_MISSING         — bar_timeframe + 許容秒 を超えて bar close が来ない
    3. WS_RECONNECT        — WebSocket 再接続回数の増加 (時間窓内)
    4. PROCESSING_LATENCY  — 最終イベント時刻と壁時計の乖離 (ms)
    5. MEMORY_RSS          — プロセス常駐メモリ (MB)
    6. PIPELINE_EXCEPTION  — pipeline タスクの異常終了 / 例外カウント増加

状態は GREEN / YELLOW / RED の 3 段階。全チェックの最悪値が全体状態。
異常は JSONL (日次ローテーション: anomalies_YYYYMMDD.jsonl) に追記される。

設計原則:
- 純粋な評価器: evaluate(snapshot) は与えられた値のみで判定する。
  収集 (pipeline からの値取り出し) は webapp 側の責務。
- float() 不使用。時間差は timedelta → 整数 ms、メモリは整数 MB。
- カウンタ系 (gap / reconnect / exception) は時間窓 (window_min) 内の増分で判定し、
  古い増分は判定から外れる (一度の再接続で永遠に YELLOW にならない)。
- ログ書き込み失敗は監視自体を止めない (warning のみ)。
"""
from __future__ import annotations

import json
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("monitor.health")

GREEN = "GREEN"
YELLOW = "YELLOW"
RED = "RED"

_LEVEL_ORDER = {GREEN: 0, YELLOW: 1, RED: 2}

# Anomaly type identifiers (仕様 §1)
SEQUENCE_GAP = "SEQUENCE_GAP"
BAR_MISSING = "BAR_MISSING"
WS_RECONNECT = "WS_RECONNECT"
PROCESSING_LATENCY = "PROCESSING_LATENCY"
MEMORY_RSS = "MEMORY_RSS"
PIPELINE_EXCEPTION = "PIPELINE_EXCEPTION"



def _td_sec(td) -> int:
    """timedelta → 整数秒 (float 経由なし)。"""
    return td.days * 86400 + td.seconds


def _td_ms(td) -> int:
    """timedelta → 整数ミリ秒 (float 経由なし)。"""
    return (td.days * 86400 + td.seconds) * 1000 + td.microseconds // 1000


def read_rss_mb() -> Optional[int]:
    """現在プロセスの常駐メモリ (MB, 整数)。取得不能なら None。

    1. Linux: /proc/self/status の VmRSS (kB) — Docker 本番経路。
    2. fallback: resource.getrusage の ru_maxrss (Linux では kB, ピーク値)。
    """
    try:
        with open("/proc/self/status", "r", encoding="ascii", errors="ignore") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    return int(parts[1]) // 1024
    except OSError:
        pass
    try:
        import resource

        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) // 1024
    except Exception:
        return None


@dataclass(frozen=True)
class HealthSnapshot:
    """1 回のサンプリングで webapp 側が収集する生値。"""

    sample_time: datetime                      # 壁時計 (UTC)
    gaps_detected: int = 0                     # 累積 (book_state.gaps_detected)
    reconnects: int = 0                        # 累積 (connector.reconnect_count)
    exceptions: int = 0                        # 累積 (pipeline 例外カウント)
    pipeline_alive: bool = True                # pipeline タスクが生存しているか
    last_bar_wall: Optional[datetime] = None   # 直近 bar close の壁時計時刻
    last_event_time: Optional[datetime] = None  # 直近処理イベントの event_time
    rss_mb: Optional[int] = None               # 常駐メモリ MB (None=取得不能)


@dataclass(frozen=True)
class Anomaly:
    time: datetime
    type: str
    level: str
    value: str
    detail: str

    def to_json(self) -> str:
        return json.dumps(
            {
                "time": self.time.astimezone(timezone.utc).isoformat(),
                "type": self.type,
                "level": self.level,
                "value": self.value,
                "detail": self.detail,
            },
            separators=(",", ":"),
            ensure_ascii=False,
        )


@dataclass
class HealthReport:
    state: str
    sample_time: datetime
    checks: dict = field(default_factory=dict)
    new_anomalies: list = field(default_factory=list)
    anomalies_today: int = 0

    def to_payload(self) -> dict:
        """WebSocket HEALTH / GET /api/health 用 (JSON 直列化可能な値のみ)。"""
        return {
            "state": self.state,
            "sample_time": self.sample_time.astimezone(timezone.utc).isoformat(),
            "checks": self.checks,
            "anomalies_today": self.anomalies_today,
        }


class HealthMonitor:
    """スナップショット列を評価して健全状態を返す純粋評価器 + JSONL 記録。"""

    def __init__(
        self,
        *,
        timeframe_sec: int,
        log_dir: str | Path = "data/monitor",
        bar_missing_tolerance_sec: int = 90,
        latency_yellow_ms: int = 2000,
        latency_red_ms: int = 10000,
        memory_yellow_mb: int = 900,
        memory_red_mb: int = 1500,
        window_min: int = 15,
        reconnect_yellow: int = 1,
        reconnect_red: int = 3,
        gap_yellow: int = 1,
        gap_red: int = 5,
        exception_yellow: int = 1,
        exception_red: int = 3,
        write_log: bool = True,
    ) -> None:
        if timeframe_sec < 1:
            raise ValueError("timeframe_sec must be >= 1")
        self.timeframe_sec = timeframe_sec
        self.log_dir = Path(log_dir)
        self.bar_missing_tolerance_sec = bar_missing_tolerance_sec
        self.latency_yellow_ms = latency_yellow_ms
        self.latency_red_ms = latency_red_ms
        self.memory_yellow_mb = memory_yellow_mb
        self.memory_red_mb = memory_red_mb
        self.window_sec = window_min * 60
        self.reconnect_yellow = reconnect_yellow
        self.reconnect_red = reconnect_red
        self.gap_yellow = gap_yellow
        self.gap_red = gap_red
        self.exception_yellow = exception_yellow
        self.exception_red = exception_red
        self.write_log = write_log

        self._start_time: Optional[datetime] = None
        # 直近スナップショットの累積カウンタ (増分検出用)
        self._prev_counters: dict[str, int] = {}
        # 時間窓内のカウンタ増分イベント: type -> deque[(time, inc)]
        self._events: dict[str, deque] = {
            SEQUENCE_GAP: deque(),
            WS_RECONNECT: deque(),
            PIPELINE_EXCEPTION: deque(),
        }
        # エッジ検出用: 前回のチェックレベル
        self._prev_levels: dict[str, str] = {}
        self._anomalies_today = 0
        self._anomalies_date: Optional[str] = None

    # ------------------------------------------------------------------ utils
    def _log_path(self, when: datetime) -> Path:
        return self.log_dir / f"anomalies_{when.astimezone(timezone.utc):%Y%m%d}.jsonl"

    def _record(self, anomaly: Anomaly, out: list) -> None:
        out.append(anomaly)
        day = f"{anomaly.time.astimezone(timezone.utc):%Y%m%d}"
        if self._anomalies_date != day:
            self._anomalies_date = day
            self._anomalies_today = 0
        self._anomalies_today += 1
        if not self.write_log:
            return
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            with self._log_path(anomaly.time).open("a", encoding="utf-8") as fh:
                fh.write(anomaly.to_json() + "\n")
        except OSError as exc:
            logger.warning("health anomaly log write failed: %s", exc)

    def _window_total(self, key: str, now: datetime) -> int:
        dq = self._events[key]
        while dq and _td_sec(now - dq[0][0]) > self.window_sec:
            dq.popleft()
        return sum(inc for _, inc in dq)

    def _counter_check(
        self,
        key: str,
        current: int,
        now: datetime,
        yellow_at: int,
        red_at: int,
        detail_fmt: str,
        out: list,
    ) -> dict:
        prev = self._prev_counters.get(key)
        if prev is not None and current > prev:
            inc = current - prev
            self._events[key].append((now, inc))
        self._prev_counters[key] = current
        total = self._window_total(key, now)
        if total >= red_at:
            level = RED
        elif total >= yellow_at:
            level = YELLOW
        else:
            level = GREEN
        # 増分があった瞬間のみ記録 (毎サンプル重複記録しない)
        if prev is not None and current > prev:
            self._record(
                Anomaly(now, key, level, str(current - prev), detail_fmt.format(total=total)),
                out,
            )
        return {"level": level, "value": str(total), "detail": detail_fmt.format(total=total)}

    def _edge_record(self, key: str, level: str, value: str, detail: str, now: datetime, out: list) -> None:
        """状態系チェック: レベルが悪化した瞬間のみ JSONL 記録。"""
        prev = self._prev_levels.get(key, GREEN)
        if _LEVEL_ORDER[level] > _LEVEL_ORDER[prev]:
            self._record(Anomaly(now, key, level, value, detail), out)
        self._prev_levels[key] = level

    # --------------------------------------------------------------- evaluate
    def evaluate(self, snap: HealthSnapshot) -> HealthReport:
        now = snap.sample_time
        if self._start_time is None:
            self._start_time = now
        out: list = []
        checks: dict = {}

        # 1. SEQUENCE_GAP
        checks["sequence_gap"] = self._counter_check(
            SEQUENCE_GAP, snap.gaps_detected, now,
            self.gap_yellow, self.gap_red,
            "book gaps in window: {total}", out,
        )

        # 3. WS_RECONNECT
        checks["ws_reconnect"] = self._counter_check(
            WS_RECONNECT, snap.reconnects, now,
            self.reconnect_yellow, self.reconnect_red,
            "reconnects in window: {total}", out,
        )

        # 6. PIPELINE_EXCEPTION (カウンタ) + タスク死亡 (即 RED)
        exc_check = self._counter_check(
            PIPELINE_EXCEPTION, snap.exceptions, now,
            self.exception_yellow, self.exception_red,
            "pipeline exceptions in window: {total}", out,
        )
        if not snap.pipeline_alive:
            exc_check = {"level": RED, "value": exc_check["value"], "detail": "pipeline task dead"}
            self._edge_record(PIPELINE_EXCEPTION + "_DEAD", RED, "1", "pipeline task dead", now, out)
        checks["pipeline"] = exc_check

        # 2. BAR_MISSING — ウォームアップ (起動から 1 bar + 許容) 中は GREEN
        warmup_sec = self.timeframe_sec + self.bar_missing_tolerance_sec
        since_start = _td_sec(now - self._start_time)
        if snap.last_bar_wall is not None:
            silent = _td_sec(now - snap.last_bar_wall)
        else:
            silent = since_start
        if since_start < warmup_sec and snap.last_bar_wall is None:
            level, detail = GREEN, f"warming up ({since_start}s)"
        elif silent > 2 * self.timeframe_sec + self.bar_missing_tolerance_sec:
            level, detail = RED, f"no bar close for {silent}s"
        elif silent > warmup_sec:
            level, detail = YELLOW, f"no bar close for {silent}s"
        else:
            level, detail = GREEN, f"last bar {silent}s ago"
        self._edge_record(BAR_MISSING, level, str(silent), detail, now, out)
        checks["bar_flow"] = {"level": level, "value": str(silent), "detail": detail}

        # 4. PROCESSING_LATENCY
        if snap.last_event_time is None:
            level, val, detail = GREEN, "0", "no event yet"
        else:
            lag_ms = _td_ms(now - snap.last_event_time)
            if lag_ms < 0:
                lag_ms = 0
            val = str(lag_ms)
            if lag_ms >= self.latency_red_ms:
                level, detail = RED, f"event lag {lag_ms}ms"
            elif lag_ms >= self.latency_yellow_ms:
                level, detail = YELLOW, f"event lag {lag_ms}ms"
            else:
                level, detail = GREEN, f"event lag {lag_ms}ms"
        self._edge_record(PROCESSING_LATENCY, level, val, detail, now, out)
        checks["latency"] = {"level": level, "value": val, "detail": detail}

        # 5. MEMORY_RSS
        if snap.rss_mb is None:
            level, val, detail = GREEN, "-", "rss unavailable"
        else:
            val = str(snap.rss_mb)
            if snap.rss_mb >= self.memory_red_mb:
                level, detail = RED, f"rss {snap.rss_mb}MB"
            elif snap.rss_mb >= self.memory_yellow_mb:
                level, detail = YELLOW, f"rss {snap.rss_mb}MB"
            else:
                level, detail = GREEN, f"rss {snap.rss_mb}MB"
        self._edge_record(MEMORY_RSS, level, val, detail, now, out)
        checks["memory"] = {"level": level, "value": val, "detail": detail}

        # 全体状態 = 最悪値
        worst = GREEN
        for c in checks.values():
            if _LEVEL_ORDER[c["level"]] > _LEVEL_ORDER[worst]:
                worst = c["level"]

        # 当日カウンタの日跨ぎリセット (異常ゼロの日でも正しく 0 に戻す)
        day = f"{now.astimezone(timezone.utc):%Y%m%d}"
        if self._anomalies_date != day:
            self._anomalies_date = day
            self._anomalies_today = 0

        return HealthReport(
            state=worst,
            sample_time=now,
            checks=checks,
            new_anomalies=out,
            anomalies_today=self._anomalies_today,
        )
