# Fabioは何を見て「相場を動かす規模」と判断したか — 具体証拠台帳

- 作成日: 2026-08-10
- 母集団: Fabio Valentini / Fabervaale公式動画70本
- 目的: 抽象的な「大口定義」ではなく、動画上の表示値・発生順序・価格結果・Fabioの判断・実際の売買行動を一件ずつ固定する
- 位置付け: `FABIO_70_VIDEO_LARGE_PARTICIPANT_AUDIT_20260810.md`の証拠索引を、実際の判断場面に絞って読み直したもの

## 先に結論

Fabioが実際に「大きな側」を判断している証拠は、一つの数値ではない。具体的には次の四種類である。

1. **攻撃が価格を動かした**  
   大きなexecuted ordersと同方向の値動きが接続し、攻撃側がresultを得た。
2. **攻撃が価格を動かせなかった**  
   大きなexecuted ordersが入ったのにlevelを抜けず、反対側の吸収規模が露出した。
3. **同じ価格で攻撃と失敗が反復した**  
   単発の失敗ではなく、複数回の攻撃が毎回同じ側に受け止められた。
4. **表示数量より大きな累積執行が露出した**  
   小さな表示数量が同価格へreloadされ続け、icebergとして実執行量が積み上がった。

Fabioはこれらを、事前に選んだprice location、当日のvolume、session、反対側の注文と照合し、entry、scale、break-even、trail、exitへ使っている。

## 重要度順の具体場面

### 1. 72・61・60・62の大きな約定が上へ進めず、Fabioはshortを構築した

出典: [The Only Orderflow Guide You'll Ever Need 37:31-38:43](https://www.youtube.com/watch?v=Pz8f0wWW12M&t=2251s)

**事前状況**

- Fabioは先にprofile等でshort候補の上側価格帯を選んでいた。
- Deep Trades画面はexecuted ordersをsizeでfilterし、Fabioが「big market participants」と呼ぶ層の価格帯とのinteractionを表示していた。

**画面に出た数値と挙動**

- 上側のhorizontal areaに`72・61・60・62 contracts`と表示された約定marker。
- 四値の単純合計は255 contracts。Fabioの口頭表現は約300 contracts。
- これらのeffortの後も、priceは上側へ継続しなかった。
- 反対側のaggressive sellersには、強い下方向のprice resultが出た。

**Fabioの判断**

- 72等の大きなeffortは価格を上へ進められず、absorbされた。
- 大きなmarkerが出た側ではなく、その規模を受け止め、実際に下へ動かしたsellersを勝者と判断した。

**Fabioの売買行動**

- 下方向のpositionをbuildし始めた。
- 約3分後、sellersの追加positionと強いcandle resultを確認し、positionをrisk-freeへ移した。

**この場面で確定できる大口認識**

> 「大きな約定が出た側」と「相場を動かした側」は同じとは限らない。Fabioは後者をトレード方向に採用した。

**この場面では確定できないこと**

- 72・61・60・62が同一主体か、同一parent orderか、色がどの売買側を示すかは確定できない。

### 2. 105と101 contractsが同じ下側価格を抜けず、Fabioはlong判断に使った

出典: [The Only Orderflow Guide You'll Ever Need 39:06-40:31](https://www.youtube.com/watch?v=Pz8f0wWW12M&t=2346s)

**事前状況**

- Fabioはprofile等でlong候補の下側価格帯を選んでいた。

**画面に出た数値と時系列**

1. priceが候補価格帯へ到達。
2. wickの位置に`105 contracts`のexecuted orderが出た。
3. 攻撃は下側levelを抜けず、price resultを得られなかった。
4. marketが同じlevelを再度攻撃して失敗。
5. 最後の試行で`101 contracts`が出たが、それでも下へ抜けなかった。

**Fabioの判断**

- 別時刻の105と101を、同じ価格帯を攻撃した複数回のeffortとして見た。
- 攻撃側が毎回resultを得られないため、completely absorbedと判断した。

**Fabioの売買行動**

- 下側価格帯の吸収をlongのexecution informationに使った。
- 上方向へbreakした後にstop lossをbreak-evenへ移し、その後の上方向explosionをaggressionに従ってtrailした。

**この場面で確定できる大口認識**

> 一発の105より、同じ価格で105、再攻撃、101と重なっても価格が下へ進まないことが、反対側の大きな受け止めを示した。

### 3. CVDの大きな下方圧力だけではshortせず、Big Tradesとprice follow-throughを待った

出典: [My Top 3 Trades from the Competition 02:05-06:52](https://www.youtube.com/watch?v=0jM5Y31YJak&t=125s)

**画面に出た順序**

1. priceはbalance中だったが、CVDはbreakout前から大きく下へ進んだ。
2. Fabioはこれをdistribution中の下方向pressureと判断した。
3. ただし、CVDの先行だけでは不十分だと明言した。
4. Deep Tradesを追加し、big playersがpriceをどこへpushしているかを確認した。
5. volumeの下方向follow-upとpriceの下方向confirmationが同じcandleで現れた。

**Fabioの判断と売買行動**

- CVD pressureをfirst milestone、Big Trades + price follow-throughをsecond confirmationとした。
- second confirmationが出たcandleで最初のshort positionを取った。
- 05:22付近でBig Tradesがpriceをそれ以上下へpushしなくなったため、利益を確定した。
- 06:03付近で再びBig Tradesがtrend方向に出てbreakdownしたため、再度shortした。
- 06:44付近でbuyersが取り戻そうとしたがresultがほぼゼロで、sellersのcontrol継続と判断した。

**この場面で確定できる大口認識**

> 「大きな圧力」「大きな約定」「実際の価格結果」は別々の確認項目。Fabioは三つが揃うまでトレードしていない。

### 4. 板に見える8 contractsが同価格へ補充され続け、Fabioは400～500の累積規模の可能性を示した

出典: [The Only Liquidity Guide You'll Ever Need 09:56-10:25](https://www.youtube.com/watch?v=FawPrRUGNpk&t=596s) / [21:30-22:33](https://www.youtube.com/watch?v=FawPrRUGNpk&t=1290s)

**画面に出た挙動**

- order bookに一度に見える数量は`8 contracts`。
- sellersが8を消費するたび、同じprice levelへ8が再表示された。
- このreloadがalgorithmで繰り返された。

**Fabioの判断**

- 表示は8でも、消費とreloadを累積すれば400や500 contractsになり得る。
- これをinvisible liquidity / icebergと説明した。
- 別の例では、institutional playersがlarge amount of ordersをfillするため上昇中に複数icebergを置き、3つ目のmarketを止めたicebergでfillされ、その後priceがcollapseする例を示した。

**この場面で確定できる大口認識**

> 一回の表示数量ではなく、同じprice levelで時間を通じてどれだけ消費され、どれだけ補充されたかが実規模の証拠になる。

**確定できないこと**

- 表示8が常に400または500を意味するわけではない。400/500はFabioが示した累積例。

### 5. 2,800 volume / +599 deltaと、4,600 volume / +812 deltaをprice resultと組み合わせた

出典: [3 Order-flow Trading Tricks Exposed! 02:03-03:09](https://www.youtube.com/watch?v=o-w5Gxss6T0&t=123s)

**画面に出た数値と順序**

- 上側でbuyersがaggressiveになったが、最初はlevelをbreakできず、sellersに吸収された。
- 表示値は`total volume 2,800`、`delta +599`。
- 下側にFabioが示した`332`のeffortもresultを得ず吸収された。
- 後の区間で`total volume 4,600`、`delta +812`が出た。Fabioはこれをbuyersのhigh / huge aggressionと読んだ。
- sellersがlevelをprotectしようとした後、priceは上へ大きくbreakした。

**Fabioの判断**

- deltaの数値一つで方向を決めていない。
- total volume、delta、上下両側のabsorption、level protection、最終的なbreakoutを時系列で読んでいる。

**この場面で確定できる大口認識**

> 大きdeltaはpressureの数値であり、大口の勝利そのものではない。そのpressureがlevelをbreakし、price resultへつながったところで支配側が確定する。

### 6. +104 deltaと+75 deltaがtopで吸収され、Fabioは下側level攻撃の確率が高いと判断した

出典: [Orderflow Series 2025 67:57-68:33](https://www.youtube.com/watch?v=8nEDJ5npS1M&t=4077s)

**入力情報**

- 視聴者から、top levelに`+104 buy delta`、2番目にlevelに`+75`というOrderflow情報が入った。
- Fabioは、その場では視聴者から得た数値を信頼して読むと明言した。

**Fabioの判断**

- top levelのabsorptionは非常に大きい。
- aggressive buyersが吸収されているため、直下のsupporting levelが攻撃され、それが食べられれば次のlevelへ進む確率が高いと判断した。

**trade actionの境界**

- この方向読みの前にFabioは、時間が金曜日のcloseに近く、range compressionと突発volatilityのため、この時間にはtradeしないと説明している。

**この場面で確定できる大口認識**

> Fabioは吸収の方向判断と、実際にtradeするかを分けている。大きな吸収があっても、session / 曜日 / 時間帯が悪ければ見送る。

### 7. huge volumeでfloorを何度攻撃してもwickしか作れず、Fabioはcontinuationを否定した

出典: [My Signature Orderflow Model 03:30-03:59](https://www.youtube.com/watch?v=Khgj5q1-ln8&t=210s)

**表示された挙動**

- aggressive market participantsが同じfloorへhuge volumeで繰り返し攻撃。
- 攻撃のたびに作れた最大のprice resultはwick。
- 下方向へのfollow-throughがない。

**Fabioの判断**

- huge volumeを見て「攻撃側が強いから継続」とは判断しない。
- passive participantsが攻撃注文を保持・吸収していると判断。
- そのlevelをpotential reversal areaとして扱う。

**大口の認識**

> 画面に現れた攻撃量が「見える大口」であっても、Fabioが重要視したのは、それを受け止めた「見えにくい反対側の規模」である。

### 8. buyersとsellersのeffortは同程度だが、resultは上へ偏り、Fabioはbuyers勝利と判断した

出典: [My Signature Orderflow Model 04:11-04:50](https://www.youtube.com/watch?v=Khgj5q1-ln8&t=251s)

**表示された関係**

- aggressive buyersとaggressive sellersのeffortはほぼ同じ。
- sellersはcompletely absorbed。
- buyersは上方向のprice resultを得た。

**Fabioの判断**

- 注文量が同じでも互角とは判断しない。
- resultが上方向へ大きくskewしているため、上のhighへ継続する確率のほうが高いと判断。

**大口の認識**

> 大口は「一番大きい約定」ではなく、競合する大きな力のうち、実際にprice resultを得た側として認識される。

### 9. candle bodyのseller Deep Trades、下方result、absorbed buyersが揃い、Fabioはshort areaを確定した

出典: [How To Find The BEST Entry Zones 05:03-06:28](https://www.youtube.com/watch?v=06R-ebyOhDI&t=303s)

**画面に出た順序**

1. aggressive seller orders / Deep Tradesがcandle body内に現れた。
2. sellersの注文活動に対し、priceが下方向へfollowした。
3. buyersがcontrolを取り戻そうとしたが、吸収された。
4. absorbed buyers -> movementをlockしたaggressive sellers -> 再度absorbed buyersという順序になった。

**Fabioの判断と行動**

- sellersがbattleに勝ったと判断。
- その一連の価格帯を、再訪時のshort areaとして使った。
- 状況が明確になった後は、そのareaへlimit orderを置く例を示し、その後marketはcollapseした。

**大口の認識**

> Big Trades marker単体ではなく、candleのどこで出たか、同方向のprice resultがあるか、反対側が失敗したかの三つで価格帯を確定している。

### 10. seller participationが最も強いprice levelと下方resultを照合し、その後のbuyer反復攻撃の失敗を見た

出典: [Fondamenti di Orderflow 43:19-47:10](https://www.youtube.com/watch?v=YG_CzO8qWRk&t=2599s)

**画面に出た順序**

- Footprintの色が強いblocksから、seller participationが広く集中したprice levelsを特定。
- そseller aggressionの後に実際の下方向price resultが出た。
- priceがその価格帯へ戻った際、buyersのaggressionが集中したが、candleはbuyersが期待する上方resultを示さなかった。
- buyersは3回、4回、5回と同じ価格帯を攻撃し、毎回吸収され、その後marketはcollapseした。

**Fabioの判断**

- 最初のseller aggressionは「無駄なaggression」ではなく、price resultを得た有効な参加。
- 後のbuyersの反復攻撃は、色では大きく見えてもresultを得られず、absorption。

**大口の認識**

> Footprintの色はaggression、candleはresult。Fabioはこの二つを分け、「強く攻撃した側」と「実際に支配した側」を判別している。

### 11. 反復するsellerの攻撃が吸収され、Fabioは上方向pressureが築かれていると判断した

出典: [The Simplest Orderflow Trading Model 11:31-13:38](https://www.youtube.com/watch?v=cUTsoU-15Tc&t=691s)

**画面に出た順序**

- 上方向pressureが築かれ、sellersが吸収された。
- buyersのaggressionとBig Tradesが出たが、その瞬間にprice resultが追従しない局面では、Fabioは直ちに上へ継続とは判断しなかった。
- breakout後のtest levelでsellersが攻撃し、再度、さらに再度と吸収された。

**Fabioの判断と売買への接続**

- 反復吸収によりhorizontal levelにhuge absorptionがあると判断。
- clean breakoutと上方向auctionを確認し、上側protection levelへ向かう判断に接続した。

**大口の認識**

> Fabioは最初のBig Tradesでは待ち、breakout、retest、反復するseller absorptionという時系列が揃った後に上方向を確定した。

### 12. 実trade中、sellersのcontrolを維持し、aggressive buyersの取り戻し可能性で23,000ドルのprofit stopを終了した

出典: [How I did 20R in one NQ Session 01:42-08:43](https://www.youtube.com/watch?v=8CWKfoSJu3c&t=102s)

**Fabioが維持中に見ていたもの**

- buyersがcompletely absorbed、sellersのeffortはrewarded。
- big sellersがmarketをcontrol。
- 戻りでsellersがreloadし、buyersの注文を吸収。
- seller momentumが再度出るたびにstopをtrail。

**Fabioの退出判断**

- 終盤でaggressive buyersがcontrolを取り戻す可能性が出た。
- Fabioは「buyersがcontrolを取り戻すなら市場から出たい」と説明し、profit stopにより追加利益23,000ドルで終了した。

**大口の認識**

> 大口観測はentry signalで終わらない。自分が追従する側のcontrolが続いている間だけpositionを維持し、反対側のcontrol取り戻しをexit条件にする。

### 13. 110 contractsのbid reloadを「大きな者がlongにfillされたい」情報と読んだが、即座にspoofingを警告した

出典: [The Only Liquidity Guide You'll Ever Need 08:50-09:58](https://www.youtube.com/watch?v=FawPrRUGNpk&t=530s)

**画面に出たもの**

- consolidation / compression中、bidに`110 contracts`が出現。
- 周辺の板数量より視覚的に突出。

**Fabioの初期判断**

- そのlevelでlongにfillされたい「非常に大きな者」がいる情報。
- market algorithmsがそのbidをfront-runする可能性がある。

**Fabioの警告**

- このパターンはspoofingにも使われる。
- 後の場面でも、fresh liquidity / reloadが表示されてもfillされる保証はないと説明している。

**大口の認識**

> 大きな未約定板数量は「情報」ではあるが「事実として執行された大口」ではない。実執行、reload、price responseの確認が必要。

### 14. 当日のvolumeが多いため、Fabioは大口表示filterを大きくした

出典: [Watch me Manage a -10.000$ trading Session 01:13-01:26](https://www.youtube.com/watch?v=jasv3L-d8ZE&t=73s)

**Fabioの実況発言と状況**

- topでbig buyersがabsorbされていた。
- Fabioは「今日はvolumeが多い。だからより大きなfilterが必要」と発言した。

**大口の認識**

> Fabioがこの場面で明言したのは、当日の市場活動が高いときは、小さい約定を大口表示から外すため、表示filterを大きくするということ。

**確定できないこと**

- 全商品共通の計算式、volatilityとfilterの関数、session別の具体係数は公開されていない。

### 15. 大規模fundは一価格へ全量を入れず、注文を分割してliquidity clusterで執行する

出典: [Logica e natura delle mutazioni 08:07-12:16](https://www.youtube.com/watch?v=0qo-x2_E6GA&t=487s)

**Fabioが説明した執行上の事実**

- big playersは数十亿級の資金を一つのprice levelへ一度に入れられない。
- fund / institutionはpositionを時間をかけてaccumulateする。
- 一回に重く執行するとpriceを自分に不利な方向へ動かし、slippageと悪いaverage fillを生む。
- そのため、反対注文が集まるliquidity pocket / clusterで分割執行する。

**Fabioの個人stopに対する説明**

- 目的はFabioや特定個人をstop outすることではない。
- 必要なのは、実際に大量執行の相手となる注文のcluster。

**大口の認識**

> 一発の超大型約定だけを探すと、大口が実際に行う分割執行、accumulation、liquidity clusterの利用を逃す。

### 16. Fabioは「単一algorithmの正体」を問わず、aggressive pressureとpassive absorptionの合成結果を読む

出典: [Fondamenti di Orderflow 05:30-06:26](https://www.youtube.com/watch?v=YG_CzO8qWRk&t=330s) / [Wyckoff e VSA 136:59-137:39](https://www.youtube.com/watch?v=fHxfr7aU7PA&t=8219s)

**Fabioの明言**

- 市場注文の90～95%がalgorithmicであっても、単一algorithmが方向を決めるわけではない。
- その瞬間の方向は、aggressive ordersの方向圧力とpassive ordersの吸収のinteractionから生まれる。
- Fabioは、それがどのalgorithmかは問わない。必要なのは相場上のedgeである。
- `institutional`という言葉自体は、論理の中で使わなければ何も意味しない。
- marketを動かすのは個人一人ではなく、注文・資金・流動性のcluster。

**この発言が上の15事例をどうまとめるか**

> Fabioの「大口」は、誰かを当てる概念ではない。相場を動かした攻撃、動かせなかった攻撃、それを止めた反対側、同価格への反復執行とreloadを、市場に現れた合成結果として読む概念である。

## 最終的に、画面の何を見ればよいか

| 観測する事実 | その後に必ず見る事実 | Fabioの判断 | 単体では判断できない理由 |
|---|---|---|---|
| 大きなexecuted marker | 攻撃方向へpriceが進んだか | 進めば攻撃側がrewarded | markerが大きくてもabsorbされ得る |
| 大きなexecuted marker | levelを抜けずwickで戻ったか | 進めなければ反対側のabsorption | 見えるmarkerの反対側が実質的に強い |
| 同価格の複数marker | 何回攻撃し、何回失敗したか | 反復失敗でabsorptionの信頼度上昇 | 同一主体でなくても市場状態として有効 |
| 大きなDelta / CVD | priceが同じ方向へfollowしたか | pressureとresultが揃ったときだけ方向確認 | CVD先行だけではFabio自身が不十分と明言 |
| 大きな未約定板数量 | 消費されたか、消えたか、reloadしたか | fill / reloadされれば実行意思の証拠が強まる | spoofingの可能性がある |
| 小さな板数量の反復reload | 同priceでの累積消費量 | iceberg / hidden liquidity | 一回の表示数量では累積規模が見えない |
| 一方のaggression | 反対側のeffortと比べ、resultはどちらへ偏ったか | resultが偏った側がbattleの勝者 | effortが同じでもresultは非対称になる |
| controlを示していた側の新規攻撃 | その攻撃が引き続きpriceを動かしたか | control継続ならposition維持 / scale | 過去の支配だけでは現在の支配を保証しない |
| 反対側のaggressionが現れた | controlを奪ったか、またabsorbされたか | 奪えばexit / stop trail、吸収されれば維持 | 反対marker一発では反転確定ではない |

## 証拠の限界

- この台帳は、Fabio本人の公式動画で説明された表示、数値、価格結果、判断、trade actionを記録した。
- 各markerの発注者名、口座、機関名、同一parent order性は確定しない。
- 色はplatform側で変更可能なため、色相だけで売買側を補完しない。
- Fabioの自動字幕は用語を誤認識する場合があるため、数字や専門用語は前後文脈と旧直接映像監査記録で照合した。
- 本台帳から得られるのは、「相場を動かす規模が何をしたか」であり、「誰がしたか」ではない。
