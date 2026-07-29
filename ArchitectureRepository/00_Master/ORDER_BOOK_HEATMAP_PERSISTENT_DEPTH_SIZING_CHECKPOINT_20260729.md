# Persistent depth history sizing checkpoint

開始: 2026-07-29 07:08 JST  
承認: user option 2 — 30-minute LIVE sizing only

Scope: read-only observation of the operational Heatmap backend. No database schema, writer, archive, or replay changes are authorized by this checkpoint.

Planned measurements:

- Book update cadence／accepted frame count
- JSON payload byte approximation and level distribution
- health state, gap／reconnect, latency, CPU／memory
- projected raw／diff bytes per hour and per day

Status: measurement pending／in progress. Next resume point is the 30-minute collector completion and sizing report.

## Completion: 2026-07-29 07:38 JST

- elapsed 1,806.13s; 10,123 BOOK_UPDATE frames; 5.6048 frames/s
- JSON transport 39,864,556 bytes; approximately 79.46MB/hour／1.907GB/day decimal
- average 99.87 bid＋ask levels/frame; first／last sequence 9033／19155
- WebSocket errors 0; health samples 60; health errors 0; latency-YELLOW 2
- no source, schema, writer, archive, retention, or runtime changes during sizing
- report: `ORDER_BOOK_HEATMAP_PERSISTENT_DEPTH_SIZING_REPORT_20260729.md`

Next resume position: write a separate persistent-depth-history implementation instruction; await a new explicit GO before source changes.
