# Persistent depth history sizing report

測定完了: 2026-07-29 07:38 JST  
承認範囲: 30-minute LIVE sizing only  
判定: **MEASUREMENT PASS／実装・永続化未承認**

## Observed

| metric | result |
|---|---:|
| elapsed | 1,806.13 s |
| BOOK_UPDATE frames | 10,123 |
| cadence | 5.6048 frames/s |
| payload JSON bytes | 39,864,556 bytes |
| average payload | 約3,939 bytes/frame |
| total bid＋ask levels | 1,011,000 |
| average levels/frame | 99.87 |
| first／last book sequence | 9,033／19,155 |
| WebSocket errors | 0 |
| health samples | 60 |
| health errors | 0 |
| health yellow | 2（latency） |

## Capacity projection

Observed JSON transport volume is approximately **79.46 MB/hour** (decimal), or **1.907 GB/day**, before database／index／compression overhead. This is a transport upper-bound approximation, not a storage design estimate.

The sample received roughly 100 levels per frame at 5.6 frames/s. Any persistence design must separately measure raw snapshot, diff encoding, keyframe cadence, compression, metadata/index overhead, writer CPU/I/O, and hydration latency. The current result does not authorize a schema, writer, archive, retention, or automatic purge.

## Health context

All 60 health polls completed without error. Book gap and reconnect remained GREEN; two transient latency-YELLOW observations were recorded. No source or runtime state was changed during sizing.

## Next decision boundary

Create a separate persistent-depth-history implementation instruction from these measurements. Do not begin source implementation until the user gives a new explicit GO for that instruction.
