# Fabio公式動画70本全件監査 — 「相場を動かす規模」の認識と判断

> **具体的な判断場面を先に読む場合:**  
> `FABIO_CONCRETE_LARGE_PARTICIPANT_EVIDENCE_20260810.md`に、表示数値・発生順序・price result・Fabioの判断・trade actionが揃う16事例を重要度順で記録した。本文書は70本全件の証拠索引として使う。

- 監査日: 2026-08-10
- 対象: Fabio Valentini / Fabervaale本人の公式YouTube動画70本
- 母集団: Fabervaale ENG 13本 + Fabervaale 57本
- URL母集団: `FABIO_OFFICIAL_VIDEO_CATALOG_70_20260810.md`
- 確認方法: 70本全てのYouTube公式自動字幕を全文取得し、英語／イタリア語の候補語で全文走査した後、該当発言の前後文脈を動画別に再確認
- 調査対象: Fabioが、何を「相場を動かす規模」の跡と見なし、何を根拠に目先の支配側を判断するか
- 前提にしないもの: 特定人・特定機関の犯人探し、一件のparent orderの推定、特定BTC数量の閾値

## 1. 全70本を読んだ後の結論

Fabioが「大口」として捉えている中心は、特定の一人、一社、一口座ではない。

Fabio自身が、市場方向は単一アルゴリズムが決めるのではなく、**aggressive ordersの方向圧力とpassive ordersの吸収の相互作用が、その瞬間の方向を作る**と説明している。

Fabioが実際に読んでいるのは次の関係である。

1. どちら側から、どれだけの攻撃的な執行が入ったか。
2. その執行は、価格を実際に動かしたか。
3. 動かしたなら、攻撃側がresultを得た。
4. 動かせなかったなら、反対側に攻撃を吸収する規模がある。
5. 同じ価格で攻撃と失敗が繰り返されれば、吸収と保護の信頼度が上がる。
6. 表示数量が小さくても、同一価格へreloadされ続けるなら、累積規模は大きい。
7. どちら側が「battle」に勝ち、価格がどちらへ動きやすくなったかをpath of least resistanceとして判断する。

したがって、この70本から得られるFabio的な最大公約数は次である。

> **大口とは名前ではなく、相場を動かす規模、またはその規模の攻撃を受け止める規模が、執行と価格結果の関係として現れた状態である。**

## 2. Fabio発言の重要度順

以下の番号は動画の人気順ではない。「Fabioは大口をどう捉えているか」への直接性、説明の明確さ、実トレード判断への接続性を基準に、全70本から抽出した発言内容を並べた。日本語は逐語訳ではなく、前後文脈を保った要約である。

### 1. 方向を決めるのは「一人の犯人」ではなく、攻撃と吸収の相互作用

[Fondamenti di Orderflow 05:30-06:26](https://www.youtube.com/watch?v=YG_CzO8qWRk&t=330s)

- Fabioの発言: 注文の90～95%がアルゴリズムであっても、単一のアルゴリズムが方向を決めるとは考えない。
- Fabioの定義: その瞬間の方向は、aggressive ordersの方向圧力とpassive ordersの吸収の相互作用から生まれる。
- Fabioの態度: それがどのアルゴリズムかは問わない。必要なのは市場でedgeを得ることである。
- 重要性: 特定主体の同定ではなく、市場全体の力の合成結果を読むという、全70本の根になる発言。

### 2. 「institutional」というラベルだけでは何も説明しない。市場を動かすのはcluster

[Wyckoff e VSA 136:59-137:39](https://www.youtube.com/watch?v=fHxfr7aU7PA&t=8219s) / [Logiche di liquidità 08:49-09:44](https://www.youtube.com/watch?v=h8LWAU01598&t=529s)

- Fabioの発言: 「institutional」という言葉を付けるだけでは意味がない。
- 一人のstopや一人のretail traderが市場を動かすのではない。方向性を催化するのは注文・stop・流動性のclusterである。
- Fabioは、市場を動かす側を「一人の複合オペレータ」のように模型化するWyckoffのcomposite operatorを説明するが、これは実在の単独犯を指すのではない。
- 重要性: 「どこの誰か」より、市場を動かす規模がclusterとして現れたかを見るという直接証拠。

### 3. volumeはeffort、price resultはその注文が価格へ与えた実影響

[My Signature Orderflow Model 03:02-03:26](https://www.youtube.com/watch?v=Khgj5q1-ln8&t=182s) / [Fondamenti di Orderflow 02:10-02:27](https://www.youtube.com/watch?v=YG_CzO8qWRk&t=130s)

- Fabioの定義: volumeは市場へ入った注文量、resultはその注文が価格変動へ与えたimpact。
- 根拠: 約定量の大きさと、その後の価格変動を分離して見る。
- 重要性: Fabioの大口判断は「大きいプリントが出た」で終わらず、それが価格を動かしたかまでを一組の証拠とする。

### 4. 大きな攻撃が結果を得られなければ、反対側の規模が見える

[My Signature Orderflow Model 03:30-04:50](https://www.youtube.com/watch?v=Khgj5q1-ln8&t=210s) / [Tick Volume Approfonditi 31:49-32:21](https://www.youtube.com/watch?v=Uv93CqSinkQ&t=1909s)

- 根拠: huge volumeで同じfloorを攻撃してもwickしか作れず、continuationが出ない。
- Fabioの判断: 攻撃側の強さとは判断せず、passive participantsがその注文を吸収していると判断する。
- 別動画では、「大きな売りeffortで結果がゼロ」をabsorptionと説明する。
- 重要性: 目立つ大口マーカーの反対側に、より重要な受け止める力が隠れている場合を読む発言。

### 5. 攻撃量が同程度でも、結果が一方へ偏れば、そちらがbattleの勝者

[My Signature Orderflow Model 04:11-04:50](https://www.youtube.com/watch?v=Khgj5q1-ln8&t=251s)

- 根拠: buyersとsellersのaggressive effortは同程度だが、sellersは吸収され、buyersだけが上方向のresultを得る。
- Fabioの判断: effortの大きさが同じでも互角とは判断しない。価格結果が上へ大きくskewしているため、上方向継続の確率が高い。
- 重要性: 規模を絶対量だけではなく、競合する力と価格結果の偏りで判断する。

### 6. aggressionとは人数ではなく、不利な価格へも成行執行を続ける度合い

[Le origini dei concetti Smart Money 16:36-19:05](https://www.youtube.com/watch?v=Z7efPv0IfxU&t=996s)

- Fabioの発言: 多数派が売りたいから価格が下がるのではない。aggressionとは、たとえばsellersがより低い価格でも売る意思を持ち、執行すること。
- 根拠: 重いbulk of contractsが入れば、priceはvolumeのresultなので、チャートにreactionとして跡が残る。
- 重要性: アンケート的な予想人数や感情ではなく、実際に市場へ入った成行執行とその価格反応を見る。

### 7. 一定のeffortに対し、受動流動性の薄い方がpath of least resistance

[The Only Liquidity Guide 06:48-07:29](https://www.youtube.com/watch?v=FawPrRUGNpk&t=408s)

- Fabioの例: aggressive effortを50 contractsに固定し、現在価格の上側に273、下側に122のpassive ordersがある状態を比べる。
- Fabioの判断: 同じ攻撃量であれば、食べるべき受動流動性が少ない下方向がpath of least resistance。
- 重要性: 大口の攻撃量だけではなく、その先にある抵抗との相対関係で目先の動きやすさを判断する。

### 8. Big Tradesは大きなexecuted ordersの絞り込みだが、判断は予め選んだlocationとprice resultで完成する

[The Only Orderflow Guide 37:31-40:31](https://www.youtube.com/watch?v=Pz8f0wWW12M&t=2251s)

- Fabioの手順: まずprofile、VWAP、supply/demandなどで重要エリアを選ぶ。次にexecuted ordersをsizeでfilterし、big market participantsとlevelのinteractionだけを見る。
- short例の根拠: 72、61、60、62のexecuted effortが上へresultを得ず、反対のsellersは強い下方向resultを得た。
- long例の根拠: 105、その後101 contractsの攻撃が同じ下側levelを抜けず、複数回吸収された。
- Fabioの判断: マーカーの数字そのものより、事前location、反復、吸収、反対側のresultが揃ったことをentry根拠にする。

### 9. 表示8 contractsでも、同一価格へ補充され続ければ累積400～500になり得る

[The Only Liquidity Guide 09:56-10:25](https://www.youtube.com/watch?v=FawPrRUGNpk&t=596s) / [21:30-22:33](https://www.youtube.com/watch?v=FawPrRUGNpk&t=1290s)

- 根拠: 板に見える8 contractsが消費されるたびにalgorithmでreloadされる。
- Fabioの判断: 一度に見える数量は8でも、累積は400または500になり得る。これがhidden liquidity / iceberg。
- institutional executionの例では、large amount of ordersをfillするため、上昇中に複数のicebergを置き、必要量が執行されたlevelから価格がcollapseする。
- 重要性: 一件の表示数量ではなく、時間を通じた反復執行と累積効果から規模を読む。

### 10. 大きな参加者は注文を分割し、執行のための流動性clusterを必要とする

[Logica e natura delle mutazioni 08:07-12:16](https://www.youtube.com/watch?v=0qo-x2_E6GA&t=487s) / [Meccanica di mercato pt.1 14:34-14:59](https://www.youtube.com/watch?v=7-r379fLris&t=874s)

- Fabioの発言: big playersは数十亿級を一価格へ一度に入れられないため、注文を分割し、時間をかけてaccumulation / distributionを作る。
- 根拠: 重い執行はslippageと不利なaverage fillを生む。そのため、相手注文が集まるliquidity pocket / clusterが必要になる。
- 重要性: 一つの大きなプリントだけを探すと、分割執行とaccumulationの跡を逃す。

### 11. CVDの圧力先行だけでは入らず、Big Tradesとprice follow-throughを待つ

[My Top 3 Trades from the Competition 02:05-03:34](https://www.youtube.com/watch?v=0jM5Y31YJak&t=125s) / [05:22-06:52](https://www.youtube.com/watch?v=0jM5Y31YJak&t=322s)

- 根拠: CVDはbreakout前から大きな下方向pressureを示す。
- Fabioの判断: これはfirst milestoneだが、それだけでは不十分。Big Tradesをsecond confirmationとし、volumeのfollow-upとpriceの下方向confirmationが出た時点でshortする。
- 管理: Big Tradesがpriceをそれ以上下へpushしなくなったら利確し、再びBig Tradesとbreakdownが揃ったら再entryする。
- 重要性: 圧力、大きな約定、価格結果の三つを分離して確認する。

### 12. 支配側の判断はentryだけでなく、scale、break-even、trail、exitまで一貫して使う

[How I did 20R in one NQ Session 01:42-08:43](https://www.youtube.com/watch?v=8CWKfoSJu3c&t=102s) / [My Best Trading Session 03:36-05:32](https://www.youtube.com/watch?v=fZlNGWvd2Ko&t=216s)

- Fabioの判断: absorbed buyersとrewarded sellersが揃えばsellersがauctionをcontrolしている。reloadと追加攻撃を確認しながらpositionを維持する。
- 管理根拠: 反対側のaggressive buyersがcontrolを取り戻す可能性が現れれば、profit stopで市場から出る。
- 重要性: 「大口を見つける」のではなく、目前のcontrolが続いているかを連続的に読む。

### 13. 観測スケールは市場活動と時間帯の文脈から切り離せない

[Watch me Manage a -10,000$ Session 01:13-01:26](https://www.youtube.com/watch?v=jasv3L-d8ZE&t=73s) / [The Simplest Orderflow Model 01:28-01:44](https://www.youtube.com/watch?v=cUTsoU-15Tc&t=88s) / [Wyckoff e VSA 113:24-115:27](https://www.youtube.com/watch?v=fHxfr7aU7PA&t=6804s)

- Fabioの実況: その日はvolumeが多いため、より大きなfilterが必要だと発言する。
- session文脈: New Yorkは日中で最もvolumeとinterestが集まり、buyersとsellersの最も強いbattleが起きると説明する。
- 別動画では、高volatility / 高liquidityの時間帯としてLondonと9:00、New York側の14:00付近（各30分程度の幅）を統計的文脈として示す。
- 証拠境界: Fabioが公開動画で明言したのは「出来高の多い日はより大きなfilter」とsession文脈である。全商品共通の計算式までは公開していない。

### 14. 板の大きな表示だけでは証拠不十分。spoofingと未約定の可能性を残す

[The Only Liquidity Guide 08:58-10:00](https://www.youtube.com/watch?v=FawPrRUGNpk&t=538s) / [30:12-30:30](https://www.youtube.com/watch?v=FawPrRUGNpk&t=1812s)

- Fabioの警告: 大きなbid reloadは大きな参加の情報になるが、spoofingに使われることもある。
- fresh liquidity / reloadが表示されても、実際にfillされる保証はない。
- 重要性: 未約定の意思表示と、実際のexecuted effort、反復reload、price resultを混同しない。

## 3. Fabioの判断と根拠を一つの流れにする

以下は独自の新規indicator定義ではない。上位発言と実況取引に繰り返し現れる共通順序をまとめたものである。

1. **locationを決める**  
   Profile、VWAP、VAH/VAL、LVN、Initial Balance、previous swing、supply/demandなどで詳細に見る価格領域を決める。location自体は大口の証拠ではない。
2. **effortを測る**  
   Deep Trades、Footprint、Delta/CVD、DOM、Heatmap、iceberg detectorにより、どちら側のexecuted aggression、passive liquidity、reloadが出たかを見る。
3. **price resultを照合する**  
   攻撃と同じ方向へpriceが進んだか、wickだけで戻されたか、価格帯を抜けられなかったかを見る。
4. **battleの勝者を決める**  
   rewarded aggressionとabsorbed aggressionを分け、一方のresultだけが強いなら、そちらがcontrolを持つと判断する。
5. **反復と継続性を見る**  
   同じlevelで攻撃が繰り返し失敗したか、reloadが継続したか、新しいaggressionが同じ方向へ追加されたかを見る。
6. **trade actionへ接続する**  
   pressure、big executions、price confirmationが揃えた時点でentry / scale / re-entryし、level failure、opposite control、exhaustion、result消失でbreak-even / trail / profit taking / exitする。

## 4. 70本全件の内容監査表

「直接」は大きな市場参加の認識または判断を直接説明するもの。「補助」はその機構・文脈・応用を支えるもの。「直接発言なし」は、字幕全文に大口判断の直接証拠がなかったものであり、動画の価値を評価したものではない。

### Fabervaale ENG 13本

| No. | 動画 | 大口認識に関する実質内容 |
|---:|---|---|
| ENG-01 | [5 Edges that refuse to die.](https://www.youtube.com/watch?v=StaphlRH8NQ) | 補助。institutional execution、delayed price response、volatilityの研究例。Fabioのイントラデイ大口認識の直接定義はない。 |
| ENG-02 | [Exposing my Risk Management Protocol](https://www.youtube.com/watch?v=LQvv5xgy_ik) | 直接発言なし。リスク、執行回数、slippage、ヘッジファンドの一般論が中心。 |
| ENG-03 | [The Only Liquidity Guide You'll Ever Need](https://www.youtube.com/watch?v=FawPrRUGNpk) | 直接。[06:48](https://www.youtube.com/watch?v=FawPrRUGNpk&t=408s) path of least resistance、[08:58](https://www.youtube.com/watch?v=FawPrRUGNpk&t=538s) bid reload、[10:00](https://www.youtube.com/watch?v=FawPrRUGNpk&t=600s) iceberg、[17:10](https://www.youtube.com/watch?v=FawPrRUGNpk&t=1030s) Big Trades + positive price result、[22:13](https://www.youtube.com/watch?v=FawPrRUGNpk&t=1333s) institutional fractional execution。 |
| ENG-04 | [My Signature Orderflow Model](https://www.youtube.com/watch?v=Khgj5q1-ln8) | 直接・中心証拠。[01:17](https://www.youtube.com/watch?v=Khgj5q1-ln8&t=77s) volume/result、[03:02](https://www.youtube.com/watch?v=Khgj5q1-ln8&t=182s) effort/resultの定義、[03:30](https://www.youtube.com/watch?v=Khgj5q1-ln8&t=210s) huge volume攻撃と吸収、[04:11](https://www.youtube.com/watch?v=Khgj5q1-ln8&t=251s) 同程度effortと結果の偏り。 |
| ENG-05 | [The Simplest Orderflow Trading Model](https://www.youtube.com/watch?v=cUTsoU-15Tc) | 直接・応用。[01:28](https://www.youtube.com/watch?v=cUTsoU-15Tc&t=88s) NYの最大volume、[02:55](https://www.youtube.com/watch?v=cUTsoU-15Tc&t=175s) battleに勝ったbiggest participants、[07:30](https://www.youtube.com/watch?v=cUTsoU-15Tc&t=450s) aggressive sellersのzero result、[13:00](https://www.youtube.com/watch?v=cUTsoU-15Tc&t=780s) 反復吸収とpressure build。 |
| ENG-06 | [The Only Orderflow Guide You'll Ever Need](https://www.youtube.com/watch?v=Pz8f0wWW12M) | 直接・中心証拠。[37:31-40:31](https://www.youtube.com/watch?v=Pz8f0wWW12M&t=2251s) executed ordersを大口に絞り、事前location、absorption、price resultでshort / longを判断する。 |
| ENG-07 | [How I did 20R in one NQ Session](https://www.youtube.com/watch?v=8CWKfoSJu3c) | 直接・実トレード。[01:42](https://www.youtube.com/watch?v=8CWKfoSJu3c&t=102s) absorbed buyers / rewarded sellers、[04:19](https://www.youtube.com/watch?v=8CWKfoSJu3c&t=259s) reload後のseller control、[07:59](https://www.youtube.com/watch?v=8CWKfoSJu3c&t=479s) big buy/sell ordersのinteractionをstop管理へ使用。 |
| ENG-08 | [How To Find The BEST Entry Zones](https://www.youtube.com/watch?v=06R-ebyOhDI) | 直接・実トレード。[02:07](https://www.youtube.com/watch?v=06R-ebyOhDI&t=127s) Big Tradesに支えられたvolumeとreload予想、[05:23](https://www.youtube.com/watch?v=06R-ebyOhDI&t=323s) candle bodyのDeep Trades、following result、absorbed buyersからseller勝利を判断。 |
| ENG-09 | [Winning the Mental Game of Trading](https://www.youtube.com/watch?v=0KyIEdvVKMQ) | 直接発言なし。心理、プロセス、law of large numbersが中心。 |
| ENG-10 | [My Best Trading Session of the Month](https://www.youtube.com/watch?v=fZlNGWvd2Ko) | 直接・実トレード。[01:33](https://www.youtube.com/watch?v=fZlNGWvd2Ko&t=93s) buyer control + absorbed sellers、[03:36](https://www.youtube.com/watch?v=fZlNGWvd2Ko&t=216s) Big Tradesとcontrol、[04:40](https://www.youtube.com/watch?v=fZlNGWvd2Ko&t=280s) effortがあってもresultなし、[05:11](https://www.youtube.com/watch?v=fZlNGWvd2Ko&t=311s) control changeで利確。 |
| ENG-11 | [Watch me Manage a -10.000$ trading Session](https://www.youtube.com/watch?v=jasv3L-d8ZE) | 直接・実況。[01:13](https://www.youtube.com/watch?v=jasv3L-d8ZE&t=73s) big buyersが吸収、当日はvolumeが多いためより大きなfilterが必要と発言。[06:33](https://www.youtube.com/watch?v=jasv3L-d8ZE&t=393s) 下方攻撃の継続と価格pushを照合。 |
| ENG-12 | [3 Order-flow Trading Tricks Exposed!](https://www.youtube.com/watch?v=o-w5Gxss6T0) | 直接・中心証拠。[00:21](https://www.youtube.com/watch?v=o-w5Gxss6T0&t=21s) small tradersとbig/informed moneyのfilter、[02:03](https://www.youtube.com/watch?v=o-w5Gxss6T0&t=123s) 2,800 volume / +599 deltaと吸収、[05:58](https://www.youtube.com/watch?v=o-w5Gxss6T0&t=358s) CVDとprice result、[07:47](https://www.youtube.com/watch?v=o-w5Gxss6T0&t=467s) huge pressureのzero result。 |
| ENG-13 | [My Top 3 Trades from the Competition](https://www.youtube.com/watch?v=0jM5Y31YJak) | 直接・中心証拠。[02:05](https://www.youtube.com/watch?v=0jM5Y31YJak&t=125s) CVD pressure、[02:45](https://www.youtube.com/watch?v=0jM5Y31YJak&t=165s) それだけでは不十分、[02:56](https://www.youtube.com/watch?v=0jM5Y31YJak&t=176s) Big Tradesとprice follow-upを追加、[05:22](https://www.youtube.com/watch?v=0jM5Y31YJak&t=322s) push消失でexit。 |

### Fabervaale 57本

| No. | 動画 | 大口認識に関する実質内容 |
|---:|---|---|
| ITA-01 | [Cosa Ho Imparato Dai Migliori Trader al Mondo](https://www.youtube.com/watch?v=d0hathR3vpQ) | 補助。orderflow / Big Tradesをoption flow、profile、footprintとともにconfluenceの一つとして扱うが、大口認識の直接定義はない。 |
| ITA-02 | [L'UNICA Guida sulla Gestione del Rischio](https://www.youtube.com/watch?v=mU66hRONvts) | 直接発言なし。リスク管理が中心。 |
| ITA-03 | [La Trappola che Fa Fallire il 90% dei Trader](https://www.youtube.com/watch?v=Ne0KsIVfsdQ) | 直接発言なし。トレーダー心理と結果の話が中心。 |
| ITA-04 | [Guida Completa all'Intermarket Analysis](https://www.youtube.com/watch?v=lxl8GvHO9bU) | 直接発言なし。マクロとintermarketが中心。 |
| ITA-05 | [Perchè le Strategie di Trading non funzionano](https://www.youtube.com/watch?v=6vGpW7e3I2Y) | 補助。Footprint aggressionとlow-volume nodeの話はあるが、大口定義ではない。 |
| ITA-06 | [Scalping sul Futures di Nasdaq su Deepcharts](https://www.youtube.com/watch?v=SouybZZEST8) | 直接・実トレード。[00:41](https://www.youtube.com/watch?v=SouybZZEST8&t=41s) breakout中のBig Trades、[01:21](https://www.youtube.com/watch?v=SouybZZEST8&t=81s) 複数Big Tradesで再確認、[01:52](https://www.youtube.com/watch?v=SouybZZEST8&t=112s) follow-throughとstaircase、[03:21](https://www.youtube.com/watch?v=SouybZZEST8&t=201s) どちらがdomainかを判断。 |
| ITA-07 | [Price Action Series - Episodio 4](https://www.youtube.com/watch?v=g4992qw4aYs) | 補助。seller aggressionとabsorptionのメカニズム。規模判定の直接説明ではない。 |
| ITA-08 | [Price Action Series 2025 - Episodio 3](https://www.youtube.com/watch?v=WGS09v2hQSc) | 補助・注意点。buyer aggressionをpassive sideが吸収する説明。繰り返すパターンを即座に「institutions」と決めつけないよう注意。 |
| ITA-09 | [Price Action Series 2025 - Episodio 2](https://www.youtube.com/watch?v=75UptlDYjJQ) | 直接寄り。強いseller volume / aggressionが入ってもpriceが動かない場合をabsorptionと判断。 |
| ITA-10 | [Price Action Series 2025 - Episodio 1](https://www.youtube.com/watch?v=h1dTflLC6q8) | 補助。priceを動かしたseller aggression、institutional execution、equilibrium / accumulation / distributionの一般説明。 |
| ITA-11 | [Comprendere la Narrativa di Mercato col Modello COT](https://www.youtube.com/watch?v=NLclwfxbd-s) | 補助。COTで機関のpositioningを読むマクロの話。イントラデイ大口観測ではない。 |
| ITA-12 | [Corso completo di Auction Market Theory](https://www.youtube.com/watch?v=Ur8-c-bDGqU) | 補助。COT、大きなoperators、asset managersの20,000 contracts delta等。マクロpositioningの説明が中心。 |
| ITA-13 | [Orderflow Series 2025](https://www.youtube.com/watch?v=8nEDJ5npS1M) | 直接・中心証拠。[58:21](https://www.youtube.com/watch?v=8nEDJ5npS1M&t=3501s) NASDAQを動かすのは視聴者ではなくより大きいaggressive operators、[64:44](https://www.youtube.com/watch?v=8nEDJ5npS1M&t=3884s) buyersがpunch to the wallをしてresultなし、[67:57](https://www.youtube.com/watch?v=8nEDJ5npS1M&t=4077s) +104 / +75 deltaと吸収、[75:02](https://www.youtube.com/watch?v=8nEDJ5npS1M&t=4502s) important operatorsの跡とsession timing。 |
| ITA-14 | [Strategia Operativa News](https://www.youtube.com/watch?v=LvVtCVKZtmk) | 補助。news中のaggressive buyersの吸収、round levelのabsorption、effort/result。Asian sessionは結果が劣るとする文脈もある。 |
| ITA-15 | [Approccio Global Macro 1.0](https://www.youtube.com/watch?v=mT-e9vHQUWQ) | 直接発言なし。ファンド規模の一般論はあるが、注文フローでの認識法ではない。 |
| ITA-16 | [Bank Report Commentary](https://www.youtube.com/watch?v=2PnHBLeFJjI) | 直接発言なし。銀行reportとinstitutional viewsが中心。 |
| ITA-17 | [Il potere dei dati](https://www.youtube.com/watch?v=pfTd_pzWCk0) | 直接発言なし。data validationとプロセスの話。 |
| ITA-18 | [Analisi Volumetrica Pratica](https://www.youtube.com/watch?v=ZrfwJBaI07Y) | 直接。[00:00](https://www.youtube.com/watch?v=ZrfwJBaI07Y&t=0s) pressureとcontractsを数値化、[15:00](https://www.youtube.com/watch?v=ZrfwJBaI07Y&t=900s) executed short ordersとaggressionの濃淡、[15:58](https://www.youtube.com/watch?v=ZrfwJBaI07Y&t=958s) buyer aggressionにprice resultなし、[23:55](https://www.youtube.com/watch?v=ZrfwJBaI07Y&t=1435s) absorption / exhaustion / iceberg。 |
| ITA-19 | [Fondamenti di Orderflow](https://www.youtube.com/watch?v=YG_CzO8qWRk) | 直接・最中心証拠。[05:30](https://www.youtube.com/watch?v=YG_CzO8qWRk&t=330s) 単一algorithmでなくaggressive/passive interactionが方向を作る、[22:45](https://www.youtube.com/watch?v=YG_CzO8qWRk&t=1365s) market ordersとlimit cluster、[44:40](https://www.youtube.com/watch?v=YG_CzO8qWRk&t=2680s) aggressionに実resultが必要、[46:20](https://www.youtube.com/watch?v=YG_CzO8qWRk&t=2780s) color=aggression / candle=result。 |
| ITA-20 | [Protocollo di validazione dell'Edge](https://www.youtube.com/watch?v=k7n6U4oVgr4) | 直接発言なし。edgeの統計検証が中心。 |
| ITA-21 | [L'arte del ragionamento probabilistico](https://www.youtube.com/watch?v=mnojKQ4d_7g) | 直接発言なし。確率思考が中心。 |
| ITA-22 | [Meccanica di Mercato pt.2](https://www.youtube.com/watch?v=C6PAcbpPYT8) | 直接。[10:18](https://www.youtube.com/watch?v=C6PAcbpPYT8&t=618s) 市場は需給・contracts・buy/sell pressureのinteraction、[28:37](https://www.youtube.com/watch?v=C6PAcbpPYT8&t=1717s) hidden limit orders=iceberg、[29:14](https://www.youtube.com/watch?v=C6PAcbpPYT8&t=1754s) 大機関の10,000 contracts執行が板流動性を食べ価格を動かす例。 |
| ITA-23 | [Meccanica di mercato pt.1](https://www.youtube.com/watch?v=7-r379fLris) | 直接寄り。[13:24](https://www.youtube.com/watch?v=7-r379fLris&t=804s) 大きなparticipantsのpressure、[14:13](https://www.youtube.com/watch?v=7-r379fLris&t=853s) retailとinstitutional/fundの執行差、[14:48](https://www.youtube.com/watch?v=7-r379fLris&t=888s) order splitting / slippage、[22:32](https://www.youtube.com/watch?v=7-r379fLris&t=1352s) 市場を動かせるsizeをinstitutional categoryの特徴と説明。 |
| ITA-24 | [La Trappola delle Aspettative](https://www.youtube.com/watch?v=SH-H6AZe-2o) | 直接発言なし。心理的期待の話。 |
| ITA-25 | [Gestione del Rischio e validazione](https://www.youtube.com/watch?v=Ole1G-_P3ss) | 直接発言なし。リスクと検証が中心。 |
| ITA-26 | [Masterclass Price Action](https://www.youtube.com/watch?v=FIOKH2t0lEU) | 補助。tick volumeでeffort/resultを補完する話、Footprintのabsorption / exhaustionの紹介。 |
| ITA-27 | [Le differenze tra VSA e Orderflow](https://www.youtube.com/watch?v=692OdHaZnRU) | 直接。[01:42](https://www.youtube.com/watch?v=692OdHaZnRU&t=102s) effort/resultの起源、[04:36](https://www.youtube.com/watch?v=692OdHaZnRU&t=276s) 高volume・大きな値幅の後に小さい実体ならresultは維持されなかった、[05:14](https://www.youtube.com/watch?v=692OdHaZnRU&t=314s) volumeは半分の情報でprice resultとの照合が必要。 |
| ITA-28 | [I benefici dell'analisi volumetrica](https://www.youtube.com/watch?v=yrGkrE5qgB4) | 直接寄り。[03:08](https://www.youtube.com/watch?v=yrGkrE5qgB4&t=188s) priceはeffect、orderflowはcause、[05:30](https://www.youtube.com/watch?v=yrGkrE5qgB4&t=330s) price-levelごとのaggression / absorption / exhaustion / participation、[06:07](https://www.youtube.com/watch?v=yrGkrE5qgB4&t=367s) highへのaggressionがzero response。[07:47](https://www.youtube.com/watch?v=yrGkrE5qgB4&t=467s) contractsの実数は観測者によらず同じとする客観性の説明。 |
| ITA-29 | [Dinamiche di Profile e Auction Market Theory](https://www.youtube.com/watch?v=2h5TVfqtXXo) | 補助。[03:14](https://www.youtube.com/watch?v=2h5TVfqtXXo&t=194s) bulk of volumeとtime-at-priceの違い、[10:52](https://www.youtube.com/watch?v=2h5TVfqtXXo&t=652s) Deltaをaggressive buyers/sellersの腕相撲と説明、[31:57](https://www.youtube.com/watch?v=2h5TVfqtXXo&t=1917s) 強いsell pressureとprofileを照合。 |
| ITA-30 | [Logica e natura delle mutazioni](https://www.youtube.com/watch?v=0qo-x2_E6GA) | 直接。[08:07](https://www.youtube.com/watch?v=0qo-x2_E6GA&t=487s) big playersのorder splitting、[08:46](https://www.youtube.com/watch?v=0qo-x2_E6GA&t=526s) fundは一価格で全量執行できずaccumulationが必要、[10:03](https://www.youtube.com/watch?v=0qo-x2_E6GA&t=603s) 個人のstopではなくclusterを探す、[11:27](https://www.youtube.com/watch?v=0qo-x2_E6GA&t=687s) slippage / average fill。 |
| ITA-31 | [Strengthening the Mindset in Trading](https://www.youtube.com/watch?v=amOPyBvuANU) | 直接発言なし。mindset、process orientation、トレーニングが中心。 |
| ITA-32 | [Fractality and Fakeout](https://www.youtube.com/watch?v=_FW5rKScPyY) | 補助。aggression、absorption、どちらがzoneをdominateするかをprice actionで扱う。規模の直接定義ではない。 |
| ITA-33 | [Elementi di Mappatura di mercato](https://www.youtube.com/watch?v=icRGUv37Y5s) | 補助。[08:14](https://www.youtube.com/watch?v=icRGUv37Y5s&t=494s) aggressive buyersが反対pressureを超えcontrol、[25:25](https://www.youtube.com/watch?v=icRGUv37Y5s&t=1525s) 契約と攻撃意思の大きい場所、[43:19](https://www.youtube.com/watch?v=icRGUv37Y5s&t=2599s) pre-NYとliquidity spike。 |
| ITA-34 | [Identify the Spring phase in session](https://www.youtube.com/watch?v=BeJQWB1xt_s) | 直接寄り。[01:14](https://www.youtube.com/watch?v=BeJQWB1xt_s&t=74s) institutionsが個人のstopを狙うのではなくliquidity clusterを見る、[07:49](https://www.youtube.com/watch?v=BeJQWB1xt_s&t=469s) institutions/funds間のbattle、[08:50](https://www.youtube.com/watch?v=BeJQWB1xt_s&t=530s) volatilityは大きなprice variation、[09:55](https://www.youtube.com/watch?v=BeJQWB1xt_s&t=595s) NY時間帯のliquidation spikes。 |
| ITA-35 | [Masterclass Indices and Cycles](https://www.youtube.com/watch?v=VmG7ED-X_2Q) | 補助。商品ごとの平均変動幅、profileで最もcontractsとparticipantsが集まるlevelを説明。直接のBig Trades認識ではない。 |
| ITA-36 | [Come ottimizzare periodicamente una strategia](https://www.youtube.com/watch?v=5fqhHNtAvtY) | 直接発言なし。戦略最適化、リスク、時間filterが中心。 |
| ITA-37 | [Costruire sicurezza con matematica e gestione del rischio](https://www.youtube.com/watch?v=rghvZL4iPDg) | 直接発言なし。リスクと数学が中心。 |
| ITA-38 | [VSA Logic and Fundamentals of Auction Market Theory](https://www.youtube.com/watch?v=BHV0n3PV-0w) | 直接寄り。[08:25](https://www.youtube.com/watch?v=BHV0n3PV-0w&t=505s) market forcesとparticipation、[09:43](https://www.youtube.com/watch?v=BHV0n3PV-0w&t=583s) swing間のparticipation比較、[11:37](https://www.youtube.com/watch?v=BHV0n3PV-0w&t=697s) structure break前のabove-average participation、[14:28](https://www.youtube.com/watch?v=BHV0n3PV-0w&t=868s) 強い反対介入と元支配側のparticipation failureの二段確認。 |
| ITA-39 | [Le origini dei concetti Smart Money](https://www.youtube.com/watch?v=Z7efPv0IfxU) | 直接・中心証拠。[15:01](https://www.youtube.com/watch?v=Z7efPv0IfxU&t=901s) 「institutional」ラベル流行への批判、[16:36](https://www.youtube.com/watch?v=Z7efPv0IfxU&t=996s) 人数ではなくaggression、[18:42](https://www.youtube.com/watch?v=Z7efPv0IfxU&t=1122s) heavy bulk of contractsはprice reactionを残す。 |
| ITA-40 | [Forex Vs Futures : Pro e Contro](https://www.youtube.com/watch?v=wak-tqEH8RE) | 補助。futuresとCFDのliquidity / centralized dataの違い、volumetric platformの必要性。大口判断の直接発言は少ない。 |
| ITA-41 | [Pillole di valore - Correlazioni Approfondite](https://www.youtube.com/watch?v=mw1ty195nHA) | 直接発言なし。BTCの機関holding、相関、relative strengthが中心。 |
| ITA-42 | [Pillole di valore - Riprogrammazione Mentale](https://www.youtube.com/watch?v=Ut2dUlGx1Io) | 直接発言なし。心理とprocessが中心。 |
| ITA-43 | [Value Nuggets - Advanced Operational Management](https://www.youtube.com/watch?v=yVSWUrhpYRk) | 補助。[41:09](https://www.youtube.com/watch?v=yVSWUrhpYRk&t=2469s) 個人では動かせない市場をinstitutionsが動かすと説明。主題はposition / risk management。 |
| ITA-44 | [Pillole di valore - Tick Volume Approfonditi](https://www.youtube.com/watch?v=Uv93CqSinkQ) | 直接。[08:00](https://www.youtube.com/watch?v=Uv93CqSinkQ&t=480s) tick pressureでaggression / participationを読む、[30:32](https://www.youtube.com/watch?v=Uv93CqSinkQ&t=1832s) absorptionの定義、[31:49](https://www.youtube.com/watch?v=Uv93CqSinkQ&t=1909s) 大きなeffort・結果ゼロ、[42:02](https://www.youtube.com/watch?v=Uv93CqSinkQ&t=2522s) price + volume breakout evidence。 |
| ITA-45 | [Pillole di valore - Richard Wyckoff Deep Dive](https://www.youtube.com/watch?v=wSTDVu84O4w) | 直接寄り。[10:40](https://www.youtube.com/watch?v=wSTDVu84O4w&t=640s) operatorsのeffortとresult、[28:21](https://www.youtube.com/watch?v=wSTDVu84O4w&t=1701s) demand/supplyとeffort/result、[30:09](https://www.youtube.com/watch?v=wSTDVu84O4w&t=1809s) volume/priceの関係がabsorption情報になる、[34:42](https://www.youtube.com/watch?v=wSTDVu84O4w&t=2082s) composite operatorの概念。 |
| ITA-46 | [Pillole di valore - Wolfe Waves](https://www.youtube.com/watch?v=bpaPtMGD3tY) | 補助。momentum / aggression、institution/fund間のbattle、BTCの大口portfolio exposureを扱うが、orderflowでの直接定義ではない。 |
| ITA-47 | [Pillole di valore - Costruire una strategia da zero Pt.4](https://www.youtube.com/watch?v=1BNCEe0GU7I) | 直接発言なし。戦略構築、session / trigger / news filterが中心。 |
| ITA-48 | [Pillole di valore - Logiche di liquidità](https://www.youtube.com/watch?v=h8LWAU01598) | 直接・中心証拠。[06:09](https://www.youtube.com/watch?v=h8LWAU01598&t=369s) composite operatorは市場を動かすheavy sideの概念、[06:54](https://www.youtube.com/watch?v=h8LWAU01598&t=414s) 大規模positionは分割執行が必要、[08:49](https://www.youtube.com/watch?v=h8LWAU01598&t=529s) 個人のstopではなくclusterが方向を催化、[28:49](https://www.youtube.com/watch?v=h8LWAU01598&t=1729s) futuresでは実liquidity clusterとabsorptionを直接照合。 |
| ITA-49 | [Value Pills - Building a Strategy from Scratch Part 3](https://www.youtube.com/watch?v=7cZQzbeDNME) | 補助。[22:14](https://www.youtube.com/watch?v=7cZQzbeDNME&t=1334s) priceはvolumeから生じる、[30:10](https://www.youtube.com/watch?v=7cZQzbeDNME&t=1810s) compression中のdominanceを判断。主題は戦略構築。 |
| ITA-50 | [Value Pills - Building a Strategy from Scratch Part 2](https://www.youtube.com/watch?v=CWXbjQ8bejA) | 補助。方向pressure、demand/supply、session liquidityの戦略化。大口の直接定義はない。 |
| ITA-51 | [Value Pills - Building a Strategy from Scratch](https://www.youtube.com/watch?v=2mMKsPwInZo) | 補助。session aggression、pressure、compression、buyers/sellers dominanceを戦略ルールへ接続。 |
| ITA-52 | [Value Nuggets - COT Report and Institutional Reversals](https://www.youtube.com/watch?v=RIn9tBF-JlA) | 補助。[23:07](https://www.youtube.com/watch?v=RIn9tBF-JlA&t=1387s) 市場そのもを作る規模のfund/institution、[64:09](https://www.youtube.com/watch?v=RIn9tBF-JlA&t=3849s) institutional orderflowへのprice reaction。週次COTが主題で、イントラデイBig Tradesとは分ける。 |
| ITA-53 | [Pillole di valore - Wyckoff e VSA](https://www.youtube.com/watch?v=fHxfr7aU7PA) | 直接・中心証拠。[70:40](https://www.youtube.com/watch?v=fHxfr7aU7PA&t=4240s) 高volumeでpriceが動かない=absorption、[76:33](https://www.youtube.com/watch?v=fHxfr7aU7PA&t=4593s) strong effort / no result、[113:24](https://www.youtube.com/watch?v=fHxfr7aU7PA&t=6804s) 高volatility/liquidity時間、[136:59](https://www.youtube.com/watch?v=fHxfr7aU7PA&t=8219s) institutionalだけでは無意味、市場はclusterが動かす。 |
| ITA-54 | [Valuable Insights - Market Structure](https://www.youtube.com/watch?v=y3M3EA451CM) | 補助。[10:44](https://www.youtube.com/watch?v=y3M3EA451CM&t=644s) buyers/sellers pressureとcontinuation、[12:36](https://www.youtube.com/watch?v=y3M3EA451CM&t=756s) wickをabsorption / buyers step-inと解釈、[75:35](https://www.youtube.com/watch?v=y3M3EA451CM&t=4535s) dominant volumetric pressureの維持。 |
| ITA-55 | [Pillole di Biohacking - Wim Hof](https://www.youtube.com/watch?v=AsPqySEzwx8) | 関連発言なし。biohackingの動画。 |
| ITA-56 | [The best TradingView features!](https://www.youtube.com/watch?v=JmPHrca3iRg) | 補助。[16:32](https://www.youtube.com/watch?v=JmPHrca3iRg&t=992s) 価格の固定entry/exitではなくmarket pressureで入退出を判断する例。大口認識の主題ではない。 |
| ITA-57 | [Motivation - Fabervaale Podcast](https://www.youtube.com/watch?v=DfD7Ye2MI9Y) | 関連発言なし。motivationの動画。 |

## 5. 公開動画から確定できることと、確定できないこと

### 確定できる

- Fabioは、単一主体ではなく、aggressive pressureとpassive absorptionの相互作用から方向を判断する。
- volume / contractsをeffort、price movementをresultとして分ける。
- 大きな攻撃が価格を動かせば攻撃側の強さ、動かせなければ反対側の吸収規模を見る。
- 表示数量より、同価格への反復reloadと累積執行を重視する。
- Big Trades、Footprint、Delta/CVD、DOM / Heatmap、iceberg detectorは別々の観測手段であり、どれか一つだけで最終判断しない。
- pressure、big executions、price follow-throughが揃った場合にentryし、result消失やopposite controlで管理・退出する。
- 当日のvolumeが多い場合、より大きなfilterが必要と発言している。

### 公開動画だけでは確定できない

- markerを発生させた個人、口座、銀行、fund、market makerの身元。
- 時刻の異なる複数markerが同一主体または同一parent orderであること。
- 全商品・全venue・全sessionで共通するBig Tradesの絶対数量。
- Fabioのproprietary Deep Trades / Deep Effort modelの全計算式、全threshold、全normalization方法。
- 板の大きな表示が実際にfillされること。
- CVD、Delta、Big Trades marker、VWAP、POCのどれか一つだけから、大口の方向を確定すること。

## 6. 字幕と映像の証拠境界

- 70本全ての公式自動字幕は取得済み。
- イタリア語自動字幕には、Deep Trades / Order Flow / absorption / effort-result等の英語用語の誤認識が一部ある。本報告は単語一致ではなく前後文脈で判断した。
- 数値はFabioの発言または旧直接映像監査で確認済みの表示値だけを記録した。
- 「直接発言なし」は、大口判断の証拠が見つからなかったという調査結果であり、動画を視聴していないという意味ではない。
