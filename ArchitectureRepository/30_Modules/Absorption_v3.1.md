# Absorption Module

**Document ID**: MOD-007
**Version**: v3.1
**Status**: Draft

---

# 1. Purpose

Detect Absorption by identifying situations where aggressive market orders are absorbed by resting liquidity without significant price movement, using quantitative stall, volume, and replenishment criteria.

---

# 2. Responsibilities

- Monitor executed volume
- Monitor price movement
- Detect absorption events
- Classify Buy/Sell Absorption
- Compute absorption strength
- Publish absorption signals

---

# 3. Inputs

- Trade events
- Order Book updates
- Footprint data

---

# 4. Outputs

- Buy Absorption (sell-side aggression absorbed at support)
- Sell Absorption (buy-side aggression absorbed at resistance)
- Absorption strength (0.0 – 1.0)
- Absorption statistics
- Event notifications

---

# 5. Processing Rules

## 5.1 Detection Window

Evaluation is performed over a sliding window of `absorption.window` (time-based).

## 5.2 Quantitative Criteria

An Absorption event is generated when ALL three conditions hold within the window:

```text
1. Stall condition   : price range ≤ absorption.price_stall_ticks
2. Aggression cond.  : directional aggressive volume ≥ volume_ref × absorption.volume_multiplier
3. Replenish cond.   : opposing resting liquidity does not decrease,
                       or is replenished to ≥ its level at window start
```

- "Directional aggressive volume" is the executed volume of the aggressor side under evaluation (per EnumDefinitions BUY/SELL).
- Condition 3 is verified from Order Book updates at the stalled price level(s).

## 5.3 Classification

| Case | Classification |
|------|----------------|
| Aggressive SELL volume absorbed, price does not fall | Buy Absorption |
| Aggressive BUY volume absorbed, price does not rise | Sell Absorption |

## 5.4 Absorption Strength

```text
strength = min( aggressive_volume / (volume_ref × absorption.volume_multiplier), 1.0 )
```

Strength is a continuous value in [0.0, 1.0]. It connects to `signal.absorption_veto_threshold` (default 0.5) in SignalEngine_v3.1.

---

# 6. Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `absorption.window` | duration | 10 s | Sliding evaluation window |
| `absorption.price_stall_ticks` | int ≥ 1 | 1 | Maximum price range regarded as "no advance" |
| `absorption.volume_multiplier` | float > 1 | 2.0 | Multiple of `volume_ref` regarded as abnormal aggression |
| `absorption.volume_ref_bars` | int ≥ 1 | 20 | Bars used for the `volume_ref` moving average |

`volume_ref` is the moving average of per-level volume over the most recent `volume_ref_bars` bars, shared with the Imbalance module. All defaults are initial values subject to calibration during implementation.

---

# 7. Error Handling

- Missing order book data
- Invalid trade sequence
- Inconsistent price levels

---

# 8. Performance Targets

- Real-time detection
- Deterministic replay
- Configurable thresholds
- Stable long-running operation

---

# 9. References

- Footprint_v3.0.md
- SignalEngine_v3.1.md
- DataDictionary_v3.1.md
- EnumDefinitions_v3.0.md
- ConfigurationReference_v3.0.md
- ErrorCodes_v3.0.md
