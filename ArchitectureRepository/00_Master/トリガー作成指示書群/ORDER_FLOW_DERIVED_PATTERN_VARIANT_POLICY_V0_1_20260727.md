# DeltaEngine Derived Named Pattern Variant Policy v0.1

作成日: 2026-07-27 JST  
状態: **50 source-grounded原型を365 named variantsへ展開するpolicy。未較正、未replay検証、production未採用、発注許可ではない。**

## 0. 結論

世界由来の50 Patternを、何でも直積して件数を増やしてはいけない。各原型について、意味が成立する方向とlocationだけを許可し、confirmation順序は原型から変えない。

```text
source-grounded base Pattern
  + allowed terminal direction
  + allowed location context
  + canonical confirmation path only
  = DeltaEngine derived named variant
```

結果は**365 variants**である。これは365個の世界通称を発見したという意味ではない。49 WORLD_DERIVED原型と1 USER_DEFINED原型を、DeltaEngineで検証可能な方向・locationへ束縛した候補である。

## 1. 件数

| Strategy Family | variants |
|---|---:|
| CVD Divergence | 41 |
| Absorption Reversal | 44 |
| Exhaustion Reversal | 48 |
| Stacked Imbalance Continuation | 32 |
| Iceberg Breakout | 32 |
| Liquidity Sweep | 35 |
| Failed Auction | 42 |
| Pulling / Stacking Strategy | 24 |
| Delta Flip | 27 |
| Book Imbalance | 40 |
| **合計** | **365** |

方向内訳はLONG 187、SHORT 178。50原型すべてをcoverageする。

## 2. Direction policy

- source／原型が方向を固定するPatternは反対方向へmirrorしない。
- `Support Hold`、`Seller Fade`、`Hidden Accumulation`、`Low Sweep`等はLONGのみ。
- `Resistance Hold`、`Buyer Fade`、`Hidden Distribution`、`High Sweep`等はSHORTのみ。
- `reversal-side`、`break direction`、`opposite-side`のようにsourceが対称構造を示すPatternだけLONG／SHORTへ展開する。
- ユーザー例`PAT-CVD-BEAR-ABSFAIL-BIDBREAK-OIUNWIND-001`はSHORTのみ。

## 3. Location universe

使用するlocationは、560 Condition Dictionaryに実在する材料へ限定した。

| location code | LONG reversal／retest側 | SHORT reversal／retest側 | breakout barrier側 | Condition材料 |
|---|---|---|---|---|
| `SESSION_EXTREME` | Session Low | Session High | LONG=High、SHORT=Low | `CD-G03-011`〜`014` |
| `PREVIOUS_DAY_EXTREME` | Previous Day Low | Previous Day High | LONG=High、SHORT=Low | `CD-G03-015`〜`018` |
| `ROLLING_5M_EXTREME` | Rolling 5m Low | Rolling 5m High | LONG=High、SHORT=Low | `CD-G03-025`〜`028` |
| `VALUE_AREA_EDGE` | VAL | VAH | LONG=VAH、SHORT=VAL | `CD-G03-043`〜`046`、`CD-G11-003`〜`006` |
| `PROFILE_HVN` | nearest HVN | nearest HVN | nearest HVN | `CD-G11-007`、`008` |
| `PROFILE_LVN` | nearest LVN | nearest LVN | nearest LVN | `CD-G11-009`、`010` |
| `VISIBLE_BOOK_WALL` | Bid Wall | Ask Wall | LONG=Ask Wall、SHORT=Bid Wall | `CD-G06-029`〜`032` |
| `BEST_BID_ASK` | Best Bid | Best Ask | LONG=Best Ask、SHORT=Best Bid | `CD-G03-001`〜`004` |
| `POST_EVENT_BALANCE` | direction neutral | direction neutral | direction neutral | `CD-G02-014`、`015` |

`active range boundary`や`round number`は現辞書に専用location材料がないため、名前だけ作ってvariantへ入れていない。

世界側のlocation根拠:

- [ATAS Footprint](https://atas.net/blog/how-to-trade-profitably-using-footprint-charts/)はprevious day high／low、VAH／VAL、support／resistance、local extremeでの確認を挙げる。
- [ATAS Imbalance](https://atas.net/blog/how-to-find-and-trade-imbalance/)はday high／low、support／resistance、VA／POCでのreversalを扱う。
- [Jigsaw](https://www.jigsawtrading.com/blog/jigsaw-trading-order-flow-trade-reversals-breakout-trade/)は同じhigh／low locationでもorder-flowの展開によりreversalとbreakoutが分かれることを示す。
- [Bookmap](https://bookmap.com/en/blog/stops-and-icebergs-how-to-detect-hidden-orders-using-mbo-data)はprior resistance、iceberg level、liquidity zoneでのfakeout／breakoutを扱う。

## 4. Location orientation

同じLONGでも、reversalとbreakoutでは観察する側が反対になる。

- `REVERSAL_EDGE`: LONGはlow／bid／VAL、SHORTはhigh／ask／VAH。
- `WITH_TREND_RETEST`: LONGはsupport側、SHORTはresistance側。
- `BREAKOUT_BARRIER`: LONGはhigh／ask／VAH、SHORTはlow／bid／VAL。

これを分けずに「LONGだからbid側」と一律変換するとIceberg Breakout等を逆にするため、各base Patternへorientationを固定した。

## 5. Confirmation policy

本版は全variantで`BASE_CANONICAL_ONLY`とする。

- 原型が`Absorption -> Fade -> Opposite Aggression`なら、その順序を維持する。
- 原型が`Break -> Retest Hold -> Acceptance`なら、その順序を維持する。
- `opposite aggression`、`structure break`、`retest`、`value migration`を自由に足し引きして別Patternを作らない。
- sourceまたはreplay evidenceが別経路を支持した時だけ、新しいbase PatternとしてIDを発行する。

したがって365件はlocationと方向が明示された観察候補であり、confirmationの無根拠な組合せ水増しではない。

## 6. Variant identity

```text
VAR-<base pattern stem>-<LONG|SHORT>-<LOCATION>-001
```

例:

```text
VAR-CVD-BEAR-ABSFAIL-BIDBREAK-OIUNWIND-SHORT-VISIBLE_BOOK_WALL-001
```

完全名:

```text
CVD Divergence / Bearish / Absorption Failure / Buy-Wall Break / OI Unwind
/ SHORT / Visible Bid Wall
```

観察順序:

```text
Hook arm
  -> Visible Bid Wall context confirmed
  -> bearish divergence
  -> bid-side absorption
  -> buy wall failure
  -> fresh OI decrease
  -> SHORT_READY
```

## 7. Variant FSM

365 variantsを計3,336 edgeへ展開した。

| edge type | 件数 |
|---|---:|
| `LOCATION_ARM` | 365 |
| `ADVANCE` | 1,876 |
| `TERMINAL` | 365 |
| `INVALIDATE` | 365 |
| `EXPIRE` | 365 |
| **合計** | **3,336** |

各variantは一意な`variant_id`を持ち、base Pattern、source、direction、location、Condition材料候補を保持する。terminalは`LONG_READY`／`SHORT_READY`であり、直接注文ではない。

## 8. 制約

- 365件すべて`UNVALIDATED`。件数は優位性を意味しない。
- `POST_EVENT_BALANCE`の4件は`EXT_CALENDAR_REQUIRED`であり、calendar未接続中はarm不可。
- `INFERRED` iceberg／stop PatternはBinance MBPから注文者identityを断定しない。
- location Condition IDは材料候補であり、全候補の同時PASSを要求するという意味ではない。
- threshold、timeout、枚数、execution gateは未較正。
- completed Flow Price Response、3段チャート、8パターン、OI、UI、runtimeは変更しない。

## 9. 機械可読正本

- `ORDER_FLOW_DERIVED_NAMED_PATTERN_VARIANTS_V0_1_20260727.csv`
- `ORDER_FLOW_DERIVED_NAMED_PATTERN_VARIANT_FSM_V0_1_20260727.csv`

次は各variant stateへCondition材料を`required / contradiction / invalidation`として接続し、Hookがどのvariantをarm／update／expireするかを定義する。