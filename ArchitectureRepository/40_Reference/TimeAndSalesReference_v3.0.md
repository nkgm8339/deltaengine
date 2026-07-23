# TimeAndSalesReference_v3.0

# Purpose

Defines the canonical terminology for Time & Sales data used throughout
the Order Flow Analysis Platform.

------------------------------------------------------------------------

## Core Concepts

  Term             Definition
  ---------------- --------------------------------------------------
  Time & Sales     Chronological record of executed trades.
  Trade Print      A single executed transaction.
  Execution Time   Timestamp when the trade was completed.
  Trade Price      Executed transaction price.
  Trade Volume     Quantity executed in the transaction.
  Aggressor Side   Whether the buyer or seller initiated the trade.
  Large Trade      Trade exceeding a configurable size threshold.

------------------------------------------------------------------------

## Reference Rules

-   This document is the SSOT for Time & Sales terminology.
-   Modules shall reference these definitions rather than redefine them.
-   Feed-specific fields may extend but shall not replace these
    concepts.

Status: Phase4 Reference Enhancement
