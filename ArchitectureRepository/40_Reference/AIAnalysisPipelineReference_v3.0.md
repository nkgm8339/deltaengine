# AIAnalysisPipelineReference_v3.0

# Purpose

Defines the canonical terminology and concepts for the AI Analysis Pipeline used throughout the Order Flow Analysis Platform.

This document is the SSOT for AI analysis, market state classification, confidence scoring, and signal interpretation.

------------------------------------------------------------------------

## Core Concepts

| Term | Definition |
|------|-----------|
| AI Analysis Pipeline | The processing stage that aggregates Order Flow module outputs and produces a high-level assessment of current market conditions |
| Market State | Classified assessment of the overall directional bias and condition of the market |
| Confidence Score | A value between 0.0 and 1.0 representing the strength of evidence supporting the current market state assessment |
| Risk Level | Classification of current market risk based on volatility and signal clarity |
| Signal Integration | The process of combining outputs from CVD, Footprint, Imbalance, and Absorption into a unified assessment |
| Deterministic Evaluation | Processing that produces identical outputs from identical inputs, enabling reproducible replay |
| Reason List | An ordered list of the specific signals and conditions that contributed to the current assessment |
| Summary | A human-readable string describing the current market condition |

------------------------------------------------------------------------

## Market State Classification

| State | Definition |
|-------|-----------|
| STRONG_BULL | Strong and sustained buying pressure with multiple confirming signals |
| BULL | Moderate buying bias with partial signal confirmation |
| NEUTRAL | No directional conviction; conflicting or absent signals |
| BEAR | Moderate selling bias with partial signal confirmation |
| STRONG_BEAR | Strong and sustained selling pressure with multiple confirming signals |

------------------------------------------------------------------------

## Confidence Score

| Range | Interpretation |
|-------|---------------|
| 0.0 – 0.49 | Below threshold; output is WAIT signal |
| 0.50 – 0.69 | Moderate confidence; directional signal issued with caution |
| 0.70 – 0.89 | High confidence; directional signal issued |
| 0.90 – 1.00 | Very high confidence; strong directional signal |

Default confidence threshold: 0.70 (configurable via YAMLReference).

------------------------------------------------------------------------

## Risk Level

| Level | Definition |
|-------|-----------|
| LOW | Signals are aligned and conditions are clear |
| MEDIUM | Some signals are conflicting or market is transitioning |
| HIGH | Signals are contradictory or insufficient data exists |

------------------------------------------------------------------------

## Input Sources

The AI Analysis Pipeline consumes outputs from the following modules:

| Input | Source Module |
|-------|--------------|
| CVD direction and slope | CVD Module |
| Footprint delta | Footprint Module |
| Imbalance events | Imbalance Module |
| Absorption events | Absorption Module |
| Signal and confidence | Signal Engine |

------------------------------------------------------------------------

## Output Contract

| Field | Type | Description |
|-------|------|-------------|
| analysis_time | TIMESTAMP | UTC time of analysis execution |
| market_state | ENUM(MarketState) | Classified market condition |
| confidence | DECIMAL(0.0–1.0) | Confidence in the assessment |
| risk_level | ENUM(LOW/MEDIUM/HIGH) | Current risk classification |
| summary | STRING | Human-readable market description |
| reason | LIST[STRING] | Contributing signals and conditions |

------------------------------------------------------------------------

## Processing Rules

-   v3.0 uses deterministic rule-based evaluation only.
-   All inputs must be available before evaluation begins.
-   Outputs from identical inputs shall always be identical.
-   Future LLM integration shall conform to this same output contract.
-   Confidence below threshold results in NEUTRAL state and WAIT signal.

------------------------------------------------------------------------

## Reference Rules

-   This document is the SSOT for AI Analysis Pipeline terminology.
-   AIAnalysis_v3.0.md (module spec) shall reference these definitions.
-   EnumDefinitions_v3.0.md holds the MarketState and SignalType enumerations.
-   JSONSchema_v3.0.md defines the serialized output structure.

Status: Phase4 Reference Enhancement
