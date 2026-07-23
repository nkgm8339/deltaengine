# ADR-009 — Divergence Module

**Status**: Accepted  
**Version**: v3.0

---

# Context

Price/CVD divergence needs a deterministic contract before it can be evaluated as a trading feature. The approved design review requires it to be isolated from existing signal scoring until out-of-sample performance is established.

# Decisions

1. Add Divergence as independent module MOD-012.
2. Separate detection from quality evaluation. Phase 0 implements only `CvdDivergenceDetector` and immutable `DivergenceEvent`.
3. Do not mix divergence into SignalEngine weights until out-of-sample superiority is confirmed. Phase 0 uses shadow-mode display wiring only.
4. Canonical persistence schemas `divergence_events` and `divergence_outcomes` are deferred to Phase 1.
5. Use the deterministic three-Candle pivot confirmation rule, `first` equal-pivot policy, bounded detector state, Decimal arithmetic, and counted/logged input rejection.

# Consequences

The live and replay pipelines retain a latest display event without changing SignalEngine behavior or storage schemas. Future evaluation can consume a stable event contract, while the known freshness policy for the latest display event remains deferred to Phase 1.

# References

- `00_Master/Reports/Divergence_Design_Review_v1_Complete.md`
- Divergence
- CVD
- ADR-002_Module_Communication
