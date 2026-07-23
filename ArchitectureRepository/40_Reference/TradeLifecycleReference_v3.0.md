# TradeLifecycleReference_v3.0

# Purpose

Defines the canonical trade lifecycle terminology used throughout the
Order Flow Analysis Platform.

------------------------------------------------------------------------

## Trade Lifecycle

  -----------------------------------------------------------------------
  Stage                               Definition
  ----------------------------------- -----------------------------------
  Signal Generated                    Strategy identifies a valid trading
                                      opportunity.

  Order Created                       Trading instruction is generated.

  Order Submitted                     Order is sent to the execution
                                      venue.

  Order Executed                      Order is filled partially or
                                      completely.

  Position Open                       Active market exposure exists.

  Position Managed                    Stops, targets, and risk controls
                                      are actively managed.

  Position Closed                     Exposure is fully exited and
                                      realized PnL is finalized.
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## Reference Rules

-   This document is the SSOT for trade lifecycle terminology.
-   Requirements, Architecture, and Modules shall reference these
    definitions.
-   Platform-specific workflow extensions shall not redefine these
    stages.

Status: Phase4 Reference Enhancement
