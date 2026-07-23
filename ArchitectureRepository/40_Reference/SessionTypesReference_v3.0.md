# SessionTypesReference_v3.0

# Purpose

Defines the standard trading session classifications used across the
repository.

------------------------------------------------------------------------

## Trading Sessions

  -----------------------------------------------------------------------
  Session                 Typical UTC             Description
  ----------------------- ----------------------- -----------------------
  Asia                    00:00--09:00            Lower average
                                                  volatility; regional
                                                  participation
                                                  dominates.

  London                  07:00--16:00            High liquidity and
                                                  strong institutional
                                                  participation.

  New York                13:00--22:00            High liquidity with
                                                  significant U.S. market
                                                  influence.

  London/New York Overlap 13:00--16:00            Highest liquidity and
                                                  trading activity.
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## Session Rules

-   All internal timestamps use UTC.
-   Session boundaries are configurable for daylight-saving adjustments.
-   Analytics modules shall reference these definitions instead of
    redefining sessions.

Status: Phase4 Reference Enhancement
