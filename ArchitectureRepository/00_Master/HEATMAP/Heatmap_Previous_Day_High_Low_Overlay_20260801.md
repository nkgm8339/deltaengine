# Previous-day high/low overlay — 2026-08-01

- Reused `/api/history/candles?timeframe=1d` to load recent daily candles.
- Added `PDH` (previous-day high) and `PDL` (previous-day low) dashed horizontal lines to the heatmap.
- Lines are drawn only when valid daily OHLC data is available; the existing heatmap and current-price lines are unchanged.

Verification: heatmap core + frame-budget tests **11 passed**.
