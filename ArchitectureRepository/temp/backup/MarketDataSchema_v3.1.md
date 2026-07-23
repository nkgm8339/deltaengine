# MarketDataSchema_v3.1

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

  Field       Type
  ----------- ---------
  bar_time    datetime
  symbol      string
  timeframe   string
  open        decimal
  high        decimal
  low         decimal
  close       decimal
  volume      decimal
  delta       decimal
  cvd         decimal

Candles are aggregated per `market.bar_timeframe` (see CVD module and
YAML configuration). Default timeframe: 1m.

------------------------------------------------------------------------

## Rules

-   UTC timestamps internally (ISO-8601).
-   Price precision follows instrument tick size.
-   Quantity and volume are decimal (fractional quantities are valid).
-   Field names align with JSONSchema, ParquetSchema, and DuckDBDDL.
-   Enumerations are defined only in EnumDefinitions.
-   Derived values are never used as source data.

Status: Phase5 Pre-Implementation Fix

## References

- JSONSchema
- ParquetSchema
- DuckDBDDL
- DataDictionary
- EnumDefinitions
