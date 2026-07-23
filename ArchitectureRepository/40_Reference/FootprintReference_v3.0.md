# FootprintReference_v3.0

# Purpose

Defines the canonical terminology for Footprint Charts used throughout
the Order Flow Analysis Platform.

------------------------------------------------------------------------

## Footprint Elements

  -----------------------------------------------------------------------
  Term                                Definition
  ----------------------------------- -----------------------------------
  Bid Volume                          Executed volume at the bid price.

  Ask Volume                          Executed volume at the ask price.

  Delta                               Ask Volume minus Bid Volume at a
                                      price level.

  Cell                                A single price row within a
                                      footprint bar.

  Cluster                             Collection of cells representing
                                      one aggregation period.

  POC                                 Price level with the highest traded
                                      volume within the footprint.

  Imbalance                           Significant dominance of buying or
                                      selling volume at a price level.
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## Reference Rules

-   All footprint modules shall reference these definitions.
-   Display settings are implementation details and are defined
    separately.
-   Exchange-specific extensions shall not redefine these terms.

Status: Phase4 Reference Enhancement
