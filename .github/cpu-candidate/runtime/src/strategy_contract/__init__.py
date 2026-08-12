"""Replay contract enforcer skeleton for named-variant Observation Instances.

This package is a *minimal contract-checking layer*, NOT the Strategy Engine.
It performs edge accept/reject decisions only, so that any future Strategy Engine
implementation that violates the design contracts (defined in the canonical policy
documents under ArchitectureRepository/00_Master/トリガー作成指示書群/) will fail
these replay contract tests immediately.

Invariants preserved by construction:
- runtime enablement 0: nothing here connects to the live pipeline, the Hook
  recording base, or config; the canonical CSVs are read-only.
- direct order authority 0: there is no order-send API anywhere in this package.
  A TERMINAL edge yields only an OrderReadyHandoff (LONG_READY / SHORT_READY)
  handed to a risk/execution gate (判定契約8).
"""
