"""Generate deterministic end-to-end and filter-equivalence evidence for phase 6."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.orderflow.big_trades.aggregation import create_big_trade_event  # noqa: E402
from src.orderflow.big_trades.constants import (  # noqa: E402
    AutomaticIntensity,
    ClusterCloseReason,
    FilterMode,
    MarkerPriceMode,
    SideFilter,
)
from src.orderflow.big_trades.filtering import (  # noqa: E402
    AutomaticSizeFilter,
    decide_cluster,
)
from src.orderflow.big_trades.models import (  # noqa: E402
    BigTradeFill,
    BigTradesSettingsSnapshot,
    ExecutionCluster,
)
from tools.big_trades_phase6_soak import (  # noqa: E402
    SOURCE_BASE,
    _runtime,
    _settle,
)
from webapp.big_trades_history import BigTradesHistoryService  # noqa: E402
from webapp.big_trades_protocol import big_trades_json_value  # noqa: E402


UTC = timezone.utc


def _trade(
    trade_id: int,
    milliseconds: int,
    price: str,
    quantity: str,
    side: str,
) -> BigTradeFill:
    source_time = SOURCE_BASE + timedelta(milliseconds=milliseconds)
    return BigTradeFill(
        event_time=source_time,
        trade_time=source_time,
        trade_id=trade_id,
        symbol="BTCUSDT",
        venue="BINANCE",
        price=Decimal(price),
        quantity=Decimal(quantity),
        side=side,
    )


def _scenario() -> tuple[BigTradeFill, ...]:
    return (
        _trade(1, 0, "100", "6", "BUY"),
        _trade(2, 10, "101", "6", "BUY"),
        _trade(3, 100, "102", "1", "SELL"),
        _trade(4, 200, "101", "6", "SELL"),
        _trade(5, 210, "100", "6", "SELL"),
        _trade(6, 300, "99", "1", "BUY"),
        _trade(7, 400, "110", "6", "BUY"),
        _trade(8, 410, "111", "6", "BUY"),
        _trade(9, 500, "112", "1", "SELL"),
        _trade(10, 1_011, "101", "1", "SELL"),
        _trade(11, 1_211, "100", "1", "BUY"),
        _trade(12, 1_411, "111", "1", "SELL"),
        _trade(13, 5_061, "112", "1", "BUY"),
        _trade(14, 5_461, "111", "1", "SELL"),
    )


def _browser_projection(details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    program = r"""
const fs=require('fs'),vm=require('vm');
vm.runInThisContext(fs.readFileSync(process.argv[1],'utf8'),{filename:process.argv[1]});
const api=globalThis.DeltaBigTradesV2,input=JSON.parse(fs.readFileSync(0,'utf8'));
const output=input.map(detail=>{
  const events=new api.BigTradeEventStore(5000),zones=new api.ReactionZoneStore(5000,20000);
  events.merge([detail.origin_event]);zones.mergeDetail(detail);zones.select(detail.zone.zone_id);
  const selected=zones.selected(),state=zones.state(selected.zone_id);
  return {
    validated:true,event_id:events.get(detail.origin_event.event_id).event_id,
    marker:{time:detail.origin_event.marker_time,price:detail.origin_event.marker_price,quantity:detail.origin_event.aggregate_quantity,side:detail.origin_event.side},
    reaction_zone:{zone_id:selected.zone_id,low:selected.zone_low,high:selected.zone_high,lifecycle:state.lifecycle,current_relation:state.relation},
    history:{interactions:zones.interactionsFor(selected.zone_id).length,linked_events:zones.linksFor(selected.zone_id).length,snapshots:zones.snapshotsFor(selected.zone_id).length,gap_segments:state.gaps.length}
  };
});
process.stdout.write(JSON.stringify(output));
"""
    completed = subprocess.run(
        [
            "node",
            "-e",
            program,
            str(ROOT / "webapp" / "static" / "big_trades.js"),
        ],
        input=json.dumps(details, ensure_ascii=False),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"browser projection failed: {completed.stderr.strip()}")
    return json.loads(completed.stdout)


def _equivalence(fills: tuple[BigTradeFill, ...]) -> dict[str, Any]:
    manual_settings = BigTradesSettingsSnapshot(
        settings_id="manual-equivalence",
        symbol="BTCUSDT",
        venue="BINANCE",
        filter_mode=FilterMode.MANUAL,
        manual_min_quantity=Decimal("10"),
        manual_max_quantity=Decimal("0"),
        automatic_intensity=AutomaticIntensity.MEDIUM,
        side_filter=SideFilter.BOTH,
        marker_price_mode=MarkerPriceMode.LAST_PRICE,
    )
    automatic_settings = replace(
        manual_settings,
        settings_id="automatic-equivalence",
        filter_mode=FilterMode.AUTOMATIC,
        calibration_id="calibration-equivalence",
    )
    manual_cluster = ExecutionCluster(
        fills,
        manual_settings,
        ClusterCloseReason.SIDE_CHANGED,
    )
    automatic_cluster = ExecutionCluster(
        fills,
        automatic_settings,
        ClusterCloseReason.SIDE_CHANGED,
    )
    automatic_filter = AutomaticSizeFilter(
        calibration_id="calibration-equivalence",
        thresholds={
            AutomaticIntensity.LOW: Decimal("5"),
            AutomaticIntensity.MEDIUM: Decimal("10"),
            AutomaticIntensity.STRONG: Decimal("20"),
        },
    )
    manual_decision = decide_cluster(manual_cluster)
    automatic_decision = decide_cluster(automatic_cluster, automatic_filter)
    manual_event = create_big_trade_event(manual_cluster, manual_decision)
    automatic_event = create_big_trade_event(automatic_cluster, automatic_decision)
    compared_fields = (
        "event_id",
        "symbol",
        "venue",
        "side",
        "first_trade_id",
        "last_trade_id",
        "first_time",
        "last_time",
        "marker_time",
        "first_price",
        "last_price",
        "marker_price",
        "low_price",
        "high_price",
        "vwap",
        "aggregate_quantity",
        "aggregate_notional",
        "fill_count",
        "price_level_count",
        "duration_ms",
        "close_reason",
        "session_id",
        "candle_id",
    )
    equal = {
        field: getattr(manual_event, field) == getattr(automatic_event, field)
        for field in compared_fields
    }
    return big_trades_json_value(
        {
            "status": "PASS"
            if manual_decision.accepted
            and automatic_decision.accepted
            and all(equal.values())
            else "FAIL",
            "manual": {
                "accepted": manual_decision.accepted,
                "threshold": manual_decision.threshold_used,
                "event_id": manual_event.event_id,
                "content_hash": manual_event.content_hash,
            },
            "automatic": {
                "accepted": automatic_decision.accepted,
                "intensity": automatic_decision.intensity,
                "threshold": automatic_decision.threshold_used,
                "calibration_id": automatic_decision.calibration_id,
                "event_id": automatic_event.event_id,
                "content_hash": automatic_event.content_hash,
            },
            "equal_execution_fields": equal,
            "expected_lineage_difference": (
                "filter mode/settings/calibration metadata differ; execution identity and facts are equal"
            ),
        }
    )


def run() -> dict[str, Any]:
    trades = _scenario()
    with tempfile.TemporaryDirectory(prefix="bt2-phase6-traces-") as temporary:
        root = Path(temporary)
        settings, activation, store, writer, runtime = _runtime(root)
        try:
            for trade in trades:
                runtime.process(trade)
            runtime.start_source_gap(SOURCE_BASE + timedelta(milliseconds=6_000))
            runtime.process(_trade(15, 7_000, "112", "1", "BUY"))
            runtime.flush()
            _settle(writer, runtime)

            history = BigTradesHistoryService(
                store,
                symbol="BTCUSDT",
                venue="BINANCE",
            )
            events = store.fetch_rows(
                "big_trade_events", order_by="last_time ASC, event_id ASC"
            )
            zones = store.fetch_rows(
                "big_trade_reaction_zones", order_by="zone_source_start ASC, zone_id ASC"
            )
            zone_by_event = {row["origin_event_id"]: row for row in zones}
            details = [
                big_trades_json_value(history.zone_detail(zone_by_event[event["event_id"]]["zone_id"]))
                for event in events
            ]
            browser = _browser_projection(details)
            traces = []
            for event, detail, ui in zip(events, details, browser, strict=True):
                fills = history.event_fills(event["event_id"], limit=5_000)["fills"]
                traces.append(
                    big_trades_json_value(
                        {
                            "raw_trades": fills,
                            "cluster": {
                                "close_reason": event["close_reason"],
                                "first_trade_id": event["first_trade_id"],
                                "last_trade_id": event["last_trade_id"],
                                "aggregate_quantity": event["aggregate_quantity"],
                                "aggregate_notional": event["aggregate_notional"],
                                "fill_count": event["fill_count"],
                                "low_price": event["low_price"],
                                "high_price": event["high_price"],
                            },
                            "event": event,
                            "zone": detail["zone"],
                            "interactions": detail["interactions"],
                            "linked_events": detail["linked_event_summary"],
                            "snapshots": detail["horizon_snapshots"],
                            "ui_projection": ui,
                        }
                    )
                )

            first_types = [
                row["interaction_type"] for row in traces[0]["interactions"]
            ]
            stale = [
                snapshot
                for trace in traces
                for snapshot in trace["snapshots"]
                if snapshot["validity"] == "MISSING_STALE"
            ]
            gaps = [
                row
                for trace in traces
                for row in trace["interactions"]
                if row["interaction_type"]
                in {"SOURCE_GAP_STARTED", "SOURCE_GAP_ENDED"}
            ]
            unavailable_cluster = ExecutionCluster(
                trades[:2],
                BigTradesSettingsSnapshot(
                    settings_id="automatic-unavailable",
                    symbol="BTCUSDT",
                    venue="BINANCE",
                    filter_mode=FilterMode.AUTOMATIC,
                    manual_min_quantity=Decimal("0"),
                    manual_max_quantity=Decimal("0"),
                    automatic_intensity=AutomaticIntensity.MEDIUM,
                    side_filter=SideFilter.BOTH,
                    marker_price_mode=MarkerPriceMode.LAST_PRICE,
                    calibration_id=None,
                ),
                ClusterCloseReason.SIDE_CHANGED,
            )
            unavailable = decide_cluster(unavailable_cluster)
            equivalence = _equivalence(trades[:2])
            checks = {
                "three_complete_traces": len(traces) == 3
                and all(
                    trace["raw_trades"]
                    and trace["interactions"]
                    and trace["snapshots"]
                    and trace["ui_projection"]["validated"]
                    for trace in traces
                ),
                "manual_automatic_equivalence": equivalence["status"] == "PASS",
                "break_retest_reentry": {
                    "FIRST_EXIT_UP",
                    "TOUCH_FROM_ABOVE",
                    "REENTER_FROM_ABOVE",
                    "CROSS_UP",
                }.issubset(first_types),
                "opposite_linked_event": bool(traces[0]["linked_events"])
                and traces[1]["event"]["side"] == "SELL",
                "stale_visible": bool(stale),
                "gap_visible": bool(gaps),
                "fail_closed_visible": unavailable.accepted is False
                and unavailable.reason.value == "AUTOMATIC_UNAVAILABLE",
                "runtime_errors_zero": runtime.statistics()["errors"] == 0,
            }
            result = {
                "status": "PASS" if all(checks.values()) else "FAIL",
                "generated_at_utc": datetime.now(UTC).isoformat(),
                "checks": checks,
                "versions": {
                    "logic": "BTLOGIC-2.0",
                    "settings_id": settings.settings_id,
                    "activation_id": activation.activation_id,
                },
                "traces": traces,
                "manual_automatic_equivalence": equivalence,
                "zone_history_trace": {
                    "zone_id": traces[0]["zone"]["zone_id"],
                    "interaction_types": first_types,
                    "linked_events": traces[0]["linked_events"],
                },
                "gap_stale_fail_closed_examples": {
                    "gap_interactions": gaps,
                    "stale_snapshots": stale,
                    "source_gap_status": runtime.status.value,
                    "automatic_unavailable": big_trades_json_value(
                        {
                            "accepted": unavailable.accepted,
                            "reason": unavailable.reason,
                            "status": "CALIBRATION_UNAVAILABLE",
                        }
                    ),
                },
                "storage": "temporary isolated DuckDB deleted after read-back",
                "production_mutations": 0,
            }
        finally:
            writer.close()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": result["status"], "checks": result["checks"]}))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
