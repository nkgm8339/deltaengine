# Enum Definitions

**Document ID**: REF-002
**Version**: v3.1
**Status**: Draft

---

# 1. Purpose

Define all shared enumerations used throughout the Architecture Repository.

All specifications shall reference these definitions.

---

# 2. TradeSide

| Name | Description |
|------|-------------|
| BUY | Buy aggressor |
| SELL | Sell aggressor |

---

# 3. SignalType

| Name | Description |
|------|-------------|
| BUY | Buy signal |
| SELL | Sell signal |
| WAIT | No actionable signal |

---

# 4. MarketState

| Name | Description |
|------|-------------|
| STRONG_BULL | Strong bullish condition |
| BULL | Bullish condition |
| NEUTRAL | Neutral market |
| BEAR | Bearish condition |
| STRONG_BEAR | Strong bearish condition |

---

# 5. Timeframe

| Name | Description |
|------|-------------|
| 1s | 1 second |
| 1m | 1 minute |
| 5m | 5 minutes |
| 15m | 15 minutes |
| 1h | 1 hour |
| 4h | 4 hours |
| 1d | 1 day |

---

# 6. SystemState

| Name | Description |
|------|-------------|
| INITIALIZING | Startup |
| CONFIGURATION_LOADED | Configuration complete |
| CONNECTING | Connecting to exchange |
| CONNECTED | Connected |
| RUNNING | Normal processing |
| RECOVERING | Recovery mode |
| SHUTTING_DOWN | Graceful shutdown |
| STOPPED | System stopped |

---

# 7. Ownership

Shared enumerations shall be defined only in this document.

---

# 8. References

- DataDictionary
- Documentation_Standard
