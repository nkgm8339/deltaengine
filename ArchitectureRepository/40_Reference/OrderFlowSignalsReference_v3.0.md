# OrderFlowSignalsReference_v3.0

# Purpose

Defines the canonical order flow signal terminology used throughout the
Order Flow Analysis Platform.

------------------------------------------------------------------------

## Core Signals

  -----------------------------------------------------------------------
  Signal                              Definition
  ----------------------------------- -----------------------------------
  Buying Pressure                     Persistent aggressive buying
                                      exceeding selling activity.

  Selling Pressure                    Persistent aggressive selling
                                      exceeding buying activity.

  Absorption                          Passive liquidity absorbs
                                      aggressive orders with limited
                                      price movement.

  Exhaustion                          Declining aggressive participation
                                      near the end of a move.

  Initiative Activity                 Aggressive orders driving price
                                      into new areas.

  Responsive Activity                 Passive or counter-directional
                                      activity defending value.

  Momentum Shift                      Observable transition in order flow
                                      favoring the opposite side.
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## Reference Rules

-   This document is the SSOT for order flow signal terminology.
-   Architecture, Modules, and Requirements shall reference these
    definitions.
-   Strategy-specific signal combinations may extend but shall not
    redefine these concepts.

Status: Phase4 Reference Enhancement
