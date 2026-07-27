"""Strategy Engine body skeleton (representative variant only).

This package is the Strategy Engine *body* skeleton. It does NOT replace the
contract enforcer in ``src/strategy_contract/`` -- that layer stays the test
reference/oracle for the transition contracts (judgement contracts 1-9, R1-R8).

The Engine here composes the enforcer as its transition gate: it adds only
(1) a Predicate Evaluator and (2) a source-agnostic event ingestion layer, then
delegates every accept/reject decision to ``ContractEnforcer``. Because the
enforcer is the single source of truth for the contract, the Engine cannot
violate it.

Invariants preserved by construction:
- runtime enablement 0: no connection to the live pipeline, Hook runtime,
  recording base, or order path.
- order authority 0: TERMINAL produces only an OrderReadyHandoff via the
  enforcer; there is no order-send API here.
- thresholds are never hardcoded: calibration comes from a CalibrationBook that
  is empty (UNVALIDATED) by default, so normal operation cannot fire.
"""
