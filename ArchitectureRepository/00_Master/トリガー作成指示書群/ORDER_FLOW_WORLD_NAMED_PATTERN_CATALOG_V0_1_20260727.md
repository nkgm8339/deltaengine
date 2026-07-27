# DeltaEngine World-Derived Named Observation Pattern Catalog v0.1

作成日: 2026-07-27 JST  
状態: **世界資料から抽出した初期named Pattern台帳。未較正、未検証、production未採用、発注許可ではない。**

## 0. 目的

Strategy Family名の下へ、観察する順序が異なるPatternを別名で登録する。後から「どのStrategyの、どのPatternが、どこまで遷移したか」をreplayと成績集計で識別できるようにする。

```text
Strategy Family
  -> named Pattern
       -> Observation Instance
            -> named State 1 -> named State 2 -> branch / invalidation / terminal
```

本版は**50 named Patterns、10 Family x 5件**で開始する。数を水増しするための無根拠な直積展開は行わない。方向、location、確認経路を展開した数百variantは、この原型と出典を失わない形で次版へ追加する。

## 1. Provenance契約

- `WORLD_DERIVED`: 外部資料が示す因果順序をDeltaEngineの観察stateへ正規化したもの。外部資料が同じPattern名やIDを使ったという意味ではない。
- `USER_DEFINED`: ユーザーが明示した観察順序。
- 一つのsourceが一つの完成売買ルールを保証したとは扱わない。複数sourceの共通要素を結合した場合はsource IDをすべて残す。
- sourceが示す現象名だけで、順序を示していないものはPattern根拠にしない。

## 2. Expiry class

| class | 失効境界 |
|---|---|
| `REACTION` | expected price／flow reactionが出ないまま局所flow regimeが変わる |
| `RETEST` | reference levelの再testがないままlocationまたはregimeが変わる |
| `BREAK_ACCEPT` | 対象range／wall／auctionの構造寿命内にbreakまたはacceptanceが出ない |
| `OI_LAGGED` | 必要なfresh OI sampleを待つ間に先行stateがstaleまたは反証される |
| `EVENT` | event impulse後の再均衡phaseを過ぎる、または別eventが開始する |

秒数やevent数は未較正であり、本版で利益thresholdを仮定しない。

## 3. Observability

- `DIRECT`: 現在のBinance trade／depth／price／delta／CVD等から直接観察可能。
- `HYBRID`: 直接eventと推定stateの両方が必要。
- `INFERRED`: native MBO identityがないため、replenishment、executed volume、price response等から推定する。
- `LIMITED`: 10秒poll OI等のsampling制約により高速遷移へそのまま使えない。

## 4. Source register

| source ID | 資料 |
|---|---|
| `S01` | [Jigsaw: Anatomy of a Reversal](https://www.jigsawtrading.com/blog/elements-of-a-reversal/) |
| `S02` | [Jigsaw: Reversals and Breakout Trades](https://www.jigsawtrading.com/blog/jigsaw-trading-order-flow-trade-reversals-breakout-trade/) |
| `S03` | [Jigsaw: Learning Pullbacks](https://www.jigsawtrading.com/blog/6-stages-of-order-flow-mastery-part-1/) |
| `S04` | [Jigsaw: DOM Setups](https://www.jigsawtrading.com/blog/which-dom-day-trading-setups-actually-work/) |
| `S05` | [Axia: Two Breakout Strategies](https://axiafutures.com/blog/two-breakout-strategies-for-futures-markets/) |
| `S06` | [Axia: Trapped Participants Reversal](https://axiafutures.com/blog/scalping-reversal-strategy-of-trapped-market-participants/) |
| `S07` | [Axia: Reversal and Continuation Scalps](https://axiafutures.com/blog/reversal-and-continuation-scalping-strategies/) |
| `S08` | [Axia: Volume Delta Reversal](https://axiafutures.com/blog/volume-delta-reversal-trade-strategy/) |
| `S09` | [Axia: Absorption and Breakout](https://axiafutures.com/blog/absorption-order-flow-eurostoxx/) |
| `S10` | [ATAS: Absorption](https://atas.net/blog/absorption-of-demand-and-supply-in-the-footprint-chart/) |
| `S11` | [ATAS: Imbalance Part 1](https://atas.net/blog/how-to-find-and-trade-imbalance/) |
| `S12` | [ATAS: Imbalance Part 2](https://atas.net/blog/imbalance/) |
| `S13` | [ATAS: How to Read Order Flow](https://atas.net/blog/how-to-read-the-order-flow/) |
| `S14` | [ATAS: Unfinished Auction](https://atas.net/blog/unfinished-auction-what-it-is-and-how-to-trade-it/) |
| `S15` | [ATAS: Open Interest](https://atas.net/blog/open-interest-how-to-use-it-in-trading/) |
| `S16` | [Bookmap: Key Order Flow Strategies](https://bookmap.com/en/blog/key-order-flow-strategies-breakouts-trends-trapped-traders-and-stop-runs) |
| `S17` | [Bookmap: Stops and Icebergs with MBO](https://bookmap.com/en/blog/stops-and-icebergs-how-to-detect-hidden-orders-using-mbo-data) |
| `S18` | [Bookmap: Stop Runs and Liquidity Traps](https://bookmap.com/blog/stop-runs-liquidity-traps-how-the-market-flushes-out-weak-hands) |
| `S19` | [Bookmap: Trend Reversal Phases](https://bookmap.com/blog/how-to-spot-trend-reversals-early-using-order-flow-analysis) |
| `S20` | [Bookmap: CVD and Iceberg Absorption](https://bookmap.com/blog/detecting-stop-runs-using-cvd-and-iceberg-absorption-for-strategic-trading) |
| `S21` | [Bookmap: Event Acceptance and Rejection](https://bookmap.com/blog/event-trading-in-2026-why-headline-speed-is-not-the-edge) |
| `S22` | [Bookmap: News Reaction Order Flow](https://bookmap.com/blog/trading-tariff-news-with-order-flow-reading-market-reactions-in-real-time) |
| `S23` | [Bookmap: Absorption Examples](https://bookmap.com/absorption/) |
| `S24` | [Bookmap: Liquidation Cascades](https://bookmap.com/blog/whos-actually-moving-the-crypto-market-spot-traders-vs-perps-vs-bots) |
| `S25` | [Bookmap: Order Book Imbalance](https://bookmap.com/blog/how-order-flow-imbalance-can-boost-your-trading-success) |
| `S26` | [Bookmap: Liquidity Tracker](https://bookmap.com/en/blog/liquidity-tracker-pro-see-whats-really-driving-price) |

## 5. Named Pattern catalog

### 5.1 CVD Divergence

| pattern ID | Pattern名 | ordered observation | terminal | invalidation | expiry | observability | provenance / source |
|---|---|---|---|---|---|---|---|
| `PAT-CVD-EXTREME-NONCONFIRM-FLIP-001` | **CVD Divergence / New Extreme / Aggressor Flip** | key level接近 -> priceだけ新極値 -> CVD不追随 -> initiator volume減衰 -> opposite aggression | reversal-side ready | CVD再整列かつ新価格acceptance | REACTION | DIRECT | WORLD_DERIVED `S13 S16` |
| `PAT-CVD-ABSORPTION-STRUCTUREBREAK-001` | **CVD Divergence / Absorption / Structure Break** | trendがliquidityへ到達 -> divergence -> aggression継続でもprice停止 -> absorption -> minor structureを反対向きにbreak | reversal-side ready | absorption level突破後にoutside hold | BREAK_ACCEPT | HYBRID | WORLD_DERIVED `S19 S20` |
| `PAT-CVD-FAILED-BREAK-SQUEEZE-001` | **CVD Divergence / Failed Break / Squeeze** | range break -> CVDがbreakと逆行 -> pullbackが深くなる -> higher-low／lower-high形成 -> wedgeをrange側へbreak | range復帰方向ready | CVDがbreak方向へ再整列しoutside hold | BREAK_ACCEPT | DIRECT | WORLD_DERIVED `S08` |
| `PAT-CVD-RETEST-WEAKER-001` | **CVD Divergence / Retest / Weaker Aggressor** | first extreme -> divergence -> 同価格再test -> initiator printがさらに減る -> opposite aggression | reversal-side ready | retestでinitiator activity回復し極値更新 | RETEST | DIRECT | WORLD_DERIVED `S01 S13` |
| `PAT-CVD-BEAR-ABSFAIL-BIDBREAK-OIUNWIND-001` | **CVD Divergence / Bearish / Absorption Failure / Buy-Wall Break / OI Unwind** | bearish divergence -> bid-side absorption -> buy wall崩壊 -> fresh OI減少 | SELL ready | bid wall再構築、price回復、またはOI不明／stale | OI_LAGGED | LIMITED | USER_DEFINED |

### 5.2 Absorption Reversal

| pattern ID | Pattern名 | ordered observation | terminal | invalidation | expiry | observability | provenance / source |
|---|---|---|---|---|---|---|---|
| `PAT-ABS-FULL-THREE-ELEMENT-001` | **Absorption Reversal / Absorption / Fade / Opposite Aggression** | key level -> initiator優勢だがprice停止 -> absorption -> initiator fade -> short pause -> opposite aggressor参加 | reversal-side ready | absorbed levelがbreakしoutside hold | REACTION | HYBRID | WORLD_DERIVED `S01` |
| `PAT-ABS-SUPPORT-HOLD-BOUNCE-001` | **Absorption Reversal / Support Hold / Sell Absorption / Bounce** | supportへsell aggression -> high volumeでも下抜けない -> passive buy吸収継続 -> sellers減衰 -> price上向き | BUY ready | support breakかつretestでresistance化 | REACTION | HYBRID | WORLD_DERIVED `S10 S20` |
| `PAT-ABS-RESISTANCE-HOLD-BOUNCE-001` | **Absorption Reversal / Resistance Hold / Buy Absorption / Rejection** | resistanceへbuy aggression -> high volumeでも上抜けない -> passive sell吸収継続 -> buyers減衰 -> price下向き | SELL ready | resistance breakかつretestでsupport化 | REACTION | HYBRID | WORLD_DERIVED `S10 S16` |
| `PAT-ABS-STOPSWEEP-SNAPBACK-001` | **Absorption Reversal / Stop Sweep / Iceberg Hold / Snapback** | stop zone接近 -> sweep／stop burst -> hidden／passive wallが吸収 -> follow-through欠如 -> level内へsnapback | reversal-side ready | sweep後にaggression継続しoutside acceptance | REACTION | INFERRED | WORLD_DERIVED `S17 S18` |
| `PAT-ABS-PULLBACK-MINORREVERSAL-001` | **Absorption Reversal / Pullback End / Trend Resume** | trend -> low-energy countertrend pullback -> prior swingでabsorption -> countertrend側fade -> with-trend aggressor復帰 | trend-side ready | pullback flowが高energy化しprior swing破壊 | RETEST | HYBRID | WORLD_DERIVED `S03 S23` |

### 5.3 Exhaustion Reversal

| pattern ID | Pattern名 | ordered observation | terminal | invalidation | expiry | observability | provenance / source |
|---|---|---|---|---|---|---|---|
| `PAT-EXH-BUYER-DOUBLE-FADE-001` | **Exhaustion Reversal / Buyer Fade / Weaker Retest** | upper key level -> buyer prints急減 -> pause -> 同価格再test -> さらに少ないbuy prints -> sellers参加 | SELL ready | buyersが再加速してlevel突破 | RETEST | DIRECT | WORLD_DERIVED `S01` |
| `PAT-EXH-SELLER-DOUBLE-FADE-001` | **Exhaustion Reversal / Seller Fade / Weaker Retest** | lower key level -> seller prints急減 -> pause -> 同価格再test -> さらに少ないsell prints -> buyers参加 | BUY ready | sellersが再加速してlevel突破 | RETEST | DIRECT | WORLD_DERIVED `S01` |
| `PAT-EXH-AGGRESSION-NO-FOLLOW-001` | **Exhaustion Reversal / Aggressive Burst / No Follow-Through** | large aggressive orders -> price進展なし -> opposite passive liquidity stack -> initiating flow停止 -> opposite trade flow | reversal-side ready | aggressive flowが継続しstackを消費 | REACTION | DIRECT | WORLD_DERIVED `S16` |
| `PAT-EXH-EFFORT-RESULT-001` | **Exhaustion Reversal / High Effort / Narrow Result** | trend終盤 -> unusually high volume -> narrow range／極値更新失敗 -> opposite imbalance／aggression -> price反転 | reversal-side ready | volumeに比例したrange expansion | REACTION | DIRECT | WORLD_DERIVED `S10 S13` |
| `PAT-EXH-LIQUIDATION-CASCADE-END-001` | **Exhaustion Reversal / Liquidation Cascade / Organic Flow Failure** | leveraged move -> liquidation増加 -> cascade spike -> forced flow peak後にorganic follow-through欠如 -> absorption／price halt | reversal-side ready | liquidation後もspot／aggressive flowとacceptance継続 | EVENT | HYBRID | WORLD_DERIVED `S24` |

### 5.4 Stacked Imbalance Continuation

| pattern ID | Pattern名 | ordered observation | terminal | invalidation | expiry | observability | provenance / source |
|---|---|---|---|---|---|---|---|
| `PAT-STACK-BUY-SUPPORT-RETEST-001` | **Stacked Imbalance Continuation / Buy Stack / Support Retest** | multiple buy imbalances -> initial imbalance zone形成 -> pullback -> zone下抜け失敗 -> buy aggression再開 | BUY ready | zoneをsell flowがbreakしbelow hold | RETEST | DIRECT | WORLD_DERIVED `S11 S12` |
| `PAT-STACK-SELL-RESIST-RETEST-001` | **Stacked Imbalance Continuation / Sell Stack / Resistance Retest** | multiple sell imbalances -> initial imbalance zone形成 -> rebound -> zone上抜け失敗 -> sell aggression再開 | SELL ready | zoneをbuy flowがbreakしabove hold | RETEST | DIRECT | WORLD_DERIVED `S11 S12` |
| `PAT-STACK-RANGE-POC-SHIFT-001` | **Stacked Imbalance Continuation / Range Exit / POC Shift** | range継続 -> boundary側stacked imbalance -> delta同方向 -> maximum-volume level同方向shift -> range break | break方向ready | opposite imbalance出現かrange中央復帰 | BREAK_ACCEPT | DIRECT | WORLD_DERIVED `S11` |
| `PAT-STACK-PULLBACK-HOLD-REACCEL-001` | **Stacked Imbalance Continuation / Trend Pullback / Zone Hold / Re-acceleration** | trend imbalance -> pullback -> initial stack zoneでprice停止 -> opposite imbalance欠如 -> same-side stack再出現 | trend-side ready | opposite stacked imbalanceがzoneを貫通 | RETEST | DIRECT | WORLD_DERIVED `S11 S12` |
| `PAT-STACK-PERSISTENCE-PROGRESS-001` | **Stacked Imbalance Continuation / Multi-Unit Persistence / Price Progress** | stacked imbalance -> 次の観察単位にも同方向imbalance -> priceが逆行せず進展 -> supporting zone切上げ／切下げ -> aggression維持 | trend-side ready | imbalance継続なのにprice進展停止 | REACTION | DIRECT | WORLD_DERIVED `S11` |

### 5.5 Iceberg Breakout

| pattern ID | Pattern名 | ordered observation | terminal | invalidation | expiry | observability | provenance / source |
|---|---|---|---|---|---|---|---|
| `PAT-ICE-BARRIER-DEPLETE-BREAK-001` | **Iceberg Breakout / Repeated Refill / Barrier Depletion / Break** | same priceで大量execution -> visible size以上のrefill推定 -> price barrier保持 -> refill速度低下／消失 -> barrier突破 | break方向ready | icebergが継続しprice反転 | BREAK_ACCEPT | INFERRED | WORLD_DERIVED `S17 S20` |
| `PAT-ICE-HIDDEN-ACCUM-BUYBREAK-001` | **Iceberg Breakout / Hidden Accumulation / Buyer Initiative** | repeated iceberg-like buy fills -> price floor保持 -> sell pressure減衰 -> aggressive buying出現 -> upper structure break | BUY ready | floor breakかつsell acceptance | BREAK_ACCEPT | INFERRED | WORLD_DERIVED `S17 S20` |
| `PAT-ICE-HIDDEN-DISTRIB-SELLBREAK-001` | **Iceberg Breakout / Hidden Distribution / Seller Initiative** | repeated iceberg-like sell fills -> price ceiling保持 -> buy pressure減衰 -> aggressive selling出現 -> lower structure break | SELL ready | ceiling breakかつbuy acceptance | BREAK_ACCEPT | INFERRED | WORLD_DERIVED `S17 S20` |
| `PAT-ICE-SECOND-ATTEMPT-DEPLETION-001` | **Iceberg Breakout / Second Attempt / Absorber Exhaustion** | known absorption zone -> first break attempt失敗 -> second attemptでexecution継続 -> absorber follow-through低下 -> zone突破 | break方向ready | second attemptもrejectされrange復帰 | BREAK_ACCEPT | INFERRED | WORLD_DERIVED `S05` |
| `PAT-ICE-BREAK-STOPS-ACCEPT-001` | **Iceberg Breakout / Wall Break / Stops / New-Level Acceptance** | iceberg barrier消費 -> price break -> stops trigger -> aggression継続 -> liquidityがprice後方へ形成 -> retest hold | continuation ready | stop burst後に新levelを保持できずsnapback | BREAK_ACCEPT | INFERRED | WORLD_DERIVED `S20 S21` |

### 5.6 Liquidity Sweep

| pattern ID | Pattern名 | ordered observation | terminal | invalidation | expiry | observability | provenance / source |
|---|---|---|---|---|---|---|---|
| `PAT-SWEEP-HIGH-ABSORB-SNAPBACK-001` | **Liquidity Sweep / High Stop Run / Sell Absorption / Snapback** | prior high上のliquidity cluster -> aggressive buy sweep -> large sell absorption -> no higher progress -> prior range復帰 | SELL ready | high外でvolume／value形成 | REACTION | HYBRID | WORLD_DERIVED `S18 S20` |
| `PAT-SWEEP-LOW-ABSORB-SNAPBACK-001` | **Liquidity Sweep / Low Stop Run / Buy Absorption / Snapback** | prior low下のliquidity cluster -> aggressive sell sweep -> large buy absorption -> no lower progress -> prior range復帰 | BUY ready | low外でvolume／value形成 | REACTION | HYBRID | WORLD_DERIVED `S18 S23` |
| `PAT-SWEEP-ICEBERG-DRYUP-001` | **Liquidity Sweep / Stops into Iceberg / Aggressor Dry-Up** | strong move -> stop sweep -> iceberg-like wall execution -> aggressionがdry-up -> opposite aggression開始 | reversal-side ready | wall消費後もsame-side aggression継続 | REACTION | INFERRED | WORLD_DERIVED `S17` |
| `PAT-SWEEP-QUICK-RETURN-TRAP-001` | **Liquidity Sweep / Quick Range Return / Trapped Traders** | level break／stops -> outside滞在短い -> range内復帰 -> breakout参加者のopposite exit flow -> reverse acceleration | reversal-side ready | range復帰せずnew level hold | REACTION | HYBRID | WORLD_DERIVED `S16 S18` |
| `PAT-SWEEP-FRONTRUN-LIQUIDITY-TARGET-001` | **Liquidity Sweep / Sell Stops / Front-Run Absorption / Offer Target** | low側stop run -> buy absorptionがlarge bid liquidity前で出現 -> bottom維持 -> buyers参加 -> upper offer liquidityへ移動 | BUY ready | bid liquidity消失かlow再break | REACTION | HYBRID | WORLD_DERIVED `S23` |

### 5.7 Failed Auction

| pattern ID | Pattern名 | ordered observation | terminal | invalidation | expiry | observability | provenance / source |
|---|---|---|---|---|---|---|---|
| `PAT-FA-RANGE-BREAK-RETURN-001` | **Failed Auction / Range Break / No Follow-Through / Return** | balance range -> boundary break -> sustained participation欠如 -> supporting liquidity不形成 -> range内復帰 | reversal-side ready | outside holdとvalue migration | BREAK_ACCEPT | DIRECT | WORLD_DERIVED `S05 S21` |
| `PAT-FA-EXTREME-HVN-FLICKBACK-001` | **Failed Auction / Extreme Break / Outside HVN / Flickback** | selected extreme break -> outsideでsmall HVN形成 -> priceが先へ進めない -> range側へflick -> LVNを後方へ残す | reversal-side ready | HVNを起点にoutside expansion | REACTION | DIRECT | WORLD_DERIVED `S06` |
| `PAT-FA-TAIL-RANGE-FAILED-CONTINUE-001` | **Failed Auction / Tail / Tight Range / Continuation Failure** | extreme tail -> tail上／下でtight range保持 -> trend方向へ再break試行 -> 直ちにrange内へ戻る -> opposite jump | reversal-side ready |再break後にoutside hold | BREAK_ACCEPT | DIRECT | WORLD_DERIVED `S07` |
| `PAT-FA-UNFINISHED-DRYUP-REVERSAL-001` | **Failed Auction / Unfinished Extreme / Aggressor Dry-Up / Reversal** | trend -> unfinished auction at extreme -> initiator volume dry-up -> opposite side advance -> price reversal | reversal-side ready | trendがunfinished levelを越えてfix | REACTION | DIRECT | WORLD_DERIVED `S14` |
| `PAT-FA-EVENT-NO-VALUE-MIGRATION-001` | **Failed Auction / Event Breakout / No Value Migration / Old-Range Return** | event impulse -> breakout -> sustained volume欠如 -> liquidity support欠如 -> new value不形成 -> old range復帰 | reversal-side ready | aggression継続、liquidity後方形成、value移動 | EVENT | HYBRID | WORLD_DERIVED `S21 S22` |

### 5.8 Pulling / Stacking Strategy

| pattern ID | Pattern名 | ordered observation | terminal | invalidation | expiry | observability | provenance / source |
|---|---|---|---|---|---|---|---|
| `PAT-PS-BID-PULL-ASK-STACK-001` | **Pulling / Stacking / Bid Pull / Ask Stack / Seller Control** | long-side context -> bidsがprice接近時にpull -> offers stack -> buy aggression進展なし -> sell aggression開始 | SELL／long-cancel ready | bids再構築しoffer stack消費 | REACTION | DIRECT | WORLD_DERIVED `S04 S26` |
| `PAT-PS-ASK-PULL-BID-STACK-001` | **Pulling / Stacking / Ask Pull / Bid Stack / Buyer Control** | short-side context -> asksがprice接近時にpull -> bids stack -> sell aggression進展なし -> buy aggression開始 | BUY／short-cancel ready | asks再構築しbid stack消費 | REACTION | DIRECT | WORLD_DERIVED `S04 S26` |
| `PAT-PS-WALL-PULL-FRAGILITY-001` | **Pulling / Stacking / Apparent Wall / Pull-on-Approach / Fragility** | large wall出現 -> price接近 -> execution前にwall pull -> backing liquidity vacuum -> opposite-side liquidity出現 -> price reversal | opposite-side ready | wall再出現し実executionで保持 | REACTION | DIRECT | WORLD_DERIVED `S04 S22` |
| `PAT-PS-BEHIND-PRICE-STACK-RETEST-001` | **Pulling / Stacking / Liquidity Behind Price / Retest Hold** | breakout -> same-side liquidityがprice後方へstack -> shallow retest -> opposing ordersが旧rangeへ戻せない -> original aggression再開 | continuation ready | behind-price liquidity pullとrange復帰 | RETEST | DIRECT | WORLD_DERIVED `S21 S26` |
| `PAT-PS-ABSORB-THEN-PULL-CUTREVERSE-001` | **Pulling / Stacking / Churn and Absorption / Protecting Wall Pull / Cut-and-Reverse** | bid／askでchurningとabsorption -> position-side wallに依存 -> wall pull -> position vulnerable -> opposite flow加速 | cut-and-reverse ready | wall復帰しoriginal direction再開 | REACTION | DIRECT | WORLD_DERIVED `S05` |

### 5.9 Delta Flip

| pattern ID | Pattern名 | ordered observation | terminal | invalidation | expiry | observability | provenance / source |
|---|---|---|---|---|---|---|---|
| `PAT-DF-POSITIVE-TAIL-SELLCONTROL-001` | **Delta Flip / Positive Delta Tail / Seller Control** | positive delta impulse -> price上進停止 -> deltaにupper tail -> aggressive sells出現 -> delta負側へflip | SELL ready | delta再度positive拡大しhigh break | REACTION | DIRECT | WORLD_DERIVED `S11 S13` |
| `PAT-DF-NEGATIVE-TAIL-BUYCONTROL-001` | **Delta Flip / Negative Delta Tail / Buyer Control** | negative delta impulse -> price下進停止 -> deltaにlower tail -> aggressive buys出現 -> delta正側へflip | BUY ready | delta再度negative拡大しlow break | REACTION | DIRECT | WORLD_DERIVED `S11 S13` |
| `PAT-DF-NEGABS-NOLOW-POSFLIP-001` | **Delta Flip / Negative Delta Absorbed / No Lower Low / Positive Flip** | negative delta／selling pressure -> absorption -> healthy upward rotation -> next unitがlower low不可 -> delta positive flip | BUY ready | lower low更新とnegative delta再加速 | REACTION | DIRECT | WORLD_DERIVED `S08` |
| `PAT-DF-SAMESIDE-DISAPPEAR-OPPOSITE-001` | **Delta Flip / Same-Side Imbalance Disappears / Opposite Delta** | trend-side imbalances継続 -> 次unitで同色imbalance消失 -> opposite imbalance出現 -> delta反転 -> price応答 | reversal-side ready | same-side imbalance復帰し極値更新 | REACTION | DIRECT | WORLD_DERIVED `S11` |
| `PAT-DF-POSTEVENT-LIQUIDITY-REALIGN-001` | **Delta Flip / Post-Event / Liquidity Reform / Directional Realignment** | event impulse沈静 -> liquidity再形成 -> deltaが片側へflip -> priceが新balanceを保持 -> same-side aggression継続 | aligned-side ready | delta再flipまたは旧range復帰 | EVENT | DIRECT | WORLD_DERIVED `S22` |

### 5.10 Book Imbalance

| pattern ID | Pattern名 | ordered observation | terminal | invalidation | expiry | observability | provenance / source |
|---|---|---|---|---|---|---|---|
| `PAT-BI-BID-PERSIST-BUYCONFIRM-001` | **Book Imbalance / Persistent Bid Skew / Buy-Flow Confirmation** | multi-level bid>ask skew -> skew持続／増幅 -> buy market flow参加 -> price上進 -> support depth切上げ | BUY ready | bid skew pullかsell absorption | REACTION | DIRECT | WORLD_DERIVED `S25 S26` |
| `PAT-BI-ASK-PERSIST-SELLCONFIRM-001` | **Book Imbalance / Persistent Ask Skew / Sell-Flow Confirmation** | multi-level ask>bid skew -> skew持続／増幅 -> sell market flow参加 -> price下進 -> resistance depth切下げ | SELL ready | ask skew pullかbuy absorption | REACTION | DIRECT | WORLD_DERIVED `S25 S26` |
| `PAT-BI-SKEW-NORESULT-FADE-001` | **Book Imbalance / One-Sided Skew / No Price Result / Fade** | strong book skew -> same-side aggression -> price進展なし -> opposite passive absorption -> skew減衰／反転 | opposite-side ready | skewが維持されbarrier消費 | REACTION | HYBRID | WORLD_DERIVED `S16 S25` |
| `PAT-BI-PULL-REVERSAL-CONFIRM-001` | **Book Imbalance / Skew Pull / Opposite Rebuild / Reversal** | initial imbalance -> price接近 -> favored-side orders pull -> opposite-side depth rebuild -> opposite aggressive trades -> price反転 | opposite-side ready | favored depth復帰しprice継続 | REACTION | DIRECT | WORLD_DERIVED `S04 S26` |
| `PAT-BI-DEEP-STACK-TOPSHIFT-001` | **Book Imbalance / Deep Stack / Top-Book Shift / Aggressor Alignment** | deeper levelsでsame-side stack -> top-book imbalance同方向へshift -> spread／microprice同方向 -> aggressive trades参加 -> price progress | aligned-side ready | deep stack cancelかaggression不一致 | REACTION | DIRECT | WORLD_DERIVED `S25 S26` |

## 6. Pattern遷移logへの要求

各行のPatternは、`ORDER_FLOW_STRATEGY_NAME_REGISTRY_V0_1_20260727.md`のlog契約に従う。最低限、次を満たす。

1. `pattern_id`と`pattern_name`をObservation Instance開始時に固定する。
2. ordered observationの各節を別`state_id`にする。
3. 順序逆転を成立扱いしない。
4. invalidationを成功stateと同じevent streamで評価する。
5. expiry到達時は`EXPIRED`を保存する。
6. terminalは`ORDER_READY`までであり、risk／execution gate通過前に注文しない。
7. `INFERRED` Patternは推定根拠eventをすべて保存し、native iceberg／stop identityと偽装しない。

## 7. 次工程

- 50原型をLONG／SHORT、location、confirmation pathへ展開する。
- 展開ごとに`DELTAENGINE_DERIVED_VARIANT`を付け、元のpattern IDとsource IDを保持する。
- 各stateへ560 Condition Dictionaryの材料を接続する。
- replayで順序、timeout、反証、同一event再利用、terminal到達可能性を検証する。