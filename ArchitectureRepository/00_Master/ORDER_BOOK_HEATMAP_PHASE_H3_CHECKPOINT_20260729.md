# Order Book Heatmap GO-H3 checkpoint

更新: 2026-07-29 06:34 JST  
承認: user `GO` interpreted as next-stage GO-H3

## 完了

- central `FOOTPRINT | HEATMAP` mode controls added.
- Heatmap canvas/status layer added without replacing Footprint DOM or Canvas.
- `ORDER_BOOK_HEATMAP_ENABLED = false` keeps default FOOTPRINT and disables Heatmap interaction/ingest.
- When enabled, BOOK_UPDATE frames are passed to the H2 store and rendered on the Heatmap canvas; no UI enablement or runtime activation was performed.
- Existing Footprint／Tape／3-stage chart contracts remain intact.

## Verification

- inline browser script syntax: PASS
- H3 UI + H2 core + existing Footprint/Tape UI contracts: **15 passed**
- Full WebApp regression remains limited by existing pytest temp-root Permission denied (previously 111 passed／15 setup errors).

## 未完了／次の再開位置

GO-H4 (Tape linkage／gap visualization) is not started. Runtime deployment and operational flag enablement remain out of scope. Rollback is the additive `orderbook_heatmap.js` and central mode markup/script only; do not revert completed Footprint/Tape/3-stage chart.
