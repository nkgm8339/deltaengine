# DeltaEngine Hook／旧ストラテジー・パターン棚卸し

作成日: 2026-07-27 JST  
種別: 現物CSVの一覧化（コード変更なし）

## 1. 正本と実測件数

| 対象 | 正本ファイル | 件数 |
|---|---|---:|
| Hook capability | `ORDER_FLOW_HOOK_PREDICATE_CAPABILITY_REGISTRY_V0_1_20260727.csv` | 88 |
| Strategy family | `ORDER_FLOW_STRATEGY_NAME_REGISTRY_V0_1_20260727.csv` | 10 |
| World named pattern | `ORDER_FLOW_WORLD_NAMED_PATTERN_REGISTRY_V0_1_20260727.csv` | 50 |
| World pattern FSM edge | `ORDER_FLOW_WORLD_NAMED_PATTERN_FSM_V0_1_20260727.csv` | 406 |
| Derived named-pattern variant | `ORDER_FLOW_DERIVED_NAMED_PATTERN_VARIANTS_V0_1_20260727.csv` | 365 |
| Variant-state binding | `ORDER_FLOW_VARIANT_STATE_CONDITION_BINDINGS_V0_1_20260727.csv` | 3,336 |

Hookカテゴリ内訳はA=24、B=20、C=9、D=8、E=6、F=5、G=12、H=4。Hook 88件は全件 `UNVALIDATED` である。

## 2. 全Hook一覧

### Category A（24）

- A01 `large_bid_wall_appeared`
- A02 `large_ask_wall_appeared`
- A03 `bid_wall_pulled`
- A04 `ask_wall_pulled`
- A05 `bid_depth_thinned`
- A06 `ask_depth_thinned`
- A07 `bid_depth_strengthened`
- A08 `ask_depth_strengthened`
- A09 `book_asymmetry_bid`
- A10 `book_asymmetry_ask`
- A11 `best_bid_retreat`
- A12 `best_ask_retreat`
- A13 `best_bid_advance`
- A14 `best_ask_advance`
- A15 `spread_expansion`
- A16 `spread_recovery`
- A17 `bid_iceberg_suspected`
- A18 `ask_iceberg_suspected`
- A19 `bid_spoofing_suspected`
- A20 `ask_spoofing_suspected`
- A21 `upside_vacuum`
- A22 `downside_vacuum`
- A23 `bid_wall_tracks_up`
- A24 `ask_wall_tracks_down`

### Category B（20）

- B01 `consecutive_market_buys`
- B02 `consecutive_market_sells`
- B03 `buy_aggression`
- B04 `sell_aggression`
- B05 `trade_speed_spike`
- B06 `trade_pause`
- B07 `large_market_buy`
- B08 `large_market_sell`
- B09 `large_buy_cluster`
- B10 `large_sell_cluster`
- B11 `buy_sweep`
- B12 `sell_sweep`
- B13 `average_trade_size_spike`
- B14 `small_trade_burst`
- B15 `buy_delta_spike`
- B16 `sell_delta_spike`
- B17 `delta_flip_buy_to_sell`
- B18 `delta_flip_sell_to_buy`
- B19 `directional_persistence`
- B20 `high_volume_neutral_delta`

### Category C（9）

- C01 `buy_absorption`
- C02 `sell_absorption`
- C03 `buy_absorption_failed`
- C04 `sell_absorption_failed`
- C05 `repeated_absorption`
- C06 `wall_collision_started`
- C07 `ask_wall_consumed`
- C08 `bid_wall_consumed`
- C09 `liquidation_absorbed`

### Category D（8）

- D01 `buy_effective_transition`
- D02 `sell_effective_transition`
- D03 `buy_trapped_transition`
- D04 `sell_trapped_transition`
- D05 `stalled_transition`
- D06 `effective_to_trapped_fast`
- D07 `trapped_resolved`
- D08 `multi_window_alignment`

### Category E（6）

- E01 `large_long_liquidation`
- E02 `large_short_liquidation`
- E03 `long_liquidation_cascade`
- E04 `short_liquidation_cascade`
- E05 `liquidation_no_price_response`
- E06 `liquidation_exhaustion`

### Category F（5）

- F01 `oi_up_price_up`
- F02 `oi_up_price_down`
- F03 `oi_down_price_up`
- F04 `oi_down_price_down`
- F05 `oi_shock`

### Category G（12）

- G01 `recent_high_touch`
- G02 `recent_low_touch`
- G03 `high_break`
- G04 `low_break`
- G05 `failed_high_break`
- G06 `failed_low_break`
- G07 `vwap_touch`
- G08 `vwap_deviation_extreme`
- G09 `volume_node_touch`
- G10 `round_number_touch`
- G11 `range_edge`
- G12 `higher_timeframe_direction`

### Category H（4）

- H01 `session_context`
- H02 `high_volatility_context`
- H03 `low_liquidity_context`
- H04 `hfm_spread_normal`

## 3. 旧ストラテジー family

| family ID | 名称 | primary basis | pattern数 |
|---|---|---|---:|
| `STR-CVD-DIVERGENCE` | CVD Divergence | price_vs_cvd_divergence | 5 |
| `STR-ABSORPTION-REVERSAL` | Absorption Reversal | absorption_then_reversal | 5 |
| `STR-EXHAUSTION-REVERSAL` | Exhaustion Reversal | buyer_or_seller_exhaustion | 5 |
| `STR-STACKED-IMBALANCE-CONTINUATION` | Stacked Imbalance Continuation | stacked_imbalance_continuation | 5 |
| `STR-ICEBERG-BREAKOUT` | Iceberg Breakout | iceberg_depletion_breakout | 5 |
| `STR-LIQUIDITY-SWEEP` | Liquidity Sweep | stop_sweep_then_reversal | 5 |
| `STR-FAILED-AUCTION` | Failed Auction | auction_failure_then_reversal | 5 |
| `STR-PULLING-STACKING` | Pulling / Stacking Strategy | book_pull_stack_dynamics | 5 |
| `STR-DELTA-FLIP` | Delta Flip | delta_sign_or_control_flip | 5 |
| `STR-BOOK-IMBALANCE` | Book Imbalance | order_book_imbalance_follow_or_fade | 5 |

全10 familyのcanonical statusは `USER_CANONICAL`。

## 4. 旧named pattern（50件）

### CVD Divergence

- `PAT-CVD-EXTREME-NONCONFIRM-FLIP-001` — New Extreme / Aggressor Flip
- `PAT-CVD-ABSORPTION-STRUCTUREBREAK-001` — Absorption / Structure Break
- `PAT-CVD-FAILED-BREAK-SQUEEZE-001` — Failed Break / Squeeze
- `PAT-CVD-RETEST-WEAKER-001` — Retest / Weaker Aggressor
- `PAT-CVD-BEAR-ABSFAIL-BIDBREAK-OIUNWIND-001` — Bearish / Absorption Failure / Buy-Wall Break / OI Unwind

### Absorption Reversal

- `PAT-ABS-FULL-THREE-ELEMENT-001` — Absorption / Fade / Opposite Aggression
- `PAT-ABS-SUPPORT-HOLD-BOUNCE-001` — Support Hold / Sell Absorption / Bounce
- `PAT-ABS-RESISTANCE-HOLD-BOUNCE-001` — Resistance Hold / Buy Absorption / Rejection
- `PAT-ABS-STOPSWEEP-SNAPBACK-001` — Stop Sweep / Iceberg Hold / Snapback
- `PAT-ABS-PULLBACK-MINORREVERSAL-001` — Pullback End / Trend Resume

### Exhaustion Reversal

- `PAT-EXH-BUYER-DOUBLE-FADE-001` — Buyer Fade / Weaker Retest
- `PAT-EXH-SELLER-DOUBLE-FADE-001` — Seller Fade / Weaker Retest
- `PAT-EXH-AGGRESSION-NO-FOLLOW-001` — Aggressive Burst / No Follow-Through
- `PAT-EXH-EFFORT-RESULT-001` — High Effort / Narrow Result
- `PAT-EXH-LIQUIDATION-CASCADE-END-001` — Liquidation Cascade / Organic Flow Failure

### Stacked Imbalance Continuation

- `PAT-STACK-BUY-SUPPORT-RETEST-001` — Buy Stack / Support Retest
- `PAT-STACK-SELL-RESIST-RETEST-001` — Sell Stack / Resistance Retest
- `PAT-STACK-RANGE-POC-SHIFT-001` — Range Exit / POC Shift
- `PAT-STACK-PULLBACK-HOLD-REACCEL-001` — Trend Pullback / Zone Hold / Re-acceleration
- `PAT-STACK-PERSISTENCE-PROGRESS-001` — Multi-Unit Persistence / Price Progress

### Iceberg Breakout

- `PAT-ICE-BARRIER-DEPLETE-BREAK-001` — Repeated Refill / Barrier Depletion / Break
- `PAT-ICE-HIDDEN-ACCUM-BUYBREAK-001` — Hidden Accumulation / Buyer Initiative
- `PAT-ICE-HIDDEN-DISTRIB-SELLBREAK-001` — Hidden Distribution / Seller Initiative
- `PAT-ICE-SECOND-ATTEMPT-DEPLETION-001` — Second Attempt / Absorber Exhaustion
- `PAT-ICE-BREAK-STOPS-ACCEPT-001` — Wall Break / Stops / New-Level Acceptance

### Liquidity Sweep

- `PAT-SWEEP-HIGH-ABSORB-SNAPBACK-001` — High Stop Run / Sell Absorption / Snapback
- `PAT-SWEEP-LOW-ABSORB-SNAPBACK-001` — Low Stop Run / Buy Absorption / Snapback
- `PAT-SWEEP-ICEBERG-DRYUP-001` — Stops into Iceberg / Aggressor Dry-Up
- `PAT-SWEEP-QUICK-RETURN-TRAP-001` — Quick Range Return / Trapped Traders
- `PAT-SWEEP-FRONTRUN-LIQUIDITY-TARGET-001` — Sell Stops / Front-Run Absorption / Offer Target

### Failed Auction

- `PAT-FA-RANGE-BREAK-RETURN-001` — Range Break / No Follow-Through / Return
- `PAT-FA-EXTREME-HVN-FLICKBACK-001` — Extreme Break / Outside HVN / Flickback
- `PAT-FA-TAIL-RANGE-FAILED-CONTINUE-001` — Tail / Tight Range / Continuation Failure
- `PAT-FA-UNFINISHED-DRYUP-REVERSAL-001` — Unfinished Extreme / Aggressor Dry-Up / Reversal
- `PAT-FA-EVENT-NO-VALUE-MIGRATION-001` — Event Breakout / No Value Migration / Old-Range Return

### Pulling / Stacking

- `PAT-PS-BID-PULL-ASK-STACK-001` — Bid Pull / Ask Stack / Seller Control
- `PAT-PS-ASK-PULL-BID-STACK-001` — Ask Pull / Bid Stack / Buyer Control
- `PAT-PS-WALL-PULL-FRAGILITY-001` — Apparent Wall / Pull-on-Approach / Fragility
- `PAT-PS-BEHIND-PRICE-STACK-RETEST-001` — Liquidity Behind Price / Retest Hold
- `PAT-PS-ABSORB-THEN-PULL-CUTREVERSE-001` — Churn and Absorption / Protecting Wall Pull / Cut-and-Reverse

### Delta Flip

- `PAT-DF-POSITIVE-TAIL-SELLCONTROL-001` — Positive Delta Tail / Seller Control
- `PAT-DF-NEGATIVE-TAIL-BUYCONTROL-001` — Negative Delta Tail / Buyer Control
- `PAT-DF-NEGABS-NOLOW-POSFLIP-001` — Negative Delta Absorbed / No Lower Low / Positive Flip
- `PAT-DF-SAMESIDE-DISAPPEAR-OPPOSITE-001` — Same-Side Imbalance Disappears / Opposite Delta
- `PAT-DF-POSTEVENT-LIQUIDITY-REALIGN-001` — Post-Event / Liquidity Reform / Directional Realignment

### Book Imbalance

- `PAT-BI-BID-PERSIST-BUYCONFIRM-001` — Persistent Bid Skew / Buy-Flow Confirmation
- `PAT-BI-ASK-PERSIST-SELLCONFIRM-001` — Persistent Ask Skew / Sell-Flow Confirmation
- `PAT-BI-SKEW-NORESULT-FADE-001` — One-Sided Skew / No Price Result / Fade
- `PAT-BI-PULL-REVERSAL-CONFIRM-001` — Skew Pull / Opposite Rebuild / Reversal
- `PAT-BI-DEEP-STACK-TOPSHIFT-001` — Deep Stack / Top-Book Shift / Aggressor Alignment

## 5. 現在の意味

- Hook 88件、named pattern 50件、derived variant 365件はカタログ／観測候補である。
- 全Hook・pattern・variantは `UNVALIDATED`。runtime有効化0、直接発注権限0。
- Hookは起点を作る観測イベントであり、単独でENTRYや発注判断を意味しない。
- Strategy EngineはpatternのFSM edge（ADVANCE／TERMINAL／INVALIDATE／EXPIRE）を前提に、後続証拠を段階評価する。

## 6. 参照元

- `ORDER_FLOW_HOOK_PREDICATE_CAPABILITY_REGISTRY_V0_1_20260727.csv`
- `ORDER_FLOW_HOOK_STRATEGY_CONDITION_ROUTING_V0_1_20260727.csv`
- `ORDER_FLOW_STRATEGY_NAME_REGISTRY_V0_1_20260727.csv`
- `ORDER_FLOW_WORLD_NAMED_PATTERN_REGISTRY_V0_1_20260727.csv`
- `ORDER_FLOW_WORLD_NAMED_PATTERN_FSM_V0_1_20260727.csv`
- `ORDER_FLOW_DERIVED_NAMED_PATTERN_VARIANTS_V0_1_20260727.csv`
- `ORDER_FLOW_VARIANT_STATE_CONDITION_BINDINGS_V0_1_20260727.csv`
