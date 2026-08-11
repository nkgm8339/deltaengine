from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from playwright.sync_api import Route, sync_playwright


BASE_URL = "http://127.0.0.1:18080"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
OUTPUT_DIR = Path(__file__).resolve().parent
FOOTPRINT_SCREENSHOT = OUTPUT_DIR / "footprint_before_1280x900_full.png"
BIG_TRADES_SCREENSHOT = OUTPUT_DIR / "big_trades_after_1280x900_full.png"
RESULT_JSON = OUTPUT_DIR / "browser_acceptance.json"
SELECTORS = (
    "#topbar", "#bottom", "#chartwrap", "#chart", "#liveobservation",
    "#main", "#center", "#right", "#fpstage", "#fpcanvas", "#heatmapcanvas",
    "#btworkspace", "#btcanvas", "#btdetail", "#tape", "#tapeviewport",
    "#btobservation", "#flowtop", "#flowpanel", "#flowbody",
)


def ident(prefix: str, digit: str) -> str:
    return prefix + digit * 64


EVENT_ID = ident("bt2_", "1")
ZONE_ID = ident("btz2_", "2")
SECOND_EVENT_ID = ident("bt2_", "3")
SECOND_ZONE_ID = ident("btz2_", "4")

EVENTS = [
    {
        "event_id": EVENT_ID, "content_hash": "a" * 64, "last_time": "2026-08-12T01:10:42.118Z",
        "marker_time": "2026-08-12T01:10:42.118Z", "marker_price": "63616.8", "side": "SELL",
        "aggregate_quantity": "57.349", "aggregate_notional": "3648968.8432", "fill_count": 184,
        "duration_ms": 37, "vwap": "63616.8", "threshold_used": "50.000", "price_level_count": 18,
    },
    {
        "event_id": SECOND_EVENT_ID, "content_hash": "b" * 64, "last_time": "2026-08-12T01:13:20.000Z",
        "marker_time": "2026-08-12T01:13:20.000Z", "marker_price": "63578.4", "side": "BUY",
        "aggregate_quantity": "26.500", "aggregate_notional": "1684867.6000", "fill_count": 72,
        "duration_ms": 24, "vwap": "63579.1", "threshold_used": "25.000", "price_level_count": 9,
    },
]

ZONES = [
    {
        "zone_id": ZONE_ID, "content_hash": "c" * 64, "origin_event_id": EVENT_ID,
        "zone_source_start": "2026-08-12T01:10:42.118Z", "zone_source_end": None,
        "zone_low": "63612.4", "zone_high": "63620.1", "zone_anchor": "63616.8", "origin_side": "SELL",
        "lifecycle": "ACTIVE_WITH_GAP", "current_relation": "BELOW",
        "gap_segments": [{"gap_epoch_id": "fixture-gap", "start_time": "2026-08-12T01:11:40Z", "end_time": "2026-08-12T01:11:55Z"}],
        "settings_id": ident("bts1_", "5"), "calibration_id": None,
        "activation_id": ident("bta1_", "6"), "logic_version": "BTLOGIC-2.0",
    },
    {
        "zone_id": SECOND_ZONE_ID, "content_hash": "d" * 64, "origin_event_id": SECOND_EVENT_ID,
        "zone_source_start": "2026-08-12T01:13:20.000Z", "zone_source_end": None,
        "zone_low": "63578.4", "zone_high": "63578.4", "zone_anchor": "63578.4", "origin_side": "BUY",
        "lifecycle": "ACTIVE", "current_relation": "ABOVE", "gap_segments": [],
        "settings_id": ident("bts1_", "5"), "calibration_id": None,
        "activation_id": ident("bta1_", "6"), "logic_version": "BTLOGIC-2.0",
    },
]

INTERACTIONS = [
    {
        "interaction_id": ident("bti2_", "7"), "content_hash": "e" * 64, "zone_id": ZONE_ID,
        "interaction_type": "FIRST_EXIT_UP", "source_event_time": "2026-08-12T01:10:42.402Z",
        "source_trade_id": 9101, "current_relation": "ABOVE", "direction": "UP", "ordinal": 1,
        "time_to_exit_ms": 284, "price": "63620.2",
    },
    {
        "interaction_id": ident("bti2_", "8"), "content_hash": "f" * 64, "zone_id": ZONE_ID,
        "interaction_type": "REENTER_FROM_ABOVE", "source_event_time": "2026-08-12T01:10:57.000Z",
        "source_trade_id": 9200, "current_relation": "INSIDE", "direction": "DOWN", "ordinal": 2,
        "time_to_exit_ms": None, "price": "63618.0",
    },
]

DETAIL = {
    "source_identity": {"schema_version": 2, "symbol": "BTCUSDT", "venue": "BINANCE", "input_mode": "AGGREGATE_TRADES", "logic_version": "BTLOGIC-2.0"},
    "zone": ZONES[0], "origin_event": EVENTS[0], "interactions": INTERACTIONS,
    "first_exit": INTERACTIONS[0], "excursions": {"max_above_ticks": "42", "max_below_ticks": "188"},
    "interaction_counts": {"TOUCH_FROM_ABOVE": 1, "REENTER_FROM_ABOVE": 1, "CROSS_DOWN": 1},
    "linked_event_summary": [{
        "link_id": ident("btl2_", "9"), "content_hash": "1" * 64, "zone_id": ZONE_ID,
        "origin_event_id": EVENT_ID, "linked_event_id": SECOND_EVENT_ID, "linked_side": "BUY",
        "linked_quantity": "26.500", "linked_low": "63612.9", "linked_high": "63619.9",
        "linked_time": "2026-08-12T01:12:48Z", "interval_gap_ticks": "0", "same_as_origin_side": False,
        "ordinal_for_zone": 1,
    }],
    "horizon_snapshots": [{
        "snapshot_id": ident("btsnap2_", "a"), "content_hash": "2" * 64, "zone_id": ZONE_ID,
        "horizon_seconds": 60, "target_time": "2026-08-12T01:11:42.118Z", "snapshot_trade_time": "2026-08-12T01:11:42.100Z",
        "relation": "BELOW", "validity": "VALID", "snapshot_price": "63590.0",
        "max_above_ticks": "42", "max_below_ticks": "188", "touch_count": 1, "cross_count": 1,
    }],
    "candle_observations": [{
        "candle_observation_id": ident("btcobs2_", "b"), "content_hash": "3" * 64, "zone_id": ZONE_ID,
        "candle_id": "2026-08-12T01:11:00Z", "open_price": "63618", "high_price": "63624",
        "low_price": "63588", "close_price": "63592", "open_relation": "INSIDE", "close_relation": "BELOW",
        "high_above_ticks": "39", "low_below_ticks": "244", "body_overlaps_zone": True,
        "wick_overlaps_zone": True, "closed_above": False, "closed_below": True,
        "upper_wick_return": True, "lower_wick_return": False,
    }],
    "gap_segments": ZONES[0]["gap_segments"], "latest_user_assessment": None,
    "user_assessment_history": [],
    "latest_checkpoint": {"inside_buy_quantity": "8.200", "inside_sell_quantity": "17.700", "current_relation": "BELOW"},
    "lineage_ids": {"event_id": EVENT_ID, "zone_id": ZONE_ID, "settings_id": ZONES[0]["settings_id"], "calibration_id": None, "activation_id": ZONES[0]["activation_id"], "logic_version": "BTLOGIC-2.0"},
}


def geometry(page: Any) -> dict[str, Any]:
    return page.evaluate(
        """selectors => Object.fromEntries(selectors.map(selector => {
          const element=document.querySelector(selector); if(!element)return [selector,null];
          const rect=element.getBoundingClientRect(),style=getComputedStyle(element);
          return [selector,{x:rect.x,y:rect.y,width:rect.width,height:rect.height,display:style.display,visibility:style.visibility,hidden:element.hidden===true}];
        }))""",
        list(SELECTORS),
    )


def frame_type(payload: str | bytes) -> str:
    if not isinstance(payload, str):
        return "<binary>"
    try:
        value = json.loads(payload)
    except json.JSONDecodeError:
        return "<non-json>"
    return value.get("type", "<json-unclassified>") if isinstance(value, dict) else "<json-unclassified>"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    console: list[dict[str, str]] = []
    page_errors: list[str] = []
    failed_requests: list[dict[str, str]] = []
    responses: list[dict[str, Any]] = []
    websocket_frames: Counter[str] = Counter()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=CHROME, args=("--disable-background-networking",))
        context = browser.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=1)
        page = context.new_page()

        def fulfill_json(route: Route, value: Any) -> None:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(value))

        page.route("**/api/history/big-trades/snapshot*", lambda route: fulfill_json(route, {
            "source_identity": DETAIL["source_identity"], "continuation": {"stream_id": "123e4567-e89b-42d3-a456-426614174000", "last_admitted_sequence": 0, "dropped_count": 0},
            "events": EVENTS, "zones": ZONES, "event_cursor": None, "zone_cursor": None,
        }))
        page.route("**/api/history/big-trades/zones/**", lambda route: fulfill_json(route, DETAIL))
        page.route("**/api/big-trades/settings", lambda route: fulfill_json(route, {"active": None, "pending": None, "history": []}))
        page.on("console", lambda message: console.append({"type": message.type, "text": message.text}))
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.on("requestfailed", lambda request: failed_requests.append({"url": request.url, "failure": request.failure or "unknown"}))
        page.on("response", lambda response: responses.append({"url": response.url, "status": response.status, "resource_type": response.request.resource_type}) if response.url.startswith(BASE_URL) else None)

        def on_websocket(websocket: Any) -> None:
            websocket.on("framereceived", lambda payload: websocket_frames.update((frame_type(payload),)))

        page.on("websocket", on_websocket)
        response = page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(5_000)
        footprint_geometry = geometry(page)
        page.screenshot(path=str(FOOTPRINT_SCREENSHOT), full_page=True)

        page.click("#modeHeatmap")
        page.wait_for_timeout(500)
        heatmap_geometry = geometry(page)
        page.click("#modeFootprint")
        page.wait_for_timeout(250)
        footprint_return_geometry = geometry(page)

        page.click("#modeBigTrades")
        page.wait_for_timeout(1_000)
        page.evaluate(
            """() => window.BIG_TRADES_UI.ingestStatus({v:1,type:'BIG_TRADES_STATUS',time:'2026-08-12T01:14:00Z',symbol:'BTCUSDT',payload:{status:'MANUAL_READY',reason:null,counters:{}}})"""
        )
        page.evaluate("zoneId => window.BIG_TRADES_UI.selectZone(zoneId)", ZONE_ID)
        page.wait_for_timeout(1_000)
        page.evaluate("() => { for(let i=0;i<60;i++) window.BIG_TRADES_UI.canvas.draw(true); }")
        big_geometry = geometry(page)
        page.screenshot(path=str(BIG_TRADES_SCREENSHOT), full_page=True)

        protected = ("#bottom", "#chartwrap", "#chart", "#main", "#center", "#right", "#tape", "#liveobservation", "#flowtop")
        geometry_delta = {
            selector: {
                key: round(big_geometry[selector][key] - footprint_geometry[selector][key], 4)
                for key in ("x", "y", "width", "height")
            }
            for selector in protected
        }
        result = {
            "fixture": "synthetic committed Big Trades history; production feature remains disabled",
            "url": BASE_URL,
            "http_status": response.status if response else None,
            "viewport": {"width": 1280, "height": 900, "device_scale_factor": 1},
            "screenshots": {"before": str(FOOTPRINT_SCREENSHOT), "after": str(BIG_TRADES_SCREENSHOT)},
            "screenshot_sha256": {
                "before": hashlib.sha256(FOOTPRINT_SCREENSHOT.read_bytes()).hexdigest(),
                "after": hashlib.sha256(BIG_TRADES_SCREENSHOT.read_bytes()).hexdigest(),
            },
            "geometry": {"footprint_before": footprint_geometry, "heatmap": heatmap_geometry, "footprint_return": footprint_return_geometry, "big_trades": big_geometry},
            "protected_geometry_delta_big_minus_footprint": geometry_delta,
            "state": page.evaluate("""() => ({bodyClass:document.body.className,scrollWidth:document.documentElement.scrollWidth,clientWidth:document.documentElement.clientWidth,scrollHeight:document.documentElement.scrollHeight,serverStatus:document.querySelector('#btserverstatus').textContent,streamStatus:document.querySelector('#btstreamstatus').textContent,canvasStatus:document.querySelector('#btcanvasstatus').textContent,detailHeadings:[...document.querySelectorAll('#btdetailfacts h3')].map(x=>x.textContent),assessmentDisabled:document.querySelector('#btassessmentsave').disabled,observationChildren:[...document.querySelector('#btobservation').children].map(x=>({tag:x.tagName,text:x.textContent.trim().slice(0,100),display:getComputedStyle(x).display})),stats:window.BIG_TRADES_UI.stats()})"""),
            "console": console,
            "console_errors": [item for item in console if item["type"] == "error"],
            "page_errors": page_errors,
            "failed_requests": failed_requests,
            "local_responses": responses,
            "websocket_frame_counts": dict(sorted(websocket_frames.items())),
        }
        RESULT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        context.close()
        browser.close()


if __name__ == "__main__":
    main()
