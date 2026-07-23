# PerformanceMetricsReference_v3.0

# Purpose

Defines the canonical performance metrics used throughout the Order Flow
Analysis Platform.

------------------------------------------------------------------------

## Core Metrics

  -----------------------------------------------------------------------
  Metric                              Definition
  ----------------------------------- -----------------------------------
  Net Profit                          Total realized profit minus total
                                      realized loss.

  Gross Profit                        Sum of all profitable trades before
                                      losses.

  Gross Loss                          Sum of all losing trades.

  Profit Factor                       Gross Profit divided by Gross Loss.

  Win Rate                            Percentage of profitable trades.

  Average Win                         Mean profit of winning trades.

  Average Loss                        Mean loss of losing trades.

  Expectancy                          Average expected outcome per trade
                                      based on wins and losses.

  Maximum Drawdown                    Largest equity decline from peak to
                                      trough.

  Sharpe Ratio                        Risk-adjusted return based on
                                      return volatility.
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## Reference Rules

-   This document is the SSOT for performance metric terminology.
-   Requirements, Modules, Reports, and Analytics shall reference these
    definitions.
-   Calculation formulas may be extended in implementation documents but
    shall not redefine the metrics.

Status: Phase4 Reference Enhancement
