# Binance × HFM latency observer

This is an observation-only tool. It never sends, changes, or cancels an order,
and it is independent from Flow Price Response and the three-panel chart.

## 1. Start the collector

From `Delta_Engine_Pro4web`:

```powershell
python -m tools.observe_hfm_binance
```

It records Binance USD-M Futures `BTCUSDT@bookTicker` and reads HFM quotes from
MT5's shared `FILE_COMMON` folder. Raw data is appended to
`data/latency/quotes.csv`.

The HFM file is checked every 10 ms. CSV writes use one ordered background
worker and are flushed in batches, so Binance disk writes do not block HFM
reading on the asyncio loop. A bounded queue fails explicitly on overload.

For a fixed-duration audit and a fresh seven-column file:

```powershell
python -m tools.observe_hfm_binance --duration-sec 120 --output data/latency/quotes_audit.csv
```

## 2. Attach the MT5 observer

1. Copy `mt5/HFMQuoteObserver.mq5` into the MT5 data folder under
   `MQL5/Experts/DeltaEngine/`.
2. Compile it in MetaEditor.
3. Open the HFM BTC chart that will actually be traded.
4. Attach `HFMQuoteObserver` to that chart and allow algorithmic trading.

The EA contains no trade functions. It writes symbol, server time, quote
sequence, Bid and Ask to `DeltaEngine_HFM_quotes_utf8.jsonl` in MT5's common
files folder. It keeps the shared file handle open while attached and closes it
on deinitialization. The selected chart symbol is detected automatically. No
socket, DLL or WebRequest permission is required.

## 3. Produce a report

After collecting data, stop with Ctrl+C and run:

```powershell
python -m tools.report_hfm_binance
```

The console report and `data/latency/report.json` contain:

- HFM-minus-Binance mid-price basis;
- LONG-side Ask difference and SHORT-side Bid difference;
- each venue's own Bid/Ask spread;
- price-move event latency (median, p95, p99, maximum and match rate);
- cross-correlation lead/lag using 250 ms return buckets;
- executable HFM outcomes after a Binance move (LONG Ask-to-Bid and SHORT
  Bid-to-Ask, with the displayed spread already included);
- one-second return correlation;
- 1-, 3-, and 5-minute OHLC differences, direction agreement, HFM candle range,
  and spread-to-range ratio.

Positive latency means HFM moved after Binance. Negative latency means the
nearest matching HFM move occurred first. The default event is a 1 bp mid-price
move and the matching window is five seconds; both are configurable:

```powershell
python -m tools.report_hfm_binance --move-bps 2 --match-window-ms 10000
```

The executable outcome section assumes a one-second manual decision delay by
default. Compare a slower manual reaction explicitly when needed:

```powershell
python -m tools.report_hfm_binance --entry-delay-ms 3000
```

## Interpretation limits

- Both feeds receive a timestamp from the same Python process. This measures
  observed arrival and cross-market response, not internet RTT by itself.
- HFM's server timestamp is retained for audit but is not used as the common
  clock.
- A displayed Bid/Ask is not proof that a market order would fill there. Actual
  fill/slippage measurement belongs to a later, separately authorized phase.
- Do not combine the result into an automatic trading score. Compare normal and
  volatile sessions before judging whether a timeframe is usable.

## DeltaEngine internal delivery audit

Use exact Binance individual trade IDs to compare a direct Binance connection
with DeltaEngine's local WebSocket:

```powershell
python -m tools.measure_binance_to_ui --duration-sec 120
```

After the 2026-07-23 live-path brush-up, a 120-second audit measured TICK
internal latency at 6.17 ms median / 63.63 ms p95 and BAR_UPDATE at 7.02 ms
median / 40.13 ms p95. This is separate from Binance-to-HFM market response.

The improved HFM bridge recorded 627 sequential quotes with no missing,
reset, or reversed sequence. Its clock-offset-independent p95/p99 receive
jitter fell from 29.8/48.8 ms to 12.3/18.4 ms. The remaining several-hundred
millisecond Binance-to-HFM response must not be attributed to DeltaEngine's
internal path.

## Multi-venue execution-cost observation

The separate GO-1 collector compares executable public Bid/Ask quotes without
touching Flow Price Response, the three-panel chart, or any trading function:

```powershell
python -m tools.observe_execution_costs --duration-sec 86400
```

It records Binance Futures as a sensor, HFM from local MT5 files, bitFlyer
Crypto CFD (`FX_BTC_JPY`), and GMO Coin leverage (`BTC_JPY`) on one local
arrival clock. Raw quotes, a ten-second health file, and the final report are
written under `data/execution_costs/`. The final report is generated
automatically after the requested duration.

JPY and USD price levels are never subtracted. Each venue's own spread is
normalized to basis points; JPY venues are compared with Binance through an
implied JPY-per-USDT ratio so combined FX/local-basis drift remains visible.
Configured fees are in `config/execution_costs.yaml`; account-specific and
time-dependent holding charges remain explicitly uncounted until verified.

For a second HFM InfinityX terminal, attach the existing observation-only EA
with this input value:

```text
QuoteFileName=DeltaEngine_HFM_InfinityX_quotes_utf8.jsonl
```

Until that file exists, the health report shows `HFM_INFINITYX` as waiting and
does not substitute an advertised spread for a measured quote.
