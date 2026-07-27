# Wall Distance Semantics Contract V0.1

作成日: 2026-07-27 JST  
状態: **お館様のA→D→E順次解決指示に基づくP3-C E契約**

## 1. 目的

G06の`wall_concentration_top10`と`distance_to_nearest_*_wall`が同じlevelを参照し、
名称、値、単位、欠測挙動を一意にする。G16のwall成立thresholdはここへ混ぜない。

## 2. Wall candidate

- sideごとにbest-firstへ並べた正数量levelの先頭10段を対象とする。
- top10内で表示数量が最大のlevelをthreshold-free `wall candidate`とする。
- 最大数量が同じlevelが複数ある場合、best priceに最も近いlevelを選ぶ。
- 全level同量の場合もnearest tie-breakでbest levelをcandidateとする。
- これはraw book shapeの代表levelであり、「実在する大口注文者」や売買優位を断定しない。

## 3. 算式

```text
wall_concentration_top10 = candidate quantity / top10 cumulative quantity
distance_ticks           = abs(best price - candidate price) / tick_size
```

- concentrationはDecimal ratio。
- distanceは非負のDecimal integer ticks。丸めない。
- price差がtick gridに一致しない場合、distance keyはomitする。
- concentrationとdistanceは必ず同じcandidate levelを使う。

## 4. Fail-closed

- bidまたはaskが空: bid／ask wall keyを全omit
- best bid >= best askのlocked／crossed book: 全wall keyをomit
- top10累積数量 <= 0: 当該side keyをomit
- tick size欠測／非正／off-grid: distanceだけomit
- gap／resync／future snapshot: D契約によりProducer側で除外
- stale／unsyncedはG01 quality conditionを通過させない

## 5. Stable ID / key

既存ID `CD-G06-029`〜`CD-G06-032`とkey名は維持する。正本定義へ
`top10 maximum-quantity wall candidate`とtie-break、ticks単位を明記し、
現行365 variant bindingを破壊するrenameは行わない。

## 6. 非対象

wall成立threshold、wall崩壊composite、G16、CalibrationBook、runtime有効化、発注権限、
raw data、完成済みFlow Price Response／3段チャート／8パターン／OI／UIは変更しない。
