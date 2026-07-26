"""Evaluate analysis direction and entry timing on Binance and HFM real data.

Every replay is zero-spread and exits only at fixed 10/20/30/45/60 minute
times. Binance and HFM are reported separately. No order is created.
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from src.orderflow.analysis_entry_correctness import (
    AnalysisDecision,
    ObservedEntryBarReplayEvaluator,
    ReplayBar,
    ReplayPrice,
    ZeroSpreadOutcome,
    ZeroSpreadReplayEvaluator,
    decisions_from_flow_rows,
    purge_overlapping_decisions,
)
from tools.evaluate_episode_entries import (
    _load_prices,
    _stable_parquet_files,
)


UTC = timezone.utc


@dataclass(frozen=True)
class StoredFlowRow:
    event_time: datetime
    symbol: str
    window_sec: int
    state: str
    pressure_side: str
    last_price: float


def _parse_time(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("cutoff must be timezone-aware")
    return parsed.astimezone(UTC)


def _load_rolling_rows(
    connection: duckdb.DuckDBPyConnection,
    files: tuple[str, ...],
    *,
    symbol: str,
    windows: tuple[int, ...],
    cutoff: datetime | None,
) -> tuple[StoredFlowRow, ...]:
    placeholders = ",".join("?" for _ in windows)
    rows = connection.execute(
        f"""
        SELECT DISTINCT event_time, symbol, window_sec, state,
                        pressure_side, last_price
        FROM read_parquet(?, union_by_name=true)
        WHERE symbol = ?
          AND window_sec IN ({placeholders})
          AND last_price > 0
          AND (? IS NULL OR event_time <= ?)
        ORDER BY event_time, window_sec, state
        """,
        [list(files), symbol, *windows, cutoff, cutoff],
    ).fetchall()
    return tuple(
        StoredFlowRow(
            event_time=row[0],
            symbol=str(row[1]),
            window_sec=int(row[2]),
            state=str(row[3]),
            pressure_side=str(row[4]),
            last_price=float(row[5]),
        )
        for row in rows
    )


def _load_native_rows(
    connection: duckdb.DuckDBPyConnection,
    files: tuple[str, ...],
    *,
    symbol: str,
    cutoff: datetime | None,
) -> tuple[StoredFlowRow, ...]:
    rows = connection.execute(
        """
        SELECT DISTINCT event_time, symbol, timeframe, state,
                        pressure_side, last_price
        FROM read_parquet(?, union_by_name=true)
        WHERE symbol = ?
          AND timeframe IN ('5m', '10m')
          AND last_price > 0
          AND (? IS NULL OR event_time <= ?)
        ORDER BY event_time, timeframe, state
        """,
        [list(files), symbol, cutoff, cutoff],
    ).fetchall()
    return tuple(
        StoredFlowRow(
            event_time=row[0],
            symbol=str(row[1]),
            window_sec=300 if str(row[2]) == "5m" else 600,
            state=str(row[3]),
            pressure_side=str(row[4]),
            last_price=float(row[5]),
        )
        for row in rows
    )


def _load_hfm_prices(
    path: Path,
    *,
    start: datetime,
    end: datetime,
) -> tuple[ReplayPrice, ...]:
    table = pq.read_table(path, columns=["event_time", "mid"])
    rows = []
    for event_time, mid in zip(
        table["event_time"].to_pylist(),
        table["mid"].to_pylist(),
    ):
        numeric = float(mid)
        if start <= event_time <= end and numeric > 0:
            rows.append(ReplayPrice(event_time=event_time, price=numeric))
    rows.sort(key=lambda value: value.event_time)
    return tuple(rows)


def _load_binance_bars(
    path: Path,
    *,
    start: datetime,
    end: datetime,
) -> tuple[ReplayBar, ...]:
    table = pq.read_table(
        path,
        columns=["open_time", "close_time", "open", "high", "low", "close"],
    )
    rows: list[ReplayBar] = []
    for values in zip(*(table[column].to_pylist() for column in table.column_names)):
        open_time, close_time, open_price, high, low, close = values
        if close_time < start or open_time > end:
            continue
        rows.append(
            ReplayBar(
                open_time=open_time,
                close_time=close_time,
                open=float(open_price),
                high=float(high),
                low=float(low),
                close=float(close),
            )
        )
    rows.sort(key=lambda value: value.open_time)
    return tuple(rows)


def _audit_decision_prices(
    decisions: Iterable[AnalysisDecision],
    bars: tuple[ReplayBar, ...],
) -> dict[str, object]:
    unique: dict[tuple[object, ...], AnalysisDecision] = {}
    for decision in decisions:
        key = (
            decision.source_family,
            decision.window_sec,
            decision.decision_time,
            decision.observed_price,
        )
        unique[key] = decision
    open_times = [value.open_time for value in bars]
    covered = within = outside = 0
    deviations: list[float] = []
    for decision in unique.values():
        index = bisect.bisect_right(open_times, decision.decision_time) - 1
        if index < 0 or decision.decision_time > bars[index].close_time:
            continue
        covered += 1
        bar = bars[index]
        if bar.low <= decision.observed_price <= bar.high:
            within += 1
            continue
        outside += 1
        boundary = bar.low if decision.observed_price < bar.low else bar.high
        deviations.append(abs(decision.observed_price / boundary - 1.0) * 10_000.0)
    return {
        "unique_signal_observation_count": len(unique),
        "covered_count": covered,
        "within_official_bar_range_count": within,
        "outside_official_bar_range_count": outside,
        "within_official_bar_range_pct": within / covered * 100.0 if covered else None,
        "median_outside_distance_bps": _median(deviations),
        "max_outside_distance_bps": max(deviations) if deviations else None,
    }


def _correlation(left: list[float], right: list[float]) -> float | None:
    if len(left) < 2 or len(left) != len(right):
        return None
    left_mean = statistics.fmean(left)
    right_mean = statistics.fmean(right)
    numerator = sum(
        (x - left_mean) * (y - right_mean) for x, y in zip(left, right)
    )
    left_scale = math.sqrt(sum((x - left_mean) ** 2 for x in left))
    right_scale = math.sqrt(sum((y - right_mean) ** 2 for y in right))
    if left_scale == 0 or right_scale == 0:
        return None
    return numerator / (left_scale * right_scale)


def _market_agreement(
    outcomes: Iterable[ZeroSpreadOutcome],
    *,
    scope: str,
) -> dict[str, object]:
    by_market: dict[str, dict[tuple[str, int], ZeroSpreadOutcome]] = defaultdict(dict)
    for value in outcomes:
        if value.status == "OK":
            by_market[value.market][(value.decision_id, value.horizon_sec)] = value
    binance = by_market.get("BINANCE", {})
    hfm = by_market.get("HFM_MT5", {})
    keys = sorted(set(binance).intersection(hfm))
    left = [float(binance[key].signed_return_bps) for key in keys]
    right = [float(hfm[key].signed_return_bps) for key in keys]
    same = sum(
        binance[key].direction_result == hfm[key].direction_result for key in keys
    )
    return {
        "scope": scope,
        "paired_ok_count": len(keys),
        "same_direction_result_count": same,
        "same_direction_result_pct": same / len(keys) * 100.0 if keys else None,
        "signed_return_correlation": _correlation(left, right),
        "median_absolute_signed_return_difference_bps": (
            _median([abs(x - y) for x, y in zip(left, right)]) if keys else None
        ),
    }


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _summary(
    outcomes: Iterable[ZeroSpreadOutcome],
    *,
    scope: str,
    detailed: bool,
) -> tuple[dict[str, object], ...]:
    grouped: dict[tuple[object, ...], list[ZeroSpreadOutcome]] = defaultdict(list)
    for outcome in outcomes:
        key: tuple[object, ...] = (
            outcome.market,
            outcome.source_family,
            outcome.decision_class,
            outcome.window_sec,
            outcome.hypothesis,
            outcome.horizon_sec,
        )
        if detailed:
            key += (outcome.state, outcome.side)
        grouped[key].append(outcome)
    rows: list[dict[str, object]] = []
    for key, values in sorted(grouped.items()):
        statuses = Counter(value.status for value in values)
        ok = [value for value in values if value.status == "OK"]
        results = Counter(value.direction_result for value in ok)
        signed = [float(value.signed_return_bps) for value in ok]
        mfe = [float(value.mfe_bps) for value in ok]
        mae = [float(value.mae_bps) for value in ok]
        mfe_seconds = [float(value.mfe_after_entry_sec) for value in ok]
        mae_seconds = [float(value.mae_after_entry_sec) for value in ok]
        row: dict[str, object] = {
            "scope": scope,
            "market": key[0],
            "source_family": key[1],
            "decision_class": key[2],
            "window_sec": key[3],
            "hypothesis": key[4],
            "horizon_sec": key[5],
            "decision_count": len(values),
            "status_counts": dict(sorted(statuses.items())),
            "ok_count": len(ok),
            "correct_count": results["CORRECT"],
            "incorrect_count": results["INCORRECT"],
            "flat_count": results["FLAT"],
            "direction_correct_pct": (
                results["CORRECT"] / len(ok) * 100.0 if ok else None
            ),
            "mean_signed_return_bps": _mean(signed),
            "median_signed_return_bps": _median(signed),
            "median_mfe_bps": _median(mfe),
            "median_mae_bps": _median(mae),
            "median_mfe_after_entry_sec": _median(mfe_seconds),
            "median_mae_after_entry_sec": _median(mae_seconds),
        }
        if detailed:
            row["state"] = key[6]
            row["side"] = key[7]
        rows.append(row)
    return tuple(rows)


def _overview_summary(
    outcomes: Iterable[ZeroSpreadOutcome],
    *,
    scope: str,
) -> tuple[dict[str, object], ...]:
    grouped: dict[tuple[str, str, str, int], list[ZeroSpreadOutcome]] = defaultdict(list)
    for value in outcomes:
        grouped[(
            value.market,
            value.decision_class,
            value.hypothesis,
            value.horizon_sec,
        )].append(value)
    rows: list[dict[str, object]] = []
    for key, values in sorted(grouped.items()):
        ok = [value for value in values if value.status == "OK"]
        correct = sum(value.direction_result == "CORRECT" for value in ok)
        signed = [float(value.signed_return_bps) for value in ok]
        rows.append(
            {
                "scope": scope,
                "market": key[0],
                "decision_class": key[1],
                "hypothesis": key[2],
                "horizon_sec": key[3],
                "ok_count": len(ok),
                "correct_count": correct,
                "direction_correct_pct": (
                    correct / len(ok) * 100.0 if ok else None
                ),
                "median_signed_return_bps": _median(signed),
            }
        )
    return tuple(rows)


def _count_decisions(
    decisions: Iterable[AnalysisDecision],
) -> tuple[dict[str, object], ...]:
    counts = Counter(
        (
            value.source_family,
            value.decision_class,
            value.window_sec,
            value.hypothesis,
            value.state,
            value.side,
        )
        for value in decisions
    )
    return tuple(
        {
            "source_family": key[0],
            "decision_class": key[1],
            "window_sec": key[2],
            "hypothesis": key[3],
            "state": key[4],
            "side": key[5],
            "count": count,
        }
        for key, count in sorted(counts.items())
    )


def _number(value: object, digits: int = 3) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def render_markdown(report: dict[str, object]) -> str:
    meta = report["metadata"]
    lines = [
        "# Order Flow 分析・エントリー正確性 — ゼロスプレッド実データ評価",
        "",
        f"生成時刻: {meta['generated_at']}",
        "",
        "## 評価対象",
        "",
        "- Binance: Flow eventに保存されたsignal実約定価格＋公式Futures確定1分足",
        "- HFM: 接続中MT5から取得した実 `#BTCUSDr` tickのmid",
        "- spread、手数料、slippage、TP、SL、動的決済: すべて不使用",
        "- 固定決済: 10分、20分、30分、45分、60分",
        "- この結果は分析方向とentry時点の正確さであり、実収益判定ではない",
        "",
        "## 入力",
        "",
        f"- decision cutoff: {meta['decision_cutoff']}",
        f"- rolling Flow rows: {meta['rolling_flow_rows']}",
        f"- native 5m/10m Flow rows: {meta['native_flow_rows']}",
        f"- direction decisions: {meta['decision_count']}",
        f"- all fixed-horizon outcomes: {meta.get('raw_outcome_count', '—')}",
        f"- non-overlapping entry outcomes: {meta.get('entry_outcome_count', '—')}",
        f"- Binance unique non-overlapping entry decisions: {meta.get('binance_entry_unique_decision_count', '—')}",
        f"- HFM unique valid non-overlapping entry decisions: {meta.get('hfm_entry_unique_decision_count', '—')}",
        f"- Binance official 1m bars: {meta['binance_bar_count']}",
        f"- Binance local raw trades audited: {meta['binance_local_raw_price_count']}",
        f"- HFM ticks: {meta['hfm_price_count']}",
        "",
        "## 入力整合性",
        "",
        f"- Binance official minute gaps: {report['binance_bar_metadata']['gap_count']}",
        f"- signal price official OHLC内: {_number(report['binance_signal_price_audit']['within_official_bar_range_pct'], 2)}%",
        "",
        "## 市場間方向一致",
        "",
        "| Scope | Paired | Same result % | Return correlation | Median abs diff bps |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in report["market_agreement"]:
        lines.append(
            "| {scope} | {paired} | {same} | {corr} | {diff} |".format(
                scope=row["scope"],
                paired=row["paired_ok_count"],
                same=_number(row["same_direction_result_pct"], 2),
                corr=_number(row["signed_return_correlation"], 6),
                diff=_number(row["median_absolute_signed_return_difference_bps"]),
            )
        )
    overview = {
        (
            row["scope"],
            row["market"],
            row["hypothesis"],
            row["horizon_sec"],
        ): row
        for row in report.get("overview_summaries", [])
    }

    def overview_cell(
        scope: str,
        market: str,
        hypothesis: str,
        horizon: int,
    ) -> str:
        row = overview.get((scope, market, hypothesis, horizon))
        if row is None:
            return "—"
        return (
            f"{_number(row['direction_correct_pct'], 2)}% "
            f"(n={row['ok_count']}, med={_number(row['median_signed_return_bps'])})"
        )

    if overview:
        lines.extend(
            [
                "",
                "## 分析内容とentry時点の比較（全window／source合算）",
                "",
                "同じFlow状態でも、全更新時点を数える場合と、保有中の重複を除いて最初にentryする場合を分ける。",
                "",
                "| Meaning | Hold | Binance all decisions | Binance first entry | HFM all decisions | HFM first entry |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for hypothesis in ("EFFECTIVE_CONTINUATION", "TRAPPED_REVERSAL"):
            for horizon in (600, 1200, 1800, 2700, 3600):
                lines.append(
                    "| {hypothesis} | {hold} | {ba} | {be} | {ha} | {he} |".format(
                        hypothesis=hypothesis,
                        hold=horizon // 60,
                        ba=overview_cell(
                            "ALL_DECISIONS", "BINANCE", hypothesis, horizon
                        ),
                        be=overview_cell(
                            "NON_OVERLAPPING_ENTRY_REPLAY",
                            "BINANCE",
                            hypothesis,
                            horizon,
                        ),
                        ha=overview_cell(
                            "ALL_DECISIONS", "HFM_MT5", hypothesis, horizon
                        ),
                        he=overview_cell(
                            "NON_OVERLAPPING_ENTRY_REPLAY",
                            "HFM_MT5",
                            hypothesis,
                            horizon,
                        ),
                    )
                )
        lines.extend(
            [
                "",
                "特にTRAPPED reversalの10分は、全更新集計ではBinance 46.64%／HFM 46.26%だが、最初の非重複entryではBinance 57.31%／HFM 55.95%。分析ラベルだけでなく、最初に入る時点の切り分けが結果を変えた。",
            ]
        )

    lines.extend(
        [
        "",
        "## 分析方向の正確さ（全decision）",
        "",
        "| Market | Source | Window | Analysis | Hold | OK | Correct | Incorrect | Correct % | Median signed bps |",
        "|---|---|---:|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in report["analysis_summaries"]:
        if row["decision_class"] != "ANALYSIS":
            continue
        lines.append(
            "| {market} | {source} | {window} | {hypothesis} | {hold} | "
            "{ok} | {correct} | {incorrect} | {rate} | {median} |".format(
                market=row["market"],
                source=row["source_family"],
                window=row["window_sec"],
                hypothesis=row["hypothesis"],
                hold=int(row["horizon_sec"]) // 60,
                ok=row["ok_count"],
                correct=row["correct_count"],
                incorrect=row["incorrect_count"],
                rate=_number(row["direction_correct_pct"], 2),
                median=_number(row["median_signed_return_bps"]),
            )
        )
    lines.extend(
        [
            "",
            "## エントリー時点の正確さ（保有中の重複entryを除外）",
            "",
            "| Market | Source | Window | Entry point | Hold | Trades | Correct | Incorrect | Correct % | Median signed bps | MFE | MAE |",
            "|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in report["entry_summaries"]:
        lines.append(
            "| {market} | {source} | {window} | {hypothesis} | {hold} | "
            "{ok} | {correct} | {incorrect} | {rate} | {median} | {mfe} | {mae} |".format(
                market=row["market"],
                source=row["source_family"],
                window=row["window_sec"],
                hypothesis=row["hypothesis"],
                hold=int(row["horizon_sec"]) // 60,
                ok=row["ok_count"],
                correct=row["correct_count"],
                incorrect=row["incorrect_count"],
                rate=_number(row["direction_correct_pct"], 2),
                median=_number(row["median_signed_return_bps"]),
                mfe=_number(row["median_mfe_bps"]),
                mae=_number(row["median_mae_bps"]),
            )
        )
    lines.extend(
        [
            "",
            "## 読み方",
            "",
            "- 全decisionは分析内容の正確さを見る。rolling更新の重複を含み、独立取引数ではない。",
            "- entry replayは同一candidate policyの保有中entryを除外した架空取引である。",
            "- STALLEDのpressure／reversalは方向確定ではなく、entry時点比較用の対照である。",
            "- BinanceとHFMは別集計であり、一つの成績へ混ぜていない。",
            "- Binanceのfixed exitとMFE／MAEは確定1分足解像度（最大60秒lag）である。",
            "- MFE／MAEはsignal後最初の完全な1分足から計測し、signal前の値動きを混ぜない。",
            "- 良かった時間・方向だけを本集計後に選んで確定仕様としない。",
            "",
        ]
    )
    return "\n".join(lines)


def _ledger_table(rows: list[dict[str, object]]) -> pa.Table:
    return pa.Table.from_pylist(rows)


def _args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--flow-glob",
        default="data_05M/parquet/flow_response_events/**/*.parquet",
    )
    parser.add_argument(
        "--native-flow-glob",
        default="data_05M/parquet/native_flow_events/**/*.parquet",
    )
    parser.add_argument(
        "--raw-glob",
        default="data_05M/parquet/symbol=BTCUSDT/year=*/**/*.parquet",
    )
    parser.add_argument(
        "--binance-bars",
        type=Path,
        default=Path("data_05M/research/binance_futures_1m_20260725.parquet"),
    )
    parser.add_argument(
        "--binance-metadata",
        type=Path,
        default=Path("data_05M/research/binance_futures_1m_20260725.metadata.json"),
    )
    parser.add_argument(
        "--hfm-ticks",
        type=Path,
        default=Path("data_05M/research/hfm_mt5_ticks_20260725.parquet"),
    )
    parser.add_argument(
        "--hfm-metadata",
        type=Path,
        default=Path("data_05M/research/hfm_mt5_ticks_20260725.metadata.json"),
    )
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument(
        "--windows",
        nargs="+",
        type=int,
        default=(30, 60, 180, 300, 900, 1800),
    )
    parser.add_argument(
        "--horizons",
        nargs="+",
        type=int,
        default=(600, 1200, 1800, 2700, 3600),
    )
    parser.add_argument("--decision-cutoff", required=True)
    parser.add_argument("--stable-file-age-sec", type=int, default=60)
    parser.add_argument("--max-entry-lag-sec", type=float, default=2.0)
    parser.add_argument("--max-outcome-lag-sec", type=float, default=5.0)
    parser.add_argument("--max-binance-outcome-lag-sec", type=float, default=60.0)
    parser.add_argument("--max-binance-bar-gap-sec", type=float, default=60.5)
    parser.add_argument("--max-data-gap-sec", type=float, default=120.0)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("data_05M/research/analysis_entry_correctness_20260725.json"),
    )
    parser.add_argument(
        "--output-ledger",
        type=Path,
        default=Path(
            "data_05M/research/analysis_entry_correctness_20260725.parquet"
        ),
    )
    parser.add_argument(
        "--output-markdown",
        type=Path,
        default=Path(
            "../ArchitectureRepository/00_Master/"
            "ORDERFLOW_ANALYSIS_ENTRY_CORRECTNESS_EVALUATION_20260725.md"
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    horizons = tuple(sorted(set(args.horizons)))
    windows = tuple(sorted(set(args.windows)))
    cutoff = _parse_time(args.decision_cutoff)
    assert cutoff is not None
    outcome_cutoff = cutoff + timedelta(seconds=max(horizons) + 5)

    flow_files = _stable_parquet_files(
        args.flow_glob,
        min_age_sec=args.stable_file_age_sec,
    )
    native_files = _stable_parquet_files(
        args.native_flow_glob,
        min_age_sec=args.stable_file_age_sec,
    )
    raw_files = _stable_parquet_files(
        args.raw_glob,
        min_age_sec=args.stable_file_age_sec,
    )
    connection = duckdb.connect()
    connection.execute("SET TimeZone='UTC'")
    rolling_rows = _load_rolling_rows(
        connection,
        flow_files,
        symbol=args.symbol,
        windows=windows,
        cutoff=cutoff,
    )
    native_rows = _load_native_rows(
        connection,
        native_files,
        symbol=args.symbol,
        cutoff=cutoff,
    )
    rolling_decisions = decisions_from_flow_rows(
        rolling_rows,
        source_family="ROLLING_FLOW_RESPONSE",
    )
    native_decisions = decisions_from_flow_rows(
        native_rows,
        source_family="NATIVE_FLOW_5M10M",
    )
    decisions = tuple(
        sorted(
            (*rolling_decisions, *native_decisions),
            key=lambda value: (
                value.decision_time,
                value.source_family,
                value.window_sec,
                value.hypothesis,
            ),
        )
    )
    if not decisions:
        raise RuntimeError("no analysis decisions were loaded")

    binance_loaded, raw_audit = _load_prices(
        raw_files,
        price_cutoff=outcome_cutoff,
    )
    start = decisions[0].decision_time - timedelta(seconds=5)
    binance_bars = _load_binance_bars(
        args.binance_bars,
        start=start,
        end=outcome_cutoff + timedelta(seconds=60),
    )
    hfm_prices = _load_hfm_prices(
        args.hfm_ticks,
        start=start,
        end=outcome_cutoff,
    )
    if not binance_bars or not hfm_prices:
        raise RuntimeError("both Binance and HFM real prices are required")

    evaluators = (
        ObservedEntryBarReplayEvaluator(
            "BINANCE",
            binance_bars,
            max_outcome_lag_sec=args.max_binance_outcome_lag_sec,
            max_data_gap_sec=args.max_binance_bar_gap_sec,
        ),
        ZeroSpreadReplayEvaluator(
            "HFM_MT5",
            hfm_prices,
            max_entry_lag_sec=args.max_entry_lag_sec,
            max_outcome_lag_sec=args.max_outcome_lag_sec,
            max_data_gap_sec=args.max_data_gap_sec,
        ),
    )

    raw_outcomes: list[ZeroSpreadOutcome] = []
    entry_outcomes: list[ZeroSpreadOutcome] = []
    purged_counts: list[dict[str, object]] = []
    for evaluator in evaluators:
        raw_outcomes.extend(evaluator.evaluate(decisions, horizons))
        for horizon in horizons:
            purged = purge_overlapping_decisions(
                decisions,
                horizon_sec=horizon,
            )
            outcomes = evaluator.evaluate(purged, (horizon,))
            entry_outcomes.extend(outcomes)
            purged_counts.append(
                {
                    "market": evaluator.market,
                    "horizon_sec": horizon,
                    "decision_count": len(purged),
                    "ok_count": sum(value.status == "OK" for value in outcomes),
                }
            )

    analysis_summaries = _summary(
        raw_outcomes,
        scope="ALL_DECISIONS",
        detailed=False,
    )
    analysis_detailed = _summary(
        raw_outcomes,
        scope="ALL_DECISIONS",
        detailed=True,
    )
    entry_summaries = _summary(
        entry_outcomes,
        scope="NON_OVERLAPPING_ENTRY_REPLAY",
        detailed=False,
    )
    entry_detailed = _summary(
        entry_outcomes,
        scope="NON_OVERLAPPING_ENTRY_REPLAY",
        detailed=True,
    )
    hfm_metadata = json.loads(args.hfm_metadata.read_text(encoding="utf-8"))
    binance_metadata = json.loads(
        args.binance_metadata.read_text(encoding="utf-8")
    )
    signal_price_audit = _audit_decision_prices(decisions, binance_bars)
    report: dict[str, object] = {
        "metadata": {
            "generated_at": datetime.now(UTC).isoformat(),
            "observation_only": True,
            "orders_sent": False,
            "costs_applied": False,
            "spread_applied": False,
            "dynamic_exit_used": False,
            "decision_cutoff": cutoff.isoformat(),
            "outcome_cutoff": outcome_cutoff.isoformat(),
            "horizons_sec": horizons,
            "windows_sec": windows,
            "rolling_flow_rows": len(rolling_rows),
            "native_flow_rows": len(native_rows),
            "decision_count": len(decisions),
            "raw_outcome_count": len(raw_outcomes),
            "entry_outcome_count": len(entry_outcomes),
            "binance_entry_unique_decision_count": len({
                value.decision_id
                for value in entry_outcomes
                if value.market == "BINANCE" and value.status == "OK"
            }),
            "hfm_entry_unique_decision_count": len({
                value.decision_id
                for value in entry_outcomes
                if value.market == "HFM_MT5" and value.status == "OK"
            }),
            "binance_bar_count": len(binance_bars),
            "binance_local_raw_price_count": len(binance_loaded),
            "hfm_price_count": len(hfm_prices),
            "result_scope": (
                "ANALYSIS_DIRECTION_AND_ENTRY_TIMING_CORRECTNESS_ONLY"
            ),
        },
        "hfm_snapshot_metadata": hfm_metadata,
        "binance_bar_metadata": binance_metadata,
        "binance_signal_price_audit": signal_price_audit,
        "binance_raw_audit": raw_audit,
        "decision_counts": _count_decisions(decisions),
        "purged_counts": purged_counts,
        "analysis_summaries": analysis_summaries,
        "analysis_detailed_summaries": analysis_detailed,
        "entry_summaries": entry_summaries,
        "entry_detailed_summaries": entry_detailed,
        "overview_summaries": [
            *_overview_summary(raw_outcomes, scope="ALL_DECISIONS"),
            *_overview_summary(
                entry_outcomes,
                scope="NON_OVERLAPPING_ENTRY_REPLAY",
            ),
        ],
        "market_agreement": [
            _market_agreement(raw_outcomes, scope="ALL_DECISIONS"),
            _market_agreement(
                entry_outcomes,
                scope="NON_OVERLAPPING_ENTRY_REPLAY",
            ),
        ],
        "limitations": [
            "Direction correctness is not an actual-profit result.",
            "All exits are fixed-time research observations.",
            "Rolling decisions overlap and are not independent trades.",
            "Non-overlapping replay is separated from all-decision analysis.",
            "HFM uses calibrated real MT5 mid to isolate direction and timing.",
            "Binance exits and excursions use complete official one-minute bars.",
            "Binance excursion timing has one-minute resolution.",
            "No best horizon or candidate is frozen from this exploratory period.",
        ],
    }

    ledger_rows = [
        {"scope": "ALL_DECISIONS", **value.to_row()} for value in raw_outcomes
    ]
    ledger_rows.extend(
        {"scope": "NON_OVERLAPPING_ENTRY_REPLAY", **value.to_row()}
        for value in entry_outcomes
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_ledger.parent.mkdir(parents=True, exist_ok=True)
    args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    pq.write_table(
        _ledger_table(ledger_rows),
        args.output_ledger,
        compression="zstd",
    )
    args.output_markdown.write_text(
        render_markdown(report),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "decisions": len(decisions),
                "raw_outcomes": len(raw_outcomes),
                "entry_outcomes": len(entry_outcomes),
                "binance_bars": len(binance_bars),
                "binance_local_raw_prices": len(binance_loaded),
                "hfm_prices": len(hfm_prices),
                "orders_sent": False,
                "json": str(args.output_json),
                "ledger": str(args.output_ledger),
                "markdown": str(args.output_markdown),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

