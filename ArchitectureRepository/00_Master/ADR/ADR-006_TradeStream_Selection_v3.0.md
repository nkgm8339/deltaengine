# ADR-006 — Trade Stream Selection

**Status**: Accepted
**Version**: v3.0

---

# Context

The platform originally subscribed to `btcusdt@aggTrade` on Binance Futures (`wss://fstream.binance.com/ws` + SUBSCRIBE). During live verification (BugFix_Live), no aggTrade events were received. Investigation with `ws_probe2.py` confirmed that `@aggTrade` is not delivered on this endpoint, while `@trade` (individual trade stream) works correctly.

`@trade` events carry the same fields as `@aggTrade` (`E`, `T`, `s`, `p`, `q`, `m`) plus the individual trade id `t`. The aggregate trade id `a` is also present. The only functional difference is the dedup key: `@aggTrade` uses `a` (aggregate), `@trade` uses `t` (individual).

---

# Decision

1. The platform subscribes to `btcusdt@trade` instead of `btcusdt@aggTrade`.
2. The dedup key (`trade_id` in the exchange profile) maps to `t` (individual trade id).
3. The `trade_id_fallback` mechanism in the normalizer is retained for generality; the Binance profile uses `trade_id_fallback: a` for backward compat with existing `@aggTrade` test fixtures.
4. `is_agg_trade_or_depth` accepts both `"aggTrade"` and `"trade"` event types so existing test fixtures (which use `e: "aggTrade"`) remain valid without modification.

---

# Rationale

- `@aggTrade` is confirmed unavailable on the Binance Futures `/ws` + SUBSCRIBE endpoint.
- `@trade` provides equivalent data at individual-trade granularity (equal or higher resolution).
- Changing the dedup key from `a` to `t` is semantically correct: each `@trade` event represents one fill, and `t` uniquely identifies it.

---

# Consequences

Positive

- Live pipeline works without runtime workarounds.
- Config, profile, and code are consistent.

Trade-offs

- Individual trades are higher frequency than aggregate trades. Volume per event may be smaller. No impact on CVD/Footprint/Imbalance correctness (they process per-event regardless of granularity).
- Existing test fixtures use `e: "aggTrade"` with field `a` as trade_id. These remain valid because `is_agg_trade_or_depth` accepts both event types and the normalizer `trade_id_fallback` mechanism handles `a` when `t` is absent.

---

# Related Documents

- YAMLReference
- WebSocket
- ExchangeConnectorReference
- ADR-003_Concurrency_Model
