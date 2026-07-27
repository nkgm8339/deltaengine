# Order Flow Trading 世界資料再学習・DeltaEngine再設計判断 report

作成日: 2026-07-26 JST  
状態: **調査報告。実装仕様・採用承認ではない。**  
対象: Binance BTCUSDT USDⓈ-Mの注文フロー観測を、HFM BTCUSDrの意思決定・執行へ使うDeltaEngine

## 0. 結論

現行の「88 Hookを較正し、50 Triggerの組合せを発火させる」という設計を、そのまま
注文フロートレード・システムとして完成させることはできない。

理由は三つある。

1. 88項目には、生データ上の観測、派生Feature、市場参加者についての推測、価格位置、
   regime、執行可否が混在している。88個すべてが同じ意味のHookではない。
2. 現行50 Triggerの多くは「条件の組合せ」であり、事前に武装されたStrategy、
   接近過程、entry timing、注文方法、無効化、約定後管理を持たない。
3. Binanceで観測するperpetual CLOBと、実際に注文するHFM BTCUSDrは同一venue・同一order
   bookではない。Binance上の証拠が正しくても、HFMで同じ価格・流動性・約定を得られるとは
   限らない。

世界の市場マイクロストラクチャ研究と実務資料を突き合わせると、正しい順序は次である。

```text
市場状態・場所・仮説からStrategyを武装
    ↓
価格が場所へ近づく経路と注文フロー証拠でStrategy状態を逐次更新
    ↓
Strategy固有のTriggerがentry可能状態を作る
    ↓
執行venueの価格・spread・latency・slippageを通して注文方法を決める
    ↓
約定後も同じStrategy instanceがfollow-through、失敗、exitを管理
    ↓
全候補・見送り・約定をepisodeとして保存し、版を分離してPDCA
```

Hook単独をBUY/SELLへ直結してはならない。同じ吸収、delta、板非対称、sweepでも、場所、
auction state、接近過程、時間軸によって、継続の証拠にも反転の証拠にもなる。

したがって現時点の判断は以下である。

- append-only収録は継続する。
- 全Hook `UNCALIBRATED`、HookEvent発火禁止、`OBSERVE`、`execution_enabled: false`を維持する。
- 現行Stage 2C-2の「無条件分布のpercentileで88 Hookを較正」は開始しない。
- 88 Hookと50 Triggerは削除せず、**未監査candidate inventory**として凍結する。
- Source Truth監査、役割再分類、Strategy Engine仕様、strategy-conditioned validationの順に
  Stage 2Cを組み替える。

## 1. 調査方法と証拠の強さ

### 1.1 優先した資料

1. 取引所・規制当局のmarket data、matching、execution仕様
2. 査読論文・working paper・主要microstructure研究
3. prop desk／ladder・DOMツール提供者が公開する実取引教育
4. DeltaEngineの現行catalog、collector、Stage 2C文書

実務教育資料は「プロがどの順序で見るか」の証拠として使うが、個別手法の収益性を証明する
学術的根拠としては使わない。逆に、学術研究の短期予測結果をそのままHFMの収益性へ外挿しない。

### 1.2 今回答えた問い

- 注文フローで直接観測できる事実は何か。
- Market-by-Priceデータから観測できないものは何か。
- 実トレーダーは、setup、場所、接近、trigger、entry、管理をどう分けるか。
- Hookの検出精度とStrategyの市場耐性をどう別々に検証するか。
- BinanceからHFMへ意思決定を移す時、何を追加検証する必要があるか。

## 2. 注文フロートレードの根本

### 2.1 市場は注文の「表示」と「約定」の逐次auctionである

CLOBでは、resting limit orderが流動性を供給し、aggressive orderがそれを消費する。
しかし表示板の厚さだけで流動性は決まらない。CMEも、depthに加えてquote refresh、
実際のfill、価格impactを見る必要があるとしている。

参照:

- [CME: Assessing Liquidity](https://www.cmegroup.com/education/articles-and-reports/assessing-liquidity)
- [CME: How Ag Markets Operate](https://www.cmegroup.com/education/articles-and-reports/overview-what-makes-ags-markets-work)
- [CFTC Futures Glossary](https://www.cftc.gov/LearnAndProtect/AdvisoriesAndArticles/CFTCGlossary/index.htm)

注文のpriorityもvenueで違う。FIFOでは同一価格内のarrival timeが重要だが、商品によって
pro-rata等もある。したがって「板数量N倍」の意味は、matching rule、tick size、depth、
queue更新速度と切り離せない。

### 2.2 価格を動かすのはtrade volume単独ではない

短いhorizonでは、best bid/askのlimit addition、cancellation、market orderをまとめた
Order Flow Imbalanceが価格変化と強く関係し、その感応度はdepthに依存するという結果がある。
また、queue imbalanceは次のmid-price moveと関係するが、効果はtick-size regime等で変わる。
deeper levelを加えたmulti-level OFIが改善する市場もある。

参照:

- [Cont, Kukanov, Stoikov: The Price Impact of Order Book Events](https://arxiv.org/abs/1011.6402)
- [Gould, Bonart: Queue Imbalance as a One-Tick-Ahead Price Predictor](https://arxiv.org/abs/1512.03492)
- [Xu, Gould, Howison: Multi-Level Order-Flow Imbalance](https://arxiv.org/abs/1907.06230)
- [Cont, de Larrard: Price Dynamics in a Markovian Limit Order Market](https://arxiv.org/abs/1104.4596)
- [Bouchaud et al.: Price Impact](https://arxiv.org/abs/0903.2428)

これは「imbalanceなら買い」を意味しない。効果はdepth、horizon、asset、regimeに条件付く。
2023-2026のBinance BTCUSDT／ETHUSDTを対象にした2026年の研究でも、1分・5分のliquidity-state
予測では、order flowの追加価値はasset／state依存で、BTCでは追加効果が確立せず、ETHのstress
stateで強かった。著者自身も、この結果はexecutionや収益性を示さないと限定している。

- [When Does Order Flow Matter? State-Dependent L2 Liquidity-State Transitions in Crypto Futures](https://arxiv.org/abs/2607.09230)

### 2.3 注文フローはStrategyではない

注文フローは、次を行うための高解像度な証拠である。

- 事前仮説が現在も成立しているか更新する。
- 予定価格帯でacceptance／rejectionのどちらが起きているか見る。
- breakout前のinitiative増加、reversal後の確認、pullback終端を区別する。
- entry後にfollow-throughがあるか、逆選択を受けたか判定する。
- passive／aggressiveのどちらで入るべきか判断する。

注文フローを単発signalへ落とすと、ローソク足のgolden crossを複雑な名称で置き換えただけに
なる。優位性の単位はHookではなく、**条件付きStrategy episode全体**である。

## 3. 実トレーダーのentry timing

複数のprop／order-flow実務資料に共通する順序は次である。

```text
1. Game plan        何を、どの環境で狙うか
2. Setup/Strategy   breakout、failed auction、pullback等の仮説
3. Location         high/low、value、VWAP、prior structure等
4. Approach path    その場所へ速く来たか、圧力が増えたか、失速したか
5. Decision event   absorption、reclaim、initiative、failure等
6. Entry tactic     anticipate／confirm／retest、passive／aggressive
7. Invalidation     どの価格・flow・時間なら仮説が誤りか
8. Follow-through   entry後に期待したflowとprice responseが出たか
9. Management       add、reduce、exit、time stop
10. Review          同じsetupのeligible全episodeで再評価
```

### 3.1 同じ場所でもreversalとbreakoutはentry timingが違う

Jigsawの実務例では、同じhigh/lowでもreversalは反転確認後に数tickを払って入る一方、
breakoutはbreak前のmomentum増加を利用し、momentumが消えれば即座に撤退する。つまり場所だけ、
あるいは共通Hookだけでは方向もentry時点も決まらない。

- [Jigsaw: Reversals and Breakout Trades](https://www.jigsawtrading.com/blog/jigsaw-trading-order-flow-trade-reversals-breakout-trade/)
- [Jigsaw: Anatomy of a Reversal](https://www.jigsawtrading.com/blog/elements-of-a-reversal/)

### 3.2 Setupが先、Triggerは最後のentry条件

SMBの公開資料は、market environment、catalyst、relative volume、sector、time of day、
technical compression、active order flow等でsetupを作り、その後に「最初のoffer liftで入るか」
「break後のpullback/retestで入るか」「break前にanticipateするか」をStrategy固有のTrigger
として分けている。

- [SMB: Stock Trading 101 — The Trigger](https://www.smbtraining.com/blog/stock-trading)
- [SMB: Using the Tape](https://www.smbtraining.com/blog/using-the-tape-prgo)
- [SMB: Finding Good Setups in a Quiet Tape](https://www.smbtraining.com/blog/finding-good-setups-in-a-quiet-tape)

### 3.3 Planと実際の接近が違えばno tradeである

Axiaの実務資料では、entry levelだけでなく、そこへどう到達するか、stallかaccelerationか、
initiativeが変化したか、failure後にreclaimしたかを計画する。実際の動きが仮説と違えば
「別Hookで埋める」のではなくno tradeとなる。

- [Axia: Why Day Trading Is Not Simple](https://axiafutures.com/blog/why-day-trading-not-simple-part-i/)
- [Axia: Two Breakout Strategies](https://axiafutures.com/blog/two-breakout-strategies-for-futures-markets/)
- [Axia: Reversal and Continuation Scalping Strategies](https://axiafutures.com/blog/reversal-and-continuation-scalping-strategies/)
- [Axia: Stop Placement Strategies](https://axiafutures.com/blog/stop-placement-strategies-professional-traders-use/)

### 3.4 entry後も注文フローを使う

priceが進まず、反対flowが優勢なら仮説失敗である。自分側のaggressionが強いのに価格が進まない
場合は、trapped／absorptionの危険がある。したがってTrigger発火でStrategyを終了してはならない。

- [Jigsaw: Trade Management Using Order Flow](https://www.jigsawtrading.com/blog/master-trade-management-using-order-flow/)
- [Axia: Breakout Trade Management](https://axiafutures.com/blog/breakout-trade-management-techniques/)

## 4. DeltaEngineが実際に観測できるもの

### 4.1 Binance depthはMarket-by-Priceである

Binance USDⓈ-Mのlocal book手順では、各更新は価格levelのabsolute quantityであり、同一価格の
後着更新が前の更新を覆う。`U/u/pu`でsequence continuityを管理できるが、public feedには
individual order IDがない。

- [Binance USDⓈ-M: How to Manage a Local Order Book](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/How-to-manage-a-local-order-book-correctly)

対照的にNasdaq TotalView ITCHはorder-by-orderのadd、execute、cancelを配信する。
SECもorder-based feedとlevel-book feedでは、individual orderの追跡可能性とactivity metricの
意味が違うと説明している。

- [Nasdaq TotalView-ITCH 5.0 Specification](https://nasdaqtrader.com/content/technicalsupport/specifications/dataproducts/NQTVITCHSpecification.pdf)
- [SEC: Order Book Reporting Methods](https://www.sec.gov/data-research/statistics-data-visualizations/order-book-reporting-methods-their-impact-some-market-activity-measures)

そのため現行データでは次を直接知ることができない。

- individual orderのqueue position
- 同一level内の注文者・注文数・priority
- 自注文のpassive fill probability
- cancelした主体と、その注文時点の意図
- hidden quantityの実値

### 4.2 `aggTrade`は完全なorder-by-order tapeではない

Binance公式connectorの説明では、USDⓈ-M `aggTrade`はsingle taker order単位にmarket tradeを
100ms cadenceでaggregateし、insurance fund／ADL tradeはaggregate対象外である。

- [Binance Official Futures Connector: Aggregate Trade Stream](https://github.com/binance/binance-futures-connector-python/blob/main/binance/websocket/um_futures/websocket_client.py)

したがって、price、quantity、maker flagからaggressor側の約定量は作れるが、これは
「Binance aggTrade由来Footprint」であり、MBOの全match sequenceと同一ではない。
100ms depthとの突合せでmulti-level consumptionを推定することはできても、すべての
micro-sequenceを観測したと断定してはならない。

### 4.3 `forceOrder`は清算全件テープではない

同じBinance公式connectorは、`forceOrder`について、各symbolで1000ms内の**latest one
liquidation orderだけ**をsnapshotとしてpushすると明記している。

- [Binance Official Futures Connector: Liquidation Order Snapshot](https://github.com/binance/binance-futures-connector-python/blob/main/binance/websocket/um_futures/websocket_client.py)

これは現行Stage 2Cへ直接影響する。

- 14日・4,000受信recordは、清算4,000件の完全母集団ではない。
- 1秒内に複数清算があっても最新1件しか見えない。
- E03/E04の「N件/秒」は、このfeedだけでは定義どおり測れない。
- E06の「清算連鎖の急停止」は、配信抑制と真の停止を区別できない。
- `forceOrder` countだけからcascade size、side別完全分布、exhaustionを較正できない。

このstreamは「観測された清算snapshot」のevent studyには使えるが、完全なliquidation tapeと
呼んではならない。

### 4.4 OIは参加者の方向を直接示さない

Open interestは未決済contract総数であり、全long OIと全short OIは等しい。OI増加と価格上昇の
組合せは「新規longが観測された」という事実ではない。取引相手側の新規short、既存positionの
移転、集計間隔内のopen/close混在がある。

- [CFTC: Commitments of Traders Explanatory Notes](https://www.cftc.gov/MarketReports/CommitmentsofTraders/ExplanatoryNotes/index.htm)
- [CME: Open Interest](https://www.cmegroup.com/education/courses/introduction-to-futures/open-interest)

したがってF01-F04はOI／price quadrantという観測Featureにはできるが、
「新規long流入」「short撤退」を事実名としては使えない。

### 4.5 表示板からspoofing intentは断定できない

spoofingの規制上の核心は、execution前にcancelする意図である。大口表示後のcancelは、
market making、repricing、risk reductionでも起きる。匿名Market-by-Price feedだけでは
主体のintentを直接観測できない。

- [CME: Disruptive Practices Prohibited — Spoofing](https://www.cmegroup.com/education/courses/market-regulation/disruptive-practices-prohibited/disruptive-practices-prohibited-spoofing.hideSubnav.educationIframe.html.html?hideAddThisExt=y&hideFooter=y&hideHeader=y&hideRightRail=y)
- [CFTC Interpretive Guidance on Spoofing](https://www.cftc.gov/LawRegulation/FederalRegister/FinalRules/2013-12365.html)

A19/A20は`SUSPECTED_DISPLAY_WITHDRAWAL_PATTERN`等の観測名に限定し、spoofing確定判定に
してはならない。

## 5. 現行88 Hookの全体監査

現行catalogの件数は正確に88である。

```text
A 24 + B 20 + C 9 + D 8 + E 6 + F 5 + G 12 + H 4 = 88
```

しかし同じ責任を持つ88 Hookではない。

| 区分 | 数 | 実際の役割 | 主な是正 |
|---|---:|---|---|
| A DOM | 24 | L2 price-level観測／派生Feature | wall/pull/depthは候補。iceberg/spoof/queueはsuspectedへ限定 |
| B Tape | 20 | aggressor trade Feature | exact sweepの可観測性を限定。institution/crowdという主体推論を除去 |
| C 板×約定 | 9 | interaction／response evidence | event-time alignmentとreference再構成が必要。C09は清算feed制約あり |
| D Flow response | 8 | 既存modelのstate transition | 市場参加者の実positionではなくmodel labelであることを明記 |
| E Liquidation | 6 | sampled liquidation snapshot | E03/E04 rateとE06 exhaustionは現定義のまま検証不能 |
| F OI | 5 | OI／price context Feature | new long/new short/cover/liquidationの断定を除去 |
| G Price/location | 12 | Strategy context／location | HookEventではなくsetup eligibilityへ移す |
| H Environment | 4 | regime／execution gate | entry evidenceでなくfilter／venue safetyへ移す |

### 5.1 観測・Feature・解釈を分離する

新しい型は最低でも次を分離する。

| 型 | 意味 | 例 |
|---|---|---|
| OBSERVATION | feedから直接得た事実 | price-level qty update、aggTrade、spread |
| FEATURE | 観測から決定的に算出 | depth ratio、OFI、trade rate、price response |
| CONTEXT | Strategyの成立範囲 | prior high、value area、session、volatility state |
| EVIDENCE | 特定Strategyへの賛成／反対証拠 | breakout approachでのinitiative増加 |
| SUSPECTED_SIGNATURE | 意図を断定しないpattern | iceberg-like replenishment、display withdrawal |
| EXECUTION_GATE | 執行可能性 | HFM spread、quote age、basis、latency |

「大口」「機関」「群集」「実需」「trap」「spoof」は、直接観測できる語へ置換するか、
model inferenceとして確率・根拠・反証条件を持たせる。

### 5.2 現行50 Triggerの問題

50件は削除対象ではないが、実際のTrigger catalogとしては未完成である。

- Strategy instanceを事前に武装する条件がない。
- entryする場所と、そこへ近づくpathが多くの型で未定義。
- Hook間の順序、最大間隔、持続、再touch、expiryが不十分。
- passive／aggressive、entry price、許容slippage、注文expiryがない。
- 仮説が誤りとなるprice／flow／time invalidationがない。
- entry後のfollow-through、add、reduce、exitがない。
- 同じ入力を重複した「確認」として数える型がある。
- 観測不能または過剰解釈のHookへ依存する型がある。

例:

- T01はC01後にB03が「反転確認」として出る順序なら候補になるが、単なる同時ANDでは
  absorptionとaggressionの意味を取り違える。
- T24/T25の「実需」はOI×priceから直接分からない。
- T29-T33は`forceOrder` sampling制約を無視してcascade／exhaustionを完全観測している前提。
- T39/T40は静的depth imbalanceを普遍的方向signalとして扱えない。
- T48は吸収、sweep、short liquidationのsideと時系列の因果物語が未定義で、単純同時発生を
  独立した三点確認とは呼べない。

50件は今後、Triggerではなく`CANDIDATE_STRATEGY_STORY`として監査し、少数のStrategy familyと
複数のentry modeへ再編する。

## 6. Strategy Engineへ直す構造

正しい責任分離は次である。

```text
Source Truth / Quality Gate
  -> Observation / Feature
  -> Market State / Location / Regime
  -> competing Strategy Instances
  -> Strategy-specific EntryDecision
  -> HFM ExecutionDecision
  -> Position Lifecycle
  -> Episode Store
  -> L0-L5 Validation / Versioned PDCA
```

StrategyはTrigger後に作る説明ではない。locationへ到達する前後で`WATCH／ARMED`になり、接近、
最初の攻防、decision event、entry、follow-through、invalidation、exitまで同じinstanceとして
生存する。

最低限必要なStrategy要素:

- 対象市場、観測venue、執行venue、holding horizon
- falsifiable market hypothesis
- eligibility、location、approach path
- required／supporting／contradicting／invalidating evidence
- expected temporal sequenceとexpiry
- entry mode、entry zone、late-entry rule
- HFM execution profile
- follow-through、add／reduce／exit
- eligible全episodeを使うevaluation contract
- 全dependencyのversion

## 7. Triggerとentry timing

TriggerはBUY／SELL labelではなく、武装済みStrategyが`ENTERABLE`へ遷移した時点である。

分離すべきentry mode:

| mode | 内容 | 固有risk |
|---|---|---|
| ANTICIPATORY | break／turn前に入る | false start |
| CONFIRMED | decision event後に入る | entry price悪化 |
| RETEST | break／reclaim後の再test | non-fill／再失敗 |
| PASSIVE | resting／limit | queue、non-fill、adverse selection |
| AGGRESSIVE | marketable order | spread、slippage、late entry |

同じprior highでも、breakout continuationはinitiative増加、break、acceptance／retest holdを待つ。
failed-auction reversalはoutside attempt、price progress failure、reference内reclaim、反対responseの
順序を待つ。同じHookの集合でも期待sequenceが違うため、単純ANDでは区別できない。

EntryDecisionは少なくともStrategy instance、decision time、location、evidence clause、反対証拠、
entry mode、entry zone、TTL、invalidation、expected follow-throughを持つ。

## 8. Executionとcross-venue

passive orderの価値は方向予測だけで決まらない。fill probability、queue position、fill time、
adverse selectionが必要である。

- [Queue-Reactive Model](https://arxiv.org/abs/1312.0563)
- [State-Dependent Fill Probabilities](https://arxiv.org/abs/2403.02572)
- [Deep Attentive Survival Analysis in LOBs](https://arxiv.org/abs/2306.05479)
- [Queue Position, Adverse Selection and Price Impact](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3991930)

Binance Market-by-PriceからHFM自注文のqueue／fillを再現することはできない。HFM側で、
quote、request、ack、fill、reject、slippage、sizeを保存し、独立のexecution profileを作る。

Bitcoinはfragmented marketであり、研究上Binanceがprice discoveryを主導する期間はあるが、
time of dayやvenueで変わる。perpetualもspotへ必ず収束しない。

- [Where Is the Price of Bitcoin Determined?](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4983566)
- [The Role of Binance in Bitcoin Volatility Transmission](https://arxiv.org/abs/2107.00298)
- [Fundamentals of Perpetual Futures](https://arxiv.org/abs/2212.06888)

HFMの2026年entity-specific policyの一例では、market orderはfirst available price、news／volatility／
insufficient liquidityではslippage、decline、partial／different-price executionがあり得る。
actual account entityとBTCUSDr contractは別途確認が必要である。

- [HFM 2026 Order Execution Policy](https://www.hfm.com/load_terms?file=ZA_HFZA%2F2026-01_HFSA_Order_Execution_Policy_2026-01.pdf)

HFM Execution Gateは少なくともquote age、spread、basis、latency、slippage、size、remaining
opportunityを評価する。現Stage 2Cではshadow結果だけを保存し、外部注文は行わない。

## 9. 検証を六段へ分ける

| Level | 問い | 代表出力 |
|---|---|---|
| L0 Source | feedを正しく保存したか | gap、sequence、clock、schema、sampling |
| L1 Hook／Feature | 定義どおり検出したか | FP／FN、side／timing error |
| L2 Evidence | setup baselineへ追加情報があるか | conditional response、ablation、regime |
| L3 Strategy／Entry | entry timingとして耐えるか | MFE／MAE、follow-through、invalidation |
| L4 Execution | HFMで実行可能か | spread、basis、latency、slippage、reject |
| L5 Shadow | realtimeで同じlifecycleを再現するか | decision trace、paper position、外部注文0 |

HookのL1正確性を勝敗で判定しない。一方、最終Strategyを市場耐性ありと主張するには、path metricに
加えてcost-adjusted expectancy、tail loss、drawdown、outlier concentrationを確認する。

発火episodeだけを保存せず、eligible、armed、no-trade、expired、invalidated、execution-blocked、
non-fillをすべて保存する。これがcounterfactual populationになる。

72時間はcollector／detector／初期分布のseedであり、市場耐性の証明ではない。14日／4,000件の
`forceOrder` recordもsampled snapshot coverageであり、完全清算母集団gateではない。

88×50×window×thresholdの試行はbacktest overfitを生むため、trial registry、chronological split、
overlap purge／embargo、untouched holdout、negative control、multiple-testing統制が必要である。

- [Bailey et al.: Effects of Backtest Overfitting](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2308659)

## 10. 常時PDCA

変更単位はsource semantics、feature formula、window、Hook、EvidenceClause、Strategy eligibility、
sequence、threshold、entry mode、invalidation、execution、management、evaluation contractである。
いずれかを変えたらversionを上げ、同じversionの中身を上書きしない。

```text
DRAFT
  -> APPROVED_RESEARCH
  -> SHADOW_CANDIDATE
  -> VALIDATED
  -> APPROVED_OBSERVE
  -> ACTIVE_SHADOW

任意段階 -> RESTRICTED / REJECTED / RETIRED
```

active版をchampion、変更版をchallengerとして同じfrozen inputで比較する。aggregate改善だけでなく、
悪化regime、tail、entry price、execution block、reason code差を提出する。旧validated bundleを
version一式で保持し、rollback可能にする。

## 11. Stage 2Cの差し替え

| 工程 | 内容 |
|---|---|
| 2C-0 | Source Truth、sampling／aggregation、HFM entity／contract監査 |
| 2C-1 | full initial dataset／sampled liquidation coverageの完了判定 |
| 2C-2 | 88項目role／claim全件監査 |
| 2C-3 | Strategy Method Constitution批准と最初のStrategySpec |
| 2C-4 | Hook／Feature L1独立検証 |
| 2C-5 | Evidence／Strategy L2-L3 holdout検証 |
| 2C-6 | HFM shadow execution L4 |
| 2C-7 | no-tradeを含むlifecycle shadow L5 |

各工程後にユーザーへ報告し、次工程承認を得る。`execution_enabled: false`は維持する。

## 12. 即時判断

継続:

- crash-safe append-only収録
- coverage／deadline台帳
- 自動復旧
- 全Hook `UNCALIBRATED`、threshold空
- `OBSERVE`、`execution_enabled: false`
- 完成済みFlow Price Response、3段チャート、8パターン

停止:

- 88項目を同質Hookとして一括percentile較正
- 50 storyをproduction Triggerとして実装
- `forceOrder`を完全清算tapeとして使うこと
- OI×priceからparticipant sideを事実認定
- Binance L2からHFM fill／queueを捏造
- Hook単独をBUY／SELL entryへ接続

## 13. 今回変更していないもの

source code、runtime、config、threshold、HookEvent、TriggerDecision、playbook、execution setting、UI、
Flow Price Response、3段チャート、8パターン、raw収録dataの変更は0である。

## 14. 次の正本候補

世界調査を実装へ結ぶ憲法草案を別文書として起草した。

`ORDER_FLOW_STRATEGY_METHOD_CONSTITUTION_OPERATIONAL_DRAFT_V0_2_20260726.md`

同草案はevent schema、Market State、StrategySpec／Instance、EntryDecision、HFM Execution Gate、
PositionState、BTC具体trace、L0-L5 validation、PDCA、Constitution testを定める。ユーザー批准前は
正本または実装承認として扱わない。

## 15. ユーザー訂正後の自動発注アーキテクチャ再解釈（2026-07-26 22:11 JST）

ユーザーとの再確認により、本reportのStrategy論を自動発注systemへ翻訳する際に欠けていた実行上の
中心を次のとおり訂正する。

- DeltaEngineは自動発注systemであり、全分析の最終目的はHFMへの説明可能な自動発注である。
- HookはObservation／Featureそのものではなく、注文フロー分析各所へ置かれ、変化を捕捉した瞬間に
  Strategy Engineを呼ぶ分散配置の起動罠である。
- HookとStrategyは1対1ではない。一つのHookが複数Strategyを呼び、一つのStrategyは複数Hookで
  条件を逐次更新する。
- Strategy Engineは呼出しごとに関係する全Strategyの条件をpoint-in-time dataで埋め、反証、
  hard reject、充足水準を評価する。
- 条件充足から、entryしない／待つ／今入る／retestを待つ、方向、発注枚数を決める。
- entry後もHookがEngineを呼び、HOLD／ADD／REDUCE／EXIT／REVERSE候補を再評価する。
- SMB等の実務資料がいう`Trigger`は、上記Hookではなく、条件が揃った後の最終Order Triggerに対応する。

前版v0.2の不足:

1. HookをEngine呼出し装置として定義していなかった。
2. HookとStrategyのmany-to-many dispatchがなかった。
3. 条件を都度埋めるCondition Boardと説明可能な充足水準がなかった。
4. `requested_size`の決定元がなかった。
5. 保有中Hookからposition判断へ戻る経路が明示されていなかった。

この訂正を反映した文書:

- `ORDER_FLOW_STRATEGY_METHOD_CONSTITUTION_OPERATIONAL_DRAFT_V0_3_20260726.md`
- `ORDER_FLOW_STRATEGY_CANDIDATE_SET_V0_1_20260726.md`

第一候補はBREAKOUT_ACCEPTANCE、FAILED_AUCTION_RECLAIM、ABSORPTION_DEFENSE、
ABSORPTION_FAILURE、PULLBACK_CONTINUATION、MOMENTUM_EXHAUSTIONの6系統とした。
Strategy数を固定する決定ではなく、何をStrategyにするかをユーザーと選定するための具体案である。

source code、runtime、config、HookEvent、execution setting、UI、raw dataの変更は0。
`execution_enabled: false`、発注0を維持する。
