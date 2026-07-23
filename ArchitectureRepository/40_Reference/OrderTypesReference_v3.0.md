# OrderTypesReference_v3.0

# Purpose

Defines the canonical order types and execution instructions used
throughout the platform.

------------------------------------------------------------------------

## Order Types

  -----------------------------------------------------------------------
  Order Type                          Description
  ----------------------------------- -----------------------------------
  Market Order                        Executes immediately at the best
                                      available price.

  Limit Order                         Executes only at the specified
                                      price or better.

  Stop Order                          Becomes a market order after the
                                      stop price is reached.

  Stop Limit Order                    Becomes a limit order after the
                                      stop price is reached.
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## Time in Force

  Type   Description
  ------ --------------------------
  GTC    Good Till Cancelled
  DAY    Valid until market close
  IOC    Immediate Or Cancel
  FOK    Fill Or Kill

------------------------------------------------------------------------

## Reference Rules

-   These definitions are SSOT for order terminology.
-   Modules shall reference this document without redefining order
    types.
-   Exchange-specific extensions shall be documented separately.

Status: Phase4 Reference Enhancement
