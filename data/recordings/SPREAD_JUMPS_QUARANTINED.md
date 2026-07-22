# Spread-jump outputs — research quarantine

Status: **DO NOT USE FOR RESEARCH**

Quarantined: 2026-07-22 JST

## Affected files

- btcusdt_session1.jsonl
- btcusdt_session1_clean.jsonl
- btcusdt_session1_clean_strong.jsonl
- spread_jumps.jsonl
- spread_jumps.csv

The files are preserved for provenance. They have not been deleted or silently
rewritten.

## Audit evidence

- All three session recordings contain 2,939 depthUpdate rows and zero
  depthSnapshot rows.
- Binance depthUpdate rows are incremental changes, not complete order books.
- clean_strong contains no quantity-zero levels. Quantity zero is the
  delete-level instruction, so removing it makes state replay incomplete.
- Bid levels in every recorded row are ascending by price.
- The retired exporter sliced the first five bid entries before choosing the
  maximum. It therefore selected distant low-price changes as best bid.
- Observed example: the retired calculation produced a spread near 50,100,
  while max(all bids) and min(all asks) in the same row differed by 0.1. Even
  that 0.1 is not certified as the historical spread because the row is only a
  diff.

The ten existing spread-jump rows were produced by this invalid method.

Preserved SHA-256 values at quarantine time:

- spread_jumps.jsonl:
  D6D9C73D034041B0357F86B34AD8CE9F837F70D1DD08C785DEC5865D42AF2531
- spread_jumps.csv:
  1CCD8543B0C114A2AC46B18B8799B66D9ECE3A0B6432BBB5288F24EDCA1F2743

## Valid replacement boundary

A replacement recording must contain a depthSnapshot and retain all subsequent
depthUpdate rows, including quantity-zero deletes. Sequence gaps invalidate
states until another snapshot appears. Only reconstructed, synchronized,
non-crossed states may be used to calculate spread.
