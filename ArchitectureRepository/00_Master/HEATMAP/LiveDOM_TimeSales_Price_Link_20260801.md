# LIVE DOM → Time & Sales price link — 2026-08-01

- Clicking a LIVE DOM price row now keeps that price as a visual reference.
- All currently retained T&S rows at that price are highlighted, and new matching rows are highlighted as they arrive.
- If no matching trade is retained, the T&S panel reports `NO TAPE AT <price>`.
- DOM-linked rows use a distinct cyan border/background (`#23DFFF`), separate from BUY/SELL colors and ordinary white selection.

Verification: heatmap core + frame-budget tests **11 passed**.
