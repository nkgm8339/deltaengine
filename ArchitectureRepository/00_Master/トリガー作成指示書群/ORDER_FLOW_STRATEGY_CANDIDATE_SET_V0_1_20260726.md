# DeltaEngine Order Flow Strategy Candidate Set v0.1

作成日: 2026-07-26 JST  
状態: **Strategy選定・具体化案。production採用、較正、observe解禁、LIVE発注の承認ではない。**  
目的: HookがStrategy Engineを起動した後、何をStrategyとして評価し、どの条件充足から
entry可否、時機、枚数、保有中判断を決めるかを具体化する。

## 0. 結論

第一候補は次の6系統とする。

1. `BREAKOUT_ACCEPTANCE`
2. `FAILED_AUCTION_RECLAIM`
3. `ABSORPTION_DEFENSE`
4. `ABSORPTION_FAILURE`
5. `PULLBACK_CONTINUATION`
6. `MOMENTUM_EXHAUSTION`

数を恒久固定する決定ではない。世界実務資料に共通し、DeltaEngineのprice、trade、DOM、
Flow Price Response、CVD／Delta、Footprint、Imbalance、Absorption、OI Contextでpoint-in-timeに
条件を埋められる初期集合である。

Strategyの優位性は未確認である。各Strategyは発注仮説としてL1-L5を通し、long／short、entry mode、
satisfaction tier、size tierを分離して検証する。

## 1. HookとStrategyの実行関係

```text
Hook = 注文フロー分析各所の起動罠

Hook発火
  -> Strategy Engine呼出し
  -> changed topicに関係する全Strategyを抽出
  -> competing StrategyとOPEN positionを追加
  -> 全Condition Boardを現在値で更新
  -> 充足水準を判定
  -> WATCH／NO_TRADE／ORDER_TRIGGER／MANAGE_POSITION
```

一つのHookが複数Strategyを起動し、一つのStrategyは複数Hookで段階的に埋まる。

例:

```text
Bid absorption-like Hook
  -> ABSORPTION_DEFENSE_LONG
  -> ABSORPTION_FAILURE_SHORT
  -> PULLBACK_CONTINUATION_LONG
  -> MOMENTUM_EXHAUSTION_LONG
  -> OPEN short positionのEXIT／REDUCE再評価
```

HookにBUY／SELL、entry枚数、最終Triggerを持たせない。

## 2. 共通Condition Board

全Strategyは最低限次のgroupを持つ。

| group | 問い |
|---|---|
| QUALITY | sourceは同期・fresh・point-in-timeか |
| ENVIRONMENT | volatility、session、spread等がStrategy適用範囲か |
| LOCATION | どのhigh／low／range／value／VWAP／auction objectiveか |
| APPROACH | 速さ、方向、aggression、trade rate、price progressはどう接近したか |
| INITIATIVE | aggressive側の量、継続、速度は変化したか |
| PASSIVE_RESPONSE | resting liquidityは維持、補充like、撤去、消費のどれか |
| PRICE_RESPONSE | flowに対して価格は進行、停滞、逆行のどれか |
| CONFIRMATION | 独立した別sourceの確認があるか |
| CONTRADICTION | 反対Strategyを支持する事実があるか |
| INVALIDATION | 元の市場仮説が破綻したか |
| EXECUTION | HFMで今その枚数を注文する価値があるか |
| POSITION | entry後に期待反応、追加、縮小、決済条件を満たすか |

同じraw inputから作ったFeatureを複数票として数えない。

## 3. 共通充足水準・時機・枚数

### 3.1 充足水準

| tier | 意味 | entry |
|---|---|---|
| DORMANT | location／eligibility外 | しない |
| WATCH | 関係locationまたは環境へ入った | しない |
| ARMED | approachと主条件が成立 | 原則待つ。ANTICIPATORY版は個別検証 |
| ENTERABLE_BASE | 最小独立条件群とdecision event成立 | BASE枚数候補 |
| ENTERABLE_STANDARD | BASE＋独立確認＋price response | STANDARD枚数候補 |
| ENTERABLE_MAX_VALIDATED | holdoutで別途有効性を確認した最上位条件 | MAX_VALIDATED候補 |
| NO_TRADE | contradiction、late、conflict | しない |
| INVALIDATED | 仮説破綻 | しない／保有中は決済評価 |
| BLOCKED | data、risk、execution不成立 | しない |

`MAX_VALIDATED`は初期状態では無効。検証なしに条件数が多いだけで最大枚数にしない。

### 3.2 数値枚数の決定

```text
risk_limited_size
  = floor_to_hfm_step(
      available_risk_budget
      / (logical_invalidation_distance * contract_value_per_price_unit
         + conservative_cost_per_unit)
    )

requested_size
  = min(
      satisfaction_tier_size_cap,
      risk_limited_size,
      existing_exposure_cap,
      execution_profile_size_cap,
      broker_contract_cap
    )
```

`logical_invalidation_distance`が0以下、非有限、未定義ならsize計算を行わず`BLOCKED`とする。

`BASE／STANDARD／MAX_VALIDATED`を実lotへ変換するtableは、Strategy variant、HFM contract spec、
size別slippage、account risk policyを版付きで持つ。いずれか不明なら`requested_size=0／BLOCKED`。

### 3.3 entry時機

- `ANTICIPATORY`: decision event前。Strategy別holdoutで承認されたvariantだけ。
- `CONFIRMED`: decision eventと必要response成立直後。
- `RETEST`: break／reclaim後の再testで条件維持を確認。
- `PASSIVE／AGGRESSIVE`: HFM fill可能性とremaining opportunityをExecution Gateで選ぶ。
- `TOO_LATE`: entry zoneまたはTTLを外れたら、後から条件が増えても追わない。

## 4. STRAT-01 BREAKOUT_ACCEPTANCE

### 仮説

重要referenceへinitiativeが増加して接近し、referenceを越えた後もprice progressとacceptanceが
維持されるなら、指定horizon内のauction continuationがeligible baselineより強い。

### 起動Hook topic

`REFERENCE_APPROACH`、`AGGRESSION_CHANGE`、`TRADE_RATE_CHANGE`、`PRICE_PROGRESS_CHANGE`、
`LEVEL_BREAK`、`RETEST`、`FLOW_STATE_CHANGE`、`CONTRADICTION`。

### Condition Board

| group | 条件 |
|---|---|
| LOCATION | prior high/low、range edge、value edge等の事前reference |
| APPROACH | breakout方向のinitiative／trade rate増加、price progress維持 |
| PASSIVE_RESPONSE | 反対側depthの消費／後退。単独wall pullは不可 |
| DECISION | reference外trade＋acceptance、またはretest hold |
| CONFIRMATION | 独立sourceの継続flow／CVD-Delta／Footprint response |
| CONTRADICTION | aggression継続なのにprogress停止、即reclaim、反対吸収 |
| INVALIDATION | reference内へ戻り指定時間acceptance、反対response成立 |

### Trigger、時機、枚数

- `CONFIRMED`: break後のacceptance成立でBASE候補。
- `RETEST`: reference holdと再initiative成立で別variantのBASE／STANDARD候補。
- `ANTICIPATORY`: Jigsaw型のbreak前momentum entry候補だが、初期は`RESEARCH_ONLY`。
- STANDARDは独立confirmationとexecution余地の両方が必要。
- MAX_VALIDATEDは無効から開始。

### 保有中

期待するのはbreak方向のprice progress、反対側depth消費、initiative継続。progress停止、flowだけ強く
価格が進まない、reference内reclaimではREDUCE／EXIT。再acceptanceと有利なretest時だけADD候補。

### 競合

`FAILED_AUCTION_RECLAIM`。同じreferenceと接近Hookを共有する。

## 5. STRAT-02 FAILED_AUCTION_RECLAIM

### 仮説

重要reference外へのattemptが十分なprice progress／acceptanceを作れず、reference内へreclaimし、
反対responseが成立するなら、失敗側position解消を伴う反対auctionが起きやすい。

### 起動Hook topic

`LEVEL_BREAK`、`PRICE_PROGRESS_FAILURE`、`FLOW_TRAPPED_OR_STALLED`、`REFERENCE_RECLAIM`、
`OPPOSITE_AGGRESSION`、`RETEST_FAILURE`。

### Condition Board

| group | 条件 |
|---|---|
| LOCATION | 事前定義reference外attempt |
| APPROACH | breakout期待を作るinitiativeまたはextension |
| FAILURE | aggressionに対するprogress低下／停滞／逆行 |
| DECISION | reference内reclaim |
| CONFIRMATION | 反対aggressionと反対price response、または外側retest失敗 |
| CONTRADICTION | reference外acceptance再成立 |
| INVALIDATION | failed extremeを越えたacceptance |

### Trigger、時機、枚数

- progress failureだけではentryしない。
- reclaim＋反対responseでCONFIRMED BASE候補。
- reclaim後の外側retest failureでSTANDARD候補。
- ANTICIPATORYは初期無効。

### 保有中

referenceから離れる反対progressを期待する。再び外側へacceptanceしたらEXIT。反対initiative継続と
有利なrotationでのみADD候補。

### 競合

`BREAKOUT_ACCEPTANCE`。

## 6. STRAT-03 ABSORPTION_DEFENSE

### 仮説

事前定義されたsupport／resistanceでaggressive attackが継続してもprice progressが低下し、
level維持／補充like／reclaimと反対responseが成立するなら、防衛側auctionへ移行しやすい。

### 起動Hook topic

`REFERENCE_TOUCH`、`AGGRESSIVE_ATTACK`、`ABSORPTION_LIKE`、`PRICE_PROGRESS_CHANGE`、
`LEVEL_HOLD_REPLENISH`、`OPPOSITE_RESPONSE`。

### Condition Board

| group | 条件 |
|---|---|
| LOCATION | support／resistance／value edge等。locationなしは禁止 |
| ATTACK | 一方向aggressionの量、速度、継続 |
| RESPONSE | attack量に対するprice progress低下 |
| PASSIVE_RESPONSE | level維持、再補充like、またはreclaim |
| CONFIRMATION | 反対aggression／上方または下方price migration |
| CONTRADICTION | level消費、through-trade、attack側progress再加速 |
| INVALIDATION | defended referenceを越えたacceptance |

### Trigger、時機、枚数

- absorption-like Hook単独では注文しない。
- opposite response成立でCONFIRMED BASE候補。
- second defense／reclaim hold＋独立confirmationでSTANDARD候補。
- MAX_VALIDATEDは無効から開始。

### 保有中

referenceから離れるprice responseを期限内に要求する。攻撃再加速、level消費、follow-through未達で
REDUCE／EXIT。防衛再確認だけで自動ADDせず、別の有利なentry zoneが必要。

### 競合

`ABSORPTION_FAILURE`。

## 7. STRAT-04 ABSORPTION_FAILURE

### 仮説

維持されていた防衛levelへ攻撃が反復し、補充力／保持力が低下してlevelが消費され、break後の
price progressが成立するなら、攻撃側auction continuationが起きやすい。

### 起動Hook topic

`REPEATED_ATTACK`、`DEFENSE_STRENGTH_CHANGE`、`DEPTH_WITHDRAWAL_OR_CONSUMPTION`、
`LEVEL_BREAK`、`THROUGH_TRADE`、`FAILED_RETEST`。

### Condition Board

| group | 条件 |
|---|---|
| LOCATION | 実際に防衛が観測されたreference |
| HISTORY | attack／defense episodeの反復とevent-time整合 |
| DETERIORATION | replenish低下、depth減少、price response悪化 |
| DECISION | level消費＋through-trade＋攻撃側progress |
| CONFIRMATION | break側acceptanceまたはfailed retest |
| CONTRADICTION | rapid replenish／reclaim／反対response |
| INVALIDATION | defended sideへ再acceptance |

### Trigger、時機、枚数

- wall pullまたはdepth減少単独ではentryしない。
- level消費＋price progressでCONFIRMED BASE候補。
- failed retestで別variantのSTANDARD候補。

### 保有中

break側progressを期待する。即reclaim、補充復活、攻撃側trappedでEXIT。continued initiativeと
新しい有利なreference形成時だけADD候補。

### 競合

`ABSORPTION_DEFENSE`。

## 8. STRAT-05 PULLBACK_CONTINUATION

### 仮説

確認済みの方向auction内でcounter-flow pullbackが重要referenceへ到達し、counter側のprogressが
低下して元方向initiativeが再開するなら、元auctionが継続しやすい。

### 起動Hook topic

`DIRECTIONAL_AUCTION_CONFIRMED`、`PULLBACK_START`、`COUNTER_FLOW_CHANGE`、`REFERENCE_TOUCH`、
`PULLBACK_STALL`、`INITIATIVE_RESUME`。

### Condition Board

| group | 条件 |
|---|---|
| ENVIRONMENT | 直前方向auctionが有効で、単なるrangeでない |
| LOCATION | breakout reference、value edge、VWAP、defended level等 |
| PULLBACK | counter-flowの速度、深さ、出来高、price progress |
| STALL | counter aggressionに対するprogress低下／停滞 |
| DECISION | 元方向initiativeとprice response再開 |
| CONFIRMATION | reference hold、CVD／Delta／Footprintの独立支持 |
| CONTRADICTION | pullbackが新しい反対auctionへ発展 |
| INVALIDATION | reference破壊＋反対acceptance |

### Trigger、時機、枚数

- pullback開始ではentryしない。
- initiative再開でCONFIRMED BASE候補。
- defended reference retestと継続responseでSTANDARD候補。
- 深すぎるpullbackまたはlate entryはNO_TRADE。

### 保有中

元方向progressを期待する。再失速、reference破壊、反対auction成立でREDUCE／EXIT。順方向rotationと
新reference形成があればADD候補。

### 競合

`MOMENTUM_EXHAUSTION`および反対side`BREAKOUT_ACCEPTANCE`。

## 9. STRAT-06 MOMENTUM_EXHAUSTION

### 仮説

extended moveまたはauction objective付近でaggressionが継続してもprice progressが低下し、
反対responseとreference reclaimが成立するなら、momentum側の解消を伴う反転が起きやすい。

### 起動Hook topic

`EXTENSION_LOCATION`、`AGGRESSION_PERSISTENCE`、`PRICE_PROGRESS_FAILURE`、`FLOW_TRAPPED_OR_STALLED`、
`OPPOSITE_RESPONSE`、`REFERENCE_RECLAIM`。

### Condition Board

| group | 条件 |
|---|---|
| LOCATION | extension、prior objective、value外、既知liquidity area等 |
| APPROACH | momentum側aggressionとprice progressの履歴 |
| EXHAUSTION | aggression継続に対するprogress低下。単なる出来高減だけでは不可 |
| DECISION | 反対responseまたはreference reclaim |
| CONFIRMATION | momentum側再test失敗、反対price migration |
| CONTRADICTION | initiative再加速と新価格acceptance |
| INVALIDATION | extreme更新＋acceptance |

### Trigger、時機、枚数

- divergence／trapped／stalled単独ではentryしない。
- opposite response＋reclaimでCONFIRMED BASE候補。
- failed retest＋独立confirmationでSTANDARD候補。
- major reversalとminor pullbackを同じ母集団へ混ぜない。

### 保有中

反対方向への初期follow-throughを短い期限で要求する。momentum再加速なら即EXIT。反対auctionの
acceptanceが進んだ場合だけADD候補。

### 競合

`PULLBACK_CONTINUATION`および元方向`BREAKOUT_ACCEPTANCE`。

## 10. Strategyにしない／後順位

| 対象 | 初期扱い |
|---|---|
| RANGE_ROTATION | LOCATION／ENVIRONMENT条件。6Strategyとの重複監査後に独立性を再評価 |
| Liquidation | sampled Context。主発火条件にしない |
| OI quadrant | Context／Feature。participant sideを事実認定しない |
| Iceberg／spoof | suspected signature。注文者・意図を断定しない |
| Session／volatility | ENVIRONMENT条件 |
| HFM spread／quote age | EXECUTION GATE |
| Flow state単独 | Condition Fill。単独発注禁止 |

## 11. 検証順序

1. 各Strategyのsource／conditionがpoint-in-timeに計算可能か確認。
2. Hookから全candidate Strategyが呼ばれるmany-to-many replay test。
3. Condition Fillのreference実装とdetector実装を独立照合。
4. eligible全episodeを保存し、fire、no-trade、late、invalidatedを分母に含める。
5. long／short、entry mode、tier別にL2-L3 holdout評価。
6. tier別sizeは最初0／shadowとし、HFM contract・risk・size別cost確認後に数値化。
7. HFM shadowで発注時機、requested size、spread、basis、slippageをL4評価。
8. entry後Hook再評価を含むL5 lifecycle shadow。
9. ユーザー承認後だけobserve／check／LIVEの次段階へ進む。

## 12. 根拠資料

- [SMB: Environment, Play, Setup, Trigger, Management](https://www.smbtraining.com/blog/stock-trading)
- [Jigsaw: Reversal and Breakout Entry Timing](https://www.jigsawtrading.com/blog/jigsaw-trading-order-flow-trade-reversals-breakout-trade/)
- [Jigsaw: Anatomy of a Reversal](https://www.jigsawtrading.com/blog/elements-of-a-reversal/)
- [Jigsaw: Trade Management Using Order Flow](https://www.jigsawtrading.com/blog/master-trade-management-using-order-flow/)
- [Axia: Trading Plan and Expected Path](https://axiafutures.com/blog/why-day-trading-not-simple-part-i/)
- [Axia: Breakout Participation and Failure](https://axiafutures.com/blog/two-breakout-strategies-for-futures-markets/)
- [Axia: Reversal and Continuation Scalping](https://axiafutures.com/blog/reversal-and-continuation-scalping-strategies/)
- [Axia: Entry, Scaling and Exit](https://axiafutures.com/blog/breakout-trade-management-techniques/)

これらはStrategy構造の参考であり、DeltaEngineでの収益性またはHFM実行可能性を証明しない。
