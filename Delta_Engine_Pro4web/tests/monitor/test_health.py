"""SelfMonitor v1 — HealthMonitor unit tests."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from src.monitor.health import (
    GREEN,
    RED,
    YELLOW,
    HealthMonitor,
    HealthSnapshot,
    read_rss_mb,
)

T0 = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)


def _mon(tmp_path, **kw):
    defaults = dict(timeframe_sec=60, log_dir=tmp_path, write_log=True)
    defaults.update(kw)
    return HealthMonitor(**defaults)


def _snap(t, **kw):
    return HealthSnapshot(sample_time=t, **kw)


def test_all_green_baseline(tmp_path):
    mon = _mon(tmp_path)
    r = mon.evaluate(_snap(T0, last_bar_wall=T0 - timedelta(seconds=10),
                           last_event_time=T0 - timedelta(milliseconds=100),
                           rss_mb=200))
    assert r.state == GREEN
    assert all(c["level"] == GREEN for c in r.checks.values())
    assert r.new_anomalies == []


def test_warmup_no_bar_is_green(tmp_path):
    # 起動直後 bar 未着でも warmup 中 (timeframe+tolerance 未満) は GREEN。
    mon = _mon(tmp_path, bar_missing_tolerance_sec=90)
    r = mon.evaluate(_snap(T0))
    assert r.checks["bar_flow"]["level"] == GREEN
    # warmup 経過後 bar が来ていなければ YELLOW → さらに経過で RED
    r2 = mon.evaluate(_snap(T0 + timedelta(seconds=200)))
    assert r2.checks["bar_flow"]["level"] == YELLOW
    r3 = mon.evaluate(_snap(T0 + timedelta(seconds=400)))
    assert r3.checks["bar_flow"]["level"] == RED
    assert r3.state == RED


def test_bar_missing_uses_last_bar_wall(tmp_path):
    mon = _mon(tmp_path)
    mon.evaluate(_snap(T0, last_bar_wall=T0))
    r = mon.evaluate(_snap(T0 + timedelta(seconds=170),
                           last_bar_wall=T0 + timedelta(seconds=60)))
    # 110 秒無音 (60+90=150 以内) → GREEN
    assert r.checks["bar_flow"]["level"] == GREEN
    r2 = mon.evaluate(_snap(T0 + timedelta(seconds=230),
                            last_bar_wall=T0 + timedelta(seconds=60)))
    # 170 秒無音 > 150 → YELLOW
    assert r2.checks["bar_flow"]["level"] == YELLOW


def test_latency_thresholds(tmp_path):
    mon = _mon(tmp_path, latency_yellow_ms=2000, latency_red_ms=10000)
    base = dict(last_bar_wall=T0, rss_mb=100)
    r = mon.evaluate(_snap(T0, last_event_time=T0 - timedelta(milliseconds=500), **base))
    assert r.checks["latency"]["level"] == GREEN
    r = mon.evaluate(_snap(T0, last_event_time=T0 - timedelta(milliseconds=2500), **base))
    assert r.checks["latency"]["level"] == YELLOW
    assert r.checks["latency"]["value"] == "2500"
    r = mon.evaluate(_snap(T0, last_event_time=T0 - timedelta(seconds=11), **base))
    assert r.checks["latency"]["level"] == RED
    assert r.state == RED


def test_memory_thresholds_and_unavailable(tmp_path):
    mon = _mon(tmp_path, memory_yellow_mb=900, memory_red_mb=1500)
    assert mon.evaluate(_snap(T0, rss_mb=899, last_bar_wall=T0)).checks["memory"]["level"] == GREEN
    assert mon.evaluate(_snap(T0, rss_mb=900, last_bar_wall=T0)).checks["memory"]["level"] == YELLOW
    assert mon.evaluate(_snap(T0, rss_mb=1500, last_bar_wall=T0)).checks["memory"]["level"] == RED
    r = mon.evaluate(_snap(T0, rss_mb=None, last_bar_wall=T0))
    assert r.checks["memory"]["level"] == GREEN
    assert "unavailable" in r.checks["memory"]["detail"]


def test_reconnect_window_counting(tmp_path):
    mon = _mon(tmp_path, window_min=15, reconnect_yellow=1, reconnect_red=3)
    mon.evaluate(_snap(T0, reconnects=0, last_bar_wall=T0))
    r = mon.evaluate(_snap(T0 + timedelta(seconds=5), reconnects=1, last_bar_wall=T0))
    assert r.checks["ws_reconnect"]["level"] == YELLOW
    r = mon.evaluate(_snap(T0 + timedelta(seconds=10), reconnects=3, last_bar_wall=T0))
    assert r.checks["ws_reconnect"]["level"] == RED
    # 窓 (15 分) を過ぎれば増分は判定から外れ GREEN に戻る
    later = T0 + timedelta(minutes=20)
    r = mon.evaluate(_snap(later, reconnects=3,
                           last_bar_wall=later - timedelta(seconds=5)))
    assert r.checks["ws_reconnect"]["level"] == GREEN


def test_gap_counter_and_anomaly_recorded(tmp_path):
    mon = _mon(tmp_path, gap_yellow=1, gap_red=5)
    mon.evaluate(_snap(T0, gaps_detected=0, last_bar_wall=T0))
    r = mon.evaluate(_snap(T0 + timedelta(seconds=5), gaps_detected=2, last_bar_wall=T0))
    assert r.checks["sequence_gap"]["level"] == YELLOW
    assert any(a.type == "SEQUENCE_GAP" and a.value == "2" for a in r.new_anomalies)


def test_pipeline_dead_is_red(tmp_path):
    mon = _mon(tmp_path)
    r = mon.evaluate(_snap(T0, pipeline_alive=False, last_bar_wall=T0))
    assert r.checks["pipeline"]["level"] == RED
    assert r.state == RED


def test_pipeline_dead_persists_exception_type_and_message(tmp_path):
    mon = _mon(tmp_path)
    r = mon.evaluate(_snap(
        T0,
        pipeline_alive=False,
        pipeline_error="ZeroDivisionError: division by zero",
        last_bar_wall=T0,
    ))

    assert r.checks["pipeline"]["level"] == RED
    assert r.checks["pipeline"]["detail"] == (
        "pipeline task dead: ZeroDivisionError: division by zero"
    )
    dead = next(a for a in r.new_anomalies if a.type == "PIPELINE_EXCEPTION_DEAD")
    assert dead.detail == r.checks["pipeline"]["detail"]
    persisted = json.loads(
        (tmp_path / "anomalies_20260718.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[-1]
    )
    assert persisted["detail"] == r.checks["pipeline"]["detail"]


def test_jsonl_written_and_daily_rotated(tmp_path):
    mon = _mon(tmp_path)
    mon.evaluate(_snap(T0, reconnects=0, last_bar_wall=T0))
    mon.evaluate(_snap(T0 + timedelta(seconds=5), reconnects=1, last_bar_wall=T0))
    day1 = tmp_path / "anomalies_20260718.jsonl"
    assert day1.is_file()
    rec = json.loads(day1.read_text(encoding="utf-8").splitlines()[0])
    assert rec["type"] == "WS_RECONNECT" and rec["level"] in (YELLOW, RED)
    # 翌日の異常は別ファイルへ
    next_day = T0 + timedelta(days=1)
    mon.evaluate(_snap(next_day, reconnects=2,
                       last_bar_wall=next_day - timedelta(seconds=5)))
    assert (tmp_path / "anomalies_20260719.jsonl").is_file()


def test_anomalies_today_resets_on_new_day(tmp_path):
    mon = _mon(tmp_path)
    mon.evaluate(_snap(T0, reconnects=0, last_bar_wall=T0))
    r = mon.evaluate(_snap(T0 + timedelta(seconds=5), reconnects=1, last_bar_wall=T0))
    assert r.anomalies_today == 1
    nd = T0 + timedelta(days=1)
    r2 = mon.evaluate(_snap(nd, reconnects=1, last_bar_wall=nd - timedelta(seconds=5)))
    assert r2.anomalies_today == 0


def test_edge_recording_no_duplicate_spam(tmp_path):
    # 状態系 (latency) は悪化した瞬間のみ記録され、継続中は再記録されない。
    mon = _mon(tmp_path)
    base = dict(last_bar_wall=T0, rss_mb=100)
    r1 = mon.evaluate(_snap(T0, last_event_time=T0 - timedelta(seconds=3), **base))
    assert any(a.type == "PROCESSING_LATENCY" for a in r1.new_anomalies)
    r2 = mon.evaluate(_snap(T0 + timedelta(seconds=5),
                            last_event_time=T0 + timedelta(seconds=2), **base))
    assert not any(a.type == "PROCESSING_LATENCY" for a in r2.new_anomalies)


def test_to_payload_serializable(tmp_path):
    mon = _mon(tmp_path)
    r = mon.evaluate(_snap(T0, last_bar_wall=T0, rss_mb=123))
    payload = r.to_payload()
    json.dumps(payload)  # 直列化可能であること
    assert payload["state"] == GREEN
    assert set(payload["checks"]) == {
        "sequence_gap", "ws_reconnect", "pipeline", "bar_flow", "latency", "memory",
    }


def test_read_rss_mb_returns_int_or_none():
    v = read_rss_mb()
    assert v is None or (isinstance(v, int) and v >= 0)
