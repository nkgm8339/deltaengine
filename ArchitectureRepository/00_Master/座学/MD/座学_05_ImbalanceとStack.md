# DeltaEngine座学 第5講 — ImbalanceとStack

作成日: 2026-07-21  
対象: FootprintのBUY/SELL数量を理解した人  
テーマ: 隣り合う価格で、積極売買の偏りを比較する

---

## この講義のゴール

1. Imbalanceが単純な同一価格比較ではないと説明できる
2. Buy ImbalanceとSell Imbalanceの式を読める
3. ratio threshold、min volume、ratio capの役割が分かる
4. Stacked Imbalanceの意味を説明できる
5. Imbalanceを単独の売買命令にしない理由が分かる

最も大切な一文はこれ。

> **Imbalanceは、隣接価格を斜めに比べ、成行圧力の局所的な偏りを見つける。**

---

## 1. なぜ斜めに比較するのか

市場では、買い成行はAskへ、売り成行はBidへぶつかる。

Footprint上で買いと売りの攻撃性を比べるとき、同じ価格の左右だけでなく、
隣接する反対側を斜めに比較する。

DeltaEngineの式:

```text
Buy Imbalance @ P
= BuyVol(P) / SellVol(Pの一つ下の価格レベル)

Sell Imbalance @ P
= SellVol(P) / BuyVol(Pの一つ上の価格レベル)
```

ここで「一つ上・一つ下」は、Footprintの価格昇順配列で隣にあるレベルを意味する。

---

## 2. Buy Imbalanceの例

| 価格 | BUY | SELL |
|---:|---:|---:|
| 100.2 | 12 | 2 |
| 100.1 | 3 | 4 |

100.2のBuy Imbalanceを調べる。

```text
12 / 4 = 3.0
```

現在のratio thresholdは3.0なので、他の条件も満たせばBuy Imbalanceになる。

注意: 100.2のSELL 2ではなく、一つ下の100.1のSELL 4と比べる。

---

## 3. Sell Imbalanceの例

| 価格 | BUY | SELL |
|---:|---:|---:|
| 100.2 | 2 | 1 |
| 100.1 | 3 | 15 |

100.1のSell Imbalanceを調べる。

```text
15 / 2 = 7.5
```

100.1のSELLを、一つ上の100.2のBUYと比べる。
比率7.5は閾値3.0以上なので、出来高条件を満たせばSell Imbalanceになる。

---

## 4. 3つの安全弁

### ratio threshold

現在値は3.0。
分子が分母の3倍以上かを確認する。

### min volume

現在の設定下限は0.002。
比較対象の数量が小さすぎる組を除外し、薄い場所の偶然を抑える。

校正済みの出来高基準がそれより大きければ、実効下限は引き上げられる。

### ratio cap

現在値は10.0。
分母が0のとき、無限大として扱わず上限値10.0を使う。

ただし分子そのものがmin volume未満なら、分母0でも採用しない。
「0.0001対0」を強い偏りとして数えないためである。

---

## 5. Stacked Imbalanceとは何か

一つの価格だけでなく、Imbalanceが連続した価格レベルに現れることをStackという。

現在のstack countは3。

```text
100.3 Buy Imbalance
100.2 Buy Imbalance
100.1 Buy Imbalance
```

3段連続ならBUY方向のStacked Imbalanceとして記録される。

単発より、複数価格で同方向の成行圧力が観測されたことを示す。
しかし、それでも価格がその方向へ進んだとは限らない。

---

## 6. Imbalanceと価格反応

### 順行

```text
BUY Stack
価格上昇
CVD上昇
```

積極買いが複数価格で優勢で、価格も上がった。
圧力が有効だった可能性を観察する。

### 停滞

```text
BUY Stack
価格ほぼ横ばい
```

買い成行の偏りがあるのに、価格が進まない。
売り指値の吸収や補充を疑い、Absorptionと板を確認する。

### 逆行

```text
BUY Stack
価格下落
```

強い買い成行の局所偏りがあるのに価格が下がる。
買い手が捕まった可能性はあるが、位置とその後の推移を記録する。

---

## 7. 単発と連続を分ける

単発Imbalanceは、その価格だけの局所現象かもしれない。

Stacked Imbalanceは、複数の連続価格に偏りが広がっている。

さらに時間方向も見る。

```text
価格方向の連続 = 同じバー内で複数価格にStack
時間方向の連続 = 次のバーでも同方向の偏りが続く
```

この二つを混同しない。

---

## 8. 画面での読む順番

1. 価格足の方向を確認
2. Footprintの元数量を確認
3. BUY/SELLどちらのImbalanceか確認
4. 単発かStackか確認
5. 価格は圧力側へ進んだか確認
6. CVDとDeltaを確認
7. Absorptionの有無を確認
8. Flow Responseの状態と時間窓を確認

Imbalanceは5指標の一つであり、他の指標へ勝手に合成しない。

---

## 9. よくある誤読

### BUY Imbalanceが出たから買う

誤り。買い成行が局所的に強かったという観測である。

### 比率が大きいほど必ず強い

誤り。分母が非常に小さいだけかもしれない。元数量とmin volumeを見る。

### ratio 10は実測で必ず10倍

誤り。分母0のケースはratio capによって10と表示され得る。

### Stackがあれば価格は抜ける

誤り。強いStackが吸収され、停滞または逆行することも重要な観測対象である。

### ImbalanceとDeltaは同じ

誤り。Deltaはバー全体の差、Imbalanceは価格レベル間の局所比較である。

---

## 10. 観察記録テンプレート

```text
バー時刻:
BUY Imbalance数:
SELL Imbalance数:
BUY Stack範囲:
SELL Stack範囲:
各Stackの段数:
元のFootprint数量:
価格反応:
CVD:
Delta:
Absorption:
Flow状態・時間窓:
その後:
```

---

## 11. 確認問題

1. Buy Imbalance @Pの分母はどこの数量か。
2. 比率条件だけでなくmin volumeが必要なのはなぜか。
3. 分母0のとき、DeltaEngineはいくつを上限として報告するか。
4. Stacked Imbalanceは何の連続か。
5. BUY Stackと価格停滞が同時に出たら何を追加確認するか。

---

## 12. 解答

1. Pの一つ下の価格レベルにあるSELL数量。
2. 極端に小さい数量同士の偶然を強い偏りとして採用しないため。
3. ratio capの10.0。
4. 同方向のImbalanceが価格配列上で連続すること。
5. Footprint元数量、Absorption、板の補充、CVD、Delta、Flow状態とその後の価格など。

---

## 13. この講義で最も大切な一文

> **Imbalanceは圧力の偏りを見つける。価格を動かせたかどうかは、別に確認しなければならない。**

---

## 参照

- `Delta_Engine_Pro4web/src/orderflow/imbalance.py`
- `Delta_Engine_Pro4web/src/orderflow/footprint.py`
- `Delta_Engine_Pro4web/config/config.yaml`
- `ArchitectureRepository/30_Modules/Imbalance_v3.2.md`

---

この文書は学習用であり、売買を指示するものではない。
