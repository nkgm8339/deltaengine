# DeltaEngine Order Flow Condition Dictionary v0.1

作成日: 2026-07-26 JST  
状態: **外部実務・一次研究から作成した初期条件宇宙。未較正、production未採用、発注許可ではない。**  
総数: **560 condition definitions**

## 0. 結論

ConditionSetは一個のStrategyではない。世界で使われる注文フロー、板、tape、価格反応、market context、執行、保有管理の条件を収めた**全体辞書**である。HookがStrategy Engineを起動すると、該当Strategyがこの560件から必要なsubsetを選び、現在値で埋め、最終的な発注条件を判定する。

```text
Condition Universe 560件 -> Strategy別subset -> Condition Fill -> 発注可否・時機・枚数・保有判断 -> Order Trigger
```

560件すべてを同時加点しない。window違い、同じraw sourceの派生、数式上従属する値は同じ`independence_lineage`に束ね、一現象を複数票として数えない。

## 1. 世界資料から固定した原則

| 外部資料 | 採用した事実 |
|---|---|
| [DeepLOB](https://www.oxford-man.ox.ac.uk/wp-content/uploads/2020/03/DeepLOB-Deep-Convolutional-Neural-Networks-for-Limit-Order-Books.pdf) | 板10段のbid/ask価格・数量40特徴を100更新使う。 |
| [Multi-Level OFI](https://arxiv.org/abs/1907.06230) | bestだけでなく追加levelも保持する。 |
| [Order Book Events](https://arxiv.org/abs/1011.6402) | limit order、market order、cancel、OFI、depthを分ける。 |
| [Queue Imbalance](https://arxiv.org/abs/1512.03492) | bid/ask queue imbalanceを候補条件にする。 |
| [LOB Resiliency](https://arxiv.org/abs/1602.00731) | shock後のspread、depth、order intensity回復を追う。 |
| [LOB-Bench](https://proceedings.mlr.press/v267/nagy25a.html) | spread、volume、imbalance、message間隔を別feature化する。 |
| [CME](https://www.cmegroup.com/education/articles-and-reports/assessing-liquidity) | depth単独でなくvolume、volatility、fill quality、refreshを併用する。 |
| [Nasdaq TotalView](https://www.nasdaq.com/solutions/data/equities/nasdaq-totalview) | price-level depth、imbalance、liquidity pocketを観測する。 |
| [Jigsaw DOM](https://www.jigsawtrading.com/blog/which-dom-day-trading-setups-actually-work/) | passive depth、market order、momentum、profile、pull/stackをcontext別に使う。 |
| [Jigsaw confirmation](https://www.jigsawtrading.com/wp-content/uploads/2013/11/ConfirmingLevelsWithOrderFlow.pdf) | absorption、fade、aggression、retest、entry後price対flowを分離する。 |
| [Axia breakout](https://axiafutures.com/blog/two-breakout-strategies-for-futures-markets/) | rhythm、location、maturity、participation、follow-throughを使う。 |
| [Axia reversal](https://axiafutures.com/blog/reversal-and-continuation-scalping-strategies/) | momentum、pullback stall、flow停止時exitを使う。 |
| [SMB](https://www.smbtraining.com/blog/stock-trading) | environment、catalyst、RVOL、location、time、order flow、trigger、managementを段階化する。 |
| [Binance Futures API](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data) | depth、aggTrade、OI、funding、basis、mark/indexのsource contractを守る。 |

外部資料に普遍的な正解件数はない。560件は外部の観測軸をDeltaEngine用に展開した**設計値**であり、世界の合意値ではない。

## 2. Condition Fill契約

各Conditionは`value`を保存し、Strategy別の版付きcomparatorとthresholdから`PASS / FAIL / UNKNOWN / STALE`を得る。辞書は利益thresholdを仮定しない。`UNKNOWN`を0へ潰さず、`STALE`をsupport条件で相殺しない。

```yaml
condition_id: CD-Gxx-nnn
condition_key: stable_machine_name
value: any
result: PASS | FAIL | UNKNOWN | STALE
comparator: GT | GE | LT | LE | EQ | IN | STATE_MATCH | null
threshold_version: string | null
evaluated_at: timestamp
source_event_ids: []
independence_lineage: string
```

## 3. Group別件数

| group | 名称 | 件数 |
|---|---|---:|
| G01 | Data Quality and Lineage | 28 |
| G02 | Session and Market Regime | 24 |
| G03 | Price and Location | 48 |
| G04 | Volatility and Tradeability | 24 |
| G05 | Raw Limit Order Book | 40 |
| G06 | Book Shape and Static Imbalance | 32 |
| G07 | Book Event Flow | 48 |
| G08 | Aggressive Trade Tape | 48 |
| G09 | Flow Price Response | 40 |
| G10 | Delta CVD and Footprint | 36 |
| G11 | Volume Profile and Auction | 32 |
| G12 | Derivatives Positioning | 32 |
| G13 | Cross Venue Relative State | 28 |
| G14 | Execution and Risk Gate | 28 |
| G15 | Open Position Lifecycle | 24 |
| G16 | Order Flow Interaction States | 48 |
| **TOTAL** |  | **560** |

## 4. Condition Dictionary

### G01 Data Quality and Lineage

| ID | condition_key | type | window | source | 定義 | independence_lineage |
|---|---|---|---|---|---|---|
| CD-G01-001 | `depth_book_synced` | FLAG | POINT_IN_TIME | ALL_SOURCES+JOURNAL | DEPTH local bookが同期済み | `QUALITY:depth_book_synced` |
| CD-G01-002 | `depth_sequence_contiguous` | FLAG | POINT_IN_TIME | ALL_SOURCES+JOURNAL | depth update sequenceが連続 | `QUALITY:depth_sequence_contiguous` |
| CD-G01-003 | `depth_snapshot_applied` | FLAG | POINT_IN_TIME | ALL_SOURCES+JOURNAL | snapshotとdiffの接続済み | `QUALITY:depth_snapshot_applied` |
| CD-G01-004 | `depth_event_fresh` | FLAG | POINT_IN_TIME | ALL_SOURCES+JOURNAL | depth event ageが上限内 | `QUALITY:depth_event_fresh` |
| CD-G01-005 | `trade_event_fresh` | FLAG | POINT_IN_TIME | ALL_SOURCES+JOURNAL | aggTrade event ageが上限内 | `QUALITY:trade_event_fresh` |
| CD-G01-006 | `liquidation_event_fresh` | FLAG | POINT_IN_TIME | ALL_SOURCES+JOURNAL | forceOrder snapshot ageが上限内 | `QUALITY:liquidation_event_fresh` |
| CD-G01-007 | `open_interest_snapshot_fresh` | FLAG | POINT_IN_TIME | ALL_SOURCES+JOURNAL | OI snapshot ageが上限内 | `QUALITY:open_interest_snapshot_fresh` |
| CD-G01-008 | `hfm_quote_fresh` | FLAG | POINT_IN_TIME | ALL_SOURCES+JOURNAL | HFM quote ageが上限内 | `QUALITY:hfm_quote_fresh` |
| CD-G01-009 | `exchange_clock_aligned` | FLAG | POINT_IN_TIME | ALL_SOURCES+JOURNAL | exchange時刻差が上限内 | `QUALITY:exchange_clock_aligned` |
| CD-G01-010 | `receive_clock_monotonic` | FLAG | POINT_IN_TIME | ALL_SOURCES+JOURNAL | receive timestampが単調 | `QUALITY:receive_clock_monotonic` |
| CD-G01-011 | `event_order_monotonic` | FLAG | POINT_IN_TIME | ALL_SOURCES+JOURNAL | source event順序が正常 | `QUALITY:event_order_monotonic` |
| CD-G01-012 | `schema_version_known` | FLAG | POINT_IN_TIME | ALL_SOURCES+JOURNAL | schema versionが既知 | `QUALITY:schema_version_known` |
| CD-G01-013 | `symbol_mapping_valid` | FLAG | POINT_IN_TIME | ALL_SOURCES+JOURNAL | venue間symbol対応が有効 | `QUALITY:symbol_mapping_valid` |
| CD-G01-014 | `tick_size_valid` | FLAG | POINT_IN_TIME | ALL_SOURCES+JOURNAL | tick size契約が既知 | `QUALITY:tick_size_valid` |
| CD-G01-015 | `quantity_step_valid` | FLAG | POINT_IN_TIME | ALL_SOURCES+JOURNAL | quantity step契約が既知 | `QUALITY:quantity_step_valid` |
| CD-G01-016 | `duplicate_event_absent` | FLAG | POINT_IN_TIME | ALL_SOURCES+JOURNAL | 重複eventが除去済み | `QUALITY:duplicate_event_absent` |
| CD-G01-017 | `trade_gap_absent` | FLAG | POINT_IN_TIME | ALL_SOURCES+JOURNAL | trade stream欠落兆候なし | `QUALITY:trade_gap_absent` |
| CD-G01-018 | `depth_gap_absent` | FLAG | POINT_IN_TIME | ALL_SOURCES+JOURNAL | depth stream gapなし | `QUALITY:depth_gap_absent` |
| CD-G01-019 | `persistence_confirmed` | FLAG | POINT_IN_TIME | ALL_SOURCES+JOURNAL | 使用eventが永続化済み | `QUALITY:persistence_confirmed` |
| CD-G01-020 | `market_state_atomic` | FLAG | POINT_IN_TIME | ALL_SOURCES+JOURNAL | 同一snapshot境界でstate生成 | `QUALITY:market_state_atomic` |
| CD-G01-021 | `cross_source_time_aligned` | FLAG | POINT_IN_TIME | ALL_SOURCES+JOURNAL | 必須source間の時刻差が上限内 | `QUALITY:cross_source_time_aligned` |
| CD-G01-022 | `source_reconnect_stable` | FLAG | POINT_IN_TIME | ALL_SOURCES+JOURNAL | 再接続後の安定期間を通過 | `QUALITY:source_reconnect_stable` |
| CD-G01-023 | `resync_cooldown_elapsed` | FLAG | POINT_IN_TIME | ALL_SOURCES+JOURNAL | book resync後cooldownを通過 | `QUALITY:resync_cooldown_elapsed` |
| CD-G01-024 | `sampling_limit_disclosed` | FLAG | POINT_IN_TIME | ALL_SOURCES+JOURNAL | sampled source制約をlineageへ記録 | `QUALITY:sampling_limit_disclosed` |
| CD-G01-025 | `aggregation_limit_disclosed` | FLAG | POINT_IN_TIME | ALL_SOURCES+JOURNAL | aggregated source制約をlineageへ記録 | `QUALITY:aggregation_limit_disclosed` |
| CD-G01-026 | `future_leakage_absent` | FLAG | POINT_IN_TIME | ALL_SOURCES+JOURNAL | 判断時刻より未来の値なし | `QUALITY:future_leakage_absent` |
| CD-G01-027 | `window_complete` | FLAG | POINT_IN_TIME | ALL_SOURCES+JOURNAL | 計算windowが欠損なく完成 | `QUALITY:window_complete` |
| CD-G01-028 | `baseline_sample_sufficient` | FLAG | POINT_IN_TIME | ALL_SOURCES+JOURNAL | 比較baselineの標本数が下限以上 | `QUALITY:baseline_sample_sufficient` |

### G02 Session and Market Regime

| ID | condition_key | type | window | source | 定義 | independence_lineage |
|---|---|---|---|---|---|---|
| CD-G02-001 | `session_id` | ENUM | POINT_IN_TIME | CLOCK+MARKET_STATE | 流動性session分類 | `REGIME:session_id` |
| CD-G02-002 | `session_phase` | ENUM | POINT_IN_TIME | CLOCK+MARKET_STATE | session内phase分類 | `REGIME:session_phase` |
| CD-G02-003 | `utc_hour` | INTEGER | POINT_IN_TIME | CLOCK+MARKET_STATE | UTC時刻bucket | `REGIME:utc_hour` |
| CD-G02-004 | `utc_weekday` | INTEGER | POINT_IN_TIME | CLOCK+MARKET_STATE | UTC曜日 | `REGIME:utc_weekday` |
| CD-G02-005 | `weekend_flag` | FLAG | POINT_IN_TIME | CLOCK+MARKET_STATE | 週末取引状態 | `REGIME:weekend_flag` |
| CD-G02-006 | `minutes_from_session_open` | FLOAT | POINT_IN_TIME | CLOCK+MARKET_STATE | session開始からの経過分 | `REGIME:minutes_from_session_open` |
| CD-G02-007 | `minutes_to_session_close` | FLOAT | POINT_IN_TIME | CLOCK+MARKET_STATE | session終了までの残分 | `REGIME:minutes_to_session_close` |
| CD-G02-008 | `asia_session_active` | FLAG | POINT_IN_TIME | CLOCK+MARKET_STATE | Asia session内 | `REGIME:asia_session_active` |
| CD-G02-009 | `europe_session_active` | FLAG | POINT_IN_TIME | CLOCK+MARKET_STATE | Europe session内 | `REGIME:europe_session_active` |
| CD-G02-010 | `us_session_active` | FLAG | POINT_IN_TIME | CLOCK+MARKET_STATE | US session内 | `REGIME:us_session_active` |
| CD-G02-011 | `major_session_overlap_active` | FLAG | POINT_IN_TIME | CLOCK+MARKET_STATE | 主要session重複中 | `REGIME:major_session_overlap_active` |
| CD-G02-012 | `funding_event_proximity` | FLOAT | POINT_IN_TIME | MARK_FUNDING+CLOCK | 次回fundingまでの距離 | `REGIME:funding_event_proximity` |
| CD-G02-013 | `settlement_event_proximity` | FLOAT | POINT_IN_TIME | MARK_FUNDING+CLOCK | settlement時刻までの距離 | `REGIME:settlement_event_proximity` |
| CD-G02-014 | `scheduled_macro_event_proximity` | FLOAT | POINT_IN_TIME | EXT_CALENDAR_REQUIRED | 予定macro eventまでの距離 | `REGIME:scheduled_macro_event_proximity` |
| CD-G02-015 | `post_news_cooldown_state` | ENUM | POINT_IN_TIME | EXT_CALENDAR_REQUIRED | news直後cooldown状態 | `REGIME:post_news_cooldown_state` |
| CD-G02-016 | `trend_regime` | ENUM | POINT_IN_TIME | CLOCK+MARKET_STATE | 上昇下降非trendのregime | `REGIME:trend_regime` |
| CD-G02-017 | `balance_regime` | ENUM | POINT_IN_TIME | CLOCK+MARKET_STATE | balanceまたはdirectional分類 | `REGIME:balance_regime` |
| CD-G02-018 | `compression_regime` | ENUM | POINT_IN_TIME | CLOCK+MARKET_STATE | 値幅圧縮状態 | `REGIME:compression_regime` |
| CD-G02-019 | `expansion_regime` | ENUM | POINT_IN_TIME | CLOCK+MARKET_STATE | 値幅拡大型状態 | `REGIME:expansion_regime` |
| CD-G02-020 | `participation_regime` | ENUM | POINT_IN_TIME | CLOCK+MARKET_STATE | 取引参加量regime | `REGIME:participation_regime` |
| CD-G02-021 | `volatility_regime` | ENUM | POINT_IN_TIME | CLOCK+MARKET_STATE | volatility regime | `REGIME:volatility_regime` |
| CD-G02-022 | `liquidity_regime` | ENUM | POINT_IN_TIME | CLOCK+MARKET_STATE | liquidity regime | `REGIME:liquidity_regime` |
| CD-G02-023 | `regime_age` | FLOAT | POINT_IN_TIME | CLOCK+MARKET_STATE | 現regime継続時間 | `REGIME:regime_age` |
| CD-G02-024 | `regime_transition_flag` | FLAG | POINT_IN_TIME | CLOCK+MARKET_STATE | regime転換検出 | `REGIME:regime_transition_flag` |

### G03 Price and Location

| ID | condition_key | type | window | source | 定義 | independence_lineage |
|---|---|---|---|---|---|---|
| CD-G03-001 | `distance_to_best_bid` | FLOAT | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | best bidまでの符号付きtick距離 | `LOCATION:best_bid` |
| CD-G03-002 | `relation_to_best_bid` | ENUM | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | best bidに対するABOVE AT BELOW | `LOCATION:best_bid` |
| CD-G03-003 | `distance_to_best_ask` | FLOAT | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | best askまでの符号付きtick距離 | `LOCATION:best_ask` |
| CD-G03-004 | `relation_to_best_ask` | ENUM | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | best askに対するABOVE AT BELOW | `LOCATION:best_ask` |
| CD-G03-005 | `distance_to_mid_price` | FLOAT | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | mid priceまでの符号付きtick距離 | `LOCATION:mid_price` |
| CD-G03-006 | `relation_to_mid_price` | ENUM | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | mid priceに対するABOVE AT BELOW | `LOCATION:mid_price` |
| CD-G03-007 | `distance_to_microprice` | FLOAT | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | micropriceまでの符号付きtick距離 | `LOCATION:microprice` |
| CD-G03-008 | `relation_to_microprice` | ENUM | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | micropriceに対するABOVE AT BELOW | `LOCATION:microprice` |
| CD-G03-009 | `distance_to_session_open` | FLOAT | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | session openまでの符号付きtick距離 | `LOCATION:session_open` |
| CD-G03-010 | `relation_to_session_open` | ENUM | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | session openに対するABOVE AT BELOW | `LOCATION:session_open` |
| CD-G03-011 | `distance_to_session_high` | FLOAT | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | session highまでの符号付きtick距離 | `LOCATION:session_high` |
| CD-G03-012 | `relation_to_session_high` | ENUM | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | session highに対するABOVE AT BELOW | `LOCATION:session_high` |
| CD-G03-013 | `distance_to_session_low` | FLOAT | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | session lowまでの符号付きtick距離 | `LOCATION:session_low` |
| CD-G03-014 | `relation_to_session_low` | ENUM | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | session lowに対するABOVE AT BELOW | `LOCATION:session_low` |
| CD-G03-015 | `distance_to_previous_day_high` | FLOAT | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | previous day highまでの符号付きtick距離 | `LOCATION:previous_day_high` |
| CD-G03-016 | `relation_to_previous_day_high` | ENUM | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | previous day highに対するABOVE AT BELOW | `LOCATION:previous_day_high` |
| CD-G03-017 | `distance_to_previous_day_low` | FLOAT | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | previous day lowまでの符号付きtick距離 | `LOCATION:previous_day_low` |
| CD-G03-018 | `relation_to_previous_day_low` | ENUM | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | previous day lowに対するABOVE AT BELOW | `LOCATION:previous_day_low` |
| CD-G03-019 | `distance_to_previous_day_close` | FLOAT | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | previous day closeまでの符号付きtick距離 | `LOCATION:previous_day_close` |
| CD-G03-020 | `relation_to_previous_day_close` | ENUM | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | previous day closeに対するABOVE AT BELOW | `LOCATION:previous_day_close` |
| CD-G03-021 | `distance_to_rolling_1m_high` | FLOAT | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | 直近1分highまでの符号付きtick距離 | `LOCATION:rolling_1m_high` |
| CD-G03-022 | `relation_to_rolling_1m_high` | ENUM | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | 直近1分highに対するABOVE AT BELOW | `LOCATION:rolling_1m_high` |
| CD-G03-023 | `distance_to_rolling_1m_low` | FLOAT | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | 直近1分lowまでの符号付きtick距離 | `LOCATION:rolling_1m_low` |
| CD-G03-024 | `relation_to_rolling_1m_low` | ENUM | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | 直近1分lowに対するABOVE AT BELOW | `LOCATION:rolling_1m_low` |
| CD-G03-025 | `distance_to_rolling_5m_high` | FLOAT | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | 直近5分highまでの符号付きtick距離 | `LOCATION:rolling_5m_high` |
| CD-G03-026 | `relation_to_rolling_5m_high` | ENUM | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | 直近5分highに対するABOVE AT BELOW | `LOCATION:rolling_5m_high` |
| CD-G03-027 | `distance_to_rolling_5m_low` | FLOAT | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | 直近5分lowまでの符号付きtick距離 | `LOCATION:rolling_5m_low` |
| CD-G03-028 | `relation_to_rolling_5m_low` | ENUM | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | 直近5分lowに対するABOVE AT BELOW | `LOCATION:rolling_5m_low` |
| CD-G03-029 | `distance_to_rolling_15m_high` | FLOAT | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | 直近15分highまでの符号付きtick距離 | `LOCATION:rolling_15m_high` |
| CD-G03-030 | `relation_to_rolling_15m_high` | ENUM | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | 直近15分highに対するABOVE AT BELOW | `LOCATION:rolling_15m_high` |
| CD-G03-031 | `distance_to_rolling_15m_low` | FLOAT | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | 直近15分lowまでの符号付きtick距離 | `LOCATION:rolling_15m_low` |
| CD-G03-032 | `relation_to_rolling_15m_low` | ENUM | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | 直近15分lowに対するABOVE AT BELOW | `LOCATION:rolling_15m_low` |
| CD-G03-033 | `distance_to_rolling_1h_high` | FLOAT | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | 直近1時間highまでの符号付きtick距離 | `LOCATION:rolling_1h_high` |
| CD-G03-034 | `relation_to_rolling_1h_high` | ENUM | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | 直近1時間highに対するABOVE AT BELOW | `LOCATION:rolling_1h_high` |
| CD-G03-035 | `distance_to_rolling_1h_low` | FLOAT | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | 直近1時間lowまでの符号付きtick距離 | `LOCATION:rolling_1h_low` |
| CD-G03-036 | `relation_to_rolling_1h_low` | ENUM | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | 直近1時間lowに対するABOVE AT BELOW | `LOCATION:rolling_1h_low` |
| CD-G03-037 | `distance_to_session_vwap` | FLOAT | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | session VWAPまでの符号付きtick距離 | `LOCATION:session_vwap` |
| CD-G03-038 | `relation_to_session_vwap` | ENUM | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | session VWAPに対するABOVE AT BELOW | `LOCATION:session_vwap` |
| CD-G03-039 | `distance_to_session_open_avwap` | FLOAT | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | session open AVWAPまでの符号付きtick距離 | `LOCATION:session_open_avwap` |
| CD-G03-040 | `relation_to_session_open_avwap` | ENUM | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | session open AVWAPに対するABOVE AT BELOW | `LOCATION:session_open_avwap` |
| CD-G03-041 | `distance_to_profile_poc` | FLOAT | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | profile POCまでの符号付きtick距離 | `LOCATION:profile_poc` |
| CD-G03-042 | `relation_to_profile_poc` | ENUM | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | profile POCに対するABOVE AT BELOW | `LOCATION:profile_poc` |
| CD-G03-043 | `distance_to_profile_vah` | FLOAT | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | value area highまでの符号付きtick距離 | `LOCATION:profile_vah` |
| CD-G03-044 | `relation_to_profile_vah` | ENUM | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | value area highに対するABOVE AT BELOW | `LOCATION:profile_vah` |
| CD-G03-045 | `distance_to_profile_val` | FLOAT | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | value area lowまでの符号付きtick距離 | `LOCATION:profile_val` |
| CD-G03-046 | `relation_to_profile_val` | ENUM | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | value area lowに対するABOVE AT BELOW | `LOCATION:profile_val` |
| CD-G03-047 | `distance_to_active_range_mid` | FLOAT | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | active range midpointまでの符号付きtick距離 | `LOCATION:active_range_mid` |
| CD-G03-048 | `relation_to_active_range_mid` | ENUM | POINT_IN_TIME | DEPTH+AGGTRADE+PROFILE | active range midpointに対するABOVE AT BELOW | `LOCATION:active_range_mid` |

### G04 Volatility and Tradeability

| ID | condition_key | type | window | source | 定義 | independence_lineage |
|---|---|---|---|---|---|---|
| CD-G04-001 | `realized_volatility_1s` | FLOAT | 1s | AGGTRADE | 1s realized volatility | `VOLATILITY:REALIZED` |
| CD-G04-002 | `price_range_ticks_1s` | FLOAT | 1s | AGGTRADE | 1s high-low tick幅 | `VOLATILITY:RANGE` |
| CD-G04-003 | `realized_volatility_5s` | FLOAT | 5s | AGGTRADE | 5s realized volatility | `VOLATILITY:REALIZED` |
| CD-G04-004 | `price_range_ticks_5s` | FLOAT | 5s | AGGTRADE | 5s high-low tick幅 | `VOLATILITY:RANGE` |
| CD-G04-005 | `realized_volatility_30s` | FLOAT | 30s | AGGTRADE | 30s realized volatility | `VOLATILITY:REALIZED` |
| CD-G04-006 | `price_range_ticks_30s` | FLOAT | 30s | AGGTRADE | 30s high-low tick幅 | `VOLATILITY:RANGE` |
| CD-G04-007 | `realized_volatility_1m` | FLOAT | 1m | AGGTRADE | 1m realized volatility | `VOLATILITY:REALIZED` |
| CD-G04-008 | `price_range_ticks_1m` | FLOAT | 1m | AGGTRADE | 1m high-low tick幅 | `VOLATILITY:RANGE` |
| CD-G04-009 | `realized_volatility_5m` | FLOAT | 5m | AGGTRADE | 5m realized volatility | `VOLATILITY:REALIZED` |
| CD-G04-010 | `price_range_ticks_5m` | FLOAT | 5m | AGGTRADE | 5m high-low tick幅 | `VOLATILITY:RANGE` |
| CD-G04-011 | `spread_ticks` | FLOAT | POINT_IN_TIME | DEPTH | best spread tick数 | `LIQUIDITY:SPREAD` |
| CD-G04-012 | `spread_percentile_1m` | FLOAT | 1m | DEPTH | 1m spread percentile | `LIQUIDITY:SPREAD` |
| CD-G04-013 | `spread_percentile_5m` | FLOAT | 5m | DEPTH | 5m spread percentile | `LIQUIDITY:SPREAD` |
| CD-G04-014 | `spread_percentile_1h` | FLOAT | 1h | DEPTH | 1h spread percentile | `LIQUIDITY:SPREAD` |
| CD-G04-015 | `trade_rate_percentile_1m` | FLOAT | 1m | AGGTRADE | 1m trade rate percentile | `LIQUIDITY:TRADE_RATE` |
| CD-G04-016 | `trade_rate_percentile_5m` | FLOAT | 5m | AGGTRADE | 5m trade rate percentile | `LIQUIDITY:TRADE_RATE` |
| CD-G04-017 | `bid_top5_depth_percentile_1m` | FLOAT | 1m | DEPTH | bid top5 depth percentile 1m | `LIQUIDITY:TOP5_DEPTH:bid` |
| CD-G04-018 | `bid_top5_depth_percentile_5m` | FLOAT | 5m | DEPTH | bid top5 depth percentile 5m | `LIQUIDITY:TOP5_DEPTH:bid` |
| CD-G04-019 | `ask_top5_depth_percentile_1m` | FLOAT | 1m | DEPTH | ask top5 depth percentile 1m | `LIQUIDITY:TOP5_DEPTH:ask` |
| CD-G04-020 | `ask_top5_depth_percentile_5m` | FLOAT | 5m | DEPTH | ask top5 depth percentile 5m | `LIQUIDITY:TOP5_DEPTH:ask` |
| CD-G04-021 | `estimated_buy_impact_ticks` | FLOAT | POINT_IN_TIME | DEPTH+AGGTRADE | 基準notional買いの推定impact | `LIQUIDITY:IMPACT:BUY` |
| CD-G04-022 | `estimated_sell_impact_ticks` | FLOAT | POINT_IN_TIME | DEPTH+AGGTRADE | 基準notional売りの推定impact | `LIQUIDITY:IMPACT:SELL` |
| CD-G04-023 | `volatility_state` | ENUM | POINT_IN_TIME | AGGTRADE | LOW NORMAL HIGH EXTREME | `VOLATILITY:STATE` |
| CD-G04-024 | `tradeability_state` | ENUM | POINT_IN_TIME | DEPTH+AGGTRADE | DEEP NORMAL THIN DISLOCATED | `LIQUIDITY:STATE` |

### G05 Raw Limit Order Book

| ID | condition_key | type | window | source | 定義 | independence_lineage |
|---|---|---|---|---|---|---|
| CD-G05-001 | `bid_l1_price` | FLOAT | POINT_IN_TIME | DEPTH | bid第1level price | `BOOK_RAW:bid:L1:price` |
| CD-G05-002 | `bid_l2_price` | FLOAT | POINT_IN_TIME | DEPTH | bid第2level price | `BOOK_RAW:bid:L2:price` |
| CD-G05-003 | `bid_l3_price` | FLOAT | POINT_IN_TIME | DEPTH | bid第3level price | `BOOK_RAW:bid:L3:price` |
| CD-G05-004 | `bid_l4_price` | FLOAT | POINT_IN_TIME | DEPTH | bid第4level price | `BOOK_RAW:bid:L4:price` |
| CD-G05-005 | `bid_l5_price` | FLOAT | POINT_IN_TIME | DEPTH | bid第5level price | `BOOK_RAW:bid:L5:price` |
| CD-G05-006 | `bid_l6_price` | FLOAT | POINT_IN_TIME | DEPTH | bid第6level price | `BOOK_RAW:bid:L6:price` |
| CD-G05-007 | `bid_l7_price` | FLOAT | POINT_IN_TIME | DEPTH | bid第7level price | `BOOK_RAW:bid:L7:price` |
| CD-G05-008 | `bid_l8_price` | FLOAT | POINT_IN_TIME | DEPTH | bid第8level price | `BOOK_RAW:bid:L8:price` |
| CD-G05-009 | `bid_l9_price` | FLOAT | POINT_IN_TIME | DEPTH | bid第9level price | `BOOK_RAW:bid:L9:price` |
| CD-G05-010 | `bid_l10_price` | FLOAT | POINT_IN_TIME | DEPTH | bid第10level price | `BOOK_RAW:bid:L10:price` |
| CD-G05-011 | `bid_l1_quantity` | FLOAT | POINT_IN_TIME | DEPTH | bid第1level quantity | `BOOK_RAW:bid:L1:quantity` |
| CD-G05-012 | `bid_l2_quantity` | FLOAT | POINT_IN_TIME | DEPTH | bid第2level quantity | `BOOK_RAW:bid:L2:quantity` |
| CD-G05-013 | `bid_l3_quantity` | FLOAT | POINT_IN_TIME | DEPTH | bid第3level quantity | `BOOK_RAW:bid:L3:quantity` |
| CD-G05-014 | `bid_l4_quantity` | FLOAT | POINT_IN_TIME | DEPTH | bid第4level quantity | `BOOK_RAW:bid:L4:quantity` |
| CD-G05-015 | `bid_l5_quantity` | FLOAT | POINT_IN_TIME | DEPTH | bid第5level quantity | `BOOK_RAW:bid:L5:quantity` |
| CD-G05-016 | `bid_l6_quantity` | FLOAT | POINT_IN_TIME | DEPTH | bid第6level quantity | `BOOK_RAW:bid:L6:quantity` |
| CD-G05-017 | `bid_l7_quantity` | FLOAT | POINT_IN_TIME | DEPTH | bid第7level quantity | `BOOK_RAW:bid:L7:quantity` |
| CD-G05-018 | `bid_l8_quantity` | FLOAT | POINT_IN_TIME | DEPTH | bid第8level quantity | `BOOK_RAW:bid:L8:quantity` |
| CD-G05-019 | `bid_l9_quantity` | FLOAT | POINT_IN_TIME | DEPTH | bid第9level quantity | `BOOK_RAW:bid:L9:quantity` |
| CD-G05-020 | `bid_l10_quantity` | FLOAT | POINT_IN_TIME | DEPTH | bid第10level quantity | `BOOK_RAW:bid:L10:quantity` |
| CD-G05-021 | `ask_l1_price` | FLOAT | POINT_IN_TIME | DEPTH | ask第1level price | `BOOK_RAW:ask:L1:price` |
| CD-G05-022 | `ask_l2_price` | FLOAT | POINT_IN_TIME | DEPTH | ask第2level price | `BOOK_RAW:ask:L2:price` |
| CD-G05-023 | `ask_l3_price` | FLOAT | POINT_IN_TIME | DEPTH | ask第3level price | `BOOK_RAW:ask:L3:price` |
| CD-G05-024 | `ask_l4_price` | FLOAT | POINT_IN_TIME | DEPTH | ask第4level price | `BOOK_RAW:ask:L4:price` |
| CD-G05-025 | `ask_l5_price` | FLOAT | POINT_IN_TIME | DEPTH | ask第5level price | `BOOK_RAW:ask:L5:price` |
| CD-G05-026 | `ask_l6_price` | FLOAT | POINT_IN_TIME | DEPTH | ask第6level price | `BOOK_RAW:ask:L6:price` |
| CD-G05-027 | `ask_l7_price` | FLOAT | POINT_IN_TIME | DEPTH | ask第7level price | `BOOK_RAW:ask:L7:price` |
| CD-G05-028 | `ask_l8_price` | FLOAT | POINT_IN_TIME | DEPTH | ask第8level price | `BOOK_RAW:ask:L8:price` |
| CD-G05-029 | `ask_l9_price` | FLOAT | POINT_IN_TIME | DEPTH | ask第9level price | `BOOK_RAW:ask:L9:price` |
| CD-G05-030 | `ask_l10_price` | FLOAT | POINT_IN_TIME | DEPTH | ask第10level price | `BOOK_RAW:ask:L10:price` |
| CD-G05-031 | `ask_l1_quantity` | FLOAT | POINT_IN_TIME | DEPTH | ask第1level quantity | `BOOK_RAW:ask:L1:quantity` |
| CD-G05-032 | `ask_l2_quantity` | FLOAT | POINT_IN_TIME | DEPTH | ask第2level quantity | `BOOK_RAW:ask:L2:quantity` |
| CD-G05-033 | `ask_l3_quantity` | FLOAT | POINT_IN_TIME | DEPTH | ask第3level quantity | `BOOK_RAW:ask:L3:quantity` |
| CD-G05-034 | `ask_l4_quantity` | FLOAT | POINT_IN_TIME | DEPTH | ask第4level quantity | `BOOK_RAW:ask:L4:quantity` |
| CD-G05-035 | `ask_l5_quantity` | FLOAT | POINT_IN_TIME | DEPTH | ask第5level quantity | `BOOK_RAW:ask:L5:quantity` |
| CD-G05-036 | `ask_l6_quantity` | FLOAT | POINT_IN_TIME | DEPTH | ask第6level quantity | `BOOK_RAW:ask:L6:quantity` |
| CD-G05-037 | `ask_l7_quantity` | FLOAT | POINT_IN_TIME | DEPTH | ask第7level quantity | `BOOK_RAW:ask:L7:quantity` |
| CD-G05-038 | `ask_l8_quantity` | FLOAT | POINT_IN_TIME | DEPTH | ask第8level quantity | `BOOK_RAW:ask:L8:quantity` |
| CD-G05-039 | `ask_l9_quantity` | FLOAT | POINT_IN_TIME | DEPTH | ask第9level quantity | `BOOK_RAW:ask:L9:quantity` |
| CD-G05-040 | `ask_l10_quantity` | FLOAT | POINT_IN_TIME | DEPTH | ask第10level quantity | `BOOK_RAW:ask:L10:quantity` |

### G06 Book Shape and Static Imbalance

P3-Cのwall候補と距離の機械算出契約は
`WALL_DISTANCE_SEMANTICS_CONTRACT_V0_1_20260727.md`を正本とする。
wall candidateはbest-first top10内の最大数量level、同量時はbestに最も近いlevelである。
これはthreshold-free raw観測であり、G16 wall成立や注文者同一性を断定しない。

| ID | condition_key | type | window | source | 定義 | independence_lineage |
|---|---|---|---|---|---|---|
| CD-G06-001 | `bid_cumulative_depth_top1` | FLOAT | POINT_IN_TIME | DEPTH | bid top1累積depth | `BOOK_SHAPE:CUM_DEPTH:bid` |
| CD-G06-002 | `bid_cumulative_depth_top3` | FLOAT | POINT_IN_TIME | DEPTH | bid top3累積depth | `BOOK_SHAPE:CUM_DEPTH:bid` |
| CD-G06-003 | `bid_cumulative_depth_top5` | FLOAT | POINT_IN_TIME | DEPTH | bid top5累積depth | `BOOK_SHAPE:CUM_DEPTH:bid` |
| CD-G06-004 | `bid_cumulative_depth_top10` | FLOAT | POINT_IN_TIME | DEPTH | bid top10累積depth | `BOOK_SHAPE:CUM_DEPTH:bid` |
| CD-G06-005 | `ask_cumulative_depth_top1` | FLOAT | POINT_IN_TIME | DEPTH | ask top1累積depth | `BOOK_SHAPE:CUM_DEPTH:ask` |
| CD-G06-006 | `ask_cumulative_depth_top3` | FLOAT | POINT_IN_TIME | DEPTH | ask top3累積depth | `BOOK_SHAPE:CUM_DEPTH:ask` |
| CD-G06-007 | `ask_cumulative_depth_top5` | FLOAT | POINT_IN_TIME | DEPTH | ask top5累積depth | `BOOK_SHAPE:CUM_DEPTH:ask` |
| CD-G06-008 | `ask_cumulative_depth_top10` | FLOAT | POINT_IN_TIME | DEPTH | ask top10累積depth | `BOOK_SHAPE:CUM_DEPTH:ask` |
| CD-G06-009 | `queue_imbalance_top1` | FLOAT | POINT_IN_TIME | DEPTH | top1 queue imbalance | `BOOK_SHAPE:QUEUE_IMBALANCE` |
| CD-G06-010 | `microprice_top1` | FLOAT | POINT_IN_TIME | DEPTH | top1 depth加重microprice | `BOOK_SHAPE:MICROPRICE` |
| CD-G06-011 | `queue_imbalance_top3` | FLOAT | POINT_IN_TIME | DEPTH | top3 queue imbalance | `BOOK_SHAPE:QUEUE_IMBALANCE` |
| CD-G06-012 | `microprice_top3` | FLOAT | POINT_IN_TIME | DEPTH | top3 depth加重microprice | `BOOK_SHAPE:MICROPRICE` |
| CD-G06-013 | `queue_imbalance_top5` | FLOAT | POINT_IN_TIME | DEPTH | top5 queue imbalance | `BOOK_SHAPE:QUEUE_IMBALANCE` |
| CD-G06-014 | `microprice_top5` | FLOAT | POINT_IN_TIME | DEPTH | top5 depth加重microprice | `BOOK_SHAPE:MICROPRICE` |
| CD-G06-015 | `queue_imbalance_top10` | FLOAT | POINT_IN_TIME | DEPTH | top10 queue imbalance | `BOOK_SHAPE:QUEUE_IMBALANCE` |
| CD-G06-016 | `microprice_top10` | FLOAT | POINT_IN_TIME | DEPTH | top10 depth加重microprice | `BOOK_SHAPE:MICROPRICE` |
| CD-G06-017 | `bid_depth_slope_top3` | FLOAT | POINT_IN_TIME | DEPTH | bid top3 depth slope | `BOOK_SHAPE:SLOPE:bid` |
| CD-G06-018 | `bid_depth_convexity_top3` | FLOAT | POINT_IN_TIME | DEPTH | bid top3 depth convexity | `BOOK_SHAPE:CONVEXITY:bid` |
| CD-G06-019 | `bid_depth_slope_top5` | FLOAT | POINT_IN_TIME | DEPTH | bid top5 depth slope | `BOOK_SHAPE:SLOPE:bid` |
| CD-G06-020 | `bid_depth_convexity_top5` | FLOAT | POINT_IN_TIME | DEPTH | bid top5 depth convexity | `BOOK_SHAPE:CONVEXITY:bid` |
| CD-G06-021 | `bid_depth_slope_top10` | FLOAT | POINT_IN_TIME | DEPTH | bid top10 depth slope | `BOOK_SHAPE:SLOPE:bid` |
| CD-G06-022 | `bid_depth_convexity_top10` | FLOAT | POINT_IN_TIME | DEPTH | bid top10 depth convexity | `BOOK_SHAPE:CONVEXITY:bid` |
| CD-G06-023 | `ask_depth_slope_top3` | FLOAT | POINT_IN_TIME | DEPTH | ask top3 depth slope | `BOOK_SHAPE:SLOPE:ask` |
| CD-G06-024 | `ask_depth_convexity_top3` | FLOAT | POINT_IN_TIME | DEPTH | ask top3 depth convexity | `BOOK_SHAPE:CONVEXITY:ask` |
| CD-G06-025 | `ask_depth_slope_top5` | FLOAT | POINT_IN_TIME | DEPTH | ask top5 depth slope | `BOOK_SHAPE:SLOPE:ask` |
| CD-G06-026 | `ask_depth_convexity_top5` | FLOAT | POINT_IN_TIME | DEPTH | ask top5 depth convexity | `BOOK_SHAPE:CONVEXITY:ask` |
| CD-G06-027 | `ask_depth_slope_top10` | FLOAT | POINT_IN_TIME | DEPTH | ask top10 depth slope | `BOOK_SHAPE:SLOPE:ask` |
| CD-G06-028 | `ask_depth_convexity_top10` | FLOAT | POINT_IN_TIME | DEPTH | ask top10 depth convexity | `BOOK_SHAPE:CONVEXITY:ask` |
| CD-G06-029 | `bid_wall_concentration_top10` | FLOAT | POINT_IN_TIME | DEPTH | bid top10最大数量wall candidateのtop10累積数量比率。同量時はbest寄り | `BOOK_SHAPE:WALL_CONCENTRATION:bid` |
| CD-G06-030 | `distance_to_nearest_bid_wall` | FLOAT | POINT_IN_TIME | DEPTH | best bidから同じbid wall candidateまでの非負ticks | `BOOK_SHAPE:WALL_DISTANCE:bid` |
| CD-G06-031 | `ask_wall_concentration_top10` | FLOAT | POINT_IN_TIME | DEPTH | ask top10最大数量wall candidateのtop10累積数量比率。同量時はbest寄り | `BOOK_SHAPE:WALL_CONCENTRATION:ask` |
| CD-G06-032 | `distance_to_nearest_ask_wall` | FLOAT | POINT_IN_TIME | DEPTH | best askから同じask wall candidateまでの非負ticks | `BOOK_SHAPE:WALL_DISTANCE:ask` |

### G07 Book Event Flow

P3-Cの機械算出契約は
`BOOK_EVENT_HISTORY_RESET_CONTRACT_V0_1_20260727.md`を正本とする。
applied depth DIFFの前後数量差をsource-timeで集計し、gap／resyncでは履歴を破棄する。
Market-by-Price上の`cancel_volume`は表示数量減少量であり、注文者の取消意図を断定しない。
window未完成時はkeyを出力しない。

| ID | condition_key | type | window | source | 定義 | independence_lineage |
|---|---|---|---|---|---|---|
| CD-G07-001 | `bid_add_volume_100ms` | FLOAT | 100ms | DEPTH | bid 表示数量追加量 | `BOOK_EVENT:bid:add_volume` |
| CD-G07-002 | `bid_add_volume_1s` | FLOAT | 1s | DEPTH | bid 表示数量追加量 | `BOOK_EVENT:bid:add_volume` |
| CD-G07-003 | `bid_add_volume_5s` | FLOAT | 5s | DEPTH | bid 表示数量追加量 | `BOOK_EVENT:bid:add_volume` |
| CD-G07-004 | `bid_cancel_volume_100ms` | FLOAT | 100ms | DEPTH | bid 表示数量取消量 | `BOOK_EVENT:bid:cancel_volume` |
| CD-G07-005 | `bid_cancel_volume_1s` | FLOAT | 1s | DEPTH | bid 表示数量取消量 | `BOOK_EVENT:bid:cancel_volume` |
| CD-G07-006 | `bid_cancel_volume_5s` | FLOAT | 5s | DEPTH | bid 表示数量取消量 | `BOOK_EVENT:bid:cancel_volume` |
| CD-G07-007 | `bid_net_flow_100ms` | FLOAT | 100ms | DEPTH | bid 追加量マイナス取消量 | `BOOK_EVENT:bid:net_flow` |
| CD-G07-008 | `bid_net_flow_1s` | FLOAT | 1s | DEPTH | bid 追加量マイナス取消量 | `BOOK_EVENT:bid:net_flow` |
| CD-G07-009 | `bid_net_flow_5s` | FLOAT | 5s | DEPTH | bid 追加量マイナス取消量 | `BOOK_EVENT:bid:net_flow` |
| CD-G07-010 | `bid_refresh_count_100ms` | FLOAT | 100ms | DEPTH | bid best近傍補充回数 | `BOOK_EVENT:bid:refresh_count` |
| CD-G07-011 | `bid_refresh_count_1s` | FLOAT | 1s | DEPTH | bid best近傍補充回数 | `BOOK_EVENT:bid:refresh_count` |
| CD-G07-012 | `bid_refresh_count_5s` | FLOAT | 5s | DEPTH | bid best近傍補充回数 | `BOOK_EVENT:bid:refresh_count` |
| CD-G07-013 | `bid_pull_ratio_100ms` | FLOAT | 100ms | DEPTH | bid pull比率 | `BOOK_EVENT:bid:pull_ratio` |
| CD-G07-014 | `bid_pull_ratio_1s` | FLOAT | 1s | DEPTH | bid pull比率 | `BOOK_EVENT:bid:pull_ratio` |
| CD-G07-015 | `bid_pull_ratio_5s` | FLOAT | 5s | DEPTH | bid pull比率 | `BOOK_EVENT:bid:pull_ratio` |
| CD-G07-016 | `bid_stack_ratio_100ms` | FLOAT | 100ms | DEPTH | bid stack比率 | `BOOK_EVENT:bid:stack_ratio` |
| CD-G07-017 | `bid_stack_ratio_1s` | FLOAT | 1s | DEPTH | bid stack比率 | `BOOK_EVENT:bid:stack_ratio` |
| CD-G07-018 | `bid_stack_ratio_5s` | FLOAT | 5s | DEPTH | bid stack比率 | `BOOK_EVENT:bid:stack_ratio` |
| CD-G07-019 | `bid_level_turnover_100ms` | FLOAT | 100ms | DEPTH | bid price level入替率 | `BOOK_EVENT:bid:level_turnover` |
| CD-G07-020 | `bid_level_turnover_1s` | FLOAT | 1s | DEPTH | bid price level入替率 | `BOOK_EVENT:bid:level_turnover` |
| CD-G07-021 | `bid_level_turnover_5s` | FLOAT | 5s | DEPTH | bid price level入替率 | `BOOK_EVENT:bid:level_turnover` |
| CD-G07-022 | `bid_depth_change_100ms` | FLOAT | 100ms | DEPTH | bid window前後depth変化 | `BOOK_EVENT:bid:depth_change` |
| CD-G07-023 | `bid_depth_change_1s` | FLOAT | 1s | DEPTH | bid window前後depth変化 | `BOOK_EVENT:bid:depth_change` |
| CD-G07-024 | `bid_depth_change_5s` | FLOAT | 5s | DEPTH | bid window前後depth変化 | `BOOK_EVENT:bid:depth_change` |
| CD-G07-025 | `ask_add_volume_100ms` | FLOAT | 100ms | DEPTH | ask 表示数量追加量 | `BOOK_EVENT:ask:add_volume` |
| CD-G07-026 | `ask_add_volume_1s` | FLOAT | 1s | DEPTH | ask 表示数量追加量 | `BOOK_EVENT:ask:add_volume` |
| CD-G07-027 | `ask_add_volume_5s` | FLOAT | 5s | DEPTH | ask 表示数量追加量 | `BOOK_EVENT:ask:add_volume` |
| CD-G07-028 | `ask_cancel_volume_100ms` | FLOAT | 100ms | DEPTH | ask 表示数量取消量 | `BOOK_EVENT:ask:cancel_volume` |
| CD-G07-029 | `ask_cancel_volume_1s` | FLOAT | 1s | DEPTH | ask 表示数量取消量 | `BOOK_EVENT:ask:cancel_volume` |
| CD-G07-030 | `ask_cancel_volume_5s` | FLOAT | 5s | DEPTH | ask 表示数量取消量 | `BOOK_EVENT:ask:cancel_volume` |
| CD-G07-031 | `ask_net_flow_100ms` | FLOAT | 100ms | DEPTH | ask 追加量マイナス取消量 | `BOOK_EVENT:ask:net_flow` |
| CD-G07-032 | `ask_net_flow_1s` | FLOAT | 1s | DEPTH | ask 追加量マイナス取消量 | `BOOK_EVENT:ask:net_flow` |
| CD-G07-033 | `ask_net_flow_5s` | FLOAT | 5s | DEPTH | ask 追加量マイナス取消量 | `BOOK_EVENT:ask:net_flow` |
| CD-G07-034 | `ask_refresh_count_100ms` | FLOAT | 100ms | DEPTH | ask best近傍補充回数 | `BOOK_EVENT:ask:refresh_count` |
| CD-G07-035 | `ask_refresh_count_1s` | FLOAT | 1s | DEPTH | ask best近傍補充回数 | `BOOK_EVENT:ask:refresh_count` |
| CD-G07-036 | `ask_refresh_count_5s` | FLOAT | 5s | DEPTH | ask best近傍補充回数 | `BOOK_EVENT:ask:refresh_count` |
| CD-G07-037 | `ask_pull_ratio_100ms` | FLOAT | 100ms | DEPTH | ask pull比率 | `BOOK_EVENT:ask:pull_ratio` |
| CD-G07-038 | `ask_pull_ratio_1s` | FLOAT | 1s | DEPTH | ask pull比率 | `BOOK_EVENT:ask:pull_ratio` |
| CD-G07-039 | `ask_pull_ratio_5s` | FLOAT | 5s | DEPTH | ask pull比率 | `BOOK_EVENT:ask:pull_ratio` |
| CD-G07-040 | `ask_stack_ratio_100ms` | FLOAT | 100ms | DEPTH | ask stack比率 | `BOOK_EVENT:ask:stack_ratio` |
| CD-G07-041 | `ask_stack_ratio_1s` | FLOAT | 1s | DEPTH | ask stack比率 | `BOOK_EVENT:ask:stack_ratio` |
| CD-G07-042 | `ask_stack_ratio_5s` | FLOAT | 5s | DEPTH | ask stack比率 | `BOOK_EVENT:ask:stack_ratio` |
| CD-G07-043 | `ask_level_turnover_100ms` | FLOAT | 100ms | DEPTH | ask price level入替率 | `BOOK_EVENT:ask:level_turnover` |
| CD-G07-044 | `ask_level_turnover_1s` | FLOAT | 1s | DEPTH | ask price level入替率 | `BOOK_EVENT:ask:level_turnover` |
| CD-G07-045 | `ask_level_turnover_5s` | FLOAT | 5s | DEPTH | ask price level入替率 | `BOOK_EVENT:ask:level_turnover` |
| CD-G07-046 | `ask_depth_change_100ms` | FLOAT | 100ms | DEPTH | ask window前後depth変化 | `BOOK_EVENT:ask:depth_change` |
| CD-G07-047 | `ask_depth_change_1s` | FLOAT | 1s | DEPTH | ask window前後depth変化 | `BOOK_EVENT:ask:depth_change` |
| CD-G07-048 | `ask_depth_change_5s` | FLOAT | 5s | DEPTH | ask window前後depth変化 | `BOOK_EVENT:ask:depth_change` |

### G08 Aggressive Trade Tape

| ID | condition_key | type | window | source | 定義 | independence_lineage |
|---|---|---|---|---|---|---|
| CD-G08-001 | `buy_market_volume_100ms` | FLOAT | 100ms | AGGTRADE | buy aggressive volume | `TAPE:buy:market_volume` |
| CD-G08-002 | `buy_market_volume_1s` | FLOAT | 1s | AGGTRADE | buy aggressive volume | `TAPE:buy:market_volume` |
| CD-G08-003 | `buy_market_volume_5s` | FLOAT | 5s | AGGTRADE | buy aggressive volume | `TAPE:buy:market_volume` |
| CD-G08-004 | `buy_trade_count_100ms` | FLOAT | 100ms | AGGTRADE | buy aggTrade件数 | `TAPE:buy:trade_count` |
| CD-G08-005 | `buy_trade_count_1s` | FLOAT | 1s | AGGTRADE | buy aggTrade件数 | `TAPE:buy:trade_count` |
| CD-G08-006 | `buy_trade_count_5s` | FLOAT | 5s | AGGTRADE | buy aggTrade件数 | `TAPE:buy:trade_count` |
| CD-G08-007 | `buy_average_trade_size_100ms` | FLOAT | 100ms | AGGTRADE | buy 平均trade size | `TAPE:buy:average_trade_size` |
| CD-G08-008 | `buy_average_trade_size_1s` | FLOAT | 1s | AGGTRADE | buy 平均trade size | `TAPE:buy:average_trade_size` |
| CD-G08-009 | `buy_average_trade_size_5s` | FLOAT | 5s | AGGTRADE | buy 平均trade size | `TAPE:buy:average_trade_size` |
| CD-G08-010 | `buy_max_trade_size_100ms` | FLOAT | 100ms | AGGTRADE | buy 最大trade size | `TAPE:buy:max_trade_size` |
| CD-G08-011 | `buy_max_trade_size_1s` | FLOAT | 1s | AGGTRADE | buy 最大trade size | `TAPE:buy:max_trade_size` |
| CD-G08-012 | `buy_max_trade_size_5s` | FLOAT | 5s | AGGTRADE | buy 最大trade size | `TAPE:buy:max_trade_size` |
| CD-G08-013 | `buy_large_trade_count_100ms` | FLOAT | 100ms | AGGTRADE | buy large trade件数 | `TAPE:buy:large_trade_count` |
| CD-G08-014 | `buy_large_trade_count_1s` | FLOAT | 1s | AGGTRADE | buy large trade件数 | `TAPE:buy:large_trade_count` |
| CD-G08-015 | `buy_large_trade_count_5s` | FLOAT | 5s | AGGTRADE | buy large trade件数 | `TAPE:buy:large_trade_count` |
| CD-G08-016 | `buy_trade_rate_100ms` | FLOAT | 100ms | AGGTRADE | buy 秒換算trade rate | `TAPE:buy:trade_rate` |
| CD-G08-017 | `buy_trade_rate_1s` | FLOAT | 1s | AGGTRADE | buy 秒換算trade rate | `TAPE:buy:trade_rate` |
| CD-G08-018 | `buy_trade_rate_5s` | FLOAT | 5s | AGGTRADE | buy 秒換算trade rate | `TAPE:buy:trade_rate` |
| CD-G08-019 | `buy_notional_100ms` | FLOAT | 100ms | AGGTRADE | buy aggressive notional | `TAPE:buy:notional` |
| CD-G08-020 | `buy_notional_1s` | FLOAT | 1s | AGGTRADE | buy aggressive notional | `TAPE:buy:notional` |
| CD-G08-021 | `buy_notional_5s` | FLOAT | 5s | AGGTRADE | buy aggressive notional | `TAPE:buy:notional` |
| CD-G08-022 | `buy_side_share_100ms` | FLOAT | 100ms | AGGTRADE | buy 全flow内side比率 | `TAPE:buy:side_share` |
| CD-G08-023 | `buy_side_share_1s` | FLOAT | 1s | AGGTRADE | buy 全flow内side比率 | `TAPE:buy:side_share` |
| CD-G08-024 | `buy_side_share_5s` | FLOAT | 5s | AGGTRADE | buy 全flow内side比率 | `TAPE:buy:side_share` |
| CD-G08-025 | `sell_market_volume_100ms` | FLOAT | 100ms | AGGTRADE | sell aggressive volume | `TAPE:sell:market_volume` |
| CD-G08-026 | `sell_market_volume_1s` | FLOAT | 1s | AGGTRADE | sell aggressive volume | `TAPE:sell:market_volume` |
| CD-G08-027 | `sell_market_volume_5s` | FLOAT | 5s | AGGTRADE | sell aggressive volume | `TAPE:sell:market_volume` |
| CD-G08-028 | `sell_trade_count_100ms` | FLOAT | 100ms | AGGTRADE | sell aggTrade件数 | `TAPE:sell:trade_count` |
| CD-G08-029 | `sell_trade_count_1s` | FLOAT | 1s | AGGTRADE | sell aggTrade件数 | `TAPE:sell:trade_count` |
| CD-G08-030 | `sell_trade_count_5s` | FLOAT | 5s | AGGTRADE | sell aggTrade件数 | `TAPE:sell:trade_count` |
| CD-G08-031 | `sell_average_trade_size_100ms` | FLOAT | 100ms | AGGTRADE | sell 平均trade size | `TAPE:sell:average_trade_size` |
| CD-G08-032 | `sell_average_trade_size_1s` | FLOAT | 1s | AGGTRADE | sell 平均trade size | `TAPE:sell:average_trade_size` |
| CD-G08-033 | `sell_average_trade_size_5s` | FLOAT | 5s | AGGTRADE | sell 平均trade size | `TAPE:sell:average_trade_size` |
| CD-G08-034 | `sell_max_trade_size_100ms` | FLOAT | 100ms | AGGTRADE | sell 最大trade size | `TAPE:sell:max_trade_size` |
| CD-G08-035 | `sell_max_trade_size_1s` | FLOAT | 1s | AGGTRADE | sell 最大trade size | `TAPE:sell:max_trade_size` |
| CD-G08-036 | `sell_max_trade_size_5s` | FLOAT | 5s | AGGTRADE | sell 最大trade size | `TAPE:sell:max_trade_size` |
| CD-G08-037 | `sell_large_trade_count_100ms` | FLOAT | 100ms | AGGTRADE | sell large trade件数 | `TAPE:sell:large_trade_count` |
| CD-G08-038 | `sell_large_trade_count_1s` | FLOAT | 1s | AGGTRADE | sell large trade件数 | `TAPE:sell:large_trade_count` |
| CD-G08-039 | `sell_large_trade_count_5s` | FLOAT | 5s | AGGTRADE | sell large trade件数 | `TAPE:sell:large_trade_count` |
| CD-G08-040 | `sell_trade_rate_100ms` | FLOAT | 100ms | AGGTRADE | sell 秒換算trade rate | `TAPE:sell:trade_rate` |
| CD-G08-041 | `sell_trade_rate_1s` | FLOAT | 1s | AGGTRADE | sell 秒換算trade rate | `TAPE:sell:trade_rate` |
| CD-G08-042 | `sell_trade_rate_5s` | FLOAT | 5s | AGGTRADE | sell 秒換算trade rate | `TAPE:sell:trade_rate` |
| CD-G08-043 | `sell_notional_100ms` | FLOAT | 100ms | AGGTRADE | sell aggressive notional | `TAPE:sell:notional` |
| CD-G08-044 | `sell_notional_1s` | FLOAT | 1s | AGGTRADE | sell aggressive notional | `TAPE:sell:notional` |
| CD-G08-045 | `sell_notional_5s` | FLOAT | 5s | AGGTRADE | sell aggressive notional | `TAPE:sell:notional` |
| CD-G08-046 | `sell_side_share_100ms` | FLOAT | 100ms | AGGTRADE | sell 全flow内side比率 | `TAPE:sell:side_share` |
| CD-G08-047 | `sell_side_share_1s` | FLOAT | 1s | AGGTRADE | sell 全flow内side比率 | `TAPE:sell:side_share` |
| CD-G08-048 | `sell_side_share_5s` | FLOAT | 5s | AGGTRADE | sell 全flow内side比率 | `TAPE:sell:side_share` |

### G09 Flow Price Response

P3-Cのprice progress機械算出契約は
`PRICE_RESPONSE_HISTORY_CONTRACT_V0_1_20260727.md`を正本とする。
normalized tradeのsource-time as-of価格差をtick sizeで割り、正方向をupward、負方向の絶対値を
downwardとして出力する。baseline欠測、tick size欠測、window未完成時はkeyを出力しない。

| ID | condition_key | type | window | source | 定義 | independence_lineage |
|---|---|---|---|---|---|---|
| CD-G09-001 | `upward_progress_ticks_100ms` | FLOAT | 100ms | DEPTH+AGGTRADE | 上方向price progress | `PRICE_RESPONSE:upward_progress_ticks` |
| CD-G09-002 | `upward_progress_ticks_1s` | FLOAT | 1s | DEPTH+AGGTRADE | 上方向price progress | `PRICE_RESPONSE:upward_progress_ticks` |
| CD-G09-003 | `upward_progress_ticks_5s` | FLOAT | 5s | DEPTH+AGGTRADE | 上方向price progress | `PRICE_RESPONSE:upward_progress_ticks` |
| CD-G09-004 | `upward_progress_ticks_30s` | FLOAT | 30s | DEPTH+AGGTRADE | 上方向price progress | `PRICE_RESPONSE:upward_progress_ticks` |
| CD-G09-005 | `downward_progress_ticks_100ms` | FLOAT | 100ms | DEPTH+AGGTRADE | 下方向price progress | `PRICE_RESPONSE:downward_progress_ticks` |
| CD-G09-006 | `downward_progress_ticks_1s` | FLOAT | 1s | DEPTH+AGGTRADE | 下方向price progress | `PRICE_RESPONSE:downward_progress_ticks` |
| CD-G09-007 | `downward_progress_ticks_5s` | FLOAT | 5s | DEPTH+AGGTRADE | 下方向price progress | `PRICE_RESPONSE:downward_progress_ticks` |
| CD-G09-008 | `downward_progress_ticks_30s` | FLOAT | 30s | DEPTH+AGGTRADE | 下方向price progress | `PRICE_RESPONSE:downward_progress_ticks` |
| CD-G09-009 | `buy_impact_per_notional_100ms` | FLOAT | 100ms | DEPTH+AGGTRADE | buy flow当たり上方impact | `PRICE_RESPONSE:buy_impact_per_notional` |
| CD-G09-010 | `buy_impact_per_notional_1s` | FLOAT | 1s | DEPTH+AGGTRADE | buy flow当たり上方impact | `PRICE_RESPONSE:buy_impact_per_notional` |
| CD-G09-011 | `buy_impact_per_notional_5s` | FLOAT | 5s | DEPTH+AGGTRADE | buy flow当たり上方impact | `PRICE_RESPONSE:buy_impact_per_notional` |
| CD-G09-012 | `buy_impact_per_notional_30s` | FLOAT | 30s | DEPTH+AGGTRADE | buy flow当たり上方impact | `PRICE_RESPONSE:buy_impact_per_notional` |
| CD-G09-013 | `sell_impact_per_notional_100ms` | FLOAT | 100ms | DEPTH+AGGTRADE | sell flow当たり下方impact | `PRICE_RESPONSE:sell_impact_per_notional` |
| CD-G09-014 | `sell_impact_per_notional_1s` | FLOAT | 1s | DEPTH+AGGTRADE | sell flow当たり下方impact | `PRICE_RESPONSE:sell_impact_per_notional` |
| CD-G09-015 | `sell_impact_per_notional_5s` | FLOAT | 5s | DEPTH+AGGTRADE | sell flow当たり下方impact | `PRICE_RESPONSE:sell_impact_per_notional` |
| CD-G09-016 | `sell_impact_per_notional_30s` | FLOAT | 30s | DEPTH+AGGTRADE | sell flow当たり下方impact | `PRICE_RESPONSE:sell_impact_per_notional` |
| CD-G09-017 | `buy_efficiency_100ms` | FLOAT | 100ms | DEPTH+AGGTRADE | buy aggression進行効率 | `PRICE_RESPONSE:buy_efficiency` |
| CD-G09-018 | `buy_efficiency_1s` | FLOAT | 1s | DEPTH+AGGTRADE | buy aggression進行効率 | `PRICE_RESPONSE:buy_efficiency` |
| CD-G09-019 | `buy_efficiency_5s` | FLOAT | 5s | DEPTH+AGGTRADE | buy aggression進行効率 | `PRICE_RESPONSE:buy_efficiency` |
| CD-G09-020 | `buy_efficiency_30s` | FLOAT | 30s | DEPTH+AGGTRADE | buy aggression進行効率 | `PRICE_RESPONSE:buy_efficiency` |
| CD-G09-021 | `sell_efficiency_100ms` | FLOAT | 100ms | DEPTH+AGGTRADE | sell aggression進行効率 | `PRICE_RESPONSE:sell_efficiency` |
| CD-G09-022 | `sell_efficiency_1s` | FLOAT | 1s | DEPTH+AGGTRADE | sell aggression進行効率 | `PRICE_RESPONSE:sell_efficiency` |
| CD-G09-023 | `sell_efficiency_5s` | FLOAT | 5s | DEPTH+AGGTRADE | sell aggression進行効率 | `PRICE_RESPONSE:sell_efficiency` |
| CD-G09-024 | `sell_efficiency_30s` | FLOAT | 30s | DEPTH+AGGTRADE | sell aggression進行効率 | `PRICE_RESPONSE:sell_efficiency` |
| CD-G09-025 | `buy_no_progress_ratio_100ms` | FLOAT | 100ms | DEPTH+AGGTRADE | buy aggression無進行比率 | `PRICE_RESPONSE:buy_no_progress_ratio` |
| CD-G09-026 | `buy_no_progress_ratio_1s` | FLOAT | 1s | DEPTH+AGGTRADE | buy aggression無進行比率 | `PRICE_RESPONSE:buy_no_progress_ratio` |
| CD-G09-027 | `buy_no_progress_ratio_5s` | FLOAT | 5s | DEPTH+AGGTRADE | buy aggression無進行比率 | `PRICE_RESPONSE:buy_no_progress_ratio` |
| CD-G09-028 | `buy_no_progress_ratio_30s` | FLOAT | 30s | DEPTH+AGGTRADE | buy aggression無進行比率 | `PRICE_RESPONSE:buy_no_progress_ratio` |
| CD-G09-029 | `sell_no_progress_ratio_100ms` | FLOAT | 100ms | DEPTH+AGGTRADE | sell aggression無進行比率 | `PRICE_RESPONSE:sell_no_progress_ratio` |
| CD-G09-030 | `sell_no_progress_ratio_1s` | FLOAT | 1s | DEPTH+AGGTRADE | sell aggression無進行比率 | `PRICE_RESPONSE:sell_no_progress_ratio` |
| CD-G09-031 | `sell_no_progress_ratio_5s` | FLOAT | 5s | DEPTH+AGGTRADE | sell aggression無進行比率 | `PRICE_RESPONSE:sell_no_progress_ratio` |
| CD-G09-032 | `sell_no_progress_ratio_30s` | FLOAT | 30s | DEPTH+AGGTRADE | sell aggression無進行比率 | `PRICE_RESPONSE:sell_no_progress_ratio` |
| CD-G09-033 | `reversion_from_window_high_100ms` | FLOAT | 100ms | DEPTH+AGGTRADE | window highから反転幅 | `PRICE_RESPONSE:reversion_from_window_high` |
| CD-G09-034 | `reversion_from_window_high_1s` | FLOAT | 1s | DEPTH+AGGTRADE | window highから反転幅 | `PRICE_RESPONSE:reversion_from_window_high` |
| CD-G09-035 | `reversion_from_window_high_5s` | FLOAT | 5s | DEPTH+AGGTRADE | window highから反転幅 | `PRICE_RESPONSE:reversion_from_window_high` |
| CD-G09-036 | `reversion_from_window_high_30s` | FLOAT | 30s | DEPTH+AGGTRADE | window highから反転幅 | `PRICE_RESPONSE:reversion_from_window_high` |
| CD-G09-037 | `reversion_from_window_low_100ms` | FLOAT | 100ms | DEPTH+AGGTRADE | window lowから反転幅 | `PRICE_RESPONSE:reversion_from_window_low` |
| CD-G09-038 | `reversion_from_window_low_1s` | FLOAT | 1s | DEPTH+AGGTRADE | window lowから反転幅 | `PRICE_RESPONSE:reversion_from_window_low` |
| CD-G09-039 | `reversion_from_window_low_5s` | FLOAT | 5s | DEPTH+AGGTRADE | window lowから反転幅 | `PRICE_RESPONSE:reversion_from_window_low` |
| CD-G09-040 | `reversion_from_window_low_30s` | FLOAT | 30s | DEPTH+AGGTRADE | window lowから反転幅 | `PRICE_RESPONSE:reversion_from_window_low` |

### G10 Delta CVD and Footprint

| ID | condition_key | type | window | source | 定義 | independence_lineage |
|---|---|---|---|---|---|---|
| CD-G10-001 | `trade_delta_1s` | FLOAT | 1s | AGGTRADE | buy minus sell volume | `DELTA_FOOTPRINT:trade_delta` |
| CD-G10-002 | `trade_delta_5s` | FLOAT | 5s | AGGTRADE | buy minus sell volume | `DELTA_FOOTPRINT:trade_delta` |
| CD-G10-003 | `trade_delta_30s` | FLOAT | 30s | AGGTRADE | buy minus sell volume | `DELTA_FOOTPRINT:trade_delta` |
| CD-G10-004 | `trade_delta_5m` | FLOAT | 5m | AGGTRADE | buy minus sell volume | `DELTA_FOOTPRINT:trade_delta` |
| CD-G10-005 | `cvd_change_1s` | FLOAT | 1s | AGGTRADE | CVD変化 | `DELTA_FOOTPRINT:cvd_change` |
| CD-G10-006 | `cvd_change_5s` | FLOAT | 5s | AGGTRADE | CVD変化 | `DELTA_FOOTPRINT:cvd_change` |
| CD-G10-007 | `cvd_change_30s` | FLOAT | 30s | AGGTRADE | CVD変化 | `DELTA_FOOTPRINT:cvd_change` |
| CD-G10-008 | `cvd_change_5m` | FLOAT | 5m | AGGTRADE | CVD変化 | `DELTA_FOOTPRINT:cvd_change` |
| CD-G10-009 | `cvd_slope_1s` | FLOAT | 1s | AGGTRADE | CVD傾き | `DELTA_FOOTPRINT:cvd_slope` |
| CD-G10-010 | `cvd_slope_5s` | FLOAT | 5s | AGGTRADE | CVD傾き | `DELTA_FOOTPRINT:cvd_slope` |
| CD-G10-011 | `cvd_slope_30s` | FLOAT | 30s | AGGTRADE | CVD傾き | `DELTA_FOOTPRINT:cvd_slope` |
| CD-G10-012 | `cvd_slope_5m` | FLOAT | 5m | AGGTRADE | CVD傾き | `DELTA_FOOTPRINT:cvd_slope` |
| CD-G10-013 | `delta_acceleration_1s` | FLOAT | 1s | AGGTRADE | delta変化率 | `DELTA_FOOTPRINT:delta_acceleration` |
| CD-G10-014 | `delta_acceleration_5s` | FLOAT | 5s | AGGTRADE | delta変化率 | `DELTA_FOOTPRINT:delta_acceleration` |
| CD-G10-015 | `delta_acceleration_30s` | FLOAT | 30s | AGGTRADE | delta変化率 | `DELTA_FOOTPRINT:delta_acceleration` |
| CD-G10-016 | `delta_acceleration_5m` | FLOAT | 5m | AGGTRADE | delta変化率 | `DELTA_FOOTPRINT:delta_acceleration` |
| CD-G10-017 | `buy_sell_ratio_1s` | FLOAT | 1s | AGGTRADE | buy対sell volume比 | `DELTA_FOOTPRINT:buy_sell_ratio` |
| CD-G10-018 | `buy_sell_ratio_5s` | FLOAT | 5s | AGGTRADE | buy対sell volume比 | `DELTA_FOOTPRINT:buy_sell_ratio` |
| CD-G10-019 | `buy_sell_ratio_30s` | FLOAT | 30s | AGGTRADE | buy対sell volume比 | `DELTA_FOOTPRINT:buy_sell_ratio` |
| CD-G10-020 | `buy_sell_ratio_5m` | FLOAT | 5m | AGGTRADE | buy対sell volume比 | `DELTA_FOOTPRINT:buy_sell_ratio` |
| CD-G10-021 | `positive_imbalance_count_1s` | FLOAT | 1s | AGGTRADE | 正footprint imbalance数 | `DELTA_FOOTPRINT:positive_imbalance_count` |
| CD-G10-022 | `positive_imbalance_count_5s` | FLOAT | 5s | AGGTRADE | 正footprint imbalance数 | `DELTA_FOOTPRINT:positive_imbalance_count` |
| CD-G10-023 | `positive_imbalance_count_30s` | FLOAT | 30s | AGGTRADE | 正footprint imbalance数 | `DELTA_FOOTPRINT:positive_imbalance_count` |
| CD-G10-024 | `positive_imbalance_count_5m` | FLOAT | 5m | AGGTRADE | 正footprint imbalance数 | `DELTA_FOOTPRINT:positive_imbalance_count` |
| CD-G10-025 | `negative_imbalance_count_1s` | FLOAT | 1s | AGGTRADE | 負footprint imbalance数 | `DELTA_FOOTPRINT:negative_imbalance_count` |
| CD-G10-026 | `negative_imbalance_count_5s` | FLOAT | 5s | AGGTRADE | 負footprint imbalance数 | `DELTA_FOOTPRINT:negative_imbalance_count` |
| CD-G10-027 | `negative_imbalance_count_30s` | FLOAT | 30s | AGGTRADE | 負footprint imbalance数 | `DELTA_FOOTPRINT:negative_imbalance_count` |
| CD-G10-028 | `negative_imbalance_count_5m` | FLOAT | 5m | AGGTRADE | 負footprint imbalance数 | `DELTA_FOOTPRINT:negative_imbalance_count` |
| CD-G10-029 | `stacked_buy_imbalance_depth_1s` | FLOAT | 1s | AGGTRADE | 連続buy imbalance段数 | `DELTA_FOOTPRINT:stacked_buy_imbalance_depth` |
| CD-G10-030 | `stacked_buy_imbalance_depth_5s` | FLOAT | 5s | AGGTRADE | 連続buy imbalance段数 | `DELTA_FOOTPRINT:stacked_buy_imbalance_depth` |
| CD-G10-031 | `stacked_buy_imbalance_depth_30s` | FLOAT | 30s | AGGTRADE | 連続buy imbalance段数 | `DELTA_FOOTPRINT:stacked_buy_imbalance_depth` |
| CD-G10-032 | `stacked_buy_imbalance_depth_5m` | FLOAT | 5m | AGGTRADE | 連続buy imbalance段数 | `DELTA_FOOTPRINT:stacked_buy_imbalance_depth` |
| CD-G10-033 | `stacked_sell_imbalance_depth_1s` | FLOAT | 1s | AGGTRADE | 連続sell imbalance段数 | `DELTA_FOOTPRINT:stacked_sell_imbalance_depth` |
| CD-G10-034 | `stacked_sell_imbalance_depth_5s` | FLOAT | 5s | AGGTRADE | 連続sell imbalance段数 | `DELTA_FOOTPRINT:stacked_sell_imbalance_depth` |
| CD-G10-035 | `stacked_sell_imbalance_depth_30s` | FLOAT | 30s | AGGTRADE | 連続sell imbalance段数 | `DELTA_FOOTPRINT:stacked_sell_imbalance_depth` |
| CD-G10-036 | `stacked_sell_imbalance_depth_5m` | FLOAT | 5m | AGGTRADE | 連続sell imbalance段数 | `DELTA_FOOTPRINT:stacked_sell_imbalance_depth` |

### G11 Volume Profile and Auction

| ID | condition_key | type | window | source | 定義 | independence_lineage |
|---|---|---|---|---|---|---|
| CD-G11-001 | `point_of_control_distance_session` | FLOAT | session | AGGTRADE+PROFILE | POC距離 | `PROFILE_AUCTION:point_of_control_distance` |
| CD-G11-002 | `point_of_control_distance_rolling_1h` | FLOAT | rolling_1h | AGGTRADE+PROFILE | POC距離 | `PROFILE_AUCTION:point_of_control_distance` |
| CD-G11-003 | `value_area_high_distance_session` | FLOAT | session | AGGTRADE+PROFILE | VAH距離 | `PROFILE_AUCTION:value_area_high_distance` |
| CD-G11-004 | `value_area_high_distance_rolling_1h` | FLOAT | rolling_1h | AGGTRADE+PROFILE | VAH距離 | `PROFILE_AUCTION:value_area_high_distance` |
| CD-G11-005 | `value_area_low_distance_session` | FLOAT | session | AGGTRADE+PROFILE | VAL距離 | `PROFILE_AUCTION:value_area_low_distance` |
| CD-G11-006 | `value_area_low_distance_rolling_1h` | FLOAT | rolling_1h | AGGTRADE+PROFILE | VAL距離 | `PROFILE_AUCTION:value_area_low_distance` |
| CD-G11-007 | `high_volume_node_distance_session` | FLOAT | session | AGGTRADE+PROFILE | 最寄りHVN距離 | `PROFILE_AUCTION:high_volume_node_distance` |
| CD-G11-008 | `high_volume_node_distance_rolling_1h` | FLOAT | rolling_1h | AGGTRADE+PROFILE | 最寄りHVN距離 | `PROFILE_AUCTION:high_volume_node_distance` |
| CD-G11-009 | `low_volume_node_distance_session` | FLOAT | session | AGGTRADE+PROFILE | 最寄りLVN距離 | `PROFILE_AUCTION:low_volume_node_distance` |
| CD-G11-010 | `low_volume_node_distance_rolling_1h` | FLOAT | rolling_1h | AGGTRADE+PROFILE | 最寄りLVN距離 | `PROFILE_AUCTION:low_volume_node_distance` |
| CD-G11-011 | `volume_at_current_price_percentile_session` | FLOAT | session | AGGTRADE+PROFILE | 現在価格volume percentile | `PROFILE_AUCTION:volume_at_current_price_percentile` |
| CD-G11-012 | `volume_at_current_price_percentile_rolling_1h` | FLOAT | rolling_1h | AGGTRADE+PROFILE | 現在価格volume percentile | `PROFILE_AUCTION:volume_at_current_price_percentile` |
| CD-G11-013 | `profile_balance_score_session` | FLOAT | session | AGGTRADE+PROFILE | profile balance | `PROFILE_AUCTION:profile_balance_score` |
| CD-G11-014 | `profile_balance_score_rolling_1h` | FLOAT | rolling_1h | AGGTRADE+PROFILE | profile balance | `PROFILE_AUCTION:profile_balance_score` |
| CD-G11-015 | `profile_skew_session` | FLOAT | session | AGGTRADE+PROFILE | profile skew | `PROFILE_AUCTION:profile_skew` |
| CD-G11-016 | `profile_skew_rolling_1h` | FLOAT | rolling_1h | AGGTRADE+PROFILE | profile skew | `PROFILE_AUCTION:profile_skew` |
| CD-G11-017 | `poc_migration_session` | FLOAT | session | AGGTRADE+PROFILE | POC移動 | `PROFILE_AUCTION:poc_migration` |
| CD-G11-018 | `poc_migration_rolling_1h` | FLOAT | rolling_1h | AGGTRADE+PROFILE | POC移動 | `PROFILE_AUCTION:poc_migration` |
| CD-G11-019 | `value_area_migration_session` | FLOAT | session | AGGTRADE+PROFILE | value area移動 | `PROFILE_AUCTION:value_area_migration` |
| CD-G11-020 | `value_area_migration_rolling_1h` | FLOAT | rolling_1h | AGGTRADE+PROFILE | value area移動 | `PROFILE_AUCTION:value_area_migration` |
| CD-G11-021 | `excess_high_score_session` | FLOAT | session | AGGTRADE+PROFILE | high excess度 | `PROFILE_AUCTION:excess_high_score` |
| CD-G11-022 | `excess_high_score_rolling_1h` | FLOAT | rolling_1h | AGGTRADE+PROFILE | high excess度 | `PROFILE_AUCTION:excess_high_score` |
| CD-G11-023 | `excess_low_score_session` | FLOAT | session | AGGTRADE+PROFILE | low excess度 | `PROFILE_AUCTION:excess_low_score` |
| CD-G11-024 | `excess_low_score_rolling_1h` | FLOAT | rolling_1h | AGGTRADE+PROFILE | low excess度 | `PROFILE_AUCTION:excess_low_score` |
| CD-G11-025 | `poor_high_score_session` | FLOAT | session | AGGTRADE+PROFILE | poor high度 | `PROFILE_AUCTION:poor_high_score` |
| CD-G11-026 | `poor_high_score_rolling_1h` | FLOAT | rolling_1h | AGGTRADE+PROFILE | poor high度 | `PROFILE_AUCTION:poor_high_score` |
| CD-G11-027 | `poor_low_score_session` | FLOAT | session | AGGTRADE+PROFILE | poor low度 | `PROFILE_AUCTION:poor_low_score` |
| CD-G11-028 | `poor_low_score_rolling_1h` | FLOAT | rolling_1h | AGGTRADE+PROFILE | poor low度 | `PROFILE_AUCTION:poor_low_score` |
| CD-G11-029 | `acceptance_above_value_session` | FLOAT | session | AGGTRADE+PROFILE | value上acceptance | `PROFILE_AUCTION:acceptance_above_value` |
| CD-G11-030 | `acceptance_above_value_rolling_1h` | FLOAT | rolling_1h | AGGTRADE+PROFILE | value上acceptance | `PROFILE_AUCTION:acceptance_above_value` |
| CD-G11-031 | `acceptance_below_value_session` | FLOAT | session | AGGTRADE+PROFILE | value下acceptance | `PROFILE_AUCTION:acceptance_below_value` |
| CD-G11-032 | `acceptance_below_value_rolling_1h` | FLOAT | rolling_1h | AGGTRADE+PROFILE | value下acceptance | `PROFILE_AUCTION:acceptance_below_value` |

### G12 Derivatives Positioning

| ID | condition_key | type | window | source | 定義 | independence_lineage |
|---|---|---|---|---|---|---|
| CD-G12-001 | `open_interest_change_5m` | FLOAT | 5m | OI | OI absolute change | `DERIVATIVES:OI_CHANGE` |
| CD-G12-002 | `open_interest_pct_change_5m` | FLOAT | 5m | OI | OI percent change | `DERIVATIVES:OI_CHANGE` |
| CD-G12-003 | `price_oi_joint_state_5m` | ENUM | 5m | OI+AGGTRADE | price方向とOI方向のjoint state | `DERIVATIVES:PRICE_OI` |
| CD-G12-004 | `open_interest_change_15m` | FLOAT | 15m | OI | OI absolute change | `DERIVATIVES:OI_CHANGE` |
| CD-G12-005 | `open_interest_pct_change_15m` | FLOAT | 15m | OI | OI percent change | `DERIVATIVES:OI_CHANGE` |
| CD-G12-006 | `price_oi_joint_state_15m` | ENUM | 15m | OI+AGGTRADE | price方向とOI方向のjoint state | `DERIVATIVES:PRICE_OI` |
| CD-G12-007 | `open_interest_change_1h` | FLOAT | 1h | OI | OI absolute change | `DERIVATIVES:OI_CHANGE` |
| CD-G12-008 | `open_interest_pct_change_1h` | FLOAT | 1h | OI | OI percent change | `DERIVATIVES:OI_CHANGE` |
| CD-G12-009 | `price_oi_joint_state_1h` | ENUM | 1h | OI+AGGTRADE | price方向とOI方向のjoint state | `DERIVATIVES:PRICE_OI` |
| CD-G12-010 | `open_interest_change_4h` | FLOAT | 4h | OI | OI absolute change | `DERIVATIVES:OI_CHANGE` |
| CD-G12-011 | `open_interest_pct_change_4h` | FLOAT | 4h | OI | OI percent change | `DERIVATIVES:OI_CHANGE` |
| CD-G12-012 | `price_oi_joint_state_4h` | ENUM | 4h | OI+AGGTRADE | price方向とOI方向のjoint state | `DERIVATIVES:PRICE_OI` |
| CD-G12-013 | `funding_rate_current` | FLOAT | POINT_IN_TIME | MARK_FUNDING | current funding rate | `DERIVATIVES:FUNDING` |
| CD-G12-014 | `funding_rate_zscore` | FLOAT | 30D_BASELINE | MARK_FUNDING | funding z-score | `DERIVATIVES:FUNDING` |
| CD-G12-015 | `minutes_to_funding` | FLOAT | POINT_IN_TIME | MARK_FUNDING+CLOCK | 次回fundingまでの分 | `DERIVATIVES:FUNDING` |
| CD-G12-016 | `funding_rate_change` | FLOAT | PREVIOUS_EVENT | MARK_FUNDING | 前回値からのfunding変化 | `DERIVATIVES:FUNDING` |
| CD-G12-017 | `futures_basis_current` | FLOAT | POINT_IN_TIME | MARK_FUNDING | future minus index | `DERIVATIVES:BASIS` |
| CD-G12-018 | `futures_basis_rate` | FLOAT | POINT_IN_TIME | MARK_FUNDING | basis rate | `DERIVATIVES:BASIS` |
| CD-G12-019 | `futures_basis_zscore` | FLOAT | 30D_BASELINE | MARK_FUNDING | basis z-score | `DERIVATIVES:BASIS` |
| CD-G12-020 | `annualized_basis_rate` | FLOAT | POINT_IN_TIME | MARK_FUNDING | annualized basis | `DERIVATIVES:BASIS` |
| CD-G12-021 | `mark_index_basis` | FLOAT | POINT_IN_TIME | MARK_FUNDING | mark minus index | `DERIVATIVES:MARK_INDEX` |
| CD-G12-022 | `mark_index_basis_zscore` | FLOAT | 30D_BASELINE | MARK_FUNDING | mark-index z-score | `DERIVATIVES:MARK_INDEX` |
| CD-G12-023 | `observed_liquidation_buy_notional_1s` | FLOAT | 1s | FORCE_ORDER | 観測buy liquidation snapshot notional | `DERIVATIVES:LIQUIDATION:buy` |
| CD-G12-024 | `observed_liquidation_buy_notional_5s` | FLOAT | 5s | FORCE_ORDER | 観測buy liquidation snapshot notional | `DERIVATIVES:LIQUIDATION:buy` |
| CD-G12-025 | `observed_liquidation_buy_notional_30s` | FLOAT | 30s | FORCE_ORDER | 観測buy liquidation snapshot notional | `DERIVATIVES:LIQUIDATION:buy` |
| CD-G12-026 | `observed_liquidation_sell_notional_1s` | FLOAT | 1s | FORCE_ORDER | 観測sell liquidation snapshot notional | `DERIVATIVES:LIQUIDATION:sell` |
| CD-G12-027 | `observed_liquidation_sell_notional_5s` | FLOAT | 5s | FORCE_ORDER | 観測sell liquidation snapshot notional | `DERIVATIVES:LIQUIDATION:sell` |
| CD-G12-028 | `observed_liquidation_sell_notional_30s` | FLOAT | 30s | FORCE_ORDER | 観測sell liquidation snapshot notional | `DERIVATIVES:LIQUIDATION:sell` |
| CD-G12-029 | `observed_liquidation_imbalance_1s` | FLOAT | 1s | FORCE_ORDER | 観測snapshot liquidation imbalance | `DERIVATIVES:LIQUIDATION_IMBALANCE` |
| CD-G12-030 | `observed_liquidation_imbalance_5s` | FLOAT | 5s | FORCE_ORDER | 観測snapshot liquidation imbalance | `DERIVATIVES:LIQUIDATION_IMBALANCE` |
| CD-G12-031 | `observed_liquidation_imbalance_30s` | FLOAT | 30s | FORCE_ORDER | 観測snapshot liquidation imbalance | `DERIVATIVES:LIQUIDATION_IMBALANCE` |
| CD-G12-032 | `adl_risk_state` | ENUM | 30M | BINANCE_ADL | symbol ADL risk | `DERIVATIVES:ADL_RISK` |

### G13 Cross Venue Relative State

| ID | condition_key | type | window | source | 定義 | independence_lineage |
|---|---|---|---|---|---|---|
| CD-G13-001 | `binance_hfm_bid_basis_100ms` | FLOAT | 100ms | DEPTH+HFM_QUOTE | Binance bid対HFM bid basis | `CROSS_VENUE:binance_hfm_bid_basis` |
| CD-G13-002 | `binance_hfm_bid_basis_1s` | FLOAT | 1s | DEPTH+HFM_QUOTE | Binance bid対HFM bid basis | `CROSS_VENUE:binance_hfm_bid_basis` |
| CD-G13-003 | `binance_hfm_bid_basis_5s` | FLOAT | 5s | DEPTH+HFM_QUOTE | Binance bid対HFM bid basis | `CROSS_VENUE:binance_hfm_bid_basis` |
| CD-G13-004 | `binance_hfm_bid_basis_30s` | FLOAT | 30s | DEPTH+HFM_QUOTE | Binance bid対HFM bid basis | `CROSS_VENUE:binance_hfm_bid_basis` |
| CD-G13-005 | `binance_hfm_ask_basis_100ms` | FLOAT | 100ms | DEPTH+HFM_QUOTE | Binance ask対HFM ask basis | `CROSS_VENUE:binance_hfm_ask_basis` |
| CD-G13-006 | `binance_hfm_ask_basis_1s` | FLOAT | 1s | DEPTH+HFM_QUOTE | Binance ask対HFM ask basis | `CROSS_VENUE:binance_hfm_ask_basis` |
| CD-G13-007 | `binance_hfm_ask_basis_5s` | FLOAT | 5s | DEPTH+HFM_QUOTE | Binance ask対HFM ask basis | `CROSS_VENUE:binance_hfm_ask_basis` |
| CD-G13-008 | `binance_hfm_ask_basis_30s` | FLOAT | 30s | DEPTH+HFM_QUOTE | Binance ask対HFM ask basis | `CROSS_VENUE:binance_hfm_ask_basis` |
| CD-G13-009 | `binance_hfm_mid_basis_100ms` | FLOAT | 100ms | DEPTH+HFM_QUOTE | Binance mid対HFM mid basis | `CROSS_VENUE:binance_hfm_mid_basis` |
| CD-G13-010 | `binance_hfm_mid_basis_1s` | FLOAT | 1s | DEPTH+HFM_QUOTE | Binance mid対HFM mid basis | `CROSS_VENUE:binance_hfm_mid_basis` |
| CD-G13-011 | `binance_hfm_mid_basis_5s` | FLOAT | 5s | DEPTH+HFM_QUOTE | Binance mid対HFM mid basis | `CROSS_VENUE:binance_hfm_mid_basis` |
| CD-G13-012 | `binance_hfm_mid_basis_30s` | FLOAT | 30s | DEPTH+HFM_QUOTE | Binance mid対HFM mid basis | `CROSS_VENUE:binance_hfm_mid_basis` |
| CD-G13-013 | `basis_change_100ms` | FLOAT | 100ms | DEPTH+HFM_QUOTE | venue間basis変化 | `CROSS_VENUE:basis_change` |
| CD-G13-014 | `basis_change_1s` | FLOAT | 1s | DEPTH+HFM_QUOTE | venue間basis変化 | `CROSS_VENUE:basis_change` |
| CD-G13-015 | `basis_change_5s` | FLOAT | 5s | DEPTH+HFM_QUOTE | venue間basis変化 | `CROSS_VENUE:basis_change` |
| CD-G13-016 | `basis_change_30s` | FLOAT | 30s | DEPTH+HFM_QUOTE | venue間basis変化 | `CROSS_VENUE:basis_change` |
| CD-G13-017 | `return_spread_100ms` | FLOAT | 100ms | DEPTH+HFM_QUOTE | venue間return差 | `CROSS_VENUE:return_spread` |
| CD-G13-018 | `return_spread_1s` | FLOAT | 1s | DEPTH+HFM_QUOTE | venue間return差 | `CROSS_VENUE:return_spread` |
| CD-G13-019 | `return_spread_5s` | FLOAT | 5s | DEPTH+HFM_QUOTE | venue間return差 | `CROSS_VENUE:return_spread` |
| CD-G13-020 | `return_spread_30s` | FLOAT | 30s | DEPTH+HFM_QUOTE | venue間return差 | `CROSS_VENUE:return_spread` |
| CD-G13-021 | `direction_agreement_100ms` | FLOAT | 100ms | DEPTH+HFM_QUOTE | venue間方向一致度 | `CROSS_VENUE:direction_agreement` |
| CD-G13-022 | `direction_agreement_1s` | FLOAT | 1s | DEPTH+HFM_QUOTE | venue間方向一致度 | `CROSS_VENUE:direction_agreement` |
| CD-G13-023 | `direction_agreement_5s` | FLOAT | 5s | DEPTH+HFM_QUOTE | venue間方向一致度 | `CROSS_VENUE:direction_agreement` |
| CD-G13-024 | `direction_agreement_30s` | FLOAT | 30s | DEPTH+HFM_QUOTE | venue間方向一致度 | `CROSS_VENUE:direction_agreement` |
| CD-G13-025 | `lead_lag_score_100ms` | FLOAT | 100ms | DEPTH+HFM_QUOTE | venue間lead-lag | `CROSS_VENUE:lead_lag_score` |
| CD-G13-026 | `lead_lag_score_1s` | FLOAT | 1s | DEPTH+HFM_QUOTE | venue間lead-lag | `CROSS_VENUE:lead_lag_score` |
| CD-G13-027 | `lead_lag_score_5s` | FLOAT | 5s | DEPTH+HFM_QUOTE | venue間lead-lag | `CROSS_VENUE:lead_lag_score` |
| CD-G13-028 | `lead_lag_score_30s` | FLOAT | 30s | DEPTH+HFM_QUOTE | venue間lead-lag | `CROSS_VENUE:lead_lag_score` |

### G14 Execution and Risk Gate

| ID | condition_key | type | window | source | 定義 | independence_lineage |
|---|---|---|---|---|---|---|
| CD-G14-001 | `hfm_symbol_tradeable` | FLAG | POINT_IN_TIME | HFM_QUOTE+HFM_EXEC+RISK_STATE | HFM symbolがtradeable | `EXECUTION_RISK:hfm_symbol_tradeable` |
| CD-G14-002 | `execution_hfm_quote_fresh` | FLAG | POINT_IN_TIME | HFM_QUOTE+HFM_EXEC+RISK_STATE | 発注用HFM quoteがfresh | `EXECUTION_RISK:execution_hfm_quote_fresh` |
| CD-G14-003 | `hfm_spread_within_limit` | FLAG | POINT_IN_TIME | HFM_QUOTE+HFM_EXEC+RISK_STATE | HFM spreadが上限内 | `EXECUTION_RISK:hfm_spread_within_limit` |
| CD-G14-004 | `hfm_basis_within_limit` | FLAG | POINT_IN_TIME | HFM_QUOTE+HFM_EXEC+RISK_STATE | Binance-HFM basisが上限内 | `EXECUTION_RISK:hfm_basis_within_limit` |
| CD-G14-005 | `execution_latency_within_limit` | FLAG | POINT_IN_TIME | HFM_QUOTE+HFM_EXEC+RISK_STATE | 推定latencyが上限内 | `EXECUTION_RISK:execution_latency_within_limit` |
| CD-G14-006 | `expected_slippage_within_limit` | FLAG | POINT_IN_TIME | HFM_QUOTE+HFM_EXEC+RISK_STATE | 推定slippageが上限内 | `EXECUTION_RISK:expected_slippage_within_limit` |
| CD-G14-007 | `expected_cost_within_limit` | FLAG | POINT_IN_TIME | HFM_QUOTE+HFM_EXEC+RISK_STATE | feeとslippage合計が上限内 | `EXECUTION_RISK:expected_cost_within_limit` |
| CD-G14-008 | `risk_reward_above_floor` | FLAG | POINT_IN_TIME | HFM_QUOTE+HFM_EXEC+RISK_STATE | reward対riskが下限以上 | `EXECUTION_RISK:risk_reward_above_floor` |
| CD-G14-009 | `invalidation_distance_valid` | FLAG | POINT_IN_TIME | HFM_QUOTE+HFM_EXEC+RISK_STATE | invalidation距離が正で有限 | `EXECUTION_RISK:invalidation_distance_valid` |
| CD-G14-010 | `risk_budget_available` | FLAG | POINT_IN_TIME | HFM_QUOTE+HFM_EXEC+RISK_STATE | 注文用risk budgetあり | `EXECUTION_RISK:risk_budget_available` |
| CD-G14-011 | `position_cap_available` | FLAG | POINT_IN_TIME | HFM_QUOTE+HFM_EXEC+RISK_STATE | exposure capに余地あり | `EXECUTION_RISK:position_cap_available` |
| CD-G14-012 | `margin_available` | FLAG | POINT_IN_TIME | HFM_QUOTE+HFM_EXEC+RISK_STATE | 必要margin利用可能 | `EXECUTION_RISK:margin_available` |
| CD-G14-013 | `broker_volume_step_valid` | FLAG | POINT_IN_TIME | HFM_QUOTE+HFM_EXEC+RISK_STATE | volume step適合 | `EXECUTION_RISK:broker_volume_step_valid` |
| CD-G14-014 | `broker_min_volume_met` | FLAG | POINT_IN_TIME | HFM_QUOTE+HFM_EXEC+RISK_STATE | minimum volume以上 | `EXECUTION_RISK:broker_min_volume_met` |
| CD-G14-015 | `broker_max_volume_not_exceeded` | FLAG | POINT_IN_TIME | HFM_QUOTE+HFM_EXEC+RISK_STATE | maximum volume以下 | `EXECUTION_RISK:broker_max_volume_not_exceeded` |
| CD-G14-016 | `broker_stop_distance_valid` | FLAG | POINT_IN_TIME | HFM_QUOTE+HFM_EXEC+RISK_STATE | stop距離がcontract適合 | `EXECUTION_RISK:broker_stop_distance_valid` |
| CD-G14-017 | `duplicate_intent_absent` | FLAG | POINT_IN_TIME | HFM_QUOTE+HFM_EXEC+RISK_STATE | 同一intent重複なし | `EXECUTION_RISK:duplicate_intent_absent` |
| CD-G14-018 | `outstanding_order_conflict_absent` | FLAG | POINT_IN_TIME | HFM_QUOTE+HFM_EXEC+RISK_STATE | 競合open orderなし | `EXECUTION_RISK:outstanding_order_conflict_absent` |
| CD-G14-019 | `idempotency_key_available` | FLAG | POINT_IN_TIME | HFM_QUOTE+HFM_EXEC+RISK_STATE | idempotency key生成済み | `EXECUTION_RISK:idempotency_key_available` |
| CD-G14-020 | `execution_mode_allowed` | FLAG | POINT_IN_TIME | HFM_QUOTE+HFM_EXEC+RISK_STATE | execution mode許可 | `EXECUTION_RISK:execution_mode_allowed` |
| CD-G14-021 | `daily_loss_limit_clear` | FLAG | POINT_IN_TIME | HFM_QUOTE+HFM_EXEC+RISK_STATE | daily loss limit未到達 | `EXECUTION_RISK:daily_loss_limit_clear` |
| CD-G14-022 | `drawdown_limit_clear` | FLAG | POINT_IN_TIME | HFM_QUOTE+HFM_EXEC+RISK_STATE | drawdown limit未到達 | `EXECUTION_RISK:drawdown_limit_clear` |
| CD-G14-023 | `cooldown_elapsed` | FLAG | POINT_IN_TIME | HFM_QUOTE+HFM_EXEC+RISK_STATE | 発注cooldown経過 | `EXECUTION_RISK:cooldown_elapsed` |
| CD-G14-024 | `max_order_rate_clear` | FLAG | POINT_IN_TIME | HFM_QUOTE+HFM_EXEC+RISK_STATE | order rate limit内 | `EXECUTION_RISK:max_order_rate_clear` |
| CD-G14-025 | `recent_reject_rate_acceptable` | FLAG | POINT_IN_TIME | HFM_QUOTE+HFM_EXEC+RISK_STATE | 直近reject率が上限内 | `EXECUTION_RISK:recent_reject_rate_acceptable` |
| CD-G14-026 | `recent_fill_rate_acceptable` | FLAG | POINT_IN_TIME | HFM_QUOTE+HFM_EXEC+RISK_STATE | 直近fill率が下限以上 | `EXECUTION_RISK:recent_fill_rate_acceptable` |
| CD-G14-027 | `emergency_stop_clear` | FLAG | POINT_IN_TIME | HFM_QUOTE+HFM_EXEC+RISK_STATE | emergency stop未発動 | `EXECUTION_RISK:emergency_stop_clear` |
| CD-G14-028 | `all_execution_hard_gates_pass` | FLAG | POINT_IN_TIME | HFM_QUOTE+HFM_EXEC+RISK_STATE | 全execution hard gate通過 | `EXECUTION_RISK:all_execution_hard_gates_pass` |

### G15 Open Position Lifecycle

| ID | condition_key | type | window | source | 定義 | independence_lineage |
|---|---|---|---|---|---|---|
| CD-G15-001 | `position_is_open` | ENUM | POINT_IN_TIME | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | 対象positionがopen | `POSITION:position_is_open` |
| CD-G15-002 | `side_matches_strategy` | ENUM | POINT_IN_TIME | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | position sideとstrategy sideの関係 | `POSITION:side_matches_strategy` |
| CD-G15-003 | `entry_fill_confirmed` | ENUM | POINT_IN_TIME | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | entry fillがbroker確認済み | `POSITION:entry_fill_confirmed` |
| CD-G15-004 | `holding_time_within_limit` | ENUM | POINT_IN_TIME | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | holding timeが上限内 | `POSITION:holding_time_within_limit` |
| CD-G15-005 | `expected_reaction_deadline_clear` | ENUM | POINT_IN_TIME | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | 期待反応期限内 | `POSITION:expected_reaction_deadline_clear` |
| CD-G15-006 | `unrealized_pnl_state` | ENUM | POINT_IN_TIME | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | unrealized PnL状態 | `POSITION:unrealized_pnl_state` |
| CD-G15-007 | `mae_within_limit` | ENUM | POINT_IN_TIME | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | MAEが上限内 | `POSITION:mae_within_limit` |
| CD-G15-008 | `mfe_state` | ENUM | POINT_IN_TIME | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | MFE状態 | `POSITION:mfe_state` |
| CD-G15-009 | `price_progress_supports_thesis` | ENUM | POINT_IN_TIME | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | entry後price progressが仮説支持 | `POSITION:price_progress_supports_thesis` |
| CD-G15-010 | `order_flow_supports_thesis` | ENUM | POINT_IN_TIME | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | entry後flowが仮説支持 | `POSITION:order_flow_supports_thesis` |
| CD-G15-011 | `passive_defense_holds` | ENUM | POINT_IN_TIME | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | 期待passive defense維持 | `POSITION:passive_defense_holds` |
| CD-G15-012 | `breakout_acceptance_holds` | ENUM | POINT_IN_TIME | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | 期待breakout acceptance維持 | `POSITION:breakout_acceptance_holds` |
| CD-G15-013 | `contradiction_below_limit` | ENUM | POINT_IN_TIME | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | 反証が上限未満 | `POSITION:contradiction_below_limit` |
| CD-G15-014 | `invalidation_absent` | ENUM | POINT_IN_TIME | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | 論理invalidation未成立 | `POSITION:invalidation_absent` |
| CD-G15-015 | `add_size_eligible` | ENUM | POINT_IN_TIME | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | 追加発注候補 | `POSITION:add_size_eligible` |
| CD-G15-016 | `reduce_size_required` | ENUM | POINT_IN_TIME | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | 縮小必要 | `POSITION:reduce_size_required` |
| CD-G15-017 | `exit_required` | ENUM | POINT_IN_TIME | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | 決済必要 | `POSITION:exit_required` |
| CD-G15-018 | `reverse_candidate` | ENUM | POINT_IN_TIME | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | 反転候補 | `POSITION:reverse_candidate` |
| CD-G15-019 | `trailing_invalidation_updated` | ENUM | POINT_IN_TIME | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | trailing invalidation更新済み | `POSITION:trailing_invalidation_updated` |
| CD-G15-020 | `remaining_risk_within_limit` | ENUM | POINT_IN_TIME | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | 残存riskが上限内 | `POSITION:remaining_risk_within_limit` |
| CD-G15-021 | `competing_strategy_dominant` | ENUM | POINT_IN_TIME | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | 競合strategyが優勢 | `POSITION:competing_strategy_dominant` |
| CD-G15-022 | `satisfaction_tier_not_downgraded` | ENUM | POINT_IN_TIME | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | entry時充足水準から未悪化 | `POSITION:satisfaction_tier_not_downgraded` |
| CD-G15-023 | `post_entry_data_fresh` | ENUM | POINT_IN_TIME | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | 保有中必須dataがfresh | `POSITION:post_entry_data_fresh` |
| CD-G15-024 | `flat_confirmation_received` | ENUM | POINT_IN_TIME | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | 決済後flat確認済み | `POSITION:flat_confirmation_received` |

### G16 Order Flow Interaction States

このgroupはG05-G13のraw／derived値を組み合わせた状態判定である。各行は材料Conditionの`depends_on`を保持し、材料と別の独立確認票として数えない。`absorption-like`、`trapped-like`、`stop-run-like`は観測反応の名称であり、非観測の注文者同一性や意図を断定しない。

| ID | condition_key | type | window | source | 定義 | independence_lineage |
|---|---|---|---|---|---|---|
| CD-G16-001 | `bid_absorption_like_active` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | bid側でsell aggressionに対し下方進行が止まるabsorption-like状態 | `COMPOSITE:ABSORPTION:BID` |
| CD-G16-002 | `ask_absorption_like_active` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | ask側でbuy aggressionに対し上方進行が止まるabsorption-like状態 | `COMPOSITE:ABSORPTION:ASK` |
| CD-G16-003 | `bid_absorption_strengthening` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | bid absorption-like反応が反復ごとに強化 | `COMPOSITE:ABSORPTION:BID` |
| CD-G16-004 | `ask_absorption_strengthening` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | ask absorption-like反応が反復ごとに強化 | `COMPOSITE:ABSORPTION:ASK` |
| CD-G16-005 | `bid_absorption_weakening` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | bid absorption-like反応が反復ごとに弱化 | `COMPOSITE:ABSORPTION:BID` |
| CD-G16-006 | `ask_absorption_weakening` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | ask absorption-like反応が反復ごとに弱化 | `COMPOSITE:ABSORPTION:ASK` |
| CD-G16-007 | `buyer_fade_active` | FLAG | STRATEGY_SPECIFIC | AGGTRADE+PRICE_RESPONSE+DELTA | 高値側でaggressive buyer参加が減衰 | `COMPOSITE:FADE:BUYER` |
| CD-G16-008 | `seller_fade_active` | FLAG | STRATEGY_SPECIFIC | AGGTRADE+PRICE_RESPONSE+DELTA | 安値側でaggressive seller参加が減衰 | `COMPOSITE:FADE:SELLER` |
| CD-G16-009 | `buyers_jump_in` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | buy aggressionが基準を超えて新規増加 | `COMPOSITE:AGGRESSION:BUY_ENTRY` |
| CD-G16-010 | `sellers_jump_in` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | sell aggressionが基準を超えて新規増加 | `COMPOSITE:AGGRESSION:SELL_ENTRY` |
| CD-G16-011 | `trapped_buyers_like` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 大きいbuy flow後も上方進行せず反転するtrapped-like状態 | `COMPOSITE:TRAPPED_LIKE:BUYER` |
| CD-G16-012 | `trapped_sellers_like` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 大きいsell flow後も下方進行せず反転するtrapped-like状態 | `COMPOSITE:TRAPPED_LIKE:SELLER` |
| CD-G16-013 | `repeated_high_test` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 同一high近傍を指定回数再試行 | `COMPOSITE:TEST:HIGH` |
| CD-G16-014 | `repeated_low_test` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 同一low近傍を指定回数再試行 | `COMPOSITE:TEST:LOW` |
| CD-G16-015 | `high_rejection_active` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | high進入後に指定時間内で下へ戻るrejection | `COMPOSITE:REJECTION:HIGH` |
| CD-G16-016 | `low_rejection_active` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | low進入後に指定時間内で上へ戻るrejection | `COMPOSITE:REJECTION:LOW` |
| CD-G16-017 | `acceptance_above_reference` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | reference上で時間・volume・retest条件を満たすacceptance | `COMPOSITE:ACCEPTANCE:ABOVE` |
| CD-G16-018 | `acceptance_below_reference` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | reference下で時間・volume・retest条件を満たすacceptance | `COMPOSITE:ACCEPTANCE:BELOW` |
| CD-G16-019 | `upside_breakout_attempt` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 上側referenceをinitiative buyで試行 | `COMPOSITE:BREAKOUT:UP:ATTEMPT` |
| CD-G16-020 | `downside_breakout_attempt` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 下側referenceをinitiative sellで試行 | `COMPOSITE:BREAKOUT:DOWN:ATTEMPT` |
| CD-G16-021 | `upside_breakout_follow_through` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 上抜け後もbuy participationとprice progress継続 | `COMPOSITE:BREAKOUT:UP:FOLLOW_THROUGH` |
| CD-G16-022 | `downside_breakout_follow_through` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 下抜け後もsell participationとprice progress継続 | `COMPOSITE:BREAKOUT:DOWN:FOLLOW_THROUGH` |
| CD-G16-023 | `upside_breakout_failure` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 上抜け後にacceptanceせずreference下へ復帰 | `COMPOSITE:BREAKOUT:UP:FAILURE` |
| CD-G16-024 | `downside_breakout_failure` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 下抜け後にacceptanceせずreference上へ復帰 | `COMPOSITE:BREAKOUT:DOWN:FAILURE` |
| CD-G16-025 | `reclaim_above_reference` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 下側からreference上へ回復し保持 | `COMPOSITE:RECLAIM:ABOVE` |
| CD-G16-026 | `reclaim_below_reference` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 上側からreference下へ回復し保持 | `COMPOSITE:RECLAIM:BELOW` |
| CD-G16-027 | `bullish_pullback_low_participation` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 上昇中pullbackのsell participationが低い | `COMPOSITE:PULLBACK:BULL:PARTICIPATION` |
| CD-G16-028 | `bearish_pullback_low_participation` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 下降中pullbackのbuy participationが低い | `COMPOSITE:PULLBACK:BEAR:PARTICIPATION` |
| CD-G16-029 | `bullish_pullback_stall` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 上昇trend内pullbackの下方進行が停滞 | `COMPOSITE:PULLBACK:BULL:STALL` |
| CD-G16-030 | `bearish_pullback_stall` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 下降trend内pullbackの上方進行が停滞 | `COMPOSITE:PULLBACK:BEAR:STALL` |
| CD-G16-031 | `buy_momentum_accelerating` | FLAG | STRATEGY_SPECIFIC | AGGTRADE+PRICE_RESPONSE+DELTA | buy flow速度と上方progressが同時加速 | `COMPOSITE:MOMENTUM:BUY` |
| CD-G16-032 | `sell_momentum_accelerating` | FLAG | STRATEGY_SPECIFIC | AGGTRADE+PRICE_RESPONSE+DELTA | sell flow速度と下方progressが同時加速 | `COMPOSITE:MOMENTUM:SELL` |
| CD-G16-033 | `buy_momentum_fading` | FLAG | STRATEGY_SPECIFIC | AGGTRADE+PRICE_RESPONSE+DELTA | buy flowまたは上方progressが明確に減衰 | `COMPOSITE:MOMENTUM:BUY` |
| CD-G16-034 | `sell_momentum_fading` | FLAG | STRATEGY_SPECIFIC | AGGTRADE+PRICE_RESPONSE+DELTA | sell flowまたは下方progressが明確に減衰 | `COMPOSITE:MOMENTUM:SELL` |
| CD-G16-035 | `bid_passive_defense_holding` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | bid補充と価格保持が継続 | `COMPOSITE:PASSIVE_DEFENSE:BID` |
| CD-G16-036 | `ask_passive_defense_holding` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | ask補充と価格保持が継続 | `COMPOSITE:PASSIVE_DEFENSE:ASK` |
| CD-G16-037 | `bid_passive_defense_failed` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | bid補充が止まり支持価格を下抜け | `COMPOSITE:PASSIVE_DEFENSE:BID` |
| CD-G16-038 | `ask_passive_defense_failed` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | ask補充が止まり抵抗価格を上抜け | `COMPOSITE:PASSIVE_DEFENSE:ASK` |
| CD-G16-039 | `two_way_trade_emerged` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 一方向flowから双方向参加へcharacter変化 | `COMPOSITE:FLOW_CHARACTER:TWO_WAY` |
| CD-G16-040 | `directional_flow_resumed_up` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | pause後にbuy主導と上方progressが再開 | `COMPOSITE:FLOW_CHARACTER:RESUME_UP` |
| CD-G16-041 | `directional_flow_resumed_down` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | pause後にsell主導と下方progressが再開 | `COMPOSITE:FLOW_CHARACTER:RESUME_DOWN` |
| CD-G16-042 | `upward_sweep_active` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 複数ask levelを短時間に連続消費 | `COMPOSITE:SWEEP:UP` |
| CD-G16-043 | `downward_sweep_active` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 複数bid levelを短時間に連続消費 | `COMPOSITE:SWEEP:DOWN` |
| CD-G16-044 | `upside_stop_run_like` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | reference上の急加速後に継続または即時失敗を伴うstop-run-like状態 | `COMPOSITE:STOP_RUN_LIKE:UP` |
| CD-G16-045 | `downside_stop_run_like` | FLAG | STRATEGY_SPECIFIC | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | reference下の急加速後に継続または即時失敗を伴うstop-run-like状態 | `COMPOSITE:STOP_RUN_LIKE:DOWN` |
| CD-G16-046 | `observed_liquidation_led_upmove` | FLAG | STRATEGY_SPECIFIC | FORCE_ORDER+AGGTRADE+PRICE_RESPONSE | 観測buy-side liquidation snapshotと上方progressが同時化 | `COMPOSITE:LIQUIDATION_LED:UP` |
| CD-G16-047 | `observed_liquidation_led_downmove` | FLAG | STRATEGY_SPECIFIC | FORCE_ORDER+AGGTRADE+PRICE_RESPONSE | 観測sell-side liquidation snapshotと下方progressが同時化 | `COMPOSITE:LIQUIDATION_LED:DOWN` |
| CD-G16-048 | `flow_price_divergence_active` | FLAG | STRATEGY_SPECIFIC | AGGTRADE+PRICE_RESPONSE+DELTA | aggressive flow方向とprice response方向が乖離 | `COMPOSITE:FLOW_PRICE:DIVERGENCE` |

## 5. Source制約

- `EXT_CALENDAR_REQUIRED`は未接続。接続前は`UNKNOWN`。
- Market-by-Price depthからindividual order、queue position、同一注文者を推定しない。
- `aggTrade`を完全MBO tapeとして扱わない。
- `forceOrder`はsampled snapshotであり、完全な清算件数・総量・cascade列を主張しない。
- HFMをBinanceと同じorder bookだと仮定しない。
- profileのpoor/excess等は定義、binning、windowの版固定前は`UNKNOWN`。

## 6. Strategyへの使用規則

1. StrategySpecは`required / supporting / contradiction / invalidation / execution / position`を明示する。
2. 一Strategyが全560件を要求してはならない。Hook topicと仮説からsubsetを引く。
3. 最終Order Triggerは少数の因果的hard condition、独立確認、反証不在、execution gateで構成する。
4. ID再利用、意味の無言変更、相関派生の独立票化を禁止する。
5. 採否、threshold、windowはwalk-forward、holdout、cost込みでStrategy variant別に検証する。
6. 本辞書だけではentry、枚数、LIVEを許可しない。
