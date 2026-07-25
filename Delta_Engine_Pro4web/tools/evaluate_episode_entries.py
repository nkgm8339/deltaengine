"""Evaluate pre-registered 5M/10M episode entry candidates offline.

The command reads existing Parquet data and writes research artifacts only.
It does not import the live web application, send commands, or mutate source
market data.
"""

from __future__ import annotations

import argparse
import glob
import json
import statistics
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import duckdb
import pyarrow.parquet as pq

from src.orderflow.episode_dataset import PriceObservation
from src.orderflow.episode_entry import (
    ATTACK_ENTRY,
    PERSIST_ENTRY,
    RESOLUTION_ENTRY,
    EntryPathOutcome,
    EpisodeEntryPathEvaluator,
    extract_entry_candidates,
    purge_overlapping_candidates,
)
from src.orderflow.orderflow_episode import FlowObservation, build_episodes


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--flow-glob",
        default="data_05M/parquet/flow_response_events/**/*.parquet",
    )
    parser.add_argument(
        "--raw-glob",
        default="data_05M/parquet/symbol=BTCUSDT/year=*/**/*.parquet",
    )
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--windows", nargs="+", type=int, default=(60, 300))
    parser.add_argument("--horizons", nargs="+", type=int, default=(300, 600))
    parser.add_argument("--cost-usd", nargs="+", type=float, default=(20.0, 30.0))
    parser.add_argument("--max-gap-sec", type=int, default=120)
    parser.add_argument("--max-episode-sec", type=int, default=600)
    parser.add_argument("--purge-horizon-sec", type=int, default=600)
    parser.add_argument("--stable-file-age-sec", type=int, default=60)
    parser.add_argument(
        "--entry-cutoff",
        help="inclusive ISO-8601 cutoff for entry observations",
    )
    parser.add_argument(
        "--hfm-quotes",
        type=Path,
        default=Path("data_05M/hfm/DeltaEngine_HFM_quotes_utf8.jsonl"),
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("data_05M/research/episode_entry_v1_20260725.json"),
    )
    parser.add_argument(
        "--output-markdown",
        type=Path,
        default=Path(
            "../ArchitectureRepository/00_Master/"
            "ORDERFLOW_5M10M_ENTRY_EVALUATION_20260725.md"
        ),
    )
    return parser.parse_args()


def _stable_parquet_files(path_glob: str, *, min_age_sec: int) -> tuple[str, ...]:
    """Freeze a file list and exclude files that may still be live-written."""
    if min_age_sec < 0:
        raise ValueError("min_age_sec must not be negative")
    cutoff = time.time() - min_age_sec
    files = []
    for raw_path in glob.glob(path_glob, recursive=True):
        path = Path(raw_path)
        try:
            if path.is_file() and path.suffix.lower() == ".parquet" and path.stat().st_mtime <= cutoff:
                files.append(str(path))
        except OSError:
            continue
    if not files:
        raise FileNotFoundError(f"no stable parquet files matched {path_glob!r}")
    return tuple(sorted(files))


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("entry cutoff must be timezone-aware")
    return parsed


def _load_flow_observations(
    connection: duckdb.DuckDBPyConnection,
    parquet_files: tuple[str, ...],
    *,
    symbol: str,
    windows: tuple[int, ...],
    entry_cutoff: datetime | None,
) -> tuple[FlowObservation, ...]:
    placeholders = ",".join("?" for _ in windows)
    query = f"""
        SELECT DISTINCT
            event_time, symbol, window_sec, state, pressure_side,
            pressure_ratio, persistence, relative_volume,
            price_change_bps, last_price
        FROM read_parquet(?, union_by_name=true)
        WHERE symbol = ?
          AND window_sec IN ({placeholders})
          AND last_price > 0
          AND (? IS NULL OR event_time <= ?)
        ORDER BY event_time, window_sec
    """
    rows = connection.execute(
        query,
        [list(parquet_files), symbol, *windows, entry_cutoff, entry_cutoff],
    ).fetchall()
    return tuple(
        FlowObservation(
            event_time=row[0],
            symbol=str(row[1]),
            window_sec=int(row[2]),
            state=str(row[3]),
            pressure_side=str(row[4]),
            pressure_ratio=float(row[5]),
            persistence=float(row[6]),
            relative_volume=float(row[7]) if row[7] is not None else None,
            price_change_bps=float(row[8]),
            last_price=float(row[9]),
        )
        for row in rows
    )


def _load_prices(
    parquet_files: tuple[str, ...],
    *,
    price_cutoff: datetime | None,
) -> tuple[tuple[PriceObservation, ...], dict[str, object]]:
    """Read immutable raw-trade columns file-by-file with explicit exclusions."""
    rows: list[tuple[datetime, int, float]] = []
    seen_trade_ids: set[int] = set()
    rejected_files: list[dict[str, str]] = []
    non_trade_files = 0
    duplicate_trade_ids = 0
    missing_required = 0
    nonpositive_price = 0
    after_cutoff = 0
    rows_seen = 0
    for raw_path in parquet_files:
        try:
            columns = pq.ParquetFile(raw_path).read(
                columns=["trade_time", "trade_id", "price"]
            ).to_pydict()
        except Exception as exc:
            rejected_files.append(
                {
                    "path": raw_path,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:300],
                }
            )
            continue
        if not {"trade_time", "trade_id", "price"}.issubset(columns):
            non_trade_files += 1
            continue
        for event_time, trade_id, price in zip(
            columns["trade_time"], columns["trade_id"], columns["price"]
        ):
            rows_seen += 1
            if event_time is None or trade_id is None or price is None:
                missing_required += 1
                continue
            numeric_price = float(price)
            if numeric_price <= 0:
                nonpositive_price += 1
                continue
            if price_cutoff is not None and event_time > price_cutoff:
                after_cutoff += 1
                continue
            numeric_trade_id = int(trade_id)
            if numeric_trade_id in seen_trade_ids:
                duplicate_trade_ids += 1
                continue
            seen_trade_ids.add(numeric_trade_id)
            rows.append((event_time, numeric_trade_id, numeric_price))
    rows.sort(key=lambda value: (value[0], value[1]))
    prices = tuple(
        PriceObservation(event_time=event_time, price=price)
        for event_time, _, price in rows
    )
    audit: dict[str, object] = {
        "files_considered": len(parquet_files),
        "files_rejected": len(rejected_files),
        "non_trade_files_ignored": non_trade_files,
        "rejected_files": rejected_files,
        "rows_seen": rows_seen,
        "rows_included": len(prices),
        "rows_missing_required": missing_required,
        "rows_nonpositive_price": nonpositive_price,
        "rows_after_cutoff": after_cutoff,
        "duplicate_trade_ids": duplicate_trade_ids,
    }
    return prices, audit


def _session_id(value: datetime) -> str:
    hour = value.astimezone(timezone.utc).hour
    if hour < 8:
        return "ASIA"
    if hour < 13:
        return "EUROPE"
    if hour < 17:
        return "EUROPE_NY_OVERLAP"
    if hour < 22:
        return "NEW_YORK"
    return "LATE"


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _summary_row(
    outcomes: list[EntryPathOutcome],
    *,
    cost_usd: float,
    session_id: str,
) -> dict[str, object]:
    statuses = Counter(value.status for value in outcomes)
    ok = [value for value in outcomes if value.status == "OK"]
    signed = [float(value.signed_return_bps) for value in ok]
    net = [float(value.proxy_net_return_bps) for value in ok]
    rule_net = [float(value.rule_proxy_net_return_bps) for value in ok]
    mfe = [float(value.mfe_bps) for value in ok]
    mae = [float(value.mae_bps) for value in ok]
    hurdle = Counter(value.hurdle_order for value in ok)
    invalidation_known = [
        value for value in ok if value.invalidation_before_favorable is not None
    ]
    first_invalidations = sum(
        value.invalidation_before_favorable is True for value in invalidation_known
    )
    first = outcomes[0]
    return {
        "window_sec": first.window_sec,
        "candidate_type": first.candidate_type,
        "horizon_sec": first.horizon_sec,
        "proxy_cost_usd": cost_usd,
        "session_id": session_id,
        "label_count": len(outcomes),
        "status_counts": dict(sorted(statuses.items())),
        "ok_count": len(ok),
        "mean_signed_return_bps": _mean(signed),
        "median_signed_return_bps": _median(signed),
        "mean_proxy_net_bps": _mean(net),
        "median_proxy_net_bps": _median(net),
        "positive_proxy_net_rate": _rate(sum(value > 0 for value in net), len(net)),
        "median_rule_proxy_net_bps": _median(rule_net),
        "positive_rule_proxy_net_rate": _rate(
            sum(value > 0 for value in rule_net), len(rule_net)
        ),
        "price_invalidation_exit_rate": _rate(
            sum(value.rule_exit_reason == "PRICE_INVALIDATION" for value in ok),
            len(ok),
        ),
        "median_mfe_bps": _median(mfe),
        "median_mae_bps": _median(mae),
        "favorable_first_rate": _rate(hurdle["FAVORABLE_FIRST"], len(ok)),
        "adverse_first_rate": _rate(hurdle["ADVERSE_FIRST"], len(ok)),
        "neither_hurdle_rate": _rate(hurdle["NEITHER"], len(ok)),
        "invalidation_eligible_count": len(invalidation_known),
        "invalidation_before_favorable_rate": _rate(
            first_invalidations, len(invalidation_known)
        ),
    }


def _summaries(
    outcomes: Iterable[EntryPathOutcome], *, cost_usd: float
) -> tuple[dict[str, object], ...]:
    overall: dict[tuple[int, str, int], list[EntryPathOutcome]] = defaultdict(list)
    sessions: dict[tuple[int, str, int, str], list[EntryPathOutcome]] = defaultdict(list)
    for outcome in outcomes:
        overall[(outcome.window_sec, outcome.candidate_type, outcome.horizon_sec)].append(
            outcome
        )
        session = _session_id(outcome.entry_time)
        sessions[
            (outcome.window_sec, outcome.candidate_type, outcome.horizon_sec, session)
        ].append(outcome)
    result = [
        _summary_row(values, cost_usd=cost_usd, session_id="ALL")
        for _, values in sorted(overall.items())
    ]
    result.extend(
        _summary_row(values, cost_usd=cost_usd, session_id=key[3])
        for key, values in sorted(sessions.items())
    )
    return tuple(result)


def _paired_comparisons(
    outcomes: Iterable[EntryPathOutcome], *, cost_usd: float
) -> tuple[dict[str, object], ...]:
    by_key = {
        (
            value.episode_id,
            value.window_sec,
            value.candidate_type,
            value.horizon_sec,
        ): value
        for value in outcomes
        if value.status == "OK"
    }
    rows: list[dict[str, object]] = []
    resolutions = [
        value
        for value in by_key.values()
        if value.candidate_type == RESOLUTION_ENTRY
    ]
    for comparison_type in (ATTACK_ENTRY, PERSIST_ENTRY):
        grouped_signed: dict[tuple[int, int], list[float]] = defaultdict(list)
        grouped_net: dict[tuple[int, int], list[float]] = defaultdict(list)
        for resolution in resolutions:
            comparison = by_key.get(
                (
                    resolution.episode_id,
                    resolution.window_sec,
                    comparison_type,
                    resolution.horizon_sec,
                )
            )
            if comparison is None:
                continue
            key = (resolution.window_sec, resolution.horizon_sec)
            grouped_signed[key].append(
                float(resolution.signed_return_bps)
                - float(comparison.signed_return_bps)
            )
            grouped_net[key].append(
                float(resolution.proxy_net_return_bps)
                - float(comparison.proxy_net_return_bps)
            )
        for key, signed in sorted(grouped_signed.items()):
            net = grouped_net[key]
            rows.append(
                {
                    "window_sec": key[0],
                    "horizon_sec": key[1],
                    "proxy_cost_usd": cost_usd,
                    "resolution_vs": comparison_type,
                    "paired_episode_count": len(signed),
                    "mean_signed_difference_bps": _mean(signed),
                    "median_signed_difference_bps": _median(signed),
                    "mean_net_difference_bps": _mean(net),
                    "median_net_difference_bps": _median(net),
                }
            )
    return tuple(rows)


def _primary_breakdowns(
    outcomes: Iterable[EntryPathOutcome], *, cost_usd: float
) -> tuple[dict[str, object], ...]:
    grouped: dict[
        tuple[int, int, str, str], list[EntryPathOutcome]
    ] = defaultdict(list)
    for outcome in outcomes:
        if outcome.candidate_type != RESOLUTION_ENTRY:
            continue
        key = (
            outcome.window_sec,
            outcome.horizon_sec,
            outcome.entry_stage.value,
            outcome.trade_side,
        )
        grouped[key].append(outcome)
    rows: list[dict[str, object]] = []
    for key, values in sorted(grouped.items()):
        row = _summary_row(values, cost_usd=cost_usd, session_id="ALL")
        row["entry_stage"] = key[2]
        row["trade_side"] = key[3]
        rows.append(row)
    return tuple(rows)


def _count_by(values: Iterable[object], *attributes: str) -> list[dict[str, object]]:
    counts: Counter[tuple[object, ...]] = Counter(
        tuple(getattr(value, attribute) for attribute in attributes) for value in values
    )
    return [
        {**dict(zip(attributes, key)), "count": count}
        for key, count in sorted(counts.items())
    ]


def _number(value: object, digits: int = 3) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _markdown(report: dict[str, object]) -> str:
    meta = report["metadata"]
    raw_audit = report["raw_load_audit"]
    lines = [
        "# 5M/10M Episode Entry Spec v1 オフライン評価",
        "",
        f"生成時刻: {meta['generated_at']}",
        "判定: **EXPLORATORY_INSUFFICIENT_DATA**",
        "",
        "## 評価境界",
        "",
        "- 既存1M Flow Price Responseと3段チャートは変更していない",
        "- LIVE／MT5注文は生成していない",
        "- 60秒観測と300秒観測を、300秒／600秒outcomeから分離した",
        "- proxy costは過去実測spread 20 USDと1.5倍stress 30 USDを一回だけ控除した",
        f"- HFM同一時計quote bytes: {meta['hfm_quote_bytes']}",
        "",
        "## 現在の運用判定",
        "",
        f"- Entry Spec v1: **{meta['deployment_decision']}**",
        f"- 30 USD proxy: **{meta['observed_proxy_cost_result']}**",
        "- 意味: 現在の結果からMT5／LIVE発注へ進まない。理論全体の統計的棄却ではない。",
        "",
        "## データ",
        "",
        f"- Flow observations: {meta['flow_observation_count']}",
        f"- RAW trades: {meta['price_observation_count']}",
        f"- RAW期間: {meta['price_start']} ～ {meta['price_end']}",
        f"- entry cutoff: {meta['analysis_entry_cutoff']}",
        f"- outcome price cutoff: {meta['analysis_price_cutoff']}",
        f"- 観測日数: {_number(meta['observed_days'], 4)}",
        f"- RAW files rejected: {raw_audit['files_rejected']}",
        f"- non-trade schema files ignored: {raw_audit['non_trade_files_ignored']}",
        f"- duplicate trade IDs excluded: {raw_audit['duplicate_trade_ids']}",
        f"- nonpositive prices excluded: {raw_audit['rows_nonpositive_price']}",
        "",
        "## 非重複候補の全体結果",
        "",
        "| cost USD | obs | entry | horizon | OK | median gross bps | median net bps | invalidation-or-horizon net | median MFE | median MAE | favorable first | adverse first |",
        "|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    overall = [row for row in report["summaries"] if row["session_id"] == "ALL"]
    for row in overall:
        lines.append(
            "| {cost} | {window} | {entry} | {horizon} | {ok} | {gross} | "
            "{net} | {rule_net} | {mfe} | {mae} | {fav} | {adv} |".format(
                cost=_number(row["proxy_cost_usd"], 0),
                window=row["window_sec"],
                entry=row["candidate_type"],
                horizon=row["horizon_sec"],
                ok=row["ok_count"],
                gross=_number(row["median_signed_return_bps"]),
                net=_number(row["median_proxy_net_bps"]),
                rule_net=_number(row["median_rule_proxy_net_bps"]),
                mfe=_number(row["median_mfe_bps"]),
                mae=_number(row["median_mae_bps"]),
                fav=_number(row["favorable_first_rate"]),
                adv=_number(row["adverse_first_rate"]),
            )
        )
    lines.extend(
        [
            "",
            "## 主候補の解放種別・売買方向別stress結果",
            "",
            "30 USD costの主候補を、突破と反転、BUYとSELLへ分離する。",
            "",
            "| obs | horizon | resolution | side | OK | median gross bps | median net bps | invalidation-or-horizon net | favorable first | adverse first | invalidation first |",
            "|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in report["primary_breakdowns"]:
        if row["proxy_cost_usd"] != 30.0:
            continue
        lines.append(
            "| {window} | {horizon} | {stage} | {side} | {ok} | {gross} | {net} | {rule_net} | {fav} | {adv} | {inv} |".format(
                window=row["window_sec"],
                horizon=row["horizon_sec"],
                stage=row["entry_stage"],
                side=row["trade_side"],
                ok=row["ok_count"],
                gross=_number(row["median_signed_return_bps"]),
                net=_number(row["median_proxy_net_bps"]),
                rule_net=_number(row["median_rule_proxy_net_bps"]),
                fav=_number(row["favorable_first_rate"]),
                adv=_number(row["adverse_first_rate"]),
                inv=_number(row["invalidation_before_favorable_rate"]),
            )
        )
    lines.extend(
        [
            "",
            "## 主候補のセッション別stress結果",
            "",
            "30 USD cost、`RESOLUTION_CONFIRMED_V1`だけを固定UTCセッションで表示する。",
            "",
            "| obs | horizon | session | OK | median net bps | favorable first | adverse first | invalidation first |",
            "|---:|---:|---|---:|---:|---:|---:|---:|",
        ]
    )
    primary_sessions = [
        row
        for row in report["summaries"]
        if row["session_id"] != "ALL"
        and row["candidate_type"] == RESOLUTION_ENTRY
        and row["proxy_cost_usd"] == 30.0
    ]
    for row in primary_sessions:
        lines.append(
            "| {window} | {horizon} | {session} | {ok} | {net} | {fav} | {adv} | {inv} |".format(
                window=row["window_sec"],
                horizon=row["horizon_sec"],
                session=row["session_id"],
                ok=row["ok_count"],
                net=_number(row["median_proxy_net_bps"]),
                fav=_number(row["favorable_first_rate"]),
                adv=_number(row["adverse_first_rate"]),
                inv=_number(row["invalidation_before_favorable_rate"]),
            )
        )
    lines.extend(
        [
            "",
            "## 判定制約",
            "",
            "- 30日未満かつpurge後200 Episode未満なので、優位性を宣言しない",
            "- 同日データで仕様確認した探索集計であり、untouched testではない",
            "- 20／30 USD控除はBinance価格上のproxyであり、HFM伝達性を証明しない",
            "- HFM同一時計Bid／Askが無いためGate 3／4は未評価",
            "- 各ローリング更新を独立取引として数えず、600秒重複purgeを主表に使用した",
            "",
            "詳細なstatus件数、raw／purged候補数、paired比較、全行outcomeはJSON成果物に保存した。",
            "",
        ]
    )
    return "\n".join(lines)


def _json_default(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    raise TypeError(f"cannot serialize {type(value).__name__}")


def main() -> int:
    args = _parse_args()
    windows = tuple(sorted(set(args.windows)))
    horizons = tuple(sorted(set(args.horizons)))
    costs = tuple(sorted(set(float(value) for value in args.cost_usd)))
    entry_cutoff = _parse_datetime(args.entry_cutoff)
    price_cutoff = (
        entry_cutoff + timedelta(seconds=max(horizons) + 30)
        if entry_cutoff is not None
        else None
    )
    connection = duckdb.connect()
    connection.execute("SET TimeZone='UTC'")
    flow_files = _stable_parquet_files(
        args.flow_glob, min_age_sec=args.stable_file_age_sec
    )
    raw_files = _stable_parquet_files(
        args.raw_glob, min_age_sec=args.stable_file_age_sec
    )
    observations = _load_flow_observations(
        connection,
        flow_files,
        symbol=args.symbol,
        windows=windows,
        entry_cutoff=entry_cutoff,
    )
    prices, raw_load_audit = _load_prices(
        raw_files,
        price_cutoff=price_cutoff,
    )
    episodes = []
    for window_sec in windows:
        episodes.extend(
            build_episodes(
                observations,
                symbol=args.symbol,
                window_sec=window_sec,
                max_gap_sec=args.max_gap_sec,
                max_episode_sec=args.max_episode_sec,
            )
        )
    candidates = extract_entry_candidates(episodes)
    purged = purge_overlapping_candidates(
        candidates, horizon_sec=args.purge_horizon_sec
    )

    summaries: list[dict[str, object]] = []
    paired: list[dict[str, object]] = []
    primary_breakdowns: list[dict[str, object]] = []
    outcome_rows: list[dict[str, object]] = []
    for cost_usd in costs:
        evaluator = EpisodeEntryPathEvaluator(
            horizons,
            proxy_cost_usd=cost_usd,
            max_data_gap_sec=args.max_gap_sec,
        )
        raw_outcomes = evaluator.evaluate(candidates, prices)
        purged_outcomes = evaluator.evaluate(purged, prices)
        summaries.extend(_summaries(purged_outcomes, cost_usd=cost_usd))
        paired.extend(_paired_comparisons(raw_outcomes, cost_usd=cost_usd))
        primary_breakdowns.extend(
            _primary_breakdowns(purged_outcomes, cost_usd=cost_usd)
        )
        outcome_rows.extend(value.to_row() for value in purged_outcomes)

    hfm_bytes = args.hfm_quotes.stat().st_size if args.hfm_quotes.exists() else 0
    price_start = prices[0].event_time if prices else None
    price_end = prices[-1].event_time if prices else None
    observed_days = (
        (price_end - price_start).total_seconds() / 86_400
        if price_start is not None and price_end is not None
        else 0.0
    )
    primary_stress = [
        row
        for row in summaries
        if row["session_id"] == "ALL"
        and row["candidate_type"] == RESOLUTION_ENTRY
        and row["proxy_cost_usd"] == 30.0
        and row["ok_count"] > 0
    ]
    no_positive_stress_median = bool(primary_stress) and all(
        float(row["median_proxy_net_bps"]) <= 0
        and float(row["median_rule_proxy_net_bps"]) <= 0
        for row in primary_stress
    )
    report: dict[str, object] = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc),
            "symbol": args.symbol,
            "windows_sec": windows,
            "horizons_sec": horizons,
            "proxy_cost_usd": costs,
            "max_gap_sec": args.max_gap_sec,
            "max_episode_sec": args.max_episode_sec,
            "purge_horizon_sec": args.purge_horizon_sec,
            "stable_file_age_sec": args.stable_file_age_sec,
            "stable_flow_file_count": len(flow_files),
            "stable_raw_file_count": len(raw_files),
            "analysis_entry_cutoff": entry_cutoff,
            "analysis_price_cutoff": price_cutoff,
            "flow_observation_count": len(observations),
            "price_observation_count": len(prices),
            "price_start": price_start,
            "price_end": price_end,
            "observed_days": observed_days,
            "hfm_quote_bytes": hfm_bytes,
            "gate_status": "EXPLORATORY_INSUFFICIENT_DATA",
            "deployment_decision": "NO_GO_FOR_HFM_ENTRY_V1",
            "observed_proxy_cost_result": (
                "NO_POSITIVE_MEDIAN_AT_30_USD"
                if no_positive_stress_median
                else "MIXED_OR_NOT_EVALUABLE"
            ),
            "hfm_gate_status": "NOT_EVALUATED_NO_SAME_CLOCK_QUOTES"
            if hfm_bytes == 0
            else "NOT_EVALUATED_BY_THIS_PROXY_REPORT",
        },
        "raw_load_audit": raw_load_audit,
        "episode_counts": _count_by(episodes, "window_sec", "stage"),
        "raw_candidate_counts": _count_by(
            candidates, "window_sec", "candidate_type"
        ),
        "purged_candidate_counts": _count_by(
            purged, "window_sec", "candidate_type"
        ),
        "summaries": summaries,
        "paired_comparisons": paired,
        "primary_breakdowns": primary_breakdowns,
        "purged_resolution_counts": _count_by(
            (
                value
                for value in purged
                if value.candidate_type == RESOLUTION_ENTRY
            ),
            "window_sec",
            "entry_stage",
            "trade_side",
        ),
        "purged_candidates": [value.to_row() for value in purged],
        "purged_outcomes": outcome_rows,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=_json_default) + "\n",
        encoding="utf-8",
    )
    args.output_markdown.write_text(_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "episodes": len(episodes),
                "raw_candidates": len(candidates),
                "purged_candidates": len(purged),
                "json": str(args.output_json),
                "markdown": str(args.output_markdown),
                "gate": report["metadata"]["gate_status"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
