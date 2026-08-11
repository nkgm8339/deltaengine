# DeltaEngine Hook／Strategy／Pattern 内容説明書

作成日: 2026-07-27 JST  
目的: IDの羅列ではなく、各項目が「何を観測するものか」「何を意味しないか」を人間向けに説明する。

## 先に結論

これは発注シグナル一覧ではない。Hookは異常・変化を検出してFSMを起こす観測イベント、strategy familyは分類、named patternは段階的な証拠の組合せ、derived variantはその具体的なFSM候補である。正本CSVには閾値・具体的な時間窓・勝率は書かれていない。したがって、以下の「意味」は名称と正本の能力分類から読める観測上の意味であり、ENTRYの断定ではない。

## 1. Hook 88種

### A: 板・可視流動性（24）

板の厚み、壁、最良気配、スプレッドの変化を観測する。壁が見えたから支え・抵抗が確定したわけではなく、取消しや補充の後続確認が必要。

| ID | Hook | 人間向けの内容 |
|---|---|---|
| A01 | large_bid_wall_appeared | 買い側に大きな見える注文の塊が現れた。下値候補を観測する起点だが、本当に維持されるかは未確定。 |
| A02 | large_ask_wall_appeared | 売り側に大きな見える注文の塊が現れた。上値候補を観測する起点だが、実注文・ spoof の別は未確定。 |
| A03 | bid_wall_pulled | 買い壁が減少・取消しされた。支えの消失候補であり、価格下落を意味しない。 |
| A04 | ask_wall_pulled | 売り壁が減少・取消しされた。上値の抑制が弱まった候補であり、上昇確定ではない。 |
| A05 | bid_depth_thinned | 買い側の板厚が薄くなった。下方向の流動性空洞候補を示す。 |
| A06 | ask_depth_thinned | 売り側の板厚が薄くなった。上方向の空洞候補を示す。 |
| A07 | bid_depth_strengthened | 買い側の板厚が増えた。買い流動性の増加を観測するが、約定意思は不明。 |
| A08 | ask_depth_strengthened | 売り側の板厚が増えた。売り流動性の増加を観測するが、継続性は不明。 |
| A09 | book_asymmetry_bid | 買い側が売り側より厚い偏りを観測。方向の候補であり、価格追随を保証しない。 |
| A10 | book_asymmetry_ask | 売り側が買い側より厚い偏りを観測。上値抑制候補であり、下落確定ではない。 |
| A11 | best_bid_retreat | 最良買い気配が後退した。買いの防衛線が下がった可能性を示す。 |
| A12 | best_ask_retreat | 最良売り気配が後退した。売りの防衛線が上がった可能性を示す。 |
| A13 | best_bid_advance | 最良買い気配が上がった。買い側の価格追随を観測する。 |
| A14 | best_ask_advance | 最良売り気配が下がった。売り側の価格追随を観測する。 |
| A15 | spread_expansion | 最良買い・売りの差が広がった。流動性低下・不確実性上昇の候補。 |
| A16 | spread_recovery | 広がったスプレッドが戻った。流動性回復候補だが、方向性は持たない。 |
| A17 | bid_iceberg_suspected | 買い側で見える板以上の補充約定が疑われる。iceberg確定ではない。 |
| A18 | ask_iceberg_suspected | 売り側で見える板以上の補充約定が疑われる。iceberg確定ではない。 |
| A19 | bid_spoofing_suspected | 買い壁の出現・取消しが spoof 的に見える。疑いであり、不正行為の断定ではない。 |
| A20 | ask_spoofing_suspected | 売り壁の出現・取消しが spoof 的に見える。疑いであり、方向確定ではない。 |
| A21 | upside_vacuum | 上方向の近傍流動性が薄く、価格が進みやすい空間を観測。突破・継続は別判定。 |
| A22 | downside_vacuum | 下方向の近傍流動性が薄く、価格が進みやすい空間を観測。下落確定ではない。 |
| A23 | bid_wall_tracks_up | 買い壁が価格上昇に追随して移動。防衛・追随の候補。 |
| A24 | ask_wall_tracks_down | 売り壁が価格下落に追随して移動。抑制・追随の候補。 |

### B: 約定・攻撃性（20）

| ID | Hook | 人間向けの内容 |
|---|---|---|
| B01 | consecutive_market_buys | 成行買いが連続。買い攻撃の連続性を観測する。 |
| B02 | consecutive_market_sells | 成行売りが連続。売り攻撃の連続性を観測する。 |
| B03 | buy_aggression | 買い成行の強さが基準を上回った候補。閾値は較正待ち。 |
| B04 | sell_aggression | 売り成行の強さが基準を上回った候補。閾値は較正待ち。 |
| B05 | trade_speed_spike | 約定頻度が急増。イベント発生・競争激化の起点。 |
| B06 | trade_pause | 約定が一時停止。参加者不在・様子見・データ欠損を区別する必要がある。 |
| B07 | large_market_buy | 大きな成行買いを観測。単発で継続買いとは限らない。 |
| B08 | large_market_sell | 大きな成行売りを観測。単発で継続売りとは限らない。 |
| B09 | large_buy_cluster | 大きな買い約定がまとまって発生。クラスターの持続と価格反応は別途確認。 |
| B10 | large_sell_cluster | 大きな売り約定がまとまって発生。価格反応は未確定。 |
| B11 | buy_sweep | 買い成行が複数価格帯を掃く動き。流動性消費の観測。 |
| B12 | sell_sweep | 売り成行が複数価格帯を掃く動き。流動性消費の観測。 |
| B13 | average_trade_size_spike | 平均約定サイズが急増。大口参加候補だが、方向は別。 |
| B14 | small_trade_burst | 小口約定が短時間に集中。群集・分割執行候補。 |
| B15 | buy_delta_spike | 買い成行量と売り成行量の差が買い側へ急増。価格追随は未確認。 |
| B16 | sell_delta_spike | デルタが売り側へ急増。下落確定ではない。 |
| B17 | delta_flip_buy_to_sell | デルタ優勢が買いから売りへ反転。反転後の継続が必要。 |
| B18 | delta_flip_sell_to_buy | デルタ優勢が売りから買いへ反転。反転後の継続が必要。 |
| B19 | directional_persistence | 約定方向が一定時間継続。持続性の観測であり、利益方向の保証ではない。 |
| B20 | high_volume_neutral_delta | 出来高は大きいがデルタは中立。吸収・相殺の候補。 |

### C: 吸収・壁との衝突（9）

| ID | Hook | 人間向けの内容 |
|---|---|---|
| C01 | buy_absorption | 買い攻撃が売り壁に受け止められた候補。 |
| C02 | sell_absorption | 売り攻撃が買い壁に受け止められた候補。 |
| C03 | buy_absorption_failed | 買い吸収が維持できず、買い側が通過・崩れた候補。 |
| C04 | sell_absorption_failed | 売り吸収が維持できず、売り側が通過・崩れた候補。 |
| C05 | repeated_absorption | 同一方向の攻撃が繰り返し受け止められた候補。 |
| C06 | wall_collision_started | 攻撃注文と可視壁の衝突開始。結果はまだ未確定。 |
| C07 | ask_wall_consumed | 売り壁が買い攻撃で消費された候補。受容・継続は別確認。 |
| C08 | bid_wall_consumed | 買い壁が売り攻撃で消費された候補。下落確定ではない。 |
| C09 | liquidation_absorbed | 清算フローが反対側に吸収された候補。清算終了の断定ではない。 |

### D: 遷移・トラップ（8）

| ID | Hook | 人間向けの内容 |
|---|---|---|
| D01 | buy_effective_transition | 買い攻撃が価格進展を伴う有効遷移候補。 |
| D02 | sell_effective_transition | 売り攻撃が価格進展を伴う有効遷移候補。 |
| D03 | buy_trapped_transition | 買い攻撃後に価格が進まず、買い側が捕まった候補。 |
| D04 | sell_trapped_transition | 売り攻撃後に価格が進まず、売り側が捕まった候補。 |
| D05 | stalled_transition | 攻撃は起きたが価格進展が止まった候補。 |
| D06 | effective_to_trapped_fast | 有効に見えた遷移が短時間でトラップへ変化した候補。 |
| D07 | trapped_resolved | トラップ状態が解消した候補。解消方向は別途判定。 |
| D08 | multi_window_alignment | 複数時間窓で同じ遷移傾向が揃った候補。窓値は較正対象。 |

### E: 清算（6）

| ID | Hook | 人間向けの内容 |
|---|---|---|
| E01 | large_long_liquidation | 大きなロング清算。強制売りの観測。 |
| E02 | large_short_liquidation | 大きなショート清算。強制買いの観測。 |
| E03 | long_liquidation_cascade | ロング清算が連鎖。カスケード候補。 |
| E04 | short_liquidation_cascade | ショート清算が連鎖。カスケード候補。 |
| E05 | liquidation_no_price_response | 清算量の割に価格が進まない。吸収・反対流動性の候補。 |
| E06 | liquidation_exhaustion | 清算連鎖が弱まり尽きた候補。反転確定ではない。 |

### F: OIと価格（5）

| ID | Hook | 人間向けの内容 |
|---|---|---|
| F01 | oi_up_price_up | OI増加と価格上昇が同時。新規参加・追随の候補。 |
| F02 | oi_up_price_down | OI増加と価格下落が同時。新規売り等の候補。 |
| F03 | oi_down_price_up | OI減少と価格上昇が同時。ショート解消等の候補。 |
| F04 | oi_down_price_down | OI減少と価格下落が同時。ロング解消等の候補。 |
| F05 | oi_shock | OIが急変。イベントの起点だが、方向は単独で決まらない。 |

### G: 価格位置・文脈（12）

| ID | Hook | 人間向けの内容 |
|---|---|---|
| G01 | recent_high_touch | 直近高値へ接触。ブレイク試行の前提候補。 |
| G02 | recent_low_touch | 直近安値へ接触。ブレイク試行の前提候補。 |
| G03 | high_break | 直近高値を上抜いた候補。受容確認が必要。 |
| G04 | low_break | 直近安値を下抜いた候補。受容確認が必要。 |
| G05 | failed_high_break | 高値を抜いたが維持できず戻った候補。 |
| G06 | failed_low_break | 安値を抜いたが維持できず戻った候補。 |
| G07 | vwap_touch | VWAPへ接触。基準価格との位置関係の観測。 |
| G08 | vwap_deviation_extreme | VWAPからの乖離が極端。逆張り・継続のどちらも未確定。 |
| G09 | volume_node_touch | 出来高集中価格帯へ接触。受容・拒否を観測する起点。 |
| G10 | round_number_touch | ラウンドナンバーへ接触。心理的注文集中の候補。 |
| G11 | range_edge | レンジ端へ到達。反発・突破の分岐点候補。 |
| G12 | higher_timeframe_direction | 上位時間足の方向文脈。単独で短期ENTRYを決めない。 |

### H: 市場状態（4）

| ID | Hook | 人間向けの内容 |
|---|---|---|
| H01 | session_context | セッション（時間帯）文脈。値動きの背景を付与する。 |
| H02 | high_volatility_context | 高ボラティリティ状態。閾値解釈を変える背景情報。 |
| H03 | low_liquidity_context | 低流動性状態。スプレッド拡大や空振りの背景情報。 |
| H04 | hfm_spread_normal | HFMスプレッドが正常範囲。異常状態でないことの確認材料。 |

## 2. Strategy family 10件

familyは「何を中心にFSMを組むか」の分類であり、完成した売買戦略ではない。各familyに5つのnamed patternが紐づく。

| family | 何を見るか |
|---|---|
| CVD Divergence | 価格の進み方と累積デルタの不一致。 |
| Absorption Reversal | 攻撃が壁に吸収された後の反応。 |
| Exhaustion Reversal | 攻撃・清算の勢いが二段階で弱る過程。 |
| Stacked Imbalance Continuation | 同方向の不均衡が積み重なり、押し戻し後も進む過程。 |
| Iceberg Breakout | 見える板を補充する隠れ注文が枯れて突破する過程。 |
| Liquidity Sweep | 高値・安値の流動性を掃いた後の受容または戻り。 |
| Failed Auction | ブレイクが受け入れられず元の価値帯へ戻る過程。 |
| Pulling / Stacking | 一方の板が引かれ、反対側が積まれる流動性再配置。 |
| Delta Flip | デルタの優勢方向が反転し、その後も続くか。 |
| Book Imbalance | 板の偏りが持続するか、結果なく解消するか。 |

## 3. Named pattern 50件の読み方

各patternは「観測の物語」を短縮した名前である。例えば `CVD / Absorption / Structure Break` は、CVDと価格の不一致を起点に、吸収、構造ブレイクを順に確認する候補であり、名前だけで売買方向や閾値を決めない。

### CVD Divergence

- New Extreme / Aggressor Flip: 新高値・安値なのに攻撃方向が反転する。
- Absorption / Structure Break: 吸収後に価格構造が崩れる。
- Failed Break / Squeeze: ブレイク失敗後に反対方向へ圧縮が解放される。
- Retest / Weaker Aggressor: 再試行時の攻撃が弱くなる。
- Bearish / Absorption Failure / Buy-Wall Break / OI Unwind: 吸収失敗、買い壁崩壊、OI減少が連続する弱気候補。

### Absorption Reversal

- Full Three Element: 攻撃・壁・価格反応の3要素が揃う。
- Support Hold / Bounce: 支持側で吸収後に反発する。
- Resistance Hold / Bounce: 抵抗側で吸収後に反落する。
- Stop Sweep / Snapback: ストップを掃った後に急速に戻る。
- Pullback / Minor Reversal: 押し戻しで吸収が再確認され小反転する。

### Exhaustion Reversal

- Buyer Double Fade / Seller Double Fade: 同方向攻撃が二段階で弱る。
- Aggression No Follow: 攻撃量の割に価格が追随しない。
- Effort Result: 努力量と結果（価格進展）の不一致。
- Liquidation Cascade End: 清算連鎖が終息し、後続反応を観測する。

### Stacked Imbalance Continuation

- Buy Support Retest / Sell Resist Retest: 支持・抵抗を再試行して維持する。
- Range POC Shift: レンジの出来高中心が移動する。
- Pullback Hold Reaccel: 押し戻しを保ち、再加速する。
- Persistence Progress: 同方向の不均衡と価格進展が持続する。

### Iceberg Breakout

- Barrier Deplete Break: 補充されていた壁が枯れて突破する。
- Hidden Accum Buybreak / Hidden Distrib Sellbreak: 隠れた蓄積・分配の後に突破する。
- Second Attempt Depletion: 2回目の試行で壁の残量が減る。
- Break Stops Accept: 突破後に停止せず価格が受け入れられる。

### Liquidity Sweep

- High/Low Absorb Snapback: 高値・安値を掃い、吸収後に戻る。
- Iceberg Dryup: 掃引先の補充が枯れる。
- Quick Return Trap: 掃引直後に元の範囲へ戻り、仕掛け側が捕まる。
- Frontrun Liquidity Target: 目標流動性へ先回りして到達する。

### Failed Auction

- Range Break Return: レンジを抜けたが戻る。
- Extreme HVN Flickback: 極端な位置から出来高ノードへ跳ね返る。
- Tail Range Failed Continue: ヒゲ先端から継続できず戻る。
- Unfinished Dryup Reversal: 未完了の約定が枯れ、反転する。
- Event No Value Migration: イベント後も価値中心が移動しない。

### Pulling / Stacking

- Bid Pull Ask Stack / Ask Pull Bid Stack: 一方を引き、反対側を積む。
- Wall Pull Fragility: 壁が引かれた直後に構造が脆くなる。
- Behind Price Stack Retest: 価格の後ろに積まれた板を再試行する。
- Absorb Then Pull Cutreverse: 吸収後に壁を引き、反対方向へ切り返す。

### Delta Flip

- Positive/Negative Tail Control: 片側の極端なデルタ後に反対側が主導する。
- NegAbs NoLow PosFlip: 売り吸収後に安値更新できず買いへ反転する。
- Sameside Disappear Opposite: 同方向の攻撃が消え、反対方向が現れる。
- Postevent Liquidity Realign: イベント後に板配置が方向転換する。

### Book Imbalance

- Bid/Ask Persist Confirm: 板偏りが持続し、価格も確認する。
- Skew NoResult Fade: 偏りがあるのに価格結果がなく消える。
- Pull Reversal Confirm: 偏りが引かれ、反対方向の反応が確認される。
- Deep Stack Topshift: 深い板の積み上がりと最良気配の変化が揃う。

## 4. 現在の運用状態

- 88 Hook、50 pattern、365 variantは、意味を持つ観測・FSM候補のカタログである。
- 全件 `UNVALIDATED`。runtime有効化0、直接発注権限0。
- 発火してもENTRYや注文を意味しない。較正、holdout、リプレイ検証が必要。
- 具体的な閾値・時間窓・採用可否は、実測データで別途決める。

## 5. 正本

`ORDER_FLOW_HOOK_PREDICATE_CAPABILITY_REGISTRY_V0_1_20260727.csv`  
`ORDER_FLOW_STRATEGY_NAME_REGISTRY_V0_1_20260727.csv`  
`ORDER_FLOW_WORLD_NAMED_PATTERN_REGISTRY_V0_1_20260727.csv`  
`ORDER_FLOW_DERIVED_NAMED_PATTERN_VARIANTS_V0_1_20260727.csv`
