# DeltaEngine UI Refresh v2.0 — Approved Design

**Document ID**: REF-UI-REFRESH-002  
**Status**: Approved design / implementation not started  
**Decision date**: 2026-07-25  
**Target runtime**: `Delta_Engine_Pro4web/webapp/static/index.html`  
**Current runtime specification**: `UI_Spec_CommandCenter_v2.md`

---

## 0. Authority and target images

This document records the UI design approved by the user on 2026-07-25.
It does not authorize analytics, payload, backend, or calculation changes.

Priority when implementing:

1. The user's latest explicit instruction
2. The full target image below
3. The approved exceptions and semantic corrections in this document
4. Existing completed UI behavior

### 0.1 Full target image

- Conversation attachment: corrected full-screen target image
- Local source at approval time:
  `C:\Users\user\Pictures\f517853a-45b1-4fef-b39a-b284c8ccfb77.png`
- Dimensions: `1536 × 1024`
- SHA-256:
  `B5A67C8FB1A42F2A0FDD19C418629E64A545F33C8BCE81460E2D4C4CFE22AB8B`

### 0.2 Selected-candle detail reference

- Conversation attachment: existing selected-candle fixed detail
- Local source at approval time:
  `C:\Users\user\Pictures\2026-07-25 02 39 50.png`
- Dimensions: `295 × 447`
- SHA-256:
  `3ECDF97445CD587FB0D90FA10B9EDF7E024DF3CF14813A47650A5314625050ED`

The selected-candle detail is retained. It is not replaced by the new
right-side `LIVE OBSERVATION` panel.

---

## 1. Approved outcome

Refresh the existing screen into a dense, dark professional trading UI while
preserving every completed observation and interaction.

The screen has two different right-side responsibilities:

- The fixed detail inside the three-stage chart shows the candle selected by
  the user, including historical candles.
- The outer `LIVE OBSERVATION` column shows the latest live observation.

They must coexist. One must not replace or control the other.

The target image's signal-like right column is semantically corrected to a
fact-only observation column. No trade signal or confidence is invented.

---

## 2. Non-negotiable invariants

The following are protected and must not change:

- Flow Price Response calculations and seven states
- 30s, 1m, 3m, 5m, 15m, and 30m observation windows
- Meaning of pressure, persistence, price change, and relative volume
- Three-stage chart:
  - PRICE + Flow Response background bands
  - CVD line + Delta bars
  - Volume bars
- Shared time axis and chart scales
- Selected-candle eight-pattern classification
- Selected-candle OI synchronization and context
- Recent Flow Event candle markers and two-hour browser-memory behavior
- Footprint, Order Book, Absorption, Imbalance, Flow Event, and Alert data
- Left click, arrow-key movement, right-click clear, wheel zoom, drag pan, and
  LIVE return
- WebSocket reconnect, health display, Developer Overlay, and existing settings
- Existing API, WebSocket, Store, analyzer, service, model, database, backend,
  and calculation behavior

Missing values must never be guessed, forward-filled, or replaced with dummy
data.

---

## 3. Explicitly approved differences from the target image

### 3.1 Top Bar omissions

Do not add:

- 24H HIGH
- 24H LOW
- 24H CHANGE or price-change percentage
- 24H VOLUME
- FUNDING

These are not available through the current browser input and will not be
introduced by changing communication or backend code.

### 3.2 Right column replacement

Do not add:

- BUY / SELL trade signal
- Confidence
- Flow Quality composite
- Momentum assessment
- Signal `WHY?`
- High / Medium / Low adjectives based on new thresholds

Use the approved `LIVE OBSERVATION` structure defined in section 7.

### 3.3 Terminology

The outer right column describes the latest observation. It must never imply:

- entry or exit instruction
- probability
- expected return
- composite score
- confirmation of a trade

---

## 4. Desktop layout

### 4.1 Primary viewport

The primary visual-comparison viewport is `1536 × 1024`.

```text
┌───────────────────────────────────────────────────────────────────────────┐
│ TOP BAR                                                                  │
├──────────────────────────────────────────────────────────────┬────────────┤
│ PRICE & FLOW RESPONSE                                        │ LIVE       │
│ fixed observation rows                                       │ OBSERVATION│
│ ┌──────────────────────────────────────┬───────────────────┐ │            │
│ │ PRICE / CVD+DELTA / VOLUME           │ SELECTED CANDLE   │ │            │
│ │ three-stage chart                    │ FIXED DETAIL      │ │            │
│ └──────────────────────────────────────┴───────────────────┘ │            │
├───────────────────────┬────────────────────┬─────────────────┤            │
│ FLOW EVENTS           │ FOOTPRINT          │ ORDER BOOK      │            │
│ ABS / IMB / ALERTS    │                    │                 │            │
└───────────────────────┴────────────────────┴─────────────────┴────────────┘
```

### 4.2 Reference geometry at 1536 × 1024

| Region | Approved geometry |
|---|---:|
| Outer padding | 10px |
| Major gap | 12px |
| Top Bar height | 62px |
| Outer right column | 322px |
| Left top chart panel | 552px high |
| Left bottom detail area | 344px high |
| Selected-candle fixed detail | 250px wide |
| Chart status region | 94px high |
| Chart status rows | 26px / 38px / 26px |

The main workspace uses:

```css
grid-template-columns: minmax(0, 1fr) 322px;
gap: 12px;
```

The left workspace uses:

```css
grid-template-rows: 552px minmax(344px, 1fr);
gap: 12px;
```

The lower observation area uses the target-image proportions:

```text
FLOW cluster   42%
FOOTPRINT      35%
ORDER BOOK     remaining width
```

At the primary viewport this is approximately:

```text
496px / 407px / 257px
```

### 4.3 Narrow desktop behavior

- The professional desktop layout remains stable down to 1280px.
- The right live column remains at least 306px wide.
- The selected-candle fixed detail remains at least 230px wide.
- Below 1280px, preserve the desktop geometry with horizontal overflow instead
  of moving panels to unrelated positions.
- Mobile redesign is outside this task.

---

## 5. Visual system

### 5.1 Color tokens

| Role | Color |
|---|---|
| Page background | `#050914` |
| Panel background | `#08101F` |
| Raised card | `#0C1628` |
| Panel border | `#273654` |
| Strong text | `#F1F5FF` |
| Normal text | `#C9D3EA` |
| Muted text | `#7F8EAD` |
| BUY / positive pressure | `#19C979` |
| SELL / negative pressure | `#FF4058` |
| STALLED / warning | `#F4C542` |
| Neutral information | `#25B7E8` |
| DIVERGENCE / OI information | `#8B63E6` |
| Unknown / missing | `#6E7B96` |

Flow Response background-band colors and meanings remain those of the current
implementation. The token refresh must not change their semantic mapping.

### 5.2 Typography

No font or icon dependency is added.

- UI text: existing system sans-serif stack
- Numeric values: existing monospace stack
- Dominant observation: 32px
- Section value: 20px
- Normal value: 15px
- Supporting label and dense table text: 11–12px
- Use tabular numbers for changing market values

### 5.3 Cards

- Outer radius: 7–8px
- Inner card radius: 5–6px
- Border: 1px
- Shadow: subtle dark shadow only
- Hover: border/color emphasis only
- Do not use large blur filters over the live chart

### 5.4 Motion

Allowed:

- opacity
- transform
- progress-bar `scaleX`

Duration: 120–160ms.

Do not animate width, height, grid tracks, chart geometry, or panel presence.

---

## 6. Top Bar

Approved left-to-right order:

1. Symbol and market/source label
2. Current price
3. Binance Open Interest with existing 1m and 5m changes
4. Existing PRICE/CVD/Delta/OI guide button
5. ATR(14)
6. HFM spread
7. Market time
8. Latency
9. FPS
10. LIVE / reconnect state
11. Health, Developer Overlay, and version/settings controls

Rules:

- Do not show a price-adjacent pseudo-change percentage.
- OI remains purple information, not BUY/SELL coloring.
- Existing OI staleness behavior remains unchanged.
- Market time is formatted from the existing market message time.
- Missing existing values show `—` without changing Top Bar height.
- No decorative control is added unless it has an existing function.

---

## 7. Outer right column — LIVE OBSERVATION

### 7.1 Purpose

Show the latest live observational facts in a fixed, quickly scannable order.
The panel follows the currently selected Flow Response observation window.

Changing the Flow window updates this panel and the chart background together.
It does not change the one-minute candle timeframe.

### 7.2 Fixed card order

1. Active Flow Response
2. Flow Measures
3. Live Metrics
4. Context
5. Observed Facts

The outer column itself remains present. Existing fields that are temporarily
missing show `—`. Fields that do not exist in the current payload are not
created.

### 7.3 Active Flow Response

Display:

- market time
- selected Flow window
- existing full state
- pressure side
- price-response direction

Approved state presentation:

| Existing state | Dominant display | Color |
|---|---|---|
| `BUY_EFFECTIVE` | `BUY PRESSURE` / `PRICE UP` | green |
| `SELL_EFFECTIVE` | `SELL PRESSURE` / `PRICE DOWN` | red |
| `BUY_STALLED` | `BUY PRESSURE` / `STALLED` | yellow |
| `SELL_STALLED` | `SELL PRESSURE` / `STALLED` | yellow |
| `BUY_TRAPPED` | `BUY PRESSURE` / `PRICE DOWN` | purple |
| `SELL_TRAPPED` | `SELL PRESSURE` / `PRICE UP` | purple |
| `UNCLEAR` | `UNCLEAR` | gray |

Do not shorten the dominant display to a standalone `BUY` or `SELL`.
Do not show confidence.

### 7.4 Flow Measures

Display:

- Pressure
- Persistence
- Relative Volume

Pressure and Persistence use progress bars.

- Pressure fill uses the magnitude of the existing `pressure_ratio`.
- The displayed pressure side comes from the existing `pressure_side`.
- Persistence uses the existing `persistence` value.
- Both retain their numeric percentage next to the bar.
- Relative Volume remains the existing unbounded `×N.N` ratio and does not use
  a percentage bar.

Do not add `Flow Quality`.

### 7.5 Live Metrics

Fixed order:

1. Price + active Flow-window price change in bps
2. CVD
3. Delta
4. Volume
5. OI Δ1M

Rules:

- Price, CVD, and Delta arrows use the existing direction presentation.
- Volume is displayed without an invented up/down judgment.
- OI direction may use an arrow but remains purple.
- Values are taken from the latest available live/current bar data.
- No metric is combined into a score.

### 7.6 Context

Fixed order:

1. Pattern — existing PRICE/CVD/Delta eight-pattern name
2. Flow — existing full Flow Response state
3. OI — `BUILDING`, `UNWINDING`, `UNCHANGED`, or `—`
4. Absorption — existing classification or `—`

Do not add Momentum.
Do not convert OI direction into LONG or SHORT.

### 7.7 Observed Facts

Title: `OBSERVED FACTS`

Show at most five direct facts using fixed templates:

- `PRESSURE SIDE · <BUY|SELL|—>`
- `PRICE RESPONSE · <signed bps|—>`
- `PERSISTENCE · <percent|—>`
- `RELATIVE VOLUME · <×N.N|—>`
- `OI CHANGE · <signed percent|—>`

Rules:

- No `WHY?` title
- No checkmark implying confirmation
- No `High`, `Weak`, `Strong`, or similar new thresholds
- No prose generated from combinations
- No advice, entry, exit, or probability language

---

## 8. Three-stage chart

### 8.1 Reuse, do not rebuild

The existing SVG renderer and all chart calculations remain intact.
The UI refresh changes only its containing layout and visual tokens.

### 8.2 Fixed observation rows

Keep the existing 94px region:

1. CVD DIVERGENCE — 26px
2. Six Flow Response cards — 38px
3. Native 05M Context — 26px

The six cards remain in this order:

`30s / 1m / 3m / 5m / 15m / 30m`

Each card retains:

- state name
- `PR`
- `P`
- `V`

Missing data changes values to `—`; it does not remove a card.

### 8.3 Chart and selected-candle columns

Inside the chart body:

```css
grid-template-columns: minmax(0, 1fr) 250px;
gap: 8px;
```

The left side contains the unchanged three-stage chart.
The right side contains the selected-candle fixed detail.

### 8.4 Selected-candle fixed detail

Retain:

- selected time
- eight-pattern number and name
- `PRICE / CVD / Δ` directions
- plain-language existing pattern description
- OHLC
- CVD
- Delta
- Volume
- Open Interest OPEN, CLOSE, CHANGE, CHANGE %, and SAMPLES
- native 05M context code/title/directions
- selected Flow Response
- selected-candle Flow Events from two-hour browser memory

Retain scrolling when the content is taller than its fixed area.

Retain the empty-state operation guide when no candle is selected.

The detail follows the selected candle only. It must not switch to the latest
live values unless the selected candle itself is the latest candle.

---

## 9. Lower observation area

### 9.1 Left cluster

Top:

- FLOW EVENTS

Bottom, fixed left-to-right order:

- ABSORPTION
- IMBALANCE
- ALERTS

The Alerts card remains in its assigned position. With no alerts, show an empty
state or `—`; do not add/remove the card during live operation.

### 9.2 Footprint

Retain:

- bar title and forming/closed state
- VA percentage control
- previous/next bar controls
- zoom and price lock
- aggregate BID, ASK, and DELTA
- PRICE, BID, ASK, DELTA, and SIG columns
- POC, VAH, VAL, and current-price presentation

### 9.3 Order Book

Retain:

- asks
- MID
- bids
- quantity
- cumulative depth
- existing background depth visualization

### 9.4 Flow Events, Absorption, Imbalance, and Alerts

Retain all current data, settings, thresholds, marker toggles, alert behavior,
and event retention. This task only relocates and restyles their panels.

---

## 10. Data ownership and missing-data rules

### 10.1 Existing browser inputs only

| Display | Existing source |
|---|---|
| Symbol / Price | HELLO / TICK |
| Current candle and chart | CANDLE / BAR_UPDATE / history |
| CVD / Delta / Volume | candle and current-bar payload |
| Flow Response | FLOW_RESPONSE |
| OI | OI and existing history |
| 05M Context | COMBINED_CONTEXT |
| Footprint / Order Book | CANDLE / BAR_UPDATE |
| Absorption / Imbalance | ANALYSIS |
| Flow Events | FLOW / ANALYSIS |
| Health / Stats | HEALTH / STATS |

### 10.2 Structurally unavailable values

The following must not be rendered or reconstructed:

- trade Signal
- Confidence
- Flow Quality
- Momentum
- signal reasons
- 24-hour market statistics
- Funding

The compatibility `SignalEngine` result is not a valid substitute because it
returns `WAIT / 0` and is not part of the current browser observation contract.

### 10.3 Temporary absence versus structural absence

- Existing field temporarily missing: preserve its fixed label and show `—`.
- Field not in the current data contract: do not create that field in the UI.

---

## 11. Implementation boundary

Expected runtime edit:

- `Delta_Engine_Pro4web/webapp/static/index.html`

Protected from modification:

- `webapp/main.py`
- `webapp/push_broker.py`
- all `src/` analytics and order-flow modules
- configuration
- API and WebSocket contracts
- database and history code
- models, types, interfaces, hooks, and services

Implementation approach:

1. Preserve existing element IDs required by renderers and controls.
2. Replace runtime DOM reparenting with declarative HTML grid placement.
3. Consolidate the overlapping visual CSS layers into one token-based layout.
4. Add a fixed `LIVE OBSERVATION` DOM structure.
5. Update only its text, class, color, and progress transforms from existing
   browser state.
6. Do not add a timer, fetch, WebSocket message type, dependency, or analytics
   state for the new panel.
7. Keep the existing chart-rendering functions and observation calculations
   unchanged.

---

## 12. Performance requirements

- No new dependency
- No new network request
- No new periodic timer
- No chart re-render triggered solely by right-panel decoration
- Right panel updates only when its existing source data changes
- Fixed DOM nodes; prefer `textContent`, class changes, and CSS custom properties
- Progress bars animate with `transform: scaleX()`
- No panel-height animation
- Existing FPS display and chart interaction responsiveness must not regress

---

## 13. Acceptance and visual review

### 13.1 Functional acceptance

- Console Error: 0
- JavaScript syntax: valid
- Existing full regression suite: pass
- Existing chart interactions: all pass
- Existing settings and overlays: all pass
- No API, WebSocket, calculation, storage, or backend diff
- No fabricated or dummy market value

### 13.2 Geometry acceptance at 1536 × 1024

| Check | Tolerance |
|---|---:|
| Top Bar height 62px | ±1px |
| Right column width 322px | ±2px |
| Major gap 12px | ±2px |
| Left chart panel height 552px | ±3px |
| Chart status region 94px | 0px |
| Selected detail width 250px | ±2px |
| Lower panel order | exact |

The chart position and height must remain unchanged across:

- initial loading
- first live data
- missing values
- reconnect
- Flow state changes
- Absorption/Imbalance event appearance and disappearance
- candle selection and clearing

### 13.3 Visual score

Compare the implementation screenshot with the approved target at
`1536 × 1024`.

Dynamic prices, timestamps, chart paths, table rows, and market values are
excluded from pixel-content comparison. Their containers, alignment, colors,
and typography remain in scope.

| Category | Weight |
|---|---:|
| Overall layout | 30 |
| Spacing and alignment | 15 |
| Color system | 15 |
| Cards, borders, and radius | 10 |
| Typography and numeric hierarchy | 10 |
| Information order | 10 |
| Icons and state marks | 5 |
| Stable live behavior | 5 |

Completion requires at least `95 / 100`.

### 13.4 Required completion report

Provide:

- final 1536 × 1024 screenshot
- geometry measurements
- visual score by category
- differences from the target image
- confirmation of protected files
- syntax, console, test, and interaction results

If the score is below 95, implementation is not complete.

---

## 14. Implementation checkpoint requirement

Before the first runtime change, create or update a UI Refresh checkpoint with:

- current time
- approved scope
- current target-image hashes
- protected-file hashes or equivalent diff baseline
- files already dirty before UI work
- completed and pending work
- verification results
- limited blocker scope
- exact resume position

Update it:

- before the first runtime change
- after layout completion
- after `LIVE OBSERVATION` completion
- before and after browser visual comparison
- after regression testing
- before any unfinished handoff

---

## 15. Final approved design statement

The target is a professional visual refresh of the existing observation
platform, not a return to an opaque signal dashboard.

The completed three-stage chart remains the center of the screen.
Order Book, Footprint, Flow Events, Absorption, Imbalance, and Alerts retain
their existing function and move into the target hierarchy.

The selected-candle fixed detail remains inside the chart.
The new outer right column shows the latest `LIVE OBSERVATION`.

No missing Signal, Confidence, Flow Quality, Momentum, Funding, or 24-hour
market statistic is invented.
