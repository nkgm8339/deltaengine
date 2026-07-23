# Footprint Module

**Document ID**: MOD-005
**Version**: v3.0
**Status**: Draft

---

# 1. Purpose

Construct Footprint data by aggregating executed BUY and SELL volume at each price level.

---

# 2. Responsibilities

- Aggregate volume by price
- Separate BUY and SELL aggressor volume
- Build tick and bar Footprints
- Publish Footprint updates

---

# 3. Inputs

- event_time
- trade_id
- price
- quantity
- side

---

# 4. Outputs

- Price level volume
- BUY volume
- SELL volume
- Footprint structure

---

# 5. Processing Rules

For each executed trade:

- Locate price level
- Add quantity to BUY or SELL column
- Update Footprint totals

No estimation is permitted.

---

# 6. Error Handling

- Invalid trade
- Missing side
- Duplicate trade_id
- Invalid price

---

# 7. Performance Targets

- Real-time aggregation
- Deterministic replay
- Consistent price-level accounting

---

# 8. References

- DataDictionary_v3.0.md
- EnumDefinitions_v3.0.md
- CVD_v3.0.md
- ErrorCodes_v3.0.md