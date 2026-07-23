# MarketStructureReference_v3.0

# Purpose

Defines the canonical market structure terminology used across the Order
Flow Analysis Platform.

------------------------------------------------------------------------

## Structure Elements

  Term               Definition
  ------------------ ---------------------------------------------------------
  Higher High (HH)   A swing high above the previous swing high.
  Higher Low (HL)    A swing low above the previous swing low.
  Lower High (LH)    A swing high below the previous swing high.
  Lower Low (LL)     A swing low below the previous swing low.
  Swing High         Local maximum surrounded by lower highs.
  Swing Low          Local minimum surrounded by higher lows.
  Trend              Sequence of HH/HL (uptrend) or LH/LL (downtrend).
  Range              Sideways price movement between support and resistance.

------------------------------------------------------------------------

## Interpretation Rules

-   Market structure is determined from confirmed swing points.
-   Trend identification shall precede strategy evaluation.
-   All modules shall reference these definitions without modification.
-   Exchange-specific terminology shall extend this reference only.

Status: Phase4 Reference Enhancement
