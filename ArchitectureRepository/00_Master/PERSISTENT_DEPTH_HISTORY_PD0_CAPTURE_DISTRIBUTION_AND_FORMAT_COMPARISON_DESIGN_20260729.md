# Persistent Depth History GO-PD0 design

作成: 2026-07-29  
承認: user `GO-PD0`  
Status: **DESIGN／measurement harness未実装／production未接続**

## 1. Objective

同一のvalidated `BOOK_UPDATE` captureを入力として、capture分布を把握し、JSONL＋ZSTD、compact binary＋ZSTD、periodic keyframe＋diff＋ZSTDの保存候補を公平に比較できるmeasurement protocolを固定する。

30分LIVE sizingで得た10,123 frames／5.6048 frames/s／99.87 levels per frame／約3,939 JSON bytes per frameはbaselineである。ただしsymbol、sync state、level count、payload size、gap、restartの分布は未取得であり、production formatの根拠としては不十分である。

## 2. Capture envelope

Each fixture record retains the original payload bytes plus an envelope:

```json
{"capture_id":"uuid","symbol":"BTCUSDT","received_at":"UTC ISO","payload":{...}}
```

Required distribution fields:

- frame count／duration／frames per second
- payload bytes raw／UTF-8 JSON
- bid count、ask count、total level count
- quantity and price string lengths
- sync_state counts
- stream ID count and segment duration
- sequence gap／duplicate／out-of-order counts
- fail-closed duration and recovery latency
- `last_update_id` delta distribution

Capture must be append-only, checksumed, and treated read-only by all candidate encoders. No live payload may be synthesized from candles, Footprint, or current book state.

## 3. Required capture strata

Collect at least these independent strata before format selection:

1. normal SYNCED period, 30 minutes minimum
2. high-cadence／high-level period, 10 minutes minimum
3. fail-closed／recovery period, including one complete gap if naturally observed
4. stream restart boundary, using an isolated replay fixture if live restart is not observed
5. representative symbols／sessions where permitted by the same contract

Synthetic fixtures may exercise error paths, but may not be used to claim production byte rates.

## 4. Candidate encoders

### A. JSONL + ZSTD

Baseline for auditability. Preserve exact payload JSON and envelope. Measure compression levels 1／3／6 independently.

### B. Compact binary + ZSTD

Typed fields for time／sequence／price／quantity with decimal string preservation metadata. Must round-trip exact source values; any lossy numeric conversion is a failure.

### C. Keyframe + diff + ZSTD

Periodic full keyframe followed by ordered add／update／delete diffs. Measure keyframe intervals 1s／5s／30s／60s. A diff stream is invalid until its keyframe and all sequence predecessors are present.

## 5. Fair benchmark protocol

For every capture／candidate combination, record:

- raw bytes, compressed bytes, compression ratio
- encode throughput and CPU time
- append latency p50／p95／p99
- flush／fsync latency p50／p95／p99
- crash recovery scan time
- random UTC range hydration latency p50／p95／p99
- full-day projection with confidence interval
- peak resident memory and temporary disk usage

Use the same host, Python version, ZSTD library, compression level, filesystem, and capture ordering. Warm and cold cache runs are separate. Report decimal bytes and binary MiB/GiB distinctly.

## 6. Correctness gates

- exact payload／decimal value round-trip
- sequence and stream boundary preservation
- gap／restart marker preservation
- no silent record drop or reorder
- truncated tail detected and bounded recovery
- manifest checksum mismatch fails closed
- replay never mixes live source or invents absent depth
- candidate reader can identify unsupported schema revision

Any candidate failing correctness is excluded regardless of compression ratio.

## 7. Decision output

The PD0 result must produce:

- `capture_distribution.csv`
- `candidate_benchmark.csv`
- `candidate_correctness.jsonl`
- a recommendation with observed assumptions and confidence limits
- a proposed PD1 isolated prototype scope

No production retention period, purge policy, schema migration, or writer enablement is selected by PD0.

## 8. Checkpoint and rollback

PD0 artifacts must live outside production data paths. The measurement harness must be removable without touching DuckDB／Parquet／raw market data. The next gate is GO-PD1 for an isolated writer／format prototype only.
