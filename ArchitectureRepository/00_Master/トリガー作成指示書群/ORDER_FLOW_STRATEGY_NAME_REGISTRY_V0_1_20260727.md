# DeltaEngine Order Flow Strategy Name Registry v0.1

作成日: 2026-07-27 JST  
状態: **名称契約。観察FSM・遷移log・replay検証の識別子を定義する。production採用、threshold確定、発注許可ではない。**

## 0. 結論

状態は匿名で遷移させない。すべてのObservation Instanceを、安定した`strategy_family_id`と`pattern_id`へ所属させる。

```text
Hook
  -> named Strategy Family
       -> named Pattern
            -> Observation Instance
                 -> named State Transition
                      -> Order Trigger Trace
```

Strategy名はCondition名ではない。Conditionは観察材料、Strategy名はその材料をどの順序で観察しているかを示す検証単位である。

## 1. 識別子の階層

| 項目 | 役割 | 例 |
|---|---|---|
| `strategy_family_id` | 通称Strategyの不変machine ID | `STR-CVD-DIVERGENCE` |
| `strategy_family_name` | 人間が読む通称 | `CVD Divergence` |
| `pattern_id` | 方向・遷移経路まで特定した不変ID | `PAT-CVD-BEAR-ABSFAIL-BIDBREAK-OIUNWIND-001` |
| `pattern_name` | 具体的な観察経路名 | `CVD Divergence / Bearish / Absorption Failure / Buy-Wall Break / OI Unwind` |
| `strategy_version` | state graphとthreshold契約の版 | `0.1.0` |
| `observation_instance_id` | Hookから開始した一回の観察 | UUID等 |
| `state_id` | pattern内の状態名 | `S03_BUY_WALL_FAILURE_CONFIRMED` |

Family名だけでは遷移経路を識別できない。検証、勝率、誤発注調査は`pattern_id + strategy_version`単位で行う。

## 2. 初期Strategy Family台帳

ユーザーが示した通称を初期正本とする。

| family ID | 戦略名（通称） | 主な根拠 | 典型的に観察する変化 |
|---|---|---|---|
| `STR-CVD-DIVERGENCE` | **CVD Divergence** | 価格とCVDのダイバージェンス | 価格極値更新 -> CVD不追随 -> flow確認 -> 反転／継続分岐 |
| `STR-ABSORPTION-REVERSAL` | **Absorption Reversal** | 吸収後の反転 | aggressor継続 -> price停止 -> opposite aggression -> 反転 |
| `STR-EXHAUSTION-REVERSAL` | **Exhaustion Reversal** | 買い・売り枯れによる反転 | 極値接近 -> aggressor減衰 -> 再test失敗 -> 反対側参加 |
| `STR-STACKED-IMBALANCE-CONTINUATION` | **Stacked Imbalance Continuation** | スタックド・インバランスで順張り | stacked imbalance -> level保持 -> pullback拒否 -> 再加速 |
| `STR-ICEBERG-BREAKOUT` | **Iceberg Breakout** | アイスバーグ注文突破 | replenishment／吸収 -> hidden liquidity消耗 -> 突破 -> stop加速 |
| `STR-LIQUIDITY-SWEEP` | **Liquidity Sweep** | ストップ狩り後の反転 | stop zone接近 -> sweep -> follow-through欠如 -> range復帰 |
| `STR-FAILED-AUCTION` | **Failed Auction** | オークション失敗からの反転 | extreme試行 -> acceptance失敗 -> 旧value復帰 -> trapped flow |
| `STR-PULLING-STACKING` | **Pulling / Stacking Strategy** | 板のPulling・Stacking | support側pull／opposite側stack -> control shift -> price反応 |
| `STR-DELTA-FLIP` | **Delta Flip** | Deltaのプラス・マイナス転換 | 既存delta減衰 -> zero-cross／反転 -> price応答 -> opposite継続 |
| `STR-BOOK-IMBALANCE` | **Book Imbalance** | 板の偏り | queue偏り発生 -> 持続／増幅 -> 約定追随／吸収 -> 順張り・逆張り分岐 |

この10件はFamilyであって、具体的なPattern数は10件に限定されない。同じFamilyの下へ方向、location、確認経路、失敗分岐の異なるPatternを持たせる。

## 3. Pattern名の作り方

```text
<Family> / <Direction> / <Observation Path> / <Terminal Confirmation>
```

例:

| pattern ID | pattern名 |
|---|---|
| `PAT-CVD-BEAR-ABSFAIL-BIDBREAK-OIUNWIND-001` | `CVD Divergence / Bearish / Absorption Failure / Buy-Wall Break / OI Unwind` |
| `PAT-ABS-BULL-SELLFADE-BUYAGGR-001` | `Absorption Reversal / Bullish / Seller Fade / Buyer Aggression` |
| `PAT-STACK-BULL-RETESTHOLD-REACCEL-001` | `Stacked Imbalance Continuation / Bullish / Retest Hold / Re-acceleration` |
| `PAT-SWEEP-BEAR-HIGHRUN-SNAPBACK-001` | `Liquidity Sweep / Bearish / High Stop Run / Range Snapback` |
| `PAT-ICE-BULL-OFFERDEPLETE-STOPS-001` | `Iceberg Breakout / Bullish / Offer Depletion / Buy Stops` |
| `PAT-FA-BULL-LOWFAIL-VALUERETURN-001` | `Failed Auction / Bullish / Low Extension Failure / Value Return` |

`Strong`、`Good`、`A+`のように後から意味が変わる評価語はIDへ入れない。観測された現象だけで命名する。

## 4. ユーザー提示例の正式名称

### Family

- `strategy_family_id`: `STR-CVD-DIVERGENCE`
- `strategy_family_name`: `CVD Divergence`

### Pattern

- `pattern_id`: `PAT-CVD-BEAR-ABSFAIL-BIDBREAK-OIUNWIND-001`
- `pattern_name`: `CVD Divergence / Bearish / Absorption Failure / Buy-Wall Break / OI Unwind`

### State列

```text
S00_ARMED_BY_HOOK
  -> S01_BEARISH_CVD_DIVERGENCE_OBSERVED
  -> S02_BID_SIDE_ABSORPTION_OBSERVED
  -> S03_BUY_WALL_FAILURE_CONFIRMED
  -> S04_OI_UNWIND_CONFIRMED
  -> S05_SELL_TRIGGER_READY
```

この名称は経路を示す。`CVD Divergence`単独、`Absorption`単独、最終snapshotでの同時成立はこのPatternの成立を意味しない。

## 5. 遷移log契約

各state遷移は最低限、次をappend-onlyで残す。

```yaml
strategy_family_id: STR-CVD-DIVERGENCE
strategy_family_name: CVD Divergence
pattern_id: PAT-CVD-BEAR-ABSFAIL-BIDBREAK-OIUNWIND-001
pattern_name: CVD Divergence / Bearish / Absorption Failure / Buy-Wall Break / OI Unwind
strategy_version: 0.1.0
observation_instance_id: OBS-...
hook_event_id: HE-...
transition_id: TR-...
from_state: S02_BID_SIDE_ABSORPTION_OBSERVED
to_state: S03_BUY_WALL_FAILURE_CONFIRMED
transitioned_at: exchange_time
received_at: local_monotonic_time
evidence_event_ids: []
evidence_condition_ids: []
contradiction_event_ids: []
time_since_previous_state_ms: 0
state_deadline_at: exchange_time
observability: DIRECT | INFERRED | UNAVAILABLE
result: ADVANCED | BRANCHED | INVALIDATED | EXPIRED | ORDER_READY
reason_code: stable_machine_reason
```

Order Triggerは`pattern_id`、`strategy_version`、全`transition_id`を参照できなければならない。これにより、どのStrategyがどの経路を通って発注に至ったかをreplayで再現できる。

## 6. 運用規則

1. Hookは一つ以上のnamed Patternをarmできる。HookとStrategyは一対一にしない。
2. 一つのmarket eventが複数Patternを更新してよい。ただし同一Pattern内で同一eventを複数stateの成立に使う場合は明示契約が必要。
3. Family名は表示用でも、family IDとpattern IDは永続識別子である。production採用後は意味を上書きしない。
4. state追加、遷移順変更、timeout変更、terminal変更は`strategy_version`を上げる。
5. Patternは必ず`source_provenance`を持ち、`WORLD_SOURCE`、`DELTAENGINE_DERIVED_VARIANT`、`USER_DEFINED`を区別する。
6. Binanceで直接見えないnative iceberg／stop identityを`DIRECT`と記録しない。replenishment等から推定する場合は`INFERRED`とする。
7. `INVALIDATED`と`EXPIRED`もStrategyの結果であり、成功遷移だけを保存しない。
8. 成績検証はFamilyを合算する前に、`pattern_id + version + direction + market regime`別で行う。

## 7. 次工程

この名称台帳を主キーとして、世界資料から抽出した観察経路を各Family配下のnamed Patternへ登録する。Condition Dictionaryは各stateの観察材料として後から接続する。