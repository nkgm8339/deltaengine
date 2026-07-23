# VWAPReference_v3.0

# Purpose

Defines the canonical terminology for Volume Weighted Average Price
(VWAP) used throughout the Order Flow Analysis Platform.

------------------------------------------------------------------------

## Core Concepts

  -----------------------------------------------------------------------
  Term                                Definition
  ----------------------------------- -----------------------------------
  VWAP                                Volume Weighted Average Price
                                      calculated from traded volume and
                                      price.

  Session VWAP                        VWAP calculated from the start of
                                      the current trading session.

  Anchored VWAP                       VWAP calculated from a user-defined
                                      anchor point.

  Standard Deviation Band             Statistical band around VWAP used
                                      to assess price dispersion.

  VWAP Cross                          Event where price crosses the VWAP.

  VWAP Slope                          Rate of change of VWAP over time.
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## Reference Rules

-   This document is the SSOT for VWAP terminology.
-   All architecture and module documents shall reference these
    definitions.
-   Implementation-specific display options shall not redefine these
    concepts.

Status: Phase4 Reference Enhancement
