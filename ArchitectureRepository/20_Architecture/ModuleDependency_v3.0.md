# Module Dependency

**Document ID**: ARC-002
**Version**: v3.0
**Status**: Draft

---

# 1. Purpose

Define dependencies between major modules of the Order Flow Analysis Platform.

---

# 2. Dependency Rules

- Dependencies shall flow in one direction.
- Circular dependencies are prohibited.
- Lower layers shall not depend on higher layers.
- Shared definitions shall be referenced from the Reference layer only.

---

# 3. Dependency Diagram

```text
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
     ├── Storage
     └── MT5 Adapter
```

---

# 4. Module Responsibilities

| Module | Depends On |
|---------|------------|
| Data Acquisition | None |
| Data Normalizer | Data Acquisition |
| Order Flow Engine | Data Normalizer |
| Signal Engine | Order Flow Engine |
| AI Analysis | Signal Engine |
| Storage | Order Flow Engine, AI Analysis |
| MT5 Adapter | AI Analysis |

---

# 5. Dependency Constraints

- Module interfaces shall be contract-based.
- Internal implementations shall not be accessed directly.
- Communication shall occur only through documented interfaces.

---

# 6. Future Extensions

The dependency model shall support:

- Multi-exchange adapters
- Multiple AI engines
- Additional analytics modules
- Distributed processing

---

# 7. References

- SystemArchitecture_v3.0.md
- Requirements_v3.0.md
- Documentation_Standard_v3.0.md