# ADR-008 — Liquidation Stream Design

**Status**: Accepted
**Version**: v3.0

---

# Context

The Binance Futures `@forceOrder` stream publishes forced liquidation orders in real time. Liquidation volume and direction (long vs. short) are valuable inputs for order flow analysis and future web dashboard features. The question is how to integrate this stream into the existing pipeline with minimal risk to the established trade/depth paths.

---

# Decisions

## Decision 1: In-Memory Only — No DuckDB/Parquet Persistence

Liquidation events are held in a pipeline-local ring buffer (`deque(maxlen=200)`) and
accumulated into two notional counters (`long_liq_notional`, `short_liq_notional`).
They are never written to DuckDB or Parquet.

**Rationale**: Liquidation data is used for real-time display and signal context only.
Persisting it would require schema changes, migration complexity, and ongoing storage cost
disproportionate to its current analytical value. A future ADR may revisit persistence
when the web dashboard is implemented.

## Decision 2: REST Market Data Functions — Fetch Only, No Polling Loop

Three REST functions are added to `src/acquisition/binance_rest.py`:
- `fetch_open_interest(symbol)` → GET /fapi/v1/openInterest
- `fetch_premium_index(symbol)` → GET /fapi/v1/premiumIndex
- `fetch_ticker_24hr(symbol)` → GET /fapi/v1/ticker/24hr

These functions return raw API dicts with numeric values as strings (no float conversion).
The polling loop, call scheduling, and integration into any dashboard are deferred to a
subsequent implementation phase.

**Rationale**: Decouples data acquisition from display/integration concerns. Functions can
be tested independently of any scheduling infrastructure.

## Decision 3: Broadcast Hooks — Optional Callbacks, Default None

Four broadcast hook parameters are added to `LivePipeline`:
- `on_trade(NormalizedTrade)` — called after each normalized trade
- `on_candle(Candle)` — called after each closed candle
- `on_analysis(AnalysisResult)` — called after each bar analysis
- `on_liquidation(LiquidationEvent)` — called after each liquidation event

All hooks default to `None`; when `None`, the existing behavior is unchanged.
The web application layer (future phase) wires callbacks to push data to WebSocket clients.

**Rationale**: Avoids coupling the pipeline to a specific transport (FastAPI, WebSocket, etc.).
The hook pattern keeps the pipeline testable without a running web server.

---

# Rationale (Cross-Decision)

The three decisions follow a common principle: **add capability without changing existing
guarantees**. The trade/depth/CVD/signal paths are unchanged. All new state is additive,
not modifying. Tests confirm this: all 207 pre-existing tests pass unchanged after the
MarketData拡張_v1 implementation.

---

# Consequences

**Positive**
- Liquidation data is available in the pipeline immediately.
- No schema migration required.
- Existing tests are unaffected.
- Web app integration point is well-defined (hook interface).

**Trade-offs**
- Liquidation events are not queryable from DuckDB.
- Ring buffer holds only the last 200 events; events before pipeline start are not available.
- REST functions require explicit call from the web layer; no automatic refresh.

---

# Related Documents

- DataNormalizer_v3.3
- MarketDataSchema_v3.3
- ExchangeConnectorReference
- ADR-006_TradeStream_Selection
- ADR-007_OrderBook_Initial_Sync
