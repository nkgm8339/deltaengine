# IndicatorDefinitions_v1.0

# Indicator Definitions

## Delta

Difference between aggressive buy volume and aggressive sell volume.

Formula: Delta = Ask Volume - Bid Volume

## CVD (Cumulative Volume Delta)

Running accumulation of Delta.

Formula: CVD(n) = CVD(n-1) + Delta(n)

## Volume

Total executed contracts during the aggregation period.

## VWAP

Volume Weighted Average Price.

Formula: VWAP = Σ(price × volume) / Σ(volume)

## Imbalance

Relative dominance of bid or ask volume at a price level.

Typical Threshold: - 300% - 400% - 500%

## Absorption

Large passive liquidity absorbing aggressive orders without significant
price movement.

## Exhaustion

Declining aggressive volume near the end of a directional move.

Status: Phase4 Reference Enhancement.
