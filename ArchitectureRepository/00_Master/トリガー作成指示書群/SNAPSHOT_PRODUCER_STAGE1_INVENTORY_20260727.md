# Snapshot Producer Stage 1 Inventory

作成日: 2026-07-27 JST
状態: Stage 1棚卸し。正本・実装仕様ではない。

## 0. 結論

指定範囲を棚卸しした結果、**Stage 2の「既存検出器のpublic出力をcondition keyへ変換するだけ」
という制約のままでは、13件のG16入力を完備するSnapshot Producerは実装できない**。
Stage 2はNO-GOとし、正本・source・test・runtime・raw dataには着手しない。

理由は次のとおり。

1. CVD public出力からG08 aggression量／件数／rate／shareとG10 delta／CVD系列の一部は
   thresholdなしで導出可能である
   (`src/orderflow/cvd.py:78-84,128-134,223-254`)。
2. OrderBook public snapshotからG05 raw depthとG06 static shapeの一部は導出可能だが、
   authoritativeな`tick_size`供給がない
   (`src/orderflow/orderbook.py:68-81,148-157`;
   `src/strategy_engine/ingestion/market_state.py:65-72`)。
3. G07 refresh／pull／stack、G09の正本どおりのprogress／efficiency／no-progress／reversion、
   G11 session／rolling profile acceptanceは、指定5検出器のpublic出力に存在しない
   (`Condition Dictionary:304-355,410-453,496-531`)。
4. Absorption detectorは内部でaggressionとreplenishmentを計算するが、publicには
   threshold適用後の`AbsorptionResult`しか出さない。これをTier Aへ戻すと、
   G16 compositeをG16材料として再利用する循環になる
   (`src/orderflow/absorption.py:146-214`; `Condition Dictionary:665-672`)。
5. production sourceには`MarketStateSnapshot(...)`生成も`IngestionAdapter.to_conditions(...)`
   呼出しも0件で、`pre_aggregated`へ値を渡す経路自体が未接続である
   （2026-07-27 `rg`実測。定義箇所は
   `src/strategy_engine/ingestion/market_state.py:57-72`、
   `src/strategy_engine/ingestion/condition_adapter.py:33-42,115-119`）。

したがって、Stage 2前に少なくとも入力時刻、tick size、G07/G09/G11算出契約、
および「public detector outputだけでなくnormalized eventを同時入力してよいか」の
追加承認が必要である。

## 1. 読み取り範囲とパス差異

### 1.1 引用表記

- `Condition Dictionary:nn` =
  `ArchitectureRepository/00_Master/トリガー作成指示書群/ORDER_FLOW_CONDITION_DICTIONARY_V0_1_20260726.md:nn`
- `G16 Draft:nn` =
  `ArchitectureRepository/00_Master/トリガー作成指示書群/DRAFT_G16_COMPOSITE_RULES_AND_E98_UPDATE_20260727.md:nn`
- `pipeline.py:nn` = `Delta_Engine_Pro4web/src/pipeline.py:nn`
- その他の`src/...:nn`、`tests/...:nn`、`webapp/...:nn`は
  `Delta_Engine_Pro4web/`からの相対pathである。

### 1.2 指示書記載pathと実在path

| 指示書記載 | 実在位置 | 判定・根拠 |
|---|---|---|
| `src/replay_pipeline.py` | 独立fileなし。`ReplayPipeline`は`src/pipeline.py`内 | `pipeline.py:272-598` |
| `src/cvd.py` | `src/orderflow/cvd.py` | importは`pipeline.py:60-62` |
| `src/absorption.py` | `src/orderflow/absorption.py` | importは`pipeline.py:60` |
| `src/imbalance.py` | `src/orderflow/imbalance.py` | importは`pipeline.py:78` |
| `src/footprint.py` | `src/orderflow/footprint.py` | importは`pipeline.py:73` |
| `src/orderbook.py` | `src/orderflow/orderbook.py` | importは`pipeline.py:79` |

パス差異はStage 1のread-only棚卸しでは実在実装へ追従できるため、調査全体のblockerにはしない。
ただし、Stage 2の変更対象pathは実在構成に合わせて再承認が必要である。

## 2. Pipeline配線とLive／Replay対称性

| mode | 検出器生成 | 主な呼出し | 出力の保持／公開 | 根拠 |
|---|---|---|---|---|
| Replay | CVD、Footprint、OrderBook、Absorption、Imbalanceを`run()`内localで生成 | tradeごとにCVD／Footprint／Absorption、depthごとにOrderBook、bar closeでImbalance | `flow_response`等を除き5検出器本体・結果はrun後のpublic属性へ保持しない | `pipeline.py:435-481,500-553,557-598` |
| Live | Replayと同じ5検出器を`run_async()`内で生成 | tradeごとにCVD／Footprint／Absorption、depthごとにOrderBook、bar closeでImbalance | `book_manager`、`volume_ref_tracker`、`cvd_calculator`、`absorption_detector`だけpublic公開。Footprintとlast bar/resultは`_` private。Imbalance detectorはpublic公開なし | `pipeline.py:1025-1097,1137-1153,1173-1254,1318-1322` |
| 共通bar close | `ImbalanceDetector.detect()`、Absorption current、Footprint totalsを評価 | `_BarCloseResult`を返す | resultにはImbalance／Absorptionがあるが、Replayは捨て、Liveは`_last_bar_close`へprivate保持 | `pipeline.py:601-685,1244-1254` |

検出器の**計算型**はLive／Replayで同一だが、pipeline外から読めるpublic interfaceは非対称である。
同一producerを使うには、producerを両pipeline内部の同じ観測点から明示的に呼び、
public result objectを渡す配線が必要になる。現状のpipeline objectを外から読む方式は採用できない。

## 3. 検出器ごとの出力棚卸し

### 3.1 CVD

| 検出器 | 出力属性/メソッド | 型 | 値の意味 | 対応するG01-G15 family | condition key候補 | 根拠（file:line） |
|---|---|---|---|---|---|---|
| `CvdCalculator` | `process()` | `CvdResult` | 1 tradeのaccept/reject、tick update、bar rollover時のclosed candle | G10 / G01候補 | 下記`CvdUpdate`と`Candle`。reject自体はG01 flagと一対一でない | `src/orderflow/cvd.py:112-124,223-254` |
| `CvdUpdate` | `event_time`, `tick_delta`, `tick_cvd` | `datetime`, `Decimal`, `Decimal` | trade単位のsigned volumeと累積CVD | G08 / G10 | DERIVE候補: `buy/sell_market_volume_*`, `buy/sell_trade_count_*`, `buy/sell_average_trade_size_*`, `buy/sell_max_trade_size_*`, `buy/sell_trade_rate_*`, `buy/sell_side_share_*`, `trade_delta_*`, `cvd_change_*`, `cvd_slope_*` | `src/orderflow/cvd.py:77-84,128-134,248-253`; `Condition Dictionary:361-408,459-470` |
| `Candle` | `open/high/low/close/volume/delta/cvd` | 全numericは`Decimal` | configured barのOHLC、総volume、bar delta、bar末CVD | G09 / G10候補 | 現行1mはG09/G10のkey windowと一致しないため直接key化不可 | `src/orderflow/cvd.py:87-100,177-189`; `config/config.yaml:12`; `Condition Dictionary:414-494` |
| `CvdCalculator` | `cvd` property | `Decimal` | 現在の累積CVD | G10候補 | 絶対CVD keyは正本にない。`TimeSample`化後の差分／傾きだけDERIVE可能 | `src/orderflow/cvd.py:215-217`; `src/strategy_engine/ingestion/condition_adapter.py:46-61` |
| `CvdCalculator` | `current_bar_snapshot()`, `finalize()` | `Candle`または`None` | 進行中／最終barの非破壊・確定snapshot | G09 / G10候補 | bar window一致時のみ材料候補。現行1mは不一致 | `src/orderflow/cvd.py:267-283`; `config/config.yaml:12` |
| `CvdCalculator` | `processed`, `duplicates`, `rejected_invalid`, `rejected_out_of_order` | `int` | 累積品質counter | G01候補 | G01はpoint-in-time FLAGでreset／window契約がないため一致keyなし | `src/orderflow/cvd.py:200-213`; `Condition Dictionary:78-109` |

判定:

- `tick_delta`の符号と絶対値からside別volume／count／sizeをrolling集計することは
  detector出力だけで可能である。
- `notional`は`CvdUpdate`にpriceがないため算出不能。
- `large_trade_count`はthresholdが必要なためCalibrationBook定義前は出力禁止。

### 3.2 Absorption

| 検出器 | 出力属性/メソッド | 型 | 値の意味 | 対応するG01-G15 family | condition key候補 | 根拠（file:line） |
|---|---|---|---|---|---|---|
| `AbsorptionDetector` | `observe_trade()` | `None` | private windowを更新し内部判定 | 対応なし | raw aggression／stall／replenish値は返さない | `src/orderflow/absorption.py:113-140` |
| `AbsorptionDetector` | `current()` | `AbsorptionResult`または`None` | 最新のthreshold適用済み吸収判定 | G01-G15対応なし。G16相当 | `bid_absorption_like_active` / `ask_absorption_like_active`に近いがTier Aではない | `src/orderflow/absorption.py:142-144`; `Condition Dictionary:671-672` |
| `AbsorptionResult` | `classification`, `strength`, `price_low`, `price_high` | `str`, `Decimal`, `Decimal`, `Decimal` | side、0..1強度、停止価格帯 | G01-G15対応なし | 対応なし: G08/G09/G07の材料値ではなく合成済み結果 | `src/orderflow/absorption.py:42-58,194-214` |
| `AbsorptionDetector` | failure／event counters | `int` | detector lifetime累積counter | G01候補 | 対応なし: point-in-time品質FLAGや材料値と意味が違う | `src/orderflow/absorption.py:85-91`; `Condition Dictionary:78-109` |

内部localの`agg_buy`／`agg_sell`とreplenishment判定は`_evaluate()`内だけに存在し、
public属性ではない (`src/orderflow/absorption.py:146-192`)。private利用禁止のためProducer材料にできない。

### 3.3 Imbalance

| 検出器 | 出力属性/メソッド | 型 | 値の意味 | 対応するG01-G15 family | condition key候補 | 根拠（file:line） |
|---|---|---|---|---|---|---|
| `ImbalanceDetector` | `detect(FootprintBar)` | `ImbalanceResult` | 1 FootprintBarのbuy/sell diagonal imbalanceとstack | G10 | `positive/negative_imbalance_count_*`, `stacked_buy/sell_imbalance_depth_*`候補 | `src/orderflow/imbalance.py:149-176,253-264`; `Condition Dictionary:479-494` |
| `BuyImbalance` / `SellImbalance` | `price`, `ratio` | `Decimal` | qualifying levelの価格と比率 | G10候補 | countはtuple長からDERIVE可能。ratio自体のkeyは正本にない | `src/orderflow/imbalance.py:52-63,206-251` |
| `StackedImbalance` | `start_price`, `end_price`, `count`, `direction` | `Decimal`, `Decimal`, `int`, `str` | 連続runの価格範囲・段数・side | G10 | `stacked_buy/sell_imbalance_depth_*`候補。ただし複数run時にmax/sum/lastのどれかは正本未定義 | `src/orderflow/imbalance.py:65-79,111-146`; `Condition Dictionary:487-494` |
| `ImbalanceDetector` | public parameters／counters | `Decimal`, `int` | ratio threshold、floor、cap、stack count、invalid pair累積 | G01候補 | condition材料ではない | `src/orderflow/imbalance.py:157-188` |

現行FootprintBarは1mで、G10 imbalance keyは1s／5s／30s／5mである
(`config/config.yaml:12`; `Condition Dictionary:479-494`)。したがって現行resultを
別window keyへ改名することは禁止する。

### 3.4 Footprint

| 検出器 | 出力属性/メソッド | 型 | 値の意味 | 対応するG01-G15 family | condition key候補 | 根拠（file:line） |
|---|---|---|---|---|---|---|
| `FootprintCalculator` | `process_trade()` | `FootprintBar`または`None` | bar rollover時のprice-level集計 | G08 / G10 / G11候補 | level合計からside volume／delta／ratio候補。ただし現行1mは正本window不一致 | `src/orderflow/footprint.py:130-186`; `config/config.yaml:12` |
| `FootprintBar` | `bar_time`, `timeframe`, `levels` | `datetime`, `str`, `tuple[PriceLevel,...]` | 価格昇順の確定bar footprint | G08 / G10候補 | matching windowならside volume等をDERIVE可能 | `src/orderflow/footprint.py:75-82,109-126`; `Condition Dictionary:361-408,459-478` |
| `PriceLevel` | `price`, `buy_volume`, `sell_volume` | `Decimal` | 1価格levelのside別約定量 | G08 / G10 | bar内合計・imbalance detector入力 | `src/orderflow/footprint.py:66-72` |
| `FootprintCalculator` | `current_tick_snapshot()` | `tuple[PriceLevel,...]` | 進行中barのprice-level集計 | G08 / G10候補 | event順序、first/last price、source時刻を失うためG09 rolling progressには使えない | `src/orderflow/footprint.py:188-192` |
| `FootprintCalculator` | `finalize()` | `FootprintBar`または`None` | 最終open barの確定 | G08 / G10候補 | `process_trade()`と同じwindow制約 | `src/orderflow/footprint.py:194-200` |
| `FootprintCalculator` | public counters | `int` | processed／invalid／duplicate累積 | G01候補 | point-in-time FLAGと一致しない | `src/orderflow/footprint.py:137-147`; `Condition Dictionary:78-109` |

`footprint.py`はVA%／POC／VAH／VALを計算しない。現行VAはwebapp側で70%を
ハードコードして計算する (`pipeline.py:649-652`; `webapp/push_broker.py:36-58`)。
これはG11のsession／rolling_1h契約ではなく、CalibrationBook経由でもないため再利用不可。

### 3.5 Order Book

| 検出器 | 出力属性/メソッド | 型 | 値の意味 | 対応するG01-G15 family | condition key候補 | 根拠（file:line） |
|---|---|---|---|---|---|---|
| `OrderBookStateManager` | `apply()` | `ApplyResult` | update適用、再初期化、gap検出 | G01候補 | `depth_sequence_contiguous`, `depth_gap_absent`候補。ただしreset／観測境界未定義 | `src/orderflow/orderbook.py:84-89,119-130,182-240`; `Condition Dictionary:82-109` |
| `OrderBookStateManager` | `is_initialized` | `bool` | 現在bookがinitializedか | G01 | `depth_book_synced`候補 | `src/orderflow/orderbook.py:144-157`; `Condition Dictionary:82` |
| `OrderBookStateManager` | `snapshot()` | `OrderBookSnapshot`または`None` | last update IDと全bid/ask price→quantity | G05 / G06 | top10 raw、cumulative depth、queue imbalance、microprice、wall concentration候補 | `src/orderflow/orderbook.py:68-81,148-157`; `Condition Dictionary:271-302` |
| `OrderBookSnapshot` | `bid_quantity_at()`, `ask_quantity_at()` | `Decimal` | 指定価格の現在数量 | G05 / G06候補 | point-in-time level quantity材料 | `src/orderflow/orderbook.py:77-81` |
| `OrderBookStateManager` | public counters | `int` | snapshot／diff／stale／gap累積 | G01候補 | `depth_snapshot_applied`, `depth_gap_absent`等はcounter差分から候補。ただしreset／freshness契約未定義 | `src/orderflow/orderbook.py:103-115`; `Condition Dictionary:82-109` |

G07に必要なwindow別add／cancel／net flow／refresh／pull／stack／turnoverは、
`ApplyResult`にも`OrderBookSnapshot`にも存在しない
(`src/orderflow/orderbook.py:68-89`; `Condition Dictionary:304-355`)。
snapshot間差分からadd/cancel量を作ることは新規stateful集計であり、refreshの「best近傍」、
pull／stack ratioの分母、level turnoverの定義は正本から一意に決まらない。

### 3.6 既存Ingestion Adapter

| 出力経路 | 固定生成key | 入力 | 根拠 |
|---|---|---|---|
| CVD | `cvd_change_5s`, `cvd_slope_5s` | `cvd_samples` | `src/strategy_engine/ingestion/condition_adapter.py:46-61` |
| Book wall | bid/ask wall concentration、nearest wall distance | best-first `bid_levels` / `ask_levels`と`tick_size` | `src/strategy_engine/ingestion/condition_adapter.py:63-87` |
| OI | 5m change／pct／joint state | OI／price samples | `src/strategy_engine/ingestion/condition_adapter.py:89-111` |
| pass-through | 任意key | `pre_aggregated` | `src/strategy_engine/ingestion/condition_adapter.py:113-119` |

### 3.7 補足: 指示対象外だが既存のFlow Price Response

完成済み`FlowPriceResponseDetector`は30s／60s／180s／300s／900s／1800sの
`buy_volume`、`sell_volume`、`delta`、first/last/high/low、price change等を
public `FlowResponseSnapshot`として返す
(`src/orderflow/flow_price_response.py:39-60,109-143,266-326`)。

- 30s／300sの`delta`はG10 `trade_delta_30s`／`trade_delta_5m`の有力DERIVE材料。
- priceは保持するが、G09の「progress」「efficiency」「no-progress」「reversion」の式と
  tick-size契約が正本にないため、key化はまだできない。
- `state`はthreshold適用済みの観測分類であり、Tier A数値の代用にはしない
  (`src/orderflow/flow_price_response.py:328-354`)。
- Live／Replayとも`flow_response`をpublic tupleへ保持する
  (`pipeline.py:462-464,1149-1151,1177-1190`)。

完成済みFlow Price Responseのロジック・出力・UIは変更対象にしない。

## 4. G16 13件とのギャップ分析

判定規則:

- `DIRECT`: public出力値が同じ意味・windowのcondition値。
- `DERIVE`: public出力だけからthresholdなしの単純集計で作れる。
- `NOT_AVAILABLE`: 必須材料、window、reference、timestampまたは式が不足。
- 1 row内に一部DERIVEがあっても、G16成立に必要な材料が1つでも欠ければ全体判定は
  `NOT_AVAILABLE`とする。

| G16 key | 必要な材料カテゴリ | 既存検出器で計算済みか | 検出器名とpublic出力 | condition keyへの変換方法 |
|---|---|---|---|---|
| `flow_price_divergence_active` | flow方向、matching price progress | flowは可、正本どおりのprice progress不可 | CVD `tick_delta/tick_cvd`; FlowResponse `delta/price_change` | **NOT_AVAILABLE**。G08/G10はDERIVE可。G09 progress式・tick size・matching window未定義 (`G16 Draft:762`) |
| `bid_absorption_like_active` | sell aggression、下方停止、bid location | detectorは合成結果のみ。Tier A材料は未公開 | Absorption `current()`; CVD tick output; OrderBook snapshot | **NOT_AVAILABLE**。aggressionはDERIVE可だがG09 no-progressと対象bid referenceなし (`G16 Draft:763`) |
| `ask_absorption_like_active` | buy aggression、上方停止、ask location | detectorは合成結果のみ。Tier A材料は未公開 | 同上 | **NOT_AVAILABLE**。aggressionはDERIVE可だがG09 no-progressと対象ask referenceなし (`G16 Draft:764`) |
| `upside_breakout_attempt` | initiative buy、上方progress、upper reference relation | buy flowは可、progress／reference不可 | CVD tick output; OrderBook snapshot | **NOT_AVAILABLE**。G08はDERIVE可。G03 selectorとG09 progressなし (`G16 Draft:765`) |
| `downside_breakout_attempt` | initiative sell、下方progress、lower reference relation | sell flowは可、progress／reference不可 | CVD tick output; OrderBook snapshot | **NOT_AVAILABLE**。G08はDERIVE可。G03 selectorとG09 progressなし (`G16 Draft:766`) |
| `upside_breakout_follow_through` | prior upside break、buy participation継続、上方progress | buy flowのみ可 | CVD tick output; FlowResponse snapshot | **NOT_AVAILABLE**。prior-break state、reference identity、継続window、G09 progressなし (`G16 Draft:767`) |
| `downside_breakout_follow_through` | prior downside break、sell participation継続、下方progress | sell flowのみ可 | CVD tick output; FlowResponse snapshot | **NOT_AVAILABLE**。prior-break state、reference identity、継続window、G09 progressなし (`G16 Draft:768`) |
| `upside_breakout_failure` | prior break、non-acceptance、reference下復帰 | 必須3要素なし | Footprint levels／UI VAは意味・window不一致 | **NOT_AVAILABLE**。G03 generic reference、G09 reversion、G11 acceptance、temporal stateなし (`G16 Draft:769`) |
| `downside_breakout_failure` | prior break、non-acceptance、reference上復帰 | 必須3要素なし | 同上 | **NOT_AVAILABLE**。G03 generic reference、G09 reversion、G11 acceptance、temporal stateなし (`G16 Draft:770`) |
| `bid_passive_defense_holding` | bid refresh/add/net/stack、price holding、reference | static bookのみ可 | OrderBook snapshot | **NOT_AVAILABLE**。G07 event flow、G09 holding、defended bid identityなし (`G16 Draft:771`) |
| `ask_passive_defense_holding` | ask refresh/add/net/stack、price holding、reference | static bookのみ可 | OrderBook snapshot | **NOT_AVAILABLE**。G07 event flow、G09 holding、defended ask identityなし (`G16 Draft:772`) |
| `bid_passive_defense_failed` | prior bid defense、refresh停止／pull、支持下抜け | static bookのみ可 | OrderBook snapshot | **NOT_AVAILABLE**。G07 event flow、prior state、support identity、break ruleなし (`G16 Draft:773`) |
| `ask_passive_defense_failed` | prior ask defense、refresh停止／pull、抵抗上抜け | static bookのみ可 | OrderBook snapshot | **NOT_AVAILABLE**。G07 event flow、prior state、resistance identity、break ruleなし (`G16 Draft:774`) |

## 5. `pre_aggregated`経路の現状

### 5.1 production source

2026-07-27の全`Delta_Engine_Pro4web/src/**/*.py`検索実測:

| 検索 | 件数 | 内容 |
|---|---:|---|
| `pre_aggregated` | 4 | `src/strategy_engine/ingestion/market_state.py:72`のfield定義、`src/strategy_engine/ingestion/condition_adapter.py:41,115,118`の読取だけ |
| `MarketStateSnapshot(` | 0 | production constructorなし |
| `IngestionAdapter(`または`.to_conditions(` | 0 | production呼出しなし |

`MarketStateSnapshot`自身も「future replay/detector-fed producerがpopulateする」と明記する
(`src/strategy_engine/ingestion/market_state.py:1-6`)。

結論:

- `pipeline.py`／ReplayPipelineは`MarketStateSnapshot`を作成しない。
- Live／Replayの`pre_aggregated`に現在入る値は**何もない**。
- AdapterはEngine production経路へ接続されておらず、現状はtest fixtureだけが呼ぶ。

### 5.2 test-only使用

testは`buy_no_progress_ratio_1s`、`downward_progress_ticks_1s`、
`bid_refresh_count_1s`、`bid_pull_ratio_1s`を手入力してpass-throughだけを検証する
(`tests/strategy_engine/test_ingestion_adapter.py:87-103`)。
E02／E03 integrationも同様にfixture値である
(`tests/strategy_engine/test_ingestion_adapter.py:130-157`)。
これはproducerの存在証明ではない。

## 6. NOT_AVAILABLE一覧

| 不足材料／契約 | 不足内容 | 根拠 |
|---|---|---|
| production snapshot wiring | snapshot constructor、adapter call、Engineへのhandoffがない | §5実測; `src/strategy_engine/ingestion/market_state.py:1-6` |
| deterministic `engine_time_ns` | Live/Replay pipelineはMarketState用monotonic時刻を生成しない | `src/strategy_engine/ingestion/market_state.py:18-31,57-72`; production検索0件 |
| authoritative tick size | OrderBook snapshot／ExchangeProfileにtick sizeがなく、MarketStateだけがoptional fieldを持つ | `src/orderflow/orderbook.py:68-75`; `src/normalization/normalizer.py:93-100`; `src/strategy_engine/ingestion/market_state.py:65-72` |
| G07 Book Event Flow | window別add/cancel/net/refresh/pull/stack/turnover/depth changeが未計算・未公開 | `src/orderflow/orderbook.py:68-89,103-115`; `Condition Dictionary:304-355` |
| G09 exact price response | progress、impact、efficiency、no-progress、reversionの機械式とpublic exact-window出力なし | `Condition Dictionary:410-453`; `G16 Draft:762-774` |
| G03 strategy reference | upper/lower／defended referenceのselector、identity、priceなし | `G16 Draft:765-774` |
| G11 session／rolling profile | specified Footprint detectorはbar levelsだけ。UI VAは70%固定・session/rollingでない | `src/orderflow/footprint.py:75-82,130-200`; `webapp/push_broker.py:36-58`; `Condition Dictionary:496-531` |
| temporal prerequisite | attempt→follow-through/failure、holding→failedの状態履歴なし | `G16 Draft:767-774,787-794` |
| Live/Replay public handoff | Replayはdetector local、LiveもFootprint／Imbalanceはprivate | `pipeline.py:435-481,1137-1153` |
| G08 notional／large-trade count | CvdUpdateにpriceなし。large判定はCalibrationBook threshold未定義 | `src/orderflow/cvd.py:77-84`; `Condition Dictionary:373-381,397-405` |

## 7. 推奨Producer設計方針（提案・未確定）

### 7.1 Stage 2前に正本化すべきProducer Input Contract

1. LiveとReplayで共通の`engine_time_ns`生成規則。
2. symbol別authoritative `tick_size`供給元。
3. G07各keyのlevel scope、分子、分母、window境界、reset、gap後の扱い。
4. G09各keyのprice reference、tick／notional単位、window境界。
5. G11のsession境界、rolling_1h、VA%、acceptance定義。
6. Producerへnormalized trade／depth updateを渡してよいか。
   public detector output限定を維持する場合、G07とprice sequenceは完備できない。
7. producer出力のfreshness、window complete、gap、resync後cooldown契約。

### 7.2 承認後の最小構成案

`src/strategy_engine/ingestion/snapshot_producer.py`をstatefulかつthreshold-freeにし、
public value objectだけを受け取る明示APIを持たせる。

```text
observe_cvd(CvdUpdate, Candle | None)
observe_footprint(FootprintBar)
observe_imbalance(ImbalanceResult)
observe_absorption(AbsorptionResult | None)
observe_book(OrderBookSnapshot, approved_time, approved_tick_size)
build_market_state(engine_time_ns) -> MarketStateSnapshot
```

ただしG07を実装するには、上記にapprovedなbook update／before-after observation contractを
追加する必要がある。これは現指示の「検出器出力だけ」からのscope拡張なので、承認なしに行わない。

設計原則:

- detector private属性は使用しない。
- Live／Replayの両call siteから同じproducer instance APIを呼ぶ。
- numeric値は`Decimal`のまま保持し、外部化時だけ`str`にする。`float()`は禁止。
- 完成windowとfresh materialが揃ったkeyだけを出し、欠測はomitする。
- thresholdが必要なlarge trade／acceptance／state flagはCalibrationBook確定までomitする。
- `AbsorptionResult`や`FlowResponseState`をTier A raw値として逆変換しない。
- webappの70% VAをG11 producerへ流用しない。
- `src/strategy_engine/ingestion/condition_adapter.py:115-119`は既にpass-through可能であり、主な不足はadapter改変より
  pipeline→producer→MarketStateSnapshotの配線である。

### 7.3 想定変更範囲の修正提案

Stage 2でproduction値を得るには、新規`snapshot_producer.py`だけでなく、
Live／Replay双方が存在する`src/pipeline.py`の観測点からproducerを呼ぶ変更が必要である。
これは当初想定の「condition_adapter.pyへのmerge」だけでは完結しない
(`pipeline.py:435-598,974-1447`; §5 production call 0件)。

変更範囲とInput Contractをお館様が承認するまで、Stage 2へ進まない。

## 8. 停止条件とcheckpoint

- checkpoint最終更新: 2026-07-27 14:07:26 JST。
- 承認範囲: Stage 1 read-only棚卸しと本報告書作成のみ。
- 完了済み:
  - PROJECT_MEMORY全文954行を確認。
  - pipeline 1,450行、指定5検出器実在file、adapter、G06〜G11、G16 Draft §4を確認。
  - public interface、Live／Replay call site、全production `pre_aggregated` call siteを照合。
  - 13 G16 keyをDIRECT／DERIVE／NOT_AVAILABLE基準で分析。
  - 棚卸し表25行、G16 13 key各1行、必須6章、placeholderなしを機械確認。
- 未完了: Snapshot Producer実装、pipeline統合、正本更新、Composite Synthesis、較正。
- 変更file: 本報告書1 fileのみ。
- source、正本、test、runtime、raw data、収録基盤: 無変更。
- commit/push: なし。
- 回帰実測:
  - 通常権限で`python -m pytest -q tests -p no:cacheprovider --basetemp .pytest_snapshot_stage1_20260727_1315_escalated`を実行。
  - **574 passed, 1 skipped in 35.22s**。全80 tracked test fileを対象とした。
  - 先行sandbox実行2回は既存ACL拒否directoryのcollection error、およびsandbox生成basetempのsetup errorで未完走。assertion resultではない。
  - 今回作成した専用basetempは検証後に削除済み。
- 発動した停止条件:
  - public属性だけではG07/G09/G11とreference／temporal stateへアクセスできない。
  - 現public pipeline interfaceはLive／Replayで非対称。
  - detector合成結果とTier A keyを同一視すると意味不一致／循環になる。
- blocker限定範囲: Snapshot Producer Stage 2と、それに依存するComposite Synthesisだけ。
- 次の再開位置:
  1. 本報告書の根拠・回帰結果をClaude web／お館様が検証。
  2. §7.1 Input Contractと`pipeline.py`変更範囲を承認。
  3. その後にStage 2設計を確定。
