# LiquidityReference_v3.0

# Purpose

Defines canonical liquidity concepts used throughout the Order Flow
Analysis Platform.

------------------------------------------------------------------------

## Liquidity Concepts

  -----------------------------------------------------------------------
  Term                                Definition
  ----------------------------------- -----------------------------------
  Liquidity                           The ability to execute orders with
                                      minimal price impact.

  High Liquidity                      Market condition with abundant
                                      resting orders and tight spreads.

  Low Liquidity                       Market condition with fewer resting
                                      orders and wider spreads.

  Liquidity Pool                      Area where stop orders and resting
                                      liquidity are concentrated.

  Liquidity Sweep                     Temporary move through a liquidity
                                      pool before continuation or
                                      reversal.

  Resting Liquidity                   Passive limit orders awaiting
                                      execution.

  Aggressive Liquidity                Market orders consuming resting
                                      liquidity.
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## Reference Rules

-   Liquidity terminology is defined once in this document.
-   Strategy and module documents shall reference these definitions.
-   Venue-specific terminology may extend but shall not replace this
    reference.

Status: Phase4 Reference Enhancement
