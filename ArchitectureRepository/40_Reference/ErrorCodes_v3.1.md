# Error Codes

**Document ID**: REF-003
**Version**: v3.1
**Status**: Draft

---

# 1. Purpose

Define the standard error codes used throughout the Order Flow Analysis Platform.

All modules shall use these codes when reporting errors.

---

# 2. Error Code Format

```
EXXXX
```

- E = Error
- First digit = Category
- Remaining digits = Sequential identifier

---

# 3. Categories

| Range | Category |
|--------|----------|
| E1xxx | Configuration |
| E2xxx | Data Acquisition |
| E3xxx | Processing |
| E4xxx | Storage |
| E5xxx | AI / Signal |
| E9xxx | Internal System |

---

# 4. Standard Error Codes

| Code | Description |
|------|-------------|
| E1001 | Configuration file not found |
| E1002 | Configuration validation failed |
| E2001 | WebSocket connection failed |
| E2002 | WebSocket timeout |
| E2003 | Invalid market data received |
| E3001 | Invalid trade data |
| E3002 | Duplicate trade_id detected |
| E3003 | Processing pipeline failure |
| E3004 | Out-of-order event rejected (beyond reorder tolerance) |
| E4001 | Parquet write failed |
| E4002 | DuckDB write failed |
| E4003 | Storage unavailable |
| E5001 | Signal generation failed |
| E5002 | AI analysis failed |
| E9001 | Unexpected internal error |
| E9002 | Bounded queue overflow |

---

# 5. Error Handling Rules

- Every error shall be logged.
- Recoverable errors shall trigger retry procedures.
- Non-recoverable errors shall terminate the affected process safely.
- Error messages shall include the corresponding error code.

---

# 6. References

- Documentation_Standard
- DataDictionary
