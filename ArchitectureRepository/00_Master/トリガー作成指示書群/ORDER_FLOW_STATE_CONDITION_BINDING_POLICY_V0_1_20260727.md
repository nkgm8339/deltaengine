# DeltaEngine State-Condition Binding Policy v0.1

作成日: 2026-07-27 JST  
状態: **365 named variantsの全3,336 edgeをCondition材料へ接続する未較正policy。production未採用、発注許可ではない。**

## 0. 結論

StrategyはConditionの同時snapshotではない。各named Patternのstateごとに観察述語を持ち、
前state成立後に到着した新しいevidenceだけで次stateへ遷移する。

```text
Hook arm
  -> location predicate
  -> observation predicate 1
  -> observation predicate 2
  -> ...
  -> LONG_READY / SHORT_READY
  -> risk / execution gate
```

## 1. 台帳

- Predicate Class: 37件
- Observation Predicate: 236件
- Invalidation Predicate: 50件
- Predicate合計: 286件
- Variant State Binding: 3,336件

Binding内訳:

| edge type | 件数 |
|---|---:|
| LOCATION_ARM | 365 |
| ADVANCE | 1,876 |
| TERMINAL | 365 |
| INVALIDATE | 365 |
| EXPIRE | 365 |
| **合計** | **3,336** |

## 2. 判定契約

1. `LOCATION_ARM`はvariant固有のlocation Condition候補から、較正済みrouteを1つ以上満たす。
2. `ADVANCE`は列挙されたPredicate Classを満たす。使用evidenceは直前遷移より後でなければならない。
3. 同じ`source_event_id`を複数stateの成立証拠として再利用しない。
4. `condition_candidate_ids`は材料routeであり、全IDの同時PASSや独立加点を意味しない。
5. `contradiction_condition_ids`は同じ材料の逆comparatorを含み得る。IDだけで正負を決めない。
6. `INVALIDATE`はnamed guardのいずれかが成立した時点でObservation Instanceを終了する。
7. `EXPIRE`はversion付きdeadlineで終了し、Order Intentを出さない。
8. `TERMINAL`は`LONG_READY`／`SHORT_READY`をrisk／execution gateへ渡すだけで、直接注文しない。
9. hard sourceが`UNKNOWN / STALE`の場合の扱いはPatternごとに固定する。OI必須stateでは成立へ代用しない。

## 3. Side binding

- `EXPLICIT_BUY_OR_BID_COMPONENT`
- `EXPLICIT_SELL_OR_ASK_COMPONENT`
- `BOTH_EXPLICIT`
- `TERMINAL_SIDE`
- `OBSERVED_INITIATOR_SIDE`
- `DYNAMIC_FROM_PATTERN_CONTEXT`

`bid absorption`、`sell aggression`、`opposite flow`等をterminal方向だけから一律変換しない。
各stateの文言とPattern文脈からpassive side、aggressor side、terminal sideを分ける。

## 4. ユーザー例

`VAR-CVD-BEAR-ABSFAIL-BIDBREAK-OIUNWIND-SHORT-VISIBLE_BOOK_WALL-001`

| edge | state | Predicate Class | 主なCondition材料 |
|---|---|---|---|
| E00 | Visible Bid Wall context | LOCATION_CONTEXT | CD-G06-029, CD-G06-030 |
| E01 | bearish divergence | FLOW_PRICE_DIVERGENCE | CD-G16-048, CVD slope/change, price progress |
| E02 | bid-side absorption | ABSORPTION_STATE | CD-G16-001/002, no-progress ratio |
| E03 | buy wall崩壊 | BREAK_ATTEMPT + WALL_STATE | breakout attempt, wall concentration/pull/defense failure |
| E04 | fresh OI減少 | OPEN_INTEREST_CHANGE | CD-G12-001/002/003 + OI freshness |
| E90 | SHORT_READY | ENGINE_TERMINAL | market Conditionなし |
| E98 | wall再構築、price回復、OI不明/stale | COMPOSITE_INVALIDATION | wall/OI材料 |
| E99 | OI_LAGGED deadline | ENGINE_EXPIRY | monotonic engine time |

## 5. 制約

- 37 Class、286 Predicate、3,336 Bindingはすべて`UNVALIDATED`。
- comparator、threshold、window、timeoutは未較正。
- 24 ADVANCE bindingは`TEMPORAL_SEQUENCE`のみで、市場Conditionを持たない。これはpauseや別event確認を
  engine time／event orderingで判定するためで、欠落ではない。
- `EVENT_REACTION`を含む4 bindingは`EXT_CALENDAR_REQUIRED`。
- native MBOがないiceberg関連は`INFERRED_MBP_REQUIRED`。
- OIは10秒poll制約のため高速stateへ流用しない。
- 完成済みFlow Price Response、3段チャート、8パターン、OI、UI、runtime、raw dataは変更しない。

## 6. 機械可読正本

- `ORDER_FLOW_OBSERVATION_PREDICATE_CLASS_REGISTRY_V0_1_20260727.csv`
- `ORDER_FLOW_OBSERVATION_PREDICATE_REGISTRY_V0_1_20260727.csv`
- `ORDER_FLOW_VARIANT_STATE_CONDITION_BINDINGS_V0_1_20260727.csv`

次は既存88 Hookを、検出名の類似ではなく、各variantの最初の観察に必要なsource family、
location、direction hint、availabilityへ接続し、arm／update／expire責任を定義する。
