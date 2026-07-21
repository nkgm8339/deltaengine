"""M6 integration test — deterministic replay.

Feeds recorded raw events (JSON Lines, Binance profile) through the full CVD path
twice and asserts the Parquet and DuckDB outputs are identical, and correct.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb
import pyarrow.parquet as pq

from src.config import load_config
from src.pipeline import ReplayPipeline, load_profile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc

# Recorded raw events in Binance aggTrade profile format (m: true=SELL, false=BUY).
# trade_id maps to the aggregate id `a` (Phase6: @aggTrade feed). All within
# minute 00:00 -> one 1m candle. Row #4 duplicates aggregate id 2.
RAW_EVENTS = [
    {"e": "aggTrade", "E": 1767225601000, "T": 1767225601000, "a": 1, "s": "BTCUSDT", "p": 100, "q": 5, "m": False},
    {"e": "aggTrade", "E": 1767225602000, "T": 1767225602000, "a": 2, "s": "BTCUSDT", "p": 101, "q": 3, "m": True},
    {"e": "aggTrade", "E": 1767225603000, "T": 1767225603000, "a": 3, "s": "BTCUSDT", "p": 102, "q": 2, "m": False},
    {"e": "aggTrade", "E": 1767225602000, "T": 1767225602000, "a": 2, "s": "BTCUSDT", "p": 101, "q": 3, "m": True},
    {"e": "aggTrade", "E": 1767225604000, "T": 1767225604000, "a": 4, "s": "BTCUSDT", "p": 103, "q": 6, "m": True},
]


def _write_jsonl(path: Path) -> None:
    path.write_text(
        "\n".join(json.dumps(e, sort_keys=True) for e in RAW_EVENTS) + "\n",
        encoding="utf-8",
    )


def _pipeline(parquet_path: Path, duckdb_path: Path) -> ReplayPipeline:
    config = load_config(PROJECT_ROOT / "config" / "config.yaml")
    profile = load_profile(PROJECT_ROOT / "config" / "profiles" / "binance.yaml")
    return ReplayPipeline.from_config(config, profile, parquet_path, duckdb_path)


def _dump_duckdb(duckdb_path: Path):
    con = duckdb.connect(str(duckdb_path), read_only=True)
    trades = con.execute("SELECT * FROM trades ORDER BY trade_id").fetchall()
    candles = con.execute("SELECT * FROM candles ORDER BY bar_time, symbol, timeframe").fetchall()
    con.close()
    return trades, candles


def _dump_parquet(base: Path):
    rows = []
    for file in sorted(base.rglob("*.parquet")):
        rows.extend(pq.ParquetFile(str(file)).read().to_pylist())
    return sorted(json.dumps(r, default=str, sort_keys=True) for r in rows)


def test_replay_is_deterministic_and_correct(tmp_path: Path) -> None:
    data = tmp_path / "recorded.jsonl"
    _write_jsonl(data)

    run1_pq, run1_duck = tmp_path / "r1" / "parquet", tmp_path / "r1" / "of.duckdb"
    run2_pq, run2_duck = tmp_path / "r2" / "parquet", tmp_path / "r2" / "of.duckdb"

    stats1 = _pipeline(run1_pq, run1_duck).run(data)
    stats2 = _pipeline(run2_pq, run2_duck).run(data)

    # --- deterministic: two runs produce identical output ---
    assert _dump_duckdb(run1_duck) == _dump_duckdb(run2_duck)
    assert _dump_parquet(run1_pq) == _dump_parquet(run2_pq)
    assert stats1 == stats2

    # --- correctness ---
    assert stats1.trades_stored == 4
    assert stats1.candles_stored == 1
    assert stats1.signals_stored == 1      # one signal per confirmed bar
    assert stats1.duplicates == 1          # row #4 discarded
    assert stats1.invalid == 0
    assert stats1.final_cvd == Decimal(-2)  # +5 -3 +2 -6

    trades, candles = _dump_duckdb(run1_duck)
    assert [t[2] for t in trades] == [1, 2, 3, 4]   # trade_id column, in order

    # single candle: bar 00:00, delta -2 (bar), cvd -2 (cumulative), volume 16
    (candle,) = candles
    columns = ["bar_time", "symbol", "timeframe", "open", "high", "low",
               "close", "volume", "delta", "cvd"]
    row = dict(zip(columns, candle))
    # DuckDB TIMESTAMP is timezone-naive; stored as UTC wall-clock (session=UTC).
    assert row["bar_time"] == datetime(2026, 1, 1, 0, 0, 0)
    assert row["symbol"] == "BTCUSDT"
    assert row["timeframe"] == "1m"
    assert row["open"] == Decimal("100")
    assert row["high"] == Decimal("103")
    assert row["low"] == Decimal("100")
    assert row["close"] == Decimal("103")
    assert row["volume"] == Decimal("16")
    assert row["delta"] == Decimal("-2")
    assert row["cvd"] == Decimal("-2")


# Two-bar fixture: trades in bar-00:00 and bar-00:01 → 2 candles → 2 signals.
RAW_TWO_BARS = [
    {"e": "aggTrade", "E": 1767225601000, "T": 1767225601000, "a": 10, "s": "BTCUSDT", "p": 100, "q": 5, "m": False},
    {"e": "aggTrade", "E": 1767225661000, "T": 1767225661000, "a": 11, "s": "BTCUSDT", "p": 101, "q": 3, "m": True},
]

RAW_THREE_BARS = RAW_TWO_BARS + [
    {"e": "aggTrade", "E": 1767225721000, "T": 1767225721000, "a": 12, "s": "BTCUSDT", "p": 102, "q": 1, "m": False},
]


def _write_jsonl_events(path: Path, events: list) -> None:
    path.write_text(
        "\n".join(json.dumps(e, sort_keys=True) for e in events) + "\n",
        encoding="utf-8",
    )


def test_replay_divergence_clears_on_non_fire_bar(tmp_path: Path) -> None:
    data = tmp_path / "three_bars.jsonl"
    _write_jsonl_events(data, RAW_THREE_BARS)
    config = load_config(PROJECT_ROOT / "config" / "config.yaml")
    profile = load_profile(PROJECT_ROOT / "config" / "profiles" / "binance.yaml")
    pipeline = ReplayPipeline.from_config(
        config, profile, tmp_path / "parquet", tmp_path / "of.duckdb"
    )
    detector = MagicMock()
    detector.update.side_effect = [object(), None]

    with patch("src.pipeline.CvdDivergenceDetector", return_value=detector):
        pipeline.run(data)

    assert detector.update.call_count == 2
    assert pipeline.divergence is None


def test_pipeline_emits_signal_on_bar_close(tmp_path: Path) -> None:
    """Each confirmed bar produces one signals row."""
    data = tmp_path / "two_bars.jsonl"
    _write_jsonl_events(data, RAW_TWO_BARS)
    config = load_config(PROJECT_ROOT / "config" / "config.yaml")
    profile = load_profile(PROJECT_ROOT / "config" / "profiles" / "binance.yaml")
    pq_path = tmp_path / "parquet"
    db_path = tmp_path / "of.duckdb"
    stats = ReplayPipeline.from_config(config, profile, pq_path, db_path).run(data)
    # bar-00:00 closes when bar-00:01 trade arrives, bar-00:01 closes on finalize
    assert stats.candles_stored == 2
    assert stats.signals_stored == 2

    con = duckdb.connect(str(db_path), read_only=True)
    rows = con.execute("SELECT signal, confidence FROM signals ORDER BY signal_time").fetchall()
    con.close()
    assert len(rows) == 2
    # confidence must be in [0, 1]
    for _, conf in rows:
        assert 0.0 <= conf <= 1.0


def test_pipeline_signal_deterministic_replay(tmp_path: Path) -> None:
    """Same input twice → identical signals table."""
    data = tmp_path / "two_bars.jsonl"
    _write_jsonl_events(data, RAW_TWO_BARS)
    config = load_config(PROJECT_ROOT / "config" / "config.yaml")
    profile = load_profile(PROJECT_ROOT / "config" / "profiles" / "binance.yaml")

    def _run(sub: str):
        return ReplayPipeline.from_config(
            config, profile,
            tmp_path / sub / "parquet",
            tmp_path / sub / "of.duckdb",
        ).run(data)

    s1 = _run("r1")
    s2 = _run("r2")
    assert s1.signals_stored == s2.signals_stored

    def _dump_signals(sub: str):
        con = duckdb.connect(str(tmp_path / sub / "of.duckdb"), read_only=True)
        rows = con.execute("SELECT * FROM signals ORDER BY signal_time").fetchall()
        con.close()
        return rows

    assert _dump_signals("r1") == _dump_signals("r2")


def test_pipeline_analysis_count_matches_candles(tmp_path: Path) -> None:
    """ReplayPipeline generates one AnalysisResult per confirmed bar."""
    data = tmp_path / "two_bars.jsonl"
    _write_jsonl_events(data, RAW_TWO_BARS)
    config = load_config(PROJECT_ROOT / "config" / "config.yaml")
    profile = load_profile(PROJECT_ROOT / "config" / "profiles" / "binance.yaml")
    stats = ReplayPipeline.from_config(
        config, profile, tmp_path / "parquet", tmp_path / "of.duckdb"
    ).run(data)
    assert stats.analysis_count == stats.candles_stored == 2


def test_mt5_disabled_no_server_started(tmp_path: Path) -> None:
    """mt5_enabled=False (default) → MT5Server is never instantiated."""
    from unittest.mock import patch

    data = tmp_path / "two_bars.jsonl"
    _write_jsonl_events(data, RAW_TWO_BARS)
    config = load_config(PROJECT_ROOT / "config" / "config.yaml")
    profile = load_profile(PROJECT_ROOT / "config" / "profiles" / "binance.yaml")

    with patch("src.pipeline.MT5Server") as mock_cls:
        ReplayPipeline.from_config(
            config, profile, tmp_path / "parquet", tmp_path / "of.duckdb"
        ).run(data)
        # ReplayPipeline never starts MT5; mock must be untouched.
        mock_cls.assert_not_called()


def test_pipeline_cvd_slope_ref_none_degrades_gracefully(tmp_path: Path) -> None:
    """cvd_slope_ref=None → CVD score absent, Signal runs on Footprint+Imbalance only."""
    data = tmp_path / "two_bars.jsonl"
    _write_jsonl_events(data, RAW_TWO_BARS)
    config = load_config(PROJECT_ROOT / "config" / "config.yaml")
    profile = load_profile(PROJECT_ROOT / "config" / "profiles" / "binance.yaml")
    # cvd_slope_ref defaults to None in config → pipeline must not raise
    stats = ReplayPipeline.from_config(
        config, profile,
        tmp_path / "parquet",
        tmp_path / "of.duckdb",
    ).run(data)
    assert stats.signals_stored == stats.candles_stored  # one signal per bar
    con = duckdb.connect(str(tmp_path / "of.duckdb"), read_only=True)
    sigs = con.execute("SELECT signal FROM signals").fetchall()
    con.close()
    # Signal values are valid (no crash, valid enum values)
    for (sig,) in sigs:
        assert sig in ("BUY", "SELL", "WAIT")
