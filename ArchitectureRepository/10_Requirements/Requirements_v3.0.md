# Requirements

**Document ID**: REQ-001
**Version**: v3.0
**Status**: Draft

---

# 1. Purpose

Define the functional and business requirements for the Order Flow Analysis Platform.

---

# 2. Business Goal

Provide a professional Order Flow Analysis Platform capable of supporting discretionary trading through high-quality market microstructure analysis.

---

# 3. Functional Requirements

## FR-001 Data Acquisition

The platform shall acquire real-time market data from supported exchanges.

## FR-002 Order Flow Processing

The platform shall calculate:

- Delta
- CVD
- Footprint
- Imbalance
- Absorption

## FR-003 Signal Generation

The platform shall generate trading signals from processed market data.

## FR-004 AI Analysis

The platform shall summarize market conditions using the Signal Engine outputs.

## FR-005 Data Storage

The platform shall store historical data using Parquet as the canonical data source and DuckDB for analytics.

## FR-006 Visualization

The platform shall provide processed data to MT5 for visualization.

---

# 4. Non-Goals

The platform does not execute trades automatically in its initial release.

---

# 5. Success Criteria

- Stable real-time processing
- Reproducible calculations
- Consistent architecture
- AI-ready documentation

---

# 6. References

- 00_Master/00_Architecture_Repository_Master_v3.0.md
- Documentation_Standard_v3.0.md
- ADR-000
- ADR-001