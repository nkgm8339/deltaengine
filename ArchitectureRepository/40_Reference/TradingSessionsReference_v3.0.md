# TradingSessionsReference_v3.0

# Purpose

Defines the canonical trading session event terminology used throughout
the Order Flow Analysis Platform.

------------------------------------------------------------------------

## Session Events

  -----------------------------------------------------------------------
  Event                               Definition
  ----------------------------------- -----------------------------------
  Session Open                        Official start of a trading
                                      session.

  Session Close                       Official end of a trading session.

  Session High                        Highest traded price during the
                                      session.

  Session Low                         Lowest traded price during the
                                      session.

  Opening Range                       Price range established during the
                                      configured opening period.

  Session VWAP                        VWAP calculated from the session
                                      open.

  Session Reset                       Initialization of session-based
                                      indicators and statistics.
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## Reference Rules

-   This document is the SSOT for trading session terminology.
-   Architecture, Modules, and Requirements shall reference these
    definitions.
-   Exchange-specific schedules shall extend, not redefine, these
    concepts.

Status: Phase4 Reference Enhancement
