# DeltaReference_v3.0

# Purpose

Defines the canonical terminology for Delta analysis used throughout the
Order Flow Analysis Platform.

------------------------------------------------------------------------

## Core Concepts

  -----------------------------------------------------------------------
  Term                                Definition
  ----------------------------------- -----------------------------------
  Delta                               Difference between aggressive buy
                                      volume and aggressive sell volume.

  Positive Delta                      Ask volume exceeds bid volume.

  Negative Delta                      Bid volume exceeds ask volume.

  Zero Delta                          Equal aggressive buy and sell
                                      volume.

  Bar Delta                           Sum of Delta values within one
                                      aggregation period.

  Cumulative Delta (CVD)              Running accumulation of Bar Delta
                                      values.

  Delta Divergence                    Price and Delta move in conflicting
                                      directions.
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## Reference Rules

-   This document is the SSOT for Delta terminology.
-   All modules shall reference these definitions.
-   Platform-specific calculations may extend but shall not redefine
    these concepts.

Status: Phase4 Reference Enhancement
