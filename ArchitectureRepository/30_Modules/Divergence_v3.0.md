# Divergence Module

**Document ID**: MOD-012  
**Version**: v3.0  
**Status**: Accepted

---

# 1. Purpose

Detect regular divergence between confirmed Candle price pivots and bar-close CVD. MOD-012 is a deterministic, shadow-mode detector; it does not contribute to SignalEngine scoring.

# 2. Inputs and Outputs

Input is one confirmed `Candle` at a time (`bar_time`, `symbol`, `timeframe`, OHLC, `cvd`). Output is `DivergenceEvent`: direction, regular kind, symbol/timeframe, detection/pivot timestamps, pivot price/CVD values, deltas, and pivot bar distance. `detected_time` is the latest Candle that confirms the pivot; it is distinct from `pivot_time`.

# 3. Processing Rules

## 3.1 Pivot rule

Swing Low is `left.low > pivot.low` and `right.low >= pivot.low`. Swing High is `left.high < pivot.high` and `right.high <= pivot.high`. The equality policy is `first`: in a contiguous equal-price cluster the first Candle is representative; a fully flat left edge is not a pivot.

## 3.2 Regular divergence

Only the latest two pivots of the same kind are compared.

- BULLISH: latest low is lower and latest CVD is higher.
- BEARISH: latest high is higher and latest CVD is lower.

`price_change = pivot_price - previous_pivot_price`; `cvd_change = pivot_cvd - previous_pivot_cvd`; `bars_between` is the accepted-Candle index difference between pivots. `DivergenceKind` is always `REGULAR`; hidden divergence is reserved for a future version.

# 4. Configuration

| Key | Type | Default | Rule |
|---|---|---:|---|
| `divergence.equal_pivot_policy` | string | `first` | Only `first` is accepted. |
| `divergence.min_price_move` | Decimal string | `"0"` | Events with a smaller absolute price delta are rejected. |
| `divergence.min_bar_distance` | integer | 0 | Events with fewer bars between pivots are rejected. |

All calculations use `Decimal`; no float conversion is permitted.

# 5. Validation, State, and Diagnostics

The first accepted Candle establishes symbol/timeframe. Non-monotonic `bar_time` is rejected as E3004; symbol and timeframe mismatch are rejected as E3001. Every rejection is logged and counted, with no exception sent to the caller. Retained state is bounded: three Candles plus one low and one high pivot. Public counters are `candles_in`, `pivots_low`, `pivots_high`, `events_detected`, all three input-rejection counters, and both filter-rejection counters.

# 6. Roadmap and Separation

Detection and quality evaluation are separate responsibilities. Phase 0 supplies only the detector. FeatureSnapshot capture, persistence (`divergence_events` / `divergence_outcomes`), outcome evaluation, and quality ranks are Phase 1 work. Until out-of-sample superiority is demonstrated, events remain shadow-mode display data and must not affect SignalEngine weights.

# 7. References

- CVD
- ErrorCodes
- `00_Master/Reports/Divergence_Design_Review_v1_Complete.md`
- `00_Master/ADR/ADR-009_Divergence_Module_v3.0.md`
