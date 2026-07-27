# DeltaEngine Order Flow Strategy Method Constitution — Operational Draft

版: v0.3 draft  
起草日: 2026-07-26 JST  
改訂日: 2026-07-26 JST  
状態: **ユーザーGOを受けた構造修正版。未批准であり、較正・observe・LIVE発注の承認ではない。**  
適用範囲: Order Flow Strategy Engine、Hook、Trigger、entry、execution、position management、検証、PDCA  
変更理由: HookをStrategy素材そのものではなくStrategy Engineを起動する分散配置の罠として定義し、
多対多Strategy評価、条件充足、entry時機、発注枚数、保有中再評価を自動発注まで接続する。

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

### 0.3 自動発注システムとしての最上位定義

DeltaEngineは研究器、表示器、Hook収集器ではなく、注文フロー分析に基づく**自動発注システム**である。
分析、Hook、Strategy Engine、Execution Gate、Position Lifecycle、検証は、最終的に説明可能な
発注判断をHFMへ自動送信し、約定後まで管理するために存在する。

本書における最上位の語義を次で固定する。

- **Hook**: 注文フロー分析の各所へ分散配置し、定義した変化を捕捉した瞬間にStrategy Engineを
  呼び出す起動罠。Hook自体はStrategyでも最終発注条件でもない。
- **Strategy**: 多数の注文フロー要素、価格位置、順序、反証、執行条件を持つ条件集合。
  一つの固定形に限定せず、同じHookから複数Strategyを候補評価する。
- **Condition Fill**: Hook呼出し時点で、該当Strategyの各条件をpoint-in-time dataから
  `PASS／FAIL／UNKNOWN／STALE`へ更新した結果。
- **Satisfaction Tier**: hard gateを通過したCondition Fillの組合せから、Strategy別に説明可能な
  段階へ分類した充足水準。単一の不透明scoreへ畳み込まない。
- **Order Trigger**: Strategy EngineがCondition Fillを評価し、entry可否、方向、時機、枚数、
  注文方式を確定した最終発注条件。Hookとは別物である。

```text
注文フロー各所のHook
    -> Strategy Engineを起動
    -> Hookと関係する複数Strategyを抽出
    -> 各Strategyの条件を現在値で埋める
    -> hard reject／反証／充足水準を評価
    -> 見送り、監視継続、entry時機、発注枚数を決定
    -> Order Trigger
    -> HFM自動発注
    -> 保有中もHook発火ごとに追加／縮小／決済を再評価
```

HookとStrategyの関係は多対多である。一つのHookを一つのStrategyへ固定してはならず、
一つのStrategyも一つのHookだけで完成させてはならない。

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

## 2.3 Hook／Detector／HookEventの責任分離

- `Detector`はraw／derived inputを読み、罠の成立条件を計算する処理である。
- `HookSpec`はどの変化を罠として置き、成立時にどのStrategy群を再評価させるかの宣言である。
- `HookEvent`は、その罠へ実際に市場状態が引っかかった一回の起動記録である。
- `Strategy Engine`はHookEventをBUY／SELLへ直結せず、その時点のMarket Stateから複数Strategyの
  Condition Boardを更新する。

Hookは検出素材の一覧名ではなく、**Strategy Engine呼出し契約を持つ実行上の装置**である。
Observation、Feature、Context、Evidence CandidateはHookが監視する入力または更新対象であり、
Hookそのものと混同しない。

## 2.4 HookSpec必須field

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
dispatch_topics: []
candidate_strategy_ids: []
condition_keys_touched: []
recheck_open_positions: boolean
wake_priority: NORMAL | URGENT_RISK | EXECUTION_CRITICAL
reference_validator_version: string
status: UNREVIEWED | UNCALIBRATED | VALIDATED_FEATURE | RESTRICTED | REJECTED | RETIRED
```

`candidate_strategy_ids`は最適化のためのrouting hintであり排他的bindingではない。同じHookは複数Strategyを
起動でき、同じStrategyは複数Hookから再評価される。新しいStrategyを追加したとき、Hook detectorの
code変更なしにrouting tableを更新できなければならない。

HookSpecに`trade_direction: BUY/SELL`または`requested_size`を置いてはならない。方向、時機、枚数は
Strategy EngineのCondition FillとRisk／Execution policyから決定する。

## 2.5 Hook Dispatch Packet

```yaml
hook_event_id: uuid
hook_id: string
hook_version: semver
detected_at: timestamp
available_at: timestamp
market_state_id: string
changed_fields: []
condition_keys_touched: []
candidate_strategy_ids: []
open_position_ids_to_recheck: []
quality_flags: []
evidence_ids: []
```

Engineはpacket受信時に、routing hintだけでなく現在のMarket State、active Strategy Instance、
competing hypothesis、open positionを照合する。Hookが候補を列挙しなかったことを理由に、既にOPENな
positionのrisk再評価を省略してはならない。
## 2.6 三つの具体的な修正例

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

## 2.7 Hook Acceptance Test

1. raw replayとproduction detectorを別実装で照合できる。
2. false positive、false negative、side error、timing errorを別々に報告する。
3. fire windowだけでなくeligible non-fire windowを含める。
4. `known_blind_spots`がdecision packetへ伝播する。
5. `UNOBSERVABLE_AS_DEFINED`の項目へthresholdを設定できない。
6. Featureが正しく計算されたことと、Strategy edgeがあることを別statusで管理する。
7. 一つのHookEventから複数Strategy Instanceが評価されるtestを持つ。
8. 一つのStrategy Instanceが異なる複数Hookから順次更新されるtestを持つ。
9. HookEventだけからOrder Triggerまたはrequested sizeを生成できない。
10. OPEN positionへ`URGENT_RISK` Hookが入った場合、entry用Strategyとは別にposition再評価が走る。

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
direction_variant: LONG | SHORT | BOTH_WITH_SEPARATE_VALIDATION
observed_instrument: BINANCE_BTCUSDT_PERP
execution_instrument: HFM_BTCUSDr
holding_horizon: definition
hypothesis: falsifiable statement
activation_topics: []
activation_hook_hints: []
condition_board_version: string
eligibility_clauses: []
disqualifying_clauses: []
location_requirements: []
approach_sequence: []
required_evidence: []
supporting_evidence: []
contradicting_evidence: []
invalidation_clauses: []
expiry_clauses: []
satisfaction_tier_rules: []
entry_modes: []
timing_policy_version: string
size_policy_version: string
order_trigger_policy_version: string
follow_through_clauses: []
position_management_rules: []
post_entry_recheck_topics: []
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

## 4.1a Strategy Engine起動契約

Strategy Engineは常時全条件を無差別scanするのではなく、Hook Dispatch Packetをwake-upとして受ける。
ただしHook IDとStrategy IDを1対1に固定しない。

```text
HookEvent
  -> changed field／topicからcandidate Strategyを索引
  -> active／competing／OPEN positionを追加
  -> 同一market snapshotで評価batchを作る
  -> 各StrategyのCondition Boardを独立更新
  -> Order Trigger候補またはNO_TRADE／WATCH／MANAGEを返す
```

同じ`ABSORPTION_AT_BID` Hookは、locationと接近経路により`ABSORPTION_DEFENSE_LONG`、
`ABSORPTION_FAILURE_SHORT`、`PULLBACK_CONTINUATION_LONG`、`NO_TRADE`を同時評価できる。
Hookが「買い用」または「売り用」のStrategyを直接選んではならない。

## 4.1b Condition Board

各Strategyは、注文フロー分析に必要な要素を次の独立groupへ保持する。

```yaml
condition_board_id: uuid
strategy_instance_id: uuid
evaluated_at: timestamp
wake_hook_event_id: uuid
market_state_id: string
groups:
  quality: []
  environment: []
  location: []
  approach: []
  initiative_and_participation: []
  passive_response: []
  price_response: []
  confirmation: []
  contradiction: []
  invalidation: []
  execution_context: []
condition_results:
  condition_id:
    result: PASS | FAIL | UNKNOWN | STALE
    value: any
    threshold_version: string | null
    evidence_ids: []
    source_lineage: []
    evaluated_at: timestamp
independence_groups: map
```

同じraw dataから作った二つのFeatureを独立した二確認として数えない。`independence_groups`により
共通source／formula依存を追跡する。

## 4.1c 充足水準

充足水準は、全項目を一個の加重scoreへ潰さず、Strategy別の説明可能なtierとして定義する。

```text
DORMANT              location／eligibility未成立
WATCH                関係locationまたはenvironment成立
ARMED                approachを含む主条件が成立
ENTERABLE_BASE        最小独立条件群とentry timing成立
ENTERABLE_STANDARD    追加の独立確認とprice response成立
ENTERABLE_MAX_VALIDATED 事前検証済み最上位条件。risk capを超えない
NO_TRADE              contradiction／late／conflict
INVALIDATED           仮説破綻
DATA_BLOCKED          quality hard gate失敗
EXECUTION_BLOCKED     HFM条件不成立
```

各tierはStrategySpecで「どのcondition groupが必須か」「同group内で何が代替可能か」を明示する。
`UNKNOWN`を0点として埋めたり、supporting evidenceでhard rejectを相殺したりしない。

## 4.1d Strategy Evaluationと多対多結果

```yaml
strategy_evaluation_id: uuid
evaluation_batch_id: uuid
wake_hook_event_id: uuid
strategy_instance_id: uuid
strategy_id: string
strategy_version: semver
condition_board_id: uuid
previous_tier: enum
current_tier: enum
eligible_entry_modes: []
selected_entry_timing: NOW | WAIT_CONFIRMATION | WAIT_RETEST | TOO_LATE | NONE
selected_side: BUY | SELL | NONE
size_tier_candidate: ZERO | BASE | STANDARD | MAX_VALIDATED
contradiction_codes: []
invalidation_codes: []
reason_trace_id: uuid
output: WATCH | ORDER_INTENT | MANAGE_POSITION | NO_TRADE | INVALIDATE | BLOCK
```

一回のHook wake-upで評価した全candidateを同じ`evaluation_batch_id`へ残す。採用された一件だけを
保存して、競合Strategyや見送り理由を消してはならない。

## 4.1e 枚数決定

発注枚数はHookへ持たせず、Strategyの充足水準とrisk／execution条件から決定する。

```yaml
size_decision_id: uuid
strategy_evaluation_id: uuid
size_policy_version: string
satisfaction_tier: enum
validated_size_unit: number
stop_or_invalidation_distance: number
volatility_state: enum
existing_exposure: number
risk_budget_available: number
execution_size_cap: number
requested_size: number
cap_results: map
reason_codes: []
status: SIZE_READY | SIZE_REDUCED | SIZE_ZERO | BLOCKED
```

`requested_size`は最低でも次の全てを通す。

1. Strategy別にholdout検証されたsize tier mapping
2. logical invalidationまでの距離
3. 口座risk budgetと既存position
4. HFM contract specification、minimum／step／maximum size
5. size別spread／slippage／fill実績
6. 日次・連敗・相関position等のhard risk cap

contract specificationまたはrisk profile未確認時に仮の1 lotを入れず`BLOCKED`とする。充足水準は
枚数を増減する入力の一つだが、risk capを上書きしない。
## 4.2 StrategyInstance必須field

```yaml
strategy_instance_id: uuid
strategy_id: string
strategy_version: semver
created_at: timestamp
last_evaluated_at: timestamp
last_wake_hook_event_id: uuid
state: WATCH | ARMED | ENTERABLE | EXECUTION_PENDING | OPEN | MANAGING | CLOSED | NO_TRADE | INVALIDATED | EXPIRED | DATA_BLOCKED | EXECUTION_BLOCKED
satisfaction_tier: enum
condition_board_id: uuid
location_reference_id: string
market_state_ids: []
evidence_clause_results: map
evidence_event_ids: []
contradiction_clause_results: map
current_entry_mode_candidates: []
size_tier_candidate: ZERO | BASE | STANDARD | MAX_VALIDATED
pending_order_intent_id: uuid | null
open_position_id: string | null
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
7. 一つのHook wake-upで複数Strategy Evaluationを同一batchへ保存する。
8. 同じStrategyを異なるHook列から段階更新して同じCondition Boardへ到達できる。
9. Hook IDを変えずにrouting設定だけで新Strategy候補を追加できる。
10. Condition Fill、tier、timing、sizeの各決定をReason Traceへ逆引きできる。
11. condition数が多いだけでMAX_VALIDATEDにならない。
12. OPEN positionに対するrisk Hookをentry candidate不在でも再評価する。

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
order_trigger_id: uuid
strategy_evaluation_id: uuid
strategy_instance_id: uuid
strategy_version: semver
condition_board_id: uuid
satisfaction_tier: ENTERABLE_BASE | ENTERABLE_STANDARD | ENTERABLE_MAX_VALIDATED
trigger_mode: ANTICIPATORY | CONFIRMED | RETEST | PASSIVE | AGGRESSIVE
observed_side: LONG | SHORT
decision_exchange_ts: timestamp
decision_receive_ts: timestamp
location_reference: map
binance_reference_price: number
entry_zone_observed: map
required_clause_results: map
contradiction_results: map
size_decision_id: uuid
requested_size: number
size_reason_codes: []
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
1. 任意の関係HookがStrategy Engineを起動
2. 同じwake-upで関係する複数StrategyとOPEN positionを抽出
3. point-in-time Market Stateから全Condition Boardを更新
4. location／eligibility／approachによりDORMANT／WATCH／ARMEDを更新
5. required evidenceの順序・age・持続と独立性を評価
6. invalidation／disqualifier／data quality／競合Strategyを評価
7. 充足水準からentry可否とentry時機を決定
8. approved size policyからrequested sizeを数値確定
9. Order Trigger／EntryDecisionを作る
10. HFM Execution Gateへ渡す
11. HFM条件不良なら注文せずEXECUTION_BLOCKED
12. fill確認後だけOPEN
13. 保有中もHook wake-upごとにadd／reduce／exitを再評価
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
7. EntryDecisionの`requested_size`をSizeDecision、Condition Board、risk profileへ逆引きできる。
8. 同じHookEventからStrategy AはBASE、Strategy BはNO_TRADEとなるcaseを再生できる。
9. satisfaction tierが同じでもstop距離／既存exposure／execution capによりsizeが減るcaseを持つ。
10. size未決定または0のOrder Triggerを外部注文へ送らない。

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

## 7.8 保有中のHook再評価

Hookはentry前だけの装置ではない。OPEN／MANAGING positionに関係するHookEventは、元のStrategy
InstanceとPositionStateを再びStrategy Engineへ渡す。

最低recheck topic:

```text
EXPECTED_FOLLOW_THROUGH
PRICE_PROGRESS_CHANGE
AGGRESSION_CHANGE
ABSORPTION_OR_TRAP
REFERENCE_HOLD_OR_BREAK
CONTRADICTION
LOGICAL_INVALIDATION
EXECUTION_LIQUIDITY_CHANGE
TIME_EXPIRY
```

Engine出力は`HOLD／ADD／REDUCE／EXIT／REVERSE_CANDIDATE／DATA_RISK_ACTION`を区別する。
`ADD`は新しい独立evidenceと有利なexecution zoneを必要とし、単に含み益が出たことを根拠にしない。
`REVERSE_CANDIDATE`は現在positionのexitと反対side新規entryを二つのExecution Decisionへ分ける。

## 7.9 Position Re-evaluation Packet

```yaml
position_evaluation_id: uuid
position_id: string
strategy_instance_id: uuid
wake_hook_event_id: uuid
condition_board_id: uuid
previous_position_state: enum
updated_satisfaction_tier: enum
follow_through_results: map
contradiction_results: map
invalidation_results: map
action: HOLD | ADD | REDUCE | EXIT | REVERSE_CANDIDATE | BLOCK
size_decision_id: uuid | null
reason_trace_id: uuid
```
## 7.10 Position Acceptance Test

1. Trigger後ではなくfill確認後にPositionStateをOPENにする。
2. initial follow-through未達をreason codeとして出せる。
3. invalidation成立後に任意Hookで元Strategyを延命しない。
4. addごとにExecution Gateとrisk再計算を行う。
5. exit requestとexit fillを区別し、flatをbroker positionと照合する。
6. entryからexitまで一つのStrategy lineageを再生できる。

---

# 8章 何をStrategyにするか

ここがStrategy Engineの肝中の肝である。schemaが正しくても、載せるStrategyが相場現象を捉えず、
発注可否・時機・枚数を決められなければ自動発注システムは成立しない。

StrategyはHook名、指標名、単発signal、相場の物語名ではない。最低限、次を一体として持つ
**発注可能な市場仮説**である。

```text
狙うauction現象
+ 成立する場所／環境
+ そこまでの接近経路
+ 必要な注文フロー要素
+ 代替可能な確認要素
+ 反対証拠／hard reject
+ entry時機の分岐
+ 充足水準別の枚数
+ entry後に期待する反応
+ add／reduce／exit／reverse条件
```

## 8.1 Strategyにしてはいけないもの

次は単独ではStrategyではない。

- `ABSORPTION`、`SWEEP`、`LARGE_TRADE`等の単独Hook
- OI上昇、session、prior high、volatility等のContext
- `BUY_EFFECTIVE`、`SELL_TRAPPED`等の単一model state
- spread正常、quote fresh等のExecution Gate
- 「買いが強そう」「大口がいるはず」等の反証不能な物語
- 条件をANDで並べただけでentry時機、枚数、失敗、管理を持たない旧Trigger

## 8.2 世界実務資料との対応

- SMBの`Environment -> Play -> Setup checks -> Trigger -> Management`を、Hook wake-upごとの
  Condition Fillと最終Order Triggerへ変換する。
- Jigsawのreversal要素、同一locationで異なるbreakout／reversal、entry前後の確認を、
  代替条件と競合Strategyとして表す。
- Axiaのlocation、approach、participation、expected flow、add／exit判断を、充足水準、
  SizeDecision、Position Re-evaluationへ表す。

外部教育資料は収益性の証明ではなく、Strategyの構成漏れを防ぐ参考である。採否はDeltaEngineの
point-in-time data、holdout、HFM executionで判定する。

## 8.3 第一候補Strategy

最初に具体化して検証する候補は次の6系統とする。これは数を恒久固定する決定ではない。

| strategy family | 狙う現象 | 競合／反対Strategy | 初回優先 |
|---|---|---|---|
| BREAKOUT_ACCEPTANCE | 重要levelをinitiativeとacceptanceで抜ける継続auction | FAILED_AUCTION_RECLAIM | 1 |
| FAILED_AUCTION_RECLAIM | level外attemptが失敗し内側へ戻る反転 | BREAKOUT_ACCEPTANCE | 1 |
| ABSORPTION_DEFENSE | 重要levelで攻撃を受け止め反対responseへ移る | ABSORPTION_FAILURE | 1 |
| ABSORPTION_FAILURE | 維持されていた防衛が崩れ攻撃側へ継続する | ABSORPTION_DEFENSE | 1 |
| PULLBACK_CONTINUATION | 既存auction内のcounter-flowが失速し元方向を再開 | MOMENTUM_EXHAUSTION | 1 |
| MOMENTUM_EXHAUSTION | 伸び切ったauctionでaggressionのprice progressが失われ反転する | PULLBACK_CONTINUATION | 1 |

long／short、ANTICIPATORY／CONFIRMED／RETESTは別variantとして検証する。同じfamily名でも条件分布、
entry価格、HFM cost、failure modelが違うため、成績を無条件に合算しない。

各候補のactivation Hook、Condition Board、tier、entry timing、size、invalidation、position管理は
`ORDER_FLOW_STRATEGY_CANDIDATE_SET_V0_1_20260726.md`を正面設計書とする。

## 8.4 後順位またはStrategy外へ置くもの

| candidate | 扱い | 理由 |
|---|---|---|
| RANGE_ROTATION | 先にContext／eligibilityとして6Strategyへ使用 | failed auction／absorption defenseとの重複を監査してから独立化 |
| LIQUIDATION_CONDITIONED | Context限定、主Strategy保留 | `forceOrder`は1秒latest-one sampled snapshot |
| OI quadrant | Context | participant sideを直接確定できない |
| ICEBERG／SPOOF | suspected signature | Market-by-Priceで注文者・意図を観測不能 |
| HFM spread normal | Execution Gate | market hypothesisではない |

## 8.5 Strategy選定Gate

候補をStrategy Registryへ入れるには、次を全て回答する。

1. Hook発火時に何のStrategy条件を埋めるか。
2. 同じHookから同時に検討すべき反対Strategyは何か。
3. 独立した注文フロー要素は最低何群必要か。
4. どのcondition組合せで`BASE／STANDARD／MAX_VALIDATED`となるか。
5. 充足水準ごとに、入らない／待つ／今入る／retestを待つをどう分けるか。
6. 充足水準とrisk／executionから何枚にするか。
7. 何が起きれば即時見送り、失効、縮小、決済、反転候補となるか。
8. HookからOrder Triggerまでをfuture leakageなしで再生できるか。
9. 発火だけでなくeligible no-tradeを保存できるか。
10. HFMで実行可能性を別に検証できるか。

一つでも未回答なら`CANDIDATE_STORY`であり、Strategyではない。

## 8.6 現行50 storyの扱い

各T01-T50はStrategyとして採用せず、上記6系統へ素材を移す監査対象とする。

```yaml
legacy_trigger_id: Txx
activation_hook_candidates: []
condition_keys_reusable: []
candidate_strategy_ids: []
unobservable_claims: []
duplicate_evidence_dependencies: []
missing_timing_policy: boolean
missing_size_policy: boolean
missing_invalidation: boolean
missing_position_management: boolean
disposition: REWRITE | SPLIT | MERGE | CONTEXT_ONLY | RESTRICT | DEFER | REJECT
```

旧Trigger数50を維持することを目的にしない。同じ市場仮説ならmergeし、同じHookでも反対仮説なら
別Strategyへsplitする。

## 8.7 Strategy Acceptance Test

1. 一つのHookから最低二つの競合Strategyを評価できる代表testを持つ。
2. Strategyごとに必要なCondition Board、timing、size、invalidation、position管理が完結する。
3. 単発Hook、Context、Execution GateだけでStrategy InstanceをENTERABLEにしない。
4. long／short、entry mode、satisfaction tier、size tierを別集計できる。
5. requested sizeの根拠をStrategy conditionまで逆引きできる。
6. entry後のHookでHOLD／ADD／REDUCE／EXITが分岐する。
7. liquidation、OI、suspected signatureは観測限界を越えたclaimでVALIDATEDになれない。

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
3. Strategy Candidate Setのユーザー選定
4. Hook dispatch topicとmany-to-many routing contract
5. MarketStateRecord／Condition Board
6. 選定Strategyと競合Strategyのend-to-end Spec
7. Satisfaction／Timing／SizeDecision／Order Trigger
8. HFM shadow ExecutionDecision
9. Position shadow lifecycleと保有中Hook再評価
10. L0-L5 validation harness
11. champion／challenger PDCA
```

Hook detectorを追加実装してからStrategyを考える順序へ戻らない。

## 11.4 現行Stage 2Cの差し替え案

| 新工程 | 実作業 | 完了条件 |
|---|---|---|
| 2C-0 | Source Truth監査 | source contract、sampling／aggregation伝播、HFM entity確認 |
| 2C-1 | 収録完了判定 | fullはinitial dataset、liquidationはsampled coverageとして報告 |
| 2C-2 | 88 role／claim監査 | 全件disposition、観測不能定義へthresholdなし |
| 2C-3 | Strategy constitution批准／Candidate Set選定 | Hook起動、多対多評価、実Strategy、時機、枚数、管理を承認 |
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
| CONST-019 | HookがEngineを起動しない | HookEventにevaluation batchが無ければFAIL |
| CONST-020 | HookとStrategyの1対1固定 | routing cardinality／設定schemaが1対1限定ならFAIL |
| CONST-021 | Condition Fillなしの発注 | EntryDecisionにcondition_board_idがなければFAIL |
| CONST-022 | 枚数根拠欠落 | requested_sizeからSizeDecision／risk／executionへ逆引き不能ならFAIL |
| CONST-023 | 保有中Hook無視 | risk topic発火後にPosition EvaluationがなければFAIL |
| CONST-024 | Strategy内容未完成 | timing／size／invalidation／managementの一つでも未定義ならFAIL |
| CONST-025 | Hookから直接order_send | strategy_evaluation_idなしのorder requestでFAIL |

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

本v0.3 draftは、次が終わるまで正本にしない。

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
2. falsifiable market hypothesisと競合Strategy
3. Source contractとblind spot
4. activation Hook topicとmany-to-many routing
5. MarketState／Condition Board field
6. eligibility／location
7. approach sequence
8. required／alternative／supporting／contradicting／invalidating evidence
9. independence groupとCondition Fill
10. satisfaction tier mapping
11. entry timing policyとentry zone
12. size tier／数値requested size policy
13. Order Trigger／EntryDecision
14. HFM Execution Gate
15. Position／follow-through／add／reduce／exit／reverse
16. eligible no-tradeを含むepisode population
17. validation manifest／holdout
18. PDCA／drift／rollback
19. Constitution conformance table
20. ユーザーapproval gate
```

この20項目のどれかを「後で決める」としたStrategyをproduction candidateにしない。

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
- [Jigsaw: Anatomy of a Reversal](https://www.jigsawtrading.com/blog/elements-of-a-reversal/)
- [Jigsaw: Trade Management Using Order Flow](https://www.jigsawtrading.com/blog/master-trade-management-using-order-flow/)
- [Axia: Why Day Trading Is Not Simple](https://axiafutures.com/blog/why-day-trading-not-simple-part-i/)
- [Axia: Stop Placement](https://axiafutures.com/blog/stop-placement-strategies-professional-traders-use/)
- [Axia: Entry, Scaling and Exit](https://axiafutures.com/blog/breakout-trade-management-techniques/)

詳細な調査判断は`ORDER_FLOW_GLOBAL_RELEARNING_REPORT_20260726.md`に分離する。

---

# 批准欄

```text
document: ORDER_FLOW_STRATEGY_METHOD_CONSTITUTION_OPERATIONAL_DRAFT_V0_3_20260726
reviewed_by: お館様
decision: PENDING
approved_version: PENDING
approved_at: PENDING
conditions: PENDING
```

批准前は、本草案を理由にthreshold、HookEvent、Strategy runtime、execution設定を変更しない。
