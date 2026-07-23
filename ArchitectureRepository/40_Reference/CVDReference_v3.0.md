# CVDReference_v3.0

# Purpose

Defines the canonical terminology for Cumulative Volume Delta (CVD) used
throughout the Order Flow Analysis Platform.

------------------------------------------------------------------------

## Core Concepts

  -----------------------------------------------------------------------
  Term                                Definition
  ----------------------------------- -----------------------------------
  Cumulative Volume Delta (CVD)       Running accumulation of Delta
                                      values over time.

  Session CVD                         CVD reset at the beginning of each
                                      trading session.

  Continuous CVD                      CVD accumulated across multiple
                                      sessions.

  CVD Slope                           Rate of change of the cumulative
                                      delta.

  CVD Divergence                      Disagreement between price movement
                                      and CVD direction.

  CVD Reset                           Initialization of CVD according to
                                      platform rules.

  CVD Baseline                        Starting reference value used after
                                      a reset.
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## Reference Rules

-   This document is the SSOT for CVD terminology.
-   All architecture, module, and strategy documents shall reference
    these definitions.
-   Calculation methods may be extended but shall not redefine these
    concepts.

Status: Phase4 Reference Enhancement
