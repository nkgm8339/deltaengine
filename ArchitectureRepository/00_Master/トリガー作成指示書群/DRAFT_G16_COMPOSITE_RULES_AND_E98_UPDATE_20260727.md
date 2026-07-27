# DRAFT: G16 Composite Rules and E98 Update

作成時刻: 2026-07-27 12:13:51 JST  
状態: **草案のみ。正本ではない。Stage 2正本反映・source実装の承認ではない。**

## 0. 結論

指定3ファイルの指示対象を照合し、E98のbefore/after草案と13件のG16 rule候補を作成した。
ただし、13件すべてで自然言語からcomparator、threshold、window、reference identity、
temporal orderingの少なくとも1つを一意に導出できない。さらに、現在のIngestion Adapterが
固定計算するTier Aは9 keyだけで、`pre_aggregated`は任意keyの無検証pass-throughである。

したがって本草案は、材料候補を狭める設計資料にはなるが、機械可読な実行正本にはできない。
停止条件`UNDEFINED`／`MISSING`が成立したため、正本反映とComposite Synthesis実装には進まない。

根拠:

- Condition Dictionaryは560件、G01〜G15は512件、G16は48件
  (`ORDER_FLOW_CONDITION_DICTIONARY_V0_1_20260726.md:4,75-93`)。
- G16は`depends_on`保持を主張するが、現表は
  `ID / condition_key / type / window / source / 定義 / independence_lineage`の7列で、
  実際の`depends_on`、論理式、threshold、reference selectorを持たない
  (`ORDER_FLOW_CONDITION_DICTIONARY_V0_1_20260726.md:665-670`)。
- G16の採否、threshold、windowは検証でStrategy variant別に決める契約である
  (`ORDER_FLOW_CONDITION_DICTIONARY_V0_1_20260726.md:729-736`)。

## 1. 読み取り結果

引用表記:

- `Condition Dictionary:Lnn`および表中の`Gxx :nn`は
  `ORDER_FLOW_CONDITION_DICTIONARY_V0_1_20260726.md:nn`を表す。
- `Bindings:nn`は`ORDER_FLOW_VARIANT_STATE_CONDITION_BINDINGS_V0_1_20260727.csv:nn`を表す。
- `condition_adapter.py:nn`は
  `Delta_Engine_Pro4web/src/strategy_engine/ingestion/condition_adapter.py:nn`を表す。

### 1.1 G01〜G15 Tier A一覧（全512件）

以下は正本行の機械転記であり、選定・改名・意味変更をしていない。

#### G01 Data Quality and Lineage

| ID | condition_key | source | 定義 | 根拠 |
|---|---|---|---|---|
| CD-G01-001 | `depth_book_synced` | ALL_SOURCES+JOURNAL | DEPTH local bookが同期済み | Condition Dictionary:L82 |
| CD-G01-002 | `depth_sequence_contiguous` | ALL_SOURCES+JOURNAL | depth update sequenceが連続 | Condition Dictionary:L83 |
| CD-G01-003 | `depth_snapshot_applied` | ALL_SOURCES+JOURNAL | snapshotとdiffの接続済み | Condition Dictionary:L84 |
| CD-G01-004 | `depth_event_fresh` | ALL_SOURCES+JOURNAL | depth event ageが上限内 | Condition Dictionary:L85 |
| CD-G01-005 | `trade_event_fresh` | ALL_SOURCES+JOURNAL | aggTrade event ageが上限内 | Condition Dictionary:L86 |
| CD-G01-006 | `liquidation_event_fresh` | ALL_SOURCES+JOURNAL | forceOrder snapshot ageが上限内 | Condition Dictionary:L87 |
| CD-G01-007 | `open_interest_snapshot_fresh` | ALL_SOURCES+JOURNAL | OI snapshot ageが上限内 | Condition Dictionary:L88 |
| CD-G01-008 | `hfm_quote_fresh` | ALL_SOURCES+JOURNAL | HFM quote ageが上限内 | Condition Dictionary:L89 |
| CD-G01-009 | `exchange_clock_aligned` | ALL_SOURCES+JOURNAL | exchange時刻差が上限内 | Condition Dictionary:L90 |
| CD-G01-010 | `receive_clock_monotonic` | ALL_SOURCES+JOURNAL | receive timestampが単調 | Condition Dictionary:L91 |
| CD-G01-011 | `event_order_monotonic` | ALL_SOURCES+JOURNAL | source event順序が正常 | Condition Dictionary:L92 |
| CD-G01-012 | `schema_version_known` | ALL_SOURCES+JOURNAL | schema versionが既知 | Condition Dictionary:L93 |
| CD-G01-013 | `symbol_mapping_valid` | ALL_SOURCES+JOURNAL | venue間symbol対応が有効 | Condition Dictionary:L94 |
| CD-G01-014 | `tick_size_valid` | ALL_SOURCES+JOURNAL | tick size契約が既知 | Condition Dictionary:L95 |
| CD-G01-015 | `quantity_step_valid` | ALL_SOURCES+JOURNAL | quantity step契約が既知 | Condition Dictionary:L96 |
| CD-G01-016 | `duplicate_event_absent` | ALL_SOURCES+JOURNAL | 重複eventが除去済み | Condition Dictionary:L97 |
| CD-G01-017 | `trade_gap_absent` | ALL_SOURCES+JOURNAL | trade stream欠落兆候なし | Condition Dictionary:L98 |
| CD-G01-018 | `depth_gap_absent` | ALL_SOURCES+JOURNAL | depth stream gapなし | Condition Dictionary:L99 |
| CD-G01-019 | `persistence_confirmed` | ALL_SOURCES+JOURNAL | 使用eventが永続化済み | Condition Dictionary:L100 |
| CD-G01-020 | `market_state_atomic` | ALL_SOURCES+JOURNAL | 同一snapshot境界でstate生成 | Condition Dictionary:L101 |
| CD-G01-021 | `cross_source_time_aligned` | ALL_SOURCES+JOURNAL | 必須source間の時刻差が上限内 | Condition Dictionary:L102 |
| CD-G01-022 | `source_reconnect_stable` | ALL_SOURCES+JOURNAL | 再接続後の安定期間を通過 | Condition Dictionary:L103 |
| CD-G01-023 | `resync_cooldown_elapsed` | ALL_SOURCES+JOURNAL | book resync後cooldownを通過 | Condition Dictionary:L104 |
| CD-G01-024 | `sampling_limit_disclosed` | ALL_SOURCES+JOURNAL | sampled source制約をlineageへ記録 | Condition Dictionary:L105 |
| CD-G01-025 | `aggregation_limit_disclosed` | ALL_SOURCES+JOURNAL | aggregated source制約をlineageへ記録 | Condition Dictionary:L106 |
| CD-G01-026 | `future_leakage_absent` | ALL_SOURCES+JOURNAL | 判断時刻より未来の値なし | Condition Dictionary:L107 |
| CD-G01-027 | `window_complete` | ALL_SOURCES+JOURNAL | 計算windowが欠損なく完成 | Condition Dictionary:L108 |
| CD-G01-028 | `baseline_sample_sufficient` | ALL_SOURCES+JOURNAL | 比較baselineの標本数が下限以上 | Condition Dictionary:L109 |

#### G02 Session and Market Regime

| ID | condition_key | source | 定義 | 根拠 |
|---|---|---|---|---|
| CD-G02-001 | `session_id` | CLOCK+MARKET_STATE | 流動性session分類 | Condition Dictionary:L115 |
| CD-G02-002 | `session_phase` | CLOCK+MARKET_STATE | session内phase分類 | Condition Dictionary:L116 |
| CD-G02-003 | `utc_hour` | CLOCK+MARKET_STATE | UTC時刻bucket | Condition Dictionary:L117 |
| CD-G02-004 | `utc_weekday` | CLOCK+MARKET_STATE | UTC曜日 | Condition Dictionary:L118 |
| CD-G02-005 | `weekend_flag` | CLOCK+MARKET_STATE | 週末取引状態 | Condition Dictionary:L119 |
| CD-G02-006 | `minutes_from_session_open` | CLOCK+MARKET_STATE | session開始からの経過分 | Condition Dictionary:L120 |
| CD-G02-007 | `minutes_to_session_close` | CLOCK+MARKET_STATE | session終了までの残分 | Condition Dictionary:L121 |
| CD-G02-008 | `asia_session_active` | CLOCK+MARKET_STATE | Asia session内 | Condition Dictionary:L122 |
| CD-G02-009 | `europe_session_active` | CLOCK+MARKET_STATE | Europe session内 | Condition Dictionary:L123 |
| CD-G02-010 | `us_session_active` | CLOCK+MARKET_STATE | US session内 | Condition Dictionary:L124 |
| CD-G02-011 | `major_session_overlap_active` | CLOCK+MARKET_STATE | 主要session重複中 | Condition Dictionary:L125 |
| CD-G02-012 | `funding_event_proximity` | MARK_FUNDING+CLOCK | 次回fundingまでの距離 | Condition Dictionary:L126 |
| CD-G02-013 | `settlement_event_proximity` | MARK_FUNDING+CLOCK | settlement時刻までの距離 | Condition Dictionary:L127 |
| CD-G02-014 | `scheduled_macro_event_proximity` | EXT_CALENDAR_REQUIRED | 予定macro eventまでの距離 | Condition Dictionary:L128 |
| CD-G02-015 | `post_news_cooldown_state` | EXT_CALENDAR_REQUIRED | news直後cooldown状態 | Condition Dictionary:L129 |
| CD-G02-016 | `trend_regime` | CLOCK+MARKET_STATE | 上昇下降非trendのregime | Condition Dictionary:L130 |
| CD-G02-017 | `balance_regime` | CLOCK+MARKET_STATE | balanceまたはdirectional分類 | Condition Dictionary:L131 |
| CD-G02-018 | `compression_regime` | CLOCK+MARKET_STATE | 値幅圧縮状態 | Condition Dictionary:L132 |
| CD-G02-019 | `expansion_regime` | CLOCK+MARKET_STATE | 値幅拡大型状態 | Condition Dictionary:L133 |
| CD-G02-020 | `participation_regime` | CLOCK+MARKET_STATE | 取引参加量regime | Condition Dictionary:L134 |
| CD-G02-021 | `volatility_regime` | CLOCK+MARKET_STATE | volatility regime | Condition Dictionary:L135 |
| CD-G02-022 | `liquidity_regime` | CLOCK+MARKET_STATE | liquidity regime | Condition Dictionary:L136 |
| CD-G02-023 | `regime_age` | CLOCK+MARKET_STATE | 現regime継続時間 | Condition Dictionary:L137 |
| CD-G02-024 | `regime_transition_flag` | CLOCK+MARKET_STATE | regime転換検出 | Condition Dictionary:L138 |

#### G03 Price and Location

| ID | condition_key | source | 定義 | 根拠 |
|---|---|---|---|---|
| CD-G03-001 | `distance_to_best_bid` | DEPTH+AGGTRADE+PROFILE | best bidまでの符号付きtick距離 | Condition Dictionary:L144 |
| CD-G03-002 | `relation_to_best_bid` | DEPTH+AGGTRADE+PROFILE | best bidに対するABOVE AT BELOW | Condition Dictionary:L145 |
| CD-G03-003 | `distance_to_best_ask` | DEPTH+AGGTRADE+PROFILE | best askまでの符号付きtick距離 | Condition Dictionary:L146 |
| CD-G03-004 | `relation_to_best_ask` | DEPTH+AGGTRADE+PROFILE | best askに対するABOVE AT BELOW | Condition Dictionary:L147 |
| CD-G03-005 | `distance_to_mid_price` | DEPTH+AGGTRADE+PROFILE | mid priceまでの符号付きtick距離 | Condition Dictionary:L148 |
| CD-G03-006 | `relation_to_mid_price` | DEPTH+AGGTRADE+PROFILE | mid priceに対するABOVE AT BELOW | Condition Dictionary:L149 |
| CD-G03-007 | `distance_to_microprice` | DEPTH+AGGTRADE+PROFILE | micropriceまでの符号付きtick距離 | Condition Dictionary:L150 |
| CD-G03-008 | `relation_to_microprice` | DEPTH+AGGTRADE+PROFILE | micropriceに対するABOVE AT BELOW | Condition Dictionary:L151 |
| CD-G03-009 | `distance_to_session_open` | DEPTH+AGGTRADE+PROFILE | session openまでの符号付きtick距離 | Condition Dictionary:L152 |
| CD-G03-010 | `relation_to_session_open` | DEPTH+AGGTRADE+PROFILE | session openに対するABOVE AT BELOW | Condition Dictionary:L153 |
| CD-G03-011 | `distance_to_session_high` | DEPTH+AGGTRADE+PROFILE | session highまでの符号付きtick距離 | Condition Dictionary:L154 |
| CD-G03-012 | `relation_to_session_high` | DEPTH+AGGTRADE+PROFILE | session highに対するABOVE AT BELOW | Condition Dictionary:L155 |
| CD-G03-013 | `distance_to_session_low` | DEPTH+AGGTRADE+PROFILE | session lowまでの符号付きtick距離 | Condition Dictionary:L156 |
| CD-G03-014 | `relation_to_session_low` | DEPTH+AGGTRADE+PROFILE | session lowに対するABOVE AT BELOW | Condition Dictionary:L157 |
| CD-G03-015 | `distance_to_previous_day_high` | DEPTH+AGGTRADE+PROFILE | previous day highまでの符号付きtick距離 | Condition Dictionary:L158 |
| CD-G03-016 | `relation_to_previous_day_high` | DEPTH+AGGTRADE+PROFILE | previous day highに対するABOVE AT BELOW | Condition Dictionary:L159 |
| CD-G03-017 | `distance_to_previous_day_low` | DEPTH+AGGTRADE+PROFILE | previous day lowまでの符号付きtick距離 | Condition Dictionary:L160 |
| CD-G03-018 | `relation_to_previous_day_low` | DEPTH+AGGTRADE+PROFILE | previous day lowに対するABOVE AT BELOW | Condition Dictionary:L161 |
| CD-G03-019 | `distance_to_previous_day_close` | DEPTH+AGGTRADE+PROFILE | previous day closeまでの符号付きtick距離 | Condition Dictionary:L162 |
| CD-G03-020 | `relation_to_previous_day_close` | DEPTH+AGGTRADE+PROFILE | previous day closeに対するABOVE AT BELOW | Condition Dictionary:L163 |
| CD-G03-021 | `distance_to_rolling_1m_high` | DEPTH+AGGTRADE+PROFILE | 直近1分highまでの符号付きtick距離 | Condition Dictionary:L164 |
| CD-G03-022 | `relation_to_rolling_1m_high` | DEPTH+AGGTRADE+PROFILE | 直近1分highに対するABOVE AT BELOW | Condition Dictionary:L165 |
| CD-G03-023 | `distance_to_rolling_1m_low` | DEPTH+AGGTRADE+PROFILE | 直近1分lowまでの符号付きtick距離 | Condition Dictionary:L166 |
| CD-G03-024 | `relation_to_rolling_1m_low` | DEPTH+AGGTRADE+PROFILE | 直近1分lowに対するABOVE AT BELOW | Condition Dictionary:L167 |
| CD-G03-025 | `distance_to_rolling_5m_high` | DEPTH+AGGTRADE+PROFILE | 直近5分highまでの符号付きtick距離 | Condition Dictionary:L168 |
| CD-G03-026 | `relation_to_rolling_5m_high` | DEPTH+AGGTRADE+PROFILE | 直近5分highに対するABOVE AT BELOW | Condition Dictionary:L169 |
| CD-G03-027 | `distance_to_rolling_5m_low` | DEPTH+AGGTRADE+PROFILE | 直近5分lowまでの符号付きtick距離 | Condition Dictionary:L170 |
| CD-G03-028 | `relation_to_rolling_5m_low` | DEPTH+AGGTRADE+PROFILE | 直近5分lowに対するABOVE AT BELOW | Condition Dictionary:L171 |
| CD-G03-029 | `distance_to_rolling_15m_high` | DEPTH+AGGTRADE+PROFILE | 直近15分highまでの符号付きtick距離 | Condition Dictionary:L172 |
| CD-G03-030 | `relation_to_rolling_15m_high` | DEPTH+AGGTRADE+PROFILE | 直近15分highに対するABOVE AT BELOW | Condition Dictionary:L173 |
| CD-G03-031 | `distance_to_rolling_15m_low` | DEPTH+AGGTRADE+PROFILE | 直近15分lowまでの符号付きtick距離 | Condition Dictionary:L174 |
| CD-G03-032 | `relation_to_rolling_15m_low` | DEPTH+AGGTRADE+PROFILE | 直近15分lowに対するABOVE AT BELOW | Condition Dictionary:L175 |
| CD-G03-033 | `distance_to_rolling_1h_high` | DEPTH+AGGTRADE+PROFILE | 直近1時間highまでの符号付きtick距離 | Condition Dictionary:L176 |
| CD-G03-034 | `relation_to_rolling_1h_high` | DEPTH+AGGTRADE+PROFILE | 直近1時間highに対するABOVE AT BELOW | Condition Dictionary:L177 |
| CD-G03-035 | `distance_to_rolling_1h_low` | DEPTH+AGGTRADE+PROFILE | 直近1時間lowまでの符号付きtick距離 | Condition Dictionary:L178 |
| CD-G03-036 | `relation_to_rolling_1h_low` | DEPTH+AGGTRADE+PROFILE | 直近1時間lowに対するABOVE AT BELOW | Condition Dictionary:L179 |
| CD-G03-037 | `distance_to_session_vwap` | DEPTH+AGGTRADE+PROFILE | session VWAPまでの符号付きtick距離 | Condition Dictionary:L180 |
| CD-G03-038 | `relation_to_session_vwap` | DEPTH+AGGTRADE+PROFILE | session VWAPに対するABOVE AT BELOW | Condition Dictionary:L181 |
| CD-G03-039 | `distance_to_session_open_avwap` | DEPTH+AGGTRADE+PROFILE | session open AVWAPまでの符号付きtick距離 | Condition Dictionary:L182 |
| CD-G03-040 | `relation_to_session_open_avwap` | DEPTH+AGGTRADE+PROFILE | session open AVWAPに対するABOVE AT BELOW | Condition Dictionary:L183 |
| CD-G03-041 | `distance_to_profile_poc` | DEPTH+AGGTRADE+PROFILE | profile POCまでの符号付きtick距離 | Condition Dictionary:L184 |
| CD-G03-042 | `relation_to_profile_poc` | DEPTH+AGGTRADE+PROFILE | profile POCに対するABOVE AT BELOW | Condition Dictionary:L185 |
| CD-G03-043 | `distance_to_profile_vah` | DEPTH+AGGTRADE+PROFILE | value area highまでの符号付きtick距離 | Condition Dictionary:L186 |
| CD-G03-044 | `relation_to_profile_vah` | DEPTH+AGGTRADE+PROFILE | value area highに対するABOVE AT BELOW | Condition Dictionary:L187 |
| CD-G03-045 | `distance_to_profile_val` | DEPTH+AGGTRADE+PROFILE | value area lowまでの符号付きtick距離 | Condition Dictionary:L188 |
| CD-G03-046 | `relation_to_profile_val` | DEPTH+AGGTRADE+PROFILE | value area lowに対するABOVE AT BELOW | Condition Dictionary:L189 |
| CD-G03-047 | `distance_to_active_range_mid` | DEPTH+AGGTRADE+PROFILE | active range midpointまでの符号付きtick距離 | Condition Dictionary:L190 |
| CD-G03-048 | `relation_to_active_range_mid` | DEPTH+AGGTRADE+PROFILE | active range midpointに対するABOVE AT BELOW | Condition Dictionary:L191 |

#### G04 Volatility and Tradeability

| ID | condition_key | source | 定義 | 根拠 |
|---|---|---|---|---|
| CD-G04-001 | `realized_volatility_1s` | AGGTRADE | 1s realized volatility | Condition Dictionary:L197 |
| CD-G04-002 | `price_range_ticks_1s` | AGGTRADE | 1s high-low tick幅 | Condition Dictionary:L198 |
| CD-G04-003 | `realized_volatility_5s` | AGGTRADE | 5s realized volatility | Condition Dictionary:L199 |
| CD-G04-004 | `price_range_ticks_5s` | AGGTRADE | 5s high-low tick幅 | Condition Dictionary:L200 |
| CD-G04-005 | `realized_volatility_30s` | AGGTRADE | 30s realized volatility | Condition Dictionary:L201 |
| CD-G04-006 | `price_range_ticks_30s` | AGGTRADE | 30s high-low tick幅 | Condition Dictionary:L202 |
| CD-G04-007 | `realized_volatility_1m` | AGGTRADE | 1m realized volatility | Condition Dictionary:L203 |
| CD-G04-008 | `price_range_ticks_1m` | AGGTRADE | 1m high-low tick幅 | Condition Dictionary:L204 |
| CD-G04-009 | `realized_volatility_5m` | AGGTRADE | 5m realized volatility | Condition Dictionary:L205 |
| CD-G04-010 | `price_range_ticks_5m` | AGGTRADE | 5m high-low tick幅 | Condition Dictionary:L206 |
| CD-G04-011 | `spread_ticks` | DEPTH | best spread tick数 | Condition Dictionary:L207 |
| CD-G04-012 | `spread_percentile_1m` | DEPTH | 1m spread percentile | Condition Dictionary:L208 |
| CD-G04-013 | `spread_percentile_5m` | DEPTH | 5m spread percentile | Condition Dictionary:L209 |
| CD-G04-014 | `spread_percentile_1h` | DEPTH | 1h spread percentile | Condition Dictionary:L210 |
| CD-G04-015 | `trade_rate_percentile_1m` | AGGTRADE | 1m trade rate percentile | Condition Dictionary:L211 |
| CD-G04-016 | `trade_rate_percentile_5m` | AGGTRADE | 5m trade rate percentile | Condition Dictionary:L212 |
| CD-G04-017 | `bid_top5_depth_percentile_1m` | DEPTH | bid top5 depth percentile 1m | Condition Dictionary:L213 |
| CD-G04-018 | `bid_top5_depth_percentile_5m` | DEPTH | bid top5 depth percentile 5m | Condition Dictionary:L214 |
| CD-G04-019 | `ask_top5_depth_percentile_1m` | DEPTH | ask top5 depth percentile 1m | Condition Dictionary:L215 |
| CD-G04-020 | `ask_top5_depth_percentile_5m` | DEPTH | ask top5 depth percentile 5m | Condition Dictionary:L216 |
| CD-G04-021 | `estimated_buy_impact_ticks` | DEPTH+AGGTRADE | 基準notional買いの推定impact | Condition Dictionary:L217 |
| CD-G04-022 | `estimated_sell_impact_ticks` | DEPTH+AGGTRADE | 基準notional売りの推定impact | Condition Dictionary:L218 |
| CD-G04-023 | `volatility_state` | AGGTRADE | LOW NORMAL HIGH EXTREME | Condition Dictionary:L219 |
| CD-G04-024 | `tradeability_state` | DEPTH+AGGTRADE | DEEP NORMAL THIN DISLOCATED | Condition Dictionary:L220 |

#### G05 Raw Limit Order Book

| ID | condition_key | source | 定義 | 根拠 |
|---|---|---|---|---|
| CD-G05-001 | `bid_l1_price` | DEPTH | bid第1level price | Condition Dictionary:L226 |
| CD-G05-002 | `bid_l2_price` | DEPTH | bid第2level price | Condition Dictionary:L227 |
| CD-G05-003 | `bid_l3_price` | DEPTH | bid第3level price | Condition Dictionary:L228 |
| CD-G05-004 | `bid_l4_price` | DEPTH | bid第4level price | Condition Dictionary:L229 |
| CD-G05-005 | `bid_l5_price` | DEPTH | bid第5level price | Condition Dictionary:L230 |
| CD-G05-006 | `bid_l6_price` | DEPTH | bid第6level price | Condition Dictionary:L231 |
| CD-G05-007 | `bid_l7_price` | DEPTH | bid第7level price | Condition Dictionary:L232 |
| CD-G05-008 | `bid_l8_price` | DEPTH | bid第8level price | Condition Dictionary:L233 |
| CD-G05-009 | `bid_l9_price` | DEPTH | bid第9level price | Condition Dictionary:L234 |
| CD-G05-010 | `bid_l10_price` | DEPTH | bid第10level price | Condition Dictionary:L235 |
| CD-G05-011 | `bid_l1_quantity` | DEPTH | bid第1level quantity | Condition Dictionary:L236 |
| CD-G05-012 | `bid_l2_quantity` | DEPTH | bid第2level quantity | Condition Dictionary:L237 |
| CD-G05-013 | `bid_l3_quantity` | DEPTH | bid第3level quantity | Condition Dictionary:L238 |
| CD-G05-014 | `bid_l4_quantity` | DEPTH | bid第4level quantity | Condition Dictionary:L239 |
| CD-G05-015 | `bid_l5_quantity` | DEPTH | bid第5level quantity | Condition Dictionary:L240 |
| CD-G05-016 | `bid_l6_quantity` | DEPTH | bid第6level quantity | Condition Dictionary:L241 |
| CD-G05-017 | `bid_l7_quantity` | DEPTH | bid第7level quantity | Condition Dictionary:L242 |
| CD-G05-018 | `bid_l8_quantity` | DEPTH | bid第8level quantity | Condition Dictionary:L243 |
| CD-G05-019 | `bid_l9_quantity` | DEPTH | bid第9level quantity | Condition Dictionary:L244 |
| CD-G05-020 | `bid_l10_quantity` | DEPTH | bid第10level quantity | Condition Dictionary:L245 |
| CD-G05-021 | `ask_l1_price` | DEPTH | ask第1level price | Condition Dictionary:L246 |
| CD-G05-022 | `ask_l2_price` | DEPTH | ask第2level price | Condition Dictionary:L247 |
| CD-G05-023 | `ask_l3_price` | DEPTH | ask第3level price | Condition Dictionary:L248 |
| CD-G05-024 | `ask_l4_price` | DEPTH | ask第4level price | Condition Dictionary:L249 |
| CD-G05-025 | `ask_l5_price` | DEPTH | ask第5level price | Condition Dictionary:L250 |
| CD-G05-026 | `ask_l6_price` | DEPTH | ask第6level price | Condition Dictionary:L251 |
| CD-G05-027 | `ask_l7_price` | DEPTH | ask第7level price | Condition Dictionary:L252 |
| CD-G05-028 | `ask_l8_price` | DEPTH | ask第8level price | Condition Dictionary:L253 |
| CD-G05-029 | `ask_l9_price` | DEPTH | ask第9level price | Condition Dictionary:L254 |
| CD-G05-030 | `ask_l10_price` | DEPTH | ask第10level price | Condition Dictionary:L255 |
| CD-G05-031 | `ask_l1_quantity` | DEPTH | ask第1level quantity | Condition Dictionary:L256 |
| CD-G05-032 | `ask_l2_quantity` | DEPTH | ask第2level quantity | Condition Dictionary:L257 |
| CD-G05-033 | `ask_l3_quantity` | DEPTH | ask第3level quantity | Condition Dictionary:L258 |
| CD-G05-034 | `ask_l4_quantity` | DEPTH | ask第4level quantity | Condition Dictionary:L259 |
| CD-G05-035 | `ask_l5_quantity` | DEPTH | ask第5level quantity | Condition Dictionary:L260 |
| CD-G05-036 | `ask_l6_quantity` | DEPTH | ask第6level quantity | Condition Dictionary:L261 |
| CD-G05-037 | `ask_l7_quantity` | DEPTH | ask第7level quantity | Condition Dictionary:L262 |
| CD-G05-038 | `ask_l8_quantity` | DEPTH | ask第8level quantity | Condition Dictionary:L263 |
| CD-G05-039 | `ask_l9_quantity` | DEPTH | ask第9level quantity | Condition Dictionary:L264 |
| CD-G05-040 | `ask_l10_quantity` | DEPTH | ask第10level quantity | Condition Dictionary:L265 |

#### G06 Book Shape and Static Imbalance

| ID | condition_key | source | 定義 | 根拠 |
|---|---|---|---|---|
| CD-G06-001 | `bid_cumulative_depth_top1` | DEPTH | bid top1累積depth | Condition Dictionary:L271 |
| CD-G06-002 | `bid_cumulative_depth_top3` | DEPTH | bid top3累積depth | Condition Dictionary:L272 |
| CD-G06-003 | `bid_cumulative_depth_top5` | DEPTH | bid top5累積depth | Condition Dictionary:L273 |
| CD-G06-004 | `bid_cumulative_depth_top10` | DEPTH | bid top10累積depth | Condition Dictionary:L274 |
| CD-G06-005 | `ask_cumulative_depth_top1` | DEPTH | ask top1累積depth | Condition Dictionary:L275 |
| CD-G06-006 | `ask_cumulative_depth_top3` | DEPTH | ask top3累積depth | Condition Dictionary:L276 |
| CD-G06-007 | `ask_cumulative_depth_top5` | DEPTH | ask top5累積depth | Condition Dictionary:L277 |
| CD-G06-008 | `ask_cumulative_depth_top10` | DEPTH | ask top10累積depth | Condition Dictionary:L278 |
| CD-G06-009 | `queue_imbalance_top1` | DEPTH | top1 queue imbalance | Condition Dictionary:L279 |
| CD-G06-010 | `microprice_top1` | DEPTH | top1 depth加重microprice | Condition Dictionary:L280 |
| CD-G06-011 | `queue_imbalance_top3` | DEPTH | top3 queue imbalance | Condition Dictionary:L281 |
| CD-G06-012 | `microprice_top3` | DEPTH | top3 depth加重microprice | Condition Dictionary:L282 |
| CD-G06-013 | `queue_imbalance_top5` | DEPTH | top5 queue imbalance | Condition Dictionary:L283 |
| CD-G06-014 | `microprice_top5` | DEPTH | top5 depth加重microprice | Condition Dictionary:L284 |
| CD-G06-015 | `queue_imbalance_top10` | DEPTH | top10 queue imbalance | Condition Dictionary:L285 |
| CD-G06-016 | `microprice_top10` | DEPTH | top10 depth加重microprice | Condition Dictionary:L286 |
| CD-G06-017 | `bid_depth_slope_top3` | DEPTH | bid top3 depth slope | Condition Dictionary:L287 |
| CD-G06-018 | `bid_depth_convexity_top3` | DEPTH | bid top3 depth convexity | Condition Dictionary:L288 |
| CD-G06-019 | `bid_depth_slope_top5` | DEPTH | bid top5 depth slope | Condition Dictionary:L289 |
| CD-G06-020 | `bid_depth_convexity_top5` | DEPTH | bid top5 depth convexity | Condition Dictionary:L290 |
| CD-G06-021 | `bid_depth_slope_top10` | DEPTH | bid top10 depth slope | Condition Dictionary:L291 |
| CD-G06-022 | `bid_depth_convexity_top10` | DEPTH | bid top10 depth convexity | Condition Dictionary:L292 |
| CD-G06-023 | `ask_depth_slope_top3` | DEPTH | ask top3 depth slope | Condition Dictionary:L293 |
| CD-G06-024 | `ask_depth_convexity_top3` | DEPTH | ask top3 depth convexity | Condition Dictionary:L294 |
| CD-G06-025 | `ask_depth_slope_top5` | DEPTH | ask top5 depth slope | Condition Dictionary:L295 |
| CD-G06-026 | `ask_depth_convexity_top5` | DEPTH | ask top5 depth convexity | Condition Dictionary:L296 |
| CD-G06-027 | `ask_depth_slope_top10` | DEPTH | ask top10 depth slope | Condition Dictionary:L297 |
| CD-G06-028 | `ask_depth_convexity_top10` | DEPTH | ask top10 depth convexity | Condition Dictionary:L298 |
| CD-G06-029 | `bid_wall_concentration_top10` | DEPTH | bid top10最大level数量比率 | Condition Dictionary:L299 |
| CD-G06-030 | `distance_to_nearest_bid_wall` | DEPTH | nearest bid wall距離 | Condition Dictionary:L300 |
| CD-G06-031 | `ask_wall_concentration_top10` | DEPTH | ask top10最大level数量比率 | Condition Dictionary:L301 |
| CD-G06-032 | `distance_to_nearest_ask_wall` | DEPTH | nearest ask wall距離 | Condition Dictionary:L302 |

#### G07 Book Event Flow

| ID | condition_key | source | 定義 | 根拠 |
|---|---|---|---|---|
| CD-G07-001 | `bid_add_volume_100ms` | DEPTH | bid 表示数量追加量 | Condition Dictionary:L308 |
| CD-G07-002 | `bid_add_volume_1s` | DEPTH | bid 表示数量追加量 | Condition Dictionary:L309 |
| CD-G07-003 | `bid_add_volume_5s` | DEPTH | bid 表示数量追加量 | Condition Dictionary:L310 |
| CD-G07-004 | `bid_cancel_volume_100ms` | DEPTH | bid 表示数量取消量 | Condition Dictionary:L311 |
| CD-G07-005 | `bid_cancel_volume_1s` | DEPTH | bid 表示数量取消量 | Condition Dictionary:L312 |
| CD-G07-006 | `bid_cancel_volume_5s` | DEPTH | bid 表示数量取消量 | Condition Dictionary:L313 |
| CD-G07-007 | `bid_net_flow_100ms` | DEPTH | bid 追加量マイナス取消量 | Condition Dictionary:L314 |
| CD-G07-008 | `bid_net_flow_1s` | DEPTH | bid 追加量マイナス取消量 | Condition Dictionary:L315 |
| CD-G07-009 | `bid_net_flow_5s` | DEPTH | bid 追加量マイナス取消量 | Condition Dictionary:L316 |
| CD-G07-010 | `bid_refresh_count_100ms` | DEPTH | bid best近傍補充回数 | Condition Dictionary:L317 |
| CD-G07-011 | `bid_refresh_count_1s` | DEPTH | bid best近傍補充回数 | Condition Dictionary:L318 |
| CD-G07-012 | `bid_refresh_count_5s` | DEPTH | bid best近傍補充回数 | Condition Dictionary:L319 |
| CD-G07-013 | `bid_pull_ratio_100ms` | DEPTH | bid pull比率 | Condition Dictionary:L320 |
| CD-G07-014 | `bid_pull_ratio_1s` | DEPTH | bid pull比率 | Condition Dictionary:L321 |
| CD-G07-015 | `bid_pull_ratio_5s` | DEPTH | bid pull比率 | Condition Dictionary:L322 |
| CD-G07-016 | `bid_stack_ratio_100ms` | DEPTH | bid stack比率 | Condition Dictionary:L323 |
| CD-G07-017 | `bid_stack_ratio_1s` | DEPTH | bid stack比率 | Condition Dictionary:L324 |
| CD-G07-018 | `bid_stack_ratio_5s` | DEPTH | bid stack比率 | Condition Dictionary:L325 |
| CD-G07-019 | `bid_level_turnover_100ms` | DEPTH | bid price level入替率 | Condition Dictionary:L326 |
| CD-G07-020 | `bid_level_turnover_1s` | DEPTH | bid price level入替率 | Condition Dictionary:L327 |
| CD-G07-021 | `bid_level_turnover_5s` | DEPTH | bid price level入替率 | Condition Dictionary:L328 |
| CD-G07-022 | `bid_depth_change_100ms` | DEPTH | bid window前後depth変化 | Condition Dictionary:L329 |
| CD-G07-023 | `bid_depth_change_1s` | DEPTH | bid window前後depth変化 | Condition Dictionary:L330 |
| CD-G07-024 | `bid_depth_change_5s` | DEPTH | bid window前後depth変化 | Condition Dictionary:L331 |
| CD-G07-025 | `ask_add_volume_100ms` | DEPTH | ask 表示数量追加量 | Condition Dictionary:L332 |
| CD-G07-026 | `ask_add_volume_1s` | DEPTH | ask 表示数量追加量 | Condition Dictionary:L333 |
| CD-G07-027 | `ask_add_volume_5s` | DEPTH | ask 表示数量追加量 | Condition Dictionary:L334 |
| CD-G07-028 | `ask_cancel_volume_100ms` | DEPTH | ask 表示数量取消量 | Condition Dictionary:L335 |
| CD-G07-029 | `ask_cancel_volume_1s` | DEPTH | ask 表示数量取消量 | Condition Dictionary:L336 |
| CD-G07-030 | `ask_cancel_volume_5s` | DEPTH | ask 表示数量取消量 | Condition Dictionary:L337 |
| CD-G07-031 | `ask_net_flow_100ms` | DEPTH | ask 追加量マイナス取消量 | Condition Dictionary:L338 |
| CD-G07-032 | `ask_net_flow_1s` | DEPTH | ask 追加量マイナス取消量 | Condition Dictionary:L339 |
| CD-G07-033 | `ask_net_flow_5s` | DEPTH | ask 追加量マイナス取消量 | Condition Dictionary:L340 |
| CD-G07-034 | `ask_refresh_count_100ms` | DEPTH | ask best近傍補充回数 | Condition Dictionary:L341 |
| CD-G07-035 | `ask_refresh_count_1s` | DEPTH | ask best近傍補充回数 | Condition Dictionary:L342 |
| CD-G07-036 | `ask_refresh_count_5s` | DEPTH | ask best近傍補充回数 | Condition Dictionary:L343 |
| CD-G07-037 | `ask_pull_ratio_100ms` | DEPTH | ask pull比率 | Condition Dictionary:L344 |
| CD-G07-038 | `ask_pull_ratio_1s` | DEPTH | ask pull比率 | Condition Dictionary:L345 |
| CD-G07-039 | `ask_pull_ratio_5s` | DEPTH | ask pull比率 | Condition Dictionary:L346 |
| CD-G07-040 | `ask_stack_ratio_100ms` | DEPTH | ask stack比率 | Condition Dictionary:L347 |
| CD-G07-041 | `ask_stack_ratio_1s` | DEPTH | ask stack比率 | Condition Dictionary:L348 |
| CD-G07-042 | `ask_stack_ratio_5s` | DEPTH | ask stack比率 | Condition Dictionary:L349 |
| CD-G07-043 | `ask_level_turnover_100ms` | DEPTH | ask price level入替率 | Condition Dictionary:L350 |
| CD-G07-044 | `ask_level_turnover_1s` | DEPTH | ask price level入替率 | Condition Dictionary:L351 |
| CD-G07-045 | `ask_level_turnover_5s` | DEPTH | ask price level入替率 | Condition Dictionary:L352 |
| CD-G07-046 | `ask_depth_change_100ms` | DEPTH | ask window前後depth変化 | Condition Dictionary:L353 |
| CD-G07-047 | `ask_depth_change_1s` | DEPTH | ask window前後depth変化 | Condition Dictionary:L354 |
| CD-G07-048 | `ask_depth_change_5s` | DEPTH | ask window前後depth変化 | Condition Dictionary:L355 |

#### G08 Aggressive Trade Tape

| ID | condition_key | source | 定義 | 根拠 |
|---|---|---|---|---|
| CD-G08-001 | `buy_market_volume_100ms` | AGGTRADE | buy aggressive volume | Condition Dictionary:L361 |
| CD-G08-002 | `buy_market_volume_1s` | AGGTRADE | buy aggressive volume | Condition Dictionary:L362 |
| CD-G08-003 | `buy_market_volume_5s` | AGGTRADE | buy aggressive volume | Condition Dictionary:L363 |
| CD-G08-004 | `buy_trade_count_100ms` | AGGTRADE | buy aggTrade件数 | Condition Dictionary:L364 |
| CD-G08-005 | `buy_trade_count_1s` | AGGTRADE | buy aggTrade件数 | Condition Dictionary:L365 |
| CD-G08-006 | `buy_trade_count_5s` | AGGTRADE | buy aggTrade件数 | Condition Dictionary:L366 |
| CD-G08-007 | `buy_average_trade_size_100ms` | AGGTRADE | buy 平均trade size | Condition Dictionary:L367 |
| CD-G08-008 | `buy_average_trade_size_1s` | AGGTRADE | buy 平均trade size | Condition Dictionary:L368 |
| CD-G08-009 | `buy_average_trade_size_5s` | AGGTRADE | buy 平均trade size | Condition Dictionary:L369 |
| CD-G08-010 | `buy_max_trade_size_100ms` | AGGTRADE | buy 最大trade size | Condition Dictionary:L370 |
| CD-G08-011 | `buy_max_trade_size_1s` | AGGTRADE | buy 最大trade size | Condition Dictionary:L371 |
| CD-G08-012 | `buy_max_trade_size_5s` | AGGTRADE | buy 最大trade size | Condition Dictionary:L372 |
| CD-G08-013 | `buy_large_trade_count_100ms` | AGGTRADE | buy large trade件数 | Condition Dictionary:L373 |
| CD-G08-014 | `buy_large_trade_count_1s` | AGGTRADE | buy large trade件数 | Condition Dictionary:L374 |
| CD-G08-015 | `buy_large_trade_count_5s` | AGGTRADE | buy large trade件数 | Condition Dictionary:L375 |
| CD-G08-016 | `buy_trade_rate_100ms` | AGGTRADE | buy 秒換算trade rate | Condition Dictionary:L376 |
| CD-G08-017 | `buy_trade_rate_1s` | AGGTRADE | buy 秒換算trade rate | Condition Dictionary:L377 |
| CD-G08-018 | `buy_trade_rate_5s` | AGGTRADE | buy 秒換算trade rate | Condition Dictionary:L378 |
| CD-G08-019 | `buy_notional_100ms` | AGGTRADE | buy aggressive notional | Condition Dictionary:L379 |
| CD-G08-020 | `buy_notional_1s` | AGGTRADE | buy aggressive notional | Condition Dictionary:L380 |
| CD-G08-021 | `buy_notional_5s` | AGGTRADE | buy aggressive notional | Condition Dictionary:L381 |
| CD-G08-022 | `buy_side_share_100ms` | AGGTRADE | buy 全flow内side比率 | Condition Dictionary:L382 |
| CD-G08-023 | `buy_side_share_1s` | AGGTRADE | buy 全flow内side比率 | Condition Dictionary:L383 |
| CD-G08-024 | `buy_side_share_5s` | AGGTRADE | buy 全flow内side比率 | Condition Dictionary:L384 |
| CD-G08-025 | `sell_market_volume_100ms` | AGGTRADE | sell aggressive volume | Condition Dictionary:L385 |
| CD-G08-026 | `sell_market_volume_1s` | AGGTRADE | sell aggressive volume | Condition Dictionary:L386 |
| CD-G08-027 | `sell_market_volume_5s` | AGGTRADE | sell aggressive volume | Condition Dictionary:L387 |
| CD-G08-028 | `sell_trade_count_100ms` | AGGTRADE | sell aggTrade件数 | Condition Dictionary:L388 |
| CD-G08-029 | `sell_trade_count_1s` | AGGTRADE | sell aggTrade件数 | Condition Dictionary:L389 |
| CD-G08-030 | `sell_trade_count_5s` | AGGTRADE | sell aggTrade件数 | Condition Dictionary:L390 |
| CD-G08-031 | `sell_average_trade_size_100ms` | AGGTRADE | sell 平均trade size | Condition Dictionary:L391 |
| CD-G08-032 | `sell_average_trade_size_1s` | AGGTRADE | sell 平均trade size | Condition Dictionary:L392 |
| CD-G08-033 | `sell_average_trade_size_5s` | AGGTRADE | sell 平均trade size | Condition Dictionary:L393 |
| CD-G08-034 | `sell_max_trade_size_100ms` | AGGTRADE | sell 最大trade size | Condition Dictionary:L394 |
| CD-G08-035 | `sell_max_trade_size_1s` | AGGTRADE | sell 最大trade size | Condition Dictionary:L395 |
| CD-G08-036 | `sell_max_trade_size_5s` | AGGTRADE | sell 最大trade size | Condition Dictionary:L396 |
| CD-G08-037 | `sell_large_trade_count_100ms` | AGGTRADE | sell large trade件数 | Condition Dictionary:L397 |
| CD-G08-038 | `sell_large_trade_count_1s` | AGGTRADE | sell large trade件数 | Condition Dictionary:L398 |
| CD-G08-039 | `sell_large_trade_count_5s` | AGGTRADE | sell large trade件数 | Condition Dictionary:L399 |
| CD-G08-040 | `sell_trade_rate_100ms` | AGGTRADE | sell 秒換算trade rate | Condition Dictionary:L400 |
| CD-G08-041 | `sell_trade_rate_1s` | AGGTRADE | sell 秒換算trade rate | Condition Dictionary:L401 |
| CD-G08-042 | `sell_trade_rate_5s` | AGGTRADE | sell 秒換算trade rate | Condition Dictionary:L402 |
| CD-G08-043 | `sell_notional_100ms` | AGGTRADE | sell aggressive notional | Condition Dictionary:L403 |
| CD-G08-044 | `sell_notional_1s` | AGGTRADE | sell aggressive notional | Condition Dictionary:L404 |
| CD-G08-045 | `sell_notional_5s` | AGGTRADE | sell aggressive notional | Condition Dictionary:L405 |
| CD-G08-046 | `sell_side_share_100ms` | AGGTRADE | sell 全flow内side比率 | Condition Dictionary:L406 |
| CD-G08-047 | `sell_side_share_1s` | AGGTRADE | sell 全flow内side比率 | Condition Dictionary:L407 |
| CD-G08-048 | `sell_side_share_5s` | AGGTRADE | sell 全flow内side比率 | Condition Dictionary:L408 |

#### G09 Flow Price Response

| ID | condition_key | source | 定義 | 根拠 |
|---|---|---|---|---|
| CD-G09-001 | `upward_progress_ticks_100ms` | DEPTH+AGGTRADE | 上方向price progress | Condition Dictionary:L414 |
| CD-G09-002 | `upward_progress_ticks_1s` | DEPTH+AGGTRADE | 上方向price progress | Condition Dictionary:L415 |
| CD-G09-003 | `upward_progress_ticks_5s` | DEPTH+AGGTRADE | 上方向price progress | Condition Dictionary:L416 |
| CD-G09-004 | `upward_progress_ticks_30s` | DEPTH+AGGTRADE | 上方向price progress | Condition Dictionary:L417 |
| CD-G09-005 | `downward_progress_ticks_100ms` | DEPTH+AGGTRADE | 下方向price progress | Condition Dictionary:L418 |
| CD-G09-006 | `downward_progress_ticks_1s` | DEPTH+AGGTRADE | 下方向price progress | Condition Dictionary:L419 |
| CD-G09-007 | `downward_progress_ticks_5s` | DEPTH+AGGTRADE | 下方向price progress | Condition Dictionary:L420 |
| CD-G09-008 | `downward_progress_ticks_30s` | DEPTH+AGGTRADE | 下方向price progress | Condition Dictionary:L421 |
| CD-G09-009 | `buy_impact_per_notional_100ms` | DEPTH+AGGTRADE | buy flow当たり上方impact | Condition Dictionary:L422 |
| CD-G09-010 | `buy_impact_per_notional_1s` | DEPTH+AGGTRADE | buy flow当たり上方impact | Condition Dictionary:L423 |
| CD-G09-011 | `buy_impact_per_notional_5s` | DEPTH+AGGTRADE | buy flow当たり上方impact | Condition Dictionary:L424 |
| CD-G09-012 | `buy_impact_per_notional_30s` | DEPTH+AGGTRADE | buy flow当たり上方impact | Condition Dictionary:L425 |
| CD-G09-013 | `sell_impact_per_notional_100ms` | DEPTH+AGGTRADE | sell flow当たり下方impact | Condition Dictionary:L426 |
| CD-G09-014 | `sell_impact_per_notional_1s` | DEPTH+AGGTRADE | sell flow当たり下方impact | Condition Dictionary:L427 |
| CD-G09-015 | `sell_impact_per_notional_5s` | DEPTH+AGGTRADE | sell flow当たり下方impact | Condition Dictionary:L428 |
| CD-G09-016 | `sell_impact_per_notional_30s` | DEPTH+AGGTRADE | sell flow当たり下方impact | Condition Dictionary:L429 |
| CD-G09-017 | `buy_efficiency_100ms` | DEPTH+AGGTRADE | buy aggression進行効率 | Condition Dictionary:L430 |
| CD-G09-018 | `buy_efficiency_1s` | DEPTH+AGGTRADE | buy aggression進行効率 | Condition Dictionary:L431 |
| CD-G09-019 | `buy_efficiency_5s` | DEPTH+AGGTRADE | buy aggression進行効率 | Condition Dictionary:L432 |
| CD-G09-020 | `buy_efficiency_30s` | DEPTH+AGGTRADE | buy aggression進行効率 | Condition Dictionary:L433 |
| CD-G09-021 | `sell_efficiency_100ms` | DEPTH+AGGTRADE | sell aggression進行効率 | Condition Dictionary:L434 |
| CD-G09-022 | `sell_efficiency_1s` | DEPTH+AGGTRADE | sell aggression進行効率 | Condition Dictionary:L435 |
| CD-G09-023 | `sell_efficiency_5s` | DEPTH+AGGTRADE | sell aggression進行効率 | Condition Dictionary:L436 |
| CD-G09-024 | `sell_efficiency_30s` | DEPTH+AGGTRADE | sell aggression進行効率 | Condition Dictionary:L437 |
| CD-G09-025 | `buy_no_progress_ratio_100ms` | DEPTH+AGGTRADE | buy aggression無進行比率 | Condition Dictionary:L438 |
| CD-G09-026 | `buy_no_progress_ratio_1s` | DEPTH+AGGTRADE | buy aggression無進行比率 | Condition Dictionary:L439 |
| CD-G09-027 | `buy_no_progress_ratio_5s` | DEPTH+AGGTRADE | buy aggression無進行比率 | Condition Dictionary:L440 |
| CD-G09-028 | `buy_no_progress_ratio_30s` | DEPTH+AGGTRADE | buy aggression無進行比率 | Condition Dictionary:L441 |
| CD-G09-029 | `sell_no_progress_ratio_100ms` | DEPTH+AGGTRADE | sell aggression無進行比率 | Condition Dictionary:L442 |
| CD-G09-030 | `sell_no_progress_ratio_1s` | DEPTH+AGGTRADE | sell aggression無進行比率 | Condition Dictionary:L443 |
| CD-G09-031 | `sell_no_progress_ratio_5s` | DEPTH+AGGTRADE | sell aggression無進行比率 | Condition Dictionary:L444 |
| CD-G09-032 | `sell_no_progress_ratio_30s` | DEPTH+AGGTRADE | sell aggression無進行比率 | Condition Dictionary:L445 |
| CD-G09-033 | `reversion_from_window_high_100ms` | DEPTH+AGGTRADE | window highから反転幅 | Condition Dictionary:L446 |
| CD-G09-034 | `reversion_from_window_high_1s` | DEPTH+AGGTRADE | window highから反転幅 | Condition Dictionary:L447 |
| CD-G09-035 | `reversion_from_window_high_5s` | DEPTH+AGGTRADE | window highから反転幅 | Condition Dictionary:L448 |
| CD-G09-036 | `reversion_from_window_high_30s` | DEPTH+AGGTRADE | window highから反転幅 | Condition Dictionary:L449 |
| CD-G09-037 | `reversion_from_window_low_100ms` | DEPTH+AGGTRADE | window lowから反転幅 | Condition Dictionary:L450 |
| CD-G09-038 | `reversion_from_window_low_1s` | DEPTH+AGGTRADE | window lowから反転幅 | Condition Dictionary:L451 |
| CD-G09-039 | `reversion_from_window_low_5s` | DEPTH+AGGTRADE | window lowから反転幅 | Condition Dictionary:L452 |
| CD-G09-040 | `reversion_from_window_low_30s` | DEPTH+AGGTRADE | window lowから反転幅 | Condition Dictionary:L453 |

#### G10 Delta CVD and Footprint

| ID | condition_key | source | 定義 | 根拠 |
|---|---|---|---|---|
| CD-G10-001 | `trade_delta_1s` | AGGTRADE | buy minus sell volume | Condition Dictionary:L459 |
| CD-G10-002 | `trade_delta_5s` | AGGTRADE | buy minus sell volume | Condition Dictionary:L460 |
| CD-G10-003 | `trade_delta_30s` | AGGTRADE | buy minus sell volume | Condition Dictionary:L461 |
| CD-G10-004 | `trade_delta_5m` | AGGTRADE | buy minus sell volume | Condition Dictionary:L462 |
| CD-G10-005 | `cvd_change_1s` | AGGTRADE | CVD変化 | Condition Dictionary:L463 |
| CD-G10-006 | `cvd_change_5s` | AGGTRADE | CVD変化 | Condition Dictionary:L464 |
| CD-G10-007 | `cvd_change_30s` | AGGTRADE | CVD変化 | Condition Dictionary:L465 |
| CD-G10-008 | `cvd_change_5m` | AGGTRADE | CVD変化 | Condition Dictionary:L466 |
| CD-G10-009 | `cvd_slope_1s` | AGGTRADE | CVD傾き | Condition Dictionary:L467 |
| CD-G10-010 | `cvd_slope_5s` | AGGTRADE | CVD傾き | Condition Dictionary:L468 |
| CD-G10-011 | `cvd_slope_30s` | AGGTRADE | CVD傾き | Condition Dictionary:L469 |
| CD-G10-012 | `cvd_slope_5m` | AGGTRADE | CVD傾き | Condition Dictionary:L470 |
| CD-G10-013 | `delta_acceleration_1s` | AGGTRADE | delta変化率 | Condition Dictionary:L471 |
| CD-G10-014 | `delta_acceleration_5s` | AGGTRADE | delta変化率 | Condition Dictionary:L472 |
| CD-G10-015 | `delta_acceleration_30s` | AGGTRADE | delta変化率 | Condition Dictionary:L473 |
| CD-G10-016 | `delta_acceleration_5m` | AGGTRADE | delta変化率 | Condition Dictionary:L474 |
| CD-G10-017 | `buy_sell_ratio_1s` | AGGTRADE | buy対sell volume比 | Condition Dictionary:L475 |
| CD-G10-018 | `buy_sell_ratio_5s` | AGGTRADE | buy対sell volume比 | Condition Dictionary:L476 |
| CD-G10-019 | `buy_sell_ratio_30s` | AGGTRADE | buy対sell volume比 | Condition Dictionary:L477 |
| CD-G10-020 | `buy_sell_ratio_5m` | AGGTRADE | buy対sell volume比 | Condition Dictionary:L478 |
| CD-G10-021 | `positive_imbalance_count_1s` | AGGTRADE | 正footprint imbalance数 | Condition Dictionary:L479 |
| CD-G10-022 | `positive_imbalance_count_5s` | AGGTRADE | 正footprint imbalance数 | Condition Dictionary:L480 |
| CD-G10-023 | `positive_imbalance_count_30s` | AGGTRADE | 正footprint imbalance数 | Condition Dictionary:L481 |
| CD-G10-024 | `positive_imbalance_count_5m` | AGGTRADE | 正footprint imbalance数 | Condition Dictionary:L482 |
| CD-G10-025 | `negative_imbalance_count_1s` | AGGTRADE | 負footprint imbalance数 | Condition Dictionary:L483 |
| CD-G10-026 | `negative_imbalance_count_5s` | AGGTRADE | 負footprint imbalance数 | Condition Dictionary:L484 |
| CD-G10-027 | `negative_imbalance_count_30s` | AGGTRADE | 負footprint imbalance数 | Condition Dictionary:L485 |
| CD-G10-028 | `negative_imbalance_count_5m` | AGGTRADE | 負footprint imbalance数 | Condition Dictionary:L486 |
| CD-G10-029 | `stacked_buy_imbalance_depth_1s` | AGGTRADE | 連続buy imbalance段数 | Condition Dictionary:L487 |
| CD-G10-030 | `stacked_buy_imbalance_depth_5s` | AGGTRADE | 連続buy imbalance段数 | Condition Dictionary:L488 |
| CD-G10-031 | `stacked_buy_imbalance_depth_30s` | AGGTRADE | 連続buy imbalance段数 | Condition Dictionary:L489 |
| CD-G10-032 | `stacked_buy_imbalance_depth_5m` | AGGTRADE | 連続buy imbalance段数 | Condition Dictionary:L490 |
| CD-G10-033 | `stacked_sell_imbalance_depth_1s` | AGGTRADE | 連続sell imbalance段数 | Condition Dictionary:L491 |
| CD-G10-034 | `stacked_sell_imbalance_depth_5s` | AGGTRADE | 連続sell imbalance段数 | Condition Dictionary:L492 |
| CD-G10-035 | `stacked_sell_imbalance_depth_30s` | AGGTRADE | 連続sell imbalance段数 | Condition Dictionary:L493 |
| CD-G10-036 | `stacked_sell_imbalance_depth_5m` | AGGTRADE | 連続sell imbalance段数 | Condition Dictionary:L494 |

#### G11 Volume Profile and Auction

| ID | condition_key | source | 定義 | 根拠 |
|---|---|---|---|---|
| CD-G11-001 | `point_of_control_distance_session` | AGGTRADE+PROFILE | POC距離 | Condition Dictionary:L500 |
| CD-G11-002 | `point_of_control_distance_rolling_1h` | AGGTRADE+PROFILE | POC距離 | Condition Dictionary:L501 |
| CD-G11-003 | `value_area_high_distance_session` | AGGTRADE+PROFILE | VAH距離 | Condition Dictionary:L502 |
| CD-G11-004 | `value_area_high_distance_rolling_1h` | AGGTRADE+PROFILE | VAH距離 | Condition Dictionary:L503 |
| CD-G11-005 | `value_area_low_distance_session` | AGGTRADE+PROFILE | VAL距離 | Condition Dictionary:L504 |
| CD-G11-006 | `value_area_low_distance_rolling_1h` | AGGTRADE+PROFILE | VAL距離 | Condition Dictionary:L505 |
| CD-G11-007 | `high_volume_node_distance_session` | AGGTRADE+PROFILE | 最寄りHVN距離 | Condition Dictionary:L506 |
| CD-G11-008 | `high_volume_node_distance_rolling_1h` | AGGTRADE+PROFILE | 最寄りHVN距離 | Condition Dictionary:L507 |
| CD-G11-009 | `low_volume_node_distance_session` | AGGTRADE+PROFILE | 最寄りLVN距離 | Condition Dictionary:L508 |
| CD-G11-010 | `low_volume_node_distance_rolling_1h` | AGGTRADE+PROFILE | 最寄りLVN距離 | Condition Dictionary:L509 |
| CD-G11-011 | `volume_at_current_price_percentile_session` | AGGTRADE+PROFILE | 現在価格volume percentile | Condition Dictionary:L510 |
| CD-G11-012 | `volume_at_current_price_percentile_rolling_1h` | AGGTRADE+PROFILE | 現在価格volume percentile | Condition Dictionary:L511 |
| CD-G11-013 | `profile_balance_score_session` | AGGTRADE+PROFILE | profile balance | Condition Dictionary:L512 |
| CD-G11-014 | `profile_balance_score_rolling_1h` | AGGTRADE+PROFILE | profile balance | Condition Dictionary:L513 |
| CD-G11-015 | `profile_skew_session` | AGGTRADE+PROFILE | profile skew | Condition Dictionary:L514 |
| CD-G11-016 | `profile_skew_rolling_1h` | AGGTRADE+PROFILE | profile skew | Condition Dictionary:L515 |
| CD-G11-017 | `poc_migration_session` | AGGTRADE+PROFILE | POC移動 | Condition Dictionary:L516 |
| CD-G11-018 | `poc_migration_rolling_1h` | AGGTRADE+PROFILE | POC移動 | Condition Dictionary:L517 |
| CD-G11-019 | `value_area_migration_session` | AGGTRADE+PROFILE | value area移動 | Condition Dictionary:L518 |
| CD-G11-020 | `value_area_migration_rolling_1h` | AGGTRADE+PROFILE | value area移動 | Condition Dictionary:L519 |
| CD-G11-021 | `excess_high_score_session` | AGGTRADE+PROFILE | high excess度 | Condition Dictionary:L520 |
| CD-G11-022 | `excess_high_score_rolling_1h` | AGGTRADE+PROFILE | high excess度 | Condition Dictionary:L521 |
| CD-G11-023 | `excess_low_score_session` | AGGTRADE+PROFILE | low excess度 | Condition Dictionary:L522 |
| CD-G11-024 | `excess_low_score_rolling_1h` | AGGTRADE+PROFILE | low excess度 | Condition Dictionary:L523 |
| CD-G11-025 | `poor_high_score_session` | AGGTRADE+PROFILE | poor high度 | Condition Dictionary:L524 |
| CD-G11-026 | `poor_high_score_rolling_1h` | AGGTRADE+PROFILE | poor high度 | Condition Dictionary:L525 |
| CD-G11-027 | `poor_low_score_session` | AGGTRADE+PROFILE | poor low度 | Condition Dictionary:L526 |
| CD-G11-028 | `poor_low_score_rolling_1h` | AGGTRADE+PROFILE | poor low度 | Condition Dictionary:L527 |
| CD-G11-029 | `acceptance_above_value_session` | AGGTRADE+PROFILE | value上acceptance | Condition Dictionary:L528 |
| CD-G11-030 | `acceptance_above_value_rolling_1h` | AGGTRADE+PROFILE | value上acceptance | Condition Dictionary:L529 |
| CD-G11-031 | `acceptance_below_value_session` | AGGTRADE+PROFILE | value下acceptance | Condition Dictionary:L530 |
| CD-G11-032 | `acceptance_below_value_rolling_1h` | AGGTRADE+PROFILE | value下acceptance | Condition Dictionary:L531 |

#### G12 Derivatives Positioning

| ID | condition_key | source | 定義 | 根拠 |
|---|---|---|---|---|
| CD-G12-001 | `open_interest_change_5m` | OI | OI absolute change | Condition Dictionary:L537 |
| CD-G12-002 | `open_interest_pct_change_5m` | OI | OI percent change | Condition Dictionary:L538 |
| CD-G12-003 | `price_oi_joint_state_5m` | OI+AGGTRADE | price方向とOI方向のjoint state | Condition Dictionary:L539 |
| CD-G12-004 | `open_interest_change_15m` | OI | OI absolute change | Condition Dictionary:L540 |
| CD-G12-005 | `open_interest_pct_change_15m` | OI | OI percent change | Condition Dictionary:L541 |
| CD-G12-006 | `price_oi_joint_state_15m` | OI+AGGTRADE | price方向とOI方向のjoint state | Condition Dictionary:L542 |
| CD-G12-007 | `open_interest_change_1h` | OI | OI absolute change | Condition Dictionary:L543 |
| CD-G12-008 | `open_interest_pct_change_1h` | OI | OI percent change | Condition Dictionary:L544 |
| CD-G12-009 | `price_oi_joint_state_1h` | OI+AGGTRADE | price方向とOI方向のjoint state | Condition Dictionary:L545 |
| CD-G12-010 | `open_interest_change_4h` | OI | OI absolute change | Condition Dictionary:L546 |
| CD-G12-011 | `open_interest_pct_change_4h` | OI | OI percent change | Condition Dictionary:L547 |
| CD-G12-012 | `price_oi_joint_state_4h` | OI+AGGTRADE | price方向とOI方向のjoint state | Condition Dictionary:L548 |
| CD-G12-013 | `funding_rate_current` | MARK_FUNDING | current funding rate | Condition Dictionary:L549 |
| CD-G12-014 | `funding_rate_zscore` | MARK_FUNDING | funding z-score | Condition Dictionary:L550 |
| CD-G12-015 | `minutes_to_funding` | MARK_FUNDING+CLOCK | 次回fundingまでの分 | Condition Dictionary:L551 |
| CD-G12-016 | `funding_rate_change` | MARK_FUNDING | 前回値からのfunding変化 | Condition Dictionary:L552 |
| CD-G12-017 | `futures_basis_current` | MARK_FUNDING | future minus index | Condition Dictionary:L553 |
| CD-G12-018 | `futures_basis_rate` | MARK_FUNDING | basis rate | Condition Dictionary:L554 |
| CD-G12-019 | `futures_basis_zscore` | MARK_FUNDING | basis z-score | Condition Dictionary:L555 |
| CD-G12-020 | `annualized_basis_rate` | MARK_FUNDING | annualized basis | Condition Dictionary:L556 |
| CD-G12-021 | `mark_index_basis` | MARK_FUNDING | mark minus index | Condition Dictionary:L557 |
| CD-G12-022 | `mark_index_basis_zscore` | MARK_FUNDING | mark-index z-score | Condition Dictionary:L558 |
| CD-G12-023 | `observed_liquidation_buy_notional_1s` | FORCE_ORDER | 観測buy liquidation snapshot notional | Condition Dictionary:L559 |
| CD-G12-024 | `observed_liquidation_buy_notional_5s` | FORCE_ORDER | 観測buy liquidation snapshot notional | Condition Dictionary:L560 |
| CD-G12-025 | `observed_liquidation_buy_notional_30s` | FORCE_ORDER | 観測buy liquidation snapshot notional | Condition Dictionary:L561 |
| CD-G12-026 | `observed_liquidation_sell_notional_1s` | FORCE_ORDER | 観測sell liquidation snapshot notional | Condition Dictionary:L562 |
| CD-G12-027 | `observed_liquidation_sell_notional_5s` | FORCE_ORDER | 観測sell liquidation snapshot notional | Condition Dictionary:L563 |
| CD-G12-028 | `observed_liquidation_sell_notional_30s` | FORCE_ORDER | 観測sell liquidation snapshot notional | Condition Dictionary:L564 |
| CD-G12-029 | `observed_liquidation_imbalance_1s` | FORCE_ORDER | 観測snapshot liquidation imbalance | Condition Dictionary:L565 |
| CD-G12-030 | `observed_liquidation_imbalance_5s` | FORCE_ORDER | 観測snapshot liquidation imbalance | Condition Dictionary:L566 |
| CD-G12-031 | `observed_liquidation_imbalance_30s` | FORCE_ORDER | 観測snapshot liquidation imbalance | Condition Dictionary:L567 |
| CD-G12-032 | `adl_risk_state` | BINANCE_ADL | symbol ADL risk | Condition Dictionary:L568 |

#### G13 Cross Venue Relative State

| ID | condition_key | source | 定義 | 根拠 |
|---|---|---|---|---|
| CD-G13-001 | `binance_hfm_bid_basis_100ms` | DEPTH+HFM_QUOTE | Binance bid対HFM bid basis | Condition Dictionary:L574 |
| CD-G13-002 | `binance_hfm_bid_basis_1s` | DEPTH+HFM_QUOTE | Binance bid対HFM bid basis | Condition Dictionary:L575 |
| CD-G13-003 | `binance_hfm_bid_basis_5s` | DEPTH+HFM_QUOTE | Binance bid対HFM bid basis | Condition Dictionary:L576 |
| CD-G13-004 | `binance_hfm_bid_basis_30s` | DEPTH+HFM_QUOTE | Binance bid対HFM bid basis | Condition Dictionary:L577 |
| CD-G13-005 | `binance_hfm_ask_basis_100ms` | DEPTH+HFM_QUOTE | Binance ask対HFM ask basis | Condition Dictionary:L578 |
| CD-G13-006 | `binance_hfm_ask_basis_1s` | DEPTH+HFM_QUOTE | Binance ask対HFM ask basis | Condition Dictionary:L579 |
| CD-G13-007 | `binance_hfm_ask_basis_5s` | DEPTH+HFM_QUOTE | Binance ask対HFM ask basis | Condition Dictionary:L580 |
| CD-G13-008 | `binance_hfm_ask_basis_30s` | DEPTH+HFM_QUOTE | Binance ask対HFM ask basis | Condition Dictionary:L581 |
| CD-G13-009 | `binance_hfm_mid_basis_100ms` | DEPTH+HFM_QUOTE | Binance mid対HFM mid basis | Condition Dictionary:L582 |
| CD-G13-010 | `binance_hfm_mid_basis_1s` | DEPTH+HFM_QUOTE | Binance mid対HFM mid basis | Condition Dictionary:L583 |
| CD-G13-011 | `binance_hfm_mid_basis_5s` | DEPTH+HFM_QUOTE | Binance mid対HFM mid basis | Condition Dictionary:L584 |
| CD-G13-012 | `binance_hfm_mid_basis_30s` | DEPTH+HFM_QUOTE | Binance mid対HFM mid basis | Condition Dictionary:L585 |
| CD-G13-013 | `basis_change_100ms` | DEPTH+HFM_QUOTE | venue間basis変化 | Condition Dictionary:L586 |
| CD-G13-014 | `basis_change_1s` | DEPTH+HFM_QUOTE | venue間basis変化 | Condition Dictionary:L587 |
| CD-G13-015 | `basis_change_5s` | DEPTH+HFM_QUOTE | venue間basis変化 | Condition Dictionary:L588 |
| CD-G13-016 | `basis_change_30s` | DEPTH+HFM_QUOTE | venue間basis変化 | Condition Dictionary:L589 |
| CD-G13-017 | `return_spread_100ms` | DEPTH+HFM_QUOTE | venue間return差 | Condition Dictionary:L590 |
| CD-G13-018 | `return_spread_1s` | DEPTH+HFM_QUOTE | venue間return差 | Condition Dictionary:L591 |
| CD-G13-019 | `return_spread_5s` | DEPTH+HFM_QUOTE | venue間return差 | Condition Dictionary:L592 |
| CD-G13-020 | `return_spread_30s` | DEPTH+HFM_QUOTE | venue間return差 | Condition Dictionary:L593 |
| CD-G13-021 | `direction_agreement_100ms` | DEPTH+HFM_QUOTE | venue間方向一致度 | Condition Dictionary:L594 |
| CD-G13-022 | `direction_agreement_1s` | DEPTH+HFM_QUOTE | venue間方向一致度 | Condition Dictionary:L595 |
| CD-G13-023 | `direction_agreement_5s` | DEPTH+HFM_QUOTE | venue間方向一致度 | Condition Dictionary:L596 |
| CD-G13-024 | `direction_agreement_30s` | DEPTH+HFM_QUOTE | venue間方向一致度 | Condition Dictionary:L597 |
| CD-G13-025 | `lead_lag_score_100ms` | DEPTH+HFM_QUOTE | venue間lead-lag | Condition Dictionary:L598 |
| CD-G13-026 | `lead_lag_score_1s` | DEPTH+HFM_QUOTE | venue間lead-lag | Condition Dictionary:L599 |
| CD-G13-027 | `lead_lag_score_5s` | DEPTH+HFM_QUOTE | venue間lead-lag | Condition Dictionary:L600 |
| CD-G13-028 | `lead_lag_score_30s` | DEPTH+HFM_QUOTE | venue間lead-lag | Condition Dictionary:L601 |

#### G14 Execution and Risk Gate

| ID | condition_key | source | 定義 | 根拠 |
|---|---|---|---|---|
| CD-G14-001 | `hfm_symbol_tradeable` | HFM_QUOTE+HFM_EXEC+RISK_STATE | HFM symbolがtradeable | Condition Dictionary:L607 |
| CD-G14-002 | `execution_hfm_quote_fresh` | HFM_QUOTE+HFM_EXEC+RISK_STATE | 発注用HFM quoteがfresh | Condition Dictionary:L608 |
| CD-G14-003 | `hfm_spread_within_limit` | HFM_QUOTE+HFM_EXEC+RISK_STATE | HFM spreadが上限内 | Condition Dictionary:L609 |
| CD-G14-004 | `hfm_basis_within_limit` | HFM_QUOTE+HFM_EXEC+RISK_STATE | Binance-HFM basisが上限内 | Condition Dictionary:L610 |
| CD-G14-005 | `execution_latency_within_limit` | HFM_QUOTE+HFM_EXEC+RISK_STATE | 推定latencyが上限内 | Condition Dictionary:L611 |
| CD-G14-006 | `expected_slippage_within_limit` | HFM_QUOTE+HFM_EXEC+RISK_STATE | 推定slippageが上限内 | Condition Dictionary:L612 |
| CD-G14-007 | `expected_cost_within_limit` | HFM_QUOTE+HFM_EXEC+RISK_STATE | feeとslippage合計が上限内 | Condition Dictionary:L613 |
| CD-G14-008 | `risk_reward_above_floor` | HFM_QUOTE+HFM_EXEC+RISK_STATE | reward対riskが下限以上 | Condition Dictionary:L614 |
| CD-G14-009 | `invalidation_distance_valid` | HFM_QUOTE+HFM_EXEC+RISK_STATE | invalidation距離が正で有限 | Condition Dictionary:L615 |
| CD-G14-010 | `risk_budget_available` | HFM_QUOTE+HFM_EXEC+RISK_STATE | 注文用risk budgetあり | Condition Dictionary:L616 |
| CD-G14-011 | `position_cap_available` | HFM_QUOTE+HFM_EXEC+RISK_STATE | exposure capに余地あり | Condition Dictionary:L617 |
| CD-G14-012 | `margin_available` | HFM_QUOTE+HFM_EXEC+RISK_STATE | 必要margin利用可能 | Condition Dictionary:L618 |
| CD-G14-013 | `broker_volume_step_valid` | HFM_QUOTE+HFM_EXEC+RISK_STATE | volume step適合 | Condition Dictionary:L619 |
| CD-G14-014 | `broker_min_volume_met` | HFM_QUOTE+HFM_EXEC+RISK_STATE | minimum volume以上 | Condition Dictionary:L620 |
| CD-G14-015 | `broker_max_volume_not_exceeded` | HFM_QUOTE+HFM_EXEC+RISK_STATE | maximum volume以下 | Condition Dictionary:L621 |
| CD-G14-016 | `broker_stop_distance_valid` | HFM_QUOTE+HFM_EXEC+RISK_STATE | stop距離がcontract適合 | Condition Dictionary:L622 |
| CD-G14-017 | `duplicate_intent_absent` | HFM_QUOTE+HFM_EXEC+RISK_STATE | 同一intent重複なし | Condition Dictionary:L623 |
| CD-G14-018 | `outstanding_order_conflict_absent` | HFM_QUOTE+HFM_EXEC+RISK_STATE | 競合open orderなし | Condition Dictionary:L624 |
| CD-G14-019 | `idempotency_key_available` | HFM_QUOTE+HFM_EXEC+RISK_STATE | idempotency key生成済み | Condition Dictionary:L625 |
| CD-G14-020 | `execution_mode_allowed` | HFM_QUOTE+HFM_EXEC+RISK_STATE | execution mode許可 | Condition Dictionary:L626 |
| CD-G14-021 | `daily_loss_limit_clear` | HFM_QUOTE+HFM_EXEC+RISK_STATE | daily loss limit未到達 | Condition Dictionary:L627 |
| CD-G14-022 | `drawdown_limit_clear` | HFM_QUOTE+HFM_EXEC+RISK_STATE | drawdown limit未到達 | Condition Dictionary:L628 |
| CD-G14-023 | `cooldown_elapsed` | HFM_QUOTE+HFM_EXEC+RISK_STATE | 発注cooldown経過 | Condition Dictionary:L629 |
| CD-G14-024 | `max_order_rate_clear` | HFM_QUOTE+HFM_EXEC+RISK_STATE | order rate limit内 | Condition Dictionary:L630 |
| CD-G14-025 | `recent_reject_rate_acceptable` | HFM_QUOTE+HFM_EXEC+RISK_STATE | 直近reject率が上限内 | Condition Dictionary:L631 |
| CD-G14-026 | `recent_fill_rate_acceptable` | HFM_QUOTE+HFM_EXEC+RISK_STATE | 直近fill率が下限以上 | Condition Dictionary:L632 |
| CD-G14-027 | `emergency_stop_clear` | HFM_QUOTE+HFM_EXEC+RISK_STATE | emergency stop未発動 | Condition Dictionary:L633 |
| CD-G14-028 | `all_execution_hard_gates_pass` | HFM_QUOTE+HFM_EXEC+RISK_STATE | 全execution hard gate通過 | Condition Dictionary:L634 |

#### G15 Open Position Lifecycle

| ID | condition_key | source | 定義 | 根拠 |
|---|---|---|---|---|
| CD-G15-001 | `position_is_open` | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | 対象positionがopen | Condition Dictionary:L640 |
| CD-G15-002 | `side_matches_strategy` | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | position sideとstrategy sideの関係 | Condition Dictionary:L641 |
| CD-G15-003 | `entry_fill_confirmed` | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | entry fillがbroker確認済み | Condition Dictionary:L642 |
| CD-G15-004 | `holding_time_within_limit` | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | holding timeが上限内 | Condition Dictionary:L643 |
| CD-G15-005 | `expected_reaction_deadline_clear` | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | 期待反応期限内 | Condition Dictionary:L644 |
| CD-G15-006 | `unrealized_pnl_state` | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | unrealized PnL状態 | Condition Dictionary:L645 |
| CD-G15-007 | `mae_within_limit` | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | MAEが上限内 | Condition Dictionary:L646 |
| CD-G15-008 | `mfe_state` | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | MFE状態 | Condition Dictionary:L647 |
| CD-G15-009 | `price_progress_supports_thesis` | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | entry後price progressが仮説支持 | Condition Dictionary:L648 |
| CD-G15-010 | `order_flow_supports_thesis` | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | entry後flowが仮説支持 | Condition Dictionary:L649 |
| CD-G15-011 | `passive_defense_holds` | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | 期待passive defense維持 | Condition Dictionary:L650 |
| CD-G15-012 | `breakout_acceptance_holds` | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | 期待breakout acceptance維持 | Condition Dictionary:L651 |
| CD-G15-013 | `contradiction_below_limit` | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | 反証が上限未満 | Condition Dictionary:L652 |
| CD-G15-014 | `invalidation_absent` | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | 論理invalidation未成立 | Condition Dictionary:L653 |
| CD-G15-015 | `add_size_eligible` | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | 追加発注候補 | Condition Dictionary:L654 |
| CD-G15-016 | `reduce_size_required` | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | 縮小必要 | Condition Dictionary:L655 |
| CD-G15-017 | `exit_required` | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | 決済必要 | Condition Dictionary:L656 |
| CD-G15-018 | `reverse_candidate` | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | 反転候補 | Condition Dictionary:L657 |
| CD-G15-019 | `trailing_invalidation_updated` | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | trailing invalidation更新済み | Condition Dictionary:L658 |
| CD-G15-020 | `remaining_risk_within_limit` | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | 残存riskが上限内 | Condition Dictionary:L659 |
| CD-G15-021 | `competing_strategy_dominant` | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | 競合strategyが優勢 | Condition Dictionary:L660 |
| CD-G15-022 | `satisfaction_tier_not_downgraded` | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | entry時充足水準から未悪化 | Condition Dictionary:L661 |
| CD-G15-023 | `post_entry_data_fresh` | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | 保有中必須dataがfresh | Condition Dictionary:L662 |
| CD-G15-024 | `flat_confirmation_received` | POSITION_LEDGER+MARKET_STATE+HFM_EXEC | 決済後flat確認済み | Condition Dictionary:L663 |

### 1.2 G16自然言語定義（全48件）

以下は正本G16全行の機械転記である。

| ID | condition_key | source | 自然言語定義 | 根拠 |
|---|---|---|---|---|
| CD-G16-001 | `bid_absorption_like_active` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | bid側でsell aggressionに対し下方進行が止まるabsorption-like状態 | Condition Dictionary:L671 |
| CD-G16-002 | `ask_absorption_like_active` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | ask側でbuy aggressionに対し上方進行が止まるabsorption-like状態 | Condition Dictionary:L672 |
| CD-G16-003 | `bid_absorption_strengthening` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | bid absorption-like反応が反復ごとに強化 | Condition Dictionary:L673 |
| CD-G16-004 | `ask_absorption_strengthening` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | ask absorption-like反応が反復ごとに強化 | Condition Dictionary:L674 |
| CD-G16-005 | `bid_absorption_weakening` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | bid absorption-like反応が反復ごとに弱化 | Condition Dictionary:L675 |
| CD-G16-006 | `ask_absorption_weakening` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | ask absorption-like反応が反復ごとに弱化 | Condition Dictionary:L676 |
| CD-G16-007 | `buyer_fade_active` | AGGTRADE+PRICE_RESPONSE+DELTA | 高値側でaggressive buyer参加が減衰 | Condition Dictionary:L677 |
| CD-G16-008 | `seller_fade_active` | AGGTRADE+PRICE_RESPONSE+DELTA | 安値側でaggressive seller参加が減衰 | Condition Dictionary:L678 |
| CD-G16-009 | `buyers_jump_in` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | buy aggressionが基準を超えて新規増加 | Condition Dictionary:L679 |
| CD-G16-010 | `sellers_jump_in` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | sell aggressionが基準を超えて新規増加 | Condition Dictionary:L680 |
| CD-G16-011 | `trapped_buyers_like` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 大きいbuy flow後も上方進行せず反転するtrapped-like状態 | Condition Dictionary:L681 |
| CD-G16-012 | `trapped_sellers_like` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 大きいsell flow後も下方進行せず反転するtrapped-like状態 | Condition Dictionary:L682 |
| CD-G16-013 | `repeated_high_test` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 同一high近傍を指定回数再試行 | Condition Dictionary:L683 |
| CD-G16-014 | `repeated_low_test` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 同一low近傍を指定回数再試行 | Condition Dictionary:L684 |
| CD-G16-015 | `high_rejection_active` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | high進入後に指定時間内で下へ戻るrejection | Condition Dictionary:L685 |
| CD-G16-016 | `low_rejection_active` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | low進入後に指定時間内で上へ戻るrejection | Condition Dictionary:L686 |
| CD-G16-017 | `acceptance_above_reference` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | reference上で時間・volume・retest条件を満たすacceptance | Condition Dictionary:L687 |
| CD-G16-018 | `acceptance_below_reference` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | reference下で時間・volume・retest条件を満たすacceptance | Condition Dictionary:L688 |
| CD-G16-019 | `upside_breakout_attempt` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 上側referenceをinitiative buyで試行 | Condition Dictionary:L689 |
| CD-G16-020 | `downside_breakout_attempt` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 下側referenceをinitiative sellで試行 | Condition Dictionary:L690 |
| CD-G16-021 | `upside_breakout_follow_through` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 上抜け後もbuy participationとprice progress継続 | Condition Dictionary:L691 |
| CD-G16-022 | `downside_breakout_follow_through` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 下抜け後もsell participationとprice progress継続 | Condition Dictionary:L692 |
| CD-G16-023 | `upside_breakout_failure` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 上抜け後にacceptanceせずreference下へ復帰 | Condition Dictionary:L693 |
| CD-G16-024 | `downside_breakout_failure` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 下抜け後にacceptanceせずreference上へ復帰 | Condition Dictionary:L694 |
| CD-G16-025 | `reclaim_above_reference` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 下側からreference上へ回復し保持 | Condition Dictionary:L695 |
| CD-G16-026 | `reclaim_below_reference` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 上側からreference下へ回復し保持 | Condition Dictionary:L696 |
| CD-G16-027 | `bullish_pullback_low_participation` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 上昇中pullbackのsell participationが低い | Condition Dictionary:L697 |
| CD-G16-028 | `bearish_pullback_low_participation` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 下降中pullbackのbuy participationが低い | Condition Dictionary:L698 |
| CD-G16-029 | `bullish_pullback_stall` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 上昇trend内pullbackの下方進行が停滞 | Condition Dictionary:L699 |
| CD-G16-030 | `bearish_pullback_stall` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 下降trend内pullbackの上方進行が停滞 | Condition Dictionary:L700 |
| CD-G16-031 | `buy_momentum_accelerating` | AGGTRADE+PRICE_RESPONSE+DELTA | buy flow速度と上方progressが同時加速 | Condition Dictionary:L701 |
| CD-G16-032 | `sell_momentum_accelerating` | AGGTRADE+PRICE_RESPONSE+DELTA | sell flow速度と下方progressが同時加速 | Condition Dictionary:L702 |
| CD-G16-033 | `buy_momentum_fading` | AGGTRADE+PRICE_RESPONSE+DELTA | buy flowまたは上方progressが明確に減衰 | Condition Dictionary:L703 |
| CD-G16-034 | `sell_momentum_fading` | AGGTRADE+PRICE_RESPONSE+DELTA | sell flowまたは下方progressが明確に減衰 | Condition Dictionary:L704 |
| CD-G16-035 | `bid_passive_defense_holding` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | bid補充と価格保持が継続 | Condition Dictionary:L705 |
| CD-G16-036 | `ask_passive_defense_holding` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | ask補充と価格保持が継続 | Condition Dictionary:L706 |
| CD-G16-037 | `bid_passive_defense_failed` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | bid補充が止まり支持価格を下抜け | Condition Dictionary:L707 |
| CD-G16-038 | `ask_passive_defense_failed` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | ask補充が止まり抵抗価格を上抜け | Condition Dictionary:L708 |
| CD-G16-039 | `two_way_trade_emerged` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 一方向flowから双方向参加へcharacter変化 | Condition Dictionary:L709 |
| CD-G16-040 | `directional_flow_resumed_up` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | pause後にbuy主導と上方progressが再開 | Condition Dictionary:L710 |
| CD-G16-041 | `directional_flow_resumed_down` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | pause後にsell主導と下方progressが再開 | Condition Dictionary:L711 |
| CD-G16-042 | `upward_sweep_active` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 複数ask levelを短時間に連続消費 | Condition Dictionary:L712 |
| CD-G16-043 | `downward_sweep_active` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 複数bid levelを短時間に連続消費 | Condition Dictionary:L713 |
| CD-G16-044 | `upside_stop_run_like` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | reference上の急加速後に継続または即時失敗を伴うstop-run-like状態 | Condition Dictionary:L714 |
| CD-G16-045 | `downside_stop_run_like` | DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | reference下の急加速後に継続または即時失敗を伴うstop-run-like状態 | Condition Dictionary:L715 |
| CD-G16-046 | `observed_liquidation_led_upmove` | FORCE_ORDER+AGGTRADE+PRICE_RESPONSE | 観測buy-side liquidation snapshotと上方progressが同時化 | Condition Dictionary:L716 |
| CD-G16-047 | `observed_liquidation_led_downmove` | FORCE_ORDER+AGGTRADE+PRICE_RESPONSE | 観測sell-side liquidation snapshotと下方progressが同時化 | Condition Dictionary:L717 |
| CD-G16-048 | `flow_price_divergence_active` | AGGTRADE+PRICE_RESPONSE+DELTA | aggressive flow方向とprice response方向が乖離 | Condition Dictionary:L718 |

### 1.3 現Ingestion Adapterの出力

固定計算されるkey:

| key | 生成箇所 | 可用条件 |
|---|---|---|
| `cvd_change_5s` | `condition_adapter.py:53` | 5秒baseとlatest CVDあり |
| `cvd_slope_5s` | `condition_adapter.py:61` | 5秒window内に異時刻sample 2件以上 |
| `bid_wall_concentration_top10` | `condition_adapter.py:82` | bid levelあり、top10総quantity > 0 |
| `ask_wall_concentration_top10` | `condition_adapter.py:82` | ask levelあり、top10総quantity > 0 |
| `distance_to_nearest_bid_wall` | `condition_adapter.py:87` | bid levelと正のtick sizeあり |
| `distance_to_nearest_ask_wall` | `condition_adapter.py:87` | ask levelと正のtick sizeあり |
| `open_interest_change_5m` | `condition_adapter.py:101` | 5分baseとlatest OIあり |
| `open_interest_pct_change_5m` | `condition_adapter.py:103` | 上記に加えてbase OI != 0 |
| `price_oi_joint_state_5m` | `condition_adapter.py:109` | 5分base/latestのOIとpriceあり |

`pre_aggregated`はkey allowlistを持たず、渡された任意keyをそのまま出力する
(`condition_adapter.py:115-119`)。したがって、実コードから確定できる固定出力一覧は上記9件であり、
他のTier Aは「adapterが計算する」のではなく、将来producerが正しく事前集計して渡すことに依存する。


## 2. 代表1型E01/E02/E03/E98の反証転記

正本:
`ORDER_FLOW_VARIANT_STATE_CONDITION_BINDINGS_V0_1_20260727.csv:363-365,368`

| edge | predicate | contradiction_condition_ids | contradiction_condition_keys |
|---|---|---|---|
| E01 | OPR-019 `bearish divergence` | `CD-G16-021 CD-G16-022` | `upside_breakout_follow_through downside_breakout_follow_through` |
| E02 | OPR-020 `bid-side absorption` | `CD-G16-037 CD-G16-038` | `bid_passive_defense_failed ask_passive_defense_failed` |
| E03 | OPR-021 `buy wall崩壊` | `CD-G16-023 CD-G16-024 CD-G16-037 CD-G16-038` | `upside_breakout_failure downside_breakout_failure bid_passive_defense_failed ask_passive_defense_failed` |
| E98 | INV-005 | `CD-G12-001 CD-G12-002 CD-G16-037 CD-G16-038` | `open_interest_change_5m open_interest_pct_change_5m bid_passive_defense_failed ask_passive_defense_failed` |

確認:

- E01の指定反証は`downside_breakout_follow_through` = CD-G16-022。
- E02の指定反証`bid_passive_defense_failed` = CD-G16-037はE98に既存。
- E03の指定反証は`downside_breakout_failure` = CD-G16-024。

## 3. E98更新草案

この節は指示されたCSV更新の**構文草案**である。正本は変更していない。
ID列とkey列の対応を維持するため、`contradiction_condition_ids`へ
`CD-G16-022 CD-G16-024`、`contradiction_condition_keys`へ対応する2 keyを同じ順で末尾追加する。
他列は変更しない。

### Before（現行E98行）

```csv
"VAR-CVD-BEAR-ABSFAIL-BIDBREAK-OIUNWIND-SHORT-VISIBLE_BOOK_WALL-001::E98","VAR-CVD-BEAR-ABSFAIL-BIDBREAK-OIUNWIND-SHORT-VISIBLE_BOOK_WALL-001","CVD Divergence / Bearish / Absorption Failure / Buy-Wall Break / OI Unwind / SHORT / Visible Bid Wall","PAT-CVD-BEAR-ABSFAIL-BIDBREAK-OIUNWIND-001","PAT-CVD-BEAR-ABSFAIL-BIDBREAK-OIUNWIND-001::E98","STR-CVD-DIVERGENCE","INVALIDATE","ANY_ACTIVE_STATE","S98_INVALIDATED","INV-005","bid wall再構築、price回復、またはOI不明／stale","COMPOSITE_INVALIDATION OPEN_INTEREST_CHANGE WALL_STATE","EXPLICIT_BUY_OR_BID_COMPONENT","SHORT","ANY_MATCHED_ATOM SIDE_RESOLVED SIGN_RESOLVED","CD-G12-001 CD-G12-002 CD-G12-003 CD-G06-029 CD-G06-030 CD-G06-031 CD-G06-032 CD-G07-011 CD-G07-014 CD-G07-035 CD-G07-038 CD-G16-035 CD-G16-036 CD-G16-037 CD-G16-038","open_interest_change_5m open_interest_pct_change_5m price_oi_joint_state_5m bid_wall_concentration_top10 distance_to_nearest_bid_wall ask_wall_concentration_top10 distance_to_nearest_ask_wall bid_refresh_count_1s bid_pull_ratio_1s ask_refresh_count_1s ask_pull_ratio_1s bid_passive_defense_holding ask_passive_defense_holding bid_passive_defense_failed ask_passive_defense_failed","CD-G12-001 CD-G12-002 CD-G16-037 CD-G16-038","open_interest_change_5m open_interest_pct_change_5m bid_passive_defense_failed ask_passive_defense_failed","CD-G01-009 CD-G01-010 CD-G01-011 CD-G01-016 CD-G01-021 CD-G01-007 CD-G01-024 CD-G01-027 CD-G01-001 CD-G01-002 CD-G01-004 CD-G01-019 CD-G01-020","exchange_clock_aligned receive_clock_monotonic event_order_monotonic duplicate_event_absent cross_source_time_aligned open_interest_snapshot_fresh sampling_limit_disclosed window_complete depth_book_synced depth_sequence_contiguous depth_event_fresh persistence_confirmed market_state_atomic","VISIBLE_BOOK_WALL","CD-G06-029 CD-G06-030","AVAILABLE","ANY invalidation atom true terminates instance.","LIMITED","COMPOSITE_CONDITION_AVAILABLE DERIVED_EVALUATOR_REQUIRED ENGINE_NATIVE","OI_LAGGED","UNVALIDATED"
```

### After（草案E98行）

```csv
"VAR-CVD-BEAR-ABSFAIL-BIDBREAK-OIUNWIND-SHORT-VISIBLE_BOOK_WALL-001::E98","VAR-CVD-BEAR-ABSFAIL-BIDBREAK-OIUNWIND-SHORT-VISIBLE_BOOK_WALL-001","CVD Divergence / Bearish / Absorption Failure / Buy-Wall Break / OI Unwind / SHORT / Visible Bid Wall","PAT-CVD-BEAR-ABSFAIL-BIDBREAK-OIUNWIND-001","PAT-CVD-BEAR-ABSFAIL-BIDBREAK-OIUNWIND-001::E98","STR-CVD-DIVERGENCE","INVALIDATE","ANY_ACTIVE_STATE","S98_INVALIDATED","INV-005","bid wall再構築、price回復、またはOI不明／stale","COMPOSITE_INVALIDATION OPEN_INTEREST_CHANGE WALL_STATE","EXPLICIT_BUY_OR_BID_COMPONENT","SHORT","ANY_MATCHED_ATOM SIDE_RESOLVED SIGN_RESOLVED","CD-G12-001 CD-G12-002 CD-G12-003 CD-G06-029 CD-G06-030 CD-G06-031 CD-G06-032 CD-G07-011 CD-G07-014 CD-G07-035 CD-G07-038 CD-G16-035 CD-G16-036 CD-G16-037 CD-G16-038","open_interest_change_5m open_interest_pct_change_5m price_oi_joint_state_5m bid_wall_concentration_top10 distance_to_nearest_bid_wall ask_wall_concentration_top10 distance_to_nearest_ask_wall bid_refresh_count_1s bid_pull_ratio_1s ask_refresh_count_1s ask_pull_ratio_1s bid_passive_defense_holding ask_passive_defense_holding bid_passive_defense_failed ask_passive_defense_failed","CD-G12-001 CD-G12-002 CD-G16-037 CD-G16-038 CD-G16-022 CD-G16-024","open_interest_change_5m open_interest_pct_change_5m bid_passive_defense_failed ask_passive_defense_failed downside_breakout_follow_through downside_breakout_failure","CD-G01-009 CD-G01-010 CD-G01-011 CD-G01-016 CD-G01-021 CD-G01-007 CD-G01-024 CD-G01-027 CD-G01-001 CD-G01-002 CD-G01-004 CD-G01-019 CD-G01-020","exchange_clock_aligned receive_clock_monotonic event_order_monotonic duplicate_event_absent cross_source_time_aligned open_interest_snapshot_fresh sampling_limit_disclosed window_complete depth_book_synced depth_sequence_contiguous depth_event_fresh persistence_confirmed market_state_atomic","VISIBLE_BOOK_WALL","CD-G06-029 CD-G06-030","AVAILABLE","ANY invalidation atom true terminates instance.","LIMITED","COMPOSITE_CONDITION_AVAILABLE DERIVED_EVALUATOR_REQUIRED ENGINE_NATIVE","OI_LAGGED","UNVALIDATED"
```

注意:

- `bid_passive_defense_failed` / CD-G16-037は既存のため重複追加しない。
- `contradiction_condition_ids`は「同じ材料の逆comparatorを含み得るためIDだけで正負を決めない」
  (`ORDER_FLOW_STATE_CONDITION_BINDING_POLICY_V0_1_20260727.md:46`)。
- 現Evaluatorでは`contradiction_atoms`の成立はvetoである
  (`Delta_Engine_Pro4web/src/strategy_engine/real_predicate_eval.py:67-68`)。
  よって、このCSV列追加だけで2 keyがE98を成立させるとは断定できない。
  E98用CalibrationBookでcandidate atomとして扱うのか、contradiction atomとして扱うのか、
  comparator方向を正本反映前に明示する必要がある。

## 4. G16合成式草案（対象13件）

表内の`candidate:`はG01〜G15から自然言語に対応し得る材料を列挙したもので、
確定`depends_on`ではない。`*`はcondition keyそのものではなく、§1.1に転記した同prefixの
全window keyを表す省略記法である。`NO_FIXED_ADAPTER_PRODUCER`はCondition Dictionaryには
存在し、adapterの任意`pre_aggregated`経路では通過できるが、固定計算もproducer契約もない
key／stateを示す。

| key | family | depends_on | logic | side | output | window | reference | 根拠 |
|---|---|---|---|---|---|---|---|---|
| `flow_price_divergence_active` | Divergence | candidate: `trade_delta_*` or `cvd_change_*`/`cvd_slope_*`; `upward_progress_ticks_*`, `downward_progress_ticks_*` | `UNDEFINED: flow方向の採用系列、matching window、最小flow量、price responseを停滞／逆行のどちらまで含めるかが一意でない` | neutral | bool | `UNDEFINED: 1s/5s/30s/5m候補` | N/A | G16 `:718`; G09 `:414-453`; G10 `:459-494` |
| `bid_absorption_like_active` | Absorption | candidate: `sell_market_volume_*`/`sell_trade_rate_*`/`sell_side_share_*`; `sell_no_progress_ratio_*` or `sell_efficiency_*`; `downward_progress_ticks_*`; `bid_wall_concentration_top10`, `distance_to_nearest_bid_wall` | `UNDEFINED: sell aggression成立、下方停止、bid locationのAND自体は読めるが、系列選択・threshold・継続条件が一意でない。NO_FIXED_ADAPTER_PRODUCER: sell aggression固定出力` | bid | bool | `UNDEFINED: 100ms/1s/5s/30s` | `MISSING: absorption対象bid referenceのidentity/price` | G16 `:671`; G06 `:299-300`; G08 `:385-408`; G09 `:415-445` |
| `ask_absorption_like_active` | Absorption | candidate: `buy_market_volume_*`/`buy_trade_rate_*`/`buy_side_share_*`; `buy_no_progress_ratio_*` or `buy_efficiency_*`; `upward_progress_ticks_*`; `ask_wall_concentration_top10`, `distance_to_nearest_ask_wall` | `UNDEFINED: buy aggression成立、上方停止、ask locationのAND自体は読めるが、系列選択・threshold・継続条件が一意でない。NO_FIXED_ADAPTER_PRODUCER: buy aggression固定出力` | ask | bool | `UNDEFINED: 100ms/1s/5s/30s` | `MISSING: absorption対象ask referenceのidentity/price` | G16 `:672`; G06 `:301-302`; G08 `:361-384`; G09 `:415-441` |
| `upside_breakout_attempt` | Breakout attempt | candidate: `buy_market_volume_*`/`buy_trade_rate_*`/`buy_side_share_*`; `upward_progress_ticks_*`; G03の`relation_to_*`/`distance_to_*` | `UNDEFINED: initiative buy AND upper reference試行は読めるが、initiativeの尺度、試行とbreakの境界、対象referenceが一意でない。NO_FIXED_ADAPTER_PRODUCER: buy aggressionとG03 location固定出力` | neutral | bool | `UNDEFINED: 100ms/1s/5s/30s` | `MISSING: strategy-specific upper reference selector/identity` | G16 `:689`; G03 `:144-191`; G08 `:361-384`; G09 `:414-418` |
| `downside_breakout_attempt` | Breakout attempt | candidate: `sell_market_volume_*`/`sell_trade_rate_*`/`sell_side_share_*`; `downward_progress_ticks_*`; G03の`relation_to_*`/`distance_to_*` | `UNDEFINED: initiative sell AND lower reference試行は読めるが、initiativeの尺度、試行とbreakの境界、対象referenceが一意でない。NO_FIXED_ADAPTER_PRODUCER: sell aggressionとG03 location固定出力` | neutral | bool | `UNDEFINED: 100ms/1s/5s/30s` | `MISSING: strategy-specific lower reference selector/identity` | G16 `:690`; G03 `:144-191`; G08 `:385-408`; G09 `:419-422` |
| `upside_breakout_follow_through` | Follow-through | candidate: `buy_market_volume_*`/`buy_trade_rate_*`/`buy_side_share_*`; `upward_progress_ticks_*`; G03 upper relation | `UNDEFINED: prior upside break AFTER (buy participation AND upward progress継続)だが、prior-break state、継続回数／時間、thresholdがない。NO_FIXED_ADAPTER_PRODUCER: temporal state、buy participation、G03 relation` | neutral | bool | `UNDEFINED: STRATEGY_SPECIFIC continuation window` | `MISSING: original upper reference identity/price` | G16 `:691`; G03 `:144-191`; G08 `:361-384`; G09 `:414-418` |
| `downside_breakout_follow_through` | Follow-through | candidate: `sell_market_volume_*`/`sell_trade_rate_*`/`sell_side_share_*`; `downward_progress_ticks_*`; G03 lower relation | `UNDEFINED: prior downside break AFTER (sell participation AND downward progress継続)だが、prior-break state、継続回数／時間、thresholdがない。NO_FIXED_ADAPTER_PRODUCER: temporal state、sell participation、G03 relation` | neutral | bool | `UNDEFINED: STRATEGY_SPECIFIC continuation window` | `MISSING: original lower reference identity/price` | G16 `:692`; G03 `:144-191`; G08 `:385-408`; G09 `:419-422` |
| `upside_breakout_failure` | Breakout failure | candidate: G03 upper `relation_to_*`; `reversion_from_window_high_*`; `acceptance_above_value_*`候補 | `UNDEFINED: prior upside break AFTER (NOT acceptance AND reference下へ復帰)だが、prior-break state、acceptance comparator、復帰幅／期限がない。NO_FIXED_ADAPTER_PRODUCER: temporal state、generic acceptance、G03 relation/reversion` | neutral | bool | `UNDEFINED: failure deadline` | `MISSING: original upper reference identity/price` | G16 `:693`; G03 `:144-191`; G09 `:446-449`; G11 `:528-529` |
| `downside_breakout_failure` | Breakout failure | candidate: G03 lower `relation_to_*`; `reversion_from_window_low_*`; `acceptance_below_value_*`候補 | `UNDEFINED: prior downside break AFTER (NOT acceptance AND reference上へ復帰)だが、prior-break state、acceptance comparator、復帰幅／期限がない。NO_FIXED_ADAPTER_PRODUCER: temporal state、generic acceptance、G03 relation/reversion` | neutral | bool | `UNDEFINED: failure deadline` | `MISSING: original lower reference identity/price` | G16 `:694`; G03 `:144-191`; G09 `:450-453`; G11 `:530-531` |
| `bid_passive_defense_holding` | Defense holding | candidate: `bid_refresh_count_*`, `bid_add_volume_*`, `bid_net_flow_*`, `bid_stack_ratio_*`; `sell_no_progress_ratio_*`/`downward_progress_ticks_*`; bid wall/location | `UNDEFINED: bid補充 AND price保持の継続は読めるが、補充尺度、保持許容幅、継続回数／時間がない。NO_FIXED_ADAPTER_PRODUCER: fixed temporal defense state` | bid | bool | `UNDEFINED: 100ms/1s/5s plus persistence` | `MISSING: defended bid reference identity/price` | G16 `:705`; G07 `:308-331`; G09 `:419-445`; G06 `:299-300` |
| `ask_passive_defense_holding` | Defense holding | candidate: `ask_refresh_count_*`, `ask_add_volume_*`, `ask_net_flow_*`, `ask_stack_ratio_*`; `buy_no_progress_ratio_*`/`upward_progress_ticks_*`; ask wall/location | `UNDEFINED: ask補充 AND price保持の継続は読めるが、補充尺度、保持許容幅、継続回数／時間がない。NO_FIXED_ADAPTER_PRODUCER: fixed temporal defense state` | ask | bool | `UNDEFINED: 100ms/1s/5s plus persistence` | `MISSING: defended ask reference identity/price` | G16 `:706`; G07 `:332-355`; G09 `:414-441`; G06 `:301-302` |
| `bid_passive_defense_failed` | Defense failed | candidate: `bid_refresh_count_*`, `bid_pull_ratio_*`, `bid_cancel_volume_*`, `bid_net_flow_*`; `downward_progress_ticks_*`; bid wall/location | `UNDEFINED: prior bid defense AFTER (補充停止 AND 支持下抜け)だが、停止comparator、prior holding state、break幅／期限がない。NO_FIXED_ADAPTER_PRODUCER: prior defense state and defended price` | bid | bool | `UNDEFINED: 100ms/1s/5s plus failure deadline` | `MISSING: defended bid support identity/price` | G16 `:707`; G07 `:308-331`; G09 `:419-422`; G06 `:299-300` |
| `ask_passive_defense_failed` | Defense failed | candidate: `ask_refresh_count_*`, `ask_pull_ratio_*`, `ask_cancel_volume_*`, `ask_net_flow_*`; `upward_progress_ticks_*`; ask wall/location | `UNDEFINED: prior ask defense AFTER (補充停止 AND 抵抗上抜け)だが、停止comparator、prior holding state、break幅／期限がない。NO_FIXED_ADAPTER_PRODUCER: prior defense state and defended price` | ask | bool | `UNDEFINED: 100ms/1s/5s plus failure deadline` | `MISSING: defended ask resistance identity/price` | G16 `:708`; G07 `:332-355`; G09 `:414-418`; G06 `:301-302` |

## 5. UNDEFINED / MISSING一覧

### 5.1 全13件共通のUNDEFINED

- comparatorとthreshold version
- 同一familyに複数ある100ms／1s／5s／30s／5mの選択・整合
- `STRATEGY_SPECIFIC` windowの具体値
- activeからinactiveへ戻すreset、expiry、re-arm
- 素材完備で不成立の場合に`false`を出すかkey省略とするか
- source freshness／quality Conditionをrule内部で要求するか、上位predicateだけで要求するか

### 5.2 MISSING

- breakout／failure／follow-through用のstrategy-specific reference selector、identity、price
- absorption／passive defenseが対象にするwall／levelの固定identityとprice
- `attempt -> follow-through/failure`と`holding -> failed`のtemporal prerequisite state
- current adapterにはbuy/sell aggression、G03 location、acceptance、reversionの固定生成がなく、
  任意`pre_aggregated`入力に依存する一方、そのproducer契約が未定義
- `pre_aggregated` producerのkey allowlist、算出契約、freshness contract

### 5.3 正本反映前に必要な決定

1. 13件ごとの確定Tier A key、AND/OR、comparator名、threshold version。
2. variant/reference contextをComposite Synthesisへ渡すschema。
3. temporal stateのscope（symbol、variant、Observation Instance、reference ID）。
4. E98へ追加する2 keyのcomparator orientationとcandidate／contradiction上の実行意味。
5. adapterが直接生成するkeyと、producerがpre-aggregateするkeyの責任境界。

## 6. 変更・検証・停止checkpoint

- checkpoint時刻: 2026-07-27 12:30:07 JST。
- 承認範囲: Stage 1草案作成のみ。正本反映、source実装、commit/pushは未承認。
- 完了済み: Tier A 512件とG16 48件の転記、adapter出力抽出、E01/E02/E03/E98照合、
  E98 before/after、対象13件の材料候補・停止理由の草案化。
- 未完了: Stage 2正本反映、Composite Synthesis実装・試験。
- 変更file: 本草案1 fileのみ。
- 正本、source、test、runtime、raw data、収録基盤: 無変更。
- commit/push: なし。
- 検証（実測）:
  - 正本と草案の転記560件をfield比較し、不一致0件。内訳G01〜G15 512件、G16 48件。
  - G16草案は13行・13 unique key、side不正0、bool以外0、未置換テンプレート記号0。
  - E98 beforeは正本との差分0列。afterの差分は`contradiction_condition_ids`と
    `contradiction_condition_keys`の2列だけ。
  - E01/E02/E03/E98はCSV parserで各1行を確認。
  - adapter固定出力9 keyと任意`pre_aggregated` pass-throughを実コードから確認。
  - 対象正本2 fileと`condition_adapter.py`のtracked diffは0。
- blocker限定範囲: G16正本反映とComposite Synthesis Stage 2のみ。
- 次の再開位置: お館様が本草案の`UNDEFINED`／`MISSING`を解消する定義を承認した後、
  E98のfield orientationを再確認してからStage 2正本反映へ進む。

