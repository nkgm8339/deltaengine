# Stage 2C-2 Hook測定値分布レポート
実行日時: 2026-07-30 11:15:29 JST
実行者: Codex
対象データ: stage2a_20260726_xz/full（全session）

## 実行条件

- 操作範囲: 収録済みfull streamのread-onlyリプレイ、分布集計、スクリプトと本レポートの作成。
- 非操作対象: `hook_thresholds.yaml`、`playbooks.yaml`、UI、収録データ、稼働中liquidation stream。
- 集計対象: A01-A24、C03-C08、D06-D08、F01-F05、G01-G11（49 Hook）。
- 対象外: E01-E06（liquidation依存）、C09（liquidation absorption）。
- 候補値を生成できない入力について、擬似値・補間値は作らない。count=0とし、理由を記録する。

## Phase 1: コードベース調査

### 1.1 リプレイの仕組み

#### integrity検証付きraw journal replay

- `Delta_Engine_Pro4web/src/observation/hook_replay.py`
  - `JournalIntegrityError`: 14行
  - `JournalRecord`: 18-23行（`sequence`、`record_type`、`received_time`、`payload`）
  - `JournalReplay`: 38行
  - `JournalReplay.__init__`: 41-63行。`session_meta.json`と`session_summary.json`を確認し、`allow_active=True`の場合だけsummary未作成sessionの確定済み部分を許容する。
  - `JournalReplay._load_manifest`: 65-92行。`manifest_events.jsonl`から`SEGMENT_CLOSE`と`FRAME_COMMIT`を読む。
  - `JournalReplay._measure_uncommitted_tail`: 94-104行。最後のcommit以降のtail byteを測る。
  - `JournalReplay._frame_records`: 125-171行。frameのoffset/長さ、SHA-256、XZ展開、件数、sequence範囲、summaryのcommitted件数を検証しながら逐次yieldする。
  - `JournalReplay.records`: 173-206行。frame形式を優先し、旧segment形式ではclose、segment SHA-256、件数、連番を検証する。
  - `JournalReplay.replay`: 208-213行。各recordの`payload`をcallbackへ渡す。
- `Delta_Engine_Pro4web/src/acquisition/replay.py`
  - `ReplaySource`は通常JSONLを一括ロードする実装であり、今回の917 MB XZ journalには使用しない。

#### journal書込み側とフォーマット

- `Delta_Engine_Pro4web/src/observation/raw_journal.py`
  - `_record_type`: 66-80行。`TRADE`、`DEPTH_UPDATE`、`DEPTH_SNAPSHOT`、`LIQUIDATION`等を分類する。
  - `AppendOnlyRawJournal`: 88行
  - `AppendOnlyRawJournal._manifest`: 190行
  - `AppendOnlyRawJournal.write`: 235行
  - `AppendOnlyRawJournal._writer_loop`: 270行。各recordをjournal version、sequence、record type、received time、payloadとして格納する。
  - `AppendOnlyRawJournal._finalize_session`: 465行
  - `CaptureCampaign`: 546行、`open`: 609行、`write`: 709行、`close`: 728行。
- session構成:
  - `session_meta.json`
  - `manifest_events.jsonl`
  - `raw-YYYYMMDDTHH.jsonl.xz`
  - 正常終了時は`session_summary.json`
- `FRAME_COMMIT`にはfile、offset、compressed bytes、frame SHA-256、record count、first/last sequence、first/last received timeがある。segment終了時には`SEGMENT_CLOSE`、session終了時には`SESSION_END`がある。

#### パイプライン再投入方法

- depth:
  - `Delta_Engine_Pro4web/src/normalization/normalizer.py`
    - `DataNormalizer.process_depth`: 386-403行
    - `normalize_raw_depth`: 473-564行
  - `Delta_Engine_Pro4web/src/orderflow/orderbook.py`
    - `OrderBookStateManager`: 97行
    - `apply`: 129-140行
    - `apply_initial_sync`: 142-151行
    - `snapshot`: 176-186行
  - production相当の順序は`Delta_Engine_Pro4web/src/pipeline.py`の`apply_verified_depth_sync`（1542行）と`process_live_depth`（1640行付近）から確認した。
- trade:
  - `Delta_Engine_Pro4web/src/normalization/normalizer.py`
    - `NormalizedTrade`: 150-160行
    - `normalize_raw`: 233-277行
    - `DataNormalizer`: 281行、`process`: 340-373行、`flush`: 375-381行
- 56 Hook候補のStage 2B detectorは、現行production `src/pipeline.py`から直接呼ばれていない。利用箇所はStage 2B単体テストとDOM benchmarkが中心である。このため今回のスクリプトが、既存normalizer/order book/flow/candle処理の出力を既存Hook detectorへ明示的に渡す。

### 1.2 Hook検出器のインターフェース

候補共通型:

- `Delta_Engine_Pro4web/src/orderflow/hooks/models.py`
  - `HookCandidate`: 85行。`metric_name`と`metric_value`が較正対象のcandidate value。
- `Delta_Engine_Pro4web/src/orderflow/hooks/detector_utils.py`
  - `make_candidate`: 51行。registry定義と測定値から`HookCandidate`を作る。

DOM A系:

- `src/orderflow/hooks/dom_features.py`
  - `DomFeatures`: 46行
  - `DomFeatureDelta`: 79行
  - `DomFeatureCache`: 84行、`process`: 102行。上位depthをbid/ask total、median、wall、spread、gapへ変換する。
- `src/orderflow/hooks/dom_wall.py`
  - `DomWallDetector`: 27行
  - `_appearance`: 34行（A01/A02）
  - `_pull`: 76行（A03/A04、A19/A20）
  - `_tracking`: 130行（A23/A24）
  - `process`: 156行
- `src/orderflow/hooks/dom_liquidity.py`
  - `DomLiquidityDetector`: 26行、`process`: 27行（A05-A10、A15/A16、A21/A22）。
- `src/orderflow/hooks/dom_quote_motion.py`
  - `DomQuoteMotionDetector`: 10行、`process`: 11行（A11-A14）。
- `src/orderflow/hooks/dom_iceberg.py`
  - `DomIcebergDetector`: 15行、`process_trade`: 24行（A17/A18）。trade前後DOMからreplenished/executed比を測る。

context C/D/E/F/G系:

- `src/orderflow/hooks/interaction.py`
  - `InteractionDetector`: 14行
  - `observe_absorption`: 20行（C03-C05）
  - `observe_wall_trade`: 84行（C06-C08）
  - `observe_liquidation_response`: 149行（C09、今回対象外）
- `src/orderflow/hooks/flow_transition.py`
  - `FlowTransitionDetector`: 26行、`process`: 34行（D06-D08）。
- `src/orderflow/hooks/liquidation.py`
  - `LiquidationDetector`: 26行、`process`: 103行、`observe_price`: 186行（E01-E06、今回対象外）。
- `src/orderflow/hooks/open_interest.py`
  - `OpenInterestDetector`: 22行、`process`: 30行（F01-F05）。
- `src/orderflow/hooks/price_structure.py`
  - `PriceStructureDetector`: 14行、`process`: 59行（G01-G11）。

既存派生入力:

- `src/orderflow/flow_price_response.py`
  - `FlowPriceResponseDetector`: 109行、`process`: 167行、`finalize`: 208行。正規化tradeから30/60/180/300/900/1800秒snapshotを作り、D detectorへ渡せる。
- `src/orderflow/cvd.py`
  - `Candle`: 88行
  - `CvdCalculator`: 193行、`process`: 223行、`finalize`: 277行。正規化tradeからclosed 1m candleを作り、G detectorへ渡せる。
- `src/orderflow/absorption.py`
  - `AbsorptionDetector`: 61行、`observe_trade`: 113行、`current`: 142行。

`UNCALIBRATED`でも各detectorはcandidateを生成する。threshold判定はdetectorの後段であり、分布集計では`HookCandidate.metric_value`を直接収集する。production pipelineの呼出し位置は未接続のため、今回のhost replay driverがcandidate層を構成する。

### 1.3 ThresholdBookの構造

- `Delta_Engine_Pro4web/src/orderflow/hooks/config.py`
  - `ThresholdBook`: 177行
  - `load`: 197-244行。YAMLをstrict key検証し、各entryを`HookThreshold`へ変換し、canonical JSONのSHA-256を計算する。
  - `threshold`: 246行
  - `status`: 250行
  - `evaluate`: 254-286行
  - `calibrated_hook_ids`: 288行
- `Delta_Engine_Pro4web/src/orderflow/hooks/models.py`
  - `HookThreshold`: 142行
  - `allows_fire`: 186行
  - `matches`: 189-203行
- `Delta_Engine_Pro4web/src/orderflow/hooks/runtime.py`
  - `HookRuntime`: 16行、`submit`: 42-67行。
- `Delta_Engine_Pro4web/config/hook_thresholds.yaml`
  - 2行: `default_status: UNCALIBRATED`
  - 6行: `thresholds: {}`

fail-closed順序は、entryなし/非CALIBRATED、manifest hash不一致、quality不正、metric不一致、数値threshold不一致で、それぞれeventを生成せずcounterを増やす（`config.py` 261-279行）。threshold判定はYAMLに保存された固定`value`へ`ge`/`gt`/`le`/`lt`/`always`を適用する。`quantile`は較正由来のmetadataであり、runtimeがその場でpercentileを計算する方式ではない。

### 1.4 既存の較正ツール

- `Delta_Engine_Pro4web/tools/calibrate_refs.py`
  - `_nearest_rank_percentile`: 46行
  - `load_bars`: 54行
  - `recommend_min_volume`: 112行
  - `recommend_stack_ref`: 125行
  - `_write_yaml_key`: 153行
  - `main`: 181行。`--write`は186行で明示指定した場合だけ設定を書き、defaultはdry-run。
- `Delta_Engine_Pro4web/tools/calibrate_cvd.py`
  - `_nearest_rank_percentile`: 43行
  - `compute_slope_ref`: 52行
  - `_write_signal_cvd_slope_ref`: 83行
  - `main`: 109行。`--write`は114/141-145行で明示指定した場合だけ設定を書き、defaultはdry-run。
- `tools/`配下にHook candidate全体を対象にした既存較正スクリプトはなかった。今回`tools/calibrate_hooks.py`を追加する。

### 1.5 収録データの構造と適用可能性

調査時点の実ファイル:

- root: `Delta_Engine_Pro4web/data_05M/hook_observer/campaigns/stage2a_20260726_xz/full`
- session directory: 29件
- 最初: `session-20260726T041939.403610Z-1e9ed663`
- 最後: `session-20260729T012627.280594Z-31c7f85a`
- 正常終了（summaryとSESSION_ENDあり）: 17件
- summary未作成/crash-incomplete: 12件
- `FRAME_COMMIT`あり: 25件
- `JournalReplay(..., allow_active=True, allow_invalid=True)`で先頭確定recordを検証できたsession: 28件
- 読めないsession: 最初の1件。旧segmentに`SEGMENT_CLOSE`がなく、`JournalIntegrityError: segment is not closed: raw-20260726T04.jsonl.xz`。
- 検出した未確定tail: `session-20260727T210042.013438Z-ea8611be`の24,860 bytes。確定frameだけを読み、tailは読まない。

frame payloadの実測種類:

- `DEPTH_SNAPSHOT`: `e=depthSnapshot`、`s/E/u/b/a`
- `DEPTH_UPDATE`: `e=depthUpdate`、`s/E/T/U/u/pu/b/a`
- `TRADE`: `e=trade`、`s/E/T/t/p/q/m/X/st`

full stream journalにはOpen Interest sample、liquidation、事前計算済みcandle、Flow Response snapshotは含まれない。したがって:

- A01-A24: depthとtradeから既存DOM detectorを実行可能。
- C03-C08: absorptionおよびwall/tradeの既存入力を再構成して実行する。absorption breakは、既存episodeの価格帯を反対側へ抜けた最初のtradeで明示する。
- D06-D08: tradeから既存`FlowPriceResponseDetector`でsnapshotを再構成して実行可能。
- F01-F05: Open Interest sampleがraw journalにないため実測不能。0件として記録する。
- G01-G11: tradeから既存`CvdCalculator`で1m closed candleを再構成して実行可能。

較正driverの固定パラメータ:

- DOM depth levels: 50（`DomFeatureCache` default）
- DOM initial sync: production `OrderBookStateManager`と同じくREST snapshot後の最初のnon-stale diffを許容し、その後は`pu/U` continuityとgap resetを適用する。独立研究用`DomDataQualityGate`のstrict初回alignmentは実収録で全diffをINVALIDにするため使用しない。
- iceberg episode window: 5,000 ms（Stage 2B test参照）
- flow transition aligned windows: 2（Stage 2B test参照）
- price structure: lookback 10 bars、timeframe 60 sec、round increment 50、volume node bin 1（Stage 2B test参照）
- Flow Response: `config/config.yaml` 131-140行の現行production値
- absorption: `config/config.yaml` 64-68行の現行production値

## Phase 2: 分布集計

### 2.1 実装

`Delta_Engine_Pro4web/tools/calibrate_hooks.py`を追加した。

- defaultはdry-runであり、`--write` optionおよびYAML/config書込み経路は実装していない。
- `JournalReplay(..., allow_active=True, allow_invalid=True)`で確定frameだけをsession単位に逐次処理する。
- session境界でnormalizer、book、detectorのstateをresetする。
- candidate valueは一時DuckDBの`DECIMAL(38,18)`へbatch insertし、メモリへ全件保持しない。
- sessionごとにtransactionを張り、失敗sessionはrollbackして部分candidateを残さない。
- 2 workerは別々の一時DBを使用し、完了後に`UNION ALL`した全candidateへ`quantile_cont`を適用する。
- percentileはlinear interpolation、標準偏差はpopulation standard deviation。
- E01-E06/C09は明示的対象外。Open Interest recordが存在しないF01-F05は擬似値を作らずcount=0とする。

### 2.2 実行結果

実行コマンド（`Delta_Engine_Pro4web`から）:

```powershell
python tools/calibrate_hooks.py --progress-every 250000 --jobs 2 --output-json C:\tmp\stage2c2_hook_distribution_full_v6_20260730.json
```

実行概要:

- 開始: 2026-07-30 12:42:47 JST
- 結果生成: 2026-07-30 14:48:33 JST
- elapsed: 7,546.974 sec
- dry-run: `true`
- discovered/selected: 29/29 session
- succeeded/failed: 28/1 session
- 成功sessionのrecord総数: 9,054,572
- candidate value総数: 15,667,491
- record type: `DEPTH_SNAPSHOT=71`、`DEPTH_UPDATE=2,289,444`、`TRADE=6,765,056`、`RAW=1`
- 入力manifest集合SHA-256: `f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b`
- limited run: `false`

失敗session:

| session | status | records | candidates | elapsed sec | error |
|---|---|---:|---:|---:|---|
| `session-20260726T041939.403610Z-1e9ed663` | ERROR | 0 | 0 | 0.004 | `JournalIntegrityError: segment is not closed: raw-20260726T04.jsonl.xz` |

このsessionのtransactionはrollbackした。残り28 sessionはすべて成功し、そのcandidateだけで以下を集計した。

### 2.3 Hook測定値分布

| Hook ID | count | min | max | mean | p50 | p5 | p10 | p25 | p75 | p90 | p95 | p99 | stddev |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A01 | 723556 | 2.9537864078 | 336034 | 1511.4508429992 | 885.4285714286 | 120.1497340426 | 175.8075396825 | 369.0515463918 | 1887.7142857143 | 3407.1428571429 | 4677.7625 | 8083.225 | 2659.1997445257 |
| A02 | 723265 | 3.0623869801 | 491187.5 | 1396.3809821597 | 862.1621621622 | 125 | 186.6090269151 | 381.568627451 | 1760 | 3161.5 | 4429 | 7177.3933333333 | 2790.3487979979 |
| A03 | 423212 | 0.000001281 | 1 | 0.2358072441 | 0.0415570076 | 0.0001057865 | 0.000181886 | 0.0013097309 | 0.3323780475 | 0.9480510776 | 0.99736234 | 1 | 0.3465671336 |
| A04 | 416832 | 0.0000010259 | 1 | 0.2459358459 | 0.0423037973 | 0.0001107733 | 0.0001956564 | 0.0014607908 | 0.3702451816 | 0.9582662537 | 0.9983945801 | 1 | 0.3538345426 |
| A05 | 935052 | 0.0000010992 | 0.9943042485 | 0.0773572444 | 0.0214034259 | 0.0001091227 | 0.0003496641 | 0.0030684327 | 0.0827550704 | 0.2257413037 | 0.3739310262 | 0.6920958425 | 0.1370113339 |
| A06 | 931297 | 8.85680756E-7 | 0.9938067788 | 0.0770940915 | 0.0193050193 | 0.0001076231 | 0.0003172725 | 0.0026096613 | 0.0829404575 | 0.230138894 | 0.3775149198 | 0.6841690574 | 0.1373521169 |
| A07 | 1011389 | 0.0000011172 | 205.5546075085 | 0.1445324117 | 0.0159551531 | 0.0000828253 | 0.0001967536 | 0.0018795387 | 0.0763396306 | 0.266824863 | 0.5544628084 | 2.2616277456 | 0.7527975385 |
| A08 | 1007302 | 8.49910844E-7 | 462.3717119448 | 0.1430770864 | 0.0141947187 | 0.0000840372 | 0.0001803752 | 0.001638877 | 0.0760487311 | 0.2759758466 | 0.5667374987 | 2.1548624903 | 1.0479319627 |
| A09 | 1194226 | 1 | 613.4444444444 | 3.8272044817 | 2.2669354268 | 1.0826580472 | 1.1708557807 | 1.481576932 | 3.9848677375 | 7.4475869641 | 11.437389558 | 25.462127852 | 5.7539621189 |
| A10 | 1080611 | 1.0000334079 | 2083.4295900178 | 3.7297427105 | 2.1736205539 | 1.0753804822 | 1.1558362192 | 1.4425898521 | 3.7036516854 | 6.6616221957 | 10.3767257821 | 27.4452092124 | 7.9835105105 |
| A11 | 41240 | 0.0152392215 | 13.7788601803 | 0.4455469282 | 0.3753398585 | 0.015751699 | 0.0474728538 | 0.1727076397 | 0.6156791942 | 0.8919830986 | 1.0921227261 | 1.7142725875 | 0.3941084431 |
| A12 | 40084 | 0.0152395466 | 13.1434158311 | 0.4580679433 | 0.3912785575 | 0.0156956217 | 0.0473879225 | 0.1854529902 | 0.6286053957 | 0.8975032953 | 1.1154654423 | 1.8049356739 | 0.4021435353 |
| A13 | 40302 | 0.0152395466 | 12.7600023005 | 0.455849595 | 0.3892688094 | 0.0156932054 | 0.0471388672 | 0.184569881 | 0.6280383119 | 0.8949303141 | 1.1106181983 | 1.7769951875 | 0.3986135793 |
| A14 | 41429 | 0.0152392215 | 10.5180697151 | 0.4431750629 | 0.3728233524 | 0.0157425799 | 0.0473444274 | 0.1725329165 | 0.61518539 | 0.8902801853 | 1.0902454579 | 1.6892219936 | 0.3818176828 |
| A15 | 41438 | 2.32234226E-8 | 12.7619141674 | 0.0060553485 | 5.98227121E-7 | 2.48814415E-8 | 9.36059710E-8 | 2.82226075E-7 | 0.0000010004 | 0.0000015227 | 0.0000022515 | 0.1228405659 | 0.0954297999 |
| A16 | 40251 | 2.32243427E-8 | 8.7168905701 | 0.0061442548 | 6.23078261E-7 | 2.46446025E-8 | 7.53361371E-8 | 2.95749622E-7 | 0.0000010167 | 0.0000015405 | 0.0000023584 | 0.1230732951 | 0.0859672907 |
| A17 | 285761 | 0.0001598977 | 81395 | 592.0452255738 | 40.48 | 0.125 | 0.4285714286 | 3 | 404 | 1644 | 3276 | 7700 | 1576.6255358009 |
| A18 | 316051 | 0.0002404424 | 105020 | 573.1311673387 | 44 | 0.1333333333 | 0.5 | 3.2 | 387.3333333333 | 1661 | 3275 | 7232 | 1490.1079433724 |
| A19 | 423212 | 1 | 775 | 26.0949784033 | 11 | 1 | 2 | 4 | 29 | 62 | 98 | 231.89 | 46.1058756601 |
| A20 | 416832 | 1 | 1439 | 31.0055705896 | 11 | 1 | 1 | 4 | 29 | 67 | 116 | 335 | 76.2500311336 |
| A21 | 2274837 | 0.0152679798 | 2.4463441754 | 0.055716766 | 0.0470884061 | 0.030901895 | 0.0310326021 | 0.0460713784 | 0.0626998066 | 0.0784677447 | 0.0937508057 | 0.1250436676 | 0.0209674108 |
| A22 | 2274837 | 0.0152959811 | 4.7663699887 | 0.0554945646 | 0.0470756231 | 0.0309089631 | 0.0310221568 | 0.046078667 | 0.062643738 | 0.0784220849 | 0.093162277 | 0.1235602337 | 0.0215924195 |
| A23 | 88938 | 0.0152265521 | 12.9713905315 | 0.491858904 | 0.4698078016 | 0.0157992534 | 0.0618600864 | 0.221291306 | 0.7426002863 | 0.914078283 | 1.0025646224 | 1.4712543629 | 0.3586689288 |
| A24 | 93831 | 0.0152370852 | 8.1877516839 | 0.4823720748 | 0.4550229434 | 0.0158315899 | 0.0618017847 | 0.2148994386 | 0.7385115845 | 0.9113299525 | 0.999825417 | 1.401433955 | 0.350023871 |
| C03 | 4 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 0 |
| C04 | 0 | — | — | — | — | — | — | — | — | — | — | — | — |
| C05 | 37 | 1 | 2 | 1.2432432432 | 1 | 1 | 1 | 1 | 1 | 2 | 2 | 2 | 0.4290407531 |
| C06 | 670740 | 0.0000010271 | 20.4595959596 | 0.0447045971 | 0.0020947681 | 0.0000914827 | 0.0001417133 | 0.0004068348 | 0.0120329817 | 0.0660099463 | 0.2091069222 | 1 | 0.1720987838 |
| C07 | 17627 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 0 |
| C08 | 17819 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 0 |
| D06 | 25 | 592 | 210704 | 13465.24 | 1010 | 836.4 | 866 | 959 | 1162 | 20556 | 62715.9999999999 | 176973.6799999997 | 42846.609112302 |
| D07 | 2039 | 45 | 73164 | 1185.8180480628 | 1018 | 535.8 | 702 | 894.5 | 1185 | 1465.2 | 1720.1 | 2581.72 | 2576.1607181723 |
| D08 | 63787 | 2 | 6 | 2.6317431452 | 2 | 2 | 2 | 2 | 3 | 4 | 4 | 5 | 0.8923393754 |
| F01 | 0 | — | — | — | — | — | — | — | — | — | — | — | — |
| F02 | 0 | — | — | — | — | — | — | — | — | — | — | — | — |
| F03 | 0 | — | — | — | — | — | — | — | — | — | — | — | — |
| F04 | 0 | — | — | — | — | — | — | — | — | — | — | — | — |
| F05 | 0 | — | — | — | — | — | — | — | — | — | — | — | — |
| G01 | 3935 | 0 | 71.4649620376 | 7.3663841919 | 5.0026329647 | 0.248436518 | 0.6629559612 | 1.9470099269 | 10.0655969738 | 15.8790121078 | 22.0333971613 | 44.6838634171 | 8.175195663 |
| G02 | 3935 | 0 | 56.7828955136 | 7.0287770548 | 4.3906782523 | 0.077506319 | 0.4339221152 | 1.5830629059 | 9.9865080038 | 17.1345938592 | 22.7031333562 | 34.1264608202 | 7.7204133527 |
| G03 | 620 | 0.0153109813 | 27.2211371361 | 3.0871687718 | 1.8533187546 | 0.1243023633 | 0.266238144 | 0.7916014768 | 3.7823844214 | 7.0508754708 | 10.8910329912 | 18.8583913736 | 3.8133100924 |
| G04 | 710 | 0.0153536718 | 45.6097689581 | 2.8169884568 | 1.7073661126 | 0.1083403126 | 0.2676265351 | 0.6655974338 | 3.5056890456 | 6.4573440178 | 9.8069218254 | 16.1241852466 | 3.6781913075 |
| G05 | 307 | 0 | 24.6410618655 | 3.7617802382 | 2.6156703271 | 0.2007974115 | 0.4976912568 | 1.1040254721 | 5.0839317662 | 8.5284948314 | 11.2992221518 | 17.1524641033 | 3.7510020219 |
| G06 | 334 | 0 | 29.0370717705 | 3.5293146511 | 2.2726072119 | 0.1785206538 | 0.3354969287 | 0.9158798109 | 4.592356749 | 8.1968877126 | 11.0435047903 | 18.7717305434 | 3.9808280597 |
| G07 | 3963 | 0.0000082522 | 113.0660228701 | 16.8955767969 | 11.5693597494 | 0.7132637849 | 1.505498512 | 4.2015995164 | 22.3579377306 | 35.113490544 | 63.6619611733 | 92.7170404361 | 18.7027427439 |
| G08 | 3963 | 0.0000082522 | 113.0660228701 | 16.8955767969 | 11.5693597494 | 0.7132637849 | 1.505498512 | 4.2015995164 | 22.3579377306 | 35.113490544 | 63.6619611733 | 92.7170404361 | 18.7027427439 |
| G09 | 3963 | 0 | 44.0409794413 | 4.9880899092 | 3.0952125274 | 0.0310381645 | 0.0923975332 | 0.8197482528 | 7.0403408992 | 12.5287637773 | 16.6591862633 | 26.5004259925 | 5.7593794519 |
| G10 | 3963 | 0 | 3.9290002824 | 1.9511509055 | 1.9577628455 | 0.1237639347 | 0.3699275117 | 0.9863014544 | 2.9606513893 | 3.4887781038 | 3.6907993936 | 3.852424312 | 1.1303908441 |
| G11 | 3935 | 0 | 43.268022915 | 4.0083224318 | 2.8259493182 | 0.1385520459 | 0.3896227886 | 1.1926939721 | 5.586606454 | 9.2906141325 | 11.9000713764 | 17.9471724845 | 3.9911987753 |

### 2.4 標本不足（count < 100）

- C03: 4
- C04: 0
- C05: 37
- D06: 25
- F01: 0
- F02: 0
- F03: 0
- F04: 0
- F05: 0

F01-F05が0件なのは、full journalに`OPEN_INTEREST` recordが存在しないためである。補間・擬似値は使用していない。

### 2.5 事後状態

- 2026-07-30 14:50:52 JST
- container: `delta_engine_pro4web-deltaengine_clone-1`、`Up 5 hours`
- health: `http://localhost:18080/api/health`は`GREEN`
- health主要値: sequence gap 0、WS reconnect 0、pipeline exception 0、event lag 69 ms、RSS 754 MB、tape dropped/pending/send_failures 0、balanced `true`
- C:空き: 93,106,585,600 bytes
- `localhost:8080`はport publish対象外のため接続不可。container publish先`localhost:18080`で確認した。
- container停止・再起動、収録停止、設定変更、収録データ変更は行っていない。

## 作業checkpoint

- checkpoint日時: 2026-07-30 14:56 JST
- 承認範囲: 指定full streamのread-only replay、`tools/calibrate_hooks.py`と本レポートの作成、指定2ファイルのみのcommit。
- 完了済み: PROJECT_MEMORY確認、dirty worktree確認、Phase 1調査、dry-run script実装、事前検証、全29 session replay、28成功/1失敗の継続処理、49 Hook分布表・標本不足・session error追記、事後container/health/disk確認、最終compile/test/統計表一致検証、指定2ファイルだけのstageと対象限定diff検証。
- 未完了: 指定messageでのcommit。
- 変更file: 本レポート、`Delta_Engine_Pro4web/tools/calibrate_hooks.py`。
- 検証結果:
  - `python -m py_compile tools/calibrate_hooks.py`: 成功。
  - 3 session選択/各1,000 record上限のsmoke: 1件は既知の未close error、2件成功、2,000 records、8,242 candidate values、A/C/D/G統計生成成功。
  - top-50 bounded snapshot最適化の前後で同一smoke入力の全統計が一致。成功session所要時間は約4秒から約1.5秒へ短縮。
  - replay用増分absorption実装を既存`AbsorptionDetector`と500 deterministic ticksで逐次比較し、result不一致0件、全5 internal counter一致。
  - sorted bounded-book index版を同一2,000 recordsで比較し、49 Hook全統計・candidate countが完全一致。
  - `--jobs 2`を同一2,000 recordsで`--jobs 1`と比較し、49 Hook全統計、全session status/count、candidate countが完全一致。defaultは1 worker。
  - replay用Flow snapshot prefix集計を既存`FlowPriceResponseDetector`と2,200 deterministic seconds（9,390 snapshots）で逐次比較し、snapshot不一致0件。18,954-record end-to-end統計も全件一致し、実時間45.7秒から22.7秒へ短縮。
  - `--write` optionは実装しておらず、threshold/config書込み経路はない。
  - 最終`python -m py_compile tools/calibrate_hooks.py`: 成功。
  - `python -m pytest tests/orderflow/test_stage2b_dom_detectors.py tests/orderflow/test_stage2b_context_detectors.py -q`: 14 passed。
  - レポートのHook統計行49件を最終run stdoutの49件と機械比較し、完全一致。
  - CLI helpはdry-run onlyを明記し、source検索でも`--write`/`args.write`/YAML書込み経路なし。
  - cached diffは本レポートと`tools/calibrate_hooks.py`の2ファイルのみ。`git diff --cached --check`成功。
- 長時間処理:
  - 旧実装の速度評価runはhost PID 7076のみを2026-07-30 11:44:24 JSTに終了。収録container/processは非操作。
  - 増分実装のsingle-worker速度評価run PID 20352は2026-07-30 12:04:15 JSTに終了。
  - 2 worker run（親8984、worker 7000/8220）はhealth endpointの5秒timeoutを検出して2026-07-30 12:09:46 JSTに全processを終了。
  - replay processを完全停止した状態でもhealth endpointは10秒timeout、container CPU約98%のままだった。containerはUpであり、禁止事項に従い停止・再起動・設定変更は行っていない。
  - single worker affinity評価run PID 8620は2026-07-30 12:23:47 JSTに終了。
  - 最終全29 session runを2026-07-30 12:42:47 JSTにhost親processと2 workerで開始。worker PID 13460/16944、priority `Idle`、processor affinity `4`/`8`（logical CPU 2/3へ個別固定）。
  - 同runは2026-07-30 14:48:33 JSTに完了。28/29 session成功、9,054,572 records、15,667,491 candidate values、elapsed 7,546.974 sec。
  - 開始前liquidation container health: GREEN。
  - 開始前C:空き: 93,296,570,368 bytes。
  - 完了後liquidation container health: GREEN。
  - 完了後C:空き: 93,106,585,600 bytes。
- blockerの限定範囲: 最初の1 sessionのみ。未close XZ segmentのため0 recordsでrollbackし、残り28 sessionの集計は完了。
- 次の再開位置: 本レポートを再stageし、指定messageでcommitする。
