# DeltaEngine Order Flow Strategy Method Constitution — Operational Draft

版: v0.2 draft  
起草日: 2026-07-26 JST  
状態: **未批准。実装・較正・observe・発注の承認ではない。**  
適用範囲: Order Flow Strategy Engine、Hook、Trigger、entry、execution、position management、検証、PDCA

# 0章 この憲法が拘束するもの

この文書の目的は一つである。

> 今後作るStrategyが、どの入力を使い、どの状態を保持し、どの順序でentryを判断し、
> 何をlogへ残し、どう失敗判定され、どう改善されるかを、実装者が勝手に変えられない形で固定する。

下位仕様は、各章に対して`CONFORM／DEVIATE／NOT_APPLICABLE`を回答しなければならない。
`DEVIATE`には理由、対象条項、代替安全策、検証、ユーザー承認が必要である。

### 0.1 この文書だけでは決めないもの

- 個別thresholdの数値
- Strategyの採用／不採用
- 発注数量
- risk limit
- LIVE移行
- 利益目標

これらはStrategy別仕様と検証結果で決める。数値を憲法へ固定して市場変化へ追随不能にしない。

### 0.2 現時点の運用状態

| 項目 | 状態 |
|---|---|
| raw収録 | 継続 |
| 88項目 | candidate inventory、全件`UNCALIBRATED` |
| HookEvent | 発火禁止 |
| 50 Trigger story | 未監査candidate、production Triggerではない |
| playbooks | `OBSERVE` |
| execution | `execution_enabled: false` |
| Flow Price Response／3段チャート／8パターン | 完成済み。変更対象外 |

---

# 1章 Source Truth

## 1.1 使用sourceと観測限界

| source | 実際のdata | 使用できること | 使用してはいけない推論 |
|---|---|---|---|
| Binance depth | Market-by-Priceのprice-level absolute quantity更新 | local book、level増減、spread、depth shape、OFI候補 | individual order、queue position、注文者同一性 |
| Binance `aggTrade` | single taker order単位にaggregateされたmarket trade | aggressor side、price、quantity、tempo、aggTrade由来Footprint | 完全なMBO match列、未配信tradeを含む完全tape |
| Binance `forceOrder` | symbol別1000ms内latest-one liquidation snapshot | 観測された清算snapshotのside／notional／event study | 全清算件数、N件/秒、完全cascade volume、真のexhaustion |
| Binance OI | 時点間の未決済contract総数 | OI changeとprice changeのjoint context | 新規long、新規short、cover、投げの主体確定 |
| HFM quote | BTCUSDrの執行側bid／ask | spread、quote age、Binance-HFM basis、entry reference | Binanceと同一order book／同一price formationという仮定 |
| HFM order result | request、ack、fill、reject等 | 実fill、slippage、latency、reject率 | Binance L2からのfill代用 |

actual HFM account entityとBTCUSDr contract specificationは未確認事項として残す。確認前に
execution modelを確定してはならない。

## 1.2 Canonical Event Envelope

Strategy関連で使う全raw eventは、payloadに加えて最低限次を持つ。

```yaml
source: BINANCE_USDM_DEPTH | BINANCE_USDM_AGGTRADE | BINANCE_FORCE_ORDER | BINANCE_OI | HFM_QUOTE | HFM_EXECUTION
symbol: string
source_event_id: string | null
exchange_ts: timestamp | null
receive_ts: timestamp
persisted_ts: timestamp
sequence_first: integer | null
sequence_last: integer | null
session_id: string
payload_hash: sha256
quality_flags: []
schema_version: string
```

`quality_flags`は少なくとも次を表現できること。

```text
GAP_DETECTED
RESYNCING
STALE
CLOCK_ANOMALY
OUT_OF_ORDER
SCHEMA_UNKNOWN
SOURCE_SAMPLED
SOURCE_AGGREGATED
CROSS_VENUE_UNALIGNED
PERSISTENCE_UNCONFIRMED
```

`SOURCE_SAMPLED`は`forceOrder`、`SOURCE_AGGREGATED`は`aggTrade`へsource contractに従い付与する。
これはdata errorではなく、下流推論へ伝える観測限界である。

## 1.3 Data Quality Gate

新規Strategy decision時に次のいずれかが成立したら`DATA_BLOCK`とする。

- depth sequence gap未解消
- local book resync中
- 必須sourceがStrategy別`max_source_age`を超過
- exchange timeとreceive timeの差が許容範囲外
- schema version不明
- journal commit未確認のeventだけでdecisionを作る
- Binance-HFM alignmentがStrategy別limit外

`DATA_BLOCK`を他のevidence点数で相殺してはならない。

## 1.4 必須log

各decision packetに次を保存する。

```yaml
source_manifest_id: string
event_id_range_by_source: map
quality_gate_result: PASS | BLOCK
quality_reason_codes: []
max_event_age_ms_by_source: map
clock_offset_ms_by_source: map
book_sync_state: SYNCED | RESYNCING | UNKNOWN
```

## 1.5 Acceptance Test

1. gapを注入したreplayで新規entryが0件になる。
2. resync完了後、`source_manifest_id`が切り替わり、古いbook stateを引き継がない。
3. `forceOrder`依存Strategy packetに`SOURCE_SAMPLED`が必ず残る。
4. future timestampまたはout-of-order eventがdecisionへ混入しない。
5. decisionから使用raw frameへhashで逆引きできる。

---

# 2章 88項目を同じHookとして扱わない

## 2.1 使用するrole enum

全項目は一つ以上のroleへ明示分類する。

```text
OBSERVATION
FEATURE
CONTEXT
EVIDENCE_CANDIDATE
SUSPECTED_SIGNATURE
EXECUTION_GATE
UNOBSERVABLE_AS_DEFINED
```

roleを決めない項目はthreshold較正対象にできない。

## 2.2 現行categoryの初期再分類

| category | 数 | 主role | 先に直す問題 |
|---|---:|---|---|
| A DOM | 24 | FEATURE／SUSPECTED_SIGNATURE | wall、iceberg、spoof、queueの観測限界 |
| B Tape | 20 | FEATURE | exact sweep、institution、crowdという過剰解釈 |
| C 板×約定 | 9 | EVIDENCE_CANDIDATE | depthとtradeのevent-time整合、C09のsampled liquidation |
| D Flow response | 8 | FEATURE／EVIDENCE_CANDIDATE | `TRAPPED`等はmodel labelで実positionではない |
| E Liquidation | 6 | OBSERVATION／UNOBSERVABLE_AS_DEFINED | E03/E04 rate、E06 exhaustion |
| F OI | 5 | CONTEXT／FEATURE | participant sideの事実名を除去 |
| G Price structure | 12 | CONTEXT | locationは単独Triggerではない |
| H Environment | 4 | CONTEXT／EXECUTION_GATE | H04だけでexecution安全としない |

## 2.3 HookSpec必須field

Hookとして残す項目は次を持つ。

```yaml
hook_id: string
hook_version: semver
name_observable: string
role: enum
source_dependencies: []
feature_dependencies: []
event_start_rule: clause
event_end_rule: clause
side_semantics: BID | ASK | BUY_AGGRESSOR | SELL_AGGRESSOR | NONE | MODEL_DEFINED
price_reference: definition
window: definition
normalization_population: definition
quality_requirements: []
known_blind_spots: []
forbidden_claims: []
output_fields: []
reference_validator_version: string
status: UNREVIEWED | UNCALIBRATED | VALIDATED_FEATURE | RESTRICTED | REJECTED | RETIRED
```

HookSpecに`trade_direction: BUY/SELL`を置いてはならない。方向上の意味はStrategy側の
`EvidenceClause`で定義する。

## 2.4 三つの具体的な修正例

### A19 現行「見せ板疑い（Bid）」

修正後の観測名候補:

```text
REPEATED_LARGE_BID_DISPLAY_WITHDRAWAL_WITHOUT_MATCHED_CONSUMPTION
```

観測するもの:

- 同距離帯baselineより大きいBid levelの出現
- そのlevelへ対応するaggressive sell量
- quantity減少のうちtradeで説明できる部分と説明できない部分
- 出現／撤去の反復

禁止claim:

- 注文者が同一
- 約定意思がなかった
- spoofingが確定

### F01 現行「OI増×価格上昇＝新規ロング流入」

修正後:

```text
OI_UP_PRICE_UP_WINDOW
```

保存するもの:

- OI start／end／change percent
- price reference start／end／change bps
- windowとsampling age

禁止claim:

- 新規longの数量
- aggressorがopening long
- 反対側shortの意図

### E03 現行「ロング清算連鎖＝N件/秒」

現`forceOrder`だけでは`UNOBSERVABLE_AS_DEFINED`とする。

代替candidate:

```text
OBSERVED_LONG_LIQUIDATION_SNAPSHOT_PERSISTENCE
```

これは連続する1秒binでlong liquidation snapshotが観測された状態であり、bin内全件数または
全notionalを意味しない。

## 2.5 Hook Acceptance Test

1. raw replayとproduction detectorを別実装で照合できる。
2. false positive、false negative、side error、timing errorを別々に報告する。
3. fire windowだけでなくeligible non-fire windowを含める。
4. `known_blind_spots`がdecision packetへ伝播する。
5. `UNOBSERVABLE_AS_DEFINED`の項目へthresholdを設定できない。
6. Featureが正しく計算されたことと、Strategy edgeがあることを別statusで管理する。

---

# 3章 Market State Record

## 3.1 一時点のstate schema

Strategy Engineは、Hookの配列ではなく次のpoint-in-time stateを読む。

```yaml
market_state_id: string
asof_exchange_ts: timestamp
constructed_at_receive_ts: timestamp
symbol_observed: BTCUSDT_PERP
horizons:
  micro:
    duration: strategy_specified
    auction_location: enum
    initiative_side: BUY | SELL | BALANCED | UNKNOWN
    price_response_state: enum
    liquidity_state: enum
    tempo_state: enum
  tactical:
    duration: strategy_specified
    auction_location: enum
    structure_state: enum
    flow_response_state: enum
  context:
    duration: strategy_specified
    session: enum
    volatility_regime: enum
    trend_range_state: enum
location:
  references: []
  nearest_reference_id: string | null
  distance_ticks: number | null
  inside_outside: enum
liquidity:
  spread_ticks: number
  depth_by_band: map
  imbalance_by_band: map
  refresh_withdrawal_features: map
flow:
  buy_aggressive_qty: number
  sell_aggressive_qty: number
  trade_rate: number
  size_distribution_features: map
response:
  price_change_ticks: number
  price_change_bps: number
  flow_price_response_states: map
participation_proxies:
  oi_change: number | null
  observed_liquidation_snapshot_features: map | null
cross_venue:
  hfm_bid: number | null
  hfm_ask: number | null
  spread: number | null
  basis: number | null
  quote_age_ms: number | null
quality:
  gate: PASS | BLOCK
  flags: []
  unknown_fields: []
state_builder_version: string
source_manifest_id: string
```

durationは固定の「1秒／30秒／5分」を憲法で決めない。Strategyごとに事前登録する。
同じFeatureを異なるhorizonで使う場合、別fieldとして保持する。

## 3.2 `auction_location`の最低enum

```text
INSIDE_VALUE
VALUE_EDGE_HIGH
VALUE_EDGE_LOW
PRIOR_HIGH_APPROACH
PRIOR_LOW_APPROACH
BREAK_ABOVE_REFERENCE
BREAK_BELOW_REFERENCE
RECLAIM_FROM_ABOVE
RECLAIM_FROM_BELOW
RANGE_MIDDLE
RANGE_EDGE_HIGH
RANGE_EDGE_LOW
LOCATION_UNKNOWN
```

`touch`だけで`REJECTION`または`ACCEPTANCE`を確定しない。acceptance／rejectionは滞在、再test、
price migration、flow responseを使う別state transitionとして定義する。

## 3.3 `liquidity_state`の最低enum

```text
NORMAL
THINNING_BID
THINNING_ASK
THIN_BOTH
CONCENTRATED_BID
CONCENTRATED_ASK
VOID_ABOVE
VOID_BELOW
REFRESHING_BID_LIKE
REFRESHING_ASK_LIKE
UNSTABLE
UNKNOWN
```

名称の`LIKE`はhidden orderまたは同一主体を確定していないことを示す。

## 3.4 一つの具体例

以下は説明用であり、数値thresholdではない。

```yaml
reference: prior_session_high = 68000
binance_last: 67996
auction_location: PRIOR_HIGH_APPROACH
approach:
  last_10s_price_change: +18 ticks
  buy_aggressive_qty: increasing
  price_progress_per_buy_qty: declining
liquidity:
  ask_at_68000: repeatedly replenished_like
  levels_above_68000: normal
flow_price_response:
  micro: BUY_STALLED_MODEL_STATE
cross_venue:
  hfm_spread: normal_for_profile
  quote_age_ms: within_limit
quality:
  gate: PASS
```

このstateだけでBUYまたはSELLを出さない。少なくとも次の二つを同時に`WATCH`できる。

- `BREAKOUT_ACCEPTANCE_LONG`: 買いが再加速し68000上でacceptされる仮説
- `FAILED_AUCTION_SHORT`: 買いが進まずattempt失敗後に68000下へreclaimする仮説

## 3.5 Point-in-Time Test

1. state構築時刻より後のeventを使用しない。
2. 同じmanifestとversionからbyte-equivalent stateを再構成できる。
3. 必須field欠落時は`UNKNOWN`またはquality `BLOCK`となり、zero補完しない。
4. 同一raw featureを複数state軸に使った場合、dependency graphで重複を追跡できる。
5. completed Flow Price Responseの値は読み取り利用し、再計算または既存表示を変更しない。

---

# 4章 Strategy SpecificationとEngine

## 4.1 StrategySpec必須field

```yaml
strategy_id: string
strategy_version: semver
family: enum
observed_instrument: BINANCE_BTCUSDT_PERP
execution_instrument: HFM_BTCUSDr
holding_horizon: definition
hypothesis: falsifiable statement
eligibility_clauses: []
disqualifying_clauses: []
location_requirements: []
approach_sequence: []
required_evidence: []
supporting_evidence: []
contradicting_evidence: []
invalidation_clauses: []
expiry_clauses: []
entry_modes: []
follow_through_clauses: []
position_management_rules: []
execution_profile_version: string
risk_profile_version: string
evaluation_contract_version: string
dependency_versions: map
status: DRAFT | SHADOW_CANDIDATE | VALIDATED | APPROVED_OBSERVE | RESTRICTED | REJECTED | RETIRED
```

`hypothesis`は「上がりそう」ではなく、条件、期待sequence、失敗を一文で書く。

例:

> prior highへbuy initiativeが増加して接近し、high上でaggressive buyに対するprice progressが維持され、
> retestでhigh下へ戻らなければ、指定horizon内の上方auction continuation確率がeligible baselineより高い。

## 4.2 StrategyInstance必須field

```yaml
strategy_instance_id: uuid
strategy_id: string
strategy_version: semver
created_at: timestamp
state: WATCH | ARMED | ENTERABLE | EXECUTION_PENDING | OPEN | MANAGING | CLOSED | NO_TRADE | INVALIDATED | EXPIRED | DATA_BLOCKED | EXECUTION_BLOCKED
location_reference_id: string
market_state_ids: []
evidence_clause_results: map
evidence_event_ids: []
contradiction_clause_results: map
current_entry_mode_candidates: []
invalidation_state: map
expiry_at: timestamp | null
reason_trace_ids: []
competing_instance_ids: []
```

## 4.3 state transition table

| From | To | 必須条件 |
|---|---|---|
| WATCH | ARMED | eligibility全PASS、disqualifier全false、quality PASS、location内 |
| ARMED | ENTERABLE | required evidence全PASS、指定順序／age内、invalidation false、entry zone内 |
| ENTERABLE | EXECUTION_PENDING | EntryDecision作成、Execution Gate評価開始 |
| EXECUTION_PENDING | OPEN | order fill確認。request送信だけではOPENにしない |
| OPEN | MANAGING | initial fillとposition state照合完了 |
| any pre-entry | NO_TRADE | disqualifier、late price、conflict unresolved、任意の明示見送り |
| any | DATA_BLOCKED | quality hard gate失敗 |
| any pre-entry | INVALIDATED | invalidation clause成立 |
| any pre-entry | EXPIRED | TTL／time window終了 |
| EXECUTION_PENDING | EXECUTION_BLOCKED | stale、spread、basis、slippage、reject等 |
| MANAGING | CLOSED | exit fillとposition flat確認 |

## 4.4 EvidenceClause schema

```yaml
clause_id: string
role: REQUIRED | SUPPORTING | CONTRADICTING | INVALIDATING | QUALITY_GATE
input_fields: []
operator: versioned expression
must_occur_after: clause_id | null
must_occur_before: clause_id | null
max_age_ms: integer | null
max_gap_ms: integer | null
minimum_duration_ms: integer | null
unknown_policy: FAIL | BLOCK | IGNORE_SUPPORTING_ONLY
result: PASS | FAIL | UNKNOWN | STALE
evaluated_at: timestamp
evidence_ids: []
```

単純な`C01 AND B03 AND D01`では不足する。どれが先で、何秒以内で、どのlocationで、
何が起きなければならないかをclauseにする。

## 4.5 競合Strategyの処理

同一locationでlong／short candidateが存在する場合、score差だけで一方を選ばない。

次のいずれかを出力する。

```text
ONE_SIDE_DISQUALIFIED
ONE_SIDE_INVALIDATED
DECISION_EVENT_RESOLVED
BOTH_STILL_WATCH
CONFLICT_NO_TRADE
```

`BOTH_STILL_WATCH`中はentry不可。共通raw dataから派生したevidenceを両側でどう解釈したか、
同じevent IDを保存する。

## 4.6 Reason Traceの最低format

```yaml
decision_id: uuid
strategy_instance_id: uuid
decision: ARM | ENTERABLE | NO_TRADE | INVALIDATE | EXPIRE | HOLD | ADD | REDUCE | EXIT
decision_ts: timestamp
market_state_id: string
passed_clause_ids: []
failed_clause_ids: []
unknown_clause_ids: []
competing_strategy_summary: map
quality_gate: PASS | BLOCK
reason_codes: []
spec_versions: map
```

自然言語summaryだけをreason traceとしてはならない。

## 4.7 Engine Acceptance Test

1. 同一input manifestで同一decision列を再生できる。
2. evidenceの到着順を入れ替えると、順序依存Strategyは同じTriggerを出さない。
3. required evidence一つを除くablationで`ENTERABLE`にならない。
4. supporting evidenceを増やしてquality blockを突破できない。
5. 競合未解決時にBUY／SELLを強制出力しない。
6. strategy／hook／threshold／execution profileのいずれかのversionが違えば別instance lineageとなる。

## 4.8 Statistical／ML／AI inferenceを使う場合

rule clause以外のmodelを使う場合、出力を次のpacketで固定する。

```yaml
inference_output_id: uuid
model_id: string
model_version: string
training_manifest_id: string
calibration_report_id: string
input_market_state_id: string
input_feature_ids: []
strategy_instance_id: uuid
predicted_object: string
output_value: number | enum | distribution
uncertainty: map
out_of_distribution_result: PASS | BLOCK | UNKNOWN
generated_at: timestamp
raw_model_output_hash: sha256
role_in_strategy: SUPPORTING | REQUIRED_IF_SEPARATELY_APPROVED
```

運用条件:

1. modelが評価する対象を`next price up`のような曖昧labelにせず、Strategyのexpected sequence、
   follow-through、invalidation等へ結び付ける。
2. training／calibration／validation／holdout manifestを分離する。
3. OOD `BLOCK`または必須input欠落時はdecisionに使わない。
4. model outputだけでStrategyを作成しない。eligibleなStrategy instanceへ紐付ける。
5. model outputでData Quality Gate、Execution Gate、logical invalidationを上書きしない。
6. 自然言語reasonだけをorder条件にしない。機械値とinput lineageを保存する。
7. modelを変更したらStrategy dependency versionを上げ、L2-L5を再検証する。

高度化はmodel名でなく、simple state-machine baselineに対するholdout上のincremental valueで判定する。

---

# 5章 Entry Timing

## 5.1 EntryDecision schema

```yaml
entry_decision_id: uuid
strategy_instance_id: uuid
strategy_version: semver
trigger_mode: ANTICIPATORY | CONFIRMED | RETEST | PASSIVE | AGGRESSIVE
observed_side: LONG | SHORT
decision_exchange_ts: timestamp
decision_receive_ts: timestamp
location_reference: map
binance_reference_price: number
entry_zone_observed: map
required_clause_results: map
contradiction_results: map
intended_order_type: MARKETABLE | LIMIT | STOP | NONE
entry_ttl_ms: integer
max_entry_deviation: definition
logical_invalidation: map
expected_follow_through: map
quality_gate: PASS | BLOCK
execution_gate_required: true
status: ENTERABLE | LATE | CONFLICT | BLOCKED | EXPIRED
```

## 5.2 実際の判定順序

```text
1. locationに入った -> WATCH
2. eligibilityとapproachが揃った -> ARMED
3. 競合仮説を識別するdecision eventを待つ
4. required evidenceの順序・age・持続を評価
5. invalidation／disqualifier／data qualityを評価
6. Binance上のentry zoneを評価
7. EntryDecisionを作る
8. HFM Execution Gateへ渡す
9. HFM条件不良なら注文せずEXECUTION_BLOCKED
10. fill確認後だけOPEN
```

## 5.3 具体例A: prior high breakout continuation

これは説明用traceであり、数値はthreshold提案ではない。

```text
reference high: Binance 68,000
t0: 67,982から買いaggression増加、trade rate増加
t1: 67,996、price progress維持、Ask depthは消費／上方へ移動
t2: 68,000をtrade、68,005まで進む
t3: 68,000-68,002をretestし、aggressive sellが出ても68,000下へ戻らない
```

`BREAKOUT_ACCEPTANCE_LONG`の一例:

| 段階 | clause |
|---|---|
| eligibility | `PRIOR_HIGH_APPROACH`、quality PASS、spread／volatilityが適用範囲内 |
| approach | buy initiative増加とprice progressが同時に維持 |
| decision | high上のtradeだけでなく、指定acceptanceまたはretest hold |
| contradiction | high上でbuy aggression増にもかかわらずpriceが進まない |
| invalidation | high下へreclaimし、指定時間維持またはsell response成立 |
| entry | CONFIRMEDまたはRETEST。Strategy版で一方を指定 |
| late | entry zone上限を越えたら追わない |

`A04 Ask wall pull`、`B01 buy consecutive`、`B11 inferred buy sweep`の単純ANDだけでは発火させない。
location、price progress、acceptance、反対evidenceが必要である。

## 5.4 具体例B: 同じprior highのfailed auction short

```text
reference high: Binance 68,000
t0-t2: 上記と同じ接近
t3: 68,005でbuy aggressionが続くがprice progress停止
t4: 67,998へ戻り、68,000のBid再確立に失敗
t5: sell aggressionと下方price responseが成立
```

`FAILED_AUCTION_SHORT`の一例:

| 段階 | clause |
|---|---|
| eligibility | prior high外へのattemptが存在 |
| decision | price progress failure -> high下reclaim -> sell responseの順序 |
| contradiction | 68,000上でacceptanceが再成立 |
| invalidation | failed highまたはStrategy別invalidation zoneを上回りacceptance |
| entry | CONFIRMED reclaimまたはretest failure |
| late | 下落後にremaining opportunity不足なら見送り |

同じA/B/D系Featureを使っても、expected sequenceが反対である。これがStrategy Engineの必要理由である。

## 5.5 具体例C: Bid absorption defense long

必要sequenceの骨格:

```text
1. 事前定義されたsupport／value edgeへ到達
2. aggressive sellがBidへ継続到達
3. sell量に対しdownward price progressが低下
4. Bid quantityの維持／再補充like、またはlevel reclaim
5. sell pressure減衰だけでなく、buy responseまたは上方price migration
6. entry zone内でCONFIRMED／RETEST entry
```

禁止:

- C01検出と同時に無条件BUY
- 同じraw flowから作ったC01とD04を独立した二確認として数える
- support locationなしのabsorptionを同じStrategyへ混ぜる
- price responseが出ないまま「大口が吸っているはず」と待ち続ける

## 5.6 Miss／Late／No Trade reason code

最低reason code:

```text
NO_SETUP
WRONG_LOCATION
APPROACH_MISMATCH
REQUIRED_EVIDENCE_MISSING
EVIDENCE_ORDER_WRONG
CONTRADICTION_ACTIVE
COMPETING_STRATEGY_UNRESOLVED
PRICE_LEFT_ENTRY_ZONE
DATA_BLOCK
EXECUTION_SPREAD_BLOCK
EXECUTION_BASIS_BLOCK
EXECUTION_STALE_QUOTE
STRATEGY_EXPIRED
```

## 5.7 Entry Acceptance Test

1. level touchだけではEntryDecisionを出さない。
2. breakoutとfailed breakoutを同じevent列から別state machineとして再生できる。
3. entry zone離脱後に新Hookを足して追随entryしない。
4. Trigger成立時の全required clauseと反対evidenceを表示できる。
5. EntryDecision時刻以後のeventを判断理由に使わない。
6. HFM Execution Gate前の状態を`FILLED`または`OPEN`にしない。

---

# 6章 HFM Execution Gate

## 6.1 観測判断と執行判断を分ける

Binance上でStrategyが`ENTERABLE`でも、HFM上で注文価値がなければ送信しない。

```text
Binance EntryDecision
  -> synchronized HFM quote取得
  -> cross-venue／cost評価
  -> ExecutionDecision
  -> execution_enabled確認
  -> order request
  -> ack／fill／reject照合
```

現Stage 2Cでは`execution_enabled: false`のため、ExecutionDecisionはshadow結果までで停止する。

## 6.2 ExecutionSnapshot schema

```yaml
execution_snapshot_id: uuid
entry_decision_id: uuid
captured_at: timestamp
binance_reference_price: number
binance_reference_ts: timestamp
hfm_bid: number
hfm_ask: number
hfm_quote_ts: timestamp | null
hfm_receive_ts: timestamp
hfm_quote_age_ms: number
hfm_spread_price: number
hfm_spread_bps: number
basis_bid_bps: number
basis_ask_bps: number
recent_basis_distribution_id: string
recent_latency_distribution_id: string
recent_slippage_distribution_id: string
requested_side: BUY | SELL
requested_size: number
contract_spec_version: string
execution_profile_version: string
```

## 6.3 ExecutionDecision schema

```yaml
execution_decision_id: uuid
entry_decision_id: uuid
execution_snapshot_id: uuid
decision: SHADOW_ELIGIBLE | LIVE_SEND_ALLOWED | BLOCK | EXPIRED
order_type: MARKET | PENDING_LIMIT | PENDING_STOP | NONE
reference_entry_price: number
worst_allowed_entry_price: number | null
ttl_ms: integer
estimated_cost_components_bps:
  spread: number
  slippage_conservative: number
  latency_adverse_move_conservative: number
  fees: number
  basis_uncertainty: number
gross_opportunity_lower_bound_bps: number
net_opportunity_lower_bound_bps: number
gate_results: map
reason_codes: []
execution_enabled_seen: boolean
```

`gross_opportunity_lower_bound_bps`とcost componentは、Strategy別validation／shadow distributionから
取る。都合のよい平均値ではなく、事前指定したconservative estimateを使う。

## 6.4 必須gate

```text
QUOTE_FRESH
SPREAD_WITHIN_PROFILE
BASIS_WITHIN_PROFILE
LATENCY_BUDGET_AVAILABLE
SIZE_WITHIN_VALIDATED_RANGE
ENTRY_PRICE_WITHIN_ZONE
NET_OPPORTUNITY_POSITIVE_AFTER_BUFFER
CONTRACT_SPEC_CONFIRMED
EXECUTION_ENABLED
```

Stage 2Cでは最後の`EXECUTION_ENABLED`が常にfalseでなければならない。shadow replayでは
「それ以外がPASS」という`SHADOW_ELIGIBLE`を残すが、実requestは作らない。

## 6.5 cross-venue blockの具体例

```text
Binance: breakout long ENTERABLE
HFM: quote受信がmax_quote_ageを超過
結果: EXECUTION_STALE_QUOTE、注文なし
```

```text
Binance: failed auction short ENTERABLE
HFM: spread拡大＋basisがvalidation範囲外
結果: EXECUTION_SPREAD_BLOCK／EXECUTION_BASIS_BLOCK、注文なし
```

正しいBinance方向判断がHFMでの正しいentryを保証しない。このblocked episodeもStrategyの
execution viability評価へ含める。

## 6.6 注文state

LIVEが別承認された将来でも、注文は最低限次を区別する。

```text
NOT_SENT
SEND_REQUESTED
ACKNOWLEDGED
PARTIALLY_FILLED
FILLED
REJECTED
CANCEL_REQUESTED
CANCELLED
STATUS_UNKNOWN
```

timeoutを`REJECTED`または`NOT_FILLED`と推定しない。`STATUS_UNKNOWN`は照会・reconciliationが
完了するまで新規重複注文を禁止するhard stateである。

## 6.7 Execution Acceptance Test

1. Binance priceだけでHFM fill priceを生成しない。
2. stale HFM quoteで`SHADOW_ELIGIBLE`にしない。
3. spread／basis／latency／slippageを別costとして保存する。
4. sizeを変えたepisodeを同一execution profileで無条件比較しない。
5. `execution_enabled: false`時のexternal order requestが0件である。
6. request、ack、fill、positionの四つを照合できるまでOPENにしない。

---

# 7章 Position Lifecycle

## 7.1 PositionState schema

```yaml
position_state_id: uuid
strategy_instance_id: uuid
execution_decision_id: uuid
broker_position_id: string | null
state: PENDING | OPEN | MANAGING | REDUCING | EXITING | FLAT | RECONCILIATION_BLOCK
side: LONG | SHORT
filled_size: number
average_fill_price: number
opened_at: timestamp
current_hfm_bid: number
current_hfm_ask: number
logical_invalidation: map
protective_order_state: map
follow_through_clause_results: map
management_clause_results: map
unrealized_path_metrics: map
data_quality_state: map
position_spec_versions: map
```

## 7.2 entry直後に検査するもの

StrategySpecは`initial_follow_through_deadline`と最低一つの期待反応を持つ。

例:

- breakout long: reference上の維持、buy flowに対する上方price progress、retest failureなし
- failed auction short: reclaim level下の維持、sell flowへの下方response、high再acceptなし
- absorption defense long: defended zoneからの離脱、sell pressure再加速なし

entry後の指定時間内に期待反応が出ない場合、`FOLLOW_THROUGH_MISSING`としてhold継続条件を
再評価する。損益が小さいことを理由に無期限holdしない。

## 7.3 decision enum

```text
HOLD_THESIS_CONFIRMED
HOLD_WITHIN_EXPECTED_NOISE
ADD_ONLY_AS_SPECIFIED
REDUCE_EVIDENCE_WEAKENED
EXIT_INVALIDATION
EXIT_FOLLOW_THROUGH_MISSING
EXIT_OPPOSITE_STRATEGY_CONFIRMED
EXIT_TIME
EXIT_EXECUTION_RISK
EMERGENCY_FLATTEN
```

## 7.4 Addの条件

含み益であることだけを理由にaddしない。addは次をすべて満たす。

- StrategySpecにadd clauseがある
- 新しい独立したdecision eventがある
- logical invalidationとtotal riskが再計算される
- HFM Execution Gateを再度通る
- original Strategy instanceとのlineageを保持する

## 7.5 Invalidation

logical invalidation成立時、`EXIT_INVALIDATION`を出す。entry後にthresholdまたはreferenceを
遠ざけ、仮説を延命することを禁止する。

protective stopの約定価格がlogical invalidation priceと違う場合、差をslippage／gapとして記録し、
Strategy truthとExecution qualityを混ぜない。

## 7.6 具体例: breakout longのentry後失敗

```text
t0: 68,000上のretest holdでlong EntryDecision
t1: HFM Execution Gate PASS相当、shadow fillを記録
t2: Binanceが68,000下へreclaim
t3: sell aggressionに下方price response
t4: Strategy invalidation clause PASS
decision: EXIT_INVALIDATION
```

この時、後から「Bid wallが出たからhold」へ別Strategyを継ぎ足してはならない。新しいStrategyへ
切り替える場合、元Strategyを一度終了し、新しいinstance、entry、riskとして扱う。

## 7.7 Data Block中の既存position

新規entryは即時停止する。既存positionの処理はStrategySpecでなく共通Risk／Fail-Safe policyが
優先し、少なくとも次を定義する。

- protective orderがbroker側に存在するか
- quote断時のposition照会経路
- `STATUS_UNKNOWN`時の重複order禁止
- 最大未確認時間
- emergency flattenの権限と承認範囲

具体的risk値とLIVE操作は本憲法では許可しない。

## 7.8 Position Acceptance Test

1. Trigger後ではなくfill確認後にPositionStateをOPENにする。
2. initial follow-through未達をreason codeとして出せる。
3. invalidation成立後に任意Hookで元Strategyを延命しない。
4. addごとにExecution Gateとrisk再計算を行う。
5. exit requestとexit fillを区別し、flatをbroker positionと照合する。
6. entryからexitまで一つのStrategy lineageを再生できる。

---

# 8章 最初に検証するStrategy Family

以下は採用Strategyではない。現行50 Trigger storyを監査・再配置するためのresearch familyである。

| family | eligibility／location | decision sequence | 主な反対証拠 | 現dataでの扱い |
|---|---|---|---|---|
| BREAKOUT_ACCEPTANCE | prior high/low、range edge、value edge | initiative増加 -> break -> acceptanceまたはretest hold | progress failure、即reclaim | 検証候補 |
| FAILED_AUCTION_RECLAIM | reference外attempt | progress failure -> reference内reclaim -> opposite response | outside acceptance再成立 | 検証候補 |
| ABSORPTION_DEFENSE | 事前support/resistance | aggressive attack -> low progress -> replenish/hold-like -> opposite response | level consumption、through-trade継続 | 検証候補 |
| ABSORPTION_FAILURE | defended level | repeated attack -> defense劣化 -> level消費 -> continuation | rapid replenish／reclaim | 検証候補 |
| PULLBACK_CONTINUATION | confirmed directional auction内のpullback | counter-flow減衰 -> defended reference -> initiative再開 | pullbackが新規反対auctionへ発展 | 検証候補 |
| MOMENTUM_EXHAUSTION | extended move／auction objective付近 | aggression継続 -> price progress低下 -> opposite response | initiative再加速と新価格acceptance | 検証候補 |
| RANGE_ROTATION | confirmed range edge | edge attempt失敗 -> range内acceptance | range break acceptance | range定義から要検証 |
| LIQUIDATION_CONDITIONED | observed liquidation snapshot周辺 | sampled event -> price/flow response | sample欠落でsequence不明 | 制限または保留 |

## 8.1 familyごとに分けるentry mode

一つのfamilyを次のように別Strategy版へ分ける。

```text
BREAKOUT_ACCEPTANCE_LONG_CONFIRMED
BREAKOUT_ACCEPTANCE_LONG_RETEST
BREAKOUT_ACCEPTANCE_SHORT_CONFIRMED
BREAKOUT_ACCEPTANCE_SHORT_RETEST
```

long／short、confirmed／retestを一つにまとめて集計しない。price behavior、cost、sample、failureが
違うためである。

## 8.2 現行50 storyの扱い

各T01-T50について次を埋める。

```yaml
legacy_trigger_id: Txx
candidate_family: enum | NONE
candidate_entry_mode: enum | UNKNOWN
observable_inputs: []
unobservable_claims: []
duplicate_evidence_dependencies: []
missing_location: boolean
missing_approach: boolean
missing_sequence: boolean
missing_invalidation: boolean
missing_execution: boolean
missing_management: boolean
disposition: REWRITE | MERGE | RESTRICT | DEFER | REJECT
```

Trigger数50を維持することを目的にしない。同じfamily／entry mode／failure modelならmergeし、
観測不能ならdeferまたはrejectする。

## 8.3 Family Acceptance Test

1. 各familyに競合familyが最低一つ定義される。
2. locationなしのfamily instanceを作らない。
3. required sequenceとinvalidationを先に固定する。
4. long／short、entry mode、regimeを別集計できる。
5. liquidation familyは`SOURCE_SAMPLED`を無視してVALIDATEDになれない。

---

# 9章 Validation

## 9.1 Validation Manifest

検証開始前に次を固定する。結果を見てから書き換えた場合は新trialとする。

```yaml
validation_id: uuid
object_type: SOURCE | HOOK | FEATURE | EVIDENCE | STRATEGY | ENTRY_MODE | EXECUTION_PROFILE | SHADOW_POLICY
object_id: string
object_version: string
source_manifest_ids: []
periods:
  discovery: range
  calibration: range
  validation: range
  untouched_holdout: range
eligibility_population: definition
exclusions: []
minimum_sample_requirements: map
regime_bins: []
horizons: []
baselines: []
metrics: []
pass_fail_rules: []
multiple_testing_family_id: string
trial_registry_id: string
created_before_result_ts: timestamp
```

## 9.2 検証level

| level | 対象 | 問い | 必須出力 |
|---|---|---|---|
| L0 | Source | 欠落・誤解なく保存したか | gap、sequence、clock、schema、sampling report |
| L1 | Hook／Feature | 定義どおり検出・計算したか | false positive／negative、side／timing error |
| L2 | Evidence | 同じsetup baselineへ追加情報を持つか | conditional response、ablation、regime別効果 |
| L3 | Strategy／Entry | eligible episode内でexpected sequenceとentry timingが耐えるか | MFE／MAE、follow-through、invalidation、no-trade |
| L4 | Execution | HFMで実行可能か | spread、basis、latency、slippage、reject、net opportunity |
| L5 | Shadow Policy | realtimeで同じlifecycleを再現できるか | decision trace、state drift、paper position、reconciliation |

L0-L5を一つの`CALIBRATED`で表現しない。各objectはlevel別statusを持つ。

## 9.3 L1 Hook／Feature検証

必須dataset:

- production detectorがfireしたwindow
- eligibleだがfireしなかったwindow
- source gap／resync／boundary case
- side反転synthetic case
- threshold直上／直下case

必須metric:

```text
reference_positive_count
production_positive_count
true_positive
false_positive
false_negative
side_error
start_time_error_distribution
end_time_error_distribution
quality_flag_propagation_errors
```

L1では勝敗・PnLを合格条件にしない。ここで問うのはsensor truthである。

## 9.4 L2 Evidence検証

Evidenceの比較対象は「全時刻平均」でなく、同じStrategy setup、location、regime、horizonを持つ
eligible baselineである。

例:

```text
対象: PRIOR_HIGH_APPROACHのeligible episode
baseline: approach stateだけ
candidate: baseline + multi-level OFI evidence
比較: high上acceptance、failed reclaim、time-to-moveのconditional distribution
```

必須検査:

- candidateを外したablation
- 同じraw dependencyからの重複Featureを一群として外すablation
- sideを反転またはevent timeをshuffleするnegative control
- session／volatility／liquidity／trend-range別の結果
- effect directionの一貫性とconfidence interval

aggregateでは有効でも特定regimeだけで逆転する場合、`RESTRICTED`とし適用範囲を明示する。

## 9.5 L3 Strategy／Entry検証

eligible全episodeを母集団にする。Trigger成立だけを母集団にしない。

必須集計:

```text
eligible_count
armed_count
enterable_count
no_trade_count_by_reason
expired_count
invalidated_pre_entry_count
entry_mode_count
time_to_first_favorable_move
time_to_first_adverse_move
MFE_distribution
MAE_distribution
follow_through_pass_rate
logical_invalidation_rate
late_entry_rate
opposite_strategy_resolution_rate
```

Strategyの最終採用では次も必要である。

```text
gross path outcome
execution-adjusted outcome
cost-adjusted expectancy
tail loss
drawdown path
outlier concentration
```

「勝った／負けた」だけではentry timingのどこが正しかったか分からない。一方、最終Strategyを
市場耐性ありと主張するのにcost-adjusted outcomeを見ないことも禁止する。

## 9.6 L4 Execution検証

EntryDecision時刻にpoint-in-timeで利用可能だったHFM quoteだけを使う。

必須metric:

- decision-to-quote age
- decision-to-request／request-to-ack／request-to-fill latency
- side別spread distribution
- basis distributionとregime drift
- requested size別fill／reject／slippage
- entry TTL超過率
- Strategy gross opportunityからexecution costを引いた残差
- Binance上はENTERABLEだがHFMでBLOCKされた比率と理由

Binance L2からHFM passive fillを生成したsimulationはL4の証拠として認めない。

## 9.7 L5 Shadow検証

realtime shadowは次を満たす。

- replayとlive shadowの同一eventに対するdecision一致
- restart前後でStrategyInstanceを重複生成しない
- no-trade／expiry／blockedを含む全episode記録
- paper positionとdecision traceの整合
- `execution_enabled: false`の外部request 0件
- version変更時に旧instanceと新instanceを混ぜない

## 9.8 splitとleakage防止

- 時系列順にdiscovery、calibration、validation、untouched holdoutを分ける。
- future horizonが重なるepisodeをtrainとtestへ跨がせない。
- overlapping label期間をpurgeし、必要なembargoをmanifestへ記録する。
- normalization、percentile、regime boundaryをcalibration以前のdataだけでfitする。
- holdoutを見た後の変更は、同じholdoutで再合格としない。

## 9.9 multiple testing

88項目×50 story×複数window×複数percentileを試すと、偶然の良好結果が出る。したがって:

- 試した全versionと不採用結果をtrial registryへ残す。
- best resultだけをreportしない。
- family単位でmultiple-testing correctionまたは同等の統制を事前指定する。
- sampleが足りる場合、walk-forward、blocked resampling、PBO／deflated metric等を使う。
- 複雑なmodelはsimple baselineを同じholdoutで超えることを要求する。

## 9.10 72時間と14日の位置づけ

- full 72時間はcollector、detector、初期distributionのseedであり、市場耐性の証明ではない。
- liquidation 14日／4,000受信recordはsampled snapshot coverageであり、完全清算母集団gateではない。
- 必要sample数はStrategy family、side、regime、entry mode別にmanifestで定める。
- gate未達は`INSUFFICIENT_SAMPLE`であり、手動thresholdで埋めない。

## 9.11 Validation Result enum

```text
PASS
PASS_RESTRICTED
FAIL_DEFINITION
FAIL_DETECTOR
FAIL_INCREMENTAL_VALUE
FAIL_ROBUSTNESS
FAIL_EXECUTION
INSUFFICIENT_SAMPLE
DATA_UNTRUSTED
REJECTED_OVERFIT_RISK
```

## 9.12 Validation Acceptance Test

1. manifest作成時刻がresult計算前である。
2. eligible non-trigger episodeを母集団から除外しない。
3. calibrationとholdoutのsource frameをhashで分離できる。
4. 全trial数を再計算できる。
5. L1合格だけでL3／L4を合格にしない。
6. restricted resultの適用外regimeでStrategyをARMできない。

---

# 10章 PDCAとVersion運用

## 10.1 変更単位

次のどれかが変わればversionを上げる。

```text
source semantics
feature formula
window
normalization population
Hook definition
EvidenceClause
Strategy eligibility
expected sequence
threshold
entry mode
invalidation
execution profile
position management
evaluation contract
```

同じversion名の中身を上書きしない。

## 10.2 Change Proposal schema

```yaml
change_id: uuid
object_id: string
from_version: string
to_candidate_version: string
problem_observed: string
affected_episode_ids: []
hypothesis_for_change: string
exact_changed_clauses: []
unchanged_clauses: []
expected_improvement_metrics: []
possible_regressions: []
new_validation_manifest_id: string
approval_state: DRAFT | APPROVED_RESEARCH | APPROVED_SHADOW | REJECTED
```

「成績が悪かったので調整」はchange hypothesisとして不十分である。どのfailure modeをどう直すかを
指定する。

## 10.3 candidate lifecycle

```text
DRAFT
  -> APPROVED_RESEARCH
  -> SHADOW_CANDIDATE
  -> VALIDATED
  -> APPROVED_OBSERVE
  -> ACTIVE_SHADOW

任意段階
  -> RESTRICTED
  -> REJECTED
  -> RETIRED
```

Stage 2Cで到達可能な上限は、別途ユーザー承認された`APPROVED_OBSERVE／ACTIVE_SHADOW`まで。
LIVEは別Stage・別承認とする。

## 10.4 Champion／Challenger

- active版をchampion、変更版をchallengerとして同じfrozen inputで実行する。
- 差分をdecision、reason code、entry price、invalidation、execution block単位で出す。
- challengerが改善したaggregateだけでpromotionしない。悪化したregimeとtailを同時に示す。
- promotion後も旧versionとrollback manifestを保持する。

## 10.5 Drift trigger

最低限次を監視し、limit超過で自動`REVALIDATION_REQUIRED`とする。

```text
source schema／cadence change
feature distribution shift
Strategy eligibility frequency shift
evidence effect direction change
follow-through pass rate shift
spread／basis／latency／slippage shift
no-trade reason distribution shift
data quality block frequency shift
```

drift limitはcalibration reportで定める。limit超過を自動threshold変更で隠さない。

## 10.6 Rollback

rollbackは次を一組で指定する。

```yaml
strategy_version: string
hook_versions: map
threshold_versions: map
state_builder_version: string
execution_profile_version: string
risk_profile_version: string
source_contract_version: string
```

一部versionだけ戻して未検証組合せを作らない。

## 10.7 append-only learning record

削除・上書きしてはならないもの:

- raw source frame
- original decision trace
- trial registry
- validation manifest／result
- rejected candidate
- promotion／restriction／retirement decision
- live／shadow episodeのoriginal outcome

誤り訂正は訂正recordを追加し、original recordを残す。

## 10.8 PDCA Acceptance Test

1. candidate変更前後のclause diffを出せる。
2. 全trialと不採用版を列挙できる。
3. champion／challengerを同一manifestで再生できる。
4. dependency変更時に影響Strategyを特定できる。
5. active版の無記録変更をhash監査で検出できる。
6. rollback bundleが過去にvalidatedなversion組合せと一致する。

---

# 11章 現行88 Hook／50 Triggerからの移行

## 11.1 削除せずcandidate inventoryとして凍結する

現行IDはtraceabilityのため残す。ただし意味とstatusを次のように扱う。

```text
legacy ID exists
  != observable claim is correct
  != detector is correct
  != evidence has market value
  != Strategy is valid
  != entry is executable
```

全88項目の`UNCALIBRATED`と発火禁止を維持する。

## 11.2 移行成果物

### 成果物A: Source Contract Matrix

88項目それぞれについて、source、aggregation、sampling、clock、blind spotを記録する。

### 成果物B: Role／Claim Audit

2章のroleとHookSpecを全件記入する。観測不能な定義は`UNOBSERVABLE_AS_DEFINED`にする。

### 成果物C: Dependency Graph

同じraw dataから派生するFeature群を示し、重複確認を防ぐ。

例:

```text
aggTrade
  -> buy/sell aggressive qty
  -> aggression ratio
  -> delta
  -> CVD
  -> Flow Price Response inputs
```

この群を五つの独立証拠として数えない。

### 成果物D: T01-T50 Story Audit

8.2のschemaでfamily、entry mode、欠落、観測不能claim、dispositionを全件記録する。

### 成果物E: First StrategySpec

最初から多数作らない。一つのfamily／side／entry modeを選び、4章から10章までをend-to-endで
満たす最小縦切りを作る。

## 11.3 最初の実装順

```text
1. Source Truth contractとquality propagation
2. 88項目Role／Claim Audit
3. MarketStateRecord
4. StrategySpec／StrategyInstance／ReasonTrace
5. 一つのStrategy familyと競合family
6. EntryDecision
7. HFM shadow ExecutionDecision
8. Position shadow lifecycle
9. L0-L5 validation harness
10. champion／challenger PDCA
```

Hook detectorを追加実装してからStrategyを考える順序へ戻らない。

## 11.4 現行Stage 2Cの差し替え案

| 新工程 | 実作業 | 完了条件 |
|---|---|---|
| 2C-0 | Source Truth監査 | source contract、sampling／aggregation伝播、HFM entity確認 |
| 2C-1 | 収録完了判定 | fullはinitial dataset、liquidationはsampled coverageとして報告 |
| 2C-2 | 88 role／claim監査 | 全件disposition、観測不能定義へthresholdなし |
| 2C-3 | Strategy constitution批准／StrategySpec | state machine、競合仮説、entry／exitを承認 |
| 2C-4 | Hook／Feature L1検証 | 独立referenceとerror report |
| 2C-5 | Evidence／Strategy L2-L3検証 | conditional baseline、holdout、entry path report |
| 2C-6 | HFM shadow execution L4 | basis／spread／latency／slippage／block report |
| 2C-7 | lifecycle shadow L5 | no-tradeを含むrealtime trace、外部注文0 |

各工程後にユーザー報告と次工程承認を行う。

---

# 12章 自動検査できる禁止事項

| ID | 禁止事項 | 自動検査 |
|---|---|---|
| CONST-001 | Hook単独からBUY／SELL entry | EntryDecisionにstrategy_instance_idがなければFAIL |
| CONST-002 | Context単独発火 | required evidenceにCONTEXTだけならFAIL |
| CONST-003 | 単純ANDだけのTrigger | sequence／age clauseが0ならFAIL |
| CONST-004 | quality blockの点数相殺 | quality BLOCK中のENTERABLE件数が1以上ならFAIL |
| CONST-005 | 観測不能Hookのthreshold | `UNOBSERVABLE_AS_DEFINED`にthresholdがあればFAIL |
| CONST-006 | future leakage | decision時刻後のevent ID参照があればFAIL |
| CONST-007 | same-version上書き | version内容hash変更でFAIL |
| CONST-008 | fire eventだけの検証 | eligible non-fire populationが0／未定義ならFAIL |
| CONST-009 | Hook精度とStrategy収益の混同 | validation level未分離ならFAIL |
| CONST-010 | Binance priceをHFM fillに代用 | HFM execution source IDなしのfillでFAIL |
| CONST-011 | `forceOrder`を全件tape扱い | sampled flag欠落または件数/秒claimでFAIL |
| CONST-012 | OIからparticipant sideを事実認定 | forbidden claim辞書一致でFAIL |
| CONST-013 | entry後にinvalidationを遠ざける | instance内の未承認invalidation変更でFAIL |
| CONST-014 | order requestだけでOPEN | fill／position照合なしOPENでFAIL |
| CONST-015 | Stage 2C外部注文 | `execution_enabled:false`中のrequestでFAIL |
| CONST-016 | raw／decision／trial削除 | append-only audit／hash chain不整合でFAIL |
| CONST-017 | holdout閲覧後の同holdout再調整 | manifest lineageとtrial時刻でFAIL |
| CONST-018 | protected機能変更 | Flow Price Response／3段チャート／8パターンhash差でFAIL |

Constitution test suiteは下位実装と独立して実行できなければならない。

---

# 13章 批准・優先順位・改訂

## 13.1 優先順位

Order Flow Strategy Method内の優先順位:

1. ユーザーの最新の明示指示
2. `PROJECT_MEMORY.md`に記録されたproject目的と保護済み成果
3. 批准後の本Constitution
4. approved ADR／Stage approval／Strategy specification
5. Hook／Feature／threshold／execution／risk profile
6. 実装

下位文書またはcodeが上位原則と矛盾する場合、上位を勝手に曲げず、矛盾をblockerとして記録する。

## 13.2 批准条件

本v0.2 draftは、次が終わるまで正本にしない。

- ユーザー本文レビュー
- 抽象表現、実装不能条文、矛盾の指摘反映
- 現行systemとのconformance gap一覧
- Constitution test IDの実装可能性確認
- ユーザーによる明示批准

## 13.3 改訂packet

改訂時は次を一つのpacketで提出する。

```yaml
amendment_id: string
affected_sections: []
old_text_or_rule: string
new_text_or_rule: string
reason: string
new_external_evidence: []
affected_specs_and_code: []
compatibility_impact: string
new_or_changed_constitution_tests: []
migration_plan: string
rollback_plan: string
user_approval: pending | approved | rejected
```

市場変化または新研究を理由に改訂できる。過去の記述を消さず、改訂履歴と根拠を残す。

## 13.4 緊急停止

次の場合、新規Strategy entryを停止できる。停止はLIVE権限拡張ではないため、system safety actionとして
常に許される。

- source semantics変更
- data integrity不明
- order status不明
- execution venue異常
- Strategy decisionとactual positionの不整合
- constitution test重大違反

再開には原因、影響期間、data validity、position reconciliation、修正version、検証結果を記録する。

---

# 14章 下位仕様の提出template

新しいStrategy specificationは最低限次の章を持つ。

```text
1. 対象family／side／entry mode
2. Source contractとblind spot
3. MarketState field
4. eligibility／location
5. approach sequence
6. required／supporting／contradicting／invalidating evidence
7. Strategy state transition
8. EntryDecisionとentry zone
9. HFM Execution Gate
10. Position／follow-through／exit
11. episode population
12. validation manifest／holdout
13. PDCA／drift／rollback
14. Constitution conformance table
15. ユーザーapproval gate
```

この15項目のどれかを「後で決める」としたStrategyをproduction candidateにしない。

---

# 15章 根拠資料

## 15.1 取引所・規制・execution

- [CME: Assessing Liquidity](https://www.cmegroup.com/education/articles-and-reports/assessing-liquidity)
- [CME: How Ag Markets Operate](https://www.cmegroup.com/education/articles-and-reports/overview-what-makes-ags-markets-work)
- [Nasdaq TotalView-ITCH 5.0](https://nasdaqtrader.com/content/technicalsupport/specifications/dataproducts/NQTVITCHSpecification.pdf)
- [SEC: Order Book Reporting Methods](https://www.sec.gov/data-research/statistics-data-visualizations/order-book-reporting-methods-their-impact-some-market-activity-measures)
- [Binance: How to Manage a Local Order Book](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/How-to-manage-a-local-order-book-correctly)
- [Binance Official Futures Connector](https://github.com/binance/binance-futures-connector-python/blob/main/binance/websocket/um_futures/websocket_client.py)
- [CFTC: OI Explanatory Notes](https://www.cftc.gov/MarketReports/CommitmentsofTraders/ExplanatoryNotes/index.htm)
- [CME: Spoofing](https://www.cmegroup.com/education/courses/market-regulation/disruptive-practices-prohibited/disruptive-practices-prohibited-spoofing.hideSubnav.educationIframe.html.html?hideAddThisExt=y&hideFooter=y&hideHeader=y&hideRightRail=y)
- [HFM 2026 Order Execution Policy](https://www.hfm.com/load_terms?file=ZA_HFZA%2F2026-01_HFSA_Order_Execution_Policy_2026-01.pdf)

## 15.2 Market microstructure／validation

- [Price Impact of Order Book Events](https://arxiv.org/abs/1011.6402)
- [Queue Imbalance as a One-Tick-Ahead Predictor](https://arxiv.org/abs/1512.03492)
- [Multi-Level Order-Flow Imbalance](https://arxiv.org/abs/1907.06230)
- [Queue-Reactive Model](https://arxiv.org/abs/1312.0563)
- [State-Dependent Fill Probabilities](https://arxiv.org/abs/2403.02572)
- [When Does Order Flow Matter?](https://arxiv.org/abs/2607.09230)
- [Effects of Backtest Overfitting](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2308659)
- [Where Is the Price of Bitcoin Determined?](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4983566)
- [Fundamentals of Perpetual Futures](https://arxiv.org/abs/2212.06888)

## 15.3 実トレーダーのentry process

以下は個別手法の収益証明ではなく、setup、location、approach、trigger、managementの実務順序を
確認する資料として使用した。

- [SMB: Stock Trading 101 — Setup and Trigger](https://www.smbtraining.com/blog/stock-trading)
- [Jigsaw: Reversal and Breakout Entry Timing](https://www.jigsawtrading.com/blog/jigsaw-trading-order-flow-trade-reversals-breakout-trade/)
- [Jigsaw: Trade Management Using Order Flow](https://www.jigsawtrading.com/blog/master-trade-management-using-order-flow/)
- [Axia: Why Day Trading Is Not Simple](https://axiafutures.com/blog/why-day-trading-not-simple-part-i/)
- [Axia: Stop Placement](https://axiafutures.com/blog/stop-placement-strategies-professional-traders-use/)

詳細な調査判断は`ORDER_FLOW_GLOBAL_RELEARNING_REPORT_20260726.md`に分離する。

---

# 批准欄

```text
document: ORDER_FLOW_STRATEGY_METHOD_CONSTITUTION_OPERATIONAL_DRAFT_V0_2_20260726
reviewed_by: お館様
decision: PENDING
approved_version: PENDING
approved_at: PENDING
conditions: PENDING
```

批准前は、本草案を理由にthreshold、HookEvent、Strategy runtime、execution設定を変更しない。
