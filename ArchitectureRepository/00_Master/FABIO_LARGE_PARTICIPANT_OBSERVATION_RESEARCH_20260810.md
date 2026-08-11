# Fabioは「相場を動かす規模」をどう認識し、トレード判断へ使うか

- 調査日: 2026-08-10
- 対象: Fabio Valentini / Fabervaale本人の公式公開動画
- 一次資料: 公式 Fabervaale ENG、Fabervaale チャンネル
- 目的: Fabioが何を大きな参加の痕跡として見て、どちら側が相場を動かしていると判断し、どうトレードへ接続しているかを記録する
- 対象外: 発注者の身元推定、独自の大口分類、独自threshold、DeltaEngine用の検出ルール

## 1. 結論

Fabioは公開動画で、一人の人物、単一口座、特定企業、または一件の親注文を「大口」として特定していない。

Fabioが追っているのは、**相場を動かせる規模の注文活動と、その活動に対する価格結果**である。

大きな攻撃が価格を動かせば、攻撃した側が結果を得ている。

大きな攻撃が価格を動かせなければ、反対側にその攻撃を受け止める規模がある。

同じ価格を何度攻撃しても動かなければ、反対側の吸収が繰り返し確認される。

表示数量が小さくても、消費されるたびに同じ価格へ補充され続ければ、画面に一度に見える数量より大きな執行規模が存在する。

Fabioはこの力関係を、本人が「law of effort and result」と呼ぶ考え方で読む。

- effort: 市場へ入った注文量、攻撃量、反復した執行
- result: その注文活動が価格を実際にどれだけ動かしたか

[My Signature Orderflow Model 03:09-03:26](https://www.youtube.com/watch?v=Khgj5q1-ln8&t=189s)で、Fabioは、volumeは入っている注文量を、resultはその注文が価格へ与えた影響を示すと説明する。

したがってFabioの大口観測は、犯人捜しではない。

**どちら側に相場を動かす規模があり、その規模が押し切ったか、反対側に止められたかを判断する作業**である。

## 2. Fabioが大きな参加を判断する共通原理

### 2.1 大きなeffortが大きなresultを得た

大量のaggressive ordersが入り、価格が同じ方向へ明確に進む。

Fabioは、その側が注文量だけでなく価格結果も得たと判断する。

これは、その時点でその側が相場を動かしている証拠になる。

### 2.2 大きなeffortがresultを得られない

大量のaggressive ordersが入っても、価格が同じ方向へ進まない。

Fabioは、攻撃した側の注文が約定しなかったとは考えない。注文は約定しているが、反対側のpassive ordersに受け止められ、価格結果を得られなかったと読む。

このとき、画面に大きく見えるのは攻撃側の約定量だが、Fabioが重要視するのは、その量を止めた反対側の規模である。

### 2.3 同程度のeffortでもresultが一方へ偏る

[My Signature Orderflow Model 04:11-04:50](https://www.youtube.com/watch?v=Khgj5q1-ln8&t=251s)で、Fabioは買い手と売り手のeffortが同程度でも、売り手が完全に吸収され、買い手だけが価格結果を得る例を示す。

Fabioの判断は、注文量が同じだから互角、ではない。

価格結果が上方向へ大きく偏っているため、上へ継続する可能性のほうが高いと判断する。

### 2.4 小さいeffortで大きなresultが出る

[My Signature Orderflow Model 01:44-02:06](https://www.youtube.com/watch?v=Khgj5q1-ln8&t=104s)で、Fabioは低いeffortで大きな上方向のresultが出る例を示す。

Fabioは、力の均衡が変わり、買い側がpath of least resistanceになったと判断する。

ここでは一件の巨大注文を探していない。少ない攻撃で価格が大きく動く市場状態そのものを見ている。

### 2.5 同じ価格への攻撃と失敗が反復する

Fabioは、同じ価格への複数回の攻撃がすべて失敗した場面をまとめて、その価格でのabsorptionとして判断している。

見る対象は「同じ大口が繰り返したか」ではない。

見る対象は、**その価格へ繰り返し投入された攻撃量が、毎回価格結果を得られなかったこと**である。

### 2.6 小さい表示数量が同じ価格へ補充され続ける

板に見える一回の数量が小さくても、消費のたびに同じ価格へreloadされれば、累積執行規模は大きくなり得る。

Fabioはこれをicebergまたはhidden liquidityの足跡として説明する。

ここでも、主体の名前ではなく、同じ価格で大量を執行し続ける動作を見ている。

## 3. 中心資料: law of effort and result

出典: [My Signature Orderflow Model](https://www.youtube.com/watch?v=Khgj5q1-ln8)

### 3.1 Fabioがこのモデルで探すもの

[00:00-00:19](https://www.youtube.com/watch?v=Khgj5q1-ln8&t=0s)で、Fabioはgranular order flow dataを使い、volumeが容易にpriceを動かしている場所、すなわちpath of least resistanceを探すと説明する。

これは「何contractsなら大口か」という固定判定ではない。

注文活動と価格結果の関係から、現在どちらへ相場が動きやすいかを見つける考え方である。

### 3.2 大量に攻撃してもwickしか作れない

[03:30-03:59](https://www.youtube.com/watch?v=Khgj5q1-ln8&t=210s)で、Fabioはfloorへaggressive market participantsがhuge volumeで何度も攻撃する例を示す。

画面上の根拠:

- aggressive ordersが同じfloorを攻撃する
- volumeは大きい
- 攻撃のたびに価格が作れる最大の結果はwickだけ
- 下方向への継続が起きない

Fabioの判断:

- 攻撃側のcontinuationとは判断しない
- passive participantsがその注文を保持し、吸収していると判断する
- その価格をpotential reversal areaとして扱う

大きな攻撃量は攻撃側の強さだけを意味しない。その攻撃量を止めた反対側の規模も同時に示す。

### 3.3 トレードへどう使うか

[05:32-06:24](https://www.youtube.com/watch?v=Khgj5q1-ln8&t=332s)で、Fabioは先にarea of interestを定め、その場所でeffort/resultの偏りを確認すると説明する。

下方向へ偏った状態なら、その領域から下へ継続する確率が高いと読む。

反対側の領域が出て売り圧力のexhaustionを示した場合は、利益をすべて危険にさらして小さな続落を狙わず、利確またはstop管理へ移る。

つまり大口観測はentryだけでなく、継続、利確、stop移動にも使われる。

## 4. Deep Tradesで大きなeffortとprice resultを照合した例

出典: [The Only Orderflow Guide You'll Ever Need](https://www.youtube.com/watch?v=Pz8f0wWW12M)

Deep Tradesは、DeepCharts / DeepDOM内で、約定済み注文をsizeで絞ってチャートへ表示する機能である。

Fabioが見る中心はmarkerそのものではない。markerで見える大きな約定と、その後の価格結果との関係である。

### 4.1 上側価格帯の72・61・60・62

[37:31-38:24](https://www.youtube.com/watch?v=Pz8f0wWW12M&t=2251s)。

画面上の根拠:

- Fabioがshort候補として事前に選んだ上側価格帯へ価格が到達
- Deep Tradesが72、61、60、62 contractsのexecuted ordersを表示
- Fabioはそのhorizontal levelのeffortを口頭で約300 contractsと表現
- そのeffortは上方向へ価格を継続させない
- aggressive sellersはstrong aggressionと下方向のprice resultを示す

Fabioの判断:

- 先の大きなeffortは吸収された
- shortを構築し始める確認になった
- 約3分後、short positionsの追加と強いcandle resultを確認
- positionをrisk-freeへ移し、下方向のmovementを取る

ここでFabioは「72 contractsを出した人物」を特定していない。

複数の大きな約定が価格を上へ進められず、反対側だけが結果を得たため、下方向へ力が偏ったと判断している。

画面の4値の単純合計は255 contractsである。Fabioの口頭表現は約300 contractsだが、差の内訳は説明されていない。

### 4.2 下側価格帯の105と101

[39:06-40:31](https://www.youtube.com/watch?v=Pz8f0wWW12M&t=2346s)。

画面上の根拠:

- long候補として選んだ下側価格帯へ価格が到達
- wick上に105 contractsのexecuted order
- aggressive ordersはその価格を抜くresultを得られずrejected
- marketが同じ価格帯を複数回試して失敗
- 最後の試行で別の101 contractsが表示される
- 101 contractsの試行も同じ価格帯を抜けない

Fabioの判断:

- aggressive ordersはcompletely absorbed
- 反復した攻撃が同じ価格で結果を得られないため、long側の判断材料になる
- 確認後のbreakでstopをbreak-evenへ移す
- その後の上方向のexplosionでは、aggressionに従ってpositionをtrailする

105と101は同一人物、同一口座、同一parent orderを意味しない。

Fabioが使った根拠は、異なる時刻の大きなexecuted effortが、同じ下側価格帯で繰り返し結果を得られなかったことである。

## 5. CVDだけではentryせず、Big Tradesとprice resultを加えた例

出典: [My Top 3 Trades from the Competition](https://www.youtube.com/watch?v=0jM5Y31YJak)

[01:31-03:34](https://www.youtube.com/watch?v=0jM5Y31YJak&t=91s)。

画面上の根拠:

- priceはbalance中央にあり、価格だけでは方向がない
- CVDはpriceより先に大きく下へ進む
- Fabioは下方向のpressureが構築されているdistributionと判断
- ただしCVDの先行だけでは足りないと明言
- Big Tradesをsecond confirmationとして追加
- volumeのfollow-upと下方向のprice confirmationが同じcandleで現れる

Fabioの判断:

- CVDは大きな下方向pressureを示す最初のmilestone
- Big Tradesはbig playersがpriceをどこへpushしているかを確認する材料
- price actionが同じ下方向へfollow-upしたcandleで最初のshort positionを取る

この例は、大量圧力だけではトレードしないことを示す。

Fabioは、pressure、big executions、実際のprice resultが同じ方向へそろったところでentryしている。

## 6. 大きな約定があってもprice resultがなければ待つ例

出典: [The Simplest Orderflow Trading Model](https://www.youtube.com/watch?v=cUTsoU-15Tc)

### 6.1 買いaggressionとBig Tradesが出ても上へ進まない

[11:31-12:18](https://www.youtube.com/watch?v=cUTsoU-15Tc&t=691s)。

画面上の根拠:

- pressureは上方向へ構築中
- sellersは吸収されている
- buyersのaggression、Big Trades、imbalanceが上側に出る
- しかしprice resultがaggressionへ追随しない

Fabioの判断:

- 直ちに上方向継続とは判断しない
- まずretracementの可能性を読む

大きな買い約定が表示されたこと自体は、買いentryの十分条件ではない。

### 6.2 breakout後、売り手の反復攻撃が吸収される

[12:42-14:20](https://www.youtube.com/watch?v=cUTsoU-15Tc&t=762s)。

画面上の根拠:

- 最初のbreakout candleが出る
- retest areaでsellersが吸収される
- buyersのlock-inとconfirmationが出る
- 同じtest levelをsellersが繰り返し攻撃する
- 攻撃のたびに、さらに吸収される
- priceは上方向のauctionを構築する

Fabioの判断:

- horizontal levelにhuge absorptionがある
- directionとbreakoutが明確になった
- 上側のprotection levelへ向かうと判断
- entryまたはretest entryを取り、protection levelを管理目標として使う

### 6.3 誰がbattleに勝っているか

[19:00-20:31](https://www.youtube.com/watch?v=cUTsoU-15Tc&t=1140s)で、Fabioはexecuted ordersを、どちらがbattleに勝っているかを見るproxyとして使うと説明する。

- rewarded buyersとabsorbed sellersならbuyersが勝っている
- buyersが吸収されsellersがresultを得るならsellersが優勢
- buyersがauctionを上へpushしresultを得ているなら、水平なfight levelのbreakoutを確認に使う

Fabioはbuyersの勝利を確認した例で、stopをその領域の下へ置くbuyを検討し、上側のprotection levelを目標にする。

## 7. aggressive sideが領域を守り、shortを再開した例

出典: [How To Find The BEST Entry Zones](https://www.youtube.com/watch?v=06R-ebyOhDI)

### 7.1 Big Tradesとdelta pressureの領域

[01:47-03:45](https://www.youtube.com/watch?v=06R-ebyOhDI&t=107s)。

画面上の根拠:

- previous swing areaにdelta pressureとBig Tradesが重なる
- Fabioはshort継続なら、このareaから新しいaggressive short positionsがreloadされると予想
- priceがareaへ戻るとstrong aggressive sellersが現れる
- buyersはBig Tradesの領域を上へ破ろうとする
- priceは上へ定着せず再び下へcollapseする

Fabioの判断:

- aggressive sellersがareaをprotectしている
- area上にriskを限定したshort executionが可能
- 再試行後も売り手の保護を確認し、short re-entryを取れる

### 7.2 売り手がbattleに勝ったと判断した根拠

[05:03-06:28](https://www.youtube.com/watch?v=06R-ebyOhDI&t=303s)。

Fabioが挙げた根拠:

- aggressive seller ordersとDeep Tradesがcandle body内にある
- 売りの注文活動に下方向のfollowing resultがある
- buyersが支配を取り戻そうとするが吸収される
- absorbed buyers、movementをlockしたaggressive sellers、再度absorbed buyersという並びになる

Fabioの判断:

- sellerがbattleに勝った
- その一連の範囲が再訪時に見るareaになる
- real-time confirmationとしてshort方向のexecutionへ使う
- 状況が明確になった後は、そのareaへlimit orderを置く例も示す

## 8. Footprintで「攻撃」と「結果」を分けた例

出典: [Fondamenti di Orderflow](https://www.youtube.com/watch?v=YG_CzO8qWRk)

### 8.1 Footprintが表示するもの

[42:25-42:45](https://www.youtube.com/watch?v=YG_CzO8qWRk&t=2545s)で、FabioはFootprintが各price levelのBid / Ask executed ordersを表示すると説明する。

表示される数量は未約定の板数量ではない。すでに成立した約定数量である。

### 8.2 大きなseller participationがresultを得た

[43:19-44:57](https://www.youtube.com/watch?v=YG_CzO8qWRk&t=2599s)。

Fabioは色の強いblocksから、seller participationが広く集中したprice levelsを探す。

そのseller aggressionの直後に下方向のprice resultが出ているため、Fabioは「無駄なaggressionではなく、実際のresultを得た」と判断する。

### 8.3 buyersが3回、4回、5回攻撃しても上へ進まない

[46:20-47:10](https://www.youtube.com/watch?v=YG_CzO8qWRk&t=2780s)。

画面上の根拠:

- Fabioは色がaggression、candleがresultを示すと説明
- buyersのaggressionが同じ上側price levelへ集中
- candleはbuyersが期待する上方向のresultを示さない
- buyersが3回、4回、5回と再試行
- 各試行が再び吸収される
- その後marketがcollapseしreversalする

Fabioの判断:

- buyersにとって非常に悪い状態
- 同じprice levelでのabsorption
- 反復する攻撃と失敗が、reversalを読む根拠になる

## 9. Deltaの大きさとprice resultを同時に読んだ数値例

出典: [3 Order-flow Trading Tricks Exposed!](https://www.youtube.com/watch?v=o-w5Gxss6T0)

[02:03-03:09](https://www.youtube.com/watch?v=o-w5Gxss6T0&t=123s)。

画面上の数値:

- total volume 2,800 contracts
- delta +599 contracts
- 下側にFabioが示した332 contracts
- 後のtotal volume 4,600 contracts
- 後のdelta +812 contracts

Fabioの読み:

- 上側でbuyersが非常にaggressiveになったが、最初はbreakできずsellersに吸収された
- 下側の332も価格結果を得ず吸収された
- 4,600 volumeと+812 deltaをbuyersのhuge aggressionとして読む
- sellersがlevelをprotectしようとした後、priceが上へ大きくbreakした

Fabioはdeltaの数値だけを大口認定に使っていない。

総約定量、aggression差、上下両側の吸収、level protection、最終的なprice breakoutを連続して読む。

## 10. 板に見えない規模をreloadとicebergから認識する

出典: [The Only Liquidity Guide You'll Ever Need](https://www.youtube.com/watch?v=FawPrRUGNpk)

### 10.1 110 contractsのbid reload

[08:58-09:58](https://www.youtube.com/watch?v=FawPrRUGNpk&t=538s)。

画面上の根拠:

- compression中、bidに110 contractsが現れる
- 周囲の板数量より突出している
- そのbidが既存のlong方向の考えをsupportする

Fabioの判断:

- その価格でlongにfillされたい非常に大きな参加があるという情報
- market algorithmsがその大きなbidをfront-runしようとする
- 既存のlong ideaをvalidateする有力情報

ただしFabioは直後にspoofingを警告する。

板へ大きな数量が表示されたことだけでは、実際にfillされる大口活動と確定しない。

### 10.2 表示8 contractsが繰り返しreloadされる

[10:00-10:25](https://www.youtube.com/watch?v=FawPrRUGNpk&t=600s)。

画面上の根拠:

- 板に見える数量は8 contracts
- sellersが8を消費するたび、同じprice levelへ8がreloadされる
- reloadが何度も反復する

Fabioの判断:

- 表示上は8でも、累積では400または500 contractsになり得る
- 同じprice levelをalgorithmが補充するhidden liquidity / iceberg
- 一度に見える板数量ではなく、反復する補充から実際の規模を読む

Fabioは8 contractsが常に400または500を意味するとは述べていない。400・500は反復reloadが作り得る累積規模の例である。

### 10.3 見える板が小さくてもsellersを止めたwall

[21:23-22:06](https://www.youtube.com/watch?v=FawPrRUGNpk&t=1283s)。

画面上の根拠:

- resting liquidityの表示は大きくない
- sellersがその価格で止められる
- iceberg detectorは同じlevelのhidden reloadを示す

Fabioの判断:

- sellersがiceberg wallに遭遇した
- 見える板数量が小さくても、その価格はsuper important level

### 10.4 分割執行されたinstitutional scale

[22:08-23:34](https://www.youtube.com/watch?v=FawPrRUGNpk&t=1328s)。

Fabioはinstitutional playersがlarge amount of ordersをfillする必要がある例として、上昇途中の複数icebergを示す。

画面上の根拠:

- 上昇途中に複数のiceberg reload
- 三つ目のicebergがmarketを止める
- そのlevelでorderが完全にfillされる
- marketがその後collapseする
- 全量を板へ一度に表示せず、algorithmがfractionalizedにreloadする

Fabioの判断:

- visible liquidityへ価格が届かなかった本当の理由は、手前のicebergで必要量がfillされたこと
- 分割された補充動作から、画面に一度に見える数量を超える執行規模を認識できる

ここで記録できるのはinstitutional scaleの動作であり、特定機関の名前ではない。

## 11. 実際のposition管理へ使った例

出典: [My Best Trading Session of the Month](https://www.youtube.com/watch?v=fZlNGWvd2Ko)

[01:17-02:02](https://www.youtube.com/watch?v=fZlNGWvd2Ko&t=77s)。

画面上の根拠:

- consolidationがbuyersに破られる
- buyersがcontrolを取る
- sellersが吸収される
- failed seller auctionとbuyer aggressionがそろう

Fabioの判断:

- long方向のtradeを取る
- 判断の根拠になったlevelがfailした場合は、すぐpositionをbreak-evenへ移す

[03:28-04:46](https://www.youtube.com/watch?v=fZlNGWvd2Ko&t=208s)では、Big Tradesとcontrolの変化をposition管理へ使う。

- buyersがcontrolを取り、Big Tradesが並ぶ
- sellersがlevelをprotectしようとする
- さらにbreakすればstopをprofit方向へtrailする
- buyersとsellersの双方がresultを得ない区間はconsolidationと判断
- Big Tradesのeffortが出てもresultがなければ、どちらがbattleに勝つか待つ
- buyersがcontrolを取った後、stopを新しい安値の下へ上げる

[05:00-05:40](https://www.youtube.com/watch?v=fZlNGWvd2Ko&t=300s)では、buyersにもsellersにもresultがない地点をpotential acceleration levelとして監視し、その後のaggressionとfailed auctionを見てtradeを閉じる。

大口観測は、entry方向を決めるだけではない。

現在のcontrolが続いているか、levelがfailしたか、利益を守るべきかを判断するためにも使われる。

## 12. Fabioの判断を一つの流れにすると何が起きているか

以下は新しい検出ルールではない。上記動画でFabioが繰り返している確認順序を、共通部分だけにまとめたものである。

1. まず観察するlocationを決める。
2. Deep Trades、Footprint、Delta、CVD、DOM、iceberg表示から、どちら側へどれだけのeffortが入ったかを見る。
3. そのeffortの後、priceが同じ方向へ進んだかを見る。
4. priceが進めば、攻撃側がresultを得たと判断する。
5. priceが進まなければ、反対側がそのeffortを吸収したと判断する。
6. 同じlevelで攻撃と失敗が反復すれば、その吸収を再確認する。
7. 反対側のeffortも同時に見て、どちらがbattleに勝ち、path of least resistanceがどちらへ向いたか判断する。
8. pressure、big executions、price confirmationがそろったときにentry、scale、re-entryを行う。
9. level failure、opposite effort、exhaustion、control changeを見てbreak-even、trail、profit taking、exitを行う。

locationは大口の証拠ではない。

VWAP、POC、VAH、VAL、LVN、Initial Balance、previous swingなどは、詳しく観察する場所を決める情報である。

その場所で実際に起きたeffort、absorption、reload、resultが、大きな参加の証拠になる。

## 13. Fabio動画から得られる「大口」の最大公約数

Fabio動画の最大公約数は、contracts数の固定thresholdではない。

次のいずれかによって、通常の雑音では説明しにくい市場規模が見えることである。

- 大きな約定量が実際にpriceを動かす
- 大きな約定量が反対側に止められ、priceを動かせない
- 同じ価格への攻撃が何度も失敗する
- 同程度の攻撃量でもprice resultが一方だけへ偏る
- 小さいeffortでpriceが大きく進み、抵抗の少ない方向が現れる
- 小さい表示数量が同じ価格へ繰り返しreloadされ、累積規模が拡大する
- Big Trades、Delta/CVD、Footprint、price resultが同じ支配方向を示す

したがって、大口は一件のmarkerや一人の主体ではない。

**相場を動かす規模、または相場を動かそうとする規模を受け止める力が、注文フローと価格結果の関係として現れた状態**である。

Fabioはその状態から、目先でどちらが支配しているか、どちらへ継続しやすいか、どのlevelが守られているかを判断している。

## 14. 公開動画から確定できないこと

- 一件のmarkerを発生させた個人、口座、銀行、ファンド、market makerの身元
- 複数markerが同一主体または同一parent orderに属すること
- 全商品、全時間帯で共通するBig Tradesの最低contracts数
- Deep Tradesの色だけから売買側を確定すること
- 板へ大きな数量が出たことだけで、実際にfillされると確定すること
- VWAP、POC、VAH、VAL、LVN、Initial Balanceへの到達だけで大きな参加と認定すること
- DeltaまたはCVDだけで大口の存在とトレード方向を確定すること
- Fabioのproprietary model内部の全計算式とthreshold

これらを補完してはいけない。

Fabio本人の公開動画から確定できるのは、表示されたeffort、価格result、反復、吸収、reload、支配側の判断、そして本人が実際に取ったentryとrisk managementである。

## 15. 直接使用した公式動画

- [My Signature Orderflow Model](https://www.youtube.com/watch?v=Khgj5q1-ln8) — Fabervaale ENG
- [The Only Orderflow Guide You'll Ever Need](https://www.youtube.com/watch?v=Pz8f0wWW12M) — Fabervaale ENG
- [My Top 3 Trades from the Competition](https://www.youtube.com/watch?v=0jM5Y31YJak) — Fabervaale ENG
- [The Simplest Orderflow Trading Model](https://www.youtube.com/watch?v=cUTsoU-15Tc) — Fabervaale ENG
- [How To Find The BEST Entry Zones](https://www.youtube.com/watch?v=06R-ebyOhDI) — Fabervaale ENG
- [My Best Trading Session of the Month](https://www.youtube.com/watch?v=fZlNGWvd2Ko) — Fabervaale ENG
- [3 Order-flow Trading Tricks Exposed!](https://www.youtube.com/watch?v=o-w5Gxss6T0) — Fabervaale ENG
- [The Only Liquidity Guide You'll Ever Need](https://www.youtube.com/watch?v=FawPrRUGNpk) — Fabervaale ENG
- [Fondamenti di Orderflow](https://www.youtube.com/watch?v=YG_CzO8qWRk) — Fabervaale

補助確認:

- [Analisi Volumetrica Pratica](https://www.youtube.com/watch?v=ZrfwJBaI07Y) — Fabervaale
  - 09:00-10:18でFootprint imbalanceをshort aggressionとlong aggressionの数学的比率として説明する
  - 300%または400%はimbalanceのthreshold例であり、Big Tradesのcontracts thresholdではない

第三者の解説、転載動画、分析者独自の大口分類は一次証拠として使用していない。
