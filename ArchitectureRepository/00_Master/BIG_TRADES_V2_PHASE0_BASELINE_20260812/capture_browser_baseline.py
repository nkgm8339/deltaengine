from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright


BASE_URL = "http://127.0.0.1:18080"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
OUTPUT_DIR = Path(__file__).resolve().parent
SCREENSHOT = OUTPUT_DIR / "existing_app_1280x900_full.png"

SELECTORS = (
    "body",
    "#topbar",
    "#flowtop",
    "#main",
    "#left",
    "#center",
    "#right",
    "#fpstage",
    "#fpcanvas",
    "#heatmapcanvas",
    "#flowpanel",
    "#flowbody",
    "#tape",
    "#tapeviewport",
    "#bottom",
    "#chartwrap",
    "#chart",
    "#liveobservation",
)


def classify_frame(payload: str | bytes) -> str:
    if not isinstance(payload, str):
        return "<binary>"
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return "<non-json>"
    if isinstance(parsed, dict):
        for key in ("type", "kind", "event", "message_type"):
            value = parsed.get(key)
            if isinstance(value, str):
                return value
    return "<json-unclassified>"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    console: list[dict[str, str]] = []
    page_errors: list[str] = []
    failed_requests: list[dict[str, str]] = []
    local_responses: list[dict[str, Any]] = []
    websocket_urls: list[str] = []
    websocket_frames: Counter[str] = Counter()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            executable_path=CHROME,
            args=("--disable-background-networking",),
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            device_scale_factor=1,
        )
        page = context.new_page()

        page.on(
            "console",
            lambda message: console.append(
                {"type": message.type, "text": message.text}
            ),
        )
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.on(
            "requestfailed",
            lambda request: failed_requests.append(
                {
                    "url": request.url,
                    "failure": request.failure or "unknown",
                }
            ),
        )
        page.on(
            "response",
            lambda response: local_responses.append(
                {
                    "url": response.url,
                    "status": response.status,
                    "resource_type": response.request.resource_type,
                }
            )
            if response.url.startswith(BASE_URL)
            else None,
        )

        def on_websocket(websocket: Any) -> None:
            websocket_urls.append(websocket.url)
            websocket.on(
                "framereceived",
                lambda payload: websocket_frames.update((classify_frame(payload),)),
            )

        page.on("websocket", on_websocket)
        response = page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(15_000)

        geometry = page.evaluate(
            """
            selectors => Object.fromEntries(selectors.map(selector => {
              const element = document.querySelector(selector);
              if (!element) return [selector, null];
              const rect = element.getBoundingClientRect();
              const style = getComputedStyle(element);
              return [selector, {
                x: rect.x,
                y: rect.y,
                width: rect.width,
                height: rect.height,
                display: style.display,
                visibility: style.visibility,
                hidden: element.hidden === true
              }];
            }))
            """,
            list(SELECTORS),
        )
        state = page.evaluate(
            """
            () => ({
              title: document.title,
              bodyClass: document.body.className,
              footprintMode: document.querySelector('#fpmodetoggle')?.textContent?.trim() ?? null,
              chartTitle: document.querySelector('#charttitle')?.textContent?.trim() ?? null,
              chartBars: document.querySelector('#chartbars')?.textContent?.trim() ?? null,
              tapeState: document.querySelector('#tapestate')?.textContent?.trim() ?? null,
              tapeCount: document.querySelector('#tapecount')?.textContent?.trim() ?? null,
              flowResponse: document.querySelector('#flowresponse')?.textContent?.trim() ?? null,
              healthDot: document.querySelector('#healthdot')?.textContent?.trim() ?? null,
              scrollWidth: document.documentElement.scrollWidth,
              clientWidth: document.documentElement.clientWidth,
              scrollHeight: document.documentElement.scrollHeight,
              clientHeight: document.documentElement.clientHeight
            })
            """
        )
        page.screenshot(path=str(SCREENSHOT), full_page=True)

        output = {
            "url": BASE_URL,
            "http_status": response.status if response else None,
            "viewport": {"width": 1280, "height": 900, "device_scale_factor": 1},
            "screenshot": str(SCREENSHOT),
            "state": state,
            "geometry": geometry,
            "console": console,
            "page_errors": page_errors,
            "failed_requests": failed_requests,
            "local_responses": local_responses,
            "websocket_urls": websocket_urls,
            "websocket_frame_counts": dict(sorted(websocket_frames.items())),
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))

        context.close()
        browser.close()


if __name__ == "__main__":
    main()
