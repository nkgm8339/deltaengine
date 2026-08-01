# LIVE DOM → Time & Sales price link — 2026-08-01

- Clicking a LIVE DOM price row now finds the latest Time & Sales trade at the same price.
- The matching T&S row is selected, rendered with the existing highlight style, and scrolled into view.
- If no matching trade is retained, the T&S panel reports `NO TAPE AT <price>`.

Verification: heatmap core + frame-budget tests **11 passed**.
