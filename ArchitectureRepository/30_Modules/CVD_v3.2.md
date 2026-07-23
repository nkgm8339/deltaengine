# CVD Module

**Document ID**: MOD-004
**Version**: v3.2
**Status**: Draft

---

# 1. Purpose

Calculate Cumulative Volume Delta (CVD) from normalized trade events.

---

# 2. Responsibilities

- Receive normalized trade events
- Classify BUY/SELL aggressor volume
- Calculate per-trade Delta
- Maintain cumulative Delta
- Generate bar-level CVD values

---

# 3. Inputs

- trade_id
- event_time
- price
- quantity
- side

---

# 4. Outputs

## 4.1 Tick CVD

Emitted after each normalized trade event (JSONSchema CVD Update Event):

- `tick_delta`: Delta of the current trade (positive for BUY, negative for SELL)
- `tick_cvd`: Running cumulative CVD since system start

Tick CVD is passed to downstream modules (Signal Engine) via asyncio.Queue per ADR-002.

## 4.2 Bar CVD (Candle)

Emitted at bar close (JSONSchema Candle Event):

- `bar_time`: UTC-aligned bar start time
- OHLC: open/high/low/close prices within the bar
- `volume`: total executed quantity within the bar
- `delta`: sum of all trade deltas within the bar (resets each bar)
- `cvd`: running cumulative CVD as of bar close (never resets)

Bar CVD is passed to Storage for persistence via asyncio.Queue per ADR-002.

---

# 5. Processing Rules

Delta = BUY Volume − SELL Volume

CVD(n) = CVD(n-1) + Delta(n)

All calculations use normalized trade events only.

Bar CVD is aggregated per the configured bar timeframe:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `market.bar_timeframe` | string | 1m | Candle aggregation interval for Bar CVD |

Bar boundaries are aligned to UTC clock time (e.g., 1m bars start at hh:mm:00).

## Bar Boundary Rules

- Bar boundaries are aligned to UTC clock time (e.g., 1m bars start at hh:mm:00).
- `delta` (bar delta) is the sum of all trade deltas within the bar. It resets to 0 at each bar boundary.
- `cvd` is the cumulative sum of all deltas since system start. It never resets within a session.
- At bar close, the module emits one Candle Event and begins a new bar.
- The first trade after system start opens the first bar.

## Replay Support

In replay mode (YAMLReference §5), the CVD module processes events identically to live mode. Deterministic replay requires identical input sequence and identical configuration.

---

# 6. Error Handling

- Missing trade event
- Invalid side
- Duplicate trade_id
- Out-of-order timestamp

---

# 7. Performance Targets

- Real-time calculation
- Zero cumulative drift
- Deterministic replay from historical data

---

# 8. References

- DataDictionary
- EnumDefinitions
- JSONSchema
- SystemArchitecture
- ErrorCodes
