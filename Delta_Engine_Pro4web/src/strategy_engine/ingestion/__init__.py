"""Ingestion adapter: normalized market state -> Tier A condition snapshot.

This subpackage maps a source-agnostic, read-only ``MarketStateSnapshot`` into the
Tier A condition keys (single-stream, window-derived) that the representative
variant needs. It does not touch existing detectors, connect to Live, or hold any
threshold (thresholds live only in the CalibrationBook).

Tier B STRATEGY_SPECIFIC composite FLAGs (divergence_active, absorption_like_active,
breakout_*, passive_defense_*) are out of scope and remain a documented gap; a
future composite synthesis layer will produce them. Every representative-variant
class also has a Tier A candidate route, so Tier A alone drives the variant
end-to-end while contradiction (Tier B) keys are simply absent (fail-closed).
"""
