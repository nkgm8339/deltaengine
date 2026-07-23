# Directory Structure

**Document ID**: IMP-002
**Version**: v3.0
**Status**: Draft

---

# 1. Purpose

Define the standard directory structure for the Order Flow Analysis Platform implementation.

---

# 2. Root Layout

```text
Delta_Engine_Pro4web/
├── config/
├── data/
│   ├── parquet/
│   └── duckdb/
├── docs/
├── logs/
├── src/
│   ├── acquisition/
│   ├── normalization/
│   ├── orderflow/
│   ├── signal/
│   ├── ai/
│   ├── database/
│   └── mt5/
├── tests/
├── tools/
└── README.md
```

---

# 3. Rules

- Architecture documents are stored under docs/.
- Source code resides under src/.
- Generated data shall not be committed unless explicitly required.
- Tests mirror the src/ directory structure.

---

# 4. References

- README.md
- CodingGuideline_v3.0.md
- Documentation_Standard_v3.0.md