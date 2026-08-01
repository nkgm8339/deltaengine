# LIVE DOM → Time & Sales price link — 2026-08-01

- Clicking a LIVE DOM price row now finds the latest Time & Sales trade at the same price.
- The matching T&S row is selected, rendered with the existing highlight style, and scrolled into view.
- If no matching trade is retained, the T&S panel reports `NO TAPE AT <price>`.
- DOM-linked rows use a distinct cyan border/background (`#23DFFF`), separate from BUY/SELL colors and ordinary white selection.

Verification: heatmap core + frame-budget tests **11 passed**.
