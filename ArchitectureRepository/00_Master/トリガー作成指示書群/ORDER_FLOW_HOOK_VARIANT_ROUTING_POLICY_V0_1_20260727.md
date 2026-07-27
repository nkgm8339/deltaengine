# DeltaEngine Hook-to-Variant Routing Policy v0.1

作成日: 2026-07-27 JST  
状態: **既存88 Hookを365 named variantsへ多対多接続するdesign routing。全route無効、未較正、production未採用、発注許可ではない。**

## 0. Hookの責任

HookはStrategyそのものでも、state成立の断定でも、Order Triggerでもない。
関連sourceが変化したためStrategy Engineを呼び、該当variantのCondition FillとObservation Instanceを
開始・更新・無効化・期限確認させる装置である。

```text
Hook event
  -> affected Predicateを持つvariant候補をwake
  -> Engineがfresh Conditionをfill
  -> current stateだけを評価
  -> advance / stay / invalidate / expire
  -> terminalならOrder Intent候補
```

## 1. asserted eventとrefresh capability

各Hookには2種類のClassを持たせる。

- `asserted_event_classes`: Hookが直接示すeventの種類。
- `capability_predicate_classes`: そのHookでraw／derived sourceが更新され、Engineが再評価できるPredicate。

例として`buy_delta_spike`は`DELTA_STATE`を直接示すが、その更新により
`FLOW_PRICE_DIVERGENCE`、`ABSORPTION_STATE`、`PRICE_STALL`等も再評価できる。
Hookが`FLOW_PRICE_DIVERGENCE`を断定したという意味ではない。

## 2. route role

- `LOCATION_ARM_CANDIDATE`: variant固有locationの再確認候補。
- `FIRST_STATE_WAKE`: first observation predicateを再評価できる。
- `ACTIVE_INSTANCE_UPDATE`: active instanceの途中stateを再評価できる。
- `INVALIDATION_RECHECK`: named invalidation guardを再評価できる。
- `CONTEXT_REFRESH_ONLY`: context更新のみ。hard stateを単独advanceしない。
- `ACTIVE_INSTANCE_RECHECK`: context-only Hookによる既存instance再確認。
- `GLOBAL_CONTEXT_REFRESH_ONLY`: session／volatility／liquidity／HFM contextを全variantへ更新。

routeは評価候補であり、Hook発火だけでObservation Instanceを必ず作る意味ではない。
`location + first predicate + freshness`を満たした時だけarmする。

## 3. 件数

- Hook capability: 88件
- routed Hook: 84件
- named variant: 365件すべてcoverage
- design route: 25,664件
- 1 Hookあたりroute: 63〜365件
- 1 variantあたりeligible Hook: 33〜82件
- runtime enabled: 0
- direct order authority: 0

route role件数:

| role | 件数 |
|---|---:|
| LOCATION_ARM_CANDIDATE | 983 |
| FIRST_STATE_WAKE | 6,386 |
| ACTIVE_INSTANCE_UPDATE | 19,987 |
| INVALIDATION_RECHECK | 11,161 |
| CONTEXT_REFRESH_ONLY | 3,800 |
| ACTIVE_INSTANCE_RECHECK | 3,686 |
| GLOBAL_CONTEXT_REFRESH_ONLY | 1,460 |

1 routeは複数roleを持てるため合計はroute総数と一致しない。

## 4. direction hint

既存Hookの`UP / DOWN / BOTH / NONE`はrouting metadataとして保持するが、
terminal方向のhard filterにはしない。

買いaggressionはLONG continuationだけでなくSHORT exhaustion／absorption reversalもwakeし得る。
direction hintで反対側variantを切ると、reversal Patternを消してしまうためである。

## 5. context-only制約

- `SUSPECTED_CONTEXT_ONLY`はhard stateを単独advanceしない。
- liquidation／OI等の`CONTEXT_REFRESH`はactive instance再確認に使うが、直接armしない。
- H category 4 Hookは365 variantすべてへglobal contextをrefreshするだけである。
- `REGISTERED_UNIMPLEMENTED` Hookのrouteも設計台帳には残すが、runtimeは無効。

## 6. routeのない4 Hook

| Hook | 理由 |
|---|---|
| G07 `vwap_touch` | 現365 variantにVWAP locationがない |
| G08 `vwap_deviation_extreme` | 現365 variantにVWAP locationがない |
| G10 `round_number_touch` | Condition Dictionaryにround-number referenceがない |
| G11 `range_edge` | 現365 variantにactive-range-edge locationがない |

名前だけでrouteを作らず、専用Condition／variant location追加後に接続する。

## 7. ユーザー例

`VAR-CVD-BEAR-ABSFAIL-BIDBREAK-OIUNWIND-SHORT-VISIBLE_BOOK_WALL-001`には、
78 design routeがある。

- first-state CVD divergenceを再評価できるHook: 28
- Visible Book Wall location arm候補: 9
- active state update／recheck候補: 74
- invalidation recheck候補: 38
- global context refresh: 4

これは1 eventで78個の注文判定を同時成立させる意味ではない。Engineが現在stateとsource dependencyにより
候補を絞り、所定順序を通った1 Observation Instanceだけを進める。

## 8. 機械可読正本

- `ORDER_FLOW_HOOK_PREDICATE_CAPABILITY_REGISTRY_V0_1_20260727.csv`
- `ORDER_FLOW_HOOK_VARIANT_OBSERVATION_ROUTING_V0_1_20260727.csv`

次はreplay契約を作り、順序逆転、同一event再利用、timeout、途中反証、
context-onlyによるhard advance、Hookからの直接注文を拒否する。
