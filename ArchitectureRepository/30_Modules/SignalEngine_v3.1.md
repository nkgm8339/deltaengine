# Signal Engine Module

**Document ID**: MOD-008
**Version**: v3.1
**Status**: Draft (rev. 2026-07-18 — §4.1a cvd_unref appended, Phase1_v2.2 Task B)

---

# 1. Purpose

Generate actionable trading signals by integrating outputs from the Order Flow analysis modules using a weighted scoring model with absorption gating.

---

# 2. Responsibilities

- Collect analytical inputs
- Normalize module outputs into directional scores
- Compute weighted composite score and confidence
- Apply absorption gating (veto)
- Generate BUY, SELL or WAIT signals
- Publish signal events with reasons

---

# 3. Inputs

| Source | Payload |
|--------|---------|
| CVD | Tick CVD, Bar CVD, CVD update events |
| Footprint | Price level BUY/SELL volume, Footprint structure |
| Imbalance | Imbalance events (direction, ratio, stacked count) |
| Absorption | Absorption events (direction, strength) |
| Configuration | Weights, thresholds, evaluation window |

---

# 4. Scoring Model

## 4.1 Module Score Normalization

Each scoring module produces a directional score in the range **[−100, +100]**.
Positive = buy pressure, negative = sell pressure, 0 = neutral.

| Module | Score definition |
|--------|------------------|
| CVD | `score_cvd = clamp( (CVD_slope / cvd_slope_ref) × 100, −100, +100 )` where `CVD_slope` is the CVD change over the evaluation window and `cvd_slope_ref` is the configured reference slope for full score |
| Footprint | `score_fp = clamp( ((BuyVol − SellVol) / (BuyVol + SellVol)) × 100, −100, +100 )` aggregated over the evaluation window |
| Imbalance | `score_imb = clamp( direction × min(stacked_count / stack_ref, 1) × 100, −100, +100 )`. Ratio threshold and stack definitions defer to `Imbalance_v3.x` (pending quantitative criteria) |

Absorption does not produce an additive score. It produces a gating event (Section 4.3).

### 4.1a CVD Unreferenced State (`cvd_unref`) — appended 2026-07-18

When `signal.cvd_slope_ref` is **null or 0**, `score_cvd` returns **None**
(unreferenced state). This is a designed state, not an error:

- The CVD module is treated as **disabled** for that evaluation (M10 decision 7):
  it is excluded from both the numerator and denominator of the composite.
- The UI renders the CVD score as `—` while unreferenced.
- No `NO_INPUT` reason is emitted for cvd_unref alone; other enabled modules
  continue to drive the signal.

Exit from the unreferenced state is performed by calibration:
`python tools/calibrate_cvd.py --write` computes the P80 of |Candle.delta| over
the recent window and writes `signal.cvd_slope_ref` into config
(2026-07-18 initial calibration: **65.203**, 7-day window, 397 samples;
re-calibration is recommended as data accumulates).

## 4.2 Composite Score and Confidence

```text
composite = ( w_cvd × score_cvd
            + w_fp  × score_fp
            + w_imb × score_imb )
            / ( w_cvd + w_fp + w_imb )

confidence = |composite| / 100        # range 0.0 – 1.0
direction  = sign(composite)          # +1 = BUY side, −1 = SELL side
```

- Weights are non-negative Configuration parameters.
- A module disabled by feature flag is excluded from both numerator and denominator.
- If all scoring modules are disabled or missing, the engine emits WAIT with `NO_INPUT` reason.

## 4.3 Absorption Gating (Veto)

When the Absorption module reports absorption **against** the composite direction
(sell absorption while `direction = +1`, or buy absorption while `direction = −1`)
with strength ≥ `absorption_veto_threshold`:

- The signal is forced to **WAIT**.
- Reason code `ABSORPTION_VETO` is appended.

Quantitative absorption strength defers to `Absorption_v3.x` (pending quantitative criteria).

## 4.4 Signal Decision Table

| Condition | Signal |
|-----------|--------|
| confidence ≥ `confidence_threshold` AND direction = +1 AND no veto | BUY |
| confidence ≥ `confidence_threshold` AND direction = −1 AND no veto | SELL |
| confidence < `confidence_threshold` | WAIT |
| Absorption veto active | WAIT |
| Required input missing | WAIT |

---

# 5. Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `signal.weight.cvd` (`w_cvd`) | float ≥ 0 | 1.0 | CVD weight |
| `signal.weight.footprint` (`w_fp`) | float ≥ 0 | 1.0 | Footprint weight |
| `signal.weight.imbalance` (`w_imb`) | float ≥ 0 | 1.0 | Imbalance weight |
| `signal.confidence_threshold` | float 0–1 | 0.6 | Minimum confidence to emit BUY/SELL |
| `signal.evaluation_window` | duration | 1 bar | Window for slope/aggregation |
| `signal.cvd_slope_ref` | float > 0 | TBD (calibration) | CVD slope mapped to score 100 |
| `signal.stack_ref` | int ≥ 1 | 3 | Stacked imbalance count mapped to score 100 |
| `signal.absorption_veto_threshold` | float 0–1 | 0.5 | Minimum absorption strength to trigger veto |

All parameters follow `ConfigurationReference_v3.0.md` concepts (Static Configuration, Default Value, Feature Flag).

---

# 6. Outputs

Signal Event per `JSONSchema_v3.0.md` Section 3:

- `signal_time`, `symbol`
- `signal`: BUY | SELL | WAIT
- `confidence`: float 0.0–1.0
- `reason[]`: contributing codes

Reason codes (extends existing set):

| Code | Meaning |
|------|---------|
| `CVD_UP` / `CVD_DOWN` | \|score_cvd\| ≥ 50 |
| `FOOTPRINT_BUY` / `FOOTPRINT_SELL` | \|score_fp\| ≥ 50 |
| `STACKED_IMBALANCE` | \|score_imb\| ≥ 50 |
| `ABSORPTION_VETO` | Gating applied |
| `LOW_CONFIDENCE` | confidence < threshold |
| `NO_INPUT` | Required input missing |

---

# 7. Processing Rules

- Combine all enabled analytical modules per Section 4.
- Produce deterministic results from identical inputs and identical configuration.
- Evaluate on each Order Flow Engine update within the evaluation window.
- Emit WAIT when confidence is below threshold or veto is active.

---

# 8. Error Handling

| Case | Handling |
|------|----------|
| Missing analytical input | Emit WAIT with `NO_INPUT`; log per ErrorCodes |
| Invalid configuration (negative weight, threshold out of range) | Fail startup validation |
| Scoring failure (NaN, division by zero when all volumes are 0) | Treat module score as 0; log warning |
| `signal.cvd_slope_ref` null or 0 (cvd_unref) | `score_cvd = None`; CVD excluded from composite (§4.1a); not an error, no warning per bar |

---

# 9. Performance Targets

- Real-time evaluation within tick processing budget (NFR: ≤ 50 ms end-to-end)
- Deterministic replay
- Configurable rule set without code change

---

# 10. Pending Dependencies

| Item | Blocking document |
|------|-------------------|
| Imbalance ratio threshold and stack definition | Imbalance_v3.x (priority 5) |
| Absorption strength quantification | Absorption_v3.x (priority 5) |
| `cvd_slope_ref` default value | **Resolved 2026-07-18**: calibrated 65.203 via `tools/calibrate_cvd.py` (§4.1a) |

---

# 11. References

- CVD_v3.0.md
- Footprint_v3.0.md
- Imbalance_v3.0.md
- Absorption_v3.0.md
- DataDictionary_v3.1.md
- ConfigurationReference_v3.0.md
- JSONSchema_v3.0.md
- ErrorCodes_v3.0.md
- ADR-002_Module_Communication_v3.0.md
- ADR-003_Concurrency_Model_v3.0.md
