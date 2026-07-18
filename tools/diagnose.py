"""SelfMonitor v1 — ワンコマンド診断レポート.

DE の現在状態を 1 コマンドで収集し、そのままチャットに貼れる形式で出力する。

収集対象 (取得できない項目はスキップし、レポートにその旨を明記):
  1. アプリバージョン (CHANGELOG 由来)
  2. 設定サマリ (symbol / timeframe / signal / monitor)
  3. DuckDB 統計 (trades / candles / signals 件数、最終 bar_time、最新シグナル)
  4. 当日の異常ログ (data/monitor/anomalies_YYYYMMDD.jsonl 末尾)
  5. 稼働中サーバの /api/health と /api/stats (HTTP, 2 秒タイムアウト)

使い方:
    python -m tools.diagnose
    python -m tools.diagnose --url http://localhost:8080
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_DEFAULT_CONFIG = "config/config.yaml"
_DEFAULT_URL = "http://localhost:8080"


def _section(title: str) -> None:
    print(f"\n## {title}")


def _kv(key: str, value) -> None:
    print(f"- {key}: {value}")


def _http_json(url: str, timeout_sec: int = 2):
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=timeout_sec) as res:
            return json.loads(res.read().decode("utf-8"))
    except Exception as exc:
        return {"_error": str(exc)}


def _duckdb_stats(db_path: str, symbol: str) -> dict:
    try:
        import duckdb
    except Exception as exc:  # pragma: no cover
        return {"_error": f"duckdb import failed: {exc}"}
    p = Path(db_path)
    if not p.is_file():
        return {"_error": f"database not found: {db_path}"}
    try:
        con = duckdb.connect(db_path, read_only=True)
    except Exception as exc:
        return {"_error": f"connect failed (server running?): {exc}"}
    try:
        out: dict = {}
        for table in ("trades", "candles", "signals"):
            try:
                out[f"{table}_count"] = con.execute(
                    f"SELECT count(*) FROM {table}").fetchone()[0]
            except Exception:
                out[f"{table}_count"] = "n/a"
        try:
            out["latest_bar_time"] = con.execute(
                "SELECT max(bar_time) FROM candles WHERE symbol = ?", [symbol]
            ).fetchone()[0]
        except Exception:
            out["latest_bar_time"] = "n/a"
        try:
            row = con.execute(
                "SELECT bar_time, signal, confidence FROM signals "
                "ORDER BY bar_time DESC LIMIT 1"
            ).fetchone()
            out["latest_signal"] = (
                f"{row[1]} conf={row[2]} @ {row[0]}" if row else "none"
            )
        except Exception:
            out["latest_signal"] = "n/a"
        return out
    finally:
        con.close()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="DeltaEngine diagnostic report")
    parser.add_argument("--config", default=_DEFAULT_CONFIG)
    parser.add_argument("--url", default=_DEFAULT_URL, help="webapp base URL")
    parser.add_argument("--tail", type=int, default=10, help="anomaly log tail lines")
    args = parser.parse_args(argv[1:])

    now = datetime.now(timezone.utc)
    print("# DeltaEngine 診断レポート")
    print(f"generated: {now.isoformat()}")

    # 1. version
    _section("バージョン")
    try:
        from webapp.version import resolve_version

        _kv("app_version", resolve_version())
    except Exception as exc:
        _kv("app_version", f"取得失敗: {exc}")

    # 2. config
    _section("設定サマリ")
    config = None
    try:
        from src.config import load_config

        config = load_config(args.config)
        _kv("symbol", config.market.symbol)
        _kv("bar_timeframe", config.market.bar_timeframe)
        _kv("signal.enabled", config.signal.enabled)
        _kv("signal.cvd_slope_ref", config.signal.cvd_slope_ref)
        _kv("signal.stack_ref", config.signal.stack_ref)
        _kv("imbalance.min_volume", config.imbalance.min_volume)
        _kv("monitor.enabled", config.monitor.enabled)
        _kv("replay.enabled", config.replay.enabled)
    except Exception as exc:
        _kv("config", f"読込失敗: {exc}")

    # 3. duckdb
    _section("データベース")
    if config is not None:
        stats = _duckdb_stats(config.database.duckdb_path, config.market.symbol)
        for k, v in stats.items():
            _kv(k, v)
    else:
        _kv("skipped", "config 読込失敗のため")

    # 4. anomaly log
    _section("当日の異常ログ")
    if config is not None:
        log_path = Path(config.monitor.log_dir) / f"anomalies_{now:%Y%m%d}.jsonl"
        if log_path.is_file():
            lines = log_path.read_text(encoding="utf-8").splitlines()
            _kv("count", len(lines))
            for line in lines[-args.tail:]:
                print(f"  {line}")
        else:
            _kv("count", 0)
            _kv("file", f"{log_path} (なし)")
    else:
        _kv("skipped", "config 読込失敗のため")

    # 5. live server
    _section("稼働中サーバ")
    health = _http_json(f"{args.url}/api/health")
    if "_error" in health:
        _kv("api/health", f"到達不可 ({health['_error']}) — サーバ停止中なら正常")
    else:
        _kv("state", health.get("state"))
        for name, c in (health.get("checks") or {}).items():
            _kv(f"check.{name}", f"{c.get('level')} — {c.get('detail')}")
        _kv("anomalies_today", health.get("anomalies_today"))
        stats = _http_json(f"{args.url}/api/stats")
        if "_error" not in stats:
            for k, v in stats.items():
                _kv(f"stats.{k}", v)
        version = _http_json(f"{args.url}/api/version")
        if "_error" not in version:
            _kv("server_version", version.get("version"))

    print("\n(このレポートはそのままチャットに貼り付けて共有できます)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
