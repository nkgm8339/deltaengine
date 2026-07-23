# DOMReference_v3.0

# Purpose

Defines the canonical terminology for the Depth of Market (DOM) used
throughout the Order Flow Analysis Platform.

------------------------------------------------------------------------

## Core Concepts

  -----------------------------------------------------------------------
  Term                                Definition
  ----------------------------------- -----------------------------------
  Depth of Market (DOM)               Real-time display of resting bid
                                      and ask liquidity.

  Bid Queue                           Resting buy limit orders at each
                                      price level.

  Ask Queue                           Resting sell limit orders at each
                                      price level.

  Best Bid                            Highest available bid price.

  Best Ask                            Lowest available ask price.

  Spread                              Difference between the Best Ask and
                                      Best Bid.

  Queue Position                      Relative execution priority within
                                      a price level.

  Book Imbalance                      Relative dominance of bid or ask
                                      liquidity in the order book.
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## Reference Rules

-   This document is the SSOT for DOM terminology.
-   Architecture and Modules shall reference these definitions.
-   Exchange-specific book structures may extend but shall not redefine
    these concepts.

Status: Phase4 Reference Enhancement
