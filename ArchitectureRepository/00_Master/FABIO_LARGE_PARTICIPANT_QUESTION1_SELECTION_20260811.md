# Fabioは通常注文と大口規模をどう選別するか

- 作成日: 2026-08-11
- 対象: Fabio Valentini / Fabervaale本人の公式YouTube動画70本
- 今回答える範囲: 問1「通常注文と大口規模をどう選別するのか」だけ
- 今回扱わない範囲: 候補の確定条件、吸収側規模、継続・消失、トレード方向、DeltaEngineへの実装

## 一文での回答

Fabioは、全商品共通の固定contracts数で通常注文と大口を二分せず、**現在の市場活動に合わせたexecuted-orderのsize filter、周囲に対する相対参加量、同一価格での反復消費・reload**を使い、大口規模の候補を選別している。

## 「通常注文」という言葉の境界

`通常注文`はFabioが公開動画で定義したformal class名ではない。本書では、次のいずれにも該当せず、大口観測画面で優先表示されない小さいactivityを説明するためだけに使う。

- 現在のsize filterを超える大きなexecuted order
- price levelまたは時間窓内で突出した累積participation
- 同じprice levelで消費とreloadを繰り返すhidden cumulative size
- 周囲より突出したresting liquidity候補

この選別で分かるのは大口規模の**候補**である。その候補が市場を支配したかは問2の対象であり、今回は判断しない。

## 1. 個別の大きな約定はDeep Tradesのsize filterで拾う

Deep Tradesは、DeepCharts / DeepDOMという取引分析ソフト内で使うインジケーターである。取引所で成立したexecuted ordersをsize等で絞り、条件に合う約定をチャート上へmarker表示する。

[The Only Orderflow Guide You'll Ever Need 37:16-37:50](https://www.youtube.com/watch?v=Pz8f0wWW12M&t=2236s)で、Fabioはexecuted ordersをsizeでfilterし、big market participantsだけを見たいと説明している。映像の設定画面ではsizeとsideを絞り、チャートを通常の小さい約定で埋めず、大きな約定候補だけを残している。

二つのfilterの役割は異なる。

- **size filter**: 小さいexecuted ordersを表示対象から外し、大きな約定候補を残す。
- **side filter**: 買い側／売り側のどちらを表示するかを分ける。side自体は規模判定ではない。

同動画で表示された`72・61・60・62 contracts`、別場面の`105・101 contracts`は、この選別後に画面へ残った大きなexecuted-order候補の具体例である。

ただし、公開動画から各場面の正確なfilter値は確定できない。表示された最小markerを、その商品全体の固定thresholdへ一般化してはならない。

## 2. size filterは当日の市場活動に合わせる

[Watch me Manage a -10.000$ trading Session 01:13-01:26](https://www.youtube.com/watch?v=jasv3L-d8ZE&t=73s)で、Fabioは「今日はvolumeが多いため、より大きなfilterが必要」と発言している。

ここから確定できる選別原則は次のとおりである。

- 同じcontracts数でも、市場活動の小さい日と大きい日では相対的な意味が違う。
- volumeが多い日は、小さい約定まで大口候補に混ざらないようfilterを上げる。
- filterは現在の商品、session、当日のactivityから切り離せない。

公開動画から確定できないもの:

- volumeからfilter値を求める数式
- volatility別の係数
- 商品別・session別の固定表
- 全venue共通の最低contracts数

したがって、Fabioの公開手法を「何contracts以上なら大口」と一つの数字に置き換えることはできない。

## 3. 一件を大きく表示しない分割執行はreload／icebergで拾う

大口規模が常に一件の大きなprintになるとは限らない。

[Logica e natura delle mutazioni 08:07-12:16](https://www.youtube.com/watch?v=0qo-x2_E6GA&t=487s)で、Fabioは大規模fundが全量を一価格へ一度に入れるとslippageと不利なaverage fillを生むため、注文を分割し、liquidity clusterを使って時間をかけて執行すると説明している。

このため、個々の約定がsize filter未満でも、同じprice levelで反復すれば大口規模になり得る。

[The Only Liquidity Guide You'll Ever Need 09:56-10:25](https://www.youtube.com/watch?v=FawPrRUGNpk&t=596s)の具体例:

1. 板に一度に見える数量は`8 contracts`。
2. sellersがその8を消費する。
3. 同じprice levelへ再び8がreloadされる。
4. この消費と補充が反復する。
5. Fabioは、一度の表示は8でも累積`400 / 500 contracts`になり得ると説明する。

ここでの選別対象は「表示8」ではない。**同価格で時間を通じて消費された累積量と、補充の反復**である。

`8 contracts`が常に400または500を意味するわけではない。400／500はFabioが示した反復reloadの累積例であり、固定倍率ではない。

## 4. Footprint／Delta／CVDは一件の大口ではなく累積participationを拾う

Deep Tradesは個別の大きなexecuted ordersを絞る。一方、Footprint、Delta、CVDは別の観測層である。

### Footprint

[Fondamenti di Orderflow 42:25-42:45](https://www.youtube.com/watch?v=YG_CzO8qWRk&t=2545s)で、FabioはFootprintが各price levelのBid側／Ask側executed ordersを表示すると説明する。

Fabioは、price levelごとに約定量が集中したblockを見て、その価格でどちら側のparticipationが周囲より大きかったかを選別する。これは一人の大口注文を抜く処理ではなく、複数約定が作ったprice-level cumulative activityを見る処理である。

[3 Order-flow Trading Tricks Exposed! 02:03-03:09](https://www.youtube.com/watch?v=o-w5Gxss6T0&t=123s)には、`total volume 2,800 / delta +599`、後の`4,600 / +812`が表示される。これらはtotal executed volumeと買い・売りaggression差を数量として読む例であり、単一parent orderのsizeではない。

### Delta／CVD

Deltaは買い成行約定量と売り成行約定量の差、CVDはそのDeltaを時間方向へ累積した圧力である。

[My Top 3 Trades from the Competition 02:05-02:56](https://www.youtube.com/watch?v=0jM5Y31YJak&t=125s)で、Fabioはpriceより先に大きく下へ進むCVDを、下方向pressureが積み上がっているfirst milestoneとして読む。

CVDで選別できるのは、大きな**合成圧力**である。個別の大口約定、発注者、一件のparent orderを選別するものではない。

## 5. DOMの突出数量は未約定の大口候補として分ける

DOM / Heatmapに表示されるのは、まだ約定していないresting limit ordersである。Deep TradesやFootprintのexecuted ordersとは証拠の種類が違う。

[The Only Liquidity Guide You'll Ever Need 08:50-09:58](https://www.youtube.com/watch?v=FawPrRUGNpk&t=530s)では、compression中のbidに`110 contracts`が現れる。周囲には`8・12・29・40`等の数量があり、110は相対的に突出している。

Fabioは、これをそのprice levelでfillされたい大きな参加の情報として読む。同時に、直後にspoofingの可能性を警告している。

したがってDOMで行うのは次の選別までである。

- 周囲より突出したresting quantityを大口流動性候補として拾う。
- 表示quantityと周囲の通常量を相対比較する。
- 表示だけではexecuted large activityへ昇格させない。

大きなwallがcancelされた場合も、「大口が退出した」とはこの段階で確定できない。

## 6. VSA／Weis Wave型の比較はswing単位の相対participationを拾う

Fabioは個別注文だけでなく、barまたはswing全体のparticipationも比較する。

[VSA Logic and Fundamentals of Auction Market Theory 08:25-11:37](https://www.youtube.com/watch?v=BHV0n3PV-0w&t=505s)では、market forcesとparticipationを読み、swing間のparticipationを比較し、structure break前のabove-average participationを確認する。

この層が選別するのは、過去のbar／swingに対して相対的に大きいeffortである。

- Deep Trades: 個別executed orderのsize。
- Footprint／Delta／CVD: price levelまたは時間窓内の累積participation／pressure。
- VSA／Weis Wave型比較: barまたはswing全体の相対participation。

この三つを「一件の大口注文」として同一視してはならない。

## 7. Locationは選別場所であって、大口認定条件ではない

FabioはProfile、VWAP、VAH／VAL、LVN、Initial Balance、previous swing、supply／demand等で詳しく見るprice areaを先に絞る。

これらは、すべてのpriceを同じ密度で監視しないためのlocation filterである。

- 重要locationにあるから大口になるわけではない。
- location外にあるから約定sizeが小さくなるわけでもない。
- locationは「どこで大口候補を重視するか」を決める。
- size、累積participation、reloadは「何を大口規模候補として拾うか」を決める。

locationとsize evidenceは別である。

## Fabioの選別方法を順番にすると

1. 商品、session、当日のvolumeを現在のactivity背景として見る。
2. Deep Tradesのsize filterを、その背景で小さい約定が大量に残らない水準へ調整する。
3. 必要に応じてside表示を分け、大きなexecuted-order候補を読む。
4. Footprint／Delta／CVDで、一件ではなくprice levelまたは時間窓に累積した大きなparticipationを拾う。
5. 個別sizeが小さくても、同じprice levelで消費・reloadが反復する場合はiceberg／hidden cumulative size候補として拾う。
6. DOMの突出quantityは、未約定の大口流動性候補として別枠で残す。
7. VSA／Weis Wave型比較で、bar／swing単位のparticipationが過去に対して異常に大きいかを見る。
8. Profile／VWAP等のlocationは、これらの候補を詳しく見る場所の優先順位にだけ使う。

## 観測層ごとの最終整理

| 観測層 | 入力データ | 大口規模の選別単位 | この段階での証拠強度 |
|---|---|---|---|
| Deep Trades | 約定済み注文 | 個別executed size | 大きな約定候補が実際に成立した |
| Footprint | price別の約定済みBid／Ask量 | price-level累積participation | その価格で大きな参加があった |
| Delta／CVD | aggressive buy／sellの差と累積 | 時間窓の合成pressure | 大きな方向圧力が積み上がった |
| DOM／Heatmap | 未約定limit orders | 周囲より突出したresting quantity | 大口流動性の表示候補にすぎない |
| iceberg／reload | 消費後の同価格補充 | 同価格の累積消費・補充 | 一時表示を超えるhidden size候補 |
| VSA／Weis Wave型比較 | bar／swing volume | 過去に対する相対participation | bar／swing規模の異常参加候補 |

## 問1の確定回答

Fabioの選別には、三つの中心がある。

1. **個別size**  
   Deep Tradesのsize filterで、小さいexecuted ordersを除き、大きな約定候補を残す。
2. **累積size**  
   Footprint／Delta／CVDと同価格reloadから、分割された約定、合成pressure、hidden cumulative sizeを拾う。
3. **相対size**  
   当日のvolume、周囲の板数量、過去bar／swing participationと比較し、その市場状態で異常に大きいものを残す。

固定contracts thresholdだけではない。`72`、`105`、`110`、`8 -> 400 / 500`は、それぞれ別場面の具体例であり、共通thresholdではない。

この問1で確定したのは大口規模の**候補選別方法**までである。候補を大口活動としてどう確定するかは問2であり、本書には持ち込んでいない。

## 証拠境界

- 全商品共通の最低contracts数は公開されていない。
- Fabioの全filter値、計算式、normalizationは公開されていない。
- Footprint／Delta／CVDの大きな値は、単一主体のsizeではない。
- DOMの突出quantityは未約定であり、spoofingの可能性がある。
- reloadの複数回表示から、同一主体または同一parent orderとは確定できない。
- markerの色相だけから売買sideを補完しない。
- VWAPやPOC等のlocationだけで大口規模とは認定しない。

## 使用した公式動画

- [The Only Orderflow Guide You'll Ever Need](https://www.youtube.com/watch?v=Pz8f0wWW12M)
- [Watch me Manage a -10.000$ trading Session](https://www.youtube.com/watch?v=jasv3L-d8ZE)
- [The Only Liquidity Guide You'll Ever Need](https://www.youtube.com/watch?v=FawPrRUGNpk)
- [Logica e natura delle mutazioni](https://www.youtube.com/watch?v=0qo-x2_E6GA)
- [Fondamenti di Orderflow](https://www.youtube.com/watch?v=YG_CzO8qWRk)
- [3 Order-flow Trading Tricks Exposed!](https://www.youtube.com/watch?v=o-w5Gxss6T0)
- [My Top 3 Trades from the Competition](https://www.youtube.com/watch?v=0jM5Y31YJak)
- [VSA Logic and Fundamentals of Auction Market Theory](https://www.youtube.com/watch?v=BHV0n3PV-0w)

第三者の動画、独自threshold、DeltaEngineの既存検出条件は使用していない。
