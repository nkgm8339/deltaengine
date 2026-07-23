# MarketDataSchema_v3.4

# Purpose

Defines the canonical market data schema used throughout the repository.
This document is the Single Source of Truth (SSOT) for market data
records.

------------------------------------------------------------------------

## Tick Record

  Field        Type              Required  Description
  ------------ ----------------- --------- ----------------------------
  event_time   datetime            Yes     Event timestamp (UTC)
  trade_time   datetime            Yes     Trade timestamp (UTC)
  trade_id     integer             Yes     Exchange trade identifier
  symbol       string              Yes     Trading instrument
  price        decimal             Yes     Executed price
  quantity     decimal             Yes     Executed quantity
  side         enum(BUY,SELL)      Yes     Aggressor side per EnumDefinitions

------------------------------------------------------------------------

## Candle Record

  Field       Type       Required  Description
  ----------- ---------- --------- ----------------------------------------------
  bar_time    datetime   Yes       UTC start time of the aggregated bar
  symbol      string     Yes       Canonical trading instrument
  timeframe   string     Yes       Aggregation period from `market.bar_timeframe`
  open        decimal    Yes       First executed price in the bar
  high        decimal    Yes       Highest executed price in the bar
  low         decimal    Yes       Lowest executed price in the bar
  close       decimal    Yes       Last executed price in the bar
  volume      decimal    Yes       Total traded quantity
  delta       decimal    Yes       Buy volume minus sell volume
  cvd         decimal    Yes       Cumulative volume delta at bar close

Candles are aggregated per `market.bar_timeframe` (see CVD module and
YAML configuration). Default timeframe: 1m.

------------------------------------------------------------------------

## Order Book Update Record

  Field             Type                       Required  Description
  ----------------- -------------------------- --------- -----------------------------------------
  event_time        datetime                    Yes      Event timestamp (UTC)
  symbol            string                      Yes      Trading instrument
  update_type       enum(SNAPSHOT, DIFF)        Yes      SNAPSHOT: full book replacement.
                                                         DIFF: incremental update to existing book.
  first_update_id           integer                     No       Exchange-provided first sequence id in
                                                                 this update (DIFF only; used for gap
                                                                 detection against previous update)
  final_update_id           integer                     Yes      Exchange-provided final sequence id in
                                                                 this update
  previous_final_update_id  integer                     No       Exchange-provided previous final update id
                                                                 (Binance Futures `pu`). When present,
                                                                 used for gap detection in preference to
                                                                 first_update_id continuity.
  bids                      list<BookLevel>             Yes      Bid side price levels (see BookLevel)
  asks                      list<BookLevel>             Yes      Ask side price levels (see BookLevel)

### BookLevel

  Field         Type       Required  Description
  ------------- ---------- --------- ------------------------------------------------------
  price         decimal      Yes     Price level per instrument tick size
  quantity      decimal      Yes     Resting quantity at this price level.
                                     For DIFF updates: quantity = 0 means the level was
                                     removed; quantity > 0 means the level is set to that
                                     value (not a delta).

Book state semantics:
- SNAPSHOT establishes the complete book; any pre-existing state SHALL be replaced.
- DIFF applies price levels as "set-to-value" (not delta): quantity > 0 overwrites,
  quantity = 0 deletes the level. Absent price levels are unchanged.
- SNAPSHOT SHALL precede any DIFF for a given symbol in a session (initialization order).
- Gap detection between DIFF updates uses `previous_final_update_id` (when present in the
  exchange profile) in preference to `first_update_id` / `final_update_id` continuity.
  On gap detection the book SHALL be re-initialized via a fresh SNAPSHOT.

------------------------------------------------------------------------

## Liquidation Event Record

Produced by the DataNormalizer from Binance `@forceOrder` stream events.
Not persisted to DuckDB or Parquet; held in a pipeline-local ring buffer only
(see ADR-008).

  Field        Type              Required  Description
  ------------ ----------------- --------- ----------------------------
  event_time   datetime            Yes     Event timestamp (UTC), from `E` field
  symbol       string              Yes     Trading instrument
  side         enum(BUY,SELL)      Yes     Direction of the liquidation order (see side semantics below)
  price        decimal             Yes     Execution price of the liquidation order
  quantity     decimal             Yes     Executed quantity of the liquidation order

### Side Semantics

The `side` field describes the **direction of the forced liquidation order**, not the direction of the original position:

| side value | Meaning |
|------------|---------|
| `SELL` | The liquidated position was **LONG** (exchange sold to close the long) |
| `BUY` | The liquidated position was **SHORT** (exchange bought to close the short) |

### Notional Accumulation

The pipeline accumulates:
- `long_liq_notional`: sum of `price × quantity` for all `side = SELL` liquidations
- `short_liq_notional`: sum of `price × quantity` for all `side = BUY` liquidations

These are session-scoped counters; they reset when the pipeline restarts.

------------------------------------------------------------------------

## Order Book State

Order Book State is not itself a persisted record but the in-memory result of
applying Order Book Update Records in sequence. Consumers (e.g., Absorption
module per Absorption_v3.1 §5.2) query the current state at price levels of
interest to evaluate resting liquidity.

  Field           Type                       Description
  --------------- -------------------------- ----------------------------------------
  symbol          string                     Trading instrument
  last_update_id  integer                    final_update_id of the last applied
                                             Order Book Update Record
  bids            map<decimal, decimal>      price → resting quantity (bid side)
  asks            map<decimal, decimal>      price → resting quantity (ask side)

Terminology (Bid Queue / Ask Queue / Best Bid / Best Ask) is defined in
DOMReference. Resting Liquidity terminology is defined in LiquidityReference.
This document does not redefine those terms.

------------------------------------------------------------------------

## Rules

-   UTC timestamps internally (ISO-8601).
-   Price precision follows instrument tick size.
-   Quantity and volume are decimal (fractional quantities are valid).
-   `float()` conversion is prohibited at all normalization stages; all
    numeric values use `Decimal(str(...))`.
-   Field names align with JSONSchema, ParquetSchema, and DuckDBDDL.
-   Enumerations are defined only in EnumDefinitions.
-   Derived values are never used as source data.
-   Order Book Update Records apply to book state per §Order Book State semantics;
    consumers SHALL NOT persist Order Book state as a canonical record.
-   Liquidation Event Records are not persisted; pipeline-local ring buffer only
    (ADR-008).

Status: v3.4 — Candle Record timeframe field specified (Calibration_log_v1)

## References

- JSONSchema
- ParquetSchema
- DuckDBDDL
- DataDictionary
- EnumDefinitions
- DOMReference
- LiquidityReference
- ADR-008_LiquidationStream
