# Test Specification

**Document ID**: TST-001
**Version**: v3.2
**Status**: Draft

---

# 1. Purpose

Define the verification strategy for the Order Flow Analysis Platform Architecture Repository, including deterministic test vectors for core modules.

---

# 2. Test Levels

- Unit Test
- Integration Test
- System Test
- Performance Test
- Regression Test
- Acceptance Test

---

# 3. Verification Targets

| Component | Verification |
|----------|--------------|
| Data Receiver | Data acquisition |
| WebSocket | Connection lifecycle |
| Data Normalizer | Normalization, deduplication, ordering |
| Database | Persistence |
| CVD | Calculation accuracy |
| Footprint | Volume aggregation |
| Imbalance | Ratio detection |
| Absorption | Event detection |
| Signal Engine | Signal generation |
| AI Analysis | Market interpretation |
| MT5 Adapter | Delivery and connection health |

---

# 4. Test Vectors

All vectors are deterministic: identical inputs and configuration shall always produce identical outputs (Deterministic Replay). Unless stated otherwise, configuration uses the default values defined in the v3.1 module specifications.

## 4.1 CVD (CVD)

### TV-CVD-01 Normal sequence

| # | trade_id | side | quantity | Expected Delta | Expected CVD |
|---|----------|------|----------|----------------|--------------|
| 1 | T1 | BUY | 5 | +5 | +5 |
| 2 | T2 | SELL | 3 | −3 | +2 |
| 3 | T3 | BUY | 2 | +2 | +4 |
| 4 | T4 | SELL | 6 | −6 | −2 |

### TV-CVD-02 Duplicate trade_id

Input: T1 (BUY 5), T1 (BUY 5) again.
Expected: second event discarded; CVD remains +5; duplicate counter = 1.

### TV-CVD-03 Invalid side

Input: T5 with side = "X".
Expected: event rejected per ErrorCodes; CVD unchanged; no partial update.

### TV-CVD-04 Out-of-order timestamp

Input: T6 with event_time earlier than last processed event.
Expected: handled per CVD error handling (reject and count); CVD unchanged.

## 4.2 Footprint (Footprint)

### TV-FP-01 Level aggregation

Input trades: (price 100, BUY 5), (price 100, SELL 3), (price 101, BUY 2).

| Price level | BUY volume | SELL volume |
|-------------|------------|-------------|
| 100 | 5 | 3 |
| 101 | 2 | 0 |

### TV-FP-02 Invalid trade

Input: trade with missing side.
Expected: rejected; Footprint totals unchanged.

## 4.3 Imbalance (Imbalance)

Fixture: tick size = 1, `ratio_threshold` = 3.0, `volume_ref` = 50 (min_volume), `ratio_cap` = 10.0, `stack_count` = 3.

### TV-IMB-01 Ratio boundary (qualify)

Input: SellVol(100) = 100, BuyVol(101) = 300. Combined volume 400 ≥ 50.
Expected: Buy Imbalance at 101, ratio 3.0.

### TV-IMB-02 Ratio boundary (not qualify)

Input: SellVol(100) = 100, BuyVol(101) = 299.
Expected: no imbalance (ratio 2.99 < 3.0).

### TV-IMB-03 Zero denominator (qualify)

Input: SellVol(100) = 0, BuyVol(101) = 60. Combined volume 60 ≥ 50.
Expected: Buy Imbalance at 101, reported ratio = 10.0 (capped).

### TV-IMB-04 Zero denominator (not qualify)

Input: SellVol(100) = 0, BuyVol(101) = 40. Combined volume 40 < 50.
Expected: no imbalance.

### TV-IMB-05 Stacked Imbalance (qualify)

Input: qualifying Buy Imbalances at 101, 102, 103 (consecutive).
Expected: Stacked Imbalance, direction BUY, count 3, range 101–103.

### TV-IMB-06 Stacked Imbalance (not qualify)

Input: qualifying Buy Imbalances at 101, 102 only.
Expected: individual imbalances published; no Stacked Imbalance.

## 4.4 Absorption (Absorption)

Fixture: `window` = 10 s, `price_stall_ticks` = 1, `volume_multiplier` = 2.0, `volume_ref` = 50 → aggression threshold = 100.

### TV-ABS-01 Buy Absorption (qualify)

Input within one window: aggressive SELL volume 120 at price 100; price range = 1 tick; bid liquidity at 100 replenished to ≥ window-start level.
Expected: Buy Absorption event, strength = min(120 / 100, 1.0) = 1.0.

### TV-ABS-02 Aggression condition fails

Same as TV-ABS-01 but aggressive SELL volume 80 (< 100).
Expected: no event.

### TV-ABS-03 Stall condition fails

Same as TV-ABS-01 but price range = 2 ticks.
Expected: no event.

### TV-ABS-04 Replenish condition fails

Same as TV-ABS-01 but bid liquidity decreases below window-start level without replenishment.
Expected: no event.

### TV-ABS-05 Sell Absorption (qualify)

Input: aggressive BUY volume 150 at price 200; price range = 1 tick; ask liquidity replenished.
Expected: Sell Absorption event, strength = 1.0.

## 4.5 Signal Engine (SignalEngine)

Fixture: `w_cvd` = `w_fp` = `w_imb` = 1.0, `confidence_threshold` = 0.6, `absorption_veto_threshold` = 0.5.

### TV-SIG-01 BUY signal

Input scores: cvd +80, fp +60, imb +70. No absorption event.
Expected: composite = 70, confidence = 0.70, signal = BUY, reasons include CVD_UP, FOOTPRINT_BUY, STACKED_IMBALANCE.

### TV-SIG-02 Confidence boundary (qualify)

Input scores: cvd +60, fp +60, imb +60.
Expected: composite = 60, confidence = 0.60, signal = BUY (≥ threshold).

### TV-SIG-03 Confidence boundary (not qualify)

Input scores: cvd +50, fp +50, imb +50.
Expected: composite = 50, confidence = 0.50, signal = WAIT, reason LOW_CONFIDENCE.

### TV-SIG-04 Absorption veto

Input scores: cvd +80, fp +80, imb +80 (direction +1). Absorption reports absorption against the composite direction with strength 1.0 (≥ 0.5).
Expected: signal = WAIT, reasons include ABSORPTION_VETO.

### TV-SIG-05 SELL signal

Input scores: cvd −90, fp −70, imb −80. No absorption event.
Expected: composite = −80, confidence = 0.80, signal = SELL.

### TV-SIG-06 Missing input

Input: Imbalance module disabled by feature flag; scores cvd +90, fp +90.
Expected: composite = (90 + 90) / 2 = 90, confidence = 0.90, signal = BUY (disabled module excluded from numerator and denominator).

### TV-SIG-07 No input

Input: all scoring modules disabled.
Expected: signal = WAIT, reason NO_INPUT.

## 4.6 Data Normalizer (DataNormalizer)

Fixture: exchange profile "EX1" with mapping (epoch_ms → event_time UTC, sym → symbol, px → price, qty → quantity, aggr → side), `dedup_window` = 10000, `reorder_tolerance` = 500 ms.

### TV-NRM-01 Normal conversion

Input raw event: epoch_ms = 1767225601000, sym = BTCUSDT, px = 50000.5, qty = 3, aggr = BUY.
Expected normalized record: event_time = 2026-01-01T00:00:01Z, symbol = BTCUSDT, price = 50000.5, quantity = 3, side = BUY.

### TV-NRM-02 Duplicate discard

Input: same trade_id delivered twice.
Expected: first emitted, second discarded, duplicate counter = 1.

### TV-NRM-03 Reorder within tolerance

Input: event B (t = 10.000 s) arrives, then event A (t = 9.600 s) arrives (400 ms late, ≤ 500 ms).
Expected: output order A → B; reordered counter = 1.

### TV-NRM-04 Reorder beyond tolerance

Input: event C (t = 9.400 s) arrives after last emitted t = 10.000 s (600 ms late, > 500 ms).
Expected: C rejected, counted, logged; no silent loss.

---

# 5. Acceptance Criteria

- Functional requirements satisfied
- Non-functional targets achieved
- Deterministic replay
- All test vectors in Section 4 pass
- No undocumented errors
- Documentation consistency verified

---

# 6. Performance Targets

- Continuous operation
- Zero intentional data loss
- Stable recovery
- Configurable scalability

---

# 7. References

- Requirements
- NFR
- CVD
- Footprint
- Imbalance
- Absorption
- SignalEngine
- DataNormalizer
- ErrorCodes
- Documentation_Standard
