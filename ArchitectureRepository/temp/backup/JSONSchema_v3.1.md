# JSON Schema Reference

**Document ID**: REF-004
**Version**: v3.1
**Status**: Draft

---

# 1. Purpose

Define canonical JSON structures exchanged between modules.

---

# 2. Trade Event

```json
{
  "event_time": "2026-01-01T00:00:00Z",
  "trade_time": "2026-01-01T00:00:00Z",
  "trade_id": 123456789,
  "symbol": "BTCUSDT",
  "price": 100000.00,
  "quantity": 0.015,
  "side": "BUY"
}
```

---

# 3. Signal Event

```json
{
  "signal_time": "2026-01-01T00:00:01Z",
  "symbol": "BTCUSDT",
  "signal": "BUY",
  "confidence": 0.87,
  "reason": [
    "CVD_UP",
    "STACKED_IMBALANCE"
  ]
}
```

---

# 4. AI Result

```json
{
  "analysis_time": "2026-01-01T00:00:01Z",
  "market_state": "BULL",
  "risk_level": "LOW",
  "summary": "Bullish order flow",
  "confidence": 0.87
}
```

---

# 5. CVD Update Event

```json
{
  "event_time": "2026-01-01T00:00:00.123Z",
  "symbol": "BTCUSDT",
  "tick_delta": 0.015,
  "tick_cvd": 1.234
}
```

Emitted by the CVD module after each normalized trade event.

---

# 6. Candle Event

```json
{
  "bar_time": "2026-01-01T00:01:00Z",
  "symbol": "BTCUSDT",
  "timeframe": "1m",
  "open": 100000.00,
  "high": 100050.00,
  "low": 99980.00,
  "close": 100020.00,
  "volume": 12.500,
  "delta": 0.800,
  "cvd": 15.300
}
```

Emitted by the CVD module at bar close. Fields align with MarketDataSchema Candle Record and ParquetSchema / DuckDBDDL Candle Schema.

---

# 7. Rules

- UTF-8 encoding
- UTC timestamps (ISO-8601)
- snake_case property names
- Unknown properties shall be ignored unless specified otherwise.

---

# 8. References

- DataDictionary
- EnumDefinitions
- Documentation_Standard
