# ExchangeConnectorReference_v3.0

# Purpose

Defines the canonical terminology for exchange connectivity used throughout the Order Flow Analysis Platform.

This document is the SSOT for WebSocket connection management, market data feed handling, and exchange interaction concepts.

------------------------------------------------------------------------

## Core Concepts

| Term | Definition |
|------|-----------|
| Exchange | A trading venue that provides real-time market data and order execution services |
| WebSocket | Persistent full-duplex communication channel used to receive real-time market data from an exchange |
| Market Data Feed | A continuous stream of market events delivered over a WebSocket connection |
| Stream Subscription | The act of registering to receive a specific type of market data from an exchange |
| Symbol | A string identifier representing a tradable instrument (e.g., BTCUSDT) |
| Endpoint | The exchange-specific WebSocket URL for a given data stream |

------------------------------------------------------------------------

## Connection Lifecycle

| State | Definition |
|-------|-----------|
| DISCONNECTED | No active connection to the exchange |
| CONNECTING | Connection attempt in progress |
| CONNECTED | Connection established; awaiting stream data |
| SUBSCRIBED | Stream subscriptions confirmed; receiving data |
| RECONNECTING | Previous connection lost; attempting to restore |

------------------------------------------------------------------------

## Feed Types

| Feed | Description |
|------|------------|
| Trade Feed | Stream of individual executed trades (price, quantity, side, timestamp). Binance: `@trade` stream. |
| Order Book Feed | Stream of Depth of Market updates (bid/ask queues). Binance: `@depth@100ms` stream. |
| Liquidation Feed | Stream of forced liquidation orders (price, quantity, side, symbol). Binance: `@forceOrder` stream. Side indicates the direction of the liquidation order: SELL = long position liquidated, BUY = short position liquidated. |
| Snapshot | Point-in-time REST response used to initialize state before streaming begins |

------------------------------------------------------------------------

## Connection Management

| Term | Definition |
|------|-----------|
| Heartbeat | Periodic message exchanged to confirm connection health |
| Reconnect | Automatic re-establishment of a lost connection |
| Reconnect Delay | Configurable wait period between reconnect attempts |
| Max Reconnect Attempts | Maximum number of reconnect attempts before escalating to error state |
| Sequence Validation | Verification that received events are in the expected order |

------------------------------------------------------------------------

## Data Validation

| Term | Definition |
|------|-----------|
| Payload Validation | Verification that a received message conforms to the expected format |
| Sequence Gap | Missing events detected through sequence number discontinuity |
| Stale Data | Data received with a timestamp significantly behind the current time |

------------------------------------------------------------------------

## REST Market Data Fetch

In addition to WebSocket streams, the platform fetches point-in-time market data via Binance Futures REST endpoints:

| Function | Endpoint | Description |
|----------|----------|-------------|
| `fetch_depth_snapshot` | GET /fapi/v1/depth | Order book snapshot (used for initial sync) |
| `fetch_open_interest` | GET /fapi/v1/openInterest | Current open interest for a symbol |
| `fetch_premium_index` | GET /fapi/v1/premiumIndex | Mark price and funding rate |
| `fetch_ticker_24hr` | GET /fapi/v1/ticker/24hr | 24-hour rolling statistics |

All functions return raw API dicts. Numeric values are returned as strings; the caller is responsible for `Decimal` conversion. `float()` conversion is prohibited platform-wide.

These functions are **fetch-only utilities**: they are not automatically called on a schedule. The polling loop and integration into dashboard or signal calculation are handled by the calling layer (future web application phase, see ADR-008).

---

## Symbol Convention

-   Symbol format follows exchange convention (e.g., BTCUSDT for Binance).
-   Symbol shall match the value defined in configuration (YAMLReference_v3.0.md).
-   Internal processing uses the symbol value as-is without transformation.

------------------------------------------------------------------------

## Reference Rules

-   This document is the SSOT for exchange connector terminology.
-   WebSocket_v3.0.md and DataReceiver_v3.0.md (module specs) shall reference these definitions.
-   Exchange-specific endpoint details belong in configuration, not architecture documents.

## References

- ADR-006_TradeStream_Selection
- ADR-007_OrderBook_Initial_Sync
- ADR-008_LiquidationStream
- YAMLReference
- DataNormalizer

Status: Updated — Liquidation Feed and REST Market Data sections added (MarketData拡張_v1)
