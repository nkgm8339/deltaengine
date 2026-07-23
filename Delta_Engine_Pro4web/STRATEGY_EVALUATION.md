# Cost-aware Flow strategy evaluation

This is an offline research tool. It does not import an exchange trading
client, send orders, or change Flow Price Response and the three-panel chart.

Run from `Delta_Engine_Pro4web`:

```powershell
python -m tools.evaluate_flow_strategies
```

The fixed configuration is `config/flow_strategy_evaluation.yaml`. Runtime
JSON and Markdown reports are written under `data/strategy_research/`.

## Causal rules

- `MODERATE_FLOW_CONTINUATION`: derives the central pressure-strength,
  persistence, and relative-volume ranges from the chronological training
  period without looking at returns. A future one-minute bar must retest the
  event price before a hypothetical passive entry is counted.
- `FAILED_AGGRESSION_REVERSAL`: requires a same-side five-minute EFFECTIVE
  event followed by STALLED/TRAPPED, a two-basis-point opposite close, and a
  later retest of that confirmed break price.

The fill bar is excluded from future-return calculation because intrabar event
ordering is unknown. Outcomes require at least 90% one-minute coverage, no gap
over three minutes, and an exact horizon exit bar. Positions are greedily
purged so their holding intervals do not overlap.

## Validation

The observation is divided chronologically. Strategy A feature ranges are
frozen on the first 60%; the last 40% starts after a one-hour embargo. Reports
show 15-, 30-, and 60-minute outcomes under 1.5bp, 3bp, and stressed 4.5bp
roundtrip costs. Every retained trade is included in the JSON ledger.

A positive mean from a small sample is not a pass. Deployment classification
requires the trade count, day count, bootstrap lower bound, cost stress, and
daily concentration limits declared in the configuration.
