# Hook Detector / Trigger Observe 基盤 — 第1段階 設計提案

作成時刻: 2026-07-26 08:41 JST
対象: `Delta_Engine_Pro4web` / branch `ui-refresh-v2`
状態: **設計提案。実装未着手。ユーザー承認待ち。**

参照:

- `ArchitectureRepository/00_Master/PROJECT_MEMORY.md`
- `ArchitectureRepository/00_Master/ORDERFLOW_ENTRY_TRIGGER_DESIGN_HANDOFF_20260726.md`
- `detector_implementation_instruction.md`
- `フックトリガーカテゴリhook_trigger_catalog_v1.md`

---

## 0. 結論

次の構造を提案する。

1. 既存分析器、Flow Price Response、3段チャート、WebApp表示は変更しない。
2. 新しいHook検出層を `src/orderflow/hooks/` に独立追加する。
3. 既存の「検出可能」素材も、B01のような明示的Hook IDへ変換するadapterを置く。
4. DOM、trade、liquidation、OI、candle、Flow transitionを、同じ`HookEvent`時刻規約へ投影する。
5. 閾値は別設定fileへ置き、実測分布から生成されていないHookは`UNCALIBRATED`として発火禁止にする。
6. 型はYAMLで宣言し、主フック、確認、否定、文脈、方向、順序、expiry、duplicate、re-armをcode変更なしで定義する。
7. 全型は`OBSERVE`だけで同時開始する。Flow単体sidecarは使用しない。
8. Hook、ニアミス、型発火、outcomeは新しいappend-only Parquetへ保存し、既存記録を変更しない。
9. DOM 100ms経路では増分計算だけを行い、保存、分位計算、集計はhot pathから外す。
10. Stage 2以降は、本書に対するユーザー承認後に開始する。

この構造なら、独立指標を説明不能なscoreへ戻さず、「どの現象が、どの根拠と反対根拠を伴い、
どの時刻に成立したか」をそのまま比較できる。

---

## 1. 変更しない境界

次は本作業の変更対象外とする。

- `src/orderflow/flow_price_response.py`の既存分類条件
- 6つのFlow時間窓の意味
- 3段チャート、8パターン、OI Context、Flow Event表示
- 既存CVD、Footprint、Imbalance、Absorptionの画面上の意味
- retired `SignalEngine`を単一scoreへ戻すこと
- `AnalysisEngine`を多数決BUY/SELLへ変更すること
- Flow state単体からBUY/SELLを作ること
- HFMへのLIVE注文
- 既存Parquet、DuckDB、JSONLの削除、改変、上書き

Hook層は既存出力を読み、新しい観測eventを横に追加するだけとする。

---

## 2. 着手前監査で確認した事実

### 2.1 現行接続点

| 入力 | 現行実装 | Hook層の接続点 |
|---|---|---|
| DOM | `orderflow/orderbook.py` | `OrderBookStateManager.apply()`が`applied=True`を返した直後 |
| trade | `pipeline.py`のnormalized trade `handle()` | 正規化直後。既存分析器と同じ到着順 |
| absorption | `orderflow/absorption.py` | `current()`の状態そのものではなく、episodeの開始／終了edgeをadapter化 |
| Flow Response | `FlowResponseOutcomeTracker.register()` | 非UNCLEARの新規state transition |
| liquidation | `normalize_raw_liquidation()` | 正規化直後。raw `o.T`もHook evidenceへ保持 |
| OI | `webapp/oi_poller.py` | 正値検証後、保存と同じsampleをHook runtimeへ渡す |
| 1m candle | `CvdCalculator`のclosed candle | bar close後だけ使用 |
| native 5m/10m | `NativeExecutionCoordinator` | 本当にcloseした時刻以後だけ使用 |
| HFM quote | `webapp/hfm_quote_tailer.py` | latest quoteを発火時contextとしてas-of参照 |

### 2.2 データ監査

2026-07-26 08:38 JST前後のread-only監査結果:

- 停止済み`data/duckdb/orderflow.duckdb`
  - trades: 11,181,860
  - candles: 6,275
  - OI samples: 6,615
  - Flow Response events: 12,011
  - Flow Response outcomes: 46,492
- 稼働中05M `/api/stats`
  - processed trades: 271,521
  - applied depth diffs: 282,563
  - applied snapshots: 1
  - detected gaps: 0
  - book synced: true
- `data/recordings`の板録画3本
  - 各2,939行
  - 全行`depthUpdate`
  - `depthSnapshot`は0
  - `clean_strong`は数量0levelも0件で、削除命令を失っている
- liquidation
  - runtimeの`deque(maxlen=200)`だけ
  - rawまたはnormalized liquidationの履歴永続化なし
- HFM
  - `data_05M/research/hfm_mt5_ticks_20260725.parquet`は利用可能
  - 現在のlive quoteは`STALE`であり、発火時にLIVE値が必ず存在するとは限らない

指示書記載の「trades 885k」「OI 14,053件」と、現在アクセスできる保存物の件数は一致しない。
対象期間、cutoff、DBが異なる可能性があるため、実装時は入力manifest、期間、SHA-256、行数を
固定し、どの母集団から分位を作ったかを曖昧にしない。

### 2.3 この監査から決まる制約

- 現存3録画はDOM分位算出とDOM決定論リプレイに使用禁止。
- DOM閾値を仮の数値で埋めない。
- liquidation閾値を現在の200件bufferだけから確定しない。
- 有効なSnapshot＋全diff＋数量0＋trade＋forceOrderのappend-only収録をStage 2冒頭に追加する。
- 収録待ちの間も、契約、検出器、synthetic test、保存、replay runnerの実装は独立して進める。
- 分位未確定Hookは`UNCALIBRATED`で沈黙させ、弱い型だけ先行observeしない。

---

## 3. 提案するmodule構成

### 3.1 Hook検出層

```text
Delta_Engine_Pro4web/
  src/orderflow/hooks/
    __init__.py
    models.py                    # HookEvent / evidence / quality / time contract
    registry.py                  # A01...H04の定義とside意味
    runtime.py                   # 入力順序、detector dispatch、edge/dedupe
    quality.py                   # book sync、gap、stale、missing、clock quality
    dom_features.py              # DOM増分feature cache
    dom_wall.py                  # A01-A04, A19-A20, A23-A24
    dom_liquidity.py             # A05-A10, A15-A16, A21-A22
    dom_quote_motion.py          # A11-A14
    dom_iceberg.py               # A17-A18
    tape_adapter.py              # B01-B08, B11-B12, B15-B16, B19
    interaction.py               # C01-C09（既存C01/C02はadapter）
    flow_transition.py           # D01-D08（既存D01-D05はadapter）
    liquidation.py               # E01-E06
    open_interest.py             # F01-F05
    price_structure.py           # G01-G11
    context_adapter.py           # G12 / H04

  src/observation/
    raw_journal.py               # create-new、時刻rotation、欠落manifest
    hook_storage.py              # Hook event/feature専用background writer
    hook_replay.py               # raw arrival orderの決定論replay
    hook_calibration.py          # 分布、日別分位、閾値artifact
    hook_frequency.py            # Hook別発火/日、noise/silent集計
    latency.py                   # p50/p95/p99/max

  src/playbooks/
    models.py                    # PlaybookObservation / evidence snapshot
    config.py                    # YAML schemaとfail-fast validation
    engine.py                    # 主＋確認＋否定＋文脈＋方向
    state_machine.py             # arm/confirm/expire/dedupe/re-arm
    outcome.py                   # 60/180/300/600秒 return/MFE/MAE
    storage.py                   # fire/near-miss/reject/outcome
    execution_gate.py            # Stage 3でもOBSERVE固定の封印点

  config/
    hook_observer.yaml           # window、band、quality、performance
    hook_thresholds.yaml         # quantile、算出値、manifest hash、status
    playbooks.yaml               # T01-T50宣言

  tools/
    capture_hook_inputs.py
    calibrate_hook_thresholds.py
    replay_hook_detectors.py
    report_hook_frequency.py
    validate_playbooks.py
```

既存`config/config.yaml`はstrict schemaで未知keyを拒否するため、Hook用設定は別fileとする。
これにより既存起動条件を変えず、Hook基盤だけを独立検証できる。

### 3.2 runtime接続

`webapp/main.py`で`HookRuntime`を1個だけ生成し、既存callbackと合成する。
`pipeline.py`へ必要な新規接続は、適用済みDOM更新を通知する
`on_book_update(update, apply_result)`の1点を基本とする。

trade、liquidation、Flow Response、closed candle、native candleは既存callbackまたは同じ
処理位置からHook runtimeへ渡す。OIとHFM quoteは既にWebApp側にあるため、同じruntimeへ渡す。

`webapp/static/index.html`は変更しない。Hook/Playbook表示は本指示のStage 1〜3に含めず、
必要になった時点で別途見え方の承認を取る。

---

## 4. 共通時刻契約

すべてUTCで保存し、次の時刻を混同しない。

| field | 意味 |
|---|---|
| `source_time` | exchangeまたは入力が示す時刻 |
| `received_time` | DeltaEngineが受信したUTC時刻 |
| `available_time` | 判断に合法的に使用可能になった時刻 |
| `detected_time` | detectorがHook成立を確定した時刻 |
| `armed_time` | playbookの主フック成立時刻 |
| `confirmed_time` | 必要な確認が揃った時刻 |
| `decision_time` | OBSERVE発火を確定した時刻 |
| `pivot_time` | divergence等の現象中心時刻。decision時刻として使用禁止 |

規則:

- 1m/5m/10m candleの情報はclose後だけ使用する。
- divergenceは`detected_time`以後だけ使用し、pivotへ遡って発火しない。
- OIは`source_time <= decision_time`を満たす直近sampleだけを使い、max age超過は`MISSING`。
- HFM quoteはsource/received/age/statusを保存し、STALEをLIVE価格として扱わない。
- DOMはupdate IDと`pu`を順序の正本とし、gapから次の有効Snapshot同期まで全A/C Hookを抑止する。
- REST Snapshotの時刻はlocal receipt metadataであり、exchange event timeと偽らない。

既存`OrderBookStateManager`の初回diff受理はlive互換のため変更しない。Hook研究用には別の
`DomDataQualityGate`を置き、最初のdiffが
`U <= lastUpdateId + 1 <= u`、以後が`pu == previous u`を満たす区間だけを有効にする。

---

## 5. HookEvent共通形式

最低限、次をParquetへ保存する。

```text
hook_event_id
hook_id
detector_version
config_hash
input_manifest_hash
symbol
side
direction_hint
source_time
received_time
available_time
detected_time
source_sequence
anchor_price
binance_bid
binance_ask
binance_mid
metric_name
metric_value
threshold_value
threshold_quantile
episode_id
quality_status
quality_flags
evidence_json
```

`direction_hint`はHookの意味を表すだけで、注文命令ではない。
A17〜A20は意図を断定できないため、名称とpayloadに必ず`SUSPECTED`を残す。

同一現象の継続更新を水増ししないため、各detectorは
`INACTIVE -> ARMED -> ACTIVE -> CLEARED`のedgeだけをevent化する。
更新中の値はfeature記録へ残しても、Hook発火件数には数えない。

---

## 6. Detector設計

### 6.1 DOM A01〜A24

DOMはmidからの固定level数ではなく、設定されたbps帯の中で比較する。価格が変わっても
同じ市場距離を比べられるよう、数量、notional、level密度、gapをside別に算出する。

| Hook | 判定する観測事実 |
|---|---|
| A01/A02 | 同side・同距離帯の通常levelを大きく超えるBid/Ask levelが新規出現 |
| A03/A04 | A01/A02で追跡中のwallが、対応するaggressive約定を十分受けず消滅／大幅減少 |
| A05/A06 | bps帯内のBid/Ask合計notionalが短時間に急減 |
| A07/A08 | 同合計notionalが短時間に急増 |
| A09/A10 | 同じ距離帯のBid/Ask notional比が極端 |
| A11/A12 | best Bid低下／best Ask上昇が短時間に連続 |
| A13/A14 | best Bid上昇／best Ask低下が短時間に連続 |
| A15 | spread bpsまたは通常spread比が上側極端値へ拡大 |
| A16 | A15 episode後、spreadが通常帯へ回復 |
| A17/A18 | 同一Bid/Ask価格で約定消化と補充が反復する`ICEBERG_SUSPECTED` |
| A19/A20 | 大口wall出現と未約定pullの反復である`SPOOFING_SUSPECTED` |
| A21/A22 | 上／下のbps帯でnotional密度が下側極端、または隣接level gapが上側極端 |
| A23/A24 | 大口Bid/Ask wallのanchor価格がmarketと同方向へ複数回移動 |

wallは価格だけでなく`side + price band + episode`で追跡する。価格が1tick変わっただけで
別のwallへ分裂させない一方、無関係なwallを結合しないband幅も設定file化する。

### 6.2 板×約定 C03〜C09

既存`AbsorptionDetector`は変更せず、その出力とDOM/trade episodeを新しい関係性detectorへ渡す。

| Hook | 状態機械 |
|---|---|
| C03/C04 | absorption／defense成立後、anchor板消滅＋価格cross＋再補充なしで`ABSORPTION_FAILED` |
| C05 | 同side・同anchor bandの独立absorption episodeが設定時間内に反復 |
| C06 | A01/A02 wallへ反対側aggressive tradeが到達し、消化を開始 |
| C07/C08 | C06後、wall残量が消滅し、価格がwallの向こうへcross |
| C09 | E系liquidation burst中、対応sideの板が維持／補充され、価格反応が下側極端 |

C01/C02も既存resultの毎tick継続をそのまま数えず、開始edgeをHook化する。

### 6.3 liquidation E01〜E06

`SELL forceOrder = long liquidation`、`BUY forceOrder = short liquidation`を維持する。

| Hook | 判定 |
|---|---|
| E01/E02 | 単発liquidation notionalの上側極端 |
| E03/E04 | 1秒等の設定windowで件数またはnotionalが上側極端 |
| E05 | burst後の絶対価格反応が下側極端 |
| E06 | burst episode後、rate/notionalが通常以下へ落ち、inter-arrivalが上側極端 |

raw `E`と`o.T`を両方保存する。side、price、quantityが非正値／非有限ならHook入力から拒否する。

### 6.4 OI F01〜F05

1分／5分の設定windowについて、window始点以前の直近sampleと現在sampleをas-of結合する。
欠測を補間せず、sample age超過または始点sampleなしは発火しない。

- F01: 有意なOI増＋価格上昇
- F02: 有意なOI増＋価格下落
- F03: 有意なOI減＋価格上昇
- F04: 有意なOI減＋価格下落
- F05: `abs(OI change %)`の上側極端

これは新規long/shortを断定する注文命令ではなく、保存済みの観測contextである。

### 6.5 価格構造 G01〜G11

1m closed candleを基本にし、bar途中を過去へ混ぜない。

- G01/G02: 設定lookbackのconfirmed高値／安値へのtouch
- G03/G04: 高値／安値を有意距離break
- G05/G06: break episode後、期限内に旧rangeへreclaim
- G07: session VWAPへのtouch
- G08: ATR等で正規化したVWAP乖離の上側極端
- G09: calibration期間のVolume ProfileからHVN/LVNを作り、runtimeはlevel lookupだけ行う
- G10: 価格末尾の出来高集中から選んだround gridへのtouch
- G11: rolling range上端／下端への正規化距離が下側極端

G09はoffline生成を使えば100ms DOM経路を重くしないため、現時点ではskipしない。

### 6.6 Flow Response D06〜D08

既存state分類は一切再計算しない。

- D06: 同windowで`EFFECTIVE -> same-pressure TRAPPED`へ遷移し、遷移時間が下側極端
- D07: `TRAPPED -> other state`の解消edge。from/to、episode durationを事実として保存
- D08: 同じpressure side/stateが複数windowで同時にACTIVE

D08は、6窓が同じ約定を含むため独立票として数えない。payloadへwindow一覧と重複由来を残し、
多数決scoreにはしない。

---

## 7. 閾値の分位対応表

`P99`は対象featureの経験分布99%点、`P01`は1%点を表す。対称Hookはside別に別々の
分布を作り、BUY側の値をSELL側へコピーしない。

初期quantileは次のとおり提案する。実際の数値は有効入力を収録してから生成し、
本表のquantile自体も発火頻度報告で変更提案はできるが、結果を見て無断変更しない。

| Hook | feature | 初期quantile／規則 |
|---|---|---|
| A01/A02 | side別level notional / 同距離帯median | P99.5 |
| A03/A04 | 追跡wallの減少率 | negative level changeのP99 |
| A03/A04 | wall期間中のexecuted_qty / wall_qty | P10以下を「未約定pull」条件 |
| A05/A06 | side帯notionalの100ms/500ms/1s減少率 | 各window P99 |
| A07/A08 | side帯notional増加率 | 各window P99 |
| A09/A10 | `log(bid_notional / ask_notional)` | 上P99／下P01 |
| A11-A14 | best quoteの累積変位bps | side・方向別P99 |
| A11-A14 | window内連続step数 | side・方向別P99 |
| A15 | spread bps、rolling median比 | P99.9 |
| A16 | A15後のspread | 通常分布P50以下へ復帰 |
| A17/A18 | 同一価格の補充回数 | P99 |
| A17/A18 | executed_qty / 初期visible_qty | P99 |
| A19/A20 | 未約定wall出現→pull cycle数 | P99.5 |
| A21/A22 | side帯notional密度 | P01 |
| A21/A22 | 最大隣接gap bps | P99.5 |
| A23/A24 | wall anchorの同方向移動回数／累積bps | 各P99 |
| B01/B02 | side別連続trade数 | P99 |
| B03/B04 | side aggression ratio | 上P95／下P05 |
| B05 | trades/sec | P99 |
| B06 | inter-trade gap ms | P99 |
| B07/B08 | trade notional | side別P99 |
| B11/B12 | sweep qty、level数 | 各P99 |
| B15/B16 | window deltaの符号付き絶対量 | side別P99 |
| B19 | persistence | pressure side別P95 |
| C03/C04 | defense後のcross bps、残量減少率 | 各P90（collision条件付き分布） |
| C05 | 同anchor absorption episode数 | P99 |
| C06 | wallへのaggressive_qty / visible_qty | P90 |
| C07/C08 | wall消化率 | P99、かつcross成立 |
| C09 | liquidation後のabs(price move bps) | 条件付きP10以下 |
| C09 | 対応side補充率 | 条件付きP90以上 |
| D06 | EFFECTIVEからTRAPPEDまでの時間 | transition分布P10以下 |
| D07 | exact state exit | magnitude閾値なし。duration percentileをevidence保存 |
| D08 | 同時ACTIVE window数 | 観測分布P90。独立票扱い禁止 |
| E01/E02 | 単発liquidation notional | side別P99 |
| E03/E04 | window内件数、notional | 各P99.5 |
| E05 | burst後のabs(price response bps) | 条件付きP10以下 |
| E06 | burst後rate/notional | 通常P25以下 |
| E06 | inter-arrival ms | burst後分布P99以上 |
| F01-F04 | abs(OI change %) | window別P75以上 |
| F01-F04 | abs(price change bps) | 同window別P60以上 |
| F05 | abs(OI change %) | window別P99 |
| G01/G02 | high/lowへの正規化距離 | touch距離分布P10以下 |
| G03/G04 | 既存高安からのbreak bps | excursion分布P90以上 |
| G05/G06 | break後retrace率 | failed-break分布P90以上 |
| G07 | VWAPへの距離 / 1m true range | P10以下 |
| G08 | abs(VWAP乖離) / ATR | P99 |
| G09 | price-bin volume density | HVN P90以上／LVN P10以下 |
| G10 | round gridへの距離 | touch分布P10以下 |
| G11 | range edgeへの距離 / range幅 | P10以下 |

G10のgrid幅だけは単純quantileでは決められない。候補gridごとの価格末尾別約定量集中度を
calibration期間で測り、集中が再現するgridだけを設定artifactへ採用する。`100/500`を勘で
固定しない。

---

## 8. 閾値生成手順

1. 入力manifestを先に作る。
   - path
   - file size
   - SHA-256
   - first/last source time
   - event type別行数
   - Snapshot数、diff数、trade数、forceOrder数、OI数
   - gap、duplicate、malformed、quantity 0 level数
2. 非正値、非有限値、修正前異常価格を既存project memoryの規則で除外する。
3. DOMは同期済み区間だけをfeature化する。
4. UTC日別にquantileを算出する。
5. 初期値は「全行を一括したquantile」だけでなく、日別quantileのmedian、IQR、min/maxも報告する。
6. 3日未満のDOM／liquidation標本は`PROVISIONAL`、有効履歴0は`UNCALIBRATED`とする。
7. 生成値、quantile、対象期間、manifest hash、tool versionを`hook_thresholds.yaml`へ書く。
8. runtimeは`value: null`、hash不一致、status不正のHookをfail closedで発火させない。
9. outcome成績を使って初期閾値を選ばない。分布と発火頻度の較正と、成績評価を分離する。

設定例:

```yaml
thresholds:
  A01:
    metric: level_notional_over_band_median
    quantile: 0.995
    value: null
    status: UNCALIBRATED
    sample_count: 0
    valid_days: 0
    input_manifest_sha256: null
```

---

## 9. append-only収録設計

現行`JsonlRecorder`は指定pathを`"w"`で開くため、既存recordへは使用しない。

新しいjournalは次を満たす。

- UTC時間ごとに新規fileをcreate-newで作る
- 既存pathがあれば上書きせず失敗
- Snapshot、全diff、数量0level、trade、forceOrderをarrival orderで保存
- REST Snapshotも同じstreamへ、receipt timeと取得理由を付けて保存
- writer queue overflow、process断、gapをmanifestへ記録
- 不完全segmentは削除せず`INVALID_FOR_REPLAY`とする
- close後にSHA-256と行数をmanifestへ確定
- Hook runtimeと保存は別queueにし、raw inputの処理順は変えない

稼働中05Mの既存DBを強制copy、停止、再起動しない。収録導入と再起動が必要になった時点で、
Stage 2の変更内容として先に報告する。

---

## 10. 決定論replayと発火頻度

replayはraw arrival orderを維持し、liveと同じ`HookRuntime`へ入力する。

同一input manifest＋同一config hashに対して、次が完全一致することを試験する。

- Hook event件数
- `hook_event_id`
- event順
- evidence値
- fire/near-miss/reject
- outcome

報告表:

| Hook ID | valid days | opportunities/day | fires/day | p50 interval | duplicate suppressed | status |
|---|---:|---:|---:|---:|---:|---|

`NOISY`と`SILENT`の境界も勘で固定せず、全Hookの`fires/day`分布から外れ値として示す。
ただし、意味上まれなA15やE03を他Hookと同じ件数へ無理に合わせない。調整案は提示し、
ユーザー確認前に値を変更しない。

---

## 11. 宣言的playbook基盤

### 11.1 YAML表現

```yaml
playbooks:
  T01:
    name: absorption_bounce
    enabled: true
    mode: OBSERVE
    direction: BUY
    primary:
      hook: C01
    confirmations:
      - hook: B03
        relation: same_side
        within_ms_from_quantile: 0.90
    vetoes:
      - hook: A05
        relation: bid_side
    contexts: []
    expiry_ms_from_quantile: 0.95
    duplicate_key: [playbook_id, direction, anchor_band]
    rearm:
      require_primary_clear: true
```

T04、T26、T31、T32、T37、T38のような順序型は`steps`で表す。
時間window、expiry、price move、anchor bandも設定fileに置き、codeへ埋め込まない。

必要なconfirmationが欠測した場合は成立にせず、`MISSING_REQUIRED_EVIDENCE`を保存する。
context欠測は設定された`missing_policy`に従うが、値を0やNEUTRALで補わない。

### 11.2 状態

```text
IDLE
  -> ARMED            primary成立
  -> CONFIRMED        必要confirmation成立、vetoなし
  -> OBSERVED_FIRE    最初の1回だけ記録
  -> COOLDOWN
  -> IDLE             re-arm条件成立

ARMED
  -> NEAR_MISS        confirmation未成立でexpiry
  -> REJECTED_VETO    veto成立
  -> REJECTED_QUALITY data quality失敗
```

各ENTRY候補は使用したHook、反対Hook、欠測Hookを全てevidence snapshotへ残す。

### 11.3 発火時共通record

```text
playbook_observation_id
playbook_id
playbook_version
mode
status                    # FIRE / NEAR_MISS / REJECTED_VETO / REJECTED_QUALITY
direction
armed_time
confirmed_time
decision_time
expiry_time
duplicate_key
binance_bid
binance_ask
binance_mid
hfm_source_time
hfm_received_time
hfm_bid
hfm_ask
hfm_spread
hfm_quote_age_ms
hfm_quote_status          # LIVE / STALE / MISSING
primary_evidence_json
confirmation_evidence_json
veto_evidence_json
context_evidence_json
missing_evidence_json
config_hash
input_manifest_hash
```

STALE HFM quoteをLIVEと偽らない。最後のraw値を監査用に保持する場合も、statusとageを必ず付ける。

### 11.4 outcome

新しいgeneric trackerを使用し、既存Flow trackerの意味を変更しない。

- horizon: 60 / 180 / 300 / 600秒
- Binance mid基準
- raw forward return bps
- direction-signed forward return bps
- MFE bps
- MAE bps
- target到達時刻とlag
- invalid/stale/gap status

HFM quoteがLIVEで継続している場合は、同じplaybook event IDへHFM bid/ask基準の別market outcomeも
保存できるようにする。ただしspread込みHFM成績を、ゼロspreadの分析方向正確性と混ぜない。

---

## 12. T01〜T50の搭載見込み

指示書scopeのA/C/D/E/F/Gと、既存B素材を明示Hookへadapter化した後の設計上の見込み:

- 搭載可能: 46型
- scope外Hook不足で搭載不可: 4型

| 型 | 不足Hook |
|---|---|
| T17 | B14 小口連打 |
| T34 | B09 大口買いcluster |
| T35 | B10 大口売りcluster |
| T36 | B13 平均約定size急増 |

残る46型には、単純同時成立だけでなく、T04、T26、T31、T32、T37、T38の順序条件も含む。
そのためStage 3はboolean ANDだけではなく、上記state machineと`steps`を実装する。

カタログの○は「素材を現行計算から得られる」という意味であり、現時点で全てが個別Hook IDを
発火しているわけではない。例えばTapeAnalyzerは連続数を持つが、その連続sideをdetailへ
保存していない。B adapterは既存表示を変えず、normalized tradeからside付きevidenceを独立生成する。

T01〜T50は比較対象であって、採用済みENTRY GOではない。全てOBSERVEし、成績確認前に
executionへ昇格させない。

---

## 13. 実装順序

### Stage 2A — 契約、収録、基礎

1. `HookEvent`、時刻、quality、config schema
2. append-only raw journalとmanifest
3. separate background storage
4. deterministic replay skeleton
5. 既存B/C01-C02/D01-D05/G12/H04 adapter
6. unit/property tests

### Stage 2B — Detector

1. DOM feature cache
2. A01-A16、A21-A22
3. A17-A20、A23-A24
4. C03-C08
5. E01-E06
6. C09
7. F01-F05
8. G01-G08、G10-G11
9. G09 offline profile
10. D06-D08

実装困難として事前skipするHookは現時点ではない。ただしA17〜A20は
`SUSPECTED`を外さず、入力品質が不足する期間は発火禁止とする。

### Stage 2C — Calibration / Replay報告

1. 有効収録manifest確定
2. feature分布と日別分位
3. threshold artifact凍結
4. deterministic replay
5. Hook別発火回数/日
6. latency報告
7. noisy/silentと調整案
8. ユーザー確認で停止

### Stage 3 — Playbook

1. YAML validator
2. temporal state machine
3. near-miss/veto/quality reject
4. Parquet保存
5. outcome tracker
6. T01〜T50 validationと46型搭載
7. 搭載／不足一覧
8. 全型`OBSERVE`固定
9. ユーザー確認で停止

### Stage 4

observe起動手順だけを報告し、ユーザーが起動する。勝手に起動しない。

---

## 14. 性能設計と検証

DOM hot path:

- Snapshot全体sortを100msごとに繰り返さない。
- 初回Snapshotでside別price indexを作り、diff levelだけを増分更新する。
- bps帯の集計値、best quote、wall episodeをcacheする。
- Decimalを維持する。
- Parquet、quantile、Volume Profile生成は別thread/process。

計測:

- detector別 `process_ns` p50/p95/p99/max
- input type別 total p50/p95/p99/max
- storage queue pending/high watermark
- queue overflow
- raw journal gap
- Hook events/sec
- memory増加

提案performance gate:

- DOM Hook hot path p99が10ms未満
- 100ms diff間隔に対しmax 25ms未満
- storage／journal queue overflow 0
- Hook追加前後で既存trade内部遅延p95の悪化が10ms未満

gateを超えた場合はobserveへ進まず、重いfeatureを非同期化またはbar-close化して再計測する。

---

## 15. 試験

- 各Hookの正例、境界、非発火、反対side
- Decimal、非正値、NaN/Infinity拒否
- DOM snapshot、diff、quantity 0 deletion
- initial sync、stale diff、gap、resnapshot
- wall出現、partial fill、full fill、pullの区別
- iceberg/spoof suspectedの反復とepisode clear
- liquidation side意味
- OI as-of、future sample不使用、stale/missing
- bar close availability、divergence pivotへの遡及禁止
- D08のwindow重複を独立票にしない
- duplicate、expiry、re-arm
- primary成立＋confirmation timeoutのnear-miss
- vetoとquality reject
- 同一replay 2回のevent ID／順序完全一致
- existing detector test
- pipeline regression
- WebApp chart寸法／Flow分類に変更がないこと

全体test件数は実装品質の一証拠であり、相場上の有効性の証明とは報告しない。

---

## 16. 承認を求める内容

次の4点への承認後、Stage 2Aへ進む。

1. Hook層を既存分析器の横へ独立追加するmodule構成
2. `hook_observer.yaml`、`hook_thresholds.yaml`、`playbooks.yaml`の3file分離
3. 有効DOM／liquidation履歴がないため、append-only収録を先に追加し、未較正Hookを発火禁止にする順序
4. Stage 2完了後に発火頻度を報告して停止し、Stage 3へ自動で進まないcheckpoint

承認前にcode、config、稼働system、既存データは変更しない。
