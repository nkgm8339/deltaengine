# Imbalance Module

**Document ID**: MOD-006
**Version**: v3.2
**Status**: Approved (implemented — Phase1_v2.2 Task A)

---

# 1. Purpose

Detect Buy and Sell Imbalances from Footprint data by comparing executed volume at adjacent price levels using diagonal comparison.

---

# 2. Responsibilities

- Calculate imbalance ratios
- Detect Buy Imbalance
- Detect Sell Imbalance
- Detect Stacked Imbalances
- Publish imbalance events
- Emit WebApp flow events with continuous strength and same-direction cooldown

---

# 3. Inputs

- Footprint price levels
- BUY volume
- SELL volume

---

# 4. Outputs

- Buy Imbalance (price level, ratio, direction)
- Sell Imbalance (price level, ratio, direction)
- Stacked Imbalance (start level, end level, count, direction)
- Imbalance statistics
- WebApp FlowEvent (category=IMBALANCE, side, strength 0–1) — see §5.4

---

# 5. Processing Rules

## 5.1 Diagonal Comparison

Imbalances are detected by comparing aggressor volume diagonally across adjacent price levels:

```text
Buy Imbalance  @P : BuyVol(P)  / SellVol(P−1tick) ≥ ratio_threshold
Sell Imbalance @P : SellVol(P) / BuyVol(P+1tick)  ≥ ratio_threshold
```

## 5.2 Qualification Conditions (v3.2 — saturation fix)

A level qualifies as an Imbalance only when the following gates pass **in order**:

1. **Volume gate**: `numerator + denominator` (combined volume of the two compared
   levels) ≥ `imbalance.min_volume`. This gate applies to zero-denominator pairs
   as well — a combined volume below the floor never qualifies.
2. **Zero denominator rule**: if the denominator volume is 0, the pair qualifies
   **only when the numerator itself carries real volume**
   (`numerator ≥ imbalance.min_volume`). The reported ratio is capped at
   `imbalance.ratio_cap`. Thin one-sided levels (e.g. 0.01 vs 0.00) do NOT
   qualify — under v3.1 they auto-qualified at ratio_cap on every pair,
   saturating strength/score at 1.00/±100 on thin 1m bars.
3. **Ratio condition**: otherwise, `numerator / denominator ≥ imbalance.ratio_threshold`.

## 5.3 Stacked Imbalance

`imbalance.stack_count` or more consecutive qualifying levels in the same direction form a Stacked Imbalance. Consecutive means adjacent price levels with no non-qualifying level in between.

## 5.4 WebApp Flow Event Emission (v3.2 — continuous strength + cooldown)

At bar close, stacked imbalances are aggregated per direction into `net`
(net stacked count for the dominant direction) and emitted as a WebApp
FlowEvent with:

```text
strength = min( net / (stack_ref × 2), 1 )        # continuous 0–1
```

where `stack_ref = signal.stack_ref` (default 3). A same-direction event is
suppressed for `cooldown_bars = 3` confirmed bars after the last emission,
**except** when the current `net` strictly exceeds the `net` at the previous
emission (escalating stack fires immediately). The cooldown state is held per
direction on the Pipeline side; the decision function is pure and
side-effect free.

---

# 6. Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `imbalance.ratio_threshold` | float > 1 | 3.0 | Diagonal ratio (300%) required to qualify |
| `imbalance.min_volume` | float ≥ 0 | 0.5 | Minimum combined volume of the compared levels. **null is deprecated**: a null value no longer resolves to 0 (which disabled the filter); it logs `E3002` and falls back to 0.5 |
| `imbalance.ratio_cap` | float | 10.0 | Reported ratio ceiling for zero-denominator cases |
| `imbalance.stack_count` | int ≥ 2 | 3 | Consecutive levels required for a Stacked Imbalance |

Consistency: `imbalance.stack_count = 3` aligns with `signal.stack_ref = 3` in SignalEngine_v3.1.

Calibration note: on thin symbols/timeframes, raise `min_volume`; if the
IMBALANCE score reaches ±100 too frequently, raise `signal.stack_ref` to 5–6
(±100 = stack_ref stacks in one bar, by design).

---

# 7. Error Handling

| Case | Handling |
|------|----------|
| Missing Footprint data | No imbalances (not an error) |
| Negative volume level | E3001 — skip all pairs involving that level, continue |
| Levels not price-ascending | E3001 — skip that pair, continue |
| `imbalance.min_volume: null` | E3002 — warn and fall back to default floor 0.5 |

---

# 8. Performance Targets

- Real-time detection
- Deterministic replay
- Configurable thresholds

---

# 9. References

- Footprint_v3.0.md
- SignalEngine_v3.1.md
- DataDictionary_v3.1.md
- EnumDefinitions_v3.0.md
- ConfigurationReference_v3.0.md
- ErrorCodes_v3.0.md

---

# 10. Revision History

| Version | Date | Change |
|---------|------|--------|
| v3.2 | 2026-07-18 | Task A saturation fix: ordered qualification gates (§5.2), min_volume null→E3002+0.5 fallback (§6), WebApp flow-event strength/cooldown (§5.4) |
| v3.1 | 2026-07-07 | Quantitative criteria added |
