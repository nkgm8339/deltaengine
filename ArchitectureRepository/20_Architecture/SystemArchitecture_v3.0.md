# System Architecture

**Document ID**: ARC-001
**Version**: v3.0
**Status**: Draft

---

# 1. Purpose

Define the high-level architecture of the Order Flow Analysis Platform and the relationships between major components.

---

# 2. Architectural Style

- Layered Architecture
- Event-Driven Processing
- Modular Design
- Single Source of Truth (SSOT)

---

# 3. High-Level Flow

```text
Exchange
   │
   ▼
Data Acquisition
   │
   ▼
Data Normalizer
   │
   ▼
Order Flow Engine
   ├── CVD
   ├── Footprint
   ├── Imbalance
   └── Absorption
        │
        ▼
Signal Engine
        │
        ▼
AI Analysis
        │
        ├── MT5
        └── Storage
```

---

# 4. Core Components

| Component | Responsibility |
|-----------|----------------|
| Data Acquisition | Receive market data |
| Data Normalizer | Normalize exchange events |
| Order Flow Engine | Calculate market microstructure metrics |
| Signal Engine | Generate trading signals |
| AI Analysis | Interpret market state |
| Storage | Persist Parquet and DuckDB data |
| MT5 Adapter | Deliver visualization data |

---

# 5. Architectural Principles

- Loose coupling
- High cohesion
- Stateless processing where practical
- Configuration-driven behavior
- Replaceable modules

---

# 6. Data Flow

Market Data → Normalization → Analysis → Signal → AI → Storage / Visualization

---

# 7. References

- Requirements_v3.0.md
- NFR_v3.0.md
- 00_Architecture_Repository_Master_v3.0.md