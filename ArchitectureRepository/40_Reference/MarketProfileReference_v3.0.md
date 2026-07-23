# MarketProfileReference_v3.0

# Purpose

Defines the canonical terminology for Market Profile used throughout the
Order Flow Analysis Platform.

------------------------------------------------------------------------

## Core Concepts

  -----------------------------------------------------------------------
  Term                                Definition
  ----------------------------------- -----------------------------------
  Market Profile                      Distribution of trading activity
                                      organized by time at price.

  TPO (Time Price Opportunity)        One time-period occurrence at a
                                      price level.

  Initial Balance (IB)                Price range established during the
                                      opening period.

  Value Area                          Price range containing the majority
                                      of TPO activity.

  POC (Point of Control)              Price level with the greatest TPO
                                      count.

  Single Prints                       Price levels visited during only
                                      one TPO period, often indicating
                                      directional conviction.

  Excess                              Tail at the edge of a profile
                                      suggesting auction completion.
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## Reference Rules

-   This document is the SSOT for Market Profile terminology.
-   Modules and strategy documents shall reference these definitions.
-   Platform-specific visualization settings shall be documented
    separately.

Status: Phase4 Reference Enhancement
